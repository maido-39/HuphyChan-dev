# pygviewer API (wire schema v1) - draft

Base URL `http://192.168.20.177:8095`.  Interactive OpenAPI: `/docs`.  `GET /` (or `/dash`) is
the UI v2 dashboard (docs/121 section 10, README's "Dashboard" section) - the default way to
use this API from a browser; everything below is what it talks to. The generated schema
is authoritative for field types; this file is the *contract in prose* - what the fields
mean, what is implemented today, and what a hardware-side implementer must copy.

## Ground rules

| rule | why |
|---|---|
| Canonical names are the **sim joint names** (`L_knee_joint`, `L_crank_A_joint`). | The robot's limb/motor indices never reach the wire; the bridge converts. One naming authority, not two. |
| Units are **SI**: rad, rad/s, N&middot;m, m, s. | Degrees on the wire is how a 20.7 deg ankle error hides. |
| Missing data is **`null`**, never a sentinel. | HUPHY sends `-1.0` for "no data"; the bridge converts and warns on three in a row. |
| No auto-unwrap. A `|dq| > pi` step is **flagged**, not fixed. | Silently unwrapping turns an encoder fault into a plausible trajectory. |
| Torque from hardware is a current estimate: field `tau_est`, displayed with an "est." label. | The field name must not claim more than the sensor does. |
| Every streamed message carries `t_ns`, `seq` and `contract_hash`. | Overlaying two streams without a timebase and a model identity is a guess. |

## Envelope

Every streamed object:

```json
{"v": 1, "type": "JointState", "t_ns": 257867569464154, "seq": 41,
 "src": "sim", "frame": "model_v30", "contract_hash": "46e0c18a..."}
```

`src` &isin; `sim | real | policy | replay | dummy`.  `t_ns` is the **sender's monotonic
clock**, not wall time; the receiver estimates the offset (protocol step 5) rather than
assuming the two hosts are synchronised.  Every message also carries an optional `run_id`
(P4, `null` unless a `POST /script/run` sequence is playing) - the same script file played on
sim and, separately, on the robot produces two recordings `compare.py` can align by this tag.

## Implemented now (P0/P1/P2/P3/P4)

| method | path | body | returns |
|---|---|---|---|
| GET | `/status` | - | `Status`: variant, mode, sim time, rates (`phys_hz`, `ctrl_hz`, `drops`), base state, **`string`** (base mode `string` only: `{z_set, length, ten_length, taut, tension_N}`), contract freshness, **`telemetry`** (P3: rx rate/age/seq-gaps/clock-offset/jitter/contract-mismatches/wrap-events/range-violations/bridge-errors/sign-sanity/replay-progress, plus A2's `violations`: `{total, by_joint, last}` SUMMARY only - see `GET /violations` for the full record list), warnings, RSS |
| GET | `/contract` | - | the whole baked model contract + its freshness verdict |
| GET | `/snapshot` | - | the raw simulator snapshot: every joint's q/qd, actuated tau/target, base pose, IMU sensors, loop closure |
| GET | `/joints` | - | one `JointState` (canonical actuated set) |
| POST | `/target` | `{"values": {"L_knee_joint": 0.9}}` | `{ok, requested, applied, clip_range}` - values out of the contract's `safe_clip` are **clamped**, not rejected (`applied` differs from `requested`, `clip_range` is the window); a NaN/inf value IS rejected, 422 (ROM clip task, 2026-09-04), and ALSO drops a `side="send"` record into `GET /violations` naming the offending joint (A2) |
| POST | `/ankle` | `{"side": "L", "pitch": -0.30, "roll": 0.10}` | AB only: foot-space command, inverted to a crank pair (`{ok, requested, applied, clip_range, note}`, same requested/applied shape as `/target`, keyed by the two crank joint names). 409 on an RP variant; 422 on a NaN/inf pitch/roll (also recorded, same as `/target` above) |
| POST | `/base` | `{"mode": "fixed", "pos": [0,0,1.05], "rpy": [0,0.1,0], "pivot_offset": [0,0,0.06], "ground": true}` or `{"mode": "string", "z_set": 0.6, "hook_offset": [0,0,0], "follow_xy": false}` | any subset; omitted fields keep their value. `string` is a safety tether: a tendon LIMIT holds the base no lower than `z_set` (slack above it), horizontal motion always free |
| POST | `/reset` | `{"keyframe": "knees_bent"}` | restores joints **and** base pose |
| POST | `/mode` | `{"mode": "manual"}` | `idle`/`manual`/`policy_sim`/`policy_shadow`/`real_replay`/`file_replay`, all six implemented (`policy_sim`/`policy_shadow` 409 without a loaded policy, `file_replay` 409 without a loaded recording) |
| POST | `/policy/load` | `{"name": "<baked>"}` or `{"onnx": "...", "pt": null}` | loads a baked ONNX (default) or a direct `.pt` (slow, mjlab env build); 409 if `policy_contract.model_contract_sha` &ne; the loaded model's, or the default pose differs by > 1e-4 rad |
| GET | `/policy/list` | - | baked policies next to this model's cache entry, each flagged `compatible` against the live contract sha |
| POST | `/policy/unload` | - | drops the policy, falls back to `manual` |
| POST | `/policy/cmd` | `{"vx": 0.6, "vy": 0.0, "wz": 0.0}` | velocity command consumed by `policy_sim` / `policy_shadow` |
| GET | `/policy/io` | - | `PolicyIO`: latest built observation, action, target and cmd; 409 if no policy loaded |
| GET/POST | `/obs_source` | `{"sources": {"projected_gravity": "sim"}}` | per observation TERM, `sim` or `real` (P4: read by `policy_shadow` only - `policy_sim` ignores this); 409 if no policy loaded |
| POST | **`/policy/shadow_follow`** | `{"enabled": true}` | (P4) `policy_shadow` only: lets the shadow action step the LOCAL sim - never a robot, there is no code path that could |
| GET | `/gains` | - | `{source: train\|real, gains: {joint: {kp, kd, kp_train, kd_train, effort, overridden, motor, real_kp?, real_kd?, real_ratio_kp?, real_ratio_kd?, real_flag_kp?, real_flag_kd?}}}` - the `real_*`/`motor` fields (P4/R7) appear once any `JointState` telemetry has carried a `gains` field; a ratio off by more than 5% sets its `real_flag_*` |
| POST | `/gains` | `{"source": "real"}` or `{"overrides": {...}}` or `{"clear_overrides": true}` | switches PD source; `real` is rejected (400) unless the contract carries a `real_gains` table - the viewer never invents hardware numbers. `clear_overrides` (UI v2, default `false`) drops every previously-applied per-joint override before applying `source`/`overrides` this call - without it overrides only ever accumulate, which is what the Gains tab's `train` preset needs (`POST /presets/apply {"name":"train"}` sets it for you) |
| POST | **`/script/run`** | `{"path": "scripts/step_knee_5x10deg.json", "run_id": "..."}` | (P4) plays a `{joint_names, rows:[[t_s,q...]], loop}` file in `manual` mode; tags every subsequent `JointState.run_id`; 404 on a missing file, 400 on an un-actuated joint name or while a policy/replay mode is active |
| POST | **`/script/stop`** | - | (P4) stops the running script; 409 if none is running |
| POST | **`/record/start`** | `{"path": null}` | starts streaming `JointState` to a `jsonl.gz` (auto path if omitted); 409 if already recording |
| POST | **`/record/stop`** | - | closes the recording, returns `{path, n_lines, errors}`; 409 if not recording |
| POST | **`/replay/load`** | `{"path": "<recording>.jsonl.gz"}` | loads a recording for `mode=file_replay`; 400 on a missing file or a `contract_hash` mismatch (R11) |
| POST | **`/replay/seek`** | `{"frac": 0.5}` | seek the loaded recording to a fraction `[0,1]` |
| POST | **`/replay/speed`** | `{"speed": 2.0}` | playback speed multiplier |
| GET | `/schema/deferred` | - | JSON schemas of the request models whose endpoints are still 501 |
| GET | **`/violations`** | query: `limit` (default 100), `side` (`recv`\|`recv_torque`\|`sim_actuator`\|`send`) | (A2, 2026-09-04) `{records, by_joint, total}` - the shared ROM/torque violation ring buffer (`pygviewer/violations.py`, max 200 records across every side). `records[i]` is `{seq, t_mono, age_s, side, joint, value, limit_lo, limit_hi, over_by, src, ...}` - `age_s` is computed at request time; a rejected NaN/inf send has `value: null` and a `rejected` key instead of `over_by`. `by_joint` is `{joint: {side: count, ..., total: n}}` and survives eviction from the ring (cumulative, never thinned) |
| POST | **`/violations/clear`** | - | clears the ring buffer AND every cumulative count (`seq` itself never resets) |
| POST | **`/tx/config`** | `{"host":"127.0.0.1","port":9872,"enable":["L_knee_joint"],"kp_max":5.0,"kd_max":0.5,"ttl_ms":250}` | (UI v2 TX, docs/121 section 10 / docs/123, wired 2026-09-04) (re)builds the real `bridge.tx_client.TxClient` that sends this - `enable` becomes that client's own hard joint allow-list (anything else is never sendable, not just filtered). 400 on an un-actuated joint name; 409 while armed (`POST /tx/disarm` first, so the wire format never changes mid-stream) |
| POST | **`/tx/enable`** | `{"on": true}` | stage 1: turns the TX panel itself on; requires a prior `/tx/config` (409 otherwise). `{"on": false}` also disarms |
| POST | **`/tx/arm`** | - | stage 2: refused (409) unless stage 1 is enabled AND the sim is in `manual` mode - policy output must never be transmittable |
| POST | **`/tx/disarm`** | - | disarm |
| POST | **`/tx/heartbeat`** | - | the KEYBOARD dead-man (dashboard: Space, held, ~100ms cadence); 409 if not armed. Distinct from arm/disarm: once this goes stale (>0.3s) the viewer simply stops sending NEW packets ("hold", not "disarm") - the robot's own age-based dead-man (`bridge.remote_target`, 0.2s deadman_s) then runs its own hold/return-to-default, same as an unplugged cable |
| GET | **`/tx/status`** | - | `{armed, sending, enable, enabled, host, port, last_seq, rate_hz, deadman_age_s, deadman_timeout_s, rejected_count, disarm_reason, last_sent_target, kp_max, kd_max, ttl_ms, arm_token, warnings, violations_count}` - `sending` is `armed AND the keyboard dead-man is fresh` (can be `false` while `armed` stays `true`, see `/tx/heartbeat`); `arm_token` is generated once per process and must be copied verbatim into the receiver's own `--arm-token` (`bridge/dummy_rx.py` / `bridge/huphy_remote_motion.py`); `violations_count` (A2) is the `side="send"`-only count from `GET /violations` |
| GET | **`/presets`** | - | (UI v2) `{builtin: {train, real}, custom: [{name, gains}]}` - `train`/`real` are fixed descriptions, not files; `custom` lists `tools/pygviewer/presets/*.json` |
| POST | **`/presets`** | `{"name": "bench1", "gains": {"L_knee_joint": {"kp": 50, "kd": 2}}}` | (UI v2) saves a named gains table to `tools/pygviewer/presets/<name>.json`; 400 on a reserved name (`train`/`real`) or an un-actuated joint |
| POST | **`/presets/apply`** | `{"name": "real"}` | (UI v2) applies a preset through the existing `SimCore.set_gains`: `train` clears every override back to the contract's own kp/kd, `real` sets kp=10/kd=1 on every actuated joint (HUPHY `robot_v1.0.yaml`'s uniform start point), any other name loads that custom file; 404 on an unknown custom name |
| GET | **`/`**, **`/dash`** | - | (UI v2) the dashboard page (`pygviewer/static/dashboard.html`) - the default entry point, see the dashboard section below |
| GET | **`/static/*`** | - | (UI v2) `pygviewer/static/` mounted as static files: `dashboard.js` and the vendored `vendor/three.min.js` / `vendor/uPlot.iife.min.js` / `vendor/uPlot.min.css` (no CDN - this LAN has no internet access) |
| WS | `/ws/out?hz=50&types=JointState,Status,PolicyIO` | - | latest-only stream, coalesced at `hz` (1-100, default 30). A slow consumer gets fewer frames; nothing is queued. **Measured live: 49.4 msg/s at `hz=50`**. UI v2: whenever `JointState` is requested AND any real telemetry has been received at least once, a SECOND `JointState` frame (`src="real"`) follows the sim one every tick - same schema, populated from `RealState.snapshot_joints()`; costs nothing when no real side is connected (verified live: absent with nothing connected, present within one tick of `bridge dummy --imu` sending telemetry) |
| WS | **`/ws/in`** | one `JointState`, `ImuState` or `PolicyIO` object per text frame | ingests into `RealState` (unknown joint names -> `{"error": ...}`, connection stays open); acks `{"ok": true, "seq": ...}` per frame. `PolicyIO` (P4) is a real host's OWN self-reported obs/action/cmd - the only source for the shadow obs mux's `actions`/`command` terms. **`JointState.q` is stored verbatim, never clipped here** - see the ROM clip note below for where an out-of-range value actually gets bounded |
| UDP | **`:9871`** (`bridge/huphy_udp.py`, run separately - see below) | HUPHY line format | adapter -> canonical `JointState`/`ImuState`, fed into the same `RealState` a `/ws/in` client would reach |

Example:

```bash
curl -s :8095/status | jq '.rates, .base.mode, .telemetry'
curl -s -X POST :8095/target -H 'content-type: application/json' \
     -d '{"values":{"L_knee_joint":0.9}}'
curl -s -X POST :8095/ankle  -H 'content-type: application/json' \
     -d '{"side":"L","pitch":-0.30,"roll":0.10}'
websocat 'ws://192.168.20.177:8095/ws/out?hz=50&types=JointState'

# P3: record 10 s, then replay it
curl -s -X POST :8095/record/start -d '{}'
sleep 10
curl -s -X POST :8095/record/stop
curl -s -X POST :8095/replay/load -d '{"path": "<path from record/stop>"}'
curl -s -X POST :8095/mode -d '{"mode": "file_replay"}'

# P3: telemetry bridges (separate processes - see "Hardware bridge" below)
mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py bridge huphy --variant LegOnly-AB --port 9871
mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py bridge dummy --pattern sine \
    --joints L_knee_joint,R_knee_joint --target ws,udp --ws-url ws://192.168.20.177:8095/ws/in
```

## Defined, not implemented (the endpoint answers **501** with its phase)

Every phase (P0-P4) is now implemented; the one row below is not a phase to reach, it is a
permanent, by-decision non-implementation.

| path | phase | body model | notes |
|---|---|---|---|
| `JointTarget` (viewer -> robot) | never (by decision) | - | see the model section below |

## Message models

### `JointState` (implemented, outbound)

```
joint_names[]   canonical sim names, always sent - never assume an order
q[]             rad
qd[]            rad/s, or null
tau_est[]       N*m; from hardware this is a CURRENT ESTIMATE
target[]        rad, or null
temp_c[]        or null
gains           {joint: {kp, kd, tau_ff, kp_enc_range}} when the source knows them
ankle_derived   {"L": {"pitch": rad, "roll": rad}, "R": ...}   AB only
```

For AB the canonical actuated set is hips + knees + **cranks**.  The ankle pitch/roll are
*derived*: in the sim they are the model's own passive state, on the robot they are computed
from the crank encoders through the mechanism.  They are reported separately, never mixed
into `q`, so a comparison never silently pairs a measured angle with a computed one.

**ROM clip on receive (`real_replay`/`file_replay`, ROM clip task, 2026-09-04)**: `RealState.q`
(fed by `/ws/in`, the HUPHY bridge, or a file replay) always holds the value exactly as
received - never clipped, never guessed - so plots and `Status.telemetry.range_violations`
keep seeing the truth. What actually drives the physics is a separate matter: at the point
`sim_core.py` snaps a direct-drive joint's (hip/knee/RP-ankle) qpos every control tick, the
value is clipped to that joint's **hard** MJCF range (`joint_contract.<name>.range`, wider
than the `safe_clip` window `/target` uses) - a non-finite (NaN/inf) sample is treated as "no
data this tick" and never snapped at all. The AB crank is never qpos-snapped (it is only ever
PD-tracked, see the crank note above) and already clips its PD target to the tighter
`safe_clip`, so it was never exposed to this - both paths now also count a per-joint clamp
event, surfaced (never in `RealState`/`range_violations` itself) as
`Status.telemetry.replay_clamp.{clamped_now, clamp_count}`, present only for joints that have
actually been clamped at least once.

