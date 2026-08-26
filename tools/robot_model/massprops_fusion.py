"""Rigid-body mass properties from FUSION 360, not from the exported STEP.

The STEP the campaign meshed is one revision behind (260814 v1) and is missing 141 screws;
Fusion holds the current design (260819 v4, "wUpper" - it now carries the upper body too).
This reads every BRep body's assembly-space mass properties out of Fusion via the MCP
connector (tools/fusion/mcp_client.py -> fusion_mcp_execute/script) and re-aggregates them
into the simulator's rigid bodies.

Two things make the aggregation exact rather than approximate:
  * Fusion reports each body's inertia about the ROOT ORIGIN (verified: for CenterParts the
    reported Ixx 192.25 kg cm2 exceeds m*(y^2+z^2)=144.48, which only the origin convention
    allows), so tensors ADD directly and the parallel-axis shift is done once at the end.
  * Every motor placeholder is a solid at generic-Steel density (RS04 198.5 cm3 -> 1.558 kg,
    RS03 118.7 -> 0.932, both exactly 7.85 g/cm3), so their CAD mass is replaced by the
    catalogue mass while keeping the measured shape tensor, scaled by the mass ratio.

Rigid-body split (same physics as massprops_step.py, now on the current CAD):
  pelvis          CenterParts + Waist_Yaw RS04 + BOTH hip-pitch RS04 stators (the CAD has the
                  right leg only, so the pelvis-side left parts are x-mirrored)
  hip_pitch_link  HipPitch2Roll + hip-roll RS04
  hip_roll_link   HipRoll2Yaw + hip-yaw RS03
  thigh           HipYaw2Knee + knee RS04 (its stator is clamped by the thigh clevis plates)
  shin            Knee2Ankle + both ankle RS03 + the Ankle2Feet parts above the ankle axis
  ankle_pitch_link  the universal-joint cross + the 6900 pitch bearings
  foot            the Ankle2Feet parts below the ankle axis + the 6900 roll bearings
  rods            the two push rods, split half shin / half foot
Upper body is no longer a placeholder OR a lump - it is articulated, on the three joints the
CAD actually has: waist yaw (z through x0,y70), shoulder pitch (x through y85,z540) and
shoulder roll (y through x-200,z540), which intersect at the shoulder point (-200,85,540):
  torso              Torso group (frame + PSU + Waist2Torso) + Neck + both shoulder-pitch RS03
  shoulder_pitch_link  Shoulder-Pitch2Roll + the shoulder-roll RS03
  arm                ArmR_Dummy
What is NOT in the robot is decided by BRANCH NAME, not by the light bulb. `ArmR_fullDoF`,
`Actuators-NotUse` and the `Human_Solid ... (REF)` bodies are alternatives and are excluded.
A light bulb that is merely off is not evidence of anything: all 69 fasteners inside
`CenterParts` are switched off so the parts underneath can be seen, and treating that as
suppression cost the pelvis 201 g of real screws. The split was verified against the dump -
the branch test matches 25 hidden bodies (671.0 kg) and ZERO live ones, and every hidden body
it does not match is a fastener on a fully visible sub-assembly.

Usage: massprops_fusion.py   (needs bodies.json from the MCP dump)
"""
import json
import os

import numpy as np

FUS = os.environ.get('PYG_BODIES', '/home/syaro/pyg_fea/fusion/bodies.json')
OUT = os.environ.get('PYG_MASSPROPS', '/home/syaro/pyg_fea/fusion/robot_massprops_fusion.json')
ANKLE_Z = -800.0                      # mm, CAD frame
# Catalogue masses (RobStride user manuals 260713, "Mechanical characteristic"). The CAD
# placeholders now carry these masses directly - tools/fusion/set_placeholder_density.py
# rescaled their density - so this table is a cross-check rather than a correction, and it
# asserts against the document. RS02 is 380 g in the manual; the 405 g that circulates is a
# reseller figure.
MOTOR_CAT = {'RS04': 1.42, 'RS03': 0.88, 'RS02': 0.380, 'RS00': 0.310}
GROUP_BODY = {'CenterParts:1': 'pelvis', 'HipPitch2Roll:1': 'hip_pitch_link',
              'HipRoll2Yaw:1': 'hip_roll_link', 'HipYaw2Knee:1': 'thigh',
              'Knee2Ankle:1': 'shin', 'Torso:1': 'torso', 'Neck:1': 'torso'}
