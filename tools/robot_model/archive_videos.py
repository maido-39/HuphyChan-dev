"""Archive videos for the YouTube channel (MuJoCo EGL, captions burned in, >= 15 s, real time).

  turntable  : printed robot model rotating; layers switch visual -> collision capsules -> hulls
  replay     : AB vs RP side by side from the mid-training measurement npz (qpos_full replay)
  envelope   : RP torque envelope - loop ankle posed along a ROM path + feasible torque parallelogram

MUJOCO_GL=egl MUJOCO_EGL_DEVICE_ID=0 .venv/bin/python3 ../../tools/robot_model/archive_videos.py <kind>
"""
import json, os, subprocess, sys
import numpy as np, mujoco
from PIL import Image, ImageDraw, ImageFont

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XMLS = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls'
OUT = f'{REPO}/docs/video/archive'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FPS = 25
os.makedirs(OUT, exist_ok=True)


def font(sz):
    return ImageFont.truetype(FONT, sz) if os.path.exists(FONT) else ImageFont.load_default()


def caption(img, title, lines, sub=None):
    im = Image.fromarray(img); dr = ImageDraw.Draw(im, 'RGBA'); W, H = im.size
    dr.rectangle([0, 0, W, 44], fill=(0, 0, 0, 170)); dr.text((12, 9), title, fill=(255, 255, 255), font=font(20 if W >= 1200 else 17))
    if sub: dr.text((W - 12 - dr.textlength(sub, font=font(16)), 14), sub, fill=(200, 200, 200), font=font(16))
    if lines:
        h = 24 * len(lines) + 14; dr.rectangle([0, H - h, W, H], fill=(0, 0, 0, 170))
        for i, t in enumerate(lines): dr.text((12, H - h + 7 + 24 * i), t, fill=(255, 255, 120) if i == 0 else (235, 235, 235), font=font(17))
    return np.asarray(im)


def encode(frames, name):
    d = f'{OUT}/_f_{name}'; os.makedirs(d, exist_ok=True)
    for k, f in enumerate(frames): Image.fromarray(f).save(f'{d}/{k:05d}.png')
    out = f'{OUT}/{name}.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{d}/%05d.png', '-pix_fmt', 'yuv420p', '-crf', '19', out], check=True)
    subprocess.run(['rm', '-r', d]); print('->', out, len(frames) / FPS, 's')


def arms_abducted(spec, deg=15.0):
    for j in list(spec.joints):
        if j.name.endswith('_shoulder_roll_joint'):
            ax = np.asarray(j.axis, float); ax /= np.linalg.norm(ax); h = np.radians(-deg) / 2
            q = np.array([np.cos(h), *(np.sin(h) * ax)]); b = j.parent
            w1, x1, y1, z1 = np.asarray(b.quat, float); w2, x2, y2, z2 = q
            b.quat = [w1*w2 - x1*x2 - y1*y2 - z1*z2, w1*x2 + x1*w2 + y1*z2 - z1*y2, w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2]
        if j.name in ('waist_yaw_joint', 'L_shoulder_pitch_joint', 'R_shoulder_pitch_joint', 'L_shoulder_roll_joint', 'R_shoulder_roll_joint'):
            spec.delete(j)


def load(tag, floor=True, W=1280, H=720):
    spec = mujoco.MjSpec.from_file(f'{XMLS}/{tag}.xml'); arms_abducted(spec)
    spec.visual.global_.offwidth = W; spec.visual.global_.offheight = H
    if floor:
        spec.worldbody.add_geom(name='floor', type=mujoco.mjtGeom.mjGEOM_PLANE, size=[4, 4, 0.1], rgba=[0.86, 0.86, 0.86, 1])
    spec.worldbody.add_light(pos=[2, -2, 3], dir=[-0.5, 0.5, -0.8], diffuse=[0.8, 0.8, 0.8], specular=[0.2, 0.2, 0.2])
    spec.worldbody.add_light(pos=[-2, 1.5, 2.5], dir=[0.5, -0.3, -0.8], diffuse=[0.45, 0.45, 0.45])
    return spec.compile()


def opts(kind):
    o = mujoco.MjvOption(); o.geomgroup[:] = 0; o.sitegroup[:] = 0; o.geomgroup[0] = 1
    if kind == 'visual': o.geomgroup[2] = 1
    elif kind == 'collision': o.geomgroup[3] = 1; o.sitegroup[5] = 1
    elif kind == 'hull': o.geomgroup[4] = 1
    elif kind == 'both': o.geomgroup[2] = 1; o.geomgroup[3] = 1; o.sitegroup[5] = 1
    o.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = 1; o.flags[mujoco.mjtVisFlag.mjVIS_CONTACTFORCE] = 1
    return o


