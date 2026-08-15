"""FastenerSelect - Fusion 360 add-in: pick every hole/screw of the same size at
once, drop the ones you do not want, add any extra faces, then hand the set to
the next command (Structural Constraints / Loads) or save it as a Selection Set.

Why a *selection* tool and not a constraint tool: the Fusion API exposes no
Simulation study objects, so an add-in cannot create a structural constraint
directly. What it can do is drive the selection - and Fusion commands consume a
pre-selection, so picking the faces here and then starting the constraint puts
them straight into its first selection input. The set is also saveable as a
named Selection Set (Design.selectionSets) for later recall.

Install:
  Windows  %APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\FastenerSelect
  macOS    ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FastenerSelect
then Utilities > Add-Ins > FastenerSelect > Run (tick "Run on Startup").
"""
import math
import traceback

import adsk.core
import adsk.fusion

CMD_ID = 'pygFastenerSelectCmd'
CMD_NAME = 'Fastener Select'
CMD_TOOLTIP = ('Select all holes/screws of the same size at once, deselect what you do not '
               'want, add extra faces, then feed the result to the next command.')
# (workspace id, panel id) candidates - whichever exist get the button
TARGET_PANELS = [
    ('FusionSolidEnvironment', 'SolidScriptsAddinsPanel'),
    ('FusionSimEnvironment', 'SimSetupPanel'),
    ('FusionSimEnvironment', 'SimulationScriptsAddinsPanel'),
    ('FusionSimEnvironment', 'SolidScriptsAddinsPanel'),
    ('FusionSimEnvironment', 'SimLoadsPanel'),
]
MM = 10.0                      # Fusion works in cm internally
CBORE_MAX_STEP_MM = 6.0        # a head recess is at most this much bigger in radius
COAX_TOL_MM = 0.3

_handlers = []                 # keep handlers alive
_app = None
_ui = None


# ----------------------------------------------------------------- geometry helpers
def face_key(face):
    """Cheap, stable identity for a face within this session."""
    try:
        occ = face.assemblyContext
        occ_name = occ.name if occ else ''
    except Exception:
        occ_name = ''
    try:
        return (occ_name, face.body.name, face.tempId)
    except Exception:
        return (occ_name, '', id(face))


class Hole:
    """A cylindrical face plus what we could measure about it."""

    __slots__ = ('face', 'radius_mm', 'axis', 'origin', 'length_mm', 'body_name',
                 'occ_name', 'cbore_face', 'cbore_mm', 'is_full', 'key')

    def __init__(self, face):
        cyl = adsk.core.Cylinder.cast(face.geometry)
        self.face = face
        self.radius_mm = cyl.radius * MM
        self.axis = cyl.axis.copy()
        self.axis.normalize()
        self.origin = cyl.origin.copy()
        bb = face.boundingBox
        diag = adsk.core.Vector3D.create(bb.maxPoint.x - bb.minPoint.x,
                                         bb.maxPoint.y - bb.minPoint.y,
                                         bb.maxPoint.z - bb.minPoint.z)
        self.length_mm = abs(diag.dotProduct(self.axis)) * MM
        try:
            self.body_name = face.body.name
        except Exception:
            self.body_name = '?'
        try:
            occ = face.assemblyContext
            self.occ_name = occ.name if occ else ''
        except Exception:
            self.occ_name = ''
        # a bolt hole wraps a full 360 deg; a fillet or a relief slot does not
        try:
            full = 2 * math.pi * (self.radius_mm / MM) * (self.length_mm / MM)
            self.is_full = full <= 1e-9 or (face.area / full) > 0.80
        except Exception:
            self.is_full = True
        self.cbore_face = None
        self.cbore_mm = 0.0
        self.key = face_key(face)

    def axis_key(self):
        v = [self.axis.x, self.axis.y, self.axis.z]
        i = max(range(3), key=lambda k: abs(v[k]))
        if v[i] < 0:
            v = [-x for x in v]
        return tuple(round(x, 3) for x in v)

    def center(self):
        bb = self.face.boundingBox
        return adsk.core.Point3D.create((bb.maxPoint.x + bb.minPoint.x) / 2,
                                        (bb.maxPoint.y + bb.minPoint.y) / 2,
                                        (bb.maxPoint.z + bb.minPoint.z) / 2)

    def coaxial_with(self, other):
        d = adsk.core.Vector3D.create(other.origin.x - self.origin.x,
                                      other.origin.y - self.origin.y,
                                      other.origin.z - self.origin.z)
        along = d.dotProduct(self.axis)
        radial_sq = max(0.0, d.length ** 2 - along ** 2)
        return math.sqrt(radial_sq) * MM <= COAX_TOL_MM

    def seat_faces(self):
        """Flat faces touching this hole - where a bolt head or a washer presses."""
        out = []
        try:
            for edge in self.face.edges:
                for f2 in edge.faces:
                    if f2 == self.face:
                        continue
                    try:
                        if f2.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                            out.append(f2)
                    except Exception:
                        continue
        except Exception:
            pass
        return out


