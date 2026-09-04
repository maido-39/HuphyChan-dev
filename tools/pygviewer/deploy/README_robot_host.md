# Deploying the pygviewer -> HUPHY bridge on a robot host

Plan A (docs/123 section 4): the robot host runs **its own copy of HUPHY** plus two small
scripts copied from this repo (`bridge/huphy_remote_motion.py`, `bridge/tx_map.py`,
`bridge/remote_target.py`, `bridge/huphy_udp.py`, `bridge/joint_map_huphy.json`, and
`schema.py`/`contract.py` for the pieces they import from `pygviewer`). **HUPHY itself is
never edited** - if something in HUPHY looks wrong while you go through this, write it down
(what you ran, what you expected, what happened) and add it to docs/123 section 5 as a bug
report instead of patching HUPHY's source.

The robot host can be a **remote machine** - everything below assumes that (SSH steps
included). If you are already on the robot host, skip the SSH step.

Every step here has been done, in order, up through "dry-run verification" using
`dummy_rx.py` as a stand-in for HUPHY, **on this development machine** - see
`docs/123_pygviewer_tx_design.md` section 5 for those numbers. Nothing past that point
(anything that touches real HUPHY or real CAN) has been run by this session - that is
precisely what this README hands off to you.

## 0. Before you start - what this bridge will and will not do

- It only ever sends `origin: "manual"` or `"script"` targets. A policy's output can never
  reach this wire (docs/123 section 4) - if you are trying to run a trained policy on the
  robot, this is the wrong tool; see docs/123 section 1 ("plan C") instead.
- `--kp-max`/`--kd-max` default to **5 / 0.5** - low, bench-safe PD gains. Nothing here raises
  them for you; if a joint feels sluggish, that is the point until you have deliberately
  decided otherwise.
- The safety chain is: sender-side `safe_clip`+slew (`tx_client.py`, already applied before
  a packet is even sent) -> arm_token/seq/contract_hash gate + 0.2s deadman + hold + 3s
  return-to-default (`bridge/remote_target.py`, robot-side) -> HUPHY's OWN guards
  (`safety/guards.py`: NaN rejection, limit clamp, slew clamp) inside `Leg.build_commands`,
  **unmodified**. Four independent layers; this bridge only adds the first two.

## 1. SSH to the robot host

```bash
ssh <user>@<robot-host>
```

Everything from here on runs **on the robot host**, not on this development machine.

## 2. Check Python

HUPHY needs Python >= 3.9.

```bash
python3 --version
```

If it's older, install a newer Python via your distro's package manager or `pyenv` before
continuing - this README does not cover that.

## 3. Clone HUPHY

```bash
git clone https://github.com/Human-Pygmalion/HUPHY
cd HUPHY
```

(If the robot host already has a HUPHY checkout - e.g. `~/external_repos/HUPHY` - use that
instead of cloning again; the important thing is that it is a real HUPHY checkout, not a
copy with local edits, since bug reports below assume the checkout matches upstream.)

## 4. Install HUPHY + IMU extras + python-can

```bash
python3 -m venv .venv          # or reuse whatever venv convention the robot host already uses
source .venv/bin/activate
pip install -e .[imu]
pip install python-can
```

`python-can` is not a HUPHY dependency it installs for you automatically in every
configuration (see `pyproject.toml` if this changes) - install it explicitly so
`huphy.motors.canbus.CanBus` can actually talk to a socketcan interface.

## 5. Bring up the CAN interface

One motor on the bench is a single CAN channel (`can0` for the left leg, `can1` for the
right leg, per `config/robot_v1.0.yaml`). Bring up whichever channel your bench motor is
wired to:

```bash
sudo ip link set can0 up type can bitrate 1000000
```

Verify it's up:

```bash
ip -details link show can0
```

You should see `state UP` and `bitrate 1000000`. If this fails, the physical CAN transceiver
/ wiring is the problem, not anything in this bridge - stop and fix that first.

## 6. Check calibration state

```bash
huphy-commission --limb left_leg   # or right_leg, or whatever config/robot_v1.0.yaml calls it
```

**Read `robot_v1.0.yaml`'s own comment before you panic at this step**: freshly-installed
calibration JSONs (`config/calibration/*.json`) have `sign=1, offset=0, limits=null` for
every motor. `limits_deg: null` makes `Motor.is_configured` `False`, which makes
`Leg.is_calibrated` `False`, which makes `Leg.enable()` **refuse to enable torque** unless
you pass `allow_uncalibrated=True` all the way down. **This is HUPHY working as designed, not
a bug** - it is refusing to move a joint whose limits it does not know. Run the commissioning
procedure in HUPHY's own `docs/motor_setup.md` / `scripts/commission.py --help` before
expecting torque to do anything; this bridge's `--allow-uncalibrated` flag exists only so you
can get as far as `--dry-run` (which never touches CAN) or an explicit, eyes-open first
enable, not as a way to skip commissioning.

## 7. Copy this repo's bridge scripts onto the robot host

From your **development machine** (not the robot host):

