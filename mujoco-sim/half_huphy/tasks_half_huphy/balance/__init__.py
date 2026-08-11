"""Register Half Huphy balance tasks."""

from mjlab.tasks.registry import register_mjlab_task

from .env_cfgs import half_huphy_balance_env_cfg
from .rl_cfg import half_huphy_balance_ppo_runner_cfg

register_mjlab_task(
  task_id="Mjlab-Balance-HalfHuphy",
  env_cfg=half_huphy_balance_env_cfg(),
  play_env_cfg=half_huphy_balance_env_cfg(play=True),
  rl_cfg=half_huphy_balance_ppo_runner_cfg(),
)
