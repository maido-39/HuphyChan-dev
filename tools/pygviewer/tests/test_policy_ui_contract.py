"""Backend half of the dashboard's "Load & Run" error-display contract (docs/121 section 10,
2026-09-04 Policy panel UX fix): the Policy panel's ``policyLoadErrorText(name, err)``
(``pygviewer/static/dashboard.js``) is a pure function of whatever ``api()`` threw, and
``api()`` builds its ``Error.message`` as ``f"{method} {path} -> {status}: {JSON.stringify(
detail)}"`` - so the string an operator actually sees on a failed load is only ever as good as
``POST /policy/load``'s own ``detail`` field. This repo has no JS test runner (checked: no
``package.json``/``jest.config*`` anywhere under ``tools/pygviewer`` - a browser-side unit
test of the JS function itself is not set up), so this file verifies the CONTRACT the JS
function depends on instead: every failure mode ``POST /policy/load`` can return produces a
non-empty, human-readable string in ``detail``, never ``null``/``{}``/an empty string that
would render as "failed to load 'x': ...: {}" with nothing useful in it.
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


@pytest.fixture(scope="module")
def client():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.reset("knees_bent")
  c.step_n(1)
  app = build_app(c, c.c.freshness())
  try:
    yield TestClient(app), c
  finally:
    c.stop()


def _assert_display_ready_detail(r) -> None:
  body = r.json()
  assert "detail" in body, body
  assert isinstance(body["detail"], str) and body["detail"].strip(), (
    f"detail must be a non-empty string an operator can read as-is, got {body['detail']!r}"
  )


def test_unknown_baked_name_404_has_a_display_ready_detail(client):
  c, _core = client
  r = c.post("/policy/load", json={"name": "no-such-policy-baked"})
  assert r.status_code == 404, r.text
  _assert_display_ready_detail(r)
  assert "no-such-policy-baked" in r.json()["detail"]  # names the thing that failed


def test_no_contract_found_400_has_a_display_ready_detail(client, tmp_path):
  c, _core = client
  fake_onnx = tmp_path / "no_contract.onnx"
  fake_onnx.write_bytes(b"not a real onnx file")
  r = c.post("/policy/load", json={"onnx": str(fake_onnx)})
  assert r.status_code == 400, r.text
  _assert_display_ready_detail(r)


@pytest.mark.skipif(not POLICIES, reason="no policy baked for LegOnly-AB yet")
def test_foreign_contract_409_has_a_display_ready_detail(client, tmp_path):
  c, _core = client
  pc = json.loads(open(POLICIES[0]).read())
  bad_onnx = tmp_path / "bad.onnx"
  bad_onnx.write_bytes(open(pc["onnx"], "rb").read())
  bad_contract = tmp_path / "bad.policy_contract.json"
  bad_contract.write_text(json.dumps(dict(pc, model_contract_sha="0" * 64)))
  r = c.post("/policy/load", json={"onnx": str(bad_onnx)})
  assert r.status_code == 409, r.text
  _assert_display_ready_detail(r)
