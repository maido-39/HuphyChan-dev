# 95. 부드러운 착지 — 진단·시행착오·문헌·시험·처방 (2026-08-24, 자율 세션)

사용자: "발을 너무 팍팍 내딛는 것 같다. 수치로 확인하고 좀 더 부드럽게." → 정량 진단([[2026-08-24_soft_landing_impact]] 연구노트) → 과거 시행착오·문헌 조사(Sonnet, 원자료 [research_raw/2026-08-24_soft_landing_research.md](research_raw/2026-08-24_soft_landing_research.md)) → 짧은 warm-start 시험 2회 → 처방 확정 → 본 런 적용.

## 0. 결론 (시험 결과 반영 — §4)
- **진단**: iter 2500 정책은 발을 **1.3–1.5 m/s**로 내려놓고(사람 0.1–0.4), 하중률 **~155 BW/s**(사람 10–20), GRF 피크 1.4–1.6 BW(사람 1.0–1.2). 피크보다 접지속도·하중률이 문제. 어떤 보상도 하강속도를 보지 않았고, GRF 캡 역치(600 N)는 옛 51.5 kg 기준이라 35 kg 로봇엔 1.73 BW.
- **시험 1 (선형 relu(−v) 밴드 벌점, w −2)**: **해킹** — 접지속도 1.24 → **2.42 m/s**로 악화. Σv·dt = 밴드 높이(상수)라 속도 무관, 정책은 밴드를 빨리 통과. 교훈 저장(memory).
- **시험 2 (제곱 v², w −1, h 0.10)**: §4.
- 문헌 검수: LimX TRON1 `foot_landing_vel` = Σ v_z²·[h<0.08 ∧ ¬contact ∧ v_z<0], w −0.15 (tracking 1) — 원문 확인(`pointfoot_flat.py:414-420`, `about_landing_threshold=0.08`). 우리 제곱형과 동일 구조.

## 1. 정량 진단 (200 Hz, `impact_probe.py`)
| 지표 (중앙값 / p90) | AB 2500 | RP 2500 | AB 3100 (기준) | 사람 |
|---|---|---|---|---|
| 접지 직전 수직속도 [m/s] | 1.34 / 1.69 | 1.54 / 1.82 | 1.24 / 1.36 | 0.1–0.4 |
| GRF 피크 [BW] | 1.40 / 1.67 | 1.55 / 1.89 | 1.50 / 1.64 | 1.0–1.2 |
| 하중률 [BW/s] | 155 / 266 | 158 / 207 | 151 / 223 | 10–20 |
| 피크 도달 [ms] | 25 | 10 | 30 | 100–150 |

## 2. 과거 시행착오 요약 (전체 표는 원자료 §1)
| 시기 | 문제 → 시도 → 결과 | 교훈 |
|---|---|---|
| 06-28 asimov as-is | air_time +0.5 + 타이트 ankle 벌점 이식 → GRF 2.1 → **3.9 BW** | 차용 레시피를 질량 안 맞추고 쓰면 사고 |
| 06-28 g1is | 임팩트 항만(foot_landing_vel −1, impact_force −0.005) → 까치발·ankle 포화 | 임팩트 항 단독은 불충분, foot-flat/자세 앵커 필요 |
| 06-29 siekmann v8 | periodic_contact +1.5 → GRF 8.9 → **3.1 BW**, 비대칭 0.83 → 0.18 | 위상 항 하나가 충격·대칭·에너지 동시 해결 |
| 06-29 v9 | push-off work 보상(캡 없이) → GRF **11.5 BW** | 임팩트 캡이 push-off보다 먼저 |
| 07-03 B1→B1w2 | contact_force_cap clip 400 → 800 | 클립이 낮으면 큰 스파이크 gradient가 죽음 |
| 07-03 B1→B3 | cap → thermal → clock 누적 → GRF P99 2.45 → 1.63 BW | 단일 "마법" 항 없음, 순서 누적 |
| 07-06 | 클록 제거 후 셔플(DS 49 %) → air_time +1.0 | swing을 강제 안 하면 에너지최소 셔플 |
| 07-12/13 gen2→gen21 | 절대 임계 stand_still → 크리핑 해킹 → 상대 임계로 수정 | 절대 임계값 = 게임 가능 |
| 07-12 bent init | GRF 피크 −37 %, knee P99는 P1 +98 %/P2 −20 % | 자세로 충격 줄이면 무릎 부하가 반대로 움직일 수 있음 |

## 3. 문헌 (검수 완료 표시 ✓)
| 항 | 식 | w | 게이트 | 로봇/배포 |
|---|---|---|---|---|
| LimX TRON1 `foot_landing_vel` ✓ | Σ v_z² | −0.15 | h<0.08 ∧ ¬contact ∧ v_z<0 | TRON1 (제품 RL 리포) |
| Humanoid-Gym `feet_contact_forces` | Σ clip(‖F‖−700, 0, 400) | −0.01 | 상시 | XBot 실기 |
| legged_gym/unitree_rl_gym `feet_contact_forces` | Σ clip(‖F‖−F_max, 0) | cfg | 상시 | G1/H1 실기 |
| Cassie jumping `Ground Impact` | exp(−αF_z²) | 5→10 | 비행/접근 위상만 | 실기 |
| Olympus `Catch landing` | clamp(−v_z, 0, 1) | ? | 착지 국면 | 실기 |
| Booster T1 `feet_vel_z` | Σ(Δz/dt)² | **0** (꺼둠) | — | 실기 배포(항은 off) |

해킹 모드(문헌+우리): 정지/동작거부, 양발 호핑, 셔플(클리어런스·stride 축소로 밴드 노출 회피), 크라우치로 무릎 부하 전가, 절대 임계 크리핑, **밴드 통과 가속(시험 1에서 실측)**.

## 4. 시험 (AB c2r model_3100 warm-start, 1024 env, +800 iter, 0.4/0.8 m/s 측정)
| | 기준 3100 | 시험 1: 선형 w −2, h 0.08 | 시험 2: 제곱 w −1, h 0.10 |
|---|---|---|---|
| 접지속도 중앙/p90 [m/s] | 1.24 / 1.36 | **2.42 / 2.92 (악화)** | (§4b) |
| 하중률 중앙 [BW/s] | 151 | 192 | |
| GRF 피크 중앙 [BW] | 1.50 | 1.66 | |
| F p99 200 Hz [BW] | 1.47 | 1.22 (캡 재스케일 효과) | |
| vx 오차 0.8 | 0.075 | 0.16 | |
| swing / strides/s / stride / apex | 0.39 s / 2.4 / 0.60 m / 0.116 m | 0.47 / 1.9 / 0.61 / 0.135 | |
| 정지 발 움직임 | 0.007 m/s | 0.005 | |

### 4b. 시험 2 결과
(기입 예정)

## 5. 처방 (확정 시 두 arm 동일 적용: `PYG_SOFT_LANDING=1`)
- `foot_impact_velocity`: Σ_feet relu(−v_z)^**2** · [h_sole<0.10 ∧ F<7 N], 명령 게이트, w −1.0 (LimX −0.15×tracking 1 ↔ 우리 tracking 1.8+1.0 스케일 고려).
- `contact_force_cap`: 420 N / clip 560 N (역치·클립 비율 1.33 유지 — B1 교훈).
- 감시 지표(해킹 방지): air_time·클리어런스·stride·정지 발 움직임·knee 토크·추종 — §4 표와 동일 프로브를 게이트(4k·8k)마다.
