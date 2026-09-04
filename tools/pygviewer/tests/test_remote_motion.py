"""docs/123 plan A item 3: ``bridge/huphy_remote_motion.py``'s pure helpers (no huphy import)
and its ``--dry-run`` path (no huphy, no CAN - "log commands + echo telemetry assuming
instant tracking"). The REAL (huphy-backed) path, ``run_real()``/``RemoteMotion``, cannot be
exercised on this machine at all - no ``huphy`` install, no CAN bus - and is reviewed against
HUPHY's source rather than tested; that gap is stated explicitly in docs/123 section 5, not
silently absorbed.
"""

import dataclasses
import json
import socket
import threading
import time

from pathlib import Path

import pytest

from pygviewer import CACHE_DIR
from pygviewer.bridge.huphy_remote_motion import (
  RemoteMotion,
  build_parser,
  enable_motor_names_to_sim_joints,
  main,
  plan_gains,
  resolve_side,
  sim_joints_for_limb,
  split_motor_targets_into_action,
)
from pygviewer.bridge.huphy_udp import DEFAULT_MAP_PATH, JointMap
from pygviewer.bridge.remote_target import DeadmanFilter, LatestOnly
from pygviewer.bridge.tx_client import TxClient
from pygviewer.contract import load_contract
from pygviewer.schema import JointTarget

VARIANT = "LegOnly-AB"


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def _jmap():
  return JointMap(DEFAULT_MAP_PATH)


# --------------------------------------------------------------------------- module import
def test_module_imports_without_huphy_installed():
  # if this file's own import at the top of this module failed, every test below would
  # error at collection - this test exists so a FUTURE accidental top-level `import huphy`
  # fails with a clear, named test rather than "everything in this file is broken".
  import pygviewer.bridge.huphy_remote_motion as m

  assert hasattr(m, "run_real")
  assert hasattr(m, "run_dry")


# --------------------------------------------------------------------------- resolve_side
def test_resolve_side_accepts_joint_map_vocabulary():
  assert resolve_side("left") == "left"
  assert resolve_side("right") == "right"


def test_resolve_side_accepts_huphy_config_key_vocabulary():
  assert resolve_side("left_leg") == "left"
  assert resolve_side("right_leg") == "right"


def test_resolve_side_rejects_garbage():
  with pytest.raises(ValueError):
    resolve_side("sideways")


# --------------------------------------------------------------------------- sim_joints_for_limb
def test_sim_joints_for_limb_returns_six_names_per_side():
  """Biped structure migration (2026-09-04): `_jmap()` is `DEFAULT_MAP_PATH` -> now
  `joint_map_biped.json`, so the limb keys are `left_leg`/`right_leg`."""
  jmap = _jmap()
  left = sim_joints_for_limb(jmap, "left_leg")
  right = sim_joints_for_limb(jmap, "right_leg")
  assert len(left) == 6 and len(right) == 6
  assert all(n.startswith("L_") for n in left)
  assert all(n.startswith("R_") for n in right)


# --------------------------------------------------------------------------- enable translation
def test_enable_single_motor_names_translate_to_sim_joints():
  jmap = _jmap()
  out = enable_motor_names_to_sim_joints(["hip_pitch", "knee"], "left_leg", jmap)
  assert out == {"L_hip_pitch_joint", "L_knee_joint"}


def test_enable_ankle_alias_expands_to_both_crank_joints():
  jmap = _jmap()
  out = enable_motor_names_to_sim_joints(["ankle"], "left_leg", jmap)
  assert out == {"L_crank_A_joint", "L_crank_B_joint"}


def test_enable_unknown_motor_name_is_a_hard_failure():
  jmap = _jmap()
  with pytest.raises(KeyError):
    enable_motor_names_to_sim_joints(["elbow"], "left_leg", jmap)


# --------------------------------------------------------------------------- split_motor_targets
def test_split_keeps_single_joints_and_pairs_the_ankle():
  single, ankle = split_motor_targets_into_action(
    {"hip_pitch": 1.0, "knee": 2.0, "ankle_a": 3.0, "ankle_b": 4.0}
  )
  assert single == {"hip_pitch": 1.0, "knee": 2.0}
  assert ankle == (3.0, 4.0)


