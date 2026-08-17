"""Ankle stops at the AS-DESIGNED radii: contact area, boss depth, and the screws.

The CAD puts the stops much closer in than the sizing study assumed:

    AB (crank)  bolt circle dia 78 mm -> r 39 mm   (study assumed 40)
    RP (gimbal) bolt circle dia 46 mm -> r 23 mm   (study recommended >= 60)

Force is T/r, so the RP stop at r 23 carries 2.6x what it would at r 60. That is the whole
story of this script: the radius is the cheapest variable in the design and it was spent.

Sizing follows three independent limits, all of which must pass:

  1. bearing / indentation on the contact face   A >= F / sigma_bearing
  2. shear-out of the boss at its root           A >= F / tau
  3. bending of the boss as a cantilever         sigma = 6*F*L / (t * h^2) <= sigma_allow
     -> this one puts a CEILING on how far the boss may stand proud, not a floor.

and the fasteners are checked separately in double the ways they can fail: shank shear,
thread-root shear, and bearing of the screw against the plate it passes through.

Loads are the measured stop residual (docs/78 §12, tools/ankle_stop_residual.py) pushed
through the mechanism by tools/ankle_stopper_sizing.py:
    AB crank ground-driven 515.1 N.m · AB motor stall 60.0 · RP gimbal 413.0 N.m

Usage: ankle_stopper_detail.py [--sf=2.0] [--t=8] [--out=docs/img]
"""
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# --- materials -------------------------------------------------------------------------
AL_Y = 276.0                      # 6061-T6 yield [MPa]
AL_TAU = 0.577 * AL_Y             # 159
AL_BRG = 1.5 * AL_Y               # 414, confined bearing on a machined face
SCM_12_9_U = 1220.0               # class 12.9 tensile strength [MPa]
SCM_12_9_Y = 1100.0
STEEL_TAU_U = 0.6 * SCM_12_9_U    # 732, shear strength of the fastener
SCM440_Y = 785.0                  # a hardened steel insert / striker pin, if used
SCM440_BRG = 1.5 * SCM440_Y

# --- loads (N.m) -----------------------------------------------------------------------
# (display name [ASCII - figure labels must not contain Hangul, it renders as tofu],
#  driver, torque N.m, stop bolt-circle diameter mm)
CASES = [
    ('AB crank', 'ground', 515.1, 78.0),
    ('AB crank', 'motor stall', 60.0, 78.0),
    ('RP gimbal', 'ground', 413.0, 46.0),
]
# Ø4 screw: shank area, and M4 thread stress area (the root is what shears if the thread
# lies in the shear plane - which is why a shoulder/stripper screw is the right part here)
A_SHANK = np.pi / 4 * 4.0 ** 2    # 12.57 mm2
A_THREAD = 8.78                   # M4 tensile stress area [mm2]


