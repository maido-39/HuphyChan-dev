# Ankle plantarflexion PUSH-OFF demand (51.8 kg biped) vs RS03 (60 N.m peak)

date:: 2026-06-22
tags:: #research #ankle #pitch #pushoff #hardware #RS03 #actuator-sizing
related:: [[37_ankle_linkage_fidelity]] [[38_parallel_ankle_sim2real]] [[39_ankle_qdd_uptorque_survey]] [[36_all_actuator_tn_envelopes]] [[21_motor_power_weight]]
context:: gaitfix_v4 MEASURED tau_ankle_pitch CLIPS at -60 N.m (= RS03 peak) during plantarflexion EVEN with push-off rewards turned down. gaitfix_v6 will RESTORE push-off -> demand rises. Q: is RS03 genuinely under-spec, and what is the fix?

## TL;DR verdict

**RS03 (60 N.m peak) is UNDER-SPEC for a human-like push-off by ~20-40%.**
Biomechanically-scaled peak plantarflexion moment for 51.8 kg = **~72-83 N.m** (1.4-1.6 N.m/kg).
We already clip at 60 with a WEAK push-off; restoring push-off only widens the gap.

Operating point is the HARD quadrant: **high torque AND moderate speed simultaneously**
(~72-83 N.m at ~3-5 rad/s ankle plantarflexion rate), peaking ~130-210 W mechanical.

## Demand BAND (51.8 kg, normal->brisk walking)

| Quantity | Normalized (human) | Scaled to 51.8 kg | Notes |
|---|---|---|---|
| Peak PF moment | 1.4-1.6 N.m/kg | **72-83 N.m** | self-selected speed; rises with speed |
| Peak PF moment (slow/low-demand) | ~1.2-1.3 N.m/kg | ~62-67 N.m | a 50 kg robot at modest speed could sit here |
| Peak ankle power | 2.5-4.0 W/kg | **130-210 W** | A2 burst, late stance |
| PF angular velocity @ peak power | -- | **~3-5 rad/s** | from prosthesis-design req (4 rad/s max) |
| Push-off timing | -- | ~49-66% stride, peak ~60% | impulsive burst |

Cross-check (powered ankle prosthesis design targets, scale them down):
- Au/Herr powered ankle (85.7 kg subject): **~110 N.m** peak torque target.
- PEA/EHA prosthesis design req (75 kg male): **120 N.m peak, 4 rad/s max, 0.2 s recovery.**
- Linear-scale 120 N.m * (51.8/75) = **~83 N.m** -> matches the 1.6 N.m/kg upper band exactly.
- 110 N.m * (51.8/85.7) = ~66 N.m (lower band, Au target was a bit conservative on torque, leaned on parallel spring).

So independent literature (gait normative AND prosthesis actuator-sizing) converges:
**51.8 kg human-like push-off wants ~66-83 N.m peak, RS03 gives 60. Shortfall ~10-38%.**

## (2) Does it EXCEED RS03 60 N.m? By how much?
YES.
- Midband 1.5 N.m/kg -> 78 N.m -> **+30% over the 60 N.m clip.**
- Upper 1.6 N.m/kg -> 83 N.m -> **+38%.**
- Even a reduced-demand robot target (1.3 N.m/kg) -> 67 N.m -> **+12%.**
RS03 60 N.m is below even the conservative end. We measured a clip with a WEAK gait => consistent.

