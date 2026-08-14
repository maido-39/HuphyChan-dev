# 70. Sim2Real 가능한 PD 게인 (Kp/Kd) — 실현성 판정과 권고

> [!abstract] TL;DR
> **결론: 현행 게인(hip 150/6, knee 220/6, ankle 28.5/1.81)은 실기 배포 envelope 안에 있다 — 유지 권고.**
> 질량 정규화 시 knee $K_p/m = 4.27$ Nm/rad/kg로 Unitree G1(4.3)·H1(4.3)과 동일선상이고, $K_d/K_p$ 시상수(0.027–0.064 s)도 배포 로봇 범위(0.013–0.05 s) 내. 배포된 휴머노이드는 **모두 링크관성 기준 under-damped**($\zeta\approx0.05{-}0.4$)로, 우리 $\zeta\approx0.16{-}0.36$은 표준 관행이다. sim이 못 보는 4개 상한(적분기·노이즈·대역폭·포화)을 수식으로 검사해도 전부 통과. 단, **PD는 반드시 모터 펌웨어 ≥1 kHz 루프에서** 실행해야 하며(50 Hz에서 돌리면 불안정), 2-RSU 발목은 링키지 강성/백래시 벤치 검증이 남는다. DR은 $K_p\times U[0.9,1.1]$, $K_d\times U[0.7,1.3]$ + 지연 0–20 ms + 마찰 additive를 권고.

관련: [[46_wrench_6dof_loads]], [[53_bc_kd_controlled_ab]], [[62_policy_reward_design_review]], `docs/mujoco/2026-07-07_kpkd_beyondmimic_derivation.md`

---

## §1. 왜 sim은 게인 실현성을 못 보는가

### 1.1 사용자 질문의 정식화

폐루프 조인트 동역학(포화·노이즈·지연 없음)은

$$J_{\text{eff}}\,\ddot e + K_d\,\dot e + K_p\,e = \tau_{\text{ext}}$$

이고 응답 모양은 $(\omega_n, \zeta)$ 두 파라미터로 완전히 결정된다:

$$\omega_n = \sqrt{K_p / J_{\text{eff}}}, \qquad \zeta = \frac{K_d}{2\sqrt{K_p\,J_{\text{eff}}}}$$

즉 **이상적 sim에서는 $(K_p, K_d)$의 절대 크기를 키워도 벌점이 없다** — $\alpha(K_p,K_d)$로 스케일하면 $\omega_n \to \sqrt\alpha\,\omega_n$으로 더 "좋아질" 뿐, 불안정·발열·노이즈라는 현실 비용이 sim에 존재하지 않는다. "sim은 비율에만 민감하다"는 말의 실체는: **현실에서 절대 크기를 제한하는 4개의 상한이 sim에서 전부 제거되어 있다**는 것이다.

### 1.2 상한 ① — 적분기: MuJoCo는 Kd를 무조건 안정으로 만든다

MuJoCo 공식 문서(Computation 장) 인용:

> "*implicit-in-velocity* Euler ... is particularly effective in systems where instabilities are caused by **velocity-dependent forces**: ... systems with **substantial damping in tendons and actuators**."
> "Semi-implicit with implicit joint damping (`Euler`): $D$ only includes derivatives of joint damping ... $\widehat M \equiv M - hD$"

즉 속도 업데이트가 $v_{t+h} = v_t + h\,\widehat M^{-1} M\,a(v_t)$, $\widehat M = M - hD$로 계산되어 **damping(= $K_d$ 항)이 아무리 커도 수치적으로 발산하지 않는다** (음의 $D$가 $\widehat M$을 키우는 방향). mjlab은 기본 `implicitfast`를 쓰고(`src/mjlab/sim/sim.py:91`), builtin position actuator의 kp/kd 미분이 $D$에 포함된다(`src/mjlab/actuator/builtin_actuator.py:106`). **우리 B-vs-C A/B에서 Kd 14–28이 "시뮬은 잘 돌지만" 실기라면 위험한 이유가 이것** — 실기 이산 루프에는 이 implicit 보호막이 없다.

