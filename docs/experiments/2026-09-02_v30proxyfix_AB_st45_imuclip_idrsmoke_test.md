# v30proxyfix AB 12-DoF Student 45D IMU/clip/DR 재스모크 (2026-09-02)

> **한 줄 판정:** 본 학습 전에 새 35.707 kg 모델에서 Student 관측·안전 목표 제한·점진적 관성 무작위화가 실제 실행되는지 확인하는 인프라 시험이다. 보행 성능을 판정하는 런이 아니다.

| 항목 | 값 |
|---|---|
| 상태 | **완료 — 인프라 PASS, 보행 성능 판정 대상 아님** |
| 서술형 정책명 | `flat-2.5max progress-reward staged-domain-rand 12dof-student-smoke (2026-09-02)` |
| P1 | `2026-09-02_03-35-53_v30proxyfix_AB_st45_imuclip_idrsmoke_test_p1`, 1024 env, seed 42, `model_200.pt` |
| P2 | `2026-09-02_03-40-21_v30proxyfix_AB_st45_imuclip_idrsmoke_test_p2`, P1 전체 상태 resume, `model_399.pt` |
| 로봇 | `prototype-tempmass-motormeasured-armfix_v30_proxyfix_loop.xml`, 35.7071 kg |
| 모델 SHA-256 | `9cfd150beb8064bd1895cdbdd8c9edd90d8ec581e1eaa5b16d09f67b1899199c` |
| 질량 DR | `mass_dr_fastener50_prototype-tempmass.json` |
| 질량 DR SHA-256 | `2b31095a52d0fcf953eba25b7c7f5b371622014ced989aee04547b20bccc243f` |

## §1 재현 조건

### §1a 실행 명령

```bash
bash analysis/run_v2_scratch.sh --smoke \
  --run v30proxyfix_AB_st45_imuclip_idrsmoke_test \
  --ankle AB --vy-stages --logger tensorboard \
  --env PYG_MODEL_TAG=prototype-tempmass-motormeasured-armfix_v30_proxyfix \
  --env PYG_MASS_DR_JSON=/home/syaro/MikuchanRemote/Human-Pygmalion/tools/robot_model/fusion_snapshots/v30_inspection/mass_dr_fastener50_prototype-tempmass.json
```

정확한 인자·P1/P2 환경 변수·승급 기록은 `analysis/out/v2_scratch_v30proxyfix_AB_st45_imuclip_idrsmoke_test.json`이 권위 원장이다. 각 phase의 `params/env.yaml`, `params/agent.yaml`, `git/mjlab.diff`도 런 디렉터리에 저장됐다.

### §1b Policy 입력·출력

- **Actor(Student), 45D:** IMU 각속도 3 + IMU 위치에서 계산한 projected gravity 3 + 모터 위치 $q(t-1),q(t)$ 24 + 이전 action 12 + 명령 $(v_x,v_y,\dot\psi)$ 3.
- `projected_gravity`는 MuJoCo `imu_upvector`의 이상적 방향에 학습 관측 잡음 `Uniform(-0.05,+0.05)`를 더한다. 실제 EBIMU의 바이어스·드리프트·필터/통신 지연·타임스탬프 지터·dropout은 아직 미모델링이며 P2 본평가 전 필수 보완이다.
- **Critic, 82D:** 시뮬레이터 true-state와 DR draw를 포함한 privileged 관측. 배포 Actor에 연결 금지.
- **Action, 12D:** 좌/우 각각 hip pitch, roll, yaw, knee, crank A(위), crank B(아래). $q_\mathrm{target}=q_\mathrm{default}+0.25a$ 뒤 기계 ROM 중앙 90% 범위로 clamp한다.


