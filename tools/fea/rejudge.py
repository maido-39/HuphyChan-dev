"""Re-summarise solved links from their stored unit results - no re-solve.

Three of the links were summarised before the boundary-condition artefact filter
existed, so their verdict used the raw peak: L2's 311 MPa sat on the clamped knee
flange while the link body never passed 40 MPa. This rebuilds the envelope summary
of every solved link with the current filters, reading the unit .frd files that are
already on disk and the *BOUNDARY / load node sets from the unit decks.

Usage: rejudge.py [LINK ...]
"""
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import envelope as E  # noqa: E402
import femlib as F  # noqa: E402

W = '/home/syaro/pyg_fea/work'


def deck_node_sets(inp):
    """(fixed nodes, loaded nodes) of a unit deck."""
    fix, load, nsets, mode, cur = set(), set(), {}, None, None
    for ln in open(inp):
        t = ln.strip()
        if t.startswith('*'):
            u = t.upper()
            if u.startswith('*NSET'):
                mode = 'nset'
                m = re.search(r'NSET\s*=\s*([^,]+)', t, re.I)
                cur = m.group(1).strip() if m else None
                nsets.setdefault(cur, set())
            elif u.startswith('*BOUNDARY'):
                mode = 'bc'
            elif u.startswith('*CLOAD'):
                mode = 'cload'
            else:
                mode = None
            continue
        if not t or mode is None:
            continue
        head = t.split(',')[0].strip()
        if mode == 'nset':
            for tok in t.split(','):
                tok = tok.strip()
                if tok.isdigit():
                    nsets[cur].add(int(tok))
        elif mode == 'bc':
            (fix.add(int(head)) if head.isdigit() else fix.update(nsets.get(head, ())))
        elif mode == 'cload':
            (load.add(int(head)) if head.isdigit() else load.update(nsets.get(head, ())))
    return fix, load


def main():
    links = sys.argv[1:] or [os.path.basename(os.path.dirname(f))
                             for f in sorted(glob.glob(f'{W}/*/envelope_P99.json'))]
    for link in links:
        d = f'{W}/{link}'
        res = f'{d}/envelope_P99.json'
        env = json.load(open(res))
        comps = env.get('comps') or ['Fx', 'Fy', 'Fz']
        frds = [f'{d}/{link}_u{c}.frd' for c in comps]
        if not all(os.path.exists(x) for x in frds):
            print(f'{link}: unit results were pruned - cannot re-judge without a re-solve')
            continue
        US, ids, coords = [], None, None
        for f in frds:
            coords, blocks = F.parse_frd(f)
            S = [x for nm, x in blocks if nm == 'STRESS'][-1]
            ids = sorted(S)
            US.append(np.array([S[i] for i in ids]))
        comb = E.combine(US, [env['magnitudes'][c] for c in comps], comps=comps)
        fix, load = deck_node_sets(f'{d}/{link}_u{comps[0]}.inp')
        P = [coords[i] for i in ids]
        s = E.summarize(comb, P, ids, load_nids=sorted(load), fix_nids=sorted(fix))
        keep = {k: v for k, v in env.items() if k not in s}
        keep.update(s)
        keep['rejudged'] = True
        keep['fix_nodes_in_deck'] = len(fix)
        json.dump(keep, open(res, 'w'), indent=1)
        oa = s['over_allowable']['SF>2.0']
        print(f"{link:18s} raw {s['max_vM']:7.1f} -> design {s.get('max_vM_design', float('nan')):7.1f} MPa "
              f"(SF {s.get('SF_design', 0):5.2f})  over SF>2 allowable: "
              f"{oa['nodes_raw']} nodes raw / {oa['nodes_design']} design "
              f"({oa['pct_design']} % of the filtered surface)")


if __name__ == '__main__':
    main()
