"""High-cycle fatigue screen for every solved link - no re-solve.

The campaign judged the links against YIELD (276 MPa). A walking robot does not fail
that way: docs/64 §10.1 already fixes the protocol - "사이클 ~6 Hz → 100 h ≈ 2.2×10⁶
(고사이클)", forces at R ≈ −0.3, moments at R ≈ −1. Aluminium has no endurance limit,
so the design must be placed on the S-N curve, not under a yield line.

Method (screening, linear statics so the field just scales):
  sigma_max  = design field / 1.25          (the 1.25 is a static design factor, not a
                                             load the structure actually sees every step)
  sigma_a    = sigma_max (1 - R)/2 ,  sigma_m = sigma_max (1 + R)/2
  Goodman:     sigma_a/S_N + sigma_m/S_u = 1/SF_fatigue

S_N for 6061-T6 at 2.2e6 cycles ≈ 124 MPa (fully reversed, polished); a machined surface
and the as-built condition take that down, so a surface factor is applied. S_u = 310 MPa.

This is a SCREEN, not a life prediction: the real answer needs a rainflow count of the
measured stress history, which docs/64 §10.1 also says ("rainflow(간이: p99 진폭+사이클수)").
What it does settle is which links are nowhere near a fatigue problem and which ones
cannot be signed off on the yield check alone.

Usage: fatigue.py [LINK ...]
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = '/home/syaro/pyg_fea/work'

S_U = 310.0            # 6061-T6 ultimate [MPa]
S_N_POLISHED = 124.0   # fully reversed strength at ~2e6 cycles [MPa]
K_SURFACE = 0.85       # machined / as-built surface
K_SIZE = 0.90          # size effect on a thick section
S_N = S_N_POLISHED * K_SURFACE * K_SIZE
R_FORCE = -0.3         # docs/64 §10.1: force-driven stress cycles
DESIGN_FACTOR = 1.25   # removed to get the physical per-cycle stress

# P99 is the 99th percentile of the measured wrench: using it as EVERY cycle's peak is
# far too severe for a fatigue count. docs/64 §10.2 also reports the RMS level, and the
# RMS/P99 ratio is remarkably uniform across the joints, so the pair brackets the answer:
# P99-level = conservative, RMS-level = the cycle the structure actually sees most of the time.
RMS_OVER_P99 = {'hip_pitch': 276 / 634, 'hip_roll': 217 / 533, 'hip_yaw': 147 / 380,
                'knee': 331 / 785, 'ankle_pitch': 360 / 897, 'ankle_roll': 353 / 859}


def screen(sigma_max, R=R_FORCE):
    """(sigma_a, sigma_m, Goodman safety factor) for one stress level."""
    a = sigma_max * (1 - R) / 2.0
    m = sigma_max * (1 + R) / 2.0
    denom = a / S_N + max(0.0, m) / S_U
    return a, m, (1.0 / denom if denom > 0 else float('inf'))


def main():
    links = sys.argv[1:] or sorted(os.path.basename(os.path.dirname(f))
                                   for f in glob.glob(f'{W}/*/envelope_P99.json'))
    print(f'6061-T6 high-cycle screen · S_N(2.2e6, corrected) = {S_N:.0f} MPa · '
          f'S_u = {S_U:.0f} MPa · R = {R_FORCE}')
    print(f'{"link":24s} {"design":>8s} {"per-cycle":>9s} {"sigma_a":>8s} {"sigma_m":>8s} '
          f'{"SF@P99":>7s} {"SF@RMS":>8s}  verdict (on the conservative P99 cycle)')
    out = {}
    for L in links:
        f = f'{W}/{L}/envelope_P99.json'
        if not os.path.exists(f):
            continue
        d = json.load(open(f))
        des = d.get('max_vM_design', d['max_vM'])
        smax = des / DESIGN_FACTOR
        a, m, sf = screen(smax)
        ratio = RMS_OVER_P99.get(d.get('joint'), 0.41)
        a_r, m_r, sf_r = screen(smax * ratio)
        # a peak covering a handful of nodes is a singularity, not a fatigue site
        oa = (d.get('over_allowable') or {}).get('SF>2.0', {})
        local = (oa.get('nodes_design') or 0) < 20
        v = ('PASS' if sf >= 1.0 else ('FAIL' if not local else 'FAIL (local peak - check the site)'))
        out[L] = dict(design_MPa=round(des, 1), per_cycle_MPa=round(smax, 1),
                      sigma_a=round(a, 1), sigma_m=round(m, 1), SF_fatigue_P99=round(sf, 2),
                      rms_over_p99=round(ratio, 3), SF_fatigue_RMS=round(sf_r, 2),
                      verdict=v, peak_is_local=local, p99_MPa=d.get('p99_vM'))
        print(f'{L:24s} {des:8.1f} {smax:9.1f} {a:8.1f} {m:8.1f} {sf:7.2f} {sf_r:8.2f}  {v}')
    json.dump(dict(method=dict(S_N=S_N, S_u=S_U, R=R_FORCE, cycles='2.2e6 (100 h at ~6 Hz)',
                               design_factor_removed=DESIGN_FACTOR,
                               note='Goodman mean-stress correction on the linear-scaled '
                                    'envelope field; a rainflow count of the measured stress '
                                    'history would replace it'),
                   links=out), open(f'{W}/fatigue.json', 'w'), indent=1)
    print(f'\n-> {W}/fatigue.json')
    bad = [k for k, v in out.items() if v['SF_fatigue_P99'] < 1.0]
    if bad:
        print('below 1.0 on the fatigue screen: ' + ', '.join(bad))


if __name__ == '__main__':
    main()
