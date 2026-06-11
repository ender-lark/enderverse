"""Orphan wiring wave — C8 (Task 5).

Adapters that promote three V2 orphans into V3 honesty-rail-clean inputs:

* :func:`build_monitor_reentry_cards` — wraps :mod:`re_entry_zone_scan` for
  MONITOR-sleeve names (BMNR / LEU / UUUU / MP). The card REQUIRES defined-risk
  fields (``stop_loss``, ``risk_band``, ``max_loss_usd``) — without them it
  does not emit. This is the ONLY Action path for MONITOR-sleeve names; the
  conviction engine still scores them but the MONITOR no-add-nudge rule means
  any other path stays advisory.
* :func:`build_grny_delta_items` — wraps :mod:`granny_diff` output (the
  ``analyze_diff`` findings dict). Lee's named-not-held adds become
  fs-group "near-Tier-A" rows dated the diff (Tier A items, source ``lee``);
  weight changes and dropped names become context rows (Tier B / Tier C).
  Output is a list of ``source_calls``-shaped dicts the conviction engine's
  :func:`fs_items_from_source_calls` already understands.
* :func:`build_inst_states` — wraps :mod:`13f_best_ideas` (``score_universe``
  output) + :mod:`insider_activity_scan` (``InsiderReport`` output) into a
  per-ticker ``inst_state`` dict that drops cleanly into
  :func:`conviction_engine.institutional_group`. Points are capped at the
  ``group_caps.institutional`` value (1.0 by default doctrine).

Unified runner :func:`compute_orphan_wiring` calls each adapter inside its own
try/except so one missing source cache never wipes the others; absent caches
render ``"not checked"`` in the honesty footer (never silent fallback).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import conviction_engine as ce
import decision_card as dc
import re_entry_zone_scan as res
import timing_engine as te

SRC = Path(__file__).resolve().parent

# MONITOR-sleeve names — operator-spec; reentry is the only Action path.
MONITOR_SLEEVE_TICKERS = frozenset({"BMNR", "LEU", "UUUU", "MP"})


def _today(today: str | date | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(str(today), "%Y-%m-%d").date()


def _unknown_band(text: str) -> dict[str, Any]:
    return {
        "band": text,
        "base": "book",
        "material": False,
        "basis": "MONITOR-sleeve card: defined-risk only, sized to max loss",
    }


# ---------------------------------------------------------------------------
# MONITOR-RE-ENTRY
# ---------------------------------------------------------------------------
def build_monitor_reentry_cards(
    monitor_zones: dict[str, dict[str, Any]] | None,
    *,
    weights: dict[str, Any],
    goal: dict[str, Any],
    today: str | date | None = None,
    insights_payload: dict[str, Any] | None = None,
    uw_states: dict[str, dict[str, Any]] | None = None,
    inst_states: dict[str, dict[str, Any]] | None = None,
    source_calls: list[dict[str, Any]] | None = None,
    prospects: dict[str, Any] | None = None,
    rates: dict[str, Any] | None = None,
    gates: list[dict[str, Any]] | None = None,
    event_risks: list[dict[str, Any]] | None = None,
    allowed_tickers: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Emit MONITOR-RE-ENTRY cards for sleeve names whose intraday range
    touches their re-entry zone AND that carry defined-risk fields.

    Each ``monitor_zones[ticker]`` row must define:
        zone_lo, zone_hi, intraday_low, intraday_high, last_close,
        stop_loss, risk_band, max_loss_usd  (and optionally source, tier).
    Rows missing any of the defined-risk fields are SKIPPED — no card emits.
    """
    today_d = _today(today)
    today_iso = today_d.isoformat()
    allowed = {str(t).upper() for t in (allowed_tickers or MONITOR_SLEEVE_TICKERS)}
    uw_states = uw_states or {}
    inst_states = inst_states or {}

    cards: list[dict[str, Any]] = []
    for raw_ticker, z in (monitor_zones or {}).items():
        if not isinstance(z, dict):
            continue
        ticker = str(raw_ticker).upper()
        if ticker not in allowed:
            continue
        try:
            zone_lo = float(z["zone_lo"])
            zone_hi = float(z["zone_hi"])
            intraday_low = float(z["intraday_low"])
            intraday_high = float(z["intraday_high"])
            last_close = float(z["last_close"])
        except (KeyError, TypeError, ValueError):
            continue
        # Defined-risk gate — REQUIRED fields. Without them, no card emits.
        stop_loss = z.get("stop_loss")
        risk_band = str(z.get("risk_band") or "").strip()
        max_loss_usd = z.get("max_loss_usd")
        if stop_loss is None or not risk_band or max_loss_usd is None:
            continue
        try:
            stop_loss_f = float(stop_loss)
            max_loss_usd_f = float(max_loss_usd)
        except (TypeError, ValueError):
            continue
        touch = res.evaluate_zone_touch(
            ticker=ticker,
            zone_lo=zone_lo, zone_hi=zone_hi,
            intraday_low=intraday_low, intraday_high=intraday_high,
            last_close=last_close,
            source=z.get("source"), tier=z.get("tier"),
        )
        if not touch.fired:
            continue

        fs_items = ce.fs_items_from_source_calls(ticker, calls=source_calls)
        if prospects is not None:
            m = ce.fs_membership_item(ticker, prospects=prospects)
            if m:
                fs_items.append(m)
        conv = ce.conviction(
            ticker,
            fs_items=fs_items,
            uw_state=uw_states.get(ticker),
            insight_payload=insights_payload,
            inst_state=inst_states.get(ticker),
            weights=weights, goal=goal, rates=rates, today=today_iso,
        )
        window = te.compute_timing(
            ticker, direction="BUY", sleeves=["monitor"], gates=gates or [],
            entry_zone={"low": zone_lo, "high": zone_hi},
            uw_state=uw_states.get(ticker),
            event_risks=event_risks or [],
            weights=weights, goal=goal, today=today_iso,
        )
        move = {
            "ticker": ticker,
            "direction": "BUY",
            "lane": "monitor_reentry",
            "band": (f"zone ${zone_lo:.2f}–${zone_hi:.2f} touched "
                     f"(intraday ${intraday_low:.2f}–${intraday_high:.2f}); "
                     f"stop ${stop_loss_f:.2f} / {risk_band}"),
        }
        impact = _unknown_band(
            f"defined risk ≤ ${max_loss_usd_f:,.2f} (stop ${stop_loss_f:.2f}, {risk_band})"
        )
        evidence_links = [
            {"label": f"re-entry zone source: {z.get('source') or 'unspecified'}",
             "ref": f"re_entry_zone_scan.{ticker}"},
            {"label": touch.reason, "ref": "evaluate_zone_touch.reason"},
            {"label": "conviction breakdown", "ref": "card.conviction.group_detail"},
        ]
        card = {
            "card_id": f"{ticker}-MONITOR-RE-ENTRY-{today_iso}",
            "ticker": ticker,
            "pattern": "MONITOR-RE-ENTRY",
            "direction": "BUY",
            "sleeve": "monitor",
            "zone": {"low": zone_lo, "high": zone_hi},
            "intraday": {"low": intraday_low, "high": intraday_high, "close": last_close},
            "defined_risk": {
                "stop_loss": stop_loss_f,
                "risk_band": risk_band,
                "max_loss_usd": max_loss_usd_f,
            },
            "touch_reason": touch.reason,
            "conviction": conv,
            "window": window,
        }
        dc.attach(
            card,
            {
                "move": move,
                "conviction": {
                    "read": conv["read"], "points": conv["points"],
                    "groups": conv["groups"], "raises": conv["raises"],
                },
                "window": {
                    "class": window["class"], "deadline": window.get("deadline"),
                    "reasons": window["reasons"], "flips": window.get("flips") or [],
                },
                "evidence": {"links": evidence_links},
                "impact": impact,
            },
        )
        cards.append(card)
    return cards


