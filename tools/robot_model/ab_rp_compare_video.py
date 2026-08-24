"""AB (closed-loop crank ankle) vs RP (serial ankle + envelope clamp) — time-synced 1:1 replay.

Both arms were measured with the SAME harness (hack_check -> measure_loads, identical command
schedule 0 / 0.4 / 0.8 m/s, 8 s each, 50 Hz), so frame i of one npz is frame i of the other.
Renders each arm from its own recorded qpos with a CHASE camera locked to that arm's base
(position + yaw), so both panels share one relative viewpoint: the overlay then aligns the two
bases and every limb difference shows as a ghost offset. Travel/tracking is read numerically
(cmd / vx / err), because the command is body-frame and the two arms yaw apart in world.
Two rows: whole body, and an L-ankle close-up (where the AB/RP kinematics actually differ).

Outputs (docs/video/):
  abrp_sidebyside_<tag>.mp4  AB left | RP right, captions + live vx readout
  abrp_shadow_<tag>.mp4      the two overlaid in one frame (50/50 blend, AB amber / RP blue)

  MUJOCO_GL=egl .venv/bin/python3 ../../tools/robot_model/ab_rp_compare_video.py [tag]
Real time: 50 Hz data, every 2nd frame -> 25 fps.
"""
import os, sys, subprocess, shutil
os.environ.setdefault('MUJOCO_GL', 'egl'); os.environ.setdefault('MUJOCO_EGL_DEVICE_ID', '0')
import numpy as np, mujoco
from PIL import Image, ImageDraw, ImageFont

TAG = sys.argv[1] if len(sys.argv) > 1 else 'g8000'
SRC = '/home/syaro/pyg_fea/work/hack_check'
WORK = f'/home/syaro/pyg_fea/work/abrp_video_{TAG}'
OUTDIR = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/video'
W = H = 720
WA = 520                                  # ankle close-up panel
DT, STRIDE = 0.02, 2                      # 50 Hz data, render every 2nd -> 25 fps real time
FPS = int(round(1 / (DT * STRIDE)))
TINT = {'AB': (0.95, 0.58, 0.22, 1.0), 'RP': (0.32, 0.62, 1.0, 1.0)}
F = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
font = lambda s: ImageFont.truetype(F, s)

d = {a: np.load(f'{SRC}/ankle{a}_c3_{TAG}.npz') for a in ('AB', 'RP')}
N = min(len(d['AB']['cmd_vx']), len(d['RP']['cmd_vx']))
frames = range(0, N, STRIDE)
cmd = d['AB']['cmd_vx'][:N]


def yaw_deg(q):
    w, x, y, z = q
    return np.degrees(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))

os.makedirs(WORK, exist_ok=True); os.makedirs(OUTDIR, exist_ok=True)


def render_arm(arm):
    """Render every STRIDE-th frame of one arm to WORK/<arm>_%05d.png (own model, shared camera)."""
    out = f'{WORK}/{arm}'
    if os.path.isdir(out) and len(os.listdir(out)) >= 2 * len(list(frames)):
        print(f'[{arm}] frames cached'); return out
    os.makedirs(out, exist_ok=True)
    m = mujoco.MjModel.from_binary_path(f'{SRC}/ankle{arm}_c3_{TAG}_model.mjb')
    m.vis.global_.offwidth, m.vis.global_.offheight = max(W, WA), max(H, WA)
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or '' for g in range(m.ngeom)]
    for g, nm in enumerate(names):                       # tint the robot, leave the world alone
        if nm.startswith('robot/'):
            m.geom_matid[g] = -1; m.geom_rgba[g] = TINT[arm]
    dat = mujoco.MjData(m)
    ankle_b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'robot/L_foot_link')
    rb, ra = mujoco.Renderer(m, H, W), mujoco.Renderer(m, WA, WA)
    cam, cama = mujoco.MjvCamera(), mujoco.MjvCamera()
    cam.type = cama.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.elevation, cam.distance = -6, 2.3           # full-body profile
    cama.elevation, cama.distance = -10, 1.05       # ankle close-up
    q = d[arm]['qpos_full']; n = len(list(frames))
    for k, i in enumerate(frames):
        dat.qpos[:] = q[i]; dat.qvel[:] = 0; mujoco.mj_forward(m, dat)
        yaw = yaw_deg(q[i, 3:7])
        cam.azimuth = cama.azimuth = yaw + 90.0                   # side view, locked to the base
        cam.lookat[:] = [q[i, 0], q[i, 1], 0.58]
        cama.lookat[:] = dat.xpos[ankle_b] + np.array([0.0, 0.0, 0.12])
        rb.update_scene(dat, camera=cam); Image.fromarray(rb.render()).save(f'{out}/{k:05d}.png')
        ra.update_scene(dat, camera=cama); Image.fromarray(ra.render()).save(f'{out}/a{k:05d}.png')
        if k % 100 == 0: print(f'[{arm}] {k}/{n}', flush=True)
    rb.close(); ra.close(); del dat, m
    return out


