"""Conviction Engine — the `uw_macro` plug (Stage 1, S3).

Turns a macro snapshot (UW yield curve + UUP/VIX/MOVE-style level proxies) into
uniform `kind="macro"` fact-cards: one per rate tenor, per curve spread, and per
level, each with a templated one-liner + `{value, value_5d_ago, chg_5d, unit}`.

Boundary (Sources vs Analyst — RECORD): the plug emits the macro NUMBERS and
fixed calcs (a curve spread = far − near is arithmetic, so it belongs here). It
does NOT classify the regime or fire MACRO ALERT thresholds (10Y>4.75%, MOVE>120,
…) — that judgment is the Analyst's macro read / `regime_detector`. Plug = facts.

Pure-logic + injectable: takes a `macro_snapshot` mapping, so it's fully testable
with FAKE numbers. The Collection layer (Stage 2) wires the live `get_yield_curve`
+ level pulls into that snapshot shape.

Snapshot shape:
    {
      "rates":  {"2Y": {"value": 3.95, "value_5d_ago": 3.98}, "10Y": {...}, ...},
      "levels": {"DXY": {"value": 99.2, "value_5d_ago": 100.5}, "VIX": {...}, ...},
    }
Rate values are in percent; spreads + rate changes are reported in bp; level
changes in points (`unit` records which).

Scope note (v1): rates 2Y/10Y/30Y, spreads 2s10s/10s30s, levels DXY/VIX/MOVE.
Fed-cut-probability, real-10Y, and WTI/copper are deferred to a later macro
enrichment chunk (they need futures / TIPS / commodity pulls in Collection).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sources import BaseSource


# Curve spreads to compute when both legs are present: (name, near, far).
DEFAULT_SPREADS = [("2s10s", "2Y", "10Y"), ("10s30s", "10Y", "30Y")]

# Honest display labels for level cards whose snapshot KEY is a slot name but
# whose VALUE is a proxy instrument. The dollar slot is keyed "DXY" (so the
# regime read + MACRO_LINE_ORDER keep finding it by subject), but the routine
# feeds UUP (the dollar ETF, ~$28) — not the ICE DXY index (~99). Rendering it
# as "USD (UUP)" stops the macro line from printing a ~28 value under "DXY".
# `subject` stays the internal routing key; this map only changes the
# human-facing CONTENT string.
# NOTE: each label here must stay identical to its band key in
# publish_gate.MACRO_BANDS, or the publish gate silently stops checking it.
_LEVEL_DISPLAY = {"DXY": "USD (UUP)"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_bp(x: float) -> str:
    x = round(x)               # nearest bp; collapses -0.0 / tiny floats to 0
    if x == 0:
        x = 0
    return f"{x:+.0f}"


def _fmt_pt(x: float) -> str:
    x = round(x, 1)            # nearest 0.1pt; collapses -0.0 to 0.0
    if x == 0:
        x = 0.0
    return f"{x:+.1f}"


def curve_spread(rates: dict, near: str, far: str):
    """(far − near) spread in bp + its 5d change in bp.

    Returns (spread_bp, chg_5d_bp) — chg is None if either leg lacks a 5d-ago
    value — or None if either leg is missing its current value (skip the spread).
    """
    n = rates.get(near)
    f = rates.get(far)
    if not n or not f or n.get("value") is None or f.get("value") is None:
        return None
    spread = (f["value"] - n["value"]) * 100.0
    n5, f5 = n.get("value_5d_ago"), f.get("value_5d_ago")
    if n5 is None or f5 is None:
        return spread, None
    return spread, (spread - (f5 - n5) * 100.0)


def uw_macro_reader(
    macro_snapshot: dict,
    as_of: str | None = None,
    spreads=DEFAULT_SPREADS,
) -> list[dict]:
    """One macro fact-card per rate tenor, curve spread, and level present.

    Missing current value -> that card is skipped (no fake number). Missing
    5d-ago value -> the card still emits with chg_5d=None and no "(±X 5d)" tail.
    """
    ts = as_of or _utc_now_iso()
    rates = macro_snapshot.get("rates", {}) or {}
    levels = macro_snapshot.get("levels", {}) or {}
    rows: list[dict] = []

    # --- rate cards (value in %, change in bp) ---
    for tenor, rec in rates.items():
        value = (rec or {}).get("value")
        if value is None:
            continue
        v5 = rec.get("value_5d_ago")
        chg = (value - v5) * 100.0 if v5 is not None else None
        content = f"{tenor} {value:.2f}%"
        if chg is not None:
            content += f" ({_fmt_bp(chg)}bp 5d)"
        rows.append({
            "kind": "macro", "subject": tenor, "content": content, "timestamp": ts,
            "data": {"value": value, "value_5d_ago": v5, "chg_5d": chg,
                     "unit": "bp", "metric": "rate"},
        })

    # --- curve-spread cards (value + change in bp) ---
    for name, near, far in spreads:
        res = curve_spread(rates, near, far)
        if res is None:
            continue
        spread, chg = res
        content = f"{name} {_fmt_bp(spread)}bp"
        if chg is not None:
            content += f" ({_fmt_bp(chg)}bp 5d)"
        rows.append({
            "kind": "macro", "subject": name, "content": content, "timestamp": ts,
            "data": {"value": spread,
                     "value_5d_ago": (spread - chg) if chg is not None else None,
                     "chg_5d": chg, "unit": "bp", "metric": "spread"},
        })

    # --- level cards (DXY / VIX / MOVE; change in points) ---
    # `subject` stays the raw slot key (regime + line-ordering find it by that);
    # the DISPLAY label (_LEVEL_DISPLAY) only changes the human-facing content.
    for sym, rec in levels.items():
        value = (rec or {}).get("value")
        if value is None:
            continue
        v5 = rec.get("value_5d_ago")
        chg = (value - v5) if v5 is not None else None
        content = f"{_LEVEL_DISPLAY.get(sym, sym)} {value:g}"
        if chg is not None:
            content += f" ({_fmt_pt(chg)} 5d)"
        rows.append({
            "kind": "macro", "subject": sym, "content": content, "timestamp": ts,
            "data": {"value": value, "value_5d_ago": v5, "chg_5d": chg,
                     "unit": "pt", "metric": "level"},
        })

    return rows


def build_uw_macro_source(
    macro_snapshot: dict, name: str = "uw_macro", **reader_kwargs
) -> BaseSource:
    """Wire the macro reader into the uniform `uw_macro` plug (trust 0.95,
    group market_data via the dials). In production Collection supplies the live
    snapshot; in tests, fake numbers."""
    def fetcher() -> list[dict]:
        return uw_macro_reader(macro_snapshot, **reader_kwargs)

    return BaseSource(name=name, fetcher=fetcher)
