# -*- coding: utf-8 -*-
"""Runtime robot-mass adjustment (for hardware-design sweeps).

Scales body masses **and inertias** consistently via the PhysX articulation view, mirroring
Isaac Lab's ``randomize_rigid_body_mass`` (events.py). Use from play / measure scripts to set a
deliberate mass before a run (e.g. ``--mass_scale 1.2`` or ``--base_mass 32``).

PhysX mass setters expect CPU tensors and are best called right after reset, before stepping.
"""

from __future__ import annotations

import re

import torch


def _body_ids(robot, body_regex: str | None):
    names = list(robot.body_names)
    if body_regex is None:
        return list(range(len(names))), names
    ids = [i for i, n in enumerate(names) if re.match(body_regex, n)]
    return ids, [names[i] for i in ids]


def apply_mass_scale(robot, scale: float, body_regex: str | None = None, recompute_inertia: bool = True):
    """Multiply the mass (and inertia) of matched bodies by ``scale`` for all envs.

    body_regex=None -> every body (uniform robot mass scale).
    """
    view = robot.root_physx_view
    masses = view.get_masses()                       # [num_envs, num_bodies] (cpu)
    default = robot.data.default_mass.to(masses.device)
    ids, _ = _body_ids(robot, body_regex)
    ids_t = torch.tensor(ids, dtype=torch.long)
    env_ids = torch.arange(masses.shape[0])
    masses[env_ids[:, None], ids_t] = default[env_ids[:, None], ids_t] * float(scale)
    view.set_masses(masses, env_ids)
    if recompute_inertia:
        inertias = view.get_inertias()
        dinert = robot.data.default_inertia.to(inertias.device)
        inertias[env_ids[:, None], ids_t] = dinert[env_ids[:, None], ids_t] * float(scale)
        view.set_inertias(inertias, env_ids)
    return get_mass_summary(robot)


def set_base_mass(robot, mass_kg: float, body_regex: str = "base_link", recompute_inertia: bool = True):
    """Set the absolute mass [kg] of the matched base body, scaling its inertia by the same ratio."""
    view = robot.root_physx_view
    masses = view.get_masses()
    ids, _ = _body_ids(robot, body_regex)
    ids_t = torch.tensor(ids, dtype=torch.long)
    env_ids = torch.arange(masses.shape[0])
    old = masses[env_ids[:, None], ids_t].clone()
    masses[env_ids[:, None], ids_t] = float(mass_kg)
    view.set_masses(masses, env_ids)
    if recompute_inertia:
        ratio = float(mass_kg) / torch.clamp(old, min=1e-6)
        inertias = view.get_inertias()
        inertias[env_ids[:, None], ids_t] = inertias[env_ids[:, None], ids_t] * ratio[..., None]
        view.set_inertias(inertias, env_ids)
    return get_mass_summary(robot)


def get_mass_summary(robot, env_idx: int = 0):
    """Return {body_name: mass_kg} + total for one env (for logging / HUD)."""
    masses = robot.root_physx_view.get_masses()[env_idx].cpu().numpy()
    names = list(robot.body_names)
    per_body = {n: float(m) for n, m in zip(names, masses)}
    per_body["TOTAL"] = float(masses.sum())
    return per_body
