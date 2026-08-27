# Raw research — authoring a closed kinematic loop (2-RSU ankle) in USD/PhysX for IsaacSim 5.x (2026-08-27, Sonnet subagent)

Context: our AB (closed-loop) ankle exists in MuJoCo as a tree + 4 `<equality><connect>` constraints per leg (2
actuated crank revolutes, 2 free-body rods, each rod tied to a crank tip and to the ankle plate via a ball-joint-like
U-joint pair, modeled as MuJoCo point/`connect` constraints — see
`pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v4_printed_loop.xml` and the mjlab copy at
`mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v4_printed_loop.xml`, lines 315-320). URDF
cannot express loops, so our USD so far only covers the serial (RP) variant. This note is WebSearch/WebFetch +
GitHub-source research only — no code was touched. All source excerpts below are copied verbatim from the fetched
page/file; no paraphrase-as-quote.

## 0. Verdict — prioritised recommendation

| # | Path | Verdict | Why | Source |
|---|---|---|---|---|
| 1 | **Hand-author the loop with `UsdPhysicsSphericalJoint` prims marked `physics:excludeFromArticulation=true`, mirroring Isaac Sim's own official closed-loop tutorial and the exact code path its MJCF importer uses internally** | **Recommended primary path.** This is the officially documented, maintainer-endorsed pattern (not a hack): keep the articulation a tree (cranks stay as actuated `UsdPhysicsRevoluteJoint`s inside the tree; rods hang off one crank as a serial branch), then close each of the ankle's independent loops with one extra `UsdPhysicsSphericalJoint`/`UsdPhysicsFixedJoint`/`UsdPhysicsRevoluteJoint` between the two links that would otherwise create a cycle, with `physics:excludeFromArticulation` set true on that joint. It becomes a maximal-coordinate (non-vectorized) PhysX joint solved by the general rigid-body/TGS solver, not the reduced-coordinate articulation solver. Our mechanism needs exactly 4 such joints per ankle (one per rod-end U-joint, matching our 4 MuJoCo `connect` constraints 1:1 — each is a distinct body pair, so each maps to a single `UsdPhysicsSphericalJoint`, not a revolute/fixed). This is a small, fixed, well-understood diff (~8 extra joint prims total for both ankles) done directly with `pxr.UsdPhysics`/`PhysxSchema` Python API — no importer dependency, no C++ rebuild. | Isaac Sim "Rig Closed-Loop Structures" tutorial (4.5.0 and 6.0.0, identical procedure); IsaacLab discussions #5157, #1453, #1501, #1341; PhysX 5.5 `Articulations.html`; `isaac-sim/mjcf-importer-extension` source `MjcfImporter.cpp` (see §3 — this is literally what the importer itself does when it *can* parse the constraint) |
| 2 | **MJCF importer (`isaacsim.asset.importer.mjcf`) auto-converting our existing loop XML** | **Do not rely on it as-is — it will silently fail or crash on our exact file.** The importer's `LoadEqualityConnect()` (in `MjcfParser.cpp`) unconditionally reads `c->Attribute("body1")`, `c->Attribute("body2")`, `c->Attribute("anchor")` with no null check. Our `<connect>` tags use the modern `site1`/`site2` MuJoCo syntax (`site1="L_rod_A_end" site2="L_ball_A"`, no `body1`/`body2`/`anchor` attributes at all — confirmed by grep, zero `site1`/`site2` handling anywhere in the importer's parser/types/importer files). `Attribute()` returns `nullptr` when the attribute is absent, and `std::string(nullptr)` is undefined behavior (segfault in practice on glibc/libstdc++). **This is a concrete, code-verified blocker**, not a theoretical fidelity gap. It is fixable two ways: (a) pre-process our MJCF to also emit the legacy `body1="<parent of site1>" body2="<parent of site2>" anchor="<site1 local pos>"` form for Isaac-bound exports (cheap script, MuJoCo itself resolves site→body+anchor at compile time so the mapping is mechanical), or (b) patch the ~10-line `LoadEqualityConnect` function and rebuild the extension. *If* fixed, fidelity for our exact case is actually excellent: because each of our 4 `connect` tags ties a **distinct** body pair (rod_A↔plate, rod_B↔plate, crank tips are already articulation joints not equality constraints — confirm this against your XML), the importer's `analyzeConstraints()` groups constraints by body-pair and, for a count of 1 per pair, emits a `UsdPhysicsSphericalJoint` with `excludeFromArticulation=true` under a dedicated `/loop_joints/` prim — i.e., it reproduces path #1 exactly, automatically. Given the crash risk plus a from-scratch C++ rebuild, hand-authoring (path #1) is still faster and lower-risk for a fixed, small (8-joint) mechanism, but path 2(a) — the site→body/anchor pre-conversion script — is a legitimate fallback if you want the importer to also carry over the rest of the tree/actuator/sensor definitions automatically. | `isaac-sim/mjcf-importer-extension` GitHub source, `MjcfParser.cpp` L756-765 (`LoadEqualityConnect`) and `MjcfImporter.cpp` L46-125 (`analyzeConstraints`) + L296-360 (joint creation + `CreateExcludeFromArticulationAttr().Set(true)`), fetched 2026-08-27; our own `pygmalion_v4_printed_loop.xml` L315-320 |
| 3 | **Serial-equivalent (RP) + software crank-space torque/position envelope, skip the true loop in Isaac entirely** | **Acceptable as a secondary/cheap validation lane, but not a substitute for #1 for "cross-engine validation" specifically** — that's exactly the comparison our task needs the true loop for. Real precedent exists for both extremes: (a) Isaac Gym's Digit/Cassie research port replaced the closed tarsus/toe chain with a *virtual high-stiffness spring* on the rod length + sub-stepped correction (not even a serial simplification — a different maximal-joint hack) because "given the closed kinematic chains and underactuated nature of the knee-shin-tarsus and tarsus-toe joints... Isaac Gym was unable to effectively model these dynamics." (b) The LiPS paper (arXiv:2503.08349) explicitly benchmarks "position equivalence" and "torque equivalence" serial approximations against directly simulating the true parallel/closed-loop ankle in IsaacGym, and finds the true-loop simulation wins — they built the real loop specifically because the approximations were insufficient for policy quality, not just for validation fidelity. This is the closest published data point to your own MuJoCo AB-vs-RP A/B finding. Use RP+envelope in Isaac only as a fast smoke-test / sanity-check lane, not as your cross-engine ground truth. | Real-World Humanoid Locomotion w/ RL (arXiv:2303.03381, Digit/Isaac Gym virtual-spring description); LiPS (arXiv:2503.08349, "position equivalence" / "torque equivalence" quotes, §below); Agility Robotics "Crossing the Sim2Real Gap With NVIDIA Isaac Lab" blog (confirms Digit's rod/tarsus closed-chain kinematics caused "instabilities in how constraints are solved" in IsaacLab — they treat it as a bug to fix, not a reason to abandon the true loop) |

