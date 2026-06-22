# reward 연구 — 발-edge / ankle_roll 과부하: gaitfix_v4 (2026-06-22 03:50)

> 트리거: gaitfix_v3 결과(발 바깥날 보행 20→18deg만 미미 감소, ankle_roll RS00 14Nm 포화 잔존: peak 100%, RMS ~110% 연속 = 열과부하).
> 바꾸려는 reward: `foot_roll_flat`(ankle_roll 관절각² 페널티)를 더 키울지 / 다른 항(발-body orientation, stance-width, hip-roll 균형)으로 바꿀지.
> 관련: [[40_foot_edge_ankle_roll]](같은 주제 docs 노트), [[34_cop_contact_rewards]], [[37_ankle_linkage_fidelity]], [[36_all_actuator_tn_envelopes]](RS00 봉투), [[28_reward_actuator_fidelity]].

---

## 1. 직전 결과 분석 (gaitfix_v3)

- **지표/측정**: ankle_roll 입각기 편향 ~18deg(이전 20deg) — `foot_roll_flat`(−0.5)+`forefoot_cop`(0.8) 추가에도 **거의 안 움직임**. RS00(연속 14Nm, datasheet 연속 5Nm 기준) **RMS ~110%·peak 100% = 열과부하 잔존**. 무릎(`knee_straight` −5.0)·toe(`forefoot_cop`)는 크게 개선.
- **현재 코드 실측**(verified, 파일·라인):
  - `foot_roll_flat` = `sum(q_ankle_roll²)` — **관절각** 페널티, weight **−0.5** (`rewards.py:193-201`, `velocity_env_cfg.py:235-237`).
  - `feet_lateral_separation` = `relu(min_lat − gap_y)`, **min_lat 0.14**, weight −3.0 (`rewards.py:179-190`, `velocity_env_cfg.py:232-234`) → **하한(floor)일 뿐 목표(target) 아님**. gap이 0.14를 넘으면 보상 0 → 더 넓힐 유인 없음.
  - `feet_distance`(IsaacLab 기본) min_dist 0.20, weight −3.0 (`velocity_env_cfg.py:230-231`) → 유클리드 간격, 횡방향 아님.
  - `forefoot_cop` 0.8 (전후 CoP=toe 적재용; **측방 CoP와 무관**).
  - **stance-width target 없음**, **hip-roll 측방균형 항 없음**, **발-body orientation 항 없음**.
- **→ 관측된 문제**: ankle_roll 각만 직접 누르는데 18deg에서 **정체** = "페널티 vs 무언가의 needs"가 평형. 그 needs가 무엇인지가 핵심.

## 2. 이전 이력

- [[40_foot_edge_ankle_roll]]: 이미 같은 결론(원인=stance-width, 증상=측방밸런스를 ankle로 푸는 것)을 생체역학+RL로 정리. 본 노트는 그 docs 노트를 **reward_research 규칙(변경 전 연구)** 형식으로 확정 + v4 구체안.
- [[28_reward_actuator_fidelity]] / `joint_overrating_penalty`(`rewards.py:96-111`): ankle_roll을 *연속정격 대비* 과부하로 직접 식별하는 thermal hinge 항이 이미 코드에 존재(아직 미배선). v4에서 활용 후보.
- ankle_pushoff_work(직접 push-off)는 **ankle 포화/torque-limit 자기충돌** 부작용으로 de-emphasize(0.1)된 이력(`flat_env_cfg.py:95`) → "ankle을 직접 더 시키는" 방향은 이미 한 번 실패. **ankle 부담을 빼는** 방향이 맞음.

## 3. 학술/자료조사 (검증 vs 추정 구분)

> 생체역학 3편은 본문 직접대조(**verified**). RL 식·가중치는 공개된 것만 verbatim 인용, 그 외는 식 형태만 표준에서 보강(**추정 표시**).

