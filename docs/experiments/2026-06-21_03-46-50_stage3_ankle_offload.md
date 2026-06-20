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

**이번 run 중요/신규 reward + 왜**: **[작성 필요]** — 추가·변경한 항과 그 이유 (어떤 측정/[[Paperreview/...]]·docs 연구가 근거인지). 예: `torque_soft_limit_ankle` 추가 → 포화 발목 offload(docs/17·22).

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
- reward 곡선 비교: 위 그래프(부모 점선). **정량 비교 [작성 필요]**: 무엇이 좋아졌나/나빠졌나.

## 5. 분석 (정성/정량)  **[작성 필요]**
- 정량: gait(추종·CoT)·관절 토크/파워·toe 사용도·진동(>5Hz)·낙상 — 측정 npz/analyze_motor_util 인용.
- 정성: 보행 자연스러움·실패모드·의도한 변경의 효과.

## 6. 관련 학습 / 연구 링크  **[작성 필요]**
- 관련 run: [[experiments/<run>]] — *어떤 관계, 무엇을 바꿨고 왜*.
- 활용 연구: [[Paperreview/<slug>]] / docs/16·17·18 — *어떤 결정에 썼는지*.