def turntable():
    W, H = 1280, 720; m = load('pygmalion_v3_printed_loop', floor=True, W=W, H=H); d = mujoco.MjData(m); r = mujoco.Renderer(m, H, W)
    d.qpos[:] = m.qpos0; d.qpos[3] = 1; mujoco.mj_forward(m, d)
    fz = min(d.geom_xpos[g][2] - m.geom_size[g][2] for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX); d.qpos[2] -= fz; mujoco.mj_forward(m, d)
    cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE; cam.lookat[:] = [0, 0, 0.8]; cam.distance = 2.5; cam.elevation = -10
    T = 18.0; n = int(T * FPS); frames = []
    phases = [(0, 6, 'visual', 'visual meshes (CAD export copy, 3D-printed lower body at measured PLA density)'),
              (6, 12, 'both', 'collision geometry on top: fitted capsules per link + box sole + loop sites (green/red)'),
              (12, 18, 'collision', 'collision only: what the physics touches. adjacent-link pairs excluded, self-collision otherwise penalised')]
    for k in range(n):
        t = k / FPS; cam.azimuth = 150 + 360 * t / T
        ph = next(p for p in phases if p[0] <= t < p[1] + 1e-9)
        r.update_scene(d, cam, opts(ph[2])); img = r.render().copy()
        frames.append(caption(img, 'Huphy 1.0 - printed robot model, 35.35 kg, 2-RSU loop ankle', [ph[3], 'pygmalion_v3_printed_loop.xml  |  27 bodies, 24 hinges, 4 connect equalities  |  hip_yaw +-45, ankle pitch -50/+30, roll +-20 deg'], sub='slow turntable (not real-time data)'))
    encode(frames, 'huphy10_printed_model_turntable'); os._exit(0)


def replay():
    """AB and RP side by side from /home/syaro/pyg_fea/work/measure_mid/mid1200_{AB,RP}.npz."""
    W, H = 960, 720; R = {}
    for mode, tag in (('AB', 'pygmalion_v3_printed_loop'), ('RP', 'pygmalion_v3_printed')):
        m = load(tag, floor=True, W=W, H=H); R[mode] = (m, mujoco.MjData(m), mujoco.Renderer(m, H, W), np.load(f'/home/syaro/pyg_fea/work/measure_mid/mid1200_{mode}.npz'))
    frames = []
    segs = [((0.8, 0.0), 'walk 0.8 m/s'), ((0.8, 0.5), 'walk 0.8 m/s + 0.5 m/s lateral'), ((-0.8, 0.0), 'walk backwards -0.8 m/s')]
    for cmd, lab in segs:
        masks = {}
        for mode in 'AB', 'RP':
            d = R[mode][3]; mk = (np.abs(d['cmd_vx'] - cmd[0]) < 1e-6) & (np.abs(d['cmd_vy'] - cmd[1]) < 1e-6); masks[mode] = np.where(mk)[0][40:]
        n = min(len(masks['AB']), len(masks['RP']))
        for k in range(0, n, 2):                       # 50 Hz data -> 25 fps
            imgs = []
            for mode in 'AB', 'RP':
                m, dd, r, d = R[mode]; i = masks[mode][k]
                dd.qpos[:] = d['qpos_full'][i]; mujoco.mj_forward(m, dd)
                cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE; cam.lookat[:] = dd.qpos[:3] + [0, 0, -0.3]; cam.distance = 2.4; cam.azimuth = 135; cam.elevation = -14
                r.update_scene(dd, cam, opts('visual')); img = r.render().copy()
                if mode == 'AB':
                    tp = d['tauank_eq_L_pitch'][i]; lines = [f'AB: policy drives the two RS03 cranks, ankle passive through the rods', f'L ankle pitch {np.degrees(d["qpos_L_ankle_pitch_joint"][i]):+5.1f} deg   ankle torque (Jc^T tau_crank) {tp:+6.1f} N*m   crank A {d["tau_L_crank_A_joint"][i]:+5.1f} N*m']
                else:
                    tp = d['tau_L_ankle_pitch_joint'][i]; lines = [f'RP: serial ankle, torque clamped to the loop envelope (crank space +-60 N*m + T-N)', f'L ankle pitch {np.degrees(d["qpos_L_ankle_pitch_joint"][i]):+5.1f} deg   ankle torque {tp:+6.1f} N*m   crank-equivalent A {d["taucrank_eq_L_A"][i]:+5.1f} N*m']
                imgs.append(caption(img, f'{mode}  iter 1200 / 32000  -  {lab}', lines, sub='real time, 25 fps'))
            frames.append(np.concatenate(imgs, axis=1))
    encode(frames, 'huphy10_training_ab_vs_rp_iter1200'); os._exit(0)