# ---------------------------------------------------------------------------
# GRNY-DELTA evidence items
# ---------------------------------------------------------------------------
def build_grny_delta_items(
    findings: dict[str, Any] | None,
    *,
    today: str | date | None = None,
) -> list[dict[str, Any]]:
    """Convert :func:`granny_diff.analyze_diff` output into source_calls rows.

    The shape returned matches what :func:`conviction_engine.fs_items_from_source_calls`
    expects (``source``, ``ticker``, ``tier``, ``date``, ``direction``, ``note`` /
    ``verbatim_quote``), so callers can flow them into the fs lane directly.
    """
    today_d = _today(today)
    today_iso = today_d.isoformat()
    out: list[dict[str, Any]] = []
    findings = findings or {}
    seen: set[tuple[str, str]] = set()

    for x in findings.get("lee_named_not_held") or []:
        ticker = str(x.get("ticker") or "").upper()
        if not ticker:
            continue
        etf = str(x.get("etf") or "?")
        weight = float(x.get("weight_pct") or 0.0)
        rank = x.get("rank")
        key = (ticker, "lee_named_not_held")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": f"grny-delta-{etf}-{ticker}-{today_iso}",
            "source": "lee",
            "ticker": ticker,
            "tier": "A",
            "direction": "bullish",
            "date": today_iso,
            "verbatim_quote": (f"GRNY-DELTA: Lee {etf} holding "
                               f"#{rank} @ {weight:.2f}% (named, not held)"),
            "note": "GRNY-DELTA named-endorsement",
            "kind": "grny_delta",
        })

    for x in findings.get("additions_vs_baseline") or []:
        ticker = str(x.get("ticker") or "").upper()
        if not ticker:
            continue
        if x.get("operator_holds"):
            continue
        if (ticker, "lee_named_not_held") in seen:
            continue
        etf = str(x.get("etf") or "?")
        weight = float(x.get("weight_pct") or 0.0)
        key = (ticker, "additions_vs_baseline")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": f"grny-delta-add-{etf}-{ticker}-{today_iso}",
            "source": "lee",
            "ticker": ticker,
            "tier": "B",
            "direction": "bullish",
            "date": today_iso,
            "verbatim_quote": (f"GRNY-DELTA: Lee {etf} new addition "
                               f"@ {weight:.2f}% (vs prior baseline)"),
            "note": "GRNY-DELTA new-addition",
            "kind": "grny_delta_add",
        })

    for x in findings.get("weight_changes") or []:
        ticker = str(x.get("ticker") or "").upper()
        if not ticker:
            continue
        if (ticker, "lee_named_not_held") in seen:
            continue
        etf = str(x.get("etf") or "?")
        prior = float(x.get("prior_weight") or 0.0)
        current = float(x.get("current_weight") or 0.0)
        change = float(x.get("change_pct") or (current - prior))
        direction = "bullish" if change >= 0 else "bearish"
        key = (ticker, "weight_changes")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": f"grny-delta-wt-{etf}-{ticker}-{today_iso}",
            "source": "lee",
            "ticker": ticker,
            "tier": "C",
            "direction": direction,
            "date": today_iso,
            "verbatim_quote": (f"GRNY-DELTA: Lee {etf} weight {prior:.2f}% → "
                               f"{current:.2f}% (Δ {change:+.2f}pp)"),
            "note": "GRNY-DELTA weight-change context",
            "kind": "grny_delta_context",
        })

    for x in findings.get("dropped_held") or []:
        ticker = str(x.get("ticker") or "").upper()
        if not ticker:
            continue
        etf = str(x.get("etf") or "?")
        prior = float(x.get("prior_weight") or 0.0)
        out.append({
            "id": f"grny-delta-drop-{etf}-{ticker}-{today_iso}",
            "source": "lee",
            "ticker": ticker,
            "tier": "C",
            "direction": "bearish",
            "date": today_iso,
            "verbatim_quote": (f"GRNY-DELTA: Lee {etf} DROPPED "
                               f"(prior {prior:.2f}%; operator still holds)"),
            "note": "GRNY-DELTA dropped-held context",
            "kind": "grny_delta_drop",
        })
    return out


