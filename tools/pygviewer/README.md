# pygviewer - Pygmalion Sim &harr; Real comparison web viewer

One process that owns one MuJoCo model, runs it at the training rates on the CPU, and serves
it as a 3D scene with a control panel (viser, **:8094**) plus a REST/WebSocket API
(FastAPI, **:8095**, OpenAPI at `/docs`).  Built so that a number read here is comparable to
the same number read in training - not merely similar.

Status: **P0 (bake + sim loop + scene + /status), P1 (manual joint control, base fixing,
ground toggle, plots), P2 (ONNX/`.pt` policy, obs builder, PD gain source, velocity
command, per-term obs-source switch) and P3 (wire schema, `/ws/in`, HUPHY UDP bridge, dummy
transmitter, record/replay, `real_replay`/`file_replay` drive, Telemetry panel) are
implemented.**  P4 comparison/shadow mode is a skeleton with the interface fixed - see
`docs/121_pygviewer_design.md` section 6.

---

## Run

```bash
cd /home/syaro/MikuchanRemote/Human-Pygmalion

# viewer (viser 8094 + API 8095), CPU only - the GPU belongs to the trainer
CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 \
    tools/pygviewer/run.py --variant LegOnly-AB --port 8094 --api-port 8095

# equivalent, as a module (namespace package, no tools/__init__.py needed)
CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 \
    -m tools.pygviewer --variant LegOnly-AB

# rate / footprint check, no browser
... tools/pygviewer/run.py --variant LegOnly-AB --headless --seconds 5
```

Options: `--base free|fixed|pivot` (default `fixed` - nothing balances the robot in P1, so a
free base topples in about 2 s), `--keyframe home|knees_bent`, `--stale-ok`,
`--no-api`, `--cache DIR`.  The process refuses to start if 8094 or 8095 is already taken.

LAN: `http://192.168.20.177:8094` and `http://192.168.20.177:8095/docs`.

## Bake

The Pygmalion MJCF in `asset_zoo` has **no actuators, no floor and no keyframe** (`nu=0`) -
mjlab attaches all three at env-build time.  So the viewer runs a model *baked out of the
training env*:

```bash
CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 \
    tools/pygviewer/run.py bake model --variant LegOnly-AB
... bake model --all          # all six, one subprocess each (~8 s and ~1.3 GB per variant)
```

Output goes to `/home/syaro/pyg_fea/pygviewer/cache/<variant>.mjb` +
`<variant>.model_contract.json`.  Six variants: `{FullDoF,SemiFullDoF,LegOnly}-{AB,RP}`.

The bake adds exactly three things to the scene spec and edits **no XML**:
`pyg_anchor` (mocap body, no geom - a geom would change the total mass, which the bake
asserts is unchanged), `base_weld` (equality/weld, inactive) and `base_pivot`
(equality/connect, inactive).  It then asserts the compiled model matches the env on `nu`,
`nq/nv`, mass, keyframe qpos, actuator force range and gain, gravity, and the whole
`opt` block (timestep, integrator, solver, iterations, cone, impratio).

The contract records, among other things: `joint_names`, `action_joint_names` and
`obs_joint_names` **in the env's own resolved order**, `obs_layout` (the actor group's terms,
because their names change with `PYG_STUDENT_TEACHER`), `default_q`, `gains` (kp/kd from the
mjlab actuator objects, effort from the model), `tn_curves`, `dof_props`, `safe_clip`,
`joint_contract` (axis, range, `travel_sign`, `mirrored` / `range_mirrored` / `axis_mirrored`),
`keyframes`, `spawn_base_z`, `env_toggles`, `sim_options`, `anchor_eq_ids`, `floor_geom`,
`loop_transmission` (AB) and source hashes.  The viewer re-hashes the XML,
`pygmalion_constants.py` and the `.mjb` at startup and refuses to run on a stale cache
unless `--stale-ok`.

Bake toggles are the ones the current runs train under
(`docs/experiments/2026-09-03_legonly_ab_v2.md` section 1b-4): `PYG_V2 PYG_INIT_BENT
PYG_INIT_MID PYG_MOTOR_MEAS PYG_TN PYG_SAFE_TARGET_CLIP PYG_STUDENT_TEACHER
PYG_ARM_ABD_DEG=15` plus the per-variant selector (AB: `PYG_ANKLE_MODE=AB` +
`PYG_MODEL_TAG`; RP: `PYG_ANKLE_MODE=RP` + `PYG_V2_XML` - the loop branch has no
`PYG_V2_XML` override at all, docs/112 L44).  `--no-init-bent` bakes the HOME keyframe.

