"""Roll every solved link into one verdict table at SF>1 / >1.5 / >2.

The user's rule (2026-08-16): the measured P99 already carries impact content,
so there is no single safety target -- report each link against the three
criteria and let the design decision follow from that.

Writes ~/pyg_fea/work/verdicts.json and prints a markdown table for docs/77.
"""
import glob
import json
import os

YIELD = 276.0     # 6061-T6
LEVELS = (1.0, 1.5, 2.0)
W = '/home/syaro/pyg_fea/work'


def main():
    rows = []
    for f in sorted(glob.glob(f'{W}/*/envelope_P99.json')):
        d = json.load(open(f))
        link = d.get('link', os.path.basename(os.path.dirname(f)))
        raw, filt = d['max_vM'], d.get('max_vM_filtered', d['max_vM'])
        rows.append(dict(
            link=link, joint=d.get('joint'), comps=d.get('comps'),
            mesh_nodes=d.get('mesh_nodes'), magnitudes=d.get('magnitudes'),
            max_vM=raw, max_vM_filtered=filt,
            SF_raw=YIELD / raw, SF_filtered=YIELD / filt,
            argmax=d.get('argmax_xyz'), governing=d.get('governing_signs'),
            verdict={f'SF>{L}': ('PASS' if YIELD / filt >= L else 'FAIL') for L in LEVELS},
            verdict_raw={f'SF>{L}': ('PASS' if YIELD / raw >= L else 'FAIL') for L in LEVELS},
            allowable_MPa={f'SF>{L}': round(YIELD / L, 1) for L in LEVELS},
            moment_model=d.get('moment_model'),
        ))
    json.dump(rows, open(f'{W}/verdicts.json', 'w'), indent=1)

    print('| link | joint | max vM (bore/raw) | max vM (filtered) | SF raw | SF filt | '
          'SF>1 | SF>1.5 | SF>2 | worst-at |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        v = r['verdict']
        print(f"| {r['link']} | {r['joint']} | {r['max_vM']:.1f} | {r['max_vM_filtered']:.1f} | "
              f"{r['SF_raw']:.2f} | {r['SF_filtered']:.2f} | {v['SF>1.0']} | {v['SF>1.5']} | "
              f"{v['SF>2.0']} | {r['argmax']} |")
    print(f'\n6061-T6 allowable: {YIELD:.0f} (SF>1) / {YIELD/1.5:.0f} (SF>1.5) / '
          f'{YIELD/2:.0f} MPa (SF>2)')
    print(f'{len(rows)} links solved')


if __name__ == '__main__':
    main()
