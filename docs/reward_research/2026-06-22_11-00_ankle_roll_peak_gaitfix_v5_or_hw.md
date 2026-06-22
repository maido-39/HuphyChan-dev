# reward 연구 — ankle_roll PEAK: gaitfix_v5(측방 foot-placement/hip-roll) vs RS00 under-spec(HW) 판정 (2026-06-22 11:00)

> 트리거: **gaitfix_v4**(stance 넓힘 0.20→0.24 *검증됨* + 발-body orientation 보상) 결과 — 지속 ankle_roll(RMS) **6.3→5.0(~20%↓)** 줄었으나 **PEAK 14 N·m(=RS00 peak 100%)·발-edge 19deg는 그대로**. 두 번째 gait-fix(v3 관절각 페널티에 이어)가 **peak을 못 움직임**.
> 바꾸려는 것: peak을 노리는 **gaitfix_v5 reward(측방 foot-placement / hip-roll offload / lin_vel_y 커리큘럼)** *또는* reward가 아니라 **HW 상향(RS00→DM-J4340 / 2-RSU 병렬 / 링크 relocate)** 결정.
> 관련: [[40_foot_edge_ankle_roll]], [[reward_research/2026-06-22_03-50_foot_edge_ankle_roll_gaitfix_v4]](직전 v4안), [[39_ankle_qdd_uptorque_survey]](RS00 대체 후보), [[38_parallel_ankle_sim2real]](2-모터 병렬), [[37_ankle_linkage_fidelity]](relocate 링크), [[36_all_actuator_tn_envelopes]](RS00 봉투), [[28_reward_actuator_fidelity]].

---

## 1. 직전 결과 분석 (gaitfix_v4)

| 지표 | gaitfix_v3 (관절각 페널티) | gaitfix_v4 (stance 넓힘+발-body orient) | 의미 |
|---|---|---|---|
| ankle_roll **PEAK** | 14 N·m = **100% RS00 peak** | 14 N·m = **여전히 100%** | ★ **안 움직임** |
| ankle_roll **RMS** | 5.5 N·m (~110% 연속 5) | 5.0 N·m (~101% 연속) | RMS 6.3→5.0 ~20%↓ |
| 발-edge 각 | 18deg | 19deg | **안 움직임** |
| stance width | (target 없음) | min_dist 0.20→0.24, **페널티 더 높은 target에도 줄었다=실제로 넓어짐(검증)** | stance 레버는 *작동* |

- **핵심 관측**: stance를 넓히는 레버는 **작동했다**(페널티가 더 높은 target에서도 떨어졌으니 정책이 실제로 발을 벌렸다 = verified). 그런데 그 효과가 **RMS(지속부하)에만** 나타나고 **PEAK·edge엔 0**. → "stance width"와 "peak ankle_roll"은 **서로 다른 물리 메커니즘**에 묶여 있다는 신호.
- **현재 코드**(verified, `velocity_env_cfg.py`): `feet_distance.min_dist=0.24`(L231), `feet_lateral_sep min_lat=0.18`(L234), `foot_roll_flat`→`foot_flat_orientation` 발-body normal(weight −0.3, L235-237), `torque_soft_limit_ankle` **ankle_roll-only, soft_ratio 0.80, w −0.01**(L126-130), command `lin_vel_y (−0.6,0.6)`(L257). **측방 foot-placement 항 없음. hip-roll offload 항 없음.**

## 2. 원인 규명 — 왜 stance는 RMS만 줄이고 PEAK은 못 줄였나 (frontal-plane 분해)

전두면(frontal) ankle_roll 수요는 **치료법이 다른 두 메커니즘**으로 분해된다:

- **(a) 정상상태 측방 CoP 센터링 (지속/RMS)**: gait cycle 동안 CoM을 지지면 위로 유지. stance를 넓히면 지지베이스가 측방으로 이동 → per-stance 측방 ankle 모멘트↓. **stance-width가 직접 듣는 부분.** 우리 데이터 정합: min_dist 0.20→0.24에서 RMS 6.3→5.0. (코드 주석 L231 "lateral CoP from a wide base"와 일치)
- **(b) step-to-step / 외란복구 transient (PEAK)**: 최대 측방 ankle 모멘트는 **heel-strike~초기 단일지지**에서 CoM 속도를 재정렬하고 측방오차를 잡을 때 발생. 생체역학 문헌은 **이 transient가 ankle의 일이 아니라고 만장일치** — 전두면 1차 교정자는 **발 placement(step width)**, 측방 ankle은 *즉각적이지만 곧 포화하는* 보조([van Leeuwen 2022][s4], [Reimann][s5], [PMC11371431][s1]). ankle CoP 이동은 **발폭에 상한** → stance를 넓혀도 *per-step peak* 권한은 안 커지고 **베이스만 이동**. 그래서 peak이 14 N·m(100%)에 못박히고 edge가 19deg에 남는다.

