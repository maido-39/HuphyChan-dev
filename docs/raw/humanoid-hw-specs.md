# 휴머노이드 HW 스펙 — 검증 원문층 (워크플로우 wr1cz09bp, 2026-06-21)

> 출처: 워크플로우 wr1cz09bp가 공식 URDF/MJCF·논문·스펙시트 직접 fetch·검증. 링크별 절대질량·PD는 verbatim. wiki: [[31_humanoid_hw_comparison]].
> 규칙: 읽기만·수정 금지. wiki 수치는 여기로 추적가능해야 함(재근거화).

## Unitree G1 (29-DOF, g1_29dof_rev_1_0) — verified: **yes**
- 총질량 ~35kg · 키 **1.32m** 직립(접으면 0.69m). ⚠ 공식페이지 1.32m(task 힌트의 1.27m는 오류). 다리 6 DOF/측, 12 total.
- 세그먼트(URDF inertial, 직접 read·2회 검증): **허벅지는 단일 'thigh' 링크 없음** — hip_pitch_link 1.35 + hip_roll_link 1.52 + **hip_yaw_link 1.702(메인 femur)**. **shin = knee_link 1.932.** 발 = ankle_roll_link 0.608(+ ankle_pitch_link 0.074 브래킷). pelvis 3.813.
- 한쪽다리합 = 1.35+1.52+1.702+1.932+0.074+0.608 = **7.186kg.**
- 액추에이터: 내부로터 PMSM, low-inertia high-speed. knee peak 90 N·m(표준)/120(EDU). per-joint peak는 URDF 미공개.
- PD(unitree_rl_gym g1_config.py, **RL 컨트롤러 게인**): Kp hip 100·knee 150·ankle 40 | **Kd hip 2·knee 4·ankle 2.** URDF엔 <dynamics> 댐핑 태그 없음.
- 출처: URDF <https://raw.githubusercontent.com/unitreerobotics/unitree_ros/master/robots/g1_description/g1_29dof_rev_1_0.urdf> · 공식 <https://www.unitree.com/g1/> · PD <https://github.com/unitreerobotics/unitree_rl_gym/blob/main/legged_gym/envs/g1/g1_config.py>

## Unitree H1 (base/v1, 19-DOF) — verified: **yes**
- 총질량 ~47kg(공식 "About 47kg"; URDF합 ~46.8) · 키 ~1.8m(공식 "about 180CM"; URDF 1.78). 다리 5 DOF/측(ankle×1), 19 total.
- ⚠ **H1-2(~70kg, 27-DOF, ankle×2)와 혼동 금지** — 70kg/27-DOF 수치는 H1-2 것.
- 세그먼트(URDF h1.urdf inertial, exact): **허벅지 = left_hip_pitch_link 4.953**(+ hip_yaw 2.965 + hip_roll 2.715). **shin = knee_link 2.824.** 발 = ankle_link 0.725. pelvis 5.983, torso 17.789(배터리 포함).
- 한쪽다리합 = 2.965+2.715+4.953+2.824+0.725 = **14.18kg.**
- 액추에이터: QDD PMSM. peak knee ~360·hip ~220·arm ~75 N·m. URDF effort: hip 200·knee 300·ankle 40. vel: hip 23·knee 14·ankle 9 rad/s. 최대 3.3m/s.
- PD(unitree_rl_gym h1, **RL 컨트롤러 게인**): Kp hip 150·knee 200·ankle 40·torso 300 | **Kd hip 2·knee 4·ankle 2·torso 6.** action_scale 0.25, decimation 4(50Hz). URDF엔 댐핑 태그 없음.
- 출처: 공식 <https://www.unitree.com/h1/> · URDF <https://github.com/unitreerobotics/unitree_ros/blob/master/robots/h1_description/urdf/h1.urdf> · PD <https://github.com/unitreerobotics/unitree_rl_gym/blob/main/deploy/deploy_real/configs/h1.yaml>

