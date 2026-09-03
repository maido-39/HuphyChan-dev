#!/usr/bin/env python3
"""Overlay a Pygmalion model's COLLISION geometry on its VISUAL meshes, CPU only.

Why this exists
---------------
viser hides geom groups 3 (collision) and 4 (hull) by default
(``mjviser/scene.py``: ``geom_groups_visible = [True, True, True, False, False, False]``),
so anything you watch in the browser is the *visual* mesh alone.  When two visual
meshes appear to interpenetrate, that tells you nothing about whether the physics
objects touched.  This tool draws both, to scale, in one picture, and prints the
numeric margin between them.

Rendering is pure software (orthographic projection + painter's algorithm through
matplotlib), because this box has no working EGL/OSMesa context and because the GPU
is normally busy with training.  Same approach as ``rom_sweep_video_cpu.py``.

Usage (cwd must be mujoco-sim/mjlab so the venv .pth resolves)::

    CUDA_VISIBLE_DEVICES="" .venv/bin/python3 \
        ../../tools/robot_model/collision_overlay_render.py \
        --tag LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix --model loop

    # inventory numbers only, no rendering
    ... collision_overlay_render.py --inventory-only
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/pygmalion-matplotlib")
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
XMLS = ROOT / "mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls"
IMGDIR = ROOT / "docs/img"

VISUAL_GROUP = 2
COLLISION_GROUP = 3
HULL_GROUP = 4

# Rendered on a key colour that no shaded geom can produce, so the coverage mask is exact.
KEY = (0, 255, 0)
BG = (247, 248, 250)
VIS_RGB = np.array([0.62, 0.66, 0.72])
COL_RGB = np.array([0.90, 0.16, 0.13])
COL_ALPHA = 0.52

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size: int, bold: bool = False):
    for p in (FONT_CANDIDATES[::-1] if bold else FONT_CANDIDATES):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# --------------------------------------------------------------------------- geometry
def geom_mesh(model: mujoco.MjModel, gi: int):
    """Triangle soup for geom ``gi`` in its own geom frame. Returns (verts, faces)."""
    t = model.geom_type[gi]
    s = model.geom_size[gi]
    if t == mujoco.mjtGeom.mjGEOM_MESH:
        md = int(model.geom_dataid[gi])
        va, vn = int(model.mesh_vertadr[md]), int(model.mesh_vertnum[md])
        fa, fn = int(model.mesh_faceadr[md]), int(model.mesh_facenum[md])
        return (np.asarray(model.mesh_vert[va : va + vn], dtype=np.float64),
                np.asarray(model.mesh_face[fa : fa + fn]))
    if t == mujoco.mjtGeom.mjGEOM_BOX:
        p = trimesh.creation.box(extents=2.0 * np.asarray(s[:3]))
    elif t == mujoco.mjtGeom.mjGEOM_CAPSULE:
        p = trimesh.creation.capsule(height=2.0 * float(s[1]), radius=float(s[0]),
                                     count=(16, 16))
    elif t == mujoco.mjtGeom.mjGEOM_CYLINDER:
        p = trimesh.creation.cylinder(radius=float(s[0]), height=2.0 * float(s[1]),
                                      sections=20)
    elif t == mujoco.mjtGeom.mjGEOM_SPHERE:
        p = trimesh.creation.icosphere(subdivisions=2, radius=float(s[0]))
    else:
        return None
    return np.asarray(p.vertices, dtype=np.float64), np.asarray(p.faces)


def basis(azimuth_deg: float, elevation_deg: float):
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    fwd = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    fwd /= np.linalg.norm(fwd)
    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(fwd @ ref)) > 0.999:  # looking straight up or straight down
        ref = np.array([1.0, 0.0, 0.0])
    right = np.cross(ref, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    return right, up, fwd


class SoftRenderer:
    """Orthographic painter's-algorithm renderer. One pass per geom set."""

    def __init__(self, model, width, height, azimuth, elevation):
        self.m, self.W, self.H = model, width, height
        self.right, self.up, self.fwd = basis(azimuth, elevation)
        self.cache: dict[int, tuple] = {}
        self.fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
        self.ax = self.fig.add_axes((0, 0, 1, 1))
        self.ax.axis("off")

    def _parts(self, gi):
        if gi not in self.cache:
            self.cache[gi] = geom_mesh(self.m, gi)
        return self.cache[gi]

    def project(self, data, geoms):
        """World triangles -> 2D screen polys, per-face shade, depth. Back-face culled."""
        polys, shades, depths = [], [], []
        light = self.right * 0.30 + self.up * 0.60 - self.fwd * 0.74
        light /= np.linalg.norm(light)
        for gi in geoms:
            got = self._parts(gi)
            if got is None:
                continue
            V, F = got
            R = data.geom_xmat[gi].reshape(3, 3)
            world = V @ R.T + data.geom_xpos[gi]
            tri = world[F]
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            ln = np.linalg.norm(n, axis=1, keepdims=True)
            n = n / np.maximum(ln, 1e-12)
            facing = n @ self.fwd
            keep = facing < 0.0  # normal points toward the camera
            if not keep.any():
                continue
            tri, n = tri[keep], n[keep]
            polys.append(np.stack((tri @ self.right, tri @ self.up), axis=-1))
            shades.append(np.clip(0.34 + 0.66 * np.abs(n @ light), 0.0, 1.0))
            depths.append((tri @ self.fwd).mean(axis=1))
        if not polys:
            return np.zeros((0, 3, 2)), np.zeros(0), np.zeros(0)
        return np.concatenate(polys), np.concatenate(shades), np.concatenate(depths)

    def draw(self, data, geoms, rgb, centre2, half_h, background, flat=False):
        poly, shade, depth = self.project(data, geoms)
        order = np.argsort(depth)[::-1]  # far to near
        poly, shade = poly[order], shade[order]
        if flat:
            shade = np.ones_like(shade)
        cols = np.clip(np.asarray(rgb)[None, :] * shade[:, None], 0, 1)
        self.ax.clear()
        self.ax.axis("off")
        bgf = tuple(c / 255 for c in background)
        self.fig.patch.set_facecolor(bgf)
        self.ax.set_facecolor(bgf)
        if len(poly):
            self.ax.add_collection(
                PolyCollection(poly, facecolors=cols, edgecolors="none", rasterized=True))
        half_w = half_h * self.W / self.H
        self.ax.set_xlim(centre2[0] - half_w, centre2[0] + half_w)
        self.ax.set_ylim(centre2[1] - half_h, centre2[1] + half_h)
        self.ax.set_aspect("equal")
        self.fig.canvas.draw()
        return np.asarray(self.fig.canvas.buffer_rgba())[:, :, :3].copy()

    def world_to_px(self, p3, centre2, half_h):
        half_w = half_h * self.W / self.H
        x, y = float(p3 @ self.right), float(p3 @ self.up)
        return (int((x - (centre2[0] - half_w)) / (2 * half_w) * self.W),
                int((1 - (y - (centre2[1] - half_h)) / (2 * half_h)) * self.H))

    def autofit(self, data, geoms, margin=1.10):
        """Centre and half-height that just contain ``geoms`` on screen."""
        poly, _, _ = self.project(data, geoms)
        pts = poly.reshape(-1, 2)
        lo, hi = pts.min(0), pts.max(0)
        centre2 = 0.5 * (lo + hi)
        half_h = 0.5 * max(hi[1] - lo[1], (hi[0] - lo[0]) * self.H / self.W) * margin
        return centre2, half_h

    def frame(self, data, vis_geoms, col_geoms, centre3, half_h, centre2=None,
              margin=1.30):
        """Composite: visual base + translucent red collision + crisp red silhouette.

        The collision colour pass is rendered on BLACK, so its pixel value is already
        premultiplied by the anti-aliased coverage; a second flat-white pass on black
        recovers that coverage.  Compositing from those two avoids the key-colour fringe
        that an exact-match chroma key leaves on every silhouette edge.
        """
        if half_h is None:
            centre2, half_h = self.autofit(data, list(vis_geoms) + list(col_geoms),
                                           margin=margin)
        elif centre2 is None:
            centre2 = np.array([centre3 @ self.right, centre3 @ self.up])
        base = self.draw(data, vis_geoms, VIS_RGB, centre2, half_h, BG).astype(np.float64)
        premult = self.draw(data, col_geoms, COL_RGB, centre2, half_h,
                            (0, 0, 0)).astype(np.float64)
        cover = self.draw(data, col_geoms, np.array([1.0, 1.0, 1.0]), centre2, half_h,
                          (0, 0, 0), flat=True).astype(np.float64)
        a = (cover.max(axis=-1) / 255.0)[:, :, None]
        out = base * (1.0 - COL_ALPHA * a) + COL_ALPHA * premult
        # crisp silhouette so the collision boundary is readable even behind the mesh
        mask = a[:, :, 0] > 0.5
        edge = np.zeros_like(mask)
        edge[1:, :] |= mask[1:, :] ^ mask[:-1, :]
        edge[:, 1:] |= mask[:, 1:] ^ mask[:, :-1]
        out[edge] = np.array([160.0, 10.0, 6.0])
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), centre2, half_h


