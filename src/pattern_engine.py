"""Pattern engine — wave 1 detectors (Task 4 / C7).

Pure detectors that scan V2 caches and emit V3 decision cards. Every card
returned passes :func:`decision_card.validate_decision_card`; conviction is
computed by :mod:`conviction_engine` so doctrine constraints (Tier D
track-only, UW inconclusive = 0, group caps) are inherited unchanged; timing
is computed by :mod:`timing_engine` with whatever gates / event_risks the
caller has loaded (empty lists are valid — the engine produces an honest
WAIT/STAGE-ONLY window).

Detectors

* **ENDORSED-DIP** — a ``top_prospects`` name whose current price is at least
  ``endorsed_dip_pct`` below its ``add_price`` and whose ``add_price_date``
  (fallback ``add_date``) is within ``endorsed_dip_lookback_days``, AND no
  thesis-break: no bearish ``source_calls`` row exists for the ticker AND the
  ticker is not listed in the caller-provided ``source_conflicts`` set. Emits
  a same-day BUY-REVIEW card.
* **EXPLICIT-ADD** — every fresh Tier-A ``source_calls`` row (age ≤
  ``conviction_weights.tier_window_days['A']``) becomes a Top-5-candidate
  card. Mechanizes the standing rule "fresh Tier-A = candidate".
* **DRUMBEAT** — one source × one ticker mention count
  ≥ ``drumbeat_min_mentions`` within ``drumbeat_window_days``. Tier-D rows
  COUNT toward the mention threshold but contribute zero conviction points
  (the conviction engine refuses to score Tier D, by doctrine).
* **prediction_signals stub** — optional ``src/prediction_signals.json``.
  Validate-if-present; honest ``not_checked`` when absent.

All detectors veto when ``source_conflicts`` flags the ticker.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import conviction_engine as ce
import decision_card as dc
import timing_engine as te

SRC = Path(__file__).resolve().parent
PREDICTION_SIGNALS_PATH = SRC / "prediction_signals.json"
TOP_PROSPECTS_PATH = SRC / "top_prospects.json"
SOURCE_CALLS_PATH = SRC / "source_calls.json"

_BEARISH_DIRECTIONS = frozenset({"bearish", "short", "sell", "sell_fast", "avoid"})


def _today(today: str | date | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(str(today), "%Y-%m-%d").date()


def _parse_iso(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _row_direction(row: dict[str, Any]) -> str:
    return str(row.get("direction") or "bullish").lower()


def _is_bearish(row: dict[str, Any]) -> bool:
    return _row_direction(row) in _BEARISH_DIRECTIONS


def _calls_for(ticker: str, calls: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    tick = ticker.upper()
    return [r for r in calls if str(r.get("ticker") or "").upper() == tick]


def _conviction_for(
    ticker: str,
    *,
    weights: dict[str, Any],
    goal: dict[str, Any],
    calls: list[dict[str, Any]],
    prospects: dict[str, Any] | None,
    insights_payload: dict[str, Any] | None,
    uw_state: dict[str, Any] | None,
    inst_state: dict[str, Any] | None,
    rates: dict[str, Any] | None,
    today: str | date | None,
) -> dict[str, Any]:
    fs_items = ce.fs_items_from_source_calls(ticker, calls=calls)
    if prospects is not None:
        membership = ce.fs_membership_item(ticker, prospects=prospects)
        if membership:
            fs_items.append(membership)
    return ce.conviction(
        ticker,
        fs_items=fs_items,
        uw_state=uw_state,
        insight_payload=insights_payload,
        inst_state=inst_state,
        weights=weights,
        goal=goal,
        rates=rates,
        today=today,
    )


def _timing_for(
    ticker: str,
    *,
    direction: str,
    weights: dict[str, Any],
    goal: dict[str, Any],
    gates: list[dict[str, Any]] | None,
    event_risks: list[dict[str, Any]] | None,
    uw_state: dict[str, Any] | None,
    entry_zone: dict[str, Any] | None,
    today: str | date | None,
    sleeves: list[str] | None = None,
) -> dict[str, Any]:
    return te.compute_timing(
        ticker,
        direction=direction,
        sleeves=sleeves or [],
        gates=gates or [],
        entry_zone=entry_zone,
        uw_state=uw_state,
        event_risks=event_risks or [],
        weights=weights,
        goal=goal,
        today=today,
    )


def _unknown_impact_review() -> dict[str, Any]:
    return {
        "band": "size deferred — review card surfaces the watch, not the trade size",
        "base": "book",
        "material": False,
        "basis": "pattern review; sizing decided on the confirm card",
    }


def _attach_pattern_card(card: dict[str, Any], *, move: dict[str, Any], conv: dict[str, Any],
                         window: dict[str, Any], evidence_links: list[dict[str, str]],
                         impact: dict[str, Any]) -> dict[str, Any]:
    dc.attach(
        card,
        {
            "move": move,
            "conviction": {
                "read": conv["read"],
                "points": conv["points"],
                "groups": conv["groups"],
                "raises": conv["raises"],
            },
            "window": {
                "class": window["class"],
                "deadline": window.get("deadline"),
                "reasons": window["reasons"],
                "flips": window.get("flips") or [],
            },
            "evidence": {"links": evidence_links},
            "impact": impact,
        },
    )
    return card


# ---------------------------------------------------------------------------
# ENDORSED-DIP
# ---------------------------------------------------------------------------
def detect_endorsed_dip(
    *,
    prospects: dict[str, Any],
    source_calls: list[dict[str, Any]] | None = None,
    current_prices: dict[str, float] | None = None,
    source_conflicts: Iterable[str] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    insights_payload: dict[str, Any] | None = None,
    uw_states: dict[str, dict[str, Any]] | None = None,
    inst_states: dict[str, dict[str, Any]] | None = None,
    rates: dict[str, Any] | None = None,
    gates: list[dict[str, Any]] | None = None,
    event_risks: list[dict[str, Any]] | None = None,
    today: str | date | None = None,
) -> list[dict[str, Any]]:
    today_d = _today(today)
    today_iso = today_d.isoformat()
    calls = source_calls or []
    prices = current_prices or {}
    conflicts = {str(t).upper() for t in (source_conflicts or [])}
    uw_states = uw_states or {}
    inst_states = inst_states or {}

    th = weights.get("pattern_thresholds", {})
    dip_pct = float(th.get("endorsed_dip_pct", 12.0))
    lookback = int(th.get("endorsed_dip_lookback_days", 30))

    out: list[dict[str, Any]] = []
    for raw_ticker, rec in (prospects or {}).items():
        if not isinstance(rec, dict):
            continue
        ticker = str(raw_ticker).upper()
        if ticker in conflicts:
            continue
        add_price = rec.get("add_price")
        try:
            add_price_f = float(add_price)
        except (TypeError, ValueError):
            continue
        if add_price_f <= 0:
            continue
        current = prices.get(ticker)
        try:
            current_f = float(current) if current is not None else None
        except (TypeError, ValueError):
            current_f = None
        if current_f is None:
            continue
        add_anchor = _parse_iso(rec.get("add_price_date") or rec.get("add_date"))
        if add_anchor is None:
            continue
        age = (today_d - add_anchor).days
        if age < 0 or age > lookback:
            continue
        drop_pct = (1.0 - current_f / add_price_f) * 100.0
        if drop_pct < dip_pct - 1e-9:
            continue
        # Thesis-break veto: any bearish source_call on the ticker (any date).
        ticker_calls = _calls_for(ticker, calls)
        if any(_is_bearish(r) for r in ticker_calls):
            continue
        conv = _conviction_for(
            ticker,
            weights=weights, goal=goal, calls=calls, prospects=prospects,
            insights_payload=insights_payload, uw_state=uw_states.get(ticker),
            inst_state=inst_states.get(ticker), rates=rates, today=today_iso,
        )
        window = _timing_for(
            ticker, direction="BUY", weights=weights, goal=goal,
            gates=gates, event_risks=event_risks, uw_state=uw_states.get(ticker),
            entry_zone=None, today=today_iso,
        )
        move = {
            "ticker": ticker,
            "direction": "REVIEW",
            "lane": "endorsed_dip",
            "band": f"current ${current_f:,.2f} vs add ${add_price_f:,.2f} "
                    f"(−{drop_pct:.1f}% within {age}d / lookback {lookback}d)",
        }
        evidence_links = [
            {"label": f"top_prospects[{ticker}].add_price (${add_price_f:,.2f} on {add_anchor.isoformat()})",
             "ref": f"top_prospects.{ticker}"},
            {"label": f"current price ${current_f:,.2f}", "ref": "current_prices"},
            {"label": "conviction breakdown", "ref": "card.conviction.group_detail"},
        ]
        card = {
            "card_id": f"{ticker}-ENDORSED-DIP-{today_iso}",
            "ticker": ticker,
            "pattern": "ENDORSED-DIP",
            "direction": "REVIEW",
            "drop_pct": round(drop_pct, 2),
            "lookback_days": age,
            "add_price": add_price_f,
            "add_price_date": add_anchor.isoformat(),
            "current_price": current_f,
            "conviction": conv,
            "window": window,
        }
        out.append(
            _attach_pattern_card(
                card,
                move=move,
                conv=conv,
                window=window,
                evidence_links=evidence_links,
                impact=_unknown_impact_review(),
            )
        )
    return out


# ---------------------------------------------------------------------------
# EXPLICIT-ADD
# ---------------------------------------------------------------------------
def detect_explicit_add(
    *,
    source_calls: list[dict[str, Any]],
    source_conflicts: Iterable[str] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    prospects: dict[str, Any] | None = None,
    insights_payload: dict[str, Any] | None = None,
    uw_states: dict[str, dict[str, Any]] | None = None,
    inst_states: dict[str, dict[str, Any]] | None = None,
    rates: dict[str, Any] | None = None,
    gates: list[dict[str, Any]] | None = None,
    event_risks: list[dict[str, Any]] | None = None,
    today: str | date | None = None,
) -> list[dict[str, Any]]:
    today_d = _today(today)
    today_iso = today_d.isoformat()
    conflicts = {str(t).upper() for t in (source_conflicts or [])}
    uw_states = uw_states or {}
    inst_states = inst_states or {}
    a_window = int(weights.get("tier_window_days", {}).get("A", 14))

    # Dedupe one card per (ticker, source) — the freshest A row wins.
    seen: dict[tuple[str, str], date] = {}
    pick: dict[tuple[str, str], dict[str, Any]] = {}
    for row in source_calls or []:
        if row.get("tier") != "A":
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker in conflicts:
            continue
        if _is_bearish(row):
            # Bearish Tier A is a SHORT card path, not an explicit-ADD candidate.
            continue
        when = _parse_iso(row.get("date"))
        if when is None:
            continue
        age = (today_d - when).days
        if age < 0 or age > a_window:
            continue
        source = str(row.get("source") or "unknown").lower()
        key = (ticker, source)
        prior = seen.get(key)
        if prior is None or when > prior:
            seen[key] = when
            pick[key] = row

    out: list[dict[str, Any]] = []
    for (ticker, source), row in pick.items():
        when = seen[(ticker, source)]
        conv = _conviction_for(
            ticker,
            weights=weights, goal=goal, calls=list(source_calls or []), prospects=prospects,
            insights_payload=insights_payload, uw_state=uw_states.get(ticker),
            inst_state=inst_states.get(ticker), rates=rates, today=today_iso,
        )
        window = _timing_for(
            ticker, direction="BUY", weights=weights, goal=goal,
            gates=gates, event_risks=event_risks, uw_state=uw_states.get(ticker),
            entry_zone=None, today=today_iso,
        )
        verbatim = str(row.get("verbatim_quote") or row.get("note") or "")[:200]
        move = {
            "ticker": ticker,
            "direction": "REVIEW",
            "lane": "explicit_add_candidate",
            "band": f"Tier-A {source} call dated {when.isoformat()} (age {(today_d - when).days}d / window {a_window}d)",
        }
        evidence_links = [
            {"label": f"{source} Tier-A {when.isoformat()}: {verbatim}" if verbatim
             else f"{source} Tier-A {when.isoformat()}",
             "ref": f"source_calls.{row.get('id') or ticker}"},
            {"label": "conviction breakdown", "ref": "card.conviction.group_detail"},
        ]
        card = {
            "card_id": f"{ticker}-EXPLICIT-ADD-{today_iso}",
            "ticker": ticker,
            "pattern": "EXPLICIT-ADD",
            "direction": "REVIEW",
            "tier": "A",
            "source": source,
            "call_date": when.isoformat(),
            "verbatim_quote": verbatim,
            "conviction": conv,
            "window": window,
        }
        out.append(
            _attach_pattern_card(
                card,
                move=move,
                conv=conv,
                window=window,
                evidence_links=evidence_links,
                impact=_unknown_impact_review(),
            )
        )
    out.sort(key=lambda c: (c["ticker"], c["source"]))
    return out


# ---------------------------------------------------------------------------
# DRUMBEAT
# ---------------------------------------------------------------------------
def detect_drumbeat(
    *,
    source_calls: list[dict[str, Any]],
    source_conflicts: Iterable[str] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    prospects: dict[str, Any] | None = None,
    insights_payload: dict[str, Any] | None = None,
    uw_states: dict[str, dict[str, Any]] | None = None,
    inst_states: dict[str, dict[str, Any]] | None = None,
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
) -> list[dict[str, Any]]:
    today_d = _today(today)
    today_iso = today_d.isoformat()
    conflicts = {str(t).upper() for t in (source_conflicts or [])}
    uw_states = uw_states or {}
    inst_states = inst_states or {}
    th = weights.get("pattern_thresholds", {})
    min_mentions = int(th.get("drumbeat_min_mentions", 4))
    window_days = int(th.get("drumbeat_window_days", 30))

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in source_calls or []:
        ticker = str(row.get("ticker") or "").upper()
        source = str(row.get("source") or "unknown").lower()
        if not ticker or ticker in conflicts:
            continue
        when = _parse_iso(row.get("date"))
        if when is None:
            continue
        age = (today_d - when).days
        if age < 0 or age > window_days:
            continue
        # Tier-D rows COUNT toward the drumbeat (doctrine: D never scores, but
        # a repeated D-mention IS a repetition signal worth flagging).
        buckets.setdefault((ticker, source), []).append(row)

    out: list[dict[str, Any]] = []
    for (ticker, source), rows in buckets.items():
        if len(rows) < min_mentions:
            continue
        tiers = [str(r.get("tier") or "?") for r in rows]
        d_only = all(t == "D" for t in tiers)
        latest = max((_parse_iso(r.get("date")) or today_d) for r in rows)
        conv = _conviction_for(
            ticker,
            weights=weights, goal=goal, calls=list(source_calls or []), prospects=prospects,
            insights_payload=insights_payload, uw_state=uw_states.get(ticker),
            inst_state=inst_states.get(ticker), rates=rates, today=today_iso,
        )
        window = _timing_for(
            ticker, direction="BUY", weights=weights, goal=goal,
            gates=None, event_risks=None, uw_state=uw_states.get(ticker),
            entry_zone=None, today=today_iso,
        )
        tier_counts: dict[str, int] = {}
        for t in tiers:
            tier_counts[t] = tier_counts.get(t, 0) + 1
        tier_breakdown = ", ".join(f"{n}×{t}" for t, n in sorted(tier_counts.items()))
        move = {
            "ticker": ticker,
            "direction": "REVIEW",
            "lane": "drumbeat",
            "band": f"{len(rows)} {source} mentions in {window_days}d "
                    f"({tier_breakdown}; latest {latest.isoformat()})",
        }
        evidence_links = [
            {"label": f"{len(rows)} {source} mentions ({tier_breakdown})",
             "ref": f"source_calls[{source}/{ticker}]"},
            {"label": "conviction breakdown (Tier-D adds 0 points by doctrine)",
             "ref": "card.conviction.group_detail"},
        ]
        card = {
            "card_id": f"{ticker}-DRUMBEAT-{today_iso}",
            "ticker": ticker,
            "pattern": "DRUMBEAT",
            "direction": "REVIEW",
            "source": source,
            "mentions": len(rows),
            "tier_breakdown": tier_counts,
            "tier_d_only": d_only,
            "latest_mention": latest.isoformat(),
            "conviction": conv,
            "window": window,
        }
        out.append(
            _attach_pattern_card(
                card,
                move=move,
                conv=conv,
                window=window,
                evidence_links=evidence_links,
                impact=_unknown_impact_review(),
            )
        )
    out.sort(key=lambda c: (c["ticker"], c["source"]))
    return out


# ---------------------------------------------------------------------------
# prediction_signals stub — pattern slot #11
# ---------------------------------------------------------------------------
def load_prediction_signals(
    path: Path | str = PREDICTION_SIGNALS_PATH,
) -> dict[str, Any]:
    """Honest-empty when absent; validated when present.

    Schema (when present):
        {"as_of": "YYYY-MM-DD",
         "rows": [{"venue", "topic", "probability", "delta_24h"?, "date"?,
                   "related_tickers"?}]}

    Returns a payload of shape:
        {"status": "ok"|"not_checked"|"invalid",
         "as_of"?, "rows"?, "note"?}

    Empty payload is the seam; the parallel prediction-markets exploration
    will fill `prediction_signals.json` later (pattern slot #11).
    """
    p = Path(path)
    if not p.exists():
        return {
            "status": "not_checked",
            "rows": [],
            "note": f"{p.name} absent — prediction_signals lane not wired (pattern slot #11)",
        }
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "rows": [],
            "note": f"{p.name} present but not valid JSON: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "rows": [],
            "note": f"{p.name} top-level must be an object",
        }
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return {
            "status": "invalid",
            "rows": [],
            "note": f"{p.name}: 'rows' must be a list",
        }
    cleaned: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            return {
                "status": "invalid",
                "rows": [],
                "note": f"{p.name}: rows[{i}] must be an object",
            }
        venue = str(row.get("venue") or "").strip()
        topic = str(row.get("topic") or "").strip()
        prob = row.get("probability")
        if not venue or not topic:
            return {
                "status": "invalid",
                "rows": [],
                "note": f"{p.name}: rows[{i}] requires non-empty venue + topic",
            }
        if not isinstance(prob, (int, float)) or isinstance(prob, bool):
            return {
                "status": "invalid",
                "rows": [],
                "note": f"{p.name}: rows[{i}].probability must be a number",
            }
        if not (0.0 <= float(prob) <= 1.0):
            return {
                "status": "invalid",
                "rows": [],
                "note": f"{p.name}: rows[{i}].probability must be in [0, 1]",
            }
        cleaned.append({
            "venue": venue,
            "topic": topic,
            "probability": float(prob),
            "delta_24h": row.get("delta_24h"),
            "date": row.get("date"),
            "related_tickers": [str(t).upper() for t in (row.get("related_tickers") or [])],
        })
    return {
        "status": "ok",
        "as_of": payload.get("as_of"),
        "rows": cleaned,
    }


# ---------------------------------------------------------------------------
# Unified runner
# ---------------------------------------------------------------------------
def detect_patterns(
    *,
    prospects: dict[str, Any] | None = None,
    source_calls: list[dict[str, Any]] | None = None,
    current_prices: dict[str, float] | None = None,
    source_conflicts: Iterable[str] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    insights_payload: dict[str, Any] | None = None,
    uw_states: dict[str, dict[str, Any]] | None = None,
    inst_states: dict[str, dict[str, Any]] | None = None,
    rates: dict[str, Any] | None = None,
    gates: list[dict[str, Any]] | None = None,
    event_risks: list[dict[str, Any]] | None = None,
    today: str | date | None = None,
    prediction_signals_path: Path | str = PREDICTION_SIGNALS_PATH,
) -> dict[str, Any]:
    """Run all wave-1 detectors with honest-empty try/except per lane."""
    today_iso = _today(today).isoformat()
    calls = list(source_calls or [])
    prospects = prospects or {}
    not_checked: list[str] = []

    def _safe(name: str, fn) -> list[dict[str, Any]]:
        try:
            return fn()
        except Exception as exc:  # honest-empty per lane
            not_checked.append(f"{name}: {type(exc).__name__}: {exc}")
            return []

    endorsed = _safe(
        "endorsed_dip",
        lambda: detect_endorsed_dip(
            prospects=prospects, source_calls=calls, current_prices=current_prices,
            source_conflicts=source_conflicts, weights=weights, goal=goal,
            insights_payload=insights_payload, uw_states=uw_states,
            inst_states=inst_states, rates=rates, gates=gates,
            event_risks=event_risks, today=today_iso,
        ),
    )
    explicit = _safe(
        "explicit_add",
        lambda: detect_explicit_add(
            source_calls=calls, source_conflicts=source_conflicts,
            weights=weights, goal=goal, prospects=prospects,
            insights_payload=insights_payload, uw_states=uw_states,
            inst_states=inst_states, rates=rates, gates=gates,
            event_risks=event_risks, today=today_iso,
        ),
    )
    drumbeat = _safe(
        "drumbeat",
        lambda: detect_drumbeat(
            source_calls=calls, source_conflicts=source_conflicts,
            weights=weights, goal=goal, prospects=prospects,
            insights_payload=insights_payload, uw_states=uw_states,
            inst_states=inst_states, rates=rates, today=today_iso,
        ),
    )
    prediction = load_prediction_signals(prediction_signals_path)

    return {
        "as_of": today_iso,
        "cards": {
            "endorsed_dip": endorsed,
            "explicit_add": explicit,
            "drumbeat": drumbeat,
        },
        "prediction_signals": prediction,
        "honesty": {
            "lanes_not_checked": not_checked,
            "prediction_signals_status": prediction["status"],
        },
    }