## Base fixing

| mode | equality | what is held | what is free |
|---|---|---|---|
| `free` | none | - | everything (gravity only) |
| `fixed` | `base_weld` | base position **and** orientation = the mocap anchor | joints |
| `pivot` | `base_pivot` | the point `pivot_offset` (in the BASE frame) sits at the anchor | base orientation, joints |

Both equalities use `solref (0.002, 1)` / `solimp (0.9999, 0.99999, 1e-5)`.  With MuJoCo's
default softness the 23 kg robot sags 3.7e-4 m off its "fixed" mount and keeps creeping
1.9e-4 m per 2 s; with these numbers it is 2.4e-13 m of drift over 2 s.  Do not relax them.

**Gravity is never modified.**  The ground is toggled by setting the floor geom's
`contype`/`conaffinity` to 0, not by removing weight.

`reset to home / knees_bent` restores the joints **and** the base pose, in every mode.

## Ankle in foot space (AB only)

The AB build's ankle pitch/roll have no motor - they are dragged by two push rods off the
crank pair.  The panel offers pitch/roll sliders anyway, inverted through the `crank_rad`
grid in `pygmalion_locomotion/assets/pygmalion_v2/ankle_rp_envelope.json`.

That grid was solved on `pygmalion_v3_printed_loop`.  **On the v30 build, used as-is, it puts
the foot 0.36 rad (20.7 deg) away from the commanded angle** - the v30 generator re-signed
the crank joint axes.  The bake therefore *fits* the per-leg sign map by commanding the grid
and reading the ankle back (L: `A -> -A`, R: `B -> -B`), which brings the worst probe
residual to 0.008 rad, and records both numbers in the contract.  If a future model makes
the fit fail (`usable: false`), the viewer falls back to the linear inverse from the 2x2
Jacobian the bake measured on that model, and the panel says so.

Crank targets are only ever reached through the PD.  Snapping a crank `qpos` tears the four
`equality/connect` closures open and MuJoCo answers with QACC NaN
(`tools/viewer/mjcf_joint_viewer.py`).  There is no code path here that does it.

## Mirrored axes

On v30 the two legs have opposite joint axes for the knee, the hips, the cranks and the
ankle roll.  `+0.35 rad` is flexion on the left knee and extension on the right.  Every
default, clip window and sign in this tool comes from the contract
(`signed_pose` / `safe_target_clip` / `joint_travel_sign`), never from a regex.  Mirrored
joints carry a second readout, `phys = travel_sign * q`, so the same physical motion reads
the same on both legs.  Note that a range-only mirror test is not enough: `ankle_roll` has
the same symmetric range on both legs and *opposite axes*, so the contract flags
`range_mirrored` and `axis_mirrored` separately.

## Policy (P2)

Two ways to drive the sim from a trained checkpoint. Both express the action exactly the way
`mjlab`'s `JointPositionAction` does: `target = clip(raw_action * action_scale + default_q,
safe_clip_lo, safe_clip_hi)`, with `raw_action` first clamped to +-`clip_actions`.

```bash
# 1. bake a .pt into ONNX + a policy_contract.json + a parity/obs-order fixture
CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py \
    bake policy --pt <run_dir>/model_5200.pt --variant LegOnly-AB

# 2. load it into a running viewer and drive it (or use the "Policy" GUI folder)
curl -s -X POST :8095/policy/load -H 'content-type: application/json' \
     -d '{"name": "LegOnly-AB__<run>__model_5200"}'
curl -s -X POST :8095/mode -H 'content-type: application/json' -d '{"mode": "policy_sim"}'
curl -s -X POST :8095/policy/cmd -H 'content-type: application/json' \
     -d '{"vx": 0.6, "vy": 0.0, "wz": 0.0}'
