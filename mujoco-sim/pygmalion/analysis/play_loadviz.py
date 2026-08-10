"""Play a trained Pygmalion policy with LIVE per-JOINT load-colour spheres.

Same indicator scheme as the offline video (render_loads.py): a coloured sphere
at each joint, recoloured every control step by that joint's torque saturation:

    |tau| < rated      -> grey      |tau| >= 0.75*peak -> YELLOW
    |tau| >= 0.90*peak -> RED

The spheres are injected as massless, non-colliding geoms into the robot spec
(one per actuated joint, at the joint anchor; ankle_pitch lifted up the shin),
so BOTH viewers render them; colour is driven via per-world geom_rgba, which the
native and viser viewers sync into the rendered model every frame.

Contact force measurement
-------------------------
Pass ``--contact-out <path.npz>`` to record per-step foot-ground contact forces.
The file will contain:
  - ``time``     [T]        simulation time (s)
  - ``lf_force`` [T, 3]    left foot net contact force  (N, global frame)
  - ``rf_force`` [T, 3]    right foot net contact force (N, global frame)
  - ``lf_fz``   [T]        left foot vertical force magnitude
  - ``rf_fz``   [T]        right foot vertical force magnitude

Usage:
    uv run python analysis/play_loadviz.py --run-dir <run>           # flat
    uv run python analysis/play_loadviz.py --run-dir <run> \
        --task Mjlab-Velocity-Rough-Pygmalion --blind --rough-terrain  # rough
    uv run python analysis/play_loadviz.py --run-dir <run> --selftest 200  # headless check
    uv run python analysis/play_loadviz.py --run-dir <run> \
        --contact-out /tmp/v3_contacts.npz                            # record forces
"""

from __future__ import annotations

import argparse
import os
import time as _time
from dataclasses import asdict
from pathlib import Path

import mujoco
import numpy as np
import torch

import mjlab.tasks  # noqa: F401
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.viewer import NativeMujocoViewer, ViserPlayViewer

# Torque limits: (peak_Nm, rated_Nm) per joint keyword.
# These are read from the MuJoCo model at runtime when --auto-limits is set;
# the values below are used as fallback for joints not found in the model.
# v1-v5 ankle_roll = 14 N·m (RS00)
# v6    ankle_roll = 60 N·m (RS03)
# v7    ankle_roll = 120 N·m (A/B 2×RS03)
SPEC = {
    "hip_pitch":   (120.0, 40.0),
    "hip_roll":    (120.0, 40.0),
    "hip_yaw":     ( 60.0, 20.0),
    "knee":        (120.0, 40.0),
    "ankle_pitch": ( 60.0, 20.0),
    "ankle_roll":  ( 14.0,  5.0),  # overridden at runtime from model actfrcrange
}
JOINT_OFFSET = {"ankle_pitch": 0.08}  # lift sphere up the shin (above ankle)
LEVEL_COLOUR = {
    0: (0.55, 0.59, 0.64, 1.0),  # grey   : < 75 %
    1: (0.97, 0.86, 0.0,  1.0),  # yellow : >= 75 %
    2: (0.95, 0.05, 0.05, 1.0),  # red    : >= 90 %
}

# ── Force-arrow constants ─────────────────────────────────────────────────────
# Foot-plate geom positions in the foot_link body frame (from XML).
#   foot1 = front/toe plate,  foot2 = rear/heel plate
_PLATE_POS = {
    "L": {"1": (-0.01, -0.122, -0.06), "2": (-0.01,  0.001, -0.06)},
    "R": {"1": ( 0.01, -0.122, -0.06), "2": ( 0.01,  0.001, -0.06)},
}
_PLATE_HALF_THICK = 0.01       # half-thickness of each foot plate (from XML size z)
_ARROW_INIT_HALF_H = 0.005     # initial tiny height while no contact (invisible-ish)
_ARROW_MAX_HALF_H  = 0.18      # half-height at max force  → 36 cm total arrow
_ARROW_MAX_FORCE   = 400.0     # N — force that produces the maximum arrow length
_ARROW_RADIUS      = 0.025     # shaft radius (thicker for visibility)

