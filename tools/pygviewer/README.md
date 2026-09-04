# pygviewer - Pygmalion Sim &harr; Real comparison web viewer

One process that owns one MuJoCo model, runs it at the training rates on the CPU, and serves
it two ways: a self-hosted **dashboard** (FastAPI, **:8095**, `GET /` or `GET /dash` - the
default entry point) that embeds the 3D scene, and the underlying viser scene + debug panel
directly (**:8094**). Built so that a number read here is comparable to the same number read
in training - not merely similar.

**Open `http://192.168.20.177:8095/` - that is the whole UI now.** `:8094` still renders (it's
the iframe the dashboard embeds, and its own control panel still works standalone for
debugging), it is just not where you start.

Status: **P0 (bake + sim loop + scene + /status), P1 (manual joint control, base fixing,
ground toggle, plots), P2 (ONNX/`.pt` policy, obs builder, PD gain source, velocity
command, per-term obs-source switch), P3 (wire schema, `/ws/in`, HUPHY UDP bridge, dummy
transmitter, record/replay, `real_replay`/`file_replay` drive, Telemetry panel), P4
(`policy_shadow` per-term obs mux, the same-target-sequence script player, `compare.py`
offline overlay, the gains diff table, `protocol.py`) and **UI v2 (the dashboard above -
layout B, docs/121 section 10) are all implemented.** See `docs/121_pygviewer_design.md`
section 6 (phase numbers) and section 10 (UI v2) for the verification detail.

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

Options: `--base free|fixed|pivot|string` (default `fixed` - nothing balances the robot in P1,
so a free base topples in about 2 s), `--string-z-set METERS` and `--string-follow-xy`
(`--base string` only), `--keyframe home|knees_bent`, `--stale-ok`,
`--no-api`, `--cache DIR`.  The process refuses to start if 8094 or 8095 is already taken.

LAN: **`http://192.168.20.177:8095/`** (the dashboard - start here), viser directly at
`http://192.168.20.177:8094`, OpenAPI at `http://192.168.20.177:8095/docs`.

## Dashboard (UI v2, layout B)

A single page (`pygviewer/static/dashboard.{html,js}`, no build step, no CDN - three.js
r150 and uPlot 1.6.30 are vendored under `pygviewer/static/vendor/` because this LAN has no
internet access) served by the same FastAPI process. 3-column grid: a 38px top bar
(variant/mode/base/warning badges/rates), a 250px left column of vertical tabs (**Model**:
variant - read-only, this process owns one baked model for its life; contract sha; reload.
**Base link**: free/fixed/pivot/string, height or `z_set` depending on mode, pivot/hook
offset, ground, string tension, home/knees_bent reset. **Telemetry/Record**: rx rate/age/
clock offset/jitter, the `side_mapping_verified` UNVERIFIED banner, record/replay. **Script**:
run/stop the two sample target-q scripts. **Status**: rates/RSS/warnings), the viser scene as
a center iframe, and a 340px right column of tabs (**Control**: a Joints&harr;Policy
mutually-exclusive toggle - Joints has one slider+number per actuated joint (range = safe_
clip, a deg/rad display toggle, a mirrored joint's `travel_sign&times;q` physical angle
alongside its raw q, AB foot-space pitch/roll sliders, a disabled "TX (HW)" checkbox
placeholder for the docs/123 hardware-transmit work); Policy has the policy picker (its
"load" button performs `load -> cmd(0,0,0) -> mode=policy_sim`, cmd sliders, mode/shadow-
follow, per-term obs source). **Gains**: kp/kd table (edits POST immediately), train/real/
custom presets. **Obs**: the 45-D observation as bar groups by term, colour-coded by
effective source, plus a three.js body-frame/gravity/gyro widget). A 320px plot strip spans
the left+center columns: up to three togglable rows (q+target, tau, qd), one uPlot panel per
joint KIND with L/R overlaid, a received real value drawn translucent on the same time grid,
a 5/10/20/60s window and click-to-expand.

Data path: one WebSocket (`/ws/out?hz=50&types=JointState,Status,PolicyIO`) for everything at
control rate, a 250 ms poll of `/snapshot` (plus `/gains`/`/presets`/`/policy/list` only while
their tab is open) for slower state - no new wire types, `JointState.src` and `PolicyIO`'s
existing fields already carry what the dashboard needs.

