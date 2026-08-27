"""Read the AB rollouts and answer the two questions the load study is waiting on.

(A) Does the AB policy walk in PhysX, and does its GRF match MuJoCo the way RP's did?
(B) Does dropping the solver position iteration count from the importer's 32 to the GRF-optimal
    4 corrupt JOINT torques? The contact sweep only ever looked at the force under the sole, and
    said so; the load study wants knee and hip torque, which is a different quantity resolved by
    a different part of the solver.

The comparison is between whole runs, not between paired samples: changing the iteration count
changes the trajectory, so a per-timestep diff is meaningless. What IS comparable is the
distribution of each joint's torque over a long stationary window - RMS (the thermal number),
P99 (the instantaneous design number) and max. If those move less than the run-to-run spread of
the gait itself, the iteration count is not a load-study variable.

  python3 tools/sim2sim/ab_iteration_report.py
"""
import json
import os

import numpy as np

WORK = '/home/syaro/pyg_fea/work/ab_rollout'
OUT = f'{WORK}/ab_iteration_verdict.json'
IMG = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/xengine_ab_iterations.png'
RUNS = [('i4x8', '4/8  (GRF-optimal)'), ('i8x4', '8/4  (tracking-optimal)'),
        ('i32x16', '32/16 (high-iteration reference)')]
LEGS = ['L_hip_pitch_joint', 'L_hip_roll_joint', 'L_hip_yaw_joint', 'L_knee_joint',
        'L_crank_A_joint', 'L_crank_B_joint', 'L_ankle_pitch_joint', 'L_ankle_roll_joint',
        'R_hip_pitch_joint', 'R_hip_roll_joint', 'R_hip_yaw_joint', 'R_knee_joint',
        'R_crank_A_joint', 'R_crank_B_joint', 'R_ankle_pitch_joint', 'R_ankle_roll_joint']

D = {}
for tag, _ in RUNS:
    f = f'{WORK}/isaac_ab_{tag}.json'
    if os.path.exists(f):
        d = json.load(open(f))
        if d.get('ok'):
            D[tag] = d
if not D:
    raise SystemExit('no successful AB rollout found in ' + WORK)

ref = D.get('i4x8') or next(iter(D.values()))
out = {'runs': {t: dict(iters=D[t]['knobs']['runtime_solver_iters'],
                        seconds=D[t]['sim_seconds'], fell=D[t]['fell'],
                        vx_mean=round(D[t]['vx_mean'], 4), vx_err=round(D[t]['vx_err'], 4),
                        support_BW=D[t]['support_check']['mean_total_Fz_BW'],
                        peak=D[t]['isaac'].get('peak_BW_med'),
                        rate=D[t]['isaac'].get('rate_BWs_med'),
                        drift_max_mm=D[t]['loop_drift_mm']['all_max'])
                 for t in D}}

print('=' * 96)
print('(A) AB policy: IsaacSim vs MuJoCo  -  bundleD1_AB, 1.6 m/s, no DR, v3 loop model')
print('=' * 96)
print(f"model {ref['usd']}")
print(f"mass  Isaac {ref['total_mass_kg']} kg  vs mjlab {ref['mjlab_mass_kg']} kg "
      f"(delta {ref['mass_delta_g']} g = the 4 dummy rod-U links URDF needs)")
for tag, label in RUNS:
    if tag not in D:
        continue
    d = D[tag]
    print(f"\n-- iterations {d['knobs']['runtime_solver_iters'][0]}/"
          f"{d['knobs']['runtime_solver_iters'][1]}  ({label})")
    print(f"{'metric':24s} {'unit':8s} {'Isaac':>10s} {'MuJoCo':>10s} {'ratio':>7s} {'%diff':>8s}")
    for r in d.get('comparison', []):
        print(f"{r['metric']:24s} {r['unit']:8s} {str(r['isaac']):>10s} {str(r['mujoco']):>10s} "
              f"{str(r['ratio']):>7s} {str(r['pct_diff']):>8s}")
    print(f"{'vx_err':24s} {'m/s':8s} {d['vx_err']:>10.4f} "
          f"{'-':>10s} {'-':>7s} {'-':>8s}   (mean vx {d['vx_mean']:.3f}, fell={d['fell']})")
out['comparison_4x8'] = ref.get('comparison')

# ---- (B) joint torque vs iteration count ----------------------------------------------------
print()
print('=' * 96)
print('(B) JOINT TORQUE vs SOLVER ITERATIONS  -  measured joint efforts, N*m, warm-up cut')
print('=' * 96)
base = 'i32x16' if 'i32x16' in D else list(D)[0]
tab = {}
worst = {'rms': ('', 0.0), 'p99': ('', 0.0)}
hdr = f"{'joint':24s}"
for tag, _ in RUNS:
    if tag in D:
        hdr += f"{tag:>12s}"
