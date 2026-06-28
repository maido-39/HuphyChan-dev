# 2026-06-29 · 사람 gait reference 추종 reward (contact-phase DeepMimic) — 까치발/shuffle 근본해결

> 트리거(user, 자율): 사람 gait 사이클/mocap을 **추종 target/loss/참조**로 도입 → 인간형 gait + **전 액추에이터 에너지/토크 최소화** + **toe 적절 사용**. 규칙 [[feedback-reward-research-rule]]. 검증 워크플로 `human-gait-reference-research`(w9d8ys8av, 19 agent, 41 findings, adversarial 10 confirmed). 방향메모 [[human-gait-reference-direction]].

## 근본원인 (정량 확정)
약한 penalty 접근(foot_flat·swing_height)이 **track 보상에 압도되어 까치발/shuffle 못 고침**:
- v2 mid-run: `foot_flat_orientation` -0.046(iter500)→-0.051(1000) **0으로 안 줄어듦**(정체) = -0.5 가중치 너무 약함. v1 swing_height와 동일 실패.
- ★ **human-likeness 툴**(`scripts/gait_humanlikeness.py`, 신규): g1is_dm4340 **hip range_ratio 0.02-0.05**(사람 관절범위의 2-5%만!)·점수 -0.03; asimov knee corr +0.85(모양은 인간형)이나 진폭 작음·점수 0.07. = **두 gait 모두 사람 관절을 5-30%만 사용 = shuffle 정량 확정**.
- 결론: 약한 음수 penalty로는 게으른 gait를 못 깬다 → **밀집 양수 reference 신호**가 필요(전 관절 궤적을 직접 인간형으로 끌어당김).

## 연구 결론 (워크플로, 검증)
- **AMP 비효율**(confirmed): rsl_rl 2.3.3 discriminator 없음(algorithms=ppo·distillation만), IsaacLab AMP은 skrl+direct(미설치·우리 manager-based와 비호환), mocap은 우리 형태(passive toe·발기하)와 불일치, GAN 불안정. = 외부 wrapper/custom trainer 400-600줄 = 과대.
- **clockless 순수회귀**(soft phase-ref, obs clock)는 mode-collapse/retrain 위험.
- ★ **추천(confirmed)**: **contact-phase-indexed DeepMimic soft 추종** — 최소노력, 사람 관절궤적으로의 **진짜 gradient**, ★ **obs 변경 없음 → 기존 ckpt warm-start**. cop_progression과 phase 공유.
- 데이터(confirmed, Perry/Winter): hip 0-40° 굴곡(mid-stance~0°), knee 10-30° stance·~60° swing, ankle plantar 20-25°@50-60%(toe-off), peak ankle τ~78N·m(→감속 필요, 우리 DM-J4340 반영). = 내 `gait_reference.py` 곡선과 일치(검증됨).

## ★ 설계 (v3 = human-reference)
**데이터** [[gait_reference]](`tasks/locomotion/gait_reference.py`, 검증): 사람 normative sagittal → 우리 관절 retarget(FK부호 [[51_joint_sign_conventions]]: `q_hip_pitch=-flex, q_knee=-flex, q_ankle_pitch=+dorsi`). R다리 = L phase+0.5. toe는 actuated 아님(추종X, 부하로 windlass 발생).

**phase (contact 유도, obs 변경 없음)**: 다리별로 contact 센서의 `current_contact_time`/`current_air_time` →
`phase = stance면 0.6·clip(contact_t/T_stance,0,1), swing이면 0.6+0.4·clip(air_t/T_swing,0,1)` (T_stance~0.6s·T_swing~0.4s 명목). 각 다리 자기 contact로 phase → L/R 위상차 자연 발생.

**reward 항** (★ 신규 2 + 유지/제거):
- ★ `gait_reference_tracking`(신규, +): `w · mean_leg exp(-k·Σ_sagittal(q−q_ref(phase))²)`. **sagittal만**(hip_pitch/knee/ankle_pitch); frontal(hip_roll/yaw·ankle_roll) 자유(균형). **w ≈ +1.0(velocity 아래: track_ang +2·track_lin +1)**, k≈2. = 밀집 양수 신호로 shuffle 격파.
- ★ `mechanical_power`(신규, −): `−w·Σ|τ·ω|` (전 관절 기계적 일률 = 에너지 최소화, **user 목표**). w 작게(예 -2e-4), 측정 후 조정.
- **유지**: track lin/ang(작업) · impact(foot_landing_vel -1.0/foot_impact_force -0.005 — ★ imitation은 힘을 못 묶음, impact 유지 필수) · anti-trembling(dof_acc/action_rate) · feet_slide · termination.
- ★ **제거**: foot_flat_orientation(full-axis는 reference의 ankle 굴신과 충돌·heel-toe 방해; reference가 발자세 담당) · feet_swing_height(reference의 hip/knee 굴곡이 swing clearance 담당 = 중복).
- **보류**: cop_progression/ankle_pushoff — reference가 이미 toe-off(ankle plantar@60%) 인코딩 → rollover 여전히 부족할 때만 단일 추가.

