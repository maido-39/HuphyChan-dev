# raw — 2-모터 병렬발목 sim2real (검증 원문 발췌)

> 주제: 2 모터가 발목 pitch+roll을 *연성(coupled)* 구동하는 **병렬발목**의 RL sim2real. (≠ 노트37의 1모터→1DOF 직렬링크). 대상: Unitree G1 / Booster T1 / Tien Kung / BRUCE.
> 수집일 2026-06-22. 검증=WebSearch+WebFetch.

## 1. Booster Gym (arxiv 2506.15132, Booster T1) — ★ 우리 제안과 가장 직접 일치 (2모터 발목 pitch+roll)
출처: https://arxiv.org/html/2506.15132v1 · https://arxiv.org/abs/2506.15132 · 코드 https://github.com/BoosterRobotics/booster_gym
- **정책 출력공간 = joint-space (가상 직렬 = virtual serial)**. 학습은 가상 직렬구조로 (계산효율). 배포 시 변환.
- **변환 메커니즘**: SDK 모듈이 *"calculates position and velocity feedback for the virtual series joints using the robot's kinematic model"* + *"dynamically converts the policy outputs from the series model to the parallel structure using **a transposed Jacobian matrix and a PD controller**."*
- **실행 위치**: 직렬↔병렬 변환은 **배포 시 (Booster SDK, 온보드 CPU)**, 학습 sim 아님. (즉 정책은 항상 pitch/roll만 보고 출력, 모터 A/B 변환은 저수준.)
- **DR**: latency randomize 0–20 ms(실측 round-trip 9–12 ms), 정책추론 <1 ms. joint stiffness/damping/friction, mass·CoM randomize. 정확 범위 일부 미명시.
- **결과**: T1서 omnidirectional 보행, 지형(grass/stone/soil/asphalt/10°slope), push recovery(10kg), zero-shot sim2real.

## 2. LiPS (arxiv 2503.08349, Tien Kung 163cm/56kg/42DOF) — Jacobian transpose 수식 명시
출처: https://arxiv.org/html/2503.08349v1
- **정책 = 직렬(series) 상태 관측 → 병렬(parallel) 액션 출력**. Algorithm 1: `at(Parallel)←RLPolicy(st(Series))`. 직렬모델로 학습, 병렬용 desired position/velocity 출력.
- **Series-Parallel 변환 모듈 = Jacobian transpose**:
  - L7 `Jtranspose ← ComputeTransposedJacobian`
  - L8 `τd^s ← ComputeSeriesDesiredTorque(Jtranspose · τd^p)`
- **Jacobian 기하식 (Eq.12)**: `J(i,:) = 1/((Bi Ci × Ci Pi)_y) · Ci Pi^T · R^A_Pi`
  - footplate pitch/roll 속도 `χ̇=[φ̇,θ̇]^T` → 2 액추에이터 joint 속도 `q̇`.
  - 능동암 `Bi Ci` × 수동링크 `Ci Pi` 외적 + 회전행렬 위치 Jacobian.
- **특이점/해 선택 (Eq.8)**: `ai²+bi²−ci²≥0`, `−1≤cos qi≤1`. *"Four solutions … final result selected based on the constraints of the rotation range."*
- **DR**: 논문 명시적 링크/백래시/컴플라이언스 randomize **보고 없음**("No historical data or pre-trained models").
- **배포**: Tien Kung, 100 Hz on NVIDIA Orin. Fig5: 병렬발목 두 joint의 실주행 위치/속도. *"significantly reduces … sim2real gap"*. 캘리브레이션 절차 미명시.

## 3. Unitree G1 — PR mode vs AB mode (펌웨어가 병렬IK 처리)
출처: https://docs.westonrobot.com/tutorial/unitree/g1_dev_guide/ · github unitree_rl_gym, unitree_rl_mjlab
- **PR Mode (default)**: *"Controls the Pitch (P) and Roll (R) motors of the ankle joint (default mode, corresponding to the URDF model)."* → 정책/유저는 **joint-space pitch/roll**만. 병렬IK는 펌웨어/SDK가.
- **AB Mode**: *"Directly controls the A and B motors … (**requires users to calculate the parallel mechanism kinematics themselves**)."* → 모터공간 직접, 유저가 병렬 운동학 책임.
- G1 nominal **armature 모델이 발목·허리 병렬링크 반영** (joint↔motor transform 정확모델링이 sim2real 핵심).
- sim2real: dynamics randomization만으로 G1 zero-shot 전이 사례 (추가 fine-tune 없이).

