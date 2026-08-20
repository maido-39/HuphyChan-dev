"""Swing inertia about the knee and the hip - the quantity a joint torque actually fights.

Mass alone said "the leg total matches to 0.2%". That number hides the finding: inertia
goes as mass times distance SQUARED, and the mass that left the thigh reappeared further
from both axes. This computes, for the sim model and the final CAD:

  I about the knee axis    of everything distal to it (shin + linkage + ankle motors + foot)
  I about the hip pitch    of the whole leg

  sim side   exact - full inertia tensors from the compiled model, rotated to world and
             parallel-axis transferred to the joint
  CAD side   a stated LOWER BOUND - every solid in fullbody_links.json as a point mass at
             its own COM (413 solids, so the discretisation is fine), motors as solid
             cylinders on their catalogued axes (their self term matters: they are the
             biggest single masses), the table's screw masses at their group's volume
             centroid. What is missing is only each solid's inertia about its own COM,
             which for compact machined parts is a few percent of the transfer term at
             these lever arms. So the CAD numbers can only go UP.

An earlier version of this tool integrated the FEA surface payloads instead; that path is
gone because the L1 payload is the foot PLATE only (262 cm3) while the CAD group is the
whole 2-RSU mechanism (569 cm3) - the very confusion docs/82 section 4 untangles - and a
tool that inherits it would assign the wrong solids to the wrong body.

The knee-motor attribution question (thigh vs shin, docs/81 section 3) is checked, not
assumed: the RS04 proxy centre sits on the knee bearing axis, so it is reported both ways
and the difference comes out in the noise.

Usage: rl_vs_cad_inertia.py [--out=docs/img]
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rl_vs_cad_shape import XML, rl_model  # noqa: E402

CAD = '/home/syaro/pyg_fea/steps'
RHO = {'struct': 2.70e-3, 'fastener': 7.85e-3, 'bearing': 7.85e-3}   # kg/cm3
KNEE = np.array([-97.45, 115.0, -310.0])      # knee bearing seat, CAD frame [mm]
HIP = np.array([-124.45, 68.1, 60.0])         # hip pitch motor centre
# the user's final-design table: motor masses, and screw+bearing mass per CAD group
MOTOR = {'robstride_rs03_ankle_a': 0.932, 'robstride_rs03_ankle_b': 0.932,
         'robstride_rs04_knee_p': 1.558, 'robstride_rs03_hip_y': 0.932,
         'robstride_rs04_hip_p': 1.558}
SCREWS = {'L2_shin': 0.185, 'L1_ankle_foot': 0.169 + 0.142, 'L3_thigh': 0.189 + 0.017,
          'L4_hip_yaw': 0.100, 'L5_hip_pitchroll': 0.122}
SHIN_GROUPS = ['L2_shin', 'L1_ankle_foot']
LEG_GROUPS = SHIN_GROUPS + ['L3_thigh', 'L4_hip_yaw', 'L5_hip_pitchroll']
SHIN_MOTORS = ['robstride_rs03_ankle_a', 'robstride_rs03_ankle_b']
LEG_MOTORS = list(MOTOR)


def sim_inertia(mujoco, m, d, bodies, point):
    """Exact (I about the lateral axis through `point`, mass, COM) from the model."""
    I, M, com = 0.0, 0.0, np.zeros(3)

    def bid(n):
        return mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n)
    for b in bodies:
        i = bid(b)
        mass = float(m.body_mass[i])
        R = np.array(d.xmat[i]).reshape(3, 3)
        c = d.xpos[i] + R @ m.body_ipos[i]
        q = np.zeros(9)
        mujoco.mju_quat2Mat(q, m.body_iquat[i])
        Ic = (R @ q.reshape(3, 3)) @ np.diag(m.body_inertia[i]) @ (R @ q.reshape(3, 3)).T
        dd = c - point
        # lateral axis is world y in the sim's convention (it walks along +x)
        I += Ic[1, 1] + mass * (dd[0] ** 2 + dd[2] ** 2)
        M += mass
        com += mass * c
    return I, M, com / M


def cad_inertia(solids, proxies, groups, motors, point):
    """Lower-bound (I, mass, COM) about the CAD lateral axis x through `point` [mm]."""
    def d2(c):
        return ((c[1] - point[1]) ** 2 + (c[2] - point[2]) ** 2) * 1e-6   # m2
    I, M, com = 0.0, 0.0, np.zeros(3)
    for r in solids:
        if r['link'] not in groups:
            continue
        mk = r['vol'] * RHO[r.get('kind', 'struct')]
        c = np.asarray(r['com'], float)
        I += mk * d2(c)
        M += mk
        com += mk * c
    for L in groups:
        mk = SCREWS[L]
        cs = np.array([r['com'] for r in solids if r['link'] == L])
        vs = np.array([r['vol'] for r in solids if r['link'] == L])
        c = (cs * vs[:, None]).sum(0) / vs.sum()
        I += mk * d2(c)
        M += mk
        com += mk * c
    for k in motors:
        p, mk = proxies[k], MOTOR[k]
        c = np.asarray(p['ctr'], float)
        r_m = p['r'] / 1000.0
        # every leg motor's axis is the lateral x except hip_y (z): about the lateral axis
        # the self term is axial (mr^2/2) for x-axis motors, transverse for the yaw one
        L_m = p['len'] / 1000.0
        self_I = (0.5 * mk * r_m ** 2 if p['axis'] == 'x'
                  else mk * (3 * r_m ** 2 + L_m ** 2) / 12.0)
        I += self_I + mk * d2(c)
        M += mk
        com += mk * c
    return I, M, com / M


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    mujoco, m, d = rl_model()
    solids = json.load(open(f'{CAD}/fullbody_links.json'))
    proxies = json.load(open(f'{CAD}/actuator_proxies.json'))

    knee_p = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'L_shin_link')]
    hip_p = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'L_hip_pitch_link')]
    sK = sim_inertia(mujoco, m, d, ['L_shin_link', 'L_ankle_pitch_link', 'L_foot_link'],
                     knee_p)
    sH = sim_inertia(mujoco, m, d, ['L_hip_pitch_link', 'L_hip_roll_link', 'L_thigh_link',
                                    'L_shin_link', 'L_ankle_pitch_link', 'L_foot_link'],
                     hip_p)
    cK0 = cad_inertia(solids, proxies, SHIN_GROUPS, SHIN_MOTORS, KNEE)
    cK1 = cad_inertia(solids, proxies, SHIN_GROUPS,
                      SHIN_MOTORS + ['robstride_rs04_knee_p'], KNEE)
    cH = cad_inertia(solids, proxies, LEG_GROUPS, LEG_MOTORS, HIP)
    # the knee-motor attribution ambiguity must not matter: the RS04 sits on the knee axis
    assert (cK1[0] - cK0[0]) / cK0[0] < 0.02, (
        'the knee motor contributes materially about its own axis - it does not sit on it, '
        'and the thigh-vs-shin attribution would change the verdict')

    rows = [('knee (shin+2RSU+foot)', sK, cK0, f'motor incl: {cK1[0]:.4f}'),
            ('hip pitch (whole leg)', sH, cH, '')]
    print(f"{'axis':24s} {'src':4s} {'I [kg m2]':>10s} {'M [kg]':>8s} {'COM below [mm]':>15s}")
    for nm, s_, c_, note in rows:
        pz = knee_p[2] * 1000 if nm.startswith('knee') else hip_p[2] * 1000
        cz = KNEE[2] if nm.startswith('knee') else HIP[2]
        print(f'{nm:24s} {"sim":4s} {s_[0]:10.4f} {s_[1]:8.3f} {pz - s_[2][2]*1000:15.1f}')
        print(f'{nm:24s} {"CAD":4s} {c_[0]:10.4f} {c_[1]:8.3f} {cz - c_[2][2]:15.1f}'
              f'   {note}')
        print(f'{nm:24s} {"":4s} {"":>10s} I {100*(c_[0]/s_[0]-1):+.1f} % (CAD는 하한)\n')

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 140, 'font.size': 9})
    fig, ax = plt.subplots(1, 2, figsize=(10.6, 4.2))
    for a, (nm, s_, c_, _) in zip(ax, rows):
        vals = [s_[0], c_[0]]
        a.bar(['RL sim\n(exact)', 'final CAD\n(lower bound)'], vals,
              color=['#3b82f6', '#c0392b'], width=0.55)
        for i, v in enumerate(vals):
            a.annotate(f'{v:.3f}', (i, v * 1.01), ha='center', fontsize=9, weight='bold')
        a.annotate(f'{100*(c_[0]/s_[0]-1):+.0f} %', (0.5, max(vals) * 0.5), ha='center',
                   fontsize=13, weight='bold', color='#c0392b')
        a.set_ylabel('I about the joint axis [kg·m²]', fontsize=8.5)
        a.set_title(nm, fontsize=9.5)
        a.grid(alpha=0.3, axis='y')
    fig.suptitle('Swing inertia — the leg totals matched, this does not: '
                 'the knee fights ~60 % more', fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'rl_vs_cad_inertia.png'), bbox_inches='tight')
    print(f"-> {os.path.join(out, 'rl_vs_cad_inertia.png')}")


if __name__ == '__main__':
    main()
