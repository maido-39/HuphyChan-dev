# log — ingest 타임라인 (append-only)

> 형식 `## [YYYY-MM-DD] <kind> | <제목> → <페이지>`. kind = research / experiment / decision / fix. 매 ingest마다 append([[SCHEMA]]). 최신이 위.

## [2026-06-21] research | knee 액추에이터 landscape(womafnnro) — 저감속 QDD(Cheetah 5.8~7.67·Berkeley 9·MIT Humanoid 12) vs SEA(Cassie 16); J_ref=J_r·N²(Wensing 2017); RS04 직결=9:1 정통, M107만 저감속 토크밀도 우위(단품X) → [[33_knee_actuator_landscape]] · [[raw/knee-actuator-landscape]]
## [2026-06-21] research | CoP/contact 보상공식 검증(wyvmh4gpv) — ★ Siekmann/Walk-These-Ways 모두 CoP/ZMP/heel→toe 보상 없음(foot-force·velocity norm을 위상클록 게이트), heel→toe CoP-progression은 표준공식 아님 → [[34_cop_contact_rewards]] · [[raw/cop-contact-reward-formulas]]
## [2026-06-21] research | 실제 휴머노이드 HW 질량/세그먼트/PD 비교(wr1cz09bp) — 다리질량 정상(=H1), 흐물거림=무릎 underdamped → [[31_humanoid_hw_comparison]] · [[raw/humanoid-hw-specs]]
## [2026-06-21] research | RobStride 컨트롤러 Kd·감속비 댐핑 산정(w2pkt68gl) — RS03/04 Kd≤100, joint_Kd=motor_Kd×g², 무릎 belt 1:2.5 → [[32_actuator_damping]] · [[raw/robstride-datasheet]]

## [2026-06-21] decision | LLM Wiki(Karpathy) 채택 → [[SCHEMA]] · [[index]] · [[log]] · [[raw/README]] + lint_docs.sh
## [2026-06-21] research | knee biomechanics 학술조사(wsx14ecd0) — ★ live spec엔 이미 flexed nominal(knee −22.9°); 과신전+10°/L-R 비대칭은 결함 → [[30_knee_biomechanics]] · [[raw/knee-biomechanics]]
## [2026-06-21] research | passive-toe 자연gait deep(w3g1xw9oq, reward레시피·HW·toe효율·둥근뒤꿈치) → [[29_natural_gait_reward_hw]]
## [2026-06-21] experiment | forefoot_pushoff2 (Kuo push-off w0.5/scale0.02/cap80, 해킹수정) → [[experiments/2026-06-21_16-30-58_forefoot_pushoff2_monitor]]
## [2026-06-21] fix | push-off reward-hacking(scale0.1→0.02+cap) + 영상 로봇수(env_spacing 8→15+origin_env, 프레임검증) + debugging loop verify_run.sh
## [2026-06-21] research | reward(power/thermal/torque-dist)·Shin actuator-clip·RobStride 데이터시트(wyilgvpyj) → [[28_reward_actuator_fidelity]]
## [2026-06-21] decision | RMS·p95·peak 토크 메트릭(ankle_roll RMS%rated 151% 열과부하) → [[24_training_health_analysis]]
## [2026-06-21] research | Kuo/Donelan/Ruina dynamic-walking 캐논(검증) → [[Paperreview/kuo-donelan-dynamic-walking]]
## [2026-06-21] research | 리딩리스트 v2(19편 fetch검증, 대가랩) → [[26_reading_list]]
## [2026-06-21] research | 건전 학습메트릭+보수적 중단(we12yjosz) → [[27_training_review_loop]]
## [2026-06-21] experiment | forefoot_cop (CoP@0.5, H-A 음성=toe 미적재) → [[experiments/2026-06-21_12-22-03_forefoot_cop]]
## [2026-06-21] research | 직접vs간접 toe보상(whirkj8ws: 직접=anti-pattern) → [[23_toe_use_methods]]
## [2026-06-21] experiment | stage-2~4 (넓은DR·발목offload·rough) → [[experiments/INDEX]]
## [2026-06-21] report | 11시 중간보고 → [[MIDREPORT_2026-06-21_1100]]

## 2026-06-21 · RS04 공식 T-N 곡선 검증 (리서치)
- 공식 RobStride GitHub `Product_Information/Product Literature/RS04/RS04User Manual260428.pdf`(85pp) 직접 다운로드·pdfimages 추출.
- **§12 T-N curve**: 출력축 곡선 90~190rpm 표시, 전구간 단조감소(95rpm=120N·m peak → 150rpm 변곡 → 190rpm ~10N·m, no-load 200). 평탄(constant-torque) corner ≤~95rpm. **OpenELAB 리셀러 "flat to 100rpm" 요약 부정확 확정.**
- **§13 회전 과부하 듀티표**(50rpm, 345mm 방열판): 120N·m=3s … 50=324s, 40=rated. **§14 스톨 듀티표**(1.414× 발열): 120=1s … 50=74s, 28.5=rated.
- 정격(연속) 40N·m@100rpm(345mm) / 35(220mm), peak 120N·m@90Apk. 무게 1420g, Φ120×56. peak 토크밀도 84.5 N·m/kg.
- ❌ 효율맵 미공개(공식 매뉴얼·스펙PDF 전수 grep). 3rd-party bench 공개데이터 없음.
- 곡선 이미지 → `assets/rs04_tn_curve_official.png`·`rs04_overload_{rotating,stall}_official.png`. 정리 → [[robstride-datasheet]], 함의 → [[21_motor_power_weight]].
