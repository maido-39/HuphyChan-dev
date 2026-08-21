"""Which parts must be machined FIRST if the robot only walks slowly on the flat.

Not every part can be CNC-milled before the first tests, so some will be printed in PLA
for a while. The campaign already answered "can PLA carry the design loads" (no part can,
docs/79), but the design loads include 2.5 m/s running and pushes. For a first-walk
prototype the honest question is narrower: under SIMPLE WALKING loads, which parts break a
PLA print at once, which survive for some hours, and which are genuinely fine. That ranks
the machining queue.

Method - the campaign's own unit solutions, re-combined with the walking basis:

  loads        tools/fea/loads_walk.json (walk_basis.py): the flat anchor restricted to the
               simple-walking command box, same link-local frame and P99 statistics as the
               design basis, x1.25 design factor kept
  stress       the retained unit .frd per link, superposed over all sign combinations
               exactly as the campaign did (envelope.combine). Before the walking field is
               reported, the recorded magnitudes must reproduce the recorded peak within
               2 % - that proves the unit fields and component order are the campaign's.
  per part     volume-weighted p99 per CAD solid (ELSET), the campaign's mesh-independent
               design measure, for BOTH bases side by side
  PLA bands    static in-plane 25.5 / static interlayer 11.3 / fatigue in-plane 3.4 (SF1.5)
               / fatigue interlayer 1.13 MPa - the docs/79 ladder - plus the two things a
               stress number cannot see: a part bolted to a motor housing (PLA HDT 55 C,
               RobStride rates its motors on an aluminium heat sink) and a part that IS a
               bearing seat (creep and wear)
  life         Ezeh & Susmel PLA S-N, endurance 10 % UTS at 2e6 cycles, inverse slope 5.5:
               N = 2e6 (5.1/sigma)^5.5 in-plane, converted with the project's 2.2e4
               cycles per walking hour (docs/79 s8a)

Bands:  RED    > 11.3 MPa or motor-bolted  - print fails statically (or thermally); mill first
        ORANGE 3.4..11.3                   - survives, but a fatigue life measured in hours
        GREEN  <= 3.4 and no flag          - PLA is defensible for simple walking

Usage: walk_triage.py [--tier=T2_walk] [LINK ...]
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import envelope as EV                                    # noqa: E402
import femlib as FL                                      # noqa: E402
from part_screen import read_mesh_sets, weighted_pct, label_of, GOVERNING  # noqa: E402

W = '/home/syaro/pyg_fea/work'
CAD = '/home/syaro/pyg_fea/steps'
DOCS_IMG = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img'
FACTOR = 1.25
GROUP = {'L1gf_foot_corner_fine': 'L1_ankle_foot', 'L2_shin': 'L2_shin', 'L3_thigh': 'L3_thigh',
         'L4_hip_yaw': 'L4_hip_yaw', 'L5_hip_pitchroll': 'L5_hip_pitchroll',
         'L6_pelvis': 'L6_pelvis'}
SHORT = {'L1gf_foot_corner_fine': 'L1 foot', 'L2_shin': 'L2 shin', 'L3_thigh': 'L3 thigh',
         'L4_hip_yaw': 'L4 hip yaw', 'L5_hip_pitchroll': 'L5 hip', 'L6_pelvis': 'L6 pelvis'}
# PLA ladder (docs/79 s8a / pla_verdict.py)
PLA_UTS_XY, PLA_INTERLAYER, SF_PLA, FAT = 51.0, 17.0, 1.5, 0.10
A_STAT_XY, A_STAT_Z = PLA_UTS_XY / 2, PLA_INTERLAYER / SF_PLA           # 25.5 / 11.3
A_FAT_XY, A_FAT_Z = PLA_UTS_XY * FAT / SF_PLA, PLA_INTERLAYER * FAT / SF_PLA  # 3.4 / 1.13
SN_ENDUR_XY, SN_K, SN_N, CYC_PER_H = PLA_UTS_XY * FAT, 5.5, 2e6, 2.2e4
AL_ALLOW = 138.0
MOTOR_CONTACT_MM, MOTOR_ZONE_MM = 1.5, 30.0
# physical names inferred from each solid's position in the CAD (cm3 rounded to 0.1)
NAMES = {
    ('L1_ankle_foot', 197.6): 'sole plate', ('L1_ankle_foot', 35.4): 'heel block',
    ('L1_ankle_foot', 14.6): 'sole rib', ('L1_ankle_foot', 24.8): 'ankle cross',
    ('L2_shin', 65.4): 'knee yoke arm (outer)', ('L2_shin', 48.3): 'knee yoke arm (inner)',
    ('L2_shin', 47.6): 'shin side plate (outer)', ('L2_shin', 44.6): 'shin side plate (inner)',
    ('L2_shin', 16.5): 'fore/aft brace', ('L2_shin', 15.1): 'ankle-motor rail',
    ('L2_shin', 12.0): 'ankle-motor mount block', ('L2_shin', 11.9): 'ankle-motor mount block',
    ('L2_shin', 11.8): 'ankle-motor mount block',
    ('L3_thigh', 119.2): 'thigh side plate (inner)', ('L3_thigh', 109.9): 'thigh side plate (outer)',
    ('L3_thigh', 117.6): 'hip-yaw bearing housing', ('L3_thigh', 70.2): 'hip-yaw top plate',
    ('L3_thigh', 39.4): 'front brace', ('L3_thigh', 32.2): 'rear brace',
    ('L4_hip_yaw', 72.2): 'front plate', ('L4_hip_yaw', 61.0): 'lower bearing flange',
    ('L4_hip_yaw', 60.9): 'rear plate', ('L4_hip_yaw', 14.5): 'outer rib',
    ('L5_hip_pitchroll', 86.1): 'hip-pitch motor flange', ('L5_hip_pitchroll', 62.5): 'rear arm',
    ('L5_hip_pitchroll', 53.8): 'front arm', ('L5_hip_pitchroll', 39.8): 'upper bridge',
    ('L6_pelvis', 72.5): 'pelvis side plate', ('L6_pelvis', 72.3): 'pelvis side plate',
    ('L6_pelvis', 71.3): 'pelvis top plate', ('L6_pelvis', 37.1): 'front/rear plate',
    ('L6_pelvis', 23.7): '2020 profile',
}


def walk_mags(env, LW, tier):
    """The walking magnitudes, component by component, never above the campaign's."""
    T = LW[tier][env['joint']]
    cam = env['magnitudes']
    out = {}
    for c in env['comps']:
        if c in ('Fx', 'Fy', 'Fz'):
            out[c] = round(T[c] * FACTOR, 1)
        elif c == 'Maxial':
            out[c] = round(min(T['tau'] * FACTOR, cam['Maxial']), 1)
        elif c in ('Mt1', 'Mt2'):
            out[c] = round(min(max(T['Mt1'], T['Mt2']) * FACTOR, cam[c]), 1)
        elif c == 'Gbody':
            out[c] = cam['Gbody']
        else:
            raise KeyError(c)
    return out


