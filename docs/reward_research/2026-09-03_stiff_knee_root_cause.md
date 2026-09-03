# Stiff-knee gait 근본원인 — 리워드가 아니라 액션창 버그 (2026-09-03)

트리거: 사용자 라이브 관찰(09-02 23:49) "무릎을 전혀 안 씀(stiff-legged), AB 발목 미활용,
toe-off 시 발끝 지지 안 됨" → 리워드 수정 전 근본원인 조사(규칙: reactive tweak 금지).

## 1. 결론 먼저

**근본원인 #1 (확정, 1순위): 모델-설정 부호 불일치 — 리워드 문제가 아님.**
v30 MJCF는 L/R 관절축이 미러(knee·hip_pitch·hip_roll; ankle_pitch는 비미러)인데, mjlab 설정은
정규식 키(`.*_knee_joint: −0.35`) 하나로 양쪽에 같은 default/clip을 적용한다. 그 결과:

| 관절 | 기계범위 | 명령대역 | 사용가능 창 |
|---|---|---|---|
| **L_knee** | [0, +120]° | [−114, −6]° | **0° (교집합 없음)** |
| R_hip_pitch | [−25, +120]° | — | 43° / 145° |
| L_hip_roll | [−25, +85]° | — | 44° / 110° |

왼무릎 default(−20°)는 **자기 관절범위 밖**. 정책의 무릎 qtarget은 두 속도 모두 100% 클립
경계에 고정된 평평한 선이고, 식별 Kp=220~229(설정 220, R²≥0.98), 토크는 한계의 18~22% —
**PD는 완벽히 추종, 정책이 아예 요청을 못 하는 구조**. 왼무릎 모터는 하드스톱에 상시
21.8 N·m를 밀며 낭비(5.67° 상수오차 × Kp220). 검증: XML 직접 확인(L_knee axis +Y [0,120] /
R_knee axis −Y [−120,0]) + 런 env.yaml(`.*_knee_joint: −0.35`, 단일 clip 튜플).
데이터: [[../experiments/2026-09-03_legonly_gait_kinematics]] (model_5600, 0.6/1.2 m/s).

**따라서 legonly_ab_v1은 09-03 12:00 보수적 중단**(docs/27) — 하중측정 목적상 무릎 하중이
스톱 하중으로 오염, 잔여 13k iter 무가치. v3/v4 모델은 양측 축이 동일했고(당시 런들 정상),
이 미러는 v30 재생성기에서 유입(docs/117 감사는 sim↔CAD 물리방향 일치를 본 것이지
학습레이어 호환성을 본 게 아님).

**근본원인 #2 (구조적, 2순위 — 문헌·코드 감사)**: swing 중 무릎을 읽는 리워드 항이 0개.
`foot_clearance`(−2.0, 발높이 0.1 m 타겟)·`foot_swing_height`(−0.25)뿐이라 다리 0.863 m 기준
**고관절 28° 진자만으로 클리어런스 충족** — stiff gait가 리워드적으로 무벌점. knee 관련 항은
전부 억제 방향(stance_knee_extension −2.0 = stance 25° 초과 굴곡 벌점, knee_overspeed −0.5).
검증된 후보 = Booster T1 knee-height swing 항(arXiv:2606.08253, 실기 93%).
원문: [[../research_raw/2026-09-03_stiff_knee_gait_fix]].

**기각/정정된 가설들**:
- "AB 발목 미활용" → **반박**: ankle_pitch ROM 28~49°/80° 실사용, 크랭크 토크 37~41%/한계.
  다만 크랭크 명령 48~88° vs 실현 24~40° = **소프트함**(τ/Kp=14/22.3 rad≈37° 오차 재현) —
  크랭크 Kp 22.3은 loop_ankle_verify 물리앵커 값이라 자유 노브 아님, 별도 검토.
- toe-off: 왼발 플랫(잠긴 무릎 쪽), 오른발 과대(+21.5° 저측굴곡, 힐라이즈 197 mm 보상동작) —
  #1 수정 후 재측정 대상.
