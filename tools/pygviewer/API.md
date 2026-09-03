# pygviewer API (wire schema v1) - draft

Base URL `http://192.168.20.177:8095`.  Interactive OpenAPI: `/docs`.  The generated schema
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
assuming the two hosts are synchronised.

## Implemented now (P0/P1/P2/P3)

| method | path | body | returns |
|---|---|---|---|
| GET | `/status` | - | `Status`: variant, mode, sim time, rates (`phys_hz`, `ctrl_hz`, `drops`), base state, contract freshness, **`telemetry`** (P3: rx rate/age/seq-gaps/clock-offset/jitter/contract-mismatches/wrap-events/range-violations/bridge-errors/sign-sanity/replay-progress), warnings, RSS |
| GET | `/contract` | - | the whole baked model contract + its freshness verdict |
| GET | `/snapshot` | - | the raw simulator snapshot: every joint's q/qd, actuated tau/target, base pose, IMU sensors, loop closure |
| GET | `/joints` | - | one `JointState` (canonical actuated set) |
| POST | `/target` | `{"values": {"L_knee_joint": 0.9}}` | `{ok, clamped_to}` - values are **clamped** to the contract's `safe_clip`, not rejected; the applied window is echoed |
| POST | `/ankle` | `{"side": "L", "pitch": -0.30, "roll": 0.10}` | AB only: foot-space command, inverted to a crank pair. 409 on an RP variant |
| POST | `/base` | `{"mode": "fixed", "pos": [0,0,1.05], "rpy": [0,0.1,0], "pivot_offset": [0,0,0.06], "ground": true}` | any subset; omitted fields keep their value |
| POST | `/reset` | `{"keyframe": "knees_bent"}` | restores joints **and** base pose |
| POST | `/mode` | `{"mode": "manual"}` | `idle`/`manual`/`policy_sim`/`real_replay` now (`policy_sim` 409 without a loaded policy, `file_replay` 409 without a loaded recording); `policy_shadow` answers 501 (P4: needs the per-term obs mux) |
| POST | `/policy/load` | `{"name": "<baked>"}` or `{"onnx": "...", "pt": null}` | loads a baked ONNX (default) or a direct `.pt` (slow, mjlab env build); 409 if `policy_contract.model_contract_sha` &ne; the loaded model's, or the default pose differs by > 1e-4 rad |
| GET | `/policy/list` | - | baked policies next to this model's cache entry, each flagged `compatible` against the live contract sha |
| POST | `/policy/unload` | - | drops the policy, falls back to `manual` |
| POST | `/policy/cmd` | `{"vx": 0.6, "vy": 0.0, "wz": 0.0}` | velocity command consumed by `policy_sim` / `policy_shadow` |
| GET | `/policy/io` | - | `PolicyIO`: latest built observation, action, target and cmd; 409 if no policy loaded |
| GET/POST | `/obs_source` | `{"sources": {"projected_gravity": "sim"}}` | per observation TERM, `sim` (works) or `real` (501 - needs the P4 per-term obs mux); 409 if no policy loaded |
| GET | `/gains` | - | `{source: train\|real, gains: {joint: {kp, kd, kp_train, kd_train, effort, overridden}}}` |
| POST | `/gains` | `{"source": "real"}` or `{"overrides": {...}}` | switches PD source; `real` is rejected (400) unless the contract carries a `real_gains` table - the viewer never invents hardware numbers |
| POST | **`/record/start`** | `{"path": null}` | starts streaming `JointState` to a `jsonl.gz` (auto path if omitted); 409 if already recording |
| POST | **`/record/stop`** | - | closes the recording, returns `{path, n_lines, errors}`; 409 if not recording |
| POST | **`/replay/load`** | `{"path": "<recording>.jsonl.gz"}` | loads a recording for `mode=file_replay`; 400 on a missing file or a `contract_hash` mismatch (R11) |
| POST | **`/replay/seek`** | `{"frac": 0.5}` | seek the loaded recording to a fraction `[0,1]` |
| POST | **`/replay/speed`** | `{"speed": 2.0}` | playback speed multiplier |
| GET | `/schema/deferred` | - | JSON schemas of the request models whose endpoints are still 501 |
| WS | `/ws/out?hz=50&types=JointState,Status,PolicyIO` | - | latest-only stream, coalesced at `hz` (1-100, default 30). A slow consumer gets fewer frames; nothing is queued. **Measured live: 49.4 msg/s at `hz=50`** |
| WS | **`/ws/in`** | one `JointState` or `ImuState` object per text frame | ingests into `RealState` (unknown joint names -> `{"error": ...}`, connection stays open); acks `{"ok": true, "seq": ...}` per frame |
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

| path | phase | body model | notes |
|---|---|---|---|
| `POST /obs_source` with a `real` value | P4 | `ObsSourceIn{sources: {term: src}}` | the switch and staleness-guard plumbing (`ObsSourceMux`) exist now; per-term real sourcing needs `policy_shadow`'s obs mux |
| `POST /mode {"mode": "policy_shadow"}` | P4 | `ModeIn` | shadow mode (obs mux, action displayed/plotted only, transmit hard-disabled) |
| `POST /script/run` | P4 | `{path, run_id}` | `{joint_names, rows: [[t_s, q...]]}` played in `manual`; the robot replays the same file |
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
contract_stale, contract_checks, telemetry, warnings[], rss_mb}`.

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
`sign`, `offset_rad`, `motor_model`. No regex, no default: a `(limb, motor)` pair not in the
table is a hard failure (`KeyError`, counted in `Status.telemetry.bridge_errors`, never a
guess). A separate 4-row `ankle_joints` table carries the FK-derived `ankle_pitch`/`ankle_roll`
values (AB only) into `JointState.ankle_derived`, never into the canonical actuated `q`.

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
