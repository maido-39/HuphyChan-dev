# reward 연구 — toe가 안 굴리는 진짜 원인(CoP 전진 부재, 스프링은 적정) + heel→toe 롤오버/발바닥 사용 gaitfix_v6 (2026-06-22 12:30)

> 트리거: **gaitfix_v4** toe 측정 — forefoot Fz max ~340N(67%BW)·forefoot load fraction mean 20–45%/max 100%가 **나오는데도** toe joint torque ~15 N·m·굴곡 max 5–11°(mean −1°)뿐. 사용자: "발/토우의 **발바닥(plantar surface)**을 heel→mid→forefoot→toe로 **굴려서(rollover)** 쓰게 하라. 지금은 안 굴고 옆날(edge)로 걷는다."
> 바꾸려는 reward: `forefoot_cop`(0.8) 단독 → **CoP 전진(temporal heel→toe) + late-stance push-off + foot-pitch(sagittal) 항**으로 보강. toe spring k는 **건드리지 않음**(판정 §3).
> 관련: [[reward_research/2026-06-22_toe_moment_rollover_plantar_surface]](선행 toe-moment geometry 노트 — 본 노트가 *gaitfix_v6 실행계획*으로 확정·확장), [[reward_research/2026-06-22_11-00_ankle_roll_peak_gaitfix_v5_or_hw]](edge/ankle_roll = frontal-plane, 전제조건), [[reward_research/2026-06-22_03-50_foot_edge_ankle_roll_gaitfix_v4]], [[34_cop_contact_rewards]], [[23_toe_use_methods]], [[15_toe_joint_research]], [[12_toe_stiffness]], [[22_energy_toe_reward]].

---

## 1. 직전 결과 분석 (gaitfix_v4)

| 양 | gaitfix_v4 측정 | 인간(질량정규화, 51.8kg 환산) | 판정 |
|---|---|---|---|
| forefoot **Fz** max | ~340 N (67%BW) | push-off Fz ~1.1×BW ≈ 560 N | 수직하중은 *들어오지만* push-off 정점엔 못 미침 |
| forefoot load **fraction** | mean 20–45% / max 100% | terminal stance엔 forefoot로 거의 전부 | 평균이 낮음 = **종말기에만 잠깐 forefoot, 지속 rollover 아님** |
| toe joint **torque** | ~15 N·m | MTP ~0.13 N·m/kg → **~6.7 N·m** | ✅ 이미 인간 MTP의 **2배+** — moment 결손 아님 |
| toe **굴곡각** | max 5–11° (mean **−1°**) | 일반 MTP ~30°, 1st-MTP 50–60° | ✗ **굴림 자체가 없음 — 진짜 결손** |

- **영상 audit / 측정**: 발이 mid-foot에서 pivot하고 심하면 **lateral edge**로 접지(ankle_roll 포화 — gaitfix_v5 별건). heel-strike→foot-flat→heel-off→toe-off의 **시간적 시퀀스가 없다**. CoP가 toe hinge 앞으로 전진하지 않아 짧은 lever에서 멈춤.
- **현재 코드**(verified, `flat_env_cfg.py` `BipedFlatForefootEnvCfg`):
  - `forefoot_cop` **weight 0.8** (L79–83) — forefoot(toe_link) GRF fraction을 **terminal single support에 게이트**해 보상. 단 **위치/분율 기반 *순간* 보상**이지 *시간적 heel→toe 순서*를 안 만든다.
  - `ankle_pushoff`(ankle_PITCH positive work) **weight 0.1 — DE-EMPHASIZED** (L94–98; 사유 주석: ankle 포화/torque-limit self-conflict). = **롤오버 엔진이 꺼져 있음**.
  - `power_cot` 0.4, `foot_landing_vel` −1.0, `foot_impact_force` −0.005. `dof_torques_l2` −2e-6(HIP_KNEE만, toe/ankle 제외, L36). `feet_air_time` 0.75/threshold 0.4.
  - `forefoot_cop` func 자체 docstring(`rewards.py:68–93`): forefoot **fraction**을 (접지 ∧ 반대발 swing ∧ 전진 ∧ `current_contact_time>0.15`)에 게이트. **heel-body 추적 없음**(아래 §4 한계).
