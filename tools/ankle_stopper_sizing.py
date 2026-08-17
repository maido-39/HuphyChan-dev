"""Ankle hard stops: the force each one takes, and the section it needs.

There are two places a hard stop can go, and the user asked for both:

  AB stop  - on each crank / motor output, limiting phi_A and phi_B
  RP stop  - on the roll-pitch gimbal itself, limiting the foot at the ROM edge

They are the same physical limit in two coordinates, coupled by the mechanism
Jacobian J = d(phi_A, phi_B)/d(pitch, roll). Virtual work gives

    M_joint = J^T tau_crank        tau_crank = J^-T M_joint

so a torque on one side is a known torque on the other, and neither can be quoted
without J. J is differenced from the SAME closed-form kinematics as ankle_rom_map.py,
which self-checks against the crank angles recorded in docs/76 SS10c.

Two things drive a stop, and they are not the same size:

  motor driven  - a control fault runs the actuators into the limit. Bounded by the
                  RS03 peak, 60 N.m per motor.
  ground driven - the foot is already at the limit and the ground hits it (a trip, a
                  landing on an edge). Bounded by the measured worst ankle moment,
                  152.1 N.m pitch / 44.4 N.m roll. This one back-drives the cranks and
                  is much the larger of the two - which is the point of the exercise.

A stop is an abuse-load element, not in the walking load path, so it is sized on the
peak tier (docs/62) rather than on P99.

Usage: ankle_stopper_sizing.py [--sf=2.0] [--out=docs/img]
"""
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ankle_rom_map import P, ROM, geom, selfcheck  # noqa: E402

YIELD = 276.0                 # 6061-T6 [MPa]
TAU_ALLOW = 0.577 * YIELD     # von Mises shear yield, 159 MPa
BEARING_ALLOW = 1.5 * YIELD   # confined bearing on a machined face, 414 MPa
JS6_C0 = 5003.0               # N, rod-end static rating (docs/76 SS7-5, 510 kgf catalogue)
JS6_S0 = 1.875                # static safety the design constrains the rod end to
RS03_PEAK = 60.0              # N.m per motor
M_PITCH_PEAK = 152.1          # N.m, measured worst frame at the joint axis (moments_8i)
M_ROLL_PEAK = 44.4


def jacobian(p_deg, r_deg, h=0.05):
    """d(phi_A, phi_B)/d(pitch, roll), all in degrees so the ratio is dimensionless."""
    J = np.zeros((2, 2))
    for j, (dp, dr) in enumerate(((h, 0.0), (0.0, h))):
        for i, side in enumerate(('A', 'B')):
            hi = geom(side, np.array([p_deg + dp]), np.array([r_deg + dr]))[0][0]
            lo = geom(side, np.array([p_deg - dp]), np.array([r_deg - dr]))[0][0]
            J[i, j] = (hi - lo) / (2 * h)
    return J


def statics_direct(side, p_deg, r_deg, tau):
    """Joint moment from a crank torque by explicit rod statics - no differencing.

    Independent of jacobian(): it builds the rod unit vector, solves the crank torque
    balance for the rod force, and takes its moment about the RP centre. Used by
    selfcheck_statics() to prove the differenced Jacobian is right.
    """
    up = side == 'A'
    rc = P['A_r'] if up else P['B_r']
    Az = P['B2RP'] + (P['A2B'] if up else 0.0)
    p = np.radians(p_deg)
    r = np.radians(r_deg if up else -r_deg)
    cp, sp, cr, sr = np.cos(p), np.sin(p), np.cos(r), np.sin(r)
    ax, ay, az = P['RP_r'], P['RP_B'], -P['RP_h']
    w = np.array([cr * ax + sr * az,
                  -sp * sr * ax + cp * ay + sp * cr * az,
                  -cp * sr * ax - sp * ay + cp * cr * az])
    phi = np.radians(geom(side, np.array([p_deg]), np.array([r_deg]))[0][0])
    c = np.array([P['A_h'], 0.0, Az])
    pin = np.array([P['A_h'], rc * np.cos(phi), Az + rc * np.sin(phi)])
    u = (w - pin) / np.linalg.norm(w - pin)
    xh = np.array([1.0, 0.0, 0.0])
    F = tau * 1000.0 / np.dot(np.cross(pin - c, u), xh)      # N (tau N.m -> N.mm)
    M = np.cross(w, F * u) / 1000.0                           # N.m about the RP centre
    return np.array([M @ xh, M @ np.array([0.0, cp, -sp])]), F


