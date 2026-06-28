# -*- coding: utf-8 -*-
"""Retroactively convert each experiment note's §2b reward CONTRIBUTION LIST into the §2b reward TABLE
(이름 · 가중치 · 기여 · 무엇 · 왜) — the rule (user 2026-06-29). Idempotent: only touches notes that still have
the old bullet list. Weights from each run's params/env.yaml; what/why from reward_glossary.
    python scripts/retro_reward_table.py
"""
import os, re, glob, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from reward_glossary import lookup, parse_reward_weights
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))   # repo root


def build_table(contribs, weights):
    names = sorted(contribs, key=lambda n: -abs(contribs[n]))
    rows = ["| Reward | 가중치 | 기여(final) | 무엇 | 왜 |", "|---|--:|--:|---|---|"]
    for n in names:
        w = weights.get(n)
        what, why = lookup(n)
        wstr = f"{w:+g}" if isinstance(w, (int, float)) else "—"
        rows.append(f"| `{n}` | {wstr} | {contribs[n]:+.4f} | {what} | {why} |")
    return "\n".join(rows)


def main():
    n_up = 0
    for note in sorted(glob.glob(os.path.join(ROOT, "docs", "experiments", "*.md"))):
        txt = open(note).read()
        m = re.search(r"\*\*보상 항목별 기여[^\n]*\*\*:\n((?:- `[A-Za-z_0-9]+`: [-+][\d.]+\n?)+)", txt)
        if not m:
            continue  # already a table, or no §2b list
        contribs = {k: float(v) for k, v in re.findall(r"- `([A-Za-z_0-9]+)`: ([-+][\d.]+)", m.group(1))}
        rm = re.search(r"(pygmalion_locomotion/logs/rsl_rl/\S+?)/model_\d+\.pt", txt)
        weights = parse_reward_weights(os.path.join(ROOT, rm.group(1))) if rm else {}
        table = build_table(contribs, weights)
        new = txt[:m.start()] + table + "\n" + txt[m.end():]
        new = new.replace("## 2b. Reward (무엇을 · 왜)", "## 2b. Reward (이름 · 값 · 무엇 · 왜)")
        open(note, "w").write(new)
        n_up += 1
        nw = sum(1 for n in contribs if n in weights)
        print(f"updated {os.path.basename(note):52s} {len(contribs):2d} terms, {nw:2d} weights"
              + ("" if rm else "  (run dir 미검출 -> 가중치 —)"))
    print(f"\n총 {n_up} 노트 갱신")


if __name__ == "__main__":
    main()