### ★ 물리적 바닥 (1차계산, verified) — 우리는 이미 거기 있다

측방 ankle 모멘트 = **Fz_vertical × 측방 CoP arm**, CoP는 **발 안에서만** 이동 가능.
- 단일지지: Fz = m·g = **51.8 × 9.81 = 508 N**.
- 관측 PEAK 14 N·m ⇒ CoP shift = 14 / 508 = **0.0276 m (~2.8 cm)** ⇒ 발 반폭 ~3–6 cm.
- = 정책이 CoP를 **발 끝(edge)**까지 몰고 있다 (독립적으로 **edge 19deg**가 교차검증). 이것은 **capture-point / XcoM 한계([Hof][s6])**: XcoM이 지지면을 벗어나면 ankle은 복구 **불가**, step이 필수.

→ **14 N·m는 이 질량에서 발이 전달할 수 있는 기하학적 천장에 사실상 도달**. ankle reward를 더 세게 눌러도 PEAK은 못 줄인다. PEAK을 줄이려면 **부하를 다른 곳(hip/step)으로 라우팅**하거나 **HW를 바꾼다(발폭↑ / 모터↑)**.

### RS00 14/5가 충분한가 — 1차계산 vs 실제 humanoid (verified)

3개 독립추정 수렴([인간 발목 inv/ev ~0.10 N·m/kg][s7], inv peak≈plantarflex peak의 13%[s8]):
- 정상 평발 보행(CoP 1–2 cm): **5–10 N·m** → RS00 14 peak는 *덮지만*, 연속 5에 대해 측정 RMS 5.0–5.7 = **100–114% = 직결(열경로 나쁨) 열적 under-spec**.
- 능동 측방밸런스/외란(CoP ~3 cm): **~15 N·m** → RS00 peak **바로 초과**.
- 발-edge 단일지지(CoP 4–5 cm): **20–25 N·m** = RS00 peak의 **1.5–1.8배**.

피어 비교(roll축, verified): 우리 14 N·m 직결 = **0.27 N·m/kg = 동급 최저**(가장 무거운데도). 가벼운 피어들은 **2-모터 병렬발목**(G1 ~50 N·m 공유, T1) 또는 **relocate+감속 링크**(X2 R57 30 N·m=1.07 N·m/kg, Berkeley 5013 9.7/4.6=0.61 N·m/kg)로 *더 큰 유효 roll 토크*를 산다. (출처 [[39_ankle_qdd_uptorque_survey]])

## 3. ★ 판정 — SPLIT (분할 결론)

| 부하 | 정체/아티팩트 | HW 바닥 | 결론 |
|---|---|---|---|
| **RMS (지속)** | ✅ gait 아티팩트, sim에서 *부분* 가능 | — | stance-width로 **이미 ~20% 회수**(6.3→5.0). 남은 ~1% 초과는 연속정격 5 자체가 빠듯(직결 열). |
| **PEAK (14 N·m)** | △ *아직 미시험 레버 1개 있음* | ⚠ mg×발반폭 물리바닥에 도달(508N×2.8cm=edge, 19deg 교차검증) | **ankle reward shaping으로는 불가.** *부하 라우팅*(foot-placement/hip)으로는 *가능성 잔존*. 그래도 안 떨어지면 = **진짜 HW 바닥 → RS00 under-spec.** |

**정직한 결론**: 데이터는 **"PEAK = 라우팅 미시험 + HW 의심 강함"**을 가리킨다.
- v3(관절각)·v4(stance+orient) **두 reward 레버가 peak을 0만큼 움직임** = peak이 ankle reward로 안 줄어든다는 강증거.
- 그러나 **아직 안 당겨본 *측방 전용* 레버**(foot-placement, hip-roll offload, lin_vel_y 커리큘럼)가 남아 있다 — 이들은 ankle을 *더 누르는* 게 아니라 **peak 수요를 ankle에서 *치우는*** 메커니즘이라 위 두 실패와 범주가 다르다.
- → **순서: (A) gaitfix_v5로 peak을 *라우팅* 시도 → 이 한 번이 아티팩트와 HW바닥을 깨끗이 분리하는 판별실험.** v5 후에도 peak이 14에 못박히면 **(B) HW 상향이 확정 답**. (양쪽 다 하되 A를 *먼저*, B를 *병행 준비*.)

