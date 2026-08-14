# ★ 최종 설계점 — B3@12k 정책 worst-case 부하 (액추에이터 판정 v3)

> 2026-07-03. **최종 reward 스택**(A1b gains + contact_force_cap + thermal_effort + Siekmann)의 수렴 정책(model_12000, run `2026-07-03_(B3)`, wandb `m4ik3uph`)을 worst-case(vx≤2.5·yaw≤1.0, `--worst-case`, ×1.15)로 측정. **HW 설계의 확정 입력.** 07-01 hot-정책 평가([v2](2026-07-01_actuator_evaluation.md))를 대체.

관련: [계획 v2 전 게이트 기록](2026-07-02_training_plan_v2.md) · [메커니즘 설계](2026-07-03_knee_ankle_mechanism_design.md) · [링크 설계 지식지도](2026-07-05_link_design_what_to_know.md)

---

## 0. 보행 시연 — 고정 전후좌우 스윕 (C1 수렴 정책)

무작위 명령 학습영상으로는 보행 품질 판정 불가 → **고정 스케줄**(전진 0.5/1.0/1.5 → 후진 → 좌우 스트레이프 → 좌우 회전 → 대각 → 정지, 각 3초)로 구동한 시연. 화면 상단 초록 라벨=현재 명령, 관절구=토크 포화색.

![[c1_demo_loadviz.mp4]]

*생성: `measure_loads.py`(기본 COMMAND_SCHEDULE) → `render_loads.py`(방향 라벨). 방향별 보행·부하를 한눈에 판정 가능.*

---

## 1. 캠페인 성과 — reward/제어가 HW 요구를 바꿈