def test_split_drops_an_unpaired_ankle_motor():
  single, ankle = split_motor_targets_into_action({"hip_pitch": 1.0, "ankle_a": 3.0})
  assert single == {"hip_pitch": 1.0}
  assert ankle is None


# --------------------------------------------------------------------------- plan_gains
def test_plan_gains_uses_message_values_when_live_and_clamps():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  msg = JointTarget(
    t_ns=1, seq=1, joint_names=["L_knee_joint"], q_target=[0.1], kp=[50.0], kd=[5.0],
    arm_token="x", origin="manual",
  )
  # side="left_leg" - the DEFAULT (biped) mapper's own limb key (2026-09-04 migration)
  plan = plan_gains(["L_knee_joint"], mapper, "left_leg", msg, "live",
                     kp_max=5.0, kd_max=0.5, default_kp=5.0, default_kd=0.5)
  assert plan.kp["knee"] == pytest.approx(5.0)  # clamped down from 50
  assert plan.kd["knee"] == pytest.approx(0.5)  # clamped down from 5
  assert plan.warnings


def test_plan_gains_uses_defaults_when_not_live():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  msg = JointTarget(
    t_ns=1, seq=1, joint_names=["L_knee_joint"], q_target=[0.1], kp=[3.0], kd=[0.4],
    arm_token="x", origin="manual",
  )
  plan = plan_gains(["L_knee_joint"], mapper, "left_leg", msg, "returning",
                     kp_max=5.0, kd_max=0.5, default_kp=2.0, default_kd=0.2)
  # not "live" -> the message's own kp/kd (3.0/0.4) are NOT used, default_kp/kd are
  assert plan.kp["knee"] == pytest.approx(2.0)
  assert plan.kd["knee"] == pytest.approx(0.2)


def test_plan_gains_skips_joints_on_the_other_side():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  plan = plan_gains(["R_knee_joint"], mapper, "left_leg", None, "idle",
                     kp_max=5.0, kd_max=0.5, default_kp=5.0, default_kd=0.5)
  assert plan.kp == {} and plan.kd == {}


# --------------------------------------------------------------------------- CLI parsing
def test_dry_run_requires_telemetry_flag():
  with pytest.raises(SystemExit):
    main(["--limb", "left", "--arm-token", "tok", "--dry-run"])


def test_build_parser_defaults():
  a = build_parser().parse_args(["--limb", "left", "--arm-token", "tok"])
  assert a.deadman_s == pytest.approx(0.2)
  assert a.hold_s == pytest.approx(3.0)
  assert a.return_s == pytest.approx(2.0)
  assert a.kp_max == pytest.approx(5.0)
  assert a.kd_max == pytest.approx(0.5)


# --------------------------------------------------------------------------- run_dry, end to end
def _free_port() -> int:
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind(("127.0.0.1", 0))
  port = s.getsockname()[1]
  s.close()
  return port


def _wait_until(cond, timeout=3.0, interval=0.02):
  deadline = time.monotonic() + timeout
  last = None
  while time.monotonic() < deadline:
    last = cond()
    if last:
      return last
    time.sleep(interval)
  raise AssertionError(f"condition not met within {timeout}s (last={last!r})")


