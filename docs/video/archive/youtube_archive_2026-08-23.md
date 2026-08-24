# YouTube archive — Maido -A (@kirima), Huphy 1.0 sim / design work

Title convention kept: `YYYYMMDD HHMMSS Huphy 1.0 - <topic>` (timestamp = when the material was made). **Filename = title.** All clips ≥ 15 s, English captions burned in; clips that are not real time say so in the caption.

Suggested playlists: **Huphy 1.0 - sim model & RL** (2026-08-23 clips), **Huphy 1.0 - ankle 2-RSU design**, **Huphy 1.0 - gait experiments (A/B)**, **Huphy 1.0 - structure (FEA)**.

---

## 1. `20260708 083722 Huphy 1.0 - PD damping A B, Kd 6 vs link-critical Kd 14 (ghost overlay)`  (51 s)

**Description:**
- Controlled A/B: reference-scaled Kd 6 vs link-inertia critical Kd 14
- Link-critical Kd raised joint loads 2–3.5× and cut tracking 2.8–5× → rejected; under-damped Kd 6 kept
- Consistent with deployed humanoids (ζ ≈ 0.05–0.4 on link inertia). docs/53, docs/70

## 2. `20260708 180640 Huphy 1.0 - init pose A B, straight vs bent knee (ghost overlay)`  (51 s)

**Description:**
- Controlled A/B: straight-knee init vs bent crouch init, same commands, policies overlaid as ghosts
- Result: no winner — bent lowers GRF ~35 percent (impact absorption) but knee torque +98 percent, CoT +8 percent, tracking down
- docs/55

## 3. `20260713 212624 Huphy 1.0 - joint reaction wrench 3D envelopes, 6 leg joints (slow turntable)`  (24 s)

**Description:**
- Force and moment vectors at each of the 6 leg joints from the measured gait (gen21p2, 15 s-dwell command sweep)
- Surfaces = RMS / P99 / peak directional quantiles; red dots = per-axis extremes
- Inputs to bearing selection and link FEA (docs/64, 65). Slow turntable, not real-time data

## 4. `20260713 214233 Huphy 1.0 - flat anchor policy gen21p2, command sweep with joint loads and GRF (60 s excerpt)`  (60 s)

**Description:**
- Current flat design anchor policy: vx sweep blocks, 15 s dwell each, real time 25 fps (60 s excerpt)
- Joint load spheres (grey < rated < yellow < orange 70 percent peak < red), GRF arrows (0.4 m = 1 BW), signed wrench panel
- Full 294 s version: docs/mujoco/assets/gen21p2_fc_demo_loadviz.mp4

## 5. `20260715 145202 Huphy 1.0 - hip geometry variants, joint motion - cant30 and roll-offset 30`  (21 s)

**Description:**
- First half: hip_pitch axis canted 30 deg. Second half: hip_roll axis offset 30 mm outward
- Joint-by-joint motion showing how foot heading and clearance change with the geometry (docs/68)

## 6. `20260720 200449 Huphy 1.0 - hip geometry A B, no-cant vs 30 deg canted hip pitch axis (side by side)`  (60 s)

**Description:**
- Left: flat anchor (gen21p2). Right: hip pitch axis canted 30 deg inner-up with feet-parallel init (cant30fp)
- Same command schedule frame-locked, real time 25 fps, joint load spheres
- 60 s excerpt of the 120 s side-by-side (docs/67, 68)

## 7. `20260724 023031 Huphy 1.0 - knee load sensitivity across 5 reward variants x 3 speeds`  (45 s)

**Description:**
- Five reward variants frame-locked at 0.75 / 1.75 / 2.5 m/s (measured qpos replay)
- Knee marker colour = load class; panel labels = block RMS / P99
- Spread concentrates at low speed (crouch near standstill), converges at 2.5 m/s — feeds the design-value uncertainty (docs/65)

## 8. `20260811 022118 Huphy 1.0 - 2-RSU ankle geometry optimisation, pattern search (slowed 4x)`  (17 s)

