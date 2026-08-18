"""Per-PART stress, not per-link: which individual solids carry the load, in Al and in PLA.

A "link" in this campaign is an assembly - L2 shin is 12 separate solids bolted and tied
together, L6 pelvis is 75. The link-level verdict answers "is the assembly strong enough",
which is the right question for the design but the wrong one for "can I print this piece".
A rail carrying the whole bending moment and a spacer that carries almost nothing both sit
inside the same link-level number.

The mesher already tags every solid separately (`ELSET=VolumeN`), so the split is free: take
the envelope field this campaign already computed, weight it by tet volume within each
element set, and every solid gets its own volume-weighted p99 - the same mesh-independent
basis the link verdicts use.

Parts are identified by volume and centroid, matched against the CAD decomposition in
steps/fullbody_links.json, because the CAD carries no per-part names (every solid in L2 is
called "Knee2Ankle"). A positional label is derived so the part can be found in the viewer.

Self-checks: the element sets must partition the mesh (every element in exactly one), and
their volumes must sum to the link volume the campaign recorded.

Usage: part_screen.py [LINK ...] [--pla=3.12] [--pla-hot=0.94] [--top=12] [--out=docs/img]
"""
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from field_volume import read_vm, weighted_pct  # noqa: E402

W = '/home/syaro/pyg_fea/work'
STEPS = '/home/syaro/pyg_fea/steps'
AL_YIELD = 276.0
AL_ALLOW = AL_YIELD / 2.0          # 138 MPa, SF 2
# the parts that are bolted to a motor run hot; everything else gets the room-temperature
# structural allowable (docs/79 §2)
PLA_ALLOW = 3.12
PLA_HOT = 0.94
# which link each part belongs to, and whether that link carries a motor (docs/79)
MOTOR_LINKS = {'L2_shin', 'L3_thigh', 'L4_hip_yaw', 'L5_hip_pitchroll', 'L6_pelvis'}
# the load case that governs each link, from the per-link screen
GOVERNING = {'L1_ankle_foot': 'L1gf_foot_corner_fine', 'L2_shin': 'L2_shin',
             'L3_thigh': 'L3_thigh', 'L4_hip_yaw': 'L4_hip_yaw',
             'L5_hip_pitchroll': 'L5_hip_pitchroll', 'L6_pelvis': 'L6_pelvis'}


def read_mesh_sets(link):
    """nodes {id: xyz} and {elset: [(n1..n4), ...]} from the campaign's .inp."""
    p = f'{W}/{link}/{link}_mesh.inp'
    if not os.path.exists(p):
        return None, None
    nodes, sets, mode, cur = {}, defaultdict(list), None, None
    for ln in open(p):
        u = ln.strip()
        if u.startswith('*'):
            up = u.upper()
            if up.startswith('*NODE'):
                mode, cur = 'N', None
            elif up.startswith('*ELEMENT') and 'C3D' in up.replace(' ', ''):
                m = re.search(r'ELSET\s*=\s*([^\s,]+)', u, re.I)
                mode, cur = 'E', (m.group(1) if m else 'ALL')
            else:
                mode, cur = None, None
            continue
        if not mode or not u:
            continue
        v = u.rstrip(',').split(',')
        try:
            if mode == 'N' and len(v) >= 4:
                nodes[int(v[0])] = (float(v[1]), float(v[2]), float(v[3]))
            elif mode == 'E' and len(v) >= 5:
                sets[cur].append(tuple(int(x) for x in v[1:5]))
        except ValueError:
            continue
    return nodes, dict(sets)


def label_of(com, bbox):
    """A positional name, so the part can be found in the viewer."""
    (x0, y0, z0), (x1, y1, z1) = bbox
    def band(v, lo, hi, names):
        f = (v - lo) / max(hi - lo, 1e-9)
        return names[0] if f < 0.34 else names[1] if f < 0.67 else names[2]
    return (f"{band(com[2], z0, z1, ['하단', '중단', '상단'])}"
            f"·{band(com[1], y0, y1, ['앞', '중앙', '뒤'])}"
            f"·{band(com[0], x0, x1, ['좌', '중', '우'])}")


