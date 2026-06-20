# -*- coding: utf-8 -*-
"""Rotate the biped's geometry so its anatomical FORWARD (the hip-pitch swing direction)
aligns with +body-X — the convention Isaac Lab's velocity command/heading assumes.

Diagnosis: hip_pitch axis = X and the two legs are separated along X, so the robot's natural
walking (sagittal) direction is body-Y. Isaac Lab treats +body-X as "forward", so a forward
(vx) command made the policy crab-walk sideways. Fix = rotate the geometry -90 deg about Z
*inside* base_link (keep base_link's freejoint frame, so the articulation root / sensors are
unchanged). Only base_link's own geoms+inertial and its two first-level child bodies need the
rotation; their whole subtrees come along rigidly.

Edits assets/biped_lower_body_mjcf/robot.xml in place (keeps a .bak). robot_files/ stays untouched.
"""
import math, shutil, sys
import xml.etree.ElementTree as ET

XML = "/home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml"
ANG = +math.pi / 2.0  # +90 deg about Z  (toe/anatomical-forward -Y -> +X = command +vx = W)

# rotation quaternion (MuJoCo w,x,y,z) for ANG about Z
QR = (math.cos(ANG / 2), 0.0, 0.0, math.sin(ANG / 2))


def rot_pos(p):
    """Rotate a position by ANG about Z."""
    x, y, z = p
    c, s = math.cos(ANG), math.sin(ANG)
    return [x * c - y * s, x * s + y * c, z]


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def parse_floats(s):
    return [float(v) for v in s.split()]


def fmt(vals):
    return " ".join(f"{v:.6g}" for v in vals)


def main():
    shutil.copy(XML, XML + ".bak")
    tree = ET.parse(XML)
    root = tree.getroot()
    wb = root.find("worldbody")
    base = wb.find("body")  # base_link
    assert base.get("name") == "base_link", base.get("name")

    # 1) base_link inertial: rotate COM pos + compose orientation quat
    inert = base.find("inertial")
    inert.set("pos", fmt(rot_pos(parse_floats(inert.get("pos")))))
    inert.set("quat", fmt(qmul(QR, tuple(parse_floats(inert.get("quat"))))))

    # 2) base_link's own geoms (trunk mesh): add the rotation quat (they were identity)
    for g in base.findall("geom"):
        q = g.get("quat")
        q = tuple(parse_floats(q)) if q else (1.0, 0.0, 0.0, 0.0)
        g.set("quat", fmt(qmul(QR, q)))

    # 3) first-level child bodies (the two legs): rotate their offset + add the rotation quat.
    #    Their whole subtrees (joints/geoms/descendants) rotate rigidly with the frame.
    n = 0
    for b in base.findall("body"):
        b.set("pos", fmt(rot_pos(parse_floats(b.get("pos")))))
        q = b.get("quat")
        q = tuple(parse_floats(q)) if q else (1.0, 0.0, 0.0, 0.0)
        b.set("quat", fmt(qmul(QR, q)))
        n += 1
    print(f"[rotate] rotated {n} first-level child bodies (expect 2)")

    # 4) 'stand' keyframe: base orientation unchanged (frame not rotated). leave qpos as-is.
    tree.write(XML)
    print(f"[rotate] wrote {XML}")
    # quick sanity print
    for b in base.findall("body"):
        print(f"  {b.get('name')}: pos={b.get('pos')} quat={b.get('quat')}")


if __name__ == "__main__":
    main()
