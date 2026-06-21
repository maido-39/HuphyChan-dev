# log — ingest 타임라인 (append-only)

> 형식 `## [YYYY-MM-DD] <kind> | <제목> → <페이지>`. kind = research / experiment / decision / fix. 매 ingest마다 append([[SCHEMA]]). 최신이 위.

## [2026-06-21] decision | LLM Wiki(Karpathy) 채택 → [[SCHEMA]] · [[index]] · [[log]] · [[raw/README]] + lint_docs.sh
## [2026-06-21] research | knee biomechanics 학술조사(wsx14ecd0, ROM/과신전·gait·screw-home·로봇설계) → [[30_knee_biomechanics]] (작성 예정)
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