```bash
scp tools/pygviewer/pygviewer/bridge/huphy_remote_motion.py \
    tools/pygviewer/pygviewer/bridge/tx_map.py \
    tools/pygviewer/pygviewer/bridge/remote_target.py \
    tools/pygviewer/pygviewer/bridge/huphy_udp.py \
    tools/pygviewer/pygviewer/bridge/joint_map_huphy.json \
    tools/pygviewer/pygviewer/contract.py \
    tools/pygviewer/pygviewer/schema.py \
    <user>@<robot-host>:~/pygviewer_bridge/pygviewer/bridge/
```

(`huphy_remote_motion.py` imports `contract.py`/`schema.py`/the rest of `bridge/` as
`from .. import ...` / `from . import ...` - keep the same relative layout, i.e. a
`pygviewer/` package directory containing `contract.py`, `schema.py`, an `__init__.py`
exporting `CACHE_DIR`/`VARIANTS`, and a `bridge/` subdirectory with the five files above plus
`__init__.py`. The simplest way to get this exactly right is `rsync -a
tools/pygviewer/pygviewer/ <user>@<robot-host>:~/pygviewer_bridge/pygviewer/` instead of
copying files one at a time - it will also copy files this bridge does not need
(`api.py`/`ui.py`/`sim_core.py`/...), which is harmless, just heavier.)

You also need the **baked model contract** for whatever variant you are testing
(`LegOnly-AB.model_contract.json`, from this repo's `CACHE_DIR` -
`/home/syaro/pyg_fea/pygviewer/cache/` on the development machine) - `contract.py` refuses to
run without it. Copy it alongside, or point `--cache` at wherever you put it:

```bash
scp /home/syaro/pyg_fea/pygviewer/cache/LegOnly-AB.model_contract.json \
    <user>@<robot-host>:~/pygviewer_bridge/cache/
```

`huphy` itself does **not** need to be installed on the development machine and pygviewer
does **not** need to be installed on the robot host - the only thing that crosses is the
handful of files above plus the one JSON contract file.

## 8. `--dry-run` verification (no CAN, no huphy import at all)

On the robot host, from the directory containing `pygviewer/`:

```bash
cd ~/pygviewer_bridge
python3 -m pygviewer.bridge.huphy_remote_motion \
  --cache ./cache --variant LegOnly-AB \
  --limb left --arm-token bench-test-1 \
  --listen 0.0.0.0:9872 \
  --telemetry <your-viewer-or-dev-machine-ip>:9870 \
  --enable hip_pitch \
  --kp-max 5 --kd-max 0.5 \
  --dry-run -v
```

This does not import `huphy` and does not touch CAN - it only proves the process starts,
parses `--enable`, and can bind :9872. From the **development machine** (or wherever the
viewer runs), send it a target with `tx_client.py` (see `tools/pygviewer/tests/
test_remote_motion.py::test_run_dry_echoes_instant_tracking_telemetry_for_a_live_target` for
a runnable example of exactly this) and confirm the `--telemetry` destination receives
`left/hip_pitch/pos` packets. If nothing arrives, check firewalls between the two hosts
before anything else - UDP has no handshake to fail loudly.

## 9. Real bench test: ONE motor, arm procedure

**Read docs/123 section 3's safety layers again before this step.** Have your hand on the
CAN power switch / e-stop, not just the keyboard.

```bash
python3 -m pygviewer.bridge.huphy_remote_motion \
  --config /path/to/HUPHY/config/robot.yaml \
  --cache ./cache --variant LegOnly-AB \
  --limb left_leg --arm-token bench-test-1 \
  --listen 0.0.0.0:9872 \
  --telemetry <your-viewer-or-dev-machine-ip>:9870 \
  --enable hip_pitch \
  --kp-max 5 --kd-max 0.5 \
  --deadman-s 0.2 --default-return-s 3
```

Note `--limb left_leg` here (HUPHY's own config key) vs `--limb left` in the dry-run above
(the joint map's vocabulary) - `resolve_side()` accepts either, use whichever matches your
`robot.yaml`.

From the sender side, arm and send a SMALL target for `hip_pitch` only (the one joint in
`--enable`) - a few degrees, not the full range. Watch the console this script prints to: it
logs every gain clamp and every ankle-FK failure, and HUPHY's own `logger.warning` calls
(overrun, clip, reject) go to the same stream.

**To stop**: `Ctrl-C`. This script's `finally` block calls `leg.disconnect()`
(HUPHY's own settle-then-disable sequence, `ControlLoop._exit`/`_settle` - holds the current
pose for a few cycles, THEN cuts torque, so a standing joint does not suddenly go limp). If
you need to stop FASTER than that (something looks wrong), cut power at the CAN/motor supply
directly - do not wait for a clean shutdown if the joint is doing something you did not
expect.

To test the deadman without touching anything: arm, send a target, then just stop sending
(kill the sender process, or unplug the network cable between the two hosts) and watch the
console - you should see the joint hold for ~0.2s then slew back toward the default pose
over the next few seconds.

## 10. Next steps

Once one motor on the bench behaves as expected (target in -> HUPHY telemetry matches -> the
deadman does what it says), the natural next steps are: enable the rest of `left_leg`'s
motors one at a time, then try the ankle pair (`--enable ankle`) and confirm the FK/IK round
trip described in `huphy_remote_motion.py`'s own module docstring does not fight the motion
you're commanding, then repeat for `right_leg`. None of that has been tried by this session -
each step is exactly the kind of thing docs/123 section 5 wants a bug report for if HUPHY (not
this bridge) does something unexpected.
