# reward 연구 — gaitfix_v7: TOE rollover(CoP anterior-progression) + base 완화(floor/deadband) + double-support 복원 (2026-06-22)

> 트리거: gaitfix_v6 = base 완화 + push-off 복원이 **방향은 맞으나 약함**. bob 1.19→1.46cm(+23%, 인간 ~2.5), 골반 roll/pitch swing **불변**(3.9/1.5°, 인간 ~7/4), toe moment 15→19 N·m(+25%, 인간 ~40 *비정규*), toe bend 11→13°(인간 25-35), ankle_pitch RMS 23→26.5(여전히 RS03 −60 클립), 낙상 1→2%.
> ★ 본 노트는 **2개 설계(토우 CoP-progression / base 완화) + adversarial 판정**을 합성한 **정본 v7 설계**다. 핵심 판정: base 완화는 *안전·hack·구현 모두 통과하나 **단독 시행은 null 보장*** → **생성 레버(temporal CoP-progression + double-support 복원)와 같은 run에 묶어야** v7로 출하 가능(GATE).
> 관련: [[2026-06-22_toe_rollover_cop_progression_gaitfix_v7]](토우 설계 정본), [[2026-06-22_12-30_toe_rollover_cop_progression_gaitfix_v6]], [[2026-06-22_13-30_gaitfix_v6_base_relax_pushoff]], [[2026-06-22_11-30_base_overconstrain_pelvis_swing_gaitfix_v6]], [[34_cop_contact_rewards]], [[23_toe_use_methods]].

---

## 1. 직전 결과 분석 (gaitfix_v6, [[experiments/2026-06-22_11-20-05_gaitfix_v6]])

| 양 | v5→v6 | 인간 | 판정 |
|---|---|---|---|
| vertical CoM bob | 1.19→1.46cm (+23%) | ~2.5cm | 완화 효과 **약함** |
| 골반 roll/pitch swing | 3.9/1.5° (**불변**) | ~7/4° | flat_orientation −0.5도 안 움직임 |
| toe moment | 15→19 N·m (+25%) | ~40(비정규)/6.7(51.8kg정규) | moment는 충분, **굴림 부재** |
| toe bend | 11→13° | 25-35° | ✗ **진짜 결손(여전)** |
| ankle_pitch RMS | 23→26.5 | — | RS03 peak −60 **클립=포화** |
| 낙상 | 1→2% | — | 안정 |

- **★ `forefoot_cop` 기여 = +0.0251 (reward 43.4의 0.06%)** — weight 0.8인데도 무시 가능. **정적 순간 분율은 heel→toe 시간 시퀀스를 못 만든다**는 가설을 측정이 직접 확증. (verified, 실험노트 §2b)
- **★ `ankle_pushoff` 기여 = +0.1038** — 0.5 복원했으나 ankle_pitch가 RS03(−60) 클립 → push-off를 **더 크랭크하면 over-drive**. 토우 수정은 ankle plantarflexion 강화가 아닌 **다른 레버**여야 함.
- **★ base 항들은 이미 near-inert**(verified, v6 보고 §): base_height **−0.0004**, flat_orientation_l2 **−0.0049**, lin_vel_z_l2 **−0.0046** = 지배항(track_lin_vel +0.74, upright +0.45)의 100-1000배 작음. → v6식 *균일 약화*(−1.0→−0.25 등 값만 낮춤)는 잘못된 축. **shape 수정(floor/deadband)** 이 옳다.
- 결론: base 완화·push-off 복원은 *directionally right but WEAK*. **CoP를 heel→toe로 *시간적으로* 전진시키는 전용 보상**(v6 HOLD)과 **step-to-step transition(double-support+heel-load)**이 빠져 있다.

## 2. 원인 (verified measurement 기반)