UPPER_BODIES = ('torso', 'shoulder_pitch_link', 'arm')
# PYG_ANKLE_LOOP=1: carry the 2-RSU ankle as the CLOSED mechanism. The two cranks and the
# two push rods become rigid bodies of their own (crank = the printed crank + its cover,
# rod = the aluminium bar + the two spherical-bearing inserts in its eyes) instead of being
# lumped into the shin / split half-half between shin and foot.
LOOP = bool(os.environ.get('PYG_ANKLE_LOOP'))
LOOP_BODIES = ('crank_A', 'crank_B', 'rod_A', 'rod_B')
MOTOR_BODY = {'Waist_Yaw': 'pelvis', 'Hip_R': 'pelvis', 'Hip_P': 'hip_pitch_link',
              'Hip_Y': 'hip_roll_link', 'Knee_P': 'thigh',
              'Ankle_A:3': 'shin', 'Ankle_A (1)': 'shin'}
# pelvis-side parts that the one-sided CAD has only on the left
MIRROR_TO_PELVIS = ('Hip_R', 'Hip_P')


ALT_BRANCH = ('NotUse', 'fullDoF', 'REF')


def is_alternative(path):
    """True for geometry that is an ALTERNATIVE design, not part of this robot."""
    return any(t in path for t in ALT_BRANCH)


def family(name):
    """Motor family of a body path, or None.

    The 'Robstride' guard is not cosmetic: the thigh carries two pins named
    'CenterPin_RS03' whose 0.4 g would otherwise be replaced by the RS03 catalogue
    mass, putting a phantom 1.76 kg on the thigh.
    """
    if 'Robstride' not in name:
        return None
    for f in MOTOR_CAT:
        if f in name:
            return f
    return None


def tensor(rec):
    """(mass kg, com mm, I about the ORIGIN in kg mm^2)."""
    m = rec['m']
    com = np.array(rec['c'], float) * 10.0                    # cm -> mm
    xx, yy, zz, xy, yz, xz = rec['I']
    I = np.array([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]]) * 100.0   # kg cm^2 -> kg mm^2
    return m, com, I


def to_com(I_o, m, com):
    return I_o - m * (np.dot(com, com) * np.eye(3) - np.outer(com, com))


def about(I_com, m, com, pt):
    d = np.asarray(com) - np.asarray(pt)
    return I_com + m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))


