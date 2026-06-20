# 22 · 에너지/토크 reward 튜닝 — toe 적재 + 관절 offload (리서치 wseyrv4mz)

> [!warning] 핵심 반전
> **순수 에너지/파워 페널티만으로는 passive toe가 더 실리지 않는다.** toe가 정책 밖(수동)이라 12개 구동관절 파워항은 **발목을 offload할 뿐 toe엔 gradient가 없음**. ECO(BRUCE 휴머노이드)에선 에너지 예산하에 **heel-to-toe가 오히려 미발현**(제어노력↑로 발을 평평하게 만듦). 에너지 emergent toe-off는 **사족보행 증거**지 이족이 아님.

## 결론 (verdict)
No, not from energy alone; ECO BRUCE heel-to-toe did NOT emerge under an energy budget (emergence is quadruped, not biped). Toe is outside the policy so a power term over the 12 actuated joints only offloads the ankle and gives no gradient to load the toe. Pair vel-norm power CoT (offload ankle, kill stand-still) with terminal-stance forefoot rollover shaping (load toe); optional Duke-style low-ankle-torque. Ankle pitch 60 roll 14 are the bottleneck vs knee 360 hips 120. Add term in mdp/rewards.py, weights in velocity_env_cfg.py.

## 권장 reward (순서)
- 1 track_lin_vel KEEP 1.0; risk lower vs energy gives zero-velocity optimum
- 2 NEW vel-norm power CoT exp(-sum abs(tau qdot)/(sig_x absvx + sig_z abswz)), abs, 12 joints; alpha_en 1.0 or additive -2e-5 annealed; offloads ankle, kills stand-still, abs not signed; needs term3
- 3 NEW forefoot rollover shaping +0.05-0.1 gated terminal stance; only gradient to load passive toe; least validated
- 4 ankle torque fraction-norm (tau/tau_max)2 or ankle-only; soft_limit ankle 0.80; keep dof_torques_l2 -1.5e-6 ankle 3-5x; global tau2 stiffens not offloads, H1=0
- 5 action_rate -0.008 to -0.005; 6 dof_acc keep -1.25e-7 all; 7 no_flight watch -0.5 to -0.25

## 가중치 / 스케줄 (annealing)
Tracking dominant (lin 1.0 ang 2.0); energy small vs tracking or velocity-normalized so slowing doesnt help; do not raise tau2. dof_torques_l2 -1.5e-6 is normal-band and NOT the cause; ADD vel-norm power plus forefoot rollover. Anneal yes for a biped: hold power weight 0 until gait stable (first 30-40pct iters) then ramp linear over thousands (LoComposition 0 to 0.008 over 12k, tracking constant). Repo has command_lin_vel_x_levels (ramp_steps 15000) so add a parallel reward-weight curriculum. Alt fixed alpha_en 1.0 multiplicative or ECO Lagrangian. Guards only_positive_rewards, feet_air_time gated at zero command, stand_still. knee 360 vs ankle 14 is 26x so fraction-normalize per limit.

## 퇴행 방지 (degeneracy guards)
Stand-still (dominant; velocity to 0 at high energy weight per Adaptive Energy Reg, ECO confirms): velocity-normalize, tracking dominant, only_positive_rewards, stand_still penalty; watch achieved/cmd above 0.85-0.9. Drag/shuffle: keep feet_air_time +0.25 feet_slide -0.1. Over-stiffen (ECO flattened foot): do not raise tau2, action_rate -0.005, one lever at a time; detect toe stuck 26pct ankle 100pct. Power hack: abs(tau qdot) not signed (Cassie). Metrics: ankle saturation fraction, toe deflection above 26pct, knee/hip peak torque, CoT down 12-50pct, tracking above 0.9; extend analyze.py. Caveats: no RL source shows emergent toe-off (keep style terms upright/base_height/flat_orientation; energy alone gives non-human kinematics, iScience); toe over-damped zeta 2.9 may resist; ankle_pitch kp80 only 2.5x softer than knee, soften toward 1/4 knee; lunar 2509.10128 is quadruped.

## 야간 자율판단 (왜 이걸 야간에 안 돌렸나)
- 제대로 된 toe-loading = **속도정규화 power CoT + 종말기 forefoot rollover shaping**(둘 다 새 custom reward 항 + annealing 커리큘럼). forefoot rollover는 "least validated"이고 순수 에너지는 퇴행(stand-still/over-stiffen) 위험.
- **무인 6시간 학습에 미검증 신규 reward 2개 + annealing을 넣는 건 고위험** → 야간엔 **안전한 발목 offload**(기존 `applied_torque_soft_limit`을 발목에 0.80/×4 scoped, velocity_env_cfg) + **rough 전이**만 실행.
- **내일(주간) 신중 구현**: 위 권장 reward(vel-norm power CoT + forefoot rollover + ankle-only)를 `mdp/rewards.py`에 추가 → 짧은 검증 → annealing 커리큘럼 → 학습. **반드시 ablation**([[19_toe_ablation]])로 효과 검증.

## 출처
- [ECO RL Humanoid Walking BRUCE](https://arxiv.org/html/2602.06445v1) — _counter: scalar energy suppressed heel-to-toe on biped_
- [Adaptive Energy Regularization](https://arxiv.org/html/2403.20001) — _vel-normalized energy CoT, 1.0 safe 1.5 degenerate_
- [Fu Minimizing Energy CoRL 2021](https://energy-locomotion.github.io/) — _pure power emergent gaits quadruped_
- [Duke Humanoid](https://ar5iv.labs.arxiv.org/html/2409.19795) — _biped passive-dynamics 31pct CoT_
- [Kuo; Adamczyk Collins Kuo 2006](https://pubmed.ncbi.nlm.nih.gov/11871597/) — _toe-off 4x cheaper; rolling foot 2.37x_
- [Humanoid Parkour; Cassie IJRR; LoComposition; IsaacLab G1](https://arxiv.org/pdf/2406.10759) — _per-joint torque, abs-power, anneal, baselines_

> [!info] 그림(원문 링크)
- [Adaptive Energy Reg alpha_en 1.5 collapses velocity vs 1.0](https://arxiv.org/html/2403.20001)
- [ECO BRUCE heel-to-toe did not emerge](https://arxiv.org/html/2602.06445v1)
- [Duke knee deactivating in swing 31pct CoT](https://ar5iv.labs.arxiv.org/html/2409.19795)
- [Adamczyk Kuo collision work vs foot rollover radius](https://journals.biologists.com/jeb/article/209/20/3953/16394/The-advantages-of-a-rolling-foot-in-human-walking)

관련: [[17_toe_usage_vibration]] · [[19_toe_ablation]] · [[Paperreview/siekmann-periodic-reward]] · [[18_research_roadmap]]