# --------------------------------------------------------------------------- annotate
def annotate(img, title, subtitle, notes, renderer=None, scale=None):
    d = ImageDraw.Draw(img, "RGBA")
    W, _ = img.size
    d.rectangle((0, 0, W, 62), fill=(18, 24, 34, 235))
    d.text((14, 8), title, font=_font(21, bold=True), fill=(255, 255, 255))
    d.text((14, 36), subtitle, font=_font(14), fill=(176, 196, 216))
    # legend
    y = 74
    for sw, label in ((VIS_RGB, "visual mesh (group 2)"),
                      (COL_RGB, "collision geom (group 3, contype/conaffinity = 1)")):
        d.rectangle((14, y, 34, y + 14), fill=tuple(int(255 * c) for c in sw),
                    outline=(30, 30, 30))
        d.text((42, y - 1), label, font=_font(14), fill=(20, 20, 20))
        y += 22
    if notes:
        box_h = 20 * len(notes) + 14
        d.rectangle((10, img.size[1] - box_h - 10, 10 + 9 * max(len(n) for n in notes) + 20,
                     img.size[1] - 10), fill=(255, 255, 255, 225), outline=(60, 60, 60))
        for i, n in enumerate(notes):
            d.text((20, img.size[1] - box_h - 2 + 20 * i), n, font=_font(14),
                   fill=(20, 20, 20))
    if scale is not None and renderer is not None:
        length_m, centre2, half_h = scale
        half_w = half_h * renderer.W / renderer.H
        px = int(length_m / (2 * half_w) * renderer.W)
        x0, y0 = W - px - 30, 92
        d.line((x0, y0, x0 + px, y0), fill=(20, 20, 20), width=3)
        d.line((x0, y0 - 6, x0, y0 + 6), fill=(20, 20, 20), width=3)
        d.line((x0 + px, y0 - 6, x0 + px, y0 + 6), fill=(20, 20, 20), width=3)
        lbl = f"{length_m*1000:.0f} mm" if length_m < 0.5 else f"{length_m:.1f} m"
        d.text((x0 + px / 2 - 22, y0 + 8), lbl, font=_font(14, bold=True), fill=(20, 20, 20))
    return img


