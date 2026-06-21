# 38 — 2-모터 병렬발목 sim2real (Unitree G1 / Booster T1 / Tesla / Fourier 식)

> 사용자 제안(2026-06-22): 현 [roll 직결 RS00 + pitch 1:1 직렬링크 RS03] **양쪽 포화** → **2×RS03 병렬발목**으로 전환. shank에 2 모터, 로드엔드(구면) 베어링 푸시로드 2개가 **발목 pitch+roll을 *공동(coupled)* 구동**. 정량: 로드힘 ~0.65–1.0 kN(worst pitch+roll), 모터크랭크 r_m 61–92mm, ROM pitch 70–90°·roll ±20°. 질문: 이걸 어떻게 sim2real 하나? (정책 출력공간 / Jacobian / DR / 실배포 gotcha).
> ★ **노트37과 구분**: 노트37 = 1모터→1DOF *직렬-디커플* 링크(Agibot X2식). 본 노트 = 2모터→2DOF *연성-병렬*(Unitree G1식). **운동학이 근본적으로 다름**(연립·특이점·Jacobian 2×2). 관련: [[37_ankle_linkage_fidelity]] · [[36_all_actuator_tn_envelopes]] · [[16_dr_expansion]] · raw [[raw/parallel-ankle-sim2real]].

## TL;DR
**업계 표준 = 정책은 joint-space(pitch/roll)만 출력하고, 병렬-IK + Jacobian-transpose(joint토크→모터토크)는 저수준 컨트롤러/SDK가 처리(캠프 A)** — Unitree G1 PR mode, Booster Gym/T1, LiPS/Tien Kung. 대안(캠프 B)은 정책이 모터 A/B 공간을 직접 출력하고 학습 sim 자체에 closed-chain을 넣는 end-to-end(BRUCE, G1 AB mode). 우리(IsaacLab)엔 **캠프 A 권장**: 현 pitch/roll hinge 정책을 그대로 두고, joint↔motor를 후처리/배포 레이어로 분리.

## (1) Transmission: joint-space ↔ motor-space — 누가 IK/Jacobian 하나?

