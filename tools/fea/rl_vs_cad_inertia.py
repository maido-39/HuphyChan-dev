"""Mass was the easy half - this compares where the mass IS and how hard it resists turning.

A swing-leg torque does not care about mass alone, it cares about the inertia about the
proximal joint, and that is mass times distance squared. Two legs can agree on total mass to
0.2% (they do) and still demand very different hip and knee torque. So this computes, for
each position:

  centre of mass   sim: body_ipos through the body frame; CAD: exact from the closed FEA
                   surface, plus the motor proxies as solid cylinders on their own axes
  inertia          the full tensor about the PROXIMAL JOINT (not the body COM) - that is the
                   quantity a joint torque actually fights - by the divergence theorem over
                   the surface triangles, with the parallel-axis transfer done explicitly

Correctness is not assumed. The surface integral's volume is checked against the CAD's own
per-solid volume sum from fullbody_links.json before any inertia is reported: if a link's
surface is not closed or is inconsistently wound, its volume comes out wrong and it is
dropped rather than quietly producing a wrong tensor.

Usage: rl_vs_cad_inertia.py [--out=docs/img]
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rl_vs_cad_shape import (XML, STATIC, CAD_HIP_PITCH, CAD_JOINT_Z, rl_model,  # noqa: E402
                             cad_surface)

CAD = '/home/syaro/pyg_fea/steps'
RHO = {'struct': 2.70e-3, 'fastener': 7.85e-3, 'bearing': 7.85e-3}   # kg/cm3
MOTOR_KG = {'RS04': 1.558, 'RS03': 0.932}        # the user's final-design table

# position -> (sim body list, CAD FEA link, CAD proximal joint point [mm, CAD frame])
POS = [
    ('hip pitch', ['L_hip_pitch_link'], 'L5_hip_pitchroll',
     np.array([CAD_HIP_PITCH[0], CAD_HIP_PITCH[1], CAD_JOINT_Z['hip_pitch']])),
    ('hip roll', ['L_hip_roll_link'], 'L4_hip_yaw',
     np.array([-124.19, 70.0, CAD_JOINT_Z['hip_yaw']])),
    ('thigh', ['L_thigh_link'], 'L3_thigh', np.array([-123.7, 70.0, CAD_JOINT_Z['hip_yaw']])),
    ('shin', ['L_shin_link'], 'L2_shin', np.array([-97.45, 115.0, CAD_JOINT_Z['knee']])),
    ('foot', ['L_ankle_pitch_link', 'L_foot_link'], 'L1_ankle_foot',
     np.array([-123.7, 145.0, CAD_JOINT_Z['ankle']])),
]
# motors that ride on each position, by the CAD position of their proxy (not the table's group)
MOTOR_ON = {'hip pitch': ['robstride_rs04_hip_p'], 'hip roll': ['robstride_rs03_hip_y'],
            'thigh': ['robstride_rs04_knee_p'],
            'shin': ['robstride_rs03_ankle_a', 'robstride_rs03_ankle_b'], 'foot': []}
RZ = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])   # sim frame -> CAD frame


def surface_inertia(P, T):
    """(volume mm3, com mm, I about the origin mm5) of the closed solid bounded by P,T.

    Divergence theorem: each triangle with the origin forms a signed tetrahedron, and the
    integrals add with that sign, so concavities and through-holes cancel correctly as long
    as the surface is closed and consistently wound.
    """
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    det = np.einsum('ij,ij->i', a, np.cross(b, c))           # 6 * signed tet volume
    if det.sum() < 0:
        # the payload's triangles are wound inward; flipping every one restores the outward
        # convention the divergence theorem needs. This is a global sign, not a repair - a
        # genuinely open or inconsistent surface still fails the volume check below.
        T = T[:, [0, 2, 1]]
        a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        det = np.einsum('ij,ij->i', a, np.cross(b, c))
    vol = det.sum() / 6.0
    assert vol > 0, 'the surface still integrates to a negative volume after re-winding'
    com = (det[:, None] * (a + b + c) / 4.0).sum(0) / (6.0 * vol)
    # second moments of a tetrahedron with one vertex at the origin, canonical form
    I = np.zeros((3, 3))
    for i in range(3):
        for j in range(3):
            if i == j:
                k, l = [x for x in range(3) if x != i]
                s = 0.0
                for m in (k, l):
                    s += (a[:, m] ** 2 + b[:, m] ** 2 + c[:, m] ** 2
                          + a[:, m] * b[:, m] + a[:, m] * c[:, m] + b[:, m] * c[:, m])
                I[i, i] = (det * s).sum() / 60.0
            else:
                s = (2 * (a[:, i] * a[:, j] + b[:, i] * b[:, j] + c[:, i] * c[:, j])
                     + a[:, i] * b[:, j] + a[:, j] * b[:, i]
                     + a[:, i] * c[:, j] + a[:, j] * c[:, i]
                     + b[:, i] * c[:, j] + b[:, j] * c[:, i])
                I[i, j] = -(det * s).sum() / 120.0
    return vol, com, I


def cylinder_I(mass, r, L, axis, com, about):
    """Inertia of a solid cylinder about `about`, its axis along `axis` (unit)."""
    Ia = 0.5 * mass * r ** 2
    It = mass * (3 * r ** 2 + L ** 2) / 12.0
    u = np.asarray(axis, float)
    u = u / np.linalg.norm(u)
    I = It * np.eye(3) + (Ia - It) * np.outer(u, u)
    d = np.asarray(com, float) - np.asarray(about, float)
    return I + mass * (np.dot(d, d) * np.eye(3) - np.outer(d, d))


def transfer(I_o, mass, com, about):
    """Inertia known about the ORIGIN -> about `about`, via the COM."""
    I_com = I_o - mass * (np.dot(com, com) * np.eye(3) - np.outer(com, com))
    d = np.asarray(com) - np.asarray(about)
    return I_com + mass * (np.dot(d, d) * np.eye(3) - np.outer(d, d))


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    mujoco, m, d = rl_model()
    solids = json.load(open(f'{CAD}/fullbody_links.json'))
    proxies = json.load(open(f'{CAD}/actuator_proxies.json'))
    volsum = defaultdict(float)
    kindvol = defaultdict(lambda: defaultdict(float))
    for r in solids:
        volsum[r['link']] += r['vol']
        kindvol[r['link']][r.get('kind', 'struct')] += r['vol']

    print(f"{'position':11s} {'src':4s} {'mass kg':>8s} {'COM below hip [mm]':>19s} "
          f"{'I_prox [kg m2]':>15s} {'r_gyr mm':>9s}")
    rows = []
    for name, bodies, link, prox in POS:
        # ---- sim side: exact, straight out of the compiled model ----
        Msim, Isim = 0.0, np.zeros((3, 3))
        proxc = RZ.T @ (prox - CAD_HIP_PITCH)          # CAD proximal point, in sim world mm
        RL_HIP = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY,
                                          'L_hip_pitch_link')] * 1000.0
        com_acc = np.zeros(3)
        for b in bodies:
            i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, b)
            mass = float(m.body_mass[i])
            R = np.array(d.xmat[i]).reshape(3, 3)
            com = d.xpos[i] * 1000.0 + R @ (m.body_ipos[i] * 1000.0)
            q = m.body_iquat[i]
            Rq = np.zeros(9)
            mujoco.mju_quat2Mat(Rq, q)
            Rq = Rq.reshape(3, 3)
            Ic = (R @ Rq) @ np.diag(m.body_inertia[i]) @ (R @ Rq).T     # kg m2, world axes
            dd = (com - (RL_HIP + proxc)) / 1000.0                       # m
            Isim += Ic + mass * (np.dot(dd, dd) * np.eye(3) - np.outer(dd, dd))
            Msim += mass
            com_acc += mass * com
        com_sim = com_acc / Msim
        z_sim = (RZ @ (com_sim - RL_HIP))[2]        # height below the hip pitch axis

        # ---- CAD side: exact surface integral + motor cylinders ----
        P, T = cad_surface(link)
        assert P is not None, f'{link}: no FEA surface payload'
        vol, com_c, I_o = surface_inertia(P, T)
        vref = kindvol[link]['struct'] * 1000.0            # cm3 -> mm3
        err = abs(vol - vref) / vref
        assert err < 0.05, (
            f'{link}: the surface integrates to {vol/1000:.1f} cm3 but the CAD solids sum to '
            f'{vref/1000:.1f} cm3 ({100*err:.1f}% off) - the surface is not closed or not '
            'consistently wound, so its inertia cannot be trusted')
        rho = RHO['struct'] * 1e-3 / 1e3                    # kg per mm3 -> kg/mm3
        rho = 2.70e-6                                        # kg/mm3, 6061
        Mstruct = vol * rho
        # non-struct solids (fasteners, bearings) as point masses at their own COMs
        Mextra, Iextra, com_x = 0.0, np.zeros((3, 3)), np.zeros(3)
        for r in solids:
            if r['link'] != link or r.get('kind', 'struct') == 'struct':
                continue
            mm_ = r['vol'] * RHO[r['kind']]
            c = np.asarray(r['com'], float)
            dd = (c - prox) / 1000.0
            Iextra += mm_ * (np.dot(dd, dd) * np.eye(3) - np.outer(dd, dd))
            Mextra += mm_
            com_x += mm_ * c
        Icad = transfer(I_o * rho * 1e-6, Mstruct, com_c, prox) + Iextra   # mm5*kg/mm3 -> kg m2
        Mcad = Mstruct + Mextra
        com_cad = (Mstruct * com_c + com_x) / Mcad
        for pk in MOTOR_ON[name]:
            p = proxies[pk]
            mk = MOTOR_KG[p['family']]
            u = {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}[p['axis']]
            Icad += cylinder_I(mk, p['r'], p['len'], u, np.asarray(p['ctr'], float), prox) / 1e6
            com_cad = (com_cad * Mcad + mk * np.asarray(p['ctr'], float)) / (Mcad + mk)
            Mcad += mk
        z_cad = (com_cad - CAD_HIP_PITCH)[2]

        # the component that a pitch-axis torque fights: about the CAD lateral axis x
        Ip_sim = float(Isim[0, 0] if name == 'x' else np.linalg.eigvalsh(Isim).max())
        Ip_cad = float(np.linalg.eigvalsh(Icad).max())
        for src, M, z, Ip in (('sim', Msim, z_sim, Ip_sim), ('CAD', Mcad, z_cad, Ip_cad)):
            print(f'{name:11s} {src:4s} {M:8.3f} {z:19.1f} {Ip:15.5f} '
                  f'{1000*np.sqrt(Ip/M):9.1f}')
        rows.append((name, Msim, z_sim, Ip_sim, Mcad, z_cad, Ip_cad))
        print()

    print(f"{'position':11s} {'dM %':>8s} {'dCOM mm':>9s} {'dI %':>8s}")
    for nm, Ms, zs, Is, Mc, zc, Ic in rows:
        print(f'{nm:11s} {100*(Mc-Ms)/Ms:+7.1f}% {zc-zs:+9.1f} {100*(Ic-Is)/Is:+7.1f}%')

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 140, 'font.size': 9})
    fig, ax = plt.subplots(1, 3, figsize=(14.6, 4.6))
    y = np.arange(len(rows))
    names = [r[0] for r in rows]
    for a, (si, ci, ttl, xl, logx) in zip(ax, [
            (1, 4, 'mass', 'mass [kg]', False),
            (2, 5, 'COM height below the hip pitch axis', 'z [mm]', False),
            (3, 6, 'inertia about the proximal joint', 'I [kg·m²]', True)]):
        a.barh(y - 0.19, [r[si] for r in rows], 0.36, color='#3b82f6', label='RL sim')
        a.barh(y + 0.19, [r[ci] for r in rows], 0.36, color='#c0392b', label='final CAD')
        for i, r in enumerate(rows):
            dv = 100 * (r[ci] - r[si]) / abs(r[si]) if r[si] else 0
            a.annotate(f'{dv:+.0f}%', (max(abs(r[si]), abs(r[ci])) * 1.04, i), fontsize=7,
                       va='center', color='#c0392b')
        a.set_yticks(y)
        a.set_yticklabels(names, fontsize=8)
        a.invert_yaxis()
        if logx:
            a.set_xscale('log')
        a.set_xlabel(xl, fontsize=8.5)
        a.set_title(ttl, fontsize=9.5)
        a.grid(alpha=0.3, axis='x')
    ax[0].legend(fontsize=7.5)
    fig.suptitle('Beyond mass: where it sits and how hard it is to swing — '
                 'the inertia a joint torque actually fights', fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'rl_vs_cad_inertia.png'), bbox_inches='tight')
    print(f"\n-> {os.path.join(out, 'rl_vs_cad_inertia.png')}")


if __name__ == '__main__':
    main()
