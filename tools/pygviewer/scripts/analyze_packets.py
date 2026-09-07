#!/usr/bin/env python3
"""Reconstruct a bench session from the packet logs.

2026-09-07, user: "시뮬로는 검증이 안되는게 너무 많아. 입/출력을 패킷 / debug 레벨로
로깅하고 분석해."

Two joint movements on the bench could not be explained after the fact (docs/127 section 8),
because nothing kept the individual commands - only the newest one, which is wiped whenever
the transmit client is rebuilt. `packet_log.py` now records both directions; this reads them
back and answers the questions that were unanswerable:

  * what target did each packet carry, and how far was it from the measured pose
  * where did a joint actually move, and which packet was in flight when it started
  * did the commanded value ever jump, and by how much between consecutive packets
  * what did the robot report about the link at that moment

Usage
-----
    analyze_packets.py --tx tx.jsonl [--rx rx.jsonl] [--joint L_hip_yaw_joint]
    analyze_packets.py --tx tx.jsonl --moves          # only where something moved
    analyze_packets.py --tx tx.jsonl --around 1234.5  # a window either side of a wall clock

Everything is printed in degrees, because that is the unit the bench is discussed in, and
every line carries the raw values it was derived from so nothing has to be taken on trust.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

MOVE_DEG = 0.5
"""What counts as "the joint moved" between consecutive packets. Below this is sensor noise
and settling; the bench's resting jitter is well under 0.1 deg."""

JUMP_DEG = 1.0
"""What counts as "the command jumped" between consecutive packets. At 50 Hz a deliberate
slider drag advances far less than this per packet."""


def read(path: Path) -> list[dict]:
  out = []
  with path.open(encoding="utf-8") as fh:
    for n, line in enumerate(fh, 1):
      line = line.strip()
      if not line:
        continue
      try:
        out.append(json.loads(line))
      except json.JSONDecodeError as e:
        print(f"{path}:{n}: skipped unparsable line ({e})", file=sys.stderr)
  return out


def deg(v):
  return None if v is None else math.degrees(v)


def fmt(v, w=8, p=2):
  return " " * w if v is None else f"{v:{w}.{p}f}"


def tx_rows(records, joint=None):
  """One row per (packet, joint): sequence, command, measurement, and the gap between them."""
  rows = []
  for r in records:
    if r.get("kind") != "tx":
      continue
    names = r.get("joints") or []
    for i, n in enumerate(names):
      if joint and n != joint:
        continue
      rows.append({
        "t_wall": r["t_wall"], "t_mono": r["t_mono"], "seq": r.get("seq"),
        "joint": n,
        "target": deg(r["q_target"][i]),
        "measured": deg((r.get("measured") or [None]*len(names))[i]),
        "kp": (r.get("kp") or [None]*len(names))[i],
        "kd": (r.get("kd") or [None]*len(names))[i],
      })
  return rows


def summarise(rows, joint_filter=None):
  by_joint = {}
  for r in rows:
    by_joint.setdefault(r["joint"], []).append(r)
  for n, rs in sorted(by_joint.items()):
    if joint_filter and n != joint_filter:
      continue
    tgt = [r["target"] for r in rs if r["target"] is not None]
    mea = [r["measured"] for r in rs if r["measured"] is not None]
    err = [r["target"] - r["measured"] for r in rs
           if r["target"] is not None and r["measured"] is not None]
    print(f"\n=== {n} · {len(rs)} packets ===")
    if tgt:
      print(f"  commanded  min {min(tgt):8.2f}  max {max(tgt):8.2f}  first {tgt[0]:8.2f}"
            f"  last {tgt[-1]:8.2f}  (deg)")
    if mea:
      print(f"  measured   min {min(mea):8.2f}  max {max(mea):8.2f}  first {mea[0]:8.2f}"
            f"  last {mea[-1]:8.2f}  (deg)")
      print(f"  the joint moved {abs(mea[-1] - mea[0]):.2f} deg over this log")
    if err:
      big = max(err, key=abs)
      print(f"  command minus measured: largest {big:+.2f} deg"
            f"  (zero error = commanding it to stay put)")
    kps = {r["kp"] for r in rs if r["kp"] is not None}
    if kps:
      print(f"  kp actually sent: {sorted(kps)}")


def moves(rows):
  """Every packet where the measurement or the command changed materially, with what was in
  flight at that moment - the "which packet was it" question."""
  prev = {}
  hits = []
  for r in rows:
    p = prev.get(r["joint"])
    prev[r["joint"]] = r
    if p is None:
      continue
    dm = None if (r["measured"] is None or p["measured"] is None) else r["measured"] - p["measured"]
    dt = None if (r["target"] is None or p["target"] is None) else r["target"] - p["target"]
    if (dm is not None and abs(dm) >= MOVE_DEG) or (dt is not None and abs(dt) >= JUMP_DEG):
      hits.append((r, dm, dt))
  if not hits:
    print(f"\nno step larger than {MOVE_DEG} deg (measured) / {JUMP_DEG} deg (commanded)")
    return
  print(f"\n=== steps over {MOVE_DEG} deg measured or {JUMP_DEG} deg commanded ===")
  print(f"{'wall':>14} {'seq':>7} {'joint':<20} {'cmd':>8} {'meas':>8} {'d_cmd':>8} {'d_meas':>8}")
  for r, dm, dt in hits:
    print(f"{r['t_wall']:14.3f} {str(r['seq']):>7} {r['joint']:<20} "
          f"{fmt(r['target'])} {fmt(r['measured'])} {fmt(dt)} {fmt(dm)}")


def link_counters(rx_records):
  """The robot's own accept/reject counts, as they changed through the log."""
  seen = []
  for r in rx_records:
    if r.get("kind") != "rx":
      continue
    pay = r.get("payload") or {}
    got = {k.split("/", 1)[1]: v for k, v in pay.items() if k.startswith("link/")}
    if got and (not seen or got != seen[-1][1]):
      seen.append((r["t_wall"], got))
  if not seen:
    return
  print("\n=== robot link counters (only when they changed) ===")
  for t, c in seen:
    print(f"  {t:14.3f}  accepted {int(c.get('accepted', 0)):6d}"
          f"  rejected_seq {int(c.get('rejected_seq', 0)):5d}"
          f"  token {int(c.get('rejected_arm_token', 0)):3d}"
          f"  contract {int(c.get('rejected_contract', 0)):3d}"
          f"  parse {int(c.get('parse_errors', 0)):3d}")


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--tx", type=Path, required=True, help="PYG_TX_LOG file (what we sent)")
  ap.add_argument("--rx", type=Path, help="PYG_RX_LOG file (what the robot sent)")
  ap.add_argument("--joint", help="restrict to one joint")
  ap.add_argument("--moves", action="store_true", help="only the steps, not the summary")
  ap.add_argument("--around", type=float,
                  help="wall-clock second to centre a window on")
  ap.add_argument("--window", type=float, default=5.0, help="half-width of --around, seconds")
  a = ap.parse_args(argv)

  tx = read(a.tx)
  rows = tx_rows(tx, a.joint)
  if a.around is not None:
    lo, hi = a.around - a.window, a.around + a.window
    rows = [r for r in rows if lo <= r["t_wall"] <= hi]
    print(f"window {lo:.3f} .. {hi:.3f} ({len(rows)} joint-packets)")
  if not rows:
    print("no transmitted packets in this log/window - nothing was being sent")
  if not a.moves:
    summarise(rows, a.joint)
  moves(rows)
  if a.rx and a.rx.exists():
    link_counters(read(a.rx))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