def test_run_dry_echoes_instant_tracking_telemetry_for_a_live_target():
  c = _contract()
  listen_port = _free_port()
  tele_port = _free_port()
  arm_token = "dry-run-test-token"

  tele_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  tele_sock.bind(("127.0.0.1", tele_port))
  tele_sock.settimeout(0.05)

  args = build_parser().parse_args([
    "--variant", VARIANT, "--cache", CACHE_DIR, "--limb", "left",
    "--listen", f"127.0.0.1:{listen_port}", "--telemetry", f"127.0.0.1:{tele_port}",
    "--arm-token", arm_token, "--hz", "50", "--seconds", "0.6",
  ])

  from pygviewer.bridge import huphy_remote_motion as m

  t = threading.Thread(target=m.run_dry, args=(args,), daemon=True)
  t.start()
  time.sleep(0.1)  # let the receive socket bind

  client = TxClient(
    "127.0.0.1", listen_port, joint_names=list(c.action_joint_names),
    arm_token=arm_token, origin="manual", contract=c, hz=50.0,
  )
  client.arm()
  client.set_target({"L_knee_joint": 0.4})
  try:
    for _ in range(15):
      client.tick()
      time.sleep(0.02)

    def _got_knee_target():
      drained = None
      for _ in range(32):
        try:
          data, _ = tele_sock.recvfrom(4096)
        except socket.timeout:
          break
        obj = json.loads(data.decode("utf-8"))
        # "left_leg/..." - --limb left resolves against the DEFAULT (biped) map, whose own
        # limb key is "left_leg" (2026-09-04 migration; resolve_side's alias resolution).
        if "left_leg/knee/pos" in obj:
          drained = obj
      return drained

    pkt = _wait_until(_got_knee_target, timeout=2.0)
    assert pkt["left_leg/knee/pos"] == pkt["left_leg/knee/tgt"]  # instant-tracking, stated
    assert pkt["left_leg/knee/pos"] > 5.0  # some non-default degrees given 0.4 rad
  finally:
    client.stop()
    t.join(timeout=3.0)
    tele_sock.close()


def test_run_dry_rejects_unknown_joint_and_wrong_arm_token():
  c = _contract()
  listen_port = _free_port()
  tele_port = _free_port()
  arm_token = "dry-run-test-token-2"

  args = build_parser().parse_args([
    "--variant", VARIANT, "--cache", CACHE_DIR, "--limb", "right",
    "--listen", f"127.0.0.1:{listen_port}", "--telemetry", f"127.0.0.1:{tele_port}",
    "--arm-token", arm_token, "--hz", "50", "--seconds", "0.4",
  ])
  from pygviewer.bridge import huphy_remote_motion as m
  from pygviewer.schema import to_jsonl

  t = threading.Thread(target=m.run_dry, args=(args,), daemon=True)
  t.start()
  time.sleep(0.1)

  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    bad_joint = JointTarget(
      t_ns=1, seq=1, joint_names=["not_a_real_joint"], q_target=[0.0],
      arm_token=arm_token, origin="manual",
    )
    sock.sendto(to_jsonl(bad_joint).strip().encode(), ("127.0.0.1", listen_port))
    bad_token = JointTarget(
      t_ns=2, seq=1, joint_names=["R_knee_joint"], q_target=[0.1],
      arm_token="wrong", origin="manual",
    )
    sock.sendto(to_jsonl(bad_token).strip().encode(), ("127.0.0.1", listen_port))
    time.sleep(0.3)
  finally:
    sock.close()
    t.join(timeout=3.0)


# ---------------------------------------------------------------- biped action-key prefixing
# (2026-09-04, docs/121 section 12 / docs/123 section 11): ``RemoteMotion`` is a plain,
# duck-typed class - it imports no ``huphy`` type at module or class scope, only inside
# ``run_real()`` - so it CAN be driven directly against a fake ``leg`` object without a real
# HUPHY install, exercising the one thing this file's rewrite exists to get right: every key
# ``RemoteMotion.__call__`` returns must carry the ``f"{action_prefix}/"`` limb prefix
# ``Biped.split_action`` requires, or a real run dies with "모르는 관절" the first tick it
# tries to command anything.
class _FakeGains:
  def __init__(self, kp, kd):
    self.kp = kp
    self.kd = kd


@dataclasses.dataclass
class _FakeMotorCfg:
  """A ``dataclasses.dataclass``, not a plain class: ``RemoteMotion.__call__``'s per-tick gain
  override does ``dataclasses.replace(motors[name], gains=...)`` and
  ``dataclasses.replace(self.leg.config, motors=...)``, both of which require an actual
  dataclass instance - matching HUPHY's real ``LimbConfig``/``Motor`` (both
  ``@dataclass(frozen=True)``, ``config/schema.py``)."""

  gains: object = None


