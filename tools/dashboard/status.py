"""Health status for the dashboard: writes tools/dashboard/status.json every 15 s.
  nohup python3 tools/dashboard/status.py > /dev/null 2>&1 &
"""
import json, os, re, socket, subprocess, time, glob, shutil
REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'; MJ = f'{REPO}/mujoco-sim/mjlab'
RUNS = {'ankleAB_c2r': dict(wandb='https://wandb.ai/dongyub39-snu/pygmalion/runs/ewuilz2q', viser=8089, note='resumed from ankleAB_c2 model_1200 after the 23:10 OOM kill'),
        'ankleRP_c2': dict(wandb='https://wandb.ai/dongyub39-snu/pygmalion/runs/a6y6vo4w', viser=8090)}
PORTS = {'dashboard': 8890, 'viser_AB': 8089, 'viser_RP': 8090, 'tensorboard': 6006, 'assembly_viewer': 8891, 'collision_viewer': 8892}
HELPERS = {'gate_watch': 'gate_watc[h].sh', 'review_loop': 'review_loo[p].sh', 'gpu_sampler': 'gpu_sample[r].sh', 'viser_live': 'viser_liv[e].py', 'train': 'train_wandb_vide[o].py'}
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def port_up(p):
    s = socket.socket(); s.settimeout(0.5)
    try: s.connect(('127.0.0.1', p)); return True
    except OSError: return False
    finally: s.close()


def tail_metrics(log):
    try:
        txt = ANSI.sub('', subprocess.run(['tail', '-c', '20000', log], capture_output=True, text=True).stdout)
    except Exception: return {}
    out = {}
    for key, pat in (('iter', r'Learning iteration (\d+)/(\d+)'), ('reward', r'Mean reward: ([-\d.]+)'), ('fell', r'fell_over: ([\d.]+)'), ('it_time', r'Iteration time: ([\d.]+)s'), ('elapsed', r'Time elapsed: ([\d:]+)'), ('eta', r'ETA: ([0-9]+ days?, [0-9:]+|[0-9:]+)')):
        m = re.findall(pat, txt)
        if m: out[key] = m[-1] if key != 'iter' else {'i': int(m[-1][0]), 'max': int(m[-1][1])}
    return out


def gpu():
    try:
        u, m, t = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.strip().split(', ')
        return dict(util=int(u), mem_used=int(m), mem_total=int(t))
    except Exception: return {}


def pgrep(pat):
    return subprocess.run(['pgrep', '-fc', pat], capture_output=True, text=True).stdout.strip()


while True:
    st = dict(time=time.strftime('%Y-%m-%d %H:%M:%S'), runs={}, services={}, helpers={}, gpu=gpu())
    for run, meta in RUNS.items():
        d = sorted(glob.glob(f'{MJ}/logs/rsl_rl/pygmalion_velocity/*_{run}'))
        d = d[-1] if d else None
        ck = sorted(glob.glob(f'{d}/model_*.pt'), key=lambda p: int(p.split('_')[-1][:-3])) if d else []
        r = dict(alive=pgrep(f'run-name {run}') not in ('', '0'), run_dir=os.path.basename(d) if d else None, wandb=meta['wandb'], viser_port=meta['viser'],
                 last_ckpt=os.path.basename(ck[-1]) if ck else None, last_ckpt_age_s=int(time.time() - os.path.getmtime(ck[-1])) if ck else None, n_ckpt=len(ck),
                 clips=len(glob.glob(f'{d}/videos/train/*.mp4')) if d else 0, metrics=tail_metrics(f'{MJ}/logs/{run}.log'))
        st['runs'][run] = r
    for name, p in PORTS.items(): st['services'][name] = port_up(p)
    for name, pat in HELPERS.items(): st['helpers'][name] = int(pgrep(pat) or 0)
    du = shutil.disk_usage(REPO); st['disk_free_gb'] = round(du.free / 1e9, 1)
    st['load'] = os.getloadavg()[0]
    json.dump(st, open(f'{REPO}/tools/dashboard/status.json.tmp', 'w')); os.replace(f'{REPO}/tools/dashboard/status.json.tmp', f'{REPO}/tools/dashboard/status.json')
    time.sleep(15)
