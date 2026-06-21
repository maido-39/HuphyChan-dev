# 학습 리포트 — 2026-06-21_03-46-50_stage3_ankle_offload

- **task/run**: `2026-06-21_03-46-50_stage3_ankle_offload`  ·  **명령**: `train.py --task Flat-v0 --num_envs 16384 --max_iterations 2500 --run_name stage3_ankle_offload --init_checkpoint flat_wide_dr/model_1499.pt`
- **의도/변경점**: stage-2(넓은DR)에서 전이 + ★torque_soft_limit_ankle(0.80, -0.01) 추가 = 포화 발목 offload (docs/17·22, wseyrv4mz)

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_03-46-50_stage3_ankle_offload/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_03-46-50_stage3_ankle_offload/model_2499.pt`

## 2. 지표 (Metrics)
- **최종 Mean reward**: 36.21 (iter 2499), max 36.91
- **error_vel_xy**: 0.5024
- **error_vel_yaw**: 0.5072
- **curriculum_vel_x**: 2.0000

![reward curve](assets/2026-06-21_03-46-50_stage3_ankle_offload_reward.png)

## 2b. Reward (무엇을 · 왜)
활성 보상 항과 **최종 기여**는 아래. 각 항의 **의미 · 가중치 · 왜**는 → [[04_reward_experiments]] ("현재 활성 Reward 전체" 표) 참조 (재도출 금지, 링크로 추적).

**보상 항목별 기여(최종, 절대값 큰 순)**:
- `track_lin_vel_xy_exp`: +0.7817
- `track_ang_vel_z_exp`: +0.7453
- `upright`: +0.4713
- `feet_air_time`: +0.1020
- `joint_deviation_hip`: -0.0493
- `dof_acc_l2`: -0.0489
- `torque_soft_limit_ankle`: -0.0434
- `dof_torques_l2`: -0.0337
- `ang_vel_xy_l2`: -0.0268
- `action_rate_l2`: -0.0208
- `torque_soft_limit`: -0.0208
- `feet_distance`: -0.0205
- `feet_slide`: -0.0159
- `no_flight`: -0.0134
- `lin_vel_z_l2`: -0.0053
- `flat_orientation_l2`: -0.0053
- `termination_penalty`: -0.0025
- `dof_pos_limits`: -0.0011
- `base_height`: -0.0003

**이번 run에서 바뀐 reward (vs 부모, cfg diff)**:
```diff
+    #   verified reward fn, just scoped. (NOTE: this offloads the ankle but does NOT by itself LOAD
+    torque_soft_limit_ankle = RewTerm(
+        func=mdp.applied_torque_soft_limit,
+        weight=-0.01,
+        params={"soft_ratio": 0.80,
```

**이번 run 중요/신규 reward + 왜**: ★ `torque_soft_limit_ankle` (soft_ratio 0.80, weight −0.01, 발목 joints) **신규 추가** → 포화 발목(stage-2서 100% peak) 부하 분산. **결과**: ankle_pitch **100%→72% peak** ✅ (단 부하가 무릎으로 가고 toe엔 안 감 → CoT↑). 근거 [[17_toe_usage_vibration]]·[[22_energy_toe_reward]](wseyrv4mz item4).

## 3. 영상 / 이미지
- 학습 영상 40개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_03-46-50_stage3_ankle_offload/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)

## 4. 부모 학습 대비 비교
- **부모**: `2026-06-21_01-52-57_flat_wide_dr`
- **변경된 설정(velocity_env_cfg diff)**:
```diff
+    )
+    # ★ ANKLE OFFLOAD (research wseyrv4mz): the ankle (RS03 60 / RS00 14) saturates at 100% peak and
+    #   is the binding actuator. An ANKLE-scoped, tighter (0.80) + heavier soft-limit penalty pushes
+    #   the policy to reduce ankle peaks (offload toward knee/hip + the passive toe). Safe: same
+    #   verified reward fn, just scoped. (NOTE: this offloads the ankle but does NOT by itself LOAD
+    #   the toe -- toe loading needs a vel-norm power CoT + forefoot-rollover term, see docs/22.)
+    torque_soft_limit_ankle = RewTerm(
+        func=mdp.applied_torque_soft_limit,
+        weight=-0.01,
+        params={"soft_ratio": 0.80,
+                "asset_cfg": SceneEntityCfg("robot", joint_names=[".*_ankle_pitch_joint", ".*_ankle_roll_joint"])},
```
- 정량 비교 (vs stage-2): Mean reward 34→**36.2**, error_vel_xy 0.57→**0.50**(소폭 개선), **ankle_pitch 100%→72% peak**(offload ✅), 다리 진동↓. **단** toe 사용 26%→**6-13%↓**, CoT 높음.

## 5. 분석 (정성/정량)
**정량** (측정 `stage3_clip`/`stage3_unclip`, analyze_motor_util + Pmech):
- ✅ **ankle_pitch offload**: 이전 100% peak(포화) → **72% peak**(43 N·m, unclipped 65-71%). 발목offload reward 효과 입증.
- ⚠️ **ankle_roll 여전 100% peak**(14 N·m, unclipped도 100%) — 횡방향이라 분산 불가 → **RS00이 진짜 병목, 상향 필요**.
- 부하 재분배 행선지 = **무릎**(peak 831W/RMS 250W로 파워 dominant, 44-58% peak), 고관절 43-75%.
- ✅ **진동↓**: >5Hz 토크에너지 다리 감소 (knee 18-40%→**8.7%**, ankle 15-23%→**12-14%**) — `dof_acc` 전관절+`action_rate`−0.008 수정 작동.
- ❌ **toe 사용 26%→6-13% (감소)**, toe HF 76%(무부하 채터), 음의일 −1~−8J(미미).
- ❌ **CoT 0.81** (목표 0.2-0.5) — knee-dominant 비효율.

**정성**: 발목offload는 **ankle_pitch + 진동엔 성공**이나 부하를 **무릎으로** 보냈고 **toe 적재·효율은 실패**. → 연구([[22_energy_toe_reward]]) 예측 **"에너지/토크만으론 toe 안 실림"을 실측 확증**. toe 적재엔 **forefoot-rollover + vel-norm power CoT reward**(다음 실험) 필수.

## 6. 관련 학습 / 연구 링크
- **부모**: [[2026-06-21_01-52-57_flat_wide_dr]] (stage-2 넓은DR). **변경**: `torque_soft_limit_ankle` 추가(발목 offload). **왜**: stage-2 측정서 발목 100% 포화([[17_toe_usage_vibration]]·[[21_motor_power_weight]]).
- **활용 연구**: [[22_energy_toe_reward]](wseyrv4mz) — 발목offload는 부하분산엔 OK이나 toe 적재엔 forefoot-rollover 필요(이 run이 확증). [[Paperreview/caps-smooth-control]] — 진동(action 평활) 수정 근거.
- **다음**: forefoot-rollover + vel-norm power CoT([[22_energy_toe_reward]] 레시피) → toe 적재 + CoT↓ 목표, [[19_toe_ablation]]로 검증. HW: **RS00(ankle_roll) 상향** 검토([[21_motor_power_weight]]).

## 7. 모터 활용 시각화 (사후 추가 — 토크·속도 avg/max·스펙선·포화%·시계열)
> `bash scripts/analyze_run.sh`가 생성(이후 리포트는 자동 임베드). 전체 해석 [[24_training_health_analysis]].

**토크** (avg/max + rated/peak 가로선 + 포화%): ankle_roll L/R **100%(빨강)**, 나머지 여유.
![s3-tq](../assets/stage3_motor_torque.png)
**속도** (avg/max + 속도한계 + 포화%): knee L/R **102-106%(속도병목)**.
![s3-sp](../assets/stage3_motor_speed.png)
**토크 시계열 · 속도 시계열** (시간에 따른 관절별 활용, L파랑/R주황):
![s3-tqts](../assets/stage3_motor_torque_ts.png)
![s3-spts](../assets/stage3_motor_speed_ts.png)
- **HW**: ankle_roll 상향 · knee 감속비 1:3→**1:2**(속도 시계열이 병목을 직관 확인).