- 발 겹침: 직선보행에서 좌우 발 최소간격 29~46 mm, 시각겹침 문턱(15 mm) 도달 0% —
  docs/119의 시각메시 폭 문제 + self_collision 문턱 10 N은 별개 트랙.

## 2. 조치 결정 (단일변인 규율)

1. **지금 (버그픽스, 리워드 아님)**: 설정을 side-aware로 —
   미러 관절(knee·hip_pitch·hip_roll)의 default pose·clip을 L_/R_ 명시 키로 분리, 물리 의도
   (v2s1/v4의 물리 자세)와 동일하게. 부호가정 있는 항(`stance_knee_extension`의 25° 문턱)은
   관절범위에서 굴곡부호 자동유도로 수정. **+ 프리플라이트 불변량 게이트**: 전 관절
   default∈range && 명령대역∩range 비퇴화 아니면 발사 거부(재발 방지, 이번 버그를 1초에 잡음).
   모델(XML)은 불변 — docs/117 감사 보존, Fusion 의존 없음, 재감사 리스크 0.
2. **재학습**: `legonly_ab_v2` = v1과 동일 레시피, 설정 수정만. 스모크(400 iter)에서
   프리플라이트 PASS + 양무릎 swing ROM > 5° 확인 후 본런.
3. **그 후에만** 리워드 개입 판단: v2 완주 게이트에서 운동학 재측정 → 무릎 swing 피크가
   여전히 인간(55~65°) 대비 크게 미달이면 #2의 swing knee-height 항을 **+800 iter warm-start
   A/B**(2026-08-24 규칙)로 단독 시험. 지금 번들 금지 — v2에서 자연 해소될 수 있음.
4. 대안 A(기록만, 사용자 판단 대기): 재생성기에서 축을 양측 동일 의미로 통일하고 모터
   로터면 규약은 배포 어댑터의 부호맵(HUPHY sign=±1 캘리브레이션, docs/116)으로 이관 —
   업계 관행(조사 13/13 설정 단일 default, 팀원 huphy.xml도 대칭+gear부호). 장기적으로
   우월하나 모델 재감사 필요 → 사용자 결정 항목으로 브리핑에 게시.

## 3. 부호가정 전수감사 (2026-09-03 수정 시 실시)

감사 범위: `legonly_ab_v1` 런 설정이 실제로 활성화하는 **모든** 리워드·관측·이벤트·종료·
액추에이터 항 + 초기자세 키프레임. 판정 기준은 "좌우 관절 부호 규약이 반대인 모델에서
좌우가 다른 의미를 갖는가".

### 3a. 관절 부호가 결과를 바꿀 수 있는 항

| 항 | 부호를 어떻게 쓰는가 | 판정 | 조치 |
|---|---|---|---|
| `stance_knee_extension` (w −2.0, 25°) | `torch.abs(q)` − target | **이미 안전** | 없음. 무릎 range는 어느 규약에서도 0이 완전신전이라 `abs(q)` = 굴곡각. 다만 버그 상태에서는 왼무릎이 0에 고정돼 이 항이 "완전히 편 무릎"이라는 **허구의 측정치**(2.52°)를 냈다 — 항 자체는 정상, 입력이 오염이었다 |
| `variable_posture` (pose, w 1.0) | $(q - q_{default})^2 / \sigma^2$ | **default가 유일한 부호원** | 1번 픽스로 해결. `std_*` 정규식은 전부 크기(σ)라 부호 없음 |
| `dof_pos_limits` (w −1.0) | 모델의 `soft_joint_pos_limits` 사용 | **이미 안전**(관절별) | 없음. 단 버그 상태에서 L_knee가 소프트 하한 밖 6°에 상시 눌려 **상시 페널티 −0.105/step**을 내고 있었다 |
| `joint_pos_rel` 관측(actor·critic) | $q - q_{default}$ | **default가 유일한 부호원** | 1번 픽스로 해결 |
| bent 키프레임 크랭크·로드 각 | v3 기하 해를 그대로 대입 | **버그(신규 발견)** | `_reexpress_loop_pose()` 추가 — 축이 뒤집힌 힌지의 각도만 부호 반전. v30 closure **37.3 mm → 0.001 mm**, v3/v4는 0.001 mm 불변 |
| action clip (`PYG_SAFE_TARGET_CLIP`) | 손으로 적은 정규식 표 | **버그(본건)** | `safe_target_clip()` 관절별 유도 |
| `_bent_joint_pos` hip_pitch/knee default | 단일 정규식 | **버그(본건)** | `signed_pose()` 크기+range유도 부호 |
| cant30/cant20 키프레임 `L_hip_yaw −0.165 / R +0.165` | 명시적 좌우 반대값 | **정상** | 없음. hip_yaw는 좌우 축·range 동일(대칭)이라 이건 규약 아티팩트가 아니라 **진짜 좌우 비대칭**(발끝 벌어짐 보정) |
| `.*_ankle_pitch_joint: 0.36` (serial bent) | 단일 정규식 | **현재 정상, 미래 취약** | 값 유지(+0.36은 range의 **짧은** 쪽이라 `signed_pose`를 쓰면 오히려 뒤집힌다). 대신 `assert_unmirrored("ankle_pitch")`로 미래 미러링 시 import 실패 |

