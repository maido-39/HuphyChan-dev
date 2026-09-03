"""P3 SKELETON - streaming jsonl.gz recorder and replayer.

Planned shape:
  * one header line: {"v":1, "contract_hash":..., "variant":..., "base":{mode,height,ground,
    pivot_offset}, "gains_source":..., "env_toggles":..., "started_utc":...}
  * then one line per message, exactly the wire objects from ``schema.py``.
  * append-and-flush, never an in-memory list: a 10 s recording must not move RSS.
  * ``Replayer`` supports seek and a speed multiplier, and REFUSES to overlay two recordings
    whose ``contract_hash`` differ unless the caller passes an explicit override.
"""

from __future__ import annotations


class Recorder:  # TODO(P3)
  def __init__(self, *_a, **_k):
    raise NotImplementedError("Recorder is P3 - see docs/121 section 6")


class Replayer:  # TODO(P3)
  def __init__(self, *_a, **_k):
    raise NotImplementedError("Replayer is P3 - see docs/121 section 6")
