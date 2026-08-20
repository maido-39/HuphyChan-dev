"""Audit of the final-design mass table before it is committed to the notes.

The table arrives as prose, so the first job is arithmetic - link rows against the declared
total, part rows against their link, category totals against both. That part is mechanical
and it passes. The second job is the part arithmetic cannot do: whether the numbers are
PHYSICALLY consistent. Two checks find things:

  motor mass       a QDD actuator's torque density is a hard fact of its magnet and gear
                   train, so plotting N.m/kg exposes a mass that cannot belong to the motor
                   it is named after, no matter how the column sums.
  side count       the actuator inventory says how many limbs are present. Fifteen motors on
                   a machine whose DoF list needs twenty-six means the table is one side.

Usage: mass_table_review.py [--out=docs/img]
"""
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

# the table as given [kg]
LINKS = [('CenterParts', 4.429), ('Ankle2Feet', 3.818), ('Neck', 3.058), ('Torso', 2.998),
         ('Shoulder-Roll2Yaw', 2.794), ('Knee2Ankle', 2.598), ('HipPitch2Roll', 2.262),
         ('WaistYaw2Pitch', 2.163), ('PipRoll2Yaw', 1.536), ('HipYaw2Knee', 1.476),
         ('Shoulder-Pitch2Roll', 1.418), ('Wlbow2WaistYaw', 1.125),
         ('Shoulderyaw2Elbowpitch', 0.838), ('Waist2HandAdapt', 0.508)]
# per link: aluminium, screws, bearings, actuators
BREAK = {
    'CenterParts': (1.111, 0.201, 0.0, 3.116), 'Ankle2Feet': (1.643, 0.169, 0.142, 1.864),
    'Neck': (0.622, 0.0, 0.0, 2.436), 'Torso': (1.320, 0.0, 1.677, 0.0),
    'Shoulder-Roll2Yaw': (0.430, 0.0, 0.0, 2.364), 'Knee2Ankle': (0.854, 0.185, 0.0, 1.558),
    'HipPitch2Roll': (0.582, 0.122, 0.0, 1.558), 'WaistYaw2Pitch': (0.155, 0.0, 0.0, 2.008),
    'PipRoll2Yaw': (0.505, 0.100, 0.0, 0.932), 'HipYaw2Knee': (1.270, 0.189, 0.017, 0.0),
    'Shoulder-Pitch2Roll': (0.486, 0.0, 0.0, 0.932), 'Wlbow2WaistYaw': (0.194, 0.0, 0.0, 0.932),
    'Shoulderyaw2Elbowpitch': (0.838, 0.0, 0.0, 0.0), 'Waist2HandAdapt': (0.508, 0.0, 0.0, 0.0)}
# motor: (peak N.m, mass in the table, catalog mass, catalog source)
MOTOR = {'RS04': (120.0, 1.558, 1.42, 'docs/33 · 84.5 N·m/kg'),
         'RS03': (60.0, 0.932, 0.88, 'docs/37·39·41'),
         'RS02': (17.0, 1.432, 0.405, 'docs/39 L29 · RS01/RS02 380-405 g'),
         'RS00': (14.0, 1.004, 0.31, 'docs/36·39')}
# Fusion360 measurement (2026-08-20, docs/83 §1): every motor occurrence is a single
# placeholder solid in generic Steel, bbox matching the catalog envelope - so the table's
# motor masses are volume x wrong density, and the catalog values replace ALL of them,
# not just the two that looked absurd.
CORRECTED_FULL = 44.509
COUNT = {'RS04': 4, 'RS03': 6, 'RS02': 2, 'RS00': 3}
# which links are one-of-a-pair
PER_SIDE = {'HipPitch2Roll', 'PipRoll2Yaw', 'HipYaw2Knee', 'Knee2Ankle', 'Ankle2Feet',
            'Shoulder-Pitch2Roll', 'Shoulder-Roll2Yaw', 'Shoulderyaw2Elbowpitch',
            'Wlbow2WaistYaw', 'Waist2HandAdapt'}
