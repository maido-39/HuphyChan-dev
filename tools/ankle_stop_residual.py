"""What the ankle hard stop actually absorbs: the constraint moment the motor did NOT make.

docs/64 §8e (2026-07-24) sized the RP gimbal stop on a "stop residual moment"

    M_stop = M_constraint - tau_motor

and reported ankle pitch P99 213 / raw peak 1056 N.m, roll P99 135 / peak 554. Those numbers
are the reason the hard stop was moved off the cross-pin onto a foot-to-shin pad. But they
were measured on 2026-07-24, ten days BEFORE docs/64 §8i found that every recorded link
wrench moment is taken about the robot CoM rather than about the joint. The neighbouring
sections (§8c, §8d, §8f) all carry a "this is an over-estimate" warning; §8e never got one.

So this recomputes M_stop with the §8i transport applied,

    M_joint = M_com + (p_com - p_joint) x F      (force is reference-point independent)

and reports the corrected and uncorrected numbers side by side, over both the rollout that
docs/64 §8e used and the modern fcp demand pool. Sign convention is not assumed: the axial
constraint moment is correlated against the motor torque and the residual is formed with
whichever sign makes them agree, which is also the self-check (a joint that is NOT on its
limit must have residual ~ 0 and correlation ~ +1).

Usage: ankle_stop_residual.py [--npz=a.npz,b.npz] [--out=docs/img]
"""
import glob
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = '/home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab/analysis/out'
sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab/src')
import mujoco  # noqa: E402

JOINTS = {'ankle_pitch': 'ankle_pitch_link', 'ankle_roll': 'foot_link'}
# the ROM the MECHANISM is designed for (docs/76 §11) - the sim model is looser on pitch
DESIGN_ROM = {'ankle_pitch': (-50.0, 30.0), 'ankle_roll': (-20.0, 20.0)}
# docs/64 §8e, the numbers this recomputation is testing [N.m]
S8E = {'ankle_pitch': dict(rms=52, p99=213, peak=1056),
       'ankle_roll': dict(rms=36, p99=135, peak=554)}


def stat(a):
    return dict(rms=float(np.sqrt((a ** 2).mean())),
                p99=float(np.percentile(np.abs(a), 99)),
                peak=float(np.abs(a).max()))


