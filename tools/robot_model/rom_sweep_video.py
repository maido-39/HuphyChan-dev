"""ROM sweep on every joint, rendered as an explainer video with the sign convention on screen.

The user's convention (2026-08-26): the actuator ROTOR face is the one carrying 6 M4 threaded
holes and 3 alignment pins. Looking straight at that exposed face, along the axis protruding
from it, CLOCKWISE is POSITIVE. In vector terms, with n the OUTWARD normal of the rotor face,
"clockwise seen with n pointing at the viewer" is a rotation vector along MINUS n, so

    required + axis = -n

Each joint is swept neutral -> min -> max -> neutral so the direction of travel is unambiguous,
and the caption states, per joint, whether the model's axis agrees with -n.

Playback is KINEMATIC: qpos is set and mj_forward is called, with the base pinned in the air.
No gravity, no contacts, no controller - a ROM/sign check must show the model's own kinematics,
not a controller's response to them.

  MUJOCO_GL=egl .venv/bin/python3 tools/robot_model/rom_sweep_video.py [--model=serial|loop]
                                                                      [--joints=a,b] [--quick]
"""
import json
import os
import subprocess
import sys

os.environ.setdefault('MUJOCO_GL', 'egl')
os.environ.setdefault('MUJOCO_EGL_DEVICE_ID', '0')
import numpy as np                      # noqa: E402
import mujoco                           # noqa: E402
from PIL import Image, ImageDraw, ImageFont   # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XMLS = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls'
SIGN_JSON = f'{REPO}/tools/robot_model/motor_sign_convention.json'
WORK = '/home/syaro/pyg_fea/work/rom_sweep'
OUTDIR = f'{REPO}/docs/video'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_R = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

W, H = 1280, 720
PANEL = 430                                   # close-up panel (square)
HEAD_H = 80                                   # header band
BODY_Y = 88                                   # top of both render panels
MAIN_W, MAIN_H = 788, 524                     # wide view
ZOOM_X = 812                                  # left edge of the close-up column
BAND_Y = 620                                  # bottom read-out band
FPS = 25
BG = (18, 20, 26)
FG = (238, 240, 245)
DIM = (150, 158, 172)
POS_C = (86, 200, 132)                        # positive travel
NEG_C = (232, 122, 96)                        # negative travel
ACC = (108, 168, 232)

f_b = lambda s: ImageFont.truetype(FONT, s)
f_r = lambda s: ImageFont.truetype(FONT_R, s)

# Which body to frame for the close-up, per joint prefix.
ZOOM_BODY = {
    'hip_pitch': '{s}_hip_pitch_link', 'hip_roll': '{s}_hip_roll_link',
    'hip_yaw': '{s}_thigh_link', 'knee': '{s}_shin_link',
    'ankle_pitch': '{s}_ankle_pitch_link', 'ankle_roll': '{s}_foot_link',
    'shoulder_pitch': '{s}_shoulder_pitch_link', 'shoulder_roll': '{s}_arm_link',
}
HUMAN = {
    'hip_pitch': 'Hip pitch - swings the whole leg forward and back',
    'hip_roll': 'Hip roll - swings the leg out to the side and back in',
    'hip_yaw': 'Hip yaw - twists the leg about its own long axis',
    'knee': 'Knee - bends the shin under the thigh',
    'ankle_pitch': 'Ankle pitch - points the toes down and pulls them up',
    'ankle_roll': 'Ankle roll - tilts the sole side to side',
    'waist_yaw': 'Waist yaw - turns the torso about the vertical axis',
    'shoulder_pitch': 'Shoulder pitch - swings the arm forward and back',
    'shoulder_roll': 'Shoulder roll - lifts the arm away from the body',
}


def ease(t):
    """Cosine ease so start and stop are gentle and the direction reads clearly."""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(t, 0.0, 1.0))


def joint_kind(name):
    return name.replace('L_', '').replace('R_', '').replace('_joint', '')


def load_signs():
    if not os.path.exists(SIGN_JSON):
        return None
    return json.load(open(SIGN_JSON))


HOLD_S = 1.0                      # still frames at neutral before and after each sweep


def sweep_profile(lo, hi, n_seg):
    """hold at neutral -> min -> max -> neutral -> hold, as (angle, phase-label) pairs.

    The holds exist so the robot can actually be looked at before and after it moves; without
    them each joint cuts straight from the section card into motion.
    """
    hold = int(HOLD_S * FPS)
    out = [(0.0, 'neutral')] * hold
    for a, b, lab in ((0.0, lo, 'to MIN'), (lo, hi, 'to MAX'), (hi, 0.0, 'back to NEUTRAL')):
        for k in range(n_seg):
            out.append((a + (b - a) * ease(k / (n_seg - 1)), lab))
    out += [(0.0, 'neutral')] * hold
    return out