# ---------------------------------------------------------------------------
# inst_state adapter (13F best ideas + insider activity)
# ---------------------------------------------------------------------------
def _accumulate(
    out: dict[str, dict[str, Any]], ticker: str, *, delta: float, lane: str,
) -> None:
    state = out.setdefault(
        ticker.upper(),
        {"points": 0.0, "status": "ok", "lanes": [], "why": ""},
    )
    state["points"] = round(state["points"] + delta, 3)
    state["lanes"].append(lane)
    state["why"] = "; ".join(state["lanes"])


def build_inst_states(
    *,
    weights: dict[str, Any],
    holdings_13f: list[dict[str, Any]] | None = None,
    insider_report: Any | None = None,
    today: str | date | None = None,
) -> dict[str, dict[str, Any]]:
    """Adapter: 13F discoveries + insider classifications → inst_state map.

    Points (capped at ``group_caps.institutional`` by the engine; we sum here
    and trust the engine cap):

    * 13F best-ideas — ``band == "High"``: +1.0 ; ``"Moderate"``: +0.6 ;
      ``"Watch"``: +0.25. Activist-lane adds a +0.25 manager-overlap bonus.
    * Insider scan — ``CLUSTER``: +0.5 ; ``BULLISH``: +0.4 ; ``BEARISH``:
      −0.3 ; ``FLAGGED``: −0.5 (pre-catalyst sale or trump-ally signal).

    The engine clamps to ±1.0; we keep raw sums so the ``why`` line is honest
    about every contributor.
    """
    del weights  # cap is enforced by conviction_engine.institutional_group
    del today  # reserved; current adapter is point-in-time
    out: dict[str, dict[str, Any]] = {}

    for rec in holdings_13f or []:
        ticker = str(rec.get("ticker") or "").upper()
        if not ticker:
            continue
        band = str(rec.get("band") or "Watch")
        delta = {"High": 1.0, "Moderate": 0.6}.get(band, 0.25)
        n_mgrs = int(rec.get("n_managers") or 0)
        lane = (f"13F {band} ({n_mgrs} mgr{'s' if n_mgrs != 1 else ''}, "
                f"{rec.get('lane', 'Best-Ideas')})")
        _accumulate(out, ticker, delta=delta, lane=lane)
        if rec.get("lane") == "Activist":
            _accumulate(out, ticker, delta=0.25, lane="activist-lane overlap")

    if insider_report is not None:
        for sig in (getattr(insider_report, "cluster", None) or []):
            _accumulate(out, sig.ticker,
                        delta=0.5,
                        lane=f"insider CLUSTER ({sig.cluster_count} insiders)")
        for sig in (getattr(insider_report, "bullish", None) or []):
            _accumulate(out, sig.ticker,
                        delta=0.4,
                        lane=f"insider BULLISH ({sig.bullish_count} csuite buys)")
        for sig in (getattr(insider_report, "bearish", None) or []):
            _accumulate(out, sig.ticker,
                        delta=-0.3,
                        lane=f"insider BEARISH ({sig.bearish_count} signals)")
        for sig in (getattr(insider_report, "flagged", None) or []):
            _accumulate(out, sig.ticker,
                        delta=-0.5,
                        lane="insider FLAGGED (pre-catalyst sale / trump-ally)")

    return {t: {k: v for k, v in s.items() if k != "lanes"} for t, s in out.items()}


