# 2026-06-28 · Menlo/Asimov "Teaching a Humanoid to Walk" — Reward/Obs/DR/Toe 레퍼런스 검증 + 적용

> 트리거 (user): 블로그 https://menlo.ai/blog/teaching-a-humanoid-to-walk 의 reward 설계 철학을 **항목별로 레퍼런스 찾아 타당성 검토** 후 학습 진행. 검증 = 워크플로 `menlo-walk-reward-philosophy-review`(8 agent, 187 web tool-use, adversarial) + 구현 레시피 agent(설치 코드 직접 확인). 전체 결과: `logs`(tasks/wy1orcgh7.output). 규칙 [[feedback-reward-research-rule]].

## 항목별 타당성 (레퍼런스)
### REWARD
- **잘 지지됨**: clock-free 보행(우리 lineage = IsaacLab G1 rough_env_cfg·unitree_rl_gym G1 모두 clock-free) · gentle-feet GRF/impact 벌점(QuietWalk 2026 arXiv:2604.23702 제곱-GRF로 발소리 ~7dB↓; SoFTA) · ang-vel 정규화(표준).
- **반박/주의**: ★ "gait clock 제거"는 우리에겐 **non-action**(이미 clock-free). 절뚝의 해법은 clock이 아니라 **대칭 증강**(Su/Sferrazza arXiv:2403.17320, IROS24: 무제약 RL은 비대칭 보행 학습→대칭 augmentation이 직접 치료; clock은 비대칭을 *가려* 우리가 측정할 비대칭 peak 하중을 숨김). ★ 블로그 **air_time +0.5(flight)**는 16kg 다리 전용 — **51.8kg 우리에겐 착지 GRF 최대화 = 저충격 목표와 정반대**. 채택 금지.

### OBSERVATION
- **잘 지지됨**: 배포 actor서 **base_lin_vel 제외**는 주류 sim2real(Berkeley Sci.Robotics 2024; Walk-These-Ways arXiv:2212.03238은 30-step history로 속도 추정; Ji 2022 RAL arXiv:2202.05481 concurrent estimator; unitree_rl_gym G1 = actor 47 vs critic 50, 차이 3D=base_lin_vel). 비대칭 A-C=교과서(Pinto 2017 arXiv:1710.06542; Lee 2020).
- **반박/주의**: ★ 블로그의 "ground-truth 속도→underdamped→격렬한 떨림" **인과는 블로그 일화**(peer-review ablation 없음 = 가설). ★ base_lin_vel 제거는 **단독으로 하는 경우 거의 없음** — 반드시 **obs history(5-30) 또는 concurrent estimator**와 병행. "height_scan 있으니 제거 안전"은 **non-sequitur**(heightmap≠속도; PRIOR arXiv:2603.18979도 heightmap+속도 GRU 병행).
- ★ **우리 현황(검증)**: `velocity_env_cfg.py`가 observations를 override 안 함 → **stock PolicyCfg에 noisy ground-truth base_lin_vel가 actor에**(IsaacLab velocity_env_cfg.py:124), **단일 policy 그룹(critic 없음)**, empirical_normalization=False, MLP[256,128,128], **history 없음**. 우리 lineage인 IsaacLab G1도 base_lin_vel을 actor에 유지(=메모리의 "deployed G1 drops it"은 별도 Unitree repo만 해당). → **memoryless 단일프레임 MLP서 base_lin_vel 단독 제거 시 추종 악화** 예상. = obs 재구조화는 **PILOT A/B**, 떨림 확정 치료 아님.

### DR
- **잘 지지됨**: targeted/measured DR(아는 것만 랜덤)=현대 consensus(Xie 2020 arXiv:2011.02404 "DR은 필수도 충분도 아님", 과랜덤→보수적 정책, **soft PD가 DR보다 중요**; Lee 2020 actuator net; PACE 2025 arXiv:2509.06342 "dynamics 랜덤 안 함, task/terrain만"; Berkeley Humanoid; Rudin 2022). link/gravity 랜덤 금지=보편.
- **반박/주의**: 블로그 "±20% mass가 학습 불안정"은 **과장**(Tan 2018 80-120% 성공; ANYmal/G1/legged_gym 1-10% 일상). 블로그 철학은 **HW로 system-ID 가능 전제** — 우린 실물 없음(논리 일부 역전).
- ★ **우리 적용**: 하중측정 목표가 targeted-DR을 **강화**(과랜덤→경직 gait→하중신호 왜곡). 단 실물 없어 actuator/sensor/latency는 "변하는 줄 알지만 측정 못함"→**중간 DR 유지**. ★ **최대 갭 = action/obs latency DR 전무**(Tan 2018: latency 미모델→sim 안정·실물 진동 = 떨림 시그니처). 2순위 = soft PD(Xie 2020 최대 lever). flat→rough: flat은 DR 경량(깨끗한 하중), rough서 task-side DR(terrain/friction0.4-1.0/restitution/push) 추가.