def circ_arrow(d, cx, cy, r, clockwise, colour, width=6):
    """A circular arrow showing which way the link is turning, as seen by the viewer."""
    a0, a1 = (200, 340) if clockwise else (340, 200)
    d.arc([cx - r, cy - r, cx + r, cy + r], min(a0, a1), max(a0, a1), fill=colour, width=width)
    tip = np.radians(a1)
    px, py = cx + r * np.cos(tip), cy + r * np.sin(tip)
    tang = np.array([-np.sin(tip), np.cos(tip)]) * (1 if clockwise else -1)
    norm = np.array([np.cos(tip), np.sin(tip)])
    p1 = (px + tang[0] * 13 + norm[0] * 7, py + tang[1] * 13 + norm[1] * 7)
    p2 = (px + tang[0] * 13 - norm[0] * 7, py + tang[1] * 13 - norm[1] * 7)
    d.polygon([(px, py), p1, p2], fill=colour)


def draw_frame(rgb_main, rgb_zoom, info):
    """Compose one frame: wide view + close-up + a read-out band that nothing overlaps."""
    im = Image.new('RGB', (W, H), BG)
    im.paste(Image.fromarray(rgb_main).resize((MAIN_W, MAIN_H)), (12, BODY_Y))
    im.paste(Image.fromarray(rgb_zoom).resize((PANEL, PANEL)), (ZOOM_X, BODY_Y))
    d = ImageDraw.Draw(im)

    d.rectangle([0, 0, W, HEAD_H], fill=(26, 29, 37))
    d.text((22, 12), info['title'], font=f_b(30), fill=FG)
    d.text((22, 50), info['human'], font=f_r(18), fill=DIM)
    d.text((W - 320, 14), 'ROM sweep + motor sign check', font=f_b(17), fill=ACC)
    d.text((W - 320, 40), info['model_tag'], font=f_r(14), fill=DIM)
    d.text((W - 320, 58), 'blue arrows = joint axes', font=f_r(13), fill=(120, 128, 142))

    d.text((22, BODY_Y + MAIN_H - 26), 'whole body', font=f_r(15), fill=DIM)
    d.text((ZOOM_X + 10, BODY_Y + PANEL - 26), 'close-up', font=f_r(15), fill=DIM)

    # ---- sign-convention badge, between the close-up and the band ----
    by2 = BODY_Y + PANEL + 10
    d.rectangle([ZOOM_X, by2, W - 12, BAND_Y - 12], fill=(26, 29, 37))
    if info['sign_state'] == 'unknown':
        d.text((ZOOM_X + 14, by2 + 12), 'rotor face not yet measured', font=f_r(15), fill=DIM)
        d.text((ZOOM_X + 14, by2 + 34), 'sign check pending', font=f_r(15), fill=DIM)
    else:
        ok = info['sign_state'] == 'match'
        d.text((ZOOM_X + 14, by2 + 8), 'motor sign', font=f_r(14), fill=DIM)
        d.text((ZOOM_X + 14, by2 + 28), 'MATCHES  + = clockwise' if ok else 'INVERTED vs spec',
               font=f_b(18), fill=POS_C if ok else NEG_C)
        d.text((ZOOM_X + 14, by2 + 54), info['sign_detail'][:46], font=f_r(12), fill=DIM)
    # The arrow shows the sense AS SEEN LOOKING AT THE ROTOR FACE, which is not the same thing
    # as "the angle is going up": on a joint whose axis is inverted vs spec, a rising angle turns
    # counter-clockwise from that viewpoint. Drawing it from the sign of dq alone made the arrow
    # contradict the verdict badge next to it.
    if abs(info['dir']) > 1e-9 and info['sign_state'] != 'unknown':
        rising = info['dir'] > 0
        cw_at_rotor = rising if info['sign_state'] == 'match' else not rising
        circ_arrow(d, W - 52, by2 + 38, 24, cw_at_rotor, POS_C if rising else NEG_C)
        d.text((W - 96, by2 + 66), 'CW' if cw_at_rotor else 'CCW', font=f_r(12), fill=DIM)

    # ---- read-out band ----
    ang, lo, hi = info['ang'], info['lo'], info['hi']
    d.rectangle([0, BAND_Y, W, H], fill=(26, 29, 37))
    col = POS_C if ang >= 0 else NEG_C
    num = f'{ang:+.1f}'
    d.text((24, BAND_Y + 24), num, font=f_b(44), fill=col)
    nx = 24 + d.textlength(num, font=f_b(44)) + 8          # place 'deg' after the number
    d.text((nx, BAND_Y + 46), 'deg', font=f_r(20), fill=DIM)
    px0 = max(nx + 46, 215)
    d.text((px0, BAND_Y + 20), info['phase'], font=f_b(19), fill=FG)
    d.text((px0, BAND_Y + 48), f'limits {lo:+.0f} to {hi:+.0f}', font=f_r(15), fill=DIM)

    bx0, bx1, by = 470, W - 40, BAND_Y + 52
    d.line([bx0, by, bx1, by], fill=(58, 64, 78), width=7)
    zx = bx0 + (bx1 - bx0) * (0 - lo) / (hi - lo)
    px = bx0 + (bx1 - bx0) * (ang - lo) / (hi - lo)
    d.line([zx, by, px, by], fill=col, width=7)
    d.line([zx, by - 13, zx, by + 13], fill=DIM, width=2)
    d.ellipse([px - 9, by - 9, px + 9, by + 9], fill=col)
    d.text((bx0 - 6, by + 12), f'{lo:.0f}', font=f_r(13), fill=DIM)
    d.text((bx1 - 22, by + 12), f'+{hi:.0f}', font=f_r(13), fill=DIM)
    d.text((zx - 5, by - 32), '0', font=f_r(13), fill=DIM)
    return im


