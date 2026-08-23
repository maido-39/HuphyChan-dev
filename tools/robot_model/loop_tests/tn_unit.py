"""T-N clamp unit check: tn_limit vs the csv, quadrant rule, and the actuator types built."""
import os, torch, numpy as np
from mjlab.asset_zoo.robots.pygmalion import pygmalion_constants as C
from mjlab.asset_zoo.robots.pygmalion.tn_actuator import tn_curve_tensor, tn_limit, tn_clamp
dev = "cpu"
for fam in ("RS04", "RS03"):
    w, t = tn_curve_tensor(C.tn_curve(fam), dev)
    sp = torch.tensor([0.0, 5.0, w[0].item(), 0.5 * (w[0] + w[-1]).item(), w[-2].item(), w[-1].item(), 30.0])
    print(fam, "corner %.2f rad/s peak %.1f | no-load %.2f rad/s" % (w[0], t[0], w[-1]), "| tau_tn at", [round(x, 2) for x in sp.tolist()], "=", [round(x, 1) for x in tn_limit(w, t, sp).tolist()])
    tau = torch.tensor([100.0, 100.0, -100.0, -100.0, 100.0]); om = torch.tensor([0.0, 18.0, 18.0, -18.0, -18.0])
    print("   clamp tau/omega", list(zip(tau.tolist(), om.tolist())), "->", [round(x, 1) for x in tn_clamp(tau, om, w, t).tolist()])
print("actuators:", [(type(a).__name__, a.target_names_expr[0], round(a.effort_limit, 1), a.armature) for a in C.PYG_ARTICULATION.actuators])
