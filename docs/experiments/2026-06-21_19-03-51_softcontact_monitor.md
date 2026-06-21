# 모니터링 로그 — softcontact (충격↓ HW 생존)

> [!info] run / 가설 / 동기
> run `2026-06-21_19-03-51_softcontact` · warm-start pushoff3 model_500 · 16384env.
> **동기(측정 기반)**: forefoot_cop·pushoff3 측정서 **충격 = 링크 reaction wrench 5~6.7kN (체중 13배)** = 3D프린트+Al HW 파손한계(1.5kN)의 **4배**. push-off는 toe 적재도 못 늘림(5.7/19.7%). → 충격을 직접 줄여야 HW 생존.
> **H-A(가설)**: `foot_landing_vel`(w-2.0, height<0.12서 발 하강속도 벌점 = 충격의 *원인*) + `foot_impact_force`(w-0.01, contact force>650 soft-cap) → **구조하중 peak이 <1.5kN로 하락**, 보행·추종 유지. ([[Paperreview/kuo-donelan-dynamic-walking]] collision, [[29_natural_gait_reward_hw]])

## 정량 로그
| 시각 | iter | reward | noise_std | error_vel | ep_len | 낙상 | landing_vel | impact_force | 판정 |
|---|---|---|---|---|---|---|---|---|---|
| (config-test) | 40 | 15.5 | — | 0.82 | — | — | -0.21 | -0.45 | 회복·항 작동 |

## 정성 + 디버깅
- config-test(40iter): reward 음수→+15 회복, 새 항 작동(landing_vel -0.21·impact_force -0.45), 크래시 없음. error_vel 0.7-0.8(push-off 0.5보다↑ = 페널티 trade-off, 수렴 추적 필요).
- ★ **핵심 발견**: HW 파손력 6.7kN은 **링크 reaction wrench(구조하중)** — contact sensor(지면력)는 그보다 작아 force 벌점만으론 약함 → **착지 속도(원인) 벌점이 주 레버**.

## 진짜 판정 = 재측정
완주 후 `measure.py` → **구조하중 peak**(forefoot_cop 5.5kN/pushoff3 6.7kN 대비)이 <1.5kN로 떨어졌나 + toe 적재·추종. **안 떨어지면**: 가중치↑ 또는 **PD 컴플라이언스**(발목 강성↓+댐핑 = 기계적 흡수)로 전환.

## 다음 추적 (보수적 중단)
reward 회복 지속 + error_vel 수렴(<0.6 목표) + 낙상<5%. landing 페널티가 보행을 망가뜨리면(error_vel↑·낙상↑) 가중치 하향. [[27_training_review_loop]] · [[24_training_health_analysis]]

관련: [[2026-06-21_16-30-58_forefoot_pushoff2]] · [[29_natural_gait_reward_hw]] · [[30_knee_biomechanics]]