### `ImuState` (implemented, inbound over `/ws/in` and the HUPHY bridge)

`quat_wxyz`, `gyro_rad_s`, `acc_m_s2`, `gravity_b` (derived from the quaternion when the
source does not send it), `age_s`. The HUPHY bridge takes `gravity_b` directly from HUPHY's
own `grav_*` fields rather than re-deriving it from a quaternion (HUPHY has already done that
reordering once; doing it again independently risks a second, different sign bug), so
`quat_wxyz` is `null` from that source today.

### `to_jsonl` / `from_jsonl` (schema.py, P3)

Every message class round-trips through `to_jsonl(msg) -> str` (one line, newline included)
and `from_jsonl(line) -> Header` (dispatches on `type`, raises `ValueError` on bad JSON, an
unknown `type`, or a validation failure). This is what `record.py`'s `Recorder`/`Replayer`
and `bridge/dummy_tx.py` all use, so the file format and the live wire format are, by
construction, the same code path - see `tests/test_schema.py`.

### `JointTarget` (documented only - **there is no outbound path, by decision**)

`{joint_names, q_target, kp?, kd?, ttl_ms}`.  The viewer receives from the robot and does not
command it (docs/121 section 1).  The model exists so the wire format is complete and a
future deployment runtime has an exact contract; `modes.py` carries
`SHADOW_MAY_TRANSMIT = False` as a constant rather than a setting, so enabling it takes a
code change and a review.