MIRRORED_MOTORS = 1.558 + 1.004      # Hip_R inside CenterParts, Elbow_Yaw inside WaistYaw2Pitch
RL_TOTAL = 51.5268


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    tot = sum(v for _, v in LINKS)
    assert abs(tot - 31.021) < 0.002, f'link rows sum to {tot:.3f}, not the declared 31.021'
    for k, v in LINKS:
        assert abs(sum(BREAK[k]) - v) < 0.007, f'{k}: parts {sum(BREAK[k]):.3f} vs {v:.3f}'
    act = sum(BREAK[k][3] for k, _ in LINKS)
    assert abs(act - 17.700) < 0.002, f'actuators sum to {act:.3f}, not 17.700'
    nmot = sum(COUNT.values())
    assert abs(sum(MOTOR[m][1] * COUNT[m] for m in MOTOR) - act) < 0.005, \
        'the motor inventory does not reproduce the actuator total'

    side = sum(v for k, v in LINKS if k in PER_SIDE)
    full = tot + side + MIRRORED_MOTORS
    print(f'표 합계          {tot:7.3f} kg   (모터 {nmot}개)')
    print(f'편측 링크 합      {side:7.3f} kg + 미러 모터 {MIRRORED_MOTORS:.3f}')
    print(f'→ 좌우 완성 추정  {full:7.3f} kg   vs RL 모델 {RL_TOTAL:.3f} '
          f'({100 * (full - RL_TOTAL) / RL_TOTAL:+.2f} %)')
    print(f'\n{"모터":6s} {"peak":>7s} {"표 kg":>7s} {"카탈로그":>9s} {"차이":>8s} '
          f'{"표 N·m/kg":>10s} {"카탈로그 N·m/kg":>15s}')
    for m, (t, mt, cat, _) in MOTOR.items():
        c = f'{cat:9.3f}' if cat else f'{"—":>9s}'
        dv = f'{100 * (mt - cat) / cat:+7.1f}%' if cat else f'{"—":>8s}'
        cd = f'{t / cat:15.1f}' if cat else f'{"—":>15s}'
        print(f'{m:6s} {t:7.0f} {mt:7.3f} {c} {dv} {t / mt:10.1f} {cd}')

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 140, 'font.size': 9})
    fig, ax = plt.subplots(1, 3, figsize=(16.0, 5.4),
                           gridspec_kw=dict(width_ratios=[1.5, 0.85, 1.15]))

    # (a) link mass, stacked by category
    names = [k for k, _ in LINKS]
    cats = ['aluminium', 'screws', 'bearings', 'actuators']
    cols = ['#7fb3ff', '#f0b27a', '#a9dfbf', '#c0392b']
    y = np.arange(len(names))
    left = np.zeros(len(names))
    for j, (c, col) in enumerate(zip(cats, cols)):
        v = np.array([BREAK[k][j] for k in names])
        ax[0].barh(y, v, 0.68, left=left, color=col, label=c)
        left += v
    for i, k in enumerate(names):
        ax[0].annotate(f'{sum(BREAK[k]):.2f}', (sum(BREAK[k]) + 0.06, i), fontsize=7,
                       va='center')
        if k in PER_SIDE:
            ax[0].annotate('×2', (-0.30, i), fontsize=7.5, va='center', color='#c0392b',
                           weight='bold')
    ax[0].set_yticks(y)
    ax[0].set_yticklabels(names, fontsize=8)
    ax[0].invert_yaxis()
    ax[0].set_xlim(-0.45, 5.2)
    ax[0].set_xlabel('mass [kg]', fontsize=8.5)
    ax[0].set_title('final-design table, per link\n'
                    '×2 marks a link the mirrored side also needs', fontsize=9.5)
    ax[0].legend(fontsize=7.5, loc='lower right')
    ax[0].grid(alpha=0.3, axis='x')

    # (b) what the table covers vs a complete machine
    ax[1].bar(['table\nas given', 'both sides\n(placeholder\nmotors)',
               'both sides\n(catalog\nmotors)', 'RL sim\nmodel'],
              [tot, full, CORRECTED_FULL, RL_TOTAL],
              color=['#e8927c', '#e8927c', '#c0392b', '#3b82f6'], width=0.62)
    ax[1].bar(['both sides\n(placeholder\nmotors)'], [side + MIRRORED_MOTORS],
              bottom=[tot], color='none', edgecolor='#111', lw=1.2, hatch='//', width=0.62)
    for i, v in enumerate([tot, full, CORRECTED_FULL, RL_TOTAL]):
        ax[1].annotate(f'{v:.2f}', (i, v + 0.7), ha='center', fontsize=9, weight='bold')
    ax[1].annotate(f'+{side + MIRRORED_MOTORS:.2f} kg\nmirrored limb', (1, tot / 2 + 8),
                   ha='center', fontsize=7.5)
    ax[1].set_ylabel('mass [kg]', fontsize=8.5)
    ax[1].set_ylim(0, 60)
    ax[1].set_title('one side; with catalog motors the robot is\n'
                    f'{CORRECTED_FULL:.1f} kg, {100 * (CORRECTED_FULL - RL_TOTAL) / RL_TOTAL:+.1f} % vs the sim model',
                    fontsize=9.5)
    ax[1].grid(alpha=0.3, axis='y')

    # (c) torque density - the physical check
    ms = list(MOTOR)
    xt = [MOTOR[m][0] / MOTOR[m][1] for m in ms]
    xc = [MOTOR[m][0] / MOTOR[m][2] if MOTOR[m][2] else np.nan for m in ms]
    y = np.arange(len(ms))
    ax[2].barh(y - 0.19, xt, 0.36, color='#c0392b', label='from the table')
    ax[2].barh(y + 0.19, xc, 0.36, color='#7fb3ff', label='catalog (docs/33·36·37·39)')
    for i, m in enumerate(ms):
        ax[2].annotate(f'{MOTOR[m][1]:.3f} kg', (xt[i] + 1.5, i - 0.19), fontsize=7,
                       va='center', color='#c0392b')
        if MOTOR[m][2]:
            ax[2].annotate(f'{MOTOR[m][2]:.2f} kg', (xc[i] + 1.5, i + 0.19), fontsize=7,
                           va='center', color='#2e86c1')
    ax[2].set_yticks(y)
    ax[2].set_yticklabels([f'{m}  ({MOTOR[m][0]:.0f} N·m)' for m in ms], fontsize=8)
    ax[2].invert_yaxis()
    ax[2].set_xlim(0, 105)
    ax[2].set_xlabel('peak torque density [N·m/kg]', fontsize=8.5)
    ax[2].set_title('placeholder solids x generic Steel:\n'
                    'RS00/RS02 land 3.2-3.5x over, RS04/RS03 near-miss', fontsize=9.5)
    ax[2].legend(fontsize=7.5, loc='lower right')
    ax[2].grid(alpha=0.3, axis='x')

    fig.suptitle('Final-design mass table — audit: the arithmetic closes, '
                 'two motor masses and the side count do not', fontsize=11.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'mass_table_review.png'), bbox_inches='tight')
    print(f"\n-> {os.path.join(out, 'mass_table_review.png')}")


if __name__ == '__main__':
    main()
