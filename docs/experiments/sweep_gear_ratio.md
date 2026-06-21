# 무릎 감속비 SWEEP — 결과 (살아있는 노트, 비별 갱신)

> 순환성 깨기: 후보 감속비를 *각각 학습*(8192env·warm-start forefoot_cop·800iter·impact완화 −1.0/−0.005)해 demand·성능 측정·비교. 설계 근거 [[35_knee_gear_ratio_analysis]]. 평지(forefoot task) 기준.
> 실행 run: `2026-06-21_22-30-15_sweep_g1p0`(g1.0 ✅·측정 sweep_g1p0.npz) · `sweep_g1p5`(g1.5 진행) · `sweep_g2p0` · `sweep_g2p5`. 각 비 단독 학습(8192env=OOM안전).

## 결과표 (비별)
| g | knee effort/vel | 무릎토크 RMS/p95/max | 무릎속도 p95/max(rpm) | 토크활용 | 속도활용 | error_vel | reward | 판정 |
|---|---|---|---|---|---|---|---|---|
| **1.0 직결** | 120/200 | **21/46/80** | **59/105** | RMS 53%연속·max 67%peak | max **53%** | **0.617** | 37.0 | ✅ 토크·속도 다 여유 |
| 1.5 | 180/133 | (진행) | | | | | | |
| 2.0 | 240/100 | | | | | | | |
| 2.5 | 300/80 | | | | | | | |

## ★ 핵심 발견 — demand가 설정 따라 *공진화* (순환성 실증)
- 벨트 1:3로 학습한 정책: 무릎토크 RMS 32·max 158·속도 클립 66.7rpm.
- **직결로 학습한 정책: 무릎토크 RMS 21·max 80·속도 max 105rpm.**
- → 정책이 *그 비의 한계*에 맞춰 다른 gait 학습 = **1:3 데이터를 다른 envelope에 투영한 분석은 순환**이었음(사용자 지적 정확). 직결-학습 무릎은 158 N·m가 필요 없었음(80<120 plateau).
- **직결 평지 충분**(토크 67%peak·속도 53%). 단 **ROUGH는 미검증**(이 sweep은 평지 forefoot task) — rough-학습 직결의 무릎 토크가 120 넘는지 별도 확인 필요.

## 가설 (H2) 진행
저감속(1.0-1.5) 추종·효율 우수, 고감속(2.5) 속도캡으로 추종↓ 예상. 직결 error_vel 0.617 = 기준. 1.5/2.0/2.5 비교 대기.

관련: [[35_knee_gear_ratio_analysis]] · [[33_knee_actuator_landscape]] · [[experiment_queue]]