def classify(path):
    """Which rigid body a body path belongs to (None = skip)."""
    parts = path.split('::')[0].split('/')
    grp = parts[2] if len(parts) > 2 else ''
    if grp.startswith('Hexagon') or grp.startswith('NoSim'):
        return None                                           # loose screws / non-sim marker
    if grp in GROUP_BODY:
        return GROUP_BODY[grp]
    if grp == 'Actuators-LegR:1':
        for key, b in MOTOR_BODY.items():
            if key in path:
                return b
        return None
    if grp.startswith('6900ZZ-Knee2UJ'):
        return 'ankle_pitch_link'                             # pitch trunnion bearings
    if grp.startswith('6900ZZ-UJ2Feet'):
        return 'foot'                                         # roll pillow bearings
    if grp == 'Ankle2Feet:1':
        return 'ANKLE_SPLIT'
    if parts[1] == 'Joints_UpperBody:1':
        if 'ArmR_fullDoF' in path:
            return None                                       # suppressed alternative arm
        # ORDER MATTERS. In the v22 rework Shoulder-Pitch2Roll was reparented UNDER
        # ArmR_Dummy (/Arm_R:1/ArmR_Dummy:1/Shoulder-Pitch2Roll:1::...). With the ArmR_Dummy
        # test first, 3.218 kg of shoulder bracketry migrates across the shoulder-roll joint
        # into arm_link and shoulder_pitch_link is left as a naked 0.880 kg RS03. So the
        # specific shoulder tests run BEFORE the catch-all arm test.
        if 'Torso2ShoulderP' in path:
            # New in v22, at the torso/shoulder interface. Deliberately dropped: the user
            # said to ignore the torso rework, so it goes neither to torso nor to the arm.
            # Recorded as a decision so it cannot be mistaken for the M2 kind of silent loss.
            return None
        if ('Shoulder-Pitch2Roll' in path or 'Shoulder_Roll' in path
                or 'Shoulder-Roll2Yaw' in path):
            return 'shoulder_pitch_link'
        if 'Shoulder_Pitch' in path:
            return 'torso'                                    # its stator rides the torso
        if '6810ZZ-Roll2Yaw' in path:
            # Promoted to /Arm_R:1/6810ZZ-Roll2Yaw:1 in v22; it matches no branch below and
            # would return None, silently dropping 50 g.
            return 'arm'
        if 'ArmR_Dummy' in path:
            return 'arm'
        return None
    return None


def collect(B):
    """Every counted body as (link, item) with item = dict(path, m, com[mm], I_o[kg mm2]).

    This is the whole physics of the aggregation in one place so that mass_dr.py can
    re-run it with perturbed masses: each item's tensor scales with its mass for fixed
    geometry, so a density error is a scale on (m, I_o) and nothing else.
    """
    bodies = {b: [] for b in ('pelvis', 'hip_pitch_link', 'hip_roll_link', 'thigh', 'shin',
                              'ankle_pitch_link', 'foot') + UPPER_BODIES
              + (LOOP_BODIES if LOOP else ())}
    rods = []
    skipped = hidden_real = 0.0
    for path, rec in B.items():
        if is_alternative(path):                              # alternative design branch
            skipped += rec['m']
            continue
        if not rec.get('live', True):
            hidden_real += rec['m']                           # switched off, still hardware
        who = classify(path)
        if who is None:
            continue
        m, com, I_o = tensor(rec)
        fam = family(path)
        if fam:                                               # placeholder -> catalogue mass
            k = MOTOR_CAT[fam] / m
            assert abs(k - 1.0) < 0.02, (
                f'{path}: CAD says {m * 1000:.1f} g, catalogue {MOTOR_CAT[fam] * 1000:.0f} g - '
                'run tools/fusion/set_placeholder_density.py --apply')
            m, I_o = MOTOR_CAT[fam], I_o * k
        item = dict(path=path, m=m, com=com, I_o=I_o, mat=rec.get('mat', ''))
        if who == 'ANKLE_SPLIT':
            if LOOP:
                name = path.split('::')[-1]
                occ = path.split('::')[0].split('/')[-1]
                tag = next((t for t in 'AB' if name.startswith(f'Crank_{t}') or name == f'Arm_{t}'
                            or f'JS06_Ankle-{t}' in path or f'JS06_FEET-{t}' in path), None)
                if tag and name.startswith('Crank_'):
                    bodies[f'crank_{tag}'].append(item)
                    continue
                if tag and (name == f'Arm_{tag}' or 'JS06' in path):
                    bodies[f'rod_{tag}'].append(item)        # bar + both eye inserts
                    continue
            # the two push rods: identified by volume (their COM sits between the ball joints)
            if 15.0 < rec['v'] < 21.0 and -780 < com[2] < -650:
                rods.append(item)
            elif abs(com[2] - ANKLE_Z) < 0.6:
                bodies['ankle_pitch_link'].append(item)   # the cross sits ON the axis
            elif com[2] < ANKLE_Z:
                bodies['foot'].append(item)
            else:
                bodies['shin'].append(item)
            continue
        bodies[who].append(item)
        Mx = np.diag([-1.0, 1.0, 1.0])
        if fam and any(k in path for k in MIRROR_TO_PELVIS) and who == 'pelvis':
            bodies['pelvis'].append(dict(item, path=path + ' (R mirror)', com=Mx @ com,
                                         I_o=Mx @ I_o @ Mx))
        if who == 'torso' and 'Shoulder_Pitch' in path:
            bodies['torso'].append(dict(item, path=path + ' (mirror)', com=Mx @ com,
                                        I_o=Mx @ I_o @ Mx))
    for r in rods:                                            # half to each end
        for b in ('shin', 'foot'):
            bodies[b].append(dict(r, path=r['path'] + ' /2', m=r['m'] / 2, I_o=r['I_o'] / 2))
    return bodies, skipped, hidden_real


