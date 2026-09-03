"""P4: the 8-step verification protocol runner (docs/121 section 5)."""

from pygviewer import protocol

VARIANT = "LegOnly-AB"


def test_run_all_returns_all_8_steps_in_order():
  results = protocol.run_all(VARIANT)
  assert [r["step"] for r in results] == list(range(1, 9))


def test_automated_steps_pass():
  results = protocol.run_all(VARIANT)
  automated = {r["step"]: r for r in results if r["step"] in (1, 4, 5, 8)}
  assert len(automated) == 4
  failed = {n: r["detail"] for n, r in automated.items() if r["status"] != "PASS"}
  assert not failed, failed


def test_manual_steps_are_never_silently_passed():
  results = protocol.run_all(VARIANT)
  manual = {r["step"]: r for r in results if r["step"] in (2, 3, 6, 7)}
  assert len(manual) == 4
  for r in manual.values():
    assert r["status"] == "MANUAL"
    assert "real" in r["detail"].lower() or "hardware" in r["detail"].lower()


def test_step1_fails_outside_its_own_dq_budget():
  r = protocol.step1_static_zero(VARIANT, dq_budget=0.001)  # tighter than the 0.005 perturbation
  assert r["status"] == "FAIL"


def test_step5_offset_estimate_matches_injected_delay():
  r = protocol.step5_latency_calibration(VARIANT, delay_ms=30.0, jitter_ms=5.0)
  assert r["status"] == "PASS"
  assert "30.0 ms" in r["detail"]


def test_cli_main_exit_code_reflects_automated_pass_fail(capsys):
  rc = protocol.main(["--variant", VARIANT])
  assert rc == 0
  out = capsys.readouterr().out
  assert "static zero" in out
  assert "MANUAL" in out
