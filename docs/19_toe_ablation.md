# 19 · Toe Ablation 연구 계획 (메트릭 + 실험설계)

> [!question] 질문: passive toe가 실제로 도움되나? 어떻게 비교(메트릭)? — 리서치 ws2d3t2mh

## 한 줄
**foot 단일인자 ablation**(toe만 바꾸고 각 구성 **재학습**). 핵심쌍 **B(rigid) vs C(no-toe)**. 1차 HW 페이오프 = **ankle_pitch(RS03 60) 부하 분산**. 강성 사다리는 Sci Rep 2025 최적((32, 56, 80) N·m/rad)과 정합.

## 실험 설계 (configs)
SINGLE-FACTOR FOOT/TOE ABLATION (vary ONLY the foot; retrain every config from scratch).

WHY RETRAIN, NOT EVAL-SWAP: the policy (rsl_rl PPO) is a closed-loop optimizer. Locking/removing the toe changes contact dynamics and the reachable gait, so a policy trained on the k=60 toe is off-distribution on a rigid/flat foot. Only a from-scratch retrain reveals each morphology's true achievable performance. Use the SAME seed set across configs for paired comparison (Henderson 2018; Colas 2018; Agarwal/RLiable 2021).

CONFIG MATRIX (factor = foot):
  A_baseline  passive toe k=60, d=4, armature=0.008 (repo ground truth, robstride_biped.yaml lines 87-98) -- current design
  B_rigid     toe joint LOCKED at 0 (high implicit stiffness e.g. k>=2000, or a fixed MJCF joint). Same foot length/contact patch as A -- isolates COMPLIANCE
  C_notoe     single-segment flat foot, distal toe segment merged into foot_link -- true MORPHOLOGY baseline (no distal segment)
  D_soft      passive toe k~=30 (~0.56 N*m/deg) -- soft end of literature grid
  E_stiff     passive toe k~=90-120 (~1.6-2.1 N*m/deg) -- stiff end / push-off emphasis
  F_damped    k=60 with higher damping (optional) -- tests the toe-slap/impact hypothesis
The CRITICAL pair is B vs C: B isolates compliance while keeping foot length; C removes the distal segment entirely.

LITERATURE ANCHOR (the stiffness ladder is NOT arbitrary): Nature Sci Rep 2025 tested {0,0.56,0.98,1.4,inf} N*m/deg and found the human-like optimum at 0.98 N*m/deg = 56 N*m/rad -- essentially your k=60. Their grid {0.56,0.98,1.4}={32,56,80} N*m/rad maps onto D/A/E. Expect A (or a value near it) to win; D/E quantify the margin.

