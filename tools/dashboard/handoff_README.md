# Pygmalion v3 (3D-printed lower body) — robot model handoff, 2026-08-23

Repo: github.com/maido-39/HuphyChan-dev @ `07a398a` (main). The mjlab-side Python lives in the `mujoco-sim/mjlab`
submodule whose commits are local (not on a remote) — the relevant files are copied here under `mjlab_pygmalion/`.
The STL meshes (75 MB) are git-ignored, so they are included here instead.

## Files
| path | what |
|---|---|
| `mjcf/pygmalion_v3_printed.xml` | serial-ankle MJCF (RP / legacy). `mujoco.MjModel.from_xml_path()` loads it (meshes in `assets_v2/`). 18 joints incl. waist/shoulders; training welds the upper body (see below) |
| `mjcf/pygmalion_v3_printed_loop.xml` | closed-loop 2-RSU ankle MJCF (AB): cranks, push rods (universal hinges), 4 `connect` equalities (solimp 0.999), passive ankle hinges |
| `urdf/*.urdf` | same robots as URDF trees (the loop URDF has crank→dummy→rod chains; closure noted in a comment). Cross-checked against the MJCF with MuJoCo's own URDF parser: 0.0000 mm (`*_urdf_crosscheck.json`) |
| `ankle_rp_envelope.json` | RP-mode pose-dependent torque envelope from the loop IK/FK (grid, Jc^T, M, extents, reflected motor params) |
| `pygmalion_v3_printed_loop_bent.json` | loop-consistent bent keyframe (closure 0.001 mm) |
| `mjlab_pygmalion/` | `pygmalion_constants.py` (actuators, gains, toggles, arm weld), `ankle_rp_actuator.py`, `tn_actuator.py`, `env_cfgs.py` (rewards/curricula) |
| `run_configs/ankle{AB,RP}_c2/` | the exact `env.yaml` / `agent.yaml` of the two runs now training |
| `motor_spec/` | measured RS03/RS04 T-N curves (48 V) and overload tables |
| `docs/` | 90 (pipeline + DR), 91 (closed loop), 92 (AB/RP setup, motor params, arms) |

## What the training model does on top of the XML (pygmalion_constants.get_spec)
- upper body (waist_yaw, shoulder pitch/roll) joints deleted = welded; arms abducted 15 deg first (`PYG_ARM_ABD_DEG`), arm–hip contact excludes removed
- `PYG_ANKLE_MODE=AB` → loop XML, crank actuators; `RP` → serial XML + `AnkleRpTnActuator`; unset → legacy serial
- measured motor params (`PYG_MOTOR_MEAS`, default on): RS04 armature 0.016333 / damping 0.009492 / frictionloss 0.269456; RS03 0.015265 / 0.022342 / 0.285370 (output shaft). RP ankle hinges get the loop-reflected values (pitch 0.0209/0.0306/0.472, roll 0.0153/0.0223/0.403)
- T-N curve clamp (`PYG_TN`, default on): Python PD per substep, motoring quadrant limited by the csv curve

## Gains in the running A/B (both arms identical except the ankle)
| joint | Kp [N*m/rad] | Kd [N*m*s/rad] | effort cap | motor |
|---|---|---|---|---|
| hip_pitch, hip_roll | 150 | 6 | 120 (T-N) | RS04 |
| hip_yaw | 150 | 6 | 60 (T-N) | RS03 |
| knee | 220 | 6 | 120 (T-N) | RS04 |
| AB: crank_A/B (per leg) | 22.3 | 1.41 | 60 (T-N) | RS03 — ankle-equivalent 28.5 / 1.81 through the lever |
| RP: ankle_pitch / ankle_roll | 28.5 | 1.81 | crank-space clamp ±60 + T-N (≈ pitch 98 / roll 84 N*m at centre, pose dependent) | 2×RS03 |
Action scale 0.25 rad per unit, control 50 Hz (dt 5 ms × 4). Joint ranges: hip_pitch −120/+25°, hip_roll −85/+25°, hip_yaw ±45°, knee −120/0°, ankle pitch −50/+30°, roll ±20°; soft-limit factor 0.9.

## Things worth an independent check
1. Mass/COM/inertia per link vs the CAD export (printed parts at measured density, docs/89). `total 35.35 kg`.
2. The loop geometry (crank axes, rod lengths A 289.0 / B 195.0 mm, ball positions) against the CAD — `loop_ankle_transmission.png` is the simulated map.
3. Motor params are assumed OUTPUT-shaft values (rotor+gear). If the bench values were rotor-side they need ×gear².
4. Collision: fitted capsules per link + box sole; adjacent-only excludes. A web viewer of exactly these geoms: `tools/collision_viewer/` in the repo.
