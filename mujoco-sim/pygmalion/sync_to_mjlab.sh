#!/bin/bash
# Apply our Pygmalion work onto a fresh mjlab clone.
# Usage: bash sync_to_mjlab.sh <path-to-mjlab>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MJ="${1:?usage: sync_to_mjlab.sh <path-to-mjlab>}"
[ -d "$MJ/src/mjlab" ] || { echo "ERROR: $MJ 는 mjlab clone이 아님"; exit 1; }

echo "[sync] robot -> $MJ/src/mjlab/asset_zoo/robots/pygmalion"
cp -r "$HERE/robot/robots_pygmalion" "$MJ/src/mjlab/asset_zoo/robots/pygmalion"
echo "[sync] task  -> $MJ/src/mjlab/tasks/velocity/config/pygmalion"
mkdir -p "$MJ/src/mjlab/tasks/velocity/config"
cp -r "$HERE/robot/task_velocity_pygmalion" "$MJ/src/mjlab/tasks/velocity/config/pygmalion"
echo "[sync] analysis -> $MJ/analysis"
mkdir -p "$MJ/analysis"; cp "$HERE"/analysis/* "$MJ/analysis/"

echo ""
echo "★ 남은 수동 작업 (robot/REGISTRATION.md 참조):"
echo "  1) src/mjlab/asset_zoo/robots/__init__.py 에 pygmalion import 2줄 추가"
echo "  2) tasks/velocity/config/__init__.py 가 pygmalion 서브패키지를 import 하는지 확인"
echo "  3) src/mjlab/sim/sim.py 의 ls_parallel 에 hasattr 가드 적용"
echo "  검증: (cd $MJ && uv run list-envs | grep Pygmalion)"