### 2-1. 토우 = 시간적 CoP-progression 부재 (★ 진짜 결손)
- 토우는 passive(k≈60 N·m/rad). toe bend = M/k = (Fz_toe·d_cop)/k. v6 geometry: CoP가 toe hinge 앞 **2-4cm에서 정체** → bend 13°. **5-9cm로 굴리면** ~30 N·m / ~30° (스프링·ankle 안 바꾸고). (verified, v6 정본 §3-1)
- 빠진 신호 = **forefoot 분율이 초기 stance엔 낮고 종말 stance엔 높아지는 시간적 ramp**. 정적 분율은 이를 못 만든다(§1 측정 확증). 생체역학: CoP는 stance 동안 heel→forefoot로 **foot-length의 ~83% 전진**(22-27 cm/s), forefoot 분율 stance 후반 단조증가 [s-cop].

### 2-2. base = −0.25도 vault 억제? → **아니오, gait-determined** (★ 진단 정정)
- v6.npz 분석(이동프레임 cmd_vx>0.2): **single-support 97-98% / double-support 2% / flight ~0%**(인간 ~80/20). M-vault = step-to-step transition(선행지 heel-strike collision + 후행지 push-off가 CoM을 위 single-support 호로 재지향, Adamczyk&Kuo / Kuo 2002)이 만든다. **double-support·heel-strike·passive-flat foot 부재** → transition 없음 → vault 없음. 측정: single-support 높이 82.19cm vs double-support 82.01cm = **M-shape 0.18cm**(인간 ~2.5).
- 골반 obliquity는 **이미 위상 정상**(L-single +0.25°, R-single −1.59°, 골반이 stance쪽으로 list) — **flat_orientation이 클램프한 게 아니라 약한 vault가 under-drive**. → 페널티 제거는 *허용적*일 뿐, vault를 *생성*하지 않는다.
- ∴ fixed-target base_height L2 = 잘못된 도구. IsaacLab G1/H1 reference는 **base_height 항 자체가 없고** flat_orientation_l2=−1.0, lin_vel_z=0/None(verified, 로컬 copy). vault 평탄화는 대사비용 +6%([Ortega&Farley]) → fixed-target는 metabolically wrong.

## 3. ★ 판정 + adversarial 검증 결과

| 설계 | 5축 검증(ankle over-drive·reward-hack·instability·interference·implementability) | 판정 |
|---|---|---|
| **A. 토우 CoP-progression** (forefoot-frac × contact-time ramp) | (구조적) ankle 토크 미결합, τ_n×frac 곱이 정적 toe-curl 배제, contact-time 센서 verified | ✅ **SURVIVES** |
| **B. base 완화** (base_height_floor margin 0.06 / flat_orientation_deadband 7°) | ankle 미접촉(corr≈−0.037), floor 0.79m 아래 0%프레임, deadband는 base orient만 봐 hack불가, 구현 API verified | ✅ **SURVIVES** — 단 **단독은 null** |

**★ adversarial 핵심 (B에 대한 GATE)**: v6 동작점에서 두 신규 base 항 모두 기여 **정확히 0.0**(floor 아래 0%, 7° 밖 0%) → bob/roll을 인간목표로 **구조적으로 못 움직임**. ∴ **B를 단독 v7으로 출하 = v6 flat 결과 재현(낭비 iteration)**. **수정(fix) = B를 그대로 유지하되 생성 레버와 같은 run에 묶는다**:
1. **A** = temporal CoP-progression (heel→toe 굴림 *생성*).
2. **double-support / heel-loading 인센티브 신설** = step-to-step transition 복원(2%→목표 15-20% double-support) → **vault를 *기계적으로* 만든다**(B가 허용한 공간을 채움).
3. **ankle_pushoff 0.5 동결**(↑금지) — ankle_pitch 이미 −60 클립.

→ **출하 v7 = A + B + double-support, ankle 동결**. (B 단독·A 단독 모두 불출하)

## 4. 제안 gaitfix_v7 (검증 통과 구체안)

