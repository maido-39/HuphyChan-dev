"""Roll every solved link into one verdict table at SF>1 / >1.5 / >2.

The user's rule (2026-08-16): the measured P99 already carries impact content,
so there is no single safety target -- report each link against the three
criteria and let the design decision follow from that.

TWO BASES, and they disagree, so both are reported (2026-08-18):

  point  `max_vM_design` - worst node once load-injection and clamped neighbourhoods are
         excluded. At an unfilleted re-entrant corner this does NOT converge: refining the
         hot spot from h 3.97 to 1.50 mm drives the foot from 202 to 327 MPa, an exponent
         sigma ~ h^-0.49. A verdict read off that number is a verdict on the mesh.
  field  `p99_vM` - moves 4 % over the same refinement. This is what the allowable check
         uses; the singular points are carried separately as "needs a fillet".

convergence.py classifies which links are singular. A link that fails on the point basis
but passes on the field basis needs a FILLET, not a thicker section.

Writes ~/pyg_fea/work/verdicts.json and prints a markdown table for docs/77.
"""
import glob
import json
import os

YIELD = 276.0     # 6061-T6
LEVELS = (1.0, 1.5, 2.0)
W = '/home/syaro/pyg_fea/work'


# convergence.py's per-family classification, if it has been run. Members of a family
# classified `singular` have a mesh-dependent point maximum; members of a `converging`
# family do not, and their point value is a real local stress.
try:
    _CVG = json.load(open(f'{W}/convergence.json'))
except Exception:                                            # noqa: BLE001
    _CVG = {}
# volume-weighted field percentile, where field_volume.py has computed it. This is the
# mesh-independent field basis: on the pelvis pair the node percentile drifts +17.1 %
# under refinement while the volume-weighted one moves +1.9 %.
try:
    _VOL = {r['link']: r for r in json.load(open(f'{W}/field_volume.json'))}
except Exception:                                            # noqa: BLE001
    _VOL = {}
_FAMILY_OF = {}
for _fam, _links in {'foot toe-off': ('L1b_foot_toeoff', 'L1d_foot_toeoff_fine',
                                      'L1e_foot_toeoff_finer'),
                     'hip pitch/roll': ('L5_hip_pitchroll', 'L5d_hip_peakfine'),
                     'shin corner': ('L2_shin', 'L2b_shin_cornerfine')}.items():
    for _l in _links:
        _FAMILY_OF[_l] = _fam
# every twin make_refine_variant.py made, using the SAME family key convergence.py builds,
# so a new twin is classified without editing either file
try:
    _SPECS = json.load(open(f'{os.path.dirname(os.path.abspath(__file__))}/link_specs.json'))
except Exception:                                            # noqa: BLE001
    _SPECS = {}
for _n, _sp in _SPECS.items():
    _b = isinstance(_sp, dict) and _sp.get('_refines')
    if not _b:
        continue
    _key = _b.split('_')[0] + ' ' + _b.split('_', 1)[1].replace('_', ' ')
    _FAMILY_OF[_n] = _FAMILY_OF[_b] = _key
assert any(v == 'foot toe-off' for v in _FAMILY_OF.values()), 'hand-listed families lost'


def _hot_h(link):
    m = (_SPECS.get(link) or {}).get('mesh', {})
    return min((b[4] for b in m.get('refine', [])), default=m.get('size_far', 1e9))


# per family, the member with the smallest hot-spot element size governs; the coarser
# members of the same family are superseded and must not be read as separate verdicts
_FINEST = {}
for _l, _f in _FAMILY_OF.items():
    if _f not in _FINEST or _hot_h(_l) < _hot_h(_FINEST[_f]):
        _FINEST[_f] = _l


