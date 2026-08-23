"""Constraint-stiffness sensitivity of a TRAINED AB policy (controlled: same checkpoint, same
commands, only the connect equality solimp/solref differ via PYG_LOOP_SOLIMP / PYG_LOOP_SOLREF).

Metrics per setting (docs/94): crank torque p99 / max, torque step |d tau| p99 (spikiness),
crank torque power fraction above 5 Hz, closure error RMS / p99 / max, rod axial force p99,
contact-only GRF p99, tracking error, falls, and the ankle-equivalent torque RMS.

  for S in "0.9 0.95 0.001" "0.95 0.99 0.001" "0.99 0.999 0.001" "0.999 0.9999 0.0001"; do
    PYG_LOOP_SOLIMP="$S" PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_ANKLE_MODE=AB CUDA_VISIBLE_DEVICES="" \
      .venv/bin/python3 ../../tools/robot_model/loop_tests/solimp_policy_sweep.py <run_dir> <ckpt> <tag>
  done
Run ONE at a time (each ~2.5 GB RAM next to the two trainers).
"""
import os, sys
import numpy as np

D, CK, TAG = sys.argv[1:4]
OUT = '/home/syaro/pyg_fea/work/solimp_sweep'
os.makedirs(OUT, exist_ok=True)
sys.argv = ['measure_loads.py', '--run-dir', D, '--checkpoint', CK, '--tag', TAG, '--device', 'cpu',
            '--steps-per-cmd', '400', '--warmup', '100', '--out-dir', OUT]
sys.path.insert(0, 'analysis')
import measure_loads  # noqa: E402

measure_loads.COMMAND_SCHEDULE = [(0.0, 0.0, 0.0), (0.8, 0.0, 0.0), (0.8, 0.5, 0.0), (-0.8, 0.0, 0.0)]
measure_loads.main()

d = np.load(f'{OUT}/{TAG}.npz')
DT = 0.02


def hf_frac(x, f0=5.0):
    x = np.asarray(x, float) - np.mean(x)
    if x.std() < 1e-9:
        return 0.0
    P = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), DT)
    return float(P[f >= f0].sum() / max(P[1:].sum(), 1e-12))


rows = {}
m_walk = (np.abs(d['cmd_vx']) > 0.1)
m_walk[:50] = False
tc = np.concatenate([d[f'tau_{s}_crank_{t}_joint'][m_walk] for s in 'LR' for t in 'AB'])
dtc = np.concatenate([np.abs(np.diff(d[f'tau_{s}_crank_{t}_joint'][m_walk])) for s in 'LR' for t in 'AB'])
cl = np.concatenate([d[f'closure_mm_{s}'][m_walk] for s in 'LR'])
fr = np.concatenate([np.abs(d[f'Frod_{s}_{t}'][m_walk]) for s in 'LR' for t in 'AB'])
ta = np.concatenate([d[f'tauank_eq_{s}_pitch'][m_walk] for s in 'LR'])
grf = np.concatenate([d[f'GRFc_{s}_foot_link_z'][m_walk] for s in 'LR'])
hf = np.mean([hf_frac(d[f'tau_{s}_crank_{t}_joint'][m_walk]) for s in 'LR' for t in 'AB'])
# tracking: base velocity vs command (walk blocks)
vx = d['base_vx'][m_walk] if 'base_vx' in d.files else None
err = float(np.mean(np.abs(vx - d['cmd_vx'][m_walk]))) if vx is not None else float('nan')
fell = int((d['base_height'][m_walk] < 0.45).sum())
rows = dict(tag=TAG, solimp=os.environ.get('PYG_LOOP_SOLIMP', 'xml 0.999 0.9999 1e-4'), solref=os.environ.get('PYG_LOOP_SOLREF', 'xml 0.002 1'),
            crank_tau_rms=float(np.sqrt((tc ** 2).mean())), crank_tau_p99=float(np.percentile(np.abs(tc), 99)), crank_tau_max=float(np.abs(tc).max()),
            dtau_p99=float(np.percentile(dtc, 99)), dtau_max=float(dtc.max()), hf5_frac=float(hf),
            closure_rms=float(np.sqrt((cl ** 2).mean())), closure_p99=float(np.percentile(cl, 99)), closure_max=float(cl.max()),
            Frod_p99=float(np.percentile(fr, 99)), Frod_max=float(fr.max()), tauank_rms=float(np.sqrt((ta ** 2).mean())),
            GRFc_p99=float(np.percentile(grf, 99)), vx_err=err, low_base_steps=fell)
import json
json.dump(rows, open(f'{OUT}/{TAG}.json', 'w'), indent=1)
print('RESULT', json.dumps(rows))
