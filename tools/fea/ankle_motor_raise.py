"""What raising the two 2-RSU ankle motors by +70 mm does to swing inertia.

The motors already sit on the shin - that was the point of the 2-RSU - but they sit LOW on
it (ctr z = -499.5 / -599.5 against a knee at -310), so a further raise is the obvious
lever on swing inertia. Three things move, and only three:

  motors      both RS03 up 70 mm (catalog 0.88 kg each - the CAD's 0.932 is a placeholder)
  cranks      they ride the motor shafts, so up 70 mm with them
  push rods   their upper ball joints ride the cranks, the foot ends stay: each rod grows
              70 mm, gaining mass at its own linear density, its COM rising 35 mm

The clevis fork does NOT move - it is shin-fixed structure holding the ankle pitch
bearings, independent of where the motors are. (Identifying the fork was the subtle part:
the two 62.05 cm3 solids at y=145 are the fork; the true rods are the 20.11 / 15.33 cm3
solids whose COMs land on the midpoints of their JMC ball-joint pairs to 0.5 mm, which
this script asserts rather than assumes.)

Inertia is computed about the two axes a swing torque actually fights - the knee axis
(y=115, z=-310, along x, from the L2 bearing seats) and the hip pitch axis (y=70, z=60,
along x) - as point masses per CAD solid plus cylinder terms for the motors. The change
is pure parallel-axis, so it is exact given the masses; the totals carry the point-mass
approximation (a few % on solids whose own size is small next to 300-800 mm arms).

Packaging is checked, not hand-waved: after the raise the upper motor clears the thigh
envelope and the knee RS04 by about 10 mm each, so +70 mm is close to the ceiling.

Usage: ankle_motor_raise.py [--raise=70] [--out=docs/img]
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

CAD = '/home/syaro/pyg_fea/steps'
RHO = {'struct': 2.70e-3, 'fastener': 7.85e-3, 'bearing': 7.85e-3}   # kg/cm3
RS03, RS04 = 0.88, 1.42          # catalog masses (docs/39, docs/33)
KNEE_AX = np.array([115.0, -310.0])     # (y, z), axis along x
HIP_AX = np.array([70.0, 60.0])
THIGH_Z_MIN = -370.0             # bottom of the L3 thigh envelope
JMC = {'A_up': [-83.7, 205.7, -523.2], 'A_dn': [-86.2, 195.0, -810.0],
       'B_up': [-163.7, 208.0, -616.0], 'B_dn': [-161.2, 195.0, -810.0]}


def I_point(m, com, ax):
    """Inertia of a point mass about a lateral (x-direction) axis at (y,z)=ax [kg mm2]."""
    return m * ((com[1] - ax[0]) ** 2 + (com[2] - ax[1]) ** 2)


def I_cyl_own(m, r, L, axis):
    """A cylinder's own inertia about a lateral axis through its COM."""
    return 0.5 * m * r * r if axis == 'x' else m * (3 * r * r + L * L) / 12.0