**Description:**
- Pattern search over crank / rod / anchor geometry with HARD constraints (Deb rules): ROM reach, torque, torque-speed, swing angle
- Soft composite scores were rejected after they picked constraint-violating designs as “best”
- Slowed 4×, not real-time
- ⚠ **Superseded design stage** (docs/71 §7e, 2026-08-04; rendered 08-11). Geometry shown — A_r 70 · B_r 62.9 · RP_h 20, P99 margin 16.3 % — is **not** the final design. Invalidated afterwards by the ball-joint ±13→±20 redesign (§8), the pitch-sign bug (§9) and the swing_foot arcsin→arccos bug (§10c); the pattern-search **method itself** was dropped in §8e after it was shown to land in 16 distinct local minima. Design of record = **v9h2** (docs/76 §1) → see clip 17

## 9. `20260812 201533 Huphy 1.0 - 2-RSU ankle replaying a learned gait, crank torques`  (20 s)

**Description:**
- Measured gait (gen21p2 policy, forward-walking block) replayed through the 2-RSU linkage
- Left: crank A/B, rods and sole updating; right: ankle torque → crank torques via the linkage Jacobian
- Ankle pitch 5.6–31.2 deg, roll −11..+10 deg, |τ_pitch| up to 52 N·m in this block
- Looped twice to reach archive length

## 10. `20260813 143100 Huphy 1.0 - 2-RSU ankle, rod-end ball swing over the whole ROM`  (19 s)

**Description:**
- Sweep of the ankle pose with the rod-end swing angle measured against the spherical-bearing limit
- Found that the ±20 deg box is about the clevis-bolt axis (foot roll), not a vertical cone — the earlier ROM-reduction conclusion was withdrawn
- Input to the clevis / bolt-axis decision and the roll ±15 recommendation (docs/71, 76)

## 11. `20260814 125038 Huphy 1.0 - 2-RSU ankle v9 design, ROM sweep with rod-end swing gauges`  (24 s)

**Description:**
- Final 2-RSU ankle geometry (v9h2): crank 40–65 mm box, rod A_h > 40, RP_B ≤ 60, human-gait coverage ×1.25 safety factor
- Boustrophedon raster over pitch −50..+30 × roll ±20 deg: 3D mechanism + rod A/B swing-angle gauges
- Gauge limit 20 deg = spherical bearing (JS6) swing; red = over
- Basis: docs/76 design summary, docs/71 optimisation setup

## 12. `20260818 075113 Huphy 1.0 - FEA of the printed links, PLA triage and lightweighting (slides)`  (28 s)

**Description:**
- Headless FEA pipeline (gmsh + solver) on the printed links with measured worst-frame gait loads (P99 × 1.25)
- Design stress read away from load / constraint nodes; mesh convergence; singularities identified by node count
- PLA triage: in-plane 25.5 MPa / interlayer 11.3 MPa → which printed plates break first, CNC replacement order
- Lightweighting (BESO) with re-verification. docs/77, 85, 86

## 13. `20260822 063900 Huphy 1.0 - v2 CAD-exact model, old policy zero-shot (pipeline check)`  (15 s)

**Description:**
- MJCF rebuilt from the 2026-08 CAD (new link lengths, aluminium 42 kg) driven by the previous policy with no retraining
- Stays upright, knees saturate → retraining needed, pipeline works end to end (docs/87)

## 14. `20260823 182339 Huphy 1.0 - closed-loop model URDF vs MJCF cross-check, 29 joints`  (58 s)

**Description:**
- Loop model: cranks and rods exported as a URDF tree (universal joints as two revolutes with a 1 g dummy link; closure as a comment)
- Read by MuJoCo’s URDF parser vs the MJCF: 29/29 joints, 0.0000 mm over 200 random poses
- Tool: tools/robot_model/urdf_crosscheck.py

## 15. `20260823 201532 Huphy 1.0 - CAD to URDF MJCF pipeline, ROM, printed density, mass DR (slides)`  (32 s)

