#!/usr/bin/env python3
"""
conviction_stack.py - the additive-conviction / urgency engine (Investing 2026).

WHAT THIS IS
    A per-NAME conviction + urgency layer. Every ticker the system tracks
    (held, watchlist, prospect, Top-5 candidate) accumulates SIGNAL EVENTS over
    time - one each time a source flags it. As INDEPENDENT signals stack,
    especially when they cluster in time, conviction rises and an urgency level
    escalates so the name gets surfaced before the window closes.

    It NEVER trades. It escalates a SURFACED flag; the operator makes the call.

THE TWO STACKING RULES (operator-set 2026-06-03)
    1. A signal stacks at FULL weight when it brings a NEW source OR a NEW
       category to the name (independent confirmation - the strongest).
    2. A SAME source repeating the SAME category over time still stacks, but at
       reduced weight - a flat reiteration adds a little (decay); a SUBSTANTIVE
       strengthening (new info / stronger language / "moves expected soon")
       adds more. Diminishing, never ignored.

WEIGHTS ARE TUNABLE
    STACK_WEIGHTS below is the starting scaffold - every number is a knob we
    adjust as we learn. Load overrides from JSON via load_weights(path), or pass
    a `weights=` dict to compute_stack(). The deterministic base lets the cloud
    routines compute a score mechanically; in-session (FS Digest / cockpit) a
    per-event judgment multiplier (SignalEvent.judgment_mult) lets Claude weight
    by substance - e.g. bump a note that clearly flags an imminent move. Time-
    clustering is kept deliberately simple (one recency window + one cluster
    bonus), NOT an elaborate decay curve - judgment carries the nuance.

USAGE
    from conviction_stack import SignalEvent, compute_stack, rank_stacks
    events = [SignalEvent("ANET", "FS-Monthly", "analyst_named", "2026-05-01"),
              SignalEvent("ANET", "Newton", "technical", "2026-06-08", strength="strong")]
    r = compute_stack(events, now="2026-06-09")
    # r.conviction_level -> "HOT", r.urgency_level -> "HOT", r.summary -> "..."

    python conviction_stack.py --self-test
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

# ----------------------------------------------------------------------------
# TUNABLE CONFIG - every value here is a knob we adjust as we learn.
# ----------------------------------------------------------------------------
STACK_WEIGHTS: Dict[str, object] = {
    # Base points per signal category: (conviction_points, urgency_points).
    # Working set; reconcile with the Two-Lens 8 categories over time.
    "category_base": {
        "analyst_named":  (10, 6),   # named BUY/pick from Lee / FS monthly
        "technical":      (6, 10),   # Newton technicals (timing-heavy -> high urgency)
        "crypto_read":    (7, 8),    # Farrell broad-crypto stance (BTC/ETH/alts)
        "flow":           (5, 6),    # unusual options flow
        "dark_pool":      (4, 4),    # dark-pool block accumulation
        "insider":        (6, 5),    # open-market insider buying
        "institutional":  (5, 3),    # 13F / institutional add
        "macro":          (3, 3),    # macro / sector tailwind
        "catalyst":       (4, 9),    # dated catalyst approaching (timing-heavy)
        "social":         (2, 3),    # social / sentiment (weakest)
        "our_research":   (5, 2),    # our own corroborating vet
        "watchlist_base": (2, 0),    # baseline: already on the watchlist (no urgency)
    },
    "strength_mult": {"weak": 0.5, "moderate": 1.0, "strong": 1.5},
    "repeat_decay": 0.35,               # same (source,category) flat reiteration -> this fraction
    "substantive_repeat_factor": 0.7,   # ...but a strengthening repeat keeps more
    "urgency_recency_days": 21,         # urgency counts only signals this recent; conviction counts all
    "cluster_window_days": 10,          # >=2 INDEPENDENT signals this close -> bonus
    "cluster_bonus": 8,
    "conviction_levels": {"BUILDING": 8, "HOT": 18, "ACT_NOW": 30},
    "urgency_levels":    {"BUILDING": 8, "HOT": 16, "ACT_NOW": 26},
}

LEVELS_ORDER = ["QUIET", "BUILDING", "HOT", "ACT_NOW"]


# ----------------------------------------------------------------------------
# Data shapes
# ----------------------------------------------------------------------------
@dataclass
class SignalEvent:
    ticker: str
    source: str                  # "Newton","Lee","Farrell","FS-Monthly","Granny","Insider",...
    category: str                # key into category_base
    date: str                    # ISO "YYYY-MM-DD"
    direction: str = "long"      # "long" | "avoid"
    strength: str = "moderate"   # "weak" | "moderate" | "strong"
    substantive: bool = False    # True if a same-source repeat brings new info / strengthens
    judgment_mult: float = 1.0   # in-session judgment knob (bump for imminence/substance)
    note: str = ""

    def day(self) -> Optional[date]:
        return _parse_day(self.date)


@dataclass
class DirectionResult:
    conviction: float
    urgency: float
    conviction_level: str
    urgency_level: str
    counted: List[Dict]          # per-event breakdown (independent vs decayed, points)


@dataclass
class StackResult:
    ticker: str
    direction: str               # net dominant: "long" | "avoid" | "none"
    conviction: float
    urgency: float
    conviction_level: str
    urgency_level: str
    long: DirectionResult
    avoid: DirectionResult
    summary: str


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _parse_day(s) -> Optional[date]:
    if not s:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _level(score: float, thresholds: Dict[str, float]) -> str:
    lvl = "QUIET"
    for name in ("BUILDING", "HOT", "ACT_NOW"):
        if score >= thresholds[name]:
            lvl = name
    return lvl


def load_weights(path) -> Dict[str, object]:
    """Load a weights JSON and merge over the defaults (shallow per top-level key)."""
    override = json.loads(Path(path).read_text())
    merged: Dict[str, object] = dict(STACK_WEIGHTS)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}  # type: ignore[dict-item]
        else:
            merged[k] = v
    return merged


# ----------------------------------------------------------------------------
# Core
# ----------------------------------------------------------------------------
def _compute_direction(events: List[SignalEvent], now: date,
                       w: Dict[str, object]) -> DirectionResult:
    base = w["category_base"]               # type: ignore[index]
    smult = w["strength_mult"]              # type: ignore[index]
    decay = w["repeat_decay"]
    subfac = w["substantive_repeat_factor"]
    recency = w["urgency_recency_days"]
    cluster_window = w["cluster_window_days"]
    cluster_bonus = w["cluster_bonus"]

    seen_pairs = set()                      # (source, category) already counted
    conviction = 0.0
    urgency = 0.0
    counted: List[Dict] = []
    recent_independent_days: List[date] = []

    # Sort by date so the FIRST of any (source,category) is the earliest one.
    ordered = sorted(events, key=lambda e: (e.day() or date.min))
    for e in ordered:
        cb, ub = base.get(e.category, (0, 0))   # type: ignore[union-attr]
        sm = smult.get(e.strength, 1.0)         # type: ignore[union-attr]
        pair = (e.source, e.category)
        independent = pair not in seen_pairs
        if independent:
            rep_factor = 1.0
            seen_pairs.add(pair)
        else:
            rep_factor = subfac if e.substantive else decay
        jm = e.judgment_mult if (e.judgment_mult and e.judgment_mult > 0) else 1.0

        c_pts = cb * sm * rep_factor * jm
        u_pts = ub * sm * rep_factor * jm
        conviction += c_pts

        d = e.day()
        within = d is not None and 0 <= (now - d).days <= recency
        if within:
            urgency += u_pts
            if independent:
                recent_independent_days.append(d)

        counted.append({
            "source": e.source, "category": e.category, "date": e.date,
            "independent": independent, "repeat_factor": round(rep_factor, 3),
            "conviction_pts": round(c_pts, 2), "urgency_pts": round(u_pts, 2),
            "counted_for_urgency": within,
        })

    # Clustering: >=2 INDEPENDENT signals within cluster_window days of each other.
    recent_independent_days.sort()
    clustered = any(
        (recent_independent_days[j] - recent_independent_days[i]).days <= cluster_window
        for i in range(len(recent_independent_days))
        for j in range(i + 1, len(recent_independent_days))
    )
    if clustered:
        urgency += cluster_bonus

    return DirectionResult(
        conviction=round(conviction, 2),
        urgency=round(urgency, 2),
        conviction_level=_level(conviction, w["conviction_levels"]),   # type: ignore[arg-type]
        urgency_level=_level(urgency, w["urgency_levels"]),            # type: ignore[arg-type]
        counted=counted,
    )


def compute_stack(events: List[SignalEvent], now=None,
                  weights: Optional[Dict[str, object]] = None) -> StackResult:
    """Compute the conviction + urgency stack for ONE name (all events share a ticker)."""
    w = weights or STACK_WEIGHTS
    now_d = _parse_day(now) or date.today()
    ticker = events[0].ticker if events else ""

    long_r = _compute_direction([e for e in events if e.direction == "long"], now_d, w)
    avoid_r = _compute_direction([e for e in events if e.direction == "avoid"], now_d, w)

    if long_r.conviction == 0 and avoid_r.conviction == 0:
        direction, conv, urg, cl, ul = "none", 0.0, 0.0, "QUIET", "QUIET"
    elif avoid_r.conviction > long_r.conviction:
        direction = "avoid"
        conv, urg, cl, ul = (avoid_r.conviction, avoid_r.urgency,
                             avoid_r.conviction_level, avoid_r.urgency_level)
    else:
        direction = "long"
        conv, urg, cl, ul = (long_r.conviction, long_r.urgency,
                             long_r.conviction_level, long_r.urgency_level)

    return StackResult(ticker=ticker, direction=direction, conviction=conv, urgency=urg,
                       conviction_level=cl, urgency_level=ul, long=long_r, avoid=avoid_r,
                       summary=_summary(ticker, direction, cl, ul, long_r, avoid_r))


def _summary(ticker, direction, cl, ul, long_r, avoid_r) -> str:
    if direction == "none":
        return f"{ticker}: QUIET - no active signals."
    if direction == "avoid":
        n = len([c for c in avoid_r.counted if c["independent"]])
        return (f"{ticker}: SELL-PRESSURE {cl} / urgency {ul} "
                f"({n} independent avoid signal{'s' if n != 1 else ''}).")
    n = len([c for c in long_r.counted if c["independent"]])
    return (f"{ticker}: conviction {cl} / urgency {ul} "
            f"({n} independent signal{'s' if n != 1 else ''} stacked).")


def rank_stacks(events: List[SignalEvent], now=None,
                weights: Optional[Dict[str, object]] = None) -> List[StackResult]:
    """Group a flat event list by ticker, compute each stack, sort hottest-first.

    This is the feed for the cockpit Prospects lane: urgency desc, then conviction desc.
    """
    by_ticker: Dict[str, List[SignalEvent]] = {}
    for e in events:
        by_ticker.setdefault(e.ticker, []).append(e)
    results = [compute_stack(evs, now=now, weights=weights) for evs in by_ticker.values()]
    return sorted(results, key=lambda r: (-r.urgency, -r.conviction, r.ticker))


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _self_test() -> bool:
    passed = 0
    failed = 0

    def check(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    NOW = "2026-06-09"

    # 1. Empty -> QUIET / none
    r = compute_stack([], now=NOW)
    check("empty -> QUIET/none", r.direction == "none" and r.conviction_level == "QUIET")

    # 2. Single analyst_named (moderate) -> conviction 10, BUILDING
    r = compute_stack([SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-06-05")], now=NOW)
    check("single analyst_named conviction==10", r.conviction == 10)
    check("single analyst_named level BUILDING", r.conviction_level == "BUILDING")

    # 3. Same (source,category) flat repeat -> +10*0.35=3.5 -> 13.5
    r = compute_stack([
        SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-05-01"),
        SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-06-01"),
    ], now=NOW)
    check("flat same-source repeat decays (13.5)", r.conviction == 13.5)

    # 4. Substantive repeat -> +10*0.7=7 -> 17.0
    r = compute_stack([
        SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-05-01"),
        SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-06-01", substantive=True),
    ], now=NOW)
    check("substantive repeat keeps more (17.0)", r.conviction == 17.0)

    # 5. Different source, same category -> full (10+10=20) -> HOT
    r = compute_stack([
        SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-06-01"),
        SignalEvent("AAA", "Lee", "analyst_named", "2026-06-03"),
    ], now=NOW)
    check("different source = independent (20.0)", r.conviction == 20.0)
    check("two independent -> HOT", r.conviction_level == "HOT")

    # 6. Strong technical -> conviction 6*1.5=9, urgency 10*1.5=15 (recent)
    r = compute_stack([SignalEvent("AAA", "Newton", "technical", "2026-06-08", strength="strong")], now=NOW)
    check("strong technical conviction==9", r.conviction == 9)
    check("strong technical urgency==15", r.urgency == 15)

    # 7. Recency: an OLD signal adds conviction but 0 urgency
    r = compute_stack([SignalEvent("AAA", "Newton", "technical", "2026-04-01", strength="strong")], now=NOW)
    check("old signal conviction==9", r.conviction == 9)
    check("old signal urgency==0 (outside window)", r.urgency == 0)

    # 8. Clustering: 2 independent recent signals within 10d -> urgency +8 bonus
    r = compute_stack([
        SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-06-01"),   # urg 6
        SignalEvent("AAA", "Lee", "analyst_named", "2026-06-05"),          # urg 6, indep
    ], now="2026-06-06")
    check("clustering bonus applied (urgency==20)", r.urgency == 20)

    # 9. Avoid dominates -> direction avoid, SELL-PRESSURE summary
    r = compute_stack([
        SignalEvent("AAA", "FS-Monthly", "analyst_named", "2026-06-05", direction="avoid"),
        SignalEvent("AAA", "Lee", "analyst_named", "2026-06-06", direction="avoid"),
    ], now=NOW)
    check("avoid direction wins", r.direction == "avoid")
    check("avoid summary says SELL-PRESSURE", "SELL-PRESSURE" in r.summary)

    # 10. Judgment multiplier doubles that event's points
    r = compute_stack([
        SignalEvent("AAA", "Newton", "technical", "2026-06-08", strength="strong", judgment_mult=2.0)
    ], now=NOW)
    check("judgment_mult doubles conviction (18)", r.conviction == 18)
    check("judgment_mult doubles urgency (30 -> ACT_NOW)", r.urgency == 30 and r.urgency_level == "ACT_NOW")

    # 11. load_weights merges override
    p = Path("/tmp/_stack_w.json")
    p.write_text(json.dumps({"repeat_decay": 0.5}))
    w = load_weights(p)
    check("load_weights overrides repeat_decay", w["repeat_decay"] == 0.5)
    check("load_weights keeps other defaults", w["cluster_bonus"] == 8)

    # 12. Level thresholds map at boundaries
    check("level boundary QUIET", _level(7.9, STACK_WEIGHTS["conviction_levels"]) == "QUIET")     # type: ignore[arg-type]
    check("level boundary BUILDING", _level(8, STACK_WEIGHTS["conviction_levels"]) == "BUILDING")  # type: ignore[arg-type]
    check("level boundary ACT_NOW", _level(30, STACK_WEIGHTS["conviction_levels"]) == "ACT_NOW")   # type: ignore[arg-type]

    # 13. rank_stacks sorts hottest-first
    evs = [
        SignalEvent("LOW", "FS-Monthly", "analyst_named", "2026-06-05"),
        SignalEvent("HOT", "Newton", "technical", "2026-06-08", strength="strong"),
        SignalEvent("HOT", "Lee", "analyst_named", "2026-06-07"),
    ]
    ranked = rank_stacks(evs, now=NOW)
    check("rank_stacks hottest first", ranked[0].ticker == "HOT")

    print(f"\n{passed}/{passed + failed} assertions passed.")
    return failed == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Conviction-Stack engine (additive conviction + urgency).")
    ap.add_argument("--self-test", action="store_true", help="Run the self-test suite.")
    args = ap.parse_args()
    if args.self_test:
        return 0 if _self_test() else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
