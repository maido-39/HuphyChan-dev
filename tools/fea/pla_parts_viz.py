"""Where a PLA print would fail, per part - static maps plus the viewer payload.

The link- and part-level screens answered "does it pass" (it does not). This answers
"where", which is the question you need before deciding whether a part is salvageable in
a different material or only in a different design.

Two outputs:

  docs/img/pla_failure_map.png   surface nodes of every link, coloured by how many times
                                 over the PLA allowable they sit. Because the allowable is
                                 2 MPa and the stresses are 20-110 MPa, almost everything
                                 is over - so the informative field is the RATIO, and the
                                 map's job is to show the gradient and to find the small
                                 regions that are actually under it.

  link_setup_*.json              gains `part_id` per surface node and a `parts` block with
                                 per-part volume, stress and over-allowable fraction, so
                                 the viewer can colour by part and switch material.

Part membership comes from the mesher's own element sets (`ELSET=VolumeN`); the viewer
payload stores coordinates rather than node ids, so surface nodes are matched back to the
mesh by nearest neighbour, with an assert on the match distance.

Usage: pla_parts_viz.py [LINK ...] [--allow=2.0] [--out=docs/img]
"""
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np
from scipy.spatial import cKDTree

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from part_screen import read_mesh_sets  # noqa: E402
from field_volume import read_vm  # noqa: E402

W = '/home/syaro/pyg_fea/work'
STATIC = '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/static'
AL_ALLOW = 138.0           # 6061-T6 at SF 2
PLA_ALLOW = 2.0            # docs/79 §8a, fatigue-governed
PLA_INPLANE = 5.0          # absolute ceiling, proven in-plane principal direction
# the case that represents each part in the viewer
LINKS = ['L1gf_foot_corner_fine', 'L2_shin', 'L3_thigh', 'L4_hip_yaw',
         'L5_hip_pitchroll', 'L6_pelvis']


def node_parts(link):
    """mesh node id -> part name, by majority of the tets touching that node."""
    nodes, sets = read_mesh_sets(link)
    if not nodes or not sets:
        return None, None
    votes = defaultdict(Counter)
    for name, tets in sets.items():
        for t in tets:
            for n in t:
                votes[n][name] += 1
    return nodes, {n: c.most_common(1)[0][0] for n, c in votes.items()}