def unit_fields(link, comps):
    U, ids = [], None
    for c in comps:
        f = f'{W}/{link}/{link}_u{c}.frd'
        assert os.path.exists(f), f'{link}: unit case {c} is gone ({f})'
        _, blocks = FL.parse_frd(f)
        st = next((v for k, v in blocks if 'STRESS' in k.upper()), None)
        assert st, f'{link}: {c} has no STRESS block'
        if ids is None:
            ids = sorted(st)
        U.append(np.array([st[i] for i in ids], float))
        print(f'   parsed u{c} ({len(ids)} nodes)', flush=True)
    return np.asarray(U), ids


def cyl_distance(P, p):
    """Distance from points P to the surface of the actuator proxy cylinder p [mm]."""
    c = np.asarray(p['ctr'], float)
    u = {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}[p['axis']]
    u = np.asarray(u, float)
    d = P - c
    a = d @ u
    rad = np.linalg.norm(d - a[:, None] * u, axis=1)
    dr = np.maximum(rad - p['r'], 0.0)
    da = np.maximum(np.abs(a) - p['len'] / 2, 0.0)
    return np.hypot(dr, da)


def life_hours(sigma):
    if sigma <= 0:
        return float('inf')
    return SN_N * (SN_ENDUR_XY / sigma) ** SN_K / CYC_PER_H


def band(sigma):
    """Stress band alone; the thermal flag is reported next to it, not folded into it,
    because under light walking duty a motor housing may not reach the PLA HDT."""
    if sigma > A_STAT_Z:
        return 'RED'
    if sigma > A_FAT_XY:
        return 'ORANGE'
    return 'GREEN'


