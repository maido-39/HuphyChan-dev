"""Measure structural loads for a trained Pygmalion velocity policy (mjlab).

CPU-only rollout from a saved checkpoint -- decoupled from any GPU training run
(launcher sets ``CUDA_VISIBLE_DEVICES=""``), so training is never interrupted.

The policy is driven through a **scheduled command sweep that covers every
locomotion direction** the policy was domain-randomised over (forward/backward,
lateral L/R, turn L/R, diagonal, curved, stand). This captures the worst-case
load envelope, not just straight-line walking.

Output npz uses the **same key layout as the IsaacLab measure.py** so the same
plotting style applies (just different data):
  tau_<joint>, omega_<joint>, Pmech_<joint>, qpos_<joint>   (per actuated joint)
  Fx/Fy/Fz_<body>, Tx/Ty/Tz_<body>                          (cfrc_int reaction wrench)
  GRF_<foot>_{x,y,z,mag}                                     (cfrc_ext on foot bodies)
  time, base_height, cmd_vx, cmd_vy, cmd_wz                  (conditions)

Usage (always via uv; see measure_loads.sh for the CPU-isolated launcher):
    uv run python analysis/measure_loads.py \
        --task Mjlab-Velocity-Flat-Pygmalion \
        --run-dir logs/rsl_rl/pygmalion_velocity/2026-06-30_20-12-31 \
        --tag flat
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import time as _time

import mujoco
import numpy as np
import torch

import mjlab.tasks  # noqa: F401  (populates the task registry)
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

# Scheduled command sweep [vx (m/s), vy (m/s), wz (rad/s)] -- covers the full
# DR command space the policy trained on. Each command is held for
# --steps-per-cmd control steps. Documented verbatim in the report.
COMMAND_SCHEDULE: list[tuple[float, float, float]] = [
    (0.5, 0.0, 0.0), (1.0, 0.0, 0.0), (1.5, 0.0, 0.0),     # forward slow/med/fast
    (-0.5, 0.0, 0.0), (-1.0, 0.0, 0.0),                     # backward
    (0.0, 0.5, 0.0), (0.0, -0.5, 0.0),                      # lateral L/R
    (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),                      # lateral fast L/R
    (0.0, 0.0, 0.5), (0.0, 0.0, -0.5), (0.0, 0.0, 0.7),     # turn L/R
    (0.8, 0.5, 0.0), (0.8, -0.5, 0.0),                      # diagonal
    (0.8, 0.0, 0.5), (0.8, 0.0, -0.5),                      # curved (fwd+turn)
    (0.0, 0.0, 0.0),                                        # stand
]


def build_command_blocks(args):
    """Return [(vx, vy, wz, nsteps), ...] driving the rollout.

    Default: the fixed 18-command schedule. --wide-dr: deterministic extremes
    (full DR corners) then random samples over the whole training range until
    --steps, for broad-coverage statistics."""
    if not args.wide_dr:
        return [(vx, vy, wz, args.steps_per_cmd) for (vx, vy, wz) in COMMAND_SCHEDULE]
    rng = np.random.default_rng(0)
    n = args.resample
    blocks = [(*e, n) for e in (
        (2.0, 0, 0), (3.0, 0, 0), (-1.5, 0, 0), (0, 1.0, 0), (0, -1.0, 0),
        (0, 0, 0.7), (0, 0, -0.7), (2.0, 0, 0.7), (1.5, 1.0, 0), (1.5, -1.0, 0),
        (0, 0, 0))]
    total = sum(b[3] for b in blocks)
    while total < args.steps:
        if rng.random() < 0.1:
            vx, vy, wz = 0.0, 0.0, 0.0
        else:
            vx = round(float(rng.uniform(-2.0, 3.0)), 2)
            vy = round(float(rng.uniform(-1.0, 1.0)), 2)
            wz = round(float(rng.uniform(-0.7, 0.7)), 2)
        blocks.append((vx, vy, wz, n))
        total += n
    return blocks


def latest_checkpoint(run_dir: Path, min_age_s: float = 10.0) -> Path:
    """Highest-step ``model_*.pt`` that finished writing (skip files the trainer
    may still be flushing)."""
    now = _time.time()
    cands: list[tuple[int, Path]] = []
    for f in run_dir.glob("model_*.pt"):
        try:
            step = int(f.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        if now - f.stat().st_mtime < min_age_s:
            continue
        cands.append((step, f))
    if not cands:
        raise FileNotFoundError(f"No settled model_*.pt in {run_dir}")
    cands.sort()
    return cands[-1][1]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", default="Mjlab-Velocity-Flat-Pygmalion")
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--checkpoint", type=Path, default=None)
    p.add_argument("--tag", default="flat", help="output basename, e.g. flat/rough")
    p.add_argument("--device", default="cpu")
    p.add_argument("--steps-per-cmd", type=int, default=150)
    p.add_argument("--warmup", type=int, default=120)
    p.add_argument("--wide-dr", action="store_true",
                   help="sample commands randomly over the FULL training DR range "
                        "(vx[-2,3], vy[-1,1], yaw[-0.7,0.7]) for a long rollout, for "
                        "broad-coverage statistics/histograms")
    p.add_argument("--steps", type=int, default=7200,
                   help="total recorded steps in --wide-dr mode")
    p.add_argument("--resample", type=int, default=120,
                   help="steps each command is held in --wide-dr mode")
    p.add_argument("--out-dir", type=Path, default=Path("analysis/out"))
    p.add_argument("--blind", action="store_true",
                   help="drop height_scan obs so a flat-trained (45-dim) policy "
                        "runs on the rough task blind (obs-dim match)")
    p.add_argument("--rough-terrain", action="store_true",
                   help="force a uniformly ROUGH terrain (no flat tiles) so the "
                        "robot actually traverses rough ground")
    args = p.parse_args()

    ckpt = args.checkpoint or latest_checkpoint(args.run_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_npz = args.out_dir / f"{args.tag}.npz"
    print(f"[measure] task={args.task} device={args.device} tag={args.tag}")
    print(f"[measure] checkpoint={ckpt}")

    env_cfg = load_env_cfg(args.task, play=True)
    env_cfg.scene.num_envs = 1
    if args.rough_terrain and env_cfg.scene.terrain is not None:
        from mjlab.terrains.config import (
            random_rough, random_spread_boxes, wave_terrain)
        from mjlab.terrains.terrain_generator import TerrainGeneratorCfg
        env_cfg.scene.terrain.terrain_type = "generator"
        env_cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
            size=(8.0, 8.0), border_width=5.0, num_rows=3, num_cols=3,
            curriculum=False,
            sub_terrains={
                "random_rough": random_rough(
                    proportion=0.5, noise_range=(0.03, 0.08), noise_step=0.01),
                "wave": wave_terrain(
                    proportion=0.3, amplitude_range=(0.04, 0.10), num_waves=5),
                "boxes": random_spread_boxes(
                    proportion=0.2, box_height_range=(0.04, 0.10), num_boxes=40),
            },
            add_lights=True,
        )
        print("[measure] --rough-terrain: uniform rough (no flat tiles)")
    if args.blind:
        for grp in ("actor", "critic"):
            terms = env_cfg.observations[grp].terms
            if "height_scan" in terms:
                del terms["height_scan"]
        print("[measure] --blind: height_scan obs removed (flat policy on rough)")
    agent_cfg = load_rl_cfg(args.task)

    env = ManagerBasedRlEnv(cfg=env_cfg, device=args.device)
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
    runner_cls = load_runner_cls(args.task) or MjlabOnPolicyRunner
    runner = runner_cls(env, asdict(agent_cfg), device=args.device)
    runner.load(str(ckpt), load_cfg={"actor": True}, strict=True,
                map_location=args.device)
    policy = runner.get_inference_policy(device=args.device)

    sim = env.unwrapped.sim
    mj = sim.mj_model
    # Save the COMPILED model (incl. this run's exact terrain heightfield) so the
    # offline renderer shows the robot on the real ground it walked on.
    mdl_path = args.out_dir / f"{args.tag}_model.mjb"
    mujoco.mj_saveModel(mj, str(mdl_path), None)
    print(f"[measure] saved model -> {mdl_path}")

    # Index actuated (scalar) joints; skip the base free joint.
    joints = []
    for j in range(mj.njnt):
        if mj.jnt_type[j] in (mujoco.mjtJoint.mjJNT_FREE, mujoco.mjtJoint.mjJNT_BALL):
            continue
        nm = mujoco.mj_id2name(mj, mujoco.mjtObj.mjOBJ_JOINT, j)
        joints.append({
            "name": (nm or f"joint{j}").split("/")[-1],  # strip "robot/" prefix
            "dof": int(mj.jnt_dofadr[j]),
            "qadr": int(mj.jnt_qposadr[j]),
        })
    bodies = []
    for b in range(1, mj.nbody):
        nm = mujoco.mj_id2name(mj, mujoco.mjtObj.mjOBJ_BODY, b) or f"body{b}"
        bodies.append({"name": nm.split("/")[-1], "id": b})
    feet = [b for b in bodies if b["name"] in ("L_foot_link", "R_foot_link")]
    print(f"[measure] joints={[j['name'] for j in joints]}")
    print(f"[measure] feet for GRF={[f['name'] for f in feet]}")

    def set_cmd(vx, vy, wz):
        env.unwrapped.command_manager.get_command("twist")[:] = torch.tensor(
            [[vx, vy, wz]], device=args.device)

    obs, _ = env.reset()
    for _ in range(args.warmup):
        set_cmd(0.5, 0.0, 0.0)
        obs = env.get_observations()
        with torch.no_grad():
            act = policy(obs)
        obs, _, _, _ = env.step(act)

    # Probe cfrc_int / cfrc_ext availability on the warp CPU backend.
    # cfrc_int/cfrc_ext only include CONTACT forces if rne_postconstraint runs
    # (gated on a sensor in mujoco_warp). Verify the warp path includes contacts
    # by cross-checking foot GRF against an independent CPU recompute
    # (mj_rnePostConstraint ALWAYS includes contacts); fall back to CPU if not.
    use_cpu_wrench = float(np.abs(sim.data.cfrc_int[0].clone().cpu()).max()) < 1e-9
    if not use_cpu_wrench and feet:
        chk = mujoco.MjData(mj)
        chk.qpos[:] = np.asarray(sim.data.qpos[0].clone().cpu())
        chk.qvel[:] = np.asarray(sim.data.qvel[0].clone().cpu())
        chk.ctrl[:] = np.asarray(sim.data.ctrl[0].clone().cpu())
        mujoco.mj_forward(mj, chk)
        mujoco.mj_rnePostConstraint(mj, chk)
        fb = feet[0]["id"]
        cpu_fz = abs(float(chk.cfrc_ext[fb][5]))
        warp_fz = abs(float(sim.data.cfrc_ext[0][fb][5].clone().cpu()))
        if cpu_fz > 50.0 and warp_fz < 0.5 * cpu_fz:
            use_cpu_wrench = True
            print(f"[measure] ⚠ warp cfrc missing contacts (footFz warp {warp_fz:.0f} "
                  f"<< cpu {cpu_fz:.0f} N) → CPU recompute")
        else:
            print(f"[measure] contact-incl OK: footFz warp {warp_fz:.0f} ~ cpu {cpu_fz:.0f} N")
    md = mujoco.MjData(mj) if use_cpu_wrench else None
    print(f"[measure] wrench source = {'CPU-recompute' if use_cpu_wrench else 'warp'}")

    rec: dict[str, list] = {**{f"tau_{j['name']}": [] for j in joints},
                            **{f"omega_{j['name']}": [] for j in joints},
                            **{f"Pmech_{j['name']}": [] for j in joints},
                            **{f"qpos_{j['name']}": [] for j in joints}}
    for b in bodies:
        for ax in ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz"):
            rec[f"{ax}_{b['name']}"] = []
    for f in feet:
        for ax in ("x", "y", "z", "mag"):
            rec[f"GRF_{f['name']}_{ax}"] = []
    rec["time"] = []
    rec["base_height"] = []
    rec["qpos_full"] = []  # (T, nq) full state for offline rendering
    for c in ("cmd_vx", "cmd_vy", "cmd_wz"):
        rec[c] = []

    dt = float(env.unwrapped.step_dt)
    blocks = build_command_blocks(args)
    print(f"[measure] {len(blocks)} command blocks, "
          f"{sum(b[3] for b in blocks)} steps, wide_dr={args.wide_dr}")
    step_i = 0
    for (vx, vy, wz, nblk) in blocks:
        for _ in range(nblk):
            set_cmd(vx, vy, wz)
            obs = env.get_observations()
            with torch.no_grad():
                act = policy(obs)
            obs, _, _, _ = env.step(act)

            qfrc = np.asarray(sim.data.qfrc_actuator[0].clone().cpu())
            qvel = np.asarray(sim.data.qvel[0].clone().cpu())
            qpos = np.asarray(sim.data.qpos[0].clone().cpu())
            if use_cpu_wrench:
                md.qpos[:] = qpos
                md.qvel[:] = qvel
                md.ctrl[:] = np.asarray(sim.data.ctrl[0].clone().cpu())
                mujoco.mj_forward(mj, md)
                mujoco.mj_rnePostConstraint(mj, md)
                cint = md.cfrc_int.copy()
                cext = md.cfrc_ext.copy()
            else:
                cint = np.asarray(sim.data.cfrc_int[0].clone().cpu())
                cext = np.asarray(sim.data.cfrc_ext[0].clone().cpu())

            for j in joints:
                tau = float(qfrc[j["dof"]])
                om = float(qvel[j["dof"]])
                rec[f"tau_{j['name']}"].append(tau)
                rec[f"omega_{j['name']}"].append(om)
                rec[f"Pmech_{j['name']}"].append(tau * om)
                rec[f"qpos_{j['name']}"].append(float(qpos[j["qadr"]]))
            for b in bodies:
                w = cint[b["id"]]
                rec[f"Tx_{b['name']}"].append(float(w[0]))
                rec[f"Ty_{b['name']}"].append(float(w[1]))
                rec[f"Tz_{b['name']}"].append(float(w[2]))
                rec[f"Fx_{b['name']}"].append(float(w[3]))
                rec[f"Fy_{b['name']}"].append(float(w[4]))
                rec[f"Fz_{b['name']}"].append(float(w[5]))
            for f in feet:
                fe = cext[f["id"]]
                fx, fy, fz = float(fe[3]), float(fe[4]), float(fe[5])
                rec[f"GRF_{f['name']}_x"].append(fx)
                rec[f"GRF_{f['name']}_y"].append(fy)
                rec[f"GRF_{f['name']}_z"].append(fz)
                rec[f"GRF_{f['name']}_mag"].append((fx**2 + fy**2 + fz**2) ** 0.5)
            rec["time"].append(step_i * dt)
            rec["base_height"].append(float(qpos[2]))
            rec["qpos_full"].append(qpos.copy())
            rec["cmd_vx"].append(vx)
            rec["cmd_vy"].append(vy)
            rec["cmd_wz"].append(wz)
            step_i += 1

    env.close()
    np.savez_compressed(out_npz, **{k: np.asarray(v) for k, v in rec.items()})
    print(f"[measure] {step_i} steps ({step_i * dt:.1f}s) -> {out_npz}")


if __name__ == "__main__":
    main()
