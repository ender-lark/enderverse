"""Congruence â€” does the money match the beliefs? (Insight hook 4)

Pure exposure math per ACTIVE insight against the live book, with honest
empty-states when no positions cache is available. The signature output is
one row per insight: named exposure (tickers_mapped held), adjacent exposure,
watch-class holdings, and the **strongest-belief / smallest-exposure flag**.

Binding guardrail: the flag *informs once* â€” it never forces a trade, never
nags, and never creates urgency. High conviction with no named window is
WATCH posture by mandate.

Book sources, in preference order:
1. ``latest_cockpit_feed.json`` â†’ ``portfolio_views.views.combined`` (the
   validated, rendered truth at feed-build time).
2. ``account_positions.json`` â†’ ``combined_positions`` (SnapTrade cache).
3. Neither readable â†’ ``{"status": "not_checked", ...}`` â€” never zeros-as-data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from insight_register import active_insights

SRC = Path(__file__).resolve().parent
FEED_PATH = SRC / "latest_cockpit_feed.json"
ACCOUNT_POSITIONS_PATH = SRC / "account_positions.json"

class CongruenceMissingError(Exception):
    pass

# ---------------------------------------------------------------------------
# Book loaders (I/O lives here; the math below is pure)
# ---------------------------------------------------------------------------
def load_book_from_feed(path: Path | str = FEED_PATH) -> tuple[dict[str, float], float]:
    path = Path(path)
    if not path.exists():
        raise CongruenceMissingError(f"{path.name} absent")
    try:
        feed = json.loads(path.read_text(encoding="utf-8"))
        combined = feed["portfolio_views"]["views"]["combined"]
        rows = combined["rows"]
        total = float(combined["total_value"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CongruenceMissingError(f"{path.name} unreadable for book: {exc}") from exc
    ticker_values: dict[str, float] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        value = row.get("market_value")
        if ticker and isinstance(value, (int, float)):
            ticker_values[ticker] = ticker_values.get(ticker, 0.0) + float(value)
    if not ticker_values or total <= 0:
        raise CongruenceMissingError(f"{path.name} book empty")
    return ticker_values, total

def load_book_from_account_positions(
    path: Path | str = ACCOUNT_POSITIONS_PATH,
) -> tuple[dict[str, float], float]:
    path = Path(path)
    if not path.exists():
        raise CongruenceMissingError(f"{path.name} absent")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["combined_positions"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CongruenceMissingError(f"{path.name} unreadable for book: {exc}") from exc
    ticker_values: dict[str, float] = {}
    total = 0.0
    for row in rows or []:
        ticker = str(row.get("ticker") or "").upper()
        value = row.get("market_value")
        if isinstance(value, (int, float)):
            total += float(value)
            if ticker:
                ticker_values[ticker] = ticker_values.get(ticker, 0.0) + float(value)
    if not ticker_values or total <= 0:
        raise CongruenceMissingError(f"{path.name} book empty")
    return ticker_values, total

# ---------------------------------------------------------------------------
# Pure exposure math
# ---------------------------------------------------------------------------
def _bucket(
    tickers: list[str], ticker_values: dict[str, float]
) -> tuple[dict[str, float], float]:
    held = {t: ticker_values[t] for t in tickers if t in ticker_values}
    return held, sum(held.values())

def exposure(
    insight: dict[str, Any], ticker_values: dict[str, float], total_value: float
) -> dict[str, Any]:
    named_held, named_value = _bucket(insight.get("tickers_mapped", []), ticker_values)
    adj_held, adj_value = _bucket(insight.get("tickers_adjacent", []), ticker_values)
    watch_held, watch_value = _bucket(insight.get("watch_tickers", []), ticker_values)
    pct = lambda v: round(100.0 * v / total_value, 2) if total_value else 0.0
    return {
        "named_held": named_held,
        "named_value": round(named_value, 2),
        "named_pct": pct(named_value),
        "adjacent_held": adj_held,
        "adjacent_value": round(adj_value, 2),
        "adjacent_pct": pct(adj_value),
        "combined_pct": pct(named_value + adj_value),
        "watch_held": watch_held,
        "watch_value": round(watch_value, 2),
        "missing_named": [t for t in insight.get("tickers_mapped", []) if t not in ticker_values],
    }

def _line(exp: dict[str, Any]) -> str:
    named = " Â· ".join(sorted(exp["named_held"])) or "none held"
    parts = [f"named ${exp['named_value']:,.0f} ({exp['named_pct']:.2f}%) â€” {named}"]
    if exp["adjacent_held"]:
        parts.append(
            f"+adjacent ${exp['adjacent_value']:,.0f} ({exp['adjacent_pct']:.2f}%): "
            + " Â· ".join(sorted(exp["adjacent_held"]))
            + f" â†’ {exp['combined_pct']:.2f}% combined"
        )
    if exp["watch_held"]:
        parts.append("watch-class held: " + " Â· ".join(sorted(exp["watch_held"])))
    return "  Â·  ".join(parts)

def congruence_report(
    payload: dict[str, Any],
    ticker_values: dict[str, float],
    total_value: float,
    *,
    weights: dict[str, Any],
    today: str | None = None,
) -> dict[str, Any]:
    """One row per ACTIVE insight: exposure + the under-sizing flag."""
    threshold = float(
        weights.get("pattern_thresholds", {}).get("congruence_flag_named_pct", 1.0)
    )
    stale_days = int(weights.get("insight_stale_days", 60))
    rows: list[dict[str, Any]] = []
    for ins in active_insights(payload, today=today, stale_days=stale_days):
        exp = exposure(ins, ticker_values, total_value)
        flagged = ins.get("polarity") == "bullish" and exp["named_pct"] < threshold
        rows.append(
            {
                "insight_id": ins["insight_id"],
                "statement": ins["statement"],
                "belief_strength": ins.get("belief_strength"),
                "stale": ins.get("stale", False),
                **exp,
                "flagged": flagged,
                "flag_note": (
                    "STRONGEST BELIEF Â· SMALLEST EXPOSURE â€” informs once, never forces"
                    if flagged
                    else ""
                ),
                "line": _line(exp),
            }
        )
    return {
        "status": "ok",
        "total_value": round(total_value, 2),
        "flag_threshold_named_pct": threshold,
        "rows": rows,
        "flagged_ids": [r["insight_id"] for r in rows if r["flagged"]],
    }

def congruence_from_repo(
    payload: dict[str, Any],
    *,
    weights: dict[str, Any],
    feed_path: Path | str = FEED_PATH,
    account_positions_path: Path | str = ACCOUNT_POSITIONS_PATH,
    today: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper with the honest-empty contract."""
    source = None
    try:
        ticker_values, total = load_book_from_feed(feed_path)
        source = "latest_cockpit_feed.portfolio_views"
    except CongruenceMissingError:
        try:
            ticker_values, total = load_book_from_account_positions(account_positions_path)
            source = "account_positions.combined_positions"
        except CongruenceMissingError as exc:
            return {
                "status": "not_checked",
                "reason": f"no positions cache available ({exc}) â€” congruence NOT computed; "
                "not checked is not all clear",
                "rows": [],
            }
    report = congruence_report(payload, ticker_values, total, weights=weights, today=today)
    report["book_source"] = source
    return report
