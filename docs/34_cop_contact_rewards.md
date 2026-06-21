# 34 · CoP/contact 보상 공식 — Siekmann & Walk-These-Ways verbatim (검증, wyvmh4gpv)

> [!question] 검증한 질문
> Siekmann 주기보상·Margolis Walk-These-Ways의 contact 보상 **정확한 공식**은? heel→toe CoP-progression 보상이 이 계열의 표준 공식인가?

> [!warning] ★ 핵심 검증 결과 (가장 중요)
> **Siekmann도 Walk-These-Ways도 CoP/ZMP/heel→toe 보상을 포함하지 않는다.** 둘 다 **foot-FORCE norm·foot-VELOCITY norm을 위상클록으로 게이트**할 뿐, center-of-pressure가 아니다. heel→toe CoP-progression 보상은 **검증된 표준 공식이 아니다** — 외부 toe-roll 리포트가 이를 과장했다면 부정확. (우리 `forefoot_cop`은 자체 합성 항 — [[23_toe_use_methods]].)

> 검증 원문층(verbatim 공식 + 출처): [[raw/cop-contact-reward-formulas]]. 관련 [[23_toe_use_methods]] · [[11_research_gait_rewards]] · [[Paperreview/siekmann-periodic-reward]] · [[22_energy_toe_reward]].

---

## 1. Siekmann et al. 2021 — Periodic Reward Composition (arXiv:2011.01387)

> 전문 대조 검증(verified=yes). 전체 verbatim → [[raw/cop-contact-reward-formulas]].

**위상 지시자 — Von Mises (Eq.1)**: 구간경계 A_i,B_i를 Von Mises에서 뽑는 베르누이 확률변수
$$A_i \sim \Phi(2\pi a_i, \kappa),\quad B_i \sim \Phi(2\pi b_i, \kappa),\quad P(A_i<\phi<B_i)=P(A_i<\phi)\,(1-P(B_i<\phi))$$
Φ=Von Mises, κ=concentration(클수록 sharp). 평활화 → E[I_i(φ)]가 위상의 매끄러운 미분가능 함수.

**보상성분**: `R_i(s,φ) = c_i · I_i(φ) · q_i(s)`

**q-커널 (단 두 측정)**:
$$q_{frc}=1-\exp(-\omega\,\|raw\_foot\_frc\|^2/100),\qquad q_{spd}=1-\exp(-2\omega\,\|raw\_foot\_spd\|^2)$$
= foot **GRF norm** / foot **velocity norm** ([0,1) bounded cost).

**swing/stance 계수 (verbatim)**:

| phase | c_frc | c_spd | 의도 |
|---|---|---|---|
| SWING | **−1** | 0 | 발힘 penalty, 속도 무시 → 발이 떠 있어야 |
| STANCE | 0 | **−1** | 발속도 penalty, 힘 무시 → 발이 planted |

**총보상 (Eq.2·3)**: `E[R] = E[R_bipedal] + R_smooth + R_cmd + β`, R_bipedal = 발별 C_frc·q_frc + C_spd·q_spd(theta 오프셋). 정상보행 anti-phase |θ_L−θ_R|≈0.5. 위상비 r → swing 길이 r, stance 1−r.

## 2. Margolis & Agrawal — Walk These Ways (arXiv:2212.03238)

> 전문 대조 검증(verified=yes).

**곱셈 합성 (Sec 3.1)**: `r = r_task · exp(c_aux · r_aux)`, **c_aux = 0.02** (r_task=양수 task항 합, r_aux=음수 aux항 합). 곱을 양수 유지하며 aux를 곱셈 스케일.

**desired contact — Gaussian/normal CDF (App.D)** — Siekmann의 von Mises와 **대조**:
$$C_{foot}^{cmd}=\Phi(t_{foot},\sigma)(1-\Phi(t_{foot}-0.5,\sigma))+\Phi(t_{foot}-1,\sigma)(1-\Phi(t_{foot}-1.5,\sigma))$$
Φ = 정규분포 CDF. C≈1 = stance 창, C≈0 = swing.