- **ankle inv/ev = 측방 CoP의 주(主) 수단, 단 CoP 이동량은 발폭에 상한**: "the lateral ankle mechanism … main means of modulating the CoP under the stance foot during sustained locomotion … the magnitude of CoP modulation is **constrained to the width of the foot**." → ankle_roll CoP 권한의 천장이 **발폭**. (verified) ([Reimann 2019, PLOS One][r1])
- **foot placement(step width)=측방밸런스 primary, ankle=보조·보정**: "ankle moment control **complements** foot placement … corrective CoP shift **once the foot has been placed**." (verified) ([van Leeuwen 2021, Sci.Rep.][r2])
- **ankle inv/ev 미세조정 = 대사비용**: step-to-step inv/ev 보정으로 균형 노력 **6–15%↓** → 포화 ankle은 *비효율적* 균형수단의 직접 증거. (verified) ([Antonellis 2017, Front.NeuroRobot.][r3])
- **RL: flat을 각² hard-penalty 대신 body-orientation으로** — IsaacLab `flat_orientation_l2 = sum(square(projected_gravity_b[:, :2]))`(base 표준, Go1 −2.5 / ANYmal-D −5.0). legged_gym `_reward_orientation` 동식. (식·base 가중치 verified; **발 link로 포팅하는 건 우리 적용=추정**) ([IsaacLab rewards][i1], [Go1 cfg][i2], [legged_gym][lg])
- **발은 base와 분리해서, 작은 가중치로** — Booster Gym: base ‖g‖² **−5.0**, **feet roll ‖φ_feet‖² −0.1**, feet yaw **−1.0**. feet-roll 가중치를 **일부러 작게(−0.1)** 둔다 = roll이 load-bearing이라 과페널티는 해롭다는 설계의도. SoFTA 동일 구조. (가중치 verified) ([Booster Gym][bg], [SoFTA][sf])
- **stance-width / feet-separation을 정식 보상항으로** — DBHL(narrow-terrain) Table I에 **Feet Separation·Feet Edge Distance·ZMP(Eq.7)** 명시. Unitree config도 feet 간격/clearance. (**항목명 verified, verbatim 식·가중치 미공개=추정**) ([DBHL arXiv:2502.17219][db], [unitree_rl_gym][un])
- **sole 다점 거리분산형 flat(더 날카로운 edge 페널티)** — 발바닥 N점의 지면거리 분산을 페널티. (형태 verified) ([narrow-terrain humanoid arXiv:2502.17219][db])

## 4. 원인·문제 규명 (4지선다 판정)

| 가설 | 판정 | 근거 |
|---|---|---|
| (a) 보상 아티팩트(exploit) | **부분기각** | −0.5 페널티 줬는데 18deg 정체 → 단순 "페널티 없어서"는 아님. *페널티 약함*은 맞으나 1차원인 아님. |
| (b) 측방밸런스 진짜 needs | **참(증상)** | ankle inv/ev = 측방 CoP 주수단. 막기만 하면 밸런스 깨짐. |
| **(c) stance-width / foot-placement** | **참(근본원인)** | step width가 측방밸런스 primary. width 부족→CoM이 지지발 위 안 옴→CoP를 발끝(=ankle_roll 포화)까지. **여길 고쳐야 demand 자체↓.** 우리 `feet_lateral_separation`은 **floor(0.14)일 뿐 target 아님** → width를 넓힐 유인 부재. |
| (d) 발 기하학(평발·발폭) | **2차** | ankle CoP 이동은 발폭에 상한 → 발 좁으면 같은 측방모멘트에 edge로 더 빨리. *천장*만 정함, *원인* 아님. |

**핵심 인과사슬**: narrow/floor-only stance → CoM 측방으로 지지선 밖 → 측방밸런스 위해 CoP 외측 → ankle_roll이 발 바깥날까지 inversion → roll 포화 + 실제 접지가 edge.
**왜 v3가 안 통했나(두 겹)**: ① 측정량이 틀림 — `foot_roll_flat`은 **관절각**을 누르지 발-vs-지면 기울기를 누르지 않음(base lean/hip-roll/지형이 같은 관절각에서 실제 접지각을 바꿈). ② 원인(stance) 미해결 — 각을 더 눌러도 정책은 밸런스 needs와 평형(18deg)에서 멈추거나 회피.