- **→ 관측된 문제**: 수직하중·forefoot fraction은 게이트가 잡는데, **CoP를 toe hinge 앞 5–9cm까지 *전진*시키는 시간적 롤오버가 없다.** moment 15 N·m·굴곡 5–11°는 CoP가 hinge 앞 ~2–4cm에서 멈춘 mid/forefoot pivot 상태와 정확히 정합.

## 2. 이전 이력

- [[reward_research/2026-06-22_toe_moment_rollover_plantar_surface]]: 본건의 **선행 원인분석**(geometry + mass-normalize). 그 노트가 "스프링 무르게 ✗, rollover로 충분"을 확정. 본 노트는 거기서 한 발 더 나아가 **gaitfix_v6 실행 reward 설계**로 구체화.
- `forefoot_cop@0.5` 단독 → H-A **실패**(코드 주석 `flat_env_cfg.py:90`: "gated GRF-fraction too weak, ~0.02% of reward"). 0.5→0.8로 키워도 *순간 분율*이라 시퀀스가 안 생김.
- `ankle_pushoff_work` scale 0.1·no-cap → **reward-HACK**(reward 324, error_vel 1.56; `rewards.py:128–129`). 이후 scale 0.02·cap 80·late-gate로 안전화, 그러나 self-conflict 우려로 **weight 0.1까지 de-emphasize**(엔진 사실상 OFF). = "ankle을 직접 더 시키는" 방향은 한 번 데였음 → **gaitfix_v5(edge/self-conflict) 해소 후에만 복원**해야 함.
- `toe_load_stance`(직접 |tau_toe| 보상)는 **안티패턴으로 폐기**(`rewards.py:42–65, 73–78`): |tau_toe|=k·deflection이라 **정적 toe-curl로 reward-hack** 가능, 게다가 toe가 over-damped라 curl이 쌈. → **직접 토크 보상으로 돌아가지 말 것.**

## 3. 원인 규명 + ★ 판정

### 3-1. 1차계산 (geometry, verified — robot.xml d=0.192m, k=60 N·m/rad)
toe moment M = forefoot_Fz × d_cop (d = CoP가 toe hinge 앞으로 나간 거리), 스프링 굴곡 = M/k.

| forefoot Fz | d (CoP 전진) | M | 굴곡 (k=60) |
|---|---|---|---|
| 340N (측정 max) | 2–4cm (현재) | **7–14 N·m** | **5–13°** ← *우리 현재 위치* |
| 340N | **8.8cm** | **30 N·m** | **28.6°** |
| 340N | 11.8cm | 40 N·m | 38° |
| 560N (1.1×BW) | 5.4cm | 30 N·m | 28.6° |

→ **CoP를 toe hinge 앞 ~5–9cm까지 굴려보내면, 스프링을 안 바꿔도 30 N·m·~30° 굴곡(=인간 일반 MTP)이 *그냥 나온다*.** 우리 측정(15 N·m·5–11°)은 CoP가 ~2–4cm에서 멈춘 mid-foot pivot과 정합.

### 3-2. 왜 `forefoot_cop`(0.8)이 진짜 롤오버를 못 만드나 (문헌 종합)
실제 heel→toe 롤오버는 **단일 CoP-위치 보상으로 거의 안 생긴다**(canonical failure mode). 필요한 4요소:
1. **(a) phase/clock 기반 *접지 시퀀스***(heel-strike→stance→toe-off를 시간에 강제) — Siekmann/Cassie periodic reward([s1]).
2. **(b) per-segment(heel vs toe) 접지 추적** — heel 초기·toe 종말을 각각 보상(Duke `contact_pattern`[s3], Mithra roll-over geometry[s7]).
3. **(c) push-off power/work 항**(롤오버의 *엔진*).
4. **(d) energy/torque 페널티를 작게** — 안 그러면 push-off가 눌려 사라짐("reward interference", Gait-Conditioned RL[s4]).