# Arrow base: (x, y, plate_bottom_z) per key "L1"/"L2"/"R1"/"R2"
# plate_bottom_z = pos[2] - _PLATE_HALF_THICK
_ARROW_BASE = {
    side + pid: (pos[0], pos[1], pos[2] - _PLATE_HALF_THICK)
    for side, plates in _PLATE_POS.items()
    for pid, pos in plates.items()
}

# force thresholds (N) → RGBA colour
_FORCE_COLOURS = [
    (  10.0, (0.0, 0.0, 0.0, 0.0)),          # no contact : invisible
    (  80.0, (0.20, 0.55, 1.00, 0.70)),       # light      : blue
    ( 250.0, (0.10, 0.90, 0.10, 0.85)),       # medium     : green
    ( 400.0, (1.00, 0.65, 0.00, 1.00)),       # heavy      : orange
    (float("inf"), (1.00, 0.10, 0.10, 1.00)), # very heavy : red
]


def force_colour(fz: float) -> tuple:
    for thresh, col in _FORCE_COLOURS:
        if fz < thresh:
            return col
    return _FORCE_COLOURS[-1][1]


def spec_for(name):
    for k, v in SPEC.items():
        if k in name:
            return v
    return None


def severity(tau_abs, peak, rated):
    if tau_abs >= 0.90 * peak:
        return 2  # red
    if tau_abs >= 0.75 * peak:
        return 1  # yellow
    return 0      # grey


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


