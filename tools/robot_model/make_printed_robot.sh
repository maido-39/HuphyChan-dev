#!/bin/bash
# One command from "the Fusion URDF-export copy is the active document" to a validated
# URDF + MJCF + domain-randomization ranges. Re-run it whenever the measurements change:
# edit tools/robot_model/alu_parts_measured.json, re-apply the densities, run this.
#
#   tools/robot_model/make_printed_robot.sh [tag]        (default tag: pygmalion_v3_printed)
#
# Stages (each writes where the next reads; all paths printed):
#   1 dump_bodies      Fusion active doc -> bodies_<tag>.json   (mass, COM, inertia per body,
#                      hidden bodies flagged)                              [needs the MCP tunnel]
#   2 massprops        bodies -> robot_massprops_<tag>.json   (rigid bodies, catalogue
#                      motor masses asserted, alternative branches excluded)
#   3 build_robot      massprops + meshes + measured ROM -> <tag>.urdf / <tag>.xml
#   4 validate_robot   mass, geometry, L/R conventions, joint sweeps, inertia readback, figures
#   5 mass_dr          per-body uncertainty -> per-link mass/COM/inertia ranges -> mass_dr.json
#                      (read by mjlab when PYG_INERTIAL_DR=1)
# Stage 0 (not in this script, run first when the survey changed):
#   tools/robot_model/alu_parts_ratio.py           ratio statistics from the measured sheet
#   tools/fusion/set_printed_density.py --apply    writes the densities into the export copy
set -euo pipefail
cd "$(dirname "$0")/../.."
TAG="${1:-pygmalion_v3_printed}"
V=mujoco-sim/mjlab/.venv/bin/python3
F=/home/syaro/pyg_fea/fusion
export PYG_BODIES="$F/bodies_${TAG#pygmalion_}.json"
export PYG_MASSPROPS="$F/robot_massprops_${TAG#pygmalion_}.json"

EXPECT="${PYG_EXPORT_DOC:-260819_HumanMesh_wUpper_URDFexport}"
echo "== 1/5 dump bodies from the active Fusion document (must be $EXPECT*)"
$V tools/fusion/dump_bodies.py "$PYG_BODIES" | tee /tmp/pyg_dump.log
grep -q "document : $EXPECT" /tmp/pyg_dump.log || { echo "!! the active Fusion document is not the URDF-export copy - open it and re-run"; exit 2; }
echo "== 2/5 aggregate rigid-body mass properties"
$V tools/robot_model/massprops_fusion.py | tail -4
echo "== 3/5 build URDF + MJCF  ($TAG)"
$V tools/robot_model/build_robot.py --massprops="$PYG_MASSPROPS" --tag="$TAG" | head -3
echo "== 4/5 validate"
$V tools/robot_model/validate_robot.py --tag="$TAG" --massprops="$PYG_MASSPROPS" | grep -E "total |standing base|sign conventions|self-contact samples [1-9]|Traceback" || true
echo "== 5/5 domain-randomization ranges"
$V tools/robot_model/mass_dr.py --bodies="$PYG_BODIES" --samples=3000 | tail -13
echo "== done: $TAG"