우리 결손: **(a) 시간적 순서 없음**(`forefoot_cop`은 *순간* 분율), **(b) heel body 없음**(`_foot_link`=plate+`_toe_link`만, 별도 heel link 부재 — §4 한계), **(c) 엔진(`ankle_pushoff`) weight 0.1로 OFF**. 즉 정책은 forefoot에 *서 있거나* 종말에만 잠깐 분율을 맞춰 보상을 받고, **heel-down→roll을 할 유인이 없다.** 게다가 push-off는 torque/action-rate 페널티에 눌릴 위험(reward interference) — 우리 `dof_torques_l2`는 다행히 HIP_KNEE만이라 ankle/toe는 제외(`flat_env_cfg.py:36`)이지만, `power_cot`(0.4)·`action_rate`·`dof_acc`가 push-off burst를 일부 상쇄할 수 있음.

### 3-3. mass-normalize 정정 (재확인, verified)
"인간 MTP push-off ~40 N·m"는 **무거운 성인 기준 + MTP를 발목 모멘트와 혼동**한 값. 51.8kg 환산: MTP **~6.7 N·m**(우리 15는 이미 초과), **진짜 push-off 동력원은 ankle_PITCH ~1.5 N·m/kg ≈ 78 N·m·power >2.5 W/kg ≈ 130 W**([s2]). → toe가 약한 게 아니라 **ankle_pitch 엔진과 CoP 전진이 약하다.**

### ★ 판정 (4지선다)

| 가설 | 판정 | 근거 |
|---|---|---|
| (a) **gait — CoP가 heel→toe로 전진 안 함** | **★ 주원인(참)** | forefoot fraction mean만 20–45%·CoP가 hinge 앞 2–4cm 정체. 시간적 시퀀스·push-off 엔진 부재. geometry상 CoP만 5–9cm 전진하면 30 N·m·30° 달성. |
| (b) 스프링 too stiff | **기각** | k=60 = mass-norm 인간 MTP ~56–60(Nature [s6])·docs/15 일치. moment는 이미 6.7(인간)→15(우리)로 *초과*인데 굴곡이 안 나옴 = 강성 문제 아님 = CoP/lever 문제. |
| (c) toe 적재(moment) 부족 | **기각** | toe moment 6.7(인간 mass-norm) 대비 우리 15 = 2배+. |
| (d) edge(ankle_roll) 때문 | **2차/전제조건** | edge면 sole 비접지 → 롤오버 물리적 불가. 그러나 edge를 고친다고 sagittal rollover가 *자동* 생기진 않음(단방향 약결합). gaitfix_v5와 **조합**. |

> **★ 스프링 강성 조정 검토(사용자 ③ 질문에 대한 답)**: "push-off moment가 인간보다 낮으니 k를 약간 낮춰 같은 하중에 더 굽게?" → **권장하지 않음.** (1) 우리 moment는 인간보다 *낮지 않고 높다*(15 vs mass-norm 6.7). (2) k↓(20–30)면 같은 작은 CoP·moment(7–14 N·m)에서 **굴곡 각만 부풀어** rollover처럼 *보이지만* 인과(forefoot 적재·push-off)는 그대로 = **증상 위장 안티패턴**. (3) sim2real 갭↑·수치불안정(docs/15: k=60이 armature 0.008과 함께 안정, 150→60으로 내린 이력). → **k=60 유지. 변경은 gait/reward 변경이지 스프링 변경이 아님**(reward-research 규칙 정신).

## 4. ★ 코드 한계 (gaitfix_v6 설계 전 반드시 인지) — heel body가 없다

