"""Conviction engine â€” weighted evidence â†’ capped independence groups â†’ read.

The unified conviction read for a name. Pieces existed across V2 (fundstrat
lane metadata, UW endpoint interpretation, source-call tiers); this engine is
where they finally SUM â€” with independence discipline:

* **Item weight** = ``tier_base[A/B/C/D] Ã— calibration multiplier Ã— freshness
  decay``. Tiers per the canonical 4-tier call ladder (P-SOURCE-CALIBRATION).
  Tier D ("should/favor" narrative) is track-only and NEVER scores â€” enforced
  here and in the tunables guard. Undated items cannot decay-score and are
  track-only (honesty over guesswork).
* **Calibration** = hit-rate bands per sourceÃ—tier once ``min_n`` scored calls
  exist; absent/insufficient history â†’ INSUFFICIENT_DATA 1.0Ã— (earned weight,
  never asserted).
* **Groups** (items cap inside, groups sum across): ``fs`` (all Fundstrat
  authors â€” one cluster), ``uw`` (V2 interpretation semantics verbatim:
  supports=+1, full battery=1.25, single-day flowâ‰¤0.5 pending OI confirm,
  inconclusive=0 because a fetch is not a direction, contradicts=âˆ’1 AND forces
  re-check), ``operator_insight`` (register hook 2 â€” max, never sum),
  ``institutional`` (honest not-checked stub until the 13F/insider wiring
  chunk).
* **Read**: HIGH/MODERATE/LOW from weighted points vs ``signals_high_min`` /
  ``signals_mod_min`` (operator tunables; starting points for the learning
  loop). Cross-group convergence is the only path up â€” same-group repetition
  is capped away. Every read ships with "what would raise this" and explicit
  ``not_checked`` lanes.

Pure functions; I/O only in the small adapters at the bottom.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from insight_register import conviction_points as _insight_points
from insight_register import match as _insight_match

SRC = Path(__file__).resolve().parent
SOURCE_CALLS_PATH = SRC / "source_calls.json"
TOP_PROSPECTS_PATH = SRC / "top_prospects.json"
FEED_PATH = SRC / "latest_cockpit_feed.json"

GROUPS = ("fs", "uw", "operator_insight", "institutional")
TIERS = ("A", "B", "C", "D")
_FS_SOURCES = {"fundstrat", "newton", "lee", "farrell", "tlee", "mark newton", "tom lee"}

def _today(today: str | date | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(str(today), "%Y-%m-%d").date()

# ---------------------------------------------------------------------------
# Calibration â€” earned multipliers, honest when history is thin
# ---------------------------------------------------------------------------
def calibration_multiplier(
    source: str, tier: str, rates: dict[str, Any] | None, weights: dict[str, Any]
) -> tuple[float, str]:
    bands = weights["calibration_bands"]
    mults = bands["multipliers"]
    row = ((rates or {}).get(str(source).lower()) or {}).get(tier)
    if not isinstance(row, dict):
        return float(mults["INSUFFICIENT_DATA"]), "INSUFFICIENT_DATA"
    n = row.get("n", 0)
    rate = row.get("win_rate")
    if not isinstance(n, (int, float)) or n < bands["min_n"] or not isinstance(rate, (int, float)):
        return float(mults["INSUFFICIENT_DATA"]), "INSUFFICIENT_DATA"
    if rate <= bands["consistent_miss_max"]:
        return float(mults["CONSISTENT_MISS"]), "CONSISTENT_MISS"
    if rate <= bands["below_breakeven_max"]:
        return float(mults["BELOW_BREAKEVEN"]), "BELOW_BREAKEVEN"
    if rate <= bands["normal_max"]:
        return float(mults["NORMAL"]), "NORMAL"
    return float(mults["HIGH_CONVICTION"]), "HIGH_CONVICTION"

# ---------------------------------------------------------------------------
# Item scoring â€” tier Ã— calibration Ã— freshness decay
# ---------------------------------------------------------------------------
def score_item(
    item: dict[str, Any],
    *,
    weights: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    now = _today(today)
    tier = item.get("tier")
    source = str(item.get("source") or "unknown")
    direction = str(item.get("direction") or "bullish").lower()
    sign = -1.0 if direction in ("bearish", "short", "sell", "sell_fast", "avoid") else 1.0

    out: dict[str, Any] = {
        "source": source,
        "tier": tier,
        "note": str(item.get("note") or "")[:160],
        "date": item.get("date"),
        "direction": "bearish" if sign < 0 else "bullish",
        "kind": item.get("kind", "call"),
    }

    if tier not in TIERS or tier == "D":
        out.update(weight=0.0, track_only=True, expired=False, fresh=0.0,
                   reason="Tier D / unknown tier â€” track-only by doctrine, never scores")
        return out

    raw_date = item.get("date")
    try:
        item_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        out.update(weight=0.0, track_only=True, expired=False, fresh=0.0,
                   reason="undated item cannot decay-score â€” track-only")
        return out

    window = int(weights["tier_window_days"].get(tier, 0))
    age = (now - item_date).days
    if age < 0:
        age = 0
    fresh = max(0.0, 1.0 - (age / window)) if window > 0 else 0.0
    expired = age > window
    base = float(weights["tier_base"][tier])
    mult, band = calibration_multiplier(source, tier, rates, weights)
    weight = 0.0 if expired else sign * base * mult * fresh
    out.update(
        weight=round(weight, 4), base=base, calibration=mult, calibration_band=band,
        fresh=round(fresh, 3), age_days=age, window_days=window,
        expired=expired, track_only=False,
    )
    return out

def _signed_capped_sum(scored: list[dict[str, Any]], cap: float) -> dict[str, Any]:
    live = [s for s in scored if not s.get("track_only") and not s.get("expired")]
    raw = sum(s["weight"] for s in live)
    points = max(-cap, min(cap, raw))
    return {
        "points": round(points, 3),
        "raw": round(raw, 3),
        "capped": abs(raw) > abs(points) + 1e-9,
        "items": scored,
        "n_live": len(live),
    }

def fs_group(
    items: list[dict[str, Any]],
    *,
    weights: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    scored = [score_item(i, weights=weights, rates=rates, today=today) for i in items]
    return _signed_capped_sum(scored, float(weights["group_caps"]["fs"]))

def uw_group(uw_state: dict[str, Any] | None, *, weights: dict[str, Any]) -> dict[str, Any]:
    """V2 endpoint-interpretation semantics, verbatim."""
    pts_map = weights["uw_points"]
    cap = float(weights["group_caps"]["uw"])
    state = uw_state or {}
    interp = state.get("interpretation")
    note = state.get("note") or ""
    force_recheck = False
    if interp == "supports":
        pts = float(pts_map["battery_full"]) if state.get("battery_complete") else float(pts_map["supports"])
        why = "same-session UW evidence SUPPORTS" + (" (full multi-day battery)" if state.get("battery_complete") else "")
    elif interp == "contradicts":
        pts = float(pts_map["contradicts"])
        force_recheck = True
        why = "same-session UW evidence CONTRADICTS â€” re-check forced"
    elif interp == "inconclusive":
        pts = 0.0
        why = "UW proof inconclusive â€” a successful fetch is not a direction"
    elif state.get("single_day_flow"):
        pts = float(pts_map["single_day_flow_max"])
        why = "single-day directional flow only â€” unconfirmed until next-morning OI"
    else:
        pts = 0.0
        why = "no same-session UW proof captured"
    return {
        "points": round(max(-cap, min(cap, pts)), 3),
        "why": why + (f" â€” {note}" if note else ""),
        "interpretation": interp,
        "single_day_flow": bool(state.get("single_day_flow")),
        "battery_complete": bool(state.get("battery_complete")),
        "force_recheck": force_recheck,
        "date": state.get("date"),
    }

def institutional_group(
    inst_state: dict[str, Any] | None, *, weights: dict[str, Any]
) -> dict[str, Any]:
    cap = float(weights["group_caps"]["institutional"])
    if not inst_state:
        return {
            "points": 0.0,
            "status": "not_checked",
            "why": "13F/insider scans not wired into the feed yet (orphan-wiring chunk) â€” not checked â‰  no signal",
        }
    pts = float(inst_state.get("points", 0.0))
    return {
        "points": round(max(-cap, min(cap, pts)), 3),
        "status": inst_state.get("status", "ok"),
        "why": inst_state.get("why", ""),
    }

# ---------------------------------------------------------------------------
# The unified read
# ---------------------------------------------------------------------------
def conviction(
    ticker: str,
    *,
    fs_items: list[dict[str, Any]] | None = None,
    uw_state: dict[str, Any] | None = None,
    insight_payload: dict[str, Any] | None = None,
    inst_state: dict[str, Any] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    tick = ticker.upper()
    fs = fs_group(fs_items or [], weights=weights, rates=rates, today=today)
    uw = uw_group(uw_state, weights=weights)
    matches = _insight_match(insight_payload, ticker=tick, today=today) if insight_payload else []
    op = _insight_points(matches, weights)
    inst = institutional_group(inst_state, weights=weights)

    groups = {
        "fs": fs["points"],
        "uw": uw["points"],
        "operator_insight": round(op["points"], 3),
        "institutional": inst["points"],
    }
    total = round(sum(groups.values()), 3)
    n_groups = sum(1 for v in groups.values() if v > 0)

    high_min = float(goal["signals_high_min"])
    mod_min = float(goal["signals_mod_min"])
    read = "HIGH" if total >= high_min else "MODERATE" if total >= mod_min else "LOW"

    contradictions: list[str] = []
    for s in fs["items"]:
        if s.get("direction") == "bearish" and not s.get("track_only") and not s.get("expired"):
            contradictions.append(f"{s['source']} bearish ({s['tier']}): {s['note']}")
    if uw["force_recheck"]:
        contradictions.append(uw["why"])

    not_checked: list[str] = []
    if inst.get("status") == "not_checked":
        not_checked.append("institutional")
    if uw["points"] == 0 and not uw["interpretation"] and not uw["single_day_flow"]:
        not_checked.append("uw_same_session")

    raises: list[str] = []
    fs_cap = float(weights["group_caps"]["fs"])
    live_tiers = {s["tier"] for s in fs["items"] if not s.get("track_only") and not s.get("expired")}
    if fs["points"] < fs_cap and "A" not in live_tiers:
        raises.append(
            f"A dated entry/stop/target call (Tier A) on {tick}"
            + (" â€” a Tier B exists; A upgrades it" if "B" in live_tiers else "")
        )
    if "uw_same_session" in not_checked:
        raises.append("Same-session UW proof interpreted 'supports' (9:40 ET gate runs it)")
    elif uw["single_day_flow"] and not uw["interpretation"]:
        raises.append("Next-morning OI confirmation of the flow (battery completes â†’ 1.25)")
    if groups["operator_insight"] == 0:
        raises.append(f"No ACTIVE insight maps {tick} â€” state the thesis as one if you believe it")
    if "institutional" in not_checked:
        raises.append("13F/insider lane goes live in the orphan-wiring chunk")

    return {
        "ticker": tick,
        "points": total,
        "read": read,
        "n_groups": n_groups,
        "thresholds": {"high": high_min, "moderate": mod_min},
        "groups": groups,
        "group_detail": {"fs": fs, "uw": uw, "operator_insight": op, "institutional": inst},
        "contradictions": contradictions,
        "force_recheck": uw["force_recheck"],
        "raises": raises,
        "not_checked": not_checked,
        "computed_at": _today(today).isoformat(),
    }

# ---------------------------------------------------------------------------
# Adapters (defensive I/O over existing V2 caches)
# ---------------------------------------------------------------------------
def load_source_calls(path: Path | str = SOURCE_CALLS_PATH) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except json.JSONDecodeError:
        return []

def fs_items_from_source_calls(
    ticker: str, calls: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    calls = load_source_calls() if calls is None else calls
    tick = ticker.upper()
    items: list[dict[str, Any]] = []
    for row in calls:
        if str(row.get("ticker") or "").upper() != tick:
            continue
        if str(row.get("source") or "").lower() not in _FS_SOURCES:
            continue
        items.append(
            {
                "group": "fs",
                "source": str(row.get("source")).lower(),
                "tier": row.get("tier"),
                "date": row.get("date"),
                "direction": row.get("direction", "bullish"),
                "note": row.get("verbatim_quote") or row.get("note") or "",
                "kind": "source_call",
            }
        )
    return items

def fs_membership_item(
    ticker: str, prospects: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Monthly-list membership = Tier-C thesis context (never an execution trigger)."""
    if prospects is None:
        path = TOP_PROSPECTS_PATH
        if not path.exists():
            return None
        try:
            prospects = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    row = (prospects or {}).get(ticker.upper())
    if not isinstance(row, dict):
        return None
    direction = str(row.get("direction") or "long").lower()
    return {
        "group": "fs",
        "source": "fundstrat",
        "tier": "C",
        "date": row.get("add_date"),
        "direction": "bearish" if direction in ("short", "sell", "sell_fast", "avoid") else "bullish",
        "note": f"monthly list membership ({row.get('conviction', 'listed')})",
        "kind": "monthly_membership",
    }

def uw_state_from_feed(ticker: str, feed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pull same-session interpretation for a ticker from the feed's UW proof
    section if present; honest empty state otherwise."""
    if feed is None:
        try:
            feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    proof = feed.get("uw_endpoint_result_proof") or {}
    rows = proof.get("rows") if isinstance(proof, dict) else proof
    tick = ticker.upper()
    best: dict[str, Any] = {}
    for row in rows or []:
        if str(row.get("ticker") or "").upper() != tick:
            continue
        interp = row.get("decision_interpretation") or row.get("interpretation")
        if interp in ("supports", "contradicts", "inconclusive"):
            best = {
                "interpretation": interp,
                "note": row.get("note") or row.get("check") or "",
                "date": row.get("date") or row.get("captured_at"),
                "battery_complete": bool(row.get("battery_complete")),
            }
            if interp == "contradicts":
                break
    return best
