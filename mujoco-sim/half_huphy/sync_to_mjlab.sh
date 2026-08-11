#!/bin/bash
# Apply Half Huphy balance/jump work onto an mjlab clone.
# Usage: bash sync_to_mjlab.sh <path-to-mjlab>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MJ="${1:?usage: sync_to_mjlab.sh <path-to-mjlab>}"
[ -d "$MJ/src/mjlab" ] || { echo "ERROR: $MJ 는 mjlab clone이 아님"; exit 1; }

echo "[sync] robot -> $MJ/src/mjlab/asset_zoo/robots/half_huphy"
rm -rf "$MJ/src/mjlab/asset_zoo/robots/half_huphy"
cp -a "$HERE/robots_half_huphy" "$MJ/src/mjlab/asset_zoo/robots/half_huphy"

echo "[sync] tasks -> $MJ/src/mjlab/tasks/half_huphy"
rm -rf "$MJ/src/mjlab/tasks/half_huphy"
cp -a "$HERE/tasks_half_huphy" "$MJ/src/mjlab/tasks/half_huphy"

INIT="$MJ/src/mjlab/asset_zoo/robots/__init__.py"
if ! grep -q 'half_huphy.half_huphy_constants' "$INIT"; then
  echo "[sync] patch robot registration in asset_zoo/robots/__init__.py"
  python3 - "$INIT" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
block = """from mjlab.asset_zoo.robots.half_huphy.half_huphy_constants import (
  HALF_HUPHY_ACTION_SCALE as HALF_HUPHY_ACTION_SCALE,
)
from mjlab.asset_zoo.robots.half_huphy.half_huphy_constants import (
  get_half_huphy_robot_cfg as get_half_huphy_robot_cfg,
)
"""
if "HALF_HUPHY_ACTION_SCALE" in text:
    sys.exit(0)
path.write_text(block + text)
print("  inserted half_huphy imports at top of", path)
PY
else
  echo "[sync] robot registration already present"
fi

if [ -d "$HERE/weights" ]; then
  echo "[sync] weights -> $MJ/weights/half_huphy"
  mkdir -p "$MJ/weights"
  rm -rf "$MJ/weights/half_huphy"
  cp -a "$HERE/weights" "$MJ/weights/half_huphy"
fi

echo ""
echo "★ 검증:"
echo "  (cd $MJ && uv sync && uv run list-envs | grep -E 'HalfHuphy|Balance-Half|Jump')"
echo "★ 학습 예:"
echo "  uv run train Mjlab-Balance-HalfHuphy --env.scene.num-envs 4096"
echo "  uv run train Mjlab-JumpKneeAnkle14-HalfHuphy --env.scene.num-envs 4096"
echo "★ play 예 (weights sync 후):"
echo "  uv run play Mjlab-JumpKneeAnkle14-HalfHuphy \\"
echo "    --checkpoint-file weights/half_huphy/jump_knee_ankle14/model_29999.pt \\"
echo "    --num-envs 1 --viewer native"
echo "  상세: $HERE/README.md / $HERE/weights/WEIGHTS.md"
