# -*- coding: utf-8 -*-
"""Per-joint motor telemetry -> wandb (scalars) + saved bar charts.

A thin ``gym.Wrapper`` that taps the robot articulation every env step and periodically
summarizes, PER JOINT, the magnitude of three signals:

  * ``torque`` = ``data.applied_torque``  -> the ACTUAL torque applied to the joint AFTER the
                 PD actuator model + effort-limit clamp (NOT the policy output, which is a
                 joint-position target). This is the value to size motors / judge sim2real.
  * ``vel``    = ``data.joint_vel``        -> measured joint angular velocity (state).
  * ``acc``    = ``data.joint_acc``        -> measured joint angular acceleration (state).

For each signal+joint it reports three reductions over the logging window:

  * ``rms`` = sqrt(mean(x^2))   -> magnitude regardless of sign; maps to motor HEATING
              (I^2 R ~ tau^2) -> compare to the CONTINUOUS (rated) torque for thermal duty.
  * ``p95`` = 95th percentile   -> a ROBUST peak (ignores single-sample sim spikes); use for
              sizing against the PEAK torque rating.
  * ``max`` = absolute peak     -> worst case (structural safety margin); read together w/ p95.

RMS (over ALL envs+steps in the window) and max (over ALL envs+steps) are EXACT; p95 is taken
over a subsample of envs to bound memory. Scalars are injected into ``extras["log"]`` so rsl_rl
logs them on its own iteration step axis (wandb tag == key, grouped by the prefix before "/").
Bar charts are rendered every ``chart_interval`` steps, saved to ``<log_dir>/telemetry/`` and
(best-effort) uploaded to wandb.
"""

from __future__ import annotations

import os

import gymnasium as gym
import torch


