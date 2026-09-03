# 2026-09-03 · Stiff-knee gait / ankle-AB underuse / no toe-off support — raw research

> Trigger: user live-view complaint on `legonly_ab_v1` (logged 09-02 23:49, docs/118 §2C):
> "무릎을 전혀 안 쓰고(stiff-legged), AB도 제대로 안 쓰며, toe-off에 발끝 지지가 안 된다."
> Scope: web research only, no reward/code edits. Pre-check of existing notes done first
> (docs/reward_research/2026-06-29_*, 2026-07-02_gait_research_q123, 2026-07-06_straight_knee_stiff_gait,
> 2026-08-26_init_pose_conventions, 2026-08-26_human_landing_bundle — all read, not re-searched).

## 0. Code-inspection ground truth (before external research, to avoid re-deriving what's already in-repo)

Read `mujoco-sim/mjlab/src/mjlab/tasks/velocity/{velocity_env_cfg.py,config/pygmalion/env_cfgs.py,mdp/rewards.py}`
and `src/mjlab/asset_zoo/robots/pygmalion/pygmalion_constants.py` directly (2026-09-03).

- Current default pose = `HOME_KEYFRAME` (`joint_pos={".*": 0.0}`, base 0.87 m) unless `PYG_INIT_BENT` is set.
  `pose` reward targets `default_joint_pos` = this same keyframe (entity.py:682 → rewards.py:641,
  per code comment at pygmalion_constants.py:625) — default is simultaneously reset pose AND the
  pose-reward's standing target, straight knee.
- `pose` (`variable_posture`) std_walking knee = **1.2 rad (69°)** — loosened 2026-07-06 specifically to
  stop the joint-deviation-to-default trap (see `docs/reward_research/2026-07-06_straight_knee_stiff_gait.md`,
  already in-repo, not re-researched here).
- Gait shaping is **NOT** phase-clocked. `docs/reward_research/2026-07-05_periodic_contact_removal` (in-repo)
  removed the fixed Siekmann clock 2026-07-05 for forcing stepping at v=0 and fighting variable-speed
  tracking; current stack is "g1-vanilla command-gated": `feet_clearance` (w −2.0, target_height 0.1 m,
  reads `foot_height_scan` site sensor), `feet_swing_height` (w −0.25, same target/sensor), `feet_air_time`
  (w +1.0, window [0.05,0.5] s), all command-gated (`command_threshold` 0.05–0.5), all OFF at zero command.
- `stance_knee_extension` (= `PYG_KNEE_EXT`, mdp/rewards.py:768) IS active in the current `legonly_ab_v1`
  recipe (docs/110 §3, "22개 항목" table, row "stance knee extension `-2`"): `Σ relu(|q_knee|-25°)²` under
  **stance contact only**. One-sided — it only punishes flexion **beyond** 25° while loaded; it does not
  reward or require any flexion, and it is inert during swing.
- **Load-bearing finding (own derivation, not from literature): no active reward term targets the knee
  joint's position/height during swing.** `feet_clearance`/`feet_swing_height`/`feet_air_time` all read
  foot/ankle-site height above ground, not knee height or knee angle. A straight leg pivoting only at the
  hip clears a target foot height `h` at swing angle `θ = arccos(1 - h/L)`; for our leg length `L≈0.8 m`
  and the configured `target_height=0.1 m`, `θ≈29°` of hip flexion alone satisfies the target with **zero**
  knee flexion. This is a sufficient, self-contained explanation for "policy barely bends the knee even
  though the knee-walking pose tolerance is loose and swing peak flexion was previously measured at
  −58…−65° in the human-landing-bundle run (docs/reward_research/2026-08-26_human_landing_bundle.md §1)" —
  that measurement was under `PYG_INIT_BENT` (bent default, `_bent_joint_pos` knee −0.67 rad target), a
  different init/default-pose branch than the current HOME-default `legonly_ab_v1`. Under HOME default +
  foot-height-only clearance, hip-pendulum swing is the cheaper solution and nothing forces knee use.

## 1. Knee clearance / stiff-knee reward design across projects