**Read order**: implement #1 directly (it's a bounded, well-documented change); if you later want the importer to also
regenerate the rest of the tree automatically, do the site→body/anchor pre-conversion in 2(a) rather than fighting a
crash; keep #3 only as an extra fast-turnaround sanity lane, per LiPS's own finding that the approximation is
inferior to the true loop for anything beyond a smoke test.

---

## 1. Official Isaac Sim procedure for closed-loop kinematics (the "how")

### 1.1 Core constraint and the fix

Isaac Sim "Rig Closed-Loop Structures" tutorial, 4.5.0 (worded identically in 6.0.0), using the Robotiq 2F-85
parallel gripper as the worked example:

> "Articulations must be kinetic trees."
> "To eliminate those warnings you must choose one joint to exclude from the Articulation and have it be treated as
> a maximal coordinate joint."
> "the joint to exclude from articulation only serves as a spatial constraint. Identify a joint with no limits, no
> resistance, and no drive."
> "To remove the joints from the articulation, select the `left_inner_knuckle_joint` and `right_inner_knuckle_joint`
> prims. In the Joint section under physics, select **Exclude From Articulation**."
> "the joint to exclude from articulation only serves as a spatial constraint"
> "maximal coordinate joints are treated with a lower priority by the solver, it is the joint that accumulates the
> most error in simulation."