def analyse(npz):
    """Corrected and uncorrected stop-residual statistics for one rollout."""
    mjb = npz.replace('.npz', '_model.mjb')
    d = np.load(npz, allow_pickle=True)
    m = mujoco.MjModel.from_binary_path(mjb)
    dat = mujoco.MjData(m)
    Q = np.asarray(d['qpos_full'])
    n = len(Q)
    # full rate: a peak is a single frame and does not survive decimation
    # (that is exactly the bug that made recompute_moments.py report subsample peaks)
    idx = np.arange(n)

    res = {}
    for joint, link in JOINTS.items():
        for side in ('L', 'R'):
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'robot/{side}_{joint}_joint')
            if jid < 0:
                continue
            keys = [f'{c}_{side}_{link}' for c in ('Fx', 'Fy', 'Fz', 'Tx', 'Ty', 'Tz')]
            tk = f'tau_{side}_{joint}_joint'
            if not all(k in d for k in keys) or tk not in d:
                continue
            anch = np.zeros((idx.size, 3))
            axis = np.zeros((idx.size, 3))
            com = np.zeros((idx.size, 3))
            for t, i in enumerate(idx):
                dat.qpos[:] = (Q[i][:m.nq] if Q.shape[1] >= m.nq
                               else np.pad(Q[i], (0, m.nq - Q.shape[1])))
                mujoco.mj_kinematics(m, dat)
                mujoco.mj_comPos(m, dat)
                com[t] = dat.subtree_com[0]
                anch[t] = dat.xanchor[jid]
                axis[t] = dat.xaxis[jid]
            F = np.stack([np.asarray(d[f'{c}_{side}_{link}'])[idx] for c in ('Fx', 'Fy', 'Fz')], 1)
            M = np.stack([np.asarray(d[f'{c}_{side}_{link}'])[idx] for c in ('Tx', 'Ty', 'Tz')], 1)
            ax = axis / np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-9)
            M_new = M + np.cross(com - anch, F)                 # §8i transport
            a_new = np.einsum('ij,ij->i', M_new, ax)
            a_old = np.einsum('ij,ij->i', M, ax)
            tau = np.asarray(d[tk])[idx]
            # is the joint actually ON its limit? the stop only carries load when it is
            lo, hi = m.jnt_range[jid]
            q = np.asarray(d[f'qpos_{side}_{joint}_joint'])[idx] if \
                f'qpos_{side}_{joint}_joint' in d else None
            near = None
            if q is not None and m.jnt_limited[jid]:
                near = (q <= lo + np.radians(3.0)) | (q >= hi - np.radians(3.0))
            # the DESIGN cap is tighter than the sim cap on pitch (+30 vs +40), so the sim
            # understates how much a real stop would be loaded. Measure that gap directly.
            dlo, dhi = DESIGN_ROM[joint]
            over = (float(((q < np.radians(dlo)) | (q > np.radians(dhi))).mean())
                    if q is not None else None)
            # do not assume the sign convention - pick the one the data supports
            s = 1.0 if np.corrcoef(a_new, tau)[0, 1] >= 0 else -1.0
            res[f'{side}_{joint}'] = dict(
                joint=joint, side=side,
                corr=float(np.corrcoef(s * a_new, tau)[0, 1]),
                corr_old=float(np.corrcoef(s * a_old, tau)[0, 1]),
                axis_new=stat(a_new), axis_old=stat(a_old),
                stop_new=stat(s * a_new - tau), stop_old=stat(s * a_old - tau),
                rom=[float(np.degrees(lo)), float(np.degrees(hi))],
                limited=bool(m.jnt_limited[jid]),
                q_range=[float(np.degrees(q.min())), float(np.degrees(q.max()))]
                if q is not None else None,
                on_limit_frac=float(near.mean()) if near is not None else None,
                design_over_frac=over, design_rom=[dlo, dhi],
                stop_on_limit=stat((s * a_new - tau)[near]) if near is not None and near.any()
                else None,
                tau=stat(tau))
    return res


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               os.path.join(HERE, '..', 'docs', 'img'))
    arg = next((a.split('=')[1] for a in sys.argv if a.startswith('--npz=')), None)
    if arg:
        files = [f if os.path.isabs(f) else os.path.join(OUTDIR, f) for f in arg.split(',')]
    else:
        # current-regime measurements only (the *_fc / *_fcp 15 s-dwell + PYG_BOX rule);
        # rough.npz is kept as the tie to docs/64 §8e, which was measured on it
        files = ([os.path.join(OUTDIR, 'rough.npz')] +
                 sorted(glob.glob(f'{OUTDIR}/*_fc.npz')) +
                 sorted(glob.glob(f'{OUTDIR}/*_fcp.npz')))
    files = [f for f in files if os.path.exists(f) and
             os.path.exists(f.replace('.npz', '_model.mjb'))]

    per_file = {}
    for f in files:
        name = os.path.basename(f)[:-4]
        try:
            per_file[name] = analyse(f)
            print(f'{name}: {len(per_file[name])} joint/side channels', flush=True)
        except Exception as e:                                   # noqa: BLE001
            print(f'{name}: SKIPPED ({type(e).__name__}: {e})', flush=True)

    print(f"\n{'rollout':16s} {'joint':12s} {'corr':>6s} {'M_axis P99':>11s} "
          f"{'(was)':>8s} {'M_stop P99':>11s} {'(was)':>8s} {'M_stop peak':>12s} {'(was)':>9s}")
    env = {}
    for name, r in per_file.items():
        for key, v in sorted(r.items()):
            print(f"{name:16s} {key:12s} {v['corr']:6.3f} {v['axis_new']['p99']:11.1f} "
                  f"{v['axis_old']['p99']:8.1f} {v['stop_new']['p99']:11.1f} "
                  f"{v['stop_old']['p99']:8.1f} {v['stop_new']['peak']:12.1f} "
                  f"{v['stop_old']['peak']:9.1f}")
            e = env.setdefault(v['joint'], dict(p99=0.0, peak=0.0, p99_old=0.0, peak_old=0.0,
                                                rms=0.0, at='', corr=1.0))
            for k, src in (('p99', 'stop_new'), ('peak', 'stop_new'), ('rms', 'stop_new')):
                if v[src][k] > e[k]:
                    e[k] = v[src][k]
                    if k == 'peak':
                        e['at'] = f'{name}/{key}'
            e['p99_old'] = max(e['p99_old'], v['stop_old']['p99'])
            e['peak_old'] = max(e['peak_old'], v['stop_old']['peak'])
            e['corr'] = min(e['corr'], v['corr'])
            g = v['stop_on_limit']
            if g:
                if g['p99'] > e.setdefault('lim_p99', 0.0):
                    e['lim_p99'], e['lim_p99_at'] = g['p99'], f'{name}/{key}'
                if g['peak'] > e.setdefault('lim_peak', 0.0):
                    e['lim_peak'], e['lim_peak_at'] = g['peak'], f'{name}/{key}'
            e['occ'] = max(e.setdefault('occ', 0.0), v['on_limit_frac'] or 0.0)

    print('\nENVELOPE over all rollouts, corrected (§8i) vs as docs/64 §8e recorded it')
    print(f"{'joint':14s} {'RMS':>7s} {'P99':>7s} {'design':>8s} {'peak':>9s}   "
          f"{'§8e P99':>8s} {'§8e peak':>9s}   {'P99 x':>6s} {'peak x':>7s}")
    for j, e in env.items():
        s = S8E[j]
        print(f"{j:14s} {e['rms']:7.1f} {e['p99']:7.1f} {e['p99']*1.25:8.1f} {e['peak']:9.1f}   "
              f"{s['p99']:8.0f} {s['peak']:9.0f}   {e['p99']/s['p99']:6.2f} "
              f"{e['peak']/s['peak']:7.2f}")
        print(f"{'':14s} worst peak at {e['at']}, min corr(M_axis, tau) = {e['corr']:.3f}")
        print(f"{'':14s} ON-LIMIT ONLY (the design basis): P99 {e['lim_p99']:.1f} "
              f"({e['lim_p99_at']}) · peak {e['lim_peak']:.1f} ({e['lim_peak_at']}) · "
              f"worst occupancy {100*e['occ']:.1f} % of frames")

    # figure: what the reference-point correction does to the stop residual
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.3))
    js = list(env)
    x = np.arange(len(js))
    for k, (lab, col, key) in enumerate((('docs/64 §8e (about the CoM)', '#c0392b', 'old'),
                                         ('corrected (§8i, about the joint)', '#2e86c1', 'new'))):
        axes[0].bar(x + (k - 0.5) * 0.36, [env[j][f'p99{"_old" if key == "old" else ""}']
                                           for j in js], 0.34, color=col, label=lab)
        axes[1].bar(x + (k - 0.5) * 0.36, [env[j][f'peak{"_old" if key == "old" else ""}']
                                           for j in js], 0.34, color=col, label=lab)
    for ax, ttl, ref in ((axes[0], 'stop residual, P99 [N$\\cdot$m]', 'p99'),
                         (axes[1], 'stop residual, raw peak [N$\\cdot$m]', 'peak')):
        for i, j in enumerate(js):
            ax.plot([i - 0.45, i + 0.45], [S8E[j][ref]] * 2, 'k--', lw=1.2)
            ax.text(i + 0.46, S8E[j][ref], f' §8e {S8E[j][ref]}', fontsize=7.5, va='center')
            ax.text(i + 0.18, env[j][ref] * 1.04,
                    f"{env[j][ref]:.0f}  ({100*env[j][ref]/S8E[j][ref]:.0f}%)",
                    fontsize=7.5, ha='center', color='#2e86c1', fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(js)
        ax.set_title(ttl)
        ax.grid(alpha=0.3, axis='y')
        ax.legend(fontsize=7.5)
    w = 0.34
    axes[2].bar(x - w / 2, [env[j]['lim_p99'] for j in js], w, color='#e67e22',
                label='on-limit P99 (duty)')
    axes[2].bar(x + w / 2, [env[j]['lim_peak'] for j in js], w, color='#7d3c98',
                label='on-limit peak (design)')
    for i, j in enumerate(js):
        axes[2].text(i - w / 2, env[j]['lim_p99'] * 1.03, f"{env[j]['lim_p99']:.0f}",
                     ha='center', fontsize=8, fontweight='bold')
        axes[2].text(i + w / 2, env[j]['lim_peak'] * 1.03, f"{env[j]['lim_peak']:.0f}",
                     ha='center', fontsize=8, fontweight='bold')
        axes[2].text(i, -0.10 * max(env[jj]['lim_peak'] for jj in js),
                     f"cap contact {100*env[j]['occ']:.1f} % of frames", ha='center',
                     fontsize=7.5, color='#555')
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(js)
    axes[2].set_title('THE DESIGN BASIS: frames on the cap only [N$\\cdot$m]')
    axes[2].grid(alpha=0.3, axis='y')
    axes[2].legend(fontsize=7.5)
    fig.suptitle('Ankle hard-stop load: docs/64 §8e carries the §8i moment reference-point '
                 'bug, and the stop is an EVERYDAY load, not an abuse case', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'ankle_stop_residual.png'))
    print('\nIs the stop ever actually touched? (sim ROM, joint travel, time on the limit)')
    for name, r in per_file.items():
        for key, v in sorted(r.items()):
            g = v['stop_on_limit']
            print(f"  {name:16s} {key:12s} sim ROM {v['rom'][0]:+6.1f}..{v['rom'][1]:+6.1f} "
                  f"limited={v['limited']}  travel {v['q_range'][0]:+6.1f}..{v['q_range'][1]:+6.1f}"
                  f"  on-limit {100*(v['on_limit_frac'] or 0):5.2f} %"
                  + (f"  -> M_stop|limit P99 {g['p99']:6.1f} peak {g['peak']:7.1f}" if g else ''))
    print('\nDESIGN cap vs SIM cap - how much of the walk is outside the DESIGNED ROM')
    for j in js:
        vals = [(f'{n}/{k}', v['design_over_frac']) for n, r in per_file.items()
                for k, v in r.items() if v['joint'] == j and v['design_over_frac'] is not None]
        vals.sort(key=lambda x: -x[1])
        med = float(np.median([v for _, v in vals]))
        print(f"  {j:12s} design ROM {DESIGN_ROM[j]}  outside it: "
              f"worst {100*vals[0][1]:5.1f} % ({vals[0][0]}) · median {100*med:5.2f} % · "
              f"n={len(vals)} channels")
        for name, v in vals[:4]:
            print(f"      {name:28s} {100*v:5.1f} %")
    print('\n-> docs/img/ankle_stop_residual.png')


if __name__ == '__main__':
    main()
