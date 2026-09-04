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

**Restarting safely - always kill any existing instance first.** Two live instances at once
has actually happened here (2026-09-04): a second `run.py` started while a first one's own
API thread had died without killing the process, so the dashboard (:8095, re-bound by the
new process) and the viser iframe (:8094, still owned by the old one) silently pointed at
TWO DIFFERENT `SimCore`s - symptom: "I loaded a policy but nothing moves". `run.py` now
refuses a second live instance via a pidfile (`tools/pygviewer/logs/pygviewer.pid`, checked
by PID liveness, not just the port_free() socket check above - a crashed process's stale
pidfile is reclaimed automatically) - but the SAFE restart sequence is still to kill first:

**Do not use a bare `pkill -f 'tools/pygviewer/run.py'`** - docs/121 section 9 (2026-09-04
12:45 entry) already caught this failing twice (exit 144): `pkill -f`/`pgrep -f` match against
a process's FULL command line, and the shell wrapper running your own kill command can ALSO
contain that same literal substring (e.g. inside a quoted argument), so a plain substring
pattern can kill the very shell you typed it into. Filter by the actual executable name
(`comm`) instead - only a real `python3` process is a candidate, never a `bash`/`sh` wrapper:

```bash
kill_pygviewer() {
  for pid in $(pgrep -f 'tools/pygviewer/run.py'); do
    case "$(ps -o comm= -p "$pid" 2>/dev/null)" in
      python3*) kill "$pid" ;;
    esac
  done
}
kill_pygviewer
sleep 1
kill_pygviewer   # second pass - a process mid-shutdown on the first pass still needs this

CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py \
    --variant LegOnly-AB --port 8094 --api-port 8095 \
    > tools/pygviewer/logs/pygviewer.log 2>&1 &
```

If `run.py` refuses to start with "pygviewer is already running as pid N", that pid really is
still alive (the pidfile check would have reclaimed a stale one on its own) - `kill <pid>` (or
repeat the loop above) and retry; do not delete the pidfile by hand as a shortcut.

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
alongside its raw q, AB foot-space pitch/roll sliders, a disabled "TX (HW)" checkbox that
read-only mirrors the Telemetry tab's real TX enable list); Policy has a policy picker
(ellipsis-truncated select with a refresh button, since baked names can be long) plus a
full-width "Load & Run" button (`load -> cmd(0,0,0) -> mode=policy_sim`; a failed load
shows the server's 400/404/409 reason as persistent red text, not just a toast that
disappears), a `loaded: <name> (onnx|pt)`/`none` status line, a Run/Stop(idle) toggle +
Unload (both disabled until something is loaded), a collapsed "load by file path" fallback,
cmd sliders, mode/shadow-follow, per-term obs source). **Gains**: kp/kd table (edits POST immediately), train/real/
custom presets. **Obs**: the 45-D observation as bar groups by term, colour-coded by
effective source, plus a three.js body-frame/gravity/gyro widget). A 320px plot strip spans
the left+center columns: up to three togglable rows (q+target, tau, qd), one uPlot panel per
joint KIND with L/R overlaid, a received real value drawn translucent on the same time grid,
a 5/10/20/60s window and click-to-expand.

Data path: one WebSocket (`/ws/out?hz=50&types=JointState,Status,PolicyIO`) for everything at
control rate, a 250 ms poll of `/snapshot` (plus `/gains`/`/presets`/`/policy/list` only while
their tab is open) for slower state - no new wire types, `JointState.src` and `PolicyIO`'s
existing fields already carry what the dashboard needs.

**TX (hardware transmit) - WIRED, docs/123 section 6 (2026-09-04).** The Telemetry/Record tab's
TX section drives a real `bridge.tx_client.TxClient` end to end: `POST /tx/config` (host, port,
per-motor `enable` list, kp_max/kd_max/ttl_ms) builds it; `POST /tx/enable` turns the panel on
(stage 1); `POST /tx/arm` arms it (stage 2, refused with a 409 + reason whenever the sim mode
is not `manual` - **policy output must never be transmittable**, enforced both at arm time and
every control tick by `SimCore._on_control_tick` -> `TxState.check_mode_gate`). Only the
CURRENT manual/script target (`SimCore.target`) is ever sent - a policy's action lives in a
different attribute entirely and is never read by the TX code path.