Selection heuristic given: "In terms of simulation efficiency, the best choice of joint to exclude from articulation
is the one that minimizes the length of articulations. However, you must also consider utility. The best joint to
remove is the one that interferes the least with the robot functionality." — for us this argues for excluding the
rod↔ankle-plate connections (passive, no drive) rather than anything crank-side (actuated).

For multi-finger/parallel synchronization the tutorial separately layers a `PhysxSchema` **Mimic Joint** API
(gearing ratio) — not applicable to our case since both ankle cranks are independently actuated, not mechanically
geared to each other.

### 1.2 USD schema attribute (exact name, confirmed twice independently)

`uniform bool physics:excludeFromArticulation = 0` (default false) — a **UsdPhysics** schema attribute on the joint
prim itself (this is core UsdPhysics, not a PhysX-only `physxJoint:` namespaced attribute). Per the Omni Physics
docs: "A joint in a loop may use its `excludeFromArticulation` attribute flag to denote that it wishes to remain a
maximal joint, and at this point the loop is then broken." Side effect: "When a joint is marked as excluded from the
articulation, `PhysxSchema.PhysxLimitAPI` is supported for that joint, whereas it is not supported for other
articulation joints." Confirmed identically in the MJCF importer's own C++ (`jointPrim.CreateExcludeFromArticulationAttr().Set(true);` — see §3).

### 1.3 A second, less-common technique: "Guide" joint purpose

A community write-up (WIM Corp tech blog, "Handling Closed Loop Robots in Isaac Sim") describes an alternative/
complementary technique used on an OnRobot RG6 gripper:

> "Isaac Sim's Articulation system does not directly support closed-loop structures" (PhysX tree-traversal fails on
> cycles).
> Method A — **Guide Joint**: change `Joint > Purpose` "from Default to Guide." Guide joints have "their position
> determined without physical resistance" and are "excluded from force calculations in articulation traversal."
> Method B — **Exclude From Articulation**: "maintains the physical connection of the joint while treating it as
> non-existent in Articulation calculations."
> Practical recipe for the 4-joint-per-finger loop: keep the single motor-driven joint at `Purpose: Default`, set the
> other 3 passive joints per finger to `Purpose: Guide`, and additionally check `Exclude From Articulation` on the
> body-connected joints.

This is a second, less-documented lever (`Joint > Purpose = Guide`) beyond `excludeFromArticulation` — worth knowing
exists, but the primary, docs-endorsed mechanism for us is still `excludeFromArticulation`.

### 1.4 Joint-type restriction inside vs. outside the articulation

IsaacLab discussion #1341 ("D6 Joint: A good choice?"), maintainer **StrainFlow**:

> "Revolute and Prismatic joints are the only two that can be vectorized and driven as part of an articulation, so
> for now they are the only joints that are supported."

This restriction applies **only to joints that remain part of the reduced-coordinate articulation tree.** A joint
marked `excludeFromArticulation` becomes a normal maximal-coordinate PhysX rigid-body joint and is *not* subject to
this restriction — PhysX 5.5 docs confirm loop-closing joints are ordinary "rigid-body Joints" (their own worked
example: "we could tie the ragdoll's hands together by adding a Distance Joint between the two hand spheres"), which
includes D6, spherical, fixed, revolute, prismatic, and distance joint types. Practical implication for our 2-RSU
ankle: model each real universal/U-joint as a **spherical** (or D6-with-2-free-rotations, tighter to the real
kinematics) joint on the excluded side, and decompose any U-joint that must stay *inside* the tree (e.g. if you want
one rod chain to remain part of the serial articulation branch feeding the ankle plate) into **two stacked revolute
joints**, per StrainFlow's explicit recommendation: "stack two revolute joints" or arrange geometry so "all
spherical bearings are parallel" and model each with a single revolute.

### 1.5 Solver participation, stability, and known failure modes

PhysX 5.5 `Articulations.html`:

> "it is possible to create loops in the articulation by adding rigid-body Joints between articulation links."

IsaacLab discussion #1501 ("How does the computation of closed loop mechanism work?"), **StrainFlow**:

