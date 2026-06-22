# reward 연구 — base reward 과구속: 골반 swing/push-off 억제 → gaitfix_v6 (토우 롤오버와 결합) (2026-06-22 11:30)

> 트리거: 측정 — base_link(골반) 수직 CoM 진동 std **~1.0cm (amp ~1.4cm) = 사람(~2.5cm amp)의 ~55%**. 토우(MTP) 거의 안 굽음(별도 finding, [[reward_research/2026-06-22_toe_moment_rollover_plantar_surface]]).
> 바꾸려는 reward: `base_height`(−1.0, 고정 target 0.85)·`flat_orientation_l2`(−1.0)·`lin_vel_z_l2`(−0.2)·`ang_vel_xy_l2`(−0.05)·`upright`(+0.5).
> 가설(user): 이들이 자연 골반 swing(fore-aft + up-down + tilt/rotation)과 push-off vault를 억제한다. ★ 핵심 결합 = **base_height 고정타겟이 vault의 CoM 상승을 막아 push-off·토우 롤오버를 동시에 억제**(별도 토우 finding과 같은 뿌리).
> 조사(web, 2 토픽 14+ sources, high confidence). 원문 [[raw/human-pelvis-com-kinematics]]. 선행 짧은 노트 [[reward_research/2026-06-22_10-35_base_rigid_pelvis_com_oscillation]]를 **확장**(필드표준 weight + 비대칭/deadband 식 + v6 구체안 + 로깅 상태정정).
> 목적: 사람다운·에너지효율·저충격 보행 + ★ **궁극목적 = HW 설계용 *현실적* 관절하중 측정**(비현실적으로 rigid한 골반은 비현실적 하중을 준다).

---

## 1. 직전 결과 분석

- **측정 (verified, npz 통계)**: base CoM 수직 진동 **std ~1.0cm / amp ~1.4cm** = 사람 preferred-speed amp(~2.5cm, 2.74±0.52cm slow)의 **~28–55%**. 토우(MTP) 거의 안 굽음(같이 묶임). → **rigid pelvis + flat toe**.
- **현재 코드 실측 (verified, 파일·라인·weight)** — `tasks/locomotion/velocity_env_cfg.py`:
  - `base_height` = `mdp.base_height_l2`, **weight −1.0**, `target_height=TARGET_BASE_HEIGHT=0.85`(L94-98). 구현 = `square(root_pos_w[:,2] − target)` — **고정 target L2, deadband·비대칭 없음** (`mdp/rewards.py:20-30`).
  - `upright` = `mdp.upright_posture`, **+0.5**, std 0.3 (L99-103). = `exp(−Σ projected_gravity_b[:,:2]² / std²)` — orientation 보너스(높이 항 아님).
  - `lin_vel_z_l2` **−0.2** (L220, flat_env_cfg.py:30에도 동일).
  - `ang_vel_xy_l2` **−0.05** (L221).
  - `flat_orientation_l2` **−1.0** (L222) = `Σ projected_gravity_b[:,:2]²` (base pitch/roll).
- **★ 로깅 상태 정정 (verified — 트리거의 "측정 못 함" 플래그는 *이미 해소*)**: 트리거는 "base orientation이 npz에 미기록 → measure.py에 추가 필요"라 했으나, **현재 `sensors/wrench_logger.py:82-90`가 이미 `base_roll/base_pitch/base_yaw`(euler, [-π,π] wrap) + `base_vx/vy/vz`(world lin_vel)를 매 스텝 기록**한다(`base_height`는 L73부터 기록 중). 즉 골반 tilt/obliquity/rotation·수직 bob 원자료는 *이미 잡힌다*. **남은 건 분석 쪽**: `scripts/analyze.py`가 이 컬럼에서 (i) base_vz/base_height의 **amp·std** (ii) base_pitch(tilt)·base_roll(obliquity)·base_yaw(rotation) **per-stride ROM** (iii) **M-shape**(midstance 최고 / DS 최저) 통계를 산출하도록 추가하면 됨. → ★ 권고를 "measure.py 로깅 추가"가 아니라 "**analyze.py에 골반-swing 통계 추가**"로 정정.
- → **관측된 문제**: `base_height_l2`가 *고정 목표높이*를 강제 → single-support vault의 CoM 상승(~2.5cm)을 페널티 → push-off과 직접 충돌. amp 55% + flat toe = **한 원인의 두 증상** 의심.

