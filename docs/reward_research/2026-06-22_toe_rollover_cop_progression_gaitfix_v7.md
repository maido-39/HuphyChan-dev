# reward 연구 — gaitfix_v7: TOE ROLLOVER = CoP anterior-progression (forefoot-fraction × contact-time ramp), no clock·no heel body (2026-06-22)

> [!info] SUPERSEDED → 정본은 [[2026-06-22_12-19_gaitfix_v7_cop_progression]]. 이 노트는 **토우 CoP-progression 설계 단독**이며 adversarial 판정 *이전*판. 정본은 (A) 토우 CoP-progression + (B) base floor/deadband 완화 + (C) double-support 복원을 **묶음 출하**로 합성하고 base-단독-null GATE를 반영함. 토우 항 상세는 여기, **출하 결정은 정본 참조**.

> 트리거: gaitfix_v6 결과 — base 완화 + push-off 복원은 **방향은 맞지만 약함**. vertical bob 1.19→1.46cm(+23%, 인간 2.5), 골반 roll/pitch swing **불변**(3.9/1.5°), toe moment 15→19 N·m(+25%, 인간 ~40 *질량비정규화*), toe bend 11→13°(인간 25-35), ankle_pitch RMS 23→26.5(여전히 RS03 −60 클립), 낙상 1→2%. v6에서 **HOLD했던** CoP-anterior-progression 전용 보상을 v7에서 신설.
> 바꾸려는 reward: `forefoot_cop`(0.8, 정적 분율, v6 기여 **+0.0251 = reward의 0.06%**)을 **시간적 CoP 전진 보상**으로 교체/보강. ankle_pitch 포화이므로 **plantarflexion을 더 크랭크하지 않고** CoP를 굴린다.
> 관련: [[2026-06-22_12-30_toe_rollover_cop_progression_gaitfix_v6]](정본 원인분석), [[2026-06-22_13-30_gaitfix_v6_base_relax_pushoff]], [[34_cop_contact_rewards]], [[23_toe_use_methods]].

---

## 1. 직전 결과 분석 (gaitfix_v6, [[experiments/2026-06-22_11-20-05_gaitfix_v6]])

| 양 | v5→v6 | 인간 | 판정 |
|---|---|---|---|
| vertical CoM bob | 1.19→1.46cm (+23%) | ~2.5cm | 완화 효과 약함 |
| 골반 roll/pitch swing | 3.9/1.5° (불변) | ~7/4° | **flat_orientation −0.5도 안 움직임** |
| toe moment | 15→19 N·m (+25%) | ~40(비정규)/6.7(51.8kg정규) | moment는 이미 충분, **굴림 부재** |
| toe bend | 11→13° | 25-35° | ✗ **진짜 결손 (여전)** |
| ankle_pitch RMS | 23→26.5 | — | RS03 peak −60 **클립** = 포화 |
| 낙상 | 1→2% | — | 안정 |

- **★ `forefoot_cop` 기여 = +0.0251 (reward 43.4의 0.06%)** — weight 0.8인데도 무시 가능. **정적 순간 분율은 시간적 시퀀스를 만들지 못한다**는 v6 가설을 측정이 직접 확증.
- **★ `ankle_pushoff` 기여 = +0.1038** — 0.5로 복원됐으나 ankle_pitch가 이미 RS03(−60) 클립 → **push-off를 더 크랭크하면 모터 over-drive**. 토우 수정은 ankle plantarflexion 강화가 아닌 **다른 레버**여야 함.
- 결론: base 완화·push-off 복원은 *directionally right but WEAK*. 골반 tilt는 안 움직였고 toe는 안 굴렀다. **CoP를 heel→toe로 *시간적으로* 전진시키는 전용 보상이 빠졌다**(v6에서 의도적으로 HOLD).

## 2. 가용 센서 (verified, 코드 grep)

- `contact_forces = ContactSensorCfg(history_length=3, **track_air_time=True**)` (IsaacLab base velocity_env_cfg.py:74). → **`current_contact_time[:, body_ids]` 신뢰 가용** (이미 `feet_air_time`·`forefoot_cop` late-gate가 사용 중, fall-back try/except 있음).
- 2-segment: `foot_link`(.*_foot_link = heel+mid plate) 접지센서 + `toe_link`(.*_toe_link) wrench Fz. **별도 heel body 없음, gait clock 없음**(verified).
- → **contact-time = stance-phase proxy**. heel/toe per-segment 접지 시퀀스(Duke contact_pattern)는 heel body 부재로 불가 → **CoP 전진을 forefoot GRF 분율의 *contact-time 따른 변화*로 직접 보상**(이게 v7 핵심).

## 3. ★ 설계 — 채택안 (a): forefoot-fraction × normalized-contact-time RAMP