### 4-A. 토우 CoP-progression (신규 `cop_progression`, `rewards.py`)
per foot i, 매 스텝:
```
frac_i  = Fz_toe_i / (Fz_foot_i + Fz_toe_i + 1e-3)          # forefoot CoP 분율 [0,1]  (Fz=net_forces_w[...,2].abs())
tau_n_i = clamp(current_contact_time_i / T_stance, 0, 1)     # 정규화 stance phase [0,1]
gate_i  = in_contact_i & other_foot_swing & (root_lin_vel_b[:,0] > 0)   # single-support·전진
r_i     = tau_n_i * frac_i * gate_i                          # τ↑(late) AND forefoot↑ 일 때만
R       = sum_i r_i                                          # [num_envs], ~[0,2]
```
- **핵심 = `tau_n*frac` 곱**: 초기 stance(τ_n 작음)엔 forefoot 분율 커도 보상≈0 → heel/mid부터. 종말 stance(τ_n→1)엔 forefoot 분율 커야 보상 큼 → CoP가 앞으로 **굴러야** 보상. = heel→toe 시간적 전진 직접 인코딩(clock 대신 contact-time = phase proxy, heel body 대신 2-seg 분율).
- params: `T_stance=0.35`(시작, config-test 0.30-0.40 튜닝), `contact_thresh=8.0`, `eps=1e-3`. `current_contact_time` = ContactSensorCfg(track_air_time=True, history_length=3) verified, `forefoot_cop`/`feet_air_time`가 이미 try/except fallback로 사용 중.
- **weight `+1.2`** (POSITIVE; 목표 기여 ~3-5% = track 가림 회피, lateral_placement +0.3·push-off급). config-test 기여 측정해 1.0→1.5.
- **`forefoot_cop` weight 0.8 → 0.0(제거)**: 같은 frac의 *정적* 버전 → 신규항의 *시간적* gradient 희석(v6 +0.0251=0.06%로 무용 확증). (정적 anchor 원하면 0.2.)
- 후보비교: (b) toe FLEXION late-gate = |τ_toe|=k·defl로 정적 curl hack → **기각**(`toe_load_stance` 폐기 안티패턴); (c) ZMP-식 frac*(τ) tracking = sharp하나 reference·σ 튜닝부담 → **fallback**.

### 4-B. base 완화 (그대로 유지, `velocity_env_cfg.py` __post_init__ L274-277 교체)
```python
# (1) base_height: fixed-target L2 제거 → collapse FLOOR (G1/H1식, vault 자유)
self.rewards.base_height.weight = -0.5
self.rewards.base_height.func   = pyg_rewards.base_height_floor   # 신규
self.rewards.base_height.params = {"target_height": TARGET_BASE_HEIGHT, "margin": 0.06}
# (2) flat_orientation: ±7° deadband (밴드 안 0, 밖 −1.0 강한 slope)
self.rewards.flat_orientation_l2.func   = pyg_rewards.flat_orientation_deadband  # 신규
self.rewards.flat_orientation_l2.weight = -1.0
self.rewards.flat_orientation_l2.params = {"deadband": 0.122}     # sin7°≈0.122
# (3) lin_vel_z_l2: -0.05 유지(bounce guard; near-inert)
```
신규 `rewards.py` 함수(IsaacLab API verified: base_height_l2→root_pos_w[:,2], flat_orientation_l2→projected_gravity_b[:,:2]):
```python
def base_height_floor(env, target_height, margin=0.06, asset_cfg=SceneEntityCfg("robot")):
    h = env.scene[asset_cfg.name].data.root_pos_w[:, 2]
    sag = (target_height - margin - h).clamp(min=0.0)   # (target−6cm) 위는 0, collapse만 grow
    return sag * sag                                    # NEG weight

def flat_orientation_deadband(env, deadband=0.122, asset_cfg=SceneEntityCfg("robot")):
    pg = env.scene[asset_cfg.name].data.projected_gravity_b[:, :2]  # [pitch-tilt, roll-tilt]
    over = (torch.norm(pg, dim=1) - deadband).clamp(min=0.0)
    return over * over                                  # 밴드(±7°) 안 0, 밖 square; NEG weight
```
- **margin=0.06 근거**(verified v6.npz): 이동중 평균 높이 **82.19cm = 목표 85cm보다 2.8cm 아래** → 2.5cm deadband는 동작점을 재페널티(tracker 부활). **6cm**라야 동작밴드+up-vault 자유, 실제 ~79cm collapse만 포획. weight −0.5 = breach 시 stiff barrier.
- **deadband 0.122 근거**: projected-gravity xy 크기 ≈ sin(tilt), sin7°=0.122 → pitch+roll 합 7° cone까지 페널티 0. v6 "tilt 불변" 원인 = slope만 −1.0→−0.5로 줄여 이미 작은 gradient 거의 안 변함; **deadband는 shape를 바꿔 밴드 안 압력 정확히 0**. 밖은 −1.0(v6 −0.5보다 강함) → 안전 net MORE restrictive.

