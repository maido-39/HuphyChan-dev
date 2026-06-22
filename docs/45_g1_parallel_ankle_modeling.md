# 45 · Unitree G1 2-RSU 병렬 발목 — sim 모델링·학습·배포 (코드 확인)

> 트리거(사용자 2026-06-22): "G1은 2-RSU로 parallel bar 발목을 쓰는데 URDF/USD에 어떻게 모델했고 어떻게 학습시키나? 다이어그램으로." → `unitreerobotics/unitree_rl_gym` clone(`refs/`, gitignore)해서 URDF·MJCF·학습·배포 코드 직접 확인. 다이어그램 = 위젯 `unitree_g1_2rsu_parallel_ankle_sim2real`.

## 결론 한 줄
**G1의 병렬 발목은 sim에 전혀 모델되지 않는다.** URDF·MJCF·학습·python배포 = 전부 **직렬 `ankle_pitch`/`ankle_roll` 2축**. 병렬 로드→모터 변환(J^T)은 **로봇 펌웨어**에만 존재(PR/Series 모드). = 교과서적 "Camp A" ([[38_parallel_ankle_sim2real]]).

## 1. URDF/USD 모델링 (verified)
- `resources/robots/g1_description/g1_29dof.urdf`: `<joint left_ankle_pitch_joint revolute>`(부모) → `<joint left_ankle_roll_joint revolute>`(자식, parent=ankle_pitch_link). **push-rod·bar·`mimic`·`<loop>` 전무.** 순수 직렬 트리.
- `g1_29dof.xml`(MJCF): 동일 직렬. `ankle_pitch_joint`(axis 0 1 0, range −0.87..0.52), `ankle_roll_joint`(axis 1 0 0, range −0.26..0.26), 둘 다 `actuatorfrcrange="-50 50"`. ★ **`equality`/`connect`/`tendon` 없음** = 병렬 닫힌루프 미모델. (sites는 IMU뿐.)
- `<actuator>`: `<motor joint="left_ankle_pitch_joint"/>` + `<motor joint="left_ankle_roll_joint"/>` = **joint당 1 ideal 모터**(병렬 2모터 아님).

## 2. 학습 (verified)
- `legged_gym/envs/g1/g1_config.py`: `num_actions=12`(다리), `file=g1_12dof.urdf`. 정책 → 12 joint 위치목표(직렬 ankle pitch/roll 포함).
- 발목 PD: `stiffness ankle=40`, `damping ankle=2`(hip 100/2보다 낮음), `action_scale=0.25`, default `ankle_pitch=-0.2, ankle_roll=0`. 정책은 병렬 기구 안 봄.

## 3. 배포 / sim2real (verified)
- `deploy/deploy_real/common/command_helper.py`: `class MotorMode: PR=0  # Series Control for Pitch/Roll`, `AB=1  # Parallel Control for A/B Joints`.
- `deploy/deploy_real/deploy_real.py`: `self.mode_pr_ = MotorMode.PR` → `init_cmd_hg(..., self.mode_pr_)`로 모드 전송. **PR(Series) 모드 = ankle pitch/roll 명령(sim과 동일 joint-space)을 보내면 펌웨어(`mode_machine`)가 내부에서 병렬 모터 A/B로 변환**.
- ★ **실제 rod 기구학/J^T 수식은 repo에 없음**(`sin/cos/rod/jacobian` grep 0건) = 펌웨어에 구현. python 측은 모드 플래그만 세팅. (`unitree_mujoco`의 G1도 직렬 — equality/tendon 0 — 이중확인.)