## Agility Digit (연구/URDF 버전, Cassie 다리) — verified: **partial**
- 총질량 **48kg**(torso 15kg) · 키 ~1.6m(부분검증). ⚠ **상용 v4는 ~65~76kg·~1.75m, 링크질량·토크·PD 비공개.** 다리 6 DOF/측(4 직접구동 + toeA/B), 20 actuated·30 DOF.
- 세그먼트(공식 URDF digit_model.urdf, exact): **허벅지 = hip_pitch 6.244279**(+ hip_roll 0.915088 + hip_yaw 0.818753). lower-leg = knee 1.227077 + **shin 0.895793** + tarsus 1.322865. 발 = toe_pitch 0.043881 + toe_roll 0.531283 ≈ 0.575.
- 한쪽다리합 = 0.915+0.819+6.244+1.227+0.896+1.323+0.044+0.531 = **11.999kg.** 양다리 ~24.0 + torso 15.03.
- 액추에이터: BLDC + parallel/cable + series-elastic leaf-spring(Cassie 파생). peak(MJCF gear×ctrlrange): hip_roll/yaw 25×4.5=112.5 · hip_pitch/knee 16×12.2=195.2 · toe 50×0.9=45 N·m. ⚠ aggregator의 115/174.7/100 N·m는 1차출처 없음.
- PD: **공식 spec엔 컨트롤러 Kp/Kd 없음.** MuJoCo Cassie MJCF의 **물리 조인트 댐핑**(우리 Kd와 단위 다름): hip/knee 1.0·shin 0.1·tarsus 0.1·achilles 0.01. passive 스프링 강성: shin 1500·heel 1250 N·m/rad. armature: hip_roll/yaw 0.038125·hip_pitch/knee 0.09344·foot 0.01225. 컨트롤러 PD는 task별·미공개.
- 출처: URDF <https://raw.githubusercontent.com/adubredu/DigitRobot.jl/main/urdf/digit_model.urdf> · 논문(48kg/30DOF/Cassie) <https://arxiv.org/pdf/2103.15309> · 토크·댐핑 <https://github.com/google-deepmind/mujoco_menagerie/blob/main/agility_cassie/cassie.xml> · 공식 <https://www.agilityrobotics.com/about/resources/spec-sheet>

## Cassie (Agility / OSU) — verified: **yes**
- 총질량 ~31kg · 키 ~1.0m 직립. 다리 7 DOF/측(5 actuated), 10 actuators·20 DOF. **torso/arms 없음**(있으면 별개 로봇 Digit).
- 세그먼트(UMich-BipedLab cassie_description URDF, exact·grep 확인): pelvis 10.33·pelvis_rotation 1.82·hip 1.17·**thigh 5.52**·knee 0.758·**shin 0.577**·tarsus 0.782·toe(발) 0.15(pelvis_abduction·vectorNav = 0).
- 한쪽다리합 = 1.82+1.17+5.52+0.758+0.577+0.782+0.15 = **10.78kg.** (URDF합 ~33.3kg, 실기 ~31kg — URDF가 일부 관성질량 lumping.)
- 액추에이터: 10 BLDC, 8 cycloidal + 2 harmonic(발). peak(ctrlrange×gear): hip_roll/yaw ±4.5×25=±112.5 · hip_pitch/knee ±12.2×16=±195.2 · foot ±0.9×50=±45 N·m. 모터 max: hip_roll/yaw 2900·hip_pitch/knee 1300·foot 5500 rpm.
- PD: **canonical HW PD 미공개.** MJCF **물리 댐핑**: hip/knee 1.0·shin 0.1·tarsus 0.1. leaf-spring 강성: shin 1500·heel 1250. control 2kHz(dt 0.0005). MJCF는 "provided directly by Agility Robotics"(menagerie README) → 공식 수치.
- 출처: URDF <https://github.com/UMich-BipedLab/cassie_description> · gear/torque/댐핑 <https://github.com/osudrl/cassie-mujoco-sim/blob/master/model/cassie.xml> · MJCF <https://github.com/google-deepmind/mujoco_menagerie/blob/main/agility_cassie> · 논문 <https://arxiv.org/pdf/1809.07279> · <https://robotsguide.com/robots/cassie/>

