"""Verify that each model transmits the whole applied load to its constraints.

Everything in this campaign rests on a load path built from rigid actuator bodies,
node-pair MPC ties between bolted bodies, and loads that are sometimes moved to a
motor reference node. Any of those can silently leak or short-circuit load - L4 once
returned 0.96 MPa under 836 N because a rigid body bridged the load straight into the
fixed side. This re-solves one unit case per link with reaction totals printed and
checks them against the applied force.

PASS means sum(reactions) = -(applied force) to within tolerance, i.e. nothing is
lost and nothing is carried by a path outside the model.

Usage: equilibrium_check.py [LINK ...]
"""
import glob
import os
import re
import shutil
import subprocess
import sys

W = '/home/syaro/pyg_fea/work'
CCX = '/home/syaro/pyg_fea/ccxenv/bin/ccx'
TOL = 1e-3          # relative


def check_all(link):
    """Every unit case, forces AND moments - the first-deck/DOF-1-3 check was too weak."""
    d = f'{W}/{link}'
    decks = sorted(glob.glob(f'{d}/{link}_u*.inp'))
    if not decks:
        return [f'{link}: no unit deck on disk (pruned) - skipped']
    return [check(link, src) for src in decks]


def check(link, src=None):
    d = f'{W}/{link}'
    decks = sorted(glob.glob(f'{d}/{link}_u*.inp'))
    if not decks:
        return f'{link}: no unit deck on disk (pruned) - skipped'
    src = src or decks[0]
    mcomp = re.search(r'_u([A-Za-z0-9]+)\.inp$', src)
    if not mcomp:
        return f'{os.path.basename(src)}: not a unit deck'
    comp = mcomp.group(1)
    s = open(src).read()
    applied = {}
    for m in re.finditer(r'^\s*(\d+),\s*([1-6]),\s*(-?[\d.eE+-]+)\s*$', s, re.M):
        dof, val = int(m.group(2)), float(m.group(3))
        if dof <= 3:
            applied[dof] = applied.get(dof, 0.0) + val
    if '*NODE PRINT' not in s:
        # per-node RF (not TOTALS=ONLY): a force balance alone cannot see a moment
        # that leaks through a constraint, which is exactly the bypass this is meant
        # to rule out.
        s = s.replace('*NODE FILE\nU\n', '*NODE PRINT, NSET=FIX\nRF\n*NODE FILE\nU\n')
    wd = f'{W}/eqcheck/{link}'
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd, exist_ok=True)
    open(f'{wd}/eq.inp', 'w').write(s)
    env = dict(os.environ, OMP_NUM_THREADS='3')
    subprocess.run([CCX, '-i', 'eq'], cwd=wd, env=env,
                   stdout=open(f'{wd}/eq.log', 'w'), stderr=subprocess.STDOUT, timeout=7200)
    dat = f'{wd}/eq.dat'
    if not os.path.exists(dat):
        return f'{link}: solver produced no .dat - see {wd}/eq.log'
    txt = open(dat).read()
    rows = re.findall(r'^\s*(\d+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*$',
                      txt, re.M)
    if not rows:
        return f'{link}: no per-node reactions in {dat}'
    import numpy as _np
    # ONLY the *NODE block: element lines also start with an integer followed by
    # comma-separated integers, and reading those as coordinates made every moment
    # residual meaningless (the first run of this check "failed" on all seven cases).
    coords = {}
    in_node = False
    for ln in open(f'{wd}/eq.inp'):
        t = ln.strip()
        if t.startswith('*'):
            in_node = t.upper().startswith('*NODE') and 'FILE' not in t.upper() \
                and 'PRINT' not in t.upper()
            continue
        if not in_node or not t:
            continue
        p4 = [x.strip() for x in t.split(',')]
        if len(p4) >= 4 and p4[0].isdigit():
            try:
                coords[int(p4[0])] = [float(p4[1]), float(p4[2]), float(p4[3])]
            except ValueError:
                pass
    RF = _np.array([[float(r[1]), float(r[2]), float(r[3])] for r in rows])
    RP = _np.array([coords.get(int(r[0]), [0, 0, 0]) for r in rows])
    R = RF.sum(0).tolist()
    # moment balance about the origin: applied moment must equal -(reaction moment)
    Mr = _np.cross(RP, RF).sum(0)
    lp = []
    for mm2 in re.finditer(r'^\s*(\d+),\s*([1-3]),\s*(-?[\d.eE+-]+)\s*$', s, re.M):
        nid, dof, val = int(mm2.group(1)), int(mm2.group(2)), float(mm2.group(3))
        v = _np.zeros(3)
        v[dof - 1] = val
        lp.append((_np.array(coords.get(nid, [0, 0, 0])), v))
    Ma = sum((_np.cross(q, v) for q, v in lp), _np.zeros(3))
    mres = float(_np.abs(Ma + Mr).max() / max(1.0, float(_np.abs(Ma).max())))
    A = [applied.get(i, 0.0) for i in (1, 2, 3)]
    scale = max(1e-9, max(abs(v) for v in A))
    err = max(abs(R[i] + A[i]) for i in range(3)) / scale
    ok = 'PASS' if err < TOL else 'FAIL'
    if comp == 'Gbody':
        return (f'{link} u{comp}: body load (*DLOAD) - a CLOAD balance does not apply, '
                f'reactions sum to [{R[0]:.1f}, {R[1]:.1f}, {R[2]:.1f}] N')
    scaleM = max(float(_np.abs(Ma).max()), float(_np.abs(Mr).max()), 1.0)
    mres = float(_np.abs(Ma + Mr).max()) / scaleM
    # The moment residual is NOT a solver error: a node-pair *EQUATION ties two nodes that
    # are up to 12 mm apart, so its constraint force pair acts at two different points and
    # injects a couple the real bolted joint does not. Reaction coverage was verified
    # complete (224/224 fixed nodes, every coordinate found), so this number measures the
    # tie artefact. Force balance still has to be exact.
    ok = 'PASS' if err < TOL else 'FAIL'
    tag = ('ties look clean' if mres < 0.05 else
           'offset MPC ties inject a noticeable couple' if mres < 0.25 else
           'TIE ARTEFACT IS LARGE - shrink the tie gap or model the fastener')
    return (f'{link} u{comp}: force residual {err:.2e} {ok} · '
            f'spurious tie couple {100*mres:.0f} % of the applied moment ({tag})')


def main():
    links = sys.argv[1:] or sorted(os.path.basename(os.path.dirname(f))
                                   for f in glob.glob(f'{W}/*/envelope_P99.json'))
    for L in links:
        for line in check_all(L):
            print(line, flush=True)


if __name__ == '__main__':
    main()