curl -s :8095/policy/io | jq '.action, .target, .cmd'
```

`ObsBuilder` reads the observation layout (term order, joint subsets, history length) from
the policy's own baked contract - nothing about "45-D" or "gyro first" is hardcoded, so a
future obs config baked with different toggles (e.g. `PYG_STUDENT_TEACHER`) just works.
`check_compatible()` REFUSES to load a policy whose `model_contract_sha` does not match the
live model, or whose default pose differs by more than 1e-4 rad (the default pose is the
action offset, so a mismatch silently biases every target) - a v4-policy-on-v2-model mistake
has already happened once on this project, this makes it a hard error instead.

`POST /obs_source` routes each observation TERM independently between `sim` (works today) and
`real` (501 until the P3 telemetry bridge exists; the switch, the mask string and the
staleness budget in `ObsSourceMux` are already wired so the P3 handoff is "supply real
values", not "invent the plumbing"). `GET/POST /gains` switches between `train` (the
contract's own kp/kd, what the policy was optimised against) and `real` (rejected with 400
unless the contract carries a `real_gains` table - the viewer will not invent hardware
numbers, because a response overlay is meaningless until both sides' gains match).

`smoke_walk.py` is the acceptance check outside pytest (mjlab env import, ~40 s, so it is run
by hand, not on every test invocation): stand at `cmd=0` and compare base height / knee angle
against `mujoco-sim/mjlab/analysis/out/legonly_ab_v2_vel0_vx0.npz` (produced by
`analysis/gait_kinematics_probe.py` from the *same checkpoint*, tolerance 0.02), then walk at
`cmd_vx` and check it does not fall and tracks within ~0.1 m/s.

## Telemetry, bridges, record/replay (P3)

Wire schema (`schema.py`): `Header{v, type, t_ns, seq, src, frame, contract_hash}` plus
`JointState`, `ImuState`, `PolicyIO`, `Status` (all implemented) and `JointTarget` (defined,
documented, never emitted - see docs/121 section 1 and API.md). `to_jsonl`/`from_jsonl` are
the one place a "type" string maps to a pydantic class, shared by the recorder, the replayer,
`/ws/in` and the dummy transmitter. `validate_joint_names` is the one gate that rejects an
unknown joint name, used by `/ws/in` and the tests - never a regex, never a default.

```bash
# receive telemetry into the viewer's own RealState
curl -s :8095/status | jq '.telemetry'          # rx rate, age, seq gaps, clock offset/jitter,
                                                 # contract mismatches, wrap events, range
                                                 # violations, bridge errors, sign sanity
websocat 'ws://127.0.0.1:8095/ws/in'            # then paste a JointState/ImuState JSON line

# HUPHY UDP bridge - standalone process, its own SimCore + RealState (see API.md for how to
# route it into a running viewer instead)
mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py bridge huphy \
    --variant LegOnly-AB --port 9871

# dummy transmitter - sine/script/jsonl -> /ws/in and/or HUPHY-format UDP
mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py bridge dummy \
    --pattern sine --joints L_knee_joint,R_knee_joint --amplitude 0.2 --freq 0.25 \
    --target ws,udp --ws-url ws://127.0.0.1:8095/ws/in --udp-port 9871

# record / replay
curl -s -X POST :8095/record/start -d '{}'; sleep 10; curl -s -X POST :8095/record/stop
curl -s -X POST :8095/replay/load -d '{"path": "<path>"}'
curl -s -X POST :8095/mode -d '{"mode": "file_replay"}'
```

**`real_replay`/`file_replay`** (`sim_core.py`): entering either mode ALWAYS forces the base
to `fixed` first (a kinematically-driven leg on a `free` base with no balance policy is not
"replaying the robot", it is a controlled fall). Every control tick, each actuated joint is
either:

* **direct-drive** (everything except an AB crank - hips/knee, or the RP ankle): snapped to
  the received `qpos` exactly (qvel zeroed), if a value was received THIS tick. With no data
  it gets an ordinary PD hold at its current target (== default right after a reset) - never
  torque-free. An earlier version zeroed torque for every direct-drive joint whenever the
  MODE was a replay mode, not just the ones with fresh data, so an unreceived joint free-fell
  under gravity; caught by `tests/test_record.py`'s differential trajectory tests.
* **PD-tracked** (an AB crank): the received value becomes `self.target`, reached through the
  ordinary PD/T-N torque path - a crank `qpos` is never snapped, or the closed loop tears open
  (module docstring, same NaN failure mode `mjcf_joint_viewer.py` documents).

`file_replay` drives from a loaded `Replayer` (`record.py`) instead of `core.real`; both paths
share the exact same direct/PD split.

`Recorder`/`Replayer` (`record.py`): one plain-JSON header line (`contract_hash`, `variant`,
base mode/height/ground/pivot, gains source, `env_toggles`, the bake's `mjb_sha256`,
`started_utc`), then one `JointState` wire line per published snapshot, append-and-flush
(`gzip.open(..., "wt")`) so a long recording never grows an in-memory list. `Replayer` loads
the whole file (recordings in this project's scope are seconds long, not hours - a genuinely
long recording would need streaming, not implemented) and REFUSES to load a file whose
`contract_hash` does not match the live model (R11) unless the caller passes an explicit
override.

**Sign sanity** (`telemetry.py` `RealState.sign_sanity_update`/`sign_sanity`): whenever ANY
real telemetry has been received, every control tick compares `sign(q_real - default)` vs
`sign(q_sim - default)` per joint over a rolling 2 s window, gated by a 0.05 rad deadband on
both sides. A joint disagreeing more than 50% of the time in that window is flagged `red` in
`Status.telemetry.sign_sanity` and the UI - this runs continuously, in every mode, not only
`real_replay`, so it doubles as a live check of the bridge's own sign convention.

## Tests

```bash
cd tools/pygviewer && CUDA_VISIBLE_DEVICES="" \
    ../../mujoco-sim/mjlab/.venv/bin/python3 -m pytest