def aggregate(items, scale=None):
    """(mass, com[mm], I_com[kg mm2]) of one rigid body from its items.

    `scale` maps item path -> multiplicative factor on that item's mass (and tensor).
    """
    M = C = Io = 0.0
    for it in items:
        k = 1.0 if scale is None else scale.get(it['path'], 1.0)
        M = M + k * it['m']
        C = C + k * it['m'] * it['com']
        Io = Io + k * it['I_o']
    C = C / M
    return M, C, to_com(Io, M, C)


def main():
    B = json.load(open(FUS))
    bodies, skipped, hidden_real = collect(B)
    out = dict(source='Fusion 360 260819_HumanMesh_wUpper_OMAKASE v4 via MCP',
               units='kg, mm, kg*mm^2', motor_masses=MOTOR_CAT, bodies={})
    tot = 0.0
    print(f"{'body':18s} {'mass':>8s}  {'COM (mm)':>28s}  principal I [kg mm2]")
    for b, items in bodies.items():
        M, C, Ic = aggregate(items)
        w = np.linalg.eigvalsh(Ic)
        assert w.min() > 0, f'{b}: non-physical inertia {w}'
        out['bodies'][b] = dict(mass=float(M), com=[float(v) for v in C],
                                I_com=[[float(v) for v in r] for r in Ic],
                                principal=[float(v) for v in w], n=len(items))
        tot += M
        print(f'{b:18s} {M:8.3f}  [{C[0]:8.1f}{C[1]:7.1f}{C[2]:8.1f}]  {w.round(0)}  ({len(items)} bodies)')
    out['ankle_loop'] = LOOP
    leg = tot - sum(out['bodies'][b]['mass'] for b in ('pelvis',) + UPPER_BODIES)
    arms = sum(out['bodies'][b]['mass'] for b in ('shoulder_pitch_link', 'arm'))
    whole = out['bodies']['pelvis']['mass'] + out['bodies']['torso']['mass'] + 2 * leg + 2 * arms
    out['whole_robot_kg'] = float(whole)
    print(f"\nalternative branches excluded: {skipped:.3f} kg "
          f"(ArmR_fullDoF / Actuators-NotUse / Human_Solid REF)")
    n_hidden = sum(1 for p, r in B.items() if not r.get('live', True) and not is_alternative(p))
    print(f"hidden in the CAD view but counted (a light bulb is a view state): "
          f"{n_hidden} bodies, {hidden_real:.3f} kg")
    print(f"one leg {leg:.3f} · one arm side {arms:.3f} · pelvis {out['bodies']['pelvis']['mass']:.3f}"
          f" · torso {out['bodies']['torso']['mass']:.3f}")
    print(f"WHOLE ROBOT {whole:.3f} kg  (pelvis + torso once, legs x2, arms x2)")
    json.dump(out, open(OUT, 'w'), indent=1)
    print(f'-> {OUT}')


if __name__ == '__main__':
    main()