## 4. 제안

### (A) gaitfix_v5 — PEAK을 노리는 reward (구체 항·weight·왜). *먼저 이것.*

원칙: **ankle_roll을 더 누르지 않는다(SOTA 안티패턴).** peak 수요를 **swing-leg placement와 hip-roll**로 *라우팅*한다.

1. ★ **[1순위] 측방 foot-placement 보상** — 전두면 peak의 *primary* 메커니즘([s1][s4][s5]). XcoM을 따라가는 목표 착지점을 추종해 **다음 step이 측방외란을 흡수**(stance ankle 대신). MIT footstep-RL 형식([s2], verbatim):
   - `r_step = (1_{r,contact} − 1_{l,contact}) · φ_contact · exp(−‖p̂ − p‖₂ / σ)`
   - 목표 `p̂_y = hip_y + k·(CoM_y + v_CoM_y/ω)`, `ω = √(g/l)` (Hof 고유진동수, [s6]).
   - weight: tracking 양(+), σ는 발폭 스케일(~0.05 m). **(b) transient를 직접 공격.** (식=verified, 우리 적용=추정)
2. ★ **[1순위] hip-roll(외전) 측방-밸런스 offload** — peak 측방모멘트를 **hip이 받게**(hip strategy, 스텝의 고대역 대안 [s3]).
   - 우리 hip-roll deviation 페널티 확인: `joint_deviation`이 `.*_hip_roll_joint` 포함(`velocity_env_cfg.py:91`) → **peak 순간 hip_roll을 다시 RS00로 떠미는 중일 수 있음**. 이 hip-roll 정규화를 **완화**(deviation 허용폭↑ 또는 weight↓).
   - ankle_roll soft-limit을 **hip-roll보다 *엄격*하게** 유지(현 `torque_soft_limit_ankle` soft_ratio 0.80, ankle_roll-only L126-130 그대로 두고, hip엔 같은 수준 페널티 *주지 않음*) → 옵티마이저가 peak 측방모멘트를 hip으로 라우팅.
3. **[2순위] lin_vel_y 커리큘럼 + 측방 push 램프** — `lin_vel_y (−0.6,0.6)`(L257)은 측방속도 명령으로 **peak 전두면 수요를 직접 생성**. y-명령 상한을 **초반 낮춰** 정책이 *스텝 기반* 측방밸런스를 먼저 배우게(안 그러면 PPO가 빠른 ankle을 greedy하게 써 RS00 포화). `command_vel_x` 커리큘럼(L141-144) 옆에 `command_vel_y` 램프 추가.
4. **[전제조건, 이미 있음] `foot_flat_orientation`(−0.3, L235-237) 유지** — sole 평탄 = 발 전폭을 CoP에 쓰는 전제. edge 19deg면 유효 반폭↓ → 필요 토크↑. 레버 1이 듣게 하는 *필요조건*.

