"""Could any of these links be printed in PLA instead of machined in 6061-T6?

The campaign already measured, per link, the stress the walking loads actually produce
(volume-weighted field p99, the mesh-independent basis). Screening a different material is
then just a matter of putting a defensible allowable next to those numbers - provided the
allowable carries the knockdowns that FDM parts actually suffer, which is where naive
comparisons go wrong.

The knockdown chain, each factor separable so the sensitivity is visible:

  sigma_ult      short-term tensile strength of the printed material
  x k_z          interlayer (Z) bond vs in-plane, because a real part rarely has its
                 principal stress conveniently in the raster plane
  x k_infill     infill density; 100 % solid = 1.0
  x k_creep      sustained-load derating - a standing biped holds load continuously and
                 thermoplastics creep at room temperature under static stress
  x k_temp       proximity to a motor; PLA's Tg is ~60 C and QDD actuators reach it
  / SF           safety factor

Three allowable levels are reported rather than one, because the honest answer depends on
which of those apply to a given part:

  optimistic   solid, in-plane loading, short-term, away from motors   (prototype only)
  moderate     solid, Z-direction, short-term                          (a jig or a cover)
  structural   solid, Z-direction, sustained load                      (a real load path)

It also reports what it would TAKE: the wall-thickness scale-up needed to bring each part
under the structural allowable, bracketed between membrane behaviour (sigma ~ 1/t) and
bending (sigma ~ 1/t^2), and what that does to mass given PLA is 1.24 vs aluminium's 2.70
g/cm3. And it reports the stiffness ratio, which is a separate question the stress screen
cannot answer.

Material numbers are placeholders pending the literature pass - override on the command
line and the whole table moves with them.

Usage: pla_screen.py [--ult=50] [--kz=0.5] [--kcreep=0.25] [--sf=2.0] [--out=docs/img]
"""
import json
import os
import re
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

W = '/home/syaro/pyg_fea/work'
AL_YIELD = 276.0          # 6061-T6
E_AL = 69000.0            # MPa
E_PLA = 3500.0            # MPa, FDM PLA along the raster
RHO_AL = 2.70             # g/cm3
RHO_PLA = 1.24

# Which solved case represents each physical part AS DESIGNED (motors present, since the
# design has them). The *_nomotor cases are a what-if about the bracket load path and are
# reported separately rather than mixed in.
PARTS = {
    'L1 발(foot)': dict(cases=['L1_ankle_foot', 'L1b_foot_toeoff', 'L1e_foot_toeoff_finer',
                               'L1f_foot_lateral_edge', 'L1g_foot_corner',
                               'L1gf_foot_corner_fine', 'L1h_foot_toeoff_clean'],
                        motor=False, note='지면 충격 직격 · 모터 없음'),
    'L2 정강이(shin)': dict(cases=['L2_shin', 'L2b_shin_cornerfine', 'L2e_shin_elastic'],
                            motor=True, note='RS03 발목 하우징 2개 체결'),
    'L3 대퇴(thigh)': dict(cases=['L3_thigh', 'L3e_thigh_elastic'],
                           motor=True, note='RS04 무릎 모터 체결'),
    'L4 힙요(hip yaw)': dict(cases=['L4_hip_yaw'], motor=True, note='RS03 요 모터 체결'),
    'L5 힙피치롤': dict(cases=['L5_hip_pitchroll', 'L5d_hip_peakfine', 'L5e_hip_elastic',
                              'L5eh_hip_elastic_clean'],
                       motor=True, note='RS04 2개(피치·롤) 체결'),
    'L6 골반(pelvis)': dict(cases=['L6_pelvis', 'L6f_pelvis_peakfine'],
                            motor=True, note='RS04 2개 + 몸통 인터페이스'),
}
NOMOTOR = {'L2 정강이(shin)': 'L2c_shin_nomotor', 'L3 대퇴(thigh)': 'L3cf_thigh_nomotor_fine',
           'L5 힙피치롤': 'L5cf_hip_nomotor_fine', 'L6 골반(pelvis)': 'L6cf_pelvis_nomotor_fine'}


