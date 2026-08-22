"""Figure: the joint ranges the model carried vs the ones the CAD actually allows.

`rom_check.py` turns each joint in the assembled CAD until two solids that were not already
touching push into each other, so the bar it produces is a measurement, not a preference.
The old range is drawn behind it: where the old bar sticks out past the measured one, the
model was letting the policy command a pose the hardware cannot reach.

The ankle pair is drawn hatched: its 2-RSU chain is closed, a serial sweep cannot decide it,
and the range comes from the mechanism studies instead.

Usage: plot_rom.py   (mjlab .venv python; writes docs/img/joint_rom_measured.png)
"""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
ROM = '/home/syaro/pyg_fea/fusion/rom_measured.json'
OUT = f'{REPO}/docs/img/joint_rom_measured.png'
# what the model carried before this pass (deg), inherited from the old MJCF
OLD = {'hip_pitch': (-125, 30), 'hip_roll': (-45, 25), 'hip_yaw': (-50, 50),
       'knee': (-120, 0), 'ankle_pitch': (-50, 30), 'ankle_roll': (-20, 20),
       'waist_yaw': (-60, 60), 'shoulder_pitch': (-180, 60), 'shoulder_roll': (-90, 15)}
CLOSED = {'ankle_pitch', 'ankle_roll'}      # a serial sweep cannot decide the 2-RSU ankle
XML = (f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v2.xml')


def main():
    import mujoco
    R = json.load(open(ROM))
    m = mujoco.MjModel.from_xml_path(XML)
    applied = {}
    for i in range(m.njnt):
        n = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, i) or ''
        base = n.replace('_joint', '')
        base = base[2:] if base[:2] in ('L_', 'R_') else base
        if base in OLD:
            applied[base] = tuple(np.degrees(m.jnt_range[i]))
    js = [j for j in OLD if j in R]
    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    y = np.arange(len(js))
    for i, j in enumerate(js):
        lo, hi = OLD[j]
        ax.barh(i + 0.26, hi - lo, 0.24, left=lo, color='#c94c4c', alpha=0.85,
                label='inherited from the old MJCF' if i == 0 else None)
        closed = j in CLOSED
        m_lo, m_hi = R[j]['free_deg']
        if closed:
            ax.barh(i, 2.0, 0.24, left=-1.0, color='#9a9a9a', hatch='xx',
                    label='sweep is a serial-model artifact' if j == 'ankle_pitch' else None)
        else:
            ax.barh(i, m_hi - m_lo, 0.24, left=m_lo, color='#3d7ea6',
                    label='CAD collision sweep' if i == 0 else None)
        a_lo, a_hi = applied[j]
        ax.barh(i - 0.26, a_hi - a_lo, 0.24, left=a_lo, color='#4f9d69',
                label='applied to the model' if i == 0 else None)
        for q, side in ((R[j]['blocked_lo'], 'lo'), (R[j]['blocked_hi'], 'hi')):
            if q is None or closed:
                continue
            ax.plot([q], [i], 'kv', ms=5)
            ax.annotate(R[j][f'blocker_{side}'].replace('_link', '').replace('L_', ''),
                        (q, i), textcoords='offset points', xytext=(0, -13), ha='center',
                        fontsize=6.2, color='0.25')
    ax.set_yticks(y)
    ax.set_yticklabels(js)
    ax.invert_yaxis()
    ax.axvline(0, color='k', lw=0.8)
    ax.set_xlabel('joint angle [deg]   (+ = flexion-side sign of the model convention)')
    ax.set_title('Pygmalion v2 joint range: inherited vs measured on the CAD (2026-08-22)',
                 fontsize=11)
    ax.grid(axis='x', alpha=0.3)
    ax.legend(fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.13),
              ncol=4, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT, dpi=130)
    print(f'-> {OUT}')
    for j in js:
        closed = j in CLOSED
        print(f'  {j:15s} old {str(OLD[j]):14s} sweep {str(tuple(R[j]["free_deg"])):16s}'
              f' -> applied {str(tuple(round(v, 1) for v in applied[j])):16s}'
              + ('  (closed chain: mechanism range)' if closed else
                 f"  stops: {R[j]['blocker_lo']} / {R[j]['blocker_hi']}"))


if __name__ == '__main__':
    main()