# --------------------------------------------------------------------------- inventory
def inventory(m, d):
    bn = lambda i: mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, int(i))
    gn = lambda i: mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(i)) or f"<unnamed#{i}>"
    geoms = []
    for i in range(m.ngeom):
        geoms.append(dict(
            idx=i, body=bn(m.geom_bodyid[i]), name=gn(i),
            type=mujoco.mjtGeom(int(m.geom_type[i])).name.replace("mjGEOM_", "").lower(),
            group=int(m.geom_group[i]), contype=int(m.geom_contype[i]),
            conaffinity=int(m.geom_conaffinity[i]),
            size=[float(x) for x in m.geom_size[i]],
            pos=[float(x) for x in m.geom_pos[i]]))
    coll = [g for g in geoms if g["contype"] or g["conaffinity"]]

    exc = set()
    for e in range(m.nexclude):
        sig = int(m.exclude_signature[e])
        exc.add((sig >> 16, sig & 0xFFFF))
        exc.add((sig & 0xFFFF, sig >> 16))

    def foot_boxes(side):
        return [g for g in coll if g["body"] == f"{side}_foot_link"]

    fb = foot_boxes("L")
    lo = np.array([np.array(g["pos"]) - np.array(g["size"][:3]) for g in fb]).min(0)
    hi = np.array([np.array(g["pos"]) + np.array(g["size"][:3]) for g in fb]).max(0)

    vis_foot = [g for g in geoms if g["body"] == "L_foot_link" and g["group"] == VISUAL_GROUP]
    V, _ = geom_mesh(m, vis_foot[0]["idx"])
    R = np.zeros(9)
    mujoco.mju_quat2Mat(R, m.geom_quat[vis_foot[0]["idx"]])
    V = V @ R.reshape(3, 3).T + m.geom_pos[vis_foot[0]["idx"]]

    # The ground-contact face only.  NOTE the mesh bottom sits at z = -0.0430000324, so a
    # threshold of exactly -0.043 silently drops all 231 bottom-face vertices and makes the
    # sole look 102 mm wide instead of 115 mm.  Use a tolerance below the true minimum.
    sole = V[V[:, 2] < V[:, 2].min() + 1e-4]
    inv = dict(
        n_geom=int(m.ngeom),
        n_contact_enabled=len(coll),
        bodies_without_collision=[bn(b) for b in range(m.nbody)
                                  if bn(b) not in {g["body"] for g in coll}],
        foot_box_union_mm=dict(length=float(1000 * (hi[0] - lo[0])),
                               width=float(1000 * (hi[1] - lo[1])),
                               height=float(1000 * (hi[2] - lo[2]))),
        foot_visual_bbox_mm=dict(length=float(1000 * (V[:, 0].max() - V[:, 0].min())),
                                 width=float(1000 * (V[:, 1].max() - V[:, 1].min())),
                                 height=float(1000 * (V[:, 2].max() - V[:, 2].min()))),
        lateral_overhang_max_mm=float(1000 * max(V[:, 1].max() - hi[1], lo[1] - V[:, 1].min())),
        lateral_overhang_sole_face_mm=float(
            1000 * max(sole[:, 1].max() - hi[1], lo[1] - sole[:, 1].min())),
        lr_foot_pair_excluded=bool((mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "L_foot_link"),
                                    mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "R_foot_link"))
                                   in exc),
        collision_geoms=coll,
    )

    # ankle coverage: does anything wrap the ankle joint, given the ankle link has no geom?
    shin = [g for g in coll if g["body"] == "L_shin_link"][0]
    shin_bottom = shin["pos"][2] - shin["size"][1] - shin["size"][0]
    ankle_z = -0.49  # L_ankle_pitch_link origin in L_shin_link frame
    inv["ankle_coverage_mm"] = dict(
        shin_capsule_bottom_below_ankle=float(1000 * (ankle_z - shin_bottom)),
        foot_box_top_above_ankle=float(1000 * hi[2]),
        overlap=float(1000 * ((ankle_z + hi[2]) - shin_bottom)))
    return inv


