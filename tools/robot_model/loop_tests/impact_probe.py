"""Foot-strike impact at PHYSICS rate (200 Hz) for a trained policy.

Wraps Simulation.step: after every substep the CPU mirror (MjData) is forwarded from the
warp state and the floor contact forces on each foot are summed. Per touchdown event:
impact velocity (foot vertical velocity just before first contact), peak vertical force in
the first 60 ms, loading rate (max dF/dt over 5 ms windows), time to peak, 30 ms impulse.
Also reports the 50 Hz sensor view (what the reward terms see) for comparison.

  PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_ANKLE_MODE=AB CUDA_VISIBLE_DEVICES="" \
    .venv/bin/python3 ../../tools/robot_model/loop_tests/impact_probe.py <run_dir> <ckpt> <tag> [vx...]
"""
import json, os, sys
import numpy as np, torch, mujoco
from dataclasses import asdict
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
import mjlab.tasks  # noqa

D, CK, TAG = sys.argv[1:4]; VXS = [float(v) for v in sys.argv[4:]] or [0.4, 0.8]
OUT = '/home/syaro/pyg_fea/work/impact'; os.makedirs(OUT, exist_ok=True)
cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True); cfg.scene.num_envs = 1; cfg.events.pop('push_robot', None)
env = ManagerBasedRlEnv(cfg=cfg, device='cpu'); envw = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion').clip_actions)
runner = (load_runner_cls('Mjlab-Velocity-Flat-Pygmalion') or MjlabOnPolicyRunner)(envw, asdict(load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion')), device='cpu')
runner.load(CK, load_cfg={'actor': True}, strict=True, map_location='cpu'); policy = runner.get_inference_policy(device='cpu')
sim = env.sim; mj = sim.mj_model; md = mujoco.MjData(mj); robot = env.scene['robot']
feet = {s: mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_BODY, f'robot/{s}_foot_link') for s in 'LR'}
floor = [g for g in range(mj.ngeom) if (mujoco.mj_id2name(mj, mujoco.mjtObj.mjOBJ_GEOM, g) or '').endswith('floor') or mj.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE]
BW = float(mj.body_subtreemass[mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_BODY, 'robot/base_link')]) * 9.81
print(f'[impact] BW {BW:.0f} N  floor geoms {floor}')
rec = {s: dict(F=[], vz=[], z=[]) for s in 'LR'}; tlog = []
orig_step = sim.step
f6 = np.zeros(6)
def hooked_step():
    orig_step()
    md.qpos[:] = sim.data.qpos[0].cpu().numpy(); md.qvel[:] = sim.data.qvel[0].cpu().numpy(); md.ctrl[:] = sim.data.ctrl[0].cpu().numpy()
    mujoco.mj_forward(mj, md)
    for s, bid in feet.items():
        Fz = 0.0
        for ci in range(md.ncon):
            c = md.contact[ci]; b1, b2 = mj.geom_bodyid[c.geom1], mj.geom_bodyid[c.geom2]
            if bid not in (b1, b2): continue
            mujoco.mj_contactForce(mj, md, ci, f6); fw = c.frame.reshape(3, 3).T @ f6[:3]
            Fz += (fw[2] if b2 == bid else -fw[2])
        vz = float(md.cvel[bid][5]); z = float(md.xpos[bid][2])
        rec[s]['F'].append(Fz); rec[s]['vz'].append(vz); rec[s]['z'].append(z)
    tlog.append(md.time)
sim.step = hooked_step
envw.reset()
dt = float(mj.opt.timestep); seg = {}
for vx in VXS:
    env.command_manager.get_command('twist')[:] = torch.tensor([[vx, 0.0, 0.0]])
    n0 = len(tlog)
    for i in range(int(10.0 / env.step_dt)):
        env.command_manager.get_command('twist')[:] = torch.tensor([[vx, 0.0, 0.0]])
        with torch.no_grad():
            obs = envw.get_observations(); act = policy(obs); envw.step(act)
    seg[vx] = (n0 + int(2.0 / dt), len(tlog))     # drop the first 2 s transient
# ---- event analysis ----
events = []
for vx, (i0, i1) in seg.items():
    for s in 'LR':
        F = np.array(rec[s]['F'][i0:i1]); vz = np.array(rec[s]['vz'][i0:i1])
        on = F > 0.02 * BW
        k = 1
        while k < len(F):
            if on[k] and not on[k - 1] and (k + 1 < len(F)) and (~on[max(0, k - 10):k]).all():
                w = F[k:k + int(0.06 / dt)]
                if len(w) < 5: break
                pk = int(np.argmax(w)); dF = np.diff(w) / dt
                lr = float(np.max(np.convolve(dF, np.ones(1) / 1, 'valid'))) if len(dF) else 0.0
                imp = float(np.sum(F[k:k + int(0.03 / dt)]) * dt)
                events.append(dict(vx=vx, foot=s, v_impact=float(-vz[k - 1]), peak_BW=float(w[pk] / BW), t_peak_ms=float(pk * dt * 1000), loading_rate_BWs=float(lr / BW), impulse_30ms=imp / BW))
                k += int(0.1 / dt)
            k += 1
ev = events
def q(key, fn=np.median): return float(fn([e[key] for e in ev])) if ev else float('nan')
summary = dict(tag=TAG, ckpt=os.path.basename(CK), BW=BW, n_events=len(ev), v_impact_med=q('v_impact'), v_impact_p90=q('v_impact', lambda x: np.percentile(x, 90)),
               peak_BW_med=q('peak_BW'), peak_BW_p90=q('peak_BW', lambda x: np.percentile(x, 90)), peak_BW_max=q('peak_BW', np.max),
               loading_rate_med=q('loading_rate_BWs'), loading_rate_p90=q('loading_rate_BWs', lambda x: np.percentile(x, 90)), t_peak_ms_med=q('t_peak_ms'), impulse30_med=q('impulse_30ms'))
# what the 50 Hz sensor sees: sample every 4th substep
for s in 'LR':
    F = np.array(rec[s]['F']); summary[f'F50_p99_BW_{s}'] = float(np.percentile(F[::4], 99) / BW); summary[f'F200_p99_BW_{s}'] = float(np.percentile(F, 99) / BW); summary[f'F200_max_BW_{s}'] = float(F.max() / BW)
json.dump(dict(summary=summary, events=ev, rec={s: {k: v for k, v in r.items()} for s, r in rec.items()}, dt=dt, seg={str(k): v for k, v in seg.items()}), open(f'{OUT}/{TAG}.json', 'w'))
print('SUMMARY', json.dumps(summary))