### 3-1. 왜 (a)인가 (3 후보 비교)
- **(a) toe-load FRACTION이 contact-time 따라 증가** ← ★채택. forefoot fraction frac = Fz_toe/(Fz_foot+Fz_toe)를 **정규화 접지시간 τ_n = clamp(t_contact/T_stance,0,1)** 으로 곱해, **늦은 stance에서 높은 forefoot 분율**일 때만 보상. 생체역학 정합: CoP가 stance 동안 heel→forefoot로 ~83% foot-length 전진([s-cop]), forefoot 분율은 stance 후반 단조증가. **clock 불요(contact-time가 proxy), heel body 불요(2-seg 분율로 충분), ankle plantarflexion 크랭크 안 함**(보상이 *어디에 적재되나*=CoP 위치이지 ankle 토크가 아님 → ankle over-drive 회피의 핵심).
- (b) toe FLEXION을 late-stance 게이트 → **기각**. |tau_toe|=k·deflection → 정적 toe-curl로 reward-hack (toe over-damped라 curl이 쌈), `toe_load_stance` 폐기와 동일 안티패턴([[23_toe_use_methods]]). bend 각 자체를 보상하면 위장.
- (c) CoP 위치를 phase-ramp 추종(ZMP식 exp(−‖frac−frac*(τ)‖)) → **차선**. (a)의 reference-tracking 버전. 더 sharp하지만 frac*(τ) reference 곡선·σ 튜닝 부담↑. (a)가 더 단순·robust → (a) 채택, (c)는 fallback.

### 3-2. ★ 정확한 공식 (구현 — `rewards.py`에 신규 함수 1개)

per foot i, 매 스텝:
```
frac_i   = Fz_toe_i / (Fz_foot_i + Fz_toe_i + eps)          # forefoot CoP 분율 [0,1]
tau_n_i  = clamp(current_contact_time_i / T_stance, 0, 1)    # 정규화 stance phase [0,1]
gate_i   = (in_contact_i) & (other_foot_swing) & (v_fwd>0)   # single-support·전진 (late_gate는 tau_n가 흡수)
r_i      = tau_n_i * frac_i * gate_i                         # τ↑(late) AND forefoot↑ 일 때만 보상
R        = sum_i r_i                                          # [num_envs], 대략 [0, 2]
```
- **핵심 = `tau_n * frac` 곱**: 초기 stance(τ_n 작음)엔 forefoot 분율이 커도 보상 작음 → **heel/mid부터 시작**하게 유도. 종말 stance(τ_n→1)엔 forefoot 분율이 커야 보상 큼 → **CoP가 앞으로 굴러야** 보상. = heel→toe **시간적 전진**을 직접 인코딩(Siekmann 위상게이트의 within-foot CoP 버전, clock 대신 contact-time).
- `T_stance`: 명령속도 의존. 보행 stance ≈ gait cycle의 60%([s-cop]), feet_air_time threshold 0.4s·관측 step time에서 **T_stance ≈ 0.30–0.40s**로 시작 → config-test에서 frac·τ_n 분포 보고 튜닝(τ_n이 항상 1로 saturate하면 T_stance↑).
- **`other_swing` 게이트 유지**(single-support): double-support 초기 heel-strike의 큰 frac을 배제(그땐 반대발도 접지 → CoP가 아직 뒤). 기존 `forefoot_cop` 게이트 재사용.
- eps=1e-3 (분모 0 방지, 기존 forefoot_cop과 동일).

### 3-3. weight
- **신규항 `cop_progression` weight = +1.0 ~ +1.5** (POSITIVE). 근거: v6에서 정적 `forefoot_cop@0.8`이 0.06%(+0.025)밖에 기여 못했으므로, **track_lin_vel(+0.74)·upright(+0.45)에 가려지지 않게** 충분히 키워야 함. 목표 기여 ≳ reward의 **3–5%**(≳ +1.3 절대값) — push-off·lateral_placement(+0.25)급. config-test에서 기여 측정해 1.0→1.5 조정.
- **기존 `forefoot_cop`은 weight 0.8→0.0(제거) 또는 0.2로 강등**: 같은 frac을 *정적*으로도 보상하면 신규항의 *시간적* gradient를 희석 → **제거 권장**(신규항이 frac을 이미 포함, τ_n=1 근방에서 forefoot_cop과 동치).
- **`ankle_pushoff`는 0.5 유지(↑금지)**: ankle_pitch 포화이므로 push-off weight를 더 올리면 over-drive. v7은 **CoP-progression이 주 레버**, push-off는 보조 엔진으로 현 수준 유지.

## 4. ★ ankle over-drive를 어떻게 피하나 (핵심 boundary)

1. **보상 대상이 ankle 토크가 아니라 *GRF 분율의 위치***. r은 Fz_toe/(Fz_foot+Fz_toe)와 contact-time만 본다 → 정책은 ankle plantarflexion을 더 쥐어짜는 대신 **CoP를 앞으로 굴리는 *자세*(heel-strike→roll, 발 pitch, hip extension으로 몸통 전진)** 로도 보상받을 수 있다. ankle은 한 경로일 뿐 유일 경로가 아님.
2. **`ankle_pushoff` weight 동결(0.5)**: ankle_pitch가 RS03(−60) 클립이므로 plantarflexion work 보상을 키우지 않는다. v7 신규항은 ankle 토크와 직접 결합하지 않으므로 ankle을 추가로 포화시키지 않는다.
3. **`torque_soft_limit_ankle`(ankle_roll-only, 커밋 5f2ca85) + ankle_pitch 포화 모니터**: §7 모터분석에서 ankle_pitch RMS/peak가 v6(26.5/−60클립) 대비 **악화되면 over-drive 신호** → T_stance·weight 하향.
4. **τ_n 게이트가 burst를 막음**: 보상이 late-stance에 집중 → 정책이 전 stance에 걸쳐 ankle을 진동시켜 farming할 수 없음(Siekmann/Duke 위상게이트 정신, reward interference 회피 [s-gaitcond]).