def bodies_in_scope(design, scope, sel_entities):
    """Yield BRepBody objects (proxies when inside occurrences)."""
    if scope == 'selected':
        for e in sel_entities or ():
            body = adsk.fusion.BRepBody.cast(e)
            if body:
                yield body
                continue
            occ = adsk.fusion.Occurrence.cast(e)
            if occ:
                for b in occ.bRepBodies:
                    yield b
                for sub in occ.childOccurrences:
                    for b in sub.bRepBodies:
                        yield b
                continue
            comp = adsk.fusion.Component.cast(e)
            if comp:
                for b in comp.bRepBodies:
                    yield b
        return
    root = design.rootComponent
    if scope == 'active':
        comp = design.activeComponent or root
        for b in comp.bRepBodies:
            yield b
        return
    for b in root.bRepBodies:
        if b.isVisible:
            yield b
    for occ in root.allOccurrences:
        if not occ.isLightBulbOn:
            continue
        for b in occ.bRepBodies:
            if b.isVisible:
                yield b


def collect_cylinders(design, scope, sel_entities, r_lo_mm, r_hi_mm, progress=None):
    out = []
    bodies = list(bodies_in_scope(design, scope, sel_entities))
    if progress:
        progress.maximumValue = max(1, len(bodies))
    for i, body in enumerate(bodies):
        if progress:
            if progress.wasCancelled:
                break
            progress.progressValue = i
            progress.message = f'Scanning {i + 1}/{len(bodies)}: %p%'
        try:
            faces = body.faces
        except Exception:
            continue
        for f in faces:
            try:
                if f.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                    continue
                r = adsk.core.Cylinder.cast(f.geometry).radius * MM
                if r < r_lo_mm or r > r_hi_mm:
                    continue
                out.append(Hole(f))
            except Exception:
                continue
    return out


def attach_counterbores(holes):
    """For each hole, remember the larger coaxial cylinder abutting it (head recess)."""
    by_axis = {}
    for h in holes:
        by_axis.setdefault(h.axis_key(), []).append(h)
    for h in holes:
        best = None
        for o in by_axis.get(h.axis_key(), ()):
            if o is h:
                continue
            step = o.radius_mm - h.radius_mm
            if step <= 0.3 or step > CBORE_MAX_STEP_MM:
                continue
            if h.coaxial_with(o) and (best is None or o.radius_mm < best.radius_mm):
                best = o
        if best is not None:
            h.cbore_face = best.face
            h.cbore_mm = best.radius_mm * 2


def group_label(h, use_axis):
    lbl = f'Ø{h.radius_mm * 2:.2f} mm'
    if h.cbore_mm:
        lbl += f' + cbore Ø{h.cbore_mm:.1f}'
    if use_axis:
        a = h.axis_key()
        lbl += f'  axis({a[0]:+.2f},{a[1]:+.2f},{a[2]:+.2f})'
    return lbl


# ------------------------------------------------------------------------- command
class State:
    def __init__(self):
        self.groups = {}      # label -> [Hole]
        self.checks = {}      # label -> checkbox input id
        self.summary = ''


