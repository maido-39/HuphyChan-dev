# 2026-06-29 · toe-use reward 설계 — 학술 근거 (passive windlass = 원인 보상, 직접 toe 금지)

> 트리거(user): "toe를 사용/emergent하게 하는 reward의 학술자료." 검증 워크플로 `toe-use-reward-research`(w2cauzd19, 17 agent, 36 findings, adversarial verify). 규칙 [[feedback-reward-research-rule]]. v9(Stage4 toe-use) 구현 근거.

## ★ 핵심 결론 — INDIRECT (원인 보상, toe 직접 X)
toe는 **passive windlass**(Hicks 1954): MTP 굴곡 → 족저근막 긴장 → 아치 ~0.5-1.0cm 상승 + 탄성 강화 → push-off 레버. **우리 1-DoF passive toe 스프링(k≈60 N·m/rad, 인간 56-60 일치)이 곧 그 메커니즘** → **능동 제어/직접 보상 금지**.
- ★ **`|τ_toe|` 보상은 반-패턴**: passive라 τ=k·deflection = roll의 *상관*일 뿐 + **정적 toe-curl로 game 가능**(over-damped toe라 held curl이 쌈). v5(toe_load_stance)서 **굽힘 magnitude만↑, timing은 그대로** = 정확히 이 실패.
- ★ **올바른 gradient = 하중(forefoot GRF / CoP)**: CoP가 terminal stance서 forefoot로 진행하면 windlass가 **emergent**. = 원인을 보상, toe는 byproduct.

## ★ 추천 stack (순서 = hard 전제)
1. **BACKBONE = Siekmann `periodic_contact` + `clock_phase`** (=v8, 완료) — stance/swing 리듬 legislate → mid-swing 관성 toe-bend(우리 실패모드) 제거. **foot-roll의 전제.**
2. **THEN `ankle_pushoff_work`(+0.5)** (rewards.py:142) — terminal single-support서 (+)plantarflexion power = **CoP를 앞으로 미는 엔진**(Kuo 2002, Adamczyk-Kuo 2013). clamp(τ_ankle·ω,0,80W)·gate.
3. **THEN `cop_progression`(+1.2)** (rewards.py:287) — `frac=Fz_toe/(Fz_foot+Fz_toe)`가 stance 통해 **상승**할 때 보상(temporal). ★ contact-time proxy 대신 **Siekmann clock terminal-stance window(phase 0.45-0.6)로 re-gate** 권장.
4. (roll 깨끗해진 뒤) `power_cot`(+0.4, 에너지, velocity-정규화로 stand-still 방지).
- ★ **DO-NOT-ADD `toe_load_stance`** — 직접-toe 반패턴, deprecate.
- **주의**: bare `forefoot_cop`(정적 분율)은 v6서 **0.06%**로 너무 약했음 → **반드시 temporal(cop_progression) + push-off power와 pair**. 단독 GRF-분율은 불충분.

## 발 기하 (geometry)
- 평발 coplanar rake로도 **3rd-rocker(forefoot rollover)는 contact-sequencing + ankle plantarflexion으로 emerge**(곡면 불필요). 
- 곡면/분절 sole은 **최적화**(필수 아님): 반경 ~0.3×leg가 충돌일 **-20~40%**, 강체발은 **+59%**(Adamczyk & Kuo 2013). 향후 옵션.
- ★ caveat: 우리는 **아치/족저근막 없음** → windlass의 **energy-return 절반(아치 상승)이 없어 push-off 이득 muted**(toe-스프링 절반만). toe 단독 이득 제한적(docs/17 일치).

## 주의 (verify가 잡은 함정)
- ★ **robot.xml toe `stiffness=20`(stale, 인간의 1/3)** → 학습엔 **YAML robstride_biped.yaml `toe_passive: stiffness 60`이 override(active)**. 60이 맞으나 robot.xml의 20은 stale 함정 — 정리 필요.
- ★ **toe sole flush**: toe 캡슐 z≈-0.0598이 발바닥과 같은 높이 → flat stance서도 toe 항상 접촉 → **forefoot-fraction 신호 약함**. cop_progression 약할 시 toe를 약간 forefoot-distinct하게.
- **ankle_roll(RS00) 재포화**: push-off + 날카로운 roll이 이미 포화된 ankle_roll 재부하 → §7 감시.
- **Siekmann period(1.0s) mismatch**: command-velocity 의존 cadence와 충돌 가능 → 추종 안되면 period 속도적응.
- **over-constraint**: periodic_contact+cop+pushoff+gait_reference 동시 stacking은 over-determine → 단계적 추가.

## 검출 (detectors)
- ★ **toe-angle timing**: L/R_toe qpos vs gait-phase — SUCCESS = peak dorsiflex가 **push-off(terminal stance ~50-60%)**.
- **CoP path**: forefoot frac vs phase — SUCCESS = stance 통해 **단조 상승**.
- **push-off power timing**: ankle τ·ω vs phase — SUCCESS = terminal-stance **(+)plantarflex power 버스트**.
- **windlass sanity**: toe deflection이 **forefoot GRF와 상관**(swing 속도 아님).
- 툴: `gait_toe_timing.py`·`gait_humanlikeness.py`·`wrench_gaitcycle.py`·§7.

## refs
Hicks 1954(windlass) · PMC6127178·Royal Soc Proc B 288(1943)(fascia extensibility, 비-강체) · PMC8031382(아치 상승 5.6-11mm) · Adamczyk & Kuo 2013(rollover radius, 충돌일) · Kuo 2002(push-off=inverted-pendulum 엔진) · Bojsen-Møller · Sci.Reports 2025 s41598-025-17957-4(toe stiffness ~56-60) · 내부 [[2026-06-29_gait_emergence_siekmann]]·docs/17·docs/23(cop_progression·forefoot_cop)·[[experiments/2026-06-29_13-00-01_siekmann_v8_flat]].
