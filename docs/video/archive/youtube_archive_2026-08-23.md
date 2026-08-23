# YouTube archive — Maido -A (@kirima), 2026-08-23 sim/design session

Channel title convention kept: `YYYYMMDD HHMMSS Huphy 1.0 - <topic>` (timestamp = render time). All clips ≥ 15 s, English captions burned in, real time unless the caption says otherwise. Files in `docs/video/archive/` — **filename = title** (YouTube picks the filename up as the default title).

---

## 1. `20260823 233958 Huphy 1.0 - 3DP lower body sim model turntable, collision capsules & hulls.mp4` (18 s)
**Title:** `20260823 233958 Huphy 1.0 - 3DP lower body sim model turntable, collision capsules & hulls`

**Description:**
MuJoCo model of the 3D-printed Huphy 1.0 lower body (35.35 kg, printed parts at measured PLA density) with the 2-RSU closed-loop ankle. Turntable switches layers: visual meshes → collision geometry (fitted capsule per link + box sole + loop sites) → collision only. Adjacent-link contact pairs excluded; everything else is a self-collision penalty in training. Arms welded 15 deg out (the hanging arm capsule overlapped the hip by 14 mm). Joint ranges from the CAD sweep: hip_yaw ±45, ankle pitch −50/+30, roll ±20 deg.
Tools: build_robot.py (URDF + MJCF from Fusion massprops), collision web viewer tools/collision_viewer.

## 2. `20260823 234224 Huphy 1.0 - 2-RSU closed-loop ankle in MuJoCo, AB crank drive + ground contact.mp4` (15.8 s)
**Title:** `20260823 234224 Huphy 1.0 - 2-RSU closed-loop ankle in MuJoCo, AB crank drive + ground contact`

**Description:**
The ankle as the real mechanism: two RS03 cranks, two push rods on universal hinges, four connect equalities closing on the foot, passive pitch/roll hinges. Cranks servoed (Kp 22.3 / Kd 1.41, ±60 N·m): co-actuation → foot pitch, differential → roll, then a circle; then on the ground the cranks tilt the sole onto its toe/heel/side edges (contact points + force arrows). Loop closure stays at 0.000 mm throughout. Three panels: whole body / ankle close-up / collision geometry. This is the AB-mode model used for RL training (mjlab, mujoco_warp).

## 3. `20260823 234140 Huphy 1.0 - RP-mode ankle torque envelope from the 2-RSU loop IK FK.mp4` (16 s, pose sweep)
**Title:** `20260823 234140 Huphy 1.0 - RP-mode ankle torque envelope from the 2-RSU loop IK FK`

**Description:**
For training on a serial (roll/pitch) ankle we need the torque the mechanism can actually deliver at each pose. Per grid point: crank IK on the closure equations, loop Jacobian Jc, feasible ankle torque = Jcᵀ·[±60, ±60] (parallelogram). Centre pose: pitch ±98 / roll ±84 N·m, shrinking to ±71 / ±50 at −48° plantarflex. RP training clamps the PD torque to this set in crank space (plus the measured RS03 torque-speed curve) — the same limit the hardware has. Left: loop posed on the ROM (cranks from IK). Right: feasible set at that pose.

## 4. `20260823 234427 Huphy 1.0 - RL AB test at iter 1200, closed-loop (AB) vs serial+envelope (RP) ankle.mp4` (21.6 s)
**Title:** `20260823 234427 Huphy 1.0 - RL AB test at iter 1200, closed-loop (AB) vs serial+envelope (RP) ankle`

**Description:**
Same reward, curriculum, masses, measured motor parameters (RS04/RS03 inertia, damping, Coulomb friction), torque-speed curves and bent init — only the ankle mechanism differs. Left: policy commands the two cranks (ankle passive through the rods). Right: serial ankle with the loop-envelope torque clamp. Checkpoint iter 1200/32000 (vx 0.8 m/s stage), commands 0.8 m/s, 0.8 + 0.5 lateral, −0.8 m/s. Captions show ankle pitch and the ankle torque in the common space (AB: Jcᵀτ_crank; RP: crank-equivalent). Early finding: AB moves the ankle 17° per stride with 12.8 N·m RMS, RP rails its ankle target (−40↔+35°) and saturates the PD — see docs/93.

## 5. `20260823 234705 Huphy 1.0 - URDF vs MJCF cross-check, joint sweeps overlaid.mp4` (34 s)
**Title:** `20260823 234705 Huphy 1.0 - URDF vs MJCF cross-check, joint sweeps overlaid`

**Description:**
The exported URDF read by MuJoCo's own URDF parser (red wireframe) overlaid on the MJCF (solid), every joint swept through its range. Joint axes, anchors, ranges, link positions over 200 random poses and per-link mass/COM/inertia all agree (0.0000 mm). The URDF root link merges into the world in the loader — the one expected difference. Tool: tools/robot_model/urdf_crosscheck.py.

## 6. `20260823 234720 Huphy 1.0 - collision geometry web viewer (three.js) with AB mechanism playback.mp4` (26 s)
**Title:** `20260823 234720 Huphy 1.0 - collision geometry web viewer (three.js) with AB mechanism playback`

**Description:**
Browser viewer of exactly the training models (RP serial / AB closed loop): visual meshes with opacity, collision capsules + box sole (green), URDF convex hulls (orange), loop closure sites (red), joint sliders, bent-init pose, and a loop-consistent crank trajectory recorded from MuJoCo so the passive foot moves correctly. Click a geom for name / size / body / mass. Screen capture (software WebGL, slower than live).

---
Suggested playlist: "Huphy 1.0 - sim model & RL". Related earlier uploads: `20260814 ... 2-RSU Ankle design confirm tool`, `20260819 ... Ankle AB motor, stopper test`, `20260820 ... pushrod`.