def help_html(extra=''):
    return (f'{extra}<b>How to use</b><br>'
            '1. Pick one hole face, press <i>Find matching</i>.<br>'
            '2. Untick a size group, or pick faces under <i>Deselect</i> to drop individual ones.<br>'
            '3. Add anything else under <i>Extra faces</i>.<br>'
            '4. OK &rarr; the faces stay selected, so starting <i>Structural Constraints</i> or '
            '<i>Loads</i> right after fills its selection input. Saving a Selection Set lets you '
            'recall exactly the same faces later.<br>'
            '<span style="color:#888">The Fusion API exposes no simulation objects, so this '
            'add-in drives the selection, not the constraint itself.</span>')


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            cmd.isRepeatable = False
            cmd.okButtonText = 'Select'
            ins = cmd.commandInputs
            state = State()

            ref = ins.addSelectionInput('ref', 'Reference hole',
                                        'Pick ONE cylindrical face; all holes of the same '
                                        'diameter will be found')
            ref.addSelectionFilter('CylindricalFaces')
            ref.setSelectionLimits(0, 1)

            scope = ins.addDropDownCommandInput('scope', 'Search scope',
                                                adsk.core.DropDownStyles.TextListDropDownStyle)
            scope.listItems.add('Whole design (visible)', True)
            scope.listItems.add('Active component', False)
            scope.listItems.add('Selected bodies / components', False)

            sc = ins.addSelectionInput('scopeSel', 'Scope bodies', 'Used only with the third scope')
            sc.addSelectionFilter('SolidBodies')
            sc.addSelectionFilter('Occurrences')
            sc.setSelectionLimits(0, 0)
            sc.isVisible = False

            ins.addValueInput('tol', 'Diameter tolerance', 'mm',
                              adsk.core.ValueInput.createByReal(0.005))     # 0.05 mm
            ins.addBoolValueInput('sameAxis', 'Same axis direction only', True, '', False)
            ins.addBoolValueInput('sameComp', 'Same component only', True, '', False)
            ins.addValueInput('within', 'Within distance of reference (0 = all)', 'mm',
                              adsk.core.ValueInput.createByReal(0.0))
            ins.addBoolValueInput('fullOnly', 'Full 360° cylinders only', True, '', True)
            ins.addBoolValueInput('withCbore', 'Include counterbore faces', True, '', False)
            ins.addBoolValueInput('withSeat', 'Include the flat seat face at each hole',
                                  True, '', False)

            find = ins.addBoolValueInput('find', 'Find matching', False, '', False)
            find.text = 'Find matching'

            table = ins.addTableCommandInput('groups', 'Matches', 3, '5:2:1')
            table.minimumVisibleRows = 3
            table.maximumVisibleRows = 12

            ex = ins.addSelectionInput('exclude', 'Deselect (subtract)', 'Faces to remove')
            ex.addSelectionFilter('Faces')
            ex.setSelectionLimits(0, 0)

            extra = ins.addSelectionInput('extra', 'Extra faces (add)',
                                          'Any faces or whole bodies to include as well')
            extra.addSelectionFilter('Faces')
            extra.addSelectionFilter('SolidBodies')
            extra.setSelectionLimits(0, 0)

            out = ins.addDropDownCommandInput('out', 'On OK',
                                              adsk.core.DropDownStyles.TextListDropDownStyle)
            out.listItems.add('Select now (feeds the next command)', True)
            out.listItems.add('Save as Selection Set', False)
            out.listItems.add('Both', False)
            ins.addStringValueInput('setName', 'Selection set name', 'Fasteners')

            info = ins.addTextBoxCommandInput('info', '', help_html(), 7, True)
            info.isFullWidth = True

            for handler, event in ((InputChangedHandler(state), cmd.inputChanged),
                                   (ExecuteHandler(state), cmd.execute)):
                event.add(handler)
                _handlers.append(handler)
        except Exception:
            if _ui:
                _ui.messageBox('FastenerSelect (create) failed:\n' + traceback.format_exc())


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self, state):
        super().__init__()
        self.state = state

    def notify(self, args):
        try:
            ins = args.inputs
            cid = args.input.id
            if cid == 'scope':
                ins.itemById('scopeSel').isVisible = \
                    ins.itemById('scope').selectedItem.name.startswith('Selected')
            elif cid == 'find':
                if args.input.value:
                    args.input.value = False
                    self.search(ins)
            elif cid.startswith('grp') or cid in ('exclude', 'extra', 'withSeat', 'withCbore'):
                self.update_count(ins)
        except Exception:
            if _ui:
                _ui.messageBox('FastenerSelect (input) failed:\n' + traceback.format_exc())

    def update_count(self, ins):
        try:
            n = len(gather(self.state, ins))
            ins.itemById('info').formattedText = help_html(
                f'<b>{n} faces will be selected.</b> {self.state.summary}<br><br>')
        except Exception:
            pass

    def search(self, ins):
        design = adsk.fusion.Design.cast(_app.activeProduct)
        if not design:
            _ui.messageBox('Open a design first.')
            return
        ref_in = ins.itemById('ref')
        if ref_in.selectionCount == 0:
            _ui.messageBox('Pick one reference hole face first.')
            return
        ref = Hole(adsk.fusion.BRepFace.cast(ref_in.selection(0).entity))
        tol_mm = ins.itemById('tol').value * MM
        same_axis = ins.itemById('sameAxis').value
        same_comp = ins.itemById('sameComp').value
        within_mm = ins.itemById('within').value * MM
        full_only = ins.itemById('fullOnly').value
        want_cbore = ins.itemById('withCbore').value

        sname = ins.itemById('scope').selectedItem.name
        scope = ('selected' if sname.startswith('Selected')
                 else 'active' if sname.startswith('Active') else 'visible')
        sel_entities = []
        if scope == 'selected':
            sc = ins.itemById('scopeSel')
            sel_entities = [sc.selection(i).entity for i in range(sc.selectionCount)]
            if not sel_entities:
                _ui.messageBox('Pick the bodies/components to search in.')
                return

        prog = _ui.createProgressDialog()
        prog.isCancelButtonShown = True
        prog.show('FastenerSelect', 'Scanning %p%', 0, 100, 0)
        try:
            r_lo = ref.radius_mm - tol_mm / 2
            r_hi = ref.radius_mm + tol_mm / 2 + (CBORE_MAX_STEP_MM if want_cbore else 0.0)
            found = collect_cylinders(design, scope, sel_entities, r_lo - 0.01, r_hi + 0.01, prog)
            attach_counterbores(found)
        finally:
            prog.hide()

        ref_c = ref.center()
        keep = []
        for h in found:
            if abs(h.radius_mm - ref.radius_mm) > tol_mm / 2:
                continue                                  # counterbores ride along via cbore_face
            if full_only and not h.is_full:
                continue
            if same_axis and h.axis_key() != ref.axis_key():
                continue
            if same_comp and h.occ_name != ref.occ_name:
                continue
            if within_mm > 0 and h.center().distanceTo(ref_c) * MM > within_mm:
                continue
            keep.append(h)

        self.state.groups = {}
        for h in keep:
            self.state.groups.setdefault(group_label(h, same_axis), []).append(h)

        table = ins.itemById('groups')
        table.clear()
        self.state.checks = {}
        for i, (label, hs) in enumerate(sorted(self.state.groups.items())):
            bid = f'grp{i}'
            lbl = table.commandInputs.addStringValueInput(f'lbl{i}', '', label)
            lbl.isReadOnly = True
            cnt = table.commandInputs.addStringValueInput(f'cnt{i}', '', f'{len(hs)}')
            cnt.isReadOnly = True
            chk = table.commandInputs.addBoolValueInput(bid, '', True, '', True)
            table.addCommandInput(lbl, i, 0)
            table.addCommandInput(cnt, i, 1)
            table.addCommandInput(chk, i, 2)
            self.state.checks[label] = bid
        self.state.summary = (f'Reference Ø{ref.radius_mm * 2:.2f} mm &rarr; '
                              f'{len(keep)} holes in {len(self.state.groups)} group(s).')
        self.update_count(ins)


