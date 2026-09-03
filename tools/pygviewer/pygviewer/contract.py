"""Model contract: what the baked ``.mjb`` promises, and how to check it is still true.

The contract is a plain JSON file written next to the ``.mjb`` by ``bake.py``.  It is the
ONLY place the viewer is allowed to learn joint order, default pose, gains, clip windows or
mirror conventions from - never a regex over joint names.  That rule exists because a single
``".*_knee_joint"`` regex is what put the v30 left knee's command window at 0 deg for a whole
training run (docs/reward_research/2026-09-03_stiff_knee_root_cause.md).

This module deliberately imports neither mjlab nor torch: the runtime process must stay
small while a GPU training run is using the machine.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_VERSION = 1


def sha256_file(path: str | os.PathLike) -> str:
  h = hashlib.sha256()
  with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
      h.update(chunk)
  return h.hexdigest()


def canonical_sha(obj: Any) -> str:
  """sha256 of a JSON object, key-sorted, so the same content always hashes the same."""
  blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
  return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class ModelContract:
  """Typed accessor over the contract JSON.  ``raw`` stays authoritative."""

  raw: dict
  path: Path

  # ---------------------------------------------------------------- identity
  @property
  def variant(self) -> str:
    return self.raw["variant"]

  @property
  def ankle_mode(self) -> str:
    return self.raw["ankle_mode"]

  @property
  def is_loop(self) -> bool:
    return self.raw["ankle_mode"] == "AB"

  @property
  def contract_sha(self) -> str:
    return self.raw["contract_sha"]

  @property
  def mjb_path(self) -> Path:
    return self.path.with_suffix("").with_suffix(".mjb")

  # ------------------------------------------------------------ joint tables
  @property
  def joint_names(self) -> list[str]:
    return list(self.raw["joint_names"])

  @property
  def action_joint_names(self) -> list[str]:
    return list(self.raw["action_joint_names"])

  @property
  def obs_joint_names(self) -> list[str]:
    return list(self.raw["obs_joint_names"])

  def default_q(self, name: str) -> float:
    return float(self.raw["default_q"][name])

  def clip(self, name: str) -> tuple[float, float]:
    """Command window for an actuated joint: the contract's ``safe_clip``.

    Falls back to the joint's own MJCF range for a joint with no clip entry (the passive
    ankle/rod hinges of the loop build), so a caller never has to invent a bound.
    """
    c = self.raw["safe_clip"].get(name)
    if c is None:
      c = self.raw["joint_contract"][name]["range"]
    return float(c[0]), float(c[1])

  def gains(self, name: str) -> dict:
    return self.raw["gains"][name]

  # ----------------------------------------------------------------- freshness
  def freshness(self) -> dict:
    """Re-hash the sources the bake was made from and report any mismatch.

    A stale ``.mjb`` is the failure mode that matters here: the XML or
    ``pygmalion_constants.py`` moved under the cache and the viewer would then be showing a
    robot the trainer no longer uses.  The caller decides whether to refuse or warn.
    """
    out: dict[str, Any] = {"stale": False, "checks": {}}
    for key, src in (("xml", self.raw["model_xml"]), ("constants", self.raw["constants_path"])):
      want = self.raw[f"{key}_sha256"]
      if not os.path.exists(src):
        out["checks"][key] = {"ok": False, "reason": "missing", "path": src}
        out["stale"] = True
        continue
      got = sha256_file(src)
      ok = got == want
      out["checks"][key] = {"ok": ok, "path": src, "want": want[:12], "got": got[:12]}
      out["stale"] = out["stale"] or not ok
    mjb = self.mjb_path
    if not mjb.exists():
      out["checks"]["mjb"] = {"ok": False, "reason": "missing", "path": str(mjb)}
      out["stale"] = True
    else:
      got = sha256_file(mjb)
      ok = got == self.raw.get("mjb_sha256")
      out["checks"]["mjb"] = {"ok": ok, "path": str(mjb)}
      out["stale"] = out["stale"] or not ok
    return out


def contract_path(cache_dir: str | os.PathLike, variant: str) -> Path:
  return Path(cache_dir) / f"{variant}.model_contract.json"


def mjb_path(cache_dir: str | os.PathLike, variant: str) -> Path:
  return Path(cache_dir) / f"{variant}.mjb"


def load_contract(cache_dir: str | os.PathLike, variant: str) -> ModelContract:
  p = contract_path(cache_dir, variant)
  if not p.exists():
    raise FileNotFoundError(
      f"no baked contract for {variant!r} at {p}. Run:\n"
      f"  mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py bake model --variant {variant}"
    )
  raw = json.loads(p.read_text())
  if raw.get("contract_version") != CONTRACT_VERSION:
    raise ValueError(
      f"{p} is contract_version {raw.get('contract_version')}, this build wants "
      f"{CONTRACT_VERSION}; re-bake."
    )
  c = ModelContract(raw=raw, path=p)
  # The stored sha must match the content, or someone hand-edited the file.
  body = {k: v for k, v in raw.items() if k != "contract_sha"}
  if canonical_sha(body) != raw["contract_sha"]:
    raise ValueError(f"{p}: contract_sha does not match its own content (hand-edited?)")
  return c


def list_baked(cache_dir: str | os.PathLike) -> list[str]:
  d = Path(cache_dir)
  if not d.exists():
    return []
  return sorted(p.name.split(".model_contract.json")[0] for p in d.glob("*.model_contract.json"))
