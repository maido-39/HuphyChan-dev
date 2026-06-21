# index — LLM Wiki 카탈로그

> 전 wiki 페이지의 카탈로그(임베딩 없이 검색). 매 ingest마다 갱신([[SCHEMA]]). 운영 메모리는 `memory/MEMORY.md`.

## 운영 (먼저 읽기)
- [[SCHEMA]] — 위키 규약·층·ingest 워크플로우 · [[log]] — ingest 타임라인 · [[raw/README]] — 검증 원문층 · [[RESUME]] — 현재 상태/재개점

## 주제 노트 (concepts)
- [[00_overview]] 개요 · [[01_install]] 설치 · [[02_asset_conversion]] MJCF→USD · [[03_environment]] env · [[05_sensing_logging]] 센싱·로깅 · [[06_teleop]] 키보드(WASD·가속·댐핑) · [[07_measurement]] 측정 · [[08_robot_hotswap]] 로봇 교체 · [[09_gpu_driver_fix]] 드라이버 · [[10_gpu_perf_tuning]] GPU 성능
- **보상/gait**: [[04_reward_experiments]] 보상 레퍼런스 · [[11_research_gait_rewards]] · [[22_energy_toe_reward]] 에너지·toe · [[27_training_review_loop]] 검토·보수적중단 · [[28_reward_actuator_fidelity]] 열/torque-dist·Shin·RobStride · [[29_natural_gait_reward_hw]] ★자연gait 레시피+HW(4질문)
- **toe/발**: [[12_toe_stiffness]] · [[15_toe_joint_research]] · [[17_toe_usage_vibration]] · [[19_toe_ablation]] · [[23_toe_use_methods]] toe-use(산업/최신/직접보상)
- **HW/사이징·생체역학**: [[20_fusion360_isaaclab]] · [[21_motor_power_weight]] 모터·파워·무게 · [[30_knee_biomechanics]] 무릎(과신전·굽힘자세) · [[31_humanoid_hw_comparison]] 실제로봇 HW비교(질량·댐핑→흐물거림 판정) · [[32_actuator_damping]] 액추에이터 댐핑(RobStride Kd·g²·토크요구)
- **지형/전이**: [[13_sim2real_height_scan]] · [[14_heightmap_survey]] · [[16_dr_expansion]] DR확장
- **분석/계획**: [[24_training_health_analysis]] 학습건강도+모터viz(RMS/p95/peak) · [[18_research_roadmap]] 로드맵 · [[experiment_queue]] ★실험큐(toe-roll/충격/gait) · [[25_dayplan_2026-06-21]] 일일계획 · [[26_reading_list]] 리딩리스트v2(검증) · [[99_troubleshooting]]

## 논문 리뷰 (verified) — [[Paperreview/INDEX]]
- [[Paperreview/kuo-donelan-dynamic-walking]] Kuo 전이-에너지 캐논 · [[Paperreview/siekmann-periodic-reward]] 주기보상 · [[Paperreview/margolis-rapid-locomotion]] · [[Paperreview/radosavovic-humanoid-transformer]] · [[Paperreview/caps-smooth-control]] · [[Paperreview/toe-stiffness-optimization]]

## 실험 (runs) — [[experiments/INDEX]]
- [[experiments/2026-06-21_01-52-57_flat_wide_dr]] stage-2 넓은DR · [[experiments/2026-06-21_03-46-50_stage3_ankle_offload]] stage-3 발목offload · [[experiments/2026-06-21_06-41-42_stage4_rough]] stage-4 rough · [[experiments/2026-06-21_12-22-03_forefoot_cop]] forefoot CoP(H-A 음성)
- 모니터로그: [[experiments/2026-06-21_12-22-03_forefoot_cop_monitor]] · [[experiments/2026-06-21_16-30-58_forefoot_pushoff2_monitor]] (Kuo push-off, 진행중)
- 보고: [[MIDREPORT_2026-06-21_1100]] 중간보고

## 운영 메모리 (별도 — memory/MEMORY.md)
샌드박스·리포트규칙·중간검토규칙·누적영상+영상프레젠테이션+메타룰(구현→rule→자동화→verify)·GitHub·RAM22GB.