**TX (hardware transmit) - STUB.** The Telemetry/Record tab also has a TX section: host:port,
a two-stage arm (an "activate" checkbox, then a real `POST /tx/arm` - refused whenever the
sim mode is not `manual`, since **policy output must never be transmittable**), a keyboard
dead-man (hold Space to send, release to stop), and one enable checkbox per motor. This is
built against `pygviewer/tx.py`'s `TxState`, a real safety state machine that **transmits
nothing anywhere** - `bridge/tx_client.py` (the actual 50 Hz UDP sender another coder is
building per `docs/123_pygviewer_tx_design.md`) had not landed when this was written. See
`GET /tx/status`'s own `note` field, always present, for the current stub boundary.

Verified live by hand (no Chrome extension reachable on this host - tried it, confirmed
unavailable): `curl` for the page/static assets/preset round trip/policy-load sequence, a
Python `websockets` client against `/ws/out` to confirm the additive `src="real"` JointState
frame (see API.md) actually appears once `bridge dummy --imu` sends telemetry. Actual browser
rendering (CSS layout, uPlot/three.js visual correctness) is **not** verified - a stated gap,
docs/121 section 10.

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

The bake adds these things to the scene spec and edits **no XML**:
`pyg_anchor` (mocap body, no geom - a geom would change the total mass, which the bake
asserts is unchanged), `base_weld` (equality/weld, inactive) and `base_pivot`
(equality/connect, inactive) for `fixed`/`pivot`; and, for `string`, two sites
(`pyg_string_anchor` on the anchor body, `pyg_string_hook` on `base_link`) plus the
`pyg_string` spatial tendon between them, baked LIMITED=false (inert until `sim_core.py`
turns it on for that one mode).  It then asserts the compiled model matches the env on `nu`,
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

| mode | constraint | what is held | what is free |
|---|---|---|---|
| `free` | none | - | everything (gravity only) |
| `fixed` | `base_weld` (equality/weld) | base position **and** orientation = the mocap anchor | joints |
| `pivot` | `base_pivot` (equality/connect) | the point `pivot_offset` (in the BASE frame) sits at the anchor | base orientation, joints |
| `string` | `pyg_string` (spatial tendon, LIMITED) | base never sinks below `z_set` (a one-directional catch, not a mount) | orientation, horizontal position, and vertical position ABOVE `z_set` |

`fixed`/`pivot` use `solref (0.002, 1)` / `solimp (0.9999, 0.99999, 1e-5)`.  With MuJoCo's
default softness the 23 kg robot sags 3.7e-4 m off its "fixed" mount and keeps creeping
1.9e-4 m per 2 s; with these numbers it is 2.4e-13 m of drift over 2 s.  Do not relax them.