**Sync-before-arm gate (R12, docs/123 section 10.2, 2026-09-04).** `POST /tx/arm` ALSO refuses
(409) until `POST /sync_from_real` (dashboard button "0. sync from hardware", above "1.
configure") has pulled every TX-enabled joint's manual target from live real telemetry, and
that sync is still valid. This exists because of a real near-miss on the bench: the real
L_knee sat at 27.8&deg; while the Joints tab's leftover manual target showed 66.4&deg; - arming
at that moment would have sent that 38.6&deg; jump as the very first packet. A sync is
invalidated by telemetry for a synced joint going stale (>1s), a `POST /tx/config` reconfigure,
the sim mode leaving `manual`, or a model contract change; moving the manual target yourself
AFTER syncing is never blocked (that is a deliberate operator command, shown only as "drift" in
`GET /tx/status`) - what IS blocked is the real joint itself drifting more than 5&deg; away from
its RAW real-at-sync reading (never the clipped/applied target - see the 2026-09-04 bench fix
below) while its manual target sits untouched. While real telemetry is connected but not yet
synced, the Joints tab's sliders/inputs and the "3. ARM" button are disabled in the dashboard
(never for a pure-sim session with no real telemetry at all). See `pygviewer/hw_sync.py`'s
module docstring for the full state machine and `tests/test_sync_from_real.py` for the ten
covered scenarios.

**2026-09-04 bench fix: clip-vs-drift and phantom-zero motors (docs/123 section 10.2b).** The
first live-bench run of this gate found it structurally unarmable: the drift check above
compared live telemetry against the CLIPPED/applied target, so any joint sitting outside the
model's `safe_clip` range (the bench's actual default pose - real L_knee_joint at 171.2&deg;
against a model ceiling of 114&deg;) permanently read as "moved 57&deg; since sync" even
standing perfectly still. Fixed by comparing real-vs-real only (`HwSyncState.real_at_sync`,
the RAW value at sync time, never the clipped one); the clip gap itself is now reported
separately and non-blockingly via `HwSyncState.clip_warnings()` - `GET /tx/status`'s and a
successful `POST /tx/arm`'s `sync.clip_warnings` name the real position, the model range, and
the exact travel arming will cause (e.g. `L_knee_joint: real 171.2 (deg) is outside the model
range [6.0, 114.0] (deg); arming will move it to 114.0 (deg) (57.2 (deg) of travel)`). A second
bug from the same session: HUPHY fills a physically disconnected motor's slot with `q=0.0`
every frame, indistinguishable from a real reading by value alone - `POST /sync_from_real` now
excludes a joint whose `GET /health` diag verdict is `dead` (via ack/miss/motor_age_ms) even
while its position field stays fresh, skipping it as `"no real data (motor not responding)"`
rather than syncing a false zero target.

On top of arm/disarm sits a THIRD, independent keyboard dead-man: holding **Space** (not while typing in a text field)
calls `POST /tx/heartbeat` every ~100ms; letting go does **not** disarm - the dashboard just
stops sending new packets ("hold", not "stop"), and the robot's own age-based dead-man
(`bridge.remote_target`, 0.2s) takes it from there, exactly as if the cable had been unplugged.
`GET /tx/status` reports `armed`/`sending`/`last_seq`/`rate_hz`/`deadman_age_s`/
`rejected_count`/`arm_token` (a per-process shared secret to copy verbatim into the receiver's
own `--arm-token`) live, and the plot strip's "sent target" series is the client's actual
clamped, slewed values (`TxClient.last_sent`), not a display echo of the slider.

**Bench experiment procedure** (one motor, loopback or a real receiver on the LAN):

```bash
# 1. terminal A - a receiver. Loopback/no hardware: the physics-modelled dummy receiver.
#    (For real hardware, use bridge/huphy_remote_motion.py instead - see deploy/README_robot_host.md.)
cd tools/pygviewer
../../mujoco-sim/mjlab/.venv/bin/python3 -m pygviewer.bridge.dummy_rx \
    --variant LegOnly-AB --listen 0.0.0.0:9872 --telemetry 127.0.0.1:9870 \
    --arm-token <copy from GET /tx/status's "arm_token"> --enable L_knee_joint

# 2. terminal B - the viewer itself, as usual (see "Quick start" above).

# 3. in the dashboard (:8095, Telemetry/Record tab, TX section):
#    a. set host=127.0.0.1 port=9872, tick the L_knee_joint enable box, click "1. configure"
#    b. tick "2. activate TX panel"
#    c. click "3. ARM" (only enabled while mode=manual - Joints tab or a running script)
#    d. move the L_knee_joint slider (Joints tab), then hold Space over the page - the badge
#       reads "SENDING" while held, "ARMED (hold Space)" the instant it is released (still
#       armed - not disarmed)
# 4. verify: terminal A's own telemetry (or a HUPHY-format UDP reader on :9870) shows
#    left_leg/knee/pos tracking left_leg/knee/tgt within the wire's own rounding (~0.01 deg) -
#    "left_leg" is HUPHY biped's own Leg.id, not the pre-biped fork's bare "left"
#    (docs/121 section 12); release Space and confirm the receiver's own log crosses
#    hold -> returning -> default over hold_s + return_s (3s + 2s by default) after 0.2s of
#    silence.
```

