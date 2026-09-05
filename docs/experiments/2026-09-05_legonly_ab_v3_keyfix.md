# legonly_ab_v3_keyfix — 시작 자세 결함을 고친 하체 걷기 재학습 (2026-09-05 발사)

> 이름 풀어쓰기: `legonly`(하체만) · `ab`(발목이 두 크랭크로 도는 폐루프 방식) · `v3`(이 계열 세 번째 본학습) · `keyfix`(유일 변인 = 시작 자세 수정).
> 약어를 쓰지 않는다. 처음 보는 사람도 읽을 수 있게 쓴다.

## §0 왜 이 학습을 하는가

직전 런 [[2026-09-03_legonly_ab_v2]](18,099회 완주)의 완주 측정에서 무릎은 살아났지만(좌 63.5° / 우 49.5°, 사람 55~65°) **좌우가 14° 다르고**, 발목 크랭크
토크가 오른쪽에서 1.4~1.5배였다. 뿌리를 파고든 리서치 노트 [[2026-09-05_legonly_v2_gait_defects_root_cause]]가 **데이터로 확인**한 원인:

- 로봇의 **시작 자세(웅크림 키프레임)** 에서 발목 크랭크 각도가 이전 세대 모델(v3)의 값을 그대로 물려받았는데, 이 모델(v30)은 크랭크 축이 좌우 미러라
  **왼쪽 크랭크 A와 오른쪽 크랭크 B의 기본값 부호가 틀렸다**(−17.12° vs 올바른 +17.03° / +17.26°).
- 정책은 관측(각도 − 기본값)과 행동(기본값 + 0.25 × 출력)을 이 틀린 기본값 기준으로 학습했고, 실제로 그 두 크랭크에만 **약 31°의 상수 편향 행동**을 내며 걷고 있었다
  (실측: 평균 각도가 기본값에서 +31.5° / +30.6° 이탈, 나머지 두 크랭크는 +3~4°). 좌우가 **다른 모터**에 걸리는 편향 → 비대칭.
- 같은 키프레임에서 발바닥이 바닥 아래 31 mm에 있어 매 에피소드 첫 0.1초에 접촉 충격이 들어갔다(좌우 대칭이라 비대칭 원인은 아님).

두 결함은 2026-09-05에 수정·검증됐다(시작 자세: 발바닥 **+5.0 mm**, 폐루프 찢김 **0.00 mm**, base z 0.868 → **0.904 m**; [[106_session_backlog]]).
크랭크 기본값이 바뀌면 옛 정책의 행동 계약과 어긋나므로 **이어 학습이 불가능**하고, 새 기준선이 필요하다. 이 런이 그 기준선이다.

**이 런의 질문 하나**: 시작 자세 결함을 고치면 **좌우 비대칭(무릎 14°, 크랭크 토크 1.4~1.5배)이 줄어드는가?** (가설 H1의 최종 판정)

## §1 설계 — v2와 유일 변인만 다르다

| 항목 | v2 | **이 런** |
|---|---|---|
| 시작 자세 파일 | `pygmalion_v3_printed_loop_bent.json`(v3 모델에서 푼 값) | `LegOnly_..._v30_proxyfix_loop_bent.json`(v30에서 새로 푼 값, 폐루프 0.000 mm) |
| 시작 높이 | 0.868 m(발바닥 −31 mm) | **0.904 m**(발바닥 +5 mm) |
| 크랭크 기본값 | 네 개 모두 −17.12° | L_A **+17.03**, L_B −17.26, R_A −17.03, R_B **+17.26** |
| 보상·게인·한계·커리큘럼·설정 33개 | — | **전부 동일** |

보상 변경 0. 저속 정체·짧은 지지에 대한 변경(리서치 노트 §7의 A1~A3)은 **이 런 위에서 각각 단일 변인으로** 이어 학습해 비교한다.

## §1a 실행 명령 (v2와 같은 런처·같은 인자, 이름만 변경)

```
cd mujoco-sim/mjlab
bash analysis/run_v2_scratch.sh --run legonly_ab_v3_keyfix --ankle AB --seed 42 --num-envs 16384 \
  --p1-max-iters 16000 --ramp-iters 10000 --digest-iters 4000 --settle-hold 10 --n-stages 5 \
  --gate-min-dwell 800 --gate-max-dwell 3000 --gate-window 100 --gate-err-ratio 1.1 --gate-fell-max 0.005 --gate-min-episodes 64 \
  --entropy-start 0.01 --entropy-end 0.002 --video-interval 8000 --video-length 500 --logger wandb --vy-stages \
  --env PYG_MODEL_TAG=LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix \
  --env PYG_MASS_DR_JSON=/home/syaro/MikuchanRemote/Human-Pygmalion/tools/robot_model/fusion_snapshots/v30_inspection/mass_dr_legonly_fastener50_prototype-tempmass.json
```

런처가 자동으로: 액션 창 사전 점검 → 1단계(커리큘럼 게이트) → 2단계(도메인 무작위화 램프) → 매시 게이트 스냅샷(§2c) → 스펙 표 삽입(§1b~) → 누적 영상.
`PYG_BENT_KEYFRAME_LEGACY`는 **설정하지 않는다**(설정하면 옛 시작 자세로 돌아가 이 런의 변인이 사라진다).

## §1c 완주 판정 기준 (v2 측정과 같은 조건으로 비교)

| 지표 | v2 | 목표 | 판정 |
|---|---|---|---|
| 무릎 스윙 최대 굴곡 좌−우 (0.6 / 1.2 m/s) | 13.9° / 16.1° | **절반 이하** | H1 확인 |
| 발목 크랭크 토크 실효값 우/좌 | 1.4~1.5 | **1.2 이하** | H1 확인 |
| 무릎 스윙 최대 굴곡 (좌·우 모두) | 63.5 / 49.5° | 사람 대역 55~65° 안 | 유지 |
| 보상·낙상·추종 | 50평균 114.3, 낙상 0 | 동급 | 회귀 없음 |

측정은 v2와 동일: 보행 운동학(0.6 / 1.2 m/s, 각 17초, 초기 자세 흔든 반복 3회) + 전체 명령 범위(121개 × 15초, 외란 없음·외란 주입) + 모터 활용도 + 추종표.
**주의**: 이 런의 체크포인트는 새 시작 자세로 측정한다(옛 정책만 `PYG_BENT_KEYFRAME_LEGACY=1`).

<!-- SPEC-TABLES:BEGIN -->
(런처가 §1b~§1b-4 보상·게인·액추에이터·가동범위 표를 자동 삽입한다)
<!-- SPEC-TABLES:END -->

## §2c 학습 중 리뷰 (게이트마다 스냅샷, docs/27 체크리스트)

| 시각 | iter | reward | ep_len | noise σ | value loss | entropy | surrogate / LR | fell / low_base | err_vxy / err_wz | DR / vx_max | thermal | 판정 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## §R 참조
- 직전 런: [[2026-09-03_legonly_ab_v2]] · 뿌리 원인: [[2026-09-05_legonly_v2_gait_defects_root_cause]] · 시작 자세 수정 기록: [[106_session_backlog]] 09-05 항목
- 시작 자세 풀이 도구: `tools/robot_model/loop_bent_keyframe.py` · 설정 선택 코드: `pygmalion_constants._bent_json_path()` (mjlab `568a4372`)
