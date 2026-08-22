# Assembly viewer — click a fastener, read its designation

    mujoco-sim/mjlab/.venv/bin/python3 tools/assembly_viewer/build_data.py
    python3 -m http.server 8891 --directory tools/assembly_viewer
    # http://<host>:8891

283 fasteners straight out of the Fusion assembly, 17 kinds. Click one and the panel gives
the designation (`M4x16`, countersunk), the standard (`ISO 10642`), the property class, which
link it belongs to, its mass, its CAD coordinate, and how many of that kind the robot uses.
Hovering a legend row isolates that kind, so "where does every M4x25 go" is one hover.

The CAD models one leg and one arm; the opposite side is drawn as a flagged, translucent
mirror and can be switched off.

**Orientation.** `build_data.py` draws real oriented screw bodies when
`~/pyg_fea/fusion/fasteners.json` exists (written by `tools/fusion/dump_fasteners.py`, which
reads each occurrence's transform so the local z is the screw axis). Without it the markers
are spheres and the sidebar says so. As of 2026-08-22 that file is empty because Fusion's
script host is wedged - `fusion_mcp_read` still answers, but every `fusion_mcp_execute`
script dies in a `__getattr__` stack overflow before the submitted code runs, including a
bare `def run(_c): raise ValueError("X")`. Restart the Fusion MCP add-in, then:

    mujoco-sim/mjlab/.venv/bin/python3 tools/fusion/dump_fasteners.py
    mujoco-sim/mjlab/.venv/bin/python3 tools/assembly_viewer/build_data.py

`preview.py` renders the same data as a static figure (docs/img/assembly_fasteners.png) for
checking the positions without a browser.