### 4-C. double-support / heel-loading 복원 (★ adversarial fix가 추가한 생성 레버)
- **문제**: B가 vault를 *허용*해도 single-support 98%면 골반이 bob할 **기계적 이유가 없다**. step-to-step transition 부재가 병목(double-support 2%, 인간 ~20%).
- **신설**: brief 양발 동시접지에 **소형 POSITIVE 보상**(목표 double-support ~15-20%) + 선행지 loading-rate 항. 구현은 `forefoot_cop`/`ankle_pushoff_work`가 쓰는 contact 게이트 재사용(`net_forces_w` 양발 in_contact AND 직전 swing→접지 전이). weight는 작게 시작(예 +0.1), config-test에서 double-support 분율 보며 튜닝. **과하면 발 끌기/double-support 과다 위험** → 분율 상한 게이트(>20%면 보상 0).
- ※ 이 항은 adversarial verdict가 명시 요구(없으면 골반이 bob할 이유 없음). 정밀 formula는 config-test 1차 후 확정(현재 *추정*).

### 4-D. 동결/유지 (held)
- `ankle_pushoff` **0.5 동결(↑금지)** — ankle_pitch RS03 −60 클립. v7 신규항 어느 것도 ankle 토크와 직접 결합 안 함.
- `foot_roll_flat` roll-only(v6), `lateral_foot_placement` +0.3, `base_height` floor화 외 dof_torques HIP_KNEE-only(ankle/toe 면제) 유지.

## 5. ankle over-drive 방지 (★ 명시)
1. **보상 대상 = ankle 토크가 아니라 GRF 분율의 *위치***(Fz_toe/(Fz_foot+Fz_toe)) + contact-time. 정책은 ankle 쥐어짜기 대신 **CoP를 자세로 굴려**(heel-strike→roll, 발 pitch, hip-extension 몸통전진) 보상 가능. ankle은 한 경로일 뿐. (검증: corr(|base_pitch|,|ankle_pitch τ|)≈−0.037, 골반 자유가 ankle 부하 안 함.)
2. **`ankle_pushoff` 0.5 동결** + **double-support는 ankle push-off가 아닌 transition으로 토우 굴림**.
3. **§7 모터분석 모니터**: ankle_pitch RMS/peak가 v6(26.5/−60클립) 대비 **악화 = over-drive 신호** → T_stance↑ 또는 cop_progression weight↓.
4. **τ_n late-gate가 burst farming 차단**(Siekmann/Duke 위상게이트 정신, reward interference 회피).

## 6. 검증법 (진짜 rollover·vault vs 위장)
- **토우**: bend 13°→**25-35°**, moment 19→~30 N·m, forefoot fraction stance 후반 **≳70%**, **CoP 전진 2-4cm→5-9cm**.
- **★ GRF M자 2차(toe-off) 피크**: 단봉→heel-strike+push-off 2-peak. **bend만↑인데 CoP 전진·2차피크 없으면 정적 toe-curl 위장 → reject**.
- **vault/골반**: bob 1.46→**~2.5cm**, double-support 2%→**15-20%**, 골반 roll swing 3.9°→**7-11°**(위상은 이미 정상). M-shape 0.18cm→**~2.5cm**.
- **ankle over-drive**: ankle_pitch RMS/peak ≤ v6.
- **안정성**: 낙상 ≤ 3-4%(>4%면 deadband 0.122→0.087=5°).
- **모니터 가드**: 평균 base_height < 80cm → margin 0.06→0.04. cop_progression 기여 ≥3% 확인. error_vel 회귀·frac/τ_n 분포(saturate면 T_stance↑).