def main():
    dz = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--raise=')), 70))
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    S = json.load(open(f'{CAD}/fullbody_links.json'))
    prox = json.load(open(f'{CAD}/actuator_proxies.json'))
    L1 = [r for r in S if r['link'] == 'L1_ankle_foot']

    # ---- identify the moving parts, with the ball-joint midpoint check ----
    rods = []
    for tag in ('A', 'B'):
        up, dn = np.array(JMC[f'{tag}_up']), np.array(JMC[f'{tag}_dn'])
        mid = (up + dn) / 2
        cand = min(L1, key=lambda r: np.linalg.norm(np.array(r['com']) - mid))
        err = np.linalg.norm(np.array(cand['com']) - mid)
        assert err < 1.0, (
            f'rod {tag}: nearest solid COM is {err:.1f} mm from the ball-joint midpoint - '
            'the rod identification is wrong and everything downstream would be too')
        rods.append(dict(tag=tag, m=cand['vol'] * RHO['struct'],
                         com=np.array(cand['com'], float),
                         length=float(np.linalg.norm(up - dn))))
    cranks = [dict(m=(32.78 + 9.86) * RHO['struct'], com=np.array([-94.5, 154.6, -503.7])),
              dict(m=(32.78 + 9.84) * RHO['struct'], com=np.array([-152.9, 154.9, -602.5]))]
    motors = []
    for k in ('robstride_rs03_ankle_a', 'robstride_rs03_ankle_b'):
        p = prox[k]
        motors.append(dict(m=RS03, com=np.array(p['ctr'], float), r=p['r'], len=p['len'],
                           axis=p['axis']))
    assert abs(motors[0]['com'][2] + 599.51) < 0.1 and \
        abs(motors[1]['com'][2] + 499.51) < 0.1, 'motor anchors moved - re-derive'

    # ---- packaging after the raise ----
    up_mot = max(motors, key=lambda m: m['com'][2])          # ankle_b, the higher one
    top_new = up_mot['com'][2] + dz + up_mot['r']
    cl_thigh = THIGH_Z_MIN - top_new
    kp = prox['robstride_rs04_knee_p']
    cdist = np.hypot(up_mot['com'][1] - kp['ctr'][1], up_mot['com'][2] + dz - kp['ctr'][2])
    cl_knee = cdist - up_mot['r'] - kp['r']
    assert cl_thigh > 0 and cl_knee > 0, (
        f'raise {dz:.0f} mm collides: thigh clearance {cl_thigh:.1f}, '
        f'knee-motor clearance {cl_knee:.1f} mm')

    # ---- delta inertia about each axis ----
    def deltas(ax):
        d = {}
        d['motors'] = sum(I_point(m['m'], m['com'] + [0, 0, dz], ax)
                          - I_point(m['m'], m['com'], ax) for m in motors)
        d['cranks'] = sum(I_point(c['m'], c['com'] + [0, 0, dz], ax)
                          - I_point(c['m'], c['com'], ax) for c in cranks)
        d['rods'] = 0.0
        for r in rods:
            rho_l = r['m'] / r['length']                     # kg per mm of rod
            m_new = r['m'] + rho_l * dz
            com_new = r['com'] + [0, 0, dz / 2]
            d['rods'] += I_point(m_new, com_new, ax) - I_point(r['m'], r['com'], ax)
        return d

    # ---- baseline totals about each axis ----
    def total(ax, links, mots):
        I = 0.0
        for r in S:
            if r['link'] in links:
                I += I_point(r['vol'] * RHO.get(r['kind'], RHO['struct']),
                             np.array(r['com'], float), ax)
        for key, mass in mots:
            p = prox[key]
            I += I_point(mass, np.array(p['ctr'], float), ax) \
                + I_cyl_own(mass, p['r'], p['len'], p['axis'])
        return I

    I_knee = total(KNEE_AX, {'L1_ankle_foot', 'L2_shin'},
                   [('robstride_rs03_ankle_a', RS03), ('robstride_rs03_ankle_b', RS03),
                    ('robstride_rs04_knee_p', RS04)])
    I_hip = total(HIP_AX, {'L1_ankle_foot', 'L2_shin', 'L3_thigh', 'L4_hip_yaw',
                           'L5_hip_pitchroll'},
                  [('robstride_rs03_ankle_a', RS03), ('robstride_rs03_ankle_b', RS03),
                   ('robstride_rs04_knee_p', RS04), ('robstride_rs03_hip_y', RS03),
                   ('robstride_rs04_hip_p', RS04)])

    print(f'== +{dz:.0f} mm 인상: 무엇이 움직이나')
    for r in rods:
        print(f"  rod {r['tag']}: {r['length']:.0f} -> {r['length']+dz:.0f} mm · "
              f"{r['m']*1000:.1f} -> {(r['m']+r['m']/r['length']*dz)*1000:.1f} g")
    print(f'  motors 2x{RS03} kg, cranks 2x{cranks[0]["m"]*1000:.0f} g: +{dz:.0f} mm')
    print(f'\n== 패키징: 상부모터-대퇴 {cl_thigh:.1f} mm · 상부모터-무릎RS04 {cl_knee:.1f} mm')

    rows = []
    for name, ax, I0 in (('knee', KNEE_AX, I_knee), ('hip pitch', HIP_AX, I_hip)):
        d = deltas(ax)
        net = sum(d.values())
        rows.append((name, d, net, I0))
        print(f'\n== {name} 축 [kg·m²]  (기준 관성 {I0/1e6:.3f})')
        for k, v in d.items():
            print(f'   {k:8s} {v/1e6:+8.4f}')
        print(f'   {"NET":8s} {net/1e6:+8.4f}   = {100*net/I0:+.1f} % of the {name} swing set')

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 140, 'font.size': 9})
    fig, ax2 = plt.subplots(1, 2, figsize=(12.8, 5.6), gridspec_kw={'width_ratios': [1, 1]})
    a = ax2[0]
    th = np.linspace(0, 2 * np.pi, 60)
    for m in motors:
        for off, ls, col in ((0, '--', '#9aa7b5'), (dz, '-', '#c0392b')):
            a.plot(m['com'][1] + m['r'] * np.cos(th), m['com'][2] + off + m['r'] * np.sin(th),
                   ls, color=col, lw=1.6)
    a.plot(kp['ctr'][1] + kp['r'] * np.cos(th), kp['ctr'][2] + kp['r'] * np.sin(th),
           color='#2e86c1', lw=1.6)
    a.annotate('knee RS04', (kp['ctr'][1], kp['ctr'][2]), ha='center', fontsize=8,
               color='#2e86c1')
    for r in rods:
        up, dn = np.array(JMC[f"{r['tag']}_up"]), np.array(JMC[f"{r['tag']}_dn"])
        a.plot([up[1], dn[1]], [up[2], dn[2]], color='#9aa7b5', ls='--', lw=1.3)
        a.plot([up[1], dn[1]], [up[2] + dz, dn[2]], color='#c0392b', lw=1.3)
    a.axhline(THIGH_Z_MIN, color='#555', lw=1.0, ls=':')
    a.annotate('thigh envelope bottom', (245, THIGH_Z_MIN + 6), fontsize=7.5, color='#555',
               ha='right')
    a.axhline(-310, color='#2e86c1', lw=0.8, ls=':')
    a.axhline(-843, color='#333', lw=1.2)
    a.annotate('sole', (245, -838), fontsize=7.5, ha='right')
    a.annotate(f'clearance {cl_thigh:.0f} mm', (60, -378), fontsize=7.5, color='#c0392b')
    a.set_aspect('equal')
    a.set_xlim(40, 255)
    a.set_ylim(-870, -260)
    a.set_xlabel('fore-aft y [mm]', fontsize=8.5)
    a.set_ylabel('z [mm]', fontsize=8.5)
    a.set_title(f'grey dashed = today · red = +{dz:.0f} mm\n'
                'motors and cranks rise, rods lengthen, fork and foot stay', fontsize=9)
    a.grid(alpha=0.25)

    b = ax2[1]
    w, xg = 0.34, np.arange(4)
    labels = ['motors', 'cranks', 'rods', 'NET']
    for i, (name, d, net, I0) in enumerate(rows):
        vals = [d['motors'] / 1e6, d['cranks'] / 1e6, d['rods'] / 1e6, net / 1e6]
        bars = b.bar(xg + (i - 0.5) * w, vals, w * 0.92,
                     color='#2e86c1' if i == 0 else '#c0392b',
                     label=f'about the {name} axis  ({100*net/I0:+.1f} % of {I0/1e6:.2f})')
        for x, v in zip(xg + (i - 0.5) * w, vals):
            b.annotate(f'{v:+.3f}', (x, v - 0.004 if v < 0 else v + 0.001),
                       ha='center', fontsize=7)
    b.axhline(0, color='k', lw=0.8)
    b.set_xticks(xg)
    b.set_xticklabels(labels, fontsize=8.5)
    b.set_ylabel('ΔI [kg·m²]', fontsize=8.5)
    b.set_title('where the change comes from\n(rod lengthening pushes back, slightly)',
                fontsize=9)
    b.legend(fontsize=8)
    b.grid(alpha=0.3, axis='y')
    fig.suptitle(f'Raising the 2-RSU ankle motors +{dz:.0f} mm — swing-inertia effect, '
                 'CAD geometry, nothing assumed about the rods', fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'ankle_motor_raise70.png'), bbox_inches='tight')
    print(f"\n-> {os.path.join(out, 'ankle_motor_raise70.png')}")


if __name__ == '__main__':
    main()
