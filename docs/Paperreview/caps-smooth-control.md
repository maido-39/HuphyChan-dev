# Regularizing Action Policies for Smooth Control with Reinforcement Learning (CAPS)
**저자**: Siddharth Mysore, Bassel Mabsout, Renato Mancuso, Kate Saenko (Boston University; Saenko also MIT-IBM Watson AI Lab). First two authors contributed equally. · **발표**: IEEE ICRA 2021 (arXiv 2012.06644v2, 26 May 2021) · [📄 원문](https://arxiv.org/abs/2012.06644)

> **한 줄**: A two-term action-policy regularizer (temporal + spatial smoothness) added directly to the policy loss of any continuous-control RL algorithm; it eliminates high-frequency control jitter and gives ~80% power savings on a real quadrotor with no reward engineering.

## 문제 (왜 필요한가)
Deep-RL continuous-control policies emit jittery, oscillatory action signals. On real hardware this causes visible vibration, motor overheating, high power draw, hardware wear, and poor sim2real transfer. Prior fixes were hand-engineered smoothing rewards (brittle, indirect, no guarantees) or output filters (which break the Markov assumption, fight the policy's overfit dynamics model, and can cause catastrophic loss of control). This is precisely our foot-vibration / action-jitter problem.

## 방법
CAPS = Conditioning for Action Policy Smoothness: two penalties added directly to the POLICY objective, leaving the critic/value update untouched. Objective (eq.1): J_CAPS = J_pi - lambda_T*L_T - lambda_S*L_S. (1) TEMPORAL term L_T = D(pi(s_t), pi(s_{t+1})) penalizes consecutive actions for differing, using the actually-visited next state (no extra env access, free in PPO rollouts). (2) SPATIAL term L_S = D(pi(s_t), pi(s_bar)) where s_bar ~ phi(s_t)=Normal(s, sigma): a perturbed nearby state is sampled from a Gaussian around the current obs and the policy is pushed to map both to similar actions. Both distance measures D are Euclidean L2 ||a1-a2||_2. Together they approximately minimize the temporal and spatial Lipschitz constants of the policy around visited states. sigma is set from expected sensor measurement noise / tolerance. CAPS is algorithm-agnostic (demonstrated on DDPG, TD3, SAC, PPO), needs zero changes to the environment or reward, and adds one extra forward pass per step (for s_bar) plus reuse of the next-state action. The spatial term doubles as a domain-randomization-like robustness mechanism for sim2real.

## 핵심 결과
- Real quadrotor (PPO, bare tracking-error reward): ~80% power reduction and 96% smoothness improvement vs SOTA Neuroflight.
- Live-flight current draw: 22.87 A (Neuroflight), 8.07 A (tuned PID) -> 4.6-4.9 A with CAPS (more efficient than PID).
- Live-flight smoothness Sm*1e3: PID 0.4, Neuroflight 4.3, PPO+CAPS 0.16; tracking MAE under 10 deg/s.
- Ablation: temporal-only noisy in transfer (Sm 1.10), spatial-only bands the output and wrecks tracking (MAE 14.85 deg/s); BOTH needed.
- 100% of CAPS agents flight-worthy over 10 seeds vs cherry-picking for Neuroflight.
- Trains in 1M timesteps: 90% less data and 8x faster wall-time than Neuroflight.
- Gym (4 tasks x 4 algos, 11 seeds): lower Sm on every task; reward roughly preserved and improved on Ant (TD3 3088->3872, PPO 3735->4257).

## 핵심 수치 (재사용용)
- Objective: J_CAPS = J_pi - lambda_T*L_T - lambda_S*L_S (eq.1)
- L_T = ||pi(s_t) - pi(s_{t+1})||_2  (temporal, L2)
- L_S = ||pi(s_t) - pi(s_bar)||_2,  s_bar ~ Normal(s_t, sigma)  (spatial, L2)
- sigma: set from expected measurement noise/tolerance (per-obs std; exact values are in the website ablation, not the paper body)
- lambda_T, lambda_S: tuned per algorithm/env via ablation on http://ai.bu.edu/caps (the paper body does not tabulate them; treat as the two hyperparams to sweep)
- Smoothness metric Sm = (2/(n*f_s)) * sum_i(M_i * f_i)  (eq.4): FFT amplitude M_i at freq f_i, sampling freq f_s, Nyquist f_s/2 - the mean amplitude-weighted normalized frequency; lower = smoother
- Real-quadrotor results: ~80% power down, 96% smoothness up, Sm 4.3->0.16 (x1e3), current 22.87A->~4.6A
- Training: 1M timesteps, 90% less data, 8x faster wall-time vs Neuroflight; 100% flight-worthy over 10 seeds
- Gym: 4 tasks (Pendulum-v0, LunarLanderContinuous-v2, Reacher-v2, Ant-v2), 4 algos (DDPG/SAC/TD3/PPO), 11 seeds, hyperparams from stable-baselines zoo

## 우리 프로젝트 관련성
Directly targets decision (b): our verified foot-vibration defect. Per project memory, current penalties are dof_acc_l2 over HIP_KNEE joints only (ankles+toe excluded, velocity_env_cfg.py:215) and action_rate_l2=-0.005 (first-order only, no jerk). CAPS is a cleaner, principled replacement/complement: add L_T = ||a_t - a_{t-1}||^2 (temporal) over ALL 12 actuated joints to attack high-freq jitter at its source, and L_S = ||pi(o_t) - pi(o_t+noise)||^2 (spatial) to make the policy robust to obs noise on real ankle/IMU sensors. The spatial term also serves decision (e) sim2real: it is effectively built-in observation-space domain randomization on the smoothness side. Because CAPS lives in the policy loss (not env/reward), it composes with our rsl_rl PPO manager-based env without touching IsaacLab source (hard constraint satisfied) - implement as a custom loss term in our external pygmalion_locomotion package. Toe stays correctly PASSIVE and out of the policy (decision c): CAPS only regularizes the 12 actuated action dims, never the toe spring. For decision (a) the 2.0 m/s curriculum: CAPS's finding that smoothness rarely costs reward (and sometimes helps on Ant, a legged task) suggests adding it should not block speed scaling and may stabilize PPO against the collapse you're guarding against.

## 왜 읽나 (한 줄)
**It is the canonical, minimal, drop-in recipe for killing RL control jitter - exactly our foot-vibration fix - with a real-robot demonstration (80% power, 96% smoothness) and an ablation proving you need BOTH temporal and spatial terms.**

## 한계
Demonstrated on a quadrotor attitude controller and Gym benchmarks, NOT on a legged biped - no contact dynamics, no gait, no ground-reaction-force coupling, so transfer to forefoot loading / contact-schedule rewards (our decision d) is untested. The exact lambda_T, lambda_S and per-dim sigma values are NOT in the paper body (they live in the website ablation), so you must sweep them yourself; CAPS is sensitive to these and to which action representation you L2-penalize. Spatial-only over-regularization forces actions into discrete bands and hurt tracking (MAE 14.85 deg/s) - over-weighting lambda_S could similarly flatten gait. Smoothing makes the policy more 'conservative,' which gave a small reward hit on some tasks and could cap peak push-off effort if lambda is too high - watch that it does not suppress the forefoot loading you actually want. The temporal term assumes the next state in the rollout is on-policy; fine for PPO. Paper offers no theory for stability/contact-rich systems.

## 우리 적용 (takeaway)
Implement CAPS as the foot-vibration fix instead of (or alongside) patching dof_acc_l2. Concretely: in our rsl_rl PPO policy loss add L_T = mean(||a_t - a_{t-1}||^2) over all 12 actuated joints and L_S = mean(||pi(o_t) - pi(o_t + N(0,sigma))||^2) with sigma per-obs from our sensor-noise model; this also extends accel/jerk regularization to the ankles that are currently uncovered. Start small and sweep: lambda_T around 1.0 and lambda_S around 1.0 (paper's order of magnitude) and tune via the Sm FFT metric on logged action signals - adopt Sm = (2/(n*f_s)) sum M_i f_i as our quantitative jitter KPI on CSV action logs at our 200 Hz control rate. Keep the toe passive and excluded. Verify it does NOT suppress forefoot push-off before committing, and re-tune lambda jointly with the velocity curriculum toward 2.0 m/s. Prefer this over output low-pass filtering, which the paper shows can catastrophically destabilize NN controllers.

## 관련 링크
- [Project website with code, ablation tables (lambda/sigma values), filter-failure demos, and full results](http://ai.bu.edu/caps)
- [Neuroflight - the quadrotor flight-control firmware/baseline CAPS is compared against (Koch et al.)](https://arxiv.org/abs/1901.06553)
- [Shen et al. 'Deep Reinforcement Learning with Smooth Policy' - concurrent spatial-only smoothing the paper contrasts with](https://arxiv.org/abs/2003.09534)