## 2. 이전 이력

- [[experiments/2026-06-21_15-40-30_forefoot_pushoff]] / [[experiments/2026-06-21_16-30-58_forefoot_pushoff2]] / forefoot_cop — 토우 rollover·push-off를 *직접* 보상(ankle_pushoff_work, forefoot_cop)으로 키우려 반복 시도했으나 토우 약함 잔존. **base reward와의 결합(base_height가 vault를 막아 push-off 억제)은 이때 미검토** = 이번 노트의 새 각도.
- ankle 자기충돌 교훈(`velocity_env_cfg.py:122-131`, [[reward_research/2026-06-22_03-50_foot_edge_ankle_roll_gaitfix_v4]]): ankle_PITCH(RS03, push-off prime mover) 토크를 4× 페널티하면 push-off과 싸운다 → offload를 ankle_ROLL-only로 좁혀 해결. **교훈 = "push-off의 적(antagonist) 항을 찾아 풀어라"** — base_height는 *또 다른* push-off antagonist(이번엔 CoM 상승 경로).
- gaitfix v3(관절각)·v4(stance+발-orient)·v5(측방 foot-placement/hip-roll)는 전부 **전두면(ankle_roll) frontal-plane** 문제. **본 v6는 시상면(sagittal) — vault·push-off·골반 bob** 으로 *독립 축*. 동시 적용 가능(서로 다른 항).

## 3. 학술/자료조사 (verified vs 추정 구분) — 원문 [[raw/human-pelvis-com-kinematics]]

> 사람 생체역학 수치·대사비용은 본문 직접대조(**verified**). 필드 RL config 가중치는 공개 repo verbatim(**verified**). "우리 base reward로의 귀속"·비대칭 식의 *우리 포팅*은 **추정**(재학습으로 확인).