> "Articulations use a reduced coordinate solver which is very accurate but cannot handle closed loops." The excluded
> joint is "noticeably less accurate in the simulation" — "If the joint isn't converging well there will be
> noticeable movement/jitters/issues with that joint." Recommendation: "play with the solver settings and pick a
> joint to exclude that can be modeled with lower accuracy" and accept "the sim2real gap." Real example given: an
> Ackermann-suspension robot had closed-loop instability so bad they redesigned the suspension geometry to eliminate
> the loop entirely rather than fight the solver.

NVIDIA developer forum, "Closing Loops in Articulation Causing Non-physical Behavior" (thread 219601) — a directly
analogous failure and fix:

> User **AlanSunHR**: closed a humanoid ragdoll loop with a distance joint + `excludeFromArticulation` on one arm
> joint. "when I press the play button, the humanoid suddenly flew away." Root cause, self-diagnosed: "When I use
> `set_joint_positions`, I only specify the active joints in the articulation. If I set all the joint positions
> including the passive ones, there's no such problem." Maintainer **qwan** (NVIDIA): manually exclude one
> loop-closing joint via the property checkbox, and "adjust physics solver iteration counts in the articulation root
> prim properties if convergence issues persist."

IsaacLab discussion #5157 ("Articulation object with mechanical closed loops") — same failure mode, one layer up the
stack (matters specifically because you're using IsaacLab's `Articulation` wrapper, not raw `ArticulationView`):

> User **jeferal**: closed-loop USD "worked correctly in Isaac Sim's GUI" but broke "when creating an `Articulation`
> object with `IdealPDActuatorCfg` and calling `write_data_to_sim()`" — "the closed loop behaviour is OK when
> creating the Articulation object, but NOT calling `robot.write_data_to_sim()`."
> Maintainer **RandomOakForest**: `write_data_to_sim()` overwrites joint params from `robot.data` — "the articulation
> wrapper sets whatever is in `robot.data`," which can stomp the carefully configured passive-joint stiffness/damping.
> Fix: for the excluded/passive joint's actuator cfg, use `stiffness=None, damping=None` so "the values from the USD
> joint prim are preserved" rather than forced to zero; ensure the excluded joint has "no limits, no resistance, and
> no drive (or that you transfer those properties to an adjacent joint before excluding it)"; avoid "repeatedly
> overwriting joint positions each step," which can "fight the constraint solver."
> Follow-up solver-iteration tuning from the same thread: user needed
> `solver_position_iteration_count=64, solver_velocity_iteration_count=32` for stability; maintainer guidance was to
> **lower the timestep first**, start moderate (8–16 position / 2–4 velocity iterations), and balance
> throughput vs. stability empirically (example given: `1/120 s` timestep with 8/2 iterations).

IsaacLab issue #1250 ("Reset Default Joint Position of Robot with Closed Loop Linkage") — **this is essentially our
exact scenario already attempted by someone else** (Digit-v3, closed-loop linkage, articulation root moved to
torso, loop joint excluded):

> "the robot ends up flying away" on a programmatic root-state + joint-position reset after a fall, despite working
> fine in the GUI. **No maintainer fix was ever posted; the issue is still open with zero responses.**

IsaacSim issue #118 (bug report, position controller + `excludeFromArticulation`) — a related but distinct failure,
useful as a heads-up if you drive the ankle cranks through the `IsaacArticulationController` OmniGraph node rather
than IsaacLab's Python actuator path:

> Setting `physics:excludeFromArticulation` from 0→1 on two passive joints "has an effect on
> `controller_handle.num_dof`" — it unexpectedly drops to 0 instead of the expected 6 active DOF, with an
> `OgnIsaacArticulationController.py` index-out-of-bounds error. Open, unresolved as of report date (Aug 2025).

**Practical synthesis for our ankle**: (1) never partially reset joint state (`set_joint_positions` on actuated
joints only) on a closed-loop articulation — always set *all* joint positions/velocities including the passive rod
DOFs together, every reset; (2) do not let `write_data_to_sim()` push `stiffness`/`damping` onto the excluded U-joint
actuator config — leave it `None` so USD-authored values persist; (3) budget for raising
`solver_position_iteration_count`/`solver_velocity_iteration_count` well above quadruped defaults (the thread above
needed 64/32 in a hard case; start at 8–16/2–4 and go up only if jittery) and consider lowering `sim.dt` first,
exactly as PhysX's own maintainers recommend, before touching iteration counts; (4) if you drive cranks via the
OmniGraph `IsaacArticulationController` node rather than IsaacLab's Python `Articulation.set_joint_position_target`,
watch for issue #118's DOF-count corruption — safer to stay on the Python `Articulation`/`ArticulationView` API.

