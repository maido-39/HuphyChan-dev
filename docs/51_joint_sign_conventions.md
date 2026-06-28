# 51 · 관절 부호 규약 (FK-검증) — 사람 gait retargeting용

> MuJoCo FK probe(`scripts/viz_collision.py`와 동일 모델, robot.xml)로 각 관절 +0.2rad 단독 적용 시 발/toe 변위를 측정해 **부호 규약을 추측이 아닌 ground-truth로 확정**. 사람 gait 추종(retargeting) 구현의 기준. 월드 규약: **forward = +x, up = +z**(base quat 적용 후). Isaac action/obs 부호 = MJCF axis 부호와 동일(컨버터 보존).

## 검증된 관절 순서 (BFS, L=even/R=odd; memory)
`[L_hip_pitch,R_hip_pitch, L_hip_roll,R_hip_roll, L_hip_yaw,R_hip_yaw, L_knee,R_knee, L_ankle_pitch,R_ankle_pitch, L_ankle_roll,R_ankle_roll, L_toe,R_toe]` — 12 actuated(toe 2개는 passive 제외). L↔R mirror = 인접쌍 swap + **hip_roll·hip_yaw·ankle_roll 부호반전**.

## 관절별 (axis / range / 부호 / 사람-매핑)
| 관절 | axis(L) | range [rad] (deg) | +값 방향 (FK) | 사람 gait 매핑 |
|---|---|---|---|---|
| hip_pitch | 1 0 0 | -2.18~+0.52 (-125~+30) | +0.2 → 발 **뒤(-x)=신전** | ★ **음수=굴곡(flexion)**. `q = -hip_flex_deg` (사람 굴곡+30°→ q≈-0.52) |
| hip_roll | 0 -0.97 0.26 | -0.79~+0.44 (-45~+25) | +0.2 → 발 **+y(외전측)** | 작게 유지(frontal). L↔R 부호반전 |
| hip_yaw | 0 0 -1 | ±0.87 (±50) | +0.2 → 약간 회전 | ~0 유지(transverse) |
| knee | -1 0 0 | -2.44~+0.17 (-140~+10) | +0.2 → 발 **앞(+x)=신전** | ★ **음수=굴곡**. `q = -knee_flex_deg` (사람 swing+60°→ q≈-1.05) |
| ankle_pitch | -1 0 0 | -0.87~+0.70 (-50~+40) | +0.2 → toe-tip **위=dorsi** | ★ **양수=dorsi, 음수=plantar(toe-off)**. `q = +ankle_dorsi_deg` (사람 plantar-20°→ q≈-0.35) |
| ankle_roll | 0 1 0 | ±0.35 (±20) | (회전만) | 작게 유지(frontal). L↔R 부호반전 |
| toe(passive) | 1 0 0 | -0.87~0 (-50~0) | 단방향(음수만) | ★ **추종 안 함** — passive spring, 부하로 emergent(windlass) |

## ★ Retargeting 부호 공식 (사람 sagittal → 우리 actuated 관절, rad)
사람 관절각(굴곡/dorsi를 +로 정의, deg→rad) 기준:
- `q_hip_pitch  = -deg2rad(hip_flexion)`      (사람 hip 굴곡 → 로봇 음수)
- `q_knee       = -deg2rad(knee_flexion)`      (사람 knee 굴곡 → 로봇 음수)
- `q_ankle_pitch = +deg2rad(ankle_dorsiflexion)` (사람 plantar(-) → 로봇 음수)
- `q_hip_roll/yaw, q_ankle_roll`: frontal/transverse — sagittal-dominant 단순화로 ~0(또는 사람 frontal 소량), L↔R 부호반전.
- toe: actuated 아님 → reference 없음(collision+spring로 자연 발생).

## 주의
- range 비대칭이 부호의 교차검증: hip_pitch 큰 범위가 음수(-125°)=굴곡, knee 큰 범위 음수(-140°)=굴곡 → FK와 일치.
- ankle_pitch/roll·toe는 관절이 발 원점 근처라 **위치 변위 ~0**; 방향은 toe-tip(L_toe_link) 변위로 판정.
- 사람 데이터의 각 정의(부호·zero)는 출처마다 다름 → 인코딩 시 출처 규약 명시 후 위 공식으로 변환. (사람 데이터 워크플로 w9d8ys8av 결과 사용.)