## 1b. 이 run의 Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| foot_clearance | **-2** | 스윙발 지면 이격(발끌림 방지) | 목표 높이 오차×발 수평속도 |
| stance_knee_extension | **-2** | 입각 중 과도한 crouch 억제 | 접촉 중 \|knee\|>25 deg 초과량^2 |
| track_angular_velocity | **+2** | 명령 회전속도 추종 | exp(-err²/std²) |
| track_linear_velocity | **+2** | 명령 전진/측방 속도 추종 | exp(-err²/std²) |
| air_time | **+1** | 체공시간 보상(질질끌기 억제) | 0.05~0.5 s 체공 발 수; \|command\|>0.5에서 활성 |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| pose | **+1** | 기본 관절자세 정규화(기괴자세 억제) | default-pose L2 |
| self_collisions | **-1** | 자기충돌 벌점 | -접촉수 |
| stand_still_penalty | **-1** | 이동 명령을 무시하고 서는 stall 방지 | 명령 대비 진행률<30%이면 flat cost |
| track_lin_vel_progress | **+1** | 고속 명령에서 정지하는 local optimum 방지 | 명령방향 실제속도 투영값, 명령크기에서 cap |
| upright | **+1** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| foot_impact_velocity | **-0.5** | 착지 직전 발 하강속도 감소 | 지면 근처 공중 발의 downward velocity^2 |
| knee_overspeed | **-0.5** | 실측 RS04 무부하 속도를 넘는 보행 억제 | relu(\|knee velocity\|-19.9)^2 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | 스윙 중 목표 높이 오차 |
| action_rate_l2 | -0.1 | 액션 급변 벌점 | -\|Δa\|² |
| foot_slip | -0.1 | 접지발 미끄러짐 벌점 | -\|v_contact\| |
| body_ang_vel | -0.05 | 몸통 각속도 벌점(흔들림 억제) | -\|ω\|² |
| angular_momentum | -0.02 | 전신 각운동량 벌점(회전 낭비 억제) | -|L|² |
| thermal_effort | -0.02 | ★열분배: Σ(τ/rated)² 정규화(관절 균등화) | -Σ(τ/rated)² |
| contact_force_cap | -0.01 | ★충격 cap: 발 GRF 역치초과분 벌점(사뿐착지) | -min(max(F-600,0),800) |
| soft_landing | -1e-05 | 착지 첫접촉 충격 벌점(약) | -첫접촉 GRF |
| torque_limit | -0 | commanded 토크 한계초과 벌점 | off(0) |

**관절별 Kp/Kd** (position-PD, effort=관절측 peak):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 150 | 6 | 120 |
| hip_roll | RS04 | 150 | 6 | 120 |
| hip_yaw | RS03 | 150 | 6 | 60 |
| knee | RS04 | 220 | 6 | 120 |
| crank_A | RS03 | 22.3 | 1.41 | 60 |
| crank_B | RS03 | 22.3 | 1.41 | 60 |


## §2 레드팀 게이트와 결과

### §2a 이번 시험이 확인하는 것

1. P1에서 질량·관성 DR가 0으로 유지되는가.
2. P2에서 실측 P1 길이 직후부터 질량/COM/관성 DR가 0→1로 증가하는가.
3. Student가 45D인지, projected gravity가 root true-state가 아니라 `robot/imu_upvector`에서 오는가.
4. 12개 motor target이 soft joint limit과 동일한 안전 범위로 제한되는가.

### §2b 현재 관측

- P1은 stage 0→4에 도달했고 iter 154에서 top-stage settle 조건을 만족했다. 다음 저장점인 iter 200에서 정상 종료했다.
- P1 `fell_over=0.0000`, 최종 gate error 0.6381, baseline 0.8803.
- stage 0은 zero-command 워밍업으로 error가 NaN이라 iter 60에 smoke 전용 MAX-DWELL 승급됐다. 본 학습 판정 근거로 사용하지 않는다.
- P2 DR 창은 P1 실측 종료점에 맞춰 iter 200→320으로 계산됐다. `dr_factor`는 iter 203의 0.0375 → 224의 0.2126 → 249의 0.4208 → 274의 0.6291 → 299의 0.8375 → 324의 **1.0000**으로 증가했고, 종료 iter 399까지 1.0을 유지했다.