**Description:**
- Fusion export copy → massprops (rigid bodies, catalogue motor masses) → URDF + MJCF with fitted capsules and box sole
- Joint ROM measured on the real CAD meshes; printed parts weighed (mass ratio 0.33 → density per part)
- Mass uncertainty propagated per link → domain-randomisation ranges (pseudo-inertia)
- Arms welded 15 deg out; closed-loop ankle transmission map; RP torque envelope. docs/88–92

## 16. `20260823 233958 Huphy 1.0 - 3DP lower body sim model turntable, collision capsules & hulls`  (18 s)

**Description:**
- MuJoCo model of the 3D-printed Huphy 1.0 lower body: 35.35 kg, printed parts at the measured PLA density (mass ratio 0.33 vs aluminium)
- Layers switch: visual meshes → collision geometry (fitted capsule per link, box sole, loop sites) → collision only
- Adjacent-link contact pairs excluded; everything else is a self-collision penalty in RL
- Arms welded 15 deg out (hanging arm capsule overlapped the hip by 14 mm)
- Joint ranges from the CAD sweep: hip_yaw ±45, ankle pitch −50/+30, roll ±20 deg
- Tools: tools/robot_model/build_robot.py (URDF + MJCF from Fusion massprops), tools/collision_viewer

## 17. `20260823 234140 Huphy 1.0 - RP-mode ankle torque envelope from the 2-RSU loop IK FK`  (16 s)

**Description:**
- Serial (roll/pitch) training needs the torque the mechanism can actually deliver at each pose
- Per grid point: crank IK on the closure equations → loop Jacobian Jc → feasible ankle torque = Jcᵀ·[±60, ±60] (parallelogram)
- Centre pose pitch ±98 / roll ±84 N·m; shrinks to ±71 / ±50 at −48 deg plantarflex
- RP training clamps the PD torque to this set in crank space (+ measured RS03 torque-speed curve) = the hardware limit
- Left: loop posed on the ROM (cranks from IK). Right: feasible set at that pose. Pose sweep, not real-time data

## 18. `20260823 234224 Huphy 1.0 - 2-RSU closed-loop ankle in MuJoCo, AB crank drive + ground contact`  (16 s)

**Description:**
- The ankle as the real mechanism: two RS03 cranks, two push rods on universal hinges, four connect equalities on the foot, passive pitch/roll hinges
- Cranks servoed Kp 22.3 / Kd 1.41, ±60 N·m: co-actuation → foot pitch, differential → roll, then a circle
- On the ground the cranks tilt the sole onto its toe / heel / side edges (contact points + force arrows)
- Loop closure 0.000 mm throughout; rod-end constraints set near-rigid (solimp 0.999) after a stiffness A/B
- Panels: whole body / ankle close-up / collision geometry. This is the AB-mode model used for RL (mjlab, mujoco_warp)

## 19. `20260823 234427 Huphy 1.0 - RL AB test at iter 1200, closed-loop (AB) vs serial+envelope (RP) ankle`  (22 s)

**Description:**
- Same reward, curriculum, masses, measured motor J/b/friction, torque-speed curves and bent init — only the ankle mechanism differs
- Left AB: policy commands the two cranks, ankle passive through the rods. Right RP: serial ankle with the loop-envelope torque clamp
- Checkpoint iter 1200 / 32000 (vx 0.8 m/s stage); commands 0.8 m/s, 0.8 + 0.5 lateral, −0.8 m/s; real time
- Captions: ankle pitch and ankle torque in the common space (AB: Jcᵀτ_crank, RP: crank-equivalent)
- Early finding: AB moves the ankle 17 deg per stride at 12.8 N·m RMS; RP rails its ankle target (−40↔+35 deg) and saturates the PD (docs/93)

## 20. `20260823 234705 Huphy 1.0 - URDF vs MJCF cross-check, joint sweeps overlaid`  (34 s)