`tests/test_tx_wiring.py` automates the same sequence over real loopback UDP against
`bridge.dummy_rx.DummyRx` (no dashboard/browser needed) - see its own docstring for what each
tier covers, and the numbers below for what it actually measured.

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
| `test_bridge_huphy.py` | the joint map has exactly 12 motor rows and starts `side_mapping_verified: false`; an unlisted `(limb, motor)` raises (hard failure, not a guess); the exact synthetic case from the task brief (+30 deg both knees -> sim `L_knee +0.5236`/`R_knee -0.5236` rad, contract `travel_sign` +1/-1, 1e-6); velocity/torque get the same sign treatment; the -1 sentinel nulls a field and warns on 3-in-a-row; `ankle_derived` stays separate from the canonical `q`; diag/CAN fields are ignored, not hard failures; an IMU packet prefers `grav_*` over reconstructing a quaternion (and does NOT treat `grav_z=-1.0`, a real upright reading, as HUPHY's "missing" sentinel - that only applies to `age`/`sensor_dt`); an optional per-row `rom_deg` clips `pos`/`tgt` before conversion and counts the clamp when set (2026-09-04); the shipped maps' `rom_deg: null` everywhere is byte-identical to the pre-`rom_deg` path |
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
| `test_rom_clip.py` (ROM clip task, 2026-09-04) | `real_replay`'s receive-side hard-range clip: a direct-drive joint (`L_knee`) 5 rad past its range lands in qpos clipped, finite, counted, with the raw telemetry value untouched; a NaN sample produces a bit-identical trajectory to no telemetry at all (differential); an AB crank pair scaled past its hard range stays inside the soft `safe_clip` and the loop stays closed; `POST /target` out-of-range vs in-range report `requested`/`applied` correctly; `POST /target` with a real NaN/Infinity over the wire (built by hand - httpx's own `json=` refuses to send one) is rejected 422, not 500 - all 7 share one module-scoped `SimCore`/`TestClient` after a per-test-instantiation version was measured to push `test_sim_rate.py`'s RSS budget over the cap in the full suite |
| `test_violations.py` (A2, 2026-09-04) | pure `ViolationLog` unit tests (ring cap, cumulative counts surviving eviction, rate-limit suppresses ring entries but not counts, `clear()` never lets `seq` go backwards, `side` filtering); `RealState.ingest_joint_state` drops a `side="recv"` record (value/limit/`over_by`/`src`) on an out-of-range `q` and a `side="recv_torque"` record on a `tau_est` over the contract's effort limit, while the pre-existing `range_violations` counter stays intact; `SimCore._tn_clamp` drops a `side="sim_actuator"` record (`tau_raw`/`tau_clamped`) when a torque this large no motor could produce is clamped, rate-limited to one ring entry per 100 ms per joint (cumulative count still bumps every call); `GET /violations` (empty/`side=`-filtered/`age_s`) and `POST /violations/clear`; a NaN `POST /target` is both 422-rejected AND recorded as a `side="send"` violation naming the joint; `Status.telemetry.violations` carries the summary shape only, never the ring; `GET /tx/status` carries `violations_count`; A1's `replay_clamp` counter and this log agree on "something happened" without either silently staying quiet |
| `test_health.py` (motor health task, 2026-09-04) | fresh HUPHY DIAG fields (temp/age/ack/miss) verdict `ok`; a fake-clock unit test (no real `time.sleep`) proves 1.5 s of silence for one joint verdicts `dead` while a never-touched joint stays `dead` with `age_s: null`; `ack=0` alone is `warn` (not `dead`); `miss>=1` is `warn`, `miss>=HEALTH_DEAD_MISS` is `dead`; diag present but `motor_age_ms` never reported is `dead`; a sender that never carries ANY diag field is judged on reception recency alone and flagged `diag: false` (never scored as if a missing ack/miss meant something); `GET /health` response shape (`link`/`joints`/`summary`); `Status.telemetry.health` carries the summary only, never the per-joint grid; a bench-style single-joint feed shows exactly one `ok` and the other 11 (never touched by this module) `dead` - the live shape this task actually measured against the running bench rig |
| `test_sync_from_real.py` (R12, docs/123 section 10.2/10.2b, 2026-09-04) | `POST /sync_from_real` 409s only when NO real telemetry has EVER arrived (`rx_count==0`), never merely "most joints have no data" (a bench-shaped 1-of-12 feed syncs fine, `synced`/`skipped` split correctly with named reasons); a real value outside `safe_clip` lands in `clipped` with `{real, applied, range}` AND the sim's own manual target actually stays inside the safe window; `POST /tx/arm` 409s naming the joint(s) with no synced value; sync then arm succeeds; a synced joint's telemetry going stale (>1s, no further packets) invalidates the sync and a later arm is refused again with nothing else having changed; plus text-presence checks that `dashboard.js` wires the "0. sync from hardware" button and never locks the Joints tab when no real telemetry is connected at all. **2026-09-04 bench fix (scenarios h-k)**: a clipped joint whose real hardware sits perfectly still now arms successfully (was a structural 409 before the fix) and the arm response's `sync.clip_warnings` names the real position/model range/travel in deg; a joint that ACTUALLY moves after sync still blocks, using the RAW real-at-sync/real-now values (never the clipped target); a joint carrying diag fields that verdict `dead` (ack/miss/motor_age_ms) with a fresh position field is skipped as "no real data (motor not responding)", never synced to a phantom 0; a joint with no data at all keeps the plain "no real data" reason unchanged |

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
    sim_core.py              200 Hz physics / 50 Hz control, PD+T-N, base modes, snapshots;
                             real_replay/file_replay snap direct-drive joints into qpos
                             clipped to the HARD model range (never safe_clip), NaN/inf
                             treated as no-data - ROM clip task, 2026-09-04
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
    tx.py                    (UI v2 TX, wired 2026-09-04) TxState: config/enable/arm/disarm/
                             heartbeat/on_control_tick, driving a real bridge.tx_client.TxClient
    hw_sync.py               (R12, docs/123 section 10.2, 2026-09-04) sync-before-arm gate:
                             POST /sync_from_real pulls manual targets from live real
                             telemetry; POST /tx/arm refuses until a valid sync covers every
                             TX-enabled joint
    bridge/
      huphy_udp.py           HUPHY UDP -> canonical JointState/ImuState (P3); clips pos/tgt
                             to a row's optional rom_deg before conversion, if set (2026-09-04)
      joint_map_biped.json   DEFAULT since 2026-09-04 (biped structure migration, docs/121
                             section 12): explicit 12-row left_leg/right_leg-motor ->
                             sim-joint table; optional per-row rom_deg: [lo,hi]|null, null
                             everywhere today
      joint_map_huphy.json   legacy (pre-biped) bare left/right vocabulary, unchanged, still
                             loadable via --map - no longer the default
      dummy_tx.py            sine/script/jsonl -> /ws/in and/or HUPHY-format UDP (P3)
      tx_map.py              sim-rad -> HUPHY cal-deg (inverse of huphy_udp.py), no huphy
                             import - docs/123 plan A item 2
      remote_target.py       LatestOnly (seq/arm_token/contract_hash gate) + DeadmanFilter
                             (0.2s deadman -> flat hold_s -> linear return_s slew to default,
                             3 independent knobs, resolved 2026-09-04), shared by dummy_rx.py
                             and huphy_remote_motion.py - docs/123 plan A item 3
      dummy_rx.py            huphy-free local round-trip target: UDP:9872 in -> 1st-order PD
                             motor model -> HUPHY-format UDP:9870 out - docs/123 item 4
      huphy_remote_motion.py robot-side HUPHY Motion; huphy imported lazily, only inside
                             run_real() - --dry-run needs neither huphy nor CAN - item 3.
                             Biped structure migration (2026-09-04): builds via build_biped()
                             (build_robot/kind:"single" never existed on this HUPHY checkout;
                             the only builders are build_leg and build_biped), --limb resolves
                             through the joint map's own limb keys + historical aliases
                             (resolve_side), and RemoteMotion prefixes every outgoing action
                             key with the resolved biped limb id ("left_leg/knee", not bare
                             "knee") since Biped.split_action hard-fails on an unprefixed name
      tx_client.py           viewer-side JointTarget sender: arm/mode-gate (blocks
                             policy_sim/policy_shadow)/safe_clip+slew/kp-kd-clamp - item 5.
                             Driven by tx.py's TxState from SimCore._on_control_tick (2026-09-04).
                             Optional hard_range kwarg: fallback clip for a joint outside the
                             loaded contract (defensive, unused by any current caller, 2026-09-04)
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