# ---------------------------------------------------------------------------
# Unified runner
# ---------------------------------------------------------------------------
def compute_orphan_wiring(
    *,
    monitor_zones: dict[str, dict[str, Any]] | None = None,
    granny_findings: dict[str, Any] | None = None,
    holdings_13f: list[dict[str, Any]] | None = None,
    insider_report: Any | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    today: str | date | None = None,
    insights_payload: dict[str, Any] | None = None,
    uw_states: dict[str, dict[str, Any]] | None = None,
    source_calls: list[dict[str, Any]] | None = None,
    prospects: dict[str, Any] | None = None,
    rates: dict[str, Any] | None = None,
    gates: list[dict[str, Any]] | None = None,
    event_risks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run all three adapters with try/except per lane and honesty rollup."""
    today_iso = _today(today).isoformat()
    not_checked: list[str] = []

    def _safe(name, fn, default):
        try:
            return fn()
        except Exception as exc:  # honest-empty per lane
            not_checked.append(f"{name}: {type(exc).__name__}: {exc}")
            return default

    inst_states = _safe(
        "inst_states",
        lambda: build_inst_states(
            weights=weights, holdings_13f=holdings_13f,
            insider_report=insider_report, today=today_iso,
        ),
        {},
    )
    grny_items = _safe(
        "grny_delta",
        lambda: build_grny_delta_items(granny_findings, today=today_iso),
        [],
    )
    # Group GRNY items by ticker so directive_recs can merge them per-ticker.
    grny_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in grny_items:
        grny_by_ticker.setdefault(str(row["ticker"]).upper(), []).append(row)

    monitor_cards = _safe(
        "monitor_reentry",
        lambda: build_monitor_reentry_cards(
            monitor_zones, weights=weights, goal=goal, today=today_iso,
            insights_payload=insights_payload, uw_states=uw_states,
            inst_states=inst_states, source_calls=source_calls,
            prospects=prospects, rates=rates, gates=gates, event_risks=event_risks,
        ),
        [],
    )

    honesty: dict[str, Any] = {}
    if granny_findings is None:
        honesty["granny_diff"] = "not checked — no granny_diff cache provided"
    if not holdings_13f and insider_report is None:
        honesty["institutional"] = ("not checked — 13F and insider caches both absent "
                                    "(was honest-stub before orphan-wiring chunk)")
    if monitor_zones is None:
        honesty["monitor_zones"] = "not checked — no re-entry zone snapshot provided"
    if not_checked:
        honesty["lanes_not_checked"] = not_checked

    return {
        "as_of": today_iso,
        "inst_states": inst_states,
        "grny_delta_items": grny_items,
        "grny_delta_by_ticker": grny_by_ticker,
        "monitor_reentry_cards": monitor_cards,
        "honesty": honesty,
    }