```

161 tests, CPU only:

| file | what it pins |
|---|---|
| `test_bake_contract.py` | all six contracts: required fields, sizes, AB action order vs docs/112, gravity, 200/50 Hz, default inside range and clip, **command window >= 0.2 rad each side of default**, no window effectively zero, mirror flags by range AND by axis, travel-sign direction, freshness, sha stability, ankle inverse residual |
| `test_basefix.py` | fixed drift < 1e-6 m per 2 s and pose error < 1e-5 m; pivot point < 1e-4 m with the orientation actually free; ground carries the robot when on and it free-falls when off; keyframe sole penetration; gravity untouched |
| `test_loop_settle.py` | AB loop closure < 0.01 mm at rest and at six foot-space commands; each command lands within 0.05 rad; transmission magnitude within 5 % of `loop_ankle_verify.json`; the two cranks of one leg have opposite axes; RP drives its ankle directly |
| `test_sim_rate.py` | >= 195 Hz physics wall-clock with 0 drops and < 600 MB RSS, AB and RP; snapshot/queue do not accumulate |
| `test_policy_parity.py` | ONNX vs the exported `.pt` agree within 1e-4 on 32 held-out observations; obs/action dims match the contract; a foreign-model or shifted-default-pose contract is REFUSED |
| `test_obs_order.py` | `ObsBuilder` reproduces the env's own 40-step obs trace term-by-term (order, joint subset, history backfill), for every baked policy |
| `test_api_policy.py` | the FastAPI layer actually exposes what P2/P3 implement (not a stale allow-list): `/mode` accepts `policy_sim` only once a policy is loaded, accepts `real_replay` and forces the base `fixed`, 409s `file_replay` without a loaded recording, 501s `policy_shadow` (P4); `/policy/load` 409s a foreign contract and 404s an unknown name; `/policy/cmd` + `/policy/io` round-trip; `/obs_source` 501s `real`; `/gains` 400s `real` with no hardware table |
| `test_schema.py` | `JointState`/`ImuState`/`Status`/`JointTarget`/`PolicyIO` round-trip through `to_jsonl`/`from_jsonl`; required header fields (`t_ns`) and required `PolicyIO` fields raise without them; `from_jsonl` rejects invalid JSON, an empty line and an unknown `type`; `validate_joint_names` flags exactly the unrecognised names |
| `test_bridge_huphy.py` | the joint map has exactly 12 motor rows and starts `side_mapping_verified: false`; an unlisted `(limb, motor)` raises (hard failure, not a guess); the exact synthetic case from the task brief (+30 deg both knees -> sim `L_knee +0.5236`/`R_knee -0.5236` rad, contract `travel_sign` +1/-1, 1e-6); velocity/torque get the same sign treatment; the -1 sentinel nulls a field and warns on 3-in-a-row; `ankle_derived` stays separate from the canonical `q`; diag/CAN fields are ignored, not hard failures; an IMU packet prefers `grav_*` over reconstructing a quaternion (and does NOT treat `grav_z=-1.0`, a real upright reading, as HUPHY's "missing" sentinel - that only applies to `age`/`sensor_dt`) |
| `test_record.py` | record -> replay is byte-for-byte identical, including the header; a foreign `contract_hash` is refused; a 10 s recording does not grow RSS (measured: 0.3 MB on the live process); `real_replay` snaps direct-drive joints to 1e-6 and routes a crank's received value into its PD target exactly; with no telemetry received at all, `real_replay` is numerically identical to staying in `manual` (differential test, 1e-9 - the actual regression this file caught); a left-leg command does not move a right-leg joint (differential, base fixed => no physical coupling path) |

Evidence figure (no OpenGL on this host, so it is matplotlib):
`mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/make_verification_figure.py` ->
`docs/img/pygviewer_p1_verification.png`.

## Verification protocol before trusting a sim/real overlay

Running the tests proves the *simulator* side.  Before any overlay of simulated and measured
data is worth reading, all eight of these must pass (docs/121 section 5; P2-P4 own most of
them):

1. **Zero pose.**  Both sides at the default keyframe: `|dq| < 0.02 rad` per joint and
   `|dg| < 0.05` on the gravity vector.
2. **Per-joint sign sweep.**  Move each physical joint +20 deg, read the canonical value,
   fill the table, and update `side_mapping_verified` in
   `tools/robot_model/motor_sign_convention.json`.  Until this passes the UI shows
   "side mapping: user-asserted, UNVERIFIED".
3. **Ankle FK cross-check.**  25 points: drive the sim forward from the *real* crank angles
   and compare pitch/roll, tolerance 0.02 rad, loop closure < 1 mm.  This is also what
   decides whether HUPHY `ankle_a` is `crank_A` or `crank_B`.
4. **Velocity sanity.**  0.5 Hz sine; finite-differenced position vs reported velocity,
   RMS < 0.3 rad/s, and the sign convention applied to velocity and torque as well as
   position.
5. **Latency.**  Five step commands; estimate the clock offset by cross-correlating the
   command edges; jitter must be < 15 ms or the overlay is greyed out.
6. **Same-target response overlay.**  1 Hz +-20 deg on one joint, sim and robot driven from
   the same script file.  Only meaningful *after* the PD gains have been matched (the panel
   has a train/real gain switch and a diff table).
7. **IMU tilt.**  +-10 deg static tilts agree within 3 deg.
8. **Recording round trip.**  Record, replay, compare bit-for-bit.

## Ports and registration

| port | service |
|---|---|
| 8094 | pygviewer viser scene + panel |
| 8095 | pygviewer API (`/docs`) |

Registered in `tools/dashboard/status.py` (`PORTS`), `tools/dashboard/start_all.sh` and
`tools/dashboard/README.md`.  Logs: `tools/pygviewer/logs/pygviewer.log`.

## Layout

```
tools/pygviewer/
  run.py                     entry point (works without tools/__init__.py)
  README.md  API.md  pytest.ini
  make_verification_figure.py
  pygviewer/
    __init__.py  __main__.py CLI, port pre-emption check, LAN IP
    bake.py                  the ONLY module that imports mjlab/torch
    contract.py              contract accessor + freshness hashes
    sim_core.py              200 Hz physics / 50 Hz control, PD+T-N, base modes, snapshots
    ui.py                    viser panel
    api.py                   FastAPI REST + WS
    schema.py                wire schema v1 (pydantic), including the deferred models
    policy.py                ObsBuilder, OnnxPolicy (default), TorchPolicy (.pt via mjlab,
                             ~11s/~1.3GB, lazy import), ObsSourceMux, action_to_target,
                             check_compatible (contract-sha + default-pose gate)
    _bake_policy.py          `.pt` -> ONNX export + parity/obs-order fixtures (bake-time only)
    telemetry.py             RealState: latest-only receive buffer, rx rate/age/seq-gaps/
                             clock-offset, wrap/range flags, sign sanity (P3)
    record.py                Recorder (streaming jsonl.gz) / Replayer (seek, speed) (P3)
    bridge/
      huphy_udp.py           HUPHY UDP -> canonical JointState/ImuState (P3)
      joint_map_huphy.json   explicit 12-row limb/motor -> sim-joint table (P3)
      dummy_tx.py            sine/script/jsonl -> /ws/in and/or HUPHY-format UDP (P3)
    modes.py                 mode constants + P4 skeletons (ModeMachine, TargetScript);
                             real_replay/file_replay themselves live in sim_core.py
  tests/
```

`bake.py` and `_bake_policy.py` are the only modules that import mjlab/torch at module load
time (bake-time subprocesses). `policy.py` imports them lazily, inside `TorchPolicy.__init__`
only, so `OnnxPolicy` and everything else in the viewer process stays fast to import.