### `PolicyIO` (implemented)

`{obs[], obs_sources{term: src}, action[], target[], cmd[vx, vy, wz]}`.  `GET /policy/io`
returns one shot; `WS /ws/out?types=PolicyIO` streams it while a policy is loaded.

### `Status` (implemented)

`{variant, mode, policy, sim_time_s, rates{phys_hz, ctrl_hz, drops, phys_steps},
base{mode, pos, quat, rpy, cmd_pos, cmd_quat, pivot_offset, ground},
string{z_set, length, ten_length, taut, tension_N} | null,
contract_stale, contract_checks, telemetry, warnings[], rss_mb,
imu{gyro_rad_s, gravity_b} | null, side_mapping_verified: bool | null}`.

`imu`/`side_mapping_verified` are UI v2 additions (both default `None`, so nothing that
predates them breaks): `imu` is the SIM's own body-frame gyro/gravity, read from the same
sensors `ObsBuilder` uses (`imu_ang_vel`, `-imu_upvector`) so the dashboard's IMU widget and
the Obs tab agree with the policy by construction, never a second derivation of the math.
The RECEIVED real IMU (if any) is a separate field, `telemetry.imu` (`RealState.imu`,
unchanged shape - `{quat_wxyz, gyro_rad_s, acc_m_s2, gravity_b, age_s}`, all optional) -
kept apart from `Status.imu` so a client can never confuse "what the sim computed" with
"what a robot reported". `side_mapping_verified` mirrors `bridge/joint_map_huphy.json`'s own
flag, read once at process start (drives the top-bar UNVERIFIED badge, docs/121 section 5).