## 4. BRUCE / Mechanical Intelligence-Aware Curriculum RL (arxiv 2507.00273) — 모터공간 end-to-end 캠프
출처: https://arxiv.org/html/2507.00273v2
- **정책 = 액추에이터공간(motor-space) 직접**. *"the action space maps directly to the physical hardware actuators, removing the need for forward or inverse kinematics."* aₜ∈ℝ¹⁶ = 각 액추에이터 joint 위치명령, qₜ=q_nom+aₜ.
- **Jacobian transpose 명시 안 씀** — MuJoCo **closed-chain equality constraint(soft, virtual spring-damper)** 가 토크전달 암묵 처리 (Eq.9). 차동풀리 Eq.1: `q̇_roll/q̇_pitch = 1/(ρl+ρr)·[[ρl,ρr],[ρl,−ρr]]·[q̇l,q̇r]`.
- **핵심개념 "mechanical intelligence"**: *"minimizing output torques does not guarantee a reduction in **actuator** torques"* (병렬에선 joint토크↓≠모터토크↓). 에너지 reward가 단순화모델서 **부정확** → 정확 링크모델링 강제. 액션공간=HW 액추에이터공간 정렬이 전이향상.
- **특이점 명시 모델링**: 5-bar 링크 *"five possible kinematic solutions given endpoint position"*; 4-bar *"singularities … when all four links become collinear"*.
- **DR (Table I)**: Kp offset ±20, obs noise ±0.03, action latency {0,1,2}step(0–40ms), mass (1±0.2). **명시적 전달비/링크 randomize 없음**(단 soft constraint impedance tunable).
- **결과**: BRUCE(kid-size, 3 병렬메커니즘), 50 Hz on Khadas Edge2, 추론 3.2ms. 전이: grass/foam/concrete 전부 성공(MPC는 grass만). closed-chain constraint sim 오버헤드 +3.4%/step.

## 5. TopA (arxiv 2507.10164) — 단순 커플링행렬(coupled ankle pitch), 모터공간
출처: https://arxiv.org/html/2507.10164v1
- **정책 = 모터공간 위치명령** (50Hz, qcmd). 저수준 PD(수 kHz, 모터드라이버)가 토크변환.
- 발목 커플링 (직렬↔모터 선형):
  `[qk;qa]_joint = [[1,0],[−1,1]]·[qk;qa]_motor` → q_a(joint)=−q_k(motor)+q_a(motor).
- Jacobian transpose **명시 안 함**(커플링행렬이 Jacobian 역할 가능하나 J^T τ 변환 기술 없음). 저수준 PD가 처리.
- 마찰모델 frequency-rich 신호로 식별·MuJoCo 매칭. 백래시/컴플라이언스/특이점 논의 없음.
- 로봇: TopA 70cm/20kg, 5DOF/leg(발목 pitch만). joint limit penalty reward(−5.0·ReLU(θ−θmax)).
- **결과**: closed-chain+adversarial 정책이 100m 코스 3.1분·40분 연속. open-chain baseline은 **코스 실패** → 병렬구조 sim 충실도가 전이에 결정적.

## 핵심 종합 (두 아키텍처 캠프)
| 캠프 | 정책 출력 | 변환 위치 | J^T | 예시 |
|---|---|---|---|---|
| **A) joint-space train + J^T deploy** | pitch/roll (가상 직렬) | 배포 저수준(SDK) | 명시 사용 | Booster Gym/T1, LiPS/Tien Kung, Unitree G1 PR mode |
| **B) motor-space end-to-end** | 모터 A/B 직접 | 없음(학습 sim이 closed-chain) | 불필요(MuJoCo eq constraint) | BRUCE, TopA, G1 AB mode |
- 캠프 A: 학습 빠름·정책 간단, 변환정확도(J 캘리브) 의존. 캠프 B: 전이충실도 최고(HW 토크/속도 비선형 그대로)·sim느림·closed-chain sim 필요.
- 공통 교훈: open-chain(직결) baseline은 병렬발목 HW서 **실패/저성능**(TopA). DR은 주로 friction/mass/latency/Kp; **링크 기하/백래시/Jacobian-error randomize는 대부분 미보고**(gap).
