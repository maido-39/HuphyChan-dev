"""Ankle 2-RSU: the designed roll-pitch ROM, what the A/B cranks actually cover,
and which constraint cuts each region away.

The design targets pitch -50..+30 deg (+ = dorsiflexion) x roll +-20 deg. Whether a pose
inside that box is reachable is decided by three things, and the point of this map is to
show WHICH one bites where:

  1. rod reach      - the closed-form crank angle has no solution (|cos arg| > 1), i.e. the
                      rod cannot span pin-to-anchor at that pose
  2. foot-side ball - the rod-end swing at the foot clevis. The clevis bolt IS the foot's
                      lateral axis and the bolt is free to rotate, so the limit applies to
                      the LATERAL tilt only: asin|u . x_foot| <= 20 deg (JS6)
  3. crank-side ball- same joint at the crank end, whose plane is sagittal, so the lateral
                      tilt is simply asin|u_x| <= 20 deg

Kinematics reproduces tools/wrench_studio/static/ankle_cad_viewer.html exactly (the closed
form verified against the IK optimiser to 3e-14 deg), and the script self-checks against
the crank angles recorded in docs/76 SS10c before drawing anything.

Usage: ankle_rom_map.py [--out docs/img]
"""
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

# CAD v2 as measured from Ankle2Feet.step (docs/76 SS10a: ball sphere centres, crank bore
# axes, UJ core). This is the AS-BUILT geometry and it reproduces the recorded neutral
# crank angles to <1e-4 deg; the v9h2 optimiser row in SS1 differs by 0.2-1.7 mm and does
# NOT reproduce them, so the as-built set is what a ROM statement must be based on.
P = dict(A_r=65.0, B_r=62.0, RP_B=50.5, RP_r=43.6, A_h=41.0,
         B2RP=200.0, RP_h=10.0, A_L=289.0, B_L=195.0, A2B=100.0)
SWING_LIMIT = 20.0          # JS6 rod end, both ends
ROM = dict(p_lo=-50.0, p_hi=30.0, r_lo=-20.0, r_hi=20.0)
# docs/76 SS10c, for the self-check
EXPECT = {('A', 0, 0): -19.05, ('A', -50, -20): 27.18, ('A', 30, 20): -61.87,
          ('B', 0, 0): -14.24, ('B', -50, 20): 35.41, ('B', 30, -20): -55.93}


def geom(side, p_deg, r_deg):
    """(phi [deg], foot-side swing [deg], crank-side swing [deg], reachable)."""
    up = side == 'A'
    rc = P['A_r'] if up else P['B_r']
    L = P['A_L'] if up else P['B_L']
    Az = P['B2RP'] + (P['A2B'] if up else 0.0)
    p = np.radians(p_deg)
    r = np.radians(r_deg if up else -r_deg)          # motor B is the mirror
    ax, ay, az = P['RP_r'], P['RP_B'], -P['RP_h']
    cp, sp, cr, sr = np.cos(p), np.sin(p), np.cos(r), np.sin(r)
    wx = cr * ax + sr * az
    wy = -sp * sr * ax + cp * ay + sp * cr * az
    wz = -cp * sr * ax - sp * ay + cp * cr * az
    Dx, Ey, Ez = wx - P['A_h'], wy, wz - Az
    k = (Ey ** 2 + Ez ** 2 + rc ** 2 - (L ** 2 - Dx ** 2)) / (2 * rc)
    arg = k / np.hypot(Ey, Ez)
    reach = np.abs(arg) <= 1.0
    phi = np.arctan2(Ez, Ey) + np.arccos(np.clip(arg, -1, 1))
    # rod unit vector from the crank pin to the foot anchor
    pin = np.stack([np.full_like(phi, P['A_h']), rc * np.cos(phi), Az + rc * np.sin(phi)])
    w = np.stack([wx * np.ones_like(phi), wy, wz])
    d = w - pin
    u = d / np.linalg.norm(d, axis=0)
    # foot lateral axis under the same rotation
    xf = np.stack([cr * np.ones_like(phi), -sp * sr * np.ones_like(phi),
                   -cp * sr * np.ones_like(phi)])
    swF = np.degrees(np.arcsin(np.clip(np.abs((u * xf).sum(0)), 0, 1)))
    swC = np.degrees(np.arcsin(np.clip(np.abs(u[0]), 0, 1)))
    return np.degrees(phi), swF, swC, reach


