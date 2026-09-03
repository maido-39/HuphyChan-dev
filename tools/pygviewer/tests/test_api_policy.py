"""The FastAPI layer must actually expose what P2 implements, not the P1-era stub list.

This caught a real bug during P2 hardening: ``POST /mode`` still hardcoded ``idle|manual``
as the only accepted values (a synchronous pre-check, added in P1 to fail fast instead of
silently dropping a bad command into the async ``core.submit`` queue) and rejected
``policy_sim`` with a 501 even though ``sim_core.py`` had implemented it. The UI panel never
saw this because it calls ``core._apply_cmd`` directly, bypassing the API - only an actual
HTTP client against ``/mode`` exercises the bug. This test drives the endpoint the way any
outside client (or the P3 bridge / a script) would.
"""

import glob
import json

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"
POLICIES = sorted(
  p
  for p in glob.glob(f"{CACHE_DIR}/*.policy_contract.json")
  if json.loads(open(p).read())["variant"] == VARIANT
)
pytestmark = pytest.mark.skipif(not POLICIES, reason="no policy baked for LegOnly-AB yet")


@pytest.fixture
def client():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.reset("knees_bent")
  c.step_n(1)  # populate the snapshot so /status and /joints have something to read
  app = build_app(c, c.c.freshness())
  try:
    yield TestClient(app), c
  finally:
    c.stop()


def _load_policy(client_core):
  client, core = client_core
  pc = json.loads(open(POLICIES[0]).read())
  r = client.post("/policy/load", json={"onnx": pc["onnx"]})
  assert r.status_code == 200, r.text
  return r.json()


def test_mode_rejects_policy_sim_without_a_loaded_policy(client):
  client, _ = client
  r = client.post("/mode", json={"mode": "policy_sim"})
  assert r.status_code == 409, r.text


def test_mode_accepts_policy_sim_once_a_policy_is_loaded(client):
  _load_policy(client)
  c, core = client
  r = c.post("/mode", json={"mode": "policy_sim"})
  assert r.status_code == 200, r.text
  core.step_n(core.decimation)  # drain: a whole ctrl period guarantees one drain boundary
  assert core.mode == "policy_sim"


def test_mode_accepts_real_replay_and_forces_base_fixed(client):
  """real_replay is P3 (see test_replay.py for the full drive-from-telemetry behaviour);
  this only checks the API-level contract: it is accepted, and the safety rule (design doc
  section 6 / item 6) that entering it always forces the base to fixed."""
  client, core = client
  core.set_base(mode="free")
  r = client.post("/mode", json={"mode": "real_replay"})
  assert r.status_code == 200, r.text
  core.step_n(core.decimation)
  assert core.mode == "real_replay"
  assert core.base_mode == "fixed"


def test_mode_rejects_file_replay_without_a_loaded_recording(client):
  client, _ = client
  r = client.post("/mode", json={"mode": "file_replay"})
  assert r.status_code == 409, r.text


def test_mode_rejects_policy_shadow_without_a_loaded_policy(client):
  client, _ = client
  r = client.post("/mode", json={"mode": "policy_shadow"})
  assert r.status_code == 409, r.text


def test_mode_accepts_policy_shadow_once_a_policy_is_loaded(client):
  """P4: policy_shadow is now a real mode, not a 501 stub (test_mode_rejects_policy_shadow_as_p4
  above was the P3-era contract; superseded now that build_shadow exists)."""
  _load_policy(client)
  c, core = client
  r = c.post("/mode", json={"mode": "policy_shadow"})
  assert r.status_code == 200, r.text
  core.step_n(core.decimation)
  assert core.mode == "policy_shadow"


def test_policy_load_refuses_a_foreign_contract(tmp_path, client):
  """Same check as ``test_policy_parity.py::test_wrong_model_is_refused``, through the HTTP
  layer: a policy contract naming another model's sha must come back 409, not load."""
  client, _ = client
  pc = json.loads(open(POLICIES[0]).read())
  bad_onnx = tmp_path / "bad.onnx"
  bad_onnx.write_bytes(open(pc["onnx"], "rb").read())
  bad_contract = tmp_path / "bad.policy_contract.json"
  bad_contract.write_text(json.dumps(dict(pc, model_contract_sha="0" * 64)))
  r = client.post("/policy/load", json={"onnx": str(bad_onnx)})
  assert r.status_code == 409, r.text


def test_policy_load_unknown_name_is_404(client):
  client, _ = client
  r = client.post("/policy/load", json={"name": "no-such-policy-baked"})
  assert r.status_code == 404, r.text


def test_policy_cmd_and_io_after_load(client):
  _load_policy(client)
  c, core = client
  r = c.post("/policy/cmd", json={"vx": 0.4, "vy": 0.0, "wz": 0.0})
  assert r.status_code == 200, r.text
  core.step_n(core.decimation)
  r = c.get("/policy/io")
  assert r.status_code == 200, r.text
  body = r.json()
  assert body["cmd"] == [0.4, 0.0, 0.0]
  assert len(body["obs_sources"]) == len(body["obs"]) == 0 or len(body["obs_sources"]) > 0


def test_obs_source_real_is_accepted_p4(client):
  """P4: per-term 'real' sourcing is implemented (test_obs_source_real_is_501_until_p3 above
  was the P3-era stub contract). Setting it does not require any real data to be flowing -
  the staleness fallback in build_shadow handles that; see test_policy_shadow.py for the
  end-to-end mux behaviour."""
  _load_policy(client)
  c, core = client
  r = c.get("/policy/io")
  term = list(r.json()["obs_sources"].keys())[0] if r.status_code == 200 else None
  term = term or list(core.obs_mux.sources.keys())[0]
  r = c.post("/obs_source", json={"sources": {term: "real"}})
  assert r.status_code == 200, r.text
  assert r.json()["sources"][term] == "real"


def test_gains_get_and_switch_to_real_without_a_table_is_rejected(client):
  client, _ = client
  r = client.get("/gains")
  assert r.status_code == 200
  assert r.json()["source"] == "train"
  r = client.post("/gains", json={"source": "real"})
  # this contract has no real_gains table baked in, so switching must fail loudly rather
  # than inventing hardware numbers
  assert r.status_code == 400, r.text
