# 문헌 조사: 좌우 대칭 / 체공시간(air-time) 보상 / 저속 명령 정체 (2026-09-05)

조사 배경: legonly 계열 완주 측정에서 (1) 무릎 스윙 좌우 비대칭 14°, (2) 0.5 m/s 명령에서 진행률 26%,
(3) duty factor 0.45~0.52 (사람 0.58~0.65) 세 가지가 관측됨. 아래는 우리 데이터 재해석이 아니라
**문헌 자체가 뭐라고 하는지**만 정리한 원자료(raw excerpt).

---

## Q1. 좌우 대칭

### Yu, Turk, Liu — "Learning Symmetric and Low-Energy Locomotion" (ACM TOG / SIGGRAPH 2018)
https://sites.cc.gatech.edu/home/turk/paper_pages/2018_symmetric_locomotion/symmetric_low_energy_locomotion.pdf

- Mirror Symmetry Loss (MSL): `w_π · Σ_i ||μ_θ(s_t) − g(μ_θ(f(s_t)))||²`
  - f: state mirroring function (좌우 관측 스왑), g: action mirroring function (좌우 액션 스왑)
  - w_π: 가중치 하이퍼파라미터
- 대상: biped, full humanoid, quadruped, hexapod — **전부 시뮬레이션 캐릭터**, 실기 검증 없음 (그래픽스/애니메이션 논문, 로보틱스 하드웨어 논문 아님).
- 모션캡처 없이 처음부터 대칭·저에너지 보행을 학습하는 최초 프레임워크로 인용됨.

### Xie et al. — "Iterative Reinforcement Learning Based Design of Dynamic Locomotion Skills for Cassie" (RSS 2019) / "Learning Locomotion Skills for Cassie: Iterative Design and Sim-to-Real" (CoRL 2019/2020)
https://proceedings.mlr.press/v100/xie20a/xie20a.pdf , https://zhaomingxie.github.io/

- 방법 (d) 네트워크 구조형: **half-cycle마다 입력/출력을 대칭형으로 변환**하는 방식(미러 네트워크) — 손실항이 아니라 추론 시 강제 변환.
- **실기 검증: Cassie 이족 로봇 (Agility Robotics)** — 실제 하드웨어 보행 성공.

### "Symmetry Considerations for Learning Task Symmetric Robot Policies" (arXiv:2403.04359)
https://arxiv.org/abs/2403.04359 (ar5iv: https://ar5iv.labs.arxiv.org/html/2403.04359)

- 3가지 방법 분류: "there are three main ways to incorporate symmetry into DRL: 1) using a symmetry loss function, 2) performing data augmentation, and 3) designing specialized network architectures."
- Mirror loss 수식: `L^sym_g(θ) = E_τ[Σ_t ||K_g[π_θ(s_t)] − π_θ(L_g[s_t])||²_2]`
- 실기: **ANYmal-D 4족 로봇**, ANYmal-Climb 박스 오르기 태스크에서 zero-shot 실기 전이.
- 부작용(원문): "optimizing the symmetry loss directly helps induce symmetry but comes at the cost of **performance and slower convergence**." symmetry loss는 실제 보상 차이를 고려하지 않고 모든 대칭 상태-액션 쌍을 동등하게 취급.
- 초기화 민감성: data augmentation "struggles when initialized weights are high."
- 완전 대칭 정책의 근본적 한계: "a symmetric policy cannot lift the right front foot to take the first step" (s = L_g[s]인 대칭 초기상태에서는 결정론적 대칭 정책이 방향을 못 정함).

### "Leveraging Symmetry in RL-based Legged Locomotion Control" (arXiv:2403.17320, Zhaocheng et al.)
https://arxiv.org/abs/2403.17320 (ar5iv: https://ar5iv.labs.arxiv.org/html/2403.17320)

