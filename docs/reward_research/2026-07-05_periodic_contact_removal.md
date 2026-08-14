# Reward 근본원인 리서치 — periodic_contact 제거 (정지 불가 + 속도추종 미수렴)

> 2026-07-05. 사용자 관찰(R2 정책 teleop 테스트): ① 가만히 서있기가 동작 안 함, ② 속도추종(track_linear_velocity)이 전혀 수렴 안 함. 두 증상 다 리워드 원인. 리워드 편집 전 근본원인 규명(HOOK 강제).
> 관련: [gait research Q123](2026-07-02_gait_research_q123.md) · [g1-vanilla > custom](../mujoco/) · R2 리포트(track_lin 0.32 정체)

## 1. 증상 (실측)
- **정지 불가**: teleop에서 command=0인데도 로봇이 계속 스텝. 가만히 못 섬.
- **속도추종 미수렴**: R2 40k 수렴 정책에서 `track_linear_velocity`가 iter 전체 **~0.32에서 정체**(track_angular 0.77·periodic_contact 0.58과 대조). 각속도는 추종하는데 선속도만 안 됨.

## 2. 근본원인 — periodic_contact = 고정 위상클럭 (command-gate 부재)

현재 pygmalion 리워드: `periodic_contact`(+1.5, Siekmann) + `gait_clock` obs(period 1.0, actor+critic). 코드 주석이 자인: *"clock이 스케줄을 legislate하도록 swing-shape 항(foot_swing_height/foot_clearance) 제거"*.

- **고정 주파수 클럭**(period 1.0, stance 0.6)이 **명령과 무관하게** 사인/코사인으로 순환 → obs에 항상 공급 + 리워드가 그 위상에 발접촉을 맞추라고 요구.
- periodic_contact은 command_threshold=0.05로 gate돼 있으나 **(a) 0.05는 너무 낮아** 미세명령에도 클럭 발동, **(b) gait_clock obs는 gate 없이 항상 순환** → 정책이 클럭에 조건화돼 **정지 상황에서도 스텝**을 학습. → **정지 불가**.
- **고정 케이던스 ↔ 가변 선속도 충돌**: vx∈[−2,3]을 추종하려면 보폭·케이던스가 속도에 따라 변해야 하는데, 클럭이 케이던스를 고정 → 정책이 "클럭 맞추기 vs 속도 맞추기" 사이에서 타협 → **track_linear_velocity 미수렴**. (각속도는 제자리회전이라 케이던스 충돌 적어 추종됨 = 증상 비대칭 설명.)

## 3. 대조군 — g1(vanilla)은 periodic_contact 없이 정지·추종 다 됨

mjlab **g1 config**(우리 "g1-vanilla > 내 커스텀" 노트의 그 기준선): periodic_contact **없음**. 게이트가 **창발**함:
- `track_linear/angular_velocity`(±2.0) + `upright`(1.0) + `pose`(1.0)
- **command-gated foot 항**: `foot_clearance`(−2.0), `foot_swing_height`(−0.25), `foot_slip`(−0.1), `soft_landing` — 전부 `command_threshold` 0.05로 gate → **명령 없으면 스텝 강요 안 함 = 정지 허용**, 명령 있으면 clearance/swing이 자연 보행 유도.
- `feet_air_time`은 g1도 0(강제 타이밍 안 씀).

즉 **고정 타이밍 리워드 없이, command-gated 형상항으로 게이트가 창발**하는 게 검증된 방식(Rudin 2021 legged_gym·Unitree 계열 표준). pygmalion만 여기서 벗어나 periodic_contact를 넣고 foot 형상항을 껐다.

## 4. 문헌·선행 정합
- 우리 [gait research Q123](2026-07-02_gait_research_q123.md): periodic_contact이 GRF/대칭에 최고 레버리지였으나, **MEVITA 경고 — 속도추종 정책은 v=0(정지)에서 최약**. 고정클럭은 이 약점을 악화(정지 못함).
- 표준 command-gated feet_air_time/clearance는 정지 친화적(threshold 0.5/0.05)이 설계 의도(함수에 command_threshold 내장 확인).

## 5. 결정 — periodic_contact 제거, g1-style command-gated 스택 복귀
**변경**:
1. `periodic_contact`(+1.5) 리워드 **제거**.
2. `gait_clock` obs(actor+critic) **제거**.
3. `foot_swing_height`(0→**base −0.25**)·`foot_clearance`(0→**base −2.0**) **재활성화**(site_names는 142-143서 이미 설정, 안전).
4. **유지**: track_lin/ang(±2), upright, pose, foot_slip(−0.1), soft_landing, **contact_force_cap(−0.01)·thermal_effort(−0.02)**(HW 페널티, 타이밍 강제 아님 → GRF/열 보완).
- track_linear_velocity weight는 2.0 유지(미수렴 원인은 weight가 아니라 클럭 충돌 → 클럭 제거로 해소 기대).

**리스크**: periodic_contact이 담당하던 GRF/대칭 이득 일부 후퇴 가능 → contact_force_cap+soft_landing+foot_slip로 완충, **학습 중 GRF·대칭 모니터**. 악화 시 command-gated periodic(threshold↑) 재도입 등 후속 검토.

**검증 지표(재학습)**: ① teleop에서 command=0 → 정지 성립, ② track_linear_velocity 수렴(→0.6+), ③ GRF peak가 R2(3.9×BW) 대비 크게 악화 안 됨.
