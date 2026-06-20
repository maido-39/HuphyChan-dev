# -*- coding: utf-8 -*-
"""Per-step joint-torque / link-reaction-wrench / foot-GRF logger.

Captures, for one environment instance (default env 0), the quantities a hardware
designer needs:

  * joint torque         robot.data.applied_torque            -> tau_<joint>            [N*m]
  * link reaction wrench robot.data.body_incoming_joint_wrench_b
                         (parent->child, parent body frame)   -> Fx/Fy/Fz/Tx/Ty/Tz_<body>
                                                                 [N] / [N*m]   ("축력 = 반력")
  * foot ground reaction ContactSensor.data.net_forces_w      -> GRF_<foot>{x,y,z,|.|}  [N]

Data is appended in memory and flushed to BOTH a wide CSV (time series, easy to open) and a
compressed NPZ (named arrays, easy to analyze in numpy). Units/frames are recorded in a
sidecar JSON so plots are unambiguous.
"""

from __future__ import annotations

import json
import os
import re

import numpy as np


class WrenchLogger:
    def __init__(
        self,
        robot,
        contact_sensor=None,
        foot_body_regex: str = ".*_foot_link",
        env_idx: int = 0,
        out_dir: str = "logs/measure",
    ):
        self.robot = robot
        self.contact_sensor = contact_sensor
        self.env_idx = int(env_idx)
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)

        # Name tables (constant across steps)
        self.joint_names = list(robot.joint_names)
        self.body_names = list(robot.body_names)

        # Foot indices in the *articulation* body order (for wrench) and in the *contact sensor*
        # body order (for GRF). They can differ, so resolve both.
        self.foot_body_idx = [i for i, n in enumerate(self.body_names) if re.match(foot_body_regex, n)]
        self.foot_body_names = [self.body_names[i] for i in self.foot_body_idx]
        self.cs_foot_idx = []
        if contact_sensor is not None:
            cs_names = list(getattr(contact_sensor, "body_names", []) or [])
            self.cs_body_names = cs_names
            self.cs_foot_idx = [i for i, n in enumerate(cs_names) if re.match(foot_body_regex, n)]
            self.cs_foot_names = [cs_names[i] for i in self.cs_foot_idx]
        else:
            self.cs_body_names = []
            self.cs_foot_names = []

        self._rows = []          # list of flat dicts (for CSV)
        self._t0 = None

    # ------------------------------------------------------------------ record
    def record(self, sim_time: float, command=None):
        """Append one row of data for ``env_idx``. ``command`` is an optional (vx,vy,wz)."""
        i = self.env_idx
        d = self.robot.data

        tau = d.applied_torque[i].detach().cpu().numpy()                    # [num_joints]
        wrench = d.body_incoming_joint_wrench_b[i].detach().cpu().numpy()   # [num_bodies, 6]
        joint_pos = d.joint_pos[i].detach().cpu().numpy()
        joint_vel = d.joint_vel[i].detach().cpu().numpy()
        base_h = float(d.root_pos_w[i, 2].detach().cpu())

        row = {"time": float(sim_time), "base_height": base_h}
        if command is not None:
            cmd = np.asarray(command, dtype=float).reshape(-1)
            row["cmd_vx"] = float(cmd[0]) if cmd.size > 0 else 0.0
            row["cmd_vy"] = float(cmd[1]) if cmd.size > 1 else 0.0
            row["cmd_wz"] = float(cmd[2]) if cmd.size > 2 else 0.0

        # joint torque + velocity + position + MECHANICAL POWER (tau*omega) per joint.
        # (omega/qpos were read but never logged -> blocked CoT, electrical power, torque-speed
        #  validation, and the toe ankle-offload metric. See docs/21 + roadmap ws2d3t2mh.)
        for j, name in enumerate(self.joint_names):
            row[f"tau_{name}"] = float(tau[j])
            row[f"omega_{name}"] = float(joint_vel[j])
            row[f"qpos_{name}"] = float(joint_pos[j])
            row[f"Pmech_{name}"] = float(tau[j] * joint_vel[j])
        # link reaction wrench (6-axis) per body
        comp = ["Fx", "Fy", "Fz", "Tx", "Ty", "Tz"]
        for b, name in enumerate(self.body_names):
            for c in range(6):
                row[f"{comp[c]}_{name}"] = float(wrench[b, c])
        # foot ground reaction (world frame) from contact sensor
        if self.contact_sensor is not None and len(self.cs_foot_idx) > 0:
            grf = self.contact_sensor.data.net_forces_w[i].detach().cpu().numpy()  # [num_cs_bodies, 3]
            for k, bi in enumerate(self.cs_foot_idx):
                fx, fy, fz = grf[bi]
                fn = self.cs_foot_names[k]
                row[f"GRF_{fn}_x"] = float(fx)
                row[f"GRF_{fn}_y"] = float(fy)
                row[f"GRF_{fn}_z"] = float(fz)
                row[f"GRF_{fn}_mag"] = float(np.linalg.norm(grf[bi]))
        self._rows.append(row)

    # -------------------------------------------------------------------- save
    def save(self, tag: str = "run"):
        """Flush to ``<out_dir>/<tag>.csv`` + ``.npz`` + ``<tag>_meta.json``. Returns paths."""
        if not self._rows:
            print("[WrenchLogger] no rows to save.")
            return None
        # union of all keys, stable order: time/base_height/cmd first, then sorted rest
        head = [k for k in ("time", "base_height", "cmd_vx", "cmd_vy", "cmd_wz") if k in self._rows[0]]
        rest = sorted(k for k in self._rows[0].keys() if k not in head)
        cols = head + rest

        csv_path = os.path.join(self.out_dir, f"{tag}.csv")
        with open(csv_path, "w") as f:
            f.write(",".join(cols) + "\n")
            for r in self._rows:
                f.write(",".join(f"{r.get(c, 0.0):.6g}" for c in cols) + "\n")

        # NPZ: column-major arrays
        arrays = {c: np.asarray([r.get(c, 0.0) for r in self._rows], dtype=np.float32) for c in cols}
        npz_path = os.path.join(self.out_dir, f"{tag}.npz")
        np.savez_compressed(npz_path, **arrays)

        meta = {
            "tag": tag,
            "env_idx": self.env_idx,
            "num_steps": len(self._rows),
            "joint_names": self.joint_names,
            "body_names": self.body_names,
            "foot_bodies": self.foot_body_names,
            "units": {
                "tau_*": "N*m (joint torque, applied_torque)",
                "Fx/Fy/Fz_*": "N (link incoming-joint reaction force, parent body frame)",
                "Tx/Ty/Tz_*": "N*m (link incoming-joint reaction moment, parent body frame)",
                "GRF_*": "N (foot net contact force, world frame)",
                "base_height": "m (world z)",
                "time": "s",
            },
        }
        meta_path = os.path.join(self.out_dir, f"{tag}_meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"[WrenchLogger] saved {len(self._rows)} steps -> {csv_path}")
        return {"csv": csv_path, "npz": npz_path, "meta": meta_path}

    # --------------------------------------------------------------- live read
    def latest_summary(self):
        """Return a compact dict for the HUD: per-joint torque + per-foot GRF magnitude + base height."""
        i = self.env_idx
        d = self.robot.data
        tau = d.applied_torque[i].detach().cpu().numpy()
        out = {"joint_torque": {n: float(tau[j]) for j, n in enumerate(self.joint_names)}}
        out["base_height"] = float(d.root_pos_w[i, 2].detach().cpu())
        if self.contact_sensor is not None and self.cs_foot_idx:
            grf = self.contact_sensor.data.net_forces_w[i].detach().cpu().numpy()
            out["foot_grf"] = {
                self.cs_foot_names[k]: float(np.linalg.norm(grf[bi])) for k, bi in enumerate(self.cs_foot_idx)
            }
        return out