SLIVER_CM3 = 0.5      # mesher splinters (0.0-0.1 cm3 faces of a brace) are not parts
KO2EN = {'하단': 'low', '중단': 'mid', '상단': 'up', '앞': 'front', '중앙': 'ctr', '뒤': 'rear',
         '좌': 'L', '중': 'C', '우': 'R'}


def en(label):
    return '·'.join(KO2EN.get(t, t) for t in (label or '').split('·'))


def finish(rows, tier, links_done):
    """Ranking, counts and figure from the row list - also used by --replot."""
    for r in rows:
        r['cad_name'] = r.get('cad_name') or NAMES.get((GROUP[r['link']], round(r['cad_vol_cm3'] or 0, 1)), '')
        r['stress_band'] = band(r['p99_walk'])
        r['thermal'] = ('bolted' if r['motor_mm'] <= MOTOR_CONTACT_MM
                        else 'zone' if r['motor_mm'] <= MOTOR_ZONE_MM else '')
        r['band'] = r['stress_band']
        r['sliver'] = r['vol_cm3'] < SLIVER_CM3
    real = [r for r in rows if not r['sliver']]
    real.sort(key=lambda r: -r['p99_walk'])
    print(f"\n{'band':6s} {'therm':6s} {'link':10s} {'part':8s} {'name':26s} {'cm3':>6s} "
          f"{'campaign':>9s} {'walk':>7s} {'ratio':>6s} {'life h':>8s} seat")
    for r in real:
        lh = f"{r['life_h']:8.1f}" if r['life_h'] < 1e5 else f"{'>1e5':>8s}"
        print(f"{r['band']:6s} {r['thermal']:6s} {r['short']:10s} {r['part']:8s} "
              f"{(r['cad_name'] or en(r['label']))[:26]:26s} {r['vol_cm3']:6.1f} "
              f"{r['p99_campaign']:9.1f} {r['p99_walk']:7.1f} "
              f"{r['p99_walk']/max(r['p99_campaign'],1e-9):6.2f} {lh} {','.join(r['bearing_seat'][:1])}")
    nb = {b: sum(1 for r in real if r['band'] == b) for b in ('RED', 'ORANGE', 'GREEN')}
    vb = {b: sum(r['vol_cm3'] for r in real if r['band'] == b) for b in nb}
    ns = sum(1 for r in rows if r['sliver'])
    print(f"\nRED {nb['RED']} parts / {vb['RED']:.0f} cm3 · ORANGE {nb['ORANGE']} / "
          f"{vb['ORANGE']:.0f} · GREEN {nb['GREEN']} / {vb['GREEN']:.0f}   "
          f"({ns} mesh slivers < {SLIVER_CM3} cm3 excluded)")

    plt.rcParams.update({'figure.dpi': 140, 'font.size': 8.5})
    big = [r for r in real if r['vol_cm3'] >= 3.0]
    fig, ax = plt.subplots(1, 2, figsize=(15.5, max(6.5, 0.27 * len(big) + 1.5)),
                           gridspec_kw={'width_ratios': [2.2, 1]})
    col = {'RED': '#c0392b', 'ORANGE': '#e67e22', 'GREEN': '#27ae60'}
    y = np.arange(len(big))
    a = ax[0]
    a.barh(y, [r['p99_walk'] for r in big], 0.66, color=[col[r['band']] for r in big],
           label='simple walking (bar)')
    a.scatter([r['p99_campaign'] for r in big], y, marker='|', s=160, color='#111',
              zorder=3, label='campaign design basis (tick)')
    for i, r in enumerate(big):
        if r['thermal'] == 'bolted':
            a.annotate('motor-bolted', (r['p99_walk'] * 1.08, i), fontsize=6, va='center',
                       color='#7d3c98')
    for v, lab in ((A_FAT_Z, 'PLA fatigue Z 1.1'), (A_FAT_XY, 'PLA fatigue XY 3.4'),
                   (A_STAT_Z, 'PLA static Z 11.3'), (A_STAT_XY, 'PLA static XY 25.5'),
                   (AL_ALLOW, '6061-T6 / SF2 138')):
        a.axvline(v, color='#555', ls='--', lw=0.9)
        a.annotate(lab, (v, -0.9), rotation=90, fontsize=7, va='bottom', ha='right',
                   color='#555')
    a.set_yticks(y)
    a.set_yticklabels([f"{r['short']} · {r['cad_name'] or en(r['label'])}  ({r['vol_cm3']:.0f} cm³)"
                       for r in big], fontsize=7.2)
    a.invert_yaxis()
    a.set_xscale('log')
    a.set_xlim(0.5, 400)
    a.set_xlabel('volume-weighted p99 von Mises [MPa]  (design tier ×1.25)')
    a.set_title('Per part: walking load vs campaign basis — colour = PLA stress band under walking',
                fontsize=9.5)
    a.legend(fontsize=7.5, loc='lower right')
    a.grid(alpha=0.3, axis='x')

    b = ax[1]
    lk = links_done
    mc = [max(r['p99_campaign'] for r in real if r['link'] == L) for L in lk]
    mw_ = [max(r['p99_walk'] for r in real if r['link'] == L) for L in lk]
    yy = np.arange(len(lk))
    b.barh(yy - 0.19, mc, 0.36, color='#9aa7b5', label='campaign basis')
    b.barh(yy + 0.19, mw_, 0.36, color='#2e86c1', label='simple walking')
    for i, (c1, w1) in enumerate(zip(mc, mw_)):
        b.annotate(f'{w1/c1:.2f}×', (max(c1, w1) * 1.05, i + 0.19), fontsize=7.5, va='center')
    b.axvline(A_FAT_XY, color=col['GREEN'], ls='--', lw=1)
    b.axvline(A_STAT_Z, color=col['ORANGE'], ls='--', lw=1)
    b.set_yticks(yy)
    b.set_yticklabels([SHORT[L] for L in lk])
    b.invert_yaxis()
    b.set_xscale('log')
    b.set_xlabel('worst part p99 [MPa]')
    b.set_title('Per link: the worst part barely moves\n(vertical load is 88–93 % of full-box)',
                fontsize=9.5)
    b.legend(fontsize=7.5)
    b.grid(alpha=0.3, axis='x')
    fig.suptitle(f'PLA triage for simple walking ({tier}: vx −0.5..1.0, |vy|,|wz| ≤ 0.5) — '
                 'what must be milled first', fontsize=11)
    fig.tight_layout()
    fig.savefig(f'{DOCS_IMG}/pla_triage_walk{"" if tier == "T2_walk" else "_" + tier}.png',
                bbox_inches='tight')
    return real


