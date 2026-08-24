# 원자료 — 이족 로봇 속도명령 박스(특히 vy)와 커리큘럼 전수조사 (2026-08-24, Sonnet 서브에이전트)

조사 지시: 이족/휴머노이드 RL의 `lin_vel_y` 범위, 축별 커리큘럼 여부, 박스 vs 디스크 샘플링, 너무 넓은 vy의 실패 사례, 고속에서 vx/vy 분리. 1차 출처(코드 파일 경로·논문 표)만.

## 표 (에이전트 보고 원문 요약, 출처 링크는 아래)
| 프로젝트 | vx | **vy** | wz | 커리큘럼 |
|---|---|---|---|---|
| legged_gym base | ±1.0 | **±1.0** | ±1 | vx만 램프(`update_command_curriculum`, 추종보상 >80 %에 ±0.5 확장) |
| unitree_rl_gym G1 / H1 / H1_2 | ±1.0(상속) | **±1.0(상속)** | ±1 | `curriculum=False`, 로봇별 override 없음 |
| IsaacLab 템플릿 | ±1.0 | **±1.0** | ±1.0 | 코어에 축별 커리큘럼 항 없음 |
| **IsaacLab G1 rough** | 0–1.0 | **0(비활성)** | ±1.0 | 없음 |
| **IsaacLab G1 flat** | 0–1.0 | **±0.5** | ±1.0 | 수동 2단(rough 0 → flat 0.5) |
| **IsaacLab H1 (rough·flat)** | 0–1.0 | **0(항상 비활성)** | ±1.0 | 없음 |
| Berkeley Humanoid | ±1.0 | ±1.0 | ±1.0 | `modify_command_velocity`가 **lin_vel_x만** 건드림 |
| **humanoid-gym / XBot-L** | −0.3–0.6 | **±0.3** | ±0.3 | off |
| **Booster T1** | ±1.0 | ±1.0 정적 / 커리큘럼 시 `\|level_x\|·U(−1,1)·0.1` | ±1 | ★vx·vy가 **같은 레벨** 공유, vy 해상도가 vx의 절반 |
| **Cassie/Digit (Li 2024, Table VI)** | 보행 ±1.5 / 주행 2.0–5.0 | **보행 ±0.6 / 주행 ±0.75** | ±45 / ±30 °/s | 스킬별 고정 |
| walk-these-ways(사족, 대조) | ±10 한계 | **±0.6 한계** | ±10 | 격자형 적응 커리큘럼(축별 박스 확장 아님) |
| **우리(pygmalion)** | 스테이지 ±0.8→±2.5 | **±1.0 고정(스테이지에 없음)** | ±0.5→±1.0 | vx·wz만 |

## 핵심 결론(에이전트)
1. **vy ±1.0은 "튜닝 안 한 사족 계보 기본값"**이다. 이족용으로 손을 댄 설정은 전부 **±0.3–0.6 또는 0**.
2. 커리큘럼은 조사한 모든 코드베이스에서 **vx만** 램프한다. vy를 램프하는 자동 커리큘럼은 사실상 없다 — 우리 `VelocityStage` TypedDict에는 `lin_vel_y` 필드가 있는데 pygmalion 스테이지 목록에서 **한 번도 채우지 않는다**.
3. **샘플링은 전부 축 독립 박스**(legged_gym `_resample_commands`, IsaacLab `UniformVelocityCommand._resample_command`, Booster 비커리큘럼 경로, 우리 것 포함). 디스크/극좌표(크기+방향) 샘플러는 8개 코드베이스에서 **발견되지 않음**. 유일한 완화는 legged_gym의 원점 데드존(`norm<0.2`면 0).
4. 너무 넓은 vy의 실패는 서술된 사후분석보다 **"조치의 흔적"**으로 남아 있다: IsaacLab G1/H1 저자들이 이족용으로 vy를 0 또는 ±0.5로 낮춤. Cassie/Digit은 **속도가 올라갈수록 vy/vx 비를 줄인다**(보행 0.6/1.5=0.40 → 주행 0.75/5.0=0.15).
5. 고속에서 분리하는 사례: Booster T1(공유 레벨, vy 해상도 절반), Cassie/Digit(스킬별). **우리는 정반대** — vx가 2.5로 커지는 동안 vy는 1.0에 고정이라 마지막에 거의 정사각 박스가 된다(초반엔 vy가 vx보다 넓다).

## 출처
- legged_gym `legged_robot_config.py` L74-78 / `legged_robot.py` L337-351, L443-452 — https://github.com/leggedrobotics/legged_gym
- unitree_rl_gym g1/h1/h1_2 config — https://github.com/unitreerobotics/unitree_rl_gym
- IsaacLab `velocity_env_cfg.py` L94-105, `config/g1/{rough,flat}_env_cfg.py`, `config/h1/rough_env_cfg.py`, `envs/mdp/commands/velocity_command.py` L145-148 — https://github.com/isaac-sim/IsaacLab
- Berkeley Humanoid `velocity_env_cfg.py` L94-107, `mdp/curriculums.py` — https://github.com/HybridRobotics/isaac_berkeley_humanoid
- humanoid-gym `humanoid_config.py` L162-172 — https://github.com/roboterax/humanoid-gym
- Booster Gym `envs/T1.yaml` L115-134, `envs/t1.py` L391-435 — https://github.com/BoosterRobotics/booster_gym
- walk-these-ways `legged_robot_config.py` L104-154 — https://github.com/Improbable-AI/walk-these-ways
- Li et al., IJRR 2024, arXiv:2401.16889 Table VI (Appendix C)
- 우리 코드: `velocity_env_cfg.py` L186-191, `mdp/curriculums.py` `commands_vel`, `config/pygmalion/env_cfgs.py` L321-328

**미확인(갭)**: HumanoidVerse 로봇별 YAML, Fourier GR-1 공식 설정, MIT Humanoid vy 수치, Agility Digit 별도 논문.