**warm-start**: flat ckpt(g1is_dm4340 또는 v2)에서 `--init_checkpoint`(obs 불변 → 망 일치). reference 신호로 fine-tune.

## 위험 (워크플로 + 완화)
- **mode collapse to mean pose**(평균자세로 주저앉음) → 완화: **낮은 w + contact-phase(시변 target) + exp 형태**.
- **phase가 flight서 미정의** → air_time로 정의(둘 다 swing); no-flight 유지(impact 항).
- ★ **imitation은 힘 한계를 안 묶음** → **impact 항 유지 필수**(peak GRF<1.5-2.7kN).
- contact-phase 명목주기(T_stance/T_swing) 불일치 → 측정 후 조정(또는 속도적응).

## 평가 (eval criteria)
- ★ **human-likeness 점수↑**(`gait_humanlikeness.py`: range_ratio→1·corr→+1; 현 ≈0).
- toe-off 타이밍 사람근접 + 좌우대칭(절뚝 없음).
- **CoT↓ + toe 사용↑**(measure: toe qpos 굽힘·foot GRF 분포).
- **peak GRF < HW 한계**(1.5-2.7kN) — 충격 안 늘었나.
- 학습건강(noise_std 수렴·낙상<5%·error_vel≤0.3).

## ★ toe 검토 (user 2026-06-29) — windlass 타이밍 누락 → v4서 toe_load_stance 추가
**검토 결과**: `gait_reference_tracking`은 **sagittal 3관절(hip_pitch/knee/ankle_pitch)만 추종, toe 미포함**(toe는 passive=위치추종 불가). toe는 "ankle reference plantarflex@toe-off + collision"으로 **간접** 굽도록 설계했으나 — 실측(`scripts/gait_toe_timing.py`)으로 **타이밍이 틀림 확인**:
- g1is_dm4340/asimov: toe **0.001 rad = 안 굽음**(옛 로봇, collision 없음).
- v2(collision 有): toe **0.087 rad 굽으나 최대굽힘 78-95% = swing(관성)** — push-off(~50-60%) 아님 = **windlass 미발생**. τ_toe max ~25N·m(스프링 작동) but L/R 비대칭(mean 10 vs 2 = 절뚝).

**원인**: toe가 **적절한 시기(push-off)에 하중받도록 강제하는 항이 없음**. ankle reference만으론 forefoot roll을 못 만들어 toe가 안 실림. ("reference가 toe-off 인코딩하니 충분"이란 초기 가정이 과낙관 — reference는 ankle 관절각만, 발이 실제로 toe로 구르는 건 별개).

**fix (v4 = `BipedHumanRefToeEnvCfg`)**: ★ **`toe_load_stance` 추가**(기존, research wljkv3uu8/docs/22) = passive toe 스프링토크 `clamp(|τ_toe|/27,0,1)`를 **terminal stance(이 발 contact + 반대발 swing=single support + 전진 + contact age>0.15s)** = **정확히 push-off 시기**에만 보상 → toe를 올바른 타이밍에 하중. static toe-curl degeneracy 방지 게이트 내장. weight **+0.5**(gated라 미발화 잦음, config-test 후 tune). 반대발 swap `[1,0]`·L/R 순서 일치 필요(preserve_order).
**iteration 순서**: v3(reference만, shape 격리) → **v4(+toe_load_stance, windlass 격리)** → v5(+power_cot 에너지). 각 단일 추가(과적 stack 방지).

## 베이스라인/참조 시각화
**사람 reference 곡선 + 우리 관절 retarget** (`gait_reference.py`, 검증):
![gait reference](assets/gait_reference_preview.png)

**베이스라인 human-likeness** (`gait_humanlikeness.py`): 현 gait 모두 사람 관절범위의 **5-30%만 사용**(검은 점선=사람, 거의 평평한 색선=로봇 shuffle); 점수 g1is_dm4340 -0.03·v2 -0.01·asimov 0.07. v3 목표 = 색선이 점선에 근접(range_ratio→1, corr→+1).
![human-likeness baselines](assets/gait_humanlikeness_baselines.png)

## refs
워크플로 w9d8ys8av(원본 /tmp tasks/w9d8ys8av.output) · Peng AMP 2104.02180 · DeepMimic Peng 2018(1804.02717) · Siekmann 2011.01387(periodic contact) · Winter 'Biomechanics' · Perry 'Gait Analysis'(Figs 8-2,8-3) · 내부 [[gait_reference]]·[[51_joint_sign_conventions]]·[[2026-06-28_heeltoe_stride_fix]]·[[experiments/2026-06-28_19-55-27_g1is_dm4340_flat]]·[[human-gait-reference-direction]].