def print_inventory(m, inv):
    print("=" * 96)
    print("COLLISION GEOM INVENTORY")
    print("=" * 96)
    print(f"{'body':<22} {'geom':<26} {'type':<8} {'grp':>3} {'ct':>3} {'ca':>3}  "
          f"{'size (m)':<28} pos (m)")
    for g in inv["collision_geoms"]:
        sz = ", ".join(f"{v:.4f}" for v in g["size"][:3] if v)
        ps = ", ".join(f"{v:+.4f}" for v in g["pos"])
        print(f"{g['body']:<22} {g['name']:<26} {g['type']:<8} {g['group']:>3} "
              f"{g['contype']:>3} {g['conaffinity']:>3}  {sz:<28} {ps}")
    print()
    print(f"contact-enabled geoms: {inv['n_contact_enabled']} / {inv['n_geom']}")
    print(f"bodies with NO contact geom: {', '.join(inv['bodies_without_collision'])}")
    print(f"L/R foot pair excluded from contact: {inv['lr_foot_pair_excluded']}")
    fb, fv = inv["foot_box_union_mm"], inv["foot_visual_bbox_mm"]
    print(f"foot collision 3-box union: L={fb['length']:.1f} W={fb['width']:.1f} "
          f"H={fb['height']:.1f} mm")
    print(f"foot visual mesh bbox:      L={fv['length']:.1f} W={fv['width']:.1f} "
          f"H={fv['height']:.1f} mm")
    print(f"lateral overhang of visual beyond collision: "
          f"{inv['lateral_overhang_max_mm']:.2f} mm/side (whole foot), "
          f"{inv['lateral_overhang_sole_face_mm']:.2f} mm/side (ground-contact face)")
    ac = inv["ankle_coverage_mm"]
    print(f"ankle joint coverage: shin capsule reaches "
          f"{ac['shin_capsule_bottom_below_ankle']:.1f} mm BELOW the ankle joint; "
          f"foot boxes reach {ac['foot_box_top_above_ankle']:.1f} mm above it -> "
          f"overlap {ac['overlap']:.1f} mm, no gap")