### §2c 학습 중 리뷰 (게이트마다 스냅샷, docs/27 체크리스트)

| 시각 | iter | reward | ep_len | noise σ | value loss | entropy | surrogate / LR | fell / low_base | err_vel xy / yaw | dr_factor / vx_max | thermal | 판정(docs/27) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 09-02 03:40 | 200 | P1 infra smoke | — | — | — | — | — | 0.000 / — | 0.638 gate / — | 0.00 / top stage | — | CONTINUE to P2; 보행 품질 판정 금지 |
| 09-02 03:49 | 214 | 28.8 (50avg 22.9) | 554 | 0.465 | 0.138 | 7.46 | -0.0061 / 2.6e-04 | 0.000 / 1.818 | 1.183 / 0.645 | 0.00 / 2.5 | 3.27 | P1 phase-end: infra pass; gait-quality N/A |
| 09-02 03:49 | 399 | 19.1 (50avg 19.7) | 390 | 0.406 | 0.161 | 5.54 | -0.0056 / 5.9e-05 | 0.000 / 2.682 | 0.853 / 0.430 | 1.00 / 2.5 | 3.69 | P2 phase-end: DR ramp pass; gait-quality N/A |

> P1 TensorBoard의 마지막 이벤트는 종료 신호 전 iter 214까지 기록됐지만, 재현 가능한 최종 체크포인트는 `model_200.pt`다. 성능 비교에는 체크포인트 번호 200을 사용한다.

![P1 training health](../mujoco/assets/v30proxyfix_AB_st45_imuclip_idrsmoke_test_p1_progress.png)

![P2 training health](../mujoco/assets/v30proxyfix_AB_st45_imuclip_idrsmoke_test_p2_progress.png)

## §3 영상

- P1 원본: `logs/rsl_rl/pygmalion_velocity/2026-09-02_03-35-53_v30proxyfix_AB_st45_imuclip_idrsmoke_test_p1/videos/train/rl-video-step-0.mp4`
- P2 원본: `logs/rsl_rl/pygmalion_velocity/2026-09-02_03-40-21_v30proxyfix_AB_st45_imuclip_idrsmoke_test_p2/videos/train/rl-video-step-0.mp4`
- P1 누적 진행 영상(원본 1 clip):

<video controls src="../mujoco/assets/accum_v30_st45_smoke_p1.mp4"></video>

- P2 누적 진행 영상(원본 1 clip):

<video controls src="../mujoco/assets/accum_v30_st45_smoke_p2.mp4"></video>

이 재스모크는 구 런처의 큰 video interval로 phase당 한 클립만 남았다. 수정된 런처는 smoke도 약 100 iter마다 기록하도록 바뀌었으며, 본 학습은 기본 약 333 iter 간격을 사용한다.

## §4 본 학습 전 NO-GO 항목

- 런 시작 시 노트 뼈대·재현 스냅샷·중간 리뷰 루프·누적 영상·registry/canvas 등록 자동화 확인.
- EBIMU-9DOFV6 로그 기반 gyro/attitude bias, latency, dropout 모델. P1에는 과도한 DR를 넣지 않고 P2에서 점진 적용.
- 물리 motor+와 모델 q+의 CAD 체인 감사 및 배포 motor ID/zero/limit 저전류 검증. 시뮬레이션 학습은 가능하지만 실기 torque enable은 NO-GO.
- fastener 50–100%를 링크별 독립 표본으로 뽑는 현 DR를 로봇 전체 체결 완성도와 상관된 표본으로 개선.

## §R 관련 문서

[[103_v2_training_plan]] · [[100_observation_design_sim2real]] · [[114_huphy_proxyfix_rotation_dr_audit]] · [[115_motor_flange_huphy_crosscheck]] · [[27_training_review_loop]]