def selfcheck():
    bad = []
    for (side, p, r), want in EXPECT.items():
        got = float(geom(side, np.array([float(p)]), np.array([float(r)]))[0][0])
        if abs(got - want) > 0.05:
            bad.append(f'{side} at ({p},{r}): {got:.2f} vs docs {want:.2f}')
    if bad:
        raise SystemExit('kinematics does not reproduce docs/76 SS10c:\n  ' + '\n  '.join(bad))
    print('self-check OK: crank angles reproduce docs/76 SS10c to 0.05 deg')


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs', 'img'))
    selfcheck()
    # sweep well past the design box so the margins are visible
    pv = np.linspace(-75, 55, 421)
    rv = np.linspace(-40, 40, 321)
    PP, RR = np.meshgrid(pv, rv)
    res = {s: geom(s, PP, RR) for s in ('A', 'B')}
    reach = res['A'][3] & res['B'][3]
    swF = np.maximum(res['A'][1], res['B'][1])
    swC = np.maximum(res['A'][2], res['B'][2])

    # what bites first: 0 feasible, 1 foot-side ball, 2 crank-side ball, 3 unreachable
    code = np.zeros_like(PP)
    code[swF > SWING_LIMIT] = 1
    code[(swC > SWING_LIMIT) & (code == 0)] = 2
    code[~reach] = 3

    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    cm = ListedColormap(['#2e9e5b', '#e8873a', '#e8d13a', '#b03030'])
    ax.pcolormesh(PP, RR, code, cmap=cm, vmin=-0.5, vmax=3.5, shading='auto')
    ax.contour(PP, RR, swF, [SWING_LIMIT], colors='#7a3d00', linewidths=1.4)
    ax.contour(PP, RR, swC, [SWING_LIMIT], colors='#7a7000', linewidths=1.0, linestyles='--')
    ax.add_patch(Rectangle((ROM['p_lo'], ROM['r_lo']), ROM['p_hi'] - ROM['p_lo'],
                           ROM['r_hi'] - ROM['r_lo'], fill=False, ec='k', lw=2.0))
    ax.text(ROM['p_lo'] + 1, ROM['r_hi'] - 3.2, 'design ROM  pitch -50..+30, roll +-20',
            fontsize=8.5, fontweight='bold')
    # margin: how far the binding constraint is from the box corners
    inbox = ((PP >= ROM['p_lo']) & (PP <= ROM['p_hi']) &
             (RR >= ROM['r_lo']) & (RR <= ROM['r_hi']))
    print(f'  inside the design box: worst foot-side swing {swF[inbox].max():.2f} deg, '
          f'worst crank-side {swC[inbox].max():.2f} deg, all reachable = {reach[inbox].all()}')
    k = np.argmax(np.where(inbox, swF, -1))
    ax.plot(PP.flat[k], RR.flat[k], 'k*', ms=13)
    ax.annotate(f'binding pose  ({PP.flat[k]:.0f}, {RR.flat[k]:.0f})\n'
                f'foot-side swing {swF.flat[k]:.1f} deg of {SWING_LIMIT:.0f}',
                xy=(PP.flat[k], RR.flat[k]), xytext=(PP.flat[k] - 46, RR.flat[k] - 12),
                fontsize=8, arrowprops=dict(arrowstyle='->', lw=0.9))
    ax.set_xlabel('pitch [deg]   (+ dorsiflexion)')
    ax.set_ylabel('roll [deg]')
    ax.set_title('Ankle 2-RSU reachable ROM and what cuts it away')
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(fc='#2e9e5b', label='reachable, both ball joints within 20 deg'),
                       Patch(fc='#e8873a', label='cut: foot-side rod-end swing > 20 deg'),
                       Patch(fc='#e8d13a', label='cut: crank-side rod-end swing > 20 deg'),
                       Patch(fc='#b03030', label='cut: rod cannot reach (no IK solution)')],
              loc='lower right', fontsize=7.4, framealpha=0.92)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'ankle_rom_coverage.png'))
    print('  -> ankle_rom_coverage.png')

    # second figure: the two swing fields with the limit, and the crank travel
    fig2, axs = plt.subplots(1, 3, figsize=(12.6, 3.9))
    for ax2, (fieldname, F, lim) in zip(axs[:2], [('foot-side rod-end swing', swF, 20.0),
                                                  ('crank-side rod-end swing', swC, 20.0)]):
        im = ax2.pcolormesh(PP, RR, F, cmap='inferno_r', vmin=0, vmax=28, shading='auto')
        ax2.contour(PP, RR, F, [lim], colors='w', linewidths=1.6)
        ax2.add_patch(Rectangle((ROM['p_lo'], ROM['r_lo']), 80, 40, fill=False, ec='w', lw=1.6))
        ax2.set_title(f'{fieldname} [deg]', fontsize=9.5)
        ax2.set_xlabel('pitch [deg]')
        fig2.colorbar(im, ax=ax2, fraction=0.046)
    axs[0].set_ylabel('roll [deg]')
    phiA = res['A'][0]
    im = axs[2].pcolormesh(PP, RR, np.where(reach, phiA, np.nan), cmap='coolwarm',
                           shading='auto')
    axs[2].contour(PP, RR, np.where(reach, phiA, np.nan), 9, colors='k', linewidths=0.4)
    axs[2].add_patch(Rectangle((ROM['p_lo'], ROM['r_lo']), 80, 40, fill=False, ec='k', lw=1.6))
    axs[2].set_title('crank A angle [deg]  (neutral -19.05)', fontsize=9.5)
    axs[2].set_xlabel('pitch [deg]')
    fig2.colorbar(im, ax=axs[2], fraction=0.046)
    fig2.suptitle('White/black box = design ROM. The foot-side ball is what binds.',
                  fontsize=9.5)
    fig2.tight_layout()
    fig2.savefig(os.path.join(out, 'ankle_rom_fields.png'))
    print('  -> ankle_rom_fields.png')


if __name__ == '__main__':
    main()