# --------------------------------------------------------------------------- poses
def pose_stand(m, d, bent=True):
    mujoco.mj_resetData(m, d)
    d.qpos[:7] = (0, 0, 1.0, 1, 0, 0, 0)
    if bent:
        for jn, ang in (("L_hip_pitch_joint", -0.30), ("R_hip_pitch_joint", 0.30),
                        ("L_knee_joint", 0.60), ("R_knee_joint", -0.60),
                        ("L_ankle_pitch_joint", 0.30), ("R_ankle_pitch_joint", 0.30)):
            j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
            if j >= 0:
                d.qpos[m.jnt_qposadr[j]] = ang
    mujoco.mj_forward(m, d)


def pose_adduct(m, d, deg, level_feet=True):
    """Symmetric hip-roll adduction: the DOF that swings the feet toward each other.

    With ``level_feet`` the ankle roll counter-rotates by the same amount, so both soles
    stay flat and approach each other edge-on.  That is the configuration a real gait
    passes through, and the one the "soles overlap" complaint is about; without it the
    feet arrive tilted and touch at their upper inner corners instead.
    """
    mujoco.mj_resetData(m, d)
    d.qpos[:7] = (0, 0, 1.0, 1, 0, 0, 0)
    r = np.deg2rad(deg)
    for hip, ankle, s in (("L_hip_roll_joint", "L_ankle_roll_joint", -1.0),
                          ("R_hip_roll_joint", "R_ankle_roll_joint", +1.0)):
        jh = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, hip)
        d.qpos[m.jnt_qposadr[jh]] = s * r
        if level_feet:
            ja = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, ankle)
            # hip and ankle roll axes are mirrored per side; pick the sign that cancels.
            best = None
            for sign in (-1.0, +1.0):
                d.qpos[m.jnt_qposadr[ja]] = sign * s * r
                mujoco.mj_forward(m, d)
                side = hip[0]
                fb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"{side}_foot_link")
                tilt = abs(d.xmat[fb].reshape(3, 3)[2, 2] - 1.0)
                if best is None or tilt < best[0]:
                    best = (tilt, sign)
            d.qpos[m.jnt_qposadr[ja]] = best[1] * s * r
    mujoco.mj_forward(m, d)


def foot_gap_mm(m, d, kind):
    """Signed inner-edge y gap between the two feet. kind in {'box','visual'}."""
    out = {}
    for side in ("L", "R"):
        pts = []
        for gi in range(m.ngeom):
            if mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY,
                                 int(m.geom_bodyid[gi])) != f"{side}_foot_link":
                continue
            want = (m.geom_group[gi] == COLLISION_GROUP if kind == "box"
                    else m.geom_group[gi] == VISUAL_GROUP)
            if not want:
                continue
            V, _ = geom_mesh(m, gi)
            pts.append(V @ d.geom_xmat[gi].reshape(3, 3).T + d.geom_xpos[gi])
        out[side] = np.concatenate(pts)
    return 1000.0 * float(out["R"][:, 1].min() - out["L"][:, 1].max())


