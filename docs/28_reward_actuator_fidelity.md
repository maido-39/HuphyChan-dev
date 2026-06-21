# 리워드(열/부하분산) + 액추에이터 충실도(토크-속도) + RobStride 데이터시트 (연구 wyilgvpyj)

> [!abstract] 한 줄
> **power_cot이 ankle_roll 열과부하(RMS 151%)를 못 막은 이유 규명** → 열(τ²)/부하분산 리워드 3종 + 실제 토크-속도 선도(Shin clip) + 검증된 RobStride 스펙. 우리 토크스펙 정확, 속도 1건만 오류.

## 0. ★ 왜 power_cot이 ankle_roll 열과부하를 못 막았나 (핵심 진단)
`power_cot = exp(-scale·Σ_14|τ·ω|/...)` 의 두 결함:
1. **14관절 합산** — 과부하 1관절이 효율적인 13관절에 *가려짐*.
2. **POWER이지 HEAT 아님** — 발열 ∝ I²R ∝ **τ²**. 정지·저속 지지의 ankle_roll은 τ 큰데 **ω≈0** → `|τ·ω|`≈0 이라 power_cot에 거의 안 잡힘. 그런데 τ²로 발열. **그래서 151% 열과부하를 못 막음.**

## 1. 리워드 항 (우선순위, rewards.py에 추가 예정)
| 항 | 수식 | 가중 | 근거 / 위험 |
|---|---|---|---|
| **T1 열 RMS-hinge** (1순위) | 관절별 EMA 발열 `h←(1-a)h+a·τ²`(a=dt/τ_thermal), 패널티 `-w_T·Σ softplus(h/τ_rated²−1)` (정격 이하 0, 초과 시 성장) | ankle_roll 1.51×가 평균보상의 ~5-15% 되게 시작→RMS%rated<~90까지↑ | RMS-vs-연속정격 = 서보 사이징 원리. **정지토크도 잡음**(power_cot 못함). 위험: τ_thermal 시상수=RS00 열질량과 맞춰야(미검증, 식별 필요). 과가중→소심 gait. (Qian 2603.01631·VisualSizer) |
| **T2 이용률 hinge** (2순위, 부하분산) | `u_i=|τ_i|/τ_rated_i`, `-w_B·Σ max(u_i−1,0)²` (관절별 *자기* 정격 정규화) | 1관절 1.5×가 ~5-15% 보상 | ankle_roll 부하를 여유 있는 hip/knee로 분산. Shin의 단일모터포화 fix의 biped판. 위험: max=비평활→LogSumExp. *동일* 이용률 강제 금지(per-own-rating). |
| **T3 Joule τ²** (3순위) | `P_J=K⁻¹(τ+τ_f)²`, `r=-c_E·Σ(P_f+P_J)` | c_E~2.0(Solo12), 우리 스케일로 | power→thermal 다리. 단 전역합산(다시 가림)이라 T1/T2 뒤. **전기식별 필요**(Kt는 데이터시트, R·마찰 없음). (Fadini Solo12 2309.16683) |
| T-CBF (선택 업그레이드) | 온도상태 CBF, 온도추정 관측 추가 시 | A1: 2.0/γ0.35 | 온도근접 시만 작동(정상보행 세금 최소). 온도추정 필요. (Qian 2603.01631) |

> 적용: forefoot 후속 실험에 **T1+T2를 power_cot와 병행**, 곡선처럼 w_T/w_B를 0서 ramp. T3·CBF는 전기식별/온도추정 후.

## 2. 액추에이터 충실도 — 실제 토크-속도 선도 (Shin 2312.17507, KAIST Hound)
- **문제(우리 코드 검증)**: `ImplicitActuatorCfg`가 그룹별 **flat effort_limit**(ankle_roll 14·hip 120·knee 360). flat clip은 **모든 속도서 peak 토크를 credit** → 실제 RobStride T-N선도(corner까지 평탄→무부하속도서 0으로 선형)보다 고속 토크 과대평가. **Shin ablation서 이 항 제거 시 6.5→4.5 m/s(최대 기여, +2.0 m/s sim2real).**
- **Shin 방법(HTML 숙독)**: 리워드 아님·Lagrangian 아님·action filter 아님 — **물리 스텝 내부의 per-motor 토크 HARD CLIP**. 매 스텝: 정책→목표위치→PD→목표*관절*토크→기어박스로 *모터*토크 매핑→**MOR(Motor Operating Region)로 clip**→관절로 역매핑→적용. MOR = 준정상 DC전기식 선형 전압포락 `-Vbus ≤ (R/Kt)τ + (1/Kv)ω ≤ Vbus` (ω=0서 최대토크, 무부하속도서 0) + 별도 자속포화 peak cap.
- **우리 구현 계획**: YAML 각 그룹에 **T-N 포락(T_peak, ω_noload)** 추가 → flat effort_limit을 **속도의존 clip 액추에이터**로 교체(custom Actuator 또는 reward 후처리). 효과: 고속 토크 과대평가 제거 → 측정 하중이 sim2real-grade.

## 3. 검증된 RobStride 데이터시트 (공식 Lingfoot/RobStride PDF, OpenELAB 교차확인)
| 모델 | 역할 | rated/peak(N·m) | 무부하/정격부하 속도(rpm) | 감속비 | Kt(N·m/Arms) |
|---|---|---|---|---|---|
| **RS00** | ankle_roll | 5 / 14 | 315 / 260 | 10:1 | 1.48 |
| **RS03** | hip_yaw·ankle_pitch | 20 / 60 | **200** / 180 | 9:1 | 2.36 |
| **RS04** | hip_pitch·roll | 40 / 120 | 200 / 167 | 9:1 | 2.1 |
| RS04+1:3 belt | knee | 120 / 360 | 66.7 / 55.7 | 9:1×3 | — |
| RS01 / RS02 | ankle_roll 상향 후보 | 6 / 17 | 315·410 / 275·360 | 7.75 | — |

- ✅ **우리 토크 스펙 전부 정확**(RS00 5/14, RS03 20/60, RS04 40/120).
- ❌ **유일 오류**: YAML `hip_yaw_rs03`·`ankle_pitch_rs03` `velocity_limit_rpm` **220→200**(RS03 무부하 200; 60/20@220 모델 없음). + 무부하 vs 정격부하 속도 구분 명기 필요.
- 📌 **ankle_roll 상향 후보 = RS01/RS02**(rated 6, peak 17, 속도 ↑) — T1/T2/clip로도 RMS<5N·m 못 내리면 물리 교체.

## 4. 분석 메트릭 (RMS·p95·peak) — 확인
우리 `analyze_motor_timeseries`가 셋 다 정확히 계산함. 용도: **RMS vs rated = THE 열 사이징 판정(binding)**, p95 vs peak = 지속근접(단발 제외), max vs peak = 순간. → rule에 "RMS%rated가 binding 열판정" 명시.

## 5. 미해결 (식별 필요)
- RS00 **열 시상수**(τ_thermal) — 데이터시트엔 145°C 권선한계 곡선만. T1 시상수에 필요.
- RobStride **권선저항 R·마찰**(τ_u, b) — Kt만 있음. T3 Joule에 필요. → bench 식별(읽기리스트 Hwangbo actuator-net과 연계).

출처: [Shin 2312.17507](https://arxiv.org/abs/2312.17507) · [Fadini Solo12 2309.16683](https://arxiv.org/abs/2309.16683) · RobStride 공식 PDF(Lingfoot/Seeed·OpenELAB) · 관련 [[26_reading_list]] · [[21_motor_power_weight]] · [[27_training_review_loop]]