**`string`** is a real safety-harness tether, not a mount: a 2-site spatial tendon between
the mocap anchor and a `pyg_string_hook` site on `base_link`, tendon-LIMITED to length
`[0, L0]` (`L0 = 1.0 m`, baked). The mocap anchor's world Z is always `z_set + L0` and its
(x, y) is either fixed at wherever the base was when the mode was entered (default - the
base can swing, like a real string) or tracks the base's own (x, y) every tick when
`follow_xy` is set (a vertical rail - no swing). Below `z_set` the tendon is taut and pulls
the base back up; above it, it is slack and the base is exactly as free as in `free` mode. A
MuJoCo tendon **limit** is a one-directional (rope) constraint - it can only be reached from
one side, unlike a spring - which is exactly a catch, never a mount. `solref_limit (0.02, 1)`
is deliberately 10x softer than the weld/pivot's `(0.002, 1)`: a rigid catch on a 23 kg
falling body is a jolt no real harness gives; the softer setting still lands within 2e-4 m of
`z_set` with zero steady-state error (`tools/pygviewer/tests/test_string_mode.py`). Tension is
read straight off the tendon-limit constraint's Lagrange multiplier (`d.efc_force`), not
computed - a controlled vertical drop of the 23.63 kg LegOnly model settles with a measured
tension equal to its own weight (231.8 N) to within measurement noise. `hook_offset` moves the
attachment point in the BASE frame, same convention as `pivot_offset` (the panel's `pivot/hook
offset x/y/z` fields drive both).

**Gravity is never modified.**  The ground is toggled by setting the floor geom's
`contype`/`conaffinity` to 0, not by removing weight.

`reset to home / knees_bent` restores the joints **and** the base pose, in every mode.

**Scenario: run a policy while hanging from the harness.**  `string` catches a fall without
constraining anything else, so it is meant to be left on WHILE a policy runs (unlike
`fixed`/`pivot`, which would fight the policy's own balance): `POST /base
{"mode":"string","z_set":<standing height - 0.15>}`, then `POST /policy/load` and `POST
/mode {"mode":"policy_sim"}` as usual. A policy that is upright and walking never feels the
tether (it stays slack, `GET /status` shows `string.taut: false`); if it falls, the tether
catches it at `z_set` instead of the floor - the same purpose a real overhead test harness
serves during early hardware bring-up.

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

## Comparison mode (P4)

Four scenarios covering the pieces added in P4 - `policy_shadow` (per-term obs source mux),
the script player, `compare.py`, and `protocol.py`. All four assume a running viewer
(`run.py --variant LegOnly-AB --port 8094 --api-port 8095`) unless noted.

**1. Run a target-q script and record it.**

```bash
curl -s -X POST :8095/record/start -d '{"path": "/tmp/sim_run.jsonl.gz"}'
curl -s -X POST :8095/script/run -d '{"path": "tools/pygviewer/scripts/step_knee_5x10deg.json"}'
sleep 6.5   # the script's own duration + a little margin
curl -s -X POST :8095/record/stop
```

**2. Compare two recordings offline.**

```bash
mujoco-sim/mjlab/.venv/bin/python3 -m pygviewer.compare \
    --sim /tmp/sim_run.jsonl.gz --real /tmp/real_run.jsonl.gz \
    --joints L_knee_joint --offset-dt 0.005
# -> R9 condition-difference warnings, an R5 clock-offset estimate (ms, +jitter), one PNG
#    per joint under docs/img/, and an R11 refusal if the two contract_hash values differ
#    (pass --i-know to override deliberately).
```

**3. `policy_shadow` with a dummy real IMU (no hardware, no transmit path).**

```bash
curl -s -X POST :8095/policy/load -d '{"name": "<baked-policy-name>"}'
curl -s -X POST :8095/mode -d '{"mode": "policy_shadow"}'
curl -s -X POST :8095/obs_source -d '{"sources": {"base_ang_vel": "real", "projected_gravity": "real"}}'
mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py bridge dummy \
    --variant LegOnly-AB --pattern sine --imu --target ws --seconds 5
curl -s :8095/policy/io | jq '.obs_sources'   # requested vs a live /status shows the EFFECTIVE
                                               # mask + any staleness fallback in shadow_warnings
# add --shadow-follow on the viewer's own command line (or POST /policy/shadow_follow
# {"enabled": true}) to let the shadow action step the LOCAL sim - it never reaches a robot.
```

**4. Run the automated half of the 8-step verification protocol.**

```bash
mujoco-sim/mjlab/.venv/bin/python3 -m pygviewer.protocol --variant LegOnly-AB
# steps 1/4/5/8 run against synthetic data and PASS/FAIL; steps 2/3/6/7 print the exact
# hardware procedure and pass criterion, tagged MANUAL - never faked.
```

`policy_shadow` details (`policy.py` `ObsBuilder.build_shadow`, `sim_core.py` `_policy_tick`):
each of the 5 obs terms (`base_ang_vel`, `projected_gravity`, `motor_pos_history`, `actions`,
`command`) is independently `sim` or `real`. `real` for the two IMU-backed terms comes from
`RealState.imu` (age-gated on `ImuState`'s own receipt time); `real` for the q-history term
comes from a SEPARATE rolling buffer (`SimCore.real_q_hist`) built from `RealState`'s joint
snapshot every control tick - never interleaved with the sim q-history within one term's
window; `real` for `actions`/`command` comes from a `PolicyIO` message received over `/ws/in`
(a real host's own self-reported obs/action/cmd - the only wire concept of "what the robot
was actually commanded"). Any term that asks for `real` but has nothing fresh (older than
`max_age_s`, default 0.1 s) falls back to `sim` for that tick only and is reported in
`shadow_warnings`/`obs_sources_effective` - never silently used stale. The action this
produces is display/plot/record only unless `--shadow-follow` is set, and even then it only
ever steps THIS process's own sim - there is no code path anywhere in this codebase that
sends it to a robot (`modes.SHADOW_MAY_TRANSMIT = False`; enforced structurally, not by
convention - see `tests/test_policy_shadow.py::test_shadow_action_has_no_transmit_path`).

**Script player** (`modes.TargetScript`, `SimCore.run_script`/`stop_script`): a
`scripts/*.json` file (`{joint_names, rows: [[t_s, q...], ...], loop}`) is linearly
interpolated by elapsed sim time and played through `manual` mode via `POST /script/run
{path, run_id}` / `POST /script/stop`. Refuses to start over a policy/replay mode or a joint
this variant does not actuate. Two samples ship in `tools/pygviewer/scripts/`:
`sine_hips_knees_1hz_20deg.json` (1 Hz, 20 deg on both hip_pitch and both knee joints, 3 s) and
`step_knee_5x10deg.json` (5 steps of 10 deg on `L_knee_joint`, 1 s dwell each - built for
protocol step 5's sharp edges). Every subsequent `JointState` (and a recording made while it
plays) carries the script's `run_id` in its `Header`, so `compare.py` can later match a sim
run against a robot run of the SAME file.

**Gains diff table (R7)**: `GET /gains` / the UI's Gains folder show the contract's `train`
kp/kd for every joint plus its motor family (`RS03`/`RS04`, from the contract's
`joint_family`); once any `JointState` telemetry carries a `gains` field, the received real
kp/kd and a ratio appear alongside, with anything off by more than 5% flagged in red - a
response overlay is not worth trusting until this matches.

## Tests

```bash
cd tools/pygviewer && CUDA_VISIBLE_DEVICES="" \
    ../../mujoco-sim/mjlab/.venv/bin/python3 -m pytest
```

244 tests added by the "UI v2 dashboard" work below (231 in `test_dashboard.py`/
`test_target_independence.py`, 13 in `test_dashboard_tx.py`), CPU only. The suite's total
count is a moving target right now - another coder is concurrently landing
`tx_map.py`/`JointTarget` work (`test_tx_map.py`/`test_schema_tx.py`, not described in this
file) on the same tree; run `pytest --collect-only -q` for the current total rather than
trusting a number written here:

| file | what it pins |
|---|---|
| `test_bake_contract.py` | all six contracts: required fields (incl. `string_rig`), sizes, AB action order vs docs/112, gravity, 200/50 Hz, default inside range and clip, **command window >= 0.2 rad each side of default**, no window effectively zero, mirror flags by range AND by axis, travel-sign direction, freshness, sha stability, ankle inverse residual, string tendon+sites present and distinct |
| `test_basefix.py` | fixed drift < 1e-6 m per 2 s and pose error < 1e-5 m; pivot point < 1e-4 m with the orientation actually free; ground carries the robot when on and it free-falls when off; keyframe sole penetration; gravity untouched |
| `test_string_mode.py` | a 23.63 kg free-fall from 0.9 m is caught by `z_set=0.6` (settles within 0.02 m, tension 231.8 N +/-10% of the robot's own weight); starts slack (0 N) while standing, goes taut and holds `base z >= z_set - 0.02` once a PD-only (no policy) topple reaches it; string -> fixed -> free -> string round trip leaves no NaN and no stale `eq_active`/`tendon_limited`; `hook_offset` moves the compiled model's `site_pos`; `follow_xy` keeps the anchor over a horizontally-offset base; an isolated single-tendon rig (no bake) settles at `z_set` with tension = weight to 1e-4 relative |
| `test_loop_settle.py` | AB loop closure < 0.01 mm at rest and at six foot-space commands; each command lands within 0.05 rad; transmission magnitude within 5 % of `loop_ankle_verify.json`; the two cranks of one leg have opposite axes; RP drives its ankle directly |
| `test_sim_rate.py` | >= 195 Hz physics wall-clock with 0 drops and < 600 MB RSS, AB and RP; snapshot/queue do not accumulate |
| `test_policy_parity.py` | ONNX vs the exported `.pt` agree within 1e-4 on 32 held-out observations; obs/action dims match the contract; a foreign-model or shifted-default-pose contract is REFUSED |
| `test_obs_order.py` | `ObsBuilder` reproduces the env's own 40-step obs trace term-by-term (order, joint subset, history backfill), for every baked policy |
| `test_api_policy.py` | the FastAPI layer actually exposes what P2-P4 implement (not a stale allow-list): `/mode` accepts `policy_sim`/`policy_shadow` only once a policy is loaded, accepts `real_replay` and forces the base `fixed`, 409s `file_replay` without a loaded recording; `/policy/load` 409s a foreign contract and 404s an unknown name; `/policy/cmd` + `/policy/io` round-trip; `/obs_source` accepts `real` (P4); `/gains` 400s `real` with no hardware table |
| `test_schema.py` | `JointState`/`ImuState`/`Status`/`JointTarget`/`PolicyIO` round-trip through `to_jsonl`/`from_jsonl`; required header fields (`t_ns`) and required `PolicyIO` fields raise without them; `from_jsonl` rejects invalid JSON, an empty line and an unknown `type`; `validate_joint_names` flags exactly the unrecognised names |
| `test_bridge_huphy.py` | the joint map has exactly 12 motor rows and starts `side_mapping_verified: false`; an unlisted `(limb, motor)` raises (hard failure, not a guess); the exact synthetic case from the task brief (+30 deg both knees -> sim `L_knee +0.5236`/`R_knee -0.5236` rad, contract `travel_sign` +1/-1, 1e-6); velocity/torque get the same sign treatment; the -1 sentinel nulls a field and warns on 3-in-a-row; `ankle_derived` stays separate from the canonical `q`; diag/CAN fields are ignored, not hard failures; an IMU packet prefers `grav_*` over reconstructing a quaternion (and does NOT treat `grav_z=-1.0`, a real upright reading, as HUPHY's "missing" sentinel - that only applies to `age`/`sensor_dt`) |
| `test_record.py` | record -> replay is byte-for-byte identical, including the header (also exercised standalone as protocol step 8); a foreign `contract_hash` is refused; a 10 s recording does not grow RSS (measured: 0.3 MB on the live process); `real_replay` snaps direct-drive joints to 1e-6 and routes a crank's received value into its PD target exactly; with no telemetry received at all, `real_replay` is numerically identical to staying in `manual` (differential test, 1e-9 - the actual regression this file caught); a left-leg command does not move a right-leg joint (differential, base fixed => no physical coupling path) |
| `test_policy_shadow.py` (P4) | the per-term obs mux: defaults to all-sim; falls back to sim (with a `shadow_warnings` entry) when `real` is requested but missing or older than `max_age_s`; a fresh real IMU correctly overwrites `base_ang_vel`/`projected_gravity` in the built observation; a `PolicyIO` message correctly feeds `actions`/`command`; `shadow_follow=False` never moves `self.target`, `True` does and only locally; a 10 deg dummy IMU tilt changes the policy's raw action by mean 0.270 rad (regression floor 0.02 rad); no transmit path exists structurally |
| `test_script_player.py` (P4) | `TargetScript` interpolation/looping/end-clamping; the two sample scripts only name actuated joints; `run_script` switches to `manual`, tags `run_id`, refuses over a policy/replay mode or an unknown joint, and clears its own state on natural completion; the two REST endpoints |
| `test_compare.py` (P4) | R11 contract-hash refusal and `--i-know` override; R9 condition-difference warning; the clock-offset estimator recovers a synthetic 30 ms injected delay to within 15 ms; PNG output; an unknown `--joints` entry is skipped, not fatal |
| `test_gains_diff.py` (P4/R7) | no `real_*` columns before any telemetry; a deliberately mismatched kp is flagged (kd is not); gains within 5% are not flagged |
| `test_protocol.py` (P4) | the 8-step runner returns all steps in order; the 4 automated steps (1/4/5/8) PASS; the 4 manual steps (2/3/6/7) never claim PASS; a deliberately tightened budget fails step 1 on demand; the CLI |
| `test_arm_abduction.py` | both arms flare OUTWARD (never one abducted/one adducted) at the welded default pose, on every baked variant that has arms - the physical acceptance check for the `pygmalion_constants.get_spec()` sign bug fixed 09-04 |
| `test_target_independence.py` | 2026-09-04 user bug report ("L/R move together"): with base=fixed+ground=off, commanding any one of the 12 actuated joints (or one AB foot-space `/ankle` side) never changes another joint's target (bit-exact) or the OPPOSITE LEG's q beyond 0.01 rad - same-leg q coupling (crank_A/B's shared closed loop, hip/knee inertia) is deliberately excluded, see the file's own docstring for why |
| `test_dashboard.py` (UI v2) | `GET /`/`/dash` and the four vendored static assets serve; `Status.imu`/`side_mapping_verified`; the full `/presets`+`/presets/apply` surface (save/list/apply/reserved-name+unknown-joint rejection/404); `GainsIn.clear_overrides`; the additive `src="real"` JointState frame on `/ws/out` is absent until telemetry arrives, then present; the Policy tab's `load -> cmd(0,0,0) -> mode=policy_sim` sequence actually lands that state; the Joints tab's deg/rad conversion round-trips (checked by extracting the literal formula from the shipped `dashboard.js` source, since there is no JS runtime on this host to execute it) |
| `test_dashboard_tx.py` (UI v2 TX STUB) | `TxState`: arm refused outside `manual` mode; `send` drops any joint not explicitly enabled; the 0.3 s dead-man timeout stops `send` (both a fast clock-manipulation test and a real `time.sleep` one); a heartbeat keeps it alive; `check_mode_gate` auto-disarms the moment the mode leaves `manual`; plus two API-layer tests (shared `SimCore`) proving `/tx/*` is actually wired to `TxState` and that one `step_n(decimation)` tick disarms it when `core.mode` changes directly, bypassing `POST /mode` entirely |

Evidence figure (no OpenGL on this host, so it is matplotlib):
`mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/make_verification_figure.py` ->
`docs/img/pygviewer_p1_verification.png`.

## Verification protocol before trusting a sim/real overlay

Running the tests proves the *simulator* side.  Before any overlay of simulated and measured
data is worth reading, all eight of these must pass (docs/121 section 5).  `protocol.py`
(P4) runs steps 1/4/5/8 automatically against synthetic data; steps 2/3/6/7 need the real
robot or a human and are never faked - `protocol.py` prints their procedure instead:

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
    tx.py                    (UI v2 TX STUB) TxState: arm/disarm/heartbeat/per-motor-enable/
                             send - transmits nothing, see its own module docstring
    bridge/
      huphy_udp.py           HUPHY UDP -> canonical JointState/ImuState (P3)
      joint_map_huphy.json   explicit 12-row limb/motor -> sim-joint table (P3)
      dummy_tx.py            sine/script/jsonl -> /ws/in and/or HUPHY-format UDP (P3)
    modes.py                 mode reference table + TargetScript (P4, the script player);
                             real_replay/file_replay/policy_shadow themselves live in
                             sim_core.py, dispatched on the plain string SimCore.mode
    compare.py               (P4) offline sim<->real overlay: R5 clock-offset estimate,
                             R9 condition warnings, R11 contract-hash refusal, PNGs to
                             docs/img/
    protocol.py              (P4) the 8-step verification protocol, runnable: steps
                             1/4/5/8 automated against synthetic data, 2/3/6/7 print the
                             hardware procedure and are tagged MANUAL
    static/                  (UI v2) dashboard.html + dashboard.js (no build step) served at
                             GET / and GET /dash; vendor/ has the local three.js/uPlot bundles
  presets/                   (UI v2) saved custom gains presets (*.json, {name, gains}),
                             GET/POST /presets + POST /presets/apply - train/real are built in
  scripts/                   (P4) sample POST /script/run target-q sequences
  tests/
```

`bake.py` and `_bake_policy.py` are the only modules that import mjlab/torch at module load
time (bake-time subprocesses). `policy.py` imports them lazily, inside `TorchPolicy.__init__`
only, so `OnnxPolicy` and everything else in the viewer process stays fast to import.
