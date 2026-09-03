"""CLI: serve the viewer, bake a model, or run a P3 telemetry bridge.

    ... tools/pygviewer/run.py --variant LegOnly-AB --port 8094 --api-port 8095
    ... tools/pygviewer/run.py bake model --all
    ... tools/pygviewer/run.py --variant LegOnly-AB --headless --seconds 5   # rate check
    ... tools/pygviewer/run.py bridge huphy --variant LegOnly-AB --port 9871
    ... tools/pygviewer/run.py bridge dummy --pattern sine --target ws,udp
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time

from . import CACHE_DIR, VARIANTS


def port_free(port: int, host: str = "0.0.0.0") -> bool:
  """Refuse to start on a port someone else owns (same check tools/quartz/run.sh makes)."""
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  try:
    s.bind((host, port))
    return True
  except OSError:
    return False
  finally:
    s.close()


def lan_ip() -> str:
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]
  except OSError:
    return "127.0.0.1"
  finally:
    s.close()


def main(argv: list[str] | None = None) -> int:
  argv = list(sys.argv[1:] if argv is None else argv)
  if argv and argv[0] == "bake":
    from .bake import main as bake_main

    return bake_main(argv[1:])
  if argv and argv[0] == "bridge":
    if len(argv) < 2 or argv[1] not in ("huphy", "dummy"):
      print("usage: run.py bridge {huphy,dummy} ...", file=sys.stderr)
      return 2
    if argv[1] == "huphy":
      from .bridge.huphy_udp import main as huphy_main

      return huphy_main(argv[2:])
    from .bridge.dummy_tx import main as dummy_main

    return dummy_main(argv[2:])

  ap = argparse.ArgumentParser(prog="pygviewer", description=__doc__)
  ap.add_argument("--variant", default="LegOnly-AB", choices=list(VARIANTS))
  ap.add_argument("--cache", default=CACHE_DIR)
  ap.add_argument("--port", type=int, default=8094, help="viser (3D scene + panel)")
  ap.add_argument("--api-port", type=int, default=8095, help="FastAPI (REST/WS, /docs)")
  ap.add_argument("--host", default="0.0.0.0")
  ap.add_argument("--headless", action="store_true", help="no viser, no API: rate check only")
  ap.add_argument("--seconds", type=float, default=5.0, help="--headless duration")
  ap.add_argument("--stale-ok", action="store_true", help="run on a contract whose sources moved")
  ap.add_argument("--no-api", action="store_true")
  ap.add_argument(
    "--base",
    default="fixed",
    choices=("free", "fixed", "pivot", "string"),
    help="base mode at startup. 'fixed' by default: with nothing balancing it a passive "
    "biped topples in ~2 s, which is a poor first screen for a joint inspector. Switch to "
    "'free' in the panel (or here) for real standing dynamics; 'string' hangs a safety "
    "tether that only engages below --string-z-set.",
  )
  ap.add_argument(
    "--string-z-set", type=float, default=None,
    help="--base string only: catch height [m]; default is this model's spawn_base_z",
  )
  ap.add_argument(
    "--string-follow-xy", action="store_true",
    help="--base string only: anchor tracks the base's (x,y) every tick (no swing) instead "
    "of staying fixed at the (x,y) the mode was entered at",
  )
  ap.add_argument("--keyframe", default="knees_bent", choices=("home", "knees_bent"))
  ap.add_argument(
    "--shadow-follow", action="store_true",
    help="policy_shadow: let the shadow action step the LOCAL sim (never a real robot). "
    "Off by default: policy_shadow only observes+displays.",
  )
  args = ap.parse_args(argv)

  os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # the GPU belongs to the trainer

  from .contract import load_contract
  from .sim_core import SimCore

  c = load_contract(args.cache, args.variant)
  fresh = c.freshness()
  if fresh["stale"]:
    msg = f"contract for {args.variant} is STALE: {fresh['checks']}"
    if not args.stale_ok:
      print(msg + "\nRe-bake, or pass --stale-ok to run anyway.", file=sys.stderr)
      return 3
    print("WARNING: " + msg, file=sys.stderr)

  core = SimCore(c, shadow_follow=args.shadow_follow)
  core.reset(args.keyframe)
  if args.base != "free":
    base_kwargs = dict(mode=args.base)
    if args.base == "string":
      if args.string_z_set is not None:
        base_kwargs["z_set"] = args.string_z_set
      base_kwargs["follow_xy"] = args.string_follow_xy
    core.set_base(**base_kwargs)

  if args.headless:
    t0 = time.perf_counter()
    core.run_blocking(args.seconds)
    el = time.perf_counter() - t0
    s = core.snapshot()
    from .api import rss_mb

    print(
      f"HEADLESS {args.variant}  {el:.2f} s wall  physics {s['rates']['phys_steps']} steps "
      f"= {s['rates']['phys_steps'] / el:.1f} Hz  ctrl {s['rates']['ctrl_hz']:.1f} Hz  "
      f"drops {s['rates']['drops']}  RSS {rss_mb():.0f} MB  sim_time {s['t']:.3f} s"
    )
    return 0

  for p, what in ((args.port, "viser"), (args.api_port, "api")):
    if not args.no_api or what == "viser":
      if not port_free(p):
        print(f"port {p} ({what}) is already in use - refusing to start", file=sys.stderr)
        return 4

  core.start()
  ip = lan_ip()

  api_thread = None
  if not args.no_api:
    import uvicorn

    from .api import build_app

    app = build_app(core, fresh)
    cfg = uvicorn.Config(
      app, host=args.host, port=args.api_port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(cfg)
    api_thread = threading.Thread(target=server.run, name="pygviewer-api", daemon=True)
    api_thread.start()

  from .ui import build_ui

  server_v = build_ui(core, host=args.host, port=args.port, freshness=fresh, base=args.base)
  print(f"pygviewer {args.variant}", flush=True)
  print(f"  viser  http://{ip}:{args.port}", flush=True)
  if not args.no_api:
    print(f"  api    http://{ip}:{args.api_port}/docs", flush=True)
  try:
    while True:
      time.sleep(1.0)
  except KeyboardInterrupt:
    pass
  finally:
    core.stop()
    try:
      server_v.stop()
    except Exception:
      pass
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