def selfcheck_statics(tol=2e-6):
    """The differenced Jacobian must reproduce explicit rod statics.

    Signs differ by a fixed convention (pitch is negated throughout; roll is negated for
    B, which is the documented B mirror inside geom), so magnitudes are compared.
    """
    worst = 0.0
    for p, r in ((0, 0), (-50, -20), (30, 20), (-20, 10), (15, -15), (-50, 20), (30, -20)):
        J = jacobian(p, r)
        for i, side in enumerate(('A', 'B')):
            tau = np.zeros(2)
            tau[i] = 1.0
            want, _ = statics_direct(side, p, r, 1.0)
            worst = max(worst, float(np.abs(np.abs(J.T @ tau) - np.abs(want)).max()))
    if worst > tol:
        raise SystemExit(f'Jacobian disagrees with explicit rod statics by {worst:.2e} N.m')
    print(f'self-check OK: Jacobian matches explicit rod statics to {worst:.1e} N.m '
          f'over 14 crank/pose combinations')


def rod_force(tau_crank, side='A'):
    """Rod axial force for a crank torque [N]. The crank radius is the lever."""
    return tau_crank * 1000.0 / (P['A_r'] if side == 'A' else P['B_r'])


def edge_poses(n=61):
    """Poses on the boundary of the design ROM box, where a stop is actually engaged."""
    p = np.linspace(ROM['p_lo'], ROM['p_hi'], n)
    r = np.linspace(ROM['r_lo'], ROM['r_hi'], n)
    out = [(float(v), ROM['r_lo']) for v in p] + [(float(v), ROM['r_hi']) for v in p]
    out += [(ROM['p_lo'], float(v)) for v in r] + [(ROM['p_hi'], float(v)) for v in r]
    return out


def worst_cases():
    """Worst crank torque and worst joint moment over the ROM boundary."""
    tau_worst = 0.0          # ground-driven torque reacted by ONE crank stop
    tau_at = None
    M_worst = 0.0            # motor-driven joint moment the RP stop must hold
    M_at = None
    ratio_min = np.inf
    for p, r in edge_poses():
        J = jacobian(p, r)
        if abs(np.linalg.det(J)) < 1e-9:
            continue
        # ground driven: the measured peak moment, worst sign combination
        for sp in (+1, -1):
            for sr in (+1, -1):
                M = np.array([sp * M_PITCH_PEAK, sr * M_ROLL_PEAK])
                tau = np.linalg.solve(J.T, M)
                if np.abs(tau).max() > tau_worst:
                    tau_worst, tau_at = float(np.abs(tau).max()), (p, r, tau.copy())
        # motor driven: both motors at peak, worst sign combination
        for sa in (+1, -1):
            for sb in (+1, -1):
                M = J.T @ np.array([sa * RS03_PEAK, sb * RS03_PEAK])
                if np.linalg.norm(M) > M_worst:
                    M_worst, M_at = float(np.linalg.norm(M)), (p, r, M.copy())
        ratio_min = min(ratio_min, float(1.0 / np.abs(np.linalg.inv(J.T)).max()))
    return tau_worst, tau_at, M_worst, M_at, ratio_min


