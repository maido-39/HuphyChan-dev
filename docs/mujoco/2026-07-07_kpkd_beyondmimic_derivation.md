# Kp/Kd 물리 유도 (BeyondMimic 방식) — 계산 과정 trace

> 2026-07-07. peer(Asimov팀) 피드백: sim은 Kp/Kd **값**보다 **감쇠비 ζ 비율**에 민감 — under/over-damped면 sim서 진동을 학습해 real서 악화. BeyondMimic 방식으로 우리 실제 관성 기반 물리계산. [BeyondMimic arXiv:2508.08241](https://arxiv.org/html/2508.08241v4). 관련: [게인 이력](2026-07-06_kp_kd_history.md).

## 1. BeyondMimic 공식
$$K_p = I\,(2\pi f_n)^2, \qquad K_d = 2\,I\,\zeta\,(2\pi f_n)$$
- $I$ = 관절 유효관성, $f_n$ = 목표 고유진동수(≈10Hz), $\zeta$ = 감쇠비(BeyondMimic 기본 2 = over-damped).
- 두 식에서 $\zeta$ 소거 → **핵심 관계**:
$$\boxed{\;\zeta = \dfrac{K_d}{2\sqrt{K_p\,I}}\;}\qquad \omega_n=\dfrac{1}{2\pi}\sqrt{K_p/I}\ \text{[Hz]}$$
- 진동 없음(critical) = $\zeta=1$ → $K_d = 2\sqrt{K_p I}$. over-damped = $\zeta>1$.

## 2. $I$(유효관성) 산출 — 우리 모델
MuJoCo **mass matrix 대각** $M_{ii}$(armature 포함) = 그 관절이 실제로 가속하는 총 관성. 자세의존이라 직립(home)·보행(무릎−60°) 두 자세서 큰 값 채택.
계산: `get_spec().compile()` → `mj_fullM(m, d, M)` → $M[\text{dof},\text{dof}]$.

| 관절 | I_home | I_walk | armature | 채택 I (kg·m²) |
|---|--:|--:|--:|--:|
| hip_pitch | 2.34 | 2.08 | ~0 | **2.34** |
| hip_roll | 2.09 | 1.37 | ~0 | **2.09** |
| hip_yaw | 0.04 | 0.32 | ~0 | **0.32** |
| knee | 0.31 | 0.31 | ~0 | **0.31** |
| ankle_pitch | 0.010 | 0.010 | ~0 | **0.010** |
| ankle_roll | 0.003 | 0.003 | ~0 | **0.003** |
*(armature≈0: 컴파일 모델 dof_armature 미반영이거나 링크관성 대비 무시가능 — hip 링크관성 2.34 ≫ RS04 반사관성 0.007. 즉 감쇠는 **링크관성이 지배**. ★이게 BeyondMimic이 armature만 쓰면 물러지는 이유 = 링크관성 무시.)*

## 3. 현재 게인의 ζ 진단 (계산 대입)
현재 P2/knee-220 게인을 위 식에 대입:

| 관절 | K_p | K_d현재 | ζ = K_d/(2√(K_pI)) | 판정 | ω_n |
|---|--:|--:|:--:|:--:|--:|
| hip_pitch | 150 | 6 | 6/(2√(150·2.34))= **0.16** | ❌ 심한 under | 1.3Hz |
| hip_roll | 150 | 6 | **0.17** | ❌ under | 1.4Hz |
| hip_yaw | 150 | 6 | **0.43** | ⚠ under | 3.4Hz |
| knee | 220 | 6 | **0.36** | ⚠ under | 4.2Hz |
| ankle_pitch | 28.5 | 1.81 | **1.68** | ✅ over | 8.4Hz |
| ankle_roll | 28.5 | 1.81 | **3.20** | ✅ over | 16Hz |

★ **근본원인**: Kp는 G1 참조스케일로 잘 잡았으나(150/220), **Kd를 G1 비율(≈0.02)로 복사** → 51.5kg(G1의 1.5×)의 큰 링크관성엔 감쇠 태부족. hip이 ζ=0.16 = **critical의 1/6 = 진동 성향**(피드백이 경고한 그 상황). 발목은 관성이 작아 Kd 1.8로도 over-damped=OK.

## 4. Critical-damped 권고값 ($\zeta=1$)
$K_d = 2\sqrt{K_p I}$ 대입:

| 관절 | K_p | K_d(ζ=1) | K_d(ζ=0.7) | **채택(BeyondMimic run)** |
|---|--:|--:|--:|--:|
| hip_pitch | 150 | 2√(150·2.34)= **37** | 26 | **35** |
| hip_roll | 150 | 35 | 25 | **35** |
| hip_yaw | 150 | 14 | 10 | **14** |
| knee | 220 | 16 | 12 | **16** |
| ankle_pitch | 28.5 | 1.1 | 0.8 | 1.81(유지, over OK) |
| ankle_roll | 28.5 | 0.6 | 0.4 | 1.81(유지) |

- $K_p$ 불변(G1 참조스케일 유효), **$K_d$만 물리 critical로 상향**. hip 6→35(≈old400/28의 Kd28과 근접), knee 6→16.
- 이유: 피드백대로 sim은 ζ에 민감 → critical이면 진동 안 배움. real은 트래킹만 되면 됨(이 Kd로 실모터가 policy 출력 추종하면 OK).

## 5. 검증 계획
현재 학습(under-damped Kd 6, knee-220)은 **남겨두고**, 다음 학습을 이 critical-damped Kd로 돌려 **1:1 비교**(같은 시퀀스 영상·고스트 오버레이). 관건: 진동/wobble 감소, gait 매끄러움, track 유지.

## 재현
```python
m=get_spec().compile(); d=mujoco.MjData(m)
d.qpos[:]=q; mujoco.mj_forward(m,d)
M=np.zeros((m.nv,m.nv)); mujoco.mj_fullM(m,d,M)   # ★ API: (m, d, dst)
I=M[m.jnt_dofadr[jid], m.jnt_dofadr[jid]]
zeta=Kd/(2*np.sqrt(Kp*I)); Kd_crit=2*np.sqrt(Kp*I)
```