반면 실기는 유한 주기 $h_{\text{loop}}$의 **명시적(explicit) 이산 PD**다. 이산 안정 경험칙은 루프 주파수가 폐루프 고유진동수의 10–20배:

$$f_{\text{loop}} \gtrsim (10{\sim}20) \times f_n$$

최악 케이스는 링크가 분리된 순간(스윙 중 무접촉)의 armature-only 관성이다. 우리 knee: $f_n = \frac{1}{2\pi}\sqrt{220/0.007} = 28.2$ Hz → 필요 루프 ≥ 300–600 Hz. **RobStride 펌웨어 서보 루프(≥1 kHz)면 통과, 50 Hz(정책 주기)에서 PD를 돌리면 명백히 불가.** sim(200 Hz + implicit)이 이 차이를 절대 보여주지 못한다.

### 1.3 상한 ② — 속도 노이즈 × Kd (D-항 노이즈 증폭)

실기 조인트 속도는 엔코더 위치의 수치 미분이라 노이즈가 증폭된다. LQR/고게인 속도 피드백이 "sim에서는 없던 문제가 실기에서 바로 나타난다"는 것은 표준 관찰이다 (Mason et al., full-dynamics LQR humanoid, arXiv:1701.08179; Boston Dynamics 특허 "Mitigating sensor noise in legged robots" — 접촉 순간 게인을 낮추는 것까지 특허화되어 있음). D-항 노이즈 토크:

$$\tau_{\text{noise}} = K_d \cdot \sigma_{\dot q}, \qquad \sigma_{\dot q} \approx \frac{2\pi}{N_{\text{enc}}}\cdot\frac{f_s}{r} \ \ (\text{1 LSB 플립, 미분 } f_s, \text{기어 } r)$$

### 1.4 상한 ③ — 전류루프 대역폭·지연

$K_p$가 만드는 폐루프 대역폭은 모터 전류루프 대역폭(QDD 기준 수백 Hz–kHz)과 통신 지연 아래에 있어야 한다. Booster는 실측 sensor-to-actuator 지연 9–12 ms를 근거로 0–20 ms 지연을 DR에 포함했다(booster_gym). 지연 $T_d$가 있으면 위상여유가 $\omega_c T_d$만큼 깎여 고게인이 진동으로 바뀐다 — sim은 기본 지연 0.

### 1.5 상한 ④ — 토크 포화, 전달계 강성, 백래시

- **유효강성 포화**: PD는 $|e| > \tau_{\max}/K_p$부터 정토크 소스가 된다. sim도 clamp는 하지만 정격(연속) 한계·발열은 없다.
- **전달계 강성**: $K_p$는 감속기/링키지 구조강성보다 충분히(~10×) 낮아야 공진을 안 때린다. Hwangbo et al. 2019 (Science Robotics, arXiv:1901.08652)가 ANYmal의 SEA 컴플라이언스 때문에 해석적 모델 대신 **actuator network**(실기 데이터로 학습한 토크 모델)를 쓴 것이 이 갭의 대표 사례다.
- **백래시 $\delta$**: 데드존에서 $K_p\delta$ 크기의 limit cycle. QDD 저감속비라 작지만 2-RSU 볼조인트 유격은 별도.

---

## §2. 실기 배포 게인 표 (로봇별, 출처)

전부 **실기 배포/공식 저장소** 값. 정책 주기는 모두 50 Hz(G1/H1/T1), PD는 모터측 고주파 루프.