| 지표 | 07-01 hot 정책 | **FINAL B3@12k** |
|---|---|---|
| gait | 과격·비대칭·무릎꿇기 계보 | **대칭(asym 0.18)·주기 1.0s·직립 0.82** |
| GRF P99 / peak (wide-dr) | 2.0 / 4.4~9.3×BW | **1.63 / 2.18×BW** (823N / 1.10kN) |
| ankle_pitch RMS | **113%(주범)** | **47%** ✅ |
| ankle_roll RMS/peak | 72%/**115%** | **14%/20%** ✅ |
| knee RMS (wc-flat) | 80%(clip 숨김) | **112%** — 유일 잔존 |
| 시스템 P_mech peak | 3.0 kW | **1.1 kW** |


## 1b. 최종정책(B3) Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| track_angular_velocity | **+2** | 명령 회전속도 추종 | \exp(-err²/std²) |
| track_linear_velocity | **+2** | 명령 전진/측방 속도 추종 | \exp(-err²/std²) |
| periodic_contact | **+1.5** | ★Siekmann 위상접촉(대칭 주기보행) | stance:발속도↓ swing:발힘↓ |
| dof_pos_limits | **-1** | 관절범위 한계 접근 벌점 | 한계초과 L1 |
| pose | **+1** | 기본 관절자세 정규화(기괴자세 억제) | default-pose L2 |
| self_collisions | **-1** | 자기충돌 벌점 | -접촉수 |
| upright | **+1** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| action_rate_l2 | -0.1 | 액션 급변 벌점(진동/저크 억제) | -|Δ a|² |
| foot_slip | -0.1 | 접지발 미끄러짐 벌점 | -|v_contact| |
| body_ang_vel | -0.05 | 몸통 각속도 벌점(흔들림 억제) | -|ω|² |
| angular_momentum | -0.02 | 전신 각운동량 벌점(회전 낭비 억제) | -|L|² |
| thermal_effort | -0.02 | ★열분배: \Sigma(τ/rated)² 정규화(관절 균등화) | -\Sigma(τ/rated)² |
| contact_force_cap | -0.01 | ★충격 cap: 발 GRF 역치초과분 벌점(사뿐착지) | -min(max(F-600,0),800) |
| soft_landing | -1e-05 | 착지 첫접촉 충격 벌점(약) | -첫접촉 GRF |
| air_time | +0 | 체공시간 보상(질질끌기 억제) | off(0) |
| foot_clearance | +0 | 스윙발 지면 이격(발끌림 방지) | off→clock이 대체 |
| foot_swing_height | +0 | 스윙발 높이 성형 | off→clock이 대체 |
| torque_limit | -0 | commanded 토크 한계초과 벌점 | off(0) |

**관절별 Kp/Kd** (position-PD, effort=관절측 peak):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 400 | 28 | 120 |
| hip_roll | RS04 | 400 | 28 | 120 |
| hip_yaw | RS03 | 400 | 9 | 60 |
| knee | RS04 | 400 | 8 | 120 |
| ankle_pitch | RS03 | 19.7 | 1.26 | 60 |
| ankle_roll | RS00 | 1.97 | 0.126 | 14 |


## 2. 최종 판정표 (worst-case, ×1.15) — 상세 `assets/actuator_eval_summary.md`

**[flat]** 미달 3: **knee**(RMS 112%·S 0.78/175℃ — 유일 실질), hip_yaw·ankle_pitch(corner 순간 peak touch 108~115%=clip×1.15 artifact 포함). hip·ankle_roll 전부 여유.
**[rough — R1b 정식학습, 100% in-DR worst-case]** ✅ **blind-OOD 추정 대체 완료**. 확장 DR(yaw±1.5)로 worst-case **구성상 100% in-DR** → 07-03 아침의 "rough 6/6 미달·속도 4-6×"는 **blind+OOD 아티팩트였음 실측 확인**. ★ **수렴 정책(39k 완주) = 권위 데이터** — mid-training(12k)은 낙관적이었음(★사용자의 '3000 너무 짧다' 지적 실증):
| iter | GRF P99/peak | knee RMS | ankle_pitch | ankle_roll(RS00기준) | base |
|---|--:|--:|--:|--:|--:|
| 12k | 1.50/2.15 | 93% | 56% | 29% | 0.83 |
| 30k | 1.74/2.40 | 89% | 84% | 138% | 0.85 |
| **39k(완주·권위)** | **1.81/3.01** | **107%** | 62% | **134%** | 0.86 |
- ★ **수렴서 부하↑**(더 선 자세 base 0.86): **knee 107%(over rated)**·**ankle_roll 134%(RS00-5 초과!)**. → 두 가지 재확인: ① knee 링크레버 1.5:1 필수(107/1.5=71%) ② **ankle_roll 2-RSU 업그레이드(G1 effort 50) 정당화** — RS00-5 단독이면 수렴 rough서 과부하(134%), 방금 적용한 2-RSU-50 스펙선 13%로 대여유. ankle_pitch 62%. GRF peak 3.01(여전 <flat계 9.3). signed: `regime_mjlab_R1b_final_rough.png`.
> ★★ 교훈: **12k 중간판정이 knee 93%·ankle_roll 29%로 낙관→수렴서 107%·134%**. 게이트는 6000+ 아니라 **수렴(완주)까지 봐야 HW 사이징 유효**(mid-training 부하는 과소평가).

플롯(q-scatter 룰 포함):

![[torque_speed_final_flat.png]]
![[q_torque_final_flat.png]]
![[q_speed_final_flat.png]]

(rough: `assets/*_final_rough.png`) · **18패널 종합(한계선 명기)**: ![[regime_FINAL_B3_mjlab.png]] · 영상: `assets/final_{flat,rough}_{loadviz,dashboard}.mp4` · CSV: `assets/actuator_eval_final_{flat,rough}.csv` (07-01 노트의 flat/rough 라벨 플롯은 원 데이터로 복원 유지)

## 2b. 학습 진행 영상 (B3 ACCUMULATION)
![[accum_B3.mp4]]

*(B3 최종정책 학습의 iter별 진행. 전 phase 영상: `assets/accum_{A1b,B1,B1w2,B2,B3,R1}.mp4`, per-run 노트 docs/experiments/*_mjlab_*.md)*

## 3. HW 확정 권고 (메커니즘 설계 입력)

1. **knee = 링크(푸시로드) 레버 1.4~1.6:1** ([설계 노트](2026-07-03_knee_ankle_mechanism_design.md) §3) → 유효 RMS 112/1.5 ≈ **75%** ✅. 벨트 불요.
2. **ankle = 2-RSU**: RS03급 2개 co-actuation → pitch 수요(RMS 9.4·peak 65)에 대여유 + **정적 toe-stance 63N·m 한계도 모터당 ~32로 해소**. 07-01의 "ankle_pitch 상향" 권고는 **본 정책 기준 철회**(정책·자세 개선이 해결).
3. **ankle_roll RS00/DM 스왑 불요 가능성**: worst-case peak 2.8~8.5 vs RS00 14 — B-스택이 roll 수요 자체를 제거. DM-J4340 스왑([노트](2026-07-01_ankle_dm4340_swap.md))은 **보류**(rough 정식학습 후 재확인).
4. hip_yaw: corner 순간 touch만 — RS03 유지.
5. 설계 수요표(×1.15, wc-flat): knee RMS 44.7/P99 94/peak 138·ω P99 42rpm / ankle_pitch 9.4/36/65·45rpm / 상세 CSV `assets/actuator_eval_flat.csv`.

## 4. 재현
```bash
# 측정(최종 정책) → 판정 → 영상
RD=logs/rsl_rl/pygmalion_velocity/<B3 run>
CUDA_VISIBLE_DEVICES="" uv run python analysis/measure_loads.py --run-dir $RD --checkpoint $RD/model_12000.pt \
  --task Mjlab-Velocity-Flat-Pygmalion --tag final_flat --worst-case --steps 7200   # (+rough: --blind --rough-terrain)
uv run python analysis/actuator_eval.py --tags final_flat final_rough --labels flat rough
MUJOCO_GL=egl uv run python analysis/render_loads.py --npz analysis/out/final_flat.npz --tag final_flat --out docs/mujoco/assets --downsample 2
```
reward 스택·게이트 이력 전문: [계획 v2](2026-07-02_training_plan_v2.md). 잔여 로드맵: rough 정식학습(OOD 해소)·속도-스케줄 clock(B3b)·toe 지오메트리 추가(Q3 완결)·`mech_design_eval.py`(기하 스윕).
