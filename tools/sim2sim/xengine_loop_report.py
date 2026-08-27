"""Join the two engines' closed-loop static results into one verdict table.

The comparison only means anything if both engines are asked the SAME question at the SAME pose.
The serial round of this work learned that the hard way: a 0.43 N*m "disagreement" turned out to be
IsaacSim answering about the pose its servo actually reached while MuJoCo answered about the pose
it was commanded. So MuJoCo is re-evaluated here at Isaac's reached pose, per phase, and each phase
is matched to the reference that asks its question:

  motors    -> `static_motor_Nm`  (only the 17 real motors resist gravity; the loop carries the rest)
  all_held  -> `bias_Nm`          (every joint has its own servo, so the loop carries nothing)

Run with the mjlab venv:  mujoco-sim/mjlab/.venv/bin/python3 tools/sim2sim/xengine_loop_report.py
"""
import importlib.util
import json
import sys

import numpy as np

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
ISAAC = sys.argv[1] if len(sys.argv) > 1 else '/home/syaro/pyg_fea/work/xengine_loop_isaac.json'
MJREF = '/home/syaro/pyg_fea/work/xengine_loop_mujoco.json'
OUT = '/home/syaro/pyg_fea/work/xengine_loop_verdict.json'

spec = importlib.util.spec_from_file_location('xlm', f'{REPO}/tools/sim2sim/xengine_loop_mujoco.py')
xlm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xlm)

iso = json.load(open(ISAAC))
ref = json.load(open(MJREF))
ACT = ref['actuated']
verdict = {'usd': iso.get('usd'), 'physics_dt': iso.get('physics_dt'),
           'total_mass_kg': {'mujoco': ref['total_mass'], 'isaac': iso.get('total_mass_kg')},
           'n_dof': iso.get('n_dof'), 'solver_iters': iso.get('solver_iters'), 'phases': {}}

for tag, key, scope in (('motors', 'static_motor_Nm', ACT),
                        ('all_held', 'bias_Nm', None)):
    ph = iso.get(tag)
    if not ph:
        verdict['phases'][tag] = {'missing': True}
        continue
    m, d = xlm.load()
    xlm.set_pose(m, d, ph['q_reached'])                # MuJoCo asked about the pose Isaac reached
    mj = xlm.references(m, d)
    names = scope if scope else [j for j in ph['q_reached'] if j in mj[key]]
    rows = []
    for jn in names:
        a, b = ph['torque_Nm'][jn], mj[key][jn]
        rows.append({'joint': jn, 'isaac': round(a, 4), 'mujoco': round(b, 4),
                     'diff': round(a - b, 5)})
    diffs = np.array([abs(r['diff']) for r in rows])
    verdict['phases'][tag] = {
        'rows': rows,
        'max_diff_Nm': float(diffs.max()), 'median_diff_Nm': float(np.median(diffs)),
        'worst_joint': rows[int(diffs.argmax())]['joint'],
        'max_load_Nm': float(max(abs(r['mujoco']) for r in rows)),
        'q_err_max_driven_rad': ph['q_err_max_driven'],
        'qd_max': ph['qd_max'],
        'loop_drift_mm_isaac': ph['loop_drift_mm'],
        'loop_gap_mm_mujoco_at_that_pose': mj['loop_gap_mm'],
        'ankle_err_rad': ph['ankle_err_rad'],
        'mujoco_static_solve_residual_Nm': mj['static_solve_residual_Nm'],
    }

    # Geometry check the torque table cannot make: hand MuJoCo only the crank angles IsaacSim
    # settled on, let its loop decide where the foot goes, and see whether it lands where PhysX
    # put it. Wrong anchors would show up here and nowhere else - both engines can be perfectly
    # self-consistent about torque while disagreeing about the mechanism.
    m2, d2 = xlm.load()
    xlm.set_pose(m2, d2, ph['q_reached'])
    for jn in [j for j in ph['q_reached'] if 'ankle' in j or '_rod_' in j]:
        d2.qpos[xlm.qadr(m2, jn)] = 0.0                # forget Isaac's answer before re-deriving it
    fk = xlm.ankle_from_cranks(m2, d2)
    verdict['phases'][tag]['ankle_from_cranks'] = {
        'mujoco_solved_rad': {k: round(v, 6) for k, v in fk.items()},
        'isaac_minus_mujoco_rad': {k: round(ph['q_reached'][k] - fk[k], 6)
                                   for k in fk if k in ph['q_reached']},
    }

json.dump(verdict, open(OUT, 'w'), indent=1)

for tag, v in verdict['phases'].items():
    if v.get('missing'):
        print(f'{tag}: MISSING'); continue
    print(f"\n== {tag} ==  max {v['max_diff_Nm']:.4f} Nm (worst {v['worst_joint']}), "
          f"median {v['median_diff_Nm']:.4f}, biggest load {v['max_load_Nm']:.3f} Nm")
    print(f"   loop drift (Isaac, mm): {v['loop_drift_mm_isaac']}")
    print(f"   ankle error vs MuJoCo pose (rad): {v['ankle_err_rad']}")
    fk = v.get('ankle_from_cranks', {})
    if fk:
        e = fk['isaac_minus_mujoco_rad']
        print(f"   loop FK check (Isaac ankle minus MuJoCo-from-same-cranks, rad): "
              f"{ {k: e[k] for k in e if 'ankle' in k} }")
    print(f"   {'joint':26s} {'isaac':>9s} {'mujoco':>9s} {'diff':>9s}")
    for r in v['rows']:
        print(f"   {r['joint']:26s} {r['isaac']:9.4f} {r['mujoco']:9.4f} {r['diff']:9.5f}")
print(f'\n-> {OUT}')