def main():
    allow = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--allow=')),
                       PLA_ALLOW))
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    links = [a for a in sys.argv[1:] if not a.startswith('--')] or LINKS

    ps = {}
    if os.path.exists(f'{W}/part_screen.json'):
        for r in json.load(open(f'{W}/part_screen.json')):
            ps[(r['link'], r['part'])] = r

    panels, wrote = [], 0
    for link in links:
        pay = f'{STATIC}/link_setup_{link}.json'
        if not os.path.exists(pay):
            print(f'{link:28s} no viewer payload - skipped')
            continue
        nodes, npart = node_parts(link)
        if not nodes:
            print(f'{link:28s} no mesh - skipped')
            continue
        D = json.load(open(pay))
        tier = 'peak' if 'peak' in D else next(iter(D))
        S = D[tier]
        P = np.asarray(S['nodes'], float)
        ids = list(nodes)
        tree = cKDTree(np.array([nodes[i] for i in ids]))
        dist, k = tree.query(P)
        # The stored payload is the PEAK tier, which doctrine (docs/62) says is an overload
        # check, not a design basis. Every verdict in this campaign is on P99 x 1.25, so
        # rebuild that field and judge on it; the peak one stays available in the viewer.
        vmP99 = read_vm(link)
        assert vmP99, f'{link}: cannot rebuild the P99 field - the unit .frd files are gone'
        full = np.array([vmP99.get(i, 0.0) for i in ids])
        vm = full[k]
        S.setdefault('fields', {})['vM_P99'] = [round(float(v), 2) for v in vm]
        S['design_tier'] = 'P99x1.25'
        assert len(P) == len(vm), f'{link}: {len(P)} nodes vs {len(vm)} stresses'
        assert dist.max() < 1.0, (
            f'{link}: a viewer node is {dist.max():.2f} mm from any mesh node - '
            'the payload and the mesh are not the same geometry')
        pid = [npart.get(ids[j], '?') for j in k]

        names = sorted(set(pid))
        S['part_id'] = [names.index(p) for p in pid]
        S['part_names'] = names
        S['materials'] = {'6061-T6 (SF2)': AL_ALLOW, 'PLA 피로 (층간)': allow,
                          'PLA 피로 (면내 상한)': PLA_INPLANE,
                          'PLA 정적 층간': 11.3, 'PLA 정적 면내': 25.5}
        S['parts'] = []
        for nm in names:
            m = np.array([p == nm for p in pid])
            r = ps.get((link, nm), {})
            S['parts'].append(dict(
                name=nm, n_surf=int(m.sum()), label=r.get('label', ''),
                vol_cm3=round(r.get('vol_cm3', 0.0), 1), p99=round(r.get('p99', 0.0), 2),
                surf_max=round(float(vm[m].max()) if m.any() else 0.0, 1),
                over_al=round(100 * float((vm[m] > AL_ALLOW).mean()) if m.any() else 0.0, 2),
                over_pla=round(100 * float((vm[m] > allow).mean()) if m.any() else 0.0, 1)))
        json.dump(D, open(pay, 'w'), separators=(',', ':'))
        wrote += 1
        panels.append((link, P, vm, pid, names))
        nover = 100 * float((vm > allow).mean())
        print(f'{link:28s} {len(names):3d} parts · 표면절점 {len(P):6d} · '
              f'PLA 허용 초과 {nover:5.1f} % · 알루미늄 초과 {100*float((vm>AL_ALLOW).mean()):4.1f} %')

    assert panels, 'nothing to draw'

    # ---- static map: every link, coloured by multiples of the PLA allowable ----
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    n = len(panels)
    fig, axes = plt.subplots(2, n, figsize=(3.2 * n, 8.0),
                             gridspec_kw=dict(height_ratios=[3, 2]))
    if n == 1:
        axes = axes.reshape(2, 1)
    for j, (link, P, vm, pid, names) in enumerate(panels):
        ratio = np.maximum(vm / allow, 1e-3)
        a = axes[0, j]
        o = np.argsort(ratio)
        sc = a.scatter(P[o, 1], P[o, 2], c=ratio[o], s=1.2, cmap='inferno',
                       norm=LogNorm(vmin=0.2, vmax=120))
        a.set_aspect('equal')
        a.set_title(f"{link.split('_')[0]} {link.split('_')[1][:8]}\n"
                    f"{100*float((vm>allow).mean()):.0f} % over PLA", fontsize=8.5, pad=4)
        a.set_xticks([])
        a.set_yticks([])
        if j == 0:
            a.set_ylabel('side view (y-z)', fontsize=8)
        # per-part bars: how far over, worst part first
        b = axes[1, j]
        rows = [(nm, float(np.max(vm[[p == nm for p in pid]]) / allow))
                for nm in names if any(p == nm for p in pid)]
        rows.sort(key=lambda t: -t[1])
        rows = rows[:10]
        y = np.arange(len(rows))
        b.barh(y, [r[1] for r in rows],
               color=['#c0392b' if r[1] > 1 else '#27ae60' for r in rows])
        b.axvline(1.0, color='k', ls='--', lw=1.1)
        b.set_yticks(y)
        b.set_yticklabels([r[0].replace('Volume', 'V') for r in rows], fontsize=6.5)
        b.invert_yaxis()
        b.set_xscale('log')
        b.set_xlabel('× over PLA allowable', fontsize=7.5)
        b.grid(alpha=0.3, axis='x')
    cb = fig.colorbar(sc, ax=axes[0, :].tolist(), fraction=0.02, pad=0.01)
    cb.set_label(f'× over the PLA allowable ({allow:.1f} MPa)', fontsize=8)
    fig.suptitle(f'Where a PLA print fails: surface stress as a multiple of the '
                 f'{allow:.1f} MPa fatigue allowable (green = under)', fontsize=10)
    fig.subplots_adjust(hspace=0.32, wspace=0.28, top=0.90)
    fig.savefig(os.path.join(out, 'pla_failure_map.png'), bbox_inches='tight')
    print(f'\n-> docs/img/pla_failure_map.png · {wrote} viewer payloads updated')


if __name__ == '__main__':
    main()