hdr += f"{'d%RMS':>9s}{'d%P99':>9s}"
print(hdr + f'   (vs {base})')
main = 'i4x8' if 'i4x8' in D else [t for t in D if t != base][0] if len(D) > 1 else base
for stat in ('rms', 'p99'):
    print(f'-- {stat.upper()}   (last column: {main} vs {base})')
    for jn in LEGS:
        row, line = {}, f'{jn:24s}'
        for tag, _ in RUNS:
            if tag not in D:
                continue
            v = D[tag]['torque_measured'].get(jn, {}).get(stat)
            row[tag] = v
            line += f'{v:>12.3f}' if v is not None else f"{'-':>12s}"
        if row.get(base):
            for tag, v in row.items():
                if tag == base or v is None:
                    continue
                dpct = 100 * (v / row[base] - 1)
                tab.setdefault(jn, {}).setdefault(tag, {})[stat] = round(dpct, 2)
                if abs(dpct) > abs(worst[stat][1]):
                    worst[stat] = (f'{jn} {tag}', dpct)
            if row.get(main):
                line += f'{100 * (row[main] / row[base] - 1):>9.1f} %'
        print(line)
out['torque_pct_change_vs_' + base] = tab
out['worst_shift'] = {k: dict(where=v[0], pct=round(v[1], 2)) for k, v in worst.items()}

GATE = 5.0
big = {jn: v for jn, v in tab.items()
       if any(abs(s.get('rms', 0)) > GATE or abs(s.get('p99', 0)) > GATE for s in v.values())}
out['gate_pct'] = GATE
out['joints_over_gate'] = sorted(big)
print()
print(f'>> joints whose RMS or P99 moves more than {GATE}% between iteration settings: '
      f'{len(big)} of {len(LEGS)}')
for jn in sorted(big):
    print('   ', jn, big[jn])
print(f">> worst RMS shift {out['worst_shift']['rms']['pct']}% at {out['worst_shift']['rms']['where']}")
print(f">> worst P99 shift {out['worst_shift']['p99']['pct']}% at {out['worst_shift']['p99']['where']}")

# ---- applied vs measured: the solver's own residual ------------------------------------------
print()
print('-- applied vs measured effort on the 12 MOTORS (|measured|-|applied|)/|applied| RMS, %')
res_row = {}
for tag, _ in RUNS:
    if tag not in D:
        continue
    d = D[tag]
    vals = []
    for jn in LEGS:
        if 'ankle' in jn:
            continue
        a = d['torque_applied'].get(jn, {}).get('rms')
        m = d['torque_measured'].get(jn, {}).get('rms')
        if a and m:
            vals.append(100 * (m / a - 1))
    res_row[tag] = dict(mean=round(float(np.mean(vals)), 3), max=round(float(np.max(np.abs(vals))), 3))
    print(f'   {tag:8s} mean {res_row[tag]["mean"]:+7.3f} %   max |.| {res_row[tag]["max"]:6.3f} %')
out['applied_vs_measured_pct'] = res_row

# ---- loop drift ------------------------------------------------------------------------------
print()
print('-- LOOP DRIFT under dynamic load (mm; static reference 0.0003 mm)')
print(f"{'run':10s}{'mean':>12s}{'p99':>12s}{'max':>12s}{'landing max':>14s}{'spawn max':>12s}")
MJD = f'{WORK}/mujoco_ab_loop_drift.json'
if os.path.exists(MJD):
    mjd = json.load(open(MJD))
    L = mjd['loop_drift_mm']
    print(f"{'MuJoCo':10s}{L['all_mean']:>12.5f}{L['all_p99']:>12.5f}{L['all_max']:>12.5f}"
          f"{'-':>14s}{'-':>12s}   <- the reference: MuJoCo's own connect is soft too")
    out['mujoco_loop_drift'] = L
    out['mujoco_walk'] = {k: mjd[k] for k in ('vx_mean', 'vx_err', 'fell', 'seconds',
                                              'solref', 'solimp', 'solver_iterations')}
for tag, _ in RUNS:
    if tag not in D:
        continue
    L = D[tag]['loop_drift_mm']
    sp = max(D[tag]['loop_drift_at_spawn_mm'].values())
    print(f"{tag:10s}{L['all_mean']:>12.5f}{L['all_p99']:>12.5f}{L['all_max']:>12.5f}"
          f"{L['landing_window_max']:>14.5f}{sp:>12.5f}")
out['loop_drift'] = {t: dict(D[t]['loop_drift_mm'],
                             spawn_max=max(D[t]['loop_drift_at_spawn_mm'].values()))
                     for t in D}

json.dump(out, open(OUT, 'w'), indent=1)
print('\nwrote', OUT)