## Hardware bridge (P3, implemented)

`tools/pygviewer/run.py bridge huphy --variant LegOnly-AB --port 9871` runs a standalone
process: a `SimCore` for the named variant plus a UDP receiver that parses HUPHY's
`{limb}/{motor}/{field}` fast-telemetry and IMU packets and feeds them into that `SimCore`'s
`RealState` (`core.real`) - the same object `/ws/in` writes into on the main viewer process.
To feed the actual viewer, either run the bridge in the same process (not done by the CLI
today - use `HuphyUdpReceiver(core, ...)` directly if embedding) or relay `/ws/in` from the
standalone bridge's `RealState` (not implemented; today's bridge CLI is a standalone
diagnostic/verification tool, see docs/121 section 9 for the live test that exercised it).

`bridge/joint_map_huphy.json` is an **explicit 12-row table** - `{limb, motor}` -> `sim_joint`,
`sign`, `offset_rad`, `motor_model`, plus an optional `rom_deg: [lo, hi] | null` (ROM clip
task, 2026-09-04; `null` on every row of this file and of `joint_map_bench.json` today, since
neither rig has been through HUPHY's `commission sweep` yet). No regex, no default: a `(limb,
motor)` pair not in the table is a hard failure (`KeyError`, counted in
`Status.telemetry.bridge_errors`, never a guess). A separate 4-row `ankle_joints` table
carries the FK-derived `ankle_pitch`/`ankle_roll` values (AB only) into
`JointState.ankle_derived`, never into the canonical actuated `q`; its rows carry the same
optional `rom_deg`.

When a row's `rom_deg` is set, `HuphyBridge.parse_fast` clips `pos`/`tgt` to it in HUPHY's own
already-calibrated cal-space degrees, **before** the sim-rad conversion below - a clamp event
is counted (`HuphyBridge.rom_clamp_count`) and warned once per joint. This is defense in depth
only, layered in front of the receive-side hard-range clip in `sim_core.py` (see the `q`
model's ROM clip note above), which stays the actual safety backstop regardless of whether
any bridge sets `rom_deg`.

Conversion, per motor: `sim_rad = travel_sign(sim_joint) * sign * radians(huphy_deg) +
offset_rad`. `travel_sign` is looked up from the **model contract** (`joint_contract.<name>.
travel_sign`), never stored in the map - it is a property of the sim model, not of the
hardware calibration. Velocity and torque use the same `travel_sign * sign` factor with no
offset (HUPHY passes those two raw, without pos's calibration - `leg.py:370-372`).
Verified (`tests/test_bridge_huphy.py` and a live UDP round trip, docs/121 section 9): a
physical +30&deg; knee flexion on both legs converts to sim `L_knee_joint +0.5236` /
`R_knee_joint -0.5236` rad (contract `travel_sign` +1 / -1), to 1e-6.

`-1` is HUPHY's sentinel for "missing" **only** on `age`/`sensor_dt`-type fields
(`IMU_MISSING_IS_MINUS_ONE` in HUPHY's own `telemetry/snapshot.py`); the bridge honours that
distinction rather than applying `-1` universally - `grav_z = -1.0` is a real, common IMU
reading (an upright robot), and treating it as "missing" would null out the most common case.

Defaults asserted by the user on 2026-09-03, both **UNVERIFIED** until verification protocol
steps 2 and 3 pass (docs/121 section 5) - the UI's Telemetry panel shows a persistent banner
until `joint_map_huphy.json`'s `side_mapping_verified` is flipped to `true`:

* sim `L_*` = HUPHY `left` / can0 / ids 1-6; `R_*` = `right` / can1 / ids 7-12.
  (This conflicts with the `L_* = physical R` note in `tools/robot_model/rotor_faces.json`,
  which is exactly why the banner exists.)
* HUPHY `ankle_a` = sim `crank_A` (upper motor), `ankle_b` = `crank_B` (lower).

## Dummy transmitter (P3, implemented)

`tools/pygviewer/run.py bridge dummy --pattern sine|script|jsonl --target ws,udp [...]`.
From one trajectory source it can send canonical `JointState`/`ImuState` to `/ws/in` and/or
the SAME trajectory re-expressed as HUPHY-format UDP packets (one per leg) to the bridge's
listening port - this is what exercises the adapter's unit/sign/name conversion end to end
rather than only in a unit test. `--latency-ms`/`--jitter-ms`/`--drop-ratio` inject network
imperfections on the sending side. `--target udp` requires an AB (loop) variant - HUPHY's
hardware has no RP analogue.

## Offline tools (P4, implemented) - not HTTP, run standalone

Neither of these needs a live viewer process; both act on `.jsonl.gz` recordings or a baked
model contract directly. Usage examples are in `README.md`'s "Comparison mode (P4)" section.

**`pygviewer.compare`** (`compare.py`) - `--sim <rec>.jsonl.gz --real <rec>.jsonl.gz [--joints
...] [--offset-joint ...] [--offset-field q|target|tau_est] [--offset-dt 0.005] [--i-know]`.
Refuses two recordings with different `contract_hash` unless `--i-know` (R11); prints a
warning (does not refuse) when the two headers' base mode/height/ground/`gains_source` differ
(R9); estimates the clock offset between the two streams by cross-correlating the GRADIENT of
the chosen field on a common absolute-time grid (R5 - correlating raw levels works for a sine
but not a step trajectory, whose flat plateaus swamp the real edge timing; see docs/121
section 9 for the two-bug writeup), with a jitter estimate from re-estimating over
sub-windows; writes one PNG per joint (target/q/tau_est, English labels) to `docs/img/`.

**`pygviewer.protocol`** (`protocol.py`) - `--variant LegOnly-AB`. Runs the 8-step
verification protocol (docs/121 section 5) end to end: steps 1 (static zero), 4 (velocity
sanity), 5 (latency calibration) and 8 (record round-trip) execute against synthetic data
built the same way `bridge/dummy_tx.py` would produce it and PASS/FAIL on the design doc's own
budgets; steps 2 (sign sweep), 3 (ankle FK cross-check), 6 (same-target overlay) and 7 (IMU
tilt) need the real robot or a human and are printed as a procedure, tagged `MANUAL` - never
claimed as passing. Exit code is non-zero only if an AUTOMATED step failed.