## 5. 검증 (진짜 rollover vs 위장 판별)

- **1차**: toe bend 13°→**25-35°**, toe moment 19→~30 N·m, forefoot fraction **stance 후반 ≳70%**.
- **★ CoP 전진거리**: toe hinge 앞 ~2-4cm → **5-9cm** (geometry: M=Fz·d, defl=M/k, k=60 — v6 정본 §3-1).
- **★ GRF 2차(toe-off) 피크 M자**: 단봉 → heel-strike + push-off 2-peak.
- **★ 위장 판별**: bend만↑인데 **CoP 전진·2차피크 없으면 정적 toe-curl 위장 → reject**. τ_n×frac 곱이 정적 curl을 구조적으로 배제하나(τ_n 작을 때 frac 보상 안 함), 측정으로 재확인.
- **★ ankle_pitch 포화 모니터**(§4-3): RMS/peak가 v6 대비 악화 = over-drive.
- **config-test**: 신규항 기여(목표 3-5%), frac·τ_n 분포(saturate 여부), error_vel 회귀 없는지.

## 6. References (verified)
- [Center of Pressure path during walking — CoP excursion **83% foot length** anteroposterior, heel→sole→forefoot, 속도 22-27 cm/s (e-arm 2923)](https://www.e-arm.org/journal/view.php?number=2923) — [s-cop] **시간적 CoP 전진의 생체역학 근거**(forefoot 분율 stance 후반 단조증가).
- [CoP progression characterizes dynamic foot function during walking (Collagen & Leather, Springer)](https://link.springer.com/article/10.1186/s42825-019-0016-6) — CoP 전진속도/궤적이 발 기능 지표.
- [Siekmann et al. 2021, Periodic Reward Composition (Cassie, arXiv:2011.01387)](https://arxiv.org/abs/2011.01387) ([ar5iv 전문](https://ar5iv.labs.arxiv.org/html/2011.01387)) — [s-siek] **위상게이트(clock으로 swing=force / stance=velocity)**. v7은 clock 대신 **contact-time**로 같은 위상게이트를 within-foot CoP에 적용. (단 Siekmann 자체엔 CoP항 없음 — [[34_cop_contact_rewards]] 검증대로 v7 CoP-progression은 *자체 합성*, 위상게이트 *구조*만 차용.)
- [Margolis & Agrawal, Walk These Ways (arXiv:2212.03238)](https://arxiv.org/abs/2212.03238) — desired-contact schedule(swing/stance 게이트), 곱셈합성 c_aux=0.02. contact-time-as-phase의 binary schedule 선례.
- [MIT footstep-constrained bipedal dynamic walking (arXiv:2203.07589)](https://arxiv.org/pdf/2203.07589) — footstep timing 제약 RL, clock 없이 contact 이벤트로 위상관리.
- [Duke Humanoid (arXiv:2409.19795)](https://arxiv.org/abs/2409.19795) — feet_air_time + **contact_pattern** 보상, passive-dynamics push-off, CoT −31~50%. heel/toe per-segment 접지 선례(우리는 heel body 부재로 2-seg CoP 분율로 근사).
- [Gait-Conditioned RL Multi-Phase Curriculum (arXiv:2505.20619)](https://arxiv.org/html/2505.20619v3) — [s-gaitcond] 명시적 Push-Off Dynamics 항 + **reward interference**(energy/torque가 push-off 상쇄) — late-gate로 회피.
- [Ankle plantarflex ~1.5 N·m/kg·power >2.5 W/kg (PMC4664043)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/) — push-off 진짜 동력원(ankle, RS03 포화 = 진짜 부하 → 크랭크 금지 근거).

> [!note] 솔직성 노트
> **verified**: v6 측정값(reward 기여표 — forefoot_cop +0.0251, ankle_pushoff +0.1038, 실험노트 §2b 직접인용); 센서 가용성(ContactSensorCfg track_air_time=True, history_length=3 — IsaacLab base grep); CoP 83% foot-length 전진(e-arm 논문); Siekmann/WTW/Duke/Gait-Conditioned reward 구조(공개논문). **추정**: 신규항 `cop_progression`의 weight(1.0-1.5)·T_stance(0.30-0.40s)·기여목표(3-5%)는 **config-test로 확정 필요**; "forefoot_cop 제거 vs 0.2 강등"은 설계판단; ankle over-drive 회피는 메커니즘 추론(측정으로 §7에서 확인). 후보(c) ZMP-tracking은 미구현 fallback.