@dataclasses.dataclass
class _FakeLegConfig:
  motors: dict


def _fake_leg_config(motor_names) -> _FakeLegConfig:
  return _FakeLegConfig(motors={n: _FakeMotorCfg() for n in motor_names})


class _FakeKinematics:
  """Trivial stand-in for HUPHY's ``AnkleKinematics`` - the exact pitch/roll numbers it
  returns are irrelevant to a test that only checks WHICH KEYS come out, not their values."""

  def solve_fk(self, a1_deg, a2_deg, *, guess_pitch_deg=0.0, guess_roll_deg=0.0):
    return (a1_deg, a2_deg)


class _FakeLeg:
  def __init__(self, motor_names):
    self.kinematics = _FakeKinematics()
    self.config = _fake_leg_config(motor_names)


def _remote_motion(mapper, *, side="left_leg", action_prefix="left_leg", arm_token="tok",
                    enable=None, default_q=None, idle_refresh=True):
  fake_leg = _FakeLeg(["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_a", "ankle_b"])
  latest = LatestOnly(expected_arm_token=arm_token)
  deadman = DeadmanFilter(
    default_q=default_q or {}, deadman_s=1.0, hold_s=1.0, return_s=1.0, enable=enable,
  )
  motion = RemoteMotion(
    leg=fake_leg, side=side, action_prefix=action_prefix, mapper=mapper, deadman=deadman,
    latest=latest, gains_cls=_FakeGains, kp_max=5.0, kd_max=0.5, default_kp=5.0, default_kd=0.5,
    idle_refresh=idle_refresh,
  )
  return motion, latest


def test_remote_motion_prefixes_single_joint_action_keys_with_the_biped_limb_id():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)  # DEFAULT_MAP_PATH -> joint_map_biped.json, limb "left_leg"
  motion, latest = _remote_motion(mapper)
  latest.put(JointTarget(
    t_ns=1, seq=1, joint_names=["L_hip_pitch_joint", "L_knee_joint"], q_target=[0.1, 0.2],
    arm_token="tok", origin="manual", ttl_ms=5000,
  ))
  action = motion(0.0, observation={})
  assert action is not None and action  # non-empty
  assert all(k.startswith("left_leg/") for k in action), action
  # the bare (unprefixed) names must never leak out - that is exactly what Biped.split_action
  # hard-fails on.
  assert "hip_pitch" not in action and "knee" not in action
  assert action["left_leg/hip_pitch"] == pytest.approx(mapper.to_motor_targets(
    ["L_hip_pitch_joint"], [0.1]
  )["left_leg"]["hip_pitch"])


def test_remote_motion_prefixes_ankle_pitch_roll_keys_too():
  """The ankle pair goes through an extra FK step (crank a1/a2 -> pitch/roll) before joining
  the action dict - confirm the prefix is applied to THOSE keys as well, not only the
  single-joint ones added earlier."""
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  motion, latest = _remote_motion(mapper)
  latest.put(JointTarget(
    t_ns=1, seq=1, joint_names=["L_crank_A_joint", "L_crank_B_joint"], q_target=[0.05, -0.05],
    arm_token="tok", origin="manual", ttl_ms=5000,
  ))
  action = motion(0.0, observation={})
  assert action is not None
  assert "left_leg/ankle_pitch" in action and "left_leg/ankle_roll" in action
  assert all(k.startswith("left_leg/") for k in action), action


def test_remote_motion_uses_a_different_action_prefix_than_the_mapper_side_when_they_differ():
  """The mapper/deadman side (the joint MAP's own limb key) and the biped action prefix (the
  actual ``Leg.id``) are usually equal, but this proves they are genuinely independent knobs -
  a legacy map's ``left`` grouping key still gets re-prefixed with whatever biped limb id the
  caller resolved (e.g. ``left_leg``), never the map's own spelling."""
  c = _contract()
  from pygviewer.bridge.huphy_udp import LEGACY_MAP_PATH
  from pygviewer.bridge.tx_map import JointTargetMapper

  legacy_mapper = JointTargetMapper(c, jmap=JointMap(LEGACY_MAP_PATH))  # groups under "left"
  motion, latest = _remote_motion(legacy_mapper, side="left", action_prefix="left_leg")
  latest.put(JointTarget(
    t_ns=1, seq=1, joint_names=["L_knee_joint"], q_target=[0.2], arm_token="tok", origin="manual",
    ttl_ms=5000,
  ))
  action = motion(0.0, observation={})
  assert set(action.keys()) == {"left_leg/knee"}
  assert "left/knee" not in action


