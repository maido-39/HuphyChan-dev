"""How much does moving the IMU site change the ACTOR's base_lin_vel observation?

`base_lin_vel` is an actor term fed by a MuJoCo velocimeter at site `imu_in_base`. A velocimeter
reports the velocity OF THE SITE, so v_site = v_body + omega x r. Moving the site by dr therefore
shifts the observation by omega x dr - which is not small when the pelvis is rotating.

Rolls out a trained policy and reports the distribution of |omega x dr| for the proposed move.

  .venv/bin/python3 imu_site_delta.py <run_dir> <ckpt> [vx] [n_envs]
"""
import os, sys
import numpy as np, torch
from dataclasses import asdict
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
import mjlab.tasks  # noqa

D, CK = sys.argv[1], sys.argv[2]
VX = float(sys.argv[3]) if len(sys.argv) > 3 else 1.6
NE = int(sys.argv[4]) if len(sys.argv) > 4 else 16
OLD = np.array([0.004, 0.0, 0.241])          # site as generated today
NEW = np.array([-0.000001, 0.007078, -0.0695])   # waist-yaw face -187 mm, base_link frame
DR = NEW - OLD

cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True)
cfg.scene.num_envs = NE
cfg.events.pop('push_robot', None)
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

obs, _ = envw.reset()
om = env.observation_manager
for grp in om.active_terms:
    print(f'GROUP {grp}:', flush=True)
    off = 0
    for nm, dim in zip(om.active_terms[grp], om.group_obs_term_dim[grp]):
        d = dim[0] if isinstance(dim, (tuple, list)) else dim
        print(f'   [{off:3d}:{off+d:3d}] {nm}', flush=True)
        off += d

tw = env.command_manager.get_term('twist')
cv = torch.tensor([VX, 0.0, 0.0], dtype=torch.float32).repeat(NE, 1)
tw.vel_command_b[:] = cv
W, V = [], []
for t in range(600):
    with torch.no_grad():
        act = policy(obs)
    obs, _, _, _ = envw.step(act)
    tw.vel_command_b[:] = cv
    # actor obs order (velocity_env_cfg.actor_terms): base_lin_vel[0:3], base_ang_vel[3:6], ...
    # Reading it straight off the observation means we compare against exactly what the policy
    # sees, gyro site frame included, rather than re-deriving it from entity state.
    # Layout verified at runtime, NOT assumed from the base cfg (the pygmalion env is asymmetric):
    #   actor  = [base_ang_vel, projected_gravity, joint_pos, joint_vel, actions, command]
    #   critic = [base_lin_vel, base_ang_vel, ...]
    # So base_lin_vel - the only position-dependent term - is CRITIC-ONLY.
    W.append(obs['actor'][:, 0:3].detach().cpu().numpy().copy())
    V.append(obs['critic'][:, 0:3].detach().cpu().numpy().copy())
W = np.concatenate(W[100:], 0)      # [N, 3] body-frame angular velocity
V = np.concatenate(V[100:], 0)
d = np.cross(W, DR[None, :])        # the observation shift, body frame
mag = np.linalg.norm(d, axis=1)
sp = np.linalg.norm(V[:, :2], axis=1)
print(f'dr = {DR.round(4).tolist()} m   |dr| = {np.linalg.norm(DR)*1000:.1f} mm')
print(f'samples {len(W)}   commanded vx {VX} m/s')
print(f'|omega|      rad/s  median {np.median(np.linalg.norm(W,axis=1)):.3f}  p95 {np.percentile(np.linalg.norm(W,axis=1),95):.3f}')
print(f'|omega x dr| m/s    median {np.median(mag):.4f}  p95 {np.percentile(mag,95):.4f}  max {mag.max():.4f}')
print(f'  per axis p95 (m/s): x {np.percentile(abs(d[:,0]),95):.4f}  y {np.percentile(abs(d[:,1]),95):.4f}  z {np.percentile(abs(d[:,2]),95):.4f}')
print(f'actual planar speed  median {np.median(sp):.3f} m/s  ->  shift is '
      f'{100*np.median(mag)/max(np.median(sp),1e-6):.1f} % of the speed being tracked (median)')
print(f'observation noise on base_lin_vel is Unoise +-0.5 m/s; p95 shift / noise halfwidth = '
      f'{np.percentile(mag,95)/0.5:.3f}')
print('NOTE: base_lin_vel is a CRITIC-ONLY term here; the actor sees base_ang_vel (a gyro, which is'
      ' position-independent on a rigid body) and projected_gravity (orientation-only). Moving the'
      ' site therefore cannot change the deployed policy input at all - only the critic value input.')
os._exit(0)
