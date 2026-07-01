# docs/mujoco — mjlab(MuJoCo-Warp) Pygmalion 분석 노트

IsaacLab 계통(`pygmalion_locomotion/`)과 별개로, **mjlab**(MuJoCo-Warp, `mujoco-sim/mjlab/`)
에서 학습한 Pygmalion 정책의 **HW 설계용 부하** 분석을 모으는 곳.

## 노트
- [2026-07-01_load_analysis_flat_rough.md](2026-07-01_load_analysis_flat_rough.md) — flat run
  `2026-06-30_20-12-31`의 다방향 부하 측정 + rough 지형 배포 비교 (토크/속도/wrench/scatter/GRF).
- [2026-07-01_training_progression.md](2026-07-01_training_progression.md) — **6000 iter마다 검증**해
  부하값이 학습에 따라 어떻게 변하는지 추세(ankle_pitch·knee 포화 vs GRF·효율 개선). `progression_watch.sh`로 60000까지 자동 확장.

## 측정 방법 (왜 / 어떻게)
도구는 mjlab 쪽에 있음 (mjlab 환경 필요): `mujoco-sim/mjlab/analysis/`.

| 스크립트 | 역할 |
|---|---|
| `measure_loads.py` | CPU 분리 rollout → IsaacLab 포맷 npz(`tau_<joint>`/`omega_<joint>`/`Fx_<body>`/`GRF_*`/`Pmech_*`/`qpos_full`) |
| `plot_loads.py` | npz → IsaacLab §7 양식 플롯(mjlab 모터 스펙) + flat/rough 색구분 + torque-RPM scatter + **q(관절각)-torque scatter** |
| `render_loads.py` | full qpos 재생 → **부하-색 영상**(관절 구 indicator, base 추적, 실제 terrain) |
| `make_dashboard_video.py` | **좌-영상/우-히스토그램 side-by-side 영상**(관절족별 토크·RPM 히스토그램+limit+현재값 마커) |
| `play_loadviz.py` | **Play(인터랙티브)에서 실시간 관절별 부하 색구** — robot spec에 관절 구 geom 주입+geom_rgba per-world(native/viser 공용). 영상과 동일 indicator |
| `progression.sh` + `progression_analyze.py` | **3000 iter마다 체크포인트 검증** → 토크·속도(max/p95/RMS)·GRF·power vs iteration 추세 플롯 + 노트(해석 섹션 보존) |
| `progression_montage.py` | 체크포인트별 **로봇 움직임 montage 영상**(동일 명령 동기화 격자, 부하-색, iter 라벨) |
| `progression_watch.sh` | 위 3개를 detached 폴링 → 학습이 진행되며 60000까지 진행분석·영상 **자동 확장** |
| `measure_loads.sh` | CPU 격리 런처(`CUDA_VISIBLE_DEVICES=""`) |

★ **계속 이어지는 루틴** (새 체크포인트/데이터마다 아래 4단계 재실행 → 노트/플롯/영상 자동 갱신):
```bash
cd ~/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
RUN=logs/rsl_rl/pygmalion_velocity/<latest_run>;  A=~/MikuchanRemote/Human-Pygmalion/docs/mujoco/assets
# 1) 넓은 DR·장시간 측정 (flat + rough)  [CPU 격리=학습 무중단]
CUDA_VISIBLE_DEVICES="" uv run python analysis/measure_loads.py --run-dir "$RUN" \
  --task Mjlab-Velocity-Flat-Pygmalion  --tag flat  --wide-dr --steps 7200
CUDA_VISIBLE_DEVICES="" uv run python analysis/measure_loads.py --run-dir "$RUN" \
  --task Mjlab-Velocity-Rough-Pygmalion --tag rough --blind --rough-terrain --wide-dr --steps 7200
# 2) 플롯 (토크/속도/scatter/q-torque/wrench/★GRF, flat·rough 색구분)
CUDA_VISIBLE_DEVICES="" uv run python analysis/plot_loads.py --flat analysis/out/flat.npz --rough analysis/out/rough.npz --out "$A"
# 3) 부하-색 영상
for t in flat rough; do CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl uv run python analysis/render_loads.py --npz analysis/out/$t.npz --tag $t --out "$A" --downsample 6; done
# 4) ★ side-by-side 대시보드 영상 (좌 로봇 / 우 히스토그램+limit+현재값)
for t in flat rough; do CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl uv run python analysis/make_dashboard_video.py --npz analysis/out/$t.npz --tag $t --out "$A"; done
```

