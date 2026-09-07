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
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
const wrap = document.getElementById('canvas-wrap');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x111318);
const camera = new THREE.PerspectiveCamera(50, window.innerWidth/window.innerHeight, 0.01, 100);
camera.position.set(1.6, 1.2, 1.6);
const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(window.innerWidth, window.innerHeight);
wrap.appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.target.set(0,0,0);

const grid = new THREE.GridHelper(2, 20, 0x333844, 0x22252e);
scene.add(grid);
// NOTE: THREE.AxesHelper's default colors are red/green/blue for X/Y/Z --
// identical to the body-axis arrow colors below. A FIXED world reference
// triad sitting at the same origin as the ROTATING body triad, in the same
// colors, is very easy to mistake for "the axes rotating the wrong way"
// when they're actually just two different things overlapping. Kept, but
// recolored to a single dim neutral so it reads as "reference", not "data".
const worldAxes = new THREE.AxesHelper(0.4);
worldAxes.setColors(0x555a66, 0x555a66, 0x555a66);
scene.add(worldAxes);

function makeArrow(color, len) {
  const dir = new THREE.Vector3(0,0,1);
  const origin = new THREE.Vector3(0,0,0);
  const a = new THREE.ArrowHelper(dir, origin, len, color, len*0.22, len*0.12);
  scene.add(a);
  return a;
}
const arrowX = makeArrow(0xff5555, 0.5);
const arrowY = makeArrow(0x55ff77, 0.5);
const arrowZ = makeArrow(0x5599ff, 0.5);
const arrowAccelDown = makeArrow(0xffcc33, 0.6);

// fixed reference: true world down
const refDown = makeArrow(0x888888, 0.6);
refDown.setDirection(new THREE.Vector3(0,-1,0).normalize());
refDown.line.material.transparent = true;
refDown.line.material.opacity = 0.5;
refDown.cone.material.transparent = true;
refDown.cone.material.opacity = 0.5;

const trailMax = 4000;
const trailGeom = new THREE.BufferGeometry();
const trailPos = new Float32Array(trailMax*3);
trailGeom.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
trailGeom.setDrawRange(0,0);
const trailLine = new THREE.Line(trailGeom, new THREE.LineBasicMaterial({color:0x33ddff}));
scene.add(trailLine);

const compGeom = new THREE.BufferGeometry();
const compPos = new Float32Array(trailMax*3);
compGeom.setAttribute('position', new THREE.BufferAttribute(compPos, 3));
compGeom.setDrawRange(0,0);
const compLine = new THREE.Line(compGeom, new THREE.LineBasicMaterial({color:0xff66ff}));
compLine.visible = false;
scene.add(compLine);

document.getElementById('chk-computed').addEventListener('change', (e) => {
  compLine.visible = e.target.checked;
});
document.getElementById('btn-reset-view').addEventListener('click', () => {
  camera.up.set(0,1,0);
  camera.position.set(1.6, 1.2, 1.6);
  controls.target.set(0,0,0);
  camera.lookAt(controls.target);
  controls.update();
});

// Lock the camera to look straight down one SENSOR axis at a time, with no
// perspective/isometric foreshortening -- the only way to judge rotation
// SENSE about an axis by eye without ambiguity is to view along that axis.
// Sensor->three.js mapping used everywhere else: three=(sensor.x, sensor.z, -sensor.y).
function lookDownSensorAxis(threePos, up) {
  camera.up.copy(up);
  camera.position.copy(threePos);
  controls.target.set(0,0,0);
  camera.lookAt(controls.target);
  controls.update();
}
document.getElementById('btn-view-x').addEventListener('click', () => {
  // sensor +X == three +X
  lookDownSensorAxis(new THREE.Vector3(2,0,0), new THREE.Vector3(0,1,0));
});
document.getElementById('btn-view-y').addEventListener('click', () => {
  // sensor +Y == three -Z
  lookDownSensorAxis(new THREE.Vector3(0,0,-2), new THREE.Vector3(0,1,0));
});
document.getElementById('btn-view-z').addEventListener('click', () => {
  // sensor +Z == three +Y; camera.up can't be parallel to the view direction
  lookDownSensorAxis(new THREE.Vector3(0,2,0), new THREE.Vector3(1,0,0));
});

// NOTE: sensor gives (x,y,z) in its own body/world convention (Z up when
// level, per HUPHY docs). three.js default is Y-up, so we remap axes for
// display only. A plain component swap (x, z, y) is a REFLECTION (det=-1),
// not a rotation -- it preserves static vector directions but inverts the
// visual sense of rotation about whichever axis isn't swapped (X here).
// This was caught because rotating the physical sensor about X visibly
// rotated the on-screen arrows the wrong way. The fix is a proper -90 deg
// rotation about X (det=+1): three.x=x, three.y=z, three.z=-y.
function toThree(v) { return new THREE.Vector3(v[0], v[2], -v[1]); }

function setArrow(arrow, vec3, len) {
  const n = vec3.length();
  if (n > 1e-6) {
    arrow.setDirection(vec3.clone().normalize());
    arrow.setLength(len, len*0.22, len*0.12);
  }
}

// Fixed-width number formatting so the HUD doesn't jump around as values
// change sign or gain/lose a digit. Always shows a sign and pads with
// leading spaces (not zeros) to a constant width; `white-space:pre` on the
// value spans (see CSS) is required for the padding to actually render.
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

let lastDropped = 0, lastPolls = 0;
evtSource.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  const s = msg.sample;
  if (s) {
    setArrow(arrowX, toThree(s.body_x), 0.5);
    setArrow(arrowY, toThree(s.body_y), 0.5);
    setArrow(arrowZ, toThree(s.body_z), 0.5);
    setArrow(arrowAccelDown, toThree(s.accel_down_world), 0.6);

    const dv = toThree(s.accel_down_world).normalize();
    const trueDown = new THREE.Vector3(0,-1,0);
    const tiltDeg = THREE.MathUtils.radToDeg(dv.angleTo(trueDown));
    const gyroMag = Math.sqrt(s.gyro_dps[0]**2 + s.gyro_dps[1]**2 + s.gyro_dps[2]**2);
    // Above ~60 dps, real inertial acceleration swamps the accel-vs-gravity
    // comparison (verified empirically: static-hold tilt error ~0.03 rad,
    // fast-rotation tilt error ~0.6 rad on the same sensor) -- the tilt
    // reading is only a trustworthy static-mismatch signal below that.
    // [STATIC]/[MOVING] are kept the same length so this line never shifts.
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

  const trail = msg.trail;
  const n = Math.min(trail.length, trailMax);
  for (let i=0;i<n;i++) {
    const p = toThree(trail[trail.length-n+i]);
    trailPos[i*3]=p.x; trailPos[i*3+1]=p.y; trailPos[i*3+2]=p.z;
  }
  trailGeom.setDrawRange(0,n);
  trailGeom.attributes.position.needsUpdate = true;

  const ctrail = msg.computed_trail;
  const cn = Math.min(ctrail.length, trailMax);
  for (let i=0;i<cn;i++) {
    const p = toThree(ctrail[ctrail.length-cn+i]);
    compPos[i*3]=p.x; compPos[i*3+1]=p.y; compPos[i*3+2]=p.z;
  }
  compGeom.setDrawRange(0,cn);
  compGeom.attributes.position.needsUpdate = true;
};

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth/window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
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
