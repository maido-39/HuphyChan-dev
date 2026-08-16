"""Textbook checks for the bolt-pattern distribution used in bolt_group.py.

The dowel-pin recommendation for the knee and hip flanges rests on this arithmetic,
so it is pinned against four closed-form cases on a 100 mm square pattern of four
bolts with the normal along +z.

Run: python3 tools/fea/test_bolt_group.py   (prints OK or raises)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bolt_group import group_check  # noqa: E402

P = [[50, 50, 0], [-50, 50, 0], [-50, -50, 0], [50, -50, 0]]
N = [0, 0, 1]
SZ, LE = [5] * 4, [10] * 4


def close(a, b, tol=1e-6):
    # the tool rounds its outputs to 0.1 N, so comparisons allow that much
    assert abs(a - b) <= max(tol * max(1.0, abs(b)), 0.05), f'{a} != {b}'


def main():
    # 1. pure axial: the force splits evenly, no shear
    r, _ = group_check(P, N, np.array([0, 0, 1000.]), np.zeros(3), SZ, LE)
    for x in r:
        close(x['T_N'], 250.0)
        close(x['V_N'], 0.0)

    # 2. pure bending about x: T = M*d/sum(d^2) = 100000*50/(4*50^2) = 500 N
    r, _ = group_check(P, N, np.zeros(3), np.array([100000., 0, 0]), SZ, LE)
    assert sorted(round(x['T_N']) for x in r) == [-500, -500, 500, 500]
    close(sum(x['T_N'] for x in r), 0.0, 1e-9)          # no net axial force

    # 3. pure torsion about the normal: V = M*r/sum(r^2), r = 70.711 mm
    r, _ = group_check(P, N, np.zeros(3), np.array([0, 0, 100000.]), SZ, LE)
    want = 100000 * np.hypot(50, 50) / (4 * (50 ** 2 + 50 ** 2))
    for x in r:
        close(x['V_N'], want, 1e-4)
        close(x['V_torsion_N'], want, 1e-4)

    # 4. pure in-plane force: splits evenly as shear, no tension
    r, _ = group_check(P, N, np.array([1000., 0, 0]), np.zeros(3), SZ, LE)
    for x in r:
        close(x['V_N'], 250.0)
        close(x['T_N'], 0.0)

    print('OK - all four closed-form cases match')


if __name__ == '__main__':
    main()
