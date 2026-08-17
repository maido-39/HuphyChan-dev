"""Which sub-SF-1 numbers are real and which are mesh singularities.

The campaign reports two stresses per link: a point maximum (`max_vM_design`, the worst
node once the load-injection and clamped neighbourhoods are excluded) and a field p99
(`p99_vM`). Where a link has been re-meshed at several densities the two behave completely
differently:

    L1b -> L1d -> L1e   point 202.2 -> 249.6 -> 327.0   field 95.9 -> 96.0 -> 100.0
    L5  -> L5d          point 348.0 -> 444.3            field 106.1 -> 103.1

A point maximum that grows without bound as h -> 0 is the signature of a geometric stress
singularity - a re-entrant corner with no fillet. There is no converged value to compare
against an allowable, so a verdict read off that number is a verdict on the mesh. The field
p99 converges (worst spread 4.3 % here) and is what the allowable check has to use, with
the singular locations carried separately as "needs a fillet", not "needs more material".

This classifies every link that has refinement variants and writes the figure that goes
with the verdict table.

Usage: convergence.py [--out docs/img]
"""
import glob
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

W = '/home/syaro/pyg_fea/work'
ALLOW = 276.0
# Refinement families: the same physical case re-meshed. Hand-listed ones first (these
# predate the `_refines` convention), then every twin make_refine_variant.py produced,
# discovered from the `_refines` key so a new twin needs no edit here.
FAMILIES = {
    'foot toe-off': ['L1b_foot_toeoff', 'L1d_foot_toeoff_fine', 'L1e_foot_toeoff_finer'],
    'hip pitch/roll': ['L5_hip_pitchroll', 'L5d_hip_peakfine'],
    'shin corner': ['L2_shin', 'L2b_shin_cornerfine'],
}


def discover_families(specs):
    """base -> [base, twin] for every twin tagged with `_refines`."""
    found = {}
    for name, spec in specs.items():
        base = isinstance(spec, dict) and spec.get('_refines')
        if not base:
            continue
        assert base in specs, f'{name}: _refines points at {base!r}, which is not a spec'
        found.setdefault(base.split('_')[0] + ' ' + base.split('_', 1)[1].replace('_', ' '),
                         [base]).append(name)
    return found


SPECS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'link_specs.json')))


