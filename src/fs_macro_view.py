#!/usr/bin/env python3
"""
fs_macro_view.py - the qualitative FS macro stance log (Issue #10 §3c).

A small, dated, ROLLING record of Fundstrat's macro READ (Lee/Newton in words),
tracked per topic so you see the trajectory + changes:
    "Equities: constructive (since May, confirmed 5/28) - was cautious in Apr"

DELIBERATELY SEPARATE from macro_state.json (the quantitative duration/credit/
dollar/vol read that drives the pretrade_gate MACRO_HEADWIND flag). This log is
ORIENTATION ONLY - it is surfaced at session-open / cockpit / FS Digest and NEVER
feeds the headwind classification. Different kind of information, different home.

Reiteration vs change:
    - same stance on a topic again  -> recorded as a CONFIRMATION (no new noise)
    - different stance               -> a new entry (the change is the signal)

    python fs_macro_view.py --self-test
    python fs_macro_view.py --demo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

CACHE_PATH = Path(__file__).parent / "fs_macro_view.json"   # NOT macro_state.json - see module doc


def load_log(path=CACHE_PATH) -> List[dict]:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else []


def save_log(log: List[dict], path=CACHE_PATH) -> None:
    Path(path).write_text(json.dumps(log, indent=2))


def _latest_for_topic(log: List[dict], topic: str) -> Optional[dict]:
    for entry in reversed(log):
        if entry["topic"] == topic:
            return entry
    return None


def add_stance(log: List[dict], date: str, topic: str, stance: str,
               note: str = "", source: str = "FS") -> List[dict]:
    """Record an FS macro stance. Same stance on a topic = confirmation; change = new entry."""
    topic = topic.strip().lower()
    latest = _latest_for_topic(log, topic)
    if latest and latest["stance"].strip().lower() == stance.strip().lower():
        # reiteration -> confirm, don't duplicate
        latest.setdefault("confirmed", [])
        if date not in latest["confirmed"] and date != latest["date"]:
            latest["confirmed"].append(date)
        if note:
            latest["note"] = note
    else:
        log.append({
            "date": date, "topic": topic, "stance": stance, "note": note,
            "source": source, "confirmed": [],
            "prev_stance": latest["stance"] if latest else None,
        })
    return log


def current_views(log: List[dict]) -> Dict[str, dict]:
    """Latest entry per topic."""
    out: Dict[str, dict] = {}
    for entry in log:
        out[entry["topic"]] = entry
    return out


def recent_changes(log: List[dict], n: int = 3) -> List[dict]:
    """Most recent stance CHANGES (entries that flipped from a prior stance)."""
    changes = [e for e in log if e.get("prev_stance")]
    return changes[-n:][::-1]


def _confirm_str(entry: dict) -> str:
    c = entry.get("confirmed") or []
    return f", confirmed {c[-1]}" if c else ""


def format_view(log: List[dict], max_topics: int = 3, asof: Optional[str] = None) -> str:
    """The compact 1-3 line FS Macro View (current per-topic reads + change markers)."""
    views = current_views(log)
    if not views:
        return "FS Macro View: (none recorded)"
    all_dates = [e["date"] for e in log] + [d for e in log for d in (e.get("confirmed") or [])]
    asof = asof or max(all_dates, default="")
    lines = [f"FS Macro View (as of {asof}):"]
    ordered = sorted(views.values(), key=lambda e: e["date"], reverse=True)[:max_topics]
    for e in ordered:
        was = f" — was {e['prev_stance']} ({e.get('date','')[:7]})" if e.get("prev_stance") else ""
        lines.append(f"  · {e['topic'].capitalize()}: {e['stance']}"
                     f" (since {e['date']}{_confirm_str(e)}){was}"
                     + (f" — {e['note']}" if e.get("note") else ""))
    return "\n".join(lines)


def format_history(log: List[dict]) -> str:
    """The full expandable trajectory (every entry, chronological)."""
    if not log:
        return "FS Macro View history: (empty)"
    lines = ["FS Macro View — full history:"]
    for e in log:
        chg = f"  (was {e['prev_stance']})" if e.get("prev_stance") else ""
        conf = f"  [confirmed {', '.join(e['confirmed'])}]" if e.get("confirmed") else ""
        lines.append(f"  {e['date']}  {e['topic']}: {e['stance']}{chg}{conf}"
                     + (f" — {e['note']}" if e.get("note") else ""))
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _self_test() -> bool:
    passed = failed = 0

    def check(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    log: List[dict] = []
    add_stance(log, "2026-04-10", "duration", "cautious", source="Newton")
    check("new topic adds entry", len(log) == 1)

    add_stance(log, "2026-05-05", "equities", "cautious", source="Lee")
    add_stance(log, "2026-05-20", "equities", "constructive", note="growth scare fading", source="Lee")
    check("changed stance adds new entry", len(log) == 3)
    check("change records prev_stance", log[-1]["prev_stance"] == "cautious")

    add_stance(log, "2026-05-28", "equities", "constructive", source="Lee")  # reiteration
    check("reiteration does NOT add entry", len(log) == 3)
    check("reiteration appends confirmed date", "2026-05-28" in log[-1]["confirmed"])

    views = current_views(log)
    check("current_views has 2 topics", set(views.keys()) == {"duration", "equities"})
    check("equities current = constructive", views["equities"]["stance"] == "constructive")

    changes = recent_changes(log, n=3)
    check("recent_changes finds the equities flip", any(c["topic"] == "equities" for c in changes))
    check("recent_changes excludes confirmations", all(c.get("prev_stance") for c in changes))

    out = format_view(log)
    check("format_view header has as-of", "FS Macro View (as of" in out)
    check("format_view shows constructive", "constructive" in out)
    check("format_view shows the change (was cautious)", "was cautious" in out)
    check("format_view shows confirmed date", "confirmed 2026-05-28" in out)

    hist = format_history(log)
    check("history lists all entries", hist.count("\n") >= 3)

    # separation guard: this module writes its OWN cache, never macro_state.json
    check("cache path is fs_macro_view.json", CACHE_PATH.name == "fs_macro_view.json")
    check("cache path is NOT macro_state.json", CACHE_PATH.name != "macro_state.json")

    print(f"\n{passed}/{passed + failed} assertions passed.")
    return failed == 0


def _demo() -> None:
    log: List[dict] = []
    add_stance(log, "2026-04-10", "duration", "cautious", note="sticky inflation", source="Newton")
    add_stance(log, "2026-04-15", "equities", "cautious", source="Lee")
    add_stance(log, "2026-05-20", "equities", "constructive", note="growth scare fading", source="Lee")
    add_stance(log, "2026-05-28", "equities", "constructive", source="Lee")
    print(format_view(log))
    print()
    print(format_history(log))


def main() -> int:
    ap = argparse.ArgumentParser(description="FS Macro View - qualitative rolling stance log (3c).")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return 0 if _self_test() else 1
    if args.demo:
        _demo()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
