# 2026-07-14 · hip-cant30 MJCF 변형 (CAD 확정 기하 반영) — cant30_p1

> 종류: **기하(하드웨어) 변경** — reward 변경 아님. 근거: [[67_hip_cant_and_roll_motor_review]] §3 확정(2026-07-14, 사용자 확인: inner-up·roll 15° 캔트 의도적). 사용자 지시로 변형 MJCF 생성 + Gen-2.1 레시피 재학습 착수.

## 1. 무엇을 왜 바꾸나

docs/67 §3에서 CAD(크로치 원점, X측방/Y전후/Z상하)와 현행 sim의 고관절 기하 차이 2건이 확정됐다:

| # | 항목 | 현행 sim | CAD 확정안 |
|---|---|---|---|
| ① | hip_pitch 축 캔트 | 0° (순수 측방) | **30° inner-up** (정면면 내, 몸쪽 끝이 위로; L/R 미러) |
| ② | 3축 동시성 | 준교차 (pitch↔yaw 스큐 3.4mm, roll도 그 근방 통과) | pitch↔yaw **정확 교차**(스큐 0) + roll 축이 교점에서 **29.7mm 수직 오프셋** (perp = 측방 28.3 / 수직 8.6 / 전후 2.3 mm) |

roll 축의 15° 상향 캔트는 **의도된 기존 설계**(sim과 동일)라 유지. yaw 축 수직 유지. §3의 부하 예측: yaw축 추가모멘트 RMS +4.0 / P99 +9.6 N·m (yaw P99 32.9→약 42.5 = RS03 peak 71%), yaw 상시왕복 유입 $\sin 30°\,\omega_p$ RMS 0.88 rad/s.

**가설(핵심)**: 기하 변경으로 관절-부하 매핑이 달라지므로 **기존 정책·부하 실측값은 이전 불가** — 새 기하에서 Gen-2.1 레시피로 **재학습 후 재측정**해야 설계값을 얻는다(docs/67 §3 "채택 시 MJCF 반영 + 재학습·재측정 선행"). 이 런(cant30_p1)이 그 첫 단계다.

## 2. 구현 (pygmalion_cant30.xml — 조인트 4개만 수정, 제로자세 링크 위치 불변)

원본 `pygmalion.xml`을 복사해 `src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_cant30.xml` 생성. body pos는 건드리지 않고 **joint pos/axis만** 수정 → qpos=0에서 모든 링크 월드 위치가 원본과 동일(검증 max diff 1.4e-14 mm), 회전 중심·축 방향만 바뀐다.

sim 좌표(X전방/Y측방/Z상): 원본 hip 체인은 base→pitch(축 월드 $(0,1,0)$)→roll(축 $(\cos15°,0,\sin15°)$ 전방+15°상향)→yaw(축 $(0,0,-1)$). hip 링크 프레임은 base 대비 $R_z(90°)$라 로컬↔월드 변환에 주의.

| 조인트 | 변경 | 값 (로컬 프레임) | 월드 의미 |
|---|---|---|---|
| L_hip_pitch | axis | (0.8660, 0, 0.5) | 월드 (0, \cos30°, +\sin30°) — 몸쪽(+Y) 끝이 위 = inner-up |
| R_hip_pitch | axis | (0.8660, 0, -0.5) | 월드 (0, \cos30°, -\sin30°) — 몸쪽(−Y) 끝이 위 (미러: a_R=-M a_L, 관절각 부호 보존) |
| L/R_hip_pitch | pos | (0, -0.003381, 0) | 축선을 전방(+X) 3.381mm 이동 → 캔트된 pitch 축이 yaw 축과 **정확 교차** (원본 스큐 3.381mm 소거; 공통수선이 X방향이므로 X이동만으로 충분) |
| L_hip_roll | pos | (-0.0283, -0.00598, -0.02232) | roll 축선을 평행이동해 교점 P로부터의 수직 오프셋을 목표 perp = (전방 +2.31, 측방 외측 28.30, 하방 8.61) mm로 설정. 축 방향(15° 캔트)은 불변 |
| R_hip_roll | pos | (+0.0283, -0.00598, -0.02232) | 좌우 미러 동일 |