### 1a. Booster T1 — explicit KNEE-height clearance term (not foot-height)
Source: **"Mind Your Steps: A General Learning Framework for Accurate Humanoid Foothold Tracking"**,
arXiv:2606.08253v1, fetched 2026-09-03. Validated on real **Booster T1** (93.08% success rate stepping onto
designated foothold targets, real hardware).

Formula (as reported by fetch, paper's own notation):
```
r_k(s_t, a_t) = ω_k · exp( -ξ_k · max(p̄_{t,z}^{□,w} + δ_k - p_{t,z}^{□,k,w}, 0)² )
```
- `p̄_{t,z}^{□,w}` = target swing-foot z (world frame)
- `δ_k` = knee clearance margin (slack, a positive offset ABOVE the foot target)
- `p_{t,z}^{□,k,w}` = **knee joint's own z-coordinate** (not the foot's)
- `□ ∈ {l,r}` selects the swing leg via the gait-phase variable
- One-sided (only penalizes/decays when the knee is BELOW `foot_target_z + δ_k`), so it directly forces
  the knee itself upward during swing, structurally distinct from a foot-height-only target.
- No von Mises/Bezier parametric swing trajectory used in this paper — phase variable + dynamically
  sampled foothold targets, swing motion otherwise free (learned).

### 1b. Unitree G1 (real robot) — "straight-knee stance" reward, opposite failure mode
Source: **"Gait-Conditioned Reinforcement Learning with Multi-Phase Curriculum for Humanoid Locomotion"**,
arXiv:2505.20619 (already cited in our own `stance_knee_extension` code comment). Fetched HTML 2026-09-03.
- Table I / Appendix Table IV: reward term **"Straight Knee"**, weight **0.1**, description:
  *"Encourage extended knee during stance to improve support efficiency."*
- Section III-E: *"straight-knee support improves force transmission and reduces muscular effort during
  stance phases."* Motivation stated explicitly: *"RL can produce stable locomotion... motions often appear
  overly crouched or energetically suboptimal."*
- No public formula, no stated target angle, no stated gating condition beyond "during stance" — paper text
  does not give more than the weight and description (confirmed absent from both HTML and the abstract).
  This is the SAME failure direction our own `stance_knee_extension` (target 25°, stance-gated) already
  addresses, at 20x the weight (−2 vs their 0.1, different reward scales so not directly comparable).
- Also reports a separate arm-leg angular-momentum reward: `R_momentum = -(L_total,z)² - 0.4(L_la,z - L_ra,z)²`
  (anti-phase arm-leg momentum compensation) — not directly relevant (we have no arms in LegOnly).