### 3b. 부호와 무관함을 확인한 항 (변경 없음)

`knee_overspeed`(|q̇|) · `thermal_effort`(τ²/rated²) · `torque_limit`(|F_cmd|, w 0) ·
`action_rate_l2`/`action_l2`(액션 차분) · `foot_clearance` · `foot_swing_height` ·
`foot_slip` · `soft_landing` · `foot_impact_velocity` · `contact_force_cap` · `air_time` ·
`self_collisions` · `track_linear_velocity` · `track_lin_vel_progress` ·
`track_angular_velocity` · `stand_still_penalty`(명령 프레임 부호만) · `upright` ·
`body_ang_vel` · `angular_momentum` · 종료항 3종 · `encoder_bias`(±0.015 대칭) ·
`push_robot`(베이스 속도) · `reset_robot_joints`(범위 0) · `PYG_ACTION_SCALE`(전 관절 0.25) ·
액추에이터 Kp/Kd/effort/T-N 파라미터(전부 크기).

`pseudo_inertia`(inertial DR): COM 오프셋 `t1/t2/t3` 범위가 0 대칭(±5 mm, 최대 비대칭
1.6 mm)이고 좌우가 **독립 추출**이므로 바디 프레임이 미러여도 통계적으로 동일 — 부호 버그
아님. 1.6 mm 비대칭은 무의미한 크기로 판단해 기록만 한다.

### 3c. 미해결로 남긴 것 (상체 전용, 이번 픽스 범위 밖)

**`shoulder_roll` 부호 규약이 코드 두 곳에서 서로 반대다.** 이 픽스에서 고치지 않았다 —
LegOnly 모델에는 어깨 관절이 아예 없어 이번 런에 영향이 0이고, 고치면 `v2u1` 계통의
재현성이 깨지기 때문이다.

- `get_spec()`(용접 경로, `PYG_UPPER_DOF` OFF): 주석 "a NEGATIVE shoulder_roll is abduction
  on both sides", 코드도 `np.radians(-abd)`.
- `_bent_joint_pos()`(`PYG_UPPER_DOF` ON): 주석 "Both shoulder-roll axes use +q for
  abduction", 코드는 `+radians(abd)`.

두 주석은 직접 모순이며, v3/v4의 shoulder_roll range는 좌우 동일 `[−32°, +30°]`(축만 미러)라
range 유도 부호는 **−1** = 용접 경로 쪽이다. 즉 `v2u1`은 `v2s1`과 **팔 자세가 좌우 반전된
상태**로 학습했을 가능성이 높다. 게다가 v30 FullDoF는 shoulder_roll range 자체가 미러
(`L [−15°, +130°]` / `R [−130°, +15°]`)라 단일 정규식 `+15°`는 오른팔에서 range 끝
(내전 한계)이 된다. 신설 프리플라이트 게이트가 이 경우 `offset-outside-window` **경고**를
띄운다(FAIL은 아님 — 창 자체는 130.5° 열려 있으므로). **상체 런을 다시 돌리기 전에 결론이
필요한 항목.**
