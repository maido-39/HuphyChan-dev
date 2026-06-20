# 20 · Fusion 360 ↔ Isaac Lab 연동 (리포트)

> CAD(Fusion360) → URDF/MJCF → USD 파이프라인 + 함정. HW 설계 반복(CAD수정→재학습) 정립용. — 리서치 ws2d3t2mh

## 파이프라인
FUSION 360 -> ISAAC LAB PIPELINE (for the Pygmalion lower-body biped; you iterate CAD<->sim often, so script it).

TWO ROUTES, SAME DATA, DIFFERENT BREAKAGE:
 - Route A (mainstream): Fusion -> URDF (community add-in) -> Isaac Lab UrdfConverter -> USD. Best-documented, one-step in Isaac Lab.
 - Route B (YOUR PROJECT): Fusion -> URDF -> MJCF -> Isaac Lab MjcfConverter -> USD. Confirmed in repo: source is assets/biped_lower_body_mjcf/robot.xml (robstride_biped.yaml line 14) and spec.py convert_to_usd() uses MjcfConverter (lines 247-267).

KEEP ROUTE B. Your env, sensors, and the -90deg forward-axis fix are all built around the MJCF->USD nesting where the converter puts every body one level deep under a container Xform named after the root body: prim paths are /Robot/base_link/<body>, NOT a flat /Robot/<body>. This is CONFIRMED in code: velocity_env_cfg.py lines 156-161 set contact_forces.prim_path='{ENV_REGEX_NS}/Robot/base_link/.*' and height_scanner='.../base_link/base_link', with a code comment explaining the nesting. spec.py also strips a spurious worldBody ArticulationRootAPI (_strip_spurious_worldbody_root, lines 214-231, called at line 266). Switching to the direct UrdfConverter route would change every prim_path AND re-introduce the forward-axis bug -> only do it if you re-validate FK end to end.

EXPORTER CHOICE (URDF stage): cadop/fusion360descriptor (GUI, WYSIWYG STL, name-mapping so URDF names stay stable as CAD evolves, separate visual/collision export) or syuntoku14/fusion2urdf (full inertials + materials; requires base component renamed exactly 'base_link', parent=Component2, flat bodies-only components, only Rigid/Slider/Revolute joints). None emit USD -- you always go through Isaac Lab's converter. None author simplified collision meshes -- you do that downstream (obj2mjcf + CoACD for the MJCF stage).

MASS / INERTIA / COM: come from Fusion's mass-properties engine AUTOMATICALLY, but ONLY if every body has a real Physical Material (density) assigned -- default 'unspecified'/'Steel' gives wildly wrong masses. Exporter converts mm->m and the inertia tensor units, writes COM as <inertial><origin>. The repo trusts source inertials: convert/import_inertia_tensor:true (yaml line 20). VERIFY against the 51.8 kg ground truth after EVERY export -- mass_utils.get_mass_summary(robot) returns {body: kg, TOTAL} for exactly this check.

COLLISION (PhysX is convex-only, <=255 verts/hull): a raw CAD mesh collider is silently reduced to one convex hull (loses concavities) or, decomposed, becomes ~32 hulls x 64 verts that tank GPU step rate; high-aspect-ratio hulls can be GPU-rejected -> CPU fallback -> large slowdown. Note your self_collision:true (yaml line 22) makes collider quality matter MORE (left/right leg + foot-foot pairs are live). Author separate decimated collision meshes; prefer primitive capsules/spheres; keep colliders on feet/shins/knees, strip elsewhere (Anymal-C pattern). This protects your training throughput.

UNITS/FRAMES: Fusion=mm, URDF/USD=m (scale 0.001). ROS/URDF +X forward, +Y left, +Z up. YOUR SPECIFIC TRAP (recurs on every re-export unless CAD is reoriented): your CAD's sagittal direction was body-Y, so an Isaac vx command crab-walks. Fix = rotate base_link's CONTENTS (child bodies+geoms+inertial) by -90deg about Z, NOT the root/freejoint frame and NOT via spawn rotation (the repo has scripts/rotate_robot_forward.py for this). Regression-check: feet separated along +Y, forward = +X.

