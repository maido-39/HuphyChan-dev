#!/usr/bin/env python3
"""Render the FINAL 2-RSU ankle design's optimisation: the v9h2 Differential-Evolution
convergence (160 generations), from the per-generation trace that produced the design of record.

Why this exists: the only optimisation-process clip in the video archive
(`20260811 022118 ... pattern search (slowed 4x)`) shows the SUPERSEDED 2026-08-04 §7e
coordinate-descent stage (A_r 70 / B_r 62.9 / RP_h 20, P99 16.3 %), which was invalidated by
the pitch-sign bug (docs/71 §9), the swing_foot arcsin->arccos bug (§10c) and the ball-joint
+-13->+-20 redesign (§8), and whose METHOD was discarded in §8e after it was shown to land in
16 distinct local minima. The design of record is v9h2 (docs/76 §1). This script renders that.

Source data (no optimisation is re-run):
  logs/sweep/romscan_gens_v9h2_f0.jsonl  - 160 lines, best individual per generation
  logs/sweep/romscan_final_v9h2_f0.json  - final winner + margins
Geometry/IK follow analysis/ankle_opt_de_v9_human.py (anchors(), rodgeo(); A2B=100).

Usage:  .venv/bin/python3 tools/ankle_de_convergence_video.py [--fps 8] [--out PATH]
"""
import argparse, json, os, subprocess, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: F401  (3d projection)

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
SWEEP = f'{REPO}/mujoco-sim/mjlab/analysis/logs/sweep'
GENS = f'{SWEEP}/romscan_gens_v9h2_f0.jsonl'
FINAL = f'{SWEEP}/romscan_final_v9h2_f0.json'
A2B = 100.0          # A crank sits A2B mm above B (ankle_opt_de_v9_human.py)
MARG_KEYS = [('torque', 'motor torque'), ('tn', 'T-N envelope'), ('rod', 'rod force'),
             ('swing', 'crank-side swing'), ('swing_foot', 'rod-end swing (JS6)'),
             ('trans', 'transmission ratio'), ('human', 'human-gait coverage')]


def anchors(P, side, tp=0.0, tr=0.0):
    """Foot-side rod anchor in the shank frame (ankle_opt_de_v9_human.py:116)."""
    ax, ay, az = side * P['RP_r'], P['RP_B'], -P['RP_h']
    cp, sp, cr, sr = np.cos(tp), np.sin(tp), np.cos(tr), np.sin(tr)
    return (cr * ax + sr * az,
            -sp * sr * ax + cp * ay + sp * cr * az,
            -cp * sr * ax - sp * ay + cp * cr * az)


def crank_tip(P, up, phi_deg):
    """Crank pivot and rod-end tip for motor A (up=True) or B."""
    side = 1.0 if up else -1.0
    Ax = side * P['A_h']
    Az = P['B2RP'] + (A2B if up else 0.0)
    r = P['A_r'] if up else P['B_r']
    phi = np.radians(phi_deg)
    return (Ax, 0.0, Az), (Ax, r * np.cos(phi), Az + r * np.sin(phi)), r


def load_trace():
    gens = [json.loads(l) for l in open(GENS)]
    final = json.load(open(FINAL))
    return gens, final