- 비교: Vanilla PPO / PPOaug(대칭 데이터 증강) / PPOeqic(equivariant MLP로 구조적 강제)
- 실기: **Xiaomi CyberDog2, Unitree Go1** 4족 로봇, door-pushing / stand-turning 태스크 실기 전이.
- PPOeqic가 샘플효율·수렴속도 최고. 단, "PPOaug demonstrates enhanced robustness against such imperfect symmetry"(실제 로봇의 비대칭 오차에는 구조적 강제보다 증강이 더 강건) — PPOeqic는 "more vulnerable to distribution shifts."
- 흥미로운 역설: 한쪽 시나리오만 학습한 정책이 양쪽 다 학습한 것보다 나은 경우 관찰 (도메인 랜덤화가 대칭 가정을 깨뜨림).

### SE-Policy — "Coordinated Humanoid Robot Locomotion with Symmetry Equivariant Reinforcement Learning Policy" (arXiv:2508.01247, Nie et al. 2026-08)
https://arxiv.org/abs/2508.01247

- Actor에 엄격한 형태학적 대칭 강제 + Critic은 불변(invariance)으로 설계.
- **Unitree G1 휴머노이드**에서 속도추종 오차 최대 40% 개선, 시공간 협응 개선 (baseline RL 대비).

### AGILE — 휴먼로이드 로코매니퓰레이션 워크플로 (arXiv:2603.20147)
- "symmetry augmentation doubles the effective training data and enforces symmetric gaits" — 데이터 증강형.

---

## Q2. Duty factor / air-time 보상

### Siekmann, Godse, Fern, Hurst — "Sim-to-Real Learning of All Common Bipedal Gaits via Periodic Reward Composition" (ICRA 2021)
arXiv:2011.01387, https://arxiv.org/abs/2011.01387 (ar5iv: https://ar5iv.labs.arxiv.org/html/2011.01387)

- 정규화 위상 φ ∈ [0,1] (절대시간이 아닌 반복 사이클).
- Stance/swing 지시함수 `I_i(φ)`는 폰미제스분포로 샘플된 시작/끝 시각 `A_i ~ Φ(2πa_i, κ)`, `B_i ~ Φ(2πb_i, κ)`에서 결정되는 확률변수(경계에서 부드럽게 스무딩).
- 기본 보상 구조: swing 구간 `c_swing_frc=-1, c_swing_spd=0` (스윙 중 지면 반력 페널티), stance 구간 `c_stance_spd=-1, c_stance_frc=0` (스탠스 중 발 속도 페널티) — **stance/swing 비율 r ∈ (0,1)** 로 걷기/뜀걸음/달리기를 구분.
- 좌우 위상 오프셋 `θ_left, θ_right`: 홉핑은 `|θ_left−θ_right|≈0`(동기), 걷기/달리기는 `≈0.5`(교대).
- 전환 페널티 없이 다중 보행을 학습시키면 "asymmetrically walking instead of hopping, or learn other undesirable behaviors" — 즉 **주기 구조 없이 단순 보상만 쓰면 원치 않는(비대칭·홉핑성) 보행으로 샌다**는 원문 경고.
- **실기: Cassie**. 서기/걷기/뜀걸음/달리기/스킵까지 하나의 정책으로 실기 전이 성공.

### legged_gym (ETH, leggedrobotics) — feet_air_time 보상 원본 구현
https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot.py

```python
def _reward_feet_air_time(self):
    contact = self.contact_forces[:, self.feet_indices, 2] > 1.
    contact_filt = torch.logical_or(contact, self.last_contacts)
    self.last_contacts = contact
    first_contact = (self.feet_air_time > 0.) * contact_filt
    self.feet_air_time += self.dt
    rew_airTime = torch.sum((self.feet_air_time - 0.5) * first_contact, dim=1)
    rew_airTime *= torch.norm(self.commands[:, :2], dim=1) > 0.1
    self.feet_air_time *= ~contact_filt
    return rew_airTime
```
- 이 항은 **접지 순간(첫 접촉)** 에만, "체공시간 − 0.5초"를 보상 — 즉 지지 지속시간 자체(스탠스 비율)엔 아무 페널티가 없고 **스윙(체공)을 길게 유지**하도록만 유도. duty factor를 직접 겨냥하는 항이 아님.
- `_reward_tracking_lin_vel`: `exp(-Σ(cmd_xy − v_xy)² / tracking_sigma)`, 기본 `tracking_sigma=0.25` (leggedrobotics/legged_gym `legged_robot_config.py`).

