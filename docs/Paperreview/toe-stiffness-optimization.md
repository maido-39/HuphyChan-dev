# Optimizing toe joint stiffness to improve human-like walking
**저자**: Kwonseung Cho, Kang-Woo Lee, Pilwon Hur (Dept. of Mechanical and Robotics Engineering, Gwangju Institute of Science and Technology, South Korea) · **발표**: Scientific Reports, vol. 15, art. 33268, 2025 · [📄 원문](https://www.nature.com/articles/s41598-025-17957-4)

> **한 줄**: A trajectory-optimization study plus a 20-subject human boot experiment that pins the best fixed passive toe (MTP) joint stiffness at ~0.98-1.04 N*m/deg, i.e. ~56-60 N*m/rad.

## 문제 (왜 필요한가)
How stiff should a passive toe (metatarsophalangeal) joint be to produce human-like, comfortable, energetically reasonable walking? The toe must do two conflicting jobs: be compliant during mid-stance rollover (heel-to-toe progression) yet stiff during terminal-stance push-off to transfer energy. The paper asks what single passive stiffness best trades these off, and whether stiffness should really be time-varying.

## 방법
Two parts. (1) SIMULATION: sagittal-plane bipedal walker, 80 kg / 1.83 m, compared as a 7-link model (rigid foot, no toe) vs a 9-link model that adds a passive toe segment (0.08 m, 0.2 kg; heel-to-MTP-axis 0.20 m). Gait solved by direct collocation (Hermite-Simpson) minimizing the sum of squared joint torques (TSS) as an effort proxy instead of metabolic cost. Solver IPOPT 1.6.3 via JuMP 1.22.2 in Julia 1.10.4; hybrid contact model with 5 stance domains (LTO->RHO->LHS->LTS->RTJO->RTO), Coulomb friction, inelastic impacts. They extract the toe joint's time-varying angle-torque relation per domain and average it over the push-off domain (Domain 5) to get a single representative stiffness. (2) EXPERIMENT: 20 healthy adults (10M/10F, 25.8+/-4.2 yr, 56.9+/-8.7 kg, 1.66 m) walked over a 6 m instrumented walkway in adjustable-stiffness toe boots (28 cm foot, 20 cm heel-to-MTP, 1095-spring-steel cantilever) at five conditions: 0, 0.56, 0.98, 1.4 N*m/deg, and rigid/infinite. Measured kinematics/kinetics (Nokov 9-camera mocap, AMTI force plate, Visual3D) and a 5-point Likert preference. Subjects split into Group 1 (>=175 cm, near the 1.83 m sim model) and Group 2 (<175 cm).

## 핵심 결과
- Simulation push-off-phase toe stiffness (Domain 5 average) = ~1.04 N*m/deg (= ~59.6 N*m/rad). Closest spring realizable = 0.98 N*m/deg (= ~56.1 N*m/rad), used as the experimental optimum.
- Toe stiffness is fundamentally TIME-VARYING: near-rigid during loading (Domain 1), drops to ~0 for rollover (Domains 2-3), then rises sharply in late push-off (Domain 5). A single fixed value is a compromise.
- Adding the passive toe (9-link vs 7-link) lowered effort objective (~8.08e6 vs 8.27e6 normalized), increased step length 0.61->0.68 m and walking speed 0.86->1.07 m/s.
- Experiment: 0.98 N*m/deg won or near-won subjective preference. Group 1 (tall, sim-matched): 0.98 scored 4.3/5 (highest), rigid scored 1.7/5 (lowest). Group 2 (short): 0 N*m/deg preferred (4.3/5), 0.98 second (3.5/5), rigid worst (1.6/5).
- Rigid/infinite stiffness was consistently the worst across both groups -- a hard joint is anti-human-like.
- Heel-off timing shifted with stiffness: 0 N*m/deg gave earliest heel-off (~50% gait cycle); higher stiffness progressively delayed it. Stance time shortest at 0 N*m/deg.
- Spatiotemporal gross measures (swing time, stride length, walking speed) showed NO significant differences across stiffness -- the effect is in the push-off/rollover detail, not gait speed.
- Sensitivity: optimization robust to model HEIGHT (162-183 cm, cost change 4.2%, sensitivity coeffs <0.75) but FAILED TO CONVERGE under mass perturbation (75-85 kg), i.e. gait dynamics are highly mass-sensitive.

## 핵심 수치 (재사용용)
- Optimal toe stiffness (sim): 1.04 N*m/deg = 59.6 N*m/rad
- Optimal toe stiffness (experimental, realizable): 0.98 N*m/deg = 56.1 N*m/rad
- Tested conditions: 0 / 0.56 / 0.98 / 1.4 N*m/deg + rigid = 0 / 32.1 / 56.1 / 80.2 N*m/rad + inf
- Sim model: 80 kg, 1.83 m; toe segment 0.08 m / 0.2 kg; heel-to-MTP 0.20 m
- 9-link walking speed 1.07 m/s, step length 0.68 m (vs 7-link 0.86 m/s, 0.61 m)
- Subjects: n=20, 56.9+/-8.7 kg, 1.66 m; Group split at 175 cm height
- Foot/boot: 28 cm length, 20 cm heel-to-MTP, 1095 spring steel cantilever
- Effort metric: sum of squared torques (TSS), not metabolic cost
- Height-robust (162-183 cm, 4.2% cost change); mass-fragile (no convergence at +/-5 kg)

## 우리 프로젝트 관련성
Direct calibration of decision (c): keep the toe passive and out of the policy. Our k=60 N*m/rad sits almost exactly on the paper's simulation optimum of 1.04 N*m/deg = 59.6 N*m/rad, and just above the experimentally-preferred 0.98 N*m/deg = 56.1 N*m/rad. So 60 N*m/rad is well-justified as a fixed passive value -- it lands in the 56-60 N*m/rad sweet spot this paper validates. Two caveats specific to us: (1) the paper's optimum is for an 80 kg / 1.83 m human; our biped is 51.8 kg / 0.87 m, much lighter and shorter, and they explicitly show gait dynamics are highly mass-sensitive (convergence failed at +/-5 kg on an 80 kg model). A lighter robot generally wants LOWER absolute push-off torque, so 56-60 N*m/rad may be slightly stiff for 51.8 kg -- worth a sweep of ~30-60 N*m/rad in sim before locking it. (2) The true optimum is time-varying (compliant in rollover, stiff in push-off); a single linear spring is a known compromise, which is the main argument someone could later make for a series-elastic or variable-stiffness toe -- but for now passive-fixed is defensible and human-preferred over rigid.

## 왜 읽나 (한 줄)
**It is the one paper that gives you a defensible number for your passive toe spring: ~56-60 N*m/rad is the human-validated optimum, bracketing your k=60 almost perfectly.**

## 한계
No metabolic cost measured -- effort is proxied by sum of squared torques, so energy claims are indirect. Experiment is level-ground only, self-selected speed, 20 healthy young adults (none at 2.0 m/s, none amputees). Simulation is a simplified sagittal passive walker tuned to an 80 kg / 1.83 m human, far from our 51.8 kg / 0.87 m biped, and the authors admit no direct numeric model-vs-experiment match plus failure to converge under mass changes -- so the absolute stiffness does NOT transfer one-to-one to a much lighter robot. Only a fixed linear stiffness was experimentally tested, never the time-varying profile the simulation says is ideal. Sensitivity is shown for height but not for foot length / MTP-axis placement, which would shift the effective moment arm and hence the equivalent stiffness on our hardware.

## 우리 적용 (takeaway)
Keep the toe passive and out of the PPO action space (decision c is well-supported). Treat k=60 N*m/rad as a sensible default but verify it for our 51.8 kg mass: run a sim sweep of toe stiffness over ~30-60 N*m/rad and pick the value that minimizes ankle/toe push-off torque while preserving forefoot loading, since the paper's optimum was tuned to an 80 kg human and gait is mass-sensitive. When designing decision (d), the contact-schedule / periodic-gait reward, use this paper's domain structure as the target: toe should be near-free during mid-stance rollover and only load late in stance (push-off), with heel-off near ~50-60% gait cycle -- reward forefoot GRF in terminal stance, not throughout. Note that the actual biomechanics want a time-varying stiffness; if a single passive spring ever shows push-off energy deficits in sim, that is the documented reason to consider a series-elastic toe later rather than putting the toe into the policy.

## 관련 링크
- [Open-access full text (PMC) -- use this, Nature HTML/PDF redirect to a login](https://pmc.ncbi.nlm.nih.gov/articles/PMC12475067/)
- [PubMed record (PMID 41006515)](https://pubmed.ncbi.nlm.nih.gov/41006515/)
- [Related: effect of toe joint stiffness and toe shape on walking biomechanics (prior human study)](https://pubmed.ncbi.nlm.nih.gov/30187893/)
- [Related: mobile arch + toe joint + joint coupling in predictive neuromuscular walking sim (Sci Rep 2024)](https://www.nature.com/articles/s41598-024-65258-z)
- [Related: adding a toe joint to a below-knee prosthesis -- energetics and preference (Sci Rep 2021)](https://www.nature.com/articles/s41598-021-81565-1)
