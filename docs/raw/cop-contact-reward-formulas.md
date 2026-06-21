# CoP/contact 보상 공식 — Siekmann / Walk-These-Ways verbatim (원문 검증)

> 출처: workflow wyvmh4gpv (full-text fetch via ar5iv.labs.arxiv.org) · fetched 2026-06-21 · verified yes
> 규칙([[raw/README]]): verbatim 공식 + 출처만. 수정 금지.
> ★ 핵심 검증 결과: **두 논문 모두 CoP/ZMP/heel→toe 보상을 포함하지 않는다** — foot-FORCE·foot-VELOCITY norm을 위상클록으로 게이트할 뿐, center-of-pressure가 아님. heel→toe CoP-progression 보상은 **표준 검증 공식이 아니다**(외부 toe-roll 리포트가 과장).

---

## (1) Siekmann et al., "Sim-to-Real Learning of All Common Bipedal Gaits via Periodic Reward Composition", ICRA 2021 (arXiv:2011.01387)

> 출처: https://ar5iv.labs.arxiv.org/html/2011.01387 · https://arxiv.org/abs/2011.01387 · fetched 2026-06-21 · verified yes(전문 대조)

**위상 지시자 — Von Mises (Eq.1)**: 각 I_i(phi)는 구간경계 A_i,B_i가 Von Mises 분포에서 뽑히는 베르누이 확률변수:
```
P(I_i(phi)=x) = { P(A_i < phi < B_i)      if x = 1
                { 1 - P(A_i < phi < B_i)  if x = 0
P(A_i < phi < B_i) = P(A_i < phi)·(1 - P(B_i < phi))
A_i ~ Phi(2*pi*a_i, kappa),  B_i ~ Phi(2*pi*b_i, kappa)
```
Phi = Von Mises 분포, a_i/b_i = 정규화([0,1]) 구간 시작/끝 ×2π, kappa = concentration(클수록 위상전이 sharp). von Mises 평활화 → E[I_i(phi)]가 위상의 매끄러운 미분가능 함수.

**단일 보상성분**: `R_i(s, phi) = c_i * I_i(phi) * q_i(s)` (c_i = swing/stance 위상계수, q_i = 측정량).

**q-커널 (두 기본 측정)**:
```
q_frc(s) = foot ground-reaction force 의 norm,  포화형: q_frc = 1 - exp(-omega * ||raw_foot_frc||^2 / 100)
q_spd(s) = foot (병진) velocity 의 norm,        포화형: q_spd = 1 - exp(-2 * omega * ||raw_foot_spd||^2)
```
(둘 다 [0,1) 범위의 bounded cost.)

**swing/stance 계수 (verbatim)**:
```
SWING:  c_swing_frc = -1,  c_swing_spd = 0   (발힘 penalty, 발속도 무시 → 발이 떠 있어야)
STANCE: c_stance_spd = -1, c_stance_frc = 0   (발속도 penalty, 발힘 무시 → 발이 planted)
```
음계수 = cost. 그 외 계수는 0.

**기대 biped 보상 (Eq.2)**:
```
E[R_bipedal(s,phi)] = E[C_frc(phi + theta_left)]·q_left_frc(s)
                    + E[C_frc(phi + theta_right)]·q_right_frc(s)
                    + E[C_spd(phi + theta_left)]·q_left_spd(s)
                    + E[C_spd(phi + theta_right)]·q_right_spd(s)
```
C_frc/C_spd = swing/stance c값 × (기대)위상지시자로 만든 위상의존 계수함수. theta_left/right = 발별 위상 오프셋. 정상 대칭보행 = anti-phase: |theta_left - theta_right| ≈ 0.5 (Fig.4).

**총보상 (Eq.3)**: `E[R(s,phi)] = E[R_bipedal] + R_smooth(s) + R_cmd(s) + beta`
(R_smooth = action차이·토크·골반가속 penalty; R_cmd = 속도/방향 명령추종; beta = 양수 유지용 상수.)

**위상비**: r∈(0,1)가 사이클 내 phase 비율 설정 — swing 길이 r, stance 길이 1−r(게이트 r·theta로 보행종류 선택).

★ **검증**: Siekmann 전문 내 contact 관련량은 **q_frc(foot-force norm)·q_spd(foot-velocity norm) 단 둘뿐.** contact-point 위치·압력분포·CoP·ZMP 항은 **어디에도 없음.**

## (2) Margolis & Agrawal, "Walk These Ways", CoRL 2022 (arXiv:2212.03238)

> 출처: https://ar5iv.labs.arxiv.org/html/2212.03238 · https://arxiv.org/abs/2212.03238 · https://gmargo11.github.io/walk-these-ways/ · fetched 2026-06-21 · verified yes(전문 대조)

**곱셈 합성 (Sec 3.1, verbatim)**: `total reward = r_task * exp(c_aux * r_aux)`, r_task = (양수)task항 합, r_aux = (음수)auxiliary항 합, **c_aux = 0.02.** 곱을 양수로 유지하며 aux penalty를 task에 곱셈 스케일.