def main():
    sf = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--sf=')), 2.0))
    t = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--t=')), 8.0))
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               os.path.join(HERE, '..', 'docs', 'img'))
    tau_a, brg_a, bend_a = AL_TAU / sf, AL_BRG / sf, AL_Y / sf
    brg_st = SCM440_BRG / sf
    scr_shank = STEEL_TAU_U / sf * A_SHANK          # N per screw, shank in shear
    scr_thread = STEEL_TAU_U / sf * A_THREAD        # N per screw, thread root in shear
    scr_brg = brg_a * 4.0 * t                       # N per screw, bearing in the 6061 plate

    print(f'SF {sf:.1f} · boss thickness t = {t:.0f} mm')
    print(f'  6061-T6   shear {tau_a:.0f} · bearing {brg_a:.0f} · bending {bend_a:.0f} MPa')
    print(f'  steel insert (SCM440) bearing {brg_st:.0f} MPa')
    print(f'  Ø4 class 12.9 screw: shank shear {scr_shank:.0f} N · thread-root shear '
          f'{scr_thread:.0f} N · bearing in {t:.0f} mm 6061 {scr_brg:.0f} N\n')

    rows = []
    for name, drv, T, dia in CASES:
        r = dia / 2
        F = T * 1000.0 / r
        A_brg = F / brg_a                 # contact area, aluminium face
        # a steel boss raises BOTH allowables, not just bearing - the earlier version
        # mixed a steel bearing limit with an aluminium shear limit and so reported no gain
        A_brg_st = F / brg_st
        A_shr_st = F / (0.577 * SCM440_Y / sf)
        A_shr = F / tau_a                 # shear-out at the root
        A_req = max(A_brg, A_shr)
        h = A_req / t                     # face height if the boss is t thick
        h_brg_st = max(A_brg_st, A_shr_st) / t
        # cantilever ceiling: how far the boss may stand proud before its root yields
        L_max = bend_a * t * h ** 2 / (6 * F)
        n_scr = max(F / scr_shank, F / scr_thread, F / scr_brg)
        n = int(np.ceil(n_scr))
        # If the stop element is the SCREW itself (a striker pin), the plate it bears
        # against must not tear out behind the pin. Two shear planes of e x t each:
        #     F/n = 2 * e * t * tau   ->  e = F / (2 n t tau)
        # This is the "how far back does the material have to extend" number, and it is a
        # MINIMUM - unlike the cantilever L_max above, which is a maximum.
        e_min = F / (max(n, 1) * 2.0 * t * tau_a)
        e_1 = F / (2.0 * t * tau_a)            # if somebody tries a single screw
        # a screw loaded in shear also bends over the plate it stands proud of
        F_per = F / max(n, 1)
        rows.append(dict(name=name, drv=drv, T=T, dia=dia, r=r, F=F, A_brg=A_brg,
                         A_shr=A_shr, A_req=A_req, h=h, h_st=h_brg_st, L_max=L_max,
                         A_req_st=max(A_brg_st, A_shr_st), n_scr=n_scr,
                         n=n, e_min=e_min, e_1=e_1, F_per=F_per))
        print(f'{name} ({drv})  T {T:.1f} N·m @ r {r:.0f} mm  ->  F {F:.0f} N '
              f'({F/9810:.2f} tonf)')
        print(f'   접촉면적  베어링 {A_brg:6.1f} mm² · 전단 {A_shr:6.1f} mm²  '
              f'-> 요구 {A_req:6.1f} mm²')
        print(f'   t={t:.0f} mm 이면 면 높이 h = {h:5.1f} mm (6061-T6) '
              f'/ {h_brg_st:5.1f} mm (SCM440 강재 보스)')
        print(f'   보스 돌출 한계 L_max = {L_max:5.1f} mm  (뿌리 굽힘 {bend_a:.0f} MPa 기준)')
        print(f'   Ø4 12.9 나사 필요 개수 {n_scr:5.2f} -> {n} 개'
              f'  (지배: '
              f'{["shank","thread","bearing"][int(np.argmax([F/scr_shank, F/scr_thread, F/scr_brg]))]})'
              f'  · 나사당 {F_per:.0f} N')
        print(f'   나사 뒤 연거리(전단파열) e ≥ {e_min:5.1f} mm  [{n}개 분담] '
              f'/ 1개뿐이면 {e_1:5.1f} mm')
        print(f'   -> 연거리 배수 e/d = {e_min/4.0:.1f}d  '
              f'(관행 최소 2d = 8 mm, 알루미늄 판단부는 3d 권장)\n')

    # ---- figure -------------------------------------------------------------------
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, axes = plt.subplots(1, 3, figsize=(14.4, 4.3))
    lbl = [f"{r['name']}\n{r['drv']}" for r in rows]
    x = np.arange(len(rows))
    cols = ['#c0392b', '#e67e22', '#2e86c1']

    axes[0].bar(x, [r['F'] / 1000 for r in rows], 0.55, color=cols)
    for i, r in enumerate(rows):
        axes[0].text(i, r['F'] / 1000 * 1.02, f"{r['F']/1000:.1f} kN\n@r {r['r']:.0f}",
                     ha='center', fontsize=8, fontweight='bold')
    axes[0].set_ylabel('contact force [kN]')
    axes[0].set_title('Force at the AS-DESIGNED radii')

    w = 0.36
    axes[1].bar(x - w / 2, [r['A_brg'] for r in rows], w, color='#7d3c98',
                label=f'bearing ({brg_a:.0f} MPa)')
    axes[1].bar(x + w / 2, [r['A_shr'] for r in rows], w, color='#16a085',
                label=f'shear-out ({tau_a:.0f} MPa)')
    for i, r in enumerate(rows):
        axes[1].text(i, r['A_req'] * 1.03, f"{r['A_req']:.0f} mm²", ha='center',
                     fontsize=8, fontweight='bold')
    axes[1].set_ylabel('required contact area [mm$^2$]')
    axes[1].set_title(f'Section needed at SF {sf:.1f}, 6061-T6')
    axes[1].legend(fontsize=7.5)

    # face height vs boss thickness - shows what t buys you
    tt = np.linspace(4, 20, 120)
    for r, c in zip(rows, cols):
        axes[2].plot(tt, r['A_req'] / tt, color=c, lw=2, label=f"{r['name']} {r['drv']}")
        axes[2].plot([t], [r['A_req'] / t], 'o', color=c, ms=7)
    axes[2].axvline(t, color='k', ls=':', lw=1.0)
    axes[2].text(t + 0.2, axes[2].get_ylim()[1] * 0.9, f'{t:.0f}T', fontsize=8)
    axes[2].set_xlabel('boss thickness t [mm]')
    axes[2].set_ylabel('required face height h = A/t [mm]')
    axes[2].set_title('Face height the 8T section has to carry')
    axes[2].grid(alpha=0.3)
    axes[2].legend(fontsize=7.5)
    for ax in axes[:2]:
        ax.set_xticks(x)
        ax.set_xticklabels(lbl, fontsize=8)
        ax.grid(alpha=0.3, axis='y')
    fig.suptitle(f'Ankle stops at the CAD radii (AB Ø78, RP Ø46) — the RP stop at r 23 mm '
                 f'carries {rows[2]["F"]/(413000/60):.1f}x what it would at r 60 mm',
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'ankle_stopper_detail.png'))
    print('-> docs/img/ankle_stopper_detail.png')


if __name__ == '__main__':
    main()
