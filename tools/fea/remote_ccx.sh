#!/usr/bin/env bash
# Dispatch one CalculiX job to the Windows workstation over the reverse tunnel.
#
# Prereq (run once on Windows, admin PowerShell):
#   Start-Service sshd
#   ssh -N -R 2222:localhost:22 -o ServerAliveInterval=30 syaro@192.168.20.177
# and CalculiX for Windows unpacked at C:\ccx\ccx.exe (or set CCX_WIN).
#
# Usage: remote_ccx.sh <job_dir> <job_name> [threads]
# Copies <job>.inp over, solves there, brings <job>.frd/.dat/.sta back.
set -euo pipefail

JOB_DIR="$1"; JOB="$2"; THREADS="${3:-8}"
WIN_USER="${WIN_USER:-syaro}"
WIN_PORT="${WIN_PORT:-2222}"
CCX_WIN="${CCX_WIN:-/c/ccx/ccx.exe}"
REMOTE_DIR="${REMOTE_DIR:-/c/pyg_fea}"

ssh -p "$WIN_PORT" -o ConnectTimeout=8 "$WIN_USER@localhost" "mkdir -p $REMOTE_DIR/$JOB" \
  || { echo "tunnel down (port $WIN_PORT) - start the reverse tunnel on Windows first" >&2; exit 2; }

echo "-> uploading $JOB.inp ($(du -h "$JOB_DIR/$JOB.inp" | cut -f1))"
scp -P "$WIN_PORT" -q "$JOB_DIR/$JOB.inp" "$WIN_USER@localhost:$REMOTE_DIR/$JOB/"

echo "-> solving on Windows with $THREADS threads"
ssh -p "$WIN_PORT" "$WIN_USER@localhost" \
  "cd $REMOTE_DIR/$JOB && OMP_NUM_THREADS=$THREADS CCX_NPROC_EQUATION_SOLVER=$THREADS $CCX_WIN -i $JOB" \
  | tail -20

echo "-> fetching results"
scp -P "$WIN_PORT" -q "$WIN_USER@localhost:$REMOTE_DIR/$JOB/$JOB.frd" "$JOB_DIR/" || true
scp -P "$WIN_PORT" -q "$WIN_USER@localhost:$REMOTE_DIR/$JOB/$JOB.sta" "$JOB_DIR/" || true
scp -P "$WIN_PORT" -q "$WIN_USER@localhost:$REMOTE_DIR/$JOB/$JOB.dat" "$JOB_DIR/" || true
ls -la "$JOB_DIR/$JOB.frd"