def main():
    rows = []
    for f in sorted(glob.glob(f'{W}/*/envelope_P99.json')):
        d = json.load(open(f))
        link = d.get('link', os.path.basename(os.path.dirname(f)))
        # the design number excludes the load-injection nodes AND the clamped nodes
        raw = d['max_vM']
        filt = d.get('max_vM_design', d.get('max_vM_filtered', d['max_vM']))
        oa = (d.get('over_allowable') or {}).get('SF>2.0', {})
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
            over_SF2_nodes=oa.get('nodes_design'), over_SF2_pct=oa.get('pct_design'),
            p99=d.get('p99_vM'),
            p99_vol=(_VOL.get(link) or {}).get('p99_vol'),
            over_vol_pct=(_VOL.get(link) or {}).get('over_vol_pct'),
            SF_field=(YIELD / d['p99_vM']) if d.get('p99_vM') else None,
            SF_field_vol=(YIELD / _VOL[link]['p99_vol']) if link in _VOL else None,
            over_SF1_pct=(d.get('over_allowable') or {}).get('SF>1.0', {}).get('pct_design'),
        ))
    json.dump(rows, open(f'{W}/verdicts.json', 'w'), indent=1)

    print('| link | point [MPa] | SF point | 필드 p99 (절점) | **필드 p99 (체적)** | '
          '**SF 필드** | 항복 절점 / **체적** | 판정 |')
    print('|---|---|---|---|---|---|---|---|')
    for r in rows:
        ext = ('—' if not r.get('over_SF1_pct') else f"{r['over_SF1_pct']:.3f} %")
        sff = r['SF_field']
        # a point failure with a passing field and a vanishing over-yield fraction is a
        # geometric singularity, not an overloaded section (convergence.py proves it per link)
        famk = _FAMILY_OF.get(r['link'], '')
        cvg = _CVG.get(famk, {})
        superseded = famk and _FINEST.get(famk) not in (None, r['link'])
        # yielded MATERIAL, not a percentile over nodes: p99 is mesh-density biased
        # (refining a hot spot adds nodes exactly where stress is high), the over-yield
        # fraction is not. Under 0.05 % means isolated nodes, i.e. a stress concentration
        # that yields locally and redistributes - not an overloaded section.
        ovp = r.get('over_SF1_pct') or 0.0
        tiny = (r.get('over_SF1_pct') or 0) < 1.0        # yield exceeded on <1 % of nodes
        if sff is None:
            note = '?'
        elif r['SF_filtered'] >= 2.0:
            note = 'PASS'
        elif cvg.get('singular'):
            note = '**필렛**'
        elif cvg.get('singular') is False:
            # the point value converged, so it is a real local stress - but if the yielded
            # material is a handful of nodes it yields locally and redistributes
            note = ('주의(수렴·실하중)' if r['SF_filtered'] >= 1.5
                    else f'국부항복 {ovp:.3f} %' if ovp < 0.05 else '**FAIL(수렴)**')
        elif sff >= 2.0 and tiny:
            note = '필렛?(미검증)'
        elif sff >= 2.0:
            note = '재검토'
        else:
            note = '**FAIL**'
        if superseded:
            note = f"~~{note.replace('*','')}~~ <span title=\"coarser mesh\">← {_FINEST[famk]}</span>"
        pv, sfv = r.get('p99_vol'), r.get('SF_field_vol')
        ovv = r.get('over_vol_pct')
        print(f"| {r['link']} | {r['max_vM_filtered']:.1f} | {r['SF_filtered']:.2f} | "
              f"{(r['p99'] or 0):.1f} | "
              f"{('**%.1f**' % pv) if pv else '—'} | "
              f"{('**%.2f**' % sfv) if sfv else ('%.2f' % (sff or 0))} | "
              f"{ext} / {('**%.4f %%**' % ovv) if ovv is not None else '—'} | {note} |")
    print(f'\n6061-T6 allowable: {YIELD:.0f} (SF>1) / {YIELD/1.5:.0f} (SF>1.5) / '
          f'{YIELD/2:.0f} MPa (SF>2)')
    print(f'{len(rows)} links solved')


if __name__ == '__main__':
    main()
