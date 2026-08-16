"""Wrench Studio — FastAPI server for interactive joint-wrench exploration.

Serves ALL measured policies (fc/fcp npz) with on-demand aggregation, motion
replay with mesh body poses, negated (bracket-load) wrench vectors, and the
robot STL meshes for a three.js client.

Run (local):   .venv/bin/python3 tools/wrench_studio/server.py   (cwd=mjlab)
Run (docker):  docker compose up  (in tools/wrench_studio)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
import mujoco  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

HERE = Path(__file__).parent
MJLAB = Path(os.environ.get("MJLAB_DIR", HERE / "../../mujoco-sim/mjlab")).resolve()
OUT = MJLAB / "analysis/out"
MESH_DIR = MJLAB / "src/mjlab/asset_zoo/robots/pygmalion/xmls/assets"
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)

LINK = {"hip_pitch": "hip_pitch_link", "hip_roll": "hip_roll_link",
        "hip_yaw": "thigh_link", "knee": "shin_link",
        "ankle_pitch": "ankle_pitch_link", "ankle_roll": "foot_link"}
JOINTS = list(LINK)
SS = 4  # aggregation subsample

app = FastAPI(title="Wrench Studio")
_npz, _models, _cloudc, _sweepc = {}, {}, {}, {}


CACHE_VER = "v3"  # bump to invalidate derived caches when formulas change

MIR_F = np.array([-1.0, 1.0, 1.0])   # polar vector, sagittal mirror flips link-local x
MIR_M = np.array([1.0, -1.0, -1.0])  # axial vector (docs/64 §8h — L/R overlap cos 0.99+)


def npz(tag):
    if tag not in _npz:
        f = OUT / f"{tag}.npz"
        if not f.exists():
            raise HTTPException(404, f"unknown policy {tag}")
        _npz[tag] = np.load(f, allow_pickle=True)
    return _npz[tag]


def sweep(tag, ds=2):
    """ONE mj_forward pass per tag: link-local bracket wrench (negated reaction,
    UNMIRRORED) + joint-axis scalars for all 12 (side, joint). Everything else
    (agg / maxmode / cloud / loadcase / maxdir) is pure array post-processing.

    Moment reference: cfrc_int torque is at subtree_com(root) = robot CoM,
    transported to the joint anchor (verified vs motor torque corr 1.000,
    docs/64 §8i).

    Returns {(sd, j): {"W6": (n,6) [Fl|Ml], "ax": (n,3) fa/fr/mp}}, n = len(q)//ds.
    """
    key = f"sweep_{tag}_{ds}"
    if key in _sweepc:
        return _sweepc[key]
    f = CACHE / f"{CACHE_VER}_{key}.npz"
    if f.exists():
        z = np.load(f)
        res = {(sd, j): {"W6": z[f"W6_{sd}_{j}"], "ax": z[f"ax_{sd}_{j}"]}
               for sd in "LR" for j in JOINTS}
        _sweepc[key] = res
        return res
    d, m = npz(tag), model(tag)
    md = mujoco.MjData(m)
    q = np.asarray(d["qpos_full"], float)
    ids, W = {}, {}
    for sd in "LR":
        for j, lk in LINK.items():
            ids[(sd, j)] = (
                mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"robot/{sd}_{j}_joint"),
                mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"robot/{sd}_{lk}"))
            W[(sd, j)] = np.stack(
                [np.asarray(d[f"{ax}_{sd}_{lk}"], float) for ax in
                 ("Tx", "Ty", "Tz", "Fx", "Fy", "Fz")], 1)
    n = len(range(0, len(q), ds))
    res = {k: {"W6": np.empty((n, 6), np.float32), "ax": np.empty((n, 3), np.float32)}
           for k in ids}
    for i, t in enumerate(range(0, len(q), ds)):
        md.qpos[:] = q[t]
        mujoco.mj_forward(m, md)
        for k, (jid, bid) in ids.items():
            w = W[k][t]
            Mw = w[0:3] + np.cross(
                md.subtree_com[m.body_rootid[bid]] - md.xanchor[jid], w[3:6])
            R = md.xmat[bid].reshape(3, 3)
            Fl, Ml = -(R.T @ w[3:6]), -(R.T @ Mw)
            res[k]["W6"][i, 0:3] = Fl
            res[k]["W6"][i, 3:6] = Ml
            ax = md.xaxis[jid] / (np.linalg.norm(md.xaxis[jid]) + 1e-12)
            fa = np.dot(w[3:6], ax)
            ma = np.dot(Mw, ax)
            res[k]["ax"][i] = (abs(fa), np.linalg.norm(w[3:6] - fa * ax),
                               np.linalg.norm(Mw - ma * ax))
    np.savez_compressed(f, **{f"W6_{sd}_{j}": res[(sd, j)]["W6"] for sd, j in res},
                        **{f"ax_{sd}_{j}": res[(sd, j)]["ax"] for sd, j in res})
    _sweepc[key] = res
    return res


def sweep_mirrored(tag, joint, ds=2):
    """(A, meta): both legs pooled into L-leg convention. A = (2n,6) [F|M],
    meta[i] = (side, t_raw)."""
    s = sweep(tag, ds)
    parts, meta = [], []
    for sd in "LR":
        V = s[(sd, joint)]["W6"].astype(float).copy()
        if sd == "R":
            V[:, 0:3] *= MIR_F
            V[:, 3:6] *= MIR_M
        parts.append(V)
        meta += [(sd, i * ds) for i in range(len(V))]
    return np.vstack(parts), meta


def model(tag):
    if tag not in _models:
        _models[tag] = mujoco.MjModel.from_binary_path(str(OUT / f"{tag}_model.mjb"))
    return _models[tag]


@app.get("/api/policies")
def policies():
    out = []
    for f in sorted(OUT.glob("*_fc*.npz")):
        tag = f.stem
        if (OUT / f"{tag}_model.mjb").exists():
            out.append(tag)
    return out


def _binkey(v, y, z):
    if abs(y) < 0.01 and abs(z) < 0.01:
        return f"vx:{round(float(v), 2)}"
    if abs(v) < 0.01 and abs(z) < 0.01:
        return f"vy:{round(float(y), 2)}"
    if abs(v) < 0.01 and abs(y) < 0.01:
        return f"wz:{round(float(z), 2)}"
    return "combo"


@app.get("/api/agg/{tag}")
def agg(tag: str):
    """Per-joint per-command-bin stats (same shape as v1 embedded DATA)."""
    cf = CACHE / f"{CACHE_VER}_agg_{tag}.json"
    if cf.exists():
        return JSONResponse(json.loads(cf.read_text()))
    d = npz(tag)
    sw = sweep(tag, 2)
    sub = SS // 2  # sweep is ds=2; agg bins at ds=SS
    vx = np.asarray(d["cmd_vx"], float)[::SS]
    vy = np.asarray(d["cmd_vy"], float)[::SS]
    wz = np.asarray(d["cmd_wz"], float)[::SS]
    keys = np.array([_binkey(vx[i], vy[i], wz[i]) for i in range(len(vx))])
    st = lambda x: [round(float(np.sqrt(np.mean(x**2))), 1),
                    round(float(np.percentile(x, 99)), 1), round(float(x.max()), 1)]
    res = {}
    for j in JOINTS:
        Vs, AXs, TAUs = [], [], []
        for sd in "LR":
            V = sw[(sd, j)]["W6"][::sub].astype(float).copy()
            if sd == "R":
                V[:, 0:3] *= MIR_F
                V[:, 3:6] *= MIR_M
            Vs.append(V)
            AXs.append(sw[(sd, j)]["ax"][::sub].astype(float))
            TAUs.append(np.abs(np.asarray(d[f"tau_{sd}_{j}_joint"], float)[::SS]))
        V = np.vstack(Vs); AX = np.vstack(AXs); TAU = np.concatenate(TAUs)
        k2 = np.concatenate([keys, keys])
        res[j] = {}
        for b in sorted(set(keys)):
            sel = k2 == b
            if sel.sum() < 100:
                continue
            e = {"tau": st(TAU[sel]), "Mperp": st(AX[sel, 2]),
                 "Fr": st(AX[sel, 1]), "Fa": st(AX[sel, 0])}
            for ci, cn in enumerate(["Fx", "Fy", "Fz", "Mx", "My", "Mz"]):
                e[cn] = st(np.abs(V[sel, ci]))
            res[j][b] = e
    cf.write_text(json.dumps(res))
    return JSONResponse(res)


@app.get("/api/blocks/{tag}")
def blocks(tag: str):
    d = npz(tag)
    cvx = np.asarray(d["cmd_vx"], float)
    cvy = np.asarray(d["cmd_vy"], float)
    cwz = np.asarray(d["cmd_wz"], float)
    n = len(cvx) // 750
    out = []
    seen = set()
    for k in range(n):
        s = k * 750
        key = (round(float(cvx[s]), 2), round(float(cvy[s]), 2), round(float(cwz[s]), 2))
        if key not in seen:
            seen.add(key)
            out.append({"cmd": key, "start": s})
    return out


@app.get("/api/bodies/{tag}")
def bodies(tag: str):
    """Mesh geoms per body (file, local pos, local quat) for three.js."""
    m = model(tag)
    out = []
    for g in range(m.ngeom):
        if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        mesh_id = m.geom_dataid[g]
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mesh_id)
        b = m.geom_bodyid[g]
        bname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b)
        out.append({"body": bname, "mesh": f"{name}.stl", "mid": int(mesh_id),
                    "gpos": m.geom_pos[g].tolist(),
                    "gquat": m.geom_quat[g].tolist(), "bid": int(b)})
    return out


@app.get("/api/motion/{tag}")
def motion(tag: str, start: int, n: int = 750, ds: int = 2):
    """Frames: body poses (xpos,xquat per mesh body) + joint anchors +
    NEGATED joint wrench (= load on bracket) in world frame."""
    cf = CACHE / f"mot2_{tag}_{start}_{n}_{ds}.json"
    if cf.exists():
        return JSONResponse(json.loads(cf.read_text()))
    d = npz(tag)
    m = model(tag)
    md = mujoco.MjData(m)
    q = np.asarray(d["qpos_full"], float)
    if start < 0 or start + n > len(q):
        raise HTTPException(400, "range")
    body_ids = sorted({e["bid"] for e in bodies(tag)})
    ids, W = {}, {}
    for sd in "LR":
        for j, lk in LINK.items():
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"robot/{sd}_{j}_joint")
            bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"robot/{sd}_{lk}")
            ids[(sd, j)] = (jid, bid)
            W[(sd, j)] = np.stack(
                [np.asarray(d[f"{ax}_{sd}_{lk}"], float) for ax in
                 ("Tx", "Ty", "Tz", "Fx", "Fy", "Fz")], 1)
    TAUo = {(sd, j): np.asarray(d[f"tau_{sd}_{j}_joint"], float) for sd in "LR" for j in JOINTS}
    OMo = {(sd, j): np.asarray(d[f"omega_{sd}_{j}_joint"], float) for sd in "LR" for j in JOINTS}
    frames = []
    for t in range(start, start + n, ds):
        md.qpos[:] = q[t]
        mujoco.mj_forward(m, md)
        poses = []
        for b in body_ids:
            poses += [round(float(v), 4) for v in md.xpos[b]]
            poses += [round(float(v), 4) for v in md.xquat[b]]
        anch, wr = [], []
        for sd in "LR":
            for j in JOINTS:
                jid, bid = ids[(sd, j)]
                anch += [round(float(v), 3) for v in md.xanchor[jid]]
                w = W[(sd, j)][t]
                # cfrc_int torque is referenced at subtree_com(root) = robot CoM, not the
                # body CoM. Verified against motor torque: corr 1.000 (docs/64 §8i).
                Mw = w[0:3] + np.cross(
                    md.subtree_com[m.body_rootid[bid]] - md.xanchor[jid], w[3:6])
                wr += [round(float(-w[3]), 0), round(float(-w[4]), 0),
                       round(float(-w[5]), 0), round(float(-Mw[0]), 1),
                       round(float(-Mw[1]), 1), round(float(-Mw[2]), 1)]
        tv = [round(float(TAUo[(sd, j)][t]), 1) for sd in "LR" for j in JOINTS]
        ov = [round(float(OMo[(sd, j)][t]), 2) for sd in "LR" for j in JOINTS]
        frames.append({"base": [round(float(v), 3) for v in q[t, 0:3]],
                       "poses": poses, "anch": anch, "w": wr, "tau": tv, "om": ov})
    res = {"bodies": body_ids, "dt": ds / 50.0, "frames": frames}
    cf.write_text(json.dumps(res))
    return JSONResponse(res)




@app.get("/api/maxmode/{tag}")
def maxmode(tag: str, joint: str, ds: int = 2, win: int = 100, mode: str = "peak"):
    """For each of the 8 bracket-wrench channels (link-local, R-mirrored,
    negated) of `joint`: the max-|value| event + surrounding traces."""
    cf = CACHE / f"{CACHE_VER}_maxmode_{tag}_{joint}_{ds}_{win}_{mode}.json"
    if cf.exists():
        return JSONResponse(json.loads(cf.read_text()))
    if joint not in LINK:
        raise HTTPException(404, "joint")
    d = npz(tag)
    sw = sweep(tag, ds)
    comps = {}
    for sd in "LR":
        V = sw[(sd, joint)]["W6"].astype(float).copy()
        if sd == "R":
            V[:, 0:3] *= MIR_F
            V[:, 3:6] *= MIR_M
        comps[sd] = V
    tau = {sd: np.asarray(d[f"tau_{sd}_{joint}_joint"], float)[::ds] for sd in "LR"}
    om = {sd: np.asarray(d[f"omega_{sd}_{joint}_joint"], float)[::ds] for sd in "LR"}
    cvx = np.asarray(d["cmd_vx"], float)[::ds]
    cvy = np.asarray(d["cmd_vy"], float)[::ds]
    cwz = np.asarray(d["cmd_wz"], float)[::ds]
    names = ["Fx", "Fy", "Fz", "Mx", "My", "Mz", "Fmag", "Mmag"]
    out = {}
    n = len(comps["L"])
    def chan(sd, ci):
        if ci < 6:
            return comps[sd][:, ci]
        if ci == 6:
            return np.linalg.norm(comps[sd][:, 0:3], axis=1)
        return np.linalg.norm(comps[sd][:, 3:6], axis=1)
    def pick(x):
        a = np.abs(x)
        if mode == "peak":
            return int(np.argmax(a))
        tgt = float(np.percentile(a, 99)) if mode == "p99" else float(np.sqrt(np.mean(a**2)))
        return int(np.argmin(np.abs(a - tgt)))
    for ci, cn in enumerate(names):
        best = None
        for sd in "LR":
            x = chan(sd, ci)
            i = pick(x)
            v = float(x[i])
            if best is None or abs(v) > abs(best[0]):
                best = (v, sd, i)
        v, sd, i = best
        a, b = max(0, i - win), min(n, i + win)
        rnd = lambda arr: [round(float(x), 1) for x in arr]
        out[cn] = {
            "value": round(v, 1), "side": sd, "idx": i,
            "t_raw": i * ds, "block_start": (i * ds // 750) * 750,
            "cmd": [round(float(cvx[i]), 2), round(float(cvy[i]), 2),
                    round(float(cwz[i]), 2)],
            "trace_t0": a, "dt": ds / 50.0,
            "comp": rnd(chan(sd, ci)[a:b]),
            "tau": rnd(tau[sd][a:b]),
            "omega": [round(float(x), 2) for x in om[sd][a:b]],
        }
    cf.write_text(json.dumps(out))
    return JSONResponse(out)


@app.get("/api/meshgeom/{tag}/{mesh_id}")
def meshgeom(tag: str, mesh_id: int):
    """Compiled mesh vertices/faces from MjModel (already recentered to match
    geom_pos/quat) — fixes exploded-parts bug from raw-STL + compiled offsets."""
    m = model(tag)
    if mesh_id < 0 or mesh_id >= m.nmesh:
        raise HTTPException(404)
    va, vn = m.mesh_vertadr[mesh_id], m.mesh_vertnum[mesh_id]
    fa, fn = m.mesh_faceadr[mesh_id], m.mesh_facenum[mesh_id]
    return JSONResponse({
        "v": np.round(m.mesh_vert[va:va + vn].astype(float), 5).ravel().tolist(),
        "f": m.mesh_face[fa:fa + fn].astype(int).ravel().tolist()})


def _cloud_all(tag: str, ds: int = 6):
    """Link-local bracket-load point cloud per joint (L-leg convention),
    thin wrapper over sweep() with subsampling."""
    key = f"cloud_{tag}_{ds}"
    if key in _cloudc:
        return _cloudc[key]
    sub = max(1, ds // 2)  # sweep is ds=2
    res = {}
    for j in JOINTS:
        A, _ = sweep_mirrored(tag, j, 2)
        A = A.reshape(2, -1, 6)[:, ::sub].reshape(-1, 6)
        res[j] = {"F": A[:, 0:3].astype(np.float32), "M": A[:, 3:6].astype(np.float32)}
    _cloudc[key] = res
    return res


@app.get("/api/cloud/{tag}")
def cloud(tag: str, joint: str, kind: str = "F", npts: int = 4000, ds: int = 6):
    """Point cloud of link-local bracket loads for one joint (left-leg
    convention; the client mirrors it back for the right leg)."""
    if joint not in LINK or kind not in ("F", "M"):
        raise HTTPException(404, "joint/kind")
    V = _cloud_all(tag, ds)[joint][kind].astype(float)
    n = np.linalg.norm(V, axis=1)
    st = max(1, len(V) // max(npts, 1))
    Vs, ns = V[::st], n[::st]
    return JSONResponse({
        "v": np.round(Vs, 2).ravel().tolist(),
        "n": np.round(ns, 2).tolist(),
        "rms": round(float(np.sqrt(np.mean(n ** 2))), 1),
        "p99": round(float(np.percentile(n, 99)), 1),
        "peak": round(float(n.max()), 1),
        "total": int(len(V))})


@app.get("/api/loadcase/{tag}")
def loadcase(tag: str, joint: str, ds: int = 2):
    """FEA load cases (docs/64 §10.2b): link-local XYZ component stats +
    simultaneous 6-component cases with (side, t_raw, block_start) for 3D jump."""
    if joint not in LINK:
        raise HTTPException(404, "joint")
    cf = CACHE / f"{CACHE_VER}_lc_{tag}_{joint}_{ds}.json"
    if cf.exists():
        return JSONResponse(json.loads(cf.read_text()))
    A, meta = sweep_mirrored(tag, joint, ds)
    fn = np.linalg.norm(A[:, 0:3], axis=1)
    mn = np.linalg.norm(A[:, 3:6], axis=1)
    comb = fn / max(np.percentile(fn, 99), 1e-9) + mn / max(np.percentile(mn, 99), 1e-9)
    sel = [("LC-1 design(x1.25)", int(np.argsort(comb)[int(0.99 * len(comb))])),
           ("LC-2 max|M|", int(mn.argmax())),
           ("LC-3 max|F| peak", int(fn.argmax())),
           ("LC-4 Fz reversal", int(np.argmin(A[:, 2])))]
    cases = []
    for nm, i in sel:
        sd, t = meta[i]
        cases.append({"name": nm, "F": np.round(A[i, 0:3], 1).tolist(),
                      "M": np.round(A[i, 3:6], 2).tolist(), "side": sd,
                      "t_raw": int(t), "block_start": int(t - t % 750),
                      "Fmag": round(float(fn[i]), 1), "Mmag": round(float(mn[i]), 2)})
    stats = {}
    for ci, cn in enumerate(["Fx", "Fy", "Fz", "Mx", "My", "Mz"]):
        v = A[:, ci]
        a = np.abs(v)
        stats[cn] = {"rms": round(float(np.sqrt(np.mean(a ** 2))), 1),
                     "p99": round(float(np.percentile(a, 99)), 1),
                     "peak": round(float(a.max()), 1),
                     "min": round(float(v.min()), 1), "max": round(float(v.max()), 1)}
    res = {"joint": joint, "frame": "link-local (+x lateral/axis, +y fore, +z up), "
           "bracket load at joint anchor, L-leg convention", "cases": cases,
           "stats": stats}
    cf.write_text(json.dumps(res))
    return JSONResponse(res)


@app.get("/api/scatter")
def scatter(joint: str, ss: int = 80):
    """tau-omega operating points for ALL policies (docs regime-plot style)."""
    cf = CACHE / f"scatter_{joint}_{ss}.json"
    if cf.exists():
        return JSONResponse(json.loads(cf.read_text()))
    out = {}
    for tag in policies():
        try:
            d = npz(tag)
            t = np.concatenate([np.asarray(d[f"tau_{s}_{joint}_joint"], float)[::ss]
                                for s in "LR"])
            o = np.concatenate([np.asarray(d[f"omega_{s}_{joint}_joint"], float)[::ss]
                                for s in "LR"])
            out[tag] = {"tau": np.round(t, 1).tolist(),
                        "om": np.round(o, 2).tolist()}
        except Exception:
            continue
    cf.write_text(json.dumps(out))
    return JSONResponse(out)



BM_FILE = CACHE / "bookmarks.json"


def _bm_load():
    return json.loads(BM_FILE.read_text()) if BM_FILE.exists() else []


@app.get("/api/bookmarks")
def bm_list():
    return _bm_load()


@app.post("/api/bookmarks")
def bm_add(bm: dict):
    bms = _bm_load()
    bm["id"] = (max([b["id"] for b in bms]) + 1) if bms else 1
    bms.append(bm)
    BM_FILE.write_text(json.dumps(bms, ensure_ascii=False))
    return bm


@app.patch("/api/bookmarks/{bid}")
def bm_rename(bid: int, body: dict):
    bms = _bm_load()
    for b in bms:
        if b["id"] == bid:
            b["name"] = body.get("name", b["name"])
    BM_FILE.write_text(json.dumps(bms, ensure_ascii=False))
    return {"ok": True}


@app.delete("/api/bookmarks/{bid}")
def bm_del(bid: int):
    bms = [b for b in _bm_load() if b["id"] != bid]
    BM_FILE.write_text(json.dumps(bms, ensure_ascii=False))
    return {"ok": True}



@app.get("/api/maxdir/{tag}")
def maxdir(tag: str, joint: str, ds: int = 2):
    """Octant-binned max bracket force/moment (link-local, per L/R side)."""
    cf = CACHE / f"{CACHE_VER}_maxdir_{tag}_{joint}_{ds}.json"
    if cf.exists():
        return JSONResponse(json.loads(cf.read_text()))
    sw = sweep(tag, ds)
    res = {}
    for sd in "LR":
        W6 = sw[(sd, joint)]["W6"].astype(float)
        ent = {"F": {}, "M": {}}
        for key, A in [("F", W6[:, 0:3]), ("M", W6[:, 3:6])]:
            mag = np.linalg.norm(A, axis=1)
            octs = (A[:, 0] >= 0).astype(int) * 4 + (A[:, 1] >= 0).astype(int) * 2 \
                + (A[:, 2] >= 0).astype(int)
            for o in range(8):
                sel = np.where(octs == o)[0]
                if len(sel) < 5:
                    continue
                i = sel[int(np.argmax(mag[sel]))]
                ent[key][str(o)] = {
                    "v": [round(float(x), 1) for x in A[i]],
                    "mag": round(float(mag[i]), 1), "idx": int(i),
                    "t_raw": int(i * ds),
                    "block_start": int((i * ds // 750) * 750)}
        res[sd] = ent
    cf.write_text(json.dumps(res))
    return JSONResponse(res)


@app.get("/api/ankle_demand")
def ankle_demand(ds: int = 20):
    """Measured ankle demand samples for the 2-RSU designer: per sample
    (pitch deg, roll deg, tau_p, tau_r, omega_p, omega_r), both legs pooled
    into the LEFT-leg convention (R roll quantities sign-flipped), both
    anchor policies pooled (src 0=flat, 1=rough)."""
    cf = CACHE / f"{CACHE_VER}_ankledemand_{ds}.json"
    if cf.exists():
        return JSONResponse(json.loads(cf.read_text()))
    pts = []
    for src, tag in enumerate(["gen21p2_fc", "p2b_v2_fc"]):
        d, m = npz(tag), model(tag)
        q = np.asarray(d["qpos_full"], float)
        for sd in "LR":
            s = 1.0 if sd == "L" else -1.0
            jp = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"robot/{sd}_ankle_pitch_joint")
            jr = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"robot/{sd}_ankle_roll_joint")
            qp = np.degrees(q[:, m.jnt_qposadr[jp]])
            qr = np.degrees(q[:, m.jnt_qposadr[jr]]) * s
            tp = np.asarray(d[f"tau_{sd}_ankle_pitch_joint"], float)
            tr = np.asarray(d[f"tau_{sd}_ankle_roll_joint"], float) * s
            wp = np.asarray(d[f"omega_{sd}_ankle_pitch_joint"], float)
            wr = np.asarray(d[f"omega_{sd}_ankle_roll_joint"], float) * s
            for t in range(0, len(q), ds):
                pts.append([round(float(qp[t]), 1), round(float(qr[t]), 1),
                            round(float(tp[t]), 1), round(float(tr[t]), 1),
                            round(float(wp[t]), 2), round(float(wr[t]), 2), src])
    res = {"pts": pts, "note": "L-leg convention; src 0=flat 1=rough; 50/ds Hz"}
    cf.write_text(json.dumps(res))
    return JSONResponse(res)


@app.get("/api/mesh/{name:path}")
def mesh(name: str):
    f = (MESH_DIR / Path(name).name).resolve()
    if not str(f).startswith(str(MESH_DIR)) or not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="application/octet-stream")


app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8091)
