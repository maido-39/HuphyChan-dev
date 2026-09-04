#!/usr/bin/env bash
# bootstrap_robot_host.sh — install HUPHY on the ROBOT host and run READ-ONLY bench checks.
#
# Runs ON the robot host (e.g. syaro@10.8.0.14). Idempotent. Never moves a motor:
# the only CAN traffic it generates is a passive `candump` listen. Manual motor control is
# a separate, explicitly armed step (see README_robot_host.md §9) done with the user present.
#
#   bash bootstrap_robot_host.sh            # install + checks
#   bash bootstrap_robot_host.sh --checks   # checks only (no install)
#
# Env overrides: ROOT (default /home/syaro/Human-Pygmalion), CAN_IF (default can0),
#                HUPHY_URL (default https://github.com/Human-Pygmalion/HUPHY)
set -uo pipefail
ROOT="${ROOT:-/home/syaro/Human-Pygmalion}"
CAN_IF="${CAN_IF:-can0}"
HUPHY_URL="${HUPHY_URL:-https://github.com/Human-Pygmalion/HUPHY}"
HUPHY_DIR="$ROOT/HUPHY"
VENV="$ROOT/.venv-huphy"
ONLY_CHECKS=0; [ "${1:-}" = "--checks" ] && ONLY_CHECKS=1
say(){ printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
warn(){ printf '\033[1;33m!! %s\033[0m\n' "$*"; }

say "host"; hostname; uname -sr; id -un
say "python"; command -v python3 && python3 --version || { warn "python3 missing — install python3 (>=3.9) first"; exit 1; }
PYV=$(python3 -c 'import sys; print(sys.version_info >= (3,9))'); [ "$PYV" = "True" ] || { warn "python >= 3.9 required"; exit 1; }

if [ "$ONLY_CHECKS" = 0 ]; then
  say "install HUPHY into $HUPHY_DIR"
  mkdir -p "$ROOT"
  if [ -d "$HUPHY_DIR/.git" ]; then (cd "$HUPHY_DIR" && git fetch -q && git status -sb | head -1); else git clone -q "$HUPHY_URL" "$HUPHY_DIR" || { warn "git clone failed (network/auth?)"; exit 1; }; fi
  (cd "$HUPHY_DIR" && git log -1 --format='HUPHY @ %h %s (%cd)' --date=short)
  say "venv $VENV"
  # Ubuntu without python3-venv (no sudo on the bench VM): fall back to a --user virtualenv,
  # which bundles pip and needs no ensurepip. Verified on 10.8.0.14 (2026-09-04).
  if [ ! -d "$VENV" ]; then
    if ! python3 -m venv "$VENV" 2>/dev/null; then
      warn "python3 -m venv failed (python3-venv not installed) — using virtualenv --user fallback"
      rm -rf "$VENV"
      python3 -m pip --version >/dev/null 2>&1 || { curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && python3 /tmp/get-pip.py --user -q; }
      export PATH="$HOME/.local/bin:$PATH"
      python3 -m pip install --user -q virtualenv && python3 -m virtualenv -q "$VENV" || { warn "virtualenv fallback failed"; exit 1; }
    fi
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  pip -q install --upgrade pip >/dev/null 2>&1 || true
  (cd "$HUPHY_DIR" && pip -q install -e '.[imu]' && pip -q install python-can) || { warn "pip install failed (offline? try pip download on a networked box)"; exit 1; }
  say "entry points"; for e in huphy-test huphy-commission huphy-bringup huphy-run huphy-imu; do command -v "$e" >/dev/null && echo "  $e: ok" || echo "  $e: MISSING"; done
else
  [ -d "$VENV" ] && source "$VENV/bin/activate"
fi

say "USB-CAN adapter"
lsusb 2>/dev/null | grep -iE 'can|peak|kvaser|canable|gs_usb|candlelight|slcan|CP210|CH340' || warn "no obvious USB-CAN device in lsusb (check cable/driver)"
say "CAN interfaces"
ip -details link show type can 2>/dev/null || warn "no socketcan interface — for gs_usb/candleLight: 'sudo modprobe gs_usb'; for slcan (CANable in serial mode): 'sudo slcand -o -c -s8 /dev/ttyACM0 can0'"
if ip link show "$CAN_IF" >/dev/null 2>&1; then
  ST=$(ip -details link show "$CAN_IF" | grep -oE 'state [A-Z-]+|bitrate [0-9]+' | tr '\n' ' '); echo "$CAN_IF: $ST"
  echo "$ST" | grep -q 'state UP' || warn "$CAN_IF is DOWN — bring up with: sudo ip link set $CAN_IF up type can bitrate 1000000"
else
  warn "$CAN_IF not present"
fi
say "can-utils"; command -v candump >/dev/null && echo "candump: ok" || warn "candump missing — sudo apt install can-utils"

say "passive listen 3 s on $CAN_IF (READ-ONLY; RobStride motors are silent until polled, so 0 frames is normal)"
if command -v candump >/dev/null && ip link show "$CAN_IF" 2>/dev/null | grep -q UP; then
  timeout 3 candump -n 20 "$CAN_IF" 2>/dev/null | head -20 || true
fi

say "HUPHY self-test (no CAN traffic)"
command -v huphy-test >/dev/null && (cd "$HUPHY_DIR" && huphy-test 2>&1 | tail -15) || warn "huphy-test not on PATH (activate $VENV)"

say "HUPHY config + calibration"
ls "$HUPHY_DIR"/config/*.yaml "$HUPHY_DIR"/config/calibration/*.json 2>/dev/null
grep -nE 'channel:|interface:|model: RS0|kp:|kd:' "$HUPHY_DIR/config/robot_v1.0.yaml" 2>/dev/null | head -20

say "DONE — next: README_robot_host.md §9 (one motor, kp<=5, user present at the bench)."
