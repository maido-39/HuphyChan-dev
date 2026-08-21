"""The parts INSIDE the links - rods, cranks, the ankle cross, the hard stop, the clevis
fork, bearing seats, tapped threads - ranked by how fast a PLA print of each would fail
under SIMPLE WALKING.

The link FEA (walk_triage.py) covers the plates. These parts were never meshed, and most of
them fail by a mode a von Mises map would not show anyway: a strut buckles, a pin bends, a
stop face is hammered, a thread strips, a bearing seat creeps loose. Each is therefore
checked by the hand calculation that matches its mode, on the measured walking loads:

  loads       tools/fea/loads_walk.json T2 (link-local P99, x1.25 design factor) for the
              joint forces; the 2-RSU rod forces and crank torques come from the measured
              ankle torques pushed through the mechanism Jacobian (ankle_stopper_sizing)
              frame by frame on the walking subset; the stop demand is the joint moment on
              the frames that sit beyond the DESIGN pitch cap (+30), since the sim cap (+40)
              is never touched in walking
  geometry    rods: rods.json (I_min, pin span, Euler load in aluminium - PLA scales by E);
              cross pins: 6900ZZ bore 10; crank and fork sections are ESTIMATES from the
              CAD solid volume and known radii, flagged as such in ASSUME
  PLA         docs/79: UTS 51 in-plane, 17 interlayer, E 2.3 GPa (3.5 upper), compressive
              37-67, notched Izod 2.5-5 kJ/m2, fatigue endurance 0.10 UTS at 2e6, slope 5.5

Output is a ranked table and docs/img/internal_parts_pla.png. SF < 1 means the PLA part
does not survive the walking load by that mode; life_h is the fatigue life where cyclic.

Usage: internal_parts_pla.py
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
W = '/home/syaro/pyg_fea/work'
DOCS_IMG = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img'
FACTOR = 1.25
# PLA (docs/79)
E_AL, E_PLA, E_PLA_HI = 69000.0, 2300.0, 3500.0
UTS_XY, UTS_Z = 51.0, 17.0
TAU_PLA = 0.577 * UTS_Z              # shear, interlayer-limited: 9.8 MPa
TAU_PLA_XY = 0.577 * UTS_XY          # 29.4 MPa if the layer is never in the shear plane
FAT_XY = 0.10 * UTS_XY               # 5.1 MPa endurance at 2e6 (before SF)
SF_FAT, K_SN, N_SN, CYC_H = 1.5, 5.5, 2e6, 2.2e4
# measured on the walking subset (this session; see docs/86 for the commands)
WALK = dict(
    rod=dict(A=dict(comp_p99=204, comp_peak=292, ten_p99=539, ten_peak=800),
             B=dict(comp_p99=181, comp_peak=246, ten_p99=503, ten_peak=823)),
    crank=dict(A=dict(p99=24.1, peak=41.0), B=dict(p99=22.2, peak=38.5)),     # N.m
    stop=dict(pitch_beyond30_p99=52.4, pitch_beyond30_peak=66.7,               # N.m
              frac_beyond30=(0.044, 0.117), sim_cap_contact=0.0004),
)
ASSUME = {
    'crank section': 'plate 14 x 26 mm (32.8 cm3 over a ~90 mm arm); root moment = crank torque',
    'fork arm section': '30 x 14 mm (62 cm3 over ~150 mm); lever seat->root 150 mm; 2 arms share',
    'cross pin': '6900ZZ bore -> pin dia 10 mm; cantilever 19.75 mm seat-centre to cross centre',
    'stop pad': 'roll-gimbal pad at r = 60 mm, shear area 87 mm2 as designed for aluminium',
    'threads': 'steel screw in tapped PLA, L_e = 2D, strip = 0.6 pi D L_e tau',
}


def life_h(sigma):
    return float('inf') if sigma <= 0 else N_SN * (FAT_XY / sigma) ** K_SN / CYC_H


def main():
    LW = json.load(open(f'{HERE}/loads_walk.json'))['T2_walk']
    rods = json.load(open(f'{W}/rods/rods.json'))
    rows = []

    # ---- 1. push rods: buckling (compression peak) and tension fatigue ----
    for tag, key in (('A', 'Arm_A'), ('B', 'Arm_B')):
        r = rods[key]
        pcr_pla = r['P_euler_N'] * E_PLA / E_AL
        dem = WALK['rod'][tag]['comp_peak'] * FACTOR
        rows.append(dict(part=f'push rod {tag}', mode='Euler buckling (compression peak)',
                         demand=f'{dem:.0f} N', capacity=f'{pcr_pla:.0f} N (PLA, E 2.3 GPa)',
                         sf=pcr_pla / dem, life=0.0, note=f'Al P_cr {r["P_euler_N"]:.0f} N; '
                         f'E 3.5 GPa gives {pcr_pla*E_PLA_HI/E_PLA:.0f} N'))
        area = r['volume_cm3'] * 1000 / r['length_mm']
        sig = WALK['rod'][tag]['ten_p99'] * FACTOR / area
        rows.append(dict(part=f'push rod {tag}', mode='tension fatigue (P99)',
                         demand=f'{sig:.1f} MPa', capacity=f'{FAT_XY/SF_FAT:.1f} MPa',
                         sf=(FAT_XY / SF_FAT) / sig, life=life_h(sig),
                         note=f'mean section {area:.0f} mm2 from volume/length'))

    # ---- 2. cranks: root bending ----
    t, w = 14.0, 26.0
    Z = t * w ** 2 / 6
    for tag in 'AB':
        sig99 = WALK['crank'][tag]['p99'] * 1e3 * FACTOR / Z
        sigpk = WALK['crank'][tag]['peak'] * 1e3 * FACTOR / Z
        rows.append(dict(part=f'crank {tag}', mode='root bending fatigue (P99) / static (peak)',
                         demand=f'{sig99:.1f} / {sigpk:.1f} MPa',
                         capacity=f'{FAT_XY/SF_FAT:.1f} / {UTS_XY/2:.1f} MPa',
                         sf=min((FAT_XY / SF_FAT) / sig99, (UTS_XY / 2) / sigpk), life=life_h(sig99),
                         note='section ESTIMATED; hub clamp on the RS03 output creeps loose in PLA'))

    # ---- 3. ankle cross pins ----
    d_pin, lever = 10.0, 19.75
    Fz = LW['ankle_roll']['Fz'] * FACTOR
    Fpin = Fz / 2
    M = Fpin * lever
    Zp = np.pi * d_pin ** 3 / 32
    sig = M / Zp
    rows.append(dict(part='ankle cross (pins)', mode='pin bending, vertical load / 2 pins',
                     demand=f'{sig:.0f} MPa', capacity=f'{UTS_XY:.0f} MPa raw UTS',
                     sf=UTS_XY / sig, life=life_h(sig),
                     note=f'Fz {Fz:.0f} N -> {Fpin:.0f} N/pin x {lever} mm; Al SF {276/sig:.1f}'))
    pb = Fpin / (d_pin * 6.0)
    rows.append(dict(part='ankle cross (pins)', mode='bearing contact under 6900 inner ring',
                     demand=f'{pb:.1f} MPa', capacity='37-67 MPa compressive, creep-limited',
                     sf=37.0 / pb, life=float('inf'), note='static OK, creep loosens the fit'))

    # ---- 4. hard stop: roll-gimbal pad at the DESIGN pitch cap ----
    r_pad, A_pad = 60.0, 87.0
    Fpk = WALK['stop']['pitch_beyond30_peak'] / (r_pad / 1e3)
    F99 = WALK['stop']['pitch_beyond30_p99'] / (r_pad / 1e3)
    tau_pk, tau_99 = Fpk / A_pad, F99 / A_pad
    rows.append(dict(part='hard stop pad (+30 design cap)', mode='pad shear, static (peak)',
                     demand=f'{tau_pk:.1f} MPa ({Fpk:.0f} N)', capacity=f'{TAU_PLA:.1f} MPa',
                     sf=TAU_PLA / tau_pk, life=0.0,
                     note=f'contact on {100*WALK["stop"]["frac_beyond30"][0]:.0f}-'
                          f'{100*WALK["stop"]["frac_beyond30"][1]:.0f} % of walking frames; '
                          'impact every step; Izod 2.5-5 kJ/m2'))
    rows.append(dict(part='hard stop pad (+30 design cap)', mode='pad shear, fatigue (P99)',
                     demand=f'{tau_99:.1f} MPa ({F99:.0f} N)',
                     capacity=f'{0.10*UTS_Z*0.577/SF_FAT:.2f} MPa',
                     sf=(0.10 * UTS_Z * 0.577 / SF_FAT) / tau_99, life=life_h(tau_99 / 0.577),
                     note='with a +40 cap the stop is touched 0.04 % of walking frames (unloaded)'))
    rows.append(dict(part='hard stop pad (fall, 379 N.m)', mode='pad shear, single event',
                     demand=f'{379/0.06/A_pad:.0f} MPa', capacity=f'{TAU_PLA_XY:.0f} MPa best case',
                     sf=TAU_PLA_XY / (379 / 0.06 / A_pad), life=0.0,
                     note='campaign sizing event (docs/76 s12); shatters'))

    # ---- 5. clevis fork arms ----
    Fy = LW['ankle_roll']['Fy'] * FACTOR
    Mf = Fy * 150.0 / 2
    Zf = 14.0 * 30.0 ** 2 / 6
    sigf = Mf / Zf
    rows.append(dict(part='clevis fork arm', mode='fore-aft bending fatigue (P99)',
                     demand=f'{sigf:.1f} MPa', capacity=f'{FAT_XY/SF_FAT:.1f} MPa',
                     sf=(FAT_XY / SF_FAT) / sigf, life=life_h(sigf),
                     note='section ESTIMATED; also holds the 6900 OD22 press-fit seats (creep)'))

    # ---- 6. tapped threads ----
    for D, Le, ext in ((5.0, 10.0, 1212 * 0.7), (4.0, 8.0, 445 * 0.7)):
        strip = 0.6 * np.pi * D * Le * TAU_PLA
        rows.append(dict(part=f'tapped M{D:.0f} in PLA', mode='thread strip vs external load',
                         demand=f'{ext:.0f} N/screw', capacity=f'{strip:.0f} N (L_e 2D, interlayer)',
                         sf=strip / ext, life=float('inf'),
                         note=f'in-plane best case {0.6*np.pi*D*Le*TAU_PLA_XY:.0f} N; no preload '
                              'included - preload alone strips or creeps'))

    # ---- 7. bearing seats ----
    Fk = np.hypot(LW['knee']['Fz'], np.hypot(LW['knee']['Fx'], LW['knee']['Fy'])) * FACTOR
    p = Fk / (65.0 * 7.0)
    rows.append(dict(part='knee 6810 seat', mode='seat contact pressure',
                     demand=f'{p:.1f} MPa', capacity='37 MPa compressive, creep-limited',
                     sf=37.0 / p, life=float('inf'),
                     note='stress trivial; press fit relaxes by creep -> radial play'))

    rows.sort(key=lambda r: r['sf'])
    print(f"{'SF':>6s} {'life h':>8s}  {'part':32s} {'mode':44s} {'demand':22s} {'capacity':30s}")
    for r in rows:
        lh = f"{r['life']:8.2f}" if r['life'] < 1e4 else f"{'—':>8s}"
        print(f"{r['sf']:6.2f} {lh}  {r['part']:32s} {r['mode']:44s} {r['demand']:22s} {r['capacity']:30s}")
        print(f"{'':16s}  {r['note']}")
    json.dump(dict(rows=rows, assume=ASSUME, walk=WALK),
              open(f'{W}/internal_parts_pla.json', 'w'), indent=1, ensure_ascii=False)

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 140, 'font.size': 8.5})
    fig, a = plt.subplots(figsize=(12.5, 0.42 * len(rows) + 1.6))
    y = np.arange(len(rows))
    col = ['#c0392b' if r['sf'] < 1 else '#e67e22' if r['sf'] < 2 else '#27ae60' for r in rows]
    a.barh(y, [max(r['sf'], 0.01) for r in rows], 0.66, color=col)
    for i, r in enumerate(rows):
        a.annotate(f"{r['sf']:.2f}   {r['demand']} vs {r['capacity']}", (max(r['sf'], 0.01) * 1.12, i),
                   fontsize=7, va='center')
    a.axvline(1.0, color='k', lw=1.1)
    a.set_yticks(y)
    a.set_yticklabels([f"{r['part']} — {r['mode']}" for r in rows], fontsize=7.5)
    a.invert_yaxis()
    a.set_xscale('log')
    a.set_xlim(0.01, 200)
    a.set_xlabel('PLA safety factor under simple walking (T2), by failure mode  [<1 = fails]')
    a.set_title('Internal parts in PLA — the parts the link FEA never meshed, each by the mode '
                'that actually kills it', fontsize=10)
    a.grid(alpha=0.3, axis='x')
    fig.tight_layout()
    fig.savefig(f'{DOCS_IMG}/internal_parts_pla.png', bbox_inches='tight')
    print(f'\n-> {W}/internal_parts_pla.json · {DOCS_IMG}/internal_parts_pla.png')


if __name__ == '__main__':
    main()
