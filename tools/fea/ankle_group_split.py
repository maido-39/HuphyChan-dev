"""What is actually inside the CAD group called "Ankle2Feet", and which body each piece is on.

The final-design table books the whole group - 3.818 kg including two RS03 - as one row, and
the campaign's earlier reading treated that row as the FOOT. Opening the group shows it is
neither a link nor a sub-assembly of two links: it is the complete 2-RSU MECHANISM. Its 31
solids run from z = -503.7 (a crank on the upper ankle motor, high on the shin) down to
z = -839.0 (the sole), and the four JMC-JS06 spherical bearings come in two pairs - Ankle-A/B
up at -523/-616 on the shin side, FEET-A/B down at -810 on the foot side. So the group spans
the ankle joint, and no single body owns it.

The split rule, stated rather than assumed:

  foot        anything rigidly attached to the foot plate, i.e. COM at or below the ankle
              axis (z = -800). The ankle cross that sits exactly on the axis goes to the
              foot, which is the conservative direction for a foot-mass claim.
  shin        the clevis fork (the 62.05 cm3 pair at y=145 plus its 15.14 braces - it holds
              the ankle pitch bearings and bolts to the shin) and the cranks with their
              clamps, which ride the motor shafts
  rods        the TRUE push rods are the 20.11 / 15.33 cm3 solids: each one's COM lands on
              the midpoint of its JMC ball-joint pair to 0.5 mm, which is asserted below.
              (An earlier pass mistook the fork pair for the rods - the ball-joint midpoint
              test is what settles it.) Their mass is split 50/50, as a parallel linkage
              conventionally is.

The check that this is right: the FEA link L1_ankle_foot, which the whole structural
campaign solved as "the foot", integrates to 262.0 cm3, and the four foot-plate solids sum
to 262.06 cm3. The campaign's foot and the geometric foot are the same object; the rest of
the group was never part of it.

Usage: ankle_group_split.py
"""
import json

import numpy as np

CAD = '/home/syaro/pyg_fea/steps'
RHO = 2.70e-3            # kg/cm3, 6061
ANKLE_Z = -800.0
MOTOR_KG = 0.88          # RS03 catalog (the table's 0.932 is a placeholder, docs/83 s1)
FEA_FOOT_CM3 = 262.0     # what the campaign actually solved as L1_ankle_foot
JMC = {'A': ([-83.7, 205.7, -523.2], [-86.2, 195.0, -810.0]),
       'B': ([-163.7, 208.0, -616.0], [-161.2, 195.0, -810.0])}
CRANK_Z = (-503.7, -602.5)   # the cranks sit on the motor shafts


