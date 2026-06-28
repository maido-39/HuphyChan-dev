# 50 · Flat→Rough 이전 학습 방법론 (검증 연구)

> 연구: 워크플로 `rough-transfer-research` (w9y3zyihr, 17 agent, 43 findings, adversarial verify 2/12 confirmed + 상세 caveat). 목적: task#6(Rough 이전)을 HW 저충격(1.5-2.7kN) 목표에 맞게 안전 수행. 규칙 [[feedback-research-recording-rule]]. 원본 결과: 워크플로 출력(JSON, /tmp tasks/w9y3zyihr.output). ★ 이 노트는 **사람-gait 우선** 일단락 후 task#6 실행 시 참조용(좋은 flat 정책 확보 후).

## ★ 핵심 (실행 레시피)
1. **Resume = policy-weights only**: `run_training.sh ... --init_checkpoint <flat.pt>` → `train.py:223-228`이 `runner.load(..., load_optimizer=False)` + `current_learning_iteration=0`. flat gait를 warm-start teacher로 재사용, optimizer state는 버려 망각 방지. **우리 stage-4가 이 패턴으로 성공**(512→256 dims 수정 후).
2. **망 차원 flat↔rough 일치 필수**: `[256,128,128]` 양쪽 동일(stage-4는 512 불일치로 최초 실패). obs(239)·action(12) 불변이라 입력/출력층 일치.
3. **obs 불변**: flat에도 height_scan(187) 켜둠 → 239-dim이 rough로 그대로 전이(우리 flat_env_cfg가 이미 이렇게). obs는 절대 바꾸지 말 것.
4. **DR 범위 flat=rough 동일**: friction(0.4-1.25/0.3-1.0)·mass±5kg·COM±5cm·push±0.8 — 동일 유지(다르게 하면 distribution shift=망각). stage-4/5 성공 이유.
5. **reward 초기 유지**: 전이 후 **500-1000 iter는 flat reward 그대로**(망 height_scan 재해석 시간 필요). plateau시에만 retune. stage-5 교훈: 이른 reward 변경이 local minima 유발.
6. **iter 예산 3000-4000**(flat 1500의 2.5-3배 — terrain 탐색+command ramp+gait 재보정).
7. **error_vel 상승은 정상**: rough서 flat 대비 40-100%↑ (flat 0.2-0.5 → rough 0.9-1.1). <1.0 성공·1.0-1.5 허용·>1.5 커리큘럼 과격.

## ★ HW 저충격용 terrain 설정 (우리 목표 특화)
`ROUGH_TERRAINS_CFG`(IsaacLab, `terrains/config/rough.py`): 10 rows(난이도)×20 cols(타입), 6 sub-terrain(stairs/inv-stairs/boxes/random_rough/slopes). 난이도 = `(row+η)/num_rows` **선형보간**.
- ★ **stair step_height 캡**: 기본 `step_height_range=(0.05, 0.23)` → 0.23m 계단은 **2kN 초과 위험**. **상한 0.15·하한 0.03-0.04**로 낮춰 worst-case 충격 제한(step_height = low+diff·(high-low), 선형).
- **random_rough 비중↑** vs stairs↓ (예 0.2→0.3 / 0.2→0.1), `noise_range=(0.02,0.10)→(0.02,0.06)`.
- **max_init_terrain_level 5→2(또는 1)**: spawn을 쉬운 row로 제한(`randint(0, level+1)`). 단 ★ **caveat: ROUGH엔 평지 자체가 없음** — row 0도 η>0이라 ~5cm 계단+2cm noise → max_init↓만으론 완전 평지 warm-up 안 됨. 진짜 부드럽게 하려면 step_height **하한**도 낮춰야.
- ★ **curriculum=False가 기본**: `terrain_levels` 커리큘럼을 명시적으로 wire 안 하면 난이도가 (0,1) 전체서 샘플 → peak step 항상 등장. **step_height_range 상한 캡이 가장 확실한 충격제한 레버**.

## caveat (verify가 잡은 부정확)
- 클래스명 정확히: `MeshPyramidStairsTerrainCfg`/`MeshInvertedPyramidStairsTerrainCfg`(ROUGH의 stairs는 **Mesh** 변종, Hf 아님)·`MeshRandomGridTerrainCfg`.
- `terrain_levels_vel`엔 `ramp_steps` 인자 **없음**(distance-gated: move_up = dist>size/2). 느린 ramp 원하면 custom 커리큘럼 항 필요.
- `slope_threshold=0.75`는 라디안 아닌 **무차원 gradient**(rise/run).
- row=난이도, col=타입 — "row 0-2=평지" 매핑은 **틀림**(모든 row가 6 타입 다 포함, row 0도 충격 위험).
- 우리 generator가 실제 8×8 grid(10×20 아님)일 수 있으니 row-count 가정 전 확인.

## 측정 (rough PLAY 시)
foot별 **peak GRF vs 1.5-2.7kN** + loading rate · ankle_roll(DM-J4340 9/27)·ankle_pitch RMS/p95/peak · incline별 ankle-knee 토크비 · row별 낙상률 · height_scan dropout 강건성 · RMS 토크 열마진 · vel 추종오차. = HW 사이징은 rough 충격 포함해 재측정.

## 위험
0.23m 계단 2kN 초과(generator 범위 캡 필수) · ankle_roll flat서 이미 포화 → rough서 악화 · height_scan 과의존(sim2real 갭) · flat ckpt 대비 reward drift · 망각 방지 위해 LR(1e-3)/entropy(0.008) 유지.

## refs
- IsaacLab `terrains/config/rough.py`(ROUGH_TERRAINS_CFG step_height 0.05-0.23) · `terrain_generator.py:247-257`(difficulty 선형) · `terrain_importer.py:329-348`(max_init_terrain_level) · `mdp/curriculums.py`(terrain_levels_vel, ramp 인자 없음).
- 우리 `train.py:223-228`(policy-only load) · `velocity_env_cfg.py` BipedRoughEnvCfg · `rsl_rl_ppo_cfg.py`([256,128,128]) · [[experiments/stage4_rough]]·[[experiments/stage5_rough]](전이 성공/수렴 교훈).
- Margolis RSS 2022(command curriculum, https://www.roboticsproceedings.org/rss18/p022.pdf) · Lee 2020 Science Robotics(height-scan teacher→blind, arxiv 2010.11251) · Kumar RMA 2021(arxiv 2107.04034) · 내부 [[16_dr_expansion]]·[[13_sim2real_height_scan]]·[[14_heightmap_survey]].