### IsaacLab GitHub Discussion #1977 / Issue #1955 — feet_air_time 튜닝
https://github.com/isaac-sim/IsaacLab/discussions/1977 , https://github.com/isaac-sim/IsaacLab/issues/1955

- 사용자 보고: 기본 가중치 0.125에서 발을 안 들고, 크게 올리면 "strange behaviors" 발생, 좋은 트레이드오프를 못 찾음 — 실무자들이 **air-time만으로는 자연스러운 duty factor를 못 얻는다**고 보고.
- legged_gym에서 실제로 quadruped pronking(4족 동시 도약)형 이상 보행이 air-time 가중치 과다 시 관찰된 사례 언급 (WebSearch 요약, 커뮤니티 보고 — 원문 스레드 직접 인용은 위 experts 코멘트).

### "Revisiting Reward Design and Evaluation for Robust Humanoid Standing and Walking" (arXiv:2404.19173)
https://arxiv.org/abs/2404.19173 (ar5iv: https://ar5iv.labs.arxiv.org/html/2404.19173)

- feet air time 항: "this term regularizes the stepping frequency by applying a penalty of 0.4 at each foot touchdown, which can be counteracted by a positive reward component equal to the number of seconds since the foot has been in the air."
- 논문 자체는 duty factor/보행률(cadence)을 사람과 정량 비교하지 않음: "it is not clear whether these stylistic characteristics are missing due to the inability of RL to perfectly optimize the above reward terms" — RL 보행의 스타일 결핍 원인 규명 자체가 미해결로 인정됨.
- 실측: RL 컨트롤러가 제조사 컨트롤러보다 "stomp more loudly"(착지 충격 큼) — 짧은 지지시간/발목 미사용과 정합적인 정성적 관찰(문헌의 별도 보고, 우리 로봇과 무관).

### Margolis et al. — "Rapid Locomotion via Reinforcement Learning" (RSS 2022 / IJRR 2024)
https://www.roboticsproceedings.org/rss18/p022.pdf , ar5iv:2205.02824

- Raibert Heuristic 기반 발 위치 + **명시적 접촉 스케줄(위상별 duty cycle, 오프셋)**을 정책 입력/보상에 결합 — Siekmann과 유사한 "주기 시계 + duty factor 파라미터" 계열, 4족.
- 저자들은 보상 스케줄링(reward scheduling)으로 페널티항을 점진 활성화해 학습 안정화.

**교차 논평(추론)**: 문헌상 "air-time 단독"과 "주기 시계(phase clock) + duty factor"는 서로 다른 계열이며, 함께 쓸 때의 상호작용을 직접 다룬 논문은 검색 범위 내에서 발견되지 않음 — 대신 정황상 (1) air-time 단독은 duty factor를 규정하지 않고 스윙 연장만 유도, (2) 사람 같은 duty factor(0.6)를 얻으려면 Siekmann류의 stance-side 항(스탠스 중 발 속도/힘 페널티, stance ratio 파라미터)이 필요하다는 것이 여러 소스에서 반복됨. 이는 문헌의 구조적 사실이며 우리 정책의 "왜"를 직접 진단한 것은 아님 — 표시된 대로 추론.

---

## Q3. 저속 명령 정체 / creep-gaming

