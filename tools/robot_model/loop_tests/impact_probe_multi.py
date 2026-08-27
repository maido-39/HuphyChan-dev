"""200 Hz foot-strike statistics across MANY envs — closes the loading-rate question.

Two earlier measurements disagreed on the ORDER of arms, not just the scale:
  impact_probe (200 Hz, 1 env)   CTL 46.2  vs  B2 79.7   BW/s
  evaluator    ( 50 Hz, 32 ep)   CTL 9.92  vs  B2  8.78  BW/s
5 ms windows against 240 ms windows explains the 5x scale, not the flip. One is physically
better resolved, the other statistically robust; neither settles it. This gives both: the
mjlab ContactSensor is read INSIDE the sim.step hook, so every physics substep is sampled
(200 Hz) for all envs at once.

  PYG_... as training; .venv/bin/python3 impact_probe_multi.py <run_dir> <ckpt> <tag> [vx] [n_envs]
"""
import json, os, sys
import numpy as np, torch
from dataclasses import asdict
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
import mjlab.tasks  # noqa

D, CK, TAG = sys.argv[1:4]
VX = float(sys.argv[4]) if len(sys.argv) > 4 else 1.6
NE = int(sys.argv[5]) if len(sys.argv) > 5 else 16
SEC, WARM = 14.0, 3.0
# BW is derived from the loaded model, not hardcoded. It used to be 346.8 N, which is v3's
# 35.347 kg - correct for every v3 run, silently wrong by 12.9 % for the 31.316 kg v4 model,
# where it understates every force expressed in body weights.
BW = None
OUT = '/home/syaro/pyg_fea/work/impact_multi'
if os.environ.get('PROBE_NODR') == '1':
    OUT += '_nodr'; os.makedirs(OUT, exist_ok=True)

cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True)
cfg.scene.num_envs = NE
cfg.events.pop('push_robot', None)
# play mode keeps the DR events (foot_friction / encoder_bias / base_com) while the
# evaluator drops them, so the two instruments were never measuring the same robot.
# PROBE_NODR=1 reproduces the evaluator's clean condition.
NODR = os.environ.get('PROBE_NODR') == '1'
if NODR:
    for _ev in ('foot_friction', 'encoder_bias', 'base_com'):
        cfg.events.pop(_ev, None)
_b = cfg.episode_length_s + 100.0
cfg.commands['twist'].resampling_time_range = (_b, _b)
for f in ('rel_standing_envs', 'rel_heading_envs', 'rel_forward_envs', 'rel_world_envs'):
    setattr(cfg.commands['twist'], f, 0.0)
env = ManagerBasedRlEnv(cfg=cfg, device='cpu')
envw = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion').clip_actions)
runner = (load_runner_cls('Mjlab-Velocity-Flat-Pygmalion') or MjlabOnPolicyRunner)(
    envw, asdict(load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion')), device='cpu')
runner.load(CK, load_cfg={'actor': True}, strict=True, map_location='cpu')
policy = runner.get_inference_policy(device='cpu')
cs = env.scene['feet_ground_contact']
BW = float(env.sim.mj_model.body_mass.sum()) * 9.81
print(f'[multi] model mass {BW / 9.81:.3f} kg -> 1 BW = {BW:.1f} N', flush=True)
sim = env.sim
dt_phys = float(env.sim.mj_model.opt.timestep)
print(f'[multi] {NE} envs, physics dt {dt_phys} ({1/dt_phys:.0f} Hz), vx {VX}', flush=True)

buf = []
orig_step = sim.step
def hooked():
    orig_step()
    f = cs.data.force
    buf.append((torch.norm(f, dim=-1) if f.ndim == 3 else f).clone().numpy())   # [E, F]
sim.step = hooked

obs, _ = envw.reset()
dones_at = []          # physics-step index of every env reset (env, t_phys)
tw = env.command_manager.get_term('twist')
cv = torch.tensor([VX, 0.0, 0.0], dtype=torch.float32).repeat(NE, 1)
tw.vel_command_b[:] = cv
for t in range(int(SEC / env.step_dt)):
    with torch.no_grad():
        act = policy(obs)
    obs, _, dones, _ = envw.step(act)
    if bool(dones.any()):
        for e in torch.nonzero(dones.flatten()).flatten().tolist():
            dones_at.append((e, len(buf)))     # buf length == physics steps so far
    tw.vel_command_b[:] = cv
sim.step = orig_step

F = np.stack(buf, 0) / BW                       # [T_phys, E, F]
w0 = int(WARM / dt_phys)
F = F[w0:]
dn = np.array(dones_at, dtype=np.int64).reshape(-1, 2)
np.savez_compressed(f'{OUT}/{TAG}_raw.npz', F=F.astype(np.float32), dt=dt_phys, dones=dn)
# A reset re-spawns the robot at the keyframe (sole 47 mm above the floor with the deep
# crouch), so the strike that follows is the drop, not the gait. Mask 0.6 s after each.
MASK = int(0.6 / dt_phys)
bad = np.zeros(F.shape[:2], dtype=bool)
for e, t in dn:
    t0 = max(0, t - w0)
    bad[t0:t0 + MASK, e] = True
print(f'[multi] resets: {len(dn)} over {F.shape[1]} envs; masked '
      f'{100*bad.mean():.1f}% of samples', flush=True)

# --- touchdown detection with debounce -------------------------------------
# A single threshold chatters: soft contact plus the loop solver makes F cross
# 0.05 BW many times per real strike (24 envs gave 9.2 crossings/s/env where the
# gait only has ~5). Schmitt trigger + minimum off-time + minimum strike height.
HI, LO = 0.25, 0.05             # BW: arm below LO, fire above HI
OFF_MIN = int(0.08 / dt_phys)   # foot off >= 80 ms before a new strike counts
WIN = int(0.06 / dt_phys)       # 60 ms post-touchdown window
peaks, rates, n_td = [], [], 0
for e in range(F.shape[1]):
    for k in range(F.shape[2]):
        f = F[:, e, k]
        msk = bad[:, e]
        armed, off_run = True, OFF_MIN
        for t in range(len(f)):
            if f[t] < LO:
                off_run += 1
                if off_run >= OFF_MIN:
                    armed = True
            else:
                if armed and f[t] > HI:
                    armed, off_run = False, 0
                    t0 = t                       # back up to the true onset
                    while t0 > 0 and f[t0 - 1] >= LO:
                        t0 -= 1
                    w = f[t0:t0 + WIN]
                    if len(w) >= 4 and not msk[t0]:
                        n_td += 1
                        peaks.append(float(w.max()))
                        rates.append(float(np.max(np.diff(w)) / dt_phys))
                off_run = 0

r = dict(tag=TAG, vx=VX, n_envs=NE, dr=not NODR, n_touchdowns=n_td, hz=round(1 / dt_phys),
         n_resets=int(len(dn)),
         td_per_s_per_env=round(n_td / (F.shape[1] * len(F) * dt_phys), 2),
         peak_BW_med=float(np.median(peaks)), peak_BW_p90=float(np.percentile(peaks, 90)),
         rate_BWs_med=float(np.median(rates)), rate_BWs_p90=float(np.percentile(rates, 90)),
         rate_BWs_p25=float(np.percentile(rates, 25)))
json.dump(r, open(f'{OUT}/{TAG}.json', 'w'), indent=1)
print('MULTI', json.dumps(r), flush=True)
os._exit(0)