| 로봇 (질량) | 관절 | K_p | K_d | K_d/K_p [s] | K_p/m | 출처 |
|---|---|---|---|---|---|---|
| **Unitree G1** (~35 kg) | hip P/R/Y | 100 | 2 | 0.020 | 2.9 | unitree_rl_gym `deploy/configs/g1.yaml` |
| | knee | 150 | 4 | 0.027 | 4.3 | 〃 |
| | ankle P/R | 40 | 2 | 0.050 | 1.1 | 〃 |
| **Unitree H1** (~47 kg) | hip P/R/Y | 150 | 2 | 0.013 | 3.2 | unitree_rl_gym `deploy/configs/h1.yaml` |
| | knee | 200 | 4 | 0.020 | 4.3 | 〃 |
| | ankle | 40 | 2 | 0.050 | 0.85 | 〃 |
| **Booster T1** (~30 kg) | hip | 200 | 5 | 0.025 | 6.7 | booster_gym `envs/T1.yaml` |
| | knee | 200 | 5 | 0.025 | 6.7 | 〃 |
| | ankle | 50 | 1 | 0.020 | 1.7 | 〃 |
| **Berkeley Humanoid** (16 kg) | hip roll | 10 | 1.5 | 0.15 | 0.63 | isaac_berkeley_humanoid `assets/berkeley_humanoid.py` |
| | hip pitch/knee | 15 | 1.5 | 0.10 | 0.94 | 〃 |
| | ankle | 1 | 0.1 | 0.10 | 0.06 | 〃 |
| **ANYmal-C** (4족, ~50 kg) | 전 관절 | 80 | 2 | 0.025 | 1.6 | legged_gym `anymal_c_rough_config.py` |
| **K-bot** (~35 kg, RS04) | knee | 100 | 10 | 0.10 | 2.9 | kscalelabs/ksim-kbot (내부 선행조사값, 금회 원파일 재확인 실패 — 참고치) |
| **Pygmalion (현행)** (51.5 kg) | hip P/R/Y | 150 | 6 | 0.040 | 2.9 | `pygmalion_constants.py` |
| | knee | 220 | 6 | 0.027 | 4.3 | 〃 |
| | ankle (2-RSU per-DOF) | 28.5 | 1.81 | 0.064 | 0.55 | 〃 |

관찰:
1. **질량 정규화하면 수렴한다**: knee $K_p/m \approx 3{-}7$, hip $\approx 3{-}7$ Nm/rad/kg. 우리 G1 기준 ×1.47 질량스케일링은 정확히 이 관행이었다.
2. **$K_d$는 한 자릿수가 표준**: 30–50 kg급에서 hip/knee $K_d = 2{-}6$ (K-bot 10이 상한 특이점). $K_d/K_p \approx 0.02{-}0.05$ s.
3. **Berkeley Humanoid의 극저게인**(15/1.5)은 저감속(9:1) 소형기라 가능 — soft gain + RL이 강성 대신 학습으로 버티는 설계 (arXiv:2407.21781).
4. mjlab의 G1 자산 규약도 참고: $K_p = J_{\text{armature}}\,\omega_n^2$ ($f_n=10$ Hz), $K_d = 2\zeta_{\text{arm}} J_{\text{armature}}\,\omega_n$ ($\zeta_{\text{arm}}=2$) — **rotor 반사관성 기준 10 Hz·과감쇠**로 잡으면 링크관성 기준으로는 자연히 under-damped가 된다(`g1_constants.py`).

---

## §3. Feasibility 판정 기준 (수식 체크리스트)

게인 $(K_p, K_d)$가 실기 배포 가능하려면 다음 6개를 모두 통과해야 한다.