class FrameSink:
    """Write frames straight to disk, numbered.

    The first version built a Python list of every PIL frame and only encoded at the end:
    2514 frames x 1280x720x3 is about 7 GB resident, which put this machine into swap with
    kswapd pinned at 100 %. Nothing here ever needs two frames at once.
    """

    def __init__(self, work):
        self.work = work
        self.n = 0

    def add(self, im):
        im.save(f'{self.work}/f{self.n:05d}.png')
        self.n += 1

    def hold(self, im, seconds):
        for _ in range(int(seconds * FPS)):
            self.add(im)


def title_card(text_lines, seconds=3.0):
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((70, 150), text_lines[0], font=f_b(46), fill=FG)
    yy = 240
    for ln in text_lines[1:]:
        d.text((70, yy), ln, font=f_r(24), fill=DIM if ln.startswith(' ') else FG)
        yy += 42
    return im, seconds


def main():
    args = sys.argv[1:]
    which = next((a.split('=')[1] for a in args if a.startswith('--model=')), 'serial')
    only = next((a.split('=')[1].split(',') for a in args if a.startswith('--joints=')), None)
    quick = '--quick' in args
    tag = next((a.split('=')[1] for a in args if a.startswith('--tag=')), 'pygmalion_v4_printed')
    xml = f'{XMLS}/{tag}{"_loop" if which == "loop" else ""}.xml'
    # A floor and a couple of lights: the raw robot XML renders as a grey object in a void,
    # which makes it genuinely hard to tell which way a limb is swinging. Added through MjSpec
    # so the shipped model file is not touched.
    spec = mujoco.MjSpec.from_file(xml)
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 1024, 768
    try:
        floor = spec.worldbody.add_geom()
        floor.name = 'rom_floor'
        floor.type = mujoco.mjtGeom.mjGEOM_PLANE
        floor.size = [4.0, 4.0, 0.05]
        floor.pos = [0.0, 0.0, 0.0]
        floor.rgba = [0.22, 0.235, 0.28, 1.0]
        for pos, dirn in (((1.4, -1.2, 3.0), (-0.3, 0.4, -1.0)),
                          ((-1.6, 1.4, 2.4), (0.4, -0.4, -1.0))):
            lt = spec.worldbody.add_light()
            lt.pos = list(pos)
            lt.dir = list(dirn)
            lt.castshadow = True
            lt.diffuse = [0.55, 0.55, 0.58]
            lt.specular = [0.12, 0.12, 0.14]
    except Exception as e:                       # keep the sweep usable if the API shifts
        print(f'[warn] could not add floor/lights ({e}); rendering without them')
    m = spec.compile()
    dta = mujoco.MjData(m)
    signs = load_signs()

    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUTDIR, exist_ok=True)
    for f in os.listdir(WORK):
        os.remove(f'{WORK}/{f}')

    hinges = [m.joint(j).name for j in range(m.njnt)
              if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE
              and not any(t in m.joint(j).name for t in ('_rod_', '_crank_'))]
    if only:
        hinges = [h for h in hinges if any(o in h for o in only)]
    n_seg = 24 if quick else 68                      # frames per leg; 68 @25fps = half the old speed

    renderer = mujoco.Renderer(m, height=768, width=1024)
    rz = mujoco.Renderer(m, height=PANEL, width=PANEL)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [0.0, 0.0, 0.62]
    cam.distance, cam.elevation, cam.azimuth = 1.95, -8, 140
    czoom = mujoco.MjvCamera()
    opt = mujoco.MjvOption()
    opt.flags[mujoco.mjtVisFlag.mjVIS_JOINT] = True

    sink = FrameSink(WORK)
    sink.hold(*title_card([
        'Joint ROM sweep and motor sign check',
        f'model: {os.path.basename(xml)}    {len(hinges)} joints',
        '',
        'Every joint is driven  NEUTRAL -> MINIMUM -> MAXIMUM -> NEUTRAL,',
        'one at a time, with the base held still.',
        '',
        'Sign convention: look straight at the actuator rotor face',
        ' (the face with 6 M4 holes and 3 alignment pins).',
        ' CLOCKWISE from that view is POSITIVE.',
    ], 4.0))

    log = {}
    for jn in hinges:
        jid = m.joint(jn).id
        lo, hi = np.degrees(m.jnt_range[jid])
        kind = joint_kind(jn)
        side = 'L' if jn.startswith('L_') else ('R' if jn.startswith('R_') else '')
        zb = ZOOM_BODY.get(kind, '').format(s=side) if side else 'torso_link'
        try:
            zbid = m.body(zb).id
        except Exception:
            zbid = m.body('base_link').id

        sg = (signs or {}).get(jn)
        state = 'unknown' if not sg else ('match' if sg.get('matches') else 'inverted')
        if sg:
            detail = f"rotor n {sg.get('n_base')}  axis {sg.get('axis')}"
        elif jn.startswith('L_'):
            detail = ''
            state = 'unknown'
        else:
            detail = ''

        sink.hold(*title_card([f'{jn}', f'range {lo:+.0f} to {hi:+.0f} deg',
                               '', HUMAN.get(kind, '')], 1.6))
        prof = sweep_profile(lo, hi, n_seg)
        prev = 0.0
        rec = []
        for ang, phase in prof:
            mujoco.mj_resetData(m, dta)
            dta.qpos[0:3] = [0, 0, 1.0]
            dta.qpos[3:7] = [1, 0, 0, 0]
            dta.qpos[m.jnt_qposadr[jid]] = np.radians(ang)
            mujoco.mj_forward(m, dta)
            renderer.update_scene(dta, camera=cam, scene_option=opt)
            main_rgb = renderer.render()
            czoom.lookat[:] = dta.xpos[zbid]
            czoom.distance, czoom.elevation, czoom.azimuth = 0.55, -6, 140
            rz.update_scene(dta, camera=czoom, scene_option=opt)
            zoom_rgb = rz.render()
            sink.add(draw_frame(main_rgb, zoom_rgb, dict(
                title=jn, human=HUMAN.get(kind, ''), ang=ang, lo=lo, hi=hi, phase=phase,
                model_tag=os.path.basename(xml), dir=ang - prev,
                sign_state=state, sign_detail=detail)))
            rec.append(ang)
            prev = ang
        log[jn] = dict(lo=float(lo), hi=float(hi), n_frames=len(prof),
                       reached_min=float(min(rec)), reached_max=float(max(rec)),
                       returned_to=float(rec[-1]))

    out = f'{OUTDIR}/rom_sweep_{tag.replace("pygmalion_", "")}_{which}.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS),
                    '-i', f'{WORK}/f%05d.png', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-crf', '20', out], check=True)
    json.dump(log, open(out.replace('.mp4', '.json'), 'w'), indent=1)
    print(f'wrote {out}  ({sink.n} frames, {sink.n/FPS:.1f} s, {len(hinges)} joints)')
    for jn, r in log.items():
        print(f"  {jn:26s} {r['lo']:+7.1f} .. {r['hi']:+7.1f}  reached "
              f"{r['reached_min']:+7.1f} / {r['reached_max']:+7.1f}  back to {r['returned_to']:+.1f}")


if __name__ == '__main__':
    main()