class JointTelemetryWrapper(gym.Wrapper):
    SIGNALS = ("torque", "vel", "acc")
    UNITS = {"torque": "N·m", "vel": "rad/s", "acc": "rad/s²"}

    def __init__(
        self,
        env,
        log_dir: str,
        scalar_interval: int = 120,
        chart_interval: int = 1500,
        p95_sub_envs: int = 256,
        key_prefix: str = "Motor",
        robot_name: str = "robot",
    ):
        super().__init__(env)
        self.telemetry_dir = os.path.join(log_dir, "telemetry")
        os.makedirs(self.telemetry_dir, exist_ok=True)
        self.scalar_interval = max(1, int(scalar_interval))
        self.chart_interval = max(1, int(chart_interval))
        self.p95_sub_envs = max(1, int(p95_sub_envs))
        self.key_prefix = key_prefix
        self.robot_name = robot_name

        self._steps = 0
        self._robot = None
        self._jnames: list[str] = []
        self._effort = None  # [J] effort limits (for the torque chart reference line), if available
        self._last_scalars: dict[str, float] = {}
        self._last_stats = None
        self._reset_accum()

    # ----- setup (lazy: scene exists only after the first step) -----
    def _ensure_robot(self):
        if self._robot is not None:
            return
        robot = self.env.unwrapped.scene[self.robot_name]
        self._robot = robot
        self._jnames = list(robot.joint_names)
        try:
            el = robot.data.joint_effort_limits
            el = el[0] if el.dim() == 2 else el
            self._effort = el.detach().float().cpu()
        except Exception:
            self._effort = None

    def _reset_accum(self):
        self._sumsq: dict[str, torch.Tensor] = {}
        self._max: dict[str, torch.Tensor] = {}
        self._buf: dict[str, list[torch.Tensor]] = {s: [] for s in self.SIGNALS}
        self._count = 0

    def _grab(self) -> dict[str, torch.Tensor]:
        d = self._robot.data
        return {
            "torque": d.applied_torque.abs(),
            "vel": d.joint_vel.abs(),
            "acc": d.joint_acc.abs(),
        }

    # ----- gym API -----
    def step(self, action):
        out = self.env.step(action)
        extras = out[-1]
        try:
            self._tap(extras)
        except Exception as exc:  # never let telemetry crash training
            if self._steps < 3:
                print(f"[telemetry] disabled after error: {exc}")
        return out

    def _tap(self, extras):
        self._ensure_robot()
        vals = self._grab()
        n_env = next(iter(vals.values())).shape[0]
        sub = min(self.p95_sub_envs, n_env)
        for s, t in vals.items():
            sq = (t * t).sum(dim=0)
            mx = t.amax(dim=0)
            if s not in self._sumsq:
                self._sumsq[s] = sq
                self._max[s] = mx
            else:
                self._sumsq[s] += sq
                self._max[s] = torch.maximum(self._max[s], mx)
            self._buf[s].append(t[:sub].detach())
        self._count += n_env
        self._steps += 1

        if self._steps % self.scalar_interval == 0:
            self._flush_scalars()
        # re-inject the last computed scalars EVERY step so rsl_rl's per-iteration mean == the
        # exact window value (it averages extras["log"] over the iteration's steps).
        if self._last_scalars and isinstance(extras, dict):
            extras.setdefault("log", {}).update(self._last_scalars)

        if self._steps % self.chart_interval == 0 and self._last_stats is not None:
            self._make_charts()

    def _compute(self):
        stats = {}
        denom = max(1, self._count)
        for s in self.SIGNALS:
            rms = torch.sqrt(self._sumsq[s] / denom)
            mx = self._max[s]
            buf = torch.cat(self._buf[s], dim=0) if self._buf[s] else None
            if buf is not None and buf.numel():
                p95 = torch.quantile(buf.float(), 0.95, dim=0)
            else:
                p95 = torch.zeros_like(rms)
            stats[s] = (rms.detach().cpu(), p95.detach().cpu(), mx.detach().cpu())
        return stats

    def _flush_scalars(self):
        stats = self._compute()
        flat: dict[str, float] = {}
        for s in self.SIGNALS:
            rms, p95, mx = stats[s]
            for j, name in enumerate(self._jnames):
                flat[f"{self.key_prefix}_{s}_rms/{name}"] = float(rms[j])
                flat[f"{self.key_prefix}_{s}_p95/{name}"] = float(p95[j])
                flat[f"{self.key_prefix}_{s}_max/{name}"] = float(mx[j])
        self._last_scalars = flat
        self._last_stats = stats
        self._reset_accum()

    # ----- charts -----
    def _make_charts(self):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
        except Exception as exc:
            print(f"[telemetry] matplotlib unavailable, skipping charts: {exc}")
            return

        names = self._jnames
        short = [n.replace("_joint", "").replace("_link", "") for n in names]
        x = np.arange(len(names))
        w = 0.27
        wandb_images = {}
        for s in self.SIGNALS:
            rms, p95, mx = (v.numpy() for v in self._last_stats[s])
            fig, ax = plt.subplots(figsize=(max(8, 0.55 * len(names)), 4.2))
            ax.bar(x - w, rms, w, label="RMS", color="#2c7fb8")
            ax.bar(x, p95, w, label="p95", color="#7fcdbb")
            ax.bar(x + w, mx, w, label="max", color="#edf8b1", edgecolor="#888")
            if s == "torque" and self._effort is not None and len(self._effort) == len(names):
                ax.plot(x, self._effort.numpy(), "r_", markersize=14, label="effort limit")
            ax.set_xticks(x)
            ax.set_xticklabels(short, rotation=45, ha="right", fontsize=8)
            ax.set_ylabel(f"|{s}| [{self.UNITS[s]}]")
            ax.set_title(f"Per-joint {s}  (step {self._steps})")
            ax.legend(fontsize=8)
            ax.grid(axis="y", alpha=0.3)
            fig.tight_layout()
            path = os.path.join(self.telemetry_dir, f"{s}_step_{self._steps:08d}.png")
            fig.savefig(path, dpi=110)
            plt.close(fig)
            wandb_images[f"{self.key_prefix}_charts/{s}"] = path

        self._log_images_to_wandb(wandb_images)

    def _log_images_to_wandb(self, path_by_key: dict[str, str]):
        try:
            import wandb
            if wandb.run is None:
                return
            step = getattr(wandb.run, "step", None)
            payload = {k: wandb.Image(p) for k, p in path_by_key.items()}
            wandb.log(payload, step=step)
        except Exception as exc:
            print(f"[telemetry] wandb image log skipped: {exc}")
