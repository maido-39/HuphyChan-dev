"""Real MuJoCo (EGL) render of the AB closed-loop ankle driven by its two crank servos.

Three panels per frame: whole body | ankle close-up, visual meshes | same close-up, collision
geometry only (capsules, box sole, rod-end sites). Sequence: hanging (base welded, no gravity)
pitch sweep -> roll sweep -> circle, then on the ground (base pinned, hips/knees held) with the
sole pressed and the cranks driven, contact points/forces drawn. Real time: 1 ms physics,
25 fps = 40 steps per frame. Overlay: crank / foot angles, closure error, phase.

MUJOCO_GL=egl MUJOCO_EGL_DEVICE_ID=0 .venv/bin/python3 ../../tools/robot_model/loop_ankle_render.py [--fast]
"""
import os, subprocess, sys
import numpy as np
import mujoco
from PIL import Image, ImageDraw, ImageFont

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v3_printed_loop.xml'
OUT = os.environ.get('AB_RENDER_OUT', f'{REPO}/docs/video/loop_ankle_ab_render.mp4')
KP, KD, DT, FPS = 22.3, 1.41, 0.001, 25
W, H = 640, 640
FAST = '--fast' in sys.argv


def build(floor):
    spec = mujoco.MjSpec.from_file(XML)
    spec.visual.global_.offwidth = 3 * W
    spec.visual.global_.offheight = H
    spec.option.timestep = DT
    spec.option.gravity[:] = [0, 0, -9.81 if floor else 0.0]
    if floor:
        spec.worldbody.add_geom(name='floor', type=mujoco.mjtGeom.mjGEOM_PLANE, size=[3, 3, 0.1], rgba=[0.85, 0.85, 0.85, 1])
    # arms as in training: welded, abducted 15 deg (negative shoulder_roll), see docs/92 s7
    for j in list(spec.joints):
        if j.name.endswith('_shoulder_roll_joint'):
            ax = np.asarray(j.axis, float); ax /= np.linalg.norm(ax); h = np.radians(-15) / 2
            q = np.array([np.cos(h), *(np.sin(h) * ax)]); b = j.parent
            w1, x1, y1, z1 = np.asarray(b.quat, float); w2, x2, y2, z2 = q
            b.quat = [w1*w2 - x1*x2 - y1*y2 - z1*z2, w1*x2 + x1*w2 + y1*z2 - z1*y2, w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2]
        if j.name in ('waist_yaw_joint', 'L_shoulder_pitch_joint', 'R_shoulder_pitch_joint', 'L_shoulder_roll_joint', 'R_shoulder_roll_joint'):
            spec.delete(j)
    spec.worldbody.add_light(pos=[1.5, -1.5, 2.5], dir=[-0.5, 0.5, -0.8], diffuse=[0.8, 0.8, 0.8], specular=[0.2, 0.2, 0.2])
    spec.worldbody.add_light(pos=[-1.5, 1.0, 2.0], dir=[0.5, -0.3, -0.8], diffuse=[0.5, 0.5, 0.5])
    for s in 'LR':
        for t in 'AB':
            a = spec.add_actuator(); a.name = f'{s}_crank_{t}_servo'; a.trntype = mujoco.mjtTrn.mjTRN_JOINT
            a.target = f'{s}_crank_{t}_joint'; a.gaintype = mujoco.mjtGain.mjGAIN_FIXED; a.biastype = mujoco.mjtBias.mjBIAS_AFFINE
            a.gainprm[0] = KP; a.biasprm[1] = -KP; a.biasprm[2] = -KD; a.forcerange[:] = [-60, 60]; a.forcelimited = True
    return spec.compile()


def jq(m, n):
    return m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)]


def closure(m, d, s='L'):
    return max(np.linalg.norm(d.site_xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, f'{s}_rod_{t}_end')] -
                              d.site_xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, f'{s}_ball_{t}')]) for t in 'AB') * 1000


