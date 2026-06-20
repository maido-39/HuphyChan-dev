# Real-World Humanoid Locomotion with Reinforcement Learning
**저자**: Ilija Radosavovic, Tete Xiao, Bike Zhang, Trevor Darrell, Jitendra Malik, Koushil Sreenath (UC Berkeley) · **발표**: Science Robotics 2024 (vol. 9, eadi9579); preprint arXiv:2303.03381, v2 Dec 2023 · [📄 원문](https://arxiv.org/abs/2303.03381)

> **한 줄**: A causal-transformer policy over proprioceptive obs-action history, trained with massively parallel RL + teacher distillation and deployed zero-shot, walks the Digit humanoid outdoors with the toe motors deliberately kept OUT of the policy on fixed PD.

## 문제 (왜 필요한가)
Get a full-sized humanoid (Digit) to walk robustly over diverse real-world terrain and disturbances with a single learned controller, transferred sim-to-real zero-shot, without per-environment tuning or model-based gait libraries.

## 방법
Policy = causal Transformer that takes a length-16 history of (observation, action) tokens and autoregressively predicts the next action (in-context adaptation, no weight updates at test time). Two-step training: (1) a fully-observed teacher state policy pi_s(a|s) trained with PPO; (2) a student observation policy pi_o distilled+co-trained with the joint loss L = L_RL(pi_o) + lambda * D_KL(pi_o || pi_s), where lambda is annealed to zero by the midpoint of training, so the student first imitates then surpasses the teacher. Pure on-policy (no offline data). Massively parallel Isaac Gym (4x A100, thousands of randomized envs); a 'virtual spring' high-stiffness rod model + alternating substep correction approximates Digit's closed kinematic chains (knee-shin-tarsus, tarsus-toe) that Isaac Gym cannot natively simulate. Trained policies are screened in Agility's high-fidelity simulator (which models the closed chains and sensor noise) to filter unsafe controllers, then deployed to hardware zero-shot. Action space = PD setpoints for 16 actuated joints PLUS predicted (policy-output) PD gains for the 8 actuated LEG joints. Crucially: the policy does NOT control the four toe motors; the toes are held at default position with FIXED PD gains. Reward is biomechanics-inspired and includes energy-minimization terms (no gait library, no reference trajectories, no explicit arm-swing reward).

## 핵심 결과
- Zero-shot outdoor deployment across plazas, sidewalks, running tracks, grass; over one week of full-day outdoor testing with NO falls and no safety gantry.
- Robust to large sudden disturbances: yoga-ball throws, stick pushes, back-pulls; recovers without falling (fails only under excessive sustained cable pulls).
- Carries varied payloads (empty/loaded backpack, handbag, loaded trash bag, paper bag) and adapts even though balance relies on arm swing.
- Fast walking: reaches commanded 1 m/s from rest within ~1 s and tracks it for the course.
- Beats Agility's state-of-the-art company controller in sim on steps and unstable planks (company controller shuts off on foot-trapping); step-recovery and foot-trapping recovery are EMERGENT (steps never seen in training).
- Emergent human-like contralateral arm swing with no arm-swing reward; gait adapts to slope and recovers from foot-trapping, with last-layer hidden states clustering by terrain (PCA/t-SNE).
- Ablations: Transformer > LSTM > TCN > MLP on success rate; larger context (16 > 8 > 1) helps; joint IL+RL > IL-only or RL-only.

## 핵심 수치 (재사용용)
- Robot Digit: ~1.6 m tall, 45 kg, 30 DOF; 4 actuated joints/arm; 8 joints/leg of which 6 actuated; shin+tarsus PASSIVE (leaf springs + four-bar linkage); toe actuated via rods at tarsus.
- Action space = 16 PD position setpoints + predicted PD gains for 8 leg joints; 4 toe motors NOT in policy, held at default with FIXED PD gains.
- Transformer: 4 blocks, embedding dim 192, 4 attention heads, MLP ratio 2.0, obs-embed MLP [512,512], action MLP [256,128], context window = 16, ~1.4M params; teacher MLP [512,512,256,128].
- Control rates: neural policy 50 Hz, joint PD controller 1 kHz.
- Commands: linear vx, linear vy, yaw rate; resampled every 10 s; below a small cutoff set to zero (exact ranges only in Table S1, in the paywalled supplement).
- Terrain/slopes: trained on slopes up to 10% grade; tested up to 8.7% grade (more robust at 0.2 m/s); rough-terrain lab tests commanded at 0.15 m/s.
- Speeds: fast-walking demo at 1 m/s; reaches command from rest within ~1 s.
- Loss: L = L_RL + lambda*D_KL(pi_o||pi_s), lambda annealed to 0 by mid-training; PPO, actor-critic, weights not shared.
- Compute: 4x A100 GPUs, thousands of envs, ~10B samples/day (project page).
- Last-layer hidden state dimension = 192.
- Sim-to-real DR: dynamics + terrain + delay randomization found most important; full ranges only in Table S2/S3 (paywalled supplement).

## 우리 프로젝트 관련성
Direct, verbatim precedent for our decision (c): keep the per-foot toe OUT of the policy. Digit has an ACTUATED toe and they STILL chose to exclude it from the action space and run it on fixed PD at default position, citing it as 'widely adopted.' Our toe is a PASSIVE spring (k=60 N*m/rad) with even stronger justification for exclusion -- this paper is the citation that defends our choice to reviewers/teammates. Note an important structural mismatch: Digit's passive shin/tarsus AND the toe form CLOSED kinematic chains that Isaac Gym could not simulate, forcing their virtual-spring approximation. Our toe is an open-chain passive revolute spring, which Isaac Lab CAN model natively as a joint with stiffness=60, damping>0, and zero actuation effort -- so we avoid their hardest sim problem entirely. For our velocity-command curriculum (a), their relevant signal is that they used a flat command-resampling scheme (every 10 s, no explicit speed curriculum reported) and still reached 1 m/s; they did not need a curriculum to hit ~1 m/s, but they also never pushed to 2.0 m/s, so curriculum remains our problem to solve. For sim2real (e), their concrete recipe is: dynamics + terrain + DELAY randomization are the trio that mattered, plus an intermediate high-fidelity-sim screening step before hardware. For foot vibration (b), this paper offers NO action-smoothness or joint-acceleration penalty -- they rely on energy-minimization reward terms; so it does not directly solve our ankle-chatter problem (look to Siekmann/Margolis-style smoothness terms instead).

## 왜 읽나 (한 줄)
**It is the single best published justification for excluding a toe joint from an RL locomotion policy (Digit's toe is actuated and they still froze it on fixed PD), bundled with a clean sim2real + transformer-policy recipe.**

## 한계
The exact reward weights, full command ranges, complete domain-randomization table, and PD gain values live in Supplementary Tables S1-S4, which are a separate file behind the Science.org paywall and are NOT in the public arXiv PDF -- so the most reusable numbers (reward coefficients, DR ranges, baseline PD gains) could not be extracted. Mechanism mismatch: their hard sim problem was Digit's CLOSED kinematic chains (handled by a virtual-spring hack); our passive toe is an open-chain spring and does not need this. They report NO action-smoothness or joint-acceleration regularization, so the paper does not directly inform our foot-vibration fix. No periodic-gait / contact-schedule reward (gait is emergent), so it does not inform our forefoot-loading reward (d). No velocity curriculum is described and top speed shown is ~1 m/s, so it gives little guidance for reaching 2.0 m/s without PPO collapse. Trained in Isaac Gym, not Isaac Lab; transformer policy is heavier and harder to run than the MLP/LSTM typical in rsl_rl PPO. Authors note a left/right asymmetry and imperfect velocity tracking.

## 우리 적용 (takeaway)
Cite this paper as precedent and ship our passive-toe-out-of-policy design as-is: model the toe in Isaac Lab as a joint with stiffness=60 N*m/rad, nonzero damping, and zero actuator effort (no action channel), mirroring Digit's fixed-PD toe -- and skip their virtual-spring closed-chain hack since our toe is open-chain. For sim2real, adopt their proven trio (dynamics + terrain + DELAY randomization) as the backbone of decision (e). Do NOT expect this paper to fix foot vibration or deliver 2.0 m/s -- those need a separate action-smoothness/ankle-accel penalty and an explicit command curriculum (pull from Siekmann periodic-reward and Margolis rapid-locomotion work). Borrow their two-stage teacher(MLP)->student distillation idea only if a privileged-info teacher is cheap; otherwise stick with single-stage rsl_rl PPO since our env is simpler than Digit.

## 관련 링크
- [arXiv abstract + full preprint PDF (28 pp; main text + methods, but NO supplement tables)](https://arxiv.org/abs/2303.03381)
- [Project page with videos and ~10B samples/day claim](https://learning-humanoid-locomotion.github.io)
- [Science Robotics published version (paywalled; supplement Tables S1-S4 with reward weights/DR ranges live here)](https://www.science.org/doi/10.1126/scirobotics.adi9579)
- [Berkeley Hybrid Robotics hosted Science Robotics PDF (12 pp article body)](https://hybrid-robotics.berkeley.edu/publications/ScienceRobotics2024_Learning_Humanoid_Locomotion.pdf)