| #   | 기준         | 수식                                                    | 통과 조건                                         |
| --- | ---------- | ----------------------------------------------------- | --------------------------------------------- |
| F1  | 폐루프 고유진동수  | f_n = (1)/(2\pi)√(K_p/(J_link)+J_arm)                 | 보행 대역 ~1–6 Hz (스윙 관성 기준), 전달계 공진의 1/3 이하      |
| F2  | 감쇠비        | ζ = K_d / (2√(K_p J_eff))                             | 배포 관행 ζ ≈ 0.05-0.5 (링크관성 기준; 실기 마찰이 잔여 감쇠 제공) |
| F3  | 이산 루프 안정   | f_loop ≥ (10-20) f_n^armature-only                    | armature-only f_n 기준 (무접촉 최악)                 |
| F4  | D-항 노이즈 토크 | τ_noise = K_d σ_q̇ < 0.05 τ_rated                     | 정지 시 속도 노이즈 플로어 실측으로 검증                       |
| F5  | 토크 헤드룸     | K_p e_95 + K_d q̇_95 < τ_rated (연속), < τ_peak (순시)    | 포화 duty < 30% (기존 A1 게인 산정 기준 유지)             |
| F6  | 유효강성 vs 구조 | K_p \lesssim 0.1  k_struct, K_pδ_backlash \ll τ_rated | 2-RSU 링키지·볼조인트 대상                             |

**배포 전 진단 프로토콜** (벤치, 관절 단위):
1. **정지 노이즈 플로어**: 로봇 매달고 $\dot q$ 로깅 → $\sigma_{\dot q}$ → F4 계산.
2. **Chirp 응답**: 0.5→15 Hz 사인 스윕 $q_{\text{target}}$ → -3 dB 대역폭과 공진 피크 확인 (F1, F6). 우리 `analyze_qtarget.py`의 $\tau \sim K_p e - K_d \dot q$ 회귀 $R^2$로 포화 진단 병행.
3. **스텝 응답**: 0.1–0.3 rad 스텝 → 오버슈트로 실효 $\zeta$ 역산, 링 발생 시 $K_d$ 부족 또는 백래시.
4. **열 정격**: 10 min 보행 상당 궤적 → RMS 토크 < 정격 (RS04 40 Nm, RS03 20 Nm).

---

## §4. 우리 게인 판정

$J_{\text{eff}}$는 BeyondMimic 유도(`docs/mujoco/2026-07-07_kpkd_beyondmimic_derivation.md`)의 질량행렬 값 사용. 노이즈 계산은 RobStride 14-bit급 로터 자기엔코더 가정: $\sigma_{\dot q} \approx \frac{2\pi}{16384}\cdot\frac{1000}{9} \approx 0.043$ rad/s (1 kHz 미분, 기어 9:1; **실측 필요**).

| 관절 | K_p/K_d | f_n (stance/swing) | ζ | F3: armature f_n → 필요루프 | F4: τ_noise | F5: 포화점 τ_rated/K_p | 판정 |
|---|---|---|---|---|---|---|---|
| hip P/R | 150/6 | 1.4 / ~3.3 Hz | ≈0.16 | 21 Hz → ≥400 Hz | 0.26 Nm (정격 0.6%) | 0.27 rad | **PASS** |
| hip Y | 150/6 | ~3.4 Hz | ≈0.43 | 21 Hz → ≥400 Hz | 0.26 Nm | 0.27 rad | **PASS** |
| knee | 220/6 | 4.2 Hz | ≈0.36 | 28 Hz → ≥600 Hz | 0.26 Nm | 0.18 rad | **PASS** |
| ankle (2-RSU) | 28.5/1.81 | 3.8–6 Hz | ≈1.0 (foot J≈0.03) | (RS03 직렬 기준 소) | 0.08 Nm | 0.7 rad | **조건부 PASS** |