- `robstride_biped.yaml:39` `foot: ".*_foot_link"` = **ankle-roll plate(heel+midfoot 일체)**, forefoot = `.*_toe_link`. **별도 heel 접지 body가 없음.**
- 따라서 문헌의 "heel body 초기 / toe body 종말" 4-접지 시퀀스 보상(Duke `contact_pattern`)을 **그대로는 못 쓴다**. 우리가 가진 2-segment(plate=heel+mid, toe=fore)로 근사하거나, **CoP 전진(anterior progression)**을 발 내부 GRF 분율의 *시간변화*로 직접 보상해야 함.
- **gait phase clock도 obs/MDP에 없음**(verified: `no_flight_phase`만, `feet_air_time`는 접지센서 air-time 기반). phase-gated 보상을 넣으려면 **clock 신호를 새로 추가**해야 함(비용↑). → v6는 **clock 불요(contact-time 게이트로 대체)**한 항을 우선 채택.

## 5. 제안 (gaitfix_v6 — 구체 reward·weight·왜). 우선순위 순.

> 원칙: ① **스프링 안 건드림**(§3). ② **CoP 전진(롤오버)을 *시간적*으로 보상**하되, heel-body·clock 부재를 우회. ③ **롤오버 엔진(ankle_pitch push-off) 복원** — 단 edge/self-conflict(gaitfix_v5) 해소가 *선결*. ④ energy/torque 페널티가 push-off를 죽이지 않게 관리.

