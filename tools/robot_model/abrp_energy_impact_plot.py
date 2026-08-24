"""AB vs RP: the two questions that matter — energy and impact (docs/101 §5).

Energy: electrical cost of transport from the matched random-command rollouts
(P = max(0, tau*omega)/eta_drive + 1.5 I^2 R, docs/21 constants), binned by achieved speed.
Impact: the four 200 Hz gate probes, paired.
"""
import json, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

KT = {'RS04': 2.1, 'RS03': 2.36}; RPH = {'RS04': 0.16, 'RS03': 0.39}
G, ETA_G, ETA_D = 9.0, 0.9, 0.80
FAM = {'hip_pitch': 'RS04', 'hip_roll': 'RS04', 'hip_yaw': 'RS03', 'knee': 'RS04',
       'crank_A': 'RS03', 'crank_B': 'RS03', 'ankle_pitch': 'RS03', 'ankle_roll': 'RS03'}
RATIO = {'ankle_pitch': 32.7 / 20.0, 'ankle_roll': 27.9 / 20.0}
M, GR, DT, DW = 35.348, 9.81, 0.02, 275
C = {'AB': '#f0961e', 'RP': '#2f9dff'}
OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/abrp_energy_impact.png'

win = {}
for a in ('AB', 'RP'):
    d = np.load(f'/home/syaro/pyg_fea/work/track_decomp/ankle{a}_c3_dec9500.npz')
    n = len(d['base_vx']); Pm = np.zeros(n); Pc = np.zeros(n)
    for k in d.files:
        if not k.startswith('tau_') or 'rod' in k: continue
        j = k[4:]; b = next((r for r in FAM if r in j), None)
        if b is None: continue
        Pm += np.clip(d[k] * d['omega_' + j], 0, None)
        I = np.abs(d[k] / RATIO.get(b, 1.0)) / (KT[FAM[b]] * G * ETA_G)
        Pc += 1.5 * I ** 2 * RPH[FAM[b]]
    P = Pm / ETA_D + Pc
    sp = np.hypot(d['base_vx'], d['base_vy'])
    rows = []
    for w in range(24):
        sl = slice(w * DW + 100, (w + 1) * DW)
        dist = sp[sl].sum() * DT
        if dist < 0.5: continue
        rows.append((sp[sl].mean(), P[sl].sum() * DT / (M * GR * dist), P[sl].mean()))
    win[a] = np.array(rows)

GATES = [4000, 8000, 12000, 16000]
V = {'AB': [0.90, 0.93, 0.97, 1.37], 'RP': [1.14, 0.85, 1.08, 0.97]}
PK = {'AB': [1.00, 1.23, 1.16, 1.23], 'RP': [1.22, 1.03, 1.02, 1.20]}
LR = {'AB': [112, 104, 88, 72], 'RP': [137, 86, 53, 102]}
UTIL = {'AB': [('knee', .43), ('crank_A', .38), ('crank_B', .35)],
        'RP': [('ankle_pitch L', .83), ('ankle_pitch R', .82), ('knee', .40)]}

fig, ax = plt.subplots(1, 4, figsize=(19, 4.4))
for a in ('AB', 'RP'):
    ax[0].scatter(win[a][:, 0], win[a][:, 1], color=C[a], s=34, alpha=.8, label=a)
    o = np.argsort(win[a][:, 0])
    k = np.convolve(win[a][o, 1], np.ones(5) / 5, 'valid')
    ax[0].plot(win[a][o, 0][2:-2], k, color=C[a], lw=2)
ax[0].set_xlabel('achieved speed [m/s]'); ax[0].set_ylabel('cost of transport  E / (m g d)')
ax[0].set_title('ENERGY: RP is cheaper, and more so with speed', fontsize=11)
ax[0].legend(fontsize=9); ax[0].grid(alpha=.25)

for a in ('AB', 'RP'):
    ax[1].scatter(win[a][:, 0], win[a][:, 2], color=C[a], s=34, alpha=.8, label=a)
ax[1].set_xlabel('achieved speed [m/s]'); ax[1].set_ylabel('electrical power [W]')
ax[1].set_title('same, in watts', fontsize=11); ax[1].legend(fontsize=9); ax[1].grid(alpha=.25)

x = np.arange(len(GATES))
for j, a in enumerate(('AB', 'RP')):
    ax[2].bar(x + (j - .5) * .38, PK[a], .38, color=C[a], label=f'{a} peak GRF')
    ax[2].plot(x + (j - .5) * .38, V[a], 'o--', color='k', ms=5, mfc=C[a], lw=1)
ax[2].set_xticks(x); ax[2].set_xticklabels([f'{g//1000}k' for g in GATES])
ax[2].set_xlabel('gate iteration'); ax[2].set_ylabel('peak GRF [BW]   /   touchdown [m/s] (dots)')
ax[2].set_title('IMPACT: rank flips every gate = tie', fontsize=11); ax[2].legend(fontsize=9); ax[2].grid(alpha=.25, axis='y')

lbl = [f'{a}\n{n}' for a in ('AB', 'RP') for n, _ in UTIL[a]]
val = [v for a in ('AB', 'RP') for _, v in UTIL[a]]
col = [C['AB']] * 3 + [C['RP']] * 3
ax[3].bar(range(6), val, color=col)
ax[3].axhline(1.0, color='#c0392b', ls='--', lw=1.3); ax[3].text(0.1, 1.02, 'motor T-N limit', color='#c0392b', fontsize=9)
ax[3].set_xticks(range(6)); ax[3].set_xticklabels(lbl, fontsize=8)
ax[3].set_ylim(0, 1.15); ax[3].set_ylabel('torque p95 / T-N limit')
ax[3].set_title('MARGIN: AB ankle has 2.2x more headroom', fontsize=11); ax[3].grid(alpha=.25, axis='y')

fig.suptitle('AB (closed-loop 2-RSU ankle) vs RP (serial ankle) — energy, impact, motor margin', fontsize=13)
fig.tight_layout(); fig.savefig(OUT, dpi=120, bbox_inches='tight'); print('wrote', OUT)