## (3) Speed dependence / does a 50 kg robot need full 1.6 N.m/kg?
- Ankle moment + power both rise monotonically with walking speed; the A2 power burst is the
  most speed-sensitive joint output (Zelik/Kuo: peak ankle power 16 W @0.9 m/s -> 24 W @1.4 -> 30 W @1.8
  for ONE 76 kg subject's segment, i.e. strongly speed-dependent).
- At SLOW / modest robot speeds (<~1.0 m/s) peak PF moment is nearer ~1.2-1.3 N.m/kg => ~62-67 N.m,
  still above 60.
- A 50 kg robot does NOT strictly need the full human 1.6 N.m/kg if we accept a slow, low-propulsion gait
  -- BUT our gaitfix_v6 goal is explicitly a NATURAL push-off gait, which pushes toward the upper band.
- Note normalization caveat: human PF moment is ~constant in N.m/kg, but our robot has a different
  foot length / ankle-to-toe lever and CoP path; if the robot's effective lever is shorter than a human's,
  required ankle torque for the same propulsive GRF can be HIGHER, not lower.

## The torque-SPEED point is the real problem (not torque alone)
Push-off is the hard quadrant of the T-N plane: peak torque (~75-83 N.m) and moderate speed
(~3-5 rad/s = ~170-290 deg/s) occur TOGETHER, demanding ~130-210 W mech right there.
A QDD motor's continuous T-N envelope droops with speed; sustaining peak torque AT speed is exactly
where a low-gear QDD struggles. So the fix must raise BOTH the torque ceiling AND hold it at ~4 rad/s.

## Fix options (ranked for our 1:1 relocated linkage)
1. **Increase linkage/gear ratio above 1:1** (e.g. 1:1.4-1:1.7). Cheapest: multiplies RS03's 60 N.m
   output torque to ~84-102 N.m, covering the full human band. Cost: ankle speed divides by the same
   ratio -> check we still hit ~4 rad/s plantarflexion rate. RS03 no-load speed must support
   4 rad/s * ratio. This is the FIRST thing to try (mirrors knee 1:2.5/1:1.5 belt decisions).
2. **Bigger motor (RS04-class)** if RS03 even after gearing can't hold torque at 4 rad/s (T-N droop).
   See [[33_knee_actuator_landscape]] / [[39_ankle_qdd_uptorque_survey]].
3. **Parallel elastic / SEA ankle** — every powered-ankle design (Au-Herr, PEA/EHA) uses a parallel
   spring engaging at the push-off angle to cut MOTOR peak torque to the peak-POWER requirement.
   This is the human strategy (Achilles tendon elastic recoil supplies a large fraction of A2).
   Most HW-efficient, most mechanically complex. Strong candidate if we want RS03 to survive.
4. **Passive toe** — toe research: a non-coupled passive toe dissipates ~45% of push-off power, i.e.
   it BLEEDS push-off energy rather than supplying torque; it lowers the realizable propulsion, not the
   ankle's burden during active push-off. It reduces demand only by accepting a weaker gait. Not a
   substitute for ankle torque if we want natural push-off.

Recommended: try (1) gear-up first, measure gaitfix_v6 ankle T-N point, then decide (2) vs (3).

## Sources (raw excerpts in log)
- Zelik & Kuo / unified push-off perspective, PMC5201006 — peak ankle power >2.5 W/kg, ">3x other joints",
  push-off 49-66% stride; segment peak 16.2/23.6/30.0 W at 0.9/1.4/1.8 m/s (N=9). https://pmc.ncbi.nlm.nih.gov/articles/PMC5201006/
- Reduced-plantarflexion walking, PMC4664043 — peak ankle power can exceed 2.5 W/kg ">three times the
  maximum power produced by other joints"; 1.4 m/s, 76.6 kg subjects; push-off ~49-66% stride.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/
- AFO knee/orthosis control, NCT05209360 / exosuit lit — control peak ankle PF moment ~1.4 N.m/kg.
  https://www.sciencedirect.com/science/article/pii/S0021929018308583
- Au-Herr powered ankle prosthesis, PMC4480765 — ~110 N.m peak ankle torque target, 85.7 kg subject,
  parallel spring 4.2 N.m/deg. https://pmc.ncbi.nlm.nih.gov/articles/PMC4480765/
- PEA/EHA prosthesis design req, PMC9776366 — meets load with **120 N.m peak, 4 rad/s max, 0.2 s recovery,
  acceptable for 75 kg male**; PEA cuts motor torque req to the peak-POWER req. https://pmc.ncbi.nlm.nih.gov/articles/PMC9776366/
- Design opt to reduce peak power, PMC10364942 — spring+actuator coupling minimizes actuator peak power.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10364942/
