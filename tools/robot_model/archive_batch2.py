"""Second archive batch: caption + rename existing design/analysis clips, build two slideshows.
Filename = YouTube title: 'YYYYMMDD HHMMSS Huphy 1.0 - <topic>' with the SOURCE file's mtime."""
import os, subprocess, datetime, json
REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'; A = f'{REPO}/docs/mujoco/assets'; OUT = f'{REPO}/docs/video/archive'; FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
def esc(t): return t.replace('\\', '\\\\').replace(':', '\\:').replace("'", "’").replace('%', '\\%')
def stamp(p): return datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y%m%d %H%M%S')
def safe(t): return t.replace('/', ' ').replace(':', ' -').replace('?', '')
def vf(title, cap, w_font=None):
    return (f"drawbox=y=0:h=42:color=black@0.65:t=fill,drawtext=fontfile={FONT}:text='{esc(title)}':fontsize=19:fontcolor=white:x=12:y=11,"
            f"drawbox=y=ih-38:h=38:color=black@0.65:t=fill,drawtext=fontfile={FONT}:text='{esc(cap)}':fontsize=15:fontcolor=yellow:x=12:y=h-27")
def run(args): subprocess.run(args, check=True)
def caption(src, topic, cap, extra_in=None, speed=None, loops=1, concat=None, trim=None):
    title = f'{stamp(src)} Huphy 1.0 - {topic}'; out = f'{OUT}/{safe(title)}.mp4'
    if os.path.exists(out):
        dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out], capture_output=True, text=True).stdout); print(f'{dur:6.1f} s  (exists) {os.path.basename(out)}'); return title, dur
    inputs = []; filt = []
    if concat:
        lst = f'{OUT}/_concat.txt'; open(lst, 'w').write(''.join(f"file '{p}'\n" for p in concat for _ in range(loops)))
        pre = f'{OUT}/_pre.mp4'; run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', pre]); src_in = pre
    elif loops > 1:
        lst = f'{OUT}/_concat.txt'; open(lst, 'w').write(f"file '{src}'\n" * loops)
        pre = f'{OUT}/_pre.mp4'; run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', pre]); src_in = pre
    else: src_in = src
    v = vf(title, cap)
    if speed: v = f"setpts={1/speed}*PTS," + v
    cmd = ['ffmpeg', '-y', '-loglevel', 'error']
    if trim: cmd += ['-ss', str(trim[0]), '-t', str(trim[1])]
    cmd += ['-i', src_in, '-vf', v, '-an', '-pix_fmt', 'yuv420p', '-crf', '20', out]; run(cmd)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out], capture_output=True, text=True).stdout)
    print(f'{dur:6.1f} s  {os.path.basename(out)}'); return title, dur
def slideshow(images, topic, cap_per, stamp_src, per=4.0):
    """images: list of (path, caption). Scaled/padded to 1280x720, per seconds each."""
    title = f'{stamp(stamp_src)} Huphy 1.0 - {topic}'; out = f'{OUT}/{safe(title)}.mp4'
    parts = []
    for k, (img, cap) in enumerate(images):
        p = f'{OUT}/_s{k}.mp4'
        run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-t', str(per), '-i', img, '-vf', f"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=white,{vf(title, cap)}", '-r', '25', '-pix_fmt', 'yuv420p', '-crf', '20', p]); parts.append(p)
    lst = f'{OUT}/_concat.txt'; open(lst, 'w').write(''.join(f"file '{p}'\n" for p in parts))
    run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out])
    for p in parts: os.remove(p)
    print(f'{per*len(images):6.1f} s  {os.path.basename(out)}'); return title, per * len(images)