---

## 2. Shipped/published examples of real closed-loop legs in Isaac-family sims

### 2.1 Agility Digit / Cassie — the direct precedent for a closed-loop ankle/toe chain

Digit and Cassie both have a closed tarsus/toe/heel-spring chain (not identical to our 2-RSU ankle geometry, but the
closest real, shipped, published biped example of "closed-loop leg linkage in an Isaac-family simulator"):

- **Isaac Gym era (research port, arXiv:2303.03381, "Real-World Humanoid Locomotion with RL")**: "given the closed
  kinematic chains and underactuated nature of the knee-shin-tarsus and tarsus-toe joints of the robot, Isaac Gym
  was unable to effectively model these dynamics. To address this limitation, a 'virtual spring' model with high
  stiffness was introduced to represent the rods, applying forces calculated from the spring's deviation from its
  nominal length to the rigid bodies, and employing an alternating simulation sub-step method to quickly correct the
  length of the virtual springs." — i.e., **neither** a true loop-closure joint **nor** a serial-equivalent
  approximation; a third pattern (compliant virtual-spring surrogate for the rod), used specifically because Isaac
  Gym-era tooling couldn't do a stable true loop.
- **Isaac Lab era (current, Agility's own words, "Crossing the Sim2Real Gap With NVIDIA Isaac Lab" blog + Robot
  Report coverage)**: Agility explicitly names, as one of the multi-month sim2real gaps they hunted down,
  "instabilities in how constraints are solved in our unique closed-chain kinematics (formed by the connecting rods
  attached to our toe plates and tarsus)." They treat this as a genuine bug in constraint-solving to be fixed (not a
  reason to fall back to a serial approximation), consistent with the general PhysX-maintainer guidance in §1.5 about
  iteration counts and joint choice for excluded joints. The blog does not disclose their exact USD joint layout.
  IsaacLab's supported-robots list (from the IsaacLab GitHub README) explicitly includes "Agility Digit and Cassie"
  as first-class IsaacLab locomotion assets today, meaning some closed-loop-in-USD solution ships in IsaacLab's own
  asset set — worth pulling `isaaclab_assets/robots/` (or the Nucleus-hosted Digit/Cassie USD) directly and
  inspecting its `physics:excludeFromArticulation` usage as a second, ready-made concrete example beyond the
  Robotiq-gripper tutorial (not yet pulled in this pass — flagged as a good next lookup if you want a second
  worked biped example rather than a gripper).

### 2.2 LiPS (arXiv:2503.08349) — a full closed-loop parallel ankle trained end-to-end in IsaacGym, with a head-to-head vs. serial approximations

This is the strongest, most directly relevant published result for deliverable #4 (does anyone judge serial+envelope
"sufficient," or do they build the real loop). Confirmed via fetch:

> Simulator: "Our training was conducted on a single NVIDIA 4090 GPU, utilizing 4096 parallel environments in
> IsaacGym for each training session."
> Their method: "The LiPS method directly uses the parallel model for training and deployment in the reinforcement
> learning environment" — i.e., **the true closed-loop ankle dynamics, not a serial surrogate**, is what they
> actually ship.
> They explicitly define and reject the two serial-approximation patterns as the field's status quo:
> - **Position equivalence**: "Directly use the joint positions in the parallel mechanism as the desired positions
>   and control the joint positions in the parallel mechanism using a PD controller. This can be simply approximated
>   by treating the two parallel joints as equivalent average forces."
> - **Torque equivalence**: "We can convert the joint torques from the serial mechanism to the parallel mechanism
>   using analytical solutions. The problem with this method is that solving the analytical solutions at the same
>   frequency as the joint control on the robot side consumes a lot of computational resources and may result in no
>   solutions."
> Broader framing (from search synthesis of the paper): "the GPU-accelerated Isaac Gym RL framework lacks native
> support for closed-chain kinematics, requiring custom implementations and approximations. Researchers have adopted
> strategies such as using kinematic rather than actuator joint space or approximating the parallel mechanism as a
> serial chain, though these approaches can yield suboptimal results."

