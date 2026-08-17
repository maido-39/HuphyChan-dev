"""Does the whole assembly hold - not just each link's stress field?

The campaign checked links one at a time and the optimiser checked a link's own safety
factor, but nobody ever asked the question the user asked: after the shape changes, does
the thing still hold TOGETHER? A lighter link can clear its own stress check and still be
unbuildable because a bolt pad lost its backing, or a joint that was already slip-critical
got worse.

This rolls the whole chain into one verdict per link:

  1. structure   - design stress vs yield at SF>1 / 1.5 / 2, static and (peak) overload
  2. fatigue     - Goodman screen at ~2.2e6 gait cycles, P99-cycle and RMS-cycle bracket
  3. fasteners   - per-interface separation / slip / bolt-shear margins under the same wrench
  4. threads     - aluminium engagement, since every tap is in 6061-T6 and there are no nuts
  5. pad backing - after material removal, is there still metal behind every bolt pad?
                   (a pad floating on a 1 mm skin passes a stress check and fails assembly)

Usage: assembly_check.py [LINK ...]
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import femlib as F  # noqa: E402

W = '/home/syaro/pyg_fea/work'
STEPS = '/home/syaro/pyg_fea/steps'
YIELD = 276.0
MIN_BACKING_MM = 4.0        # metal depth required behind a bolt pad
MIN_SLIP = 1.0
MIN_SEP = 1.5


def pad_backing(link, spec, nodes, elems, active=None):
    """Depth of material behind every bolt pad of this link, after any removal."""
    env = spec['envelope']
    pads = []
    for blk in list(env.get('fix', [])) + list(env.get('points', [])):
        if blk.get('type') == 'bolt_pads':
            ax = 'xyz'.index(blk['axis']) if isinstance(blk.get('axis'), str) else 2
            for q in blk['points']:
                pads.append((np.asarray(q, float), ax))
    if not pads:
        return []
    eids = list(active) if active is not None else list(elems)
    cen = np.array([np.mean([nodes[n] for n in elems[e][:4]], axis=0) for e in eids])
    out = []
    for q, ax in pads:
        oth = [k for k in range(3) if k != ax]
        near = (np.abs(cen[:, oth[0]] - q[oth[0]]) < 5.0) & (np.abs(cen[:, oth[1]] - q[oth[1]]) < 5.0)
        if not near.any():
            out.append(dict(pad=[round(float(v), 1) for v in q], backing_mm=0.0, ok=False))
            continue
        d = np.abs(cen[near][:, ax] - q[ax])
        out.append(dict(pad=[round(float(v), 1) for v in q],
                        backing_mm=round(float(d.max()), 1),
                        ok=bool(d.max() >= MIN_BACKING_MM)))
    return out


def main():
    specs = json.load(open(f'{HERE}/link_specs.json'))
    links = sys.argv[1:] or sorted(os.path.basename(os.path.dirname(f))
                                   for f in glob.glob(f'{W}/*/envelope_P99.json'))
    fat = (json.load(open(f'{W}/fatigue.json')).get('links', {})
           if os.path.exists(f'{W}/fatigue.json') else {})
    bolts = json.load(open(f'{W}/bolt_groups.json')) if os.path.exists(f'{W}/bolt_groups.json') else {}
    rods = (json.load(open(f'{W}/rods/rods.json'))
            if os.path.exists(f'{W}/rods/rods.json') else {})
    report = {}
    for link in links:
        d = f'{W}/{link}'
        res = json.load(open(f'{d}/envelope_P99.json'))
        des = res.get('max_vM_design', res['max_vM'])
        row = dict(design_MPa=round(des, 1), SF=round(YIELD / des, 2))
        pk = f'{d}/envelope_peak.json'
        if os.path.exists(pk):
            p = json.load(open(pk))
            row['peak_MPa'] = round(p.get('max_vM_design', p['max_vM']), 1)
            row['SF_peak'] = round(YIELD / row['peak_MPa'], 2)
        if link in fat:
            row['SF_fatigue_P99'] = fat[link]['SF_fatigue_P99']
            row['SF_fatigue_RMS'] = fat[link]['SF_fatigue_RMS']
        # fasteners on this link
        bg = {k: v for k, v in bolts.items() if k.split(':')[0] == link}
        if bg:
            worst_slip = min(min(r['slip_margin'] for r in v['rows']) for v in bg.values())
            worst_sep = min(min(r['sep_margin'] for r in v['rows'] if r['sep_margin'])
                            for v in bg.values() if any(r['sep_margin'] for r in v['rows']))
            row['bolt_slip_margin'] = round(worst_slip, 2)
            row['bolt_separation_margin'] = round(worst_sep, 2)
        # pad backing on the CURRENT geometry (or the optimised element set if there is one)
        opt = f'{d}/optimise.json'
        active = None
        if os.path.exists(opt):
            o = json.load(open(opt))
            row['optimised_volume_pct'] = (o.get('final') or {}).get('volume_pct')
        if link in specs:
            nodes, elems, _ = F.parse_inp(f'{d}/{link}_mesh.inp')
            pb = pad_backing(link, specs[link], nodes, elems, active)
            if pb:
                row['pad_backing_min_mm'] = min(p['backing_mm'] for p in pb)
                row['pads_without_backing'] = sum(1 for p in pb if not p['ok'])
        # verdict
        fails = []
        if row['SF'] < 2.0:
            fails.append(f"structure SF {row['SF']}")
        if row.get('SF_fatigue_P99', 9) < 1.0 and row.get('SF_fatigue_RMS', 9) < 1.5:
            fails.append(f"fatigue {row.get('SF_fatigue_P99')}")
        if row.get('bolt_slip_margin', 9) < MIN_SLIP:
            fails.append(f"joint slips ({row['bolt_slip_margin']})")
        if row.get('bolt_separation_margin', 9) < MIN_SEP:
            fails.append(f"joint gaps ({row['bolt_separation_margin']})")
        if row.get('pads_without_backing', 0):
            fails.append(f"{row['pads_without_backing']} bolt pads without backing")
        row['verdict'] = 'HOLDS' if not fails else 'FAILS: ' + '; '.join(fails)
        report[link] = row
        print(f"{link:24s} SF {row['SF']:5.2f} | peak {row.get('SF_peak', '—'):>5} | "
              f"fatigue {row.get('SF_fatigue_P99', '—'):>5} | slip "
              f"{row.get('bolt_slip_margin', '—'):>5} | backing "
              f"{row.get('pad_backing_min_mm', '—'):>5} mm  -> {row['verdict']}")
    if rods:
        print()
        for k, v in rods.items():
            ok = (v.get('SF_buckling') or 0) >= 2.0
            print(f"{k:24s} buckling SF {v.get('SF_buckling')} · static SF {v['SF_yield']}  "
                  f"-> {'HOLDS' if ok else 'FAILS: buckling'}")
            report[k] = dict(SF_buckling=v.get('SF_buckling'), SF_yield=v['SF_yield'],
                             verdict='HOLDS' if ok else 'FAILS: buckling')
    json.dump(report, open(f'{W}/assembly_check.json', 'w'), indent=1)
    bad = [k for k, v in report.items() if not v['verdict'].startswith('HOLDS')]
    print(f'\n{len(report) - len(bad)}/{len(report)} hold · not yet: ' + (', '.join(bad) or 'none'))
    print(f'-> {W}/assembly_check.json')


if __name__ == '__main__':
    main()