### 3a. 사람 골반/CoM이 보이는, 우리가 누르고 있는 자연 운동량 (verified)
- **골반 ROM 3평면 (Lewis 2017, n=44 / PMC5545133)**: TILT(시상) 2–5° (mean 4.3°, biphasic ~2/stride); OBLIQUITY(전두 drop) 6–11° (mean 7.4°, 2/stride); ROTATION(횡) 3–14° (mean 9.5°, 1/stride). 여성 +1.9° obliquity·+2° rotation. [출처](https://pmc.ncbi.nlm.nih.gov/articles/PMC5545133/)
- **수직 CoM amp ~3–5cm**: 고전 Saunders/Inman canon ~5cm pk-pk; Gard 1998 3.0±0.4cm; Orendurff 2004 속도의존 **2.74±0.52cm(느림)→4.83±0.92cm(빠름)**. **M-shape**: CoM **최고=mid-single-support(vault apex)**, **최저=double-support**, 2 peaks/stride, PE↔KE 진자교환. ML amp ~5cm@1.4m/s, 3D "bow-tie" ~18cm/stride. [Orendurff](https://pubmed.ncbi.nlm.nih.gov/15685471/) · [Frontiers review](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2019.00999/full)
- **Six determinants = 상승은 *기능적*, 노이즈 아님**: 골반 rotation 8°→CoG −9.5mm, obliquity 5°→−3mm, stance knee 5°→peak↓. 이 항들은 M을 *납작하게* 하는 기구지만 결과는 여전히 3–5cm — **rigid가 아니라 "controlled rise"**. [podiapaedia](https://podiapaedia.org/wiki/biomechanics/gait/determinants-of-gait/)
- ★ **납작한 CoM은 *비싸다* (Ortega & Farley JAP 2005, PMID 15890757)**: CoM 수직운동을 *억지로 평탄화*(무릎 굽혀 CoM 고정)하면 CoM work는 줄어도 **순 대사비용 +~6%**(crouch 지지근력↑·진자교환 손실). 자연 vault가 대사 최적. → **고정-height 보상은 사람이 *피하는* 보행을 *강제*.** [출처](https://journals.physiology.org/doi/full/10.1152/japplphysiol.00103.2005)
- ★ **push-off ↔ CoM 상승 결합**: 후행 ankle push-off가 DS에서 CoM 속도 redirect, CoM 에너지변화 = push-off의 **86–96%** [Kuo transition](https://pmc.ncbi.nlm.nih.gov/articles/PMC2726857/). push-off **−50%**면 대사 **+~50%**, collision +0.6J/1J, 무릎이 stance work로 보상 [Huang/Kuo PMC4664043](https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/). late-stance push-off가 CoM을 *위·앞*으로 impulsive하게 밀어 다음 vault로 [Lipfert JEB 2014](https://journals.biologists.com/jeb/article/217/8/1218/). → **push-off가 곧 CoM을 들어올리는 일** = base_height 페널티가 push-off을 직접 처벌.

### 3b. 필드표준 base/torso reward — 고정 base_height_l2 target은 휴머노이드 안티패턴인가 (verified weights)
- ★ **IsaacLab 휴머노이드 자신의 config가 가장 직접 증거**:
  - **G1 rough**: `lin_vel_z_l2 = 0.0` (**비활성**), `flat_orientation_l2 = −1.0`, **base_height 항 없음**. [G1 cfg](https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/g1/rough_env_cfg.py)
  - **H1 rough**: `lin_vel_z_l2 = None`(**비활성**), `flat_orientation_l2 = −1.0`, **base_height 항 없음**. [H1 cfg](https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/h1/rough_env_cfg.py)
  - → **레퍼런스 휴머노이드는 의도적으로 lin_vel_z를 죽이고 base_height를 빼고**, orientation(−1.0)만 약하게 둔다. 우리 사례에 가장 직접적인 한 점.
- **legged_gym 기본**(우리가 상속한 베이스 계열): `lin_vel_z −2.0`, `ang_vel_xy −0.05`, **orientation −0.0(OFF)**, **base_height −0.0(OFF)** = 상위 기본은 둘 다 *끈* 채 출하, 사용자가 opt-in. `_reward_base_height`=순수 L2(deadband 없음). [legged_gym](https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot.py)
- **반례(의도적 stiff-torso, sim2real용)**: Unitree G1(unitree_rl_gym) `base_height −10`, `lin_vel_z −2`, orientation −1 → "다소 robotic/stiff bob"으로 알려짐 [unitree](https://github.com/unitreerobotics/unitree_rl_gym/blob/main/legged_gym/envs/g1/g1_config.py). Booster T1(arXiv 2506.15132 Table II) `base_height −20`, `‖g‖² −5`, `v_z² −2`, `ang_vel_xy −0.2` — 안정하나 일부러 stiff. → **stiff가 *틀린* 건 아니지만 우리 목적(사람다운·현실적 하중)과 반대.** [Booster](https://arxiv.org/html/2506.15132v1)
- **골반 motion을 *허용*하는 구체 대안 (식·weight)**:
  - **(A) DROP/비활성 (IsaacLab 휴머노이드 패턴)**: base_height 항 제거 + lin_vel_z→0, orientation −1.0만. 최저위험·필드검증. 안정은 orientation(−1.0)+termination-on-fall+feet/contact가 담당.
  - **(B) 비대칭 base-height (아래만 페널티)**: arXiv 2603.08619 "Embedding Classical Balance Control…": 상승은 *선형 보상*/무페널티, 하강만 *제곱 페널티* + stability band → vault 상승 허용, 붕괴 금지. 우리 실용포팅 = `base_height < (target − δ)`일 때만 페널티, 그 위는 0. [출처](https://arxiv.org/html/2603.08619v1)
  - **(C) deadband/tolerance**: `square(max(0, |h − target| − δ_h))`, **δ_h ~ 0.02–0.03 m**(=사람 ±bob) → ~2.5cm vault에 페널티 0.
  - **(D) motion imitation**(범위 밖, 참고): HumanPlus(AMASS mocap), GMP(arXiv 2503.09015: `lin_vel_z −0.8`*만*·`proj_gravity −6.0` + 동결 생성 prior) — 고정-height 항 없이 mocap에서 골반 dynamics를 *주입*. 우리는 prior가 없으므로 A/B/C가 적합.
- **안정 trade-off 안전범위 (verified)**: `flat_orientation`는 휴머노이드 합의 ~−1.0(G1/H1)~−5(Booster) — **유지·승급금지**(높이가 아니라 기울기 페널티라 bob을 안 막음, 값싼 안정기). `lin_vel_z` −2(stiff)~−0.8(GMP, prior 있어서)~0(IsaacLab 휴머노이드). `ang_vel_xy` −0.05가 보편값(legged_gym/unitree/IsaacLab) — 골반 tilt/rotation rate 허용. `base_height` = 범인; OFF(legged_gym/IsaacLab 휴머노이드)~−10/−20(stiff). **고정-target L2 형상이 우리 목적에 틀림.**

## 4. ★ 판정 — 골반 swing 억제 = reward 과구속이 맞나 (증거기반)

**맞다. base reward(특히 base_height_l2 고정타겟)가 자연 골반 swing·push-off을 과구속한다 — 삼중 수렴 증거:**

| 증거축 | 내용 | verified? |
|---|---|---|
| **(i) 우리 측정** | 수직 amp 1.4cm = 사람의 28–55%; 동시에 토우 flat. 두 증상이 같이 출현. | verified(npz) |
| **(ii) 생체역학** | 자연 vault 3–5cm는 *대사 최적*(평탄화 +6% cost, Ortega & Farley). push-off이 CoM을 들어올림(에너지 86–96% 결합) → **base_height 페널티 = push-off 페널티**. | verified(논문) |
| **(iii) 필드 RL** | IsaacLab G1·H1이 lin_vel_z를 죽이고 base_height를 *뺀다*. 고정-target L2 = 휴머노이드 안티패턴. | verified(repo) |

**어느 항이 무엇을 억제하나:**
- ★ **`base_height_l2`(−1.0, 고정 target 0.85) = 핵심 범인 (sagittal)**: single-support vault의 ~2.5cm CoM 상승을 페널티 → push-off이 CoM을 올리면 height 페널티↑ → policy가 **push-off·vault·골반 bob을 동시에 억제**. ankle_PITCH는 [[reward_research/2026-06-22_03-50_foot_edge_ankle_roll_gaitfix_v4]]에서 *토크 항*을 풀어줬지만, base_height가 *위쪽 CoM 경로*에서 같은 push-off을 여전히 막고 있다 = **토우가 안 굽는 잔여 원인**. (귀속=추정, 재학습으로 확인)
- **`lin_vel_z_l2`(−0.2)**: 수직 CoM 속도 = vault의 시간미분 → 진자운동을 직접 감쇠.
- **`flat_orientation_l2`(−1.0)·`ang_vel_xy_l2`(−0.05)**: base pitch/roll(=골반 tilt 4°·obliquity 7°)과 그 rate를 억제. (단 transverse rotation은 yaw라 직접 안 막음.)
- **`upright`(+0.5)**: orientation 보너스(높이 무관) → 낙상안전, *건드리지 않음*.
- **순효과**: 비현실적으로 rigid한 골반 → HW 설계용 관절하중이 비현실적(목적 위배). 사람은 3–5cm vault + 4–10° 골반 swing이 *정상이며 대사최적*.

**어느 항을 얼마나 완화하면 안정 유지하며 자연 모션 회복되나** (증거기반 안전범위):
- base_height: **OFF 또는 비대칭/deadband(δ≈0.025m)** — 안정은 orientation(−1.0)+termination+feet가 담당하므로 *load-bearing 아님*.
- lin_vel_z: **−0.2 → −0.05**(prior 없으니 0보다 약하게 유지해 bounce 방지).
- flat_orientation **−1.0 유지**(낮추면 낙상위험↑, 동시완화 금지). ang_vel_xy **−0.05 유지**.

## 5. 제안 — gaitfix_v6 (토우 롤오버와 결합)

> 원칙: **sagittal vault·push-off의 *적(antagonist)* 항을 푼다. base_height의 *형상*을 고쳐 상승을 허용하되 붕괴는 막는다. orientation은 안정기로 유지.** ankle gaitfix(v3–v5, 전두면)와 *독립 축*이라 병행 가능. 실험순서대로.

### (1순위) base_height — 형상 교체 `tasks/locomotion/velocity_env_cfg.py:94-98` + `mdp/rewards.py:20-30`
2단계로:
- ★ **(a) 먼저 시도 = IsaacLab 휴머노이드식 DROP**: `base_height.weight = −1.0 → 0`(또는 항 제거). 최저위험·필드검증(G1/H1). *왜*: 고정-target L2가 vault·push-off의 직접 antagonist. 안정은 `flat_orientation(−1.0)` + termination-on-fall + `feet_distance(−2.0)`/`no_flight(−0.5)`가 잡음.
- **(b) (a)에서 주저앉으면 = 비대칭/deadband 신규 mdp 보상**: `base_height_l2`를 `square(max(0, (target − δ) − h))` 류 **하한-only 페널티**(δ_h ≈ 0.025 m)로 교체. 상승·정상 bob은 페널티 0, target−δ 아래 붕괴만 처벌(arXiv 2603.08619 비대칭형 포팅). weight ~−0.5(붕괴 안전망). *왜*: squat-collapse 안전망을 유지하면서 up-bob은 자유.
- ★ **결합(토우/push-off)**: 이 항 완화가 **골반 bob *과* 토우 롤오버를 동시에 푸는 레버** — 고정-height가 vault와 ankle/toe push-off의 *공유 antagonist*였기 때문(ankle 자기충돌 노트와 일관). 토크 항(v4)만으론 부족했던 잔여 토우 약함이 여기서 풀릴 것으로 기대.

### (2순위) lin_vel_z_l2 `velocity_env_cfg.py:220` (+ `flat_env_cfg.py:30`)
- **−0.2 → −0.05** (또는 0). *왜*: 수직 CoM 속도(vault 미분)를 과감쇠. IsaacLab 휴머노이드=0, GMP=−0.8(강 prior). prior 없으니 **−0.05가 안전한 완화값**(완전 제거는 bounce 위험). **두 파일 다** 바꿔야 함(중복 정의).

### (유지) flat_orientation_l2 / ang_vel_xy / upright
- `flat_orientation_l2`(−1.0, L222) **유지** — 값싼 안정기, bob 안 막음. G1/H1과 일치. **base_height 완화와 *동시에* 낮추지 말 것**(낙상위험). 그래도 골반 tilt가 안 살아나면 *그 다음* run에서만 −0.7로 소폭 완화 시도.
- `ang_vel_xy_l2`(−0.05, L221) **유지**(보편값, tilt/rotation rate 허용).
- `upright`(+0.5, L99-103) **유지**(낙상안전, 높이 무관).

### (옵션, 범위 표시만) CoM 수직궤적/모션참조
- prior(AMASS/GMP) 도입은 큰 변경 → 본 v6 범위 밖. A/B/C(완화·비대칭)로 먼저 회복되는지 확인.

### 안정 안 깨지는 weight 범위 요약
| 항 | 현재 | v6 권고 | 안전범위(필드) | 비고 |
|---|---|---|---|---|
| base_height | −1.0 (L2 고정) | **0 (drop)** → squat 시 하한-only(δ0.025, ~−0.5) | OFF ~ −20 | 형상이 핵심, 값 아님 |
| lin_vel_z_l2 | −0.2 | **−0.05** | 0 ~ −2 | 두 파일 동시 |
| flat_orientation_l2 | −1.0 | **−1.0 유지** | −1 ~ −5 | 동시 완화 금지 |
| ang_vel_xy_l2 | −0.05 | **−0.05 유지** | −0.05 ~ −0.2 | 보편값 |
| upright | +0.5 | **+0.5 유지** | — | 낙상안전 |

### 검증법 (base reward가 진짜 범인인지 깨끗이 가른다)
- **1차 지표**: 재학습 후 base CoM 수직 **amp 1.4 → ~2.5cm 접근?** (목표 sanity **1.5–2.5cm**, **>4cm면 불안정 bounce** = 과완화). 
- **M-shape**: midstance(single-support) 최고 / double-support 최저, 2 peaks/stride 출현?
- **골반 ROM**(이미 로깅됨, §1): base_pitch(tilt) 2–5°, base_roll(obliquity) 6–11°, base_yaw(rotation) 3–14° 범위로 살아나나?
- **push-off/토우**: ankle plantarflex 토크↑ + 토우(MTP) 롤오버 출현? (sagittal §7 모터 활용 재확인)
- **낙상**: termination rate·episode length 악화 없나(완화로 인한 불안정 감시).
- ★ **판별**: 위가 나타나면 **base reward가 (토우와 공유된) 원인이었음 입증** → reward로 마무리. 안 나타나면 → 토우/ankle pitch push-off 항을 우선(이번 변경의 핵심 산출물 = 두 가설 분리).

### ★ 로깅 권고 (정정)
- 트리거의 "measure.py에 base euler/lin_vel 추가"는 **이미 `wrench_logger.py:82-90`에 구현됨**(base_roll/pitch/yaw + base_vx/vy/vz, base_height는 L73). **추가로 할 일은 `scripts/analyze.py`에 골반-swing 통계**(수직 bob amp/std, 골반 3평면 ROM, M-shape peak/trough 위상)를 **계산·플롯**하는 것. 플롯 **영문 라벨만**(한글=두부).

## 6. References (verified vs 추정)

> [!note] 솔직성 노트
> **verified**: 사람 골반 ROM(PMC5545133)·수직 CoM amp/M-shape(Orendurff/Gard/Frontiers)·six determinants·평탄화 +6% 대사(Ortega&Farley)·push-off↔CoM 86–96% 결합(Kuo)·−50% push-off +50% 대사(Huang/Kuo); IsaacLab G1/H1·legged_gym·unitree·Booster의 **공개 config 가중치 verbatim**; 비대칭 height 보상 식(2603.08619); 우리 코드 실측(파일·라인·weight)·**로깅이 이미 존재**(wrench_logger.py:82-90). **추정**: base reward → 우리 골반 억제로의 *귀속*(재학습으로 확인); 비대칭/deadband 식의 *우리 포팅*·δ_h=0.025·완화 weight 구체값; "base_height가 토우 억제의 공유 antagonist"는 생체역학(push-off↔CoM)+ankle 자기충돌 관측+우리 두 증상 동시출현의 **수렴 추론**(단일 논문 직접주장 아님).

- 사람 골반 ROM (n=44): https://pmc.ncbi.nlm.nih.gov/articles/PMC5545133/
- Orendurff 2004 수직 CoM vs 속도: https://pubmed.ncbi.nlm.nih.gov/15685471/
- Frontiers Neurol 2019 CoM 3D 궤적 리뷰: https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2019.00999/full
- Six determinants: https://podiapaedia.org/wiki/biomechanics/gait/determinants-of-gait/
- Ortega & Farley 2005 (평탄화 +6% 대사): https://journals.physiology.org/doi/full/10.1152/japplphysiol.00103.2005
- Kuo step-to-step transition (push-off↔CoM redirect): https://pmc.ncbi.nlm.nih.gov/articles/PMC2726857/
- Huang/Kuo (push-off −50% → 대사 +50%): https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/
- Lipfert JEB 2014 (impulsive push-off): https://journals.biologists.com/jeb/article/217/8/1218/
- IsaacLab G1 rough cfg: https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/g1/rough_env_cfg.py
- IsaacLab H1 rough cfg: https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/h1/rough_env_cfg.py
- legged_gym base reward: https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot.py
- unitree_rl_gym G1 config: https://github.com/unitreerobotics/unitree_rl_gym/blob/main/legged_gym/envs/g1/g1_config.py
- Booster Gym (arXiv 2506.15132): https://arxiv.org/html/2506.15132v1
- Natural Humanoid Locomotion w/ Generative Motion Prior (arXiv 2503.09015): https://arxiv.org/html/2503.09015v1
- HumanPlus HST (arXiv 2406.10454): https://arxiv.org/abs/2406.10454
- 비대칭 height 보상 (arXiv 2603.08619): https://arxiv.org/html/2603.08619v1
- 원문 발췌: [[raw/human-pelvis-com-kinematics]] · 선행: [[reward_research/2026-06-22_10-35_base_rigid_pelvis_com_oscillation]] · 결합: [[reward_research/2026-06-22_toe_moment_rollover_plantar_surface]] · ankle 자기충돌: [[reward_research/2026-06-22_03-50_foot_edge_ankle_roll_gaitfix_v4]]
