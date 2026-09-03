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

## Implemented now (P0/P1)

| method | path | body | returns |
|---|---|---|---|
| GET | `/status` | - | `Status`: variant, mode, sim time, rates (`phys_hz`, `ctrl_hz`, `drops`), base state, contract freshness, warnings, RSS |
| GET | `/contract` | - | the whole baked model contract + its freshness verdict |
| GET | `/snapshot` | - | the raw simulator snapshot: every joint's q/qd, actuated tau/target, base pose, IMU sensors, loop closure |
| GET | `/joints` | - | one `JointState` (canonical actuated set) |
| POST | `/target` | `{"values": {"L_knee_joint": 0.9}}` | `{ok, clamped_to}` - values are **clamped** to the contract's `safe_clip`, not rejected; the applied window is echoed |
| POST | `/ankle` | `{"side": "L", "pitch": -0.30, "roll": 0.10}` | AB only: foot-space command, inverted to a crank pair. 409 on an RP variant |
| POST | `/base` | `{"mode": "fixed", "pos": [0,0,1.05], "rpy": [0,0.1,0], "pivot_offset": [0,0,0.06], "ground": true}` | any subset; omitted fields keep their value |
| POST | `/reset` | `{"keyframe": "knees_bent"}` | restores joints **and** base pose |
| POST | `/mode` | `{"mode": "manual"}` | `idle`/`manual` now; the others answer 501 with their phase |
| GET | `/schema/deferred` | - | JSON schemas of the request models whose endpoints are still 501 |
| WS | `/ws/out?hz=50&types=JointState,Status` | - | latest-only stream, coalesced at `hz` (1-100, default 30). A slow consumer gets fewer frames; nothing is queued |

Example:

```bash
curl -s :8095/status | jq '.rates, .base.mode'
curl -s -X POST :8095/target -H 'content-type: application/json' \
     -d '{"values":{"L_knee_joint":0.9}}'
curl -s -X POST :8095/ankle  -H 'content-type: application/json' \
     -d '{"side":"L","pitch":-0.30,"roll":0.10}'
websocat 'ws://192.168.20.177:8095/ws/out?hz=50&types=JointState'
```

## Defined, not implemented (the endpoint answers **501** with its phase)

| path | phase | body model | notes |
|---|---|---|---|
| `POST /policy/load` | P2 | `PolicyLoadIn{onnx?, pt?, run_dir?}` | must REFUSE a policy whose `policy_contract.model_contract_sha` differs from the loaded model's |
| `POST /policy/cmd` | P2 | `{vx, vy, wz}` | velocity command for `policy_sim` / `policy_shadow` |
| `POST /gains` | P2 | `GainsIn{source: train\|real, overrides}` | the response-comparison overlay is meaningless until the two sides' PD gains match |
| `POST /obs_source` | P4 | `ObsSourceIn{sources: {term: src}}` | per observation TERM, sim or real, with a staleness guard |
| `POST /script/run` | P4 | `{path, run_id}` | `{joint_names, rows: [[t_s, q...]]}` played in `manual`; the robot replays the same file |
| `POST /record/start`, `/record/stop` | P3 | - | streaming `jsonl.gz`, header carries contract hash, base mode, gains and toggles |
| `WS /ws/in` | P3 | `JointState` / `ImuState` | telemetry ingest |
| `UDP :9871` | P3 | HUPHY line format | adapter -> canonical `JointState` |

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

### `ImuState` (P3)

`quat_wxyz`, `gyro_rad_s`, `acc_m_s2`, `gravity_b` (derived from the quaternion when the
source does not send it), `age_s`.

### `JointTarget` (documented only - **there is no outbound path, by decision**)

`{joint_names, q_target, kp?, kd?, ttl_ms}`.  The viewer receives from the robot and does not
command it (docs/121 section 1).  The model exists so the wire format is complete and a
future deployment runtime has an exact contract; `modes.py` carries
`SHADOW_MAY_TRANSMIT = False` as a constant rather than a setting, so enabling it takes a
code change and a review.

### `PolicyIO` (P2)

`{obs[], obs_sources{term: src}, action[], target[], cmd[vx, vy, wz]}`.

### `Status` (implemented)

`{variant, mode, policy, sim_time_s, rates{phys_hz, ctrl_hz, drops, phys_steps},
base{mode, pos, quat, rpy, cmd_pos, cmd_quat, pivot_offset, ground},
contract_stale, contract_checks, telemetry, warnings[], rss_mb}`.

## Hardware bridge mapping (P3, contract fixed now)

`bridge/joint_map_huphy.json` will be an **explicit 12-row table** - `limb`, `motor` -> sim
name, `sign`, `offset`.  No regex, no default: a joint that is not in the table is a hard
failure.  The sign must be applied to velocity and torque as well as position (HUPHY's
`leg.py` passes those raw).  Defaults asserted by the user on 2026-09-03, both **unverified**
until protocol steps 2 and 3 pass, and shown with an "UNVERIFIED" banner until then:

* sim `L_*` = HUPHY `left` / can0 / ids 1-6; `R_*` = `right` / can1 / ids 7-12.
  (This conflicts with the `L_* = physical R` note in `tools/robot_model/rotor_faces.json`,
  which is exactly why the banner exists.)
* HUPHY `ankle_a` = sim `crank_A` (upper motor), `ankle_b` = `crank_B` (lower).