## 5. ★ 위험: 발을 평탄 강제하면 측방균형을 해치나? — **예, 단독이면 해친다**

- ankle inv/ev는 측방 CoP의 *기능적 주수단*([r1]) → ankle_roll 각을 직접 더 누르면 **측방밸런스 핸들을 제거**. 대체핸들(step width / lateral placement / hip-roll)을 **먼저** 안 주면 → (i)밸런스 reward 손해로 정체, (ii)힙/무릎으로 비정상 회피, (iii)학습붕괴. 우리 18deg 정체가 (i)의 신호.
- **그래서 roll 페널티는 작게(−0.1~−0.5) 유지**가 SOTA 합의(Booster −0.1, SoFTA −0.1). **단독 증량은 명시적 안티패턴.**
- 올바른 순서 = **원인부터**: width/hip-roll로 ankle demand의 *원인*을 제거 → 그 뒤 flat orientation은 *낮아진* demand 마무리(작은 가중치로도 듣는다).

## 6. 제안 (gaitfix_v4 — 구체 변경·weight·왜)

**원칙: "foot_roll_flat↑" 단독은 하지 않는다. 원인(stance-width + hip-roll 균형)을 먼저 주고, flat은 관절각→발-body orientation으로 교체(약하게).** 우선순위 순.

1. ★ **[1순위, 원인] stance-width TARGET 추가** — `feet_lateral_separation`을 floor가 아니라 **목표 횡간격**으로. 현재 `relu(min_lat−gap)`(0.14 넘으면 0)을 양측 hinge `relu(|gap_y − w*| − band)` 형으로 바꾸거나, **target 항을 신설**(예 w*≈0.22~0.26m, 51.8kg 하체 골반폭+α; 넓→좁 커리큘럼). weight ~−1.0. *왜*: 측방 CoP 권한을 **더 넓은 base**에서 얻어 ankle_roll이 풀어야 할 측방모멘트 자체를 줄임([r1] CoP는 발폭 상한 / [r2] placement가 primary). **이게 RMS를 떨어뜨리는 핵심 레버.** (적용=추정, 생체역학 근거=verified)

2. ★ **[1순위, 원인] hip_roll 측방균형 경로** — hip-roll 기본 자세를 약간 외전(abduction)으로 주거나(legs slightly abducted), hip-roll deviation 페널티를 **완화**해 hip이 측방하중을 분담하게. 대상 관절 `.*_hip_roll_joint`(존재 확인됨, `velocity_env_cfg.py:91`). *왜*: 측방밸런스를 ankle 대신 hip이 나눠 → ankle_roll 부담 offload.

3. **[2순위] `foot_roll_flat`(관절각²) → 발-BODY orientation 보상으로 교체** — `_foot_link`의 projected-gravity xy(=발 sole normal vs world up)를 페널티: 발 quaternion으로 `g_foot = quat_rotate_inverse(foot_quat_w, gravity_vec)` 후 `sum(g_foot[:, :2]²)`. (IsaacLab `flat_orientation_l2`를 **발 link로 포팅**; `body_quat_w` 사용 — `projected_gravity_b`는 base 전용이라 발용은 직접 계산.) **weight −0.2~−0.5(작게)**. *왜*: 관절각이 아니라 **실제 접지 평탄도**(base/hip 자세 불변)를 측정 → v3가 틀린 측정량을 고침. 가중치는 1·2 적용 *후* 재튜닝. (식 verified, 발-포팅=추정)
   - 대안/보강: sole 다점 지면거리 분산형(edge-contact를 더 날카롭게 직접 페널티, [db]).

4. **[3순위, 폴리시] edge stomping 억제 + 발내 CoP centering** — 이미 있는 `foot_impact_force`/`foot_landing_vel`로 edge 충격 억제, 그리고 **1·2가 stance를 확보한 뒤** 발 안 측방 CoP를 중앙으로(ZMP/CoP-centering, [db] Eq.7) 미세조정.