def add_force_arrow_geoms(spec) -> None:
    """Inject 4 cylinder geoms (one per foot plate) for force visualisation."""
    for body in spec.bodies:
        bname = body.name
        if "L_foot_link" in bname:
            side = "L"
        elif "R_foot_link" in bname:
            side = "R"
        else:
            continue
        for pid, pos in _PLATE_POS[side].items():
            g = body.add_geom()
            g.name  = f"farrow_{side}{pid}"
            g.type  = mujoco.mjtGeom.mjGEOM_CYLINDER
            # Cylinder local +Z points upward in body frame.
            # Place centre below the plate so arrow grows DOWNWARD from the
            # plate bottom:  top = plate_bottom, bottom = plate_bottom - 2*half_h
            plate_bottom_z = pos[2] - _PLATE_HALF_THICK
            g.pos   = [pos[0], pos[1], plate_bottom_z - _ARROW_INIT_HALF_H]
            g.size  = [_ARROW_RADIUS, _ARROW_INIT_HALF_H, 0.0]
            g.rgba  = [0.0, 0.0, 0.0, 0.0]   # initially invisible
            g.contype     = 0
            g.conaffinity = 0
            g.density     = 0.0
            g.group       = 0


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
    p.add_argument("--contact-out", type=Path, default=None,
                   help="Save per-step foot-ground contact forces to this .npz file")
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

    # ── Contact force sensor (always initialised for arrow display) ───────────
    _contact_sensor = None
    try:
        _contact_sensor = env.unwrapped.scene["feet_ground_contact"]
        print(f"[loadviz] contact sensor OK: {list(_contact_sensor.primary_names)}")
    except (KeyError, AttributeError) as e:
        print(f"[loadviz] WARNING: feet_ground_contact not found ({e}); arrows disabled")

    # ── Force-arrow geom IDs ──────────────────────────────────────────────────
    arrow_ids: dict[str, int] = {}
    for g in range(m.ngeom):
        gn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if "farrow_" in gn:
            key = gn.split("farrow_")[-1]  # e.g. "L1", "L2", "R1", "R2"
            arrow_ids[key] = g
    print(f"[loadviz] force-arrow geoms: {arrow_ids}")

    # Ankle-pitch qpos addresses for front/rear force split
    _ankle_qposadr: dict[str, int] = {}
    for side, jname in (("L", "L_ankle_pitch_joint"), ("R", "R_ankle_pitch_joint")):
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"robot/{jname}")
        if jid < 0:
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname)
        if jid >= 0:
            _ankle_qposadr[side] = int(m.jnt_qposadr[jid])

    # ── Contact force recorder ────────────────────────────────────────────────
    _contact_primary_names: list[str] = []
    _contact_time: list[float] = []
    _contact_lf: list[list[float]] = []
    _contact_rf: list[list[float]] = []

    if args.contact_out is not None and _contact_sensor is not None:
        _contact_primary_names = list(_contact_sensor.primary_names)
        print(f"[loadviz] contact forces will be saved to: {args.contact_out}")

    def _record_contact(step_time: float) -> None:
        """Append per-foot net contact force for env_idx=ei at this step."""
        if _contact_sensor is None:
            return
        data = _contact_sensor.data
        if data is None or data.force is None:
            return
        # force shape: [B, 2, 3]  (B=num_envs, 2 primaries, xyz)
        lf = data.force[ei, 0].tolist()   # left foot
        rf = data.force[ei, 1].tolist()   # right foot
        _contact_time.append(step_time)
        _contact_lf.append(lf)
        _contact_rf.append(rf)

        # Print every 50 steps (≈1.5 s wall-clock at 33 Hz policy)
        if len(_contact_time) % 50 == 1:
            lfz = abs(lf[2])
            rfz = abs(rf[2])
            print(
                f"[contact] t={step_time:6.2f}s  "
                f"L-foot Fz={lfz:7.1f} N  R-foot Fz={rfz:7.1f} N  "
                f"(total={lfz+rfz:.1f} N)"
            )

    def _save_contact_npz() -> None:
        if not _contact_time or args.contact_out is None:
            return
        out = args.contact_out
        out.parent.mkdir(parents=True, exist_ok=True)
        lf_arr = np.array(_contact_lf, dtype=np.float32)
        rf_arr = np.array(_contact_rf, dtype=np.float32)
        np.savez_compressed(
            out,
            time=np.array(_contact_time, dtype=np.float32),
            lf_force=lf_arr,
            rf_force=rf_arr,
            lf_fz=np.abs(lf_arr[:, 2]),
            rf_fz=np.abs(rf_arr[:, 2]),
        )
        t = np.array(_contact_time, dtype=np.float32)
        lf_fz = np.abs(lf_arr[:, 2])
        rf_fz = np.abs(rf_arr[:, 2])
        in_contact = (lf_fz > 1.0) | (rf_fz > 1.0)
        print(f"\n[contact] Saved {len(t)} steps → {out}")
        print(f"[contact] Left  foot Fz : mean={lf_fz[in_contact].mean():.1f} N  "
              f"max={lf_fz.max():.1f} N  stance_pct={in_contact.mean()*100:.1f}%")
        print(f"[contact] Right foot Fz : mean={rf_fz[in_contact].mean():.1f} N  "
              f"max={rf_fz.max():.1f} N")

    # Build dof → peak torque map from model's actfrcrange (set by effort_limit).
    # This automatically reflects per-version torque limits (v6: ankle_roll=60,
    # v7: ankle_roll/pitch=120) without any hardcoded SPEC overrides.
    dof_peak: dict[int, float] = {}
    for a in range(m.nu):
        adr = int(m.actuator_trnid[a, 0])
        trntype = int(m.actuator_trntype[a])
        if trntype != mujoco.mjtTrn.mjTRN_JOINT:
            continue
        peak = float(m.actuator_forcerange[a, 1])
        if peak <= 0.0:
            # fallback: read from jnt_actfrcrange
            dof = int(m.jnt_dofadr[adr])
            peak_jnt = float(m.jnt_actfrcrange[adr, 1])
            peak = peak_jnt if peak_jnt > 0.0 else 120.0
        dof = int(m.jnt_dofadr[adr])
        # keep the maximum across actuators sharing the same dof
        dof_peak[dof] = max(dof_peak.get(dof, 0.0), peak)

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
            dof = int(m.jnt_dofadr[jid])
            # Use model-derived peak; fall back to SPEC if not found
            fallback = spec_for(jn)
            peak = dof_peak.get(dof, fallback[0] if fallback else 120.0)
            rated = fallback[1] if fallback else peak * 0.33
            ind.append((g, dof, peak, rated))

    print(f"[loadviz] indicator spheres: {len(ind)}  checkpoint: {ckpt.name}")
    for _, dof, pk, _ in ind:
        # find joint name for this dof for logging
        for j in range(m.njnt):
            if m.jnt_dofadr[j] == dof:
                jname = (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) or "").split("/")[-1]
                print(f"  {jname:<30} peak={pk:.1f} N·m")
                break

    sim.expand_model_fields(("geom_rgba", "geom_size", "geom_pos"))

    def colourise():
        qfrc = sim.data.qfrc_actuator
        for g, dof, pk, rt in ind:
            col = LEVEL_COLOUR[severity(abs(float(qfrc[ei, dof])), pk, rt)]
            sim.model.geom_rgba[ei, g] = torch.tensor(col, device=sim.device)
        _record_contact(float(sim.data.time[ei]))

        # ── Force arrows: per-plate contact force visualisation ──────────────
        if _contact_sensor is not None and arrow_ids:
            fd = _contact_sensor.data
            if fd is not None and fd.force is not None:
                # fd.force: [B, 2, 3] — index 0=left, 1=right
                lf_fz = abs(float(fd.force[ei, 0, 2]))
                rf_fz = abs(float(fd.force[ei, 1, 2]))

                # Split total Fz between front(1) and rear(2) plates using ankle
                # pitch angle.  Positive pitch = toes-up = weight shifts rearward.
                def _split(fz_total: float, side: str):
                    adr = _ankle_qposadr.get(side)
                    pitch = float(sim.data.qpos[ei, adr]) if adr is not None else 0.0
                    # front_frac in [0.20, 0.80]
                    front_frac = max(0.20, min(0.80, 0.50 - pitch * 1.5))
                    return fz_total * front_frac, fz_total * (1.0 - front_frac)

                lf1, lf2 = _split(lf_fz, "L")
                rf1, rf2 = _split(rf_fz, "R")

                for key, fz in (("L1", lf1), ("L2", lf2), ("R1", rf1), ("R2", rf2)):
                    gid = arrow_ids.get(key)
                    if gid is None:
                        continue
                    # Arrow grows downward from plate bottom.
                    # top  = plate_bottom_z (fixed)
                    # bottom = plate_bottom_z - 2*half_h  (extends with force)
                    half_h = max(
                        _ARROW_INIT_HALF_H,
                        min(_ARROW_MAX_HALF_H, fz / _ARROW_MAX_FORCE * _ARROW_MAX_HALF_H),
                    )
                    ax, ay, pz = _ARROW_BASE[key]
                    sim.model.geom_size[ei, gid] = torch.tensor(
                        [_ARROW_RADIUS, half_h, 0.0], device=sim.device
                    )
                    sim.model.geom_pos[ei, gid] = torch.tensor(
                        [ax, ay, pz - half_h], device=sim.device
                    )
                    sim.model.geom_rgba[ei, gid] = torch.tensor(
                        force_colour(fz), device=sim.device
                    )

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
        names = {0: "grey", 1: "yellow (>75%)", 2: "red (>90%)"}
        print(f"[loadviz] selftest {args.selftest} steps OK; levels seen: "
              f"{sorted(names[s] for s in seen)}")
        _save_contact_npz()
        return

    resolved = args.viewer
    if resolved == "auto":
        has_disp = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        resolved = "native" if has_disp else "viser"
    print(f"[loadviz] viewer = {resolved}")
    try:
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
    finally:
        _save_contact_npz()
        env.close()


def _spec_with_inds(orig_spec_fn, radius):
    spec = orig_spec_fn()
    add_indicator_geoms(spec, radius)
    add_force_arrow_geoms(spec)
    return spec


if __name__ == "__main__":
    main()
