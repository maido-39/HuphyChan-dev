#!/usr/bin/env bash
# bench_scan.sh — find which CAN id(s) answer on the bench bus by pinging ALL ids 1..127.
#
# `huphy-commission scan` only pings the ids listed in its config, so this generates a
# throw-away config that lists every id (all as RS03 - the model only affects value
# decoding, not the ping) and runs the scan. The ping is a STOP frame: harmless for an
# idle motor (it is the same frame `scan` always uses). ~13 s at the default 0.1 s timeout.
#
#   source /home/syaro/Human-Pygmalion/.venv-huphy/bin/activate
#   bash bench_scan.sh [can0]
set -uo pipefail
# Usage: bash bench_scan.sh [channel] [interface]
#   socketcan: bash bench_scan.sh can0
#   slcan (CANable canable-fw, no sudo): CAN_BITRATE=1000000 bash bench_scan.sh /dev/ttyACM0 slcan
CH="${1:-can0}"
IFACE="${2:-socketcan}"
[ "$IFACE" = "slcan" ] && export CAN_BITRATE="${CAN_BITRATE:-1000000}"
TMP=$(mktemp /tmp/huphy_scan_XXXX.yaml)
{
  echo "name: scan"
  echo "safety: {command_margin_deg: 3.0, max_delta_deg: 20.0, enforce_limits: false}"
  echo "telemetry: {host: '', port: 9870, csv_path: null, csv_flush_every: 50}"
  echo "imus: {}"
  echo "limbs:"
  echo "  scan:"
  echo "    kind: leg"
  echo "    side: left"
  echo "    channel: $CH"
  echo "    interface: $IFACE"
  echo "    control_hz: 100.0"
  echo "    motors:"
  for i in $(seq 1 127); do printf "      m%d: {id: %d, model: RS03, kp: 5.0, kd: 0.5}\n" "$i" "$i"; done
} > "$TMP"
if [ "$IFACE" = "socketcan" ]; then ip -details link show "$CH" 2>/dev/null | grep -qE 'state UP|UP,' || { echo "!! $CH is not UP — run: sudo ip link set $CH up type can bitrate 1000000"; exit 1; }; else [ -e "$CH" ] || { echo "!! $CH missing"; exit 1; }; fi
echo "== scanning ids 1..127 on $CH (STOP-frame ping, read-only for an idle motor) =="
huphy-commission --config "$TMP" --limb scan scan 2>&1 | grep -vE "응답 없는 모터|WARNING"
rm -f "$TMP"
