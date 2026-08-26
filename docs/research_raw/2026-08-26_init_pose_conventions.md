# 원자료 — 휴머노이드 RL 기본자세(무릎 굴곡) 컨벤션 전수조사 (2026-08-26, Sonnet 서브에이전트)

부호 규약(13개 설정 공통): **hip_pitch 음수 = 전방 굴곡**, **knee 양수 = 굴곡**, **ankle_pitch 음수 = 배측굴곡**.

## 로봇별 기본자세 · 액션 오프셋 · pose 보상
| 로봇 / 코드베이스 | hip_pitch | **knee** | ankle_pitch | 초기 높이 | 액션 = 기본 + scale·a | 무릎/힙피치를 잡는 pose 항 |
|---|---|---|---|---|---|---|
| XBot-L (humanoid-gym) | 0° | **0°** | 0° | 0.95 (타깃 0.89) | ✔ scale 0.25 | `default_joint_pos` w 0.5지만 실질은 yaw/roll만 |
| **G1** (unitree_rl_gym) | −5.7° | **17.2°** | −11.5° | 0.80 (타깃 0.78) | ✔ scale 0.25 | 없음(hip_pos는 roll/yaw만), **base_height w −10** |
| G1 29dof (IsaacLab) | −5.7° | 17.2° | −11.5° | 0.75 | ✔ `use_default_offset` scale 0.5 | `joint_deviation_hip`(yaw/roll만) |
| **Booster T1** | −11.5° | **22.9°** | −14.3° | 0.72 (타깃 0.68) | ✔ scale 1.0 | 관절 pose 항 **없음**, **base_height w −20** |
| G1 (IsaacLab `G1_CFG`) | −11.5° | 24.1° | −13.2° | 0.74 | ✔ | 〃 |
| Fourier N1 | −14.0° | 29.5° | −13.7° | 0.70 | ✔ | 미확인 |
| ★ **우리 (Pygmalion bent)** | **−18.3°** | **−38.4°(굴곡 38.4°)** | +20.6° | 0.83 | ✔ scale 0.25 | `pose` σ_knee **1.2 rad** = 사실상 없음 |
| **mjlab G1 `KNEES_BENT_KEYFRAME`** | −17.9° | **38.3°** | −20.8° | 0.76 | ✔ | `variable_posture` σ_walking knee 0.35 |
| H1 (IsaacLab) | −16.0° | **45.3°** | −29.8° | 1.05 | ✔ | `joint_deviation_hip`(yaw/roll만) |
| H1 (HumanoidVerse) | −22.9° | 45.8° | −22.9° | — | ✔ | 미확인 |
| **Berkeley Humanoid** | −26.5° | **56.3°** | −20.0° | 0.515 | ✔ scale 0.5 | `joint_deviation_knee` w **−0.01**(매우 약함), 힙피치 0 |
| Cassie / Digit (IsaacLab) | — | 폐쇄 4절이라 직접 비교 불가 | — | 0.9 / 1.05 | ✔ | 시상면 힙·무릎 **제외** |
| ToddlerBot | 5.2° | 21.8° | 16.6° | — | home_pos 상속 | 미확인 |

## 판정 3가지
1. **`use_default_offset=True`(또는 legged_gym의 `target = scale·a + default`)는 13/13 예외 없음.**
   → "기본자세 = 액션 원점"은 표준이고, 문제는 *어떤* 기본자세인가다.
2. **두 군집으로 갈린다**: 곧은 쪽(0–30°: XBot-L·G1·T1·N1) vs 깊은 크라우치(38–56°: **우리**·mjlab G1·H1·Berkeley).
   ★ **우리 −38.4°는 mjlab의 G1 `KNEES_BENT_KEYFRAME`(38.3°)을 그대로 물려받은 값**이고, 같은 파일의 미사용 `HOME_KEYFRAME`이 legged_gym G1 값(17.2°)이다.
   → 제안한 **−20°는 곧은 쪽 군집(G1 17–24°, T1 22.9°)의 한복판**이다. 임의값이 아니다.
3. ★ **mjlab에는 `base_height` 보상이 아예 없다.** legged_gym 계열은 전부 있고 **G1 −10 / T1 −20**으로 무겁다.
   초기자세와 별개로 높이를 잡아주는 항이 없다는 구조적 차이 → [[62_policy_reward_design_review]] 미절제 ⑥ 확인.
   ⇒ 내가 넣은 `base_height_deadband` w −5.0은 **필드 표준 대비 약하다**. 상향 근거.

## 그 밖에
- **IsaacLab 공식 설정(G1·H1·Digit·Cassie)은 시상면 힙·무릎을 pose 정규화에서 제외**한다(hip_roll/yaw·팔·몸통만). 무릎 각도는 추종·토크·air_time 보상으로만 간접 결정된다 — crouch가 흔한 이유.
- 초기 높이 vs `base_height_target`: 전부 타깃이 초기보다 **2.5–6.3 % 낮다**(G1 0.80→0.78, T1 0.72→0.68, XBot-L 0.95→0.89). 이유를 주석으로 밝힌 레포는 없었다.
- **arXiv:2505.20619**: *"RL은 안정적으로 걷지만 결과가 과도하게 crouch하거나 에너지 비효율적"* → **"straight knee" 보상 w 0.1** 신설. 단 수식·타깃각·전후 수치 미공개.
- van Marum 2404.19173(Digit)은 crouch가 아니라 **제자리 hopping**이 문제였고 base_height(w 0.05)+단발접촉으로 해결. crouch 출처로 인용하면 안 됨.
- ⚠ crouch의 인과(“base_height 없음 → crouch”)를 **수치로 격리한 논문·이슈는 찾지 못했다**. 필드의 작업가설로 취급할 것.

## 인간 기준 (Perry & Burnfield 2010 / Winter — **2차·합의값**, 원표 직접 인용 아님)
| 국면 | 무릎 굴곡(0°=완전신전) |
|---|---|
| 접지(0 %) | **0–5°** |
| 로딩(0–10 %) | 15–20° |
| 중간입각(10–30 %) | 0–5° |
| 전유각/toe-off(50–60 %) | 35–40° |
| 스윙 피크(70–73 %) | **60–70°** |
⚠ 우리 `refs/human_gait/camargo2021`(1.20 m/s 실측)에서 무릎각을 직접 뽑는 게 더 정확하다 — `analyze_tm.py`에 `knee_angle_r`만 넣으면 되나 `matio` 파서 미설치로 미완. **후속 과제**.

## 출처
unitree_rl_gym `legged_gym/envs/g1/g1_config.py` · IsaacLab `isaaclab_assets/robots/{unitree,cassie,agility}.py` + `locomotion/velocity/config/{g1,h1,digit,cassie}/rough_env_cfg.py` · booster_gym `envs/T1.yaml` · humanoid-gym `humanoid/envs/custom/humanoid_config.py` · Wiki-GRx-Gym `legged_gym/envs/n1/n1_config.py` · HumanoidVerse `config/robot/{h1,g1}/*.yaml` · isaac_berkeley_humanoid `assets/berkeley_humanoid.py` · toddlerbot `descriptions/default.yml` · mjlab `asset_zoo/robots/unitree_g1/g1_constants.py` · arXiv:2505.20619 · arXiv:2404.19173