def load(link, tier='P99'):
    f = f'{W}/{link}/envelope_{tier}.json'
    if not os.path.exists(f):
        return None
    d = json.load(open(f))
    # The refinement axis is the LOCAL element size at the refined hot spot, not the node
    # count: these variants refine different regions, so a variant can have more nodes
    # overall and a coarser hot spot (L1d has 340k nodes at h 2.6, L1e 296k at h 1.5).
    r = SPECS.get(link, {}).get('mesh', {}).get('refine', [])
    h = min((b[4] for b in r), default=SPECS.get(link, {}).get('mesh', {}).get('size_far'))
    oa = (d.get('over_allowable') or {}).get('SF>1.0', {})
    return dict(link=link, nodes=d.get('mesh_nodes', 0), h=h, point=d.get('max_vM_design'),
                field=d.get('p99_vM'), rev=d.get('analysis_rev'),
                over_n=oa.get('nodes_design') or 0, over_pct=oa.get('pct_design') or 0.0)


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    families = dict(FAMILIES)
    for k, v in discover_families(SPECS).items():
        if k not in families:
            families[k] = v
    fam = {k: [r for r in (load(l) for l in v) if r] for k, v in families.items()}
    skipped = {k: [l for l in families[k] if not load(l)] for k in families}
    fam = {k: v for k, v in fam.items() if len(v) >= 2}
    for k, miss in skipped.items():
        if miss and k not in fam:
            print(f'{k:22s} not yet classifiable - still unsolved: {", ".join(miss)}')

    print(f"{'family':16s} {'link':26s} {'h[mm]':>6s} {'nodes':>8s} {'point':>8s} "
          f"{'field p99':>10s}")
    verdict = {}
    for name, rows in fam.items():
        rows.sort(key=lambda r: -r['h'])            # coarse -> fine
        for r in rows:
            print(f"{name:16s} {r['link']:26s} {r['h']:6.2f} {r['nodes']:8d} "
                  f"{r['point']:8.1f} {r['field']:10.1f}")
        p = np.array([r['point'] for r in rows])
        f = np.array([r['field'] for r in rows])
        h = np.array([r['h'] for r in rows])
        dp = 100 * (p[-1] - p[0]) / p[0]
        df = 100 * (f[-1] - f[0]) / f[0]
        # a geometric singularity has sigma ~ h^-lambda with lambda > 0; a converged
        # solution has lambda -> 0. Fit on the two ends (log-log slope).
        lam = float(-np.log(p[-1] / p[0]) / np.log(h[-1] / h[0]))
        # How much MATERIAL is actually over yield. This is the discriminator the field p99
        # cannot give: p99 is a percentile over NODES, so refining a hot spot adds nodes
        # exactly where the stress is high and inflates it (L6f +17 % on a +2.9 % node
        # count). The over-yield fraction has no such bias - at a true singularity it stays
        # vanishing however fine the mesh gets, because the yielded volume tends to zero.
        ov = np.array([r['over_pct'] for r in rows])
        ovn = np.array([r['over_n'] for r in rows])
        verdict[name] = dict(point_drift=float(dp), field_drift=float(df),
                             h_coarse=float(h[0]), h_fine=float(h[-1]), lam=lam,
                             over_pct=float(ov[-1]), over_n=int(ovn[-1]),
                             # singular = the point runs away while the yielded material
                             # stays a vanishing fraction. The field drift is NOT used as a
                             # gate any more: it is mesh-density biased (see above).
                             singular=bool(lam > 0.2 and ov[-1] < 0.05),
                             field=float(f[-1]), sf=float(ALLOW / f[-1]))
        tag = ('SINGULAR - point runs away, yielded material vanishing'
               if verdict[name]['singular'] else 'converging' if lam < 0.2
               else 'DIVERGENT + real yielded volume - not just a singularity')
        print(f"{'':16s} -> h {h[0]:.2f} -> {h[-1]:.2f} mm: point {dp:+.0f} %, "
              f"field {df:+.0f} %, lambda {lam:+.2f}, over-yield {ovn[-1]} nodes "
              f"({ov[-1]:.4f} %): {tag}")
        print(f"{'':16s}    field verdict SF {verdict[name]['sf']:.2f} "
              f"(allowable {ALLOW:.0f} MPa)\n")

    # the figure: point vs field against mesh density, normalised to the coarsest mesh
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, axes = plt.subplots(1, len(fam) + 1, figsize=(3.6 * (len(fam) + 1), 4.0))
    for ax, (name, rows) in zip(axes, fam.items()):
        n = np.array([r['h'] for r in rows])
        o = np.argsort(-n)                          # coarse (left) -> fine (right)
        n = n[o]
        p = np.array([rows[i]['point'] for i in o])
        f = np.array([rows[i]['field'] for i in o])
        ax.plot(n, p, 'o-', color='#c0392b', lw=2, ms=7, label='point max (design)')
        ax.plot(n, f, 's-', color='#2e86c1', lw=2, ms=7, label='field p99')
        ax.axhline(ALLOW, color='k', ls='--', lw=1.0)
        ax.text(n.min(), ALLOW * 1.02, f'allowable {ALLOW:.0f}', fontsize=7.5)
        for x, y in zip(n, p):
            ax.annotate(f'{y:.0f}', (x, y), textcoords='offset points', xytext=(0, 7),
                        fontsize=7.5, ha='center', color='#c0392b')
        for x, y in zip(n, f):
            ax.annotate(f'{y:.0f}', (x, y), textcoords='offset points', xytext=(0, -13),
                        fontsize=7.5, ha='center', color='#2e86c1')
        v = verdict[name]
        ax.set_title(f'{name}\npoint {v["point_drift"]:+.0f} % · field {v["field_drift"]:+.0f} % '
                     f'· $\\lambda$ {v["lam"]:+.2f}', fontsize=9.5)
        ax.set_xlabel('local element size at the hot spot [mm]')
        ax.invert_xaxis()
        ax.set_ylim(0, max(p.max(), ALLOW) * 1.25)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel('von Mises [MPa]')
    axes[0].legend(fontsize=7.5, loc='center left')

    # last panel: the field verdict for every link in the campaign
    rows = []
    for f in sorted(glob.glob(f'{W}/*/envelope_P99.json')):
        link = os.path.basename(os.path.dirname(f))
        d = json.load(open(f))
        if d.get('p99_vM'):
            rows.append((link, ALLOW / d['p99_vM'], d['max_vM_design']))
    rows.sort(key=lambda r: r[1])
    ax = axes[-1]
    y = np.arange(len(rows))
    cols = ['#c0392b' if r[1] < 2 else '#e67e22' if r[1] < 3 else '#27ae60' for r in rows]
    ax.barh(y, [r[1] for r in rows], color=cols)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0].replace('_', ' ')[:22] for r in rows], fontsize=6.5)
    ax.axvline(2.0, color='k', ls='--', lw=1.0)
    ax.set_xlabel('SF on the field p99')
    ax.set_title(f'every link, field basis\nworst {rows[0][0][:18]} SF {rows[0][1]:.2f}',
                 fontsize=9.5)
    ax.set_xscale('log')
    ax.grid(alpha=0.3, axis='x')
    fig.suptitle('Refining the hot spot (left to right) drives the point maximum up as '
                 '$\\sigma \\sim h^{-\\lambda}$ while the field p99 holds - the sub-SF-1 '
                 'numbers are unfilleted corners, not undersized sections', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'fea_mesh_convergence.png'))
    print(f'-> docs/img/fea_mesh_convergence.png')
    json.dump(verdict, open(f'{W}/convergence.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
