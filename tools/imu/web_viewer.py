#!/usr/bin/env python3
"""Live browser viewer for a single EBIMU: 3D attitude triad + odometry trail.

Read-only. Uses HUPHY's actual deployment class
(``huphy.sensors.ebimu.imu.EbimuImu``) to read the sensor -- this script never
writes a byte to the serial port. It runs a tiny stdlib HTTP server (no Flask,
no websockets -- nothing beyond the vendored ``pyserial`` this project already
uses) that serves one HTML page and pushes live samples to it over
Server-Sent Events.

Why this exists
----------------
Sensor mounting / quaternion axis-order bugs are hard to catch from numbers
alone -- a swapped or sign-flipped axis often "looks reasonable" in a table.
This page draws two things that must coincide if attitude and accelerometer
agree with each other, on a sensor at rest:

  * the IMU body axes (X/Y/Z arrows), rotated into world frame by the
    quaternion -- this is "attitude".
  * a separate arrow: the raw accelerometer vector, ALSO rotated into world
    frame by the *same* quaternion. If the quaternion and the raw
    accelerometer axes actually agree, this arrow points straight down
    (world -Z) *no matter how the sensor is tilted*, because rotating a
    body-frame "up" vector by the very rotation that produced it must give
    back world "up" -- that is a tautology only if both signals share one
    consistent body frame. If they don't, this arrow visibly wanders off
    vertical as you tilt the sensor, and which way it leans tells you which
    axis is wrong.

A third trail shows odometry: the position EBIMU reports on its own `dist`
output block, plotted as a fading trail from the origin.

Run
---
    python3 web_viewer.py \\
        --huphy-src ~/HUPHY/src --pydeps ~/pydeps \\
        --port /dev/ttyUSB0 --output quat,gyro,accel,dist,temp,time \\
        --http-port 8899

Then open ``http://<this-host>:8899/`` from any browser on the same network.
Stop with Ctrl-C; ``EbimuImu.disconnect()`` runs in a ``finally`` either way.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


# --------------------------------------------------------------------------
# Quaternion -> rotation matrix, verified to match HUPHY's own
# gravity_from_quat() convention (g_body = R^T @ (0,0,-1)_world, R = body->world).
# See tools/imu/README.md for the numeric check that pinned this down; do not
# "simplify" the signs here without re-checking against gravity_from_quat.
# --------------------------------------------------------------------------
def quat_to_R(w: float, x: float, y: float, z: float):
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


def mat_vec(R, v):
    return (
        R[0][0] * v[0] + R[0][1] * v[1] + R[0][2] * v[2],
        R[1][0] * v[0] + R[1][1] * v[1] + R[1][2] * v[2],
        R[2][0] * v[0] + R[2][1] * v[1] + R[2][2] * v[2],
    )


def normalize(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-9:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


# Empirical calibration, 2026-09-02: a 90s rotation capture (2053 points,
# see tools/imu/measurements/2026-09-02/rotation_capture_20260902_2106.csv)
# found accel_x consistently equal to +gravity_x instead of -gravity_x
# (94.6% of samples), while Y and Z already satisfy the expected
# gravity = -normalize(accel) relation to within 0.001. Independently
# re-verified with a from-scratch script bypassing HUPHY/this viewer
# entirely (raw pyserial read + hand-parsed wire fields). HUPHY's own
# `gravity` field (used as `projected_gravity` in policy.py) is computed
# purely from the quaternion and does NOT depend on accel, so this
# correction only affects the diagnostic accel-vs-gravity comparison
# below (the yellow arrow / computed trail) -- it does not, and cannot,
# change `projected_gravity` itself. Root cause undetermined (datasheet
# doesn't document a quaternion axis diagram to check against); applying
# as a per-unit calibration constant pending vendor confirmation.
ACCEL_CORRECTION = (-1.0, 1.0, 1.0)


# --------------------------------------------------------------------------
# Shared live state, updated by the reader thread, read by SSE handlers.
# --------------------------------------------------------------------------
class LiveState:
    def __init__(self, trail_max_points: int, g_mps2: float) -> None:
        self.lock = threading.Lock()
        self.sample: dict | None = None
        self.trail: deque = deque(maxlen=trail_max_points)
        self.computed_trail: deque = deque(maxlen=trail_max_points)
        self.dropped = 0
        self.host_polls = 0
        self.unique_packets = 0
        self.g_mps2 = g_mps2
        self.accel_correction = ACCEL_CORRECTION
        # dead-reckoning state for the "computed" (drifts fast) trail
        self._dr_vel = [0.0, 0.0, 0.0]
        self._dr_pos = [0.0, 0.0, 0.0]
        self._dr_last_t: float | None = None

    def update(self, state, imu_dropped: int) -> None:
        with self.lock:
            self.dropped = imu_dropped
            self.host_polls += 1
            if not state.is_valid:
                return
            gravity = state.gravity
            gyro = state.gyro_dps
            accel = state.accel_mps2  # raw wire values, uncorrected -- for the HUD readout
            accel_corrected = tuple(a * c for a, c in zip(accel, self.accel_correction))
            qw = state.extra.get("qw", 1.0)
            qx = state.extra.get("qx", 0.0)
            qy = state.extra.get("qy", 0.0)
            qz = state.extra.get("qz", 0.0)
            R = quat_to_R(qw, qx, qy, qz)

            body_x = mat_vec(R, (1.0, 0.0, 0.0))
            body_y = mat_vec(R, (0.0, 1.0, 0.0))
            body_z = mat_vec(R, (0.0, 0.0, 1.0))

            accel_dir_body = normalize(accel_corrected)
            # Flip sign so a *correctly* mounted+decoded sensor draws this
            # pointing straight down (0,0,-1) in world, same convention as
            # `gravity`, so it can be compared to the fixed reference arrow.
            accel_down_world = mat_vec(R, tuple(-c for c in accel_dir_body))

            new_packet = self.sample is None or self.sample.get("stamp") != state.stamp
            if new_packet:
                dx = state.extra.get("dx", 0.0)
                dy = state.extra.get("dy", 0.0)
                dz = state.extra.get("dz", 0.0)
                self.trail.append((dx, dy, dz))
                self.unique_packets += 1

                # crude world-frame double integration for comparison; not a
                # real odometry filter, drifts within seconds -- diagnostic only
                now = state.stamp
                if self._dr_last_t is not None:
                    dt = now - self._dr_last_t
                    if 0.0 < dt < 0.5:
                        accel_world = mat_vec(R, accel_corrected)
                        lin_world = (
                            accel_world[0],
                            accel_world[1],
                            accel_world[2] - self.g_mps2,
                        )
                        for i in range(3):
                            self._dr_vel[i] += lin_world[i] * dt
                            self._dr_pos[i] += self._dr_vel[i] * dt
                        self.computed_trail.append(tuple(self._dr_pos))
                self._dr_last_t = now

            self.sample = {
                "stamp": state.stamp,
                "quat": [qw, qx, qy, qz],
                "gravity": list(gravity),
                "gyro_dps": list(gyro),
                "accel_mps2": list(accel),
                "accel_corrected_mps2": list(accel_corrected),
                "body_x": list(body_x),
                "body_y": list(body_y),
                "body_z": list(body_z),
                "accel_down_world": list(accel_down_world),
                "dist": [
                    state.extra.get("dx", 0.0),
                    state.extra.get("dy", 0.0),
                    state.extra.get("dz", 0.0),
                ],
                "temp_c": state.extra.get("temp", 0.0),
                "roll": state.extra.get("roll", 0.0),
                "pitch": state.extra.get("pitch", 0.0),
                "yaw": state.extra.get("yaw", 0.0),
            }

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "sample": self.sample,
                "trail": list(self.trail),
                "computed_trail": list(self.computed_trail)[-500:],
                "dropped": self.dropped,
                "host_polls": self.host_polls,
                "unique_packets": self.unique_packets,
            }


def reader_thread(imu, live: LiveState, poll_hz: float, stop_event: threading.Event) -> None:
    period = 1.0 / poll_hz
    while not stop_event.is_set():
        t0 = time.monotonic()
        state = imu.read()
        live.update(state, imu.dropped)
        sleep_for = period - (time.monotonic() - t0)
        if sleep_for > 0:
            time.sleep(sleep_for)


# --------------------------------------------------------------------------
# HTTP / SSE server
# --------------------------------------------------------------------------
HTML_PAGE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EBIMU live viewer</title>
<style>
  html, body { margin:0; height:100%; background:#111318; color:#e8e8ec; font-family: ui-monospace, Menlo, Consolas, monospace; }
  #canvas-wrap { position:absolute; inset:0; }
  #hud { position:absolute; top:10px; left:10px; background:rgba(15,17,22,0.82); border:1px solid #2a2e38;
         border-radius:8px; padding:10px 14px; font-size:12px; line-height:1.55; min-width:300px; }
  #hud h1 { font-size:13px; margin:0 0 6px 0; color:#9fd; }
  #hud .row { display:flex; justify-content:space-between; gap:14px; }
  #hud .lbl { color:#8a90a0; flex:0 0 auto; }
  #hud .row > span:last-child { white-space:pre; text-align:right; }
  #hud .warn { color:#ff6b6b; font-weight:bold; }
  #hud .ok { color:#6bff9e; }
  #legend { position:absolute; bottom:10px; left:10px; background:rgba(15,17,22,0.82); border:1px solid #2a2e38;
            border-radius:8px; padding:8px 12px; font-size:11px; line-height:1.6; }
  .swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:-1px; }
  #controls { position:absolute; top:10px; right:10px; background:rgba(15,17,22,0.82); border:1px solid #2a2e38;
              border-radius:8px; padding:8px 12px; font-size:12px; }
  #controls label { display:block; margin:4px 0; cursor:pointer; }
  button { background:#23262f; color:#e8e8ec; border:1px solid #3a3f4c; border-radius:6px; padding:4px 8px; cursor:pointer; font-size:11px; }
  button:hover { background:#2c3040; }
</style>
</head>
<body>
<div id="canvas-wrap"></div>
<div id="hud">
  <h1>EBIMU live</h1>
  <div class="row"><span class="lbl">3D self-check</span><span id="v-selfcheck">-</span></div>
  <div class="row"><span class="lbl">quat (w,x,y,z)</span><span id="v-quat">-</span></div>
  <div class="row"><span class="lbl">gravity (body)</span><span id="v-grav">-</span></div>
  <div class="row"><span class="lbl">gyro dps</span><span id="v-gyro">-</span></div>
  <div class="row"><span class="lbl">accel m/s^2</span><span id="v-accel">-</span></div>
  <div class="row"><span class="lbl">dist (dx,dy,dz)</span><span id="v-dist">-</span></div>
  <div class="row"><span class="lbl">roll/pitch/yaw</span><span id="v-rpy">-</span></div>
  <div class="row"><span class="lbl">temp C</span><span id="v-temp">-</span></div>
  <div class="row"><span class="lbl">down-arrow tilt off vertical</span><span id="v-tilt">-</span></div>
  <div class="row"><span class="lbl">gyro |w| (motion speed)</span><span id="v-gyromag">-</span></div>
  <div class="row"><span class="lbl">dropped lines / polls</span><span id="v-drop">-</span></div>
  <div class="row"><span class="lbl">stream</span><span id="v-conn">connecting…</span></div>
</div>
<div id="legend">
  <div><span class="swatch" style="background:#ff5555"></span>body X</div>
  <div><span class="swatch" style="background:#55ff77"></span>body Y</div>
  <div><span class="swatch" style="background:#5599ff"></span>body Z</div>
  <div><span class="swatch" style="background:#ffcc33"></span>accel-implied down (X-corrected, rotated by quat)</div>
  <div><span class="swatch" style="background:#888;border:1px dashed #ccc"></span>true world down (reference)</div>
  <div><span class="swatch" style="background:#33ddff"></span>odometry trail (sensor `dist`)</div>
  <div><span class="swatch" style="background:#ff66ff"></span>computed trail (double-integrated accel, drifts)</div>
</div>
<div id="controls">
  <label><input type="checkbox" id="chk-computed"> show computed trail</label>
  <div style="margin-top:6px;">look straight down an axis (removes perspective ambiguity):</div>
  <div style="display:flex; gap:4px; margin-top:4px;">
    <button id="btn-view-x">-X</button>
    <button id="btn-view-y">-Y</button>
    <button id="btn-view-z">-Z</button>
    <button id="btn-reset-view">reset</button>
  </div>
</div>
<script>
/* ===========================================================================
   From-scratch 3D view.  No library, no CDN, no Y-up.

   Why this is hand-written (2026-09-07, user: "뷰어의 x 축 회전이 반대인데,
   Y-UP 인 THREE.JS 쓰지말고 제로부터 구현하던가 해"):

   * The sensor's world is RIGHT-HANDED, +Z UP.  three.js is Y-up, so every
     earlier version of this page carried a sensor->library axis mapping, and
     every rotation-sense bug this viewer has had came out of that mapping.
     The first attempt was a plain component swap (x,z,y), which is a
     REFLECTION (determinant -1): it leaves static arrows pointing the right
     way while inverting the visual sense of rotation.  It was replaced by a
     proper -90 deg rotation about X, and the sense was reported wrong again.
     The mapping is now GONE.  Sensor coordinates are drawn verbatim; there is
     no axis transform anywhere in this file, so the class of bug cannot come
     back.
   * Both libraries were loaded from public CDNs.  With no route to them the
     whole 3D block throws on load, which looks exactly like "the viewer does
     not navigate" - no camera, no controls, no drawing at all.  Nothing here
     is fetched.

   Conventions, stated once and asserted by the self-check at the bottom:
     world      right-handed, +X / +Y horizontal, +Z up
     camera     orbits `target` at distance r, azimuth `az` about +Z,
                elevation `el` up from the XY plane
     screen     +x right, +y DOWN (canvas convention), so world +Z draws upward
     drag       the scene follows the pointer: drag right -> the face toward
                you swings right (az DECREASES, derived below); drag down ->
                you see more of the top (el INCREASES)
   ========================================================================= */

const wrap = document.getElementById('canvas-wrap');
const cv = document.createElement('canvas');
cv.style.width = '100%'; cv.style.height = '100%'; cv.style.display = 'block';
cv.style.touchAction = 'none'; cv.style.cursor = 'grab';
cv.tabIndex = 0;
wrap.appendChild(cv);
const ctx = cv.getContext('2d');

const DEG = Math.PI / 180;
const HOME = { az: 215 * DEG, el: 24 * DEG, r: 2.6 };
const cam = { az: HOME.az, el: HOME.el, r: HOME.r, tx: 0, ty: 0, tz: 0, persp: true };
const FOV_Y = 50 * DEG;
const EL_LIMIT = 89.5 * DEG;   // never let the view direction meet world up

// ---- small vector helpers (world space, all Z-up) -------------------------
const sub = (a, b) => [a[0]-b[0], a[1]-b[1], a[2]-b[2]];
const add = (a, b) => [a[0]+b[0], a[1]+b[1], a[2]+b[2]];
const scl = (a, k) => [a[0]*k, a[1]*k, a[2]*k];
const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const vlen = (a) => Math.hypot(a[0], a[1], a[2]);
function norm(a) { const n = vlen(a); return n < 1e-12 ? [0,0,0] : [a[0]/n, a[1]/n, a[2]/n]; }

// ---- camera basis ---------------------------------------------------------
// The eye sits on a sphere around the target; `fwd` looks back at the target.
// `right` is fwd x worldUp, which is why elevation is clamped short of 90 deg:
// at exactly vertical those two are parallel and `right` collapses to zero.
function camBasis(c) {
  const t = [c.tx, c.ty, c.tz];
  const dir = [Math.cos(c.el)*Math.cos(c.az), Math.cos(c.el)*Math.sin(c.az), Math.sin(c.el)];
  const eye = add(t, scl(dir, c.r));
  const fwd = norm(sub(t, eye));
  const right = norm(cross(fwd, [0, 0, 1]));
  const up = cross(right, fwd);        // unit already: right and fwd are orthonormal
  return { eye, fwd, right, up };
}

let VIEW = camBasis(cam);
function refreshView() { VIEW = camBasis(cam); }

// ---- projection -----------------------------------------------------------
// Returns {x, y, d} in CSS pixels, or null when the point is behind the eye.
// `d` is depth along the view direction, used only for back-to-front sorting.
let W = 1, H = 1;
function project(p) {
  const v = sub(p, VIEW.eye);
  const d = dot(v, VIEW.fwd);
  if (d <= 1e-4) return null;
  const xs = dot(v, VIEW.right);
  const ys = dot(v, VIEW.up);
  // Orthographic is for the axis-lock views: judging the SENSE of a rotation
  // by eye is only unambiguous looking straight down that axis with parallel
  // projection, where nothing is foreshortened.
  const s = cam.persp
    ? (H / 2) / Math.tan(FOV_Y / 2) / d
    : (H / 2) / (cam.r * Math.tan(FOV_Y / 2));
  return { x: W/2 + xs*s, y: H/2 - ys*s, d };   // screen +y is DOWN, hence the minus
}

// ---- draw list ------------------------------------------------------------
// Every primitive is queued with a depth, then painted back to front. The
// scene is a few hundred items, so a full sort per frame costs nothing.
let queue = [];
function qline(a, b, color, width, alpha) {
  const A = project(a), B = project(b);
  if (!A || !B) return;
  queue.push({ d: (A.d + B.d)/2, kind: 'line', A, B, color,
               width: width || 1, alpha: alpha === undefined ? 1 : alpha });
}
function qpoly(pts, color, alpha) {
  const P = pts.map(project);
  if (P.some((q) => !q)) return;
  queue.push({ d: P.reduce((s, q) => s + q.d, 0)/P.length, kind: 'poly', P, color,
               alpha: alpha === undefined ? 1 : alpha });
}
function qtext(p, text, color, dx, dy) {
  const A = project(p);
  if (!A) return;
  queue.push({ d: A.d, kind: 'text', A, text, color, dx: dx || 0, dy: dy || 0 });
}
function qpolyline(pts, color, width, alpha) {
  for (let i = 1; i < pts.length; i++) qline(pts[i-1], pts[i], color, width, alpha);
}

// An arrow: a shaft plus a head drawn as a triangle in the plane containing the
// shaft and facing the camera, so it still reads as a head from any angle.
function qarrow(from, dir, length, color, alpha) {
  const d = norm(dir);
  if (vlen(d) < 0.5) return;                    // zero/degenerate direction
  const tip = add(from, scl(d, length));
  const headLen = length * 0.22, headRad = length * 0.075;
  const base = add(from, scl(d, length - headLen));
  let side = cross(d, VIEW.fwd);
  if (vlen(side) < 1e-6) side = cross(d, VIEW.up);   // shaft points at the camera
  side = norm(side);
  qline(from, base, color, 2.5, alpha);
  qpoly([tip, add(base, scl(side, headRad)), add(base, scl(side, -headRad))], color, alpha);
}

function paint() {
  const dpr = window.devicePixelRatio || 1;
  const w = wrap.clientWidth || 1, h = wrap.clientHeight || 1;
  if (cv.width !== Math.round(w*dpr) || cv.height !== Math.round(h*dpr)) {
    cv.width = Math.round(w*dpr); cv.height = Math.round(h*dpr);
  }
  W = w; H = h;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#111318'; ctx.fillRect(0, 0, w, h);
  queue.length = 0;
  refreshView();
  buildScene();
  queue.sort((a, b) => b.d - a.d);              // far first
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.font = '11px ui-monospace, Menlo, Consolas, monospace';
  for (const it of queue) {
    ctx.globalAlpha = it.alpha === undefined ? 1 : it.alpha;
    if (it.kind === 'line') {
      ctx.strokeStyle = it.color; ctx.lineWidth = it.width;
      ctx.beginPath(); ctx.moveTo(it.A.x, it.A.y); ctx.lineTo(it.B.x, it.B.y); ctx.stroke();
    } else if (it.kind === 'poly') {
      ctx.fillStyle = it.color;
      ctx.beginPath(); ctx.moveTo(it.P[0].x, it.P[0].y);
      for (let i = 1; i < it.P.length; i++) ctx.lineTo(it.P[i].x, it.P[i].y);
      ctx.closePath(); ctx.fill();
    } else {
      ctx.fillStyle = it.color; ctx.fillText(it.text, it.A.x + it.dx, it.A.y + it.dy);
    }
  }
  ctx.globalAlpha = 1;
}

// ---- the scene ------------------------------------------------------------
// Straight from the server payload, in SENSOR/world coordinates. No mapping.
const S = {
  body_x: [1,0,0], body_y: [0,1,0], body_z: [0,0,1],
  accel_down: [0,0,-1],
  trail: [], computed: [], showComputed: false,
};

function buildScene() {
  // ground grid on the world XY plane (z = 0), because +Z is up
  const N = 10, step = 0.2, ext = N * step;
  for (let i = -N; i <= N; i++) {
    const c = (i === 0) ? '#3b4150' : '#22252e';
    qline([i*step, -ext, 0], [i*step, ext, 0], c, 1, 0.9);
    qline([-ext, i*step, 0], [ext, i*step, 0], c, 1, 0.9);
  }
  // Fixed world reference triad - deliberately ONE dim neutral colour, never
  // the body colours: a fixed triad in the same colours as the rotating one,
  // sharing an origin with it, is very easy to misread as "the axes are
  // turning the wrong way" when it is really two things overlapping.
  const REF = '#555a66';
  qarrow([0,0,0], [1,0,0], 0.4, REF, 0.85); qtext([0.44,0,0], 'X', REF, 3, 3);
  qarrow([0,0,0], [0,1,0], 0.4, REF, 0.85); qtext([0,0.44,0], 'Y', REF, 3, 3);
  qarrow([0,0,0], [0,0,1], 0.4, REF, 0.85); qtext([0,0,0.44], 'Z up', REF, 3, -3);
  // fixed true-world-down reference (gravity points -Z)
  qarrow([0,0,0], [0,0,-1], 0.6, '#888888', 0.5);
  // rotating body triad, exactly as the sensor reports it
  qarrow([0,0,0], S.body_x, 0.5, '#ff5555', 1);
  qarrow([0,0,0], S.body_y, 0.5, '#55ff77', 1);
  qarrow([0,0,0], S.body_z, 0.5, '#5599ff', 1);
  // accel-implied down, to compare against the grey reference above
  qarrow([0,0,0], S.accel_down, 0.6, '#ffcc33', 1);
  if (S.trail.length > 1) qpolyline(S.trail, '#33ddff', 1.5, 1);
  if (S.showComputed && S.computed.length > 1) qpolyline(S.computed, '#ff66ff', 1.5, 1);
}

// ---- navigation -----------------------------------------------------------
// Sign derivation for azimuth, so "it turns the wrong way" is settled by
// arithmetic instead of by taste. Put the camera at el=0, azimuth a; then
//   eye   = (cos a, sin a, 0)
//   fwd   = -eye
//   right = fwd x (0,0,1) = (-sin a, cos a, 0)
// Take the point on the object nearest the camera, P = (1,0,0) (its "front" at
// a = 0) and move the camera to a = D:
//   v  = P - eye = (1-cos D, -sin D, 0)
//   xs = v . right = -sin D (1-cos D) - cos D sin D  ~=  -D  for small D
// So INCREASING az drags the front to the LEFT. For the scene to follow the
// pointer, dragging right (dx > 0) must DECREASE az. Asserted in selfCheck().
const ROT_PER_PX = 0.008;      // radians per CSS pixel
let drag = null;

cv.addEventListener('pointerdown', (e) => {
  cv.focus();
  cv.setPointerCapture(e.pointerId);
  const pan = e.button === 2 || e.shiftKey || e.ctrlKey;
  drag = { x: e.clientX, y: e.clientY, pan };
  cv.style.cursor = pan ? 'move' : 'grabbing';
});
cv.addEventListener('pointermove', (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.x = e.clientX; drag.y = e.clientY;
  if (drag.pan) {
    // slide the target across the screen plane, so the scene follows the pointer
    const k = 2 * cam.r * Math.tan(FOV_Y/2) / Math.max(H, 1);
    const t = add([cam.tx, cam.ty, cam.tz],
                  add(scl(VIEW.right, -dx*k), scl(VIEW.up, dy*k)));
    cam.tx = t[0]; cam.ty = t[1]; cam.tz = t[2];
  } else {
    cam.az -= dx * ROT_PER_PX;                                  // see derivation above
    cam.el = Math.max(-EL_LIMIT, Math.min(EL_LIMIT, cam.el + dy * ROT_PER_PX));
  }
});
function endDrag(e) {
  if (!drag) return;
  drag = null; cv.style.cursor = 'grab';
  if (e && e.pointerId !== undefined && cv.hasPointerCapture(e.pointerId)) {
    cv.releasePointerCapture(e.pointerId);
  }
}
cv.addEventListener('pointerup', endDrag);
cv.addEventListener('pointercancel', endDrag);
cv.addEventListener('contextmenu', (e) => e.preventDefault());  // right-drag pans
cv.addEventListener('wheel', (e) => {
  e.preventDefault();
  cam.r = Math.max(0.3, Math.min(20, cam.r * Math.exp(e.deltaY * 0.0012)));
}, { passive: false });

// Keyboard, so the view is reachable without a mouse and without a trackpad
// gesture the browser might swallow. Arrow keys match the drag directions.
window.addEventListener('keydown', (e) => {
  const t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return;
  const step = e.shiftKey ? 10*DEG : 3*DEG;
  if (e.key === 'ArrowLeft') cam.az += step;
  else if (e.key === 'ArrowRight') cam.az -= step;
  else if (e.key === 'ArrowUp') cam.el = Math.min(EL_LIMIT, cam.el + step);
  else if (e.key === 'ArrowDown') cam.el = Math.max(-EL_LIMIT, cam.el - step);
  else if (e.key === '+' || e.key === '=') cam.r = Math.max(0.3, cam.r / 1.1);
  else if (e.key === '-' || e.key === '_') cam.r = Math.min(20, cam.r * 1.1);
  else if (e.key === 'r' || e.key === 'R') resetView();
  else return;
  e.preventDefault();
});

// ---- view buttons ---------------------------------------------------------
// Looking straight down a SENSOR axis, orthographic.
function lookAlong(az, el) {
  cam.az = az; cam.el = el; cam.tx = cam.ty = cam.tz = 0; cam.persp = false;
}
function resetView() {
  cam.az = HOME.az; cam.el = HOME.el; cam.r = HOME.r;
  cam.tx = cam.ty = cam.tz = 0; cam.persp = true;
}
document.getElementById('btn-view-x').onclick = () => lookAlong(0, 0);         // eye on +X
document.getElementById('btn-view-y').onclick = () => lookAlong(90*DEG, 0);    // eye on +Y
document.getElementById('btn-view-z').onclick = () => lookAlong(0, EL_LIMIT);  // eye above
document.getElementById('btn-reset-view').onclick = resetView;
document.getElementById('chk-computed').addEventListener('change', (e) => {
  S.showComputed = e.target.checked;
});

// ---- self-check -----------------------------------------------------------
// Runs once at load and prints its verdict into the HUD. The point is that the
// three properties this viewer has actually got wrong before are now checked by
// the page itself rather than by eye: up is up, a right-handed rotation looks
// right-handed, and the scene follows the pointer.
function selfCheck() {
  const save = JSON.stringify(cam);
  const fails = [];
  W = 800; H = 600;
  resetView();
  refreshView();

  // 1. world +Z must draw ABOVE the origin (smaller screen y).
  const o = project([0,0,0]), pz = project([0,0,0.5]);
  if (!o || !pz || !(pz.y < o.y - 1)) fails.push('+Z is not up on screen');

  // 2. A right-handed rotation of +90 deg about world +X sends +Y to +Z, so the
  //    tip must move UP the screen. This is the exact sense that was reported
  //    inverted; it can only hold while nothing remaps the axes.
  const py = project([0, 0.5, 0]);
  const pyRot = project([0, 0, 0.5]);          // Rx(+90) . (0,0.5,0) = (0,0,0.5)
  if (!py || !pyRot || !(pyRot.y < py.y - 1)) fails.push('+X rotation sense is inverted');

  // 3. Dragging right must carry the front of the object to the right. The probe
  //    sits on the object's near face - straight toward the camera from the
  //    target, but NOT at the eye itself, where depth is zero and project()
  //    correctly returns null.
  const front = scl(norm(VIEW.eye), 0.5);
  const before = project(front);
  cam.az -= 40 * ROT_PER_PX;                   // as if dragged 40 px right
  refreshView();
  const after = project(front);
  if (!before || !after || !(after.x > before.x + 1)) fails.push('drag direction is inverted');

  Object.assign(cam, JSON.parse(save));
  refreshView();
  const el = document.getElementById('v-selfcheck');
  if (el) {
    el.textContent = fails.length ? ('FAIL: ' + fails.join('; ')) : 'pass (up / X-sense / drag)';
    el.className = fails.length ? 'warn' : 'ok';
  }
  return fails;
}

// ---- HUD ------------------------------------------------------------------
// Fixed-width number formatting so the readout never jumps as values change
// sign or gain a digit. `white-space:pre` on the value spans (see CSS) is what
// makes the padding actually render.
function padNum(v, decimals, width) {
  const s = (v >= 0 ? '+' : '-') + Math.abs(v).toFixed(decimals);
  return s.padStart(width, ' ');
}
function fmt(arr, decimals=3, width=8) {
  return '[' + arr.map(v => padNum(v, decimals, width)).join(', ') + ']';
}
function padInt(n, width) { return String(n).padStart(width, ' '); }

const evtSource = new EventSource('/stream');
evtSource.onopen = () => { document.getElementById('v-conn').textContent = 'live'; document.getElementById('v-conn').className='ok'; };
evtSource.onerror = () => { document.getElementById('v-conn').textContent = 'disconnected'; document.getElementById('v-conn').className='warn'; };

const TRAIL_MAX = 4000;
evtSource.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  const s = msg.sample;
  if (s) {
    S.body_x = s.body_x; S.body_y = s.body_y; S.body_z = s.body_z;
    S.accel_down = s.accel_down_world;

    // Tilt: angle between the accel-implied down and true world down (0,0,-1),
    // both already in world coordinates - no display transform is involved.
    const dv = norm(s.accel_down_world);
    const tiltDeg = Math.acos(Math.max(-1, Math.min(1, dot(dv, [0,0,-1])))) / DEG;
    const gyroMag = Math.hypot(s.gyro_dps[0], s.gyro_dps[1], s.gyro_dps[2]);
    // Above ~60 dps real inertial acceleration swamps the accel-vs-gravity
    // comparison (measured on this sensor: 0.03 rad held still, 0.6 rad during
    // fast rotation), so the tilt number is only a trustworthy static-mismatch
    // signal below that. [STATIC]/[MOVING] are the same length so the line
    // never shifts.
    const moving = gyroMag > 60.0;

    const tiltEl = document.getElementById('v-tilt');
    tiltEl.textContent = padNum(tiltDeg, 2, 7) + ' deg ' + (moving ? '[MOVING]' : '[STATIC]');
    tiltEl.className = moving ? '' : (tiltDeg > 3.0 ? 'warn' : 'ok');

    const gyroEl = document.getElementById('v-gyromag');
    gyroEl.textContent = padNum(gyroMag, 1, 7) + ' dps';
    gyroEl.className = moving ? 'warn' : 'ok';

    document.getElementById('v-quat').textContent = fmt(s.quat, 4, 7);
    document.getElementById('v-grav').textContent = fmt(s.gravity, 3, 6);
    document.getElementById('v-gyro').textContent = fmt(s.gyro_dps, 1, 7);
    document.getElementById('v-accel').textContent = fmt(s.accel_mps2, 3, 8);
    document.getElementById('v-dist').textContent = fmt(s.dist, 3, 9);
    document.getElementById('v-rpy').textContent = fmt([s.roll, s.pitch, s.yaw], 1, 6);
    document.getElementById('v-temp').textContent = padNum(s.temp_c, 1, 6);
  }
  document.getElementById('v-drop').textContent = padInt(msg.dropped, 6) + ' / ' + padInt(msg.host_polls, 7);

  S.trail = msg.trail.slice(-TRAIL_MAX);
  S.computed = msg.computed_trail.slice(-TRAIL_MAX);
};

function animate() { paint(); requestAnimationFrame(animate); }
selfCheck();
animate();
</script>
</body>
</html>
"""


