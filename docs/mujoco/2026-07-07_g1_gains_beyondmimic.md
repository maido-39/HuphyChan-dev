# Unitree G1 SIM/REAL Kp·Kd 게인 — BeyondMimic($\zeta$) 방식 분석

2026-07-07. Pygmalion(51.5 kg 하지 휴머노이드) 게인 재설계를 위한 레퍼런스 분석.
방법론은 [[2026-07-07_kpkd_beyondmimic_derivation]] 참조 (BeyondMimic, [arXiv:2508.08241](https://arxiv.org/abs/2508.08241)):

$$K_p = I\,(2\pi f_n)^2, \quad K_d = 2 I \zeta\,(2\pi f_n) \;\Rightarrow\; \zeta = \frac{K_d}{2\sqrt{K_p I}}, \quad f_n = \frac{1}{2\pi}\sqrt{K_p/I}\ \text{[Hz]}$$

$\zeta<1$ under-damped(진동 경향, sim2real 불리), $\zeta=1$ critical, $\zeta>1$ over-damped.

## §1 G1 게인 추출

### 1a. REAL 배포 게인 (실기 컨트롤러)

`refs/unitree_rl_gym/deploy/deploy_real/configs/g1.yaml:13-14` (다리 12관절, 좌/우 동일):

| 관절 그룹 | K_p [N·m/rad] | K_d [N·m·s/rad] |
|---|---|---|
| hip_pitch / hip_roll / hip_yaw | 100 | 2 |
| knee | 150 | 4 |
| ankle_pitch / ankle_roll | 40 | 2 |

학습(SIM) 컨트롤러 게인 `refs/unitree_rl_gym/legged_gym/envs/g1/g1_config.py:42-53`도 **동일** (hip 100/2, knee 150/4, ankle 40/2). 즉 G1은 SIM 학습과 REAL 배포에 같은 PD 게인을 쓰며, sim2real 게인 갭이 0이다. action_scale=0.25, decimation=4 (`g1_config.py:55-57`).

### 1b. SIM 모델 (unitree_mujoco)

`refs/unitree_mujoco/unitree_robots/g1/g1_29dof.xml`: 액추에이터는 `<motor>` **토크 타입**이라 XML에 게인이 없고(게인은 RL 컨트롤러에서 적용), `ctrlrange`는 토크 한계다.

| 관절 | 토크한계 [N·m] (xml 행) | armature [kg·m²] | joint damping / frictionloss |
|---|---|---|---|
| hip_pitch/roll/yaw | ±88 (L388-390) | 0.01 (L6-18 default class) | 0.05 / 0.2 |
| knee | ±139 (L391) | 0.01 | 0.05 / 0.2 |
| ankle_pitch/roll | ±50 (L392-393) | 0.01 | 0.05 / 0.1 |

총 질량(29dof 모델, `body_mass` 합): **35.1 kg**.

## §2 G1 실기 게인의 $\zeta$ / $f_n$ (I_eff = MuJoCo 질량행렬 대각)

standing pose(배포 default_angles: hip_pitch −0.1, knee 0.3, ankle_pitch −0.2, `g1.yaml:15-16`)에서 `mj_fullM` 대각 성분 $I_\text{eff}$ (armature 0.01 포함, 좌/우 동일하므로 좌측만 표기):

| 관절 | I_eff [kg·m²] | K_p | K_d | ζ | f_n [Hz] | 판정 |
|---|---|---|---|---|---|---|
| hip_pitch | 0.913 | 100 | 2 | **0.105** | 1.67 | 심한 under-damped |
| hip_roll | 0.743 | 100 | 2 | **0.116** | 1.85 | 심한 under-damped |
| hip_yaw | 0.084 | 100 | 2 | **0.345** | 5.50 | under-damped |
| knee | 0.124 | 150 | 4 | **0.465** | 5.55 | under-damped |
| ankle_pitch | 0.013 | 40 | 2 | **1.399** | 8.90 | over-damped |
| ankle_roll | 0.010 | 40 | 2 | **1.551** | 9.88 | over-damped |

주의: $I_\text{eff}$는 자세 의존(대각 성분은 해당 관절 아래 체인 전체의 관성). standing pose 기준 값이며, swing 중 무릎 굴곡 시 hip $I_\text{eff}$는 더 작아져 $\zeta$는 다소 올라간다.

## §3 해석 — G1도 hip/knee는 under-damped다

예상("G1은 ζ≈1일 것")과 달리, **G1 자체가 hip $\zeta\approx0.11$, knee $\zeta\approx0.47$의 뚜렷한 under-damped 설계**다. ankle만 $\zeta>1$. 그럼에도 G1이 실기에서 안정한 이유로 볼 수 있는 요인:

1. **가벼운 다리 → 낮은 절대 관성**: G1 총 35.1 kg, hip_pitch $I_\text{eff}=0.91$ vs Pygmalion **2.34** (약 **2.6배** 차이). 같은 $K_d$라면 $\zeta \propto 1/\sqrt{I}$이므로 G1이 $\sqrt{2.6}\approx1.6$배 유리하고, 같은 $\zeta$를 만들려면 Pygmalion은 $K_d$를 $\sqrt{I_\text{Pyg}/I_\text{G1}}\times\sqrt{K_{p,\text{Pyg}}/K_{p,\text{G1}}}$ 배 키워야 한다 (hip 기준 $2\times\sqrt{1.5}\approx2$배 → G1의 2가 아니라 ≈4 상당).
2. **낮은 $f_n$을 감수한 설계**: hip $f_n\approx1.7$ Hz로 매우 소프트. G1 배포 정책은 50 Hz + action_scale 0.25로 목표각 변화 자체를 작게 유지 → 진동 여기(excitation)가 적다. 즉 "강한 $K_p$ + 임계감쇠"가 아니라 "약한 $K_p$ + 약한 $K_d$ + 정책이 흡수" 전략.
3. **관절 자체 물리 감쇠**: XML의 joint damping 0.05 + frictionloss 0.2 N·m (실기 기어 마찰 대응)이 소진폭 진동을 추가로 죽인다. hip 유효 $K_d\approx2.05$ + 쿨롱마찰 — $I$가 작을수록 이 고정 마찰의 상대 기여가 크다.
4. **접지 시 부하 감쇠**: stance 다리는 지면 컨택트가 사실상의 감쇠기로 작동. 자유 진동이 문제 되는 건 swing 다리인데, swing 시 $I_\text{eff}$가 작아져 $\zeta$가 상승.

핵심: **G1의 "낮은 $K_d$"는 낮은 관성의 결과이지, 낮은 $\zeta$가 무해하다는 증거가 아니다.** 그리고 Asimov 팀 피드백(under-damped = sim2real 불리) 기준으로 보면 G1 hip ζ 0.11도 좋은 설계라기보다 "가볍고 토크 여유가 커서 버티는" 케이스에 가깝다. 51.5 kg인 Pygmalion이 이 값을 그대로 이식하면 $\zeta$가 더 내려가 진동 위험이 커진다.

## §4 G1 vs Pygmalion 비교

Pygmalion $I_\text{eff}$: hip_pitch 2.34, knee 0.315 (standing pose, [[2026-07-07_kpkd_beyondmimic_derivation]] §measurement).

| 관절 | 로봇/설정 | I_eff | K_p | K_d | ζ | f_n [Hz] |
|---|---|---|---|---|---|---|
| hip_pitch | G1 (SIM=REAL) | 0.913 | 100 | 2 | 0.105 | 1.67 |
| hip_pitch | Pygmalion 현재 | 2.34 | 150 | 6 | 0.160 | 1.27 |
| hip_pitch | Pygmalion BeyondMimic | 2.34 | 150 | 35 | **0.93** | 1.27 |
| knee | G1 (SIM=REAL) | 0.124 | 150 | 4 | 0.465 | 5.55 |
| knee | Pygmalion 현재 | 0.315 | 220 | 6 | 0.360 | 4.21 |
| knee | Pygmalion BeyondMimic | 0.315 | 220 | 16 | **0.96** | 4.21 |
| ankle_pitch | G1 (SIM=REAL) | 0.013 | 40 | 2 | 1.399 | 8.90 |

관찰:
- **현재 Pygmalion hip ζ 0.16은 G1(0.11)보다 이미 높다** — 그러나 둘 다 심한 under-damped 영역. G1이 "이 정도로 굴러간다"는 존재 증명일 뿐, 2.6배 무거운 관성에서 같은 전략의 안전 마진은 더 작다.
- $f_n$은 세 설정 모두 1.3–5.5 Hz 대역으로 유사 — BeyondMimic 보정은 $K_p$($f_n$)는 유지하고 $K_d$만 올려 $\zeta\to1$로 이동시키는 것이라 추종 대역폭 손실이 없다.
- G1 ankle은 오히려 $\zeta>1$ (over-damped): 접지 관절에는 감쇠 여유를 두는 게 Unitree의 실전 선택이라는 점이 BeyondMimic 방향과 부합.

## §5 Sim2real 시사점

1. **게인을 로봇 간 복사하지 말 것**: $K_p, K_d$가 아니라 $(f_n, \zeta)$가 이식 가능한 설계 변수. G1 hip 100/2를 Pygmalion에 그대로 쓰면 $\zeta=2/(2\sqrt{100\cdot2.34})=0.065$로 더 악화된다.
2. **SIM=REAL 게인 일치가 G1 배포의 전제**: unitree_rl_gym은 학습·배포 게인이 동일 — 우리도 학습 게인을 곧 하드웨어 게인으로 쓸 수 있는 값($\zeta\approx1$, 모터 대역폭 내 $f_n$)으로 설계해야 한다.
3. **hip $K_d$ 35, knee $K_d$ 16 (BeyondMimic 보정)은 G1 대비 과하지 않다**: 관성비($\times2.6$)와 $K_p$비($\times1.5$)를 반영하면 G1 hip $K_d=2$의 등가값은 이미 ≈4이고, G1 자체가 under-damped였음을 고려하면 $\zeta\approx1$ 목표가 보수적으로 옳다.
4. **ankle은 G1도 over-damped로 운용** — 접지 충격을 받는 관절은 $\zeta\ge1$이 실전 검증된 방향.
5. 잔여 리스크: $\zeta\approx1$로 올린 $K_d$는 노이즈 있는 실기 속도 측정에서 고주파 토크 잡음을 키울 수 있음 → 배포 시 속도 필터(1st-order LPF) 병행 검토.

### 출처
- REAL 게인: `refs/unitree_rl_gym/deploy/deploy_real/configs/g1.yaml:13-16`
- SIM 학습 게인: `refs/unitree_rl_gym/legged_gym/envs/g1/g1_config.py:42-53`
- SIM 모델: `refs/unitree_mujoco/unitree_robots/g1/g1_29dof.xml` (motor L388-400, default joint L6-18)
- $I_\text{eff}$ 계산: MuJoCo `mj_fullM` 대각, standing pose (본 노트 §2 스크립트, mujoco python)
- 방법론: BeyondMimic [arXiv:2508.08241](https://arxiv.org/abs/2508.08241), [[2026-07-07_kpkd_beyondmimic_derivation]]