### PR vs AB 모드 (Weston/Unitree 문서 + 웹 verified)
- **PR(기본)**: pitch/roll 모터 제어 = URDF 직렬과 일치. **펌웨어가 PR↔모터 변환을 내부 처리** → sim-trained 정책 그대로 보냄.
- **AB**: A/B 모터 직접 제어 = **"사용자가 병렬 기구학을 직접 계산해야"**(Weston G1 가이드). Unitree는 변환 수식 **비공개**(펌웨어/CAD).
- ★ **IK인가?**: joint(pitch/roll)→motor(A/B) 역기구학이 맞으나 **2-DOF 병렬발목은 닫힌형(analytic), 반복 IK 솔버 아님**. 정기구학 `pitch≈k_p(θ_A+θ_B)/2, roll≈k_r(θ_A−θ_B)/2`(차동)+rod 삼각함수; 역+`τ_motor=J^T·τ_joint`. = 닫힌 펌웨어 블랙박스(PR) 또는 사용자 닫힌형(AB).

## 3.5 ★ joint 파라미터 충실도 — G1은 병렬 보정을 *안 한다* (verified)
질문: 직렬 모델이면 병렬의 반사관성·마찰이 빠지는데 joint 파라미터로 보정하나? → **G1은 안 함.**
- G1 MJCF 발목 joint = `actuatorfrcrange ±50`뿐. **`armature` 0 · `frictionloss` 0 · `damping` 0** (default 클래스에도 없음) = **모터 반사관성·rod/베어링 마찰 미모델**. 링크 `inertial`(mass 0.608·diaginertia)만 CAD 실측.
- `g1_config.py`: `armature=0`(base 기본값), joint friction 0. `domain_rand` = 지면마찰[0.1,1.25]·base질량·push만 — **joint armature/friction 랜덤화 0**.
- 왜 그래도 됨: **PD 게인(kp40/kd2)을 실로봇서 튜닝** → 컨트롤러가 미모델 동역학 흡수 + DR robustness + G1 backdrivable QDD는 마찰 작음 + position 제어(action_scale 0.25)라 관성/마찰 민감도 낮음.
- ★ **덜 엄밀한 쪽**. 엄밀법(PACE/K-Bot·[[44_sim2real_hw_matching]]): **armature=I_rotor·gear² + friction 3항(Coulomb/viscous/static) 벤치 ID**. ★ **병렬 발목은 반사관성이 *각도의존*(병렬 야코비안 J(θ))** → 상수 armature는 근사(중립/worst-case).
- 우리: armature는 *설정함*(RS00 0.0015·RS03 0.0049 = G1보다 엄밀) but **friction 전무**([[44_sim2real_hw_matching]] §6 미해결). 2-RSU면 armature = 2모터를 J(θ)로 반사한 값.

## 4. ★ 우리 로봇 적용 (2-RSU 채택 시)
- 우리 sim은 이미 `ankle_pitch`/`ankle_roll` 직렬 → **G1과 동일 구조. 그대로 가면 됨**(병렬을 sim에 넣을 필요 없음; IsaacLab/PhysX는 닫힌루프 native 미지원).
- 병렬→모터 변환은 **배포 SDK/펌웨어**에 (RobStride CAN + 우리 rod 기하). sim의 flat joint effort 한계(예 RS00 14·RS03 60)는 병렬 기구의 **각도의존 유효토크를 근사**한 것 = 충실도 단순화([[37_ankle_linkage_fidelity]]·[[41_ankle_pitch_pushoff_rs03_underspec]]).
- 사이징은 **joint-space 토크**(우리 §7 측정)로 하고, **rod 힘 = τ_joint / r_a(θ)**를 worst-case(push-off=최대토크 AND ROM끝=최악 레버암)에서 따로 검증([[43_ankle_hw_decision]]). 그 r_a(θ)는 sim 학습엔 불필요, HW 사이징 후처리만.

## 출처
- repo: [unitreerobotics/unitree_rl_gym](https://github.com/unitreerobotics/unitree_rl_gym) (`refs/unitree_rl_gym`, shallow clone) — `g1_29dof.urdf`·`g1_29dof.xml`·`g1_config.py`·`deploy_real/common/command_helper.py`·`deploy_real.py`.
- 내부: [[38_parallel_ankle_sim2real]](Camp A/B)·[[44_sim2real_hw_matching]]·[[37_ankle_linkage_fidelity]]·[[43_ankle_hw_decision]].