5. **[측정/HW 연계] `joint_overrating_penalty` 배선 고려** — ankle_roll을 연속정격(5Nm) 대비 hinge로 직접 누르되 *load-balancing*으로 hip/knee로 떠넘김([[28_reward_actuator_fidelity]]). 단 이는 *증상* 항이므로 1·2 다음. HW: **발폭/접지패치**가 ankle CoP 권한의 천장 → sizing 변수([[37_ankle_linkage_fidelity]], [[36_all_actuator_tn_envelopes]] RS00 봉투).

### 검증 방법 (ankle_roll demand가 실제로 떨어지나)
- **1차 지표**: ankle_roll 입각기 편향각(목표 <8deg), RS00 RMS%연속정격(목표 <100%), peak%peak.
- **§7 모터 활용 리포트** 재실행 → ankle_roll RMS/p95/peak 포화 해소 확인. 영상 클로즈업 audit으로 발바닥 전면접지 육안 확인.
- **stance-width 측정**: 입각기 발간 횡간격(y)이 target(≈0.22~0.26m)으로 올라갔는지.
- ★ **판별 실험(아티팩트 vs HW under-spec)**: 넓은 flat stance가 확보됐는데도 ankle_roll이 여전히 포화면 → **RS00 14Nm가 진짜 부족**(reward 튜닝이 아니라 stance geometry/linkage/모터 사이즈가 답). 떨어지면 → gait 아티팩트였음이 입증. 이 분기가 본 변경의 핵심 산출물.

## 7. References

- [Reimann, Fettrow, Jeka (2018/2019), PLOS One — balance mechanisms / ankle CoP는 발폭 상한][r1]
- [van Leeuwen et al. (2021), Sci.Rep. — ankle inv/ev↔측방 CoP, placement 보정][r2]
- [Antonellis et al. (2017), Front.NeuroRobot. — inv/ev 미세조정 대사비 6–15%↓][r3]
- [IsaacLab mdp/rewards.py — flat_orientation_l2 = sum(square(projected_gravity_b[:, :2]))][i1]
- [IsaacLab Go1 flat cfg — flat_orientation_l2 weight −2.5 (ANYmal-D −5.0)][i2]
- [legged_gym legged_robot.py — _reward_orientation][lg]
- [Booster Gym (arXiv:2506.15132) — base ‖g‖² −5.0, feet roll −0.1, feet yaw −1.0][bg]
- [SoFTA (LeCAR) — 동일 orientation 구조][sf]
- [DBHL narrow-terrain (arXiv:2502.17219) — Feet Separation·Feet Edge Distance·ZMP][db]
- [unitree_rl_gym — feet 간격/clearance gait 항][un]

[r1]: https://jekalab.org/wp-content/uploads/2018/02/Reimann-Fettrow-Jeka_2018.pdf
[r2]: https://www.nature.com/articles/s41598-021-00463-8
[r3]: https://www.frontiersin.org/journals/neurorobotics/articles/10.3389/fnbot.2017.00062/full
[i1]: https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab/isaaclab/envs/mdp/rewards.py
[i2]: https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/go1/flat_env_cfg.py
[lg]: https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot.py
[bg]: https://arxiv.org/html/2506.15132v1
[sf]: https://lecar-lab.github.io/SoFTA/resources/Main-Paper.pdf
[db]: https://arxiv.org/html/2502.17219v2
[un]: https://github.com/unitreerobotics/unitree_rl_gym

> [!note] 솔직성 노트 (verified vs 추정)
> **verified**: 생체역학 3편(본문 직접대조); IsaacLab `flat_orientation_l2`/legged_gym `_reward_orientation` **식**과 base 가중치(Go1 −2.5, ANYmal −5.0); Booster/SoFTA feet-roll **−0.1** 가중치; DBHL Feet Separation·Feet Edge Distance·ZMP **항목명**; 우리 코드 실측(파일·라인·weight). **추정**: base orientation 식을 *발 link로 포팅*하는 적용; stance-width target의 구체 수치(≈0.22~0.26m, w=커리큘럼)와 가중치; DBHL의 verbatim 식·가중치(미공개). "flat 단독 증량 안티패턴"은 생체역학(ankle=측방 주수단)+우리 18deg 정체 관측의 추론(단일 논문 직접주장 아님).