**desired contact state — Gaussian/normal CDF (Appendix D, verbatim)**:
```
C_foot^cmd( t_foot ) = Phi(t_foot, sigma)·(1 - Phi(t_foot - 0.5, sigma))
                     + Phi(t_foot - 1, sigma)·(1 - Phi(t_foot - 1.5, sigma))
```
Phi(x; sigma) = **정규(Gaussian) 분포 CDF** (Siekmann의 von Mises와 대조!). C_foot^cmd ≈ 1 = 명령 stance 창, ≈ 0 = swing.

**발별 타이밍 (clip된 위상, verbatim)**:
```
[t_FR, t_FL, t_RR, t_RL] = clip( [ t + theta2 + theta3,
                                   t + theta1 + theta3,
                                   t + theta1,
                                   t + theta2 ], 0, 1 )
gait 오프셋 theta^cmd: pronk(0,0,0), trot(0.5,0,0), bound(0,0.5,0), pace(0,0,0.5)
```

**swing-force & stance-velocity 항 (Table 1, "augmented auxiliary", verbatim 식 + 가중치)**:
```
swing-phase tracking (force) r_cf^cmd = sum_foot [ 1 - C_foot^cmd ]·exp{ -||f_foot||^2 / sigma_cf }   weight = -0.08
   (명령 SWING(1-C≈1)에서 발 FORCE penalty)
stance-phase tracking (velocity) r_cv^cmd = sum_foot [ C_foot^cmd ]·exp{ -||v_xy^foot||^2 / sigma_cv }   weight = -0.08
   (명령 STANCE(C≈1)에서 발 xy-VELOCITY penalty)
```

**기타 Table 1 항 (verbatim 식 + 가중치)**:
- task: xy-vel track exp{-|v_xy - v_xy^cmd|^2/sigma_vxy} **+0.02**; yaw-rate track exp{-(omega_z - omega_z^cmd)^2/sigma_omega_z} **+0.01**.
- aug aux: body height (h_z-h_z^cmd)^2 **-0.2**; body pitch (phi-phi^cmd)^2 **-0.1**; Raibert footswing placement (p_xy,foot - p_xy,foot^cmd)^2 **-0.2**; footswing height sum_foot (h_z,foot - h_z^cmd)^2·C_foot^cmd **-0.6**.
- fixed aux penalty(z-vel, roll/pitch-vel, foot slip, collision, joint limit, torque, jvel, jacc, action-rate×2): weights -4e-4, -2e-5, -8e-4, -0.02, -0.2, …, -2e-5, -5e-9, -2e-3, -2e-3.

★ **검증**: Walk-These-Ways도 **이진적 desired-contact SCHEDULE**(swing=force penalty, stance=velocity penalty) + Raibert 발디딤 휴리스틱만 보상. **within-foot CoP progression 없음.**

## (3) heel→toe CoP-progression / roll-over 보상 — 존재하나? (★ 핵심)

★★ **두 타깃 논문 어디에도 CoP(center-of-pressure)·ZMP(zero-moment-point)·heel→toe/roll-over 보상이 없다.** Siekmann 전문서 직접 검증: contact 관련량은 foot-force norm(q_frc)·foot-velocity norm(q_spd) **단 둘뿐**, contact-point 위치·압력분포·CoP·ZMP 항 전무. Walk-These-Ways도 desired contact schedule(force-in-swing, velocity-in-stance) + Raibert footstep heuristic뿐 — within-foot CoP 진행 없음.

광범위 문헌검색 결과: CoP/ZMP는 주로 **모델기반 제어**(LIP/ALIP/H-LIP 축소차수모델, support polygon 내 ZMP/CoP 유지)와 일부 CoM→CoP 연결벡터 추종 안정성-보상 연구에 등장. 그러나 **이 contact-schedule RL 계열의 어떤 정전 논문도 verbatim heel→toe CoP-progression 보상 공식을 정의하지 않음.** 그런 항은 두 작업의 표준이 아니며 contact-RL 문헌서 확립된 closed-form 보상으로 발견되지 않음.

> 함의(우리): 외부 toe-roll 리포트가 "Siekmann/Walk-These-Ways가 heel→toe CoP 보상을 쓴다"는 식으로 과장했다면 **부정확.** 이들은 **위상클록으로 게이트한 foot-force/foot-velocity norm**을 쓰지 CoP가 아니다. heel→toe CoP-progression은 검증된 표준 공식이 아니다 (우리 forefoot_cop 보상은 자체 합성 항임 — [[23_toe_use_methods]]).

## 출처 (하이퍼링크)

- Siekmann, Godse, Fern, Hurst (2021), "Sim-to-Real Learning of All Common Bipedal Gaits via Periodic Reward Composition," ICRA — https://arxiv.org/abs/2011.01387 (full-text: https://ar5iv.labs.arxiv.org/html/2011.01387)
- Margolis & Agrawal (2022), "Walk These Ways: Tuning Robot Control for Generalization with Multiplicity of Behavior," CoRL — https://arxiv.org/abs/2212.03238 (full-text: https://ar5iv.labs.arxiv.org/html/2212.03238 · 프로젝트: https://gmargo11.github.io/walk-these-ways/)
