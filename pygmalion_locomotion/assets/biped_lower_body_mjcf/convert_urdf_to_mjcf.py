# -*- coding: utf-8 -*-
"""
Reproducible URDF -> MJCF conversion for the RobStride lower-body biped.

Steps:
  1. Flatten the xacro into a plain URDF, fix mesh paths + scale, inject a
     <mujoco> compiler block.
  2. Load the URDF in MuJoCo and dump a raw MJCF (mj_saveLastXML).
  3. Post-process: semantic joint/body names, motor-accurate actuators,
     per-motor armature/damping/frictionloss classes, collision scheme,
     base free joint, standing keyframe.

Requires:  pip install mujoco lxml
Usage:     python convert_urdf_to_mjcf.py  (run from the package root)
"""
import re
from pathlib import Path
import mujoco
from lxml import etree

ROOT = Path(__file__).parent
XACRO = ROOT / "src_urdf" / "USD_Conversion_TEST.xacro"   # original xacro
MESHDIR = "meshes"

# ------------------------------------------------------------------ joint map
# old "Revolute N" -> (joint_name, body_name, default-class, peak_torque[N*m])
JSPEC = {
    "Revolute 1":  ("L_hip_pitch_joint",  "L_hip_pitch_link",  "rs04",      120.0),
    "Revolute 2":  ("L_hip_roll_joint",   "L_hip_roll_link",   "rs04",      120.0),
    "Revolute 3":  ("L_hip_yaw_joint",    "L_thigh_link",      "rs03",       60.0),
    "Revolute 4":  ("L_knee_joint",       "L_shin_link",       "rs04_knee", 360.0),
    "Revolute 5":  ("L_ankle_pitch_joint","L_ankle_pitch_link","rs03",       60.0),
    "Revolute 6":  ("L_ankle_roll_joint", "L_foot_link",       "rs00",       14.0),
    "Revolute 7":  ("L_toe_joint",        "L_toe_link",        "toe",        None),
    "Revolute 8":  ("R_hip_pitch_joint",  "R_hip_pitch_link",  "rs04",      120.0),
    "Revolute 9":  ("R_hip_roll_joint",   "R_hip_roll_link",   "rs04",      120.0),
    "Revolute 10": ("R_hip_yaw_joint",    "R_thigh_link",      "rs03",       60.0),
    "Revolute 11": ("R_knee_joint",       "R_shin_link",       "rs04_knee", 360.0),
    "Revolute 12": ("R_ankle_pitch_joint","R_ankle_pitch_link","rs03",       60.0),
    "Revolute 13": ("R_ankle_roll_joint", "R_foot_link",       "rs00",       14.0),
    "Revolute 14": ("R_toe_joint",        "R_toe_link",        "toe",        None),
}
BODY_RENAME = {
    "L_hip_rp_1": "L_hip_pitch_link", "L_hip_ry_1": "L_hip_roll_link",
    "L_bukji_up_1": "L_thigh_link", "L_bukji_down_1": "L_shin_link",
    "L_ankle_1": "L_ankle_pitch_link", "L_feet_1": "L_foot_link", "L_feet_toe_1": "L_toe_link",
    "R_hip_rp__1": "R_hip_pitch_link", "R_hip_ry_1": "R_hip_roll_link",
    "R_bukji_up_1": "R_thigh_link", "R_bukji_down_1": "R_shin_link",
    "R_ankle_1": "R_ankle_pitch_link", "R_feet_1": "R_foot_link", "R_feet_toe_1": "R_toe_link",
}
# per-motor reflected inertia / damping / friction (ESTIMATES - tune/measure!)
CLASSES = {
    "rs04":      dict(armature="0.0097", damping="1.0", frictionloss="0.3"),
    "rs04_knee": dict(armature="0.0875", damping="1.5", frictionloss="0.5"),  # incl. 1:3 belt
    "rs03":      dict(armature="0.0049", damping="0.5", frictionloss="0.2"),
    "rs00":      dict(armature="0.0015", damping="0.2", frictionloss="0.1"),
}


def step1_clean_urdf() -> Path:
    src = XACRO.read_text()
    src = re.sub(r"\s*<xacro:include[^>]*/>", "", src)
    src = src.replace("package://USD_Conversion_TEST_description/meshes/", "")
    src = src.replace('scale="0.001 0.001 0.001"', 'scale="1 1 1"')  # meshes are in METERS
    src = src.replace(' xmlns:xacro="http://www.ros.org/wiki/xacro"', "")
    inject = f'''
  <mujoco>
    <compiler meshdir="{MESHDIR}" balanceinertia="true" discardvisual="false"
              fusestatic="false" strippath="false" autolimits="true"/>
  </mujoco>
  <material name="silver"><color rgba="0.7 0.7 0.7 1.0"/></material>
'''
    src = re.sub(r'(<robot name="USD_Conversion_TEST"\s*>)', r"\1" + inject, src)
    out = ROOT / "robot.urdf"
    out.write_text(src)
    return out