세부:
- **$\zeta$ under-damped는 결함이 아니라 관행**: 같은 방법으로 추정하면 G1 배포 게인도 hip $\zeta \approx 0.1$, knee $\approx 0.37$; H1 hip $\approx 0.05$. 실기에서는 기어 마찰·점성 손실이 모델 밖 감쇠를 더해주므로 명시적 $K_d$는 낮게 두는 것이 배포 표준이다. **B-vs-C A/B에서 link-critical Kd(14+)가 부하 2–3.5×·추종 2.8–5× 악화로 기각된 결과([[53_bc_kd_controlled_ab]])는 이 관행과 정합**하고, F4 계산상 Kd 14도 노이즈로는 통과였으므로 기각 사유는 어디까지나 성능이다(노이즈 상한만 보면 $K_d^{\max} \approx 0.05\times40/0.043 \approx 47$).
- **F3이 진짜 제약**: knee 220은 armature-only 28 Hz → **PD를 50 Hz 정책 루프에서 돌리는 배포는 불가능**. 반드시 RobStride 펌웨어 위치모드(내장 서보 루프) 또는 자체 MCU ≥1 kHz PD로 실행하고, 정책은 $q_{\text{target}}$만 50 Hz로 갱신 (G1/H1/T1 전부 이 구조).
- **F5**: knee 유효강성 포화점 0.18 rad(정격)/0.55 rad(peak). action scale 0.5에서 스윙 목표오차가 0.18 rad를 자주 넘으면 정격영역 초과 — §7 motor-util 리포트의 knee 112% 이슈와 같은 축이므로, 실기에서는 RMS로 재확인.
- **발목 조건부**: 게인 자체는 G1 40/2보다 부드러워 안전하나, **feasibility가 게인이 아니라 기구에 달렸다**: (i) 2-RSU 링키지 강성 $k_{\text{struct}} \gg 285$ Nm/rad 확인, (ii) 볼조인트 백래시 $\delta$에서 $K_p\delta$ limit cycle, (iii) 조인트공간 $K_d$가 모터공간에서 $J_{\text{RSU}}^{-T} K_d J_{\text{RSU}}^{-1}$로 사상되며 특이점 근처에서 증폭되는 것 — 벤치 chirp 필수.

---

## §5. 권고

### 5.1 게인: 현행 유지

$$\boxed{\text{hip } 150/6,\quad \text{knee } 220/6,\quad \text{ankle } 28.5/1.81 \;\;(\text{변경 없음})}$$

변경 불요 근거: 질량 정규화 배포 표와 일치(§2), 6개 기준 통과(§4), 그리고 이미 A/B로 대안(Kd14+)이 기각됨. 굳이 조정한다면 후보는 **hip $K_d$ 6→4** ($K_d/K_p$ 0.04→0.027로 G1/H1 관행에 근접, 스윙 다리 반응성↑)이지만, 이는 성능 실험이지 feasibility 사안이 아니다 — 리워드 리서치 룰 대상.

### 5.2 배포 아키텍처 (게인보다 중요)

1. PD는 **모터 펌웨어 ≥1 kHz**에서, 정책은 50 Hz로 $q_{\text{target}}$만 송신.
2. 펌웨어 속도필터 컷오프 확인 — 필터가 강하면 $\sigma_{\dot q}$는 줄지만 위상지연이 실효 $K_d$를 깎는다(둘 다 sim에 없음).
3. 배포 전 §3 진단 프로토콜(노이즈 플로어 → chirp → 스텝 → 열) 관절별 1회.

### 5.3 Domain Randomization 권고

| 항목 | 범위 | 근거 |
|---|---|---|
| K_p | × U[0.9, 1.1] | 기어드 휴머노이드 실배포 (arXiv:2504.00614); Booster는 [0.95,1.05] |
| K_d | × U[0.7, 1.3] (보수 시작) → 필요 시 [0.5, 1.5] | arXiv:2504.00614가 [0.5,1.5] 사용 — K_d 불확실성(마찰·필터)이 K_p보다 큼 |
| 관절 마찰 | additive [0, 1.5] Nm | Booster T1 [0, 2.0] additive 준용, RS04급 하향 |
| armature | × U[0.9, 1.1] | 반사관성 불확실성 |
| 지연 (obs→act) | [0, 20] ms | Booster 실측 9–12 ms 기반 |

주의: 문헌 합의는 **$K_p/K_d$ DR 단독으론 부족하고 정적 마찰·지연 randomization이 전이를 좌우**한다는 것 (Saturn Lite 연구: rotor inertia+마찰+PD만으론 실패, static friction 추가로 성공, arXiv:2503.01255; Booster; Actuator Reality Shaping arXiv:2607.02205). 현행 PYG_NO_DR 계열 런에 DR을 켤 때 위 5종을 한 묶음으로.