def envelope():
    W, H = 760, 720; m = load('pygmalion_v3_printed_loop', floor=False, W=W, H=H); d = mujoco.MjData(m); r = mujoco.Renderer(m, H, W)
    E = json.load(open(f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2/ankle_rp_envelope.json')); pa = np.radians(E['grid']['pitch_deg']); ra = np.radians(E['grid']['roll_deg'])
    Lg = E['legs']['L']; crank = np.array(Lg['crank_rad']); JcT = np.array(Lg['JcT']); ext = np.array(Lg['tau_extent'])
    jq = lambda n: m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)]
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    T = 16.0; n = int(T * FPS); frames = []
    for k in range(n):
        t = k / FPS; ph = 2 * np.pi * t / T
        p = np.radians(-10 + 40 * np.sin(ph)); rr = np.radians(20 * np.sin(2 * ph))       # a loop over the ROM
        i = int(np.clip(np.argmin(abs(pa - p)), 0, len(pa) - 1)); j = int(np.clip(np.argmin(abs(ra - rr)), 0, len(ra) - 1))
        d.qpos[:] = m.qpos0; d.qpos[3] = 1; d.qpos[2] = 1.0
        d.qpos[jq('L_ankle_pitch_joint')] = p; d.qpos[jq('L_ankle_roll_joint')] = rr; d.qpos[jq('L_crank_A_joint')] = crank[i, j, 0]; d.qpos[jq('L_crank_B_joint')] = crank[i, j, 1]
        # rod joints: point the rods at the balls (approximate, for the picture)
        mujoco.mj_forward(m, d)
        for tag in 'AB':
            rod = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f'L_rod_{tag}'); end = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, f'L_rod_{tag}_end'); ball = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, f'L_ball_{tag}')
            for it in range(3):
                mujoco.mj_forward(m, d)
                v_cur = d.site_xpos[end] - d.xpos[rod]; v_tgt = d.site_xpos[ball] - d.xpos[rod]
                Rr = d.xmat[rod].reshape(3, 3); a = Rr.T @ v_cur; b = Rr.T @ v_tgt
                for u in ('u1', 'u2'):
                    jn = f'L_rod_{tag}_{u}'; jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn); ax = m.jnt_axis[jid]
                    # angle about this axis that best aligns a to b
                    pa_ = a - ax * (a @ ax); pb_ = b - ax * (b @ ax)
                    if np.linalg.norm(pa_) > 1e-6 and np.linalg.norm(pb_) > 1e-6:
                        ang = np.arctan2(np.cross(pa_, pb_) @ ax, pa_ @ pb_); d.qpos[m.jnt_qposadr[jid]] += ang
                    mujoco.mj_forward(m, d); v_cur = d.site_xpos[end] - d.xpos[rod]; a = Rr.T @ v_cur
        mujoco.mj_forward(m, d)
        cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE; ank = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'L_ankle_pitch_link')]
        cam.lookat[:] = ank + [0, 0, 0.08]; cam.distance = 0.75; cam.azimuth = 140 + 25 * np.sin(ph / 2); cam.elevation = -16
        r.update_scene(d, cam, opts('visual')); img = r.render().copy()
        fig, ax = plt.subplots(figsize=(5.2, 7.2), dpi=100)
        JT = JcT[i, j]; corners = np.array([[sa * 60, sb * 60] for sa, sb in ((1, 1), (1, -1), (-1, -1), (-1, 1), (1, 1))]); poly = corners @ JT.T
        ax.fill(poly[:, 0], poly[:, 1], color='tab:green', alpha=0.25); ax.plot(poly[:, 0], poly[:, 1], color='tab:green', lw=2, label='feasible ankle torque (crank |tau| <= 60)')
        ax.plot([-ext[i, j, 0], ext[i, j, 0]], [0, 0], 'r|-', lw=1.5, ms=12, label=f'pitch-only extent +-{ext[i, j, 0]:.0f} N*m'); ax.plot([0, 0], [-ext[i, j, 1], ext[i, j, 1]], 'b|-', lw=1.5, ms=12, label=f'roll-only extent +-{ext[i, j, 1]:.0f} N*m')
        ax.set_xlim(-120, 120); ax.set_ylim(-120, 120); ax.set_aspect('equal'); ax.grid(alpha=0.3); ax.set_xlabel('ankle pitch torque [N*m]'); ax.set_ylabel('ankle roll torque [N*m]')
        ax.set_title(f'pose: pitch {np.degrees(p):+5.1f} deg, roll {np.degrees(rr):+5.1f} deg\ncranks A {np.degrees(crank[i, j, 0]):+5.1f}  B {np.degrees(crank[i, j, 1]):+5.1f} deg (IK)', fontsize=10); ax.legend(fontsize=8, loc='lower left')
        fig.tight_layout(); fig.canvas.draw(); plot = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy(); plt.close(fig)
        plot = np.asarray(Image.fromarray(plot).resize((520, 720)))
        frame = np.concatenate([img, plot], axis=1)
        frames.append(caption(frame, 'Huphy 1.0 - RP-mode ankle torque envelope from the 2-RSU loop (IK/FK of the closed loop)', ['left: loop ankle posed on the ROM (cranks from IK)   right: torque the two RS03 cranks can deliver at this pose', 'RP training clamps the PD torque to this parallelogram (crank space +-60 N*m + T-N) = the hardware limit'], sub='pose sweep, not real-time data'))
    encode(frames, 'huphy10_rp_torque_envelope'); os._exit(0)


if __name__ == '__main__':
    {'turntable': turntable, 'replay': replay, 'envelope': envelope}[sys.argv[1]]()
