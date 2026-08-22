# Assembly viewer — click a fastener, read its designation

    mujoco-sim/mjlab/.venv/bin/python3 tools/assembly_viewer/build_data.py
    python3 -m http.server 8891 --directory tools/assembly_viewer
    # http://<host>:8891

283 fasteners straight out of the Fusion assembly, 17 kinds. Tap one and the panel gives the
designation (`M4x16`, countersunk), the standard (`ISO 10642`), the property class, the link
it belongs to, its mass, **which way it goes in and which way the head faces**, and the seat
coordinate in CAD mm.

Each screw is anchored on its **bearing face**, not its centre: the Fusion fastener components
put their origin there, which build_data.py verified rather than assumed - the origin sits
along +axis from the bounding-box centre by exactly (length/2 - head height) for every size in
the assembly, 283 out of 283. So the head is drawn growing out of the surface and the shank
sinking into the part, and countersunk heads taper.

**Navigation.** Drag rotates, right-drag or two fingers pans, wheel zooms, double-click flies
to a screw. Keys: `1`-`4` iso/front/side/top, `F` fit (or focus the selection), `[` `]` step
through the filtered set focusing each one, `Esc` clears every filter, `/` jumps to search.
Framing accounts for the sidebar so the robot does not sit behind it.

**Finding one screw among 283.** Three filters compose: the search box (`M4x20`, `countersunk`,
`shin`, `ISO 10642`), the designation list, and the per-link chips. Whatever survives can be
stepped through one at a time with `[` / `]`, which is the actual assembly loop - "show me each
of the 78 M4x20 in the shin, one by one". Unmatched screws dim by default or hide outright.

**Mobile.** Below 860 px the sidebar becomes a drawer behind `☰` and the info panel becomes a
bottom sheet; below 560 px the view presets collapse into the search bar. Picking falls back to
the nearest screw within ~34 px of the tap, because a finger is much wider than a 4 mm screw,
and a drag is never mistaken for a tap.

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