def main():
    sf = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--sf=')), 2.0))
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               os.path.join(HERE, '..', 'docs', 'img'))
    selfcheck()
    selfcheck_statics()
    tau_g, tau_at, M_m, M_at, ratio = worst_cases()
    tau_a, brg_a = TAU_ALLOW / sf, BEARING_ALLOW / sf

    print(f'\nmechanism, worst over the ROM boundary')
    print(f'  crank torque per N.m of joint moment: up to {1/ratio:.3f} (transmission {ratio:.3f})')
    print(f'  ground driven, worst crank torque {tau_g:.1f} N.m at pitch {tau_at[0]:.0f} '
          f'roll {tau_at[1]:.0f}  (tau_A {tau_at[2][0]:+.1f}, tau_B {tau_at[2][1]:+.1f})')
    print(f'  motor driven, worst joint moment  {M_m:.1f} N.m at pitch {M_at[0]:.0f} '
          f'roll {M_at[1]:.0f}  (M_p {M_at[2][0]:+.1f}, M_r {M_at[2][1]:+.1f})')

    cases = {
        'AB stop, ground driven': dict(
            T=tau_g, r=(20.0, 40.0), col='#c0392b',
            why='foot at the limit, ground hits it; back-driven through the rod into '
                'the crank stop. GOVERNS.'),
        'AB stop, motor driven': dict(
            T=RS03_PEAK, r=(20.0, 40.0), col='#e67e22',
            why='RS03 stalls into its own stop at peak torque, one motor'),
        'RP stop, ground driven': dict(
            T=float(np.hypot(M_PITCH_PEAK, M_ROLL_PEAK)), r=(40.0, 60.0), col='#2e86c1',
            why='measured worst ankle moment taken straight by the gimbal stop'),
        'RP stop, motor driven': dict(
            T=M_m, r=(40.0, 60.0), col='#27ae60',
            why='both motors at peak pushing the gimbal into its stop'),
    }

    print(f'\n6061-T6 at SF {sf:.1f}: shear allowable {tau_a:.0f} MPa, '
          f'bearing allowable {brg_a:.0f} MPa')
    print(f"\n{'stop / driver':26s} {'torque':>9s} {'radius':>7s} {'force':>8s} "
          f"{'A_shear':>9s} {'A_bearing':>10s}")
    for name, c in cases.items():
        for rs in c['r']:
            F = c['T'] * 1000.0 / rs
            print(f"{name if rs == c['r'][0] else '':26s} {c['T']:7.1f}Nm {rs:6.0f}mm "
                  f"{F:7.0f}N {F/tau_a:8.1f}mm2 {F/brg_a:9.1f}mm2")

    rr = np.linspace(15, 75, 241)
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, axes = plt.subplots(1, 3, figsize=(15.4, 4.3))
    for name, c in cases.items():
        F = c['T'] * 1000.0 / rr
        axes[0].plot(rr, F, color=c['col'], lw=2.0, label=f"{name}  ({c['T']:.0f} N$\\cdot$m)")
        axes[1].plot(rr, F / tau_a, color=c['col'], lw=2.0, label=f'{name} (shear)')
        axes[1].plot(rr, F / brg_a, color=c['col'], lw=1.1, ls='--')
        for rs in c['r']:
            axes[0].plot([rs], [c['T'] * 1000.0 / rs], 'o', color=c['col'], ms=5)
            axes[1].plot([rs], [c['T'] * 1000.0 / rs / tau_a], 'o', color=c['col'], ms=5)
    axes[0].set_ylabel('force on the stop face [N]')
    axes[0].set_title('Force a hard stop has to take')
    axes[1].set_ylabel('required area [mm$^2$]')
    axes[1].set_title(f'Section at SF {sf:.1f}   solid = shear ({tau_a:.0f} MPa), '
                      f'dashed = bearing ({brg_a:.0f} MPa)')
    for ax in axes[:2]:
        ax.set_xlabel('stop radius from the rotation axis [mm]')
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7.2)
        ax.set_xlim(15, 75)
    # third panel: where over the ROM the back-driven crank torque is worst
    pv = np.linspace(ROM['p_lo'], ROM['p_hi'], 49)
    rv = np.linspace(ROM['r_lo'], ROM['r_hi'], 33)
    Z = np.zeros((rv.size, pv.size))
    for i, rq in enumerate(rv):
        for j, pq in enumerate(pv):
            J = jacobian(float(pq), float(rq))
            Z[i, j] = max(np.abs(np.linalg.solve(
                J.T, np.array([sp * M_PITCH_PEAK, sr * M_ROLL_PEAK]))).max()
                for sp in (+1, -1) for sr in (+1, -1))
    im = axes[2].pcolormesh(pv, rv, Z, cmap='inferno', shading='auto')
    axes[2].plot([tau_at[0]], [tau_at[1]], 'c*', ms=15)
    axes[2].annotate(f'{tau_g:.0f} N$\\cdot$m', xy=(tau_at[0], tau_at[1]),
                     xytext=(tau_at[0] + 9, tau_at[1] + 5), color='c', fontsize=9,
                     fontweight='bold')
    axes[2].set_xlabel('pitch [deg]')
    axes[2].set_ylabel('roll [deg]')
    axes[2].set_title(f'Back-driven crank torque under the peak ankle moment [N$\\cdot$m]\n'
                      f'min {Z.min():.0f} = {Z.min()/RS03_PEAK:.1f}x the RS03 peak - the motor '
                      f'can never hold it', fontsize=9)
    fig.colorbar(im, ax=axes[2], fraction=0.046)
    fig.suptitle('Ankle hard stops. The ground back-driving a crank at the ROM edge is '
                 f'{tau_g / RS03_PEAK:.1f}x the motor stall case.', fontsize=10)
    fig.tight_layout()
    dst = os.path.join(out, 'ankle_stopper_sizing.png')
    fig.savefig(dst)
    print(f'\n-> docs/img/ankle_stopper_sizing.png')
    for name, c in cases.items():
        print(f'  {name}: {c["why"]}')

    # where the over-travel load goes decides which stop is the right one
    Fr = rod_force(tau_g, 'A')
    print(f'\nrod end, if the stop is on the CRANK: the whole over-travel load goes through '
          f'the rod\n  F_rod {Fr:.0f} N -> s0 = C0/F = {JS6_C0/Fr:.2f} vs the design floor '
          f'{JS6_S0:.3f} ({"BELOW" if JS6_C0/Fr < JS6_S0 else "ok"})')
    print(f'rod end, if the stop is on the RP GIMBAL: the load short-circuits foot -> gimbal '
          f'-> stop\n  the rods stay at their walking load (P99 1.10 kN, s0 4.5)')


if __name__ == '__main__':
    main()
