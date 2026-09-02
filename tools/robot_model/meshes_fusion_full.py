#!/usr/bin/env python3
"""Stage a complete, current Pygmalion visual-mesh set from the live Fusion document.

The CAD document is never edited or saved.  Bodies are tessellated through Fusion's
``meshManager``, fetched in bounded chunks by :mod:`upper_meshes_fusion`, classified with the
same rigid-body rules as :mod:`massprops_fusion`, transformed from root-CAD centimetres to
link-frame simulator metres, and written only below ``--out``.  Nothing in the active robot
asset directory is replaced by this program.

Visual meshes intentionally omit catalogue motors, bearings and fasteners.  Their mass and
inertia remain in the rigid-body data; motors are rendered as measured analytic cylinders by
``build_robot.py``.  This keeps simulator visuals tractable while preserving every structural
body whose shape can affect envelope or self-collision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/fusion"))
sys.path.insert(0, str(REPO / "tools/robot_model"))
import mcp_client as M  # noqa: E402
import massprops_fusion as MP  # noqa: E402
from upper_meshes_fusion import Fetcher  # noqa: E402

R_SIM = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
HIP = np.array([-123.7, 70.0, 60.0])
ORIGIN = {
    "pelvis": np.array([0.0, 70.0, 60.0]),
    "hip_pitch_link": HIP, "hip_roll_link": HIP, "thigh": HIP,
    "shin": np.array([-123.7, 115.0, -310.0]),
    "ankle_pitch_link": np.array([-123.7, 145.0, -800.0]),
    "foot": np.array([-123.7, 145.0, -800.0]),
    "torso": np.array([0.0, 70.0, 177.5]),
    "shoulder_pitch_link": np.array([-200.0, 85.0, 540.0]),
    "arm": np.array([-200.0, 85.0, 540.0]),
}

FASTENER = re.compile(
    r"ISO ?10642|ISO ?4762|JIS B1176|Hexagon|Washer|\bNut\b|\bScrew\b|DIN |GB/T|SHCS|FHCS",
    re.I,
)
BEARING = re.compile(r"6900ZZ|6810ZZ|6814ZZ|CRBS|JMC-JS06|\bbearing\b", re.I)

LIST_SCRIPT = r'''
import adsk.core, adsk.fusion, json
def run(_c):
    app=adsk.core.Application.get()
    root=adsk.fusion.Design.cast(app.activeProduct).rootComponent
    # E2Box-IMU removed from this block 2026-09-02: it used to be blocked outright (nobody
    # wanted the IMU board modelled), but massprops_fusion.classify() now routes it to
    # pelvis (docs: the physical E2Box IMU, previously silently dropped, "missing" against
    # the teammate's huphy_mjcf repo which models it) -- if the LIVE LISTING itself still
    # excludes it, classify() never even sees a row to route, no matter how main()'s Python
    # selection logic filters. Robstride/fastener/bearing exclusions are unrelated and stay:
    # motors are drawn as primitives, not meshed, by a separate, deliberate convention.
    block=("NotUse","fullDoF","REF","NoSim","Robstride",
           "ISO 10642","ISO4762","ISO 4762","JIS B1176","Hexagon","Washer","Screw",
           "6900ZZ","6810ZZ","6814ZZ","CRBS","JMC-JS06")
    out=[]; stack=[]
    for i in range(root.occurrences.count): stack.append((root.occurrences.item(i),"",True))
    while stack:
        o,path,live=stack.pop(); live=live and o.isLightBulbOn; p=path+"/"+o.name
        for i in range(o.bRepBodies.count):
            b=o.bRepBodies.item(i); key=p+"::"+b.name
            if any(x in key for x in block): continue
            pr=b.physicalProperties
            out.append([p,i,b.name,pr.mass,pr.volume,
                        [pr.centerOfMass.x,pr.centerOfMass.y,pr.centerOfMass.z],
                        b.material.name if b.material else "?",bool(live and b.isLightBulbOn)])
        for i in range(o.childOccurrences.count): stack.append((o.childOccurrences.item(i),p,live))
    print(json.dumps({"doc":app.activeDocument.name,"rows":out}))
'''


def mirror_y(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    out = mesh.copy()
    out.vertices[:, 1] *= -1
    out.faces = out.faces[:, [0, 2, 1]]
    return out


def link_mesh(parts: list[trimesh.Trimesh], origin: np.ndarray) -> trimesh.Trimesh:
    if not parts:
        raise RuntimeError("empty rigid-body mesh group")
    mesh = trimesh.util.concatenate(parts)
    mesh.vertices = (mesh.vertices * 10.0 - origin) @ R_SIM.T / 1000.0
    mesh.remove_unreferenced_vertices()
    return mesh


def write_group(name: str, parts: list[trimesh.Trimesh], origin: np.ndarray,
                out: Path, mirror: bool = True) -> dict:
    mesh = link_mesh(parts, origin)
    hull = mesh.convex_hull
    files = [(name, mesh), (name + "_hull", hull)]
    if mirror:
        files += [("R_" + name, mirror_y(mesh)), ("R_" + name + "_hull", mirror_y(hull))]
    hashes = {}
    for stem, obj in files:
        path = out / f"{stem}.stl"
        obj.export(path)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    bounds = mesh.bounds
    return {
        "parts": len(parts), "vertices": int(len(mesh.vertices)), "faces": int(len(mesh.faces)),
        "bbox_m": np.round(bounds[1] - bounds[0], 5).tolist(), "files_sha256": hashes,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "tools/robot_model/fusion_snapshots/v30_inspection/meshes")
    ap.add_argument("--cache", type=Path,
                    help="shared per-body NPZ cache (default: OUT/.parts)")
    ap.add_argument("--expect", default="260819_HumanMesh_wUpper_OMAKASE_RrecoverFromCrash")
    ap.add_argument("--quality", default="Low", choices=("Low", "Medium", "High"))
    ap.add_argument("--chunk", type=int, default=16000)
    ap.add_argument("--include-fasteners", action="store_true")
    ap.add_argument("--include-torso-rework", action="store_true",
                    help="include Torso2ShoulderP, previously excluded by the user's 2026-08-26 scope")
    ap.add_argument("--leg-only", action="store_true",
                    help="stage only geometry below the waist flange for the 12-DOF LegOnly model")
    ap.add_argument("--limit", type=int, default=0, help="smoke-test only: fetch at most N bodies")
    args = ap.parse_args()

    M.connect()
    listing = None
    for attempt in range(4):
        try:
            payload = M.printed(LIST_SCRIPT).strip()
            if not payload:
                raise RuntimeError("empty stdout")
            listing = json.loads(payload)
            break
        except RuntimeError as exc:
            if attempt == 3:
                raise RuntimeError(f"Fusion body listing failed after 4 tries: {exc}") from exc
            print(f"transient missing body listing; retry {attempt + 1}/3", flush=True)
            time.sleep(0.75 * (attempt + 1))
    assert listing is not None
    if not listing["doc"].startswith(args.expect):
        raise SystemExit(f"active document {listing['doc']!r} does not match {args.expect!r}")

    selected = []
    skipped = {"alternative": 0, "motor": 0, "fastener_or_bearing": 0,
               "unclassified": 0, "leg_only_cut": 0}
    for occ_path, idx, body_name, mass, volume, com_cm, material, live in listing["rows"]:
        key = occ_path + "::" + body_name
        if args.leg_only and (occ_path.startswith("/Joints_UpperBody")
                              or "::Baselink_toWaistYaw" in key
                              or "Robstride RS04 - Waist_Yaw" in key):
            skipped["leg_only_cut"] += 1
            continue
        if MP.is_alternative(key):
            skipped["alternative"] += 1; continue
        who = MP.classify(key)
        if who is None and args.include_torso_rework and "Torso2ShoulderP" in key:
            who = "torso"
        if who is None:
            skipped["unclassified"] += 1; continue
        if MP.family(key):
            skipped["motor"] += 1; continue
        if not args.include_fasteners and (FASTENER.search(key) or BEARING.search(key)):
            skipped["fastener_or_bearing"] += 1; continue
        selected.append({"occ": occ_path, "idx": idx, "name": body_name, "key": key,
                         "who": who, "mass": mass, "volume": volume,
                         "com_mm": (np.asarray(com_cm) * 10.0).tolist(),
                         "material": material, "live": live})

    selected.sort(key=lambda x: x["key"])
    if args.limit:
        selected = selected[:args.limit]
    print(f"document: {listing['doc']}")
    print(f"selected structural bodies: {len(selected)} · skipped {skipped}", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    part_cache = args.cache or (args.out / ".parts")
    part_cache.mkdir(exist_ok=True)
    fetcher = Fetcher(quality=args.quality, chunk=args.chunk)
    groups: dict[str, list[trimesh.Trimesh]] = {k: [] for k in ORIGIN}
    loop_groups: dict[str, list[trimesh.Trimesh]] = {
        "crank_A": [], "crank_B": [], "rod_A": [], "rod_B": [],
        "shin_noloop": [], "foot_noloop": [],
    }
    hip_pitch_flange_raw: list[trimesh.Trimesh] = []
    torso2shoulderp_raw: list[trimesh.Trimesh] = []
    fetched = []
    for n, rec in enumerate(selected, 1):
        cache_key = hashlib.sha256(rec["key"].encode()).hexdigest()[:20]
        cache_path = part_cache / f"{cache_key}.npz"
        if cache_path.exists():
            saved = np.load(cache_path)
            v, f = saved["v"], saved["f"]
            source = "cache"
        else:
            v, f = fetcher.body(rec["occ"], rec["idx"])
            np.savez_compressed(cache_path, v=v, f=f)
            source = "Fusion"
        mesh = trimesh.Trimesh(v.reshape(-1, 3), f.reshape(-1, 3), process=False)
        who = rec["who"]
        if who == "ANKLE_SPLIT":
            z = rec["com_mm"][2]
            tag = next((t for t in "AB" if rec["name"].startswith(f"Crank_{t}")), None)
            rod = next((t for t in "AB" if rec["name"] == f"Arm_{t}"), None)
            if tag:
                groups["shin"].append(mesh); loop_groups[f"crank_{tag}"].append(mesh)
            elif rod:
                groups["shin"].append(mesh); loop_groups[f"rod_{rod}"].append(mesh)
            elif abs(z + 800.0) < 0.6:
                groups["ankle_pitch_link"].append(mesh)
            elif z < -800.0:
                groups["foot"].append(mesh); loop_groups["foot_noloop"].append(mesh)
            else:
                groups["shin"].append(mesh); loop_groups["shin_noloop"].append(mesh)
        else:
            groups[who].append(mesh)
            if who == "shin": loop_groups["shin_noloop"].append(mesh)
            if who == "foot": loop_groups["foot_noloop"].append(mesh)
            # pelvis is exempt from write_group's automatic mirror=True copy (it is one
            # shared body, not a per-side one, so most of its content is already whole-CAD
            # symmetric) -- but HipPitchFlange (2026-09-02 reclassification, see
            # massprops_fusion.classify) is single-leg CAD data like any other hip part, and
            # massprops.collect() already mirrors ITS mass onto the R side. Without the same
            # mesh mirror here the mass is right but the R-side bracket is invisible, which
            # is exactly what the user's viewer review first reported as a "missing
            # R_hip_pitch motor mount bracket".
            #
            # mirror_y() must run on a mesh already in LINK-LOCAL SIM-FRAME coordinates (the
            # write_group/link_mesh convention every other mirrored body relies on) -- but
            # here we are still inside the per-body fetch loop, where `mesh` is raw Fusion
            # assembly-space centimetres, untouched by link_mesh's CAD->sim rotation or the
            # pelvis-origin subtraction. Mirroring at THIS stage negates the wrong axis
            # entirely (assembly Y, not sim Y / robot left-right) and produces exactly the
            # garbled, disconnected geometry the user's screenshot showed. So: collect the
            # raw part here, transform+mirror it correctly AFTER link_mesh runs, in main()
            # below (see hip_pitch_flange_raw).
            if who == "pelvis" and "HipPitchFlange" in rec["key"]:
                hip_pitch_flange_raw.append(mesh)
            # Same one-sided-CAD gap, this time on torso: Torso2ShoulderP (2026-09-02,
            # reinstated) is single-arm data like HipPitchFlange was single-leg -- same
            # premature-mirror trap applies, same raw-collect-then-splice-after-link_mesh fix.
            if who == "torso" and "Torso2ShoulderP" in rec["key"]:
                torso2shoulderp_raw.append(mesh)
        fetched.append({k: rec[k] for k in ("key", "who", "mass", "volume", "material", "live")})
        print(f"[{n:3d}/{len(selected):3d}] {who:22s} {rec['name'][:42]:42s} "
              f"{len(mesh.faces):7d} tris  [{source}]", flush=True)

    if args.limit:
        print("--limit smoke test complete; no grouped STL set was published")
        return

    loop_points = json.load(open("/home/syaro/pyg_fea/fusion/ankle_loop_points_v3_printed.json"))
    origins = dict(ORIGIN)
    for tag in "AB":
        origins[f"crank_{tag}"] = np.asarray(loop_points[tag]["motor"])
        origins[f"rod_{tag}"] = np.asarray(loop_points[tag]["pin"])
    origins["shin_noloop"] = ORIGIN["shin"]
    origins["foot_noloop"] = ORIGIN["foot"]

    stats = {}
    for name, parts in {**groups, **loop_groups}.items():
        if name == "ankle_pitch_link" or not parts:
            continue
        stats[name] = write_group(name, parts, origins[name], args.out,
                                  mirror=name not in ("pelvis", "torso"))
        print(f"wrote {name:22s}: {stats[name]['parts']:3d} parts · "
              f"{stats[name]['faces']:8d} faces · bbox {stats[name]['bbox_m']}")

    def splice_mirror(raw_parts: list[trimesh.Trimesh], group: str, label: str) -> None:
        """Transform `raw_parts` into `group`'s link-local sim-frame coordinates (same
        link_mesh call write_group already used for the rest of that group's parts), mirror
        the result (mirror_y expects exactly that frame -- see hip_pitch_flange_raw's
        comment above for why this must happen AFTER link_mesh, not before), and splice the
        mirrored copy onto the {group}.stl/_hull.stl write_group already wrote to disk.
        Use for single-sided CAD data (one leg, one arm) that classify() routes onto a
        SHARED body (pelvis, torso) instead of a per-side one -- write_group's own
        mirror=True only mirrors a whole per-side group, not one part inside a shared one.
        """
        if not raw_parts:
            return
        mirrored = mirror_y(link_mesh(raw_parts, origins[group]))
        path, hull_path = args.out / f"{group}.stl", args.out / f"{group}_hull.stl"
        merged = trimesh.util.concatenate([trimesh.load(path, process=False), mirrored])
        merged.export(path)
        merged.convex_hull.export(hull_path)
        stats[group]["files_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        stats[group]["files_sha256"][hull_path.name] = hashlib.sha256(hull_path.read_bytes()).hexdigest()
        print(f"spliced {label} mirror onto {group}: +{len(mirrored.faces)} faces "
              f"({path.name} and {hull_path.name} re-exported)")

    splice_mirror(hip_pitch_flange_raw, "pelvis", "HipPitchFlange")
    splice_mirror(torso2shoulderp_raw, "torso", "Torso2ShoulderP")

    manifest = {
        "tag": "fusion-v30-inspection", "status": "STAGED; not promoted to training assets",
        "document": listing["doc"], "quality": args.quality, "chunk_values": fetcher.chunk,
        "cad_to_sim": "sim=(-cad_y,cad_x,cad_z); CAD cm -> link-frame m",
        "include_fasteners": args.include_fasteners,
        "include_torso_rework": args.include_torso_rework,
        "leg_only": args.leg_only,
        "leg_only_cut": "all Joints_UpperBody plus Baselink_toWaistYaw and Waist_Yaw motor",
        "omission_contract": "catalogue motors, bearings, and fasteners are inertial-only; motors render as analytic cylinders",
        "skipped": skipped, "fetched_bodies": fetched, "groups": stats,
    }
    (args.out / "fusion_mesh_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"staged complete set -> {args.out}")


if __name__ == "__main__":
    main()
