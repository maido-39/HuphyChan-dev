# Equality connect/weld solref·solimp conventions — raw findings (2026-08-24)

Workflow `equality-solimp-conventions` (6 haiku search lenses → 14 haiku raw-XML extractions → sonnet brief). Verified by Fable directly: Cassie/Menagerie, Robotiq 2F-85, ALOHA, ToddlerBot mjx, og_bruce, MuJoCo modeling/computation pages. Summary + decision: [docs/94](../94_loop_constraint_stiffness.md).

## Sonnet brief (unedited)

# Decision Brief: solref/solimp convention for the 2-RSU ankle loop `<connect>` equalities

**Our current setting:** `solref="0.002 1"` `solimp="0.999 0.9999 0.0001"` (midpoint/power default to 0.5/2, unset), dt=5 ms training in mjlab/mujoco_warp. Under refsafe (`timeconst = max(timeconst, 2*dt)`), the declared 2 ms timeconst is **floored to 10 ms** at training time — a 5x softening the XML doesn't show. (source: https://mujoco.readthedocs.io/en/latest/mjwarp/index.html)

---

## 1. What real models do

### 1a. Extraction-verified rows (fetched and confirmed this pass)

| Model | Equality | solref | solimp | dt | RL use | Source |
|---|---|---|---|---|---|---|
| Cassie `cassie.xml` (OSU DRL) | connect ×4 (2 plantar-rod→foot, 2 achilles-rod→heel-spring) | **0.005 1** (set, default `<equality>` class) | **0.9 0.95 0.001 0.5 2** (MuJoCo default — not overridden in file) | 0.0005 (0.5 ms) | Yes, OSUDRL RL | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml |
| Cassie `cassie_noise_terrain.xml` | connect ×4, identical topology | 0.005 1 | 0.9 0.95 0.001 0.5 2 | 0.0005 | Yes | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml |
| Cassie `cassiepole.xml` | connect ×4, identical topology | 0.005 1 (inherited from default class) | 0.9 0.95 0.001 0.5 2 (default) | 0.0005 | Yes | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml |
| dm_control Quadruped | tendon `fixed` ×4, leg coupling (not a rod loop, but the only other verified equality with non-default numbers) | **0.005 0.5** (explicit, `class="coupling"`) | **0.95 0.99 0.01** (explicit) | 0.005 | Yes | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml |
| Gymnasium Humanoid | option only confirmed; equality not re-verified this pass | n/a confirmed | n/a confirmed | 0.003 | Yes | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/humanoid.xml |
| Hopper, Walker2D, Ant, HalfCheetah, Swimmer, Cheetah, Finger, CMU-V2019/2020 | **none found** in fetched XML | — | contact solref/solimp only (0.02 1 / 0.8 .8 .01 typical) | 0.002–0.01 | Yes (no loop closure at all) | see FINDINGS list |

**Key honest takeaway from the verified set alone:** almost none of the standard RL locomotion benchmarks have a kinematic loop at all — Cassie is the only extraction-verified case of an actual rod-loop `connect`, and its convention is flat: **`solref 0.005 1` + unmodified MuJoCo default solimp (0.9/0.95/0.001)**. That is *softer* on both axes than our current 0.002/0.999-0.9999-0.0001.

### 1b. Closed-loop precedents from search findings — quoted directly from source, **not independently re-fetched/verified in this pass**, but the most on-point comparisons for a real GPU-RL parallel mechanism

| Model | Equality | solref | solimp | dt | RL use | Source |
|---|---|---|---|---|---|---|
| BRUCE (Humanoids 2025) | connect+weld+tendon, 3 parallel mechs, native MJX | 0.005 1.05 | 0.2 0.95 0.002 **0.9 6** (deliberate backlash deadband) | default (MJX, 8192 envs) | Yes — zero-shot sim2real | https://arxiv.org/html/2507.00273v2 |
| ToddlerBot (Stanford, MJX) | site-site connect (neck linkage) | 0.004 1 | 0.9999 0.9999 0.001 0.5 2 | default, `iterations=1, ls_iterations=4` | Yes — reports sim2real gap 0.082→0.133 m | https://github.com/hshi74/toddlerbot/blob/main/toddlerbot/descriptions/toddlerbot_2xc/toddlerbot_2xc_mjx.xml |
| Digit (Berkeley, arXiv 2410.03654) | connect, 4-bar knee | default | default | CPU MuJoCo | Yes | https://arxiv.org/html/2410.03654v1 |
| Cassie (Menagerie) | connect ×2/leg | 0.005 1 | default | 0.002 typical | Yes (used by Digit paper) | https://github.com/google-deepmind/mujoco_menagerie/blob/main/agility_cassie/cassie.xml |
| Robotiq 2F-85 gripper (Menagerie) | connect (4-bar) + helper tendon | 0.005 1 | 0.95 0.99 0.001 | default | non-RL, but DeepMind-curated pattern | https://github.com/google-deepmind/mujoco_menagerie/blob/main/robotiq_2f85/2f85.xml |
| MuJoCo XML reference (equality default) | n/a | 0.02 1 | 0.9 0.95 0.001 0.5 2 | — | baseline default | https://mujoco.readthedocs.io/en/stable/XMLreference.html |

**Pattern across every real loop-closure precedent found, verified or not:** `solref` timeconst clusters at **4–5 ms**; `solimp` dmax clusters at **0.95–0.99**, with only ToddlerBot pushing to 0.9999 — and it pairs that with a JAX/Brax backend (not mujoco_warp), only 1 solver iteration, and an admitted ~60% sim2real velocity-tracking gap. **No verified or found precedent runs dmax=0.9999 + width=0.0001 on the same fp32-mujoco_warp/Newton stack we use at dt=5 ms.** Our setting is an outlier on both axes relative to every real loop-closure model we found.

---

## 2. MuJoCo solref/solimp semantics, 6 lines