## 7. References (verified·hyperlinked)
- [CoP path during walking — CoP excursion **83% foot-length**, heel→forefoot, 22-27 cm/s (e-arm 2923)](https://www.e-arm.org/journal/view.php?number=2923) — [s-cop] 시간적 CoP 전진 생체역학 근거.
- [CoP progression characterizes dynamic foot function (Springer)](https://link.springer.com/article/10.1186/s42825-019-0016-6) — CoP 전진속도/궤적=발 기능 지표.
- [Siekmann et al. 2021 Periodic Reward Composition, Cassie (arXiv:2011.01387)](https://arxiv.org/abs/2011.01387) — [s-siek] 위상게이트(clock); v7은 contact-time로 within-foot CoP에 적용(CoP항 자체는 *자체 합성*).
- [MIT footstep-constrained bipedal walking (arXiv:2203.07589)](https://arxiv.org/pdf/2203.07589) — clock 없이 contact-event 위상관리.
- [Duke Humanoid (arXiv:2409.19795)](https://arxiv.org/abs/2409.19795) — feet_air_time + contact_pattern, passive push-off, CoT −31~50%; heel/toe per-seg(우린 heel body 부재→2-seg 근사).
- [Gait-Conditioned RL Multi-Phase (arXiv:2505.20619)](https://arxiv.org/html/2505.20619v3) — [s-gaitcond] push-off항 + reward interference(late-gate로 회피).
- [Ankle plantarflex ~1.5 N·m/kg, power >2.5 W/kg (PMC4664043)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/) — push-off 동력원=ankle(RS03 포화 = 크랭크 금지 근거).
- [IsaacLab G1 rough_env_cfg (G1: lin_vel_z=0, flat_orientation=−1.0, NO base_height)](https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/g1/rough_env_cfg.py) — 로컬 copy 대조 verified. [H1 동형](https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/h1/rough_env_cfg.py).
- [Ortega & Farley 2005, CoM vertical 평탄화 = 대사 +6% (J Appl Physiol)](https://journals.physiology.org/doi/full/10.1152/japplphysiol.00103.2005) — fixed-target height = metabolically wrong.
- [Adamczyk & Kuo step-to-step transition (PMC2726857)](https://pmc.ncbi.nlm.nih.gov/articles/PMC2726857/) · [Kuo et al. 2002 (PMID 12409498)](https://pubmed.ncbi.nlm.nih.gov/12409498/) — heel-strike collision + push-off가 vault 생성(98% single-support flat foot엔 부재) = §2-2·4-C 근거.

> [!note] 솔직성 노트
> **verified**: v6 기여표(forefoot_cop +0.0251, ankle_pushoff +0.1038, base_height −0.0004, flat_orientation −0.0049, lin_vel_z −0.0046 — 실험노트 직접인용); v6.npz 측정(평균높이 82.19cm, single/double 97-98%/2%, M-shape 0.18cm, 골반 위상-정상, ankle_pitch RMS 26.7/max~58.7); 센서(ContactSensorCfg track_air_time=True history_length=3); IsaacLab base reward API(base_height_l2→root_pos_w[:,2], flat_orientation_l2→projected_gravity_b[:,:2] — 로컬 grep); G1/H1 reward 구조; CoP 83% 전진(e-arm). adversarial 검증: B 5축 통과 + B-단독-null(밴드/floor 0% 프레임).
> **추정/config-test 확정 필요**: cop_progression weight(1.0-1.5)·T_stance(0.30-0.40s)·기여목표(3-5%); double-support 항(4-C)의 정밀 formula·weight(+0.1 시작)·목표분율(15-20%) — verdict가 *요구*했으나 구체 formula는 1차 config-test 후 확정; "forefoot_cop 제거 vs 0.2"·"margin 0.06 vs 0.04"는 설계판단; ankle over-drive 회피는 메커니즘 추론(§7 측정 확인). 후보(c) ZMP-tracking 미구현 fallback.
> **adversarial 결론**: A·B 모두 survives. B-단독은 null → **A+B+double-support 묶음 단일 run으로만 출하**, ankle 동결.