This is exactly the same fork in the road we're facing (our MuJoCo AB = "true loop," our MuJoCo RP = "torque
equivalence" via crank-space IK/FK envelope), published by an independent group, with the true-loop side winning.
It's the single best piece of evidence that **serial+envelope in Isaac should not be treated as equivalent to the
true loop for anything beyond a cheap sanity check** — reinforces recommendation #3 in §0.

Note: IsaacGym (the older, now-deprecated 2021-era standalone GPU sim used by LiPS) and IsaacSim/PhysX 5 (current)
share PhysX ancestry but LiPS's paper does not disclose whether their "true parallel model" used the same
"extra-joint + exclude-from-articulation" pattern documented in §1, a different maximal-joint trick, or IsaacGym's
now-removed Flex backend. Treat their result as strong motivational evidence, not as a ready-made USD recipe.

### 2.3 Ankle/knee closed-loop hardware landscape (context, not sim-specific)

"A Framework for Optimal Ankle Design of Humanoid Robots" (arXiv:2509.16469 — already in `refs/` locally) confirms
our mechanism naming and the state of the art: parallel 2-DOF ankle architectures it studies are **SPU**
(Spherical-Prismatic-Universal, linear actuator) and **RSU** (Revolute-Spherical-Universal, rotary actuator — our
family). Notable RSU/parallel-ankle shipping robots it names: "Tesla's Optimus, Unitree's G1, PNDbotics' Adam,
Agility Robotics' Digit, Fourier's N1, LOLA, Pandora, and Kangaroo." Structurally: "The shin W and the foot F are
connected to each other through the interposition of 3 legs... The central leg consists of a single universal joint
U0 that directly connects the shin and the foot... The other two legs... RSU mechanism has, as its leg i, a serial
kinematic chain connecting four links through the sequence of joints: revolute Ri, spherical Si, and universal Ui."
Connectivity-graph note directly useful for counting how many joints you must exclude: "Each graph contains 2
independent loops" for a 3-leg (1 central U + 2 actuated RSU legs) parallel ankle — i.e., **you need to break exactly
2 independent loops per ankle** (not per leg) if your geometry follows this canonical 3-leg pattern; our repo's own
4-connect encoding (2 per leg × 2 legs) is consistent with "2 rods × 1 excluded joint each" if there is no separate
central passive U-joint, or may need re-auditing against this "2 independent loops" count if there is a third,
central connection not captured by the 4 `connect` tags.

### 2.4 Other Isaac-adjacent closed-loop robots found (not deeply verified this pass)

- **Unitree G1** — hardware ankle is a real parallel mechanism per §2.3, but the shipped `unitree_rl_lab` / IsaacLab
  G1 USD assets found in this search are **not** confirmed to model the true closed loop (no `excludeFromArticulation`
  usage found in the surfaced search snippets); the G1 policy ecosystem (`G1-Playground`, `unitree_rl_lab`,
  `unitree_sim_isaaclab`) appears to train against the standard IsaacLab G1 USD, which likely already collapses the
  ankle to its 2 serial-equivalent actuated DOF at the USD level (as most RL-focused USD ports do) rather than
  exposing the parallel linkage — worth a direct USD inspection if you want a second confirmed example, not yet done
  in this pass.
- **Robotiq 2F-85 gripper** — the actual shipped, maintained, first-party Isaac Sim example of a closed loop
  (§1.1/§1.4), not a leg but structurally the cleanest fully-worked reference for the `excludeFromArticulation` +
  mimic-joint pattern.
- **Disney BDX droid / Open_Duck_Mini / BDX-R-IsaacLab** — community IsaacLab ports exist and train real policies,
  but nothing surfaced in this pass confirms a closed-loop leg mechanism specifically (BDX's legs are commonly
  simplified to serial in these community ports); not a strong precedent either way without deeper digging.

---