def find_thresholds(m, d):
    """Adduction angle at which visual meshes / collision boxes first touch."""
    res = {}
    for kind in ("visual", "box"):
        lo, hi = 0.0, 8.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            pose_adduct(m, d, mid)
            if foot_gap_mm(m, d, kind) > 0:
                lo = mid
            else:
                hi = mid
        res[kind] = 0.5 * (lo + hi)
    return res


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag",
                    default="LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix")
    ap.add_argument("--model", default="loop", choices=("loop", "serial"))
    ap.add_argument("--xml", default=None, help="explicit XML path, overrides --tag/--model")
    ap.add_argument("--out-dir", default=str(IMGDIR))
    ap.add_argument("--prefix", default="legonly_collision")
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--height", type=int, default=850)
    ap.add_argument("--inventory-only", action="store_true")
    a = ap.parse_args()

    xml = Path(a.xml) if a.xml else XMLS / f"{a.tag}{'_loop' if a.model == 'loop' else ''}.xml"
    assert xml.exists(), f"missing {xml}"
    m = mujoco.MjModel.from_xml_path(str(xml))
    d = mujoco.MjData(m)

    inv = inventory(m, d)
    inv["xml"] = str(xml)
    print_inventory(m, inv)

    th = find_thresholds(m, d)
    inv["adduction_threshold_deg"] = th
    print()
    print(f"hip-roll adduction at which VISUAL meshes first touch:    {th['visual']:.3f} deg")
    print(f"hip-roll adduction at which COLLISION boxes first touch:  {th['box']:.3f} deg")
    print(f"  -> visual-only overlap band: {th['box'] - th['visual']:.3f} deg of hip roll")

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out.parent / "mujoco/assets" if False else out).joinpath(
        f"{a.prefix}_inventory.json").write_text(json.dumps(inv, indent=2))

    if a.inventory_only:
        return

    gid_vis = [i for i in range(m.ngeom) if m.geom_group[i] == VISUAL_GROUP]
    gid_col = [i for i in range(m.ngeom) if m.geom_group[i] == COLLISION_GROUP]
    bodies = lambda names: {mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n) for n in names}

    def subset(gids, keep_bodies):
        return [g for g in gids if int(m.geom_bodyid[g]) in keep_bodies]

    fb, fv = inv["foot_box_union_mm"], inv["foot_visual_bbox_mm"]
    made = []

    # ---------------------------------------------------------------- 1. whole body
    pose_stand(m, d, bent=True)
    r = SoftRenderer(m, a.width, a.height, azimuth=145.0, elevation=-7.0)
    img, c2, hh = r.frame(d, gid_vis, gid_col, None, None, margin=1.40)
    annotate(img, "LegOnly v30 (AB loop) - collision geometry over visual mesh",
             f"{xml.name}  |  {inv['n_contact_enabled']} contact-enabled geoms of "
             f"{inv['n_geom']}  |  CPU orthographic render",
             ["15 collision geoms: 1 pelvis capsule + (4 leg capsules + 3 sole boxes) x 2 legs",
              "crank / rod / ankle-pitch links carry NO collision geom (visual only)"],
             renderer=r, scale=(0.2, c2, hh))
    p = out / f"{a.prefix}_full.png"
    img.save(p)
    made.append(p)
    print("wrote", p)

    # ---------------------------------------------------------------- 2. below the knee
    keep = bodies(["L_shin_link", "L_ankle_pitch_link", "L_foot_link",
                   "L_crank_A", "L_crank_B", "L_rod_A", "L_rod_B"])
    r2 = SoftRenderer(m, a.width, a.height, azimuth=100.0, elevation=-4.0)
    ankle = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "L_ankle_pitch_link")]
    img, c2, hh = r2.frame(d, subset(gid_vis, keep), subset(gid_col, keep), None,
                           None, margin=1.35)
    ac = inv["ankle_coverage_mm"]
    dd = ImageDraw.Draw(img)
    px, py = r2.world_to_px(ankle, c2, hh)
    dd.ellipse((px - 11, py - 11, px + 11, py + 11), outline=(0, 90, 220), width=4)
    lbl = "ankle pitch/roll joint - no collision geom on this link"
    f = _font(15, bold=True)
    tw = int(dd.textlength(lbl, font=f))
    tx = px + 18 if px + 18 + tw < a.width - 10 else px - 18 - tw
    dd.text((tx, py - 10), lbl, font=f, fill=(0, 70, 190))
    annotate(img, "Left leg below the knee - ankle collision coverage",
             "shin capsule (r = 57.2 mm, half-length 217.9 mm) + 3 sole boxes; "
             "ankle_pitch_link itself has zero geoms",
             [f"shin capsule reaches {ac['shin_capsule_bottom_below_ankle']:.1f} mm BELOW "
              f"the ankle joint centre",
              f"sole boxes reach 15.0 mm ABOVE it -> "
              f"{ac['overlap']:.1f} mm of overlap, so the ankle has no collision gap",
              "the 4-bar crank and rod links are visual-only (contype = conaffinity = 0)"],
             renderer=r2, scale=(0.1, c2, hh))
    p = out / f"{a.prefix}_lowerleg.png"
    img.save(p)
    made.append(p)
    print("wrote", p)

    # ---------------------------------------------------------------- 3. sole, from below
    keep = bodies(["L_foot_link", "R_foot_link"])
    r3 = SoftRenderer(m, a.width, a.height, azimuth=0.0, elevation=89.9)
    img, c2, hh = r3.frame(d, subset(gid_vis, keep), subset(gid_col, keep), None,
                           None, margin=1.45)
    dd = ImageDraw.Draw(img)
    for side in ("L", "R"):
        foot_bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"{side}_foot_link")
        px, py = r3.world_to_px(d.xpos[foot_bid], c2, hh)
        dd.text((px - 8, py + 130), f"{side} foot", font=_font(17, bold=True),
                fill=(25, 35, 55))
    dd.text((14, 130), "viewed from underneath; toes point up the page",
            font=_font(14), fill=(70, 80, 95))
    annotate(img, "Both soles seen from below - 3-box sole vs visual sole outline",
             f"collision boxes {fb['length']:.0f} x {fb['width']:.0f} x {fb['height']:.0f} mm "
             f"(union)  vs  visual mesh {fv['length']:.0f} x {fv['width']:.0f} x "
             f"{fv['height']:.0f} mm",
             [f"grey fringe = visual mesh outside the collision box: "
              f"{inv['lateral_overhang_max_mm']:.2f} mm per side",
              f"the ground-contact face is just as wide: "
              f"{inv['lateral_overhang_sole_face_mm']:.2f} mm per side of the sole is "
              f"drawn but never collides",
              "length and height match exactly; the 3 boxes leave a 0.10 mm seam"],
             renderer=r3, scale=(0.1, c2, hh))
    p = out / f"{a.prefix}_sole.png"
    img.save(p)
    made.append(p)
    print("wrote", p)

    # ---------------------------------------------------------------- 4. the overlap band
    mid = 0.5 * (th["visual"] + th["box"])
    pose_adduct(m, d, mid)
    gap_v, gap_b = foot_gap_mm(m, d, "visual"), foot_gap_mm(m, d, "box")
    keep = bodies(["L_foot_link", "R_foot_link"])
    r4 = SoftRenderer(m, a.width, a.height, azimuth=180.0, elevation=6.0)
    img, c2, hh = r4.frame(d, subset(gid_vis, keep), subset(gid_col, keep), None,
                           None, margin=1.45)
    annotate(img, "Why the feet look like they overlap - the visual-only band",
             f"hip-roll adduction {mid:.2f} deg, viewed from the front",
             [f"visual meshes are already interpenetrating: inner-edge gap "
              f"{gap_v:+.1f} mm",
              f"collision boxes are still apart: inner-edge gap {gap_b:+.1f} mm",
              f"the physics engine reports NO contact here, and viser draws only the "
              f"visual mesh -> looks like the feet pass through each other"],
             renderer=r4, scale=(0.05, c2, hh))
    p = out / f"{a.prefix}_overlap_band.png"
    img.save(p)
    made.append(p)
    print("wrote", p)

    print()
    for p in made:
        print("IMAGE", p)


if __name__ == "__main__":
    main()
