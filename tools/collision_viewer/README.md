# Collision geometry viewer — what the physics actually touches

    mujoco-sim/mjlab/.venv/bin/python3 tools/collision_viewer/build_data.py   # robot.json + decimated meshes (15 MB)
    python3 -m http.server 8892 --directory tools/collision_viewer
    # http://<host>:8892   (three.js, works on a phone: ☰ opens the panel)

Two models straight from the MJCFs the training uses: **RP (serial ankle)** = `pygmalion_v3_printed.xml`,
**AB (closed-loop ankle)** = `pygmalion_v3_printed_loop.xml` — same arms welded 15 deg out as in training.

Layers: visual meshes (opacity slider), **collision primitives** (green: fitted capsules per link, box sole),
convex hulls (orange: the URDF collision meshes), loop sites (red: rod ends / foot balls = the `connect`
constraints), floor grid at the sole. Click any geom for its name, type, size, body, mass and whether it
collides (`contype 0` = visual only). Contact-exclude pairs (adjacent links) are listed at the bottom.

Pose: one slider per hinge (the loop model also exposes the passive ankle and rod joints — posing those by hand
does NOT keep the loop closed), `zero`, `bent init` (the training keyframe; for AB the loop-consistent solution),
and **▶ play AB mechanism**: a 9 s closure-consistent trajectory recorded from plain MuJoCo with the two crank
servos driven (pitch sweep, roll sweep, circle) so you can watch the cranks/rods move the passive foot.

Keys: `1/2/3` iso/front/side, `F` fit. Data: `build_data.py` (MjModel → bodies/joints/geoms/excludes/connects,
trimesh quadric decimation to 12k faces per mesh, AB trajectory at 25 Hz).