- 산출 근거: CAD 좌표 pitch $(-68.1,70,72.25)$·roll $(-128.3,43.5,37.5)$·yaw $(-100,70,-92)$에서 $P_{CAD}=(-100,70,53.8)$, $\Delta = \text{roll}-P$의 roll-축 수직성분 = $(-28.3, +2.31, -8.61)$, $|{\cdot}|=29.67$mm. 캔트로 교점이 원본 근사교점보다 **13.8mm 아래로 내려가므로**, roll 이동량은 "CAD perp − 현행 perp(교점 하강 반영)"로 계산했다(단순 29.7mm 병진이 아님).
- joint pos 이동은 qpos=0 FK에 영향 없음(회전 중심만 이동) → **키프레임 HOME/KNEES_BENT 관절값 그대로 유지**(각도 동일, 움직임 기하만 다름).

## 3. 토글 배선

`pygmalion_constants.py`: `PYG_HIP_CANT30=1`이면 `PYG_XML`이 `pygmalion_cant30.xml`을 가리킴(PYG_INIT_BENT와 같은 env-var 패턴, `get_spec()` 경유라 학습·play·측정 전부 일관). **측정·렌더 시에도 학습과 동일하게 지정 필수** (experiment-note 스킬 §0 규칙과 동일 — 누락 시 기하가 달라져 평가 무효).

## 4. 검증 (analysis/verify_cant30_geometry.py — 전 항목 PASS)

| 검증 항목 | 목표 | 실측 (L / R) |
|---|---|---|
| pitch 축 측방으로부터 각 | 30.0° ± 0.1 | **30.000° / 30.000°**, inner-up 둘 다 True |
| pitch↔yaw 스큐 | 0 ± 0.5mm | **0.0000 / 0.0000 mm** (교점 P=(-100.5, \mp94.8, +45.6)mm base 기준) |
| roll 축 오프셋 \lvert perp \rvert | 29.7 ± 1mm | **29.671 / 29.671 mm**, 성분 (전방 2.31, 측방 ∓28.30, 수직 −8.61) |
| roll 축 15° 상향 캔트 유지 | 15.0° | 15.000° / 15.000° |
| yaw 수직 | 0° | 0.0000° |
| L/R 미러(y-flip) | — | 축 diff ≤ 4e-16, 앵커 diff ≤ 0.056mm(원본 소스의 기존 비대칭 0.056mm 그대로) |
| 제로자세 링크 위치 = 원본 | — | max diff 1.4e-14 mm |
| bent 키프레임 FK | NaN 없음 | PASS, 발 사이트 z=+0.006 (base 0.83 기준 지면 근접) |
| 랜덤 qpos 100회 FK | NaN 없음·발 도달 | 0 bad |

## 5. 실험 계획 (cant30_p1)

- **레시피**: Gen-2.1 flat P1 (현행 코드 = gen21_bent_p1과 동일 reward/gains), `PYG_HIP_CANT30=1 PYG_INIT_BENT=1 PYG_NO_DR=1`, 8192 envs, 20000 iters, fresh(워밍스타트 없음 — 기하가 달라 정책 이전 부적절).
- **대조군**: gen21_bent_p1 (2026-07-13_05-39-18) — 유일 변인 = 고관절 기하. 런 직후 params/env.yaml diff로 단일변인 실증.
- **판정 지표**(docs/67 §3 예측 대조): ① yaw 토크 RMS/P99 (+4.0/+9.6 N·m 예측, RS03 71% 이내인지) ② yaw 속도 왕복 RMS (~0.88 rad/s 예측) ③ pitch 토크 RMS/P99 (15°에서 −8~−9%였던 $\cos\alpha$ 이득의 30° 스케일) ④ 기생(베어링) 모멘트 ⑤ 추종·자연스러움이 base 기하 대비 유지되는지.

## 파일

- `mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_cant30.xml` (신규)
- `mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/pygmalion_constants.py` (PYG_HIP_CANT30 토글)
- `mujoco-sim/mjlab/analysis/verify_cant30_geometry.py` (검증, 재실행 가능)
- 근거: [[67_hip_cant_and_roll_motor_review]] §3
