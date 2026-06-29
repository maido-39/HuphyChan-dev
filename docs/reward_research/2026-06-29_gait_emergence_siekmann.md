# 2026-06-29 · 사람 gait emergence — Siekmann periodic contact (접근 재설계)

> 트리거(user): "여전히 까치발. 사람 gait가 RL서 어떻게 emerge하는지 철저 학술조사." → **사용자 제공 deep-research 보고서**(verified, 다수 1차출처) + 내부 v-series 검토. 규칙 [[feedback-reward-research-rule]]. 이 노트가 periodic-contact reward 변경의 근거.

## ★ 핵심 결론 (보고서)
사람같은 stride는 **3요소 결합**으로 emerge (하나로 안 됨):
1. **자세/기하 anchor** (base_height + leg-extension 제약) — 까치발(plantarflex onto forefoot) 유인 제거. ★ 이미 보유(base_height -1.0@0.85). foot-orientation shaping은 증상치료(약함).
2. ★★ **phase-clocked 주기 contact-schedule reward (Siekmann 2011.01387)** — stance↔swing 리듬을 **legislate** → heel-strike→toe-off 타이밍 + L/R 절뚝을 한 번에 해결. **reference-free, Cassie sim-to-real 검증**. = **최고 레버리지**.
3. **energy/mechanical-work penalty** (−|τ·q̇|) — 기하·contact scaffold가 있으면 inverted-pendulum stride + late-stance push-off 유도(shuffle 아님). track에 **종속**(서있기로 만족 불가하게).

**까치발/절뚝 진단**: 까치발 = velocity-tracking reach를 위한 다리신전+plantarflex의 RL attractor(기하적). 절뚝 = symmetry loss + 공유 phase clock으로 해결. ★ **올바른 toe-off 타이밍 = contact schedule을 실제 측정 cycle에 묶어야**(고정 nominal split 아님 — 내 contact-phase 미스매치의 원인).

## ★ Siekmann periodic reward (구현)
다리별 phase φ_i (L=φ, R=φ+0.5; 공유 clock):
- **swing 구간**: 발 force 벌점 (expected ‖F‖≈0).
- **stance 구간**: 발 속도 벌점 (expected ‖v_xy‖≈0).
- smooth (von Mises/sigmoid) phase indicator, swing:stance ≈ **40:60**, cycle ≈ **100-120 steps/min**(T≈1.0s).
- ★ phase는 **clock(obs) + 실제 contact에 re-sync** (고정주기 미스매치 방지).
효과: 깨끗한 stance(planted·loaded·flat)/swing → 까치발 단축경로 제거 + 절뚝 구조적 억제. 검출: toe-off가 ~60% phase로 수렴, stance:swing→60:40.

**우리 구현**: clock obs `[sin2πφ, cos2πφ]`(+2 dim, fresh train) + reward `mean_feet[ I_stance(φ)·exp(-k_v·‖v_xy‖) + I_swing(φ)·exp(-k_f·‖F‖) ]` (positive, weight ~+1.5). I_swing=σ(s(φ-0.6))·σ(s(1-φ)), I_stance=1-I_swing.

## 단계 계획 (보고서, 검출지표 §H)
- **Stage0 (유지)**: base_height(-1.0@0.85, ±2-3cm 밴드 허용) + velocity track(dominant).
- **Stage1 (최고레버리지, 지금)**: ★ **Siekmann periodic contact** + clock obs. swing_height/foot_flat 제거(periodic이 대체). 검출: toe-off~60%, stance:swing 60:40, 까치발 사라짐.
- **Stage2**: **symmetry loss**(Abdolhosseini LOSS: ‖π(s)−M_a π(M_s s)‖) + 공유 clock. 검출: GRF asym 0.83→>0.95, 8×BW spike 제거.
- **Stage3**: impact cap `−k·max(0,F−F_lim)`(soft ~700-900N, hard 1.5kN; BW=508N) + energy `−k·|τ·q̇|`(소, track 종속). HW 1.5-2.7kN 준수.
- **Stage4**: stride(feet_air_time/stride-length, cadence 100-120·hip ROM↑) + push-off(**terminal-stance(40-60%) gated ankle-power burst**, un-timed toe-deflection 아님 → passive toe windlass 작동).
- **Stage5 (naturalness 부족 시)**: DeepMimic-lite reference(phase=측정contact, imitation weight↑). AMP은 rsl_rl 비호환이라 보류.

## 핵심 수치 타깃/검출 (biomech §H)
stance:swing 60:40·double-support 20-24% · cadence 100-120 · hip ROM ~40°(우리 ~30%=짧음) · knee swing peak ~60° · ankle 5-10°DF→20°PF@toe-off · GRF double-hump 1.0-1.2BW(running만 2-3BW; 우리 8×BW=절뚝/충격) · ankle push-off = 최대 power(~45%, ~2.8-4.5 W/kg)@40-60% · CoP heel→toe(heel-off 30-40%, toe-off 60%) · GRF L/R asym→1.0.

## 주의 (보고서 caveat)
- morphology 전이: Siekmann/energy 결과는 Cassie(경량·toe無)/quadruped — **메커니즘은 전이, 상수(cycle·swing:stance·energy weight)는 재튜닝**.
- reward-hacking: force 벌점은 soft-contact 악용 가능 → **absolute work + threshold impact** 사용.
- energy 단독은 우리 로봇엔 speculative; **energy + 기하 + phase scaffold**가 well-supported. 각 단계 §H로 검증 후 다음.
- 팔 없음 → arm-swing 창발 이득 없음(하체 전용).

## refs (보고서 1차출처)
Siekmann 2011.01387(periodic contact, Cassie s2r) · Heess 1707.02286 · van Marum 2404.19173(regularizers·feet_air_time) · Fu 2111.01674(energy→gait, quadruped) · Margolis 2212.03238 · Radosavovic Sci.Robot eadi9579/2303.03381(energy→arm swing) · Peng DeepMimic 1804.02717·AMP 2104.02180 · Abdolhosseini 2019(symmetry DUP/PHASE/LOSS/NET)·2410.12983(mirror 비판) · Reda 2107.06629(impact penalty) · Kuo/Donelan(inverted pendulum·collision work) · Collins/Ruina Science 2005(passive dynamic) · Winter·Perry(biomech 수치). 내부 [[2026-06-29_human_gait_reference]]·[[2026-06-29_tiptoe_regression]].
