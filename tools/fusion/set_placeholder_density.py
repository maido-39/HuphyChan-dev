"""Make the CAD placeholders weigh what the real parts weigh, by editing their density.

The motors and bearings in the Fusion document are stand-in solids left at the default
Steel 7850 kg/m3, so the model carried ~13.3 kg of motors instead of ~9.4 kg. Their SHAPES
are right - the RS04 placeholder measures 120.0 x 120.0 x 55.7 mm against a catalogue
120 x 120 x 56, it is simply hollow - so the honest fix is to scale each placeholder's
density until its mass matches the manufacturer figure, which is what the user asked for.

Catalogue masses come from the RobStride user manuals (Mechanical characteristic) and the
NSK / IKO bearing tables; see docs/88 for the source table and the two corrections found
along the way (one 6810ZZ was modelled in aluminium, and the JMC-JS06 placeholders are
spherical-bearing INSERTS, already at the right 13 g, not whole rod ends).

Each target gets its own copied material named `PYG <part> <mass>g` so nothing else in the
document shifts, and re-running only updates that copy.

Usage: set_placeholder_density.py [--apply]     (default is a dry run)
"""
import json
import sys

sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/fusion')
import mcp_client as M  # noqa: E402

# occurrence-name substring -> (target mass in grams for the WHOLE occurrence, why)
TARGETS = {
    'Robstride RS04': (1420.0, 'RS04 manual 260713 1420g+-20g'),
    'Robstride RS03': (880.0, 'RS03 manual 260713 880g+-20g'),
    'Robstride RS02': (380.0, 'RS02 manual 260713 380g+-3g (405g is a reseller figure)'),
    'Robstride RS00': (310.0, 'RS00 manual 260713 310g+-3g'),
    'CRBS808AUUU': (122.0, 'IKO CRBS 808 A UU catalogue 122g'),
    '6814ZZ': (134.0, 'NSK/Koyo 6814ZZ 134g'),
    '6810ZZ': (50.0, 'NSK 6810ZZ 50g (Koyo 52g)'),
    '6900ZZ': (9.0, 'NSK 6900ZZ 9g - per bearing'),
}
# occurrences whose target is per BODY rather than per occurrence
PER_BODY = {'6900ZZ'}

SRC = r'''
import adsk.core, adsk.fusion

TARGETS = __TARGETS__
PER_BODY = __PER_BODY__
APPLY = __APPLY__

def walk(o, path, live, out):
    live = live and o.isLightBulbOn
    p = path + "/" + o.name
    hit = None
    for key in TARGETS:
        if key in o.name:
            hit = key
    if live and hit:
        bodies = [o.bRepBodies.item(i) for i in range(o.bRepBodies.count)]
        bodies = [b for b in bodies if b.isLightBulbOn]
        if bodies:
            out.append((p, hit, bodies))
    for i in range(o.childOccurrences.count):
        walk(o.childOccurrences.item(i), p, live, out)

def run(_context: str):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    found = []
    for i in range(root.occurrences.count):
        walk(root.occurrences.item(i), "", True, found)

    report = []
    for path, key, bodies in found:
        tgt_g, per_body = TARGETS[key][0], key in PER_BODY
        cur = sum(b.physicalProperties.mass for b in bodies) * 1000.0
        want = tgt_g * len(bodies) if per_body else tgt_g
        scale = want / cur if cur > 0 else 1.0
        rows = []
        for b in bodies:
            mat = b.material
            d0 = mat.materialProperties.itemById("structural_Density").value
            d1 = d0 * scale
            rows.append([b.name, round(b.physicalProperties.mass * 1000.0, 3),
                         round(d0, 1), round(d1, 1)])
            if APPLY:
                # the copy needs a name no other material has: four RS04 bodies asking for
                # "PYG RS04 1420g" makes addByCopy throw on the second one.
                tag = path.strip("/").replace("/", "-").replace(":", "_")
                name = "PYG " + tag + "-" + b.name + " " + \
                       str(round(want / len(bodies), 1)) + "g"
                if not mat.name.startswith("PYG "):
                    mat = des.materials.addByCopy(mat, name[:120])
                    b.material = mat
                for pid in ("structural_Density", "thermal_Density"):
                    pr = mat.materialProperties.itemById(pid)
                    if pr:
                        pr.value = d1
        after = sum(b.physicalProperties.mass for b in bodies) * 1000.0
        report.append(dict(path=path, key=key, n=len(bodies), before_g=round(cur, 2),
                           want_g=round(want, 2), after_g=round(after, 2),
                           scale=round(scale, 5), bodies=rows))
    if APPLY:
        return          # an exception would roll the material edits back
    emit(dict(applied=APPLY, n=len(report), report=report))
'''


def main():
    apply = '--apply' in sys.argv
    M.connect()

    def build(flag):
        return (SRC.replace('__TARGETS__', json.dumps({k: [v[0]] for k, v in TARGETS.items()}))
                .replace('__PER_BODY__', json.dumps(sorted(PER_BODY)))
                .replace('__APPLY__', flag))

    if apply:
        M.run_script(build('True'))          # side effect only - must not raise
    r = M.script(build('False'))             # read back what the document now holds
    print(f"{'occurrence':46s} {'n':>2s} {'now g':>9s} {'target g':>9s} "
          f"{'density kg/m3':>16s}  status")
    ok = 0
    for e in r['report']:
        occ = e['path'].split('/')[-1]
        d = e['bodies'][0]
        hit = abs(e['before_g'] - e['want_g']) < 0.05
        ok += hit
        print(f"{occ[:46]:46s} {e['n']:2d} {e['before_g']:9.2f} {e['want_g']:9.2f} "
              f"{d[2]:7.0f} -> {d[3]:6.0f}  {'OK' if hit else 'not applied'}")
    tot = sum(e['before_g'] for e in r['report'])
    want = sum(e['want_g'] for e in r['report'])
    print(f"\n{ok}/{len(r['report'])} occurrences at the catalogue mass · "
          f"placeholders now {tot / 1000:.3f} kg, target {want / 1000:.3f} kg"
          + ('' if apply else '   (DRY RUN - pass --apply)'))
    assert not apply or ok == len(r['report']), \
        'the document did not keep every density edit'
    json.dump(r, open('/home/syaro/pyg_fea/fusion/density_fix.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
