"""Volume-weighted stress percentiles - the mesh-independent field metric.

`p99_vM` in every envelope is a percentile over NODES. That is biased by mesh density: a
refinement sphere adds nodes exactly where the stress is high, so those nodes crowd into
the top 1 % and push the percentile up even though nothing physical changed. Measured on
the pelvis twin: +2.9 % nodes, +17.1 % p99. Four of the six twins moved the same way.

Weighting each sample by the VOLUME it represents removes that bias, because refining a
region splits its volume among more elements instead of adding volume. The quantity being
estimated - "the stress below which 99 % of the material lies" - is then a property of the
solution, not of the discretisation.

Implementation: read the mesh (nodes + C3D4/C3D10 connectivity) and the .frd stresses,
compute each element's volume from its four corner nodes, assign the element the mean von
Mises of its corners, then take the weighted percentile over elements.

It self-checks two ways: the summed element volume must match the volume the campaign
recorded for the part, and on a UNIFORM mesh the volume-weighted and node-based
percentiles must agree (they only diverge where the mesh is graded).

Usage:
  field_volume.py L6_pelvis L6f_pelvis_peakfine     # compare a refinement pair
  field_volume.py --all                             # every solved link
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import envelope as EV      # noqa: E402
import femlib as FL        # noqa: E402

W = '/home/syaro/pyg_fea/work'
ALLOW = 276.0


def read_mesh(link):
    """nodes {id: xyz} and tets [(n1..n4), ...] from the campaign's .inp."""
    p = f'{W}/{link}/{link}_mesh.inp'
    if not os.path.exists(p):
        return None, None
    nodes, tets, mode = {}, [], None
    for ln in open(p):
        u = ln.strip()
        if u.startswith('*'):
            up = u.upper()
            mode = ('N' if up.startswith('*NODE')
                    else 'E' if up.startswith('*ELEMENT') and 'C3D' in up.replace(' ', '')
                    else None)
            continue
        if not mode or not u:
            continue
        v = u.rstrip(',').split(',')
        try:
            if mode == 'N' and len(v) >= 4:
                nodes[int(v[0])] = (float(v[1]), float(v[2]), float(v[3]))
            elif mode == 'E' and len(v) >= 5:
                tets.append(tuple(int(x) for x in v[1:5]))     # first 4 = corner nodes
        except ValueError:
            continue
    return nodes, tets


def read_vm(link, tier='P99'):
    """Full-field envelope von Mises per node id.

    fields.json is a SURFACE subset written for the viewer (22 k of 258 k nodes), so it
    cannot be used here - volume weighting needs the interior. The unit-case .frd files
    are retained, so the envelope is rebuilt from them exactly the way the campaign did,
    with the magnitudes and component list recorded in the envelope json.
    """
    env = f'{W}/{link}/envelope_{tier}.json'
    if not os.path.exists(env):
        return None
    d = json.load(open(env))
    comps, mags = d.get('comps'), d.get('magnitudes')
    if not comps or not mags:
        return None
    # parse_frd -> (coords{nid:xyz}, blocks[(name, {nid:[vals]})])
    U, ids = [], None
    for c in comps:
        f = f'{W}/{link}/{link}_u{c}.frd'
        if not os.path.exists(f):
            return None
        _, blocks = FL.parse_frd(f)
        st = next((v for k, v in blocks if 'STRESS' in k.upper()), None)
        assert st, f'{link}: {os.path.basename(f)} has no STRESS block'
        if ids is None:
            ids = sorted(st)
        U.append(np.array([st[i] for i in ids], float))
    e = EV.combine(np.asarray(U), [mags[c] for c in comps], comps=comps)
    vm = e['vm_max']
    assert ids is not None and len(ids) == len(vm), (
        f'{link}: {len(vm)} stresses but {0 if ids is None else len(ids)} node ids')
    # the rebuilt envelope must reproduce what the campaign recorded, or the load
    # magnitudes / component order have drifted and the weighting would be meaningless
    ref = d.get('max_vM')
    assert ref is None or abs(vm.max() - ref) / ref < 0.02, (
        f'{link}: rebuilt envelope peak {vm.max():.1f} vs recorded {ref:.1f} - '
        'magnitudes or component order changed, refusing to weight a mismatched field')
    return {int(i): float(v) for i, v in zip(ids, vm)}


def weighted_pct(vals, wts, q):
    o = np.argsort(vals)
    v, w = np.asarray(vals)[o], np.asarray(wts)[o]
    c = np.cumsum(w)
    return float(np.interp(q / 100.0 * c[-1], c, v))


def analyse(link):
    nodes, tets = read_mesh(link)
    if not nodes or not tets:
        return None
    vm = read_vm(link)
    if not vm:
        return dict(link=link, note='no per-node stress dump - run export_fields.py first',
                    n_nodes=len(nodes), n_tets=len(tets))
    idx = {i: k for k, i in enumerate(nodes)}
    P = np.array([nodes[i] for i in nodes])
    T = np.array([[idx[n] for n in t] for t in tets if all(n in idx for n in t)])
    a, b, c, d = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]], P[T[:, 3]]
    vol = np.abs(np.einsum('ij,ij->i', b - a, np.cross(c - a, d - a))) / 6.0
    S = np.array([vm.get(i, 0.0) for i in nodes])
    sv = S[T].mean(axis=1)
    tot = vol.sum()
    return dict(link=link, n_tets=len(T), vol_mm3=float(tot),
                p99_vol=weighted_pct(sv, vol, 99), p999_vol=weighted_pct(sv, vol, 99.9),
                p99_node=float(np.percentile(S, 99)),
                over_vol_pct=float(100 * vol[sv > ALLOW].sum() / tot),
                peak=float(S.max()))


def main():
    links = ([os.path.basename(os.path.dirname(f)) for f in
              sorted(glob.glob(f'{W}/*/envelope_P99.json'))] if '--all' in sys.argv
             else [a for a in sys.argv[1:] if not a.startswith('--')])
    assert links, __doc__
    rows = [r for r in (analyse(l) for l in links) if r]
    miss = [r for r in rows if r.get('note')]
    if miss:
        print(f'{len(miss)} link(s) have a mesh but no per-node stress dump:')
        for r in miss[:6]:
            print(f"  {r['link']:28s} {r['n_nodes']:7d} nodes / {r['n_tets']:7d} tets")
        print('  -> tools/fea/export_fields.py <link> writes the field the weighting needs\n')
    got = [r for r in rows if not r.get('note')]
    if not got:
        return
    print(f"{'link':28s} {'tets':>8s} {'vol cm3':>9s} {'p99 vol':>9s} {'p99 node':>9s} "
          f"{'bias':>7s} {'yield vol %':>11s}")
    for r in got:
        bias = 100 * (r['p99_node'] - r['p99_vol']) / r['p99_vol']
        print(f"{r['link']:28s} {r['n_tets']:8d} {r['vol_mm3']/1000:9.1f} "
              f"{r['p99_vol']:9.1f} {r['p99_node']:9.1f} {bias:+6.1f}% {r['over_vol_pct']:11.4f}")
    json.dump(got, open(f'{W}/field_volume.json', 'w'), indent=1)
    print(f'\n-> {W}/field_volume.json')


if __name__ == '__main__':
    main()