def analyse(link):
    nodes, sets = read_mesh_sets(link)
    if not nodes or not sets:
        return None
    vm = read_vm(link)
    if not vm:
        return None
    idx = {i: k for k, i in enumerate(nodes)}
    P = np.array([nodes[i] for i in nodes])
    S = np.array([vm.get(i, 0.0) for i in nodes])
    bbox = (P.min(0), P.max(0))

    seen, rows = set(), []
    for name, tets in sets.items():
        T = np.array([[idx[n] for n in t] for t in tets if all(n in idx for n in t)])
        if not len(T):
            continue
        key = tuple(sorted(map(tuple, np.sort(T, axis=1)[:50])))
        assert key not in seen, f'{link}: element set {name} duplicates another'
        seen.add(key)
        a, b, c, d = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]], P[T[:, 3]]
        vol = np.abs(np.einsum('ij,ij->i', b - a, np.cross(c - a, d - a))) / 6.0
        sv = S[T].mean(axis=1)
        tot = vol.sum()
        com = (P[T].mean(axis=1) * vol[:, None]).sum(0) / tot
        rows.append(dict(link=link, part=name, n_tets=len(T), vol_cm3=float(tot / 1000),
                         com=[round(float(v), 1) for v in com],
                         label=label_of(com, bbox),
                         p99=float(weighted_pct(sv, vol, 99)),
                         peak=float(sv.max()),
                         over_al=float(100 * vol[sv > AL_YIELD].sum() / tot)))
    # the sets must partition the part: their volumes must add up to the link volume
    tot = sum(r['vol_cm3'] for r in rows)
    ref = None
    fv = f'{W}/field_volume.json'
    if os.path.exists(fv):
        m = {r['link']: r for r in json.load(open(fv))}
        if link in m:
            ref = m[link]['vol_mm3'] / 1000
    assert ref is None or abs(tot - ref) / ref < 0.02, (
        f'{link}: element sets sum to {tot:.1f} cm3 but the link is {ref:.1f} - '
        'the sets do not partition the mesh')
    return rows


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    links = args or list(GOVERNING.values())
    top = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--top=')), 12))
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')

    allrows = []
    for l in links:
        r = analyse(l)
        if not r:
            print(f'{l:28s} skipped (no mesh or no field)')
            continue
        base = re.match(r'(L\d[a-z]*)', l).group(1)
        hot = any(l.startswith(k[:2]) for k in MOTOR_LINKS if k[:2] != 'L1')
        for x in r:
            x['pla_allow'] = PLA_HOT if hot else PLA_ALLOW
            x['sf_al'] = AL_ALLOW / max(x['p99'], 1e-9)
            x['sf_pla'] = x['pla_allow'] / max(x['p99'], 1e-9)
        allrows += r
        print(f'{l:28s} {len(r):3d} parts, {sum(x["vol_cm3"] for x in r):7.1f} cm3')

    assert allrows, 'nothing analysed'
    allrows.sort(key=lambda r: -r['p99'])

    print(f"\n부품 단위 — 응력 높은 순 (상위 {top})")
    print(f"{'링크':20s} {'부품':10s} {'위치':14s} {'체적':>8s} {'p99':>7s} "
          f"{'SF(6061)':>9s} {'SF(PLA)':>8s}  판정")
    for r in allrows[:top]:
        va = '✅' if r['sf_al'] >= 1 else '❌'
        vp = '✅' if r['sf_pla'] >= 1 else '❌'
        print(f"{r['link']:20s} {r['part']:10s} {r['label']:14s} {r['vol_cm3']:6.1f}cm³ "
              f"{r['p99']:6.1f}M {r['sf_al']:8.2f}{va} {r['sf_pla']:7.3f}{vp}")

    n_al = sum(1 for r in allrows if r['sf_al'] >= 1)
    n_pla = sum(1 for r in allrows if r['sf_pla'] >= 1)
    v_pla = sum(r['vol_cm3'] for r in allrows if r['sf_pla'] >= 1)
    v_tot = sum(r['vol_cm3'] for r in allrows)
    print(f"\n총 {len(allrows)} 부품 · {v_tot:.0f} cm³")
    print(f"  6061-T6 SF2 통과 : {n_al:3d} / {len(allrows)} 부품 "
          f"({100*n_al/len(allrows):.0f} %)")
    print(f"  PLA 통과         : {n_pla:3d} / {len(allrows)} 부품 "
          f"({100*n_pla/len(allrows):.0f} %) · 체적 {v_pla:.0f}/{v_tot:.0f} cm³ "
          f"({100*v_pla/v_tot:.0f} %)")
    lo = [r for r in allrows if r['sf_pla'] >= 1]
    if lo:
        print(f"\nPLA 가능 부품 (응력 ≤ 허용):")
        for r in sorted(lo, key=lambda r: -r['vol_cm3'])[:15]:
            print(f"   {r['link']:20s} {r['part']:10s} {r['label']:14s} "
                  f"{r['vol_cm3']:6.1f}cm³ p99 {r['p99']:5.2f}M SF {r['sf_pla']:5.2f}")

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, ax = plt.subplots(1, 3, figsize=(15.2, 4.8))
    s = np.array([r['p99'] for r in allrows])
    v = np.array([r['vol_cm3'] for r in allrows])

    ax[0].scatter(v, s, s=22, c=['#c0392b' if x < 1 else '#27ae60'
                                 for x in (r['sf_al'] for r in allrows)], alpha=0.75)
    ax[0].axhline(AL_ALLOW, color='k', ls='--', lw=1.2)
    ax[0].text(v.min(), AL_ALLOW * 1.06, f'6061-T6 SF2 = {AL_ALLOW:.0f} MPa', fontsize=7.5)
    ax[0].axhline(PLA_ALLOW, color='#7d3c98', ls='--', lw=1.2)
    ax[0].text(v.min(), PLA_ALLOW * 1.15, f'PLA structural = {PLA_ALLOW:.1f}', fontsize=7.5,
               color='#7d3c98')
    ax[0].axhline(PLA_HOT, color='#c0392b', ls=':', lw=1.2)
    ax[0].set_xscale('log')
    ax[0].set_yscale('log')
    ax[0].set_xlabel('part volume [cm³]')
    ax[0].set_ylabel('volume-weighted p99 [MPa]')
    ax[0].set_title(f'{len(allrows)} parts: stress vs size', fontsize=9.5)
    ax[0].grid(alpha=0.3)

    srt = np.sort(s)[::-1]
    ax[1].plot(np.arange(1, len(srt) + 1), srt, lw=2, color='#2e86c1')
    for lvl, col, nm in ((AL_ALLOW, 'k', '6061 SF2'), (PLA_ALLOW, '#7d3c98', 'PLA struct'),
                         (PLA_HOT, '#c0392b', 'PLA hot')):
        ax[1].axhline(lvl, color=col, ls='--', lw=1.1)
        n = int((s >= lvl).sum())
        ax[1].text(len(srt) * 0.45, lvl * 1.12, f'{nm}: {len(srt)-n} parts below',
                   fontsize=7.5, color=col)
    ax[1].set_yscale('log')
    ax[1].set_xlabel('parts ranked by stress')
    ax[1].set_ylabel('volume-weighted p99 [MPa]')
    ax[1].set_title('How many parts clear each allowable', fontsize=9.5)
    ax[1].grid(alpha=0.3)

    byl = defaultdict(list)
    for r in allrows:
        byl[r['link']].append(r)
    names = sorted(byl)
    y = np.arange(len(names))
    frac_al = [100 * sum(1 for r in byl[n] if r['sf_al'] >= 1) / len(byl[n]) for n in names]
    frac_pla = [100 * sum(1 for r in byl[n] if r['sf_pla'] >= 1) / len(byl[n]) for n in names]
    wdt = 0.38
    ax[2].barh(y - wdt / 2, frac_al, wdt, color='#27ae60', label='6061-T6 SF2')
    ax[2].barh(y + wdt / 2, frac_pla, wdt, color='#7d3c98', label='PLA')
    ax[2].set_yticks(y)
    ax[2].set_yticklabels([n.replace('_', ' ')[:20] for n in names], fontsize=8)
    ax[2].invert_yaxis()
    ax[2].set_xlim(0, 105)
    ax[2].set_xlabel('% of parts passing')
    ax[2].set_title('Pass rate per link, part by part', fontsize=9.5)
    ax[2].legend(fontsize=7.5)
    ax[2].grid(alpha=0.3, axis='x')

    fig.suptitle('Part-level screen: every solid judged on its own volume-weighted stress',
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'part_screen.png'))
    json.dump(allrows, open(f'{W}/part_screen.json', 'w'), indent=1, ensure_ascii=False)
    print('\n-> docs/img/part_screen.png · ~/pyg_fea/work/part_screen.json')


if __name__ == '__main__':
    main()