def arg(name, default):
    return float(next((a.split('=')[1] for a in sys.argv if a.startswith(f'--{name}=')),
                      default))


def main():
    ult = arg('ult', 50.0)         # MPa, FDM PLA in-plane at high infill
    kz = arg('kz', 0.50)           # interlayer / in-plane
    kcreep = arg('kcreep', 0.25)   # sustained-load derating
    ktemp = arg('ktemp', 0.30)     # near a motor, approaching Tg
    sf = arg('sf', 2.0)
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')

    V = {r['link']: r for r in json.load(open(f'{W}/field_volume.json')) if r.get('p99_vol')}
    levels = {
        'optimistic (프로토타입)': ult / sf,
        'moderate (지그·커버)': ult * kz / sf,
        'structural (실하중)': ult * kz * kcreep / sf,
        'structural + 모터열': ult * kz * kcreep * ktemp / sf,
    }
    print(f'PLA 허용응력 사슬  ult {ult:.0f} · k_z {kz:.2f} · k_creep {kcreep:.2f} · '
          f'k_temp {ktemp:.2f} · SF {sf:.1f}')
    for k, v in levels.items():
        print(f'   {k:26s} {v:6.2f} MPa   (6061-T6 대비 1/{AL_YIELD/sf/v:.0f})')
    a_struct = levels['structural (실하중)']
    a_hot = levels['structural + 모터열']

    rows = []
    for name, spec in PARTS.items():
        got = [(c, V[c]['p99_vol']) for c in spec['cases'] if c in V]
        assert got, f'{name}: none of {spec["cases"]} has a volume-weighted result'
        worst_case, s = max(got, key=lambda t: t[1])
        allow = a_hot if spec['motor'] else a_struct
        sf_pla = allow / s
        # what it would take: sigma ~ 1/t (membrane) .. 1/t^2 (bending)
        need = s / allow
        t_mem, t_bend = need, np.sqrt(need)
        m_mem = (RHO_PLA / RHO_AL) * t_mem
        m_bend = (RHO_PLA / RHO_AL) * t_bend
        nm = NOMOTOR.get(name)
        rows.append(dict(name=name, case=worst_case, stress=s, allow=allow, sf=sf_pla,
                         motor=spec['motor'], note=spec['note'],
                         t_mem=t_mem, t_bend=t_bend, m_mem=m_mem, m_bend=m_bend,
                         nomotor=V[nm]['p99_vol'] if nm and nm in V else None,
                         sf_al=AL_YIELD / s))
    rows.sort(key=lambda r: -r['sf'])

    print(f"\n{'부품':18s} {'최악 케이스':26s} {'응력':>7s} {'PLA허용':>7s} {'SF(PLA)':>8s} "
          f"{'SF(6061)':>9s}  판정")
    for r in rows:
        v = ('✅가능' if r['sf'] >= 1.0 else
             '⚠경계' if r['sf'] >= 0.7 else '❌불가')
        print(f"{r['name']:18s} {r['case']:26s} {r['stress']:6.1f}M {r['allow']:6.2f}M "
              f"{r['sf']:8.2f} {r['sf_al']:9.2f}  {v}")

    print(f"\n{'부품':18s} {'필요 두께배수':>22s} {'PLA 질량비(vs 현 알루미늄)':>26s}")
    for r in rows:
        print(f"{r['name']:18s} {r['t_bend']:8.1f}x ~ {r['t_mem']:6.1f}x   "
              f"{r['m_bend']:10.1f}x ~ {r['m_mem']:6.1f}x")

    print(f'\n강성: E_PLA {E_PLA/1000:.1f} GPa vs 6061-T6 {E_AL/1000:.0f} GPa = '
          f'**{E_AL/E_PLA:.0f}배 무름**. 같은 형상이면 처짐이 {E_AL/E_PLA:.0f}배다 — '
          f'강도와 별개로 이것만으로 실격일 수 있다(§강성).')
    nm = [r for r in rows if r['nomotor']]
    if nm:
        print('\n참고 — 모터 브래킷이 하중을 안 나눌 때(what-if):')
        for r in nm:
            print(f"   {r['name']:18s} {r['stress']:6.1f} -> {r['nomotor']:6.1f} MPa "
                  f"(SF(PLA) {r['allow']/r['nomotor']:.2f})")

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, ax = plt.subplots(1, 3, figsize=(15.0, 4.6))
    nm_en = {'L1 발(foot)': 'L1 foot', 'L2 정강이(shin)': 'L2 shin', 'L3 대퇴(thigh)': 'L3 thigh',
             'L4 힙요(hip yaw)': 'L4 hip yaw', 'L5 힙피치롤': 'L5 hip pitch/roll',
             'L6 골반(pelvis)': 'L6 pelvis'}
    lab = [nm_en[r['name']] for r in rows]
    y = np.arange(len(rows))

    ax[0].barh(y, [r['stress'] for r in rows], color='#2e86c1', label='measured field p99')
    for k, (nmv, val) in enumerate(levels.items()):
        ax[0].axvline(val, color=['#27ae60', '#e67e22', '#c0392b', '#7d3c98'][k], ls='--',
                      lw=1.3, label=f'{nmv.split(" ")[0]} {val:.1f} MPa')
    ax[0].axvline(AL_YIELD / 2, color='k', ls=':', lw=1.2, label='6061-T6 SF2 = 138')
    ax[0].set_yticks(y)
    ax[0].set_yticklabels(lab, fontsize=8)
    ax[0].invert_yaxis()
    ax[0].set_xscale('log')
    ax[0].set_xlabel('stress / allowable [MPa]')
    ax[0].set_title('Measured stress vs PLA allowables', fontsize=9.5)
    ax[0].legend(fontsize=6.5, loc='lower right')
    ax[0].grid(alpha=0.3, axis='x')

    cols = ['#27ae60' if r['sf'] >= 1 else '#e67e22' if r['sf'] >= 0.7 else '#c0392b'
            for r in rows]
    ax[1].barh(y, [r['sf'] for r in rows], color=cols)
    ax[1].axvline(1.0, color='k', ls='--', lw=1.2)
    for i, r in enumerate(rows):
        ax[1].text(r['sf'] * 1.15, i, f"{r['sf']:.3f}", va='center', fontsize=7.5)
    ax[1].set_yticks(y)
    ax[1].set_yticklabels(lab, fontsize=8)
    ax[1].invert_yaxis()
    ax[1].set_xscale('log')
    ax[1].set_xlabel('safety factor in PLA (1.0 = marginal)')
    ax[1].set_title('Not one part reaches SF 1', fontsize=9.5)
    ax[1].grid(alpha=0.3, axis='x')

    w = 0.38
    ax[2].barh(y - w / 2, [r['t_bend'] for r in rows], w, color='#7d3c98', label='bending σ~1/t²')
    ax[2].barh(y + w / 2, [r['t_mem'] for r in rows], w, color='#c0392b', label='membrane σ~1/t')
    ax[2].axvline(1.0, color='k', ls='--', lw=1.0)
    ax[2].set_yticks(y)
    ax[2].set_yticklabels(lab, fontsize=8)
    ax[2].invert_yaxis()
    ax[2].set_xscale('log')
    ax[2].set_xlabel('wall thickness multiple needed')
    ax[2].set_title('What it would take', fontsize=9.5)
    ax[2].legend(fontsize=7)
    ax[2].grid(alpha=0.3, axis='x')

    fig.suptitle(f'PLA substitution screen — structural allowable {a_struct:.1f} MPa '
                 f'({a_hot:.1f} near motors) against measured walking stress', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'pla_screen.png'))
    json.dump(rows, open(f'{W}/pla_screen.json', 'w'), indent=1, ensure_ascii=False)
    print('\n-> docs/img/pla_screen.png · ~/pyg_fea/work/pla_screen.json')


if __name__ == '__main__':
    main()