class Panels:
    def __init__(self, m):
        self.r = mujoco.Renderer(m, H, W)
        self.m = m
        self.cam_body = mujoco.MjvCamera(); self.cam_body.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.cam_ankle = mujoco.MjvCamera(); self.cam_ankle.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.vis = mujoco.MjvOption(); self.col = mujoco.MjvOption()
        for o in (self.vis, self.col):
            o.geomgroup[:] = 0; o.sitegroup[:] = 0
        self.vis.geomgroup[2] = 1; self.vis.geomgroup[0] = 1          # visual meshes (+ floor)
        self.col.geomgroup[3] = 1; self.col.geomgroup[0] = 1; self.col.sitegroup[5] = 1   # collision capsules/box + loop sites
        for o in (self.vis, self.col):
            o.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = 1
            o.flags[mujoco.mjtVisFlag.mjVIS_CONTACTFORCE] = 1
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 17) if os.path.exists('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf') else ImageFont.load_default()

    def frame(self, d, text_lines, ankle_body='L_ankle_pitch_link'):
        m = self.m
        base = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'base_link')]
        ank = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, ankle_body)]
        self.cam_body.lookat[:] = base + [0, 0, -0.35]; self.cam_body.distance = 2.6; self.cam_body.azimuth = 150; self.cam_body.elevation = -12
        self.cam_ankle.lookat[:] = ank + [0, 0, 0.06]; self.cam_ankle.distance = 0.62; self.cam_ankle.azimuth = 135; self.cam_ankle.elevation = -15
        imgs = []
        for cam, opt in ((self.cam_body, self.vis), (self.cam_ankle, self.vis), (self.cam_ankle, self.col)):
            self.r.update_scene(d, cam, opt); imgs.append(self.r.render().copy())
        img = Image.fromarray(np.concatenate(imgs, axis=1))
        dr = ImageDraw.Draw(img)
        for k, ttl in enumerate(('whole body (visual meshes)', 'L ankle close-up (visual)', 'L ankle close-up: COLLISION geometry (capsules, box sole, loop sites)')):
            dr.rectangle([k * W, 0, k * W + W, 26], fill=(0, 0, 0)); dr.text((k * W + 8, 5), ttl, fill=(255, 255, 255), font=self.font)
        y = H - 22 * len(text_lines) - 8
        dr.rectangle([0, y - 4, 3 * W, H], fill=(0, 0, 0))
        for i, t in enumerate(text_lines):
            dr.text((8, y + 22 * i), t, fill=(255, 255, 0) if i == 0 else (255, 255, 255), font=self.font)
        return np.asarray(img)


