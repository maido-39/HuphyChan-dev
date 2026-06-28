# 2026-06-28 · G1 reward의 발 떨림·불안정·액추에이터 포화 원인 규명 + 최소 수정 설계

> 트리거 (user 2026-06-28): "G1+충격저감으로 가되, 우리 reward 대비 **발을 엄청 떨고, 걸음 불안정, 액추에이터 포화도 심해**. 여러 가설 세워 검증하고 진행." → reward 변경 전 ROOT CAUSE 연구 (규칙 [[feedback-reward-research-rule]], 훅 강제).

## 1. 증상 정량화 (측정 데이터)
**떨림 (torque chatter dτ/dt RMS [N·m/s] · omega 부호반전/s)** — G1이 gaitfix의 2~3배:
| 실험 | ankle_roll dτ/dt | rev/s | ankle_pitch dτ/dt | knee dτ/dt |
|---|--:|--:|--:|--:|
| g1vanilla | 179 | 13.5 | 927 | 1038 |
| g1van_full | 195 | 14.0 | 731 | 1186 |
| gaitfix_v7 | **119** | **6.8** | **305** | **477** |
| gaitfix_v4 | **96** | **7.2** | **279** | **475** |

**포화 ([[48_motor_util_sizing]])**: G1 ankle_roll RMS 169-200% rated·sat 9-42% vs gaitfix 101-113%·sat 1-6%. **비대칭** ([[47_gaitcycle_6dof]]): G1 절뚝(한 발 cycle)·stance 8-20% vs gaitfix 대칭·stance 43-57%.

## 2. 가설 + 검증 (reward 설정 직접 대조 — 결정적 증거)
| 가설 | 검증 (config diff) | 판정 |
|---|---|---|
| **H1** 약한 action_rate → chatter | G1 `action_rate_l2 -0.005` vs gaitfix `-0.008` | ✅ 기여 |
| **H2** ★ ankle 가속 페널티 부재 → 발 떨림(buzz) | G1 `dof_acc_l2` 범위 = **hip+knee만**(`[".*_hip_.*",".*_knee_joint"]`); gaitfix = **ankle 포함**(LEG_TORQUE_JOINTS). gaitfix 주석: "ankles excluded → high-freq buzz, >5Hz torque energy ankle 17-23%" | ✅ **주원인(smoking gun)** |
| **H3** 약한 토크벌점 → 포화 | G1 `dof_torques_l2 -1.5e-7` vs gaitfix `-1.5e-6` (**10× 약함**) | ✅ 기여 |
| **H4** ankle offload 항 부재 → ankle이 측방밸런스 전담 → 포화·절뚝 | G1엔 foot_flat_orientation·lateral_foot_placement·wide feet_distance·torque_soft_limit_ankle **전부 없음**; gaitfix엔 있음 | ✅ 기여 |

**배제(adversarial check)**: DR(g1van_full은 G1 DR 매칭인데도 떨림) · PD게인(ankle stiffness40/damping2 동일) · 네트워크(동일 아키텍처) → 차이는 **오직 reward 항**. 진단 확정.

## 3. 진단 결론
- **발 떨림** ← H2(ankle dof_acc 부재) + H1(약한 action_rate). 가장 직접적.
- **포화 악화** ← H3(10× 약한 토크벌점) + H4(ankle이 측방밸런스 전담).
- **불안정·절뚝** ← H4(lateral_foot_placement 부재 → 스텝이 아닌 ankle로 drift 보정).

## 4. 최소 수정 설계 (G1+충격저감 유지하며 떨림·포화만 제거; gaitfix처럼 과도하게 넣어 *안 걷게* 만들지 않기)
적용(저위험·표적):
1. ★ **dof_acc_l2에 ankle 포함** (hip+knee → LEG_TORQUE_JOINTS) — 떨림 직접 fix, 순수 평활이라 보행 저해 위험 낮음.
2. **action_rate_l2 -0.005 → -0.008** — 평활 소폭 강화.
3. **포화는 주로 액추에이터 교체로 구조적 해결**: ankle_roll RS00(14/5)→**DM-J4340-2EC(40/14)** = clip 14→40, 정격 5→14 → RMS%rated 자연 급감. 토크벌점은 과하면 *소심 gait*([[28_reward_actuator_fidelity]]) 위험이라 **소폭만**(ankle_roll 범위 -1.5e-7→-5e-7) 또는 유지.

보류(필요 시 단계적 추가, 보행 깨질 위험): foot_flat_orientation·lateral_foot_placement·wide stance — gaitfix서 *clean 조건 미보행* 원인일 수 있어 1차엔 제외, 떨림/비대칭 잔존 시 추가.

**검증 방법**: 위 수정 + 액추에이터 교체로 flat 학습 → measure → §1 chatter 지표 재측정(목표: ankle dτ/dt·rev/s를 gaitfix 수준으로) + §48 포화(목표 RMS%rated<100). 개선 확인 후 rough 이전.

★ **2026-06-28 업데이트 — 로봇모델 변경 반영**: reward_tuning 브랜치 로봇모델 채택(사용자 지시) = **toe 관절 복원**(passive spring, stiffness60/damping4/armature0.008) + primitive-capsule collision + G1식 발바닥 5캡슐 + self_collision off. ankle_roll 모터는 **DM-J4340-2EC(27/9, 무부하100rpm@48V)**, knee +1.8:1. ⚠ **본 떨림 진단(§1-2)은 *rigid-toe* 데이터 기반** — toe 복원으로 동역학이 바뀌므로 학습 후 chatter를 *재측정*해 fix 유효성 재확인 필요. 단 핵심 fix(ankle dof_acc 포함 + action_rate↑)는 toe와 독립적이라 그대로 적용. 학습: `Pygmalion-Velocity-Flat-G1ImpactStable-v0` (run g1is_dm4340_flat).

## 출처/내부
- 데이터: `scripts/scatter_torque_rpm.py`·chatter 일회분석. 설정: `g1_vanilla_env_cfg.py`(G1)·`velocity_env_cfg.py`(gaitfix).
- [[48_motor_util_sizing]]·[[47_gaitcycle_6dof]]·[[49_ankle_actuator_tn_sizing]]·[[28_reward_actuator_fidelity]]·[[g1-vanilla-beats-custom-reward]]