def step2_raw_mjcf(urdf: Path) -> Path:
    model = mujoco.MjModel.from_xml_path(str(urdf))
    raw = ROOT / "robot_raw.xml"
    mujoco.mj_saveLastXML(str(raw), model)
    return raw


def step3_postprocess(raw: Path) -> Path:
    tree = etree.parse(str(raw))
    root = tree.getroot()
    root.set("model", "biped_lower_body")
    comp = root.find("compiler")
    comp.set("meshdir", MESHDIR); comp.set("angle", "radian"); comp.set("autolimits", "true")

    # option
    opt = etree.Element("option", timestep="0.005", integrator="implicitfast")
    etree.SubElement(opt, "flag").set("eulerdamp", "disable")
    root.insert(list(root).index(comp) + 1, opt)

    # defaults
    default = etree.Element("default")
    etree.SubElement(default, "joint", limited="true", armature="0.01", damping="0.5", frictionloss="0.1")
    etree.SubElement(default, "geom", condim="3", contype="1", conaffinity="0", friction="1.0 0.005 0.0001")
    for name, kw in CLASSES.items():
        c = etree.SubElement(default, "default"); c.set("class", name)
        etree.SubElement(c, "joint", **kw)
    ctoe = etree.SubElement(default, "default"); ctoe.set("class", "toe")
    etree.SubElement(ctoe, "joint", armature="0.0005", damping="0.2", frictionloss="0.05",
                     stiffness="20", springref="0")
    cv = etree.SubElement(default, "default"); cv.set("class", "visual")
    etree.SubElement(cv, "geom", contype="0", conaffinity="0", group="2", density="0")
    cc = etree.SubElement(default, "default"); cc.set("class", "collision")
    etree.SubElement(cc, "geom", contype="1", conaffinity="0", group="3", condim="3")
    root.insert(list(root).index(root.find("asset")), default)

    wb = root.find("worldbody")
    for b in wb.iter("body"):
        if b.get("name") in BODY_RENAME:
            b.set("name", BODY_RENAME[b.get("name")])
    for j in wb.iter("joint"):
        if j.get("name") in JSPEC:
            nj, _, cls, peak = JSPEC[j.get("name")]
            j.set("name", nj); j.set("class", cls)
            j.attrib.pop("actuatorfrcrange", None)
            if peak is not None:
                j.set("actuatorfrcrange", f"-{peak:g} {peak:g}")
    for b in wb.iter("body"):
        for gi, g in enumerate(b.findall("geom")):
            for a in ("contype", "conaffinity", "group", "density", "rgba", "type"):
                g.attrib.pop(a, None)
            g.set("class", "visual" if gi == 0 else "collision")
            g.set("type", "mesh")
            if gi != 0:
                g.set("name", b.get("name").replace("_link", "") + "_col")

    base = next(b for b in wb.iter("body") if b.get("name") == "base_link")
    fj = etree.Element("freejoint"); fj.set("name", "root"); base.insert(0, fj)

    act = etree.SubElement(root, "actuator")
    for _, (nj, _, _, peak) in JSPEC.items():
        if peak is None:
            continue
        etree.SubElement(act, "motor", name=nj.replace("_joint", ""),
                         joint=nj, gear="1", ctrlrange=f"-{peak:g} {peak:g}")

    key = etree.SubElement(root, "keyframe")
    etree.SubElement(key, "key", name="stand",
                     qpos=" ".join(["0", "0", "0.87", "1", "0", "0", "0"] + ["0"] * 14))

    etree.indent(tree, space="  ")
    out = ROOT / "robot.xml"
    tree.write(str(out), pretty_print=True, encoding="UTF-8", xml_declaration=False)
    return out


if __name__ == "__main__":
    urdf = step1_clean_urdf()
    raw = step2_raw_mjcf(urdf)
    out = step3_postprocess(raw)
    # validate
    m = mujoco.MjModel.from_xml_path(str(out))
    print(f"OK -> {out.name}: nq={m.nq} nv={m.nv} nu={m.nu} bodies={m.nbody}")