### 영상 색 기준 (`render_loads.py`)
**각 관절 anchor에 색구(sphere) indicator** — 관절마다 1개라 ankle roll/pitch, hip yaw/roll/pitch,
knee를 **개별 구분**. 색: **회색** \|τ\|<rated · **🟡노랑** ≥rated(nominal) · **🟠주황** ≥70% peak ·
**🔴빨강** ≥peak(100%). ankle_pitch 구는 roll과 겹치지 않게 **종아리쪽으로 올림**(복사뼈 위).
로봇은 **측정 당시 실제 terrain**(`<tag>_model.mjb`, rough heightfield 포함) 위에 렌더 → 발이 지면에 맞음.

### Play 실시간 관절별 부하 색구 (`play_loadviz.py`)
영상과 **동일한 관절별 구 indicator**를 인터랙티브 Play에 적용. robot spec에 관절마다 massless
구 geom을 주입(ankle_pitch는 종아리쪽 offset)하고, `geom_rgba`를 per-world expand해 매 step 색
갱신 → native·viser 둘 다 매 프레임 동기화로 반영.

**헤드리스/원격 → viser 웹뷰어 (외부접속)**: 기본 `--host 0.0.0.0 --port 8080`로 바인딩 →
원격 PC 브라우저에서 **`http://<서버IP>:8080`** 접속(같은 망/포트 개방 필요). 실행 시 접속 URL을 출력.

```bash
cd ~/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
RUN=logs/rsl_rl/pygmalion_velocity/2026-06-30_20-12-31   # 또는 최신 run 디렉토리

# ── Flat 지형 ──
uv run python analysis/play_loadviz.py --run-dir "$RUN"                         # auto(원격→viser)
uv run python analysis/play_loadviz.py --run-dir "$RUN" --viewer viser --port 8080

# ── Rough(거친지형, blind 배포) ──
uv run python analysis/play_loadviz.py --run-dir "$RUN" \
  --task Mjlab-Velocity-Rough-Pygmalion --blind --rough-terrain --viewer viser

# 로컬 디스플레이가 있으면 native 창:
uv run python analysis/play_loadviz.py --run-dir "$RUN" --viewer native
# 헤드리스 검증(뷰어 없이): --selftest 200  → "levels seen: grey/yellow/orange/red"
```
접속 후 viser UI에서 재생/일시정지·카메라 조작 가능. 외부에서 안 열리면 방화벽에서 8080 포트를 여세요
(`http://localhost:8080`은 서버 로컬에서, 원격은 서버 IP 사용). SSH만 가능하면
`ssh -L 8080:localhost:8080 <서버>` 후 로컬 브라우저에서 `localhost:8080`.

### 핵심 설계 결정
- **CPU + `CUDA_VISIBLE_DEVICES=""`** → 학습 GPU와 완전 격리(학습 무중단). 검증: 측정 중 GPU 메모리 불변, 체크포인트 계속 증가.
- **다방향 명령 스윕** (`COMMAND_SCHEDULE`): 전진(0.5/1.0/1.5)·후진·측방(±0.5/±1.0)·회전(±0.5/0.7)·대각·곡선·정지 = 학습 DR(lin_vel_x/y, yaw) 전 범위. **worst-case 하중 = 전진만 측정의 한계 보완.**
- **모터 스펙(mjlab ≠ IsaacLab)**: mjlab Pygmalion은 ROBSTRIDE 00/03/04, **knee가 plain RS04(감속 없음)**. SPEC: hip_pitch/roll·knee (120/40/143rpm), hip_yaw·ankle_pitch (60/20/191), ankle_roll (14/5/315). (IsaacLab은 knee 360/120/66.7rpm로 3:1 감속 — 다름.)
- **rough = blind 배포**: rough-학습 체크포인트가 없어, flat 정책을 height_scan 없이 rough 지형에 올림 = "평지정책이 거친지형을 안 보고 걷는" 강건성 하중. **정식 rough gait 아님**(caveat). rough 정책 학습 후 재측정 권장.

### 측정량
1. **관절 토크/속도** RMS·p95·max + 모터 peak/rated/속도한계 대비 포화% (`<tag>_torque.png`/`_speed.png`/`_torque_ts.png`/`_speed_ts.png`)
2. **토크-RPM scatter** (관절족별, L+R, peak×maxspeed box, flat/rough 오버레이) (`cmp_torque_speed_scatter.png`)
3. **관절위치별 6-DoF 반력 wrench** `cfrc_int`=[moment;force], 전역·바디 CoM 기준 (`cmp_link_force.png`)
