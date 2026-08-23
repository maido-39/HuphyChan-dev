"""env steps/s and GPU memory for a mode x num_envs (random actions, 150 steps after warmup)."""
import os, sys, time, torch
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
n = int(sys.argv[1]); mode = os.environ.get("PYG_ANKLE_MODE", "legacy")
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=False); cfg.scene.num_envs = n
env = ManagerBasedRlEnv(cfg=cfg, device="cuda:0"); env.reset()
a = torch.zeros(n, env.action_manager.total_action_dim, device="cuda:0")
for i in range(30): env.step(torch.randn_like(a) * 0.3)
torch.cuda.synchronize(); t0 = time.time()
for i in range(150): env.step(torch.randn_like(a) * 0.3)
torch.cuda.synchronize(); dt = time.time() - t0
m = env.sim.mj_model
print("RESULT mode=%s envs=%d  %.0f env-steps/s (%.1f steps/s)  GPU peak %.2f GB  nv=%d neq=%d" % (
    mode, n, 150 * n / dt, 150 / dt, torch.cuda.max_memory_allocated() / 1e9, m.nv, m.neq))
env.close()