## 3. MJCF importer fidelity — exact code path (this is the load-bearing finding for deliverable #3)

Source: `isaac-sim/mjcf-importer-extension` (the open-sourced extension backing `isaacsim.asset.importer.mjcf`,
current `main`, `[package] version = "2.3.6"`, commit history shows the loop-joint feature landed in
"add loop joints and fix tendons" on 2025-02-21, immediately before the "release 5.0" tag — i.e. this is a
**5.0-era feature**, present in 5.0/5.1).

`MjcfTypes.h`:
```
struct MJCFEqualityConnect
{
public:
    std::string body1;
    std::string body2;
    Vec3 anchor;
};
```

`MjcfParser.cpp` (constraint parsing — **only path that exists**, no `site1`/`site2` handling anywhere in the repo):
```cpp
void LoadEqualityConnect(tinyxml2::XMLElement* c, MJCFEqualityConnect* equalityConnect)
{
    equalityConnect->body1 = std::string(c->Attribute("body1"));
    equalityConnect->body2 = std::string(c->Attribute("body2"));
    // Parse anchor attribute
    std::string anchorStr = std::string(c->Attribute("anchor"));
    sscanf(anchorStr.c_str(), "%f %f %f", &equalityConnect->anchor.x, &equalityConnect->anchor.y,
           &equalityConnect->anchor.z);
}
```
Called from `MjcfImporter.cpp` for every `<equality><connect .../></equality>` element found:
```cpp
tinyxml2::XMLElement* eq = root->FirstChildElement("equality");
...
tinyxml2::XMLElement* c = eq->FirstChildElement("connect");
...
MJCFEqualityConnect* equalityConnect = new MJCFEqualityConnect();
LoadEqualityConnect(c, equalityConnect);
```

Our `pygmalion_v4_printed_loop.xml` (L315-320):
```xml
<equality>
  <connect name="L_loop_A" site1="L_rod_A_end" site2="L_ball_A" solref="0.002" solimp="0.999 0.9999 0.0001"/>
  <connect name="L_loop_B" site1="L_rod_B_end" site2="L_ball_B" solref="0.002" solimp="0.999 0.9999 0.0001"/>
  <connect name="R_loop_A" site1="R_rod_A_end" site2="R_ball_A" solref="0.002" solimp="0.999 0.9999 0.0001"/>
  <connect name="R_loop_B" site1="R_rod_B_end" site2="R_ball_B" solref="0.002" solimp="0.999 0.9999 0.0001"/>
</equality>
```
uses **`site1`/`site2`**, not `body1`/`body2`/`anchor`. `tinyxml2::XMLElement::Attribute("body1")` returns `nullptr`
when the attribute is absent; `std::string(nullptr)` is undefined behavior. **This will not import correctly (most
likely a hard crash) as-is.** This is a concrete, reproducible blocker, not a speculative fidelity concern.

Downstream, *if* the parse succeeded, `MjcfImporter.cpp`'s `analyzeConstraints()` (L46-125) groups `connect`
constraints **by unordered body pair** and picks a USD joint type purely from **how many constraints share that
pair**:
```cpp
switch (constraints.size())
{
case 1: jointDef.type = "spherical"; jointDef.position = constraints[0]->anchor; break;
case 2: jointDef.type = "revolute"; /* axis inferred from the vector between the two anchors */ break;
case 3: jointDef.type = "fixed";    /* position = average of the 3 anchors */ break;
}
```
And joint creation (L328-360) always finishes with:
```cpp
jointPrim.CreateExcludeFromArticulationAttr().Set(true);
```
under path `rootPrimPath + "/loop_joints/" + <body1>_<body2>`. This is precisely the manual pattern from §1 —
**the importer is a thin code-generator for exactly the hand-authored recipe**, nothing more sophisticated (no D6,
no universal-joint type, no MuJoCo `solref`/`solimp` compliance carried over — compliance/stiffness of the loop
closure is lost on import either way, hand-authored or imported). Since our 4 constraints are 4 distinct body pairs
(rod↔plate ×2 legs ×2 rods), a fixed importer would emit 4 `UsdPhysicsSphericalJoint`s, matching our own MuJoCo
modeling choice (each real U-joint approximated as a 3-DOF point constraint) exactly.