## Berkeley Humanoid (UC Berkeley Hybrid Robotics 연구 플랫폼) — verified: **partial**
- 총질량 **16kg**(arms 없이; 옵션 4-DoF arms ×2 = +6kg → 22kg, 단 실제 빌드는 16kg) · 키 **0.85m**. 다리 6 DoF/측, 12 total. thigh 길이 220mm·calf 180mm(질량 아님).
- ⚠ **세그먼트 절대질량 미공개** — 논문은 길이·액추에이터 질량·rotor inertia·상대 mass-randomization(Base ±1kg, Linkage ×0.9~1.1)만 게재. per-link 질량은 75MB 바이너리 USD(berkeley_humanoid.usd) 안에만 → pxr/USD 미설치로 추출 불가, **추정 안 함**(추출하려면 Isaac Sim/usdcat로 physics:mass read).
- ⚠ **별개 로봇 "Berkeley Humanoid Lite"(arXiv 2504.17249, 3D프린트)와 혼동 금지** — 이건 16kg 연구 플랫폼.
- 액추에이터: custom QDD, 전부 9:1 단단 planetary, 토크제어 1kHz. 4 모터타입(Table2) peak/sustained N·m: 5013 9.7/4.59 · 8513 45.3/18.9 · 8518 62.6/26.1 · 10413 81.1/34.2.
- PD(공식 Isaac repo berkeley_humanoid.py IdentifiedActuatorCfg, **RL 게인**): HR/HAA Kp10/**Kd1.5**(eff20) · HFE Kp15/**Kd1.5**(eff30) · KFE Kp15/**Kd1.5**(eff30, armature 1.5e-4×81) · FFE Kp1/Kd0.1(eff20) · FAA Kp1/Kd0.1(eff5). 저수준 PD 25kHz, RL 50Hz.
- 출처: 논문 <https://arxiv.org/abs/2407.21781> (PDF <https://arxiv.org/pdf/2407.21781>) · 공식 코드/USD <https://github.com/HybridRobotics/isaac_berkeley_humanoid> · <https://berkeley-humanoid.com/>

## Fourier GR-1 (GR1T1, Fourier Intelligence) — verified: **yes**
- 총질량 **55kg**(URDF합 52.83kg, 35링크·손가락/배터리 제외) · 키 **1.65m**. 다리 6 DOF/측·12 total, whole-body 40 DOF.
- 세그먼트(공식 FFTAI URDF gr1t1.urdf, exact): **허벅지 = thigh_roll 1.45 + thigh_yaw 3.17 + thigh_pitch 7.99(메인 femur) = 12.61.** **shin = shank_pitch_link 1.93.** 발 = foot_pitch 0.538 + foot_roll 0.538 = 1.076.
- 한쪽다리합 = 1.45+3.17+7.99+1.93+0.538+0.538 = **15.616kg.** 양다리 31.23.
- 액추에이터: Fourier FSA(QDD). 공식 hip 모듈 peak 300 N·m(마케팅). URDF effort(per-joint peak): hip_roll 48·hip_yaw 66·hip_pitch 225·knee_pitch 225·ankle_pitch 15·ankle_roll 30. vel: 12.15/16.76/37.38/37.38/20.32/20.32 rad/s.
- PD(공식 Wiki-GRx-Deploy demo_walk.py, **walk 컨트롤러 게인**): Kp [hip_roll,hip_yaw,hip_pitch,knee,ankle_p,ankle_r]=[180,120,90,120,45,45] · **Kd=[10,10,8,8,2.5,2.5].** waist 90/8.
- 출처: URDF <https://github.com/FFTAI/Wiki-GRx-URDF/blob/master/GRX/GR1/gr1t1/basic_urdf/gr1t1.urdf> · PD <https://github.com/FFTAI/Wiki-GRx-Deploy/blob/master/pubsub_radian/demo_walk.py> · 스펙(55kg/1.65m/40DOF/300N·m) <https://www.therobotreport.com/fourier-intelligence-launches-production-version-of-gr-1-humanoid-robot/>

---
> 우리 로봇(robstride_biped, 비교 기준): 총 51.8kg · 키 0.87m · thigh 5.10 · shin 2.82 · 발 0.97 · 한쪽다리 11.85kg(45.8%) · base/torso 28.1kg. PD knee 80/3·hip 200/5. thigh 관성 0.052·shin 0.033 kg·m²(우리 URDF, 검증). 출처: 우리 URDF·robstride_biped.yaml.
