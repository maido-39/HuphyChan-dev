# 55 · 초기자세 A/B — straight(편) vs bent(굽힌 무릎) 통제 비교

> 2026-07-08. "초기자세를 조금 굽혀 시작 vs 펴서 시작, 어느 쪽이 토크↓·에너지효율↑·하중↓·자연스러운가?" 변인통제(seed 42, Kd6, PYG_NO_DR=1, 오직 init pose만: HOME knee 0°/base 0.87 vs KNEES_BENT knee −38°/hip −18°/ankle +21°/base 0.83). init_state가 pose reward 타겟(default_joint_pos)과 결합돼 **초기자세+서있는 타겟 동시** 변경. straight=B(2026-07-07_18-51-51), bent=2026-07-08_13-33-33_bent_kd6, 둘 다 10000-iter. 방법: [[pyg-no-dr-gating]]·[[feedback-qtarget-analysis-rule]].

## 1. 종합 — 명확한 승자 없는 트레이드오프 (가설 "straight=토크폭증"은 기각)

| 지표 | straight | bent | 승자 |
|---|--:|--:|---|
| sum\|tau\| p95 (총관절토크) | 222 | 212 N·m | bent 약간↓ (−5%) |
| sum\|tau\| peak | 348 | 310 N·m | bent↓ |
| **CoT (positive work)** | **0.162** | 0.175 | **straight** (에너지 8%↑효율) |
| 기계일률 | 81.7 | 88.3 J/m | straight↓ |
| **GRF peak** | 2.15 | **1.39 BW** | **bent** (충격 35%↓) |
| GRF p95 | 1.14 | 1.03 BW | bent↓ |
| 이동거리(동일명령) | 29.8 | 20.6 m | straight (전진속도 추종↑) |

## 2. 관절별 토크/오차 — 부하 재분배 (q/qtarget/error 표준분석)

![[qtarget_error_straight_vs_bent.png]]

tau_p95 [N·m] / err_p95 [rad] (L+R pooled, PD fit **R²=1.00 양쪽 = 무포화**):

| joint | straight tau | bent tau | Δ | straight err | bent err |
|---|--:|--:|--:|--:|--:|
| hip_pitch | 50.9 | 38.9 | **−24%** | 0.368 | 0.278 |
| hip_roll | 47.3 | 33.9 | −28% | 0.322 | 0.229 |
| hip_yaw | 17.8 | 22.3 | +25% | 0.148 | 0.156 |
| **knee** | 29.9 | **59.2** | **+98%** | 0.151 | 0.276 |
| ankle_pitch | 39.7 | 31.7 | −20% | 1.389 | 1.111 |
| ankle_roll | 9.8 | 4.3 | −56% | 0.332 | 0.146 |

→ bent는 **hip·ankle 토크를 낮추는 대신 knee 토크를 2배로** 올림. 총합은 비슷(재분배). 둘 다 포화 없음(R²=1).

## 3. 해석 (물리적으로 일관)
- **bent(크라우치)**: 무릎·발목을 굽혀 **착지충격 흡수**(GRF peak 2.15→1.39 BW, −35%) + hip/ankle 토크↓. 대가로 **무릎을 계속 굽힌 채 체중지지 → knee 토크 2배 + CoT 8%↑**(크라우치 보행의 알려진 비효율) + 동일명령서 전진거리 30%↓(속도 추종 저하).
- **straight(편)**: 다리 신전으로 **에너지 효율↑·속도추종↑**, 하지만 **착지 딱딱**(GRF↑) + hip/ankle 토크↑.
- 가설 "straight=토크 폭증"은 **부분적 오해** — straight는 hip/ankle 토크가 크나 knee는 오히려 작고, 총 토크는 bent와 비슷. "폭증"한 건 오히려 bent의 **knee 토크**.

## 4. 설계 함의
- **HW 하중 관점(프로젝트 목표)**: bent의 **낮은 GRF(−35%)는 충격하중 저감에 유리**하나, **knee 액추에이터(RS04) 수요가 2배**로 커져 knee 사이징 악화. hip은 여유↑.
- **에너지/자연스러움**: straight가 CoT·속도추종 우세. bent는 속도 추종이 약함(전진거리↓).
- **절충**: 살짝만 굽힌(−38°보다 완만한) 중간 자세로 GRF 저감과 knee 토크의 균형점을 찾는 후속 스윕 가치 있음.

![[ghost_straight_vs_bent.mp4]]

## 재현
```bash
# bent 학습: PYG_NO_DR=1 PYG_INIT_BENT=1 uv run train Mjlab-Velocity-Flat-Pygmalion --env.scene.num-envs 8192 --agent.max-iterations 10000 --agent.seed 42
uv run python analysis/measure_loads.py --run-dir <bent> --checkpoint <bent>/model_9999.pt --tag bent_kd6 --device cpu
uv run python analysis/analyze_qtarget.py --npz Bbase_kd6 bent_kd6 --labels straight bent --out ../../docs/assets/wrench --tag straight_vs_bent
uv run python analysis/ghost_compare.py --a analysis/out/Bbase_kd6 --b analysis/out/bent_kd6 --labels straight bent --out ../../docs/mujoco/assets
```
