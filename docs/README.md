# 🦿 Human-Pygmalion 문서 (Obsidian Vault)

하반신 이족 로봇 **사람형 보행 학습 + 하중 측정** 환경 구축 노트.
각 노트는 **왜 / 무엇을 / 어떻게 / 어디서**로 구성. 이미지는 `assets/`.

> [!important] 노트 작성 표준 (research) — 개인 학습용(비배포)
> 1. **소스**: 모든 주장/정보는 **신뢰소스 2개 이상 또는 인터넷 소스 5개 이상**으로 뒷받침(논문·공식문서 우선).
> 2. **이미지(필수)**: 이해를 돕는 시각자료 반드시 포함 (저작권 안전 순서) —
>    (a) **자작 개념도**(`assets/<note>_*.svg`) — 자유롭게 임베드(1차 수단).
>    (b) **자유 라이선스 이미지**(Wikimedia Commons CC/퍼블릭도메인 등): 출처·라이선스·저자 캡션과 함께 `assets/`에 저장·임베드.
>    (c) **논문 figure는 assets/ 에 저장 후 임베드**" : `assets/figures/{PAPERNAME}/{PAPERNAME}-fig.X` 에 저장 후, `![[{PAPERNAME}-fig.X]]` 형태로 링크(임베딩)
> 3. 모든 그림 = 출처 캡션 + 해당 주장도 §출처로 교차검증.
> 4. **레퍼런스 = point 리스팅**: 한 줄에 `- [하이퍼링크](url) — 간단한 논문 설명. **왜**: 왜 보면 좋은지`. 인라인 나열 금지.
> 5. **중요 논문 = 리뷰까지**: 프로젝트 결정에 핵심인 논문은 `Paperreview/<slug>.md`에 구조화 리뷰(문제·방법·핵심수치·우리 프로젝트 관련성·왜읽기·한계·우리적용) 작성하고, 해당 노트의 레퍼런스에서 `→ 리뷰 [[Paperreview/<slug>]]`로 링크. 색인은 [[Paperreview/INDEX]].

## 읽는 순서 (MOC)
1. [[00_overview]] — 프로젝트·로봇·시스템 개요, 핵심 결정
2. [[01_install]] — conda + Isaac Sim 5.0 + Isaac Lab 2.2 (Blackwell)
3. [[02_asset_conversion]] — MJCF → USD
4. [[03_environment]] — velocity locomotion env 구성
5. [[04_reward_experiments]] — reward trial-and-error 로그
6. [[05_sensing_logging]] — 토크/축력(x,y,z 반력)/GRF 센싱·로깅 (★산출물 핵심)
7. [[06_teleop]] — 키보드 조작 + HUD
8. [[07_measurement]] — 측정 캠페인 + 분석 (하드웨어 설계용)
9. [[08_robot_hotswap]] — 로봇/질량/관성/관절구조를 YAML 한 파일로 교체+재학습 (★자주 바꾸는 작업)
10. [[09_gpu_driver_fix]] — PhysX GPU 폴백(Blackwell 드라이버) 해결
11. [[10_gpu_perf_tuning]] — GPU 활용 최적화(num_envs↑ → util 90%)
12. [[11_research_gait_rewards]] — 리서치: 주파수영역 gait reward 비판평가
13. [[12_toe_stiffness]] — 리서치: passive toe 강성(찰싹임 해결)
14. [[13_sim2real_height_scan]] — sim2real: height_scan 없이 실기기 배포
15. [[14_heightmap_survey]] — 서베이: 보행로봇 heightmap 처리 기술(47 refs)
16. [[15_toe_joint_research]] — 리서치: toe 관절 sim 모델링·sim2real(armature 안정성)
17. [[16_dr_expansion]] — 리서치: DR 확장(속도 2.0·회전 1.57·아스팔트~미끄럼 마찰·강한 외란)+명령 커리큘럼
18. [[17_toe_usage_vibration]] — 데이터+리서치: toe 사용도(8%→26%)·발 진동(발목 가속도 규제)·passive toe 논문/보상
19. [[18_research_roadmap]] — ★연구 로드맵: HW 설계(조인트/연결부 사이징) + 자연/효율 보행
20. [[19_toe_ablation]] — Toe ablation 실험설계 + 메트릭(CoT·ankle offload·GRF충격·구조wrench)
21. [[20_fusion360_isaaclab]] — Fusion360 → URDF/MJCF → USD 연동 + 함정 체크리스트
22. [[21_motor_power_weight]] — 모터/감속비·부위별 W·무게/페이로드 민감도 (HW 사양)
23. [[22_energy_toe_reward]] — 에너지/토크 reward로 toe 적재+발목 offload (★순수에너지론 toe 안실림, 레시피)
24. [[99_troubleshooting]] — 문제·해결 로그
- [[Paperreview/INDEX]] — 핵심 논문 리뷰 색인 (커리큘럼·주기보상·toe·액션평활·강성)
- [[experiments/INDEX]] — 학습 실험 대장 (trial-and-error 전부)
- [[RESUME]] — 현재 상태 & 재개 지점 (재부팅 대비)

## 산출물 위치
- 코드: `../pygmalion_locomotion/` (분리 워크스페이스)
- 폴리시/로그: `../pygmalion_locomotion/logs/`
- 측정 그래프/통계: `assets/*_analysis.md`, `*.png`, `*_stats.json`

## 진행 현황 (2026-06-20)
- [x] Phase 0: conda + torch cu128(Blackwell 검증) / Isaac Sim 5.0 · Lab 2.2 설치
- [x] **GPU 드라이버 570.195.03** (Blackwell PhysX GPU 해결 — [[09_gpu_driver_fix]])
- [x] Phase 1: MJCF→USD 변환 (worldBody 버그 수정)
- [x] Phase 2~3: velocity env(평지/계단/울퉁불퉁/경사) + cmd_vel + 외란 + **로봇 핫스왑 spec(질량/관성)**
- [x] **Phase 4: 학습 수렴** — Mean reward +41.9, **episode length 990/1000, error_vel_xy 0.25** (사람다운 보행, GPU 1500 iter)
- [x] Phase 5: 센싱(토크/6축반력/GRF) 실데이터 로깅 ✅
- [x] Phase 7: **측정+하드웨어 분석 실데이터** (모터 util%: 발목·고관절롤 100% 포화, 무릎 과설계 — [[07_measurement]])
- [~] 진화 영상(record_progress) / 키보드 조작(play_keyboard) — 생성·검증 중
- [~] rough(계단/경사/disturbance) 측정 — 다음