def gather(state, ins):
    """checked groups (+ counterbores / seats) + extras - exclusions."""
    want_cbore = ins.itemById('withCbore').value
    want_seat = ins.itemById('withSeat').value
    ents, seen = [], set()

    def push(face):
        k = face_key(face)
        if k not in seen:
            seen.add(k)
            ents.append(face)

    for label, hs in state.groups.items():
        bid = state.checks.get(label)
        chk = ins.itemById(bid) if bid else None
        if chk is not None and not chk.value:
            continue
        for h in hs:
            push(h.face)
            if want_cbore and h.cbore_face:
                push(h.cbore_face)
            if want_seat:
                for f in h.seat_faces():
                    push(f)

    extra = ins.itemById('extra')
    for i in range(extra.selectionCount):
        e = extra.selection(i).entity
        body = adsk.fusion.BRepBody.cast(e)
        if body:
            for f in body.faces:
                push(f)
        else:
            face = adsk.fusion.BRepFace.cast(e)
            if face:
                push(face)

    excl = ins.itemById('exclude')
    drop = set()
    for i in range(excl.selectionCount):
        face = adsk.fusion.BRepFace.cast(excl.selection(i).entity)
        if face:
            drop.add(face_key(face))
    if drop:
        ents = [f for f in ents if face_key(f) not in drop]
    return ents


class ExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, state):
        super().__init__()
        self.state = state

    def notify(self, args):
        try:
            ins = args.command.commandInputs
            ents = gather(self.state, ins)
            if not ents:
                _ui.messageBox('Nothing to select.')
                return
            mode = ins.itemById('out').selectedItem.name
            design = adsk.fusion.Design.cast(_app.activeProduct)
            note = ''

            if mode.startswith('Save') or mode.startswith('Both'):
                col = adsk.core.ObjectCollection.create()
                for e in ents:
                    col.add(e)
                name = ins.itemById('setName').value or 'Fasteners'
                try:
                    design.selectionSets.add(col, name)
                    note = f' Saved as Selection Set "{name}".'
                except Exception:
                    note = (' Selection Set could not be created on this build - '
                            'the faces are still selected.')

            if mode.startswith('Select') or mode.startswith('Both'):
                _ui.activeSelections.clear()
                added = 0
                for e in ents:
                    try:
                        _ui.activeSelections.add(e)
                        added += 1
                    except Exception:
                        pass
                note = f'{added} of {len(ents)} faces selected.' + note

            if note:
                _ui.statusMessage = 'FastenerSelect: ' + note.strip()
        except Exception:
            if _ui:
                _ui.messageBox('FastenerSelect (execute) failed:\n' + traceback.format_exc())


# --------------------------------------------------------------------------- add-in
def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        old = _ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        cd = _ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, '')
        h = CommandCreatedHandler()
        cd.commandCreated.add(h)
        _handlers.append(h)

        added = []
        for ws_id, panel_id in TARGET_PANELS:
            try:
                ws = _ui.workspaces.itemById(ws_id)
                if not ws:
                    continue
                panel = ws.toolbarPanels.itemById(panel_id)
                if not panel or panel.controls.itemById(CMD_ID):
                    continue
                ctrl = panel.controls.addCommand(cd)
                ctrl.isPromoted = True
                added.append(f'{ws_id}/{panel_id}')
            except Exception:
                continue
        if not added:
            _ui.messageBox('FastenerSelect loaded, but no toolbar panel accepted the button.\n'
                           'Run it from Utilities > Add-Ins > Scripts and Add-Ins.')
    except Exception:
        if _ui:
            _ui.messageBox('FastenerSelect run failed:\n' + traceback.format_exc())


def stop(context):
    try:
        if not _ui:
            return
        for ws_id, panel_id in TARGET_PANELS:
            try:
                ws = _ui.workspaces.itemById(ws_id)
                panel = ws.toolbarPanels.itemById(panel_id) if ws else None
                ctrl = panel.controls.itemById(CMD_ID) if panel else None
                if ctrl:
                    ctrl.deleteMe()
            except Exception:
                continue
        cd = _ui.commandDefinitions.itemById(CMD_ID)
        if cd:
            cd.deleteMe()
        _handlers.clear()
    except Exception:
        if _ui:
            _ui.messageBox('FastenerSelect stop failed:\n' + traceback.format_exc())