# ---------------------------------------------------------------- idle refresh (2026-09-04)
# docs/123 section 11b: a real bench finding, not a bug in this file's prior logic - HUPHY's
# ControlLoop only updates a robot's observed state from the RESPONSE to a command it just
# sent (CONTROL mode never calls robot.refresh(), that is OBSERVE-only - control/loop.py:
# 257-275). Before this fix, RemoteMotion.__call__ returned None whenever nothing was armed
# yet, so literally no frame ever went out and every enabled joint's telemetry stayed frozen
# at the bus's pre-connect cache (all-zero) - even though the hardware was fully connected.
def test_idle_refresh_sends_zero_gain_action_for_enabled_joints_before_anything_is_armed():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  enable = {"L_hip_pitch_joint", "L_knee_joint"}  # 2 of the 6 side joints
  motion, latest = _remote_motion(mapper, enable=enable)

  action = motion(0.0, observation={})  # nothing ever put() into `latest` - phase is "idle"

  assert action is not None
  assert set(action.keys()) == {"left_leg/hip_pitch", "left_leg/knee"}
  assert motion.idle_refresh_count == 1
  motors = motion.leg.config.motors
  assert motors["hip_pitch"].gains.kp == 0.0 and motors["hip_pitch"].gains.kd == 0.0
  assert motors["knee"].gains.kp == 0.0 and motors["knee"].gains.kd == 0.0
  # never-enabled joints are untouched, not zeroed defensively - nothing was ever asked of them
  assert motors["hip_roll"].gains is None


def test_idle_refresh_never_includes_a_disabled_joint():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  motion, latest = _remote_motion(mapper, enable={"L_knee_joint"})

  action = motion(0.0, observation={})

  assert action is not None
  assert set(action.keys()) == {"left_leg/knee"}
  assert "left_leg/hip_pitch" not in action


def test_idle_refresh_uses_the_last_observed_position_never_a_synthesized_target():
  """Position is moot while kp=0, but this locks the SOURCE down: the observed pose, or 0.0
  if nothing has been observed yet - never default_q, which is exactly the "drive toward the
  default pose the instant the process connects, before anyone armed anything" swing this
  fix exists to NOT reintroduce (default_q for L_hip_pitch_joint is -0.175 rad in this
  contract - deliberately NOT what this test's observation or assertion use, so a regression
  that started reading default_q back in would be caught, not coincidentally pass)."""
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  motion, latest = _remote_motion(mapper, enable={"L_hip_pitch_joint", "L_knee_joint"})

  action = motion(0.0, observation={"left_leg/hip_pitch.pos": 0.42})  # knee: not observed yet

  assert action["left_leg/hip_pitch"] == pytest.approx(0.42)
  assert action["left_leg/knee"] == pytest.approx(0.0)


def test_idle_refresh_drops_an_unpaired_enabled_ankle_motor_and_warns():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  # only the A crank motor enabled, not B - HUPHY's ankle command is atomic (both or neither,
  # same rule split_motor_targets_into_action already applies on the live path)
  motion, latest = _remote_motion(mapper, enable={"L_crank_A_joint"})

  action = motion(0.0, observation={})

  assert action is None  # nothing else was enabled either, so there is nothing left to send
  assert any("ankle_a/ankle_b" in w for w in motion.warnings)


def test_idle_refresh_returns_none_when_nothing_is_enabled_on_this_side():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  motion, latest = _remote_motion(mapper, enable=set())  # empty --enable

  assert motion(0.0, observation={}) is None
  assert motion.idle_refresh_count == 0


