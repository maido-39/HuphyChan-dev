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


def check(link):
    d = f'{W}/{link}'
    decks = sorted(glob.glob(f'{d}/{link}_u*.inp'))
    if not decks:
        return f'{link}: no unit deck on disk (pruned) - skipped'
    src = decks[0]
    comp = re.search(r'_u([A-Za-z]+)\.inp$', src).group(1)
    s = open(src).read()
    applied = {}
    for m in re.finditer(r'^\s*(\d+),\s*([1-6]),\s*(-?[\d.eE+-]+)\s*$', s, re.M):
        dof, val = int(m.group(2)), float(m.group(3))
        if dof <= 3:
            applied[dof] = applied.get(dof, 0.0) + val
    if '*NODE PRINT' not in s:
        s = s.replace('*NODE FILE\nU\n',
                      '*NODE PRINT, NSET=FIX, TOTALS=ONLY\nRF\n*NODE FILE\nU\n')
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
    m = re.search(r'total force.*?\n\n?\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)',
                  txt, re.S | re.I)
    if not m:
        return f'{link}: no reaction totals in {dat}'
    R = [float(m.group(i)) for i in (1, 2, 3)]
    A = [applied.get(i, 0.0) for i in (1, 2, 3)]
    scale = max(1e-9, max(abs(v) for v in A))
    err = max(abs(R[i] + A[i]) for i in range(3)) / scale
    ok = 'PASS' if err < TOL else 'FAIL'
    return (f'{link}: unit {comp} applied {A} N -> reactions '
            f'[{R[0]:.3g}, {R[1]:.3g}, {R[2]:.3g}] N, residual {err:.2e} {ok}')


def main():
    links = sys.argv[1:] or sorted(os.path.basename(os.path.dirname(f))
                                   for f in glob.glob(f'{W}/*/envelope_P99.json'))
    for L in links:
        print(check(L), flush=True)


if __name__ == '__main__':
    main()