### 1c. Berkeley Humanoid Lite — explicit exclusion of hip_pitch/knee/ankle_pitch from deviation penalty
Source: `HybridRobotics/berkeley-humanoid-lite` GitHub, file
`source/berkeley_humanoid_lite/berkeley_humanoid_lite/tasks/locomotion/velocity/config/humanoid/env_cfg.py`
(fetched raw content 2026-09-03, lines ~190-212). Verbatim code comment:
```python
# penalize deviation from default of the joints that are not essential for locomotion
joint_deviation_hip = RewTerm(func=mdp.joint_deviation_l1,
    params={"asset_cfg": SceneEntityCfg("robot",
        joint_names=[".*_hip_yaw_joint", ".*_hip_roll_joint"])}, weight=-1.0)
joint_deviation_ankle_roll = RewTerm(..., joint_names=[".*_ankle_roll_joint"], weight=-1.0)
joint_deviation_shoulder = RewTerm(..., weight=-1.0)
joint_deviation_elbow = RewTerm(..., weight=-1.0)
```
`hip_pitch`, `knee`, and `ankle_pitch` (the sagittal / propulsive joints) appear in **none** of the
`joint_deviation_*` terms — only frontal/transverse-plane joints (hip_roll, hip_yaw, ankle_roll) and the
arms are deviation-penalized. This is the explicit, source-commented version of the pattern our own
2026-08-26 conventions note inferred indirectly ("IsaacLab 공식 설정은 시상면 힙·무릎을 pose 정규화에서
제외한다") — now directly confirmed in a second, independent, currently-maintained codebase with the
rationale spelled out in the comment itself.

### 1d. LimX Dynamics PointFoot (biped, point-foot, real product line) — zero joint-deviation reward, gait-schedule only
Source: `limxdynamics/pointfoot-legged-gym` GitHub (fetched raw
`legged_gym/envs/pointfoot_flat/pointfoot_flat_config.py` and `.../pointfoot_flat.py`, 2026-09-03,
default branch `master`).
- `default_joint_angles`: **all 8 leg joints = 0.0** (abad/hip/knee/foot, L+R). No bent default at all.
- `rewards.scales` contains **no `joint_deviation`/pose term whatsoever** for the legs. Full list:
  `keep_balance, tracking_lin_vel, tracking_ang_vel, base_height(-2), lin_vel_z, ang_vel_xy, torques,
  dof_acc, action_rate, dof_pos_limits(-2.0), collision, action_smooth, orientation(-10.0),
  feet_distance(-100), feet_regulation, foot_landing_vel, tracking_contacts_shaped_force(-2),
  tracking_contacts_shaped_vel(-2)`.
- Gait control instead comes from a **Margolis/CaJun-style continuous contact-schedule reward**
  (`class gait`: `frequencies [1.5,2.5] Hz`, `offsets`, `durations`, `swing_height [0.0,0.1]` sampled per
  episode as commands; `kappa_gait_probs=0.05` smoothing kernel — same mathematical family as our
  Siekmann/periodic_contact backbone, independently converged-on by a shipped commercial biped):
  ```python
  # tracking_contacts_shaped_force: encourage near-zero foot force when desired_contact==0 (swing)
  reward += (1 - desired_contact[:, i]) * exp(-foot_forces[:, i]**2 / gait_force_sigma)   # gait_force_sigma=25.0
  # tracking_contacts_shaped_vel: encourage near-zero foot velocity when desired_contact==1 (stance)
  reward += desired_contact[:, i] * exp(-foot_velocities[:, i]**2 / gait_vel_sigma)        # gait_vel_sigma=0.25
  ```
  This is force-in-swing / velocity-in-stance shaping — the mirror image of, and same family as, our
  already-adopted-then-removed Siekmann `periodic_contact` (swing=force≈0, stance=velocity≈0). Independent
  convergence is evidence the mechanism itself is sound; our 2026-07-05 removal was about the FIXED-period
  clock fighting variable-speed tracking and standing, not about the force/velocity-shaping idea itself —
  LimX's version avoids that failure mode by making `frequencies/offsets/durations/swing_height` themselves
  sampled COMMANDS (curriculum-resampled every 5 s) rather than a single fixed period, i.e. gait-conditioned
  in the same spirit as arXiv:2505.20619's "multi-phase curriculum" and our own `variable_posture` std-blend.
- `feet_height_target=0.10`, `height_tracking_sigma=0.01` exist as **config values but are not wired to any
  `_reward_*` function** in `pointfoot_flat.py` (grepped all `_reward_` defs; no `feet_height`/`swing_height`
  reward function exists) — i.e., this particular LimX branch does NOT reward hitting a swing-height target
  directly; swing-phase leg trajectory (incl. any knee bend) is left fully emergent from the force/velocity
  contact-schedule shaping alone. Flagged as uncertain/vestigial rather than an active mechanism — do not
  cite this repo as evidence FOR an explicit swing-height reward; cite it only for the zero-joint-deviation
  point and the contact-schedule formula above.

### 1e. Disney BDX droid / Open_Duck_Mini — reference-tracking (DeepMimic-style), not pose-deviation at all
Source: WebSearch results on `github.com/apirrone/Open_Duck_Mini` (official open clone of Disney's BDX
droid, Disney Research collab acknowledged in repo) + `la.disneyresearch.com/bdx-droids/` + eweek/variety
coverage of the official Disney BDX-R IsaacLab port (`github.com/KaydenKnapik/BDX-R-Isaaclab`). Not fetched
in full (time-boxed); reported findings:
- BDX/Open_Duck_Mini reward is an **imitation reward against a reference motion** generated by "a parametric
  walk engine" that produces a `polynomial_coefficients.pkl` reference trajectory — i.e. DeepMimic-family
  tracking, not a joint-deviation-from-static-default penalty. Structurally immune to the stiff-knee trap
  because there is no static default to collapse onto; the target is a moving reference.
- BDX-R robot itself has "five degree-of-freedom legs" in a bird/duck-like (not humanoid knee) configuration
  — geometry not directly transferable to our knee-flexion question; included for completeness per the
  question list, not as a load-bearing source.
- Not independently verified beyond search-summary level; treat as background context, not a cited
  parameter source.

### 1f. Summary table — knee/pose treatment across all robots checked (this session + reused 2026-08-26 table)
| Robot | Default knee (init = action origin) | Swing-phase knee/foot-height driver | Deviation-from-default on knee? |
|---|---|---|---|
| Booster T1 | 22.9° (docs/reward_research/2026-08-26_init_pose_conventions.md, reused) | explicit **knee-height** clearance (§1a, this session) | not found |
| Unitree G1 (unitree_rl_gym) | 17.2° (reused) | none found beyond tracking/air_time (reused) | none (roll/yaw only, reused) |
| Unitree G1 (arXiv 2505.20619, real robot) | not stated | "straight knee" stance reward, w=0.1, no formula (§1b) | n/a (reward is anti-crouch, not pose-lock) |
| Berkeley Humanoid Lite | not found this session (repo config values not located within time budget) | not located | **explicitly excluded** (§1c, verbatim source comment) |
| LimX PointFoot | 0.0 (straight, §1d) | contact-schedule only; foot-height cfg present but **unwired** (§1d) | **none at all** (no joint_deviation term exists) |
| mjlab G1 `KNEES_BENT_KEYFRAME` | 38.3° (reused) | `variable_posture` σ=0.35 (reused, this is the historically-bad value) | yes, at σ=0.35 (reused) |
| H1 (IsaacLab) | 45.3° (reused) | joint_deviation_hip (yaw/roll only, reused) | none on knee (reused) |
| **Pygmalion (current, code-read 2026-09-03)** | 0.0 (HOME) | `feet_clearance`/`feet_swing_height` = **foot**-height only (§0) | none on knee (σ_walking=1.2 rad, reused) |

## 2. Human normative gait joint angles (Perry/Winter) — REUSED, not re-searched

Already adversarially verified in-repo. Not re-derived here; citing directly per the "no duplicate
research" instruction.

**Knee** (from `docs/reward_research/2026-07-06_straight_knee_stiff_gait.md` §bottom, Perry & Burnfield
2010 / Winter consensus table, secondary source):
| Phase | Knee flexion (0°=full extension) |
|---|---|
| Initial contact (0%) | 0–5° |
| Loading response (0–10%) | 15–20° |
| Mid-stance (10–30%) | 0–5° |
| Pre-swing / toe-off (50–60%) | 35–40° |
| Swing peak (70–73%) | **60–70°** |

**Ankle** (from `docs/reward_research/2026-06-29_verify_ankle_normative_angles_torque.md`, adversarially
corrected — the ORIGINAL claim's mid-stance sign was backwards, corrected version below):
IC ~0° (neutral) → loading-response plantarflex to ~−5° (foot-flat ~7-12%) → controlled dorsiflexion rising
through stance → **terminal-stance dorsiflexion peak ~+10° @~48%** (spring-loading event, often omitted by
naive sources) → **powered plantarflexion peak ~−15 to −20° @ toe-off ~60-62%** → swing dorsiflexion back to
~0°/neutral for clearance. Peak plantarflexor moment **~1.4-1.5 N·m/kg** (Winter; clinical 1.25-1.5 N·m/kg)
→ ~78 N·m @ 51.8 kg reference mass used in that note (scale to our 35.7 kg total / per-leg mass for our
robot: do NOT reuse the 78 N·m absolute figure verbatim, re-derive from our own mass — flagged there
already).

**Hip** (new this session, lower confidence — qualitative only, standard clinical consensus, not
adversarially verified against a primary source this session):
WebSearch of AAPM&R/consensus summaries + general clinical-gait-analysis knowledge: hip sagittal ROM over
a full cycle is **~40°** total, from ~**+30° flexion at initial contact/terminal swing** down to ~**−10 to
−20° extension at terminal stance** (peak extension right before toe-off), returning to peak flexion again
at terminal swing/next initial contact. AAPM&R (`now.aapmr.org/biomechanics-normal-gait/`, fetched, no
degree table) confirms only the qualitative pattern (hip extends through stance, flexes through swing) —
exact degree-by-phase table not obtained from a primary source this session; treat as directional
guidance, not a tracking target, consistent with our own rule against re-deriving unverified normative
numbers (see §1 caveat in the ankle-angle adversarial-verify note about not encoding unverified curves
verbatim as tracking targets).

## 3. Flat-foot (no toe joint) toe-off / push-off mechanism

**Primary mechanism — REUSED from in-repo research, not re-derived**: our own
`docs/reward_research/2026-06-29_toe_use_reward.md` and
`docs/reward_research/2026-06-29_verify_biomech_toe_pushoff_mtp_angle.md` already established (with
citations Kuo 2002, Adamczyk & Kuo 2013, PMC5201006) that "3rd-rocker" forefoot rollover **emerges from
contact-sequencing + ankle plantarflexion alone, curved sole not required** — ankle plantarflexion IS the
push-off engine (Kuo 2002 inverted-pendulum framing; PMC5201006 "ankle push-off = forefoot rocker engine").
For a robot with NO toe joint (our v30 flat 3-box sole), the mechanism is: heel-strike → flat/full-sole
stance → late-stance ankle plantarflexion rotates the whole rigid foot forward about its front edge,
lifting the heel while the front edge/forefoot region stays loaded — geometrically substituting for a toe
joint using only the existing ankle-pitch DOF. This is confirmed by the "functional rockers" framework
(heel rocker / ankle rocker / forefoot rocker) found again this session:

- **New this session**: "Heel-Contact Toe-Off Walking Pattern Generator Based on the Linear Inverted
  Pendulum" (worldscientific.com/doi/10.1142/S021984361650002X) and the WABIAN-2R line of work both use
  this same heel/ankle/forefoot rocker decomposition for humanoid walking-pattern generation (model-based,
  not RL) — WABIAN-2R itself HAS passive 1-DOF toe joints, so it is not a pure counter-example, but the
  rocker-decomposition concept transfers: our robot only needs the **ankle rocker** phase (rotate about a
  fixed ankle axis while foot stays flat) plus enough plantarflexion range to approximate the terminal
  **forefoot rocker** (rotate about the front edge) without an actual toe hinge.
- Most Unitree-style flat single-segment-foot humanoids (G1, H1, T1, etc.) do exactly this in practice —
  no source found this session claiming they use a distinct "virtual toe joint" mechanism; push-off in
  their published reward stacks is achieved via velocity tracking + ankle torque/effort terms + swing-height
  clearance, with the forefoot-rocker geometry emerging passively from foot-plate shape + ankle ROM, not
  from any dedicated toe-off reward term. This matches our own already-verified conclusion (do not add a
  direct toe-off/CoP reward; the mechanism is indirect).

**Sole shape effect — NEW quantitative data this session**: "Model Analysis And Design Of Ellipse Based
Segmented Varying Curved Foot For Biped Robot Walking" (arXiv:2506.07283, fetched 2026-09-03), tested on a
real "TT II" biped robot with 3 elliptical curved-sole variants (ESVC1/3/5, major×minor axis
0.04575×0.03750 / 0.05205×0.03150 / 0.06901×0.02595 m) vs flat foot vs a straight-line ("line") foot
baseline:
| Condition | Result vs flat foot |
|---|---|
| Marking time (in-place stepping) | flat foot uses **+8.04%** more energy than line-foot baseline |
| Straight walking @ 0.1 m/s | flat +7.99% vs line baseline; **ESVC5 (flattest ellipse) −7.27%** vs flat |
| Lateral walking @ 0.2 m/s | **ESVC5 up to −18.52%** vs line baseline (largest effect measured) |
| Impact | curved sole "extends contact duration when impact... normal pressure smaller... reduces energy dissipation at the collision" |
Paper does NOT claim curved sole enables toe-off without a toe joint — its claim is scoped to rollover
dynamics / energy efficiency during stance, consistent with our own prior conclusion (docs/17/23, reused)
that curved/segmented sole is an **optimization, not a requirement**, for 3rd-rocker emergence (Adamczyk &
Kuo 2013 reused figure: rounded foot radius ~0.3×leg reduces collision work −20~40%, rigid flat foot +59%
— already in `docs/reward_research/2026-06-29_toe_use_reward.md`, not re-verified this session, cited for
context only).

## 4. Sources (this session, new)
- Mind Your Steps (Booster T1 knee-clearance reward): https://arxiv.org/html/2606.08253v1
- Gait-Conditioned RL Multi-Phase Curriculum (G1 "straight knee" reward, real robot): https://arxiv.org/abs/2505.20619 / https://arxiv.org/html/2505.20619
- Berkeley Humanoid Lite reward config (raw source, hip/knee deviation exclusion): https://github.com/HybridRobotics/berkeley-humanoid-lite (source/berkeley_humanoid_lite/berkeley_humanoid_lite/tasks/locomotion/velocity/config/humanoid/env_cfg.py)
- LimX Dynamics PointFoot RL env (raw source, default pose + reward scales + contact-schedule formulas): https://github.com/limxdynamics/pointfoot-legged-gym (legged_gym/envs/pointfoot_flat/{pointfoot_flat_config.py,pointfoot_flat.py})
- Ellipse-based curved foot design, quantitative energy comparison (TT II robot): https://arxiv.org/html/2506.07283
- Heel-contact/toe-off walking pattern generator (functional rockers, LIP-based): https://www.worldscientific.com/doi/abs/10.1142/S021984361650002X
- Disney BDX droid / Open_Duck_Mini (imitation-reward walking, background only): https://github.com/apirrone/Open_Duck_Mini · https://la.disneyresearch.com/bdx-droids/ · https://github.com/KaydenKnapik/BDX-R-Isaaclab
- AAPM&R normal gait biomechanics (hip qualitative pattern, no degree table extracted): https://now.aapmr.org/biomechanics-normal-gait/

## 5. Sources reused from in-repo notes (not re-fetched this session)
- `docs/reward_research/2026-07-06_straight_knee_stiff_gait.md` — our own stiff-knee root-cause history + Perry/Burnfield knee table.
- `docs/reward_research/2026-06-29_verify_ankle_normative_angles_torque.md` — adversarially-corrected ankle angle timeline + torque.
- `docs/reward_research/2026-06-29_toe_use_reward.md`, `2026-06-29_verify_biomech_toe_pushoff_mtp_angle.md` — passive-toe/windlass, indirect-reward doctrine, sole-curvature-optional conclusion, Kuo/Adamczyk citations.
- `docs/reward_research/2026-06-29_gait_emergence_siekmann.md`, `2026-07-02_gait_research_q123.md` — Siekmann backbone, contact-schedule literature survey, ankle push-off = forefoot-rocker engine.
- `docs/research_raw/2026-08-26_init_pose_conventions.md` — 13-codebase default-knee-angle survey (G1/H1/T1/N1/Berkeley/Cassie/Digit/ToddlerBot), reused verbatim in §1f.
- `docs/reward_research/2026-08-26_human_landing_bundle.md` — PYG_INIT_MID / PYG_KNEE_EXT / stance_knee_extension design history and measured effect sizes.

## 6. Honesty check
- Verified by direct fetch/curl this session: Mind Your Steps formula (WebFetch summary of arXiv HTML,
  not hand-checked against the PDF's rendered equations — treat the LaTeX-ish transcription as
  approximate), arXiv 2505.20619 weight/description (WebFetch summary), Berkeley Humanoid Lite raw source
  (curl, exact lines quoted), LimX PointFoot raw source (curl, exact lines quoted, both config and reward
  function file), arXiv 2506.07283 quantitative table (WebFetch summary of HTML).
- Verified by direct repo read (own codebase): all of §0, the geometry derivation (θ=arccos(1-h/L)) is
  my own calculation, not from a source — flag if used as a training target, it needs a real per-robot leg
  length, not the illustrative 0.8 m used here.
- Not independently re-verified: Disney BDX/Open_Duck_Mini claims (search-summary only, no fetch);
  AAPM&R hip degree values (no table found, qualitative only); LimX's `feet_height_target` wiring
  (inferred "unused" from absence of a matching `_reward_*` function in one file — did not check for an
  alternate injection point, e.g. a base class).
