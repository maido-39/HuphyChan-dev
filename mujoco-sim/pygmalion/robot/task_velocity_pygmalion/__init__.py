from mjlab.tasks.registry import register_mjlab_task
from mjlab.tasks.velocity.rl import VelocityOnPolicyRunner

from .env_cfgs import (
  pygmalion_flat_env_cfg,
  pygmalion_rough_env_cfg,
)
from .rl_cfg import pygmalion_ppo_runner_cfg

register_mjlab_task(
  task_id="Mjlab-Velocity-Rough-Pygmalion",
  env_cfg=pygmalion_rough_env_cfg(),
  play_env_cfg=pygmalion_rough_env_cfg(play=True),
  rl_cfg=pygmalion_ppo_runner_cfg(),
  runner_cls=VelocityOnPolicyRunner,
)

register_mjlab_task(
  task_id="Mjlab-Velocity-Flat-Pygmalion",
  env_cfg=pygmalion_flat_env_cfg(),
  play_env_cfg=pygmalion_flat_env_cfg(play=True),
  rl_cfg=pygmalion_ppo_runner_cfg(),
  runner_cls=VelocityOnPolicyRunner,
)