made = []
made.append(caption(f'{A}/ankle_v9_rom_sweep.mp4', '2-RSU ankle v9 design, ROM sweep with rod-end swing gauges', 'pitch -50..+30 x roll +-20 raster: 3D mechanism + rod A/B swing-angle gauges (JS6 limit 20 deg, red = over). v9h2 winner: crank 40-65, A_h>40, human gait coverage x1.25 SF'))
made.append(caption(f'{A}/ankle_ballswing_sweep.mp4', '2-RSU ankle, rod-end ball swing over the whole ROM', 'boustrophedon sweep of the ankle pose; gauges = rod-end swing angle vs the spherical-bearing limit. Basis for the clevis-bolt-axis decision (docs/71, 76)'))
made.append(caption(f'{A}/ankle_2rsu_motion_torque.mp4', '2-RSU ankle replaying a learned gait, crank torques', 'measured gait (gen21p2, 0.8-2.5 m/s blocks) replayed through the 2-RSU linkage: cranks A/B, rods, sole; ankle torque up to 52 N*m -> crank torques', loops=2))
made.append(caption(f'{A}/ankle_opt_process.mp4', '2-RSU ankle geometry optimisation, pattern search (slowed 4x)', 'pattern search over crank / rod / anchor geometry with hard constraints (Deb rules): ROM reach, torque, T-N, swing angle. slowed 4x, not real-time', speed=0.25))
made.append(caption(f'{A}/wrench3d_turntable_gen21p2.mp4', 'joint reaction wrench 3D envelopes, 6 leg joints (slow turntable)', 'force / moment vectors at each joint from the measured gait (gen21p2 fc): RMS / P99 / peak directional quantiles. slow turntable, not real-time data. docs/64-65'))
made.append(caption(f'{A}/ghost_straight_vs_bent.mp4', 'init pose A/B, straight vs bent knee (ghost overlay)', 'same commands, two policies overlaid: straight-knee init vs bent crouch init. Result: no winner - bent lowers GRF 35 percent but knee torque +98 percent (docs/55)'))
made.append(caption(f'{A}/ghost_B_Kd6_vs_C_Kd14.mp4', 'PD damping A/B, Kd 6 vs link-critical Kd 14 (ghost overlay)', 'controlled A/B: link-critical Kd raised loads 2-3.5x and cut tracking 2.8-5x -> rejected, under-damped Kd 6 kept (docs/53, 70)'))
made.append(caption(f'{A}/knee_reward_sensitivity_5way.mp4', 'knee load sensitivity across 5 reward variants x 3 speeds', '5 policies frame-locked at 0.75 / 1.75 / 2.5 m/s; knee marker colour = load class, panel labels = block RMS / P99. Spread concentrates at low speed (docs/65)'))
made.append(caption(f'{A}/ab_nocant_vs_cant30fp.mp4', 'hip geometry A/B, no-cant vs 30 deg canted hip pitch axis (side by side)', 'left: flat anchor gen21p2 / right: cant30 feet-parallel. same command schedule frame-locked, real time 25 fps, joint load spheres (docs/67, 68)', trim=(0, 60)))
made.append(caption(f'{A}/joint_motion_cant30.mp4', 'hip geometry variants, joint motion: cant30 and roll-offset 30', 'hip_pitch axis canted 30 deg (first half) vs hip_roll axis offset 30 mm outward (second half): how the foot heading / clearance changes per joint (docs/68)', concat=[f'{A}/joint_motion_cant30.mp4', f'{A}/joint_motion_rolloff30.mp4']))
made.append(caption(f'{REPO}/docs/img/robot_v2_zeroshot_walk1.mp4', 'v2 CAD-exact model, old policy zero-shot (pipeline check)', 'MJCF rebuilt from the 2026-08 CAD (new link lengths, 42 kg aluminium) driven by the previous policy: stays up, knees saturate -> retraining needed (docs/87)'))
made.append(caption(f'{A}/gen21p2_fc_demo_loadviz.mp4', 'flat anchor policy gen21p2, command sweep with joint loads and GRF (60 s excerpt)', 'vx sweep blocks 15 s each, real time 25 fps: joint load spheres (grey<rated<yellow<orange<red), GRF arrows (0.4 m = 1 BW), signed wrench panel', trim=(60, 60)))
made.append(caption(f'{REPO}/docs/video/urdf_crosscheck_pygmalion_v3_printed_loop.mp4', 'closed-loop model URDF vs MJCF cross-check, 29 joints', 'loop model (cranks + rods as a URDF tree) read by MuJoCo URDF parser (red wire) vs the MJCF: 29/29 joints, 0.0000 mm over 200 random poses'))
I = f'{REPO}/docs/img'
made.append(slideshow([(f'{A}/fea_setup_L1_ankle_foot.png', 'FEA setup: printed ankle-foot group, measured worst-frame load cases from the gait data'), (f'{I}/L5_field.png', 'von Mises field, shin link (L5) under the P99 load case'), (f'{I}/L5_load_breakdown.png', 'load breakdown per case: which gait phase drives the stress'), (f'{I}/L1b_foot_deformed.png', 'foot plate deformed shape (scaled) - sole plate bending under toe-off'), (f'{I}/fea_mesh_convergence.png', 'mesh convergence: design stress read away from load/constraint nodes (3 rules)'), (f'{I}/pla_failure_map.png', 'PLA triage: in-plane 25.5 MPa / interlayer 11.3 MPa limits -> which printed parts break first'), (f'{I}/fea_final_verdict.png', 'final verdict table: safety factors per link, CNC replacement order')], 'FEA of the printed links, PLA triage and lightweighting (slides)', None, f'{I}/fea_final_verdict.png'))
made.append(slideshow([(f'{I}/pygmalion_v3_printed_zero_pose.png', 'CAD export copy -> URDF + MJCF: zero pose, printed-density masses (35.35 kg)'), (f'{I}/pygmalion_v3_printed_joint_sweeps.png', 'every joint swept through its range in the built model'), (f'{I}/joint_rom_measured.png', 'joint ROM measured on the real CAD meshes (triangle-mesh interpenetration sweep)'), (f'{I}/alu_parts_density_ratio.png', 'printed parts weighed: measured / aluminium mass ratio 0.33 -> density per part'), (f'{I}/mass_dr_ranges.png', 'mass uncertainty propagated per link -> domain randomisation ranges (pseudo-inertia)'), (f'{I}/arm_abduction_15deg.png', 'arms welded 15 deg out so the hanging arm capsule clears the hip'), (f'{I}/loop_ankle_transmission.png', 'closed-loop ankle: crank angles -> passive foot pitch / roll (transmission map)'), (f'{I}/ankle_rp_envelope.png', 'RP-mode torque envelope from the loop IK/FK: what the two RS03 cranks can deliver per pose')], 'CAD to URDF MJCF pipeline, ROM, printed density, mass DR (slides)', None, f'{I}/ankle_rp_envelope.png'))
for f in ('_concat.txt', '_pre.mp4'):
    p = f'{OUT}/{f}'
    if os.path.exists(p): os.remove(p)
json.dump(made, open(f'{OUT}/_batch2.json', 'w'), ensure_ascii=False, indent=1)
