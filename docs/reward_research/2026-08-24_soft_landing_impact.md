# 착지 충격("발을 팍팍 내딛음") — 정량 진단과 soft-landing 보상 처방 (2026-08-24)

## 증상 (사용자 관찰)
ankleAB_c2r / ankleRP_c2 (iter 2500, vx 0.8 단계) 보행에서 발이 바닥을 세게 친다.

## 정량 (물리 200 Hz, `tools/robot_model/loop_tests/impact_probe.py`, 0.4·0.8 m/s 각 10 s, 접촉력 = 발 geom 접촉합)

| 지표 (중앙값 / p90) | AB 폐루프 | RP 직렬 | 사람 보행 (1.0–1.3 m/s) |
|---|---|---|---|
| 발 접지 직전 수직속도 | **1.34 / 1.69 m/s** | **1.54 / 1.82 m/s** | 0.1–0.4 m/s (뒤꿈치) |
| 수직 GRF 피크 | 1.40 / 1.67 BW (max 2.17) | 1.55 / 1.89 BW (max 2.01) | 1.0–1.2 BW |
| 하중률 max dF/dt | **155 / 266 BW/s** | **158 / 207 BW/s** | 10–20 BW/s (달리기 50–100) |
| 피크 도달 시간 | 25 ms | 10 ms | 100–150 ms |
| 50 Hz 센서가 본 p99 (보상 관점) | 1.41 BW | 1.52–1.56 BW | — |

→ 피크 크기(1.4–1.6 BW)보다 **접지 속도(사람의 4×)와 하중률(10×)**이 "팍팍"의 실체. 피크는 20 ms 이상 지속돼 50 Hz 센서에도 잡히지만, 하중률·접지속도는 **어떤 보상도 보지 않는다**.

## 근본 원인
1. `soft_landing` weight −1e-5 = 사실상 꺼짐(첫접촉 50 Hz 한 샘플만 보는 항이라 켜도 약함).
2. `contact_force_cap` threshold 600 N은 **51.5 kg 로봇(BW 505 N)의 1.2 BW**로 잡은 값([[2026-07-02_gait_research_q123]] C11). 프린트 로봇은 BW 347 N → 600 N = **1.73 BW**, 클립 800 N = 2.3 BW. p90 피크(1.67–1.89 BW)가 역치를 스치는 수준이라 거의 작동하지 않는다.
3. 발 궤적 항(foot_clearance/swing_height, 목표 0.1 m)은 높이만 보고 하강 속도는 안 본다 → 정책은 발을 올렸다 **떨어뜨리는** 게 가장 싸다(air_time +1.0은 체공만 보상).
4. 시뮬 요인 아님: 구속 강성 스윕([[94_loop_constraint_stiffness]])에서 부드러운 구속이 오히려 더 튀었고, 접지속도는 정책이 만든 값.

## 문헌 (기존 노트 재사용)
- Humanoid-Gym 역치형 GRF 벌점(C11, 실로봇), Cassie smoothing/impact 가중치 커리큘럼(C3) — [[2026-07-02_gait_research_q123]].
- 착지 속도 항은 접촉 직전 **밀도 높은 신호**: 발이 지면 근처(h < h₀)에서 아래로 움직이는 속도를 벌점 → 접촉 순간만 보는 soft_landing보다 gradient가 매 스텝 살아 있음(Berkeley Humanoid·LimX 계열 "feet contact momentum / impact velocity" 항과 같은 형태).

## 처방 (`PYG_SOFT_LANDING=1`, 두 arm 동일 적용 — A/B 단일변인 유지)
| 항 | 변경 | 근거 |
|---|---|---|
| `foot_impact_velocity` (신규) | $\sum_{feet} \mathrm{relu}(-v_{z})\cdot[z_{foot} < 0.08\ \text{m} \wedge F < 0.02\,BW]$, 명령 게이트, **w = −2.0** | 측정 데이터에서 항 평균 0.04 m/s/발 → −2.0이면 스텝당 ≈ −0.16 (추종 +1.8의 9 %). 1.5 m/s 슬램 순간엔 −3/스텝 |
| `contact_force_cap` | threshold 600 → **420 N (1.2 BW)**, clip 800 → **560 N** | BW 재스케일(505→347 N) |
| `soft_landing` | 그대로(−1e-5) | 첫접촉 단일샘플 항, 대체됨 |
| 로그 | `Metrics/foot_impact_vel_mean`, `Metrics/foot_impact_vel_max` | 진행 추적 |

게이트: 4k iter 후 impact_probe 재측정 — 접지속도 중앙값 **< 0.6 m/s**, 하중률 중앙값 **< 60 BW/s**, 피크 p90 **< 1.4 BW**, 추종·낙상은 현행 대비 ±10 % 내. 미달이면 w −2 → −4, h₀ 0.08 → 0.12.

## 반증 가능 예측
접지속도 항만 켜도(역치 재스케일 없이) 하중률이 절반 이하로 떨어지면 "하강속도 무벌점"이 주원인. 안 떨어지면 GRF 역치(②)가 지배.

## 적용 시점
두 본 런은 iter ~2700/32000(8 %). 보상을 바꾸면 **둘 다 재시작**(A/B 공정성) — 결정은 사용자.
