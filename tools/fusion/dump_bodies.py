"""Dump every BRep body's mass properties out of the live Fusion document.

Mass, volume, centre of mass and the inertia tensor (Fusion reports it about the ROOT
ORIGIN, so the tensors add directly), plus the material name and whether the body's light
bulb is on - suppressed geometry such as the 6.5 kg `ArmR_fullDoF` alternative arm must
never reach the model.

The connector's stdout capture returns nothing on this Fusion build, so the payload comes
back through the exception channel (mcp_client.script). It carries the whole document in
one call.

Usage: dump_bodies.py [out.json] [--expect=<document name prefix>]
       (default /home/syaro/pyg_fea/fusion/bodies.json; with --expect the dump is refused,
        and nothing written, unless the ACTIVE document's name starts with the prefix)
"""
import json
import sys

sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/fusion')
import mcp_client as M  # noqa: E402

SRC = r'''
import adsk.core, adsk.fusion

def walk(o, path, live, out):
    live = live and o.isLightBulbOn
    p = path + "/" + o.name
    for i in range(o.bRepBodies.count):
        b = o.bRepBodies.item(i)
        pr = b.physicalProperties
        xx, yy, zz, xy, yz, xz = pr.getXYZMomentsOfInertia()[1:]
        bb = b.boundingBox
        out[p + "::" + b.name] = {
            "bb": [round(bb.minPoint.x*10,1), round(bb.minPoint.y*10,1), round(bb.minPoint.z*10,1),
                   round(bb.maxPoint.x*10,1), round(bb.maxPoint.y*10,1), round(bb.maxPoint.z*10,1)],
            "m": round(pr.mass, 6), "v": round(pr.volume, 4),
            "c": [round(pr.centerOfMass.x, 5), round(pr.centerOfMass.y, 5),
                  round(pr.centerOfMass.z, 5)],
            "I": [round(xx, 5), round(yy, 5), round(zz, 5),
                  round(xy, 5), round(yz, 5), round(xz, 5)],
            "mat": b.material.name if b.material else "?",
            "live": bool(live and b.isLightBulbOn)}
    for i in range(o.childOccurrences.count):
        walk(o.childOccurrences.item(i), p, live, out)

def run(_context: str):
    app = adsk.core.Application.get()
    root = adsk.fusion.Design.cast(app.activeProduct).rootComponent
    out = {}
    for i in range(root.occurrences.count):
        walk(root.occurrences.item(i), "", True, out)
    emit({"doc": app.activeDocument.name, "bodies": out})
'''


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dest = args[0] if args else '/home/syaro/pyg_fea/fusion/bodies.json'
    expect = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--expect=')), None)
    M.connect()
    r = M.script(SRC)
    if expect and not r['doc'].startswith(expect):
        # refuse BEFORE writing: a wrong active document must not overwrite the tagged dump
        sys.exit(f"!! active document is {r['doc']!r}, expected {expect}* - nothing written")
    B = r['bodies']
    json.dump(B, open(dest, 'w'), indent=0)
    live = {k: v for k, v in B.items() if v['live']}
    print(f"document : {r['doc']}")
    print(f"bodies   : {len(B)}  ({len(live)} live, {len(B) - len(live)} suppressed)")
    print(f"live mass: {sum(v['m'] for v in live.values()):.3f} kg   "
          f"(suppressed {sum(v['m'] for v in B.values() if not v['live']):.3f} kg)")
    print(f'-> {dest}')


if __name__ == '__main__':
    main()
