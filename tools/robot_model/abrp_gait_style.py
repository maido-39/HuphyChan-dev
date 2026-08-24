"""AB vs RP gait STYLE, against human normative data.

Cycle-normalised (0-100 %, heel strike to ipsilateral heel strike) joint kinematics and
vertical GRF from matched 1.2 m/s rollouts, next to the human bands in refs/human_gait
(4 datasets, 101-point cycles; Moissenet 2019 self-selected speed 1.157 m/s is the closest
match to the commanded speed here).

Robot ankle angles are plotted as a DEVIATION from their own mid-stance value: the model's
zero is the CAD neutral pose, the human curves are anchored to each subject's quiet standing,
so only the waveform shape is comparable, not the absolute offset.
  .venv/bin/python3 ../../tools/robot_model/abrp_gait_style.py <tag>
"""
import sys, json, glob
import numpy as np, mujoco
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

TAG = sys.argv[1] if len(sys.argv) > 1 else 'gait20k'
SRC = '/home/syaro/pyg_fea/work/apex_recheck'
REF = '/home/syaro/MikuchanRemote/Human-Pygmalion/refs/human_gait'
OUT = f'/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/abrp_gait_style_{TAG}.png'
BW, DT, N = 346.8, 0.02, 101
C = {'AB': '#f0961e', 'RP': '#2f9dff'}
JOINTS = ['ankle_pitch', 'knee', 'hip_pitch', 'hip_roll']


def cycles(mask):
    e = np.diff(mask.astype(int)); hs = np.where(e == 1)[0] + 1
    return [(hs[i], hs[i + 1]) for i in range(len(hs) - 1) if 15 < hs[i + 1] - hs[i] < 200]


def norm(sig, a, b):
    return np.interp(np.linspace(0, 100, N), np.linspace(0, 100, b - a), sig[a:b])


res, stats = {}, {}
for arm in ('AB', 'RP'):
    d = np.load(f'{SRC}/ankle{arm}_c3_{TAG}.npz')
    m = mujoco.MjModel.from_binary_path(f'{SRC}/ankle{arm}_c3_{TAG}_model.mjb')
    adr = {}
    for j in JOINTS:
        for s in 'LR':
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'robot/{s}_{j}_joint')
            if jid >= 0: adr[f'{s}_{j}'] = m.jnt_qposadr[jid]
    fid = {s: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f'robot/{s}_foot_link') for s in 'LR'}
    q = d['qpos_full']; n = len(q)
    md = mujoco.MjData(m); fp = {s: np.zeros((n, 3)) for s in 'LR'}
    for i in range(n):
        md.qpos[:] = q[i]; mujoco.mj_kinematics(m, md)
        for s in 'LR': fp[s][i] = md.xpos[fid[s]]
    on = {s: d[f'GRFc_{s}_foot_link_z'] > 0.05 * BW for s in 'LR'}
    spd = np.hypot(d['base_vx'], d['base_vy'])   # speed-matched cycle selection: a gait
    LO, HI = 1.05, 1.35                          # comparison across different speeds is void
    curves = {k: [] for k in ['grf'] + JOINTS}
    T, DUTY, SL, DS, WIDTH = [], [], [], [], []
    for s in 'LR':
        for a, b in cycles(on[s]):
            if a < 40 or not (LO <= spd[a:b].mean() <= HI): continue
            curves['grf'].append(norm(d[f'GRFc_{s}_foot_link_z'] / BW, a, b))
            for j in JOINTS:
                if f'{s}_{j}' in adr: curves[j].append(np.degrees(norm(q[:, adr[f'{s}_{j}']], a, b)))
            T.append((b - a) * DT); DUTY.append(on[s][a:b].mean())
            SL.append(float(np.linalg.norm(fp[s][b, :2] - fp[s][a, :2])))
            DS.append(float((on['L'][a:b] & on['R'][a:b]).mean()))
            WIDTH.append(float(np.abs(fp['L'][a:b, 1] - fp['R'][a:b, 1]).mean()))
    res[arm] = {k: np.array(v) for k, v in curves.items() if len(v)}
    bh = d['base_height']
    stats[arm] = dict(n_cycles=len(T), cycles_kept_frac=float(np.mean((spd > LO) & (spd < HI))), stride_time=np.mean(T), cadence=120 / np.mean(T),
                      duty=np.mean(DUTY), stride_len=np.mean(SL), double_support=np.mean(DS),
                      step_width=np.mean(WIDTH), base_h_mean=bh.mean(), base_h_pp=np.ptp(bh),
                      speed=float(np.mean(np.hypot(d['base_vx'], d['base_vy']))))

