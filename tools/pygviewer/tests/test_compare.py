"""P4: ``compare.py`` - contract/condition checks, clock-offset estimation, plotting."""

import gzip
import json
import math
import random

import pytest

from pygviewer import compare
from pygviewer.record import Recorder
from pygviewer.schema import JointState

JOINTS = ["a", "b"]


def _write_recording(path, contract_hash, base_mode, n=300, dt=0.01, delay_s=0.0,
                      jitter_s=0.0, freq_hz=1.0, seed=0):
  rec = Recorder(
    path,
    dict(v=1, contract_hash=contract_hash, variant="TestVariant",
          base=dict(mode=base_mode, height=0.9, ground=True, pivot_offset=[0, 0, 0]),
          gains_source="train", mode="manual"),
  )
  rng = random.Random(seed)
  t0_ns = 1_000_000_000
  for i in range(n):
    t = i * dt + delay_s + rng.uniform(-jitter_s, jitter_s)
    q0 = math.sin(2 * math.pi * freq_hz * (i * dt))
    msg = JointState(
      t_ns=t0_ns + int(t * 1e9), seq=i, src="sim", contract_hash=contract_hash,
      joint_names=JOINTS, q=[q0, -q0], target=[q0, -q0], tau_est=[q0 * 0.1, -q0 * 0.1],
    )
    rec.write_message(msg)
  rec.close()


@pytest.fixture
def recordings(tmp_path):
  sim_path = tmp_path / "sim.jsonl.gz"
  real_path = tmp_path / "real.jsonl.gz"
  _write_recording(sim_path, "abc123", "fixed", delay_s=0.0, jitter_s=0.0)
  _write_recording(real_path, "abc123", "fixed", delay_s=0.030, jitter_s=0.005, seed=1)
  return sim_path, real_path


def test_load_recording_reads_header_and_rows(recordings):
  sim_path, _ = recordings
  hdr, rows = compare.load_recording(sim_path)
  assert hdr["contract_hash"] == "abc123"
  assert len(rows) == 300
  assert rows[0]["type"] == "JointState"


def test_contract_mismatch_is_refused_without_i_know(tmp_path):
  a = tmp_path / "a.jsonl.gz"
  b = tmp_path / "b.jsonl.gz"
  _write_recording(a, "hash-a", "fixed")
  _write_recording(b, "hash-b", "fixed")
  with pytest.raises(SystemExit):
    compare.main(["--sim", str(a), "--real", str(b), "--out-dir", str(tmp_path)])


def test_contract_mismatch_is_allowed_with_i_know(tmp_path):
  a = tmp_path / "a.jsonl.gz"
  b = tmp_path / "b.jsonl.gz"
  _write_recording(a, "hash-a", "fixed")
  _write_recording(b, "hash-b", "fixed")
  rc = compare.main(["--sim", str(a), "--real", str(b), "--out-dir", str(tmp_path), "--i-know"])
  assert rc == 0


def test_condition_warning_fires_on_different_base_mode(recordings, tmp_path, capsys):
  sim_path, _ = recordings
  real_path = tmp_path / "real_free.jsonl.gz"
  _write_recording(real_path, "abc123", "free", delay_s=0.03)
  compare.main(["--sim", str(sim_path), "--real", str(real_path), "--out-dir", str(tmp_path)])
  out = capsys.readouterr().out
  assert "R9" in out
  assert "base.mode" in out


def test_clock_offset_estimate_recovers_injected_delay(recordings):
  hdr_sim, rows_sim = compare.load_recording(recordings[0])
  hdr_real, rows_real = compare.load_recording(recordings[1])
  result = compare.estimate_clock_offset_ms(rows_sim, rows_real, "a", "q", dt=0.005)
  assert result["offset_ms"] is not None
  assert abs(result["offset_ms"] - 30.0) <= 15.0, result


def test_plot_and_cli_write_pngs(recordings, tmp_path, capsys):
  sim_path, real_path = recordings
  rc = compare.main(
    ["--sim", str(sim_path), "--real", str(real_path), "--joints", "a,b",
     "--out-dir", str(tmp_path), "--tag", "unittest"]
  )
  assert rc == 0
  out = capsys.readouterr().out
  assert "clock offset estimate" in out
  for j in JOINTS:
    p = tmp_path / f"compare_unittest_{j}.png"
    assert p.exists() and p.stat().st_size > 0


def test_unknown_joint_is_skipped_not_fatal(recordings, tmp_path, capsys):
  sim_path, real_path = recordings
  rc = compare.main(
    ["--sim", str(sim_path), "--real", str(real_path), "--joints", "a,not_a_joint",
     "--out-dir", str(tmp_path)]
  )
  assert rc == 0
  err = capsys.readouterr().err
  assert "not_a_joint" in err