def main():
    S = [r for r in json.load(open(f'{CAD}/fullbody_links.json'))
         if r['link'] == 'L1_ankle_foot']
    assert S, 'no L1_ankle_foot solids'
    tot = sum(r['vol'] for r in S)

    def is_joint_part(r):
        # the JMC-JS06 rod-end spherical bearings and their flanges are bought parts, not
        # structure; the FEA never meshed them, so they are kept in their own bucket
        return 'JMC-JS06' in r['path'] or 'Flange' in r['path']

    import numpy as np
    rod_ids = set()
    for up, dn in JMC.values():
        mid = [(a + b) / 2 for a, b in zip(up, dn)]
        cand = min((r for r in S if not is_joint_part(r)),
                   key=lambda r: sum((a - b) ** 2 for a, b in zip(r['com'], mid)))
        err = sum((a - b) ** 2 for a, b in zip(cand['com'], mid)) ** 0.5
        assert err < 1.0, (
            f'rod check: nearest solid COM is {err:.1f} mm off the ball-joint midpoint')
        rod_ids.add(id(cand))

    foot, shin, rods, joints = [], [], [], []
    for r in S:
        z = r['com'][2]
        if is_joint_part(r):
            joints.append(r)
        elif id(r) in rod_ids:
            rods.append(r)
        elif z <= ANKLE_Z:
            foot.append(r)
        else:
            shin.append(r)   # clevis fork + braces + cranks: all shin-fixed or motor-borne
    assert len(rods) == 2, f'expected 2 push rods, matched {len(rods)}'
    vf = sum(r['vol'] for r in foot)
    vs = sum(r['vol'] for r in shin)
    vr = sum(r['vol'] for r in rods)
    vj_foot = sum(r['vol'] for r in joints if r['com'][2] <= ANKLE_Z)
    vj_shin = sum(r['vol'] for r in joints if r['com'][2] > ANKLE_Z)
    assert abs(vf + vs + vr + vj_foot + vj_shin - tot) < 1e-6, \
        'the split must conserve volume'

    # the campaign's foot: the four plate solids, excluding the cross that sits on the axis
    cross = min(foot, key=lambda r: abs(r['com'][2] - ANKLE_Z))
    v_plate = vf - cross['vol']
    print(f'Ankle2Feet 그룹: 솔리드 {len(S)}개 · {tot:.1f} cm3 · {tot * RHO:.3f} kg (알루미늄)')
    print(f'  z 범위 {min(r["com"][2] for r in S):.1f} ~ {max(r["com"][2] for r in S):.1f} mm '
          f'(발목 축 {ANKLE_Z:.0f})\n')
    print(f"{'구분':22s} {'솔리드':>6s} {'cm3':>8s} {'kg':>8s}")
    print(f'{"발측 구조":26s} {len(foot):6d} {vf:8.2f} {vf * RHO:8.3f}')
    print(f'{"  - 캠페인 FEA 발(발판)":26s} {len(foot)-1:6d} {v_plate:8.2f} {v_plate * RHO:8.3f}')
    print(f'{"  - 발목 크로스(축상)":26s} {1:6d} {cross["vol"]:8.2f} {cross["vol"] * RHO:8.3f}')
    print(f'{"로드 2개 (50/50 분배)":26s} {len(rods):6d} {vr:8.2f} {vr * RHO:8.3f}')
    print(f'{"정강이측(클레비스 포크+크랭크)":26s} {len(shin):6d} {vs:8.2f} {vs * RHO:8.3f}')
    print(f'{"JMC-JS06 볼조인트·플랜지 (발측)":26s} '
          f'{len([r for r in joints if r["com"][2] <= ANKLE_Z]):6d} {vj_foot:8.2f} '
          f'{vj_foot * RHO:8.3f}')
    print(f'{"JMC-JS06 볼조인트·플랜지 (정강이측)":26s} '
          f'{len([r for r in joints if r["com"][2] > ANKLE_Z]):6d} {vj_shin:8.2f} '
          f'{vj_shin * RHO:8.3f}')
    assert abs(v_plate - FEA_FOOT_CM3) < 1.0, (
        f'the four plate solids sum to {v_plate:.2f} cm3 but the campaign FEA solved '
        f'{FEA_FOOT_CM3} cm3 - they are not the same object and the whole foot verdict '
        'would be attached to the wrong geometry')
    print(f'\n★ 캠페인이 푼 L1_ankle_foot {FEA_FOOT_CM3:.1f} cm3 = 발판 솔리드 4개 '
          f'{v_plate:.2f} cm3 → 같은 물체다.')

    m_foot = (vf + vj_foot + 0.5 * vr) * RHO
    m_shin = (vs + vj_shin + 0.5 * vr) * RHO + 2 * MOTOR_KG
    print(f'\n== 강체 귀속 (나사·베어링 제외, 알루미늄만)')
    print(f'  발    = 발측 {(vf + vj_foot) * RHO:.3f} + 로드 절반 {0.5 * vr * RHO:.3f} '
          f'= **{m_foot:.3f} kg**')
    print(f'  정강이 += 정강이측 {(vs + vj_shin) * RHO:.3f} + 로드 절반 {0.5 * vr * RHO:.3f} '
          f'+ RS03×2 {2 * MOTOR_KG:.3f} = **{m_shin:.3f} kg**')
    print(f'\n  RL 심 모델 발(ankle_pitch 0.1098 + foot 0.9736) = 1.083 kg')
    print(f'  → 발 질량 차이 {100 * (m_foot - 1.083) / 1.083:+.1f} % '
          f'(나사·베어링 미포함이므로 하한)')


if __name__ == '__main__':
    main()