**[순서 게이트]** gaitfix_v5(stance-width + foot-body orientation + `lateral_foot_placement` w0.3, 이미 wiring됨 `velocity_env_cfg.py:264–266)`로 **edge부터 해소** → sole 전면접지 확보(롤오버 전제조건). v6는 그 위에서.

1. ★ **[1순위·엔진] `ankle_pushoff` weight 0.1 → ~0.5 복원** (`flat_env_cfg.py:95,137`). *왜*: ankle_PITCH plantarflexor concentric work가 **CoP를 forefoot로 전진시키는 物理 엔진**("ankle push-off의 주기능 = forefoot rocker 보존", Perry [s5]). 현재 OFF여서 forefoot_cop(결과 보상)만으론 CoP가 안 간다. **단 self-conflict(ankle_roll 포화)가 gaitfix_v5로 해소된 *뒤*에만** 올린다 — `torque_soft_limit`가 ankle_roll-only로 분리됐으므로(커밋 5f2ca85) ankle_PITCH는 자유. scale 0.02·cap 80·late-gate 유지(reward-hack 방어). **config-test에서 reward 기여·error_vel 모니터.**
2. ★ **[1순위·시간적 롤오버] CoP anterior-progression 보상 신설** — `forefoot_cop`의 *순간 분율* 대신, stance 동안 **forefoot fraction이 시간에 따라 *증가*하는 것**을 보상(d(frac)/dt > 0 during stance, late-gate). 우리 2-segment로 충분히 구현 가능(heel body 불요): `frac_fore = Fz_toe/(Fz_foot+Fz_toe)`가 초기 낮음→종말 높음으로 *전진*하면 보상. *왜*: 이것이 `forefoot_cop`에 없는 **temporal heel→toe 순서**를 직접 만든다(canonical fix [s1][s3]). 대안: forefoot fraction의 reference-vs-phase 곡선 추종(`exp(-||frac-frac*(t)||)`, ZMP식 [s8]) — 단 phase clock 필요해 후순위.
   - 구현주의: clock 없이 `current_contact_time`(이미 `forefoot_cop`이 씀, `rewards.py:89`)을 phase 대용으로 — "접지 후 경과시간 클수록 forefoot fraction 높을 것"을 보상. **새 reward 함수 1개 추가**(`rewards.py`), config-test로 scale 튜닝.
3. **[2순위·sagittal foot-pitch] foot-pitch 롤오버 보상** — 착지 시 발끝 살짝 든 heel-first pitch + 종말기 heel-rise pitch를 보상. **foot-BODY projected-gravity의 *pitch* 성분**(이미 있는 `foot_flat_orientation`이 roll/pitch xy를 *둘 다* 누르는데, **pitch는 롤오버에 필요하므로 과페널티 금지**). *왜*: heel rocker→forefoot rocker의 발 자세 시퀀스. **각² hard 금지·exp 포화형**, weight 작게(−0.1~−0.3) — 균형/롤오버 해치지 않게(docs/40 교훈). ⚠️ 현 `foot_flat_orientation`(−0.3, `velocity_env_cfg.py:239`)이 **pitch까지 평탄 강제**하면 heel-rise를 막아 롤오버와 충돌할 수 있음 → **roll만 누르고 pitch는 풀거나**, weight 재튜닝 검토.
4. **[3순위·anti-slap 유지] `foot_landing_vel`(−1.0) 유지** — heel rocker의 eccentric controlled-lowering(slap 방지)에 대응. 그대로.
5. **[4순위·edge 억제] gaitfix_v5 항 유지·조합** — `foot_flat_orientation`(roll), `lateral_foot_placement`(0.3), stance-width. edge는 sagittal rollover의 *전제조건*.
6. **[관리] push-off가 안 눌리게** — `power_cot`(0.4)·`action_rate`(−0.01)·`dof_acc`(−3e-7)가 push-off burst를 상쇄하는지 reward 기여로 점검. 누르면 push-off 항이 reward의 충분 비중(≳수%)을 갖게 weight 조정(reward interference 회피 [s4]). `dof_torques_l2`는 이미 HIP_KNEE-only라 ankle/toe push-off는 페널티 면제(verified, OK).
7. **[선택·고급] sub-foot contact-sequence** — heel body가 없으므로 보류. 정 필요하면 robot.xml에 heel 접지 site/body 분리가 선행(비용↑). 현재는 #2(CoP progression)로 대체.

### 검증 방법 (롤오버가 *진짜* 생겼나 — 위장 판별 포함)
- **1차 지표**: toe 굴곡각 5–11° → **25–35°**, toe moment 15 → ~30 N·m, forefoot fraction mean↑(종말기 ≳70%).
- ★ **CoP 전진거리**: toe hinge 앞 CoP 진행 ~2–4cm → **5–9cm**(geometry §3-1로 굴곡각과 교차검증).
- ★ **GRF 2차(toe-off) 피크 출현**: 현재 단봉 → heel-strike + push-off **2-peak M자**가 나와야 진짜 rollover([s2] CoM redirection).
- ★ **위장(adversarial) 판별**([[23_toe_use_methods]]): 굴곡각만↑인데 **CoP 전진/GRF 2차피크가 없으면 = 정적 toe-curl 위장** → reject. (k를 안 내린 이유와 동일 논리.)
- **§7 모터 활용**: ankle_PITCH(RS03 60 N·m effort) push-off에서 binding 여부 — push-off 진짜 동력이라 RS03이 한계일 수 있음([s2] 78 N·m·130 W). edge 해소 후 ankle_roll(RS00) RMS/peak 동반 점검(gaitfix_v5 지표).
- 영상 클로즈업 audit: heel-strike→foot-flat→heel-off→toe-off 육안 시퀀스 + 발바닥 전면접지(edge 아님).

### HW 함의 (ULTIMATE PURPOSE = 하중측정)
- toe moment 타깃 = mass-norm **~6.7 N·m**(이미 초과) → **k=60 스프링 정당**(현 설계 OK).
- 진짜 push-off 부하 = **ankle_PITCH ~78 N·m·~130 W** → RS03 60 N·m effort가 push-off의 **binding actuator** 후보([[36_all_actuator_tn_envelopes]]). v6 후 측정값이 HW sizing 핵심 산출물.
- ⚠️ **순수 passive·non-coupled toe는 push-off power ~45%를 *소산***([s2-arch], PMC11211509): gait를 다 고쳐도 toe propulsion이 계속 낮으면 = **진짜 HW finding**(arch/windlass coupling 또는 약한 active toe 검토). 이건 reward로 못 고치는, *측정으로 드러날* 설계 트레이드오프.

## 6. References (verified vs 추정 명시)
- [Siekmann et al. 2021, *Periodic Reward Composition* (Cassie, clock/Von-Mises 접지스케줄)](https://arxiv.org/abs/2011.01387) — swing=force penalty / stance=velocity penalty 위상게이트. [s1]
- [Duke Humanoid 2024 (arXiv 2409.19795)](https://arxiv.org/abs/2409.19795) — Isaac-Gym reward 표(feet_air_time+contact_pattern), passive-dynamics push-off, CoT −31~50%. [s3]
- [Gait-Conditioned RL Multi-Phase Curriculum (arXiv 2505.20619)](https://arxiv.org/html/2505.20619v1) — 명시적 Push-Off Dynamics 항 + **reward interference**(energy/torque가 push-off 상쇄) + 항 routing. [s4]
- [JAEGER (arXiv 2505.06584)](https://arxiv.org/pdf/2505.06584) — feet_air_time(+), contact-force(−), torque(1e-4 tiny) 가중치. (torque 페널티 작게의 근거)
- [A unified perspective on ankle push-off (PMC5201006)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5201006/) — ankle push-off가 forefoot rocker 보존(Perry). [s5]
- [Biomechanics of Normal Gait — 4 rockers (AAPM&R)](https://now.aapmr.org/biomechanics-normal-gait/) — heel/ankle/forefoot/toe rocker 타이밍. [s5b]
- [Ankle plantarflex ~1.5 N·m/kg·power >2.5 W/kg (PMC4664043)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/) — push-off 진짜 동력원·CoM redirection. [s2]
- [MTP moment ~0.13 N·m/kg (4-seg foot model, PMC4101357)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4101357/) — toe moment 타깃 mass-norm. 
- [Toe joint stiffness 최적화 (Nature Sci Rep s41598-025-17957-4)](https://www.nature.com/articles/s41598-025-17957-4) — low-k가 rollover·high-k가 push-off, ~0.98–1.04 Nm/deg(=56–60 Nm/rad). k=60 인간일치 확인. [s6]
- [Mithra human-inspired feet (PMC12561541)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12561541/) — heel/toe roll-over 반경·arc(per-segment 접지 설계근거). [s7]
- [Toe joint neuromuscular sim (PMC11211509)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11211509/) — non-coupled passive toe가 push-off power ~45% 소산, MTP 35°(decoupled)/68°(arch). [s2-arch]
- [ZMP/CoP tracking reward r_zmp=exp(−||p−proj_ZML||/0.05) (arXiv 2502.17219)](https://arxiv.org/html/2502.17219v2) — CoP-vs-phase 추종형(대안 #2). [s8]
- [CoP excursion ~80–83% foot length (PMC4029865)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4029865/)

> [!note] 솔직성 노트 (verified vs 추정)
> **verified**: 생체역학 수치(MTP 0.13·ankle 1.5 N·m/kg·power 2.5 W/kg·MTP 30°/50–60°·rocker, 문헌 직접인용); Cassie/Duke/Gait-Conditioned reward 구조·"reward interference"(공개논문); 우리 코드 실측(파일·라인·weight: `forefoot_cop` 0.8, `ankle_pushoff` 0.1 DE-EMPHASIZED, `foot_flat_orientation` −0.3, `dof_torques_l2` HIP_KNEE-only, `lateral_foot_placement` 0.3 wiring됨, toe k=60); toe lever-arm geometry(robot.xml d=0.192m·k=60으로 M=Fz·d, defl=M/k 자체계산); **heel body 부재·gait clock 부재**(코드 grep으로 확인). **추정**: CoP-progression 신규항·foot-pitch 항의 구체 식·scale·weight(config-test 필요); `ankle_pushoff` 0.1→0.5 복원폭(self-conflict 해소 가정); "스프링 k 유지" 판정은 geometry+문헌+우리 측정의 추론(단일논문 직접주장 아님); sub-foot contact-sequence는 heel-body 분리 선행 필요(미구현).
