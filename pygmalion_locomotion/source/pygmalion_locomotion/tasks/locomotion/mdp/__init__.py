# -*- coding: utf-8 -*-
"""MDP terms for the biped velocity task.

We reuse Isaac Lab's velocity-locomotion mdp wholesale (rewards/observations/events/
terminations/curriculums) and layer our own human-likeness reward terms on top in
``rewards.py``. Nothing in the Isaac Lab source tree is modified.
"""

# Re-export the full reference velocity mdp namespace (track_*_exp, feet_air_time_positive_biped,
# feet_slide, joint_deviation_l1, randomize_rigid_body_mass, push_by_setting_velocity, ...).
from isaaclab_tasks.manager_based.locomotion.velocity.mdp import *  # noqa: F401,F403

# Our additions (human-like gait shaping).
from .rewards import (  # noqa: F401
    base_height_l2,
    upright_posture,
    feet_distance_l1,
    no_flight_phase,
    applied_torque_soft_limit,
)
from .unitree_rewards import (  # noqa: F401
    energy,
    feet_gait,
    foot_clearance_reward,
)
# Spec-driven physical-property override (startup event).
from .events import apply_robot_physics  # noqa: F401
