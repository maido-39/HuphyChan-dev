# 2026-06-28 · 다음 레버 구현 레시피 — contact-clock + rsl_rl 대칭증강 (설치코드 검증)

> 병렬연구(agent, 32 tool-use, 설치 IsaacLab 2.2 / rsl_rl 2.3.3 직접 확인). swing_height(Phase1)가 부족하거나 절뚝 잔존 시 *즉시* 적용. [[2026-06-28_heeltoe_stride_fix]].

## ★ 검증된 핵심 사실 (틀리면 학습 손상)
- sim dt 0.005, decimation 4 → **control dt(step_dt) 0.02s**. `env.episode_length_buf`(+1/step, reset 0) 존재.
- **runtime joint 순서(14, BFS-by-depth, 레벨마다 L 먼저)**: `[L_hip_pitch,R_hip_pitch, L_hip_roll,R_hip_roll, L_hip_yaw,R_hip_yaw, L_knee,R_knee, L_ankle_pitch,R_ankle_pitch, L_ankle_roll,R_ankle_roll, L_toe,R_toe]` → ★ **L=짝수/R=홀수** → **L↔R mirror = 인접쌍 swap** `[1,0,3,2,5,4,7,6,9,8,11,10,13,12]`(14) / `[...,11,10]`(12 action). (기존 L블록/R블록 가정이면 학습 손상.)
- action 12 = 위 순서 − toe쌍. stock obs 239. height_scan **187=17(x)×11(y)**, "xy" → flat `iy*17+ix`. velocity_command 3=[vx,vy,wz].
- rsl_rl 2.3.3: `RslRlSymmetryCfg`(isaaclab_rl) + `RslRlPpoAlgorithmCfg.symmetry_cfg` 존재, runner가 `_env` 자동주입. PPO가 `data_augmentation_func(obs,actions,env,obs_type)` 호출, **critic obs도 별도 증강**(obs_type="critic", 14-joint+base_lin_vel).

## 레버1 — periodic contact-clock (보폭/no-flight; swing_height 부족 시)
- **reward fn** `gait_phase_contact`(rewards.py): leg_phase=remainder(t/period), R=+offset; is_stance=phase<0.55; reward=Σ_feet ¬(in_contact XOR is_stance). weight +0.18, period 0.8s, offset 0.5. (t=episode_length_buf*step_dt.)
- **obs fn** `gait_clock`: [cosφL,sinφL,cosφR,sinφR] → policy obs에 추가. ★ **obs-dim 변경 → from-scratch 재학습**. 배포 재현: step_count*0.02/0.8 mod 1.
- is_stance>50% → 양발 stance 겹침 → **flight 없음**(51.8kg GRF spike 방지). 40 step/stride. `init_at_random_ep_len=True`(우리 train.py)가 env간 phase 비동기화 → 좋음.

## 레버2 — rsl_rl 대칭증강 (L/R 절뚝; ★ warm-start 가능, 재학습 불필요)
- `symmetry.py`(신규): `JOINT_SWAP_14=[1,0,3,2,...]`, `ACTION_SWAP_12=[1,0,...,11,10]`. **sign flip(roll/yaw축)**: hip_roll·hip_yaw·ankle_roll (swap 후 ×-1); pitch/knee/toe는 swap만.
- 스칼라 항 sign flip(swap 없음): base_ang_vel(wx,wz), projected_gravity(gy), velocity_commands(vy,wz), base_lin_vel(vy, critic). height_scan: y행 반전 perm. gait_clock: L↔R쌍 swap.
- ★ **history 주의**: AsymObservationsCfg는 proprio가 history_length=5 flatten → 5프레임 각각에 per-frame mirror 적용(reshape [B,5,d]→mirror→back). **런타임에 `observation_manager.group_obs_term_dim/active_terms`로 오프셋 산출**(하드코딩 금지, obs-cfg 변경에 강건).
- `rsl_rl_ppo_cfg.py`: `algorithm.symmetry_cfg = RslRlSymmetryCfg(use_data_augmentation=True, data_augmentation_func=...)`. **obs/action width 불변 → ckpt warm-start OK**.
- 검증: `use_data_augmentation=False`로 두면 rsl_rl이 symmetry metric만 로깅 → 좋은 대칭정책서 ~0이어야. 크면 sign 오류.

## ★ Apply-decision
- **절뚝** = 레버2(대칭, 무료 warm-start) 먼저. **짧은보폭/flight** = 레버1(clock, 재학습). 둘 다 설치버전 완전지원.
