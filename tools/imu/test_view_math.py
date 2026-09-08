"""The IMU viewer's camera math, checked outside the browser.

2026-09-07. The 3D view in ``web_viewer.py`` was rewritten from scratch after
the user reported, for the second time, that rotation about X looked inverted
and that the view could not be navigated at all:

    "IMU 뷰어 네비게이션 가능하게 해줘. 그리고 뷰어의 x 축 회전이 반대로인데,
     Y-UP 인 THREE.JS 쓰지말고 제로부터 구현하던가 해"

Two separate causes sat behind that:

* three.js is Y-up while the sensor's world is Z-up, so the page carried a
  sensor -> library axis mapping. The first version of it was a component swap
  (x, z, y), which is a REFLECTION (determinant -1): static arrows point the
  right way while the visual sense of every rotation is inverted. Replacing it
  with a proper rotation did not settle the report either. The rewrite deletes
  the mapping entirely - sensor coordinates are drawn verbatim.
* three.js and OrbitControls were both loaded from public CDNs. With no route
  to them, the whole 3D block throws on load: no camera, no controls, no
  drawing - indistinguishable from "navigation is broken". Nothing is fetched
  now.

This file re-implements the page's own camera and projection formulas in Python
and asserts the three properties the viewer has actually got wrong before. The
page runs the same three assertions in the browser and prints the verdict into
its own readout (``selfCheck`` / ``v-selfcheck``); this file is the version that
runs in CI, where there is no browser.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

VIEWER = Path(__file__).resolve().parent / "web_viewer.py"

FOV_Y = math.radians(50.0)
ROT_PER_PX = 0.008
HOME = dict(az=math.radians(215.0), el=math.radians(24.0), r=2.6)
W, H = 800.0, 600.0


# --------------------------------------------------------------- the page's math
def _sub(a, b): return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
def _add(a, b): return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]
def _scl(a, k): return [a[0]*k, a[1]*k, a[2]*k]
def _dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _cross(a, b):
  return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _norm(a):
  n = math.sqrt(_dot(a, a))
  return [0.0, 0.0, 0.0] if n < 1e-12 else [a[0]/n, a[1]/n, a[2]/n]


def cam_basis(az: float, el: float, r: float, target=(0.0, 0.0, 0.0)):
  """``camBasis`` from the page, verbatim: +Z is world up, always."""
  t = list(target)
  direction = [math.cos(el)*math.cos(az), math.cos(el)*math.sin(az), math.sin(el)]
  eye = _add(t, _scl(direction, r))
  fwd = _norm(_sub(t, eye))
  right = _norm(_cross(fwd, [0.0, 0.0, 1.0]))
  up = _cross(right, fwd)
  return dict(eye=eye, fwd=fwd, right=right, up=up)


def project(view, p, r: float, persp: bool = True):
  """``project`` from the page. Screen +y points DOWN, so world +Z draws upward."""
  v = _sub(list(p), view["eye"])
  d = _dot(v, view["fwd"])
  if d <= 1e-4:
    return None
  xs, ys = _dot(v, view["right"]), _dot(v, view["up"])
  s = (H/2)/math.tan(FOV_Y/2)/d if persp else (H/2)/(r*math.tan(FOV_Y/2))
  return dict(x=W/2 + xs*s, y=H/2 - ys*s, d=d)


def _home_view():
  return cam_basis(HOME["az"], HOME["el"], HOME["r"])


# ------------------------------------------------------------------- 1. up is up
def test_world_z_draws_above_the_origin():
  v = _home_view()
  o = project(v, (0, 0, 0), HOME["r"])
  pz = project(v, (0, 0, 0.5), HOME["r"])
  assert o and pz
  assert pz["y"] < o["y"] - 1, "world +Z must render upward; screen y grows downward"


def test_ground_plane_is_xy_not_xz():
  """A Z-up world puts the floor on z = 0. Two points spread across it must land
  at clearly different screen positions and neither above the world +Z tip."""
  v = _home_view()
  a = project(v, (1.0, 0.0, 0.0), HOME["r"])
  b = project(v, (0.0, 1.0, 0.0), HOME["r"])
  top = project(v, (0.0, 0.0, 1.0), HOME["r"])
  assert a and b and top
  assert abs(a["x"] - b["x"]) > 10, "the two floor axes must be visibly distinct"
  assert top["y"] < min(a["y"], b["y"]), "the +Z tip must sit above both floor axes"


# --------------------------------------------------- 2. right-handed looks right-handed
def test_right_handed_x_rotation_moves_y_upward():
  """The exact sense reported inverted, twice. A right-handed +90 deg rotation
  about world +X carries +Y onto +Z, so on screen the tip must move UP. Under
  the old reflecting map (x, z, y) this came out downward."""
  v = _home_view()
  before = project(v, (0.0, 0.5, 0.0), HOME["r"])
  after = project(v, (0.0, 0.0, 0.5), HOME["r"])       # Rx(+90) . (0, 0.5, 0)
  assert before and after
  assert after["y"] < before["y"] - 1


def test_x_rotation_sense_holds_from_every_azimuth():
  """Not an artefact of one camera angle: sweeping a body vector through a
  right-handed rotation about +X must trace the same sense from anywhere the
  rotation plane is not seen edge-on."""
  for deg in range(0, 360, 15):
    az = math.radians(deg)
    v = cam_basis(az, HOME["el"], HOME["r"])
    # +Y rotated by +30 deg about +X: (0, cos30, sin30)
    a = project(v, (0.0, 0.5, 0.0), HOME["r"])
    b = project(v, (0.0, 0.5*math.cos(math.radians(30)), 0.5*math.sin(math.radians(30))),
                HOME["r"])
    assert a and b
    assert b["y"] <= a["y"] + 1e-6, f"+X rotation looks inverted at azimuth {deg} deg"


# ------------------------------------------------------ 3. the scene follows the pointer
def test_dragging_right_carries_the_front_to_the_right():
  """`cam.az -= dx * ROT_PER_PX`. The derivation is written out in the page; this
  asserts the conclusion, which is what an operator actually experiences."""
  v = _home_view()
  # on the object's near face, straight toward the camera - not AT the eye,
  # where depth is zero and the projection correctly refuses the point
  front = _scl(_norm(v["eye"]), 0.5)
  before = project(v, front, HOME["r"])
  v2 = cam_basis(HOME["az"] - 40*ROT_PER_PX, HOME["el"], HOME["r"])   # dragged 40 px right
  after = project(v2, front, HOME["r"])
  assert before and after
  assert after["x"] > before["x"] + 1


def test_dragging_down_shows_more_of_the_top():
  """`cam.el += dy * ROT_PER_PX`, and screen y grows downward, so dragging down
  raises the camera - the world +Z tip must move toward the screen centre."""
  v = _home_view()
  before = project(v, (0, 0, 0.5), HOME["r"])
  v2 = cam_basis(HOME["az"], HOME["el"] + 40*ROT_PER_PX, HOME["r"])
  after = project(v2, (0, 0, 0.5), HOME["r"])
  assert before and after
  assert after["y"] > before["y"], "raising the camera must foreshorten the +Z arrow"


def test_elevation_clamp_keeps_the_right_vector_defined():
  """`right = fwd x worldUp` collapses at exactly vertical, which is why the page
  clamps elevation to 89.5 deg. At the clamp it must still be a usable basis."""
  v = cam_basis(HOME["az"], math.radians(89.5), HOME["r"])
  assert math.sqrt(_dot(v["right"], v["right"])) > 0.9
  assert abs(_dot(v["right"], v["fwd"])) < 1e-9


# ------------------------------------------------------------- the page itself
def _source() -> str:
  return VIEWER.read_text()


def test_no_external_dependency_remains():
  """Both libraries came from public CDNs; with no route to them the 3D block
  threw on load and the viewer simply did not navigate."""
  src = _source()
  assert "three.min.js" not in src and "OrbitControls" not in src
  # no <script src=>, no fetched stylesheet, no https:// outside prose
  assert "<script src=" not in src and "<link " not in src
  page = src[src.index("HTML_PAGE"):]
  assert "https://" not in page, "the page must fetch nothing at load"


def test_no_axis_remapping_remains():
  """The whole class of rotation-sense bug came from mapping sensor axes into a
  Y-up frame. Nothing may reintroduce a `toThree`-style transform."""
  src = _source()
  assert "toThree" not in src
  assert "camera.up" not in src


def test_page_declares_the_same_constants_this_file_tests():
  src = _source()
  assert f"const ROT_PER_PX = {ROT_PER_PX}" in src
  assert "cam.az -= dx * ROT_PER_PX" in src, "drag right must decrease azimuth"
  assert "cam.el = Math.max(-EL_LIMIT, Math.min(EL_LIMIT, cam.el + dy * ROT_PER_PX))" in src
  m = re.search(r"const HOME = \{ az: ([\d.]+) \* DEG, el: ([\d.]+) \* DEG, r: ([\d.]+) \}", src)
  assert m, "HOME camera not found"
  assert (float(m.group(1)), float(m.group(2)), float(m.group(3))) == (215.0, 24.0, 2.6)


def test_page_runs_its_own_self_check():
  """The same three properties are asserted in the browser and reported in the
  readout, so a user can see the verdict without running this file."""
  src = _source()
  assert "function selfCheck()" in src and "selfCheck();" in src
  assert 'id="v-selfcheck"' in src
  for needle in ["+Z is not up on screen", "+X rotation sense is inverted",
                 "drag direction is inverted"]:
    assert needle in src


def test_navigation_is_actually_wired():
  """The original report was that the view could not be navigated at all."""
  src = _source()
  for needle in ["pointerdown", "pointermove", "pointerup", "wheel", "keydown",
                 "btn-view-x", "btn-view-y", "btn-view-z", "btn-reset-view"]:
    assert needle in src, needle


# ------------------------------------------- the physical board (2026-09-08)
BOARD_MM = {"x": 16.3, "y": 18.6, "z": 3.05}
MM_PER_UNIT = 62.0


def test_board_dimensions_are_the_manufacturers():
  """User: "IMU (body frame) 시각화 부분에, 실제 H/W IMU 의 X/Y/Z 축 시각화 추가해 줘."

  The three arrows say which way the axes point but not which way the THING is lying, so
  there was nothing on screen to check against the object on the bench. The board is now
  drawn - and drawn to the manufacturer's real dimensions rather than a guessed cube:
  16.3 (W) x 18.6 (H) x 3.05 (D) mm, EBIMU-9DOFV6 manual section 9, with the manual's own
  gyroscope-axis diagram (section 4-3) putting X and Y in the plane and Z out of it.

  Asserted here because a "to scale" label that is not to scale is worse than no label: it
  invites someone to read a mounting angle off the picture.
  """
  src = _source()
  assert "const BOARD_MM = { x: 16.3, y: 18.6, z: 3.05 };" in src
  assert "16.3 &times; 18.6 &times; 3.05 mm" in src, "the legend must state the real size"
  assert "section 9" in src and "4-3" in src, "cite where the numbers came from"


def test_board_is_a_thin_card_not_a_cube():
  """The whole point of using real dimensions is that the proportions carry information."""
  assert BOARD_MM["z"] < BOARD_MM["x"] / 4
  assert BOARD_MM["z"] < BOARD_MM["y"] / 4
  longest = max(BOARD_MM.values()) / MM_PER_UNIT
  assert longest < 0.5, "the board must sit inside the 0.5-long body arrows, not swallow them"
  assert longest > 0.15, "...but still be big enough to read an attitude off"


def test_board_is_built_from_the_same_axes_as_the_arrows():
  """If the box were built from its own copy of the rotation it could drift out of step with
  the arrows, and the picture would be quietly wrong in exactly the case it exists for."""
  src = _source()
  m = re.search(r"function boardCorners\(\)\s*\{.*?\n\}", src, re.S)
  assert m, "boardCorners() not found"
  body = m.group(0)
  for axis in ("S.body_x", "S.body_y", "S.body_z"):
    assert axis in body, axis
  assert "quat" not in body and "toThree" not in body, (
    "the board must reuse the measured body axes, never re-derive a rotation of its own"
  )


def test_board_carries_a_fiducial():
  """A rectangular slab is symmetric: a 180 degree mounting error looks identical without a
  corner marker, which is precisely the error this view exists to catch."""
  src = _source()
  m = re.search(r"function drawBoard\(\)\s*\{.*?\n\}", src, re.S)
  assert m, "drawBoard() not found"
  body = m.group(0)
  assert "+X+Y" in body, "the marked corner must be named on screen"
  assert "NOT a claim about the silkscreen" in body, (
    "the marker is drawn by us; the comment must not let a reader take it for a board feature"
  )


def test_the_body_arrows_are_labelled():
  src = _source()
  for axis, colour in (("X", "#ff5555"), ("Y", "#55ff77"), ("Z", "#5599ff")):
    assert f"qtext(scl(S.body_{axis.lower()}, 0.56), '{axis}', '{colour}'" in src, axis


def test_the_board_can_be_switched_off():
  src = _source()
  assert 'id="chk-board"' in src and "S.showBoard" in src
  assert "if (S.showBoard) drawBoard();" in src
