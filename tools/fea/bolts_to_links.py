"""Attach detected bolts (detect_bolts.py) to each link's joint metadata.

A bolt belongs to every link whose solid supplies one of its holes, so a
cross-link bolt (link <-> actuator flange) shows up on both sides -- that is
exactly the joint we later model with pretension + contact.

Run: bolts_to_links.py            (uses ~/pyg_fea/steps/bolts_all.json)
"""
import json
import os
from collections import Counter, defaultdict

STEPS = '/home/syaro/pyg_fea/steps'


def main():
    bolts = json.load(open(f'{STEPS}/bolts_all.json'))
    per = defaultdict(list)
    for b in bolts:
        srcs = set(b.get('links') or [])
        for p in b.get('parts', {}).values():
            if p:
                srcs.add(p.split('#')[0])
        for s in srcs:
            per[s].append(b)

    for link, bs in sorted(per.items()):
        jf = f'{STEPS}/link_{link}_joints.json'
        data = json.load(open(jf)) if os.path.exists(jf) else dict(link=link, screws=[], bearings=[])
        data['detected_bolts'] = bs
        data['_bolt_method'] = (
            'holes classified by the design rule: clearance = nominal + 0.15 mm '
            '(M4 4.15 / M5 5.15), tapped = tap-drill dia (M4 3.3 / M5 4.2) coaxial '
            'and offset along the same axis; head recess depth separates ISO 4762 '
            'socket heads from low-head (소두) screws. tools/fea/detect_bolts.py')
        json.dump(data, open(jf, 'w'), indent=1)
        c = Counter((b['size'], 'paired' if b['tap_d'] else 'clearance-only') for b in bs)
        lh = sum('소두' in b['head_type'] for b in bs)
        print(f'{link:28s} {len(bs):3d} bolts  ' +
              ' '.join(f'{k[0]}/{k[1]}×{v}' for k, v in sorted(c.items())) +
              (f'   LOW-HEAD ×{lh}' if lh else ''))
    print(f'\n{len(bolts)} bolts distributed over {len(per)} links/actuators')


if __name__ == '__main__':
    main()
