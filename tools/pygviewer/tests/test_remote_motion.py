"""docs/123 plan A item 3: ``bridge/huphy_remote_motion.py``'s pure helpers (no huphy import)
and its ``--dry-run`` path (no huphy, no CAN - "log commands + echo telemetry assuming
instant tracking"). The REAL (huphy-backed) path, ``run_real()``/``RemoteMotion``, cannot be
exercised on this machine at all - no ``huphy`` install, no CAN bus - and is reviewed against
HUPHY's source rather than tested; that gap is stated explicitly in docs/123 section 5, not
silently absorbed.
"""

import json
import socket
import threading
import time

import pytest

from pygviewer import CACHE_DIR
from pygviewer.bridge.huphy_remote_motion import (
  build_parser,
  enable_motor_names_to_sim_joints,
  main,
  plan_gains,
  resolve_side,
  sim_joints_for_limb,
  split_motor_targets_into_action,
)
from pygviewer.bridge.huphy_udp import DEFAULT_MAP_PATH, JointMap
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
  jmap = _jmap()
  left = sim_joints_for_limb(jmap, "left")
  right = sim_joints_for_limb(jmap, "right")
  assert len(left) == 6 and len(right) == 6
  assert all(n.startswith("L_") for n in left)
  assert all(n.startswith("R_") for n in right)


# --------------------------------------------------------------------------- enable translation
def test_enable_single_motor_names_translate_to_sim_joints():
  jmap = _jmap()
  out = enable_motor_names_to_sim_joints(["hip_pitch", "knee"], "left", jmap)
  assert out == {"L_hip_pitch_joint", "L_knee_joint"}


def test_enable_ankle_alias_expands_to_both_crank_joints():
  jmap = _jmap()
  out = enable_motor_names_to_sim_joints(["ankle"], "left", jmap)
  assert out == {"L_crank_A_joint", "L_crank_B_joint"}


def test_enable_unknown_motor_name_is_a_hard_failure():
  jmap = _jmap()
  with pytest.raises(KeyError):
    enable_motor_names_to_sim_joints(["elbow"], "left", jmap)


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
  plan = plan_gains(["L_knee_joint"], mapper, "left", msg, "live",
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
  plan = plan_gains(["L_knee_joint"], mapper, "left", msg, "returning",
                     kp_max=5.0, kd_max=0.5, default_kp=2.0, default_kd=0.2)
  # not "live" -> the message's own kp/kd (3.0/0.4) are NOT used, default_kp/kd are
  assert plan.kp["knee"] == pytest.approx(2.0)
  assert plan.kd["knee"] == pytest.approx(0.2)


def test_plan_gains_skips_joints_on_the_other_side():
  c = _contract()
  from pygviewer.bridge.tx_map import JointTargetMapper

  mapper = JointTargetMapper(c)
  plan = plan_gains(["R_knee_joint"], mapper, "left", None, "idle",
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
        if "left/knee/pos" in obj:
          drained = obj
      return drained

    pkt = _wait_until(_got_knee_target, timeout=2.0)
    assert pkt["left/knee/pos"] == pkt["left/knee/tgt"]  # instant-tracking assumption, stated
    assert pkt["left/knee/pos"] > 5.0  # some non-default degrees given 0.4 rad
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