# ---- figure -----------------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    tags = [t for t, _ in RUNS if t in D]
    lab = {t: f"{D[t]['knobs']['runtime_solver_iters'][0]}/{D[t]['knobs']['runtime_solver_iters'][1]}"
           for t in tags}
    col = {'i4x8': '#3b6ea5', 'i8x4': '#c0603a', 'i32x16': '#2a7f2a'}
    fig, ax = plt.subplots(1, 4, figsize=(19, 4.3))

    # (a) GRF: Isaac at each iteration setting vs the MuJoCo reference
    mj_peak = ref['mujoco']['peak_BW_med']
    mj_rate = ref['mujoco']['rate_BWs_med']
    x = np.arange(len(tags))
    ax[0].bar(x - 0.18, [D[t]['isaac']['peak_BW_med'] / mj_peak for t in tags], 0.34,
              label='peak landing force', color='#3b6ea5')
    ax[0].bar(x + 0.18, [D[t]['isaac']['rate_BWs_med'] / mj_rate for t in tags], 0.34,
              label='loading rate', color='#c0603a')
    for k, t in enumerate(tags):
        ax[0].text(k - 0.18, D[t]['isaac']['peak_BW_med'] / mj_peak + 0.12,
                   f"{D[t]['isaac']['peak_BW_med'] / mj_peak:.2f}", ha='center', fontsize=8)
        ax[0].text(k + 0.18, D[t]['isaac']['rate_BWs_med'] / mj_rate + 0.12,
                   f"{D[t]['isaac']['rate_BWs_med'] / mj_rate:.1f}", ha='center', fontsize=8)
    ax[0].axhline(1.0, color='k', lw=1, ls='--')
    ax[0].set_xticks(x); ax[0].set_xticklabels([lab[t] for t in tags])
    ax[0].set_xlabel('solver iterations  position/velocity')
    ax[0].set_ylabel('IsaacSim / MuJoCo')
    ax[0].set_title('(a) AB landing force vs MuJoCo\nno setting reproduces the soft landing')
    ax[0].legend(fontsize=8)

    # (b) ACTUATED joint torque P99, relative to the high-iteration reference
    act12 = [j for j in LEGS if 'ankle' not in j]
    w = 0.8 / max(1, len(tags))
    for i_, t in enumerate(tags):
        v = [D[t]['torque_measured'][j]['p99'] / D[base]['torque_measured'][j]['p99'] for j in act12]
        ax[1].bar(np.arange(len(act12)) + i_ * w - 0.4 + w / 2, v, w, label=lab[t], color=col.get(t))
    ax[1].axhspan(0.95, 1.05, color='0.85', zorder=0)
    ax[1].axhline(1.0, color='k', lw=1, ls='--')
    ax[1].set_xticks(np.arange(len(act12)))
    ax[1].set_xticklabels([j.replace('_joint', '').replace('hip_', 'hip ') for j in act12],
                          rotation=55, ha='right', fontsize=7)
    ax[1].set_ylabel(f'P99 torque / {lab[base]}')
    ax[1].set_title('(b) the 12 MOTORS\ngrey band = +/-5%, the load-study gate')
    ax[1].legend(fontsize=8, title='iterations', title_fontsize=8)

    # (c) the PASSIVE ankle hinges: a joint with no motor must read ~0 N*m
    pas = [j for j in LEGS if 'ankle' in j]
    for i_, t in enumerate(tags):
        v = [D[t]['torque_measured'][j]['p99'] for j in pas]
        ax[2].bar(np.arange(len(pas)) + i_ * w - 0.4 + w / 2, v, w, label=lab[t], color=col.get(t))
    ax[2].set_xticks(np.arange(len(pas)))
    ax[2].set_xticklabels([j.replace('_joint', '') for j in pas], rotation=55, ha='right', fontsize=7)
    ax[2].set_ylabel('P99 |effort| [N m]   (truth = 0)')
    ax[2].set_title('(c) UNACTUATED ankle hinges\nwhatever is here is solver error')
    ax[2].legend(fontsize=8, title='iterations', title_fontsize=8)

    # (d) loop drift distribution, log axis - drift is non-negative
    lo = 1e-4
    bins = np.logspace(np.log10(lo), np.log10(20.0), 100)
    for t in tags:
        z = np.load(f'{WORK}/isaac_ab_{t}_traces.npz')
        dr = z['loop_drift_mm'][int(3.0 / float(z['dt'])):].ravel()
        ax[3].hist(np.clip(dr, lo, None), bins=bins, histtype='step', log=True,
                   color=col.get(t), label=f'{lab[t]}   max {dr.max():.3f} mm')
    if 'mujoco_loop_drift' in out:
        ax[3].axvline(out['mujoco_loop_drift']['all_max'], color='k', lw=1.6,
                      label=f"MuJoCo max {out['mujoco_loop_drift']['all_max']:.3f} mm")
    ax[3].axvline(0.0003, color='k', ls=':', lw=1.2, label='static hold 0.0003 mm')
    ax[3].set_xscale('log')
    ax[3].set_xlabel('rod-end gap [mm]')
    ax[3].set_ylabel('substeps')
    ax[3].set_title('(d) how far the closed loop pulls apart\nwhile walking')
    ax[3].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(IMG, dpi=130)
    print('wrote', IMG)
except Exception as e:
    import traceback
    print('plot skipped:', type(e).__name__, e)
    traceback.print_exc()
