# 원자료 — 비대칭 actor-critic(특권 critic) 관측 분할 전수조사 (2026-08-24, Sonnet 서브에이전트)

## 코드베이스별 actor vs critic 전용
| 코드베이스 | actor obs | critic 전용 | 방식 |
|---|---|---|---|
| legged_gym | `base_lin_vel, base_ang_vel, proj_g, cmd, q−def, dq, act` (+heights) | **없음(죽은 코드)** — `num_privileged_obs=None` | 스캐폴드만 |
| IsaacLab (velocity) | `PolicyCfg`에 base_lin_vel 포함 | **shipped config에 CriticCfg 없음** | 기본 대칭 |
| unitree_rl_gym Go2 | legged_gym 그대로 | 없음 | — |
| **unitree_rl_gym G1/H1** | `ang_vel, proj_g, cmd, q−def, dq, act, sin/cos phase` (47) | **actor ∪ {base_lin_vel}** (50) | 단순 비대칭 |
| walk-these-ways | `proj_g, q−def, dq, act`(+플래그), `observe_vel=False` | friction·restitution·payload mass·CoM·motor strength/offset·body height·body vel·clock·desired contact | **RMA형**: actor는 `cat(obs_history, adaptation_module(obs_history))` |
| **humanoid-gym XBot-L** | `cmd, q, dq, act, ang_vel, euler` **15프레임 스택**(705) | +`base_lin_vel`, ref diff, **rand_push_force/torque, env_frictions, body_mass, stance_mask, contact_mask** (3프레임, 219) | 비대칭 + 스택 깊이도 다름 |
| HumanoidVerse | `*_wolinvel*`: ang_vel, proj_g, cmd, q, dq, act, short_history | +`base_lin_vel`만 | 대칭/비대칭 YAML 둘 다 제공 |
| Berkeley Humanoid | 공유 `PolicyCfg`(base_lin_vel 포함) | **없음** | 완전 대칭(반례) |
| **Booster T1** | `proj_g, ang_vel, cmd, gait phase, q−def, dq, act` (47) | `base_mass_scaled, base_lin_vel, base_height_rel_terrain, pushing_forces, pushing_torques` (14) | 비대칭 |
| **mjlab(공개판)** | base_lin_vel을 **velocimeter 센서 + Unoise(±0.5)**로 actor에 유지 | 같은 항 **노이즈 제거** + foot_height/air_time/contact/contact_forces | "같은 센서, 노이즈만 제거" 중간형 |

## base_lin_vel 판정
- **critic 전용**: unitree G1/H1(47 vs 50, Δ3), humanoid-gym, Booster T1, HumanoidVerse `*_wolinvel*`
- **actor에 그대로**: legged_gym, IsaacLab shipped, Berkeley Humanoid (하드웨어 튜닝 안 된 계보)
- **추정기로 대체**: walk-these-ways(adaptation module), DreamWaQ(CENet), RMA, DWL
- 어느 레포도 "하드웨어에서 측정 불가"를 **주석으로 명시하지 않는다** — 패턴에서 추론된 관행(HumanoidVerse의 `wolinvel` 파일명이 유일한 암시).

## 그 밖의 항목
- 접촉력/접촉상태: humanoid-gym·mjlab **critic 전용**, Booster는 **양쪽 모두 제외**(보상·종료에만), unitree/legged_gym 없음.
- 발 air time: **mjlab만** critic 전용.
- 지형 height scan: humanoid-gym critic 전용, IsaacLab·legged_gym은 actor.
- **DR 파라미터(마찰·질량·CoM·모터강도)**: walk-these-ways(플래그) / **humanoid-gym `env_frictions·body_mass`** / **Booster `base_mass_scaled`** = critic 전용. legged_gym·IsaacLab·**mjlab은 어느 쪽에도 안 넣음**.
- **외력(push)**: humanoid-gym `rand_push_force/torque`, Booster `pushing_forces/torques` = critic 전용.
- 관절 토크: **어디에도 없음**.

