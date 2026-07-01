"""Play a trained Pygmalion policy with LIVE per-JOINT load-colour spheres.

Same indicator scheme as the offline video (render_loads.py): a coloured sphere
at each joint, recoloured every control step by that joint's torque saturation:

    |tau| < rated      -> grey      |tau| >= 0.70*peak -> ORANGE
    |tau| >= rated     -> YELLOW    |tau| >= peak      -> RED

The spheres are injected as massless, non-colliding geoms into the robot spec
(one per actuated joint, at the joint anchor; ankle_pitch lifted up the shin),
so BOTH viewers render them; colour is driven via per-world geom_rgba, which the
native and viser viewers sync into the rendered model every frame.

Usage:
    uv run python analysis/play_loadviz.py --run-dir <run>           # flat
    uv run python analysis/play_loadviz.py --run-dir <run> \
        --task Mjlab-Velocity-Rough-Pygmalion --blind --rough-terrain  # rough
    uv run python analysis/play_loadviz.py --run-dir <run> --selftest 200  # headless check
"""

from __future__ import annotations

import argparse
import os
import time as _time
from dataclasses import asdict
from pathlib import Path

import mujoco
import torch

import mjlab.tasks  # noqa: F401
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.viewer import NativeMujocoViewer, ViserPlayViewer

SPEC = {
    "hip_pitch": (120.0, 40.0), "hip_roll": (120.0, 40.0), "hip_yaw": (60.0, 20.0),
    "knee": (120.0, 40.0), "ankle_pitch": (60.0, 20.0), "ankle_roll": (14.0, 5.0),
}
JOINT_OFFSET = {"ankle_pitch": 0.08}  # lift sphere up the shin (above ankle)
LEVEL_COLOUR = {
    0: (0.55, 0.59, 0.64, 1.0), 1: (0.97, 0.86, 0.0, 1.0),
    2: (1.0, 0.50, 0.0, 1.0), 3: (0.95, 0.05, 0.05, 1.0),
}


def spec_for(name):
    for k, v in SPEC.items():
        if k in name:
            return v
    return None


def severity(tau_abs, peak, rated):
    if tau_abs >= peak:
        return 3
    if tau_abs >= 0.70 * peak:
        return 2
    if tau_abs >= rated:
        return 1
    return 0


def latest_checkpoint(run_dir: Path, min_age_s: float = 10.0) -> Path:
    now = _time.time()
    cands = []
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
    return sorted(cands)[-1][1]


def add_indicator_geoms(spec, radius: float) -> None:
    """Inject one massless sphere geom per actuated joint at its anchor."""
    for b in spec.bodies:
        for j in b.joints:
            sp = spec_for(j.name)
            if sp is None:
                continue
            jt = next(k for k in SPEC if k in j.name)
            g = b.add_geom()
            g.name = "ind_" + j.name
            g.type = mujoco.mjtGeom.mjGEOM_SPHERE
            g.size = [radius, 0.0, 0.0]
            pos = list(j.pos)
            pos[2] += JOINT_OFFSET.get(jt, 0.0)
            g.pos = pos
            g.rgba = [0.55, 0.59, 0.64, 1.0]
            g.contype = 0
            g.conaffinity = 0
            g.density = 0.0  # massless: no effect on dynamics
            g.group = 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", default="Mjlab-Velocity-Flat-Pygmalion")
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--checkpoint", type=Path, default=None)
    p.add_argument("--device", default="cpu")
    p.add_argument("--env-idx", type=int, default=0)
    p.add_argument("--radius", type=float, default=0.06)
    p.add_argument("--blind", action="store_true")
    p.add_argument("--rough-terrain", action="store_true")
    p.add_argument("--viewer", choices=["auto", "native", "viser"], default="auto")
    p.add_argument("--host", default="0.0.0.0",
                   help="viser bind host (0.0.0.0 = allow external connections)")
    p.add_argument("--port", type=int, default=8080, help="viser port")
    p.add_argument("--selftest", type=int, default=0)
    args = p.parse_args()

    ckpt = args.checkpoint or latest_checkpoint(args.run_dir)
    env_cfg = load_env_cfg(args.task, play=True)
    env_cfg.scene.num_envs = max(1, args.env_idx + 1)
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
    if args.blind:
        for grp in ("actor", "critic"):
            terms = env_cfg.observations[grp].terms
            if "height_scan" in terms:
                del terms["height_scan"]

    # Inject indicator spheres into the robot spec before the env compiles it.
    robot_cfg = env_cfg.scene.entities["robot"]
    orig_spec_fn = robot_cfg.spec_fn
    rad = args.radius
    robot_cfg.spec_fn = lambda: _spec_with_inds(orig_spec_fn, rad)

    agent_cfg = load_rl_cfg(args.task)
    env = ManagerBasedRlEnv(cfg=env_cfg, device=args.device)
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
    runner_cls = load_runner_cls(args.task) or MjlabOnPolicyRunner
    runner = runner_cls(env, asdict(agent_cfg), device=args.device)
    runner.load(str(ckpt), load_cfg={"actor": True}, strict=True, map_location=args.device)
    base_policy = runner.get_inference_policy(device=args.device)

    sim = env.unwrapped.sim
    m = sim.mj_model
    ei = args.env_idx

    # Map indicator geom id -> (joint dof, peak, rated).
    ind = []
    for g in range(m.ngeom):
        gn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if "ind_" not in gn:
            continue
        jn = gn.split("ind_")[-1]
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "robot/" + jn)
        if jid < 0:
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
        if jid >= 0:
            ind.append((g, int(m.jnt_dofadr[jid]), *spec_for(jn)))
    print(f"[loadviz] indicator spheres: {len(ind)}  checkpoint: {ckpt.name}")

    sim.expand_model_fields(("geom_rgba",))

    def colourise():
        qfrc = sim.data.qfrc_actuator
        for g, dof, pk, rt in ind:
            col = LEVEL_COLOUR[severity(abs(float(qfrc[ei, dof])), pk, rt)]
            sim.model.geom_rgba[ei, g] = torch.tensor(col, device=sim.device)

    def policy(obs):
        act = base_policy(obs)
        colourise()
        return act

    if args.selftest:
        env.reset()
        seen = set()
        for _ in range(args.selftest):
            obs = env.get_observations()
            with torch.no_grad():
                act = policy(obs)
            env.step(act)
            for g, dof, pk, rt in ind:
                seen.add(severity(abs(float(sim.data.qfrc_actuator[ei, dof])), pk, rt))
        env.close()
        names = {0: "grey", 1: "yellow", 2: "orange", 3: "red"}
        print(f"[loadviz] selftest {args.selftest} steps OK; levels seen: "
              f"{sorted(names[s] for s in seen)}")
        return

    resolved = args.viewer
    if resolved == "auto":
        has_disp = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        resolved = "native" if has_disp else "viser"
    print(f"[loadviz] viewer = {resolved}")
    if resolved == "native":
        NativeMujocoViewer(env, policy).run()
    else:
        import socket
        import viser
        server = viser.ViserServer(host=args.host, port=args.port, label="mjlab-loadviz")
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "<this-host-ip>"
        print(f"[loadviz] viser bound {args.host}:{args.port}  -> 외부접속: "
              f"http://{ip}:{args.port}  (또는 http://localhost:{args.port})")
        ViserPlayViewer(env, policy, checkpoint_manager=None, viser_server=server).run()
    env.close()


def _spec_with_inds(orig_spec_fn, radius):
    spec = orig_spec_fn()
    add_indicator_geoms(spec, radius)
    return spec


if __name__ == "__main__":
    main()
