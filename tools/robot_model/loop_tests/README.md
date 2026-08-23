# Loop-ankle tests inside mjlab (docs/91 §4.2-4.4, §5)

Run from `mujoco-sim/mjlab` with `CUDA_VISIBLE_DEVICES="" PYG_V2=1 PYG_ANKLE_LOOP=1 PYG_NO_DR=1 .venv/bin/python3 ../../tools/robot_model/loop_tests/<script>`.

| script | what |
|---|---|
| `loop_env_smoke.py` | env builds, obs/action dims, reward terms evaluate, thermal rated vector |
| `loop_env_hang.py` | root pinned in the air: crank action -> ankle map (loop) or ankle action (serial, drop PYG_ANKLE_LOOP) + standing sag |
| `loop_env_load.py` | hanging, external foot torque 0/10/20/40 N*m -> deflection + closure (constraint stiffness A/B via PYG_LOOP_SOLIMP) |
| `loop_env_ground.py` | root pinned 10-20 mm below standing: feet pressed into the floor, closure/jitter/env divergence (mujoco_warp #1510 check) |
| `loop_bent_keyframe.py` | plain MuJoCo: solve the loop-consistent KNEES_BENT pose -> `assets/pygmalion_v2/pygmalion_v3_printed_loop_bent.json` |
| `loop_bent_check.py` | mjlab: reset with PYG_INIT_BENT=1 and report closure |