CODE-GROUNDED EXECUTION NOTES (verified against the repo):
 1. STIFFNESS/DAMPING SWEEP IS PURE-YAML, NO USD RECONVERT. The toe is a passive_spring actuator group applied at runtime as an ImplicitActuatorCfg (spec.py build_articulation_cfg). The convert_to_usd() cache keys ONLY on source-file bytes + the convert/* block, NOT the actuators block (spec.py convert_to_usd lines 234-267). So configs A, D, E, F = edit robstride_biped.yaml toe_passive.stiffness/damping and retrain. Fast.
 2. B_rigid: cheapest as a very-high implicit stiffness on the toe_passive group (still pure-YAML). A truly fixed joint requires editing assets/biped_lower_body_mjcf/robot.xml + USD reconvert (--force) and re-verifying the /Robot/base_link/<body> prim paths.
 3. C_notoe: INVASIVE -- edit the MJCF geometry (merge distal segment into foot_link), reconvert USD with convert_asset.py --force, and re-verify contact-sensor prim paths (velocity_env_cfg lines 156-161) and that foot_body_regex='.*_foot_link' still matches. Budget for this; consider doing A/B/C first and adding D/E only if the morphology effect is real.
 4. CONFOUND CONTROL -- hold these IDENTICAL across configs (verified terms): mass 51.8 kg + add_base_mass DR (-5,5) (velocity_env line 172), base_com DR, friction DR static(0.30,1.25)/dynamic(0.20,1.10) (lines 182-188), PD gains (hip kp200/kd5, knee kp200/kd5, ankle_pitch kp80/kd3, ankle_roll kp40/kd2 -- yaml), ALL reward weights incl torque_soft_limit soft_ratio 0.85 weight -0.0025 (lines 116-120), dof_acc_l2 -1.25e-7, dof_torques_l2 -1.5e-6, action_rate_l2 -0.008, command curriculum (start_max 1.0 final_max 2.0 ramp 15000), terrain, PPO hyperparams, total env-steps, seed set.
 5. CORRECTION to a stale research caveat: dof_acc_l2 ALREADY covers ALL actuated joints incl. ankles (velocity_env lines 215-218: asset_cfg=LEG_TORQUE_JOINTS, with a code comment that it was the foot-vibration fix), NOT hip+knee only. The toe is passive so it is in NO reward by construction. This is fine for the ablation as long as it is identical across configs; smoothness differences will surface in Harmonic Ratio / GRF, not in reward.

STATISTICS: N>=3 seeds minimum, escalate to N>=5 if any pairwise gap is within ~1 SD. Evaluate each trained policy on a FIXED held-out set of eval seeds/initial states (decoupled from training seed). Report IQM + 95% stratified bootstrap CIs (RLiable), show per-seed points, and pre-register the decision rule: 'adopt the change only if the 95% bootstrap CI on the A-minus-config difference excludes 0.'

PRE-REQUISITE INFRA FIX (blocks CoT + the ankle-offload claim): add per-joint power. wrench_logger.py reads joint_vel at line 72 but never writes it. Add omega_<joint> and P_mech_<joint>=tau*omega columns BEFORE running the study (see power_method deliverable).

PAYLOAD/AMP AS SEPARATE SECOND FACTORS: keep +10 kg payload and (future) AMP human-likeness OUT of the main sweep. Re-run only the 2-3 best foot configs at +10 kg as a follow-up, to keep the 5x3=15-training serial campaign feasible on the 9.7 GB / sm_120 box (one training at a time -> multi-day).

## 메트릭
| metric | formula | expected | role |
|---|---|---|---|
| Mechanical Cost of Transport (CoT) | `(1/(m*g*v)) * <sum_j max(0, tau_j*omega_j)>_t` | LOWER with a correctly-tuned toe (A<B,C). Report a | primary efficiency / human-likeness |
| ankle_pitch peak torque & util% | `peak|tau_ankle_pitch|; util%=peak/60 (RS03 peak)` | LOWER with toe -- the toe adds passive push-off to | motor offload (binding actuator) |
| ankle_pitch peak positive power & stance impulse | `max(P+_ankle_pitch); integral of tau over stance` | LOWER with toe | motor offload |
| GRF impact peak | `first local max of vertical GRF after each touchdown` | LOWER with softer toe (compliant distal segment sp | shock load / structural |
| GRF loading rate | `slope of vertical GRF from 20% to 80% of rise to impact peak` | LOWER with toe | shock load / structural |
| 6-axis link wrench at ankle/foot (peak |F|, peak moments) | `max over time of sqrt(Fx^2+Fy^2+Fz^2) and per-axis |T| at an` | LOWER shock loads up the leg with toe -> smaller m | STRUCTURAL SIZING -- the actual deliverable beyond CoT |
| MTP-equivalent negative (dissipative) work | `integral of min(0, tau_toe*omega_toe) dt over stance` | stiffer toe REDUCES negative MTP work (Sci Rep PMC | mechanistic |
| velocity-tracking error (GUARD) | `RMS error of lin_vel_x vs cmd_vx, ang_vel_z vs cmd_wz` | ~UNCHANGED -- credits CoT/power gains only at matc | guard against 'efficient by walking slower' |
| fall rate & mean time-to-fall | `fraction of eval episodes terminating early; mean survival t` | UNCHANGED or BETTER with toe | robustness guard |
| push-recovery success % | `apply base force, fixed magnitude swept ~50-300 N x ~0.1 s a` | UNCHANGED or BETTER with toe | robustness guard |
| trunk Harmonic Ratio (smoothness) | `per stride: DFT base_link accel per axis; HR=sum(even-harmon` | HIGHER (smoother/more symmetric) with toe | human-likeness smoothness |
| knee torque-SPEED envelope check | `scatter (omega_knee, tau_knee) reflected to motor side under` | all points inside envelope w/ margin; toe should n | actuator validity (ties to gear deliverable) |

## 출처
- [Optimizing toe joint stiffness to improve human-like walking (Nature Sci Rep 2025) -- human-like optimum 0.98 N*m/deg = 56 N*m/rad ~= your k=60; lower stiffness aids rollover, higher aids push-off](https://www.nature.com/articles/s41598-025-17957-4) — _toe_ablation_
- [Effect of upward curvature of toe springs on walking biomechanics (PMC7499201) -- stiffer toe reduces MTP negative work -2.81 -> -1.81 J](https://pmc.ncbi.nlm.nih.gov/articles/PMC7499201/) — _toe_ablation_
- [Deep RL at the Edge of the Statistical Precipice / RLiable (Agarwal et al. NeurIPS 2021) -- IQM + stratified bootstrap CIs for few-seed evaluation](https://proceedings.neurips.cc/paper_files/paper/2021/file/f514cec81cb148559cf475e7426eed5e-Paper.pdf) — _toe_ablation_stats_
- [Deep Reinforcement Learning that Matters (Henderson et al. 2017) -- seed-to-seed variance, need shared seeds for fair ablation](https://arxiv.org/pdf/1709.06560) — _toe_ablation_stats_
- [Validation of a Measure of Smoothness of Walking (Harmonic Ratio of trunk acceleration)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3032432/) — _toe_ablation_

관련: [[17_toe_usage_vibration]] · [[Paperreview/toe-stiffness-optimization]] · [[Paperreview/siekmann-periodic-reward]] · [[18_research_roadmap]]
