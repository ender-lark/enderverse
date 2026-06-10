"""Directive recommendations â€” the ranked, decision-first card stack (v1).

Pulls the live reallocation brief (adds + funding trims) from the V2 feed,
computes â€” never asserts â€” each card's conviction (conviction_engine), timing
class (timing_engine), and per-account execution legs (execution_plan), then
attaches the validated 5-field decision card and ranks the stack.

Ranking (v1 blend, all weights in ``conviction_weights.json``): extends the
feed's existing goal_score where one exists (capital-priority lineage) with
conviction-points and window-decay terms. Top ``daily_card_max`` cards form
the strip; the rest are the ranked backlog â€” visible, never hidden.

Honesty rails carried through: cash not_checked (no cash rows in cache),
institutional not wired yet, UW same-session only when a state is provided,
gates stamped with their file date. Idea inputs enter ONLY as cards with
action implications â€” no parallel panels, no gate bypass (V2 rebuild rule).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import conviction_engine as ce
import decision_card as dc
import execution_plan as ep
import insight_register as ir
import timing_engine as te

SRC = Path(__file__).resolve().parent
FEED_PATH = SRC / "latest_cockpit_feed.json"

_WINDOW_FACTOR = {"OPEN-NOW": 1.0, "STAGE-ONLY": 0.66, "GATED": 0.33, "WAIT": 0.0}

def _load_feed(feed: dict[str, Any] | None) -> dict[str, Any]:
    if feed is not None:
        return feed
    return json.loads(FEED_PATH.read_text(encoding="utf-8"))

def _etf_tickers(accounts_rows_path: Path = ep.ACCOUNT_POSITIONS_PATH) -> set[str]:
    try:
        rows = json.loads(accounts_rows_path.read_text(encoding="utf-8"))["account_positions"]
    except (OSError, KeyError, json.JSONDecodeError):
        return set()
    return {
        str(r.get("ticker") or "").upper()
        for r in rows
        if r.get("asset_type") in ep.ETF_LIKE_TYPES and r.get("ticker")
    }

def _goal_score_index(feed: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for a in feed.get("actions") or []:
        t = str(a.get("ticker") or "").upper()
        gs = a.get("goal_score")
        if t and isinstance(gs, (int, float)):
            out[t] = max(out.get(t, 0.0), float(gs))
    return out

def _event_risks(feed: dict[str, Any]) -> list[dict[str, Any]]:
    risks = []
    lane = feed.get("event_risk")
    rows = lane.get("rows") if isinstance(lane, dict) else lane
    for r in rows or []:
        risks.append({"name": r.get("name") or r.get("what"), "note": r.get("note") or r.get("what"), "date": r.get("date")})
    if not risks:
        for a in feed.get("actions") or []:
            if a.get("kind") == "event_risk":
                risks.append({"name": a.get("what"), "note": a.get("what"), "date": None})
    return risks

def _drift_index(feed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    td = feed.get("target_drift") or {}
    return {str(r.get("ticker") or "").upper(): r for r in (td.get("rows") or [])}

def build_directive_cards(
    *,
    feed: dict[str, Any] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    insights_payload: dict[str, Any] | None = None,
    accounts: list[dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None,
    uw_states: dict[str, dict[str, Any]] | None = None,
    entry_zones: dict[str, dict[str, Any]] | None = None,
    rates: dict[str, Any] | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    feed = _load_feed(feed)
    today_iso = today or date.today().isoformat()
    insights_payload = insights_payload or ir.load_insights()
    accounts = accounts or ep.load_accounts()
    gates = gates if gates is not None else te.load_gates()
    uw_states = uw_states or {}
    entry_zones = entry_zones or {}
    etfs = _etf_tickers()
    goal_scores = _goal_score_index(feed)
    risks = _event_risks(feed)
    drift = _drift_index(feed)
    book = float(((feed.get("portfolio_views") or {}).get("views") or {}).get("combined", {}).get("total_value") or 0.0)
    blend = weights.get("priority_blend", {})
    cap_w = float(blend.get("capital_priority_weight", 1.0))
    conv_w = float(blend.get("conviction_weight", 25.0))
    win_w = float(blend.get("window_decay_weight", 20.0))

    rb = feed.get("reallocation_brief") or {}
    cards: list[dict[str, Any]] = []

    def _conviction(ticker: str) -> dict[str, Any]:
        items = ce.fs_items_from_source_calls(ticker)
        m = ce.fs_membership_item(ticker)
        if m:
            items.append(m)
        uw = uw_states.get(ticker) or ce.uw_state_from_feed(ticker, feed)
        return ce.conviction(
            ticker, fs_items=items, uw_state=uw, insight_payload=insights_payload,
            weights=weights, goal=goal, rates=rates, today=today_iso,
        )

    def _impact(dollars: float) -> dict[str, Any]:
        thresh = book * float(goal["impact_material_pct_book"]) / 100.0 if book else None
        material = bool(thresh and dollars >= thresh)
        return {
            "band": f"â‰ˆ ${dollars:,.0f} ({(100*dollars/book):.1f}% of book)" if book else f"â‰ˆ ${dollars:,.0f}",
            "base": "book",
            "material": material,
            "basis": f"materiality floor {goal['impact_material_pct_book']}% of book"
            + (f" = ${thresh:,.0f}" if thresh else ""),
        }

    # ---- ADD candidates -----------------------------------------------------
    for row in rb.get("rows") or []:
        ticker = str(row.get("ticker") or "").upper()
        dollars = float(row.get("notional_usd") or 0.0)
        conv = _conviction(ticker)
        window = te.compute_timing(
            ticker, direction="BUY", sleeves=["ai_semis"], gates=gates,
            entry_zone=entry_zones.get(ticker),
            uw_state=uw_states.get(ticker) or ce.uw_state_from_feed(ticker, feed),
            event_risks=risks, weights=weights, goal=goal, today=today_iso,
        )
        execution = ep.plan_buy(ticker, dollars, accounts=accounts, is_etf=ticker in etfs)
        impact = _impact(dollars)
        move = {
            "ticker": ticker,
            "direction": "BUY",
            "lane": "reallocation_add",
            "band": f"${dollars:,.0f} ({row.get('current_pct', 0):.1f}% â†’ {row.get('target_pct', 0):.1f}%)",
        }
        card = {
            "card_id": f"{ticker}-ADD-{today_iso}",
            "ticker": ticker,
            "direction": "BUY",
            "dollars": dollars,
            "sequence": row.get("sequence"),
            "entry_note": row.get("entry_note"),
            "rb_gate": row.get("gate"),
            "conviction": conv,
            "window": window,
            "execution": execution,
            "impact": impact,
        }
        dc.attach(
            card,
            {
                "move": move,
                "conviction": {"read": conv["read"], "points": conv["points"], "groups": conv["groups"], "raises": conv["raises"]},
                "window": {"class": window["class"], "deadline": window["deadline"], "reasons": window["reasons"], "flips": window["flips"]},
                "evidence": {"links": [
                    {"label": "reallocation_brief (live positions)", "ref": "feed.reallocation_brief"},
                    {"label": "conviction breakdown", "ref": "card.conviction.group_detail"},
                ]},
                "impact": impact,
            },
        )
        base = goal_scores.get(ticker, 50.0)
        card["priority"] = round(
            cap_w * base + conv_w * conv["points"] + win_w * _WINDOW_FACTOR[window["class"]], 1
        )
        if row.get("sequence") == "now":
            card["priority"] += 5.0
        cards.append(card)

    # ---- FUNDING TRIMS ------------------------------------------------------
    stock_adds_present = any(
        str(r.get("ticker") or "").upper() not in etfs for r in rb.get("rows") or []
    )
    for row in rb.get("trims") or []:
        ticker = str(row.get("ticker") or "").upper()
        dollars = float(row.get("notional_usd") or 0.0)
        drow = drift.get(ticker) or {}
        rotation = {"overexposed": drow.get("direction") == "OVERSIZED", "state": ""}
        conv = _conviction(ticker)
        window = te.compute_timing(
            ticker, direction="TRIM", rotation=rotation, weights=weights, goal=goal, today=today_iso,
        )
        execution = ep.plan_sell(
            ticker, dollars, accounts=accounts, funded_buys_are_etf=not stock_adds_present
        )
        impact = _impact(dollars)
        funds = ", ".join(f"{f.get('ticker')} ${f.get('notional_usd', 0):,.0f}" for f in row.get("funds") or [])
        move = {
            "ticker": ticker,
            "direction": "TRIM" if (row.get("target_pct") or 0) > 0 else "SELL",
            "lane": "funding_trim",
            "band": f"${dollars:,.0f} ({row.get('current_pct', 0):.1f}% â†’ {row.get('target_pct', 0):.1f}%)",
        }
        card = {
            "card_id": f"{ticker}-TRIM-{today_iso}",
            "ticker": ticker,
            "direction": move["direction"],
            "dollars": dollars,
            "funds": funds,
            "conviction": conv,
            "window": window,
            "execution": execution,
            "impact": impact,
        }
        dc.attach(
            card,
            {
                "move": move,
                "conviction": {"read": conv["read"], "points": conv["points"], "groups": conv["groups"], "raises": conv["raises"]},
                "window": {"class": window["class"], "deadline": window["deadline"], "reasons": window["reasons"], "flips": window["flips"]},
                "evidence": {"links": [
                    {"label": f"funds â†’ {funds}" if funds else "funding trim", "ref": "feed.reallocation_brief.trims"},
                    {"label": "target drift", "ref": "feed.target_drift"},
                ]},
                "impact": impact,
            },
        )
        base = goal_scores.get(ticker, 45.0)
        card["priority"] = round(
            cap_w * base + conv_w * max(0.0, -conv["points"]) + win_w * _WINDOW_FACTOR[window["class"]], 1
        )
        cards.append(card)

    cards.sort(key=lambda c: -c["priority"])
    max_cards = int(goal["daily_card_max"])
    funding = rb.get("funding") or {}
    return {
        "built": today_iso,
        "cards": cards[:max_cards],
        "backlog": cards[max_cards:],
        "funding": funding,
        "honesty": {
            "cash": "not_checked â€” no cash rows in positions cache",
            "institutional": "not wired (orphan-wiring chunk)",
            "uw_same_session": sorted(uw_states.keys()) or "none provided this session",
            "gates_as_of": (gates[0].get("stated") if gates else None),
            "positions_as_of": rb.get("positions_snapshot_date"),
        },
    }