def readout(i):
    return {a: (float(d[a]['base_vx'][i]), float(cmd[i])) for a in ('AB', 'RP')}


def compose():
    sxs, sh = f'{WORK}/sxs', f'{WORK}/shadow'
    os.makedirs(sxs, exist_ok=True); os.makedirs(sh, exist_ok=True)
    f28, f20, f16 = font(28), font(20), font(16)
    for k, i in enumerate(frames):
        im = {a_: Image.open(f'{WORK}/{a_}/{k:05d}.png').convert('RGB') for a_ in ('AB', 'RP')}
        an = {a_: Image.open(f'{WORK}/{a_}/a{k:05d}.png').convert('RGB') for a_ in ('AB', 'RP')}
        v = readout(i); t = i * DT
        blend = lambda p, q_: Image.fromarray((0.5 * np.asarray(p, float) + 0.5 * np.asarray(q_, float)).astype(np.uint8))
        # ---- side by side: body row + ankle close-up row ----
        c = Image.new('RGB', (2 * W, 60 + H + 36 + WA + 40), (18, 18, 22))
        c.paste(im['AB'], (0, 60)); c.paste(im['RP'], (W, 60))
        c.paste(an['AB'], (W // 2 - WA // 2, 60 + H + 36)); c.paste(an['RP'], (W + W // 2 - WA // 2, 60 + H + 36))
        dr = ImageDraw.Draw(c)
        dr.text((16, 14), 'AB  closed-loop crank ankle', font=f28, fill=(245, 160, 60))
        dr.text((W + 16, 14), 'RP  serial ankle + envelope clamp', font=f28, fill=(90, 165, 255))
        av, rv = v['AB'][0], v['RP'][0]; cv = v['AB'][1]
        dr.text((16, 60 + H + 8), f'cmd {cv:.1f} m/s', font=f20, fill=(230, 230, 235))
        dr.text((190, 60 + H + 8), f'AB vx {av:+.2f} (err {av - cv:+.2f})', font=f20, fill=(245, 160, 60))
        dr.text((W - 60, 60 + H + 8), f'RP vx {rv:+.2f} (err {rv - cv:+.2f})', font=f20, fill=(90, 165, 255))
        dr.text((2 * W - 400, 60 + H + 10), f't = {t:5.2f} s    25 fps = real time    chase cam, base-locked', font=f16, fill=(170, 170, 180))
        for j in (0, 1):
            dr.text((j * W + W // 2 - WA // 2, 60 + H + 36 + WA + 10), 'L ankle close-up', font=f16, fill=(150, 150, 160))
        c.save(f'{sxs}/{k:05d}.png')
        # ---- shadow: body overlay | ankle overlay ----
        c2 = Image.new('RGB', (W + WA + 48, 60 + H + 44), (18, 18, 22))
        c2.paste(blend(im['AB'], im['RP']), (0, 60))
        c2.paste(blend(an['AB'], an['RP']), (W + 24, 60 + (H - WA) // 2))
        dr = ImageDraw.Draw(c2)
        dr.text((16, 14), 'AB', font=f28, fill=(245, 160, 60)); dr.text((66, 14), 'over', font=f28, fill=(200, 200, 205))
        dr.text((146, 14), 'RP', font=f28, fill=(90, 165, 255))
        dr.text((205, 20), '- same command, same clock, bases aligned', font=f20, fill=(200, 200, 205))
        dr.text((16, 60 + H + 10), f'cmd {v["AB"][1]:.1f} m/s    AB {v["AB"][0]:+.2f}    RP {v["RP"][0]:+.2f} m/s', font=f20, fill=(230, 230, 235))
        dr.text((W + 24, 60 + H + 10), f't = {t:5.2f} s   L ankle overlay', font=f16, fill=(170, 170, 180))
        c2.save(f'{sh}/{k:05d}.png')
    return sxs, sh


def encode(src, name):
    out = f'{OUTDIR}/{name}'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{src}/%05d.png',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', out], check=True)
    print('wrote', out, os.path.getsize(out) // 1024, 'KB')


for arm in ('AB', 'RP'):
    render_arm(arm)
sxs, sh = compose()
encode(sxs, f'abrp_sidebyside_{TAG}.mp4')
encode(sh, f'abrp_shadow_{TAG}.mp4')
shutil.rmtree(f'{WORK}/sxs', ignore_errors=True); shutil.rmtree(f'{WORK}/shadow', ignore_errors=True)
print('DONE')
os._exit(0)
