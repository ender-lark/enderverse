#!/usr/bin/env python3
"""
options_shadow_log.py — the "learn from the misses" ledger for options surfacing.

Wide-net-then-filter only teaches us something if we WRITE DOWN what we filtered out.
Every conviction name that passed the conviction gate but did NOT become an ACT
(WATCH / WAIT / SKIP) is appended here with the reason it was held back. Later we fill in
what the name actually did (forward return); the names we filtered that THEN RIPPED are the
signal that a dial is too tight. This is how the thresholds get tuned from REAL missed
opportunities instead of by guesswork — the operator's explicit ask, and the antidote to
"no bright lines."

Append-only JSONL, tolerant (a malformed line never breaks a read). No network; pure file IO.
Pairs with options_expression.build_expression() output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

DEFAULT_PATH = Path(__file__).resolve().parent / "options_shadow_log.jsonl"


def rejection_row(result: dict, *, as_of: Optional[str] = None) -> Optional[dict]:
    """A near-miss/hold row for the ledger, or None if this result was an ACT (acted ideas
    are tracked by the normal outcome logger, not the shadow log)."""
    if not isinstance(result, dict):
        return None
    if result.get("disposition") == "ACT":
        return None
    return {
        "as_of": as_of or result.get("as_of"),
        "ticker": result.get("ticker"),
        "disposition": result.get("disposition"),
        "filter_reason": result.get("filter_reason") or result.get("the_catch"),
        "structure": result.get("structure"),
        "iv_environment": result.get("iv_environment"),
        "break_even_pct": result.get("break_even_pct"),
        "outcome": None,  # forward return, filled later by record_outcome()
    }


def append_rejections(results, *, path: Path | str = DEFAULT_PATH, as_of: Optional[str] = None) -> int:
    """Append every near-miss/hold from a build_expression() batch. Returns count written."""
    rows = [r for r in (rejection_row(x, as_of=as_of) for x in (results or [])) if r]
    if not rows:
        return 0
    with Path(path).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return len(rows)


def load_log(path: Path | str = DEFAULT_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def open_misses(path: Path | str = DEFAULT_PATH) -> list[dict]:
    """Rows still awaiting a forward-return outcome — the 'did we wrongly filter it?' worklist
    that later turns into 'this dial is too tight, loosen it'."""
    return [r for r in load_log(path) if r.get("outcome") is None]


def _self_test() -> int:
    import tempfile
    fails: list[str] = []
    results = [
        {"ticker": "A", "disposition": "ACT", "as_of": "2026-06-18"},
        {"ticker": "B", "disposition": "WAIT", "filter_reason": "IV tax", "as_of": "2026-06-18"},
        {"ticker": "C", "disposition": "SKIP", "filter_reason": "illiquid", "as_of": "2026-06-18"},
    ]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "log.jsonl"
        n = append_rejections(results, path=p)
        if n != 2:
            fails.append(f"appended {n}, expected 2 (ACT excluded)")
        if len(load_log(p)) != 2:
            fails.append("load_log count != 2")
        if len(open_misses(p)) != 2:
            fails.append("open_misses != 2")
        if append_rejections([{"ticker": "A", "disposition": "ACT"}], path=p) != 0:
            fails.append("ACT-only batch should append 0")
    if fails:
        print("options_shadow_log self-test: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("options_shadow_log self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
