# 관절별 Kp/Kd(게인) 이력 — 현재값 + 과거 학습값

> 2026-07-06. 각 학습 run의 params/env.yaml에서 실측 파싱. 형식 = **Kp / Kd / effort(N·m)**. 게인은 캠페인 중 3세대로 진화(armature-soft → hip·knee chirp화 → ankle 2-RSU 스왑).

## 1. ★ 현재값 (2026-07-06 hip 참조스케일 후)

| 관절 | Kp | Kd | effort | 모터 | 근거 |
|---|--:|--:|--:|---|---|
| hip_pitch | **150** | **6** | 120 | RS04 | ★G1·K-bot 참조 ×1.47 질량스케일 |
| hip_roll | **150** | **6** | 120 | RS04 | 〃 |
| hip_yaw | **150** | **6** | 60 | RS03 | 〃 (uniform hip like G1/K-bot) |
| knee | **220** | **6** | 120 | RS04 | ★2026-07-07 참조스케일(G1 150·×1.47), 400→220 |
| ankle_pitch | 28.5 | 1.81 | 90 | RS03×2(2-RSU) | G1 ankle 스펙 매칭 |
| ankle_roll | 28.5 | 1.81 | 50 | RS03×2(2-RSU) | 〃 |

### 1a. hip 참조스케일 (2026-07-06, user "hip 너무 커")
| | G1(35kg) | K-bot(34kg, 동일RS04) | ×1.47 | **채택** |
|---|--|--|--|--|
| hip Kp | 100 | 100 | 147~151 | **150** |
| hip Kd | 2 | 10(과감쇠) | G1→3 / K-bot→15 | **6** (G1측+마진, K-bot 할인) |
- 근거: $K_p\propto I\propto m$, 우리 51.5kg / 참조 ~35kg = 1.47. G1·K-bot 둘 다 Kp 100 → 150. Kd는 G1(2)·K-bot(10, 사용자가 과함 지적) 사이서 **K-bot 할인**해 6 ($K_d/K_p$=0.04, G1 0.02~K-bot 0.1 중간). Asimov는 게인 비공개라 제외.
- 이전 400/28은 chirp(10Hz·ζ2) 유래 = **G1의 4× Kp·과감쇠** → 과강성 wobble 의심원.

## 2. 이력 (run별 실측)

| run (시기) | hip_p/r | hip_yaw | knee | ankle_pitch | ankle_roll |
|---|---|---|---|---|---|
| **A0a** 07-02_00-54 (초기) | 28 / 1.76 | 20 / 1.26 | 28 / 1.76 | 20 / 1.26 | **2 / 0.13** |
| **A1b·B3** 07-02_23-03 | **400 / 28** | **400 / 9** | **400 / 8** | 20 / 1.26 | 2 / 0.13 |
| **R1b** rough 07-03_16-32 | 400 / 28 | 400 / 9 | 400 / 8 | 20 / 1.26 | 2 / 0.13 |
| **C1** flat 07-04_12-13 | 400 / 28 | 400 / 9 | 400 / 8 | **28.5 / 1.81** | **28.5 / 1.81** |
| **R2** rough 07-05_04-29 | 400 / 28 | 400 / 9 | 400 / 8 | 28.5 / 1.81 | 28.5 / 1.81 |
| **V2** flat 07-06 (현재) | 400 / 28 | 400 / 9 | 400 / 8 | 28.5 / 1.81 | 28.5 / 1.81 |

*(effort: hip_p/r·knee 120 · hip_yaw 60 · ankle_pitch 60→90 · ankle_roll 14→50, C1부터 2-RSU값)*

## 3. 세대별 변경 이유

### 세대 1 — armature-derived (A0a): 전 관절 soft ❌
- 산정식 $K_p = \text{armature}\times\omega_n^2$ (로터 반사관성만, $\omega_n$=10Hz). 링크 관성 무시 → **유효 대역폭 0.56Hz**로 과소 = wobble. ankle_roll $K_p$=2는 G1의 1/14 = 위치권한 거의 0.
- 참조: [gain 분석](2026-07-02_gait_analysis_and_wobble.md)·[action scale](2026-07-02_action_scale_and_gains.md)

### 세대 2 — hip·knee chirp화 (A1b, 07-02): hip/knee만 상향 ✅, ankle은 방치
- chirp 사인스윕으로 재산정 → **hip_p/r·hip_yaw·knee = $K_p$ 400**(A1의 knee 800은 과강성→load가 knee로 이동, A1b서 **400/8로 재균형**).
- ★그러나 **ankle은 여전히 armature-soft**(pitch 20, roll 2) — B3·R1b 내내 유지. R1b rough서 ankle_roll 과부하(134%)의 한 원인.

### 세대 3 — ankle 2-RSU 스왑 (C1, 07-04): ankle을 G1 스펙으로 ✅ 현재
- 2-RSU 전환 결정 후 ankle을 **G1 ankle 실스펙 $K_p$ 28.5 / $K_d$ 1.81 / effort 50**에 정렬(roll), pitch는 2모터 co-act로 effort 90.
- roll $K_p$: 2 → **28.5**(14×↑), pitch 20 → 28.5. 근거: G1이 동일 2-RSU를 33kg서 이 게인 운용. [메커니즘 §4b](2026-07-03_knee_ankle_mechanism_design.md)·[2-RSU 분석](2026-07-04_serial_vs_2rsu_analysis.md).

## 4. 미해결·관찰
- hip/knee $K_p$ 400은 chirp 검증됐으나 **G1(40~99) 대비 4× 강성** — 과강성 의심(별도 실험 후보, 재학습 필요라 미변경). [메커니즘 §4b](2026-07-03_knee_ankle_mechanism_design.md).
- 현재 V2 학습은 **게인 불변**(리워드·커리큘럼·외력만 변경) — 즉 R2와 동일 게인.
- 관련: [Reward&Gains 표 규칙](../../) — 각 실험노트 §1b에 run별 게인 소급 기록됨.
