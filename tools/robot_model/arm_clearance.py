"""Which fixed shoulder abduction (multiple of 5 deg) keeps the hanging arms clear of the legs
over the walking ROM? Plain MuJoCo on the serial v3_printed model with the arm-hip contact
excludes REMOVED, min signed distance between every arm geom and every leg/pelvis collision
geom over a hip/knee grid (+ the bent init pose)."""
import itertools, sys
import numpy as np, mujoco
XML = '/home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v3_printed.xml'
spec = mujoco.MjSpec.from_file(XML)
for ex in list(spec.excludes):
    if 'arm' in ex.bodyname1 + ex.bodyname2 and 'hip' in ex.bodyname1 + ex.bodyname2:
        spec.delete(ex)
m = spec.compile(); d = mujoco.MjData(m)
jq = lambda n: m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)]
gname = lambda g: mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ''
arm = [g for g in range(m.ngeom) if m.geom_contype[g] and 'arm' in gname(g)]
legs = [g for g in range(m.ngeom) if m.geom_contype[g] and any(k in gname(g) for k in ('hip', 'thigh', 'shin', 'foot', 'pelvis', 'base'))]
print('arm geoms', [gname(g) for g in arm]); print('leg/pelvis geoms', len(legs))
GRIDS = {
  'nominal (stand + bent)': dict(hip_pitch=[0.0], hip_roll=[0.0], hip_yaw=[0.0], knee=[0.0]),
  'walking envelope': dict(hip_pitch=np.radians([-90, -60, -30, 0, 25]), hip_roll=np.radians([-25, -10, 0, 15]), hip_yaw=np.radians([-20, 0, 20]), knee=np.radians([-120, -60, 0])),
  'full ROM corners': dict(hip_pitch=np.radians([-90, -60, -30, 0, 25]), hip_roll=np.radians([-45, -25, -10, 0, 15, 25]), hip_yaw=np.radians([-45, -20, 0, 20, 45]), knee=np.radians([-120, -60, 0])),
}
grid = GRIDS[sys.argv[1]] if len(sys.argv) > 1 else GRIDS['walking envelope']
fromto = np.zeros(6)
def min_dist(abd_deg, pitch_deg=0.0):
    worst = (1e9, None)
    for s, sign in (('L', 1), ('R', 1)):
        d.qpos[jq(f'{s}_shoulder_roll_joint')] = np.radians(abd_deg)
        d.qpos[jq(f'{s}_shoulder_pitch_joint')] = np.radians(pitch_deg)
    poses = list(itertools.product(*grid.values())) + [(-0.32, 0.0, 0.0, -0.67)]
    for hp, hr, hy, kn in poses:
        for s in 'LR':
            d.qpos[jq(f'{s}_hip_pitch_joint')] = hp; d.qpos[jq(f'{s}_hip_roll_joint')] = hr
            d.qpos[jq(f'{s}_hip_yaw_joint')] = hy; d.qpos[jq(f'{s}_knee_joint')] = kn
        mujoco.mj_kinematics(m, d)
        for ga in arm:
            for gl in legs:
                dist = mujoco.mj_geomDistance(m, d, ga, gl, 0.2, fromto)
                if dist < worst[0]:
                    worst = (dist, (gname(ga), gname(gl), np.degrees([hp, hr, hy, kn]).round(0).tolist()))
    return worst
print('shoulder roll (negative = abduction, arm outward) | min signed distance arm<->leg over the grid (+bent pose) | worst pair @ hip_pitch/roll/yaw/knee deg')
for abd in (0, -5, -10, -15, -20, -25, -30):
    dist, info = min_dist(abd)
    print(f'  {abd:3d} deg | {dist * 1000:+7.1f} mm | {info}')
