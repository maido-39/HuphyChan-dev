# EBIMU read-only measurement

`ebimu_wrapper_measure.py` is the preferred tool as of 2026-09-02: it drives
HUPHY's actual deployment class (`huphy.sensors.ebimu.imu.EbimuImu`) instead of
re-implementing a reader, so the numbers match what a real control loop would
see (staleness/age per poll, the wrapper's own `dropped` counter, the
background read-thread's latest-only semantics). `EbimuImu.connect()`/`read()`
never write to the port. It needs pyserial; if the host has no `pip`, vendor
the pure-Python wheel instead of touching system Python — see "No pip on the
host" below.

`ebimu_readonly_probe.py` is the older standalone reader (native tty fallback
when pyserial is entirely unavailable, no HUPHY class dependency). Keep it as
a fallback only.

Both intentionally never alter HUPHY or send any EBIMU command. First run
HUPHY's read-only configuration query, then use the reported output order
verbatim.

If the host has HUPHY but lacks its optional `pyserial` dependency, use
`ebimu_config_show.py` instead. It is the same read-only `<cfg>` plus mandatory
`>` resume exchange implemented by HUPHY's `huphy-imu show`; it never changes a
stored EBIMU setting.

```bash
cd ~/HUPHY
huphy-imu --config config/robot_v1.0.yaml show

python3 /path/to/Human-Pygmalion/tools/imu/ebimu_wrapper_measure.py \
  --huphy-src ~/HUPHY/src --pydeps /path/to/vendored/pydeps \
  --port /dev/ttyUSB0 \
  --output quat,gyro,accel,dist,temp,time \
  --seconds 120 --poll-hz 500 --label level_still --out-dir ~/imu_logs
```

## No pip on the host

If `python3 -m pip` is missing and you don't want to touch system packages on
a shared/live host (e.g. one that's mid-training), don't `apt install
python3-pip` — vendor pyserial instead, with zero root/system changes:

```bash
# on a machine that has pip + internet:
python3 -m pip download pyserial --no-deps -d /tmp/pyserial_pkg
scp /tmp/pyserial_pkg/pyserial-*.whl target-host:/tmp/pydeps_src/
# on the target host:
mkdir -p ~/pydeps && cd ~/pydeps
python3 -c "import zipfile; zipfile.ZipFile('/tmp/pydeps_src/pyserial-*.whl').extractall('.')"
# then pass --pydeps ~/pydeps to ebimu_wrapper_measure.py
```

pyserial is pure Python (no compiled extension), so this is safe and fully
reversible — nothing outside `~/pydeps` is touched.

The configuration query sends `<cfg>` and then the required resume byte `>`;
it does not change stored sensor settings. The probe sends no serial bytes.
Do **not** run `huphy-imu apply` for this measurement.

Record these conditions separately:

1. `level_still`: mounted robot powered but motionless, at least 10 minutes.
2. `tilt_static`: sensor fixed at a two-axis tilt (not moving), at least 2 minutes.
3. `hand_motion`: gentle roll/pitch/yaw motion for 2 minutes; make a visible
   start/stop motion event so delay can be aligned to a phone video.

The summaries are sufficient to derive nominal rate, arrival jitter, dropped
packets, stationary gyro bias/noise, gravity-vector error, temperature drift,
and the first bounded P2 sensor DR. They do not prove end-to-end latency without
an external visible event or synchronized motor telemetry.