**Description:**
- Exported URDF read by MuJoCo’s own URDF parser (red wireframe) overlaid on the MJCF (solid)
- Every joint swept through its range; 200 random all-joint poses
- Joint axes, anchors, ranges, link positions and per-link mass / COM / inertia agree to 0.0000 mm
- Only expected difference: the URDF root link merges into the world in the loader
- Tool: tools/robot_model/urdf_crosscheck.py

## 21. `20260823 234720 Huphy 1.0 - collision geometry web viewer (three.js) with AB mechanism playback`  (26 s)

**Description:**
- Browser viewer (three.js) of exactly the training models: RP serial / AB closed loop
- Layers: visual meshes with opacity, collision capsules + box sole (green), URDF convex hulls (orange), loop closure sites (red)
- Joint sliders, bent-init pose, and a loop-consistent crank trajectory recorded from MuJoCo so the passive foot moves correctly
- Click a geom for name / size / body / mass / contype
- Screen capture under software WebGL — slower than live

## 17. `20260824 012359 Huphy 1.0 - 2-RSU ankle geometry optimisation, final DE convergence (160 generations)`  (23 s)

**Description:**
- The optimisation that actually produced the design of record: **v9h2** differential evolution, NP = 80, F = 0.6, CR = 0.9, 160 generations, Deb lexicographic hard constraints (feasibility first, then maximise the worst margin)
- Left: the 2-RSU geometry of the best individual at each generation (neutral pose). Right top: P99 min-margin vs generation — first feasible at gen 4, final **+3.41 %**. Right bottom: per-constraint margins, orange = binding
- Final: A_r 65.0 · B_r 62.0 · RP_B 50.5 · RP_r 43.8 · A_h 41.2 · B2RP 200.0 · RP_h 10.0 · A_L 289.1 · B_L 193.3 mm; binding = rod-end swing (JS6) +3.4 %, human-gait coverage +4.1 %, transmission ratio +3.8 %
- Rendered from the stored per-generation trace (`romscan_gens_v9h2_f0.jsonl`), no optimisation re-run. 1 frame = 1 generation, not real-time. Replaces clip 8 as the optimisation-process clip. docs/71 §17j, docs/76 §1

## 18. `20260824 112300 Huphy 1.0 - ankle AB vs RP, side by side gait at iter 8000`  (24 s)

**Description:**
- The ankle A/B under training: **AB** = closed-loop crank ankle (two cranks + rods, parallel 2-RSU) vs **RP** = serial roll/pitch ankle with the loop's torque envelope applied as a clamp. Everything else identical — same reward stack, same curriculum, same warm start, same seed
- Both clips are the **same recorded rollout clock**: command 0 → 0.4 → 0.8 m/s, 8 s each, replayed at 25 fps = real time. Top row whole body, bottom row left-ankle close-up
- Bottom bar reads the command, each arm's measured forward speed and its error. At 0.8 m/s the tracking error is the same for both (+0.055 vs +0.056 m/s)
- Chase camera locked to each robot's own base, because the velocity command is body-frame and the two arms yaw apart in the world
- Iter 8000 of 32000, after the squared soft-landing penalty was added. docs/93 §5c, docs/95 §7

## 19. `20260824 112300 Huphy 1.0 - ankle AB vs RP, ghost overlay at iter 8000`  (24 s)

**Description:**
- The same two rollouts **overlaid**: bases aligned, 50/50 blend, AB tinted amber and RP tinted blue, so every limb difference at the same instant shows as a ghost offset
- Right panel is the same overlay on the left ankle, where the two kinematics actually differ
- What it shows: the gait rhythm is nearly identical (2.0–2.1 strides/s), but AB drives a **sharp dorsiflexion spike at terminal stance (31°)** while RP holds a **flatter 18–22° plateau** — a push-off style difference, not a performance difference
- Vertical GRF p99 1.26 (AB) vs 1.29 BW (RP) and stance ripple 0.149 vs 0.155 — no measurable "RP trembles more" at this stage
- Same ghost-overlay convention as clips 1 and 2. docs/93 §5c
