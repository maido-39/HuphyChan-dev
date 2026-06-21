# 학습 리포트 — 2026-06-21_10-33-47_stage5_rough_converge

- **task/run**: `2026-06-21_10-33-47_stage5_rough_converge`  ·  **명령**: `(미기록)`
- **의도/변경점**: stage-5: rough-terrain CONVERGENCE, warm-start from stage-4 rough (1300 iter)

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_rough/2026-06-21_10-33-47_stage5_rough_converge/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_rough/2026-06-21_10-33-47_stage5_rough_converge/model_1300.pt`

## 2. 지표 (Metrics)

## 2b. Reward (무엇을 · 왜)
활성 보상 항과 **최종 기여**는 아래. 각 항의 **의미 · 가중치 · 왜**는 → [[04_reward_experiments]] ("현재 활성 Reward 전체" 표) 참조 (재도출 금지, 링크로 추적).
- (로그에서 보상 항목 미검출 — 학습 로그 경로 확인)

**이번 run 중요/신규 reward + 왜**: **신규 reward 없음**. 이 run의 변수는 *보상*이 아니라 **iter 누적(수렴)**이었다 — stage-3/4에서 확립한 표준 rough locomotion 보상셋(추종 track_lin/ang_vel + 안정 flat_orientation·base_height·feet_air_time + `torque_soft_limit_ankle` 발목 offload[[28_reward_actuator_fidelity]] + height_scan 지형관측)을 그대로 두고 더 돌려 rough를 잡으려 했음. 보상이 아니라 *학습량/커리큘럼*이 병목이었고, 그조차 부족(미수렴). 보상 세부는 [[04_reward_experiments]].

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![tb](assets/2026-06-21_10-33-47_stage5_rough_converge_tensorboard.png)

- **수렴(noise_std)**: 0.47 → **0.62** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.3 → **5.3**, ep_len 최종 **879**
- **추종 error_vel_xy**: 최종 **0.918** (낮을수록 good), yaw 0.989
- **안정성 낙상률 20%** (base_contact 1.88 / time_out 7.29) (낙상多 ❌)
- **value loss 최종** 0.141, entropy 10.124, LR 5.8e-04
- **커리큘럼 vx 상한 최종** 2.00
- **정성 해석(★중요)**: 이 run은 **수렴하지 못했다**. noise_std가 0.47→**0.62로 *증가***(정책이 아직 탐색 중 = 미수렴) + **낙상 20%**(rough에서 불안정) + error_vel **0.918**(추종 나쁨, 평지 forefoot의 0.5 대비 ~2배). reward는 0.3→5.3로 올랐으나 절대값이 낮고 ep_len 879(<1000, 조기종료 잔존). **판정: vx=2.0 rough를 평지 base에서 1300 iter로는 못 잡음** — 지형이 너무 거칠거나 iter 부족. (커리큘럼 vx 상한이 이미 2.0로 maxed라 명령이 계속 어려웠음.) **왜 1300서 멈췄나**: forefoot(평지) 실험으로 전환하며 *수렴 전에 중단* = 보수적-중단 규칙 위반의 반례(이건 "느린 정상"이 아니라 "미수렴"이었으나 더 돌렸어야 함). **다음 튜닝**: ① 더 좋은 평지 base(forefoot 계열 수렴본)에서 warm-start ② rough 커리큘럼을 더 완만히(terrain level 천천히) ③ iter 2.5k+ ④ 낙상 분석(어느 지형/명령서 넘어지나).

## 3. 영상 / 이미지
- 학습 영상 22개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_rough/2026-06-21_10-33-47_stage5_rough_converge/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-21_10-33-47_stage5_rough_converge_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_rough/2026-06-21_10-33-47_stage5_rough_converge/videos/accumulated_progress.mp4`, 156MB)

## 4. 부모 학습 대비 비교
- **부모**: [[2026-06-21_06-41-42_stage4_rough]] (stage-4 rough, 1999 iter).
- **변경점**: stage-4 모델에서 이어 rough 수렴 시도(같은 rough task, 추가 iter). 핵심 차이는 **iter 누적**(수렴 목적). → 결과적으로 stage-4(1999)+stage-5(1300)로도 rough 미수렴(낙상 20%).
- **정량 비교**: error_vel stage-5 0.918 — rough는 평지(forefoot 0.5)보다 본질적으로 어려움. 낙상 20%는 rough 정책으로 배포 불가 수준.

## 5. 분석 (정성/정량)
- **정량**: 모터 측정 npz 없음(이 run은 measure 미실행) → 토크/속도/구조하중 분석 **보류**(배포 후보가 아니라 재측정 우선순위 낮음). TensorBoard 지표는 §2c.
- **정성**: rough에서 **미수렴**(낙상 20%·추종 0.918). 평지 base가 충분히 강건하지 않은 채 vx=2.0 rough로 밀어붙여 정책이 지형+고속명령을 동시에 못 잡음. = **전략 교훈**: 평지에서 *완전 수렴*(forefoot 계열) 후 rough 이전이 옳다(현재 forefoot 라인이 그 base를 만드는 중).

## 6. 관련 학습 / 연구 링크
- 부모 [[2026-06-21_06-41-42_stage4_rough]] · 평지 base 라인 [[2026-06-21_12-22-03_forefoot_cop]]·[[2026-06-21_16-30-58_forefoot_pushoff2]](여기서 강건 base 확립 → 이후 rough 재시도).
- 연구: [[27_training_review_loop]](미수렴 vs 보수적중단 — 이 run은 *미수렴이라 더 돌렸어야*) · [[14_heightmap_survey]](rough 커리큘럼).