def main():
    tier = next((a.split('=')[1] for a in sys.argv if a.startswith('--tier=')), 'T2_walk')
    links = [a for a in sys.argv[1:] if not a.startswith('--')] or list(GOVERNING.values())
    if '--replot' in sys.argv:
        # names, bands, figure and ranking from the stored rows - no .frd parsing
        J = json.load(open(f'{W}/walk_triage_{tier}.json'))
        real = finish(J['rows'], tier, list(dict.fromkeys(r['link'] for r in J['rows'])))
        json.dump(J, open(f'{W}/walk_triage_{tier}.json', 'w'), indent=1, ensure_ascii=False)
        print(f'\n-> replotted {tier}')
        return
    LW = json.load(open(f'{HERE}/loads_walk.json'))
    assert tier in LW, f'tier {tier} not in loads_walk.json'
    solids = json.load(open(f'{CAD}/fullbody_links.json'))
    prox = json.load(open(f'{CAD}/actuator_proxies.json'))
    seats = []
    for g in GROUP.values():
        f = f'{CAD}/link_{g}_joints.json'
        if os.path.exists(f):
            for b in json.load(open(f)).get('bearings', []):
                for s in b.get('seats', []):
                    seats.append(dict(link=s['link'], loc=np.asarray(s['loc'], float),
                                      r=float(s['r']), type=b.get('type', '')))

    rows, links_done = [], []
    for link in links:
        env = json.load(open(f'{W}/{link}/envelope_P99.json'))
        comps = env['comps']
        mw = walk_mags(env, LW, tier)
        print(f'\n== {link}  joint {env["joint"]}', flush=True)
        print('   campaign', env['magnitudes'])
        print('   walking ', mw, flush=True)
        U, ids = unit_fields(link, comps)
        e_cam = EV.combine(U, [env['magnitudes'][c] for c in comps], comps=comps)
        vm_cam = e_cam['vm_max']
        ref = env['max_vM']
        assert abs(vm_cam.max() - ref) / ref < 0.02, (
            f'{link}: rebuilt campaign peak {vm_cam.max():.1f} vs recorded {ref:.1f} - unit '
            'fields or component order are not the campaign\'s, refusing to continue')
        vm_walk = EV.combine(U, [mw[c] for c in comps], comps=comps)['vm_max']
        del U
        cam_of = dict(zip(ids, vm_cam))
        walk_of = dict(zip(ids, vm_walk))

        nodes, sets = read_mesh_sets(link)
        assert nodes and sets, f'{link}: mesh element sets missing'
        idx = {i: k for k, i in enumerate(nodes)}
        P = np.array([nodes[i] for i in nodes])
        Sc = np.array([cam_of.get(i, 0.0) for i in nodes])
        Sw = np.array([walk_of.get(i, 0.0) for i in nodes])
        bbox = (P.min(0), P.max(0))
        group = GROUP[link]
        cads = [r for r in solids if r['link'] == group and r.get('kind', 'struct') == 'struct']
        myseats = [s for s in seats if s['link'] == group]
        motors = [(k, p) for k, p in prox.items()]
        link_tot = 0.0
        for name, tets in sets.items():
            T = np.array([[idx[n] for n in t] for t in tets if all(n in idx for n in t)])
            if not len(T):
                continue
            a, b, c, d = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]], P[T[:, 3]]
            vol = np.abs(np.einsum('ij,ij->i', b - a, np.cross(c - a, d - a))) / 6.0
            tot = vol.sum()
            link_tot += tot
            com = (P[T].mean(axis=1) * vol[:, None]).sum(0) / tot
            s_cam = S_w = None
            sc, sw = Sc[T].mean(axis=1), Sw[T].mean(axis=1)
            p99c, p99w = weighted_pct(sc, vol, 99), weighted_pct(sw, vol, 99)
            pn = np.unique(T)
            PP = P[pn]
            # physical identity: nearest CAD solid of the same group
            cad_name, cad_vol = '?', None
            if cads:
                k = min(cads, key=lambda r: np.linalg.norm(np.asarray(r['com']) - com))
                cad_vol = k['vol']
                cad_name = NAMES.get((group, round(cad_vol, 1)), '')
            # flags
            dm = {kname: float(cyl_distance(PP, p).min()) for kname, p in motors}
            near = min(dm, key=dm.get)
            seat_hit = [s['type'] for s in myseats
                        if np.linalg.norm(PP - s['loc'], axis=1).min() <= 1.3 * s['r'] + 5.0]
            rows.append(dict(
                link=link, short=SHORT[link], part=name, cad_name=cad_name,
                label=label_of(com, bbox), vol_cm3=round(float(tot / 1000), 1),
                cad_vol_cm3=cad_vol, p99_campaign=round(float(p99c), 2),
                p99_walk=round(float(p99w), 2), peak_walk=round(float(sw.max()), 1),
                motor_mm=round(dm[near], 1), motor=near.replace('robstride_', ''),
                bearing_seat=seat_hit[:2],
                life_h=round(life_hours(p99w), 1),
                sf_al_walk=round(AL_ALLOW / max(p99w, 1e-9), 2)))
        links_done.append(link)
        print(f'   {len(sets)} parts, {link_tot/1000:.1f} cm3; link field p99 '
              f'{weighted_pct(Sc, np.ones_like(Sc), 99):.1f} -> '
              f'{weighted_pct(Sw, np.ones_like(Sw), 99):.1f} MPa (node-based, reference only)',
              flush=True)

    out = dict(tier=tier, factor=FACTOR,
               bands=dict(RED=f'> {A_STAT_Z:.1f} MPa', ORANGE=f'{A_FAT_XY:.1f}..{A_STAT_Z:.1f} MPa',
                          GREEN=f'<= {A_FAT_XY:.1f} MPa',
                          thermal='bolted = touches a motor proxy (<=1.5 mm), zone = within 30 mm'),
               rows=rows)
    finish(rows, tier, links_done)
    json.dump(out, open(f'{W}/walk_triage_{tier}.json', 'w'), indent=1, ensure_ascii=False)
    print(f'\n-> {W}/walk_triage_{tier}.json · {DOCS_IMG}/pla_triage_walk.png')


if __name__ == '__main__':
    main()