1. `solref = [timeconst, dampratio]` (positive form) models the constraint as a virtual spring-damper: `timeconst` (s) sets how fast the constraint force ramps toward correcting a violation, `dampratio=1` is critical damping. Negative form `[-stiffness, -damping]` bypasses this and sets spring/damper constants directly.
2. `solimp = [dmin, dmax, width, midpoint, power]` sets the constraint **impedance** `d` — the fraction of a violation the solver tries to correct — as a function of the violation magnitude `r`, interpolating from `dmax` (at r≈0) down to `dmin` (at r≥width) via a sigmoid shaped by midpoint/power.
3. `d≈1` (rigid) means the solver tries to fully close the gap this step; `d≈0` means the constraint barely pushes back — so `dmax→1` and a tiny `width` (ours: 0.0001) together mean the constraint operates at near-full correction authority almost immediately, with essentially no soft "ramp zone" before saturating. (source: https://mujoco.readthedocs.io/en/stable/computation/index.html)
4. `refsafe` (on by default) enforces `timeconst ≥ 2·dt` — a numerical-stability floor, not a suggestion — so at dt=5 ms any declared timeconst below 10 ms is silently overridden. (source: https://mujoco.readthedocs.io/en/latest/mjwarp/index.html)
5. MuJoCo's own XML reference states the same rule in prose: "timeconst should be at least two times larger than the simulation timestep to maintain stability" (source: https://mujoco.readthedocs.io/en/stable/XMLreference.html) — meaning our declared `0.002` was never going to run as-is at dt=5 ms even before refsafe is invoked as an "edge case."
6. Net effect for us: the *impedance* half of our setting (dmax=0.9999, width=1e-4) is exactly as aggressive as declared — solimp is not refsafe-clamped — while the *time-constant* half is quietly softened 5x by the clamp. That mismatch (very high, narrow-band impedance + a longer-than-intended force-ramp window) is the mechanism the reviewer is flagging.

---

## 3. Why near-1 impedance can spike, specifically with fp32 + dt=5ms + contact

- **Iteration-budget coupling (verified precedent, MuJoCo issue #1129):** a user with Digit's four-bar `connect` loops reports directly: *"the more I bring down the constraint solver's iteration and ls_iteration, the more these constraints are broken."* Near-1 impedance asks the solver to close almost the entire violation in one solve; if `iterations`/`ls_iterations` (ours: 50/20 per mjlab default, per `sim.py`) can't fully converge that in the same step as a contact event, the residual is corrected as an overshoot next step — that overshoot *is* the torque spike. (https://github.com/google-deepmind/mujoco/issues/1129)
- **fp32 amplifies this non-linearly, and not monotonically with softening (open issue, mujoco_warp #1510):** in fp32 mujoco_warp, soft equality constraints coupled through contact show sustained mm-scale oscillation (8.6 mm drift vs 0.04 mm in fp64 classic MuJoCo) and — critically — **softening doesn't reliably help**: "timeconst=0.05 rings worse than 0.02." So "just add compliance" is not a safe universal fix in our exact backend; it can trade a spike for a resonance. This issue is open as of the finding's date — any convention chosen now should be re-checked against the installed mujoco_warp build. (https://github.com/google-deepmind/mujoco_warp/issues/1510)
- **Loop geometry nonlinearity (MuJoCo 3.7.0 changelog):** four-bar/loop constraints have centripetal/Coriolis terms (`J̇v`) in their constraint bias; MuJoCo 3.7.0 added this term and measured a 74.5% reduction in constraint error on a synthetic four-bar case. If this fix isn't actually active in our pinned mujoco_warp build (claimed present in project notes but not independently confirmed against our commit hash — see Open Questions), residual geometric error is larger, and a near-1 impedance turns that residual directly into force rather than absorbing it. (https://mujoco.readthedocs.io/en/stable/changelog.html)
- **What soft settings cost — not free either:** our own project's doc91 measurement is the clearest local data point: MuJoCo's *default* solimp (0.9/0.95) on this exact ankle loop produced a **2.7 mm gap at 10 N·m and 23° ankle sag vs. 20° for the serial-equivalent baseline** — i.e., the "just soften it" direction introduces real, measurable **fake series elasticity**: the loop behaves like it has a spring nobody designed in, which distorts the reflected torque-position map the policy trains against and grows sim2real gap if the softness isn't matched to actual rod-end/rose-joint compliance (arXiv 2608.01697 makes the general point: numerical solver settings "do not directly correspond to physical parameters," so compliance chosen for solver comfort rather than measured backlash is itself a source of sim2real error). (docs/91_closed_loop_ankle_rl.md; https://arxiv.org/html/2608.01697)
- **Bottom line mechanism:** our setting has the narrowest soft-zone (`width=1e-4`) and highest ceiling (`dmax=0.9999`) of any precedent found, on the one backend (fp32 mujoco_warp, Newton, dt=5ms/contact-coupled) that's independently documented to ring/spike under exactly this kind of tight, foot-contact-coupled loop. That's the concrete, evidence-backed version of the reviewer's concern — it isn't generic caution, it maps to a specific open GitHub issue on our own stack.

---

## 4. Recommended convention range + concrete A/B plan

**Range, synthesized from the verified/precedent table (not a guess):**
- `solref` timeconst: declare **0.004–0.005 s**. At dt=5 ms this gets refsafe-floored to 0.01 s regardless, matching every real precedent's post-clamp behavior anyway — there is no downside to matching the Cassie/BRUCE/ToddlerBot cluster here. Reserve anything tighter for a dt≤2 ms *validation* lane (mirrors our existing doc91 CPU protocol), where the clamp floor is low enough not to bite.
- `solimp` dmax: **0.95–0.99**, not 0.9999. This is the value used by every real closed-loop precedent except ToddlerBot, and ToddlerBot's own reported result (62% sim2real velocity-error growth) is not an advertisement for pushing to 0.9999 on a different backend.
- `solimp` width: **0.001–0.01**, not 0.0001. This is what gives the impedance curve an actual ramp instead of instant saturation — directly answering the reviewer's "no compliance" complaint at the parameter that controls it most directly.
- `solimp` dmin: 0.9 (MuJoCo default, matches Cassie).
- dampratio: 1.0, unless we have a specific reason to intentionally underdamp/overdamp like BRUCE's 1.05 (their backlash-modeling choice, not a default).

### A/B plan — 4 arms, run with the existing sweep harness (`tools/robot_model/loop_tests/solimp_policy_sweep.py`, `PYG_LOOP_SOLIMP`/`PYG_LOOP_SOLREF` env vars), **two lanes each**:

| Arm | solref | solimp | Rationale |
|---|---|---|---|
| A (control, current) | 0.002 1 | 0.999 0.9999 0.0001 | as-shipped baseline |
| B (Cassie/Menagerie convention) | 0.005 1 | 0.9 0.95 0.001 0.5 2 | MuJoCo canonical default, matches the only verified real loop-closure precedent |
| C (Robotiq/dm_control coupling convention) | 0.005 1 | 0.95 0.99 0.001 0.5 2 | mid-tight, matches 2F-85 and dm_control quadruped coupling zone |
| D (BRUCE deadband, optional) | 0.005 1.05 | 0.2 0.95 0.002 0.9 6 | explicit backlash deadband — only worth running if we have/get a measured backlash number for our rod-ends to justify midpoint/power=0.9/6, otherwise skip |

**Lane 1 — GPU training (mujoco_warp, fp32, dt=5 ms, refsafe on):** what the policy actually trains under; solref differences across arms collapse to the same 10 ms floor, so this lane isolates the effect of solimp alone.
**Lane 2 — CPU validation (classic MuJoCo, fp64, dt=1 ms, per doc91 protocol):** same declared values, unclamped; this lane isolates solref's real effect and tells us whether Lane 1's floor is masking something we'd want at deployment/hardware-bench dt.

**Metrics (per the existing docs/94 sweep + project's established motor-util rule), compared across A–D in both lanes:**
- Crank/ankle-equivalent torque **p99, max, RMS/p95/peak** (project's standard motor-util triplet)
- Torque step `|Δτ|` p99 — the direct spike metric the reviewer asked about
- Torque power spectral fraction above 5 Hz — chatter/spike energy, not just peak
- Closure error RMS/p99/max — the drift cost of going soft
- Rod axial force p99
- **Contact-only** GRF p99 for the loop foot (per project convention, commit 0b23b72 — GRF must be contact-only, not conflated with constraint force)
- Tracking error and fall rate (make sure a spike-reducing setting doesn't cost control authority)
- Step throughput / wall-clock (BRUCE's own reported +3.4% overhead for 3 mechanisms is a reasonable ceiling to sanity-check against)
- Multi-env divergence canary: same seed run across several GPU envs, check spread — directly modeled on the #1510 report of "72 identical worlds... spread ~2x" as an fp32-instability tripwire

**Decision rule:** pick the arm with the lowest `|Δτ|` p99 / high-freq power fraction that still keeps closure error under a hardware-relevant tolerance (use measured rod-end backlash if we get it; otherwise ≤2x arm A's closure error as a placeholder ceiling) and doesn't regress tracking/fall-rate/throughput beyond the BRUCE +3.4% ballpark.

---

## 5. Open questions / honest gaps

- **We don't have a measured backlash/compliance spec for our actual rod-ends/rose joints.** Every convention above is borrowed from someone else's hardware; BRUCE explicitly measured their backlash and encoded it (`solimp[4]=6` deadband). Until we have our own number, arm D and any "physically motivated" softness claim is unverified for our hardware.
- **Whether the mujoco_warp build actually pinned in mjlab has the 3.7.0 J̇v Coriolis-bias fix active for our exact config** (Newton, `njmax=300`) is asserted in project notes as "no upgrade needed" but was not independently re-confirmed against our installed commit hash in this pass — worth a one-line version check before trusting that the loop-stabilization improvement is actually in effect.
- **mujoco_warp issue #1510 (fp32 soft-constraint + contact oscillation) is open, not fixed**, as of the finding's date. Any convention picked today is against a moving target; re-run the A/B (or at least Lane 1) after any mujoco_warp version bump before finalizing for hardware/paper claims.
- **Unconfirmed whether our site-to-site connect form predates or postdates the eq_data/joint-ref bugfix (PR #1487, 2026-07-06)** — worth confirming our mjlab pin date against that fix, since body-anchored (not site-based) forms are the ones known to be affected, but it's cheap to double check we're actually on the fixed side.
- **No verified or found precedent trains RL at dt=5 ms with dmax≥0.999 on fp32 mujoco_warp/Newton.** ToddlerBot's 0.9999 case is JAX/Brax with 1 solver iteration, not our stack. This means arm A (our current setting) isn't "wrong per precedent" so much as **untested by anyone else on our exact engine** — the A/B isn't just tuning, it's generating precedent that doesn't currently exist publicly.
- **Whether disabling refsafe and instead lowering training dt (e.g., to 2 ms) for better solref fidelity is viable without a GPU throughput hit** is untested — flagged in our own doc91 as "GPU throughput not yet measured" for this exact ankle config.

## Raw findings

- **Cassie (osudrl/cassie-mujoco-sim)** | connect (4 constraints) | solref `0.005 1` | solimp `default` | dt 0.0005 | RL Yes - OSUDRL RL training | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml
  > <equality><connect name="left-plantar-rod-eq" body1="left-plantar-rod" body2="left-foot" anchor="0.35012 0 0"/><connect name="left-achilles-rod-eq" body1="left-achilles-rod" body2="left-heel-spring" anchor="0.5012 0 0"/><connect name="right-plantar-rod-eq" body1="right-plantar-rod" body2="right-foot" anchor="0.35012 0 0"/><connect name="right-achilles-rod-eq" body1="right-achilles-rod" body2="righ
- **Cassie (variant: cassie_noise_terrain.xml)** | connect (4 constraints) | solref `0.005 1` | solimp `default` | dt 0.0005 | RL Yes - terrain randomization variant | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
  > <equality><connect name="left-plantar-rod-eq" body1="left-plantar-rod" body2="left-foot" anchor="0.35012 0 0"/><connect name="left-achilles-rod-eq" body1="left-achilles-rod" body2="left-heel-spring" anchor="0.5012 0 0"/><connect name="right-plantar-rod-eq" body1="right-plantar-rod" body2="right-foot" anchor="0.35012 0 0"/><connect name="right-achilles-rod-eq" body1="right-achilles-rod" body2="righ
- **Cassie (variant: cassiepole.xml)** | connect (4 constraints) | solref `0.005 1` | solimp `default` | dt 0.0005 | RL Yes - pole balancing variant | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
  > 4 equality connect constraints: left/right plantar-rod to foot, left/right achilles-rod to heel-spring
- **Gymnasium Humanoid** | tendon (2 fixed tendons: left_hipknee, right_hipknee) | solref `0 1 (implicit in tendon default)` | solimp `default (not specified in global defaults)` | dt 0.003 | RL Yes - Gymnasium standard humanoid task | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/humanoid.xml
  > <equality><fixed name="left_hipknee" body1="left_thigh" body2="left_shin" solimp="0 0.99 0.01" solref="0 1" anchor1="0 -0.3 0" anchor2="0 0.3 0"/><fixed name="right_hipknee" body1="right_thigh" body2="right_shin" solimp="0 0.99 0.01" solref="0 1" anchor1="0 -0.3 0" anchor2="0 0.3 0"/></equality>
- **dm_control Humanoid (CMU V2019)** | none | solref `0.015 1 (global default for geoms)` | solimp `0.99 0.99 0.003 (global default for geoms)` | dt default (0.002) | RL Yes - dm_control CMU mocap model | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/humanoid_CMU_V2019.xml
  > No <equality> section defined
- **dm_control Humanoid (CMU V2020)** | none | solref `0.015 1 (contact default)` | solimp `0.98 0.98 0.001 (contact default)` | dt default (0.002) | RL Yes - dm_control 2020 mocap update | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/humanoid_CMU_V2020.xml
  > No <equality> section defined
- **Gymnasium Hopper-v5** | none | solref `.02 1` | solimp `.8 .8 .01` | dt 0.002 | RL Yes - Gymnasium standard task | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/hopper.xml
  > No <equality> section defined
- **Gymnasium Walker2D-v5** | none | solref `default` | solimp `default` | dt 0.002 | RL Yes - Gymnasium bipedal task | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/walker2d.xml
  > No <equality> section defined
- **Gymnasium Ant-v5** | none | solref `default` | solimp `default` | dt 0.01 | RL Yes - Gymnasium quadruped task | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/ant.xml
  > No <equality> section defined
- **Gymnasium HalfCheetah-v5** | none | solref `0.02 1` | solimp `0.0 0.8 0.01` | dt 0.01 | RL Yes - Gymnasium locomotion task | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/half_cheetah.xml
  > No <equality> section defined
- **dm_control Swimmer** | none | solref `.05 1` | solimp `0 .8 .1` | dt 0.002 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/swimmer.xml
  > No <equality> section defined; joints configured with solref=.05 1 and solimp=0 .8 .1
- **dm_control Cheetah** | none | solref `default` | solimp `default` | dt 0.01 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/cheetah.xml
  > No <equality> section defined
- **dm_control Quadruped** | tendon (4 coupling constraints) | solref `.005 .5` | solimp `0.95 0.99 0.01` | dt .005 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
  > <equality><fixed name="coupling_front_left" ... /><fixed name="coupling_front_right" ... /><fixed name="coupling_back_right" ... /><fixed name="coupling_back_left" ... /></equality> with solref=.005 .5 and solimp=0.95 0.99 0.01
- **dm_control Finger** | none | solref `.02 1` | solimp `0 0.9 0.01` | dt 0.01 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/finger.xml
  > No <equality> section defined
- **dm_control Acrobot** | none | solref `default` | solimp `default` | dt 0.01 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/acrobot.xml
  > No <equality> section defined
- **dm_control Pendulum** | none | solref `default` | solimp `default` | dt 0.02 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/pendulum.xml
  > No <equality> section defined
- **dm_control Rodent** | none | solref `0.005 1 (general), 0.01 1 (lumbar joints)` | solimp `0.99 0.9999 0 (joint default)` | dt default (0.002 implied) | RL Yes - dm_control locomotion model | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/rodent.xml
  > No <equality> section defined; geom defaults specify solref=0.005 1; lumbar joints specify solref=0.01 1
- **dm_control Dog (v2)** | none | solref `0.01 1 (contact default)` | solimp `0.95 0.99 0.001 (contact default, foot geoms: 0.9 0.95 0.001)` | dt 0.005 | RL Yes - dm_control locomotion model | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/dog_v2/dog.xml
  > No <equality> section defined
- **dm_control Fruitfly (v2)** | none | solref `0.0002 1` | solimp `0.95 0.99 0.01` | dt 0.0001 (100 microseconds) | RL Yes - dm_control high-frequency model | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/fruitfly_v2/fruitfly.xml
  > No <equality> section defined
- **dm_control Reacher** | none | solref `default` | solimp `default` | dt 0.02 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/reacher.xml
  > No <equality> section defined
- **dm_control CartPole** | none | solref `.08 1 (solreflimit for slider joint)` | solimp `default` | dt 0.01 | RL Yes - dm_control suite task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/cartpole.xml
  > No <equality> section defined
- **dm_control Walker** | none | solref `default` | solimp `0 .99 .01 (solimplimit)` | dt 0.0025 | RL Yes - dm_control suite bipedal task | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/walker.xml
  > No <equality> section defined
- **MuJoCo default solref/solimp values** | constraint_default_values | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/XMLreference.html
  > Default solref [0.02, 1.0] (timeconst 20ms, dampratio 1.0); Default solimp [0.9, 0.95, 0.001] (dmin 0.9, dmax 0.95, width 0.001)
- **solimp parameter definition** | constraint_parameter_definition | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/computation/index.html
  > solimp: [dmin, dmax, width, midpoint, power] — dmin and dmax are impedance bounds; width is the contact distance range for impedance interpolation; midpoint controls the interpolation midpoint; power sets the power-law exponent for interpolation curve
- **solref parameter definition** | constraint_parameter_definition | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/computation/index.html
  > solref: [timeconst, dampratio] — timeconst is time constant in seconds; dampratio is damping ratio (1.0 = critically damped). Negative form: [-stiffness, -damping] for direct impedance control
- **MuJoCo soft vs hard constraints** | constraint_type_guidance | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/computation/index.html
  > Soft constraints (equality/contact) use solref/solimp to create spring-damper behavior; Hard constraints (limits with no solref) enforce strict bounds. Soft constraints allow penetration and energy dissipation; hard constraints are discontinuous but stiff
- **refsafe and solref clamping in MJWarp** | solver_numerical_safeguard | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/latest/mjwarp/index.html
  > refsafe clamps solref timeconst >= 2*dt; in fp32 MJWarp at dt=5ms, solref=0.002 becomes 0.01 (10ms) — much softer than intended. This is a numerical stability measure in float32 precision
- **Impedance near 1.0 and numerical issues** | numerical_stability_warning | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/computation/index.html
  > When impedance d approaches 1.0, the constraint becomes very stiff and can cause numerical ill-conditioning in the solver. Recommended practice: keep impedance well below 1.0 for smooth solver convergence
- **MuJoCo 3.7.0 connect/weld Jdot·v term** | solver_improvement_3x | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/changelog.html
  > Version 3.7.0 (April 14, 2026): Added centripetal/Coriolis acceleration term J̇v to constraint solver bias for connect and weld equality constraints. Measured ~75% reduction in constraint violation for four-bar linkages (jdotv_connect_3d.xml: 1.399e-3 → 5.493e-3 error reduction)
- **connect constraint site-based vs body-anchored** | constraint_anchor_semantics | solref `None` | solimp `None` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/XMLreference.html
  > MuJoCo 3.x supports site1/site2 form for connect constraints (site-to-site), which compute anchor position at runtime and avoid the eq_data initialization bug of body-anchored forms. Site-based connects are immune to joint ref position issues and are recommended for updated models
- **Cassie precedent for loop closure** | soft_constraint_example | solref `None` | solimp `None` | dt None | RL None | https://github.com/google-deepmind/mujoco_menagerie/blob/main/agility_cassie/cassie.xml
  > <equality solref="0.005 1"/> ... <connect body1="left-plantar-rod" body2="left-foot" anchor="0.35012 0 0"/> — Cassie models ankle rod loops with soft solref of 5ms and default solimp, minimal recipe for loop closure in RL training
- **ToddlerBot tight constraint example** | soft_constraint_example | solref `None` | solimp `None` | dt None | RL None | https://github.com/stanfordvl/toddlerbot/blob/main/toddlerbot.xml
  > <connect site1="closing_neck_pitch_front_1" site2="closing_neck_pitch_front_2" solref="0.004 1" solimp="0.9999 0.9999 0.001 0.5 2"/> — Tight coupling (site-to-site) for parallel linkage in MJX with 5-parameter solimp including midpoint=0.5 and power=2
- **MJWarp fp32 numerical issues with soft constraints** | solver_numerical_issue | solref `None` | solimp `None` | dt None | RL None | https://github.com/google-deepmind/mujoco_warp/issues/1510
  > In MuJoCo-Warp (fp32): networks of soft equality constraints coupled through contacts exhibit sustained mm-scale oscillation (8.6mm drift vs 0.04mm in fp64 classic MuJoCo), non-monotonic response to solref softening (timeconst=0.05 rings worse than 0.02), and world-to-world divergence of identical environments
- **Pygmalion 2-RSU ankle loop** | connect (4 per leg) | solref `0.002 (timeconst ms)` | solimp `0.999 0.9999 0.0001` | dt 0.005 (5 ms training), 0.001 (1 ms validation/plain MuJoCo) | RL yes | /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v3_printed_loop.xml
  > <equality>
    <connect name="L_loop_A" site1="L_rod_A_end" site2="L_ball_A" solref="0.002" solimp="0.999 0.9999 0.0001"/>
    <connect name="L_loop_B" site1="L_rod_B_end" site2="L_ball_B" solref="0.002" solimp="0.999 0.9999 0.0001"/>
    <connect name="R_loop_A" site1="R_rod_A_end" site2="R_ball_A" solref="0.002" solimp="0.999 0.9999 0.0001"/>
    <connect name="R_loop_B" site1="R_rod_B_end" site
- **Cassie (canonical precedent)** | connect (2 rods per leg: plantar, achilles) | solref `0.005 (5 ms default soft connect)` | solimp `default` | dt 0.002 (2 ms, typical for Cassie) | RL yes | https://github.com/google-deepmind/mujoco_menagerie/blob/main/agility_cassie/cassie.xml
  > <equality solref="0.005 1"/> ... <connect body1="left-plantar-rod" body2="left-foot" anchor="0.35012 0 0"/> <connect body1="left-achilles-rod" body2="left-heel-spring" anchor="0.5012 0 0"/>
- **BRUCE (arXiv 2507.00273, Humanoids 2025)** | 3 parallel mechanisms: tendon eq, 5-bar connect, 4-bar connect | solref `0.005 1.05` | solimp `0.2 0.95 0.002 0.9 6` | dt default | RL None | https://arxiv.org/html/2507.00273v2
  > Unlike prior approaches that rely on simplified serial approximations, we simulate all closed-chain constraints natively using GPU-accelerated MuJoCo (MJX). ... the inclusion of all three parallel mechanism constraints introduced only a 3.4% increase in per-step simulation time
- **Digit (arXiv 2410.03654, Berkeley 2024)** | 4-bar knee loop constraints | solref `default` | solimp `default` | dt CPU MuJoCo (~100M samples/day throughput) | RL yes | https://arxiv.org/html/2410.03654v1
  > Digit uses four-bar linkages that introduce loops in the kinematic tree. We use the MuJoCo simulator which is able to simulate this using equality constraints. While MuJoCo is considerably slower than GPU-based simulators, like IsaacGym, we can afford to use a slower simulator thanks to the sample efficiency of our method.
- **ToddlerBot (arXiv 2502.00893, Stanford, MJX)** | connect + joint-equality (gears) + tendon (couplings) | solref `0.004 (tight timeconst)` | solimp `0.9999 0.9999 0.001 0.5 2` | dt default (batched MJX) | RL None | https://github.com/hshi74/toddlerbot/blob/main/toddlerbot/descriptions/toddlerbot_2xc/toddlerbot_2xc_mjx.xml
  > <connect site1="closing_neck_pitch_front_1" site2="closing_neck_pitch_front_2" solref="0.004 1" solimp="0.9999 0.9999 0.001 0.5 2"/> ... <joint joint1="left_hip_yaw_driven" joint2="left_hip_yaw_drive" polycoef="0 -0.8571428571 0 0 0"/> ... <option iterations="1" ls_iterations="4">
- **mujoco_warp fp32 + refsafe clamp** | all (CONNECT, WELD, JOINT, TENDON supported) | solref `clamped to >= 2*dt (10 ms minimum at 5 ms training timestep)` | solimp `all 5 components supported` | dt 0.005 (5 ms training default) | RL None | https://mujoco.readthedocs.io/en/latest/mjwarp/index.html
  > MJWarp utilizes floats in contrast to MuJoCo's default double representation for mjtNum. Solver settings, including iterations, collision detection, and small friction values may be sensitive to differences in floating point representation. ... if not (opt_disableflags & DisableBit.REFSAFE): timeconst = wp.max(timeconst, 2.0 * timestep)
- **mujoco_warp issue #1510 (soft equality + contact oscillation)** | weld + contact coupling (mm-scale oscillation) | solref `non-monotonic behavior with softening` | solimp `default` | dt None | RL None | https://github.com/google-deepmind/mujoco_warp/issues/1510
  > classic mujoco (fp64/euler): max item drift 0.040 mm / mujoco_warp (fp32/euler): max item drift 8.600 mm ... Batched worlds aren't just noisy, they diverge: 72 identical worlds of a knife-edge scene spread ~2x in my failure metric. ... softening the welds behaves non-monotonically — timeconst=0.05 rings worse than 0.02
- **mujoco_warp issue #1129 (solver iterations impact)** | connect (Digit four-bar) | solref `default` | solimp `default` | dt None | RL None | https://github.com/google-deepmind/mujoco/issues/1129
  > I am having the same issue with the agile robotics digit which has closed loop chains in its legs which are implemented using equality connect constraints. The more I bring down the constraint solver's iteration and ls_iteration, the more these constraints are broken.
- **mjlab Pygmalion config** | all (training with loops) | solref `training default (refsafe clamped)` | solimp `per-constraint in XML` | dt 0.005 (5 ms default training) | RL None | /home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab/src/mjlab/sim/sim.py
  > ls_iterations: int = 50 (default) ... njmax: int | None = None ... Constraint arrays are batched by world: no world may have more than njmax
- **MuJoCo 3.7.0+ Jdot·v bias (centripetal/Coriolis)** | connect, weld (four-bar stabilization) | solref `any` | solimp `any` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/changelog.html
  > Added the centripetal/Coriolis acceleration term J̇v to the constraint solver bias for connect and weld equality constraints. This significantly improves the stability of constrained mechanisms like four-bar linkages. ... jdotv_connect_3d.xml | 1.399e-3 | 5.493e-3 | 74.5% [reduction]
- **MuJoCo documentation (equality section)** | general guidance | solref `default` | solimp `default` | dt None | RL None | https://mujoco.readthedocs.io/en/stable/computation/index.html
  > Kinematic loops are not allowed; if loop joints are needed they should be modeled with equality constraints. [...] equality constraints can be used to create "loop joints" [...] The same can be done in MuJoCo but is not recommended – because it leads to both slower and less accurate simulation
- **pyg_fea solimp sweep findings** | connect (rod-end closure) | solref `overrideable at runtime` | solimp `overrideable at runtime (4 params: damping, stiffness, impedance, ...)` | dt None | RL None | /home/syaro/MikuchanRemote/Human-Pygmalion/tools/robot_model/loop_tests/solimp_policy_sweep.py
  > Metrics per setting (docs/94): crank torque p99 / max, torque step |d tau| p99 (spikiness), crank torque power fraction above 5 Hz, closure error RMS / p99 / max, rod axial force p99, contact-only GRF p99, tracking error, falls, and the ankle-equivalent torque RMS.
- **arXiv 2608.01697 (dynamics normalization, Aug 2026)** | serial ankle compensation (avoiding constraint softness) | solref `None` | solimp `None` | dt None | RL None | https://arxiv.org/html/2608.01697
  > in such a constraint formulation, loop-closure accuracy and dynamic response depend on the constraint and solver settings. Because these numerical settings do not directly correspond to the robot's physical parameters, appropriate values are difficult to determine solely from hardware characteristics
- **Agility Cassie (MuJoCo Menagerie)** | connect | solref `0.005 1` | solimp `default` | dt None | RL Yes — Berkeley Digit (arXiv 2410.03654) | https://github.com/google-deepmind/mujoco_menagerie/blob/main/agility_cassie/cassie.xml
  > <equality solref="0.005 1"/> ... <connect body1="left-plantar-rod" body2="left-foot" anchor="0.35012 0 0"/> <connect body1="left-achilles-rod" body2="left-heel-spring" anchor="0.5012 0 0"/>
- **ToddlerBot (Stanford, MJX GPU)** | connect | solref `0.004 1` | solimp `0.9999 0.9999 0.001 0.5 2` | dt default | RL Yes — MJX/Brax training at 1024 envs, sim-to-real gap 0.082 m (sim) vs 0.133 m (real) | https://github.com/hshi74/toddlerbot/blob/main/toddlerbot/descriptions/toddlerbot_2xc/toddlerbot_2xc_mjx.xml
  > <connect site1="closing_neck_pitch_front_1" site2="closing_neck_pitch_front_2" solref="0.004 1" solimp="0.9999 0.9999 0.001 0.5 2"/>
- **Robotiq 2F-85 Gripper (MuJoCo Menagerie)** | connect | solref `0.005 1` | solimp `0.95 0.99 0.001` | dt None | RL None | https://github.com/google-deepmind/mujoco_menagerie/blob/main/robotiq_2f85/2f85.xml
  > <connect anchor="0 0 0" body1="right_follower" body2="right_coupler" solimp="0.95 0.99 0.001" solref="0.005 1"/>. Design note: "This adds stability to the model by having a tendon that distributes the forces between both joints, such that the equality constraint doesn't have to do that much work in order to equalize both joints."
- **BRUCE (Humanoids 2025, MJX GPU)** | connect, weld, tendon | solref `0.005 1.05` | solimp `0.2 0.95 0.002 0.9 6` | dt None | RL Yes — MJX training with native closed-chain constraints, motor-space actions | https://arxiv.org/abs/2507.00273
  > solve constraints with a deliberate deadband to model backlash (og_bruce: solref='0.005 1.05', solimp='0.2 0.95 0.002 0.9 6'). Only +3.4% per-step overhead for all three parallel mechanisms (hip differential, five-bar, four-bar) at 8192 envs. Zero-shot sim-to-real transfer.
- **Pygmalion 2-RSU ankle (this project, MuJoCo-Warp)** | connect | solref `0.002` | solimp `0.999 0.9999 1e-4 (adopted), 0.9 0.95 (default—inadequate)` | dt 0.001 (1 ms for stability) | RL Pending — configuration validated, GPU throughput not yet measured | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/91_closed_loop_ankle_rl.md
  > Default `connect` is too soft (2.7 mm gap at 10 N·m, ankle sag 23° vs serial 20°) → solimp 0.999 0.9999 1e-4 achieves 0.04 mm gap and 19.9° deflection matching serial baseline.
- **MuJoCo-Warp (fp32 backend, Issue #1510)** | weld (and connect through contacts) | solref `None` | solimp `None` | dt None | RL Not recommended without validation — known numerical instability in constraint-contact coupling. | https://github.com/google-deepmind/mujoco_warp/issues/1510
  > classic mujoco (fp64/euler): max item drift 0.040 mm / mujoco_warp (fp32/euler): max item drift 8.600 mm. Softening the welds behaves non-monotonically — timeconst=0.05 rings worse than 0.02. Batched worlds aren't just noisy, they diverge: 72 identical worlds of a knife-edge scene spread ~2× in failure metric.
- **MuJoCo (generic, Yuval Tassa guidance)** | connect, tendons | solref `None` | solimp `None` | dt None | RL Pattern: use tendons for passive rods in contact-loaded loops | https://github.com/google-deepmind/mujoco/discussions/2268
  > Yuval Tassa (MuJoCo lead): "stabilizing linkages is hard ... your inertias are all wrong (visualize them in simulate and you'll see what I mean) ... [spatial tendons are] both cheaper and much more stable than connects"
- **mjlab (Kevin Zakka guidance)** | connect, joint, tendon, serial approximation | solref `None` | solimp `None` | dt None | RL All four approaches confirmed viable for mjlab locomotion training | https://github.com/mujocolab/mjlab/issues/918
  > Kevin Zakka (mjlab maintainer): "We do not plan to support ball joints as a general primitive... several modeling approaches (spatial tendons, equality connect, precomputed torque tables, serial-chain approximation) ... how to train a policy on a robot with linkages"
- **MuJoCo 3.7.0+ (centripetal/Coriolis bias)** | connect, weld | solref `None` | solimp `None` | dt None | RL Yes — automatic benefit for all connect/weld constraints in current mjlab | https://mujoco.readthedocs.io/en/stable/changelog.html
  > Added the centripetal/Coriolis acceleration term J̇v to the constraint solver bias for connect and weld equality constraints. This significantly improves the stability of constrained mechanisms like four-bar linkages. Measured ~75% reduction in drift (jdotv_connect_3d.xml: 5.493e-3 → 1.399e-3, 74.5% improvement)
- **Body anchor vs. site-to-site (MuJoCo issue #1270, PR #1487)** | connect, weld | solref `None` | solimp `None` | dt None | RL Yes — site-to-site form is preferred for loop randomization in domain randomization | https://github.com/google-deepmind/mujoco_warp/pull/1487
  > Site-to-site form: sites snap together at start, correctly track runtime site_pos changes. Body-anchored form: depends on eq_data computed at qpos0; if joint ref values change, eq_data is not updated (bug fixed in PR #1487, 2026-07-06).
- **MuJoCo-Warp refsafe clamp constraint** | all (applies to solref) | solref `None` | solimp `None` | dt 5 ms (mjlab default) → clamped solref timeconst to 10 ms minimum | RL mjlab training with refsafe requires solimp tuning or dt reduction | https://mujoco.readthedocs.io/en/latest/mjwarp/index.html
  > MJWarp applies constraint solver setting refsafe clamp: if not (opt_disableflags & DisableBit.REFSAFE): timeconst = wp.max(timeconst, 2.0 * timestep). At mjlab's training timestep of 5 ms the loop's solref=0.002 would be clamped to a 10 ms time constant (unless refsafe is disabled), i.e. a much softer loop than the 1 ms/2 ms standalone test.
- **DeepMind dm_control Humanoid** | Contact (geom) | solref `0.015 1` | solimp `0.9 0.99 0.003` | dt default | RL yes | https://raw.githubusercontent.com/deepmind/dm_control/master/dm_control/suite/humanoid.xml
  > solimp=".9 .99 .003" solref=".015 1" (applied to all geom elements in default body class)
- **DeepMind dm_control Quadruped** | Tendon coupling constraint + Contact (geom) | solref `0.01 1 (geom default); 0.005 0.5 (tendon coupling)` | solimp `0.9 0.99 0.003 (geom default); 0.95 0.99 0.01 (tendon coupling)` | dt default | RL yes | https://raw.githubusercontent.com/deepmind/dm_control/master/dm_control/suite/quadruped.xml
  > solimp='.9 .99 .003' solref='.01 1' (default); coupling: solimp='0.95 0.99 0.01' solref='.005 .5'; ball: solref='-10000 -30' (soft contact override)
- **MuJoCo GitHub Discussion #2323 - Weld Equality for Docking** | Weld equality constraint | solref `0.0001, 1e6` | solimp `0.9, 0.99, 1e-6, 0.9, 6` | dt default | RL default | https://github.com/google-deepmind/mujoco/discussions/2323
  > solimp=[0.9, 0.99, 1e-6, 0.9, 6] and solref=[0.0001, 1e6] (tuned parameters for stable weld constraint in docking simulation)
- **OpenAI mujoco-py claw.xml** | Weld equality constraint (mocap to claw) | solref `0.06 1` | solimp `0.02 0.1 0.05` | dt default | RL yes | https://github.com/openai/mujoco-py/blob/master/xmls/claw.xml
  > <weld body1="mocap" body2="claw" solimp="0.02 0.1 0.05" solref="0.06 1"></weld>
- **machines-in-motion mujoco_utils** | Contact (geom - endeffector) | solref `0.015 1` | solimp `0.99 0.99 0.001` | dt default | RL yes | https://github.com/machines-in-motion/mujoco_utils
  > solref="0.015 1" solimp="0.99 0.99 0.001" (contact parameters for Solo12 robot endeffector interaction)
- **MuJoCo MJX Issue #2548 - MJX vs MuJoCo Differences** | Contact constraint (box-box collision) | solref `0.04 0.2` | solimp `0.95 0.99 0.0001 0.5 2` | dt 0.004 | RL default | https://github.com/google-deepmind/mujoco/issues/2548
  > solimp=".95 .99 .0001 .5 2" solref=".04 .2" timestep="0.004" iterations="4" ls_iterations="6" — difference is bigger for box-box collision; tracking errors between MJX and MuJoCo reported
- **MuJoCo MJX Issue #2173 - Equality Constraint eq_active Bug** | Weld equality constraint | solref `0.005 1 (active state); attempted workarounds with large solref values` | solimp `0.95 0.99 0.001 (active state); attempted workarounds solimp[0]=solimp[1]=0` | dt default | RL default | https://github.com/google-deepmind/mujoco/issues/2173
  > solimp="0.95 0.99 0.001" solref="0.005 1"; user noted 'equality constraints (or at least the weld equality) ignores the eq_active field'; workarounds attempted: 'setting solimp[0] = solimp[1] = 0, and solref[0] to be really large'
- **MuJoCo Official Documentation - XML Reference** | Equality constraint defaults | solref `0.02 1` | solimp `0.9 0.95 0.001 0.5 2` | dt default | RL no | https://mujoco.readthedocs.io/en/stable/XMLreference.html
  > solref default: 0.02 1 (timeconst, dampratio); solimp default: 0.9 0.95 0.001 0.5 2 (d0, dwidth, width, midpoint, power) — timeconst should be at least two times larger than simulation timestep to maintain stability
- **ROBOLAWEB solref/solimp Cheat Sheet** | Contact material properties | solref `0.002 (rigid metal) to 0.04 (foam) time constant with damping 0.1-4` | solimp `varies by material; rigid: 0.9 0.95 0.001 0.5 2; soft: 0.95 0.99 0.001 0.5 2` | dt default | RL default | https://robolaweb.gitbook.io/robolaweb-docs/basic-concept/solref-solimp-parameter-cheat-sheet
  > Rigid Metal/Concrete: solref=0.002 1, solimp=0.9 0.95 0.001 0.5 2; Foam/Sponge: solref=0.04 4, solimp=0.8 0.99 0.001 0.5 2; note 'solimp is sufficient' for rigid objects, lower time constant → stiffer contact
- **Isaac Sim/PhysX Robotiq 2F-85 Gripper (Isaac Sim Documentation)** | Joint drive (PhysX compliance) | solref `natural_frequency ~9000 rad/s (computed from stiffness/damping)` | solimp `default` | dt default | RL default | https://docs.omniverse.nvidia.com/kit/docs/omni_physics/107.3/dev_guide/guides/gripper_tuning_example.html
  > Stiffness: ~275 kg·m²/s² (PhysX units); Damping: ~0.06 kg·m²/s; computed natural frequency: 9.0e3 rad/s; note PhysX and USD use different units: 1 USD unit = (180/π) PhysX units for stiffness/damping
- **Isaac Lab Closed-Loop Articulation (GitHub Discussion #5157)** | Excluded joint constraints + compliance | solref `default (stiffness/damping from USD joint prim)` | solimp `default` | dt smaller timesteps reduce constraint error | RL yes | https://github.com/isaac-sim/IsaacLab/discussions/5157
  > Finger drive joints: Stiffness=0.0, Damping=5000.0; Stability joints: Stiffness=0.05; Test structure: Stiffness=10000.0, Damping=10000.0; critical issue: 'If the excluded joint or its neighbors rely on a specific drive configuration and you overwrite that to (0, 0) or some default from Lab, the kinematic loop may become either too loose or too stiff and produce non-physical motion'; solution: use 
- **MuJoCo GitHub Issue #584 - Unreliable Simulation Report** | Contact + Joint constraints (all types tested) | solref `extensively tuned across scenes without success` | solimp `extensively tuned across scenes without success` | dt default | RL no | https://github.com/google-deepmind/mujoco/issues/584
  > User reports: 'weird penetrations and reaction forces'; 'The simulation breaks too often (I get resets and bad values). I have attempted too many options (solvers, integration schemes, friction coefficients, joint friction, joint damping, joint stiffness, density, solref, solimp, disabling self-collisions [by hand], etc..) and I cannot find values that work reliably in most cases' — reveals tuning

## Raw XML extractions

- cassie | `<option timestep='0.0005' iterations='50' solver='PGS' gravity='0 0 -9.81'/>` | solref N/A | solimp N/A | dt 0.0005 | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml
- cassie | `<equality solref='0.005 1'/> (default class, line 18)` | solref 0.005 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt N/A | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml
- cassie | `<connect name = 'left-plantar-rod-eq' body1='left-plantar-rod'  body2='left-foot'        anchor='0.35012 0 0'/>` | solref 0.005 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt N/A | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml
- cassie | `<connect name = 'left-achilles-rod-eq' body1='left-achilles-rod' body2='left-heel-spring' anchor='0.5012 0 0'/>` | solref 0.005 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt N/A | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml
- cassie | `<connect name = 'right-plantar-rod-eq' body1='right-plantar-rod'  body2='right-foot'        anchor='0.35012 0 0'/>` | solref 0.005 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt N/A | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml
- cassie | `<connect name = 'right-achilles-rod-eq' body1='right-achilles-rod' body2='right-heel-spring' anchor='0.5012 0 0'/>` | solref 0.005 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt N/A | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie.xml
- cassie | `<option timestep='0.0005' iterations='50' solver='PGS' gravity='0 0 -9.81'/>` | solref None | solimp None | dt 0.0005 | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<!-- Timestep is set to 0.0005 because our controller runs at 2 kHz -->` | solref None | solimp None | dt 0.0005 | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<geom contype='0' conaffinity='0' condim='1' solref='0.005 1'/>` | solref 0.005 1 | solimp None | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<equality solref='0.005 1'/>` | solref 0.005 1 | solimp None | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<equality>` | solref None | solimp None | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<connect body1='left-plantar-rod'  body2='left-foot'        anchor='0.35012 0 0'/>` | solref 0.005 1 | solimp 0.9 0.95 0.001 0.5 2 | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<connect body1='left-achilles-rod' body2='left-heel-spring' anchor='0.5012 0 0'/>` | solref 0.005 1 | solimp 0.9 0.95 0.001 0.5 2 | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<connect body1='right-plantar-rod'  body2='right-foot'        anchor='0.35012 0 0'/>` | solref 0.005 1 | solimp 0.9 0.95 0.001 0.5 2 | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `<connect body1='right-achilles-rod' body2='right-heel-spring' anchor='0.5012 0 0'/>` | solref 0.005 1 | solimp 0.9 0.95 0.001 0.5 2 | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassie | `</equality>` | solref None | solimp None | dt None | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassie_noise_terrain.xml
- cassiepole.xml | `<option timestep='0.0005' iterations='50' solver='PGS' gravity='0 0 -9.81'/>` | solref  | solimp  | dt 0.0005 | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- cassiepole.xml | `<geom contype='0' conaffinity='0' condim='1' solref='0.005 1'/>` | solref 0.005 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt  | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- cassiepole.xml | `<equality solref='0.005 1'/>` | solref 0.005 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt  | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- cassiepole.xml | `<connect body1='left-plantar-rod'  body2='left-foot'        anchor='0.35012 0 0'/>` | solref  | solimp  | dt  | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- cassiepole.xml | `<connect body1='left-achilles-rod' body2='left-heel-spring' anchor='0.5012 0 0'/>` | solref  | solimp  | dt  | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- cassiepole.xml | `<connect body1='right-plantar-rod'  body2='right-foot'        anchor='0.35012 0 0'/>` | solref  | solimp  | dt  | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- cassiepole.xml | `<connect body1='right-achilles-rod' body2='right-heel-spring' anchor='0.5012 0 0'/>` | solref  | solimp  | dt  | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- cassiepole.xml | `<equality>` | solref MuJoCo default 0.02 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt  | verified=True | https://raw.githubusercontent.com/osudrl/cassie-mujoco-sim/master/model/cassiepole.xml
- humanoid | `<option integrator="RK4" iterations="50" solver="PGS" timestep="0.003">` | solref MuJoCo default 0.02 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt 0.003 | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/humanoid.xml
- humanoid_CMU_V2019 | `8` | solref N/A (solimplimit for joint limits, not contact) | solimp 0 0.99 0.01 (solimplimit for joint limits, not general contact) | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/humanoid_CMU_V2019.xml
- humanoid_CMU_V2019 | `9` | solref 0.015 1 | solimp 0.99 0.99 0.003 | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/humanoid_CMU_V2019.xml
- humanoid_CMU_V2020 | `10` | solref None | solimp solimplimit (not solimp) | dt None | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/humanoid_CMU_V2020.xml
- humanoid_CMU_V2020 | `11` | solref 0.015 1 | solimp 0.99 0.99 0.003 | dt None | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/humanoid_CMU_V2020.xml
- humanoid_CMU_V2020 | `28` | solref 0.015 1 | solimp 0.98 0.98 0.001 | dt None | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/locomotion/walkers/assets/humanoid_CMU_V2020.xml
- hopper | `    <geom conaffinity="1" condim="1" contype="1" margin="0.001" material="geom" rgba="0.8 0.6 .4 1" solimp=".8 .8 .01" solref=".02 1"/>` | solref .02 1 | solimp .8 .8 .01 | dt None | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/hopper.xml
- hopper | `  <option integrator="RK4" timestep="0.002"/>` | solref None | solimp None | dt 0.002 | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/hopper.xml
- walker2d | `<option integrator="RK4" timestep="0.002"/>` | solref MuJoCo default 0.02 1 | solimp MuJoCo default 0.9 0.95 0.001 0.5 2 | dt 0.002 | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/walker2d.xml
- ant | `<option integrator="RK4" timestep="0.01"/>` | solref None | solimp None | dt 0.01 | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/ant.xml
- half_cheetah | `<joint armature=".1" damping=".01" limited="true" solimplimit="0 .8 .03" solreflimit=".02 1" stiffness="8"/>` | solref 0.02 1 (solreflimit, for limit contacts) | solimp 0 0.8 0.03 (solimplimit, for limit contacts) | dt None | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/half_cheetah.xml#L4
- half_cheetah | `<geom conaffinity="0" condim="3" contype="1" friction=".4 .1 .1" rgba="0.8 0.6 .4 1" solimp="0.0 0.8 0.01" solref="0.02 1"/>` | solref 0.02 1 | solimp 0.0 0.8 0.01 | dt None | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/half_cheetah.xml#L5
- half_cheetah | `<option gravity="0 0 -9.81" timestep="0.01"/>` | solref None | solimp None | dt 0.01 | verified=True | https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/envs/mujoco/assets/half_cheetah.xml#L9
- swimmer | `  <option timestep="0.002" density="3000">` | solref None | solimp None | dt 0.002 | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/swimmer.xml
- swimmer | `      <joint type="hinge" pos="0 -.05 0" axis="0 0 1" limited="true" solreflimit=".05 1" solimplimit="0 .8 .1" armature="1e-6"/>` | solref .05 1 | solimp 0 .8 .1 | dt None | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/swimmer.xml
- cheetah | `<option timestep="0.01"/>` | solref N/A | solimp N/A | dt 0.01 | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/cheetah.xml
- quadruped.xml | `16` | solref N/A | solimp N/A | dt <option timestep=".005"/> | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `19` | solref <geom solimp=".9 .99 .003" solref=".01 1"/> | solimp N/A | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `23` | solref N/A | solimp limited="true" solimplimit="0 .99 .01"/> | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `54` | solref <equality solimp="0.95 0.99 0.01" solref=".005 .5"/> | solimp Effective solref=.005 .5, solimp=0.95 0.99 0.01 (explicitly set in default class="coupling") | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `202` | solref solref="-10000 -30"/> | solimp Inherits from default geom: solimp=.9 .99 .003 (line 19) | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `271` | solref <equality> | solimp Equality block containing tendon constraints (lines 272-275) | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `272` | solref <tendon name="coupling_front_left" tendon1="coupling_front_left" class="coupling"/> | solimp Effective solref=.005 .5, solimp=0.95 0.99 0.01 (inherited from default class="coupling") | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `273` | solref <tendon name="coupling_front_right" tendon1="coupling_front_right" class="coupling"/> | solimp Effective solref=.005 .5, solimp=0.95 0.99 0.01 (inherited from default class="coupling") | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `274` | solref <tendon name="coupling_back_right" tendon1="coupling_back_right" class="coupling"/> | solimp Effective solref=.005 .5, solimp=0.95 0.99 0.01 (inherited from default class="coupling") | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- quadruped.xml | `275` | solref <tendon name="coupling_back_left" tendon1="coupling_back_left" class="coupling"/> | solimp Effective solref=.005 .5, solimp=0.95 0.99 0.01 (inherited from default class="coupling") | dt N/A | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/quadruped.xml
- finger | `<option timestep="0.01" cone="elliptic" iterations="200">` | solref None | solimp None | dt 0.01 | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/finger.xml
- finger | `<geom solimp="0 0.9 0.01" solref=".02 1"/>` | solref .02 1 | solimp 0 0.9 0.01 | dt None | verified=True | https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/suite/finger.xml