def test_no_idle_refresh_flag_restores_the_old_send_nothing_before_arming_behaviour():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  motion, latest = _remote_motion(mapper, enable={"L_knee_joint"}, idle_refresh=False)

  assert motion(0.0, observation={}) is None
  assert motion.idle_refresh_count == 0


def test_idle_refresh_gains_never_leak_into_the_next_live_tick():
  """The instant a live target arrives, the gain path must be the message/default gain plan
  again - not still holding the zero gains the idle tick set. Torque-capable code sharing a
  path with a zero-gain safety frame is exactly the kind of thing that must never linger."""
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  motion, latest = _remote_motion(mapper, enable={"L_knee_joint"})

  idle_action = motion(0.0, observation={})
  assert idle_action is not None
  motors = motion.leg.config.motors
  assert motors["knee"].gains.kp == 0.0 and motors["knee"].gains.kd == 0.0

  latest.put(JointTarget(
    t_ns=1, seq=1, joint_names=["L_knee_joint"], q_target=[0.3], arm_token="tok",
    origin="manual", ttl_ms=5000,
  ))
  live_action = motion(1.0, observation={})

  assert live_action is not None and "left_leg/knee" in live_action
  motors = motion.leg.config.motors
  # back to this RemoteMotion's real default_kp/default_kd (5.0/0.5, _remote_motion's own
  # constants) - not 0, and not left over from the idle tick above.
  assert motors["knee"].gains.kp == pytest.approx(5.0)
  assert motors["knee"].gains.kd == pytest.approx(0.5)
  assert motion.idle_refresh_count == 1  # unchanged - the live tick did not count as idle


def test_stats_ticker_prints_idle_refresh_only_when_a_counter_fn_is_given(capsys):
  from pygviewer.bridge.huphy_remote_motion import _Receiver, _StatsTicker

  latest = LatestOnly(expected_arm_token="tok")
  recv = _Receiver("127.0.0.1", 0, latest, set())

  with_fn = _StatsTicker(latest, recv, idle_refresh_fn=lambda: 3)
  with_fn.print_once()
  assert "idle_refresh=3" in capsys.readouterr().out

  without_fn = _StatsTicker(latest, recv)  # dry-run's own construction - no such concept there
  without_fn.print_once()
  assert "idle_refresh=" not in capsys.readouterr().out


# ---------------------------------------------------------------- bench limb (2026-09-04)
def test_resolve_side_accepts_a_map_limb_name_that_is_not_left_or_right():
  """`joint_map_bench.json` labels the single bench RS03's row `limb: "bench"` (matching
  `bench_rs03_slcan.yaml`'s own limb key and the `bench/knee/...` telemetry keys
  `deploy/bench/bench_telemetry.py` emits). `side` is used downstream AS the map's limb key,
  so it must come back verbatim - the old hardcoded left/right list made `--limb bench` a
  hard ValueError, which is exactly what blocked the first bench TX bring-up."""
  from pygviewer.bridge.huphy_remote_motion import resolve_side, sim_joints_for_limb
  from pygviewer.bridge.huphy_udp import JointMap
  jmap = JointMap(str(Path(DEFAULT_MAP_PATH).parent / "joint_map_bench.json"))
  assert resolve_side("bench", jmap) == "bench"
  assert sim_joints_for_limb(jmap, "bench") == ["L_knee_joint"]


def test_resolve_side_keeps_the_historical_aliases_and_names_the_map_limbs_when_it_fails():
  from pygviewer.bridge.huphy_remote_motion import resolve_side
  from pygviewer.bridge.huphy_udp import JointMap
  jmap = JointMap(str(Path(DEFAULT_MAP_PATH).parent / "joint_map_bench.json"))
  assert resolve_side("left_leg", jmap) == "left"
  assert resolve_side("RIGHT", jmap) == "right"
  assert resolve_side("left") == "left"  # still works with no map at all
  with pytest.raises(ValueError, match="bench"):
    resolve_side("nosuchlimb", jmap)