### TOE
- **잘 지지됨**: passive spring toe=생체역학 타당(인간 MTP windlass 에너지저장·GRF모먼트암↓; SURENA III passive toe 발목-15.3%/무릎-9.0% 에너지; Duke arXiv:2409.19795 CoT-31%). 무센서 DOF(toe) **critic-only**=비대칭 A-C(Pinto/Lee, 우리 스택 네이티브 지원). 무센서 접촉추론 입증(QuietWalk; Lee 2020).
- **반박/주의**: 최대 toe 이득은 **active toe**(Kim 2026 arXiv:2606.19699, 14-DOF biped: toe 없으면 ankle/knee/hip power +29/11/22%; active toe CoT-17.5%). passive는 더 작은 slice. 발목 ROM ±20/15°는 그들 parallel-RSU **HW 사실**(우리 DM-J4340 다름) → 모방 금지.
- ★ **우리 버그(검증)**: passive toe 복원했고 action서는 제외(line 178)했으나, **stock joint_pos/joint_vel ObsTerm이 joint_names 필터 없음(=[.*])**(IsaacLab velocity_env_cfg.py:131-132) → **인코더 없는 passive toe가 actor obs로 누출**(배포불가 sim-only 신호 = 블로그가 피한 안티패턴). 수정: actor joint_pos/vel을 ACTUATED_JOINTS로 scope + toe는 critic 그룹에.

## ★ 적용 계획 (NOW = clean A/B, reward+PD 고정)
1. ★ **actor joint_pos/vel → ACTUATED_JOINTS** (toe 누출 차단; 최고 value/risk, 거의 버그수정).
2. **비대칭 A-C**: `critic` 그룹(base_lin_vel + foot contact/air-time/GRF + toe pos/vel) 추가 + actor서 base_lin_vel 제거. ★ rsl_rl 2.3.3은 **`critic` 이름 그룹 자동감지**(obs_groups API 아님 — 우리 버전 미지원, 쓰면 critic==actor 조용히 실패).
3. **obs history 5-10**(proprioception) — base_lin_vel 제거와 *반드시* 병행.
4. **action latency DR**(~0-2 control step/0-20ms) — 별도 A/B. ⚠ ImplicitActuator라 DelayedPDActuator로 교체 필요→토크 동역학 변화→§7 하중측정 영향. **하중측정 목표와 tension** → 신중/후순위.
5. **rsl_rl 대칭 증강** — 절뚝 직접 치료, mirror map이 우리 joint 순서와 맞는지 검증 필수.

**구현 사실(설치코드 검증)**: IsaacLab 2.2 + rsl_rl 2.3.3. 비대칭 A-C는 `critic` ObsGroup 추가만(PPO/runner/wrapper 수정 불요, num_privileged_obs 자동). foot contact/air-time/GRF는 빌트인 obs 함수 없음→custom MDP 함수 4개 필요. obs 변경(1-3)은 **전부 from-scratch 재학습**(obs dim 변화).

**LATER**: empirical_normalization=True · PD softening(Xie 2020, kp sweep+하중 재검증) · QuietWalk 제곱-GRF impact(별도 연구노트 필요) · rough서 task-side DR · mass DR 후순위 복귀 · MLP[512,256,128](obs A/B 후, flat+rough 동시) · toe lock vs spring A/B(§7로 발목 offload 정량) · CAN latency는 배포단계.

## 이번 적용 결정
**obs 재구조화 묶음(1+2+3)을 새 arm `BipedG1ImpactStableAsymObs`로 구현** → 현재 baseline(g1is_dm4340_flat)과 A/B. 대칭증강(5)·latency(4)는 후속 별도 arm. 이유: 1-3은 "obs 인터페이스 교정"이라는 한 논리적 변경 + history는 base_lin_vel 제거의 전제라 묶음이 맞음.

## 출처
Pinto2017(1710.06542)·Lee2020(2010.11251)·Berkeley(Radosavovic2024)·WalkTheseWays(2212.03238)·Ji2022(2202.05481)·Xie2020(2011.02404)·Tan2018(1804.10332)·PACE2025(2509.06342)·BerkeleyHumanoid(2407.21781)·Su/Sferrazza대칭(2403.17320)·QuietWalk(2604.23702)·Kim2026 active-toe(2606.19699)·Duke(2409.19795)·Menlo blog. 내부 검증: velocity_env_cfg.py·IsaacLab stock obs·rsl_rl 2.3.3 wrapper. [[2026-06-28_g1_trembling_saturation]]·[[48_motor_util_sizing]]·[[49_ankle_actuator_tn_sizing]]·[[g1-vanilla-beats-custom-reward]]
