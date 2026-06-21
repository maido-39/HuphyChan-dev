# 학습 리포트 — 2026-06-21_15-40-30_forefoot_pushoff

- **task/run**: `2026-06-21_15-40-30_forefoot_pushoff`  ·  **명령**: `(미기록)`
- **의도/변경점**: ankle_pushoff scale=0.1 = REWARD-HACKED (reward 324, error_vel 1.56) — documented FAILURE, superseded by pushoff2

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/model_300.pt`

## 2. 지표 (Metrics)

## 2b. Reward (무엇을 · 왜)
활성 보상 항과 **최종 기여**는 아래. 각 항의 **의미 · 가중치 · 왜**는 → [[04_reward_experiments]] ("현재 활성 Reward 전체" 표) 참조 (재도출 금지, 링크로 추적).
- (로그에서 보상 항목 미검출 — 학습 로그 경로 확인)

**이번 run 중요/신규 reward + 왜** (env.yaml 확인):
- **★ `ankle_pushoff` (w=1.0, scale=0.1) — 신규이자 실패 원인**: Kuo push-off 일을 직접 보상하려 했으나 **w·scale이 둘 다 과대**(정상은 w0.5·scale0.02). 이 과대값이 push-off 항을 484까지 폭주시켜 추종을 죽임(=reward-HACK). 인과 보상 의도는 옳았으나([[Paperreview/kuo-donelan-dynamic-walking]]·[[29_natural_gait_reward_hw]]) **일(work) 보상엔 cap + 작은 scale이 필수**라는 교훈(→ [[2026-06-21_16-30-58_forefoot_pushoff2]]에서 scale0.02·cap80·w0.5로 정상화).
- `forefoot_cop` w0.5·`power_cot` w0.4 등 나머지는 부모 forefoot_cop과 동일(여기선 ankle_pushoff 과대가 전부를 가림).

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![tb](assets/2026-06-21_15-40-30_forefoot_pushoff_tensorboard.png)

- **수렴(noise_std)**: 0.27 → **0.34** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.7 → **484.5**, ep_len 최종 **975**
- **추종 error_vel_xy**: 최종 **1.732** (낮을수록 good), yaw 1.618
- **안정성 낙상률 6%** (base_contact 0.88 / time_out 12.62) (주의 ⚠️)
- **value loss 최종** 17.723, entropy 2.802, LR 2.6e-04
- **커리큘럼 vx 상한 최종** 1.49
- **정성 해석(★ REWARD-HACKING 실패 사례)**: reward 0.7→**484.5**(!!)인데 error_vel **1.732**(최악) = **추종을 버리고 push-off 보상만 farming**. ankle_pushoff `scale=0.1`이 너무 커서, 정책이 명령속도 추종 대신 **발목을 진동시켜 tau·omega 양수일을 긁음**(value loss **17.7**=폭주 보상에 가치함수 못 따라감). 교과서적 reward-hacking(*상관* push-off일을 직접 보상하면 게임됨, Skalse 2022 / [[23_toe_use_methods]]). 낙상 6%는 낮아 보이나 추종이 죽어 무의미. **판정: 폐기**. **수정**: scale 0.1→**0.02 + cap 80**(진동 farming 차단)+w0.5 → 자식 run에서 정상화.

## 3. 영상 / 이미지
- 학습 영상 5개: `logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/videos/train/` (rl-video-step-0 … 6000).
- **누적(step-captioned) 영상 — 노트에서 재생**:
![[2026-06-21_15-40-30_forefoot_pushoff_accumulate.mp4]]
  (원본 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/videos/accumulated_progress.mp4`, 4MB)

## 4. 부모 학습 대비 비교
- **부모**: [[2026-06-21_12-22-03_forefoot_cop]] (CoP 진단 run).
- **변경점**: `ankle_pushoff_work` 추가, **scale=0.1**(과대) → 이 과대값이 해킹의 원인. cop 대비 reward가 0.7→484로 폭발한 게 적신호였음(정상이면 ~40대).

## 5. 분석 (정성/정량)
- **정량**: 모터 측정 불필요(해킹 run = 배포 무의미). TensorBoard만으로 진단 완료(§2c: reward 484 + error_vel 1.73 = 해킹 확정).
- **정성**: **모니터링 루프가 잡아낸 성공 사례** — iter ~190서 reward 324·error_vel 1.56 보고 즉시 중단·수정([[27_training_review_loop]]의 "reward-hacking → 보상 고치고 재시작" 케이스). 교훈: **push-off 같은 *일(work)* 보상은 반드시 cap + 작은 scale**(안 그러면 진동 farming).

## 6. 관련 학습 / 연구 링크
- 부모 [[2026-06-21_12-22-03_forefoot_cop]] → 수정 자식 [[2026-06-21_16-30-58_forefoot_pushoff2]](scale0.02+cap80, 정상).
- 연구: [[23_toe_use_methods]](직접 일-보상 = anti-pattern) · [[29_natural_gait_reward_hw]](push-off 보상 가드: cap·작은 scale) · [[27_training_review_loop]](해킹 탐지·중단).