### ★ 캠프 A — 정책=joint-space, 저수준이 J^T 변환 (★ 권장, 업계 다수)
정책은 **가상 직렬(virtual serial) 발목**(pitch θ, roll φ hinge 2개)만 보고 출력. 배포 시 SDK가:
1. 모터 엔코더(A/B) → **FK**로 가상 직렬 joint 위치/속도 피드백 계산 (`q_serial = FK(q_motor)`).
2. 정책의 desired joint torque/position → **Jacobian transpose**로 모터토크: `τ_motor = J^T · τ_joint`, `J = ∂(joint)/∂(motor)`.
3. 모터 PD(수 kHz)가 추종.
- **Booster Gym(T1)**: *"calculates position/velocity feedback for virtual series joints … converts policy outputs from series to parallel via a **transposed Jacobian matrix and a PD controller**"* — 변환은 **배포 SDK(온보드 CPU)**, 학습 sim 아님. [arxiv 2506.15132](https://arxiv.org/abs/2506.15132) · [code](https://github.com/BoosterRobotics/booster_gym).
- **Unitree G1 PR mode(default)**: 정책은 P/R(pitch/roll)만, 병렬 운동학은 펌웨어. (AB mode면 유저가 직접 계산.) [G1 dev guide](https://docs.westonrobot.com/tutorial/unitree/g1_dev_guide/).
- **LiPS(Tien Kung)**: 직렬상태로 학습 → 병렬액션, `τd^s ← Jᵀ τd^p`. [arxiv 2503.08349](https://arxiv.org/html/2503.08349v1).
- 장점: 정책 단순·학습 빠름·기존 pitch/roll 보상 그대로. 단점: J 정확도(캘리브)에 전이품질 의존.

### 캠프 B — 정책=motor-space, 학습 sim에 closed-chain
정책이 **모터 A/B 위치를 직접** 출력. 학습 sim 자체가 병렬 폐쇄체인(MuJoCo equality constraint) → FK/IK 불필요, 액션공간=HW 액추에이터공간.
- **BRUCE / Mechanical-Intelligence RL**: *"action space maps directly to physical actuators, removing the need for FK/IK."* closed-chain을 MuJoCo soft equality constraint로. [arxiv 2507.00273](https://arxiv.org/html/2507.00273v2).
- **G1 AB mode**, **TopA**(커플링행렬 `[[1,0],[−1,1]]`). [TopA arxiv 2507.10164](https://arxiv.org/html/2507.10164v1).
- 장점: 전이충실도 최고 — 모터 T-N 비선형·커플링이 학습에 직접 노출(*"병렬에선 joint토크 최소화≠모터토크 최소화"* → 에너지 reward 정확). 단점: sim 느림(+3.4%/step), closed-chain 모델 필요, IsaacLab은 MuJoCo만큼 폐쇄체인 친화적이지 않음.

> **우리 권장 = 캠프 A.** 현 IsaacLab sim은 발목을 pitch/roll hinge로 모델(노트37) → 정책은 그대로. 추가할 것은 **배포(및 하중측정) 레이어의 J^T 변환**뿐. 단 **에너지/토크 reward를 모터공간에서 평가**(캠프 B 통찰)하면 충실도↑ — pitch+roll 동시요구 시 한 모터가 양쪽을 합산받아 포화(아래 ⑤).

## (2) Jacobian J = ∂(motor)/∂(joint) — 계산/캘리브

2×2 병렬발목 J는 **링크 기하에서 해석적**으로 나옴. LiPS Eq.12:
```
J(i,:) = 1/((B_iC_i × C_iP_i)_y) · C_iP_i^T · R^A_{P_i}     (i=1,2 : 두 로드)
```
- 입력: footplate pitch φ̇·roll θ̇ → 두 로드/모터 각속도 q̇.
- 구성: **능동크랭크 벡터 B_iC_i × 수동로드 벡터 C_iP_i** (외적) + 회전행렬로 표현된 위치 Jacobian.
- 우리 케이스: 2 푸시로드(로드엔드 구면조인트) → footplate의 2 부착점 P_i, 모터크랭크 r_m(61–92mm), 발측 레버암. **각 자세(θ,φ)마다 J 재계산**(자세의존, 상수 아님).
- **τ변환은 J^T**: `τ_joint = J^T τ_motor` (속도가 `q̇_motor = J q̇_joint`면 토크는 전치). HW 로드힘 = `F = τ_motor / r_m`(노트37 ÷레버암과 동형, 단 2DOF라 **두 로드 힘이 pitch·roll에 동시 의존**).
- **캘리브**: 업계는 대개 **해석 J(CAD 기하)** + 모터 엔코더 zero-offset 캘리브. 정밀 병렬로봇(재활)은 카메라/외부센서로 kinematic calibration(레버암 실측, [parallel ankle calib](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7486647/)) — 단 보행로봇은 보통 CAD J로 충분(엔코더 홈잉만). 우리: **Fusion CAD에서 r_m·부착점·레버암 측정 → 해석 J** (노트37 권고와 동일 패턴, 2DOF로 확장).

## (3) Domain Randomization — 링크/Jacobian/백래시/컴플라이언스

★ **gap 발견**: 위 4편 논문 전부 **friction/mass/latency/Kp/obs-noise는 randomize하나, 링크 기하·Jacobian-error·백래시·로드 컴플라이언스는 거의 미보고**(LiPS·BRUCE 명시적 없음, Booster latency만). 즉 학계가 아직 약한 부분 = **우리가 의도적으로 추가하면 robustness 이득**:
- **Jacobian/전달비 오차**: r_m·부착점을 ±5–10% randomize(또는 J에 곱셈 노이즈) → CAD↔실측 레버암 오차·조립공차 흡수.
- **백래시**: joint↔motor에 deadband(±0.5–2° 추정) 주입. 로드엔드 구면베어링·크랭크 핀의 누적 유격 → 발 진동/리밋사이클 유발 가능(노트17 toe 진동과 연관).
- **로드 컴플라이언스**: 로드 축강성 유한(우리 Al Ø~9mm/CF) → joint에 직렬 스프링(stiffness randomize). 캠프 A에선 PD gain·armature로 근사.
- **latency/Kp**: 기존 DR(노트16) 유지 — Booster 0–20ms, BRUCE 0–40ms·Kp±20.
- 참고: 우리 DR 확장 노트 [[16_dr_expansion]]에 **링크-특화 DR 블록 추가** 권장.

## (4) 실배포 gotcha (백래시·캘리브·특이점·ROM)

1. **★ 특이점 near ROM limit** — 병렬발목의 최대 함정. 로드/크랭크가 **공선(collinear)** 이 되면 J 특이(BRUCE *"singularities when all four links become collinear"*; LiPS Eq.8 `ai²+bi²−ci²≥0`로 해 존재성 제약). 특이점서 J 역행렬 폭발 → 작은 joint속도에 무한 모터속도 요구. **우리 ROM pitch 70–90°는 큼** → 끝단서 특이점/유효비 급변 위험. 대책: (a) 기하설계로 ROM 내 특이점 배제, (b) 정책 joint limit을 **링크 가용·특이점 안전범위로 제한**(노트37 권고와 동일, 2DOF로), (c) reward에 limit penalty(TopA −5.0·ReLU).
2. **백래시/유격** — 2 로드 + 4 구면조인트 = 직렬링크보다 유격원 多. 캘리브 zero-offset 드리프트 → joint angle 오차. 대책: 엔코더 홈잉 절차 + DR 백래시(위 ③).
3. **캘리브 = J 정확도** — 캠프 A는 전이품질이 J(=CAD 레버암 정확도)에 직접 의존. CAD↔HW 레버암 어긋나면 모터토크 배분 틀림 → 한 모터 조기포화. **Fusion CAD 측정값을 실측 검증** 권장.
4. **PR↔AB 일관성(G1 교훈)** — 학습/배포 모드 일치 필수. PR(joint)로 학습했으면 배포도 PR, 아니면 SDK가 매 step FK/IK·J^T를 정확 수행해야. mode 불일치 = 즉시 발산.
5. **모터 동시포화(★ 우리 핵심)** — pitch+roll worst-case 동시요구 시 **한 모터가 두 토크기여 합산**(`τ_motor = J^T τ_joint`의 행 합) → 단일 joint 측정보다 모터부하 큼. 현 측정(노트36: pitch RS03 128%연속·roll RS00 114%)은 *직렬*기준 — **병렬화하면 각 RS03가 pitch+roll 합산**받음. ⇒ **하중측정을 반드시 모터공간(J^T 후)에서** 해야 2-RS03 사이징이 옳음(캠프 B 통찰의 실전 적용). 2 모터로 토크 분담되나, *worst-case 동시*엔 분담이상으로 집중될 수 있음 → r_m·부착각으로 J 컨디셔닝 최적화.

## ★ 우리 RS03×2 / ~1kN 케이스 적용 권고
1. **아키텍처 = 캠프 A**: IsaacLab 정책은 현 pitch/roll hinge 유지. **신규: 후처리/배포 레이어에 2×2 해석 Jacobian(CAD 기하)** 추가 → `τ_motor=J^T τ_joint`, `F_rod=τ_motor/r_m`.
2. **하중측정을 모터공간에서**: 노트37의 "joint토크÷레버암"을 **2DOF J^T로 일반화** — pitch·roll joint토크를 매 step J^T 곱해 **각 RS03 토크·각 로드힘** 산출. 이게 진짜 사이징 기준(동시포화 반영). 0.65–1.0 kN 추정과 대조.
3. **ROM/특이점**: 70–90° pitch는 특이점 위험 → CAD에서 ROM 전구간 J 조건수 스윕, 특이점 들면 정책 joint limit 축소 후 재학습(노트37과 동일 패턴).
4. **DR 추가**(학계 gap = 우리 차별화): Jacobian ±5–10%·백래시 deadband·로드 stiffness → [[16_dr_expansion]].
5. **검증 순서**: flat→rough(발목 demand ~2배, 노트37) sweep 후 r_m(61–92mm) 확정. r_m이 (a)로드힘 F=τ/r_m(HW 1.5–2.7kN 파손 마진)과 (b)병렬 토크/속도 동시를 결정.

## 근거 (hyperlink)
- Booster Gym/T1 (J^T+PD, virtual serial, 캠프A): [arxiv 2506.15132](https://arxiv.org/abs/2506.15132) · [html](https://arxiv.org/html/2506.15132v1) · [code](https://github.com/BoosterRobotics/booster_gym)
- LiPS/Tien Kung (Jacobian 기하식 Eq.12, 특이점 Eq.8): [arxiv 2503.08349](https://arxiv.org/html/2503.08349v1)
- Unitree G1 PR vs AB mode (펌웨어 병렬IK): [G1 dev guide](https://docs.westonrobot.com/tutorial/unitree/g1_dev_guide/) · [unitree_rl_gym](https://github.com/unitreerobotics/unitree_rl_gym) · [unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab)
- BRUCE / Mechanical-Intelligence RL (모터공간 end-to-end, closed-chain constraint, 특이점): [arxiv 2507.00273](https://arxiv.org/html/2507.00273v2)
- TopA (커플링행렬, open-chain baseline 실패): [arxiv 2507.10164](https://arxiv.org/html/2507.10164v1)
- HumanPlus(H1, PD URDF 매핑 — 참고): [arxiv 2406.10454](https://arxiv.org/pdf/2406.10454) · [site](https://humanoid-ai.github.io/)
- 병렬발목 kinematic calibration(재활로봇, 특이점 5–10cm 회피): [PMC7486647](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7486647/)

관련: [[37_ankle_linkage_fidelity]] · [[36_all_actuator_tn_envelopes]] · [[16_dr_expansion]] · [[31_humanoid_hw_comparison]] · raw [[raw/parallel-ankle-sim2real]]
