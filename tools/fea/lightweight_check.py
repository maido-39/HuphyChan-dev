"""Does the retained material actually form a structure?

The lightweighting screen kept every element whose envelope stress was below
yield/(SF*1.6) and outside a keep-out. That is a LOW-STRESS MAP, not a design: it never
asked whether what remains is connected, or whether a load path still runs from the
loaded interface to the constrained one. This measures exactly that:

  * connected components of the retained element set (face-adjacency)
  * whether ANY single component contains both the fixed nodes and the loaded nodes
  * how much of the removable set is actually load-path material sitting at low stress
    only because the structure around it is stiff

Usage: lightweight_check.py [LINK ...]
"""
import glob
import json
import os
import sys
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import envelope as E  # noqa: E402
import femlib as F  # noqa: E402

W = '/home/syaro/pyg_fea/work'
YIELD = 276.0
KEEP_MARGIN = 1.6
LEVEL = 1.5


def retained_mask(link, nodes, elems, vm_node, ids, spec):
    """Same criterion lightweight.py uses, on element centroids."""
    idx = {n: k for k, n in enumerate(ids)}
    allow = YIELD / LEVEL
    zones = []
    env = spec['envelope']
    for blk in list(env.get('fix', [])) + list(env.get('points', [])):
        if blk.get('type') == 'bolt_pads':
            for q in blk['points']:
                zones.append((np.asarray(q, float), 9.0))
        elif blk.get('ctr'):
            zones.append((np.asarray(blk['ctr'], float), float(blk.get('r', 10)) + 12.0))
    jf = f"/home/syaro/pyg_fea/steps/link_{spec.get('geometry_of', link)}_joints.json"
    if os.path.exists(jf):
        J = json.load(open(jf))
        for b in J.get('detected_bolts', []):
            zones.append((np.asarray(b['head_point'], float), 9.0))
        for b in J.get('bearings', []):
            for s in b.get('seats', []):
                zones.append((np.asarray(s['loc'], float), (s.get('r') or 20) + 10.0))
    eids = list(elems)
    cen = np.array([np.mean([nodes[n] for n in elems[e][:4]], axis=0) for e in eids])
    stress = np.array([np.mean([vm_node[idx[n]] for n in elems[e][:4] if n in idx] or [0.0])
                       for e in eids])
    keep = np.zeros(len(eids), bool)
    for c, r in zones:
        keep |= np.linalg.norm(cen - c, axis=1) < r
    retained = (stress >= allow / KEEP_MARGIN) | keep
    vol = np.array([abs(np.dot(np.cross(*(np.array([nodes[n] for n in elems[e][:4]])[1:]
                                          - np.array(nodes[elems[e][0]]))[:2]),
                               np.array(nodes[elems[e][3]]) - np.array(nodes[elems[e][0]]))) / 6.0
                    for e in eids])
    return eids, retained, vol, stress


def components(eids, elems, mask):
    """Connected components of the retained elements, by shared face (3 shared nodes)."""
    sel = [e for e, m in zip(eids, mask) if m]
    face = {}
    for e in sel:
        c = elems[e][:4]
        for k in range(4):
            f = tuple(sorted(c[:k] + c[k + 1:]))
            face.setdefault(f, []).append(e)
    adj = {e: set() for e in sel}
    for f, es in face.items():
        for a in es:
            for b in es:
                if a != b:
                    adj[a].add(b)
    seen, comps = set(), []
    for e in sel:
        if e in seen:
            continue
        q, cur = deque([e]), []
        seen.add(e)
        while q:
            x = q.popleft()
            cur.append(x)
            for y in adj[x]:
                if y not in seen:
                    seen.add(y)
                    q.append(y)
        comps.append(cur)
    comps.sort(key=len, reverse=True)
    return comps


def main():
    specs = json.load(open(f'{HERE}/link_specs.json'))
    links = sys.argv[1:] or sorted(os.path.basename(os.path.dirname(f))
                                   for f in glob.glob(f'{W}/*/envelope_P99.json'))
    out = {}
    for link in links:
        d = f'{W}/{link}'
        if not os.path.exists(f'{d}/fields.json') or link not in specs:
            continue
        env = json.load(open(f'{d}/envelope_P99.json'))
        nodes, elems, _ = F.parse_inp(f'{d}/{link}_mesh.inp')
        fd = json.load(open(f'{d}/fields.json'))
        tris = [t for (_, _, t) in F.boundary_faces(elems).values()]
        ids = sorted({t for tri in tris for t in tri})
        vm = np.array(fd['fields']['vM_env'])
        eids, ret, vol, stress = retained_mask(link, nodes, elems, vm, ids, specs[link])
        comps = components(eids, elems, ret)
        # which components touch the fixed nodes and which touch the loaded nodes?
        import re as _re
        fix, load = set(), set()
        deck = sorted(glob.glob(f'{d}/{link}_u*.inp'))
        if deck:
            from rejudge import deck_node_sets
            fix, load = deck_node_sets(deck[0])
        big = comps[0] if comps else []
        def touches(comp, nds):
            s = {n for e in comp for n in elems[e]}
            return len(s & nds)
        joined = None
        for k, c in enumerate(comps[:12]):
            if touches(c, fix) and touches(c, load):
                joined = k
                break
        tot = vol.sum()
        out[link] = dict(
            elements=len(eids), retained=int(ret.sum()),
            retained_vol_pct=round(100 * vol[ret].sum() / tot, 1),
            components=len(comps),
            largest_component_elems=len(big),
            largest_component_pct_of_retained=round(100 * len(big) / max(1, int(ret.sum())), 1),
            component_that_joins_fix_and_load=joined,
            fix_nodes=len(fix), load_nodes=len(load))
        print(f'{link:24s} retained {ret.sum():6d}/{len(eids):6d} elems '
              f'({out[link]["retained_vol_pct"]:5.1f} % vol) · {len(comps):5d} disconnected '
              f'pieces · largest holds {out[link]["largest_component_pct_of_retained"]:5.1f} % '
              f'· fix↔load path: '
              f'{"component #%d" % joined if joined is not None else "NONE"}', flush=True)
    json.dump(out, open(f'{W}/lightweight_connectivity.json', 'w'), indent=1)
    print(f'\n-> {W}/lightweight_connectivity.json')


if __name__ == '__main__':
    main()
