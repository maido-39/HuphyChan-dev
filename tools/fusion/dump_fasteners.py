"""Every fastener in the Fusion assembly: designation, where it sits, which way it points.

The assembly viewer needs more than a position - to be useful for actually building the
robot it has to show which way a screw goes in, so this pulls each fastener occurrence's
full 3D transform (its local z is the screw axis) along with the bounding box that tells
head from tip.

The designation is parsed out of the Fusion component name, which carries the standard:
"Hexagon Socket Countersunk Head Screw ISO 10642 - M4 x 16 Steel 8.8 Plain v1" ->
M4x16 countersunk ISO 10642, class 8.8.

Usage: dump_fasteners.py [out.json]   (default ~/pyg_fea/fusion/fasteners.json)
"""
import json
import re
import sys

sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/fusion')
import mcp_client as M  # noqa: E402

SRC = r'''
import adsk.core, adsk.fusion

KEY = ("Screw", "Bolt", "Nut", "Washer", "Pin")

def run(_context: str):
    # An explicit stack, not recursion: the connector wraps the script in a module whose
    # __getattr__ blows the Python stack long before the assembly tree runs out of depth.
    app = adsk.core.Application.get()
    root = adsk.fusion.Design.cast(app.activeProduct).rootComponent
    stack = []
    for i in range(root.occurrences.count):
        stack.append((root.occurrences.item(i), "", True))
    out = []
    stats = [0, 0, 0]                       # visited, name hits, emitted
    while stack:
        o, path, live = stack.pop()
        live = live and o.isLightBulbOn
        p = path + "/" + o.name
        stats[0] += 1
        if any(k in o.name for k in KEY):
            stats[1] += 1
            if live:
                bb = None
                for i in range(o.bRepBodies.count):
                    b = o.bRepBodies.item(i)
                    if not b.isLightBulbOn:
                        continue
                    box = b.boundingBox
                    v = [box.minPoint.x, box.minPoint.y, box.minPoint.z,
                         box.maxPoint.x, box.maxPoint.y, box.maxPoint.z]
                    if bb is None:
                        bb = v
                    else:
                        bb = [min(bb[j], v[j]) for j in range(3)] + \
                             [max(bb[j], v[j]) for j in range(3, 6)]
                if bb is not None:
                    m = o.transform2.asArray()
                    out.append([p, o.name, [round(x, 5) for x in m],
                                [round(x, 4) for x in bb]])
                    stats[2] += 1
            continue                        # a screw has no children worth walking
        for i in range(o.childOccurrences.count):
            stack.append((o.childOccurrences.item(i), p, live))
    emit({"stats": stats, "rows": out})
'''

HEAD = [('Countersunk', 'countersunk'), ('Button', 'button'),
        ('Cap Screw', 'socket head cap'), ('Pan', 'pan'), ('Hex', 'hex')]


def designation(name):
    """('M4x16', 'countersunk', 'ISO 10642', '8.8') from a Fusion component name."""
    size = re.search(r'M(\d+(?:\.\d+)?)\s*x\s*(?:[\d.]+\s*x\s*)?(\d+(?:\.\d+)?)', name)
    std = re.search(r'((?:ISO|DIN|JIS|ANSI)\s*[A-Z]?\s*[\d]+(?:\s*-\s*\d+)?)', name)
    cls = re.search(r'\b(\d\.\d|A\d|8\.8|4\.6|12\.9|10\.9)\b', name)
    kind = next((v for k, v in HEAD if k in name), 'other')
    if 'Nut' in name:
        kind = 'nut'
    elif 'Washer' in name:
        kind = 'washer'
    elif 'Pin' in name:
        kind = 'pin'
    def num(t):
        # only a DECIMAL may lose trailing zeros - stripping "10" would give "1"
        return t.rstrip('0').rstrip('.') if '.' in t else t

    return dict(
        size=f'M{num(size.group(1))}x{num(size.group(2))}' if size else name[:24],
        head=kind,
        std=std.group(1).replace('  ', ' ') if std else '',
        grade=cls.group(1) if cls else '')


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else '/home/syaro/pyg_fea/fusion/fasteners.json'
    M.connect()
    res = M.script(SRC)
    rows = res['rows']
    print(f"walked {res['stats'][0]} occurrences, "
          f"{res['stats'][1]} fastener-named, {res['stats'][2]} with geometry")
    out = []
    for path, name, mat, bb in rows:
        d = designation(name)
        # column-major-free: Fusion's asArray is row major 4x4; the axis is the third column
        axis = [mat[2], mat[6], mat[10]]
        pos = [mat[3] * 10.0, mat[7] * 10.0, mat[11] * 10.0]        # cm -> mm, CAD frame
        out.append(dict(path=path, name=name, pos=pos, axis=axis,
                        bbox_mm=[v * 10.0 for v in bb], **d))
    json.dump(out, open(dest, 'w'), indent=1)
    import collections
    c = collections.Counter(f"{o['size']} {o['head']}" for o in out)
    print(f'{len(out)} fasteners, {len(c)} kinds')
    for k, v in c.most_common():
        print(f'  {v:4d}  {k}')
    print(f'-> {dest}')


if __name__ == '__main__':
    main()