**timing**: `[t_FR,t_FL,t_RR,t_RL]=clip([t+θ2+θ3, t+θ1+θ3, t+θ1, t+θ2],0,1)`; gait θ: pronk(0,0,0)·trot(0.5,0,0)·bound(0,0.5,0)·pace(0,0,0.5).

**swing-force & stance-velocity 항 (Table 1, verbatim + 가중치)**:

| 항 | 식 | weight |
|---|---|---|
| swing-force r_cf | Σ_foot [1 − C_foot^cmd]·exp{−‖f_foot‖²/σ_cf} | **−0.08** |
| stance-vel r_cv | Σ_foot [C_foot^cmd]·exp{−‖v_xy^foot‖²/σ_cv} | **−0.08** |

기타: xy-vel track +0.02, yaw-rate +0.01, body height −0.2, pitch −0.1, Raibert footswing −0.2, footswing height −0.6; fixed aux(z-vel/rp-vel/slip/collision/joint-limit/torque/jvel/jacc/action-rate×2) = −4e-4, −2e-5, −8e-4, −0.02, −0.2, …, −2e-5, −5e-9, −2e-3, −2e-3.

## 3. ★ heel→toe CoP-progression 보상은 표준인가? — 아니다 (검증)

- **두 논문 어디에도 CoP·ZMP·heel→toe·roll-over 보상 없음.** Siekmann 전문서 contact 관련량은 **q_frc(foot-force norm)·q_spd(foot-velocity norm) 단 둘뿐** — contact-point 위치·압력분포·CoP·ZMP 항 전무. Walk-These-Ways는 이진적 desired-contact **schedule**(swing=force penalty, stance=velocity penalty) + Raibert footstep 휴리스틱뿐, within-foot CoP 진행 없음.
- 문헌검색: CoP/ZMP는 주로 **모델기반 제어**(LIP/ALIP/H-LIP, support polygon 내 ZMP 유지)와 일부 CoM→CoP 연결벡터 안정성-보상에 등장. **이 contact-schedule RL 계열의 정전 논문 중 verbatim heel→toe CoP-progression 보상을 정의한 것은 없음.**
- **함의**: 이들은 **위상클록으로 게이트한 foot-force/foot-velocity norm**을 쓰지 CoP가 아니다. 외부 toe-roll 리포트가 "heel→toe CoP 보상이 표준"이라 했다면 과장. 우리 `forefoot_cop`(앞발 GRF 비율 toe/(toe+foot))은 **자체 합성 항**이며 검증된 표준 공식 차용이 아님 — 안티패턴 논의는 [[23_toe_use_methods]] 참조.

## 4. References (하이퍼링크)

- [Siekmann, Godse, Fern, Hurst (2021), "Sim-to-Real Learning of All Common Bipedal Gaits via Periodic Reward Composition," ICRA — arXiv:2011.01387](https://arxiv.org/abs/2011.01387) ([full-text ar5iv](https://ar5iv.labs.arxiv.org/html/2011.01387))
- [Margolis & Agrawal (2022), "Walk These Ways," CoRL — arXiv:2212.03238](https://arxiv.org/abs/2212.03238) ([full-text ar5iv](https://ar5iv.labs.arxiv.org/html/2212.03238) · [프로젝트 페이지](https://gmargo11.github.io/walk-these-ways/))

> [!note] 솔직성 노트
> 모든 공식은 ar5iv 전문(2011.01387, 2212.03238)에서 직접 대조(verified=yes). "CoP 보상 부재"는 **부정 진술**이라 두 논문 전문 범위 내 검증 — 더 넓은 RL 문헌엔 CoM-CoP 안정성-보상류가 존재하나 이 두 contact-schedule 작업의 표준은 아님.