def make_handler(live: LiveState, push_hz: float):
    push_period = 1.0 / push_hz

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: A002 - quiet by default
            pass

        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/index.html":
                body = HTML_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    while True:
                        payload = json.dumps(live.snapshot())
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(push_period)
                except (BrokenPipeError, ConnectionResetError):
                    return
            else:
                self.send_response(404)
                self.end_headers()

    return Handler


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--huphy-src", required=True, type=Path)
    p.add_argument("--pydeps", required=True, type=Path, help="dir containing vendored serial/ package")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--output", required=True)
    p.add_argument("--poll-hz", type=float, default=200.0, help="host read-loop poll rate")
    p.add_argument("--push-hz", type=float, default=30.0, help="SSE push rate to browser")
    p.add_argument("--http-host", default="0.0.0.0")
    p.add_argument("--http-port", type=int, default=8899)
    p.add_argument("--trail-max-points", type=int, default=6000)
    p.add_argument("--g-mps2", type=float, default=9.80665)
    args = p.parse_args()

    sys.path.insert(0, str(args.pydeps))
    sys.path.insert(0, str(args.huphy_src))
    from huphy.sensors.ebimu.imu import EbimuImu  # noqa: E402

    output = tuple(x.strip() for x in args.output.split(",") if x.strip())
    imu = EbimuImu("viewer", args.port, baudrate=args.baudrate, output=output)
    imu.connect()
    print(f"connected: {imu}")

    live = LiveState(args.trail_max_points, args.g_mps2)
    stop_event = threading.Event()
    t = threading.Thread(target=reader_thread, args=(imu, live, args.poll_hz, stop_event), daemon=True)
    t.start()

    server = ThreadingHTTPServer((args.http_host, args.http_port), make_handler(live, args.push_hz))
    print(f"open http://<this-host>:{args.http_port}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.shutdown()
        imu.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
