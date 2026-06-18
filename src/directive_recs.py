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

import battery_evidence as be
import battery_feed_adapter as bfa
import conviction_engine as ce
import conviction_sizing_calibrator as csc
import decision_card as dc
import decision_dossiers as dd
import execution_plan as ep
import insight_register as ir
import timing_engine as te

SRC = Path(__file__).resolve().parent
FEED_PATH = SRC / "latest_cockpit_feed.json"
THESES_PATH = SRC / "theses.json"
SOURCE_RATES_PATH = SRC / "source_rates.json"

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

def _load_theses(path: Path = THESES_PATH) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("theses") if isinstance(payload, dict) else payload
    return [row for row in rows or [] if isinstance(row, dict)]

def _load_source_rates(path: Path = SOURCE_RATES_PATH) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None

def _positions_for_sizing(feed: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (((feed.get("portfolio_views") or {}).get("views") or {})
            .get("combined") or {}).get("rows") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper().strip()
        try:
            value = float(row.get("market_value") or row.get("value") or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if ticker:
            out.append({"ticker": ticker, "market_value": max(0.0, value)})
    return out

def _macro_for_sizing(feed: dict[str, Any]) -> dict[str, Any] | None:
    macro = feed.get("macro")
    if not isinstance(macro, dict):
        return None
    regime = macro.get("regime")
    if isinstance(regime, dict):
        label = regime.get("label")
        if isinstance(label, str) and label.strip():
            safe = dict(macro)
            safe["regime"] = label
            safe.setdefault("regime_label", label)
            return safe
    return macro

def _current_value(positions: list[dict[str, Any]], ticker: str) -> float:
    tick = ticker.upper()
    total = 0.0
    for row in positions:
        if str(row.get("ticker") or "").upper() != tick:
            continue
        try:
            total += float(row.get("market_value") or 0.0)
        except (TypeError, ValueError):
            pass
    return total

def _gap_for_ticker(report: csc.ConvictionReport, ticker: str) -> csc.ConvictionGap | None:
    tick = ticker.upper()
    groups = (
        report.critically_below,
        report.below_floor,
        report.in_band,
        report.above_ceiling,
        report.monitor_suppressed,
        report.no_thesis,
    )
    for group in groups:
        for gap in group:
            if gap.ticker.upper() == tick:
                return gap
    return None

def _caps_sizing(
    *,
    ticker: str,
    proposed_usd: float,
    book: float,
    positions: list[dict[str, Any]],
    theses: list[dict[str, Any]],
    macro_pulse: dict[str, Any] | None = None,
    source_rates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the caps-derived size anchor for a BUY card.

    The card can still propose a smaller/larger staged trade. This object makes
    the tier-band cap visible before the operator accepts the notional anchor.
    """
    tick = ticker.upper()
    proposed = max(0.0, float(proposed_usd or 0.0))
    if book <= 0:
        return {
            "suggested_usd": round(proposed, 2),
            "source": "caps",
            "heat": "not_checked",
            "cap_basis": "caps not checked - portfolio book value unavailable",
        }
    current = _current_value(positions, tick)
    sizing_positions = list(positions)
    if not any(str(row.get("ticker") or "").upper() == tick for row in sizing_positions):
        sizing_positions.append({"ticker": tick, "market_value": current})
    report = csc.calibrate(
        sizing_positions,
        theses,
        sleeve_total=book,
        macro_pulse=macro_pulse,
        source_rates=source_rates,
    )
    gap = _gap_for_ticker(report, tick)
    if not gap:
        return {
            "suggested_usd": round(proposed, 2),
            "source": "caps",
            "heat": "not_checked",
            "cap_basis": f"caps not checked - calibrator emitted no row for {tick}",
        }
    ceiling_value = gap.ceiling_pct * book
    floor_value = gap.floor_pct * book
    cap_room = max(0.0, ceiling_value - current)
    suggested = min(proposed, cap_room)
    heat = gap.classification
    if "monitor_suppressed" in gap.flags:
        heat = "MONITOR_SUPPRESSED"
    elif cap_room <= 0:
        heat = "ABOVE_CAP"
    elif suggested < proposed:
        heat = "CAP_CLIPPED"
    flags = f"; flags {', '.join(gap.flags)}" if gap.flags else ""
    macro = f"; urgency {gap.macro_urgency}" if gap.macro_urgency != "NORMAL" else ""
    return {
        "suggested_usd": round(suggested, 2),
        "source": "caps",
        "heat": heat,
        "cap_basis": (
            f"{gap.tier} floor {gap.floor_pct * 100:.1f}% (${floor_value:,.0f}) / "
            f"ceiling {gap.ceiling_pct * 100:.1f}% (${ceiling_value:,.0f}); "
            f"current {gap.current_pct * 100:.1f}% (${current:,.0f}); "
            f"cap room ${cap_room:,.0f}; floor gap ${gap.gap_to_floor_value:,.0f}"
            f"{macro}{flags}"
        ),
        "current_pct": round(gap.current_pct * 100.0, 3),
        "floor_pct": round(gap.floor_pct * 100.0, 3),
        "ceiling_pct": round(gap.ceiling_pct * 100.0, 3),
    }

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
    extra_cards: list[dict[str, Any]] | None = None,
    extra_fs_items: dict[str, list[dict[str, Any]]] | None = None,
    inst_states: dict[str, dict[str, Any]] | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    feed = _load_feed(feed)
    today_iso = today or date.today().isoformat()
    insights_payload = insights_payload or ir.load_insights()
    accounts = accounts or ep.load_accounts()
    gates = gates if gates is not None else te.load_gates()
    uw_states = uw_states or {}
    entry_zones = entry_zones or {}
    extra_fs_items = extra_fs_items or {}
    inst_states = inst_states or {}
    etfs = _etf_tickers()
    goal_scores = _goal_score_index(feed)
    risks = _event_risks(feed)
    drift = _drift_index(feed)
    book = float(((feed.get("portfolio_views") or {}).get("views") or {}).get("combined", {}).get("total_value") or 0.0)
    positions_for_sizing = _positions_for_sizing(feed)
    theses_for_sizing = _load_theses()
    source_rates_for_sizing = rates if isinstance(rates, dict) else _load_source_rates()
    macro_for_sizing = _macro_for_sizing(feed)
    blend = weights.get("priority_blend", {})
    cap_w = float(blend.get("capital_priority_weight", 1.0))
    conv_w = float(blend.get("conviction_weight", 25.0))
    win_w = float(blend.get("window_decay_weight", 20.0))

    rb = feed.get("reallocation_brief") or {}
    cards: list[dict[str, Any]] = []
    dossier_rows = dd.load_dossiers()

    def _conviction(ticker: str) -> dict[str, Any]:
        items = ce.fs_items_from_source_calls(ticker)
        m = ce.fs_membership_item(ticker)
        if m:
            items.append(m)
        extras = extra_fs_items.get(ticker.upper())
        if extras:
            items.extend(extras)
        sector_items = ce.fs_sector_items_for_ticker(ticker, weights=weights)
        uw = uw_states.get(ticker) or ce.uw_state_from_feed(ticker, feed)
        battery_inputs = bfa.gather_battery_inputs(ticker, feed)
        battery = be.build_battery_evidence(
            ticker,
            uw_opportunity=battery_inputs["uw_opportunity"],
            group_rotation=battery_inputs["group_rotation"],
            iv_ctx=battery_inputs["iv_ctx"],
            battery_source_config=weights.get("battery_sources"),
        )
        return ce.conviction(
            ticker, fs_items=items, sector_items=sector_items, uw_state=uw, insight_payload=insights_payload,
            inst_state=inst_states.get(ticker.upper()),
            weights=weights, goal=goal, rates=rates, today=today_iso,
            battery=battery,
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

    def _funding_only_low_salience(card: dict[str, Any]) -> bool:
        move = ((card.get("decision_card") or {}).get("move") or {})
        return (
            move.get("lane") == "funding_trim"
            and bool(card.get("funds"))
            and not ((card.get("impact") or {}).get("material"))
            and ((card.get("window") or {}).get("class") == "STAGE-ONLY")
        )

    def _salience_bucket(card: dict[str, Any]) -> int:
        if _funding_only_low_salience(card):
            return 2
        if (card.get("impact") or {}).get("material"):
            return 0
        return 1

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
        sizing = _caps_sizing(
            ticker=ticker,
            proposed_usd=dollars,
            book=book,
            positions=positions_for_sizing,
            theses=theses_for_sizing,
            macro_pulse=macro_for_sizing,
            source_rates=source_rates_for_sizing,
        )
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
            "sizing": sizing,
        }
        dc.attach(
            card,
            {
                "move": move,
                "conviction": {
                    "read": conv["read"], "points": conv["points"],
                    "groups": conv["groups"], "raises": conv["raises"],
                    "conflicted": conv.get("conflicted"),
                    "conflict_detail": conv.get("conflict_detail"),
                },
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
        if conv.get("conflicted"):
            # Real disagreement is NO-ADD / RE-CHECK, never a confident buy.
            # Keep the LOUD priority (points already carry opposition magnitude)
            # so the card surfaces; actionability is gated downstream via the
            # conflict flag (the display layer routes it to a non-ACT rail). Do
            # NOT cap priority — a ceiling would cancel the loud points and
            # bury the card.
            card["conflict_recheck"] = True
            move["direction"] = "RE-CHECK"
            card["conviction_conflict"] = True   # mirror onto card for render/posture lookups
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
                "conviction": {
                    "read": conv["read"], "points": conv["points"],
                    "groups": conv["groups"], "raises": conv["raises"],
                    "conflicted": conv.get("conflicted"),
                    "conflict_detail": conv.get("conflict_detail"),
                },
                "window": {"class": window["class"], "deadline": window["deadline"], "reasons": window["reasons"], "flips": window["flips"]},
                "evidence": {"links": [
                    {"label": f"funds â†’ {funds}" if funds else "funding trim", "ref": "feed.reallocation_brief.trims"},
                    {"label": "target drift", "ref": "feed.target_drift"},
                ]},
                "impact": impact,
            },
        )
        base = goal_scores.get(ticker, 45.0)
        if conv.get("conflicted"):
            # conv["points"] is now a POSITIVE opposition magnitude; the old
            # max(0.0, -points) would zero it and re-bury the conflict in the
            # exact lane where "never sell a live thesis into weakness" lives.
            conv_lift = conv_w * float(
                (conv.get("conflict_detail") or {}).get("opposition_magnitude")
                or conv["points"]
            )
        else:
            conv_lift = conv_w * max(0.0, -conv["points"])
        raw_priority = round(
            cap_w * base + conv_lift + win_w * _WINDOW_FACTOR[window["class"]], 1
        )
        if _funding_only_low_salience(card):
            card["priority"] = min(raw_priority, 9.0)
            card["priority_note"] = "funding-only immaterial leg; pair with funded add, never hero-ranked"
        else:
            card["priority"] = raw_priority
        if conv.get("conflicted"):
            card["conflict_recheck"] = True
            move["direction"] = "RE-CHECK"
            card["conviction_conflict"] = True
        cards.append(card)

    # Merge in orphan-wired extra cards (e.g. MONITOR-RE-ENTRY). Each extra
    # card gets a priority computed with the same blend; if a priority is
    # already attached we trust it (orphan_wiring can override).
    for card in extra_cards or []:
        direction = str(card.get("direction") or ((card.get("decision_card") or {}).get("move") or {}).get("direction") or "").upper()
        if direction in {"BUY", "ADD"} and not card.get("sizing"):
            ticker = str(card.get("ticker") or "").upper()
            dollars = float(card.get("dollars") or card.get("notional_usd") or 0.0)
            card["sizing"] = _caps_sizing(
                ticker=ticker,
                proposed_usd=dollars,
                book=book,
                positions=positions_for_sizing,
                theses=theses_for_sizing,
                macro_pulse=macro_for_sizing,
                source_rates=source_rates_for_sizing,
            )
        if "priority" not in card:
            ticker = str(card.get("ticker") or "").upper()
            conv = card.get("conviction") or {}
            window = card.get("window") or {}
            base = goal_scores.get(ticker, 55.0)  # MONITOR-RE-ENTRY pulses get
            #  a touch above the unscored default so they cluster with reallocation
            #  adds rather than disappearing into the backlog.
            card["priority"] = round(
                cap_w * base
                + conv_w * float(conv.get("points") or 0.0)
                + win_w * _WINDOW_FACTOR.get(window.get("class", "WAIT"), 0.0),
                1,
            )
        if (card.get("conviction") or {}).get("conflicted"):
            card["conflict_recheck"] = True
            card["conviction_conflict"] = True
            mv = (card.get("decision_card") or {}).get("move") or card.get("move") or {}
            if mv:
                mv["direction"] = "RE-CHECK"
        cards.append(card)

    for card in cards:
        if "dossier" not in card:
            dd.attach_card_dossier(card, dossiers=dossier_rows, today=today_iso)

    cards.sort(key=lambda c: (_salience_bucket(c), -c["priority"]))
    max_cards = int(goal["daily_card_max"])
    funding = rb.get("funding") or {}
    return {
        "built": today_iso,
        "cards": cards[:max_cards],
        "backlog": cards[max_cards:],
        "funding": funding,
        "honesty": {
            "cash": "not_checked â€” no cash rows in positions cache",
            "institutional": (
                "wired via orphan_wiring (13F + insider lanes)"
                if inst_states else "not wired (orphan-wiring chunk)"
            ),
            "uw_same_session": sorted(uw_states.keys()) or "none provided this session",
            "gates_as_of": (gates[0].get("stated") if gates else None),
            "positions_as_of": rb.get("positions_snapshot_date"),
        },
    }