---

## 4. Caveats / things not fully verified this pass

- Did not obtain a second **confirmed** shipped leg/ankle USD (beyond the Robotiq gripper tutorial) with
  `excludeFromArticulation` set — the Digit/Cassie IsaacLab asset almost certainly has one, but this pass didn't
  pull and inspect that USD directly; worth a follow-up if you want a second worked example before committing to a
  layout.
- Did not verify whether LiPS's "true parallel model in IsaacGym" used the same `excludeFromArticulation` mechanism,
  a different maximal-joint approach, or IsaacGym's separate Flex backend — their paper doesn't say, and IsaacGym is
  EOL/not what you're targeting (IsaacSim 5.x/PhysX 5) anyway, so treat it as motivational evidence only.
- Solver-iteration numbers cited (8-16/2-4 baseline, up to 64/32 in a hard case) come from a gripper/manipulator and
  a generic ragdoll-arm thread, not a legged/ground-contact articulation under load — our ankle will also be
  carrying full-body dynamic loads plus foot contact simultaneously with the loop closure, so budget for retuning
  empirically rather than trusting these numbers directly.
- The importer-crash claim (§3) is based on static code reading of `tinyxml2::XMLElement::Attribute()` semantics and
  C++ `std::string(const char*)` UB with a null pointer — not an actual reproduced crash log in an IsaacSim 5.x
  install. High confidence given the code, but worth a 5-minute empirical confirmation before writing it into any
  external-facing decision doc.
- Did not check whether a newer/unreleased branch of the importer (beyond the `main` fetched here) has since added
  `site1`/`site2` support; if you're on a very recent IsaacSim 5.x point release, re-grep the shipped extension's
  `MjcfParser.cpp` locally for `"site1"` before assuming the blocker still applies.

---

## 5. Empirical follow-up (2026-08-27, implementation pass) — §4's open item, settled

The §3/§4 prediction was correct in mechanism and wrong in failure mode, so the caveat in §4 is now
closed with a measurement rather than a code reading.

**Static, on the installed extension** (`isaacsim.asset.importer.mjcf`, `version = "2.5.8"`, i.e.
newer than the 2.3.6 `main` read in §3): `strings` on the shipped
`bin/libisaacsim.asset.importer.mjcf.plugin.so` contains `body1`, `body2`, `anchor`, `connect`,
`equality` and **no `site1`/`site2` at all**. So the §4 caveat "re-grep a newer point release before
assuming the blocker still applies" is answered: it still applies at 2.5.8.

**Dynamic** (`tools/sim2sim/mjcf_import_probe.py`, one run, our `pygmalion_v4_printed_loop.xml`):

```
[Error] [omni.kit.commands.command] Failed to execute a command: MJCFCreateAsset.
  ... isaacsim/asset/importer/mjcf/impl/commands.py", line 88, in do
 <class 'RuntimeError'> basic_string::_M_construct null not valid
```
Result: `import_status = (False, None)`, 0 joint-ish prims in the output stage, no `/loop_joints`
scope, `physics:excludeFromArticulation` set on nothing.

**Verdict**: the predicted `std::string(nullptr)` is exactly what happens - `_M_construct null not
valid` is libstdc++'s own name for it. It surfaces as a catchable `RuntimeError` rather than the
predicted segfault, so the process survives; but nothing usable is produced, which is the part that
mattered. Path #1 (hand-authoring) was the right call. Not tried: the §0 path 2(a) site->body/anchor
pre-conversion, which remains a live fallback if the importer's other output (meshes, actuators,
sensors) is ever wanted automatically.

**One correction to §0 row 1's arithmetic**: it says "exactly 4 such joints per ankle ... ~8 extra
joint prims total for both ankles". The model has **2 `connect` per ankle, 4 in total**, so the built
USD carries **4** spherical joints, not 8 - one per rod (`L/R_loop_A`, `L/R_loop_B`). §2.3's "2
independent loops per ankle" is the count that matches our geometry, and our 4 tags are 2 per leg,
not 4 per leg. The §0 conclusion is unaffected; only the joint count was doubled.

Built and validated: see `docs/sim2sim/2026-08-27_ab_loop_usd.md`.
