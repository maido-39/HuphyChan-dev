# 자연스러운/효율적 보행 emergence — reward 레시피 + HW + 검증 (연구 w3g1xw9oq)

> [!abstract] 당신의 체감 관찰 → 검증된 보상/HW
> 4질문(emergent 조건·관찰→reward(hacking 없이)·toe가 정말 효율↑?·둥근 뒤꿈치?)에 fetch·검증 기반으로 답. 핵심: **원인을 보상**(push-off 일·collision·에너지·smoothness)하고 **toe·접촉시간·COM은 부산물로 emerge**시킨다. toe는 **부하를 발목으로 *전이***(free lunch 아님).

## Q1+Q2 — reward 레시피 (랭크 + 수식 + hacking 가드)
| # | 항 | 수식 | reward-hacking 가드 |
|---|---|---|---|
| 1 | **track_lin/ang_vel (지배 유지)** | exp(-‖v_cmd−v‖²/0.5²), w 1.0/2.0 | **모든 페널티 합 < 추종 크기.** 모든 smoothness/energy/impact 항은 *정지/freeze*서 최소화됨 → 추종이 최대 양수항이어야 "정지"가 최적이 안 됨. **achieved/cmd 속도비 >0.85 감시**(떨어지면 그 항이 과함). |
| 2 | **ankle_pushoff_work (toe 적재 1차 lever)** | +0.5·Σ_feet clamp(τ_ankleP·ω_ankleP, 0, **cap 80**)·gate(종말 단일지지+전진), **scale 0.02** | ★ Kuo 인과 타깃. forefoot_cop은 *상관(GRF비율)*만 보상→실패. push-off **일**이 상류 원인(Malcolm: hip work −49% swing 보조). 해킹: (1)발목 진동 farming→**엄격 게이트+cap**이 차단 (2)격한 toe-off→**cap+no_flight**. **power_cot와 병행**(net-energy 절감 크레딧). *내 scale 0.1·cap無가 해킹됨(reward 324)*. |
| 3 | **Siekmann 주기 접촉 (push-off로 부족 시 fallback)** | swing서 foot FORCE 페널티·stance서 foot VELOCITY 페널티, von-Mises 평활, clock을 obs에 | 참조궤적 없이 heel-to-toe 굴림 스케줄. stance서 발속도≈0 강제→GRF로 수동 toe(k60) 적재 *구조적으로*. **관찰(i) 짧은/점접촉·발 slap 직접 수정**. 가드: phase **hard-clip 금지**(von-Mises 평활이 안정·anti-chatter), duty는 **soft 타깃**(모방 강요 금지). |
| 4 | **power_cot (에너지 압력, 유지)** | exp(−0.003·Σ\|τ·ω\|/(σ\|v_cmd\|+0.1)), w 0.4 | Fu: 파워패널티+추종=자연 gait. 속도정규화=anti-degeneracy(정지 안 free). forefoot_cop run서 **작동**(knee RMS 58→35·ankle_roll RMS%rated 151→113). 단 12관절 합이라 **toe 단독 적재 불가**(toe는 합 밖). 가드: **\|τ·ω\| 절대값**(signed는 회생제동 artifact), **가중 anneal**(초반 30-40% ~0→ramp; 큰 고정가중은 0-action 붕괴). |
| 5 | **action smoothness: action_rate(1차, 유지) + ★2차 jerk(신규)** | −0.008‖aₜ−aₜ₋₁‖² **+ −w₂‖aₜ−2aₜ₋₁+aₜ₋₂‖²** (+옵션 CAPS spatial) | CAPS: **파워 −80%·smoothness +96%** 실HW. **관찰(iii) "관절 고주파 안씀" 직접 수정**. repo 결함: action_rate가 1차뿐(>5Hz: knee40%·toe41%). 가드: **modest 가중**(모든 accel항 최소=frozen), push-recovery(±1.2 push)로 검증, FFT로 >5Hz 감소 확인. |
| 6 | dof_acc(전관절, 유지)+dof_torques(유지) | −1.25e−7·Σq̈²·−1.5e−6·Στ² | anti-jitter 바닥. 가드: **toe 운동 페널티 금지**(toe는 변형이 목적·과감쇠 ζ2.9), 전역 τ² 올리지 말 것(발 stiffen=ECO BRUCE 실패). |
| ✗ | **금지: 직접 \|τ_toe\| / raw forefoot_cop을 1차 lever로** | — | 보상해킹(정적 curl). 굳이 쓰면 **PBRS(potential-based)만**. |

## Q3 — passive toe가 정말 토크↓·효율↑? **조건부 YES, 단 *부하 전이*(free lunch 아님)**
- **토크: 견고** — Cho 2025: 9링크(toe) vs 7링크 = 총제곱토크 **−59%**(단 게임가능 목적값). **SURENA III(실HW): net 발목에너지 −15.3%·무릎 −9.0%**.
- **그러나 부하가 *발목으로 전이*** — 단단한 toe서 무릎/hip heel-off 토크↓ 하나 **발목 토크/파워↑**. **우리 forefoot_cop run서 확증**: ankle_pitch RMS 9.3→12.6↑.
- **net 에너지는 미보장**(제곱토크≠대사CoT). → **발목 액추에이터 size UP**(다운사이즈 금지), toe로 무릎은 덜어짐.

## Q4 — 둥근 발뒤꿈치? **YES, 단 *modest·bounded* (2차 lever)**
- Adamczyk/Kuo: 둥근 roll-over arc가 **step전환 collision 일↓**(가장 작은 arc=가장 큰 것의 2.37배 비용), 대사 최소 ~**0.30 다리길이** 반경. → **관찰(ii) 부드러운 COM 전이**를 줌.
- **단 발 *길이* 통제 시 반경 단독은 통계 비유의**(Adamczyk/Kuo 2013). = heel 라운딩은 초기 stance CoP 굴림엔 도움이나 **2차 lever**; 1차는 **발 길이 + push-off**.
- → **modest 라운딩 + 뒤꿈치는 FIRM 유지**(compliance는 toe 스프링에만).

## HW 설정 요약
- **toe 강성 k=60** 유지(Cho 인간최적 56-60), 댐핑4·armature0.008 유지(올리지 말 것). ablation서 30-60 sweep.
- **분절발(foot_link+toe_link) 유지**, toe pivot ~0.19m 전방. sim서 CoP가 heel→toe 진행 검증.
- **뒤꿈치 modest 라운딩**(0.3L arc, FIRM).
- **ankle_pitch PD 부드럽게**(kp 80→~50, kd 3) + **발목 액추에이터 size UP**.

## 다음 실험 (연구 권장 = 지금 적용)
ankle_pushoff_work **w0.5·scale0.02·cap80**(해킹수정) + power_cot0.4 유지 + forefoot_cop은 **진단용 로깅**만. **config-test FIRST**(reward O(0.1-1)·L/R 순서·게이트가 종말 단일지지서만). + 2차 jerk 항 동시. warm-start stage-3/forefoot. → 측정서 toe 적재(앞발 GRF·toe RMS) + **발목으로 전이된 부하** 확인.

관련: [[Paperreview/kuo-donelan-dynamic-walking]] · [[23_toe_use_methods]] · [[28_reward_actuator_fidelity]] · [[26_reading_list]] · [[27_training_review_loop]]