## 논문 근거(수치)
- **Pinto 2017**(arXiv:1710.06542) 비대칭 AC 원조(DDPG+HER, 이미지): 실기 Asym **5/5·5/5·5/5** vs Sym **0/5·0/5·0/5**.
- **Lee 2020**(2010.11251) teacher-student: 학생 직접 RL은 "경사·계단 통과 불가"로 실패. 배포 학생은 16.8 cm 계단 zero-shot, 숲 시험 "한 번도 실패 없음".
- **RMA**(2107.04034): 특권 17차원 → 8차원 latent, 50스텝 고유수용 히스토리로 회귀. A1이 12 kg(체중 100 %) 운반, 15 cm 하강 80 %, 기름 90 %.
- **DreamWaQ**(2301.10602, Nahrendra/Yu/**Myung**): CENet이 **base lin vel을 회귀해 actor에 넣는다**(학습·배포 모두). 밀기 회복 0.511→**1.121 m/s**(2.2×), 생존율 20.51→**95.23 %**. "CENet vs 순수 비대칭 critic" 단독 ablation은 없음.
- **Gu 2024 DWL**(2408.14472): 비대칭 critic(마찰·push·질량·토크·96차원 height scan) + GRU denoising 추정기. 실기 경사 100 vs 80 %, 계단오름 **100 vs 20 %**, 내림 100 vs 60 %, 불규칙 100 vs 20 %, IMU 드리프트 −87 %.
- **Wu 2024 Learn to Teach**(2402.06783): 단일단계 혼합 학습으로 표준 2단계 대비 샘플 **50 % 절감**.
- **반례**: Radosavovic(2303.03381, 2402.19469) — 특권 critic도 distillation도 없이 causal transformer + 고유수용 히스토리로 in-context 적응.

## 실패 모드
1. **history aliasing**: Baisero & Amato(2105.11674) 정리 4.1 — 부분관측에서 시불변 상태가치 `V^π(s)`는 **일반적으로 정의되지 않음**; 4.2 — 정의돼도 `V^π(h)`의 **편향 추정**. 8개 POMDP·20시드에서 상태 critic(A2C-asym-s)은 "과제를 완전히 실패하거나 준최적으로 느리게 수렴", Cleaner에선 "성능 붕괴". Pinto 2017을 지목해 "평가 환경이 사실상 완전관측이라 이 실패가 안 드러났다"고 비판.
2. **이론적 반대편**: Lambrechts, Ernst, Mahajan(ICML 2025, 2501.19116) — 특권 입력이 **history-sufficient**면 비대칭이 aliasing 오차를 없앤다. 즉 문제는 "순수 상태" critic.
3. Kausik(2509.26000): 완전상태 가정이 비현실적, 선택적 신호만으로 동등 이상.
4. SoloParkour(2409.13678) Fig.4b: "No Priv. Critic" 변형은 동일 연산 예산에서 성능 하락(Climb 40 cm에서 완주율 ~100 %→50 % 미만).
5. ★추론(단일 실험 증거 아님): 가장 어려운 sim2real을 다룬 연구는 **전부 지도학습 추정기/distillation 층을 얹는다** — 순수 critic 비대칭만으로는 부족하다는 실무적 판단으로 보임.

## 종합
- `base_lin_vel` critic 전용 = 하드웨어 튜닝된 휴머노이드 코드베이스의 **사실상 표준**(9개 중 5개). 남은 건 미튜닝 계보.
- 풍부한 특권 정보(지형·접촉·DR·외력)는 두 갈래: (A) **순수 비대칭 PPO**(unitree G1/H1, humanoid-gym, Booster, mjlab) — 단순, (B) **teacher-student/추정기**(walk-these-ways, Lee, RMA, Miki, DreamWaQ, DWL) — 최난도 전이용, 실기 2~5× 개선 보고.

## 출처
legged_gym 8fa29ac · IsaacLab b0542fe · unitree_rl_gym 276801e · walk-these-ways 0e7236b · humanoid-gym ae46e20 · HumanoidVerse 101492b · isaac_berkeley_humanoid ffc7b26 · booster_gym da396a0 · mujocolab/mjlab 0fb8a68 (공개판)
arXiv: 1710.06542, 2010.11251, 2107.04034, 2201.08117, 2301.10602, 2408.14472, 2402.06783, 2303.03381, 2402.19469, 2409.13678, 2105.11674, 2501.19116, 2509.26000