### 핵심 수식 재확인 (legged_gym, 위 Q2와 동일 소스)
`tracking_lin_vel = exp(-||cmd_xy − v_xy||² / 0.25)` — **절대 오차 제곱**을 쓰며 명령 크기로 정규화하지 않음.
문헌 자체에 "이 절대오차 공식은 저속 명령에서 상대오차가 커도 절대오차가 작아 보상이 높게 나온다"는 명시적 경고 문장은 검색 범위 내 발견 못함 — 이는 공식의 **수학적 성질**로서 관찰 가능하나, 논문이 이를 결함으로 논한 출처는 못 찾음 (추측 표시).

### IsaacLab `UniformVelocityCommandCfg` — rel_standing_envs
https://isaac-sim.github.io/IsaacLab/main/_modules/isaaclab/envs/mdp/commands/commands_cfg.html

- `rel_standing_envs`: "The sampled probability of environments that should be standing still. Defaults to 0.0."
- 이는 **연속 임계값이 아니라 이진 플래그**로 "완전 정지 환경"을 명령분포에서 별도 샘플링하는 방식 — (a)"임계 대신 연속 게이팅"과는 반대 방향이지만, (c)"명령 분포로 저속 비중 확보"의 실제 채택 사례. 근처(0 초과, 미소) 명령을 아예 만들지 않음으로써 회색지대를 원천 차단하는 설계 철학.

### IsaacLab Issue #458 — "Legged robots stand still despite the rewards of tracking linear and angular velocities"
https://github.com/isaac-sim/IsaacLab/issues/458

- Solo12 4족 로봇 학습 시, 속도추종 보상이 있음에도 로봇이 넘어진 뒤 정지 상태를 선호하는 문제 보고. **근본원인 진단이나 해결책이 스레드에 명시되지 않음(미해결 실무 보고)** — 우리 문제(느리게라도 감)와는 반대 극단(아예 안 감)이지만 "임계 근방에서 보상 지형이 정지를 국소최적으로 만든다"는 동일 계열 실패 패턴.

### 명령 커리큘럼 (legged_gym 원본)
```python
def update_command_curriculum(self, env_ids):
    if torch.mean(self.episode_sums["tracking_lin_vel"][env_ids]) / self.max_episode_length \
            > 0.8 * self.reward_scales["tracking_lin_vel"]:
        self.command_ranges["lin_vel_x"][0] = np.clip(..., -max_curriculum, 0.)
        self.command_ranges["lin_vel_x"][1] = np.clip(..., 0., max_curriculum)
```
- 추종 성능이 80% 문턱을 넘을 때만 명령 범위를 확장 — **저속 구간 성능이 나빠도 이미 학습된 좁은 범위 안에서는 임계를 넘기기 쉬워** 커리큘럼이 계속 확장되고, 저속 자체의 부진은 별도로 검증되지 않는 구조. (이 문장은 코드 로직에서 직접 읽히는 구조적 사실이며, 저속-특이적 실패를 논문이 별도로 지적한 것은 아님 — 추론 표시.)

### 일반적 명령 커리큘럼 문헌 (TransCurriculum arXiv:2603.14156, HACL arXiv:2505.18429 등)
- "training from low-speed commands facilitates the acquisition of stable locomotion patterns" — 대부분의 커리큘럼 문헌은 **저속에서 시작해 고속으로 확장**하는 방향만 다루며, 반대로 "고속 학습 후 저속 성능이 퇴화"하는 사례나 그 해결책을 명시적으로 다룬 논문은 검색 범위 내 확인 못함.

---

## 검색에 사용한 쿼리 로그 (요약)
- mirror symmetry loss bipedal RL Yu 2018 / Cassie mirror policy sim-to-real
- feet air time reward legged_gym hopping exploit / Siekmann periodic reward composition duty cycle
- velocity tracking low speed dead zone gaming / Unitree H1 G1 symmetry mirror 2024-2025
- Leveraging Symmetry in RL-based Legged Locomotion / Symmetry Considerations survey (2403.04359)
- legged_gym source code (_reward_tracking_lin_vel, _reward_feet_air_time, update_command_curriculum)
- IsaacLab rel_standing_envs / Issue #458 stand-still
