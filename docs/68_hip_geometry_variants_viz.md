# 68. Hip 기하 변형 — 회전축 가시화 & 관절 모션 (2026-07-15)

> 오프셋을 넣은 hip 기하 변형들(cant30·rolloff30)을 base와 함께 **6개 다리 관절의 회전축**으로 비교(§회전축)하고, **각 관절 움직임을 영상**으로 정리(§모션)하며, **초기자세가 수정된 학습 자세(bent init)** 도 별도 섹션으로 다룬다(§초기자세). 부하 분석은 [[67_hip_cant_and_roll_motor_review]] §8(cant)·§9(rolloff), 정의는 각 XML/토글. 렌더: `analysis/axis_viz.py`(MUJOCO_GL=egl).

## 변형 정의 (단일 축만 바뀜)
| 변형 | XML / 토글 | 기하 변경 | 부하 귀착 |
|---|---|---|---|
| **base** | `pygmalion.xml` | 기준(pitch·roll·yaw 근사 동심) | — |
| **cant30** | `pygmalion_cant30.xml` / `PYG_HIP_CANT30` | hip_pitch 축 **30° inner-up 틸트** + roll 오프셋 29.7mm | pitch −3%·knee↓ / **발목·yaw↑** (§8) |
| **rolloff30** | `pygmalion_rolloff30.xml` / `PYG_ROLLOFF30` | hip_roll 축만 **외측 30mm**, yaw 이하·pitch 원위치 | **hip_roll RMS↑**(고정 offset 모멘트, §9) |

## 회전축 (기본 자세, 좌측 다리 6관절)
색: hip_pitch=빨강 · hip_roll=초록 · hip_yaw=파랑 · knee=주황 · ankle_pitch=보라 · ankle_roll=청록. 각 화살표는 관절 앵커를 지나 월드 회전축 방향. 우측 다리는 미러 대칭.

![[axis_variants_compare.png]]

**읽는 법**:
- **cant30**: 빨강(hip_pitch) 화살표가 **안쪽-위로 30° 기울어짐**(base는 수평) — FRONT·ISO 모두에서 확인. 축이 시상면에서 벗어나 pitch↔yaw 커플링·기생모멘트 발생(§8).
- **rolloff30**: 힙 블록이 **좌우로 더 벌어짐**(다리 부착점이 외측 30mm) — 발↔roll축 횡거리↑ → hip_roll 외전 부하 상시 증가(§9). pitch/knee/ankle 축 방향은 base와 동일(위치만 외측).
- **base**: 세 힙축이 좁게 모임(동심 근사).

## 관절 모션 영상 (각 관절 순차 스윕, 실시간 25fps)
좌측 다리 6관절을 하나씩 가동범위의 60%까지 스윕(0→+→−→0). 상단 라벨 = 관절명(축색)·현재각·범위. 활성 관절 축을 굵게 강조.

### rolloff30
![[joint_motion_rolloff30.mp4]]

### cant30
![[joint_motion_cant30.mp4]]

> 관절 **운동학(범위·자유도)** 은 세 변형이 동일 — 오프셋은 축의 **위치/방향**만 바꾼다. 그래서 모션 영상은 오프셋 모델에서도 base와 같은 관절 동작을 보이며, 차이는 축이 지나는 위치(rolloff30=외측)·기울기(cant30=틸트)로 스틸에 드러난다. hip_roll 스윕 구간에서 rolloff30의 외측 피벗, cant30의 틸트축 회전이 관찰된다.

## 초기자세 변형 — bent init (실제 학습 자세)
현행 모든 정책(flat25b·gen2·gen21·cant30·rolloff30)은 **`PYG_INIT_BENT=1`** 로 학습된다 — 초기자세를 직립(HOME)이 아니라 **무릎 굽힌 크라우치(BENT)** 로 시작하고, 그 자세가 **자세보상(pose reward)의 목표(standing-target)** 도 된다(default_joint_pos = init 키프레임 각도). 즉 위 §회전축의 "직립"은 참조용이고, 정책이 실제로 서고 걷는 자세는 아래 BENT다.

| 키프레임 | base z | hip_pitch | knee | ankle_pitch | 용도 |
|---|---|---|---|---|---|
| HOME (직립) | 0.87 | 0° | 0° | 0° | 구 straight arm / 참조 |
| **BENT (현행)** | 0.83 | **−18° (−0.32)** | **−38° (−0.67)** | **+21° (+0.36)** | ★현행 전 정책의 init·자세목표 |
- 근거: init-pose A/B([[55_init_pose_straight_vs_bent]]) — bent=GRF −35%(충격흡수)·CoT 8%↓ but knee토크 +98%. bent 채택 확정.
- ★**cant30fp (feet-parallel, 2026-07-15)**: cant30은 캔트된 pitch축이 굴곡 시 yaw를 유입해 BENT에서 **발이 ±9° toe-out**. `KNEES_BENT_CANT_KEYFRAME`(hip_yaw L −0.165/R +0.165 rad, `PYG_HIP_CANT30`일 때만)로 **발을 X+ 평행**(heading 0.00° 검증)하게 보정. 이 초기자세로 재학습한 cant 버전 = **cant30fp**(구 cant30=발벌어짐, 계보상 대체). base/rolloff30 발은 원래 평행이라 무변경.
- ★측정·렌더·play 시 `PYG_INIT_BENT` 재지정 필수(obs/action default_joint_pos가 바뀌어 누락 시 평가 무효 — [[feedback-video-realtime-rule]] 계열 규칙).

![[init_pose_home_vs_bent.png]]

### BENT 자세에서의 회전축 (변형별)
같은 6축을 **실제 학습 자세(BENT)** 에서 표시. 굴곡으로 knee·ankle 축 위치가 직립 대비 아래·앞으로 이동하지만 축 방향(자유도)은 불변. cant30 pitch 틸트·rolloff30 힙폭 확대는 자세와 무관하게 유지.

![[axis_variants_bent_compare.png]]

## 링크
[[67_hip_cant_and_roll_motor_review]] (부하 A/B) · [[66_experiment_registry]] Era-9 · cant30 학습 [[2026-07-14_cant30_p2]] · rolloff30 학습 [[2026-07-15_gen21_rough_uneven2_p2b]](큐 rolloff30_p1). 렌더러 `analysis/axis_viz.py`.
