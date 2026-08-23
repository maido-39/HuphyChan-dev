#!/bin/bash
# One command from "the Fusion URDF-export copy is the active document" to a validated
# URDF + MJCF + domain-randomization ranges. Re-run it whenever the measurements change:
# edit tools/robot_model/alu_parts_measured.json, re-apply the densities, run this.
#
#   tools/robot_model/make_printed_robot.sh [tag]        (default tag: pygmalion_v3_printed)
#
# Stages (each writes where the next reads; all paths printed):
#   1 dump_bodies      Fusion active doc -> bodies_<tag>.json   (mass, COM, inertia, bbox per
#                      body, hidden bodies flagged; refused unless the doc is the export copy)
#   2 massprops        bodies -> robot_massprops_<tag>.json   (rigid bodies, catalogue
#                      motor masses asserted, alternative branches excluded)
#   3 motor_proxies    bodies -> motor_proxies_<tag>.json     (actuator cylinder centre/axis/size
#                      from the SAME dump, so the drawn motor sits where its mass is)
#   4 build_robot      massprops + proxies + meshes + measured ROM -> <tag>.urdf / <tag>.xml
#   5 validate_robot   mass, geometry, L/R conventions, joint sweeps, inertia readback, figures
#   6 mass_dr          per-body uncertainty -> per-link mass/COM/inertia ranges -> mass_dr.json
#                      (read by mjlab when PYG_INERTIAL_DR=1)
# Not in this script (slow, geometry-only, run when the CAD shape changes): rom_check.py ->
# rom_measured.json, which stage 4 REQUIRES. Meshes likewise (meshes_step.py /
# upper_meshes_fusion.py).
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
export PYG_MOTOR_PROXIES="$F/motor_proxies_${TAG#pygmalion_}.json"
ROM="$F/rom_measured.json"
[ -f "$ROM" ] || { echo "!! $ROM missing - run tools/robot_model/rom_check.py first (slow, only when the geometry changed)"; exit 3; }
echo "== 1/6 dump bodies from the active Fusion document (refused before writing unless it is $EXPECT*)"
$V tools/fusion/dump_bodies.py "$PYG_BODIES" --expect="$EXPECT"
echo "== 2/6 aggregate rigid-body mass properties"
$V tools/robot_model/massprops_fusion.py | tail -4
echo "== 3/6 actuator cylinders (centre, axis, size) from the SAME dump"
$V tools/robot_model/motor_proxies_fusion.py | tail -3
echo "== 4/6 build URDF + MJCF  ($TAG)"
$V tools/robot_model/build_robot.py --massprops="$PYG_MASSPROPS" --tag="$TAG" | head -3
echo "== 5/6 validate"
$V tools/robot_model/validate_robot.py --tag="$TAG" --massprops="$PYG_MASSPROPS" | grep -E "total |standing base|sign conventions|self-contact samples [1-9]|Traceback" || true
echo "== 6/6 domain-randomization ranges"
$V tools/robot_model/mass_dr.py --bodies="$PYG_BODIES" --samples=3000 | tail -13
echo "== done: $TAG"