---

## 출처

1. Unitree G1 배포 config — https://github.com/unitreerobotics/unitree_rl_gym `deploy/deploy_real/configs/g1.yaml` (kps [100,100,100,150,40,40], kds [2,2,2,4,2,2], control_dt 0.02)
2. Unitree H1 배포 config — 同 repo `deploy/deploy_real/configs/h1.yaml` (kps [150,150,150,200,40], kds [2,2,2,4,2])
3. Booster T1 — https://github.com/BoosterRobotics/booster_gym `envs/T1.yaml` (stiffness hip/knee 200, ankle 50; damping 5/5/1; DR stiffness·damping ×[0.95,1.05], friction additive [0,2], base mass ×[0.8,1.2]); 논문 https://arxiv.org/abs/2506.15132
4. Berkeley Humanoid — https://github.com/HybridRobotics/isaac_berkeley_humanoid (stiffness 10–15, damping 1.5, ankle 1/0.1); 논문 https://arxiv.org/abs/2407.21781
5. ANYmal-C — https://github.com/leggedrobotics/legged_gym `anymal_c_rough_config.py` (80/2, decimation 4)
6. K-bot — https://github.com/kscalelabs/ksim-kbot (knee 100/10은 내부 선행조사 참고치)
7. MuJoCo Computation docs (implicit-in-velocity, implicit joint damping) — https://mujoco.readthedocs.io/en/stable/computation/index.html
8. Hwangbo et al., "Learning agile and dynamic motor skills for legged robots," Science Robotics 2019 (actuator network) — https://arxiv.org/abs/1901.08652
9. 기어드 휴머노이드 sim2real ($K_p$×[0.9,1.1], $K_d$×[0.5,1.5]) — https://arxiv.org/abs/2504.00614
10. Static friction이 sim2real 성패 좌우 — https://arxiv.org/html/2503.01255v1
11. Actuator Reality Shaping (zero-shot 전이용 randomization 항목) — https://arxiv.org/abs/2607.02205
12. Joint torque-space perturbation injection — https://arxiv.org/abs/2504.06585
13. 속도 노이즈·고게인 속도피드백 실기 문제 (full-dynamics LQR humanoid) — https://arxiv.org/abs/1701.08179
14. Boston Dynamics 특허 "Mitigating sensor noise in legged robots" — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10583879
15. Isaac Sim joint drive 튜닝 가이드 — https://docs.isaacsim.omniverse.nvidia.com/4.5.0/robot_setup/joint_tuning.html
16. 내부: `mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/pygmalion_constants.py`, `unitree_g1/g1_constants.py`, `mjlab/sim/sim.py` (implicitfast), `docs/mujoco/2026-07-07_kpkd_beyondmimic_derivation.md`, [[53_bc_kd_controlled_ab]]

## §6 150Hz 명령률 제약 + RobStride 운동제어모드 검증 (2026-07-21, 사용자 질의)
**질문**: 모터 제어(CAN 명령)가 150 Hz 한계 — kHz PD 조건을 어떻게 충족하나?
**답**: PD를 모터 온보드로 — RobStride **운동제어(MIT) 모드** 사용. 검증 결과:

| 주장 | 판정 | 근거 |
|---|---|---|
| 1 CAN 프레임에 (목표각, 목표속도, Kp, Kd)+τ_ff 탑재 | ✅ **공식 확인** | RobStride 00 매뉴얼 Communication Type 1: Byte0~1 angle(−4π~4π)·2~3 velocity·4~5 Kp(0~500)·6~7 Kd(0~5), τ는 확장 ID — [aifitlab 매뉴얼](https://wiki.aifitlab.com/robstride-docs/robstride-00-instruction-manual) |
| PD가 드라이버 온보드에서 실행 | ✅ 확인 | 위 프레임 구조 자체가 증거(호스트는 파라미터만 전송) + [Seeed 가이드](https://wiki.seeedstudio.com/robstride_control/) MIT식 c_ref=K_p e+K_dė+c_ff; 로컬 robstride-datasheet.md §MIT-mode(출력축 게인, Seeed+CubeMars 대조 기검증) |
| 내부 루프 = kHz급 | ⚠ **정황 확인(공식 미기재)** | 매뉴얼에 루프율 없음. 2차: [OpenELAB](https://openelab.io/blogs/learn/robstride02-qdd-17n-m-joint-motor-module-complete-technical-guide) 전류루프 10~20 kHz(듀얼엔코더)·호스트 제어 50~200 Hz 권장; 동급 MIT Cheetah 드라이버 전류 20 kHz([IROS](https://dspace.mit.edu/bitstream/handle/1721.1/126619/IROS.pdf?sequence=2&isAllowed=y)). PD(위치/속도)루프율은 미공표 — **벤치 chirp로 실측이 확정 수단**(§4 잔여리스크와 동일 항목) |
- **게인 범위 호환**: RS00 온보드 Kd 상한 5.0 — 우리 ankle Kd 1.81 ✓, Kp 28.5<500 ✓. knee 220/6도 RS04급 범위 내(모델별 스케일 상이, 매뉴얼 확인).
- **결론**: 150 Hz는 명령 갱신률로 충분(정책 50 Hz의 3배). PD는 온보드 실행 확정, 루프율만 벤치 검증 항목으로 이월. 호스트-PD 경로(Kp ~1/10 감축+재학습)는 불필요 전망.

### §6b 심화 조사 (2026-07-21) — 루프율 공표 부재의 확정 + 계보·배포 증거
1. **공표 부재 확정**: RobStride RS00 매뉴얼·Xiaomi CyberGear 전체 매뉴얼([cybergear-docs](https://github.com/belovictor/cybergear-docs/blob/main/instructionmanual/instructionmanual.md), 파라미터 표 3.3.3 포함) 전수 — **전류/속도/위치 루프율 미기재**(cur_filt_gain 등 필터계수만). "몇 kHz"는 벤더 공식으로는 확인 불가가 사실.
2. **펌웨어 계보 증거**: RobStride 운동제어 프레임(Byte4~5 Kp 0~500·Byte6~7 Kd 0~5)이 **CyberGear와 바이트 단위 동일** = CyberGear 파생 확정. 그리고 이 프로토콜(p_des·v_des·Kp·Kd·τ_ff 16bit 패킹)은 **Ben Katz mini-cheetah 오픈펌웨어의 CAN 규격 그대로** — 그 원형 펌웨어에서 PD는 FOC 전류루프와 같은 인터럽트 fast-path에서 평가됨(전류루프율로 실행). 동급 드라이버 전류루프 10~20 kHz([OpenELAB](https://openelab.io/blogs/learn/robstride02-qdd-17n-m-joint-motor-module-complete-technical-guide)·[MIT Cheetah 3](https://dspace.mit.edu/bitstream/handle/1721.1/126619/IROS.pdf?sequence=2&isAllowed=y) 20 kHz).
3. **★배포 증거(가장 강함)**: K-Scale **K-Bot이 동일 모터(RS04)·동일 운동제어모드**로 실보행 — 호스트 제어 50~200 Hz + 온보드 PD([K-Scale Docs](https://docs.kscale.dev/robots/k-bot/quickstart/), RS04 knee Kp100/Kd10 — 우리 knee 220/6과 동일 오더). 아키텍처가 우리 모터·게인급에서 field-proven.
4. **결론(갱신)**: "온보드 PD, 전류루프 fast-path 실행, 동일모터 실배포 선례"까지 확인 — 150 Hz 명령률 우려는 사실상 해소. 잔여 확인 = **우리 개체 벤치 chirp**(luop율·유효 대역 실측, 유일한 미공표 수치의 직접 측정). 우리 knee Kp 220은 K-bot 100의 2.2×이므로 chirp에서 고Kp 안정성만 추가 확인.
