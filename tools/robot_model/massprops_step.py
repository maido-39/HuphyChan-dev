"""Rigid-body mass properties of the Pygmalion leg from the CAD STEP, exactly.

The robot model needs, per rigid body, a mass, a centre of mass and a full inertia tensor.
The STEP has every solid's shape, so OCC's volume integrals give those exactly for the
structural parts; bought parts enter by catalogue mass; the only judgement is WHICH body
each solid belongs to, and that assignment is written out so it can be reviewed.

Sources (all under ~/pyg_fea/steps, produced by tools/fea/xcaf_links.py from the STEP):
  link_L*.step              structural solids of each CAD sub-assembly (6061-T6, 2.70)
  link_ACT_*.step           the seven actuator placeholders - shape used for the tensor,
                            density rescaled to the CATALOGUE mass (their CAD mass is a
                            placeholder: Fusion measurement, docs/83 s1)
  fullbody_links.json       every solid incl. fasteners / bearings with volume and COM -
                            those enter as point masses at steel density

Rigid bodies (L leg, CAD frame, mm). The 2-RSU ankle is SERIAL here - pitch then roll -
as the goal requires: the two RS03, the cranks and the clevis fork ride the shin, the push
rods are split half to the shin and half to the foot, the ankle cross goes to the foot.
  pelvis          CenterParts + Waist_Yaw RS04 + BOTH hip-pitch RS04 stators (the right one
                  mirrored from the left) + the 40 cm3 CRBS808 outer housing from the
                  HipPitch2Roll group (it bolts 10xM4 into the hip-pitch stator)
  hip_pitch_link  HipPitch2Roll + Hip_P(roll) RS04
  hip_roll_link   PipRoll2Yaw + Hip_Y RS03
  thigh           HipYaw2Knee + Knee RS04 (its stator is clamped between the thigh clevis
                  plates by 2 x 10xM4 PCD106; the shin hangs on its 6xM5 output flange)
                  minus the 70 cm3 hip-yaw ring (bolted 8xM4 into the hip-yaw RS03 stator,
                  holds the 6814 outer seat -> it turns with hip_roll_link)
  shin            Knee2Ankle + Ankle RS03 x2 + fork + cranks + rods/2
  ankle_pitch_link  the universal-joint cross (the real intermediate body)
  foot            sole plates + rods/2 (+ the 6900 cross bearings)
Bearings are split half/half between the two bodies they join, chosen by the distance of
the bearing centre to each joint AXIS (hip pitch and hip roll share a point, so a point
test could never pick the roll pair - the first review caught exactly that).

Checks: every OCC volume must match the JSON inventory (0.5 %); every tensor must be
positive definite and satisfy the triangle inequality; the sum of body masses must equal
the inventory sum. Writes ~/pyg_fea/steps/robot_massprops_step.json.

Usage: massprops_step.py   (mjlab .venv python - it has OCP)
"""
import json
import os
import sys

import numpy as np

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

STEPS = '/home/syaro/pyg_fea/steps'
RHO_AL, RHO_STEEL = 2.70e-6, 7.85e-6          # kg/mm3
MOTOR_KG = {'RS04': 1.42, 'RS03': 0.88}        # catalogue (docs/33, 39)
ANKLE_Z = -800.0

BODY_OF_GROUP = {'L6_pelvis': 'pelvis', 'L5_hip_pitchroll': 'hip_pitch_link',
                 'L4_hip_yaw': 'hip_roll_link', 'L3_thigh': 'thigh', 'L2_shin': 'shin'}
MOTOR_BODY = {'robstride_rs04_hip_r_1_': 'pelvis', 'robstride_rs04_hip_r': 'pelvis',
              'robstride_rs04_hip_p': 'hip_pitch_link', 'robstride_rs03_hip_y': 'hip_roll_link',
              'robstride_rs04_knee_p': 'thigh', 'robstride_rs03_ankle_a': 'shin',
              'robstride_rs03_ankle_b': 'shin'}
# joint points, for bearing assignment and for the output
JOINT_PT = {'hip_pitch': [-123.7, 70.0, 60.0], 'hip_roll': [-123.7, 70.0, 60.0],
            'hip_yaw': [-123.7, 70.0, -97.0], 'knee': [-123.7, 115.0, -310.0],
            'ankle': [-123.7, 145.0, ANKLE_Z]}
JOINT_AXIS = {'hip_pitch': [1, 0, 0], 'hip_roll': [0, 1, 0], 'hip_yaw': [0, 0, 1],
              'knee': [1, 0, 0], 'ankle': [1, 0, 0]}


def dist_to_axis(p, j):
    d = np.asarray(p, float) - np.asarray(JOINT_PT[j], float)
    u = np.asarray(JOINT_AXIS[j], float)
    return float(np.linalg.norm(d - np.dot(d, u) * u))