def draw_mechanism(ax, P, n0A, n0B, lims):
    ax.clear()
    ax.set_axis_off()
    ax.set_box_aspect((1, 1, 1.35))
    for up, col, name, n0 in ((True, '#d95f02', 'A (upper)', n0A), (False, '#1f77b4', 'B (lower)', n0B)):
        side = 1.0 if up else -1.0
        piv, tip, r = crank_tip(P, up, 180.0 + n0)   # PHI0=pi branch + neutral offset
        w = anchors(P, side)
        ax.plot(*zip(piv, tip), color=col, lw=4, solid_capstyle='round')
        ax.scatter(*piv, color=col, s=70, depthshade=False)
        ax.plot(*zip(tip, w), color=col, lw=2.2, alpha=0.85)
        ax.scatter(*w, color='#2ca02c', s=45, depthshade=False)
        ax.text(piv[0], piv[1], piv[2] + 18, f'motor {name}', color=col,
                fontsize=9.5, fontweight='bold', ha='center')
    # shank axis and foot plate
    ax.plot([0, 0], [0, 0], [lims[2][0], lims[2][1]], color='0.75', lw=7, alpha=0.55, zorder=0)
    fp = np.array([[-70, -60], [70, -60], [70, 90], [-70, 90], [-70, -60]], float)
    ax.plot(fp[:, 0], fp[:, 1], np.zeros(len(fp)), color='#8c6d31', lw=1.4)
    ax.text(0, 95, 4, 'foot, neutral pose (pitch 0, roll 0)', color='#8c6d31',
            fontsize=9, ha='center')
    ax.set_xlim(*lims[0]); ax.set_ylim(*lims[1]); ax.set_zlim(*lims[2])
    ax.view_init(elev=16, azim=-58)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fps', type=float, default=8.0)
    ap.add_argument('--hold', type=float, default=3.0, help='seconds to hold the final frame')
    ap.add_argument('--out', default=f'{REPO}/docs/mujoco/assets/ankle_opt_de_v9h2_convergence.mp4')
    ap.add_argument('--workdir', default='/tmp/ankle_de_frames')
    args = ap.parse_args()

    gens, final = load_trace()
    n = len(gens)
    score = np.array([g['best_score'] for g in gens]) * 100.0
    feas = np.array([g['best_feas'] for g in gens])
    pstd = np.array([g['pop_std'] for g in gens])
    nfeas = np.array([g['n_feas'] for g in gens])
    first_feas = int(np.argmax(feas)) + 1 if feas.any() else None

    # fixed 3D limits over the whole run so the geometry morph is readable
    xs, ys, zs = [], [], []
    for g in gens:
        P = g['best_x']
        for up in (True, False):
            piv, tip, _ = crank_tip(P, up, 180.0)
            w = anchors(P, 1.0 if up else -1.0)
            for p in (piv, tip, w):
                xs.append(p[0]); ys.append(p[1]); zs.append(p[2])
    pad = 25.0
    lims = ((min(xs) - pad, max(xs) + pad), (min(ys) - pad, max(ys) + pad), (-70, max(zs) + pad))

    os.makedirs(args.workdir, exist_ok=True)
    for f in os.listdir(args.workdir):
        if f.endswith('.png'):
            os.remove(os.path.join(args.workdir, f))

    fig = plt.figure(figsize=(12.5, 7.0), dpi=100)
    ax3d = fig.add_axes([0.01, 0.06, 0.42, 0.80], projection='3d')
    axc = fig.add_axes([0.52, 0.56, 0.45, 0.33])
    axm = fig.add_axes([0.52, 0.09, 0.45, 0.34])

    ymin = max(-40.0, float(score.min()) - 3)
    for i, g in enumerate(gens):
        P, m = g['best_x'], g['best_marg']
        draw_mechanism(ax3d, P, g['best_n0A'], g['best_n0B'], lims)
        ax3d.set_title(f"generation {g['gen']:3d} / {n}    "
                       + ('feasible' if g['best_feas'] else 'infeasible'),
                       fontsize=13, fontweight='bold',
                       color=('#136d13' if g['best_feas'] else '#b00'))
        fig.suptitle('2-RSU ankle, FINAL design optimisation (v9h2): differential evolution, '
                     'NP=80 F=0.6 CR=0.9, Deb lexicographic hard constraints',
                     fontsize=12.5, y=0.975)
        ax3d.text2D(0.0, -0.06,
                    f"A_r {P['A_r']:.1f}  B_r {P['B_r']:.1f}  RP_B {P['RP_B']:.1f}  "
                    f"RP_r {P['RP_r']:.1f}  A_h {P['A_h']:.1f}\n"
                    f"B2RP {P['B2RP']:.1f}  RP_h {P['RP_h']:.1f}  "
                    f"A_L {P['A_L']:.1f}  B_L {P['B_L']:.1f}  [mm]",
                    transform=ax3d.transAxes, fontsize=10.5, family='monospace')

        axc.clear()
        axc.plot(np.arange(1, i + 2), score[:i + 1], color='#1f77b4', lw=1.8)
        axc.scatter([i + 1], [score[i]], color=('#136d13' if g['best_feas'] else '#b00'), s=34, zorder=3)
        axc.axhline(0, color='0.5', lw=1, ls='--')
        if first_feas and i + 1 >= first_feas:
            axc.axvline(first_feas, color='#136d13', lw=1, ls=':')
            axc.text(first_feas + 2, ymin + 2, f'first feasible (gen {first_feas})',
                     fontsize=8.5, color='#136d13')
        axc.set_xlim(0, n + 1); axc.set_ylim(ymin, max(6.0, float(score.max()) + 2))
        axc.set_xlabel('DE generation', fontsize=9.5)
        axc.set_ylabel('P99 min-margin [%]', fontsize=9.5)
        axc.set_title(f"best-of-population   score {score[i]:+.2f} %   "
                      f"feasible individuals {nfeas[i]:3d}/80   pop std {pstd[i]:.3f}",
                      fontsize=10)
        axc.grid(alpha=0.3)

        axm.clear()
        vals = [m.get(k, np.nan) * 100.0 for k, _ in MARG_KEYS]
        labels = [lab for _, lab in MARG_KEYS]
        colors = ['#b00' if (v is not None and v < 0) else '#8fbf8f' for v in vals]
        if g['best_feas']:
            b = int(np.nanargmin(vals))
            colors[b] = '#d95f02'
        ypos = np.arange(len(vals))
        axm.barh(ypos, np.clip(vals, -60, 120), color=colors, height=0.62)
        axm.set_yticks(ypos); axm.set_yticklabels(labels, fontsize=9)
        axm.invert_yaxis()
        axm.axvline(0, color='0.35', lw=1.2)
        axm.set_xlim(-60, 120)
        axm.set_xlabel('constraint margin [%]   (negative = violated, orange = binding)', fontsize=9)
        for y, v in zip(ypos, vals):
            axm.text(min(v, 118) + 2, y, f'{v:+.1f}', va='center', fontsize=8.5)
        axm.set_title('hard constraints (Deb rules: feasibility first, then maximise the worst margin)',
                      fontsize=10)
        axm.grid(axis='x', alpha=0.25)

        fig.savefig(f'{args.workdir}/f{i:04d}.png', facecolor='white')
        if (i + 1) % 40 == 0:
            print(f'  frame {i+1}/{n}', flush=True)

    # hold the final frame
    last = f'{args.workdir}/f{n-1:04d}.png'
    for k in range(int(round(args.hold * args.fps))):
        subprocess.run(['cp', last, f'{args.workdir}/f{n+k:04d}.png'], check=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(args.fps),
                    '-i', f'{args.workdir}/f%04d.png', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-crf', '20', args.out], check=True)
    dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'csv=p=0', args.out], capture_output=True, text=True).stdout.strip()
    print(f'wrote {args.out}  ({float(dur):.1f} s, {n} generations + {args.hold:.0f} s hold)')
    print(f"final: score {final['score']*100:+.2f} %  binding = "
          f"{min(((k, v) for k, v in final['marg'].items() if not k.endswith('_pk')), key=lambda kv: kv[1])[0]}")


if __name__ == '__main__':
    sys.exit(main())
