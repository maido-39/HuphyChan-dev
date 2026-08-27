#!/usr/bin/env bash
# PhysX contact/solver sweep - one knob at a time, everything else held fixed.
#
# Each arm is a full 45 s bundleD1_RP rollout on pygmalion_v3_printed.usd at 1.6 m/s,
# measured by tools/sim2sim/isaac_grf_rollout.py with its three built-in calibrations
# (dt identity, mean support = 1 BW, net-vs-filtered). ~37 s wall each.
#
# The baseline arm re-runs with no knob set and reproduces the committed result BIT FOR
# BIT (vx_err 0.13858409302325575, 101 strikes, peak 2.4713 BW). The rollout is
# deterministic - one env, no domain randomisation, fixed ONNX policy - so run-to-run
# variance is exactly zero and every delta below is signal.
#
# COMPLIANT CONTACT, WHERE THE NUMBERS COME FROM
#   MuJoCo solref = (0.02, 1) -> timeconst tau = 0.02 s, damping ratio zeta = 1, i.e. a
#   critically damped MASS-NORMALISED spring-damper:
#       k_n = 1 / (tau^2 * zeta^2) = 2500 s^-2      b_n = 2 / tau = 100 s^-1
#   PhysX's compliantContactStiffness/Damping are FORCE units (N/m, N*s/m), so they need
#   the effective mass at the foot contact:
#       M = 35.3475 kg (v3_printed, both engines)   m_eff ~ M/2 = 17.674 kg
#       k = 2500 * 17.674 = 44184 N/m               b = 100 * 17.674 = 1767 N*s/m
#   Sanity: static sink under load = g / k_n = 9.81 / 2500 = 3.9 mm, independent of the
#   mass split - that is how deep MuJoCo's own contact is by construction, and the reason
#   its peaks are lower. m_eff only sets where in the 4 mm the force lands.
#   d2 sidesteps the m_eff guess entirely: compliantContactAccelerationSpring=1 makes the
#   spring acceleration-based, which IS MuJoCo's convention, so k=2500 / b=100 go in raw.
#
# Usage: tools/sim2sim/contact_sweep.sh [arm ...]   (no args = all arms)
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=$HOME/isaacsim_venv/bin/python3
OUT=/home/syaro/pyg_fea/work/contact_sweep
mkdir -p "$OUT"

run () {  # run <tag> <env assignments...>
    local tag=$1; shift
    echo "=== $tag : $* ==="
    local t0=$SECONDS
    env "$@" PYG_TAG="$tag" OMNI_KIT_ACCEPT_EULA=YES nice -n 10 \
        "$PY" tools/sim2sim/isaac_grf_rollout.py > "$OUT/$tag.log" 2>&1
    echo "    exit=$? elapsed=$((SECONDS - t0))s"
}

arm_base ()        { run base          PYG_NOOP=1; }
arm_a ()           { run a_maxdepen1   PYG_MAXDEPEN=1.0; }
arm_b ()           { run b_iters84     PYG_ITERS=8,4; }
arm_c0 ()          { run c0_deinst     PYG_DEINST=1; }
arm_c ()           { run c_offsets     PYG_OFFSETS=0.005,0.0; }
arm_e ()           { run e_bounce02    PYG_BOUNCE=0.2; }
arm_d0 ()          { run d0_footmat    PYG_FOOTMAT=1; }
arm_d ()           { run d_compliant   PYG_COMPLIANT=44184,1767; }
arm_d2 ()          { run d2_accspring  PYG_COMPLIANT=2500,100 PYG_COMPLIANT_ACC=1; }
# which half of arm_b did the work: position count, or velocity count?
arm_b1 ()          { run b1_pos8vel1   PYG_ITERS=8,1; }
arm_b2 ()          { run b2_pos32vel4  PYG_ITERS=32,4; }
arm_b3 ()          { run b3_pos4vel4   PYG_ITERS=4,4; }
arm_b4 ()          { run b4_pos16vel4  PYG_ITERS=16,4; }
# combination arms - filled in from the single-knob results
arm_combo ()       { run combo         PYG_ITERS=8,4 PYG_MAXDEPEN=1.0; }
arm_combo2 ()      { run combo2        PYG_ITERS=8,4 PYG_MAXDEPEN=1.0 PYG_COMPLIANT=44184,1767; }
arm_combo3 ()      { run combo3        PYG_ITERS=8,4 PYG_MAXDEPEN=1.0 PYG_OFFSETS=0.005,0.0; }
arm_combo4 ()      { run combo4        PYG_ITERS=4,4 PYG_MAXDEPEN=1.0; }
# how far down does the position-iteration trend go, and does more velocity help?
arm_b5 ()          { run b5_pos2vel4   PYG_ITERS=2,4; }
arm_b6 ()          { run b6_pos1vel4   PYG_ITERS=1,4; }
arm_b7 ()          { run b7_pos4vel8   PYG_ITERS=4,8; }
arm_b8 ()          { run b8_pos4vel16  PYG_ITERS=4,16; }
arm_b9 ()          { run b9_pos8vel8   PYG_ITERS=8,8; }

if [ $# -eq 0 ]; then
    arm_base; arm_a; arm_b; arm_c0; arm_c; arm_e; arm_d0; arm_d; arm_d2
else
    for a in "$@"; do "arm_$a"; done
fi