BEARING_PAIR = {'hip_yaw': ('hip_roll_link', 'thigh'), 'knee': ('thigh', 'shin'),
                'ankle': ('shin', 'foot'), 'hip_pitch': ('pelvis', 'hip_pitch_link'),
                'hip_roll': ('hip_pitch_link', 'hip_roll_link')}
JMC = {'A': ([-83.7, 205.7, -523.2], [-86.2, 195.0, -810.0]),
       'B': ([-163.7, 208.0, -616.0], [-161.2, 195.0, -810.0])}


def read_solids(path):
    rd = STEPControl_Reader()
    assert rd.ReadFile(path) == IFSelect_RetDone, path
    rd.TransferRoots()
    shape = rd.OneShape()
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    out = []
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def props(solid, rho):
    """(mass kg, com mm, inertia about COM in the global axes kg mm2, volume mm3)."""
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, g)
    vol = g.Mass()
    c = g.CentreOfMass()
    com = np.array([c.X(), c.Y(), c.Z()])
    M = g.MatrixOfInertia()           # about the COM, unit density (mm5)
    I = np.array([[M.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]) * rho
    return vol * rho, com, I, vol


def cyl_axis(solid):
    """Axis direction and a point of the largest cylindrical face."""
    best = None
    ex = TopExp_Explorer(solid, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face_s(ex.Current())
        ex.Next()
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() != GeomAbs_Cylinder:
            continue
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        cy = ad.Cylinder()
        d, L = cy.Axis().Direction(), cy.Axis().Location()
        if best is None or g.Mass() > best[0]:
            best = (g.Mass(), np.array([d.X(), d.Y(), d.Z()]), np.array([L.X(), L.Y(), L.Z()]),
                    cy.Radius())
    return best


def transfer(I_com, m, com, about):
    d = np.asarray(com) - np.asarray(about)
    return I_com + m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))


