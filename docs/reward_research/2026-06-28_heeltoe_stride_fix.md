# 2026-06-28 · 까치발+짧은보폭 → 인간형 heel→flat→toe-off reward fix (검증 phased)

> 트리거: g1is_dm4340_flat이 **까치발-shuffle**(노트 [[experiments/2026-06-28_19-55-27_g1is_dm4340_flat]]) + 발목 RMS 200% 포화. 검증 워크플로 `heeltoe-stride-gait-fix`(6 agent, 136 web tool-use, adversarial). 규칙 [[feedback-reward-research-rule]].

## 근본원인 (텐서보드 + 설치코드 검증)
까치발+shuffle = **stride/clearance gradient 부재** + **contact-ordering 신호 부재**. PPO가 속도명령을 *가장 게으른* shuffle(앞꿈치 거의 고정)로 만족. 검증:
- `feet_air_time_positive_biped`은 단일-stance *지속시간*(threshold 0.4s서 clamp)을 보상 — **stride 아님**, +0.0096로 dead(gradient 0). threshold↓는 "스텝 안 함"(IsaacLab Disc#1977) → 잘못된 레버.
- foot-flat/heel-toe/swing-clearance 항이 **하나도 없음** → plantigrade 강제 수단 부재.

## ★ Phase 1 (g1is_dm4340 walking base에 추가; reward만)
1. ★ **ADD feet_swing_height = -20 · Σ(foot_z − h_target)² · (¬contact)** (신규 fn). PRIMARY anti-tiptoe — 까치발은 swing 발 clearance 목표를 물리적으로 못 채움(발 전체를 들어야). **Unitree G1 검증**(g1_config feet_swing_height -20 @0.08; WTW 2212.03238). h_target은 우리 발 기하(foot_link 원점 standing z + ~0.06 clearance)로 config-test 측정해 설정.
2. **DEMOTE feet_air_time 0.25 → 0.0** (G1도 끔; dead 항). threshold 낮추지 말 것.
3. **KEEP 그대로**: feet_slide -0.1, impact층(foot_landing_vel -1.0/foot_impact_force -0.005/knee_straight -5.0), anti-trembling(ankle dof_acc -3e-7/action_rate -0.01), flat_orientation_l2 -1.0(base), track(lin1.0/ang2.0). ★ **impact 항 절대 올리지 말 것** — toe-tap이 힘/속도를 덜 등록해 까치발을 *심화*. stride부터 고치면 impact층이 *부드러운 full-foot 착지*를 유도.
4. (옵션) vel-cmd 시작상한 1.0→0.6 m/s + ramp 연장 — 초기 고속이 shuffle 유발.

★ **clock 결정**: 연구는 G1식 periodic contact-clock(+0.18)도 권고(no-flight 보장 = double-support 겹침; obs에 clock phase 필요). 단 ① obs 변경 ② 블로그/[[2026-06-28_menlo_blog_review]]의 clock-free·비대칭-마스킹 우려와 충돌. → **Phase 1은 swing_height만(no clock, no obs변경)으로 최소 시작**. swing_height는 swing 발만 들게 해 flight 자체를 유도하지 않고 impact층이 flight를 억제 → clock 없이도 가능성 큼. **부족 시(보폭 짧음 or flight 발생) Phase 1b로 contact-clock 추가**.

**GATE(Phase 2 진입)**: 까치발/shuffle 사라짐 + 보폭↑ + error_vel_xy ≤0.25 + 낙상<5% + noise_std 수렴(v7처럼 0.26 정체 아님).

## Phase 2 (GATE 통과 후 *그리고* heel-strike 여전히 없을 때만, 단일 추가)
- **cop_progression +0.3~0.5**(annealed 0→target ~1-2k iter, terminal-single-support gated; v7의 +1.2 아님). 인간 heel→toe rollover를 직접 인코딩하는 유일 항(Hansen roll-over PMC2906615). 평평 5캡슐 sole+passive toe라 기하적으로 실현가능.
- (옵션) foot_flat_orientation **roll_only=True 또는 ≤-0.3**, ★ **cop_progression과 절대 동시 금지**(full-axis foot_flat은 heel-strike/push-off pitch를 막아 CoP roll의 antagonist — v5/v6/v7 실패 원인).

## ★ DROP (재-stack 금지)
lateral_foot_placement·base_height_floor·double_support_bonus·power_cot·ankle_pushoff_work·feet_lateral_separation·forefoot_cop·upright·feet_distance@-3.0 = **v5-v7 12항 동시 stack** = v7 추종 악화(error_vel 0.55)·noise_std 0.26 정체의 주범(foot_flat 자체 아닌 *집합 간섭*; Gait-Conditioned RL 2505.20619). 필요시 측정된 결함에 한해 *늦게·단일*로만.

## 블로그 화해
Menlo minimal-shaping·정책-자가발견은 **따름**(20항 아닌 2항 구조항만). **DEPART**: 블로그 air_time +0.5(=flight 유도, 16kg엔 OK)는 **51.8kg 하중측정엔 치명**(GRF spike) → G1 no-flight 레버(swing_height[+clock])로 대체. 그리고 블로그는 heel-toe 미추구 but 우리는 평평sole+passive toe로 실현가능하니 cop_progression 1개를 *늦게* 추가.

## ESCAPE (Phase 3, hand-shaped가 2-3 단일런 후에도 brittle하면)
AMP/style reward 1개 human walk clip(Peng 2021 2104.02180) — heel→toe 창발, 충돌항 열거 없이.

## ★ v2 (2026-06-28, 사용자 "반영해줘" — Phase1 swing_height 단독 실패 후)
Phase1(swing_height -20@0.12) 실패 원인 2가지 확정:
1. **swing_height가 reward의 ~1%** (track 압도) + h_target≈자연발높이 → 약함. **그리고 swing_height는 swing 발만** → *stance 까치발(발목 plantarflexion)을 못 막음*.
2. ★ **toe_link에 collision geom이 없음**(reward_tuning이 발바닥을 foot_link 5캡슐로 바꾸며 toe collision 제거) → 발끝(=foot_link 앞캡슐)으로 서도 **toe_link는 부하 0 → passive 스프링 안 굽음**("toe 반응 없음"의 진짜 이유; stiffness 60 탓 아님 — 부하만 있으면 25N·m/60=~24° 변형).

**v2 적용**:
- ★ **robot.xml: toe_link에 collision geom 추가**(L+R, toe mesh를 collision으로) → toe가 지면 접촉·하중받음. (USD --force 재변환 필요; Asimov 종료 후.)
- ★ **foot_flat_orientation(roll_only=False, full-axis) 추가** = 발 **pitch-tilt(까치발) 직접 penalize** (swing-only가 못한 stance 평탄화). weight -0.5(연구는 full-axis가 heel-strike와 충돌 경고 → 중간값 + 모니터; 너무 약하면↑, 보행 깨지면↓).
- **swing_height weight -20→-30** (기여 강화).
- cop_progression은 여전히 **보류**(plantigrade 된 뒤 단일 추가; foot_flat과 antagonist).
- stiffness: 60 유지(부하 생기면 적정 변형). MJCF class toe(20) vs YAML(60) 불일치는 reconvert 후 런타임 확인.
- **검증**: v2 학습 → close-up(발 평탄·toe 굽힘) + measure(발목 RMS↓?). toe 굽으면 성공.

### Collision geometry 시각화 (MuJoCo, `scripts/viz_collision.py`)
18 collision geom = torso 캡슐 + head 구 + thigh/shin 캡슐(×2) + **발바닥 5캡슐 rake(×2)** + ★ **toe collision(×2, 신규)**. 측면뷰서 toe 블록이 sole 앞쪽 끝·sole 높이에 위치 = 발이 앞으로 구르면 toe 접촉→하중→스프링 굽힘. (primitive=unitree-lab식, mesh보다 빠르고 안정.)
![collision body](assets/collision_body.png)
![collision foot (sole rake + toe block at front)](assets/collision_foot_side.png)

## 출처
Unitree g1_config/g1_env(feet_swing_height -20·contact +0.18·period 0.8s·offset 0.5·is_stance phase<0.55) · Siekmann 2011.01387(periodic clock) · WTW 2212.03238 · Hansen PMC2906615(roll-over) · Gait-Conditioned RL 2505.20619(간섭) · Peng 2021 2104.02180(AMP) · IsaacLab mdp feet_air_time_positive_biped(verified) · 내부 [[experiments/2026-06-28_19-55-27_g1is_dm4340_flat]]·[[2026-06-28_menlo_blog_review]]·[[2026-06-28_g1_trembling_saturation]].