def main():
    os.makedirs(f'{REPO}/docs/video/_frames_ab', exist_ok=True)
    frames = []
    steps_per_frame = int(round(1 / (FPS * DT)))
    # ---------- part 1: hanging ----------
    m = build(floor=False); d = mujoco.MjData(m); P = Panels(m)
    d.qpos[:] = m.qpos0; d.qpos[2] = 1.2; d.qpos[3] = 1
    base_q = d.qpos[:7].copy()
    aid = {(s, t): mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f'{s}_crank_{t}_servo') for s in 'LR' for t in 'AB'}
    hold = [j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE and not any(k in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) or '') for k in ('crank', 'rod', 'ankle'))]
    def hold_joints(d):
        for j in hold:
            d.qfrc_applied[m.jnt_dofadr[j]] = -300 * d.qpos[m.jnt_qposadr[j]] - 6 * d.qvel[m.jnt_dofadr[j]]
    T1 = 3.6 if not FAST else 1.5
    phases = [('HANGING: co-actuation -> foot PITCH (crank A = B, +-30 deg)', lambda t: (np.radians(30) * np.sin(2 * np.pi * t / T1),) * 2),
              ('HANGING: differential -> foot ROLL (crank A = -B, +-14 deg)', lambda t: (np.radians(14) * np.sin(2 * np.pi * t / T1), -np.radians(14) * np.sin(2 * np.pi * t / T1))),
              ('HANGING: both -> foot circles (pitch 25 deg, roll 12 deg)', lambda t: (np.radians(25) * np.sin(2 * np.pi * t / T1) + np.radians(12) * np.cos(2 * np.pi * t / T1),
                                                                                       np.radians(25) * np.sin(2 * np.pi * t / T1) - np.radians(12) * np.cos(2 * np.pi * t / T1)))]
    t_global = 0.0
    for label, fn in phases:
        n = int(T1 * 1.0 * FPS)
        for k in range(n):
            t = k / FPS
            cA, cB = fn(t)
            for _ in range(steps_per_frame):
                d.qpos[:7] = base_q; d.qvel[:6] = 0; hold_joints(d)
                for s in 'LR':
                    d.ctrl[aid[(s, 'A')]] = cA; d.ctrl[aid[(s, 'B')]] = cB
                mujoco.mj_step(m, d)
            t_global += 1 / FPS
            lines = [label, f't = {t_global:5.2f} s   crank A {np.degrees(d.qpos[jq(m, "L_crank_A_joint")]):+6.1f}  B {np.degrees(d.qpos[jq(m, "L_crank_B_joint")]):+6.1f} deg  ->  foot pitch {np.degrees(d.qpos[jq(m, "L_ankle_pitch_joint")]):+6.1f}  roll {np.degrees(d.qpos[jq(m, "L_ankle_roll_joint")]):+6.1f} deg   loop closure {closure(m, d):.3f} mm',
                     'AB mode: the policy commands the two RS03 cranks (Kp 22.3 / Kd 1.41, +-60 N*m); ankle pitch/roll are passive through the rods. real time, 25 fps']
            frames.append(P.frame(d, lines))
    # ---------- part 2: on the ground ----------
    m = build(floor=True); d = mujoco.MjData(m); P = Panels(m)
    aid = {(s, t): mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f'{s}_crank_{t}_servo') for s in 'LR' for t in 'AB'}
    hold = [j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE and not any(k in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) or '') for k in ('crank', 'rod', 'ankle'))]
    d.qpos[:] = m.qpos0; d.qpos[3] = 1
    mujoco.mj_forward(m, d)
    fid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'L_foot_link')
    d.qpos[2] += 0.002 + 0.043 - d.xpos[fid][2]            # sole 2 mm above the floor
    mujoco.mj_forward(m, d); base_q = d.qpos[:7].copy()
    T2 = 5.0 if not FAST else 2.0
    def fn2(t):
        if t < T2 / 2:
            c = np.radians(10) * np.sin(2 * np.pi * t / (T2 / 2)); return c, c
        c = np.radians(8) * np.sin(2 * np.pi * (t - T2 / 2) / (T2 / 2)); return c, -c
    n = int(T2 * FPS)
    for k in range(n):
        t = k / FPS; cA, cB = fn2(t)
        for _ in range(steps_per_frame):
            d.qpos[:7] = base_q; d.qvel[:6] = 0; hold_joints(d)
            for s in 'LR':
                d.ctrl[aid[(s, 'A')]] = cA; d.ctrl[aid[(s, 'B')]] = cB
            mujoco.mj_step(m, d)
        t_global += 1 / FPS
        nc = 0; fz = 0.0
        for i in range(d.ncon):
            c = d.contact[i]
            if 'floor' in ((mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1) or '') + (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2) or '')):
                f = np.zeros(6); mujoco.mj_contactForce(m, d, i, f); nc += 1; fz += f[0]
        lines = ['ON THE GROUND: base held, sole 2 mm above the floor, cranks tilt the foot onto its toe / heel / side edge (contact points + force arrows drawn)',
                 f't = {t_global:5.2f} s   crank A {np.degrees(d.qpos[jq(m, "L_crank_A_joint")]):+6.1f}  B {np.degrees(d.qpos[jq(m, "L_crank_B_joint")]):+6.1f} deg  ->  foot pitch {np.degrees(d.qpos[jq(m, "L_ankle_pitch_joint")]):+6.1f}  roll {np.degrees(d.qpos[jq(m, "L_ankle_roll_joint")]):+6.1f} deg   floor contacts {nc}  normal {fz:5.0f} N   closure {closure(m, d):.3f} mm',
                 'real time, 25 fps']
        frames.append(P.frame(d, lines))
    for k, f in enumerate(frames):
        Image.fromarray(f).save(f'{REPO}/docs/video/_frames_ab/{k:04d}.png')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{REPO}/docs/video/_frames_ab/%04d.png', '-pix_fmt', 'yuv420p', '-crf', '20', OUT], check=True)
    subprocess.run(['rm', '-r', f'{REPO}/docs/video/_frames_ab'])
    print('->', OUT, len(frames), 'frames', len(frames) / FPS, 's')
    os._exit(0)     # the EGL context free at interpreter exit throws on this driver; the file is written


if __name__ == '__main__':
    main()