**검증법 (아티팩트 vs HW를 깨끗이 가른다)**:
- 1차 지표: ankle_roll **PEAK %peak**(목표 <90% = <12.6 N·m), edge 각(목표 <12deg), 측방 step width 변조가 실제로 생겼는지(touchdown y 분산).
- **§7 모터 활용 리포트** 재실행 → ankle_roll RMS/p95/**peak** 포화 해소 확인 + 클로즈업 영상 audit(발 전면접지·스텝 측방교정 육안).
- ★ **판별**: v5 후 **peak이 <90%로 내려가면 = peak도 (라우팅 가능한) gait 아티팩트였음 입증** → reward로 마무리. **여전히 ~14(100%)에 못박히면 = 진짜 HW 바닥 → (B) 확정.**

### (B) HW 상향 — v5가 peak을 못 내리면 (근거·우선순위)

데이터(0.27 N·m/kg = 피어 최저, 20–25 N·m edge worst-case vs 14 peak, 연속 100–114%)는 **이미 HW 의심이 강하다**. v5 실패 시 즉시:

1. ★ **[최단경로] RS00 → DAMIAO DM-J4340-2EC** (27/9 N·m, 362 g, Φ57, $155). RS00(14/310g/$125)과 **거의 동일 외형**, peak **1.9×**·연속 **1.8×**, **디커플드 roll-직결 드롭인**(+52 g·+$30). edge worst-case 20–25 N·m을 peak이, 정상 5–10 N·m을 연속이 덮음. *주의*: **40:1 저속** → 로그된 roll-rate와 대조 필수(verified caveat). (출처 [[39_ankle_qdd_uptorque_survey]])
2. **[대안] 2-RSU(2-RSU/2-RSU03) 병렬발목** — G1/T1식, 차동으로 **유효 roll 토크 ~2×**. 단 2×2 운동학·sim2real 비용(캠프A: 정책 joint-space, Jᵀ는 SDK). (출처 [[38_parallel_ankle_sim2real]])
3. **[대안] roll relocate+감속 링크** — X2식, 공짜 감속 + distal 관성↓. 단 sim에 링크 구조하중 미반영(현재 직결 hinge 모델). (출처 [[37_ankle_linkage_fidelity]])
4. **[가장 싼 물리 레버] 발폭(mediolateral)↑** — peak 바닥 = mg×발반폭이므로 **발을 넓히면 바닥 자체가 올라감**(모터 안 바꾸고 천장↑). HW 설계 변수로 우선 검토 가치. (1차계산 verified)

**둘 다 할지**: **A를 먼저(1 run, 판별실험), B는 병행 준비**(DM-J4340 BOM·로드레이트 확인을 v5 학습 동안 진행). A가 성공해도 연속정격 5 vs RMS 5.0–5.7(직결 열)은 남으므로 **열 마진 관점에선 B(특히 옵션1)가 여전히 권장**.

## 5. References (verified vs 추정)

> [!note] 솔직성 노트
> **verified**: frontal-plane 분해 생체역학(foot-placement=primary, ankle=보조·포화, push-off=무관; ablation MoS ~20%↓)[s1][s3][s4][s5]; mg×발반폭 1차계산(508N×2.8cm=edge, 19deg 교차검증) 및 XcoM/capture-point 한계[s6]; 인간 ankle inv/ev ~0.10 N·m/kg·inv≈PF의 13%[s7][s8]; MIT footstep reward **식**[s2]; 우리 코드 실측(파일·라인·weight); 피어 roll-토크/DM-J4340 스펙([[39_ankle_qdd_uptorque_survey]]). **추정**: footstep/XcoM 식을 *우리 발·hip에 포팅*하는 적용·σ·k·weight; lin_vel_y 커리큘럼 램프 수치; hip-roll deviation 완화폭. **"PEAK은 ankle reward로 안 준다"**는 v3·v4 두 실패 관측 + 생체역학 + 1차계산의 **삼중 수렴 추론**(단일 논문 직접주장 아님).

- [s1] [Modelling strategies supplemental to foot placement (PMC11371431) — foot placement primary, ankle/trunk 보조, push-off 무관; ablation MoS ~20%↓](https://pmc.ncbi.nlm.nih.gov/articles/PMC11371431/)
- [s2] [MIT — Integrating Model-Based Footstep Planning with Model-Free RL (arXiv 2408.02662) — r=exp(−‖p̂−p‖/σ) + −max(|τ|−0.9τ_max,0)](https://arxiv.org/html/2408.02662v1)
- [s3] [Balance recovery after ML perturbations (PMC11687818) — hip add/abduction + step width, hip·foot placement primary](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11687818/)
- [s4] [External lateral stabilization reduces step-by-step ankle moment (J Biomech 2022) — ankle 모멘트의 밸런스 분획은 reroutable](https://www.sciencedirect.com/science/article/pii/S0021929022003001)
- [s5] [Altered active control of step width to ML perturbations (Sci.Rep. 2020) — step width/foot placement 전두면 dominant](https://www.nature.com/articles/s41598-020-69052-5)
- [s6] [Hof — Notes on the margin of stability (J Biomech) — XcoM, MoS, ankle CoP는 발폭 상한, ω=√(g/l)](https://www.sciencedirect.com/science/article/pii/S0021929024001222)
- [s7] [Human ankle inversion/eversion ~0.10 N·m/kg (PMC10434928)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10434928/)
- [s8] [Ankle inversion peak ≈ 13% of plantarflexion peak (PMC3791398)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3791398/)
- [DAMIAO DM-J4340-2EC 27/9 N·m (RS00 드롭인 후보)](https://aifitlab.com/products/damiao-dm-j4340-2ec-servo-motor) · 내부 [[39_ankle_qdd_uptorque_survey]]
- 내부: [[40_foot_edge_ankle_roll]] · [[38_parallel_ankle_sim2real]] · [[37_ankle_linkage_fidelity]] · [[36_all_actuator_tn_envelopes]]