human = {}
for f in sorted(glob.glob(f'{REF}/*_ankle.csv')):
    name = f.split('/')[-1].replace('_ankle.csv', '')
    a = np.loadtxt(f, delimiter=',', skiprows=1)
    human[name] = (np.interp(np.linspace(0, 100, N), a[:, 0], a[:, 1]),
                   np.interp(np.linspace(0, 100, N), a[:, 0], a[:, 2]) if a.shape[1] > 2 else None)

x = np.linspace(0, 100, N)
fig, ax = plt.subplots(1, 4, figsize=(19, 4.6))
# ---- vertical GRF
for arm in ('AB', 'RP'):
    g = res[arm]['grf']; mu = g.mean(0)
    ax[0].plot(x, mu, color=C[arm], lw=2, label=f'{arm} (n={len(g)})')
    ax[0].fill_between(x, mu - g.std(0), mu + g.std(0), color=C[arm], alpha=.18, lw=0)
ax[0].axhline(1.0, color='0.5', lw=.8, ls=':')
ax[0].set_title('vertical GRF — human walking is M-shaped\n(two ~1.1 BW peaks, mid-stance valley ~0.7)', fontsize=10)
ax[0].set_xlabel('gait cycle [%]'); ax[0].set_ylabel('GRF [BW]'); ax[0].legend(fontsize=9); ax[0].grid(alpha=.25)
# ---- ankle, robot deviation vs human band
H = np.array([v[0] for v in human.values()])
ax[1].fill_between(x, H.min(0), H.max(0), color='0.6', alpha=.35, lw=0, label='human, 4 datasets')
ax[1].plot(x, H.mean(0), color='0.25', lw=1.6, ls='--', label='human mean')
for arm in ('AB', 'RP'):
    a = res[arm]['ankle_pitch']; mu = a.mean(0)
    mu = mu - mu[:60].mean() + H.mean(0)[:60].mean()      # align on stance mean
    ax[1].plot(x, mu, color=C[arm], lw=2, label=f'{arm} (stance-aligned)')
ax[1].set_title('ankle pitch — waveform vs human\n(dorsiflexion +, robot offset removed)', fontsize=10)
ax[1].set_xlabel('gait cycle [%]'); ax[1].set_ylabel('angle [deg]'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.25)
# ---- knee & hip
for j, k in enumerate(('knee', 'hip_pitch')):
    for arm in ('AB', 'RP'):
        if k not in res[arm]: continue
        a = res[arm][k]; mu = a.mean(0)
        ax[2 + j].plot(x, mu, color=C[arm], lw=2, label=arm)
        ax[2 + j].fill_between(x, mu - a.std(0), mu + a.std(0), color=C[arm], alpha=.18, lw=0)
    ax[2 + j].set_title(f'{k} — cycle trajectory', fontsize=10)
    ax[2 + j].set_xlabel('gait cycle [%]'); ax[2 + j].set_ylabel('angle [deg]')
    ax[2 + j].legend(fontsize=9); ax[2 + j].grid(alpha=.25)
fig.suptitle(f'AB vs RP gait style, cycles matched to 1.05-1.35 m/s (model_20000, 1.2 command) — human band from refs/human_gait', fontsize=13)
fig.tight_layout(); fig.savefig(OUT, dpi=120, bbox_inches='tight')
json.dump(stats, open(f'/home/syaro/pyg_fea/work/abrp_gait_style_{TAG}.json', 'w'), indent=1, default=float)
print('wrote', OUT)
for a, s in stats.items():
    print(a, {k: round(v, 3) for k, v in s.items()})
