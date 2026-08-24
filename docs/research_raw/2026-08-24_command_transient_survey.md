# 원자료 — 명령 전환 과도·리샘플링·추종 지표 보고 관행 전수조사 (2026-08-24, Sonnet 서브에이전트)

## 1. 명령 리샘플링 간격
| 코드베이스 | 값 | 출처 |
|---|---|---|
| legged_gym / unitree_rl_gym | `resampling_time = 10.` 고정 | `legged_robot_config.py:43`, 트리거 `legged_robot.py:285` |
| walk-these-ways | 10. 고정 + 범위 커리큘럼(Box/Grid Adaptive) | Improbable-AI repo |
| HumanoidVerse | `locomotion_command_resampling_time: 10.0` | `config/env/locomotion.yaml:22` |
| IsaacLab 일반 locomotion | `(10.0, 10.0)` | `velocity_env_cfg.py:96` |
| **IsaacLab Digit(휴머노이드)** | **`(3.0, 8.0)`** | `config/digit/rough_env_cfg.py:243` |
| **mjlab(우리)** | **`(3.0, 8.0)`** | `velocity_env_cfg.py:179` |
→ 10 s 고정이 레거시 기본, **(3,8) s는 IsaacLab 계보의 휴머노이드 선택**. 우리 값은 Digit과 동일.

## 2. 명령 필터/슬루 제한 — **주류 프레임워크에 없음**
- legged_gym `_resample_commands`(L292-306): 균등샘플을 그대로 `self.commands`에 씀. 유일한 가공은 **데드존**(‖v‖≤0.2면 0).
- IsaacLab `UniformVelocityCommand._resample_command`, mjlab 동일(L75-99): `r.uniform_(*ranges)` → 관측·보상으로 직행.
- HumanoidVerse `command_generator.resample_commands`: 동일.
- walk-these-ways: 범위 커리큘럼은 있으나 `cmd_filter`/`lag`/`smooth_command` 없음.
→ **명령은 문자 그대로 계단 함수**로 바뀐다. 과도 처리는 "학습 중 노출"로만 해결.
- 혼동 주의 — 존재하는 건 **액션/액추에이터 측 평활**: mjlab actuator `slew_rate`(기본 off, `builtin_actuator.py:349`), 명령→토크 지연(`actuator.py:70,276`); Cassie(Li 2024)는 **정책 출력에 4 Hz 버터워스 LPF**(Fig. 28 ablation: 없으면 점프가 지터).
- 명령 레벨 rate limit의 유일한 사례: Cassie 학습 시 **yaw 명령만 30 deg/s로 변화율 제한**(Table VI). 선속도는 평범한 범위. Mini Cheetah(Rapid Locomotion)는 **실기 테스트에서만** 6.0 m/s까지 ramp.

## 3. 지표 정의·보고 관행
- **보상**: `exp(−‖Δv‖²/σ²)`, σ²=0.25가 legged_gym·HumanoidVerse·IsaacLab·mjlab 공통. 매 스텝이라 과도 포함.
- **로깅 지표**: IsaacLab/mjlab `CommandTerm`의 `error_vel_xy` = `Σ(error/max_command_step)` — 과도 포함, **학습 중에는 확률적(탐색) 정책**으로 계산.
- rsl_rl 5.4.0 코드 확인: `PPO.act()` → `self.actor(obs, stochastic_output=True)`(샘플링), `get_inference_policy()` → `get_policy()` = raw actor(결정론적). play/evaluate는 후자. **학습 지표가 배포 성능을 과대평가(=오차 과대)하는 구조** (에이전트 추론, 논문 서술 아님).
- ★ **mjlab에 정식 평가기가 이미 있다**: `src/mjlab/tasks/velocity/scripts/evaluate.py` — 에피소드당 **명령 고정**(`resampling_time_range = episode_length+warmup+10`), **결정론적 정책**, **`warmup_s=2.0` 과도 제외**(`_rollout_chunk:249`), 시나리오별 **mean/RMS/max** 보고(`evaluation/metrics.py:121-235`).
- 논문 관행: Cassie는 **제자리 보행**(명령 변화 없음) MAE로 비교(Fig. 8); Rapid Locomotion은 명령 격자별 RMSE; Berkeley Humanoid는 60 s 조이스틱 시험 평균을 캡션에서 "steady-state"라 부름(용어 느슨).

## 4. 가속/과도응답 보상 — **선례 없음**
6개 보상 명세(legged_gym, walk-these-ways, IsaacLab, mjlab, HumanoidVerse, Rapid Locomotion Table VI, Cassie)에 **명령 속도에 빨리 도달하라는 항이 없다**. 오히려 반대 방향 항만 보편적: `action_rate`(mjlab −0.1, Rapid −2e-4), 관절가속 −5e-9, 토크 −2e-7.
- 문서화된 실패: Cassie ablation — LPF를 빼고 평활 보상 가중치를 키우면 "로봇이 **정지 상태**에 머무는 준최적 행동을 쉽게 학습"(점프 등 동적 스킬 미탐색).

## 5. 보고된 추종 오차(캘리브레이션)
| 출처 | 조건 | 오차 |
|---|---|---|
| Berkeley Humanoid Fig. 8 | ±0.5 m/s 조이스틱 60 s | 0.051 sim / 0.058 hw (전후), 0.086 / 0.116 (측면) |
| Cassie 제자리(arXiv:2401.16889 Fig. 8) | 0 m/s | MAE ≈ 0.10 m/s |
| **Cassie 1.4 m/s 계단 명령**(Fig. 16) | 1.4 지령 | **달성 1.14 = 갭 0.26 (18 %)** |
| **Cassie −1.0 후진** | −1.0 지령 | **달성 −0.5 = 갭 0.5 (50 %)** |
| CurricuLLM(동일 로봇 인용) | — | 0.41±0.10 / 0.46±0.38 → 원논문의 5–8배 |
| Mini Cheetah 6.0 m/s | ramp | 5.46 sim / 3.81 real |
→ 공개 수치는 **프로토콜에 지배**된다(제자리 vs 이동, 과도 포함 여부, 결정론 vs 확률).

## 통념과 어긋나는 점
- "당연히 명령을 램프해서 도달 가능하게 만들 것"이라는 통념은 **코드상 사실이 아니다**(legged_gym·IsaacLab·mjlab 모두 계단).
- "steady-state"라는 용어가 논문마다 다르게 쓰인다(Berkeley Humanoid는 명령이 계속 바뀌는 60 s 평균을 그렇게 부름).
- 고속 오차는 노이즈가 아니라 **체계적 언더슛(bias)**으로 나타난다(Cassie 18 %·50 %).

## 출처
- 코드: `mjlab/src/mjlab/tasks/velocity/{velocity_env_cfg.py, mdp/velocity_command.py, scripts/evaluate.py, evaluation/{config,metrics}.py}`, `rsl_rl/algorithms/ppo.py`(L120, L396-398), `runners/on_policy_runner.py`(L163-166), `refs/unitree_rl_gym/legged_gym/envs/base/legged_robot{,_config}.py`
- https://github.com/isaac-sim/IsaacLab · https://github.com/Improbable-AI/walk-these-ways · https://github.com/LeCAR-Lab/HumanoidVerse
- arXiv:2401.16889 (Cassie versatile, Li 2024) · arXiv:2407.21781 (Berkeley Humanoid) · arXiv:2205.02824 (Rapid Locomotion)
