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
are spheres and the sidebar says so. All 283 are oriented as of 2026-08-22: 187 go in
laterally, 60 fore-aft, 36 vertically, and every one is axis-aligned.

Two failure modes cost time and are worth recognising:
- **script host wedged.** `fusion_mcp_read` keeps answering while every `fusion_mcp_execute`
  dies in a `__getattr__` stack overflow *before the submitted code runs* - a bare
  `def run(_c): raise ValueError("X")` never raises. Restart the Fusion MCP add-in.
- **tunnel dead.** The local forward still listens, so the port looks open; the give-away is
  `RemoteDisconnected` and then a timeout. Check the process, not the port:
  `ps -eo pid,etime,cmd | grep "ssh .*27182"`. Restart with
  `ssh -N -L 27182:127.0.0.1:27182 syaro@192.168.20.161` from this host.

After either, re-run:

    mujoco-sim/mjlab/.venv/bin/python3 tools/fusion/dump_fasteners.py
    mujoco-sim/mjlab/.venv/bin/python3 tools/assembly_viewer/build_data.py

`preview.py` renders the same data as a static figure (docs/img/assembly_fasteners.png) for
checking the positions without a browser.