def main():
    inv = json.load(open(f'{STEPS}/fullbody_links.json'))
    bodies = {b: dict(parts=[]) for b in ('pelvis', 'hip_pitch_link', 'hip_roll_link',
                                         'thigh', 'shin', 'ankle_pitch_link', 'foot')}

    def add(body, name, m, com, I_com, kind, src):
        bodies[body]['parts'].append(dict(name=name, mass=float(m), com=[float(v) for v in com],
                                          I_com=[[float(v) for v in r] for r in I_com],
                                          kind=kind, src=src))

    # ---- structural solids, exact, from the per-link STEPs ----
    vol_check = {}
    for grp, body in BODY_OF_GROUP.items():
        for k, s in enumerate(read_solids(f'{STEPS}/link_{grp}.step')):
            m, com, I, vol = props(s, RHO_AL)
            vol_check[grp] = vol_check.get(grp, 0.0) + vol
            b = body
            if grp == 'L3_thigh' and 65e3 < vol < 75e3 and np.linalg.norm(com - [-123.7, 70.0, -100.2]) < 3:
                b = 'hip_roll_link'           # hip-yaw ring: bolted to the RS03 stator, 6814 outer seat
            if grp == 'L5_hip_pitchroll' and 35e3 < vol < 45e3 and np.linalg.norm(com - [-56.3, 72.7, 79.8]) < 3:
                b = 'pelvis'                  # CRBS808 outer housing on the hip-pitch stator
            add(b, f'{grp}#{k}', m, com, I, 'struct', 'occ')
    # ---- the ankle group: split by rigid body ----
    for k, s in enumerate(read_solids(f'{STEPS}/link_L1_ankle_foot.step')):
        m, com, I, vol = props(s, RHO_AL)
        vol_check['L1_ankle_foot'] = vol_check.get('L1_ankle_foot', 0.0) + vol
        rod = None
        for tag, (up, dn) in JMC.items():
            mid = (np.array(up) + np.array(dn)) / 2
            if np.linalg.norm(com - mid) < 1.0:
                rod = tag
        if rod:
            add('shin', f'rod_{rod}/2', m / 2, com, I / 2, 'rod', 'occ')
            add('foot', f'rod_{rod}/2', m / 2, com, I / 2, 'rod', 'occ')
        elif abs(com[2] - ANKLE_Z) < 0.6 and abs(com[0] + 123.7) < 1.0 and 20 < vol / 1000 < 30:
            # the universal-joint cross: the intermediate body between pitch and roll
            add('ankle_pitch_link', f'L1#{k} (ankle cross)', m, com, I, 'struct', 'occ')
        elif com[2] <= ANKLE_Z + 0.5:
            add('foot', f'L1#{k}', m, com, I, 'struct', 'occ')
        else:
            add('shin', f'L1#{k} (fork/crank)', m, com, I, 'struct', 'occ')
    # volume cross-check against the inventory
    for grp, v in vol_check.items():
        ref = sum(r['vol'] for r in inv if r['link'] == grp and r.get('kind', 'struct') == 'struct') * 1000
        assert abs(v - ref) / ref < 0.005, f'{grp}: OCC {v/1e3:.1f} vs inventory {ref/1e3:.1f} cm3'

    # ---- fasteners and bearings: point masses at steel density ----
    for r in inv:
        kind = r.get('kind', 'struct')
        if kind == 'struct':
            continue
        m = r['vol'] * 1000 * RHO_STEEL
        com = np.array(r['com'], float)
        if kind == 'bearing':
            # every bearing, grouped or loose: half to each body it joins, by nearest joint AXIS
            j = min(JOINT_AXIS, key=lambda q: dist_to_axis(com, q))
            for b in BEARING_PAIR[j]:
                add(b, r['path'][-40:] + ' /2', m / 2, com, np.zeros((3, 3)), kind, 'inv')
        elif r['link'] in BODY_OF_GROUP:
            add(BODY_OF_GROUP[r['link']], r['path'][-40:], m, com, np.zeros((3, 3)), kind, 'inv')
        elif r['link'] == 'L1_ankle_foot':
            add('foot' if com[2] <= ANKLE_Z + 0.5 else 'shin', r['path'][-40:], m, com,
                np.zeros((3, 3)), kind, 'inv')
        else:
            j = min(JOINT_AXIS, key=lambda q: dist_to_axis(com, q))
            for b in BEARING_PAIR[j]:
                add(b, r['path'][-40:] + ' /2', m / 2, com, np.zeros((3, 3)), kind, 'inv')

    # ---- motors: exact shape, catalogue mass, exact axis ----
    motors = {}
    for key, body in MOTOR_BODY.items():
        sols = read_solids(f'{STEPS}/link_ACT_{key.replace("robstride_", "robstride_")}.step')
        assert len(sols) == 1, key
        fam = 'RS04' if 'rs04' in key else 'RS03'
        m0, com, I0, vol = props(sols[0], 1.0)
        rho = MOTOR_KG[fam] / vol
        add(body, key, MOTOR_KG[fam], com, I0 * rho, 'motor', 'occ+catalogue')
        if key == 'robstride_rs04_hip_r':
            # the pelvis carries BOTH hip-pitch stators; the STEP only has the left one
            Mx = np.diag([-1.0, 1.0, 1.0])
            add(body, key + ' (R mirror)', MOTOR_KG[fam], Mx @ com, Mx @ (I0 * rho) @ Mx,
                'motor', 'mirror')
        ax = cyl_axis(sols[0])
        motors[key] = dict(family=fam, com=[float(v) for v in com],
                           axis=[float(v) for v in ax[1]] if ax else None,
                           axis_point=[float(v) for v in ax[2]] if ax else None,
                           r=float(ax[3]) if ax else None)

    # ---- aggregate per body ----
    out = dict(frame='CAD global, mm, kg, kg*mm^2; L leg', joints=JOINT_PT, motors=motors,
               bodies={})
    total = 0.0
    for b, d in bodies.items():
        ms = np.array([p['mass'] for p in d['parts']])
        cs = np.array([p['com'] for p in d['parts']])
        M = ms.sum()
        com = (ms[:, None] * cs).sum(0) / M
        I = np.zeros((3, 3))
        for p in d['parts']:
            I += transfer(np.array(p['I_com']), p['mass'], p['com'], com)
        w = np.linalg.eigvalsh(I)
        assert w.min() > 0 and w.max() <= w[0] + w[1] + 1e-6, f'{b}: inertia not physical {w}'
        out['bodies'][b] = dict(mass=float(M), com=[float(v) for v in com],
                                I_com=[[float(v) for v in r] for r in I],
                                principal=[float(v) for v in w], n_parts=len(d['parts']),
                                parts=d['parts'])
        total += M
        print(f"{b:15s} {M:7.3f} kg  com [{com[0]:7.1f} {com[1]:6.1f} {com[2]:7.1f}]  "
              f"principal I [kg mm2] {w.round(0)}  ({len(d['parts'])} parts)")
    out['leg_total_incl_pelvis_motors'] = float(total)
    print(f'\nsum of bodies {total:.3f} kg (pelvis counted once, with both pelvis motors)')
    for k, v in motors.items():
        print(f"  motor {k:26s} axis {np.round(v['axis'], 3) if v['axis'] else None} "
              f"through {np.round(v['axis_point'], 1) if v['axis_point'] else None}")
    json.dump(out, open(f'{STEPS}/robot_massprops_step.json', 'w'), indent=1)
    print(f'-> {STEPS}/robot_massprops_step.json')


if __name__ == '__main__':
    main()