ACTUATOR DRIVES are owned by your spec, not the URDF/USD: build_articulation_cfg sets ImplicitActuatorCfg stiffness/damping/effort_limit/armature from the YAML actuators block (spec.py), and the URDF joint_drive is explicitly None for both converters (spec.py lines 275 + MjcfConverter path). So URDF/MJCF joint limits only need to be physically plausible, not final. IMPORTANT consequence for the toe ablation + gear study: stiffness/effort/armature changes are runtime-only and do NOT trigger a USD reconvert (the convert cache keys on source bytes + convert/* only).

## 함정 체크리스트
- Assign a real Physical Material (density) to EVERY body in Fusion before export (Modify > Physical Material). Default 'unspecified' = wrong mass. Verify with Inspect > Mass Properties.
- Model every link as a top-level bodies-only COMPONENT (no nested components); name base_link exactly; use the exact env link/joint names; joint origins of mated components must be coincident.
- After every export run a 4-point regression script and gate on it: (1) TOTAL mass == 51.8 kg (mass_utils.get_mass_summary), (2) COM sane, (3) FK shows feet separated along +Y with forward = +X, (4) contact + height-scan sensors actually find bodies.
- Set mesh scale = 0.001 (mm -> m). Confirm lengths and the inertia tensor are in meters/kg*m^2.
- FORWARD-AXIS: if CAD sagittal is body-Y, rotate base_link CONTENTS (children+geoms+inertial) -90deg about Z via scripts/rotate_robot_forward.py. NOT the root frame, NOT spawn rotation. Re-apply on every re-export until the CAD itself is reoriented.
- Author SEPARATE decimated collision meshes; do not use raw CAD triangle meshes as colliders. Prefer primitive capsules/spheres. Keep colliders on feet/shins/knees, strip elsewhere (Anymal-C pattern). Matters more here because self_collision:true.
- Respect the PhysX convex limit: <=255 verts per hull; if using convex_decomposition, tune hull count/error per link and watch for GPU->CPU fallback (Isaac Lab simulation_performance guide).
- After MJCF->USD convert, INSPECT the prim tree: expect /Robot/base_link/<body> nesting. Ensure contact_forces prim_path='{ENV_REGEX_NS}/Robot/base_link/.*' and height_scanner='.../base_link/base_link' (velocity_env_cfg lines 159-161) still match new body names.
- Confirm spec.py _strip_spurious_worldbody_root ran (the MJCF converter can add a worldBody ArticulationRootAPI that must be deactivated).
- Every joint in the USD must belong to an actuator group or Isaac Lab errors at startup; verify the toe is still covered by the toe_passive passive_spring group (spec.py validates this).
- A toe stiffness/damping/effort or knee armature/effort change is a YAML-only, runtime change (ImplicitActuatorCfg) -- do NOT force a USD reconvert for it. Only mesh/geometry/joint-structure changes need convert_asset.py --force.
- Isaac Sim 5.1+ changed merge_fixed_joints (links carrying explicit mass/inertia no longer merged; open bug IsaacLab #3943). Verify post-convert body count matches expectation.
- If you ever change the knee belt ratio, update analyze.py line 31 and analyze_motor_util.py line 32 MOTOR_RATING['knee'] AND the YAML knee effort_limit/velocity_limit_rpm/armature together, or util% charts will be wrong.

## 출처
- [cadop/fusion360descriptor -- Fusion 360 URDF exporter (GUI, WYSIWYG STL, name mapping, visual/collision)](https://github.com/cadop/fusion360descriptor) — _fusion360_
- [syuntoku14/fusion2urdf -- Fusion 360 URDF export (component/joint/base_link rules, inertials)](https://github.com/syuntoku14/fusion2urdf) — _fusion360_
- [Isaac Sim MJCF Importer Extension -- naming rules, ArticulationRootAPI, body-tree nesting (the /Robot/base_link/<body> quirk)](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/ext_isaacsim_asset_importer_mjcf.html) — _fusion360_
- [NVIDIA PhysX 5.3 Geometry -- convex mesh 255-vertex limit, convex-only rigid colliders](https://nvidia-omniverse.github.io/PhysX/physx/5.3.0/docs/Geometry.html) — _fusion360_
- [Isaac Lab Simulation Performance and Tuning -- remove non-essential colliders, primitives over meshes, GPU/CPU fallback](https://isaac-sim.github.io/IsaacLab/main/source/how-to/simulation_performance.html) — _fusion360_

관련: [[02_asset_conversion]] · [[08_robot_hotswap]] · [[18_research_roadmap]]
