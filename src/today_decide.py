"""TODAY â€” DECIDE: the decision-first surface (C5).

One module, two halves:

* :func:`build_today_decide_payload` â€” pure data assembly. Pulls the ranked
  card stack (``directive_recs``), the gate states (``timing_engine``), the
  congruence report (``congruence``), goal-anchor math, source-conflict
  detection, and last dispositions (forward-compatible with the C6 spine)
  into ONE payload dict. Testable without any HTML.
* :func:`render_today_decide_html` â€” payload â†’ a self-contained HTML section
  (scoped ``td-`` styles + a tiny clipboard script, zero network calls).

Mandate rails enforced by construction:
* The pace line is computed once, lives ONLY in ``payload["goal_anchor"]``,
  is labeled display-only, and is rendered ONLY inside the goal-anchor block.
  Nothing in ranking, urgency, or card rendering reads it (tested).
* ACT / PASS / RECHECK rails copy disposition lines to the clipboard; a
  second tap copies ``UNDO <card_id>`` and visually reverts â€” undo is real,
  not cosmetic (the C6 spine accepts the UNDO verb; see Task-3 addendum).
* Honest absence everywhere: unreadable book â†’ pace not computed; missing
  congruence â†’ "not checked"; no dispositions yet â†’ said plainly.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import data_health as _dh
import cloud_routine_receipts as crr
import congruence as cg
import conviction_engine as ce
import directive_recs as dr
import insight_register as ir
import lookthrough_disclosure as ltd
import timing_engine as te
import disposition_log

SRC = Path(__file__).resolve().parent
FEED_PATH = SRC / "latest_cockpit_feed.json"

_GATE_COLORS = {"red": "#f87171", "red_but_tested": "#fbbf24", "green": "#34d399", "context": "#94a3b8"}
_CLASS_COLORS = {"OPEN-NOW": "#34d399", "STAGE-ONLY": "#fbbf24", "GATED": "#f87171", "WAIT": "#94a3b8"}
_BAND_COLORS = {"LOW": "#94a3b8", "MODERATE": "#fbbf24", "HIGH": "#34d399"}
_SELL_BAND_COLORS = {"LOW": "#94a3b8", "MODERATE": "#fbbf24", "HIGH": "#f87171"}
_TRUST_COLORS = {"ok": "#34d399", "warn": "#fbbf24", "alert": "#f87171", "info": "#94a3b8"}
_TRUST_HEALTH_SOURCES = {"portfolio", "uw_price", "uw_macro", "live_tape", "fundstrat_daily", "fundstrat_bible"}
_GROUP_LABELS = {
    "fs": "Fundstrat / source calls",
    "uw": "UW same-session proof",
    "operator_insight": "Operator insight",
    "institutional": "Institutional lane",
}

def _today(today: str | date | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(str(today), "%Y-%m-%d").date()

def _load_feed(feed: dict[str, Any] | None) -> dict[str, Any]:
    if feed is not None:
        return feed
    return json.loads(FEED_PATH.read_text(encoding="utf-8"))

def _months_between(d0: date, d1: date) -> int:
    return max(0, (d1.year - d0.year) * 12 + (d1.month - d0.month))

def _goal_anchor(feed: dict[str, Any], goal: dict[str, Any], today_iso: str) -> dict[str, Any]:
    target = float(goal["fi_target"])
    try:
        book = float(feed["portfolio_views"]["views"]["combined"]["total_value"])
    except (KeyError, TypeError, ValueError):
        return {
            "book_value": None, "fi_target": target, "pct_to_target": None, "gap_usd": None,
            "pace_line": "(display-only) book value not readable from feed â€” pace not computed",
            "horizon": goal["window_horizon"],
        }
    gap = max(0.0, target - book)
    months = _months_between(_today(today_iso),
                             datetime.strptime(goal["window_horizon"], "%Y-%m-%d").date())
    per_month = gap / months if months else gap
    pace_line = (
        f"(display-only) gap ${gap:,.0f} Â· {months} months to {goal['window_horizon']}"
        f" Â· â‰ˆ ${per_month:,.0f}/month â€” pace never feeds ranking or urgency"
    )
    return {
        "book_value": round(book, 2), "fi_target": target,
        "pct_to_target": round(100.0 * book / target, 1), "gap_usd": round(gap, 2),
        "pace_line": pace_line, "horizon": goal["window_horizon"],
    }

def detect_source_conflicts(feed: dict[str, Any], card: dict[str, Any]) -> list[dict[str, Any]]:
    """A card conflicts when another live lane claims the opposite direction
    on the same ticker (live case: MAGS lean-in vs full-sell trim)."""
    conflicts: list[dict[str, Any]] = []
    tick = str(card.get("ticker") or "").upper()
    direction = card.get("direction")
    for a in feed.get("actions") or []:
        if str(a.get("ticker") or "").upper() != tick:
            continue
        kind = str(a.get("kind") or "").lower()
        claim = a.get("what") or f"{kind} lane row"
        if kind == "lean_in" and direction in ("SELL", "TRIM"):
            conflicts.append({"with": "lean_in lane", "their_claim": claim,
                              "card_claim": f"{direction} ${float(card.get('dollars') or 0):,.0f}"})
        elif kind in ("trim", "reduce", "exit") and direction == "BUY":
            conflicts.append({"with": f"{kind} lane", "their_claim": claim,
                              "card_claim": f"BUY ${float(card.get('dollars') or 0):,.0f}"})
    return conflicts


def _text_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, list):
            parts.extend(str(v or "") for v in value)
        elif isinstance(value, dict):
            parts.extend(str(v or "") for v in value.values())
        else:
            parts.append(str(value or ""))
    return " ".join(parts).upper()


def _gate_lookup(gates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        for key in (gate.get("gate_id"), gate.get("symbol")):
            text = str(key or "").strip().upper()
            if text:
                out[text] = gate
    return out


def _gate_applies_to_card(gate: dict[str, Any] | None, card: dict[str, Any]) -> bool:
    if not gate:
        return True
    symbol = str(gate.get("symbol") or "").strip().upper()
    gate_id = str(gate.get("gate_id") or "").strip().upper()
    card_ticker = str(card.get("ticker") or "").strip().upper()
    rb_gate = str(card.get("rb_gate") or "").strip().upper()
    if card_ticker and card_ticker in {symbol, gate_id}:
        return True
    if rb_gate and rb_gate in {symbol, gate_id}:
        return True
    applies_to = {str(value or "").strip().upper() for value in gate.get("applies_to") or []}
    if card_ticker and card_ticker in applies_to:
        return True
    direction = _card_action_direction(card)
    if direction in {"BUY", "ADD"} and ("*BUY*" in applies_to or "BUY" in applies_to):
        return True
    if "*" in applies_to:
        return True
    window = card.get("window") or {}
    blob = _text_blob(
        card.get("entry_note"),
        window.get("named_trigger"),
        window.get("reasons") or [],
        window.get("flips") or [],
    )
    return bool((symbol and symbol in blob) or (gate_id and gate_id in blob))


def _card_blockers(
    card: dict[str, Any],
    data_health: dict[str, Any],
    gates: list[dict[str, Any]],
) -> list[str]:
    lookup = _gate_lookup(gates)
    blockers: list[str] = []
    for item in data_health.get("items") or []:
        if not isinstance(item, dict) or not item.get("blocks"):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        if item.get("source") == "decision_dossier":
            item_ticker = str(item.get("ticker") or "").strip().upper()
            item_card_ids = {
                str(value or "").strip()
                for value in item.get("card_ids") or []
                if str(value or "").strip()
            }
            card_ticker = str(card.get("ticker") or "").strip().upper()
            card_id = str(card.get("card_id") or "").strip()
            if (item_ticker and item_ticker == card_ticker) or (card_id and card_id in item_card_ids):
                blockers.append(label)
            continue
        if item.get("source") != "gates":
            blockers.append(label)
            continue
        gate = None
        for key in (item.get("gate_id"), item.get("symbol")):
            text = str(key or "").strip().upper()
            if text and text in lookup:
                gate = lookup[text]
                break
        if _gate_applies_to_card(gate, card):
            blockers.append(label)
    return blockers


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _price_from_row(row: Any, symbol: str) -> float | None:
    if isinstance(row, (int, float, str)):
        return _coerce_float(row)
    if not isinstance(row, dict):
        return None
    ticker = str(row.get("ticker") or row.get("symbol") or row.get("t") or "").upper()
    if ticker and ticker != symbol:
        return None
    for key in ("price", "last", "last_price", "close", "c", "current_price", "mark"):
        parsed = _coerce_float(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _lookup_gate_price(feed: dict[str, Any], symbol: str) -> tuple[float | None, str]:
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return None, ""
    for key in ("current_closes", "latest_closes", "closes"):
        value = feed.get(key)
        if isinstance(value, dict):
            for lookup_key in (symbol, symbol.lower()):
                if lookup_key in value:
                    parsed = _price_from_row(value.get(lookup_key), symbol)
                    if parsed is not None:
                        return parsed, "close"
            for rows_key in ("rows", "data", "items", "prices"):
                rows = value.get(rows_key)
                if isinstance(rows, list):
                    for row in rows:
                        parsed = _price_from_row(row, symbol)
                        if parsed is not None:
                            return parsed, "close"
        elif isinstance(value, list):
            for row in value:
                parsed = _price_from_row(row, symbol)
                if parsed is not None:
                    return parsed, "close"
    for key in ("current_prices", "latest_prices", "prices", "quotes", "quote", "uw_prices"):
        value = feed.get(key)
        if isinstance(value, dict):
            for lookup_key in (symbol, symbol.lower()):
                if lookup_key in value:
                    parsed = _price_from_row(value.get(lookup_key), symbol)
                    if parsed is not None:
                        return parsed, "live"
            for rows_key in ("rows", "data", "items", "prices"):
                rows = value.get(rows_key)
                if isinstance(rows, list):
                    for row in rows:
                        parsed = _price_from_row(row, symbol)
                        if parsed is not None:
                            return parsed, "live"
        elif isinstance(value, list):
            for row in value:
                parsed = _price_from_row(row, symbol)
                if parsed is not None:
                    return parsed, "live"
    return None, ""


def _gate_level_text(gate: dict[str, Any]) -> str:
    low = _coerce_float(gate.get("level_low"))
    high = _coerce_float(gate.get("level_high"))
    if low is None and high is None:
        return ""
    if high is None:
        high = low
    if low is None:
        low = high
    if abs(float(low) - float(high)) < 0.005:
        return f"{float(high):.2f}"
    return f"{float(low):.2f}-{float(high):.2f}"


def _gate_card_note(gate: dict[str, Any], feed: dict[str, Any]) -> dict[str, str]:
    symbol = str(gate.get("symbol") or gate.get("gate_id") or "gate").upper()
    source = str(gate.get("source") or "").strip()
    stated = str(gate.get("stated") or "").strip()
    state = str(gate.get("state") or "unknown").replace("_", " ").upper()
    stored_state = str(gate.get("stored_state") or gate.get("state") or "unknown").replace("_", " ").upper()
    rule = str(gate.get("confirm_rule") or gate.get("note") or "gate must confirm").strip()
    level = _gate_level_text(gate)
    blocks = _dh._gate_blocks_action(gate)  # local module helper; keeps render semantics aligned with data health
    price = _coerce_float(gate.get("live_price"))
    basis = str(gate.get("price_type") or "").strip()
    if price is None:
        price, basis = _lookup_gate_price(feed, symbol)
    source_tail = "; ".join(part for part in (f"source {source}" if source else "", f"stated {stated}" if stated else "") if part)

    if not blocks:
        return {
            "label": f"{symbol} context",
            "status": "context",
            "summary": f"Context only: {str(gate.get('note') or rule).strip()} ({source_tail or 'source not checked'}).",
        }
    if str(gate.get("state") or "").lower() == "green":
        if stored_state != "GREEN" and price is not None:
            level_text = f" clears {level}" if level else ""
            return {
                "label": f"{symbol} gate",
                "status": "ok",
                "summary": (
                    f"Price condition now MET: {symbol} {basis or 'price'} {price:.2f}{level_text}; "
                    f"stored gate was {stored_state.lower()} from {stated or 'unknown date'}."
                ),
            }
        return {
            "label": f"{symbol} gate",
            "status": "ok",
            "summary": f"Gate confirmed: {rule} ({source_tail or 'source not checked'}).",
        }
    if price is not None:
        result = te.evaluate_gate(gate, price, price_type=basis or "live")
        suggested = str(result.get("suggested_state") or "").lower()
        if suggested == "green":
            level_text = f" clears {level}" if level else ""
            return {
                "label": f"{symbol} gate",
                "status": "warn",
                "summary": (
                    f"Condition now appears MET: {symbol} {basis or 'price'} {price:.2f}{level_text}; "
                    "reconfirm to unlock full size."
                ),
            }
        return {
            "label": f"{symbol} gate",
            "status": "warn",
            "summary": (
                f"Capped to stage-only until {rule}. Last {basis or 'price'} {price:.2f}; "
                f"gate still {state.lower()} ({source_tail or 'source not checked'})."
            ),
        }
    return {
        "label": f"{symbol} gate",
        "status": "warn",
        "summary": (
            f"Capped to stage-only until {rule}. Not live-rechecked in this render; "
            f"gate still {state.lower()} ({source_tail or 'source not checked'})."
        ),
    }


def _evaluate_gates_for_render(feed: dict[str, Any], gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluated: list[dict[str, Any]] = []
    for gate in gates or []:
        if not isinstance(gate, dict):
            continue
        next_gate = dict(gate)
        next_gate["stored_state"] = gate.get("state")
        symbol = str(gate.get("symbol") or "").upper()
        price, basis = _lookup_gate_price(feed, symbol)
        if price is None:
            next_gate["live_evaluation"] = {
                "status": "not_checked",
                "why": "no current price available to re-evaluate this render",
            }
            evaluated.append(next_gate)
            continue
        result = te.evaluate_gate(gate, price, price_type=basis or "live")
        next_gate["live_price"] = price
        next_gate["price_type"] = basis or "live"
        next_gate["live_evaluation"] = {
            "status": "checked",
            "suggested_state": result.get("suggested_state"),
            "changed": bool(result.get("changed")),
            "why": result.get("why"),
        }
        suggested = str(result.get("suggested_state") or "").strip()
        if suggested:
            next_gate["state"] = suggested
        evaluated.append(next_gate)
    return evaluated


def _card_gate_notes(card: dict[str, Any], gates: list[dict[str, Any]], feed: dict[str, Any]) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    for gate in gates or []:
        if _gate_applies_to_card(gate, card):
            notes.append(_gate_card_note(gate, feed))
    return notes


def _health_item(data_health: dict[str, Any], source: str) -> dict[str, Any] | None:
    for item in data_health.get("items") or []:
        if isinstance(item, dict) and item.get("source") == source:
            return item
    return None


def _trust_rank(status: str) -> int:
    return {"ok": 0, "info": 1, "warn": 2, "alert": 3}.get(status, 1)


def _automation_trust_item() -> dict[str, str]:
    proof_path = SRC / "cloud_automation_status.json"
    receipt_path = SRC / "cloud_routine_receipts.json"
    if not proof_path.exists():
        return {
            "label": "Automations",
            "status": "warn",
            "detail": "automation proof file not checked in this render",
        }
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"label": "Automations", "status": "alert", "detail": "automation proof file unreadable"}
    routines = [
        row for row in proof.get("routines") or []
        if isinstance(row, dict) and str(row.get("status") or "").upper() == "ACTIVE"
    ]
    expected = crr.proof_required_automations(routines)
    if not expected:
        return {"label": "Automations", "status": "warn", "detail": "no core scheduled routines listed as active"}
    try:
        receipts = crr.load_receipts(receipt_path)
        summary = crr.summarize_receipts(receipts, expected_automations=expected)
    except Exception as exc:
        return {"label": "Automations", "status": "alert", "detail": f"routine receipts unreadable: {type(exc).__name__}"}
    expected_count = int(summary.get("expected_count") or 0)
    scheduled = int(summary.get("scheduled_success_count") or 0)
    failed = int(summary.get("failed_latest_count") or 0)
    missing = int(summary.get("missing_scheduled_success_count") or 0)
    if failed:
        return {"label": "Automations", "status": "alert", "detail": f"{failed} latest scheduled routine receipt failed"}
    if missing:
        return {
            "label": "Automations",
            "status": "alert",
            "detail": f"scheduled proof {scheduled}/{expected_count}; {missing} core routine(s) not proven",
        }
    return {"label": "Automations", "status": "ok", "detail": f"scheduled proof {scheduled}/{expected_count}"}


def _build_trust_panel(data_health: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    calibration = _health_item(data_health, "source_call_calibration")
    track = _health_item(data_health, "track_record")
    if calibration and calibration.get("status") in {"behind", "stale", "missing"}:
        items.append({
            "label": "Source scoring",
            "status": "alert",
            "detail": str(calibration.get("detail") or "source-call calibration is stale"),
        })
    elif not track or track.get("status") in {"empty", "missing"}:
        items.append({
            "label": "Source scoring",
            "status": "alert",
            "detail": "Source scoring is OFF - no graded track record yet, so analyst calls are not moving any score.",
        })
    elif track.get("status") == "fresh":
        items.append({"label": "Source scoring", "status": "ok", "detail": str(track.get("detail") or "graded track record loaded")})
    else:
        items.append({"label": "Source scoring", "status": "warn", "detail": str((track or {}).get("detail") or "not checked")})

    items.append(_automation_trust_item())

    fs = _health_item(data_health, "fs_inbox")
    if not fs:
        items.append({"label": "FS inbox", "status": "warn", "detail": "not checked this render"})
    elif fs.get("status") == "fresh":
        items.append({"label": "FS inbox", "status": "ok", "detail": str(fs.get("detail") or "checked")})
    elif fs.get("status") == "behind":
        items.append({"label": "FS inbox", "status": "alert", "detail": str(fs.get("detail") or "behind")})
    else:
        items.append({"label": "FS inbox", "status": "warn", "detail": str(fs.get("detail") or fs.get("status") or "not checked")})

    core = [
        row for row in data_health.get("items") or []
        if isinstance(row, dict) and row.get("source") in _TRUST_HEALTH_SOURCES
    ]
    bad = [row for row in core if row.get("status") in {"behind", "stale", "missing"}]
    soft = [row for row in core if row.get("status") in {"aging", "empty", "not_checked"}]
    if bad:
        detail = "; ".join(f"{row.get('label')}: {row.get('detail')}" for row in bad[:3])
        items.append({"label": "Core data", "status": "alert", "detail": detail})
    elif soft:
        detail = "; ".join(f"{row.get('label')}: {row.get('detail')}" for row in soft[:3])
        items.append({"label": "Core data", "status": "warn", "detail": detail})
    elif core:
        labels = ", ".join(str(row.get("label") or row.get("source")) for row in core[:5])
        items.append({"label": "Core data", "status": "ok", "detail": f"{labels} fresh"})
    else:
        items.append({"label": "Core data", "status": "warn", "detail": "freshness not checked"})

    worst = max(items, key=lambda row: _trust_rank(row.get("status", "info")))
    source = next((row for row in items if row["label"] == "Source scoring"), None)
    headline = source["detail"] if source and source["status"] == "alert" else worst["detail"]
    return {"status": worst.get("status", "info"), "headline": headline, "items": items}


def _card_action_direction(card: dict[str, Any]) -> str:
    move = (card.get("decision_card") or {}).get("move") or {}
    direction = str(move.get("direction") or card.get("direction") or "").upper()
    return "TRIM" if direction == "REDUCE" else direction


def _opposes_action(direction: str, action: str) -> bool:
    direction = str(direction or "").lower()
    action = str(action or "").upper()
    if action == "BUY":
        return direction == "bear"
    if action in {"TRIM", "SELL"}:
        return direction == "bull"
    return False


def _group_display_rows(groups: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in (groups or {}).items():
        try:
            points = round(float(value), 3)
        except (TypeError, ValueError):
            points = 0.0
        direction = "bull" if points > 0 else "bear" if points < 0 else "neutral"
        rows.append({
            "key": key,
            "label": _GROUP_LABELS.get(key, str(key).replace("_", " ").title()),
            "points": points,
            "direction": direction,
        })
    rows.sort(key=lambda row: (abs(row["points"]), row["label"]), reverse=True)
    return rows


def _factor_display_rows(factors: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for factor in factors or []:
        if not isinstance(factor, dict):
            continue
        row = dict(factor)
        row["conflict"] = bool(
            factor.get("direction") in {"bull", "bear"}
            and _opposes_action(str(factor.get("direction") or ""), action)
        )
        rows.append(row)
    rows.sort(
        key=lambda row: (
            bool(row.get("conflict")),
            bool(row.get("decisive")),
            float(row.get("strength") or 0.0),
        ),
        reverse=True,
    )
    return rows


def _layer_points_text(points: Any) -> str:
    try:
        value = float(points or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return f"{value:+.2f}"


def _conviction_layer_display(layers: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(layers, dict) or layers.get("mode") in {None, "off"}:
        return {"mode": "off", "rows": []}
    name = layers.get("name") or {}
    sector = layers.get("sector") or {}
    overall = layers.get("overall") or {}
    rows = [
        {
            "key": "name",
            "label": "Name-specific",
            "status": name.get("status") or "not_checked",
            "points": name.get("points") or 0.0,
            "read": name.get("read") or "LOW",
            "direction": name.get("direction") or "NEUTRAL",
            "detail": "direct ticker evidence",
        },
        {
            "key": "sector",
            "label": "Sector/sleeve",
            "status": sector.get("status") or "not_checked",
            "points": sector.get("points") or 0.0,
            "read": sector.get("read") or "LOW",
            "direction": sector.get("direction") or "NEUTRAL",
            "detail": sector.get("category") or sector.get("sleeve") or "",
        },
        {
            "key": "overall",
            "label": "Shadow overall",
            "status": "shadow",
            "points": overall.get("points_decimal", overall.get("points", 0.0)),
            "read": overall.get("read") or "LOW",
            "direction": overall.get("direction") or "NEUTRAL",
            "detail": (
                f"sector lift {_layer_points_text(overall.get('sector_lift'))} "
                f"(cap {float(overall.get('sector_lift_cap') or 0.0):.2f})"
            ),
        },
    ]
    return {
        "mode": layers.get("mode") or "shadow",
        "formula_version": (overall.get("formula_version") or "shadow_v1"),
        "rows": rows,
        "conflict": overall.get("conflict"),
        "clamped_reasons": list(overall.get("clamped_reasons") or []),
        "sector_only_recheck": overall.get("sector_only_recheck"),
    }


def _display_band_color(action: str, band: str, conflict: str | None) -> str:
    if conflict:
        return "#fb923c"
    colors = _SELL_BAND_COLORS if str(action or "").upper() in {"TRIM", "SELL"} else _BAND_COLORS
    return colors.get(str(band or "").upper(), "#94a3b8")


def build_conviction_display(card: dict[str, Any]) -> dict[str, Any]:
    """Build the one render-ready conviction display consumed by all renderers."""
    conviction = card.get("conviction") or {}
    battery = conviction.get("battery") or {}
    summary = battery.get("battery_summary") or {}
    action = _card_action_direction(card)
    label = ce.conviction_label(
        action,
        {**conviction, "ticker": conviction.get("ticker") or card.get("ticker")},
    )
    factors = _factor_display_rows(summary.get("decisive_factors") or [], action)

    conflict = str(label.get("conflict_note") or "").strip() or None
    opposing = [
        row for row in factors
        if row.get("conflict") and (row.get("decisive") or float(row.get("strength") or 0.0) >= 0.7)
    ]
    if opposing and not conflict:
        labels = ", ".join(str(row.get("label") or row.get("key")) for row in opposing[:2])
        conflict = f"decisive battery evidence opposes this {action or 'action'} setup: {labels}"
    elif opposing and conflict and "battery" not in conflict.lower():
        conflict = f"{conflict}; battery opposition: {opposing[0].get('label') or opposing[0].get('key')}"
    if card.get("conflicts") and not conflict:
        conflict = "source conflict present; resolve before action"

    band = str(label.get("band") or "LOW").upper()
    iv_hint = summary.get("iv_hint") or battery.get("iv_hint") or {
        "status": "not_checked",
        "value": "not_checked",
        "hint": "IV options-vs-shares hint not checked",
    }
    if isinstance(iv_hint, dict) and "status" not in iv_hint:
        why = str(iv_hint.get("why") or iv_hint.get("hint") or "")
        status = "not_checked" if "not_checked" in why else "checked"
        iv_hint = {**iv_hint, "status": status, "hint": iv_hint.get("hint") or why}
    return {
        "text": label.get("text") or "",
        "x5": int(label.get("x5") or 1),
        "band": band,
        "band_color": _display_band_color(action, band, conflict),
        "conflict": conflict,
        "why": {
            "groups": _group_display_rows(conviction.get("groups") or {}),
            "decisive_factors": factors,
        },
        "layers": _conviction_layer_display(conviction.get("conviction_layers") or {}),
        "raises": list(conviction.get("raises") or []),
        "iv_hint": iv_hint,
        "not_checked": list(conviction.get("not_checked") or []),
    }


def attach_conviction_displays(cards: list[dict[str, Any]]) -> None:
    for card in cards or []:
        if isinstance(card, dict):
            card["conviction_display"] = build_conviction_display(card)


def _fed_day_packet(feed: dict[str, Any]) -> dict[str, Any]:
    packet = feed.get("fed_day_reallocation_packet") or {}
    return packet if isinstance(packet, dict) else {}


def _date_string(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return ""


def _fed_day_freshness(feed: dict[str, Any], today_iso: str) -> dict[str, Any]:
    packet = _fed_day_packet(feed)
    if not packet:
        return {
            "packet": {},
            "freshness": "absent",
            "packet_as_of": None,
            "caption": "Fed-day packet not_checked - no packet on disk; no pullback rows fabricated.",
            "honesty": "not_checked - no packet on disk",
        }
    as_of_raw = str(packet.get("as_of") or "").strip()
    as_of = _date_string(as_of_raw)
    today_day = _date_string(today_iso) or today_iso
    if as_of and as_of == today_day:
        return {
            "packet": packet,
            "freshness": "fresh",
            "packet_as_of": as_of,
            "caption": f"Fed-day packet current as of {as_of}. Research/recheck rows stay rail-free until separately confirmed.",
            "honesty": "",
        }
    display_as_of = as_of or as_of_raw or "unknown"
    return {
        "packet": packet,
        "freshness": "stale",
        "packet_as_of": display_as_of,
        "caption": f"Fed-day packet STALE/not_checked as of {display_as_of}; rows are research context only and prices are not current.",
        "honesty": f"stale (as_of {display_as_of}) - research context only, prices not current",
    }


def _fed_day_rows_by_ticker(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packet = state.get("packet") or {}
    out: dict[str, dict[str, Any]] = {}
    labels = {
        "act_if_green": "Fed-day act-if-green packet",
        "higher_quality_pullbacks": "Higher-quality pullback",
        "deep_discount_research": "Deep-discount research",
    }
    for section, label in labels.items():
        for row in packet.get(section) or []:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").upper()
            if ticker and ticker not in out:
                out[ticker] = {
                    "section": section,
                    "label": label,
                    "row": row,
                    "freshness": state.get("freshness") or "absent",
                    "packet_as_of": state.get("packet_as_of"),
                }
    return out


def _attach_fed_day_context(cards: list[dict[str, Any]], state: dict[str, Any]) -> None:
    by_ticker = _fed_day_rows_by_ticker(state)
    for card in cards or []:
        ticker = str(card.get("ticker") or "").upper()
        if ticker in by_ticker:
            card["fed_day_context"] = by_ticker[ticker]


def _coerce_money(value: Any) -> float | None:
    parsed = _coerce_float(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _band_text(band: Any) -> str:
    if isinstance(band, dict):
        low = _coerce_money(band.get("low"))
        high = _coerce_money(band.get("high"))
        if low is not None and high is not None:
            if abs(low - high) < 0.5:
                return f"${high:,.0f}"
            return f"${low:,.0f}-${high:,.0f}"
        if high is not None:
            return f"up to ${high:,.0f}"
        if low is not None:
            return f"from ${low:,.0f}"
    parsed = _coerce_money(band)
    return f"${parsed:,.0f}" if parsed is not None else ""


def _fed_day_card_summary(context: dict[str, Any]) -> str:
    row = context.get("row") or {}
    section = str(context.get("section") or "")
    freshness = str(context.get("freshness") or "fresh")
    packet_as_of = str(context.get("packet_as_of") or "").strip()
    if section == "act_if_green":
        band = _band_text(row.get("dollar_band"))
        first = _band_text(row.get("green_first_tranche"))
        gate = str(row.get("gate_status") or "green/amber/red gate must be reviewed").strip()
        parts = [
            f"Candidate band {band}" if band else "",
            f"first tranche {first}" if first else "",
            gate,
        ]
        return "; ".join(part for part in parts if part)
    discount = _coerce_float(row.get("pct_below_high"))
    price = _coerce_money(row.get("price"))
    if price is not None and freshness == "stale":
        price_text = f"price ${price:,.0f} as of {packet_as_of or 'unknown'} - STALE, research context only"
    elif price is not None:
        price_text = f"price ${price:,.0f}"
    else:
        price_text = ""
    sources = ", ".join(str(tag) for tag in row.get("source_tags") or [] if tag) or str(row.get("source") or "chart/source screen")
    bits = [
        f"{discount:.1f}% below 52w high" if discount is not None else "",
        price_text,
        sources,
    ]
    return "; ".join(bit for bit in bits if bit)


def _build_fed_day_watch_queue(state: dict[str, Any], cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packet = state.get("packet") or {}
    if not packet:
        return []
    existing = {str(card.get("ticker") or "").upper() for card in cards or []}
    queue: list[dict[str, Any]] = []
    section_meta = {
        "act_if_green": ("Act-if-green candidate", 0),
        "higher_quality_pullbacks": ("Higher-quality pullback", 1),
        "deep_discount_research": ("Deep-discount research", 2),
    }
    for section, (label, bucket) in section_meta.items():
        for row in packet.get(section) or []:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").upper()
            if not ticker or ticker in existing:
                continue
            rank_score = _coerce_float(row.get("rank_score"))
            exposure = _coerce_money(row.get("current_exposure_usd"))
            discount = _coerce_float(row.get("pct_below_high"))
            impact_score = (
                rank_score if rank_score is not None
                else min(100.0, abs(discount or 0.0) + min((exposure or 0.0) / 10_000.0, 20.0))
            )
            queue.append({
                "ticker": ticker,
                "section": section,
                "label": label,
                "bucket": bucket,
                "impact_score": round(float(impact_score), 2),
                "status": str(row.get("status") or "not_checked"),
                "research_status": str(row.get("research_status") or ""),
                "summary": _fed_day_card_summary({
                    "section": section,
                    "row": row,
                    "freshness": state.get("freshness") or "absent",
                    "packet_as_of": state.get("packet_as_of"),
                }),
                "disconfirmation": str(row.get("disconfirmation") or ""),
                "price": row.get("price"),
                "pct_below_high": row.get("pct_below_high"),
                "current_exposure_usd": row.get("current_exposure_usd"),
                "source_tags": list(row.get("source_tags") or []),
                "freshness": state.get("freshness") or "absent",
                "packet_as_of": state.get("packet_as_of"),
            })
    queue.sort(key=lambda row: (int(row["bucket"]), -float(row["impact_score"]), str(row["ticker"])))
    return queue


def build_today_decide_payload(
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
    orphan_honesty: dict[str, Any] | None = None,
    congruence_result: dict[str, Any] | None = None,
    dispositions_path: Path | str = disposition_log.DISPOSITIONS_PATH,
    today: str | None = None,
) -> dict[str, Any]:
    feed = _load_feed(feed)
    today_iso = today or date.today().isoformat()
    insights_payload = insights_payload or ir.load_insights()
    gates = gates if gates is not None else te.load_gates()
    gates = _evaluate_gates_for_render(feed, gates)
    stack = dr.build_directive_cards(
        feed=feed, weights=weights, goal=goal, insights_payload=insights_payload,
        accounts=accounts, gates=gates, uw_states=uw_states, entry_zones=entry_zones,
        rates=rates,
        extra_cards=extra_cards, extra_fs_items=extra_fs_items, inst_states=inst_states,
        today=today_iso,
    )
    if congruence_result is None:
        congruence_result = cg.congruence_from_repo(insights_payload, weights=weights, today=today_iso)
    recheck = (date.fromisoformat(today_iso)
               + timedelta(days=int(goal["recheck_default_days"]))).isoformat()
    last = disposition_log.last_dispositions(dispositions_path)
    for card in stack["cards"] + stack["backlog"]:
        card["conflicts"] = detect_source_conflicts(feed, card)
        disclosure = ltd.card_lookthrough_disclosure(card, accounts=accounts, feed=feed)
        if disclosure:
            card["lookthrough"] = disclosure
        card["recheck_date"] = recheck
        card["last_disposition"] = last.get(card["card_id"])
    data_health = _dh.assess(
        feed,
        gates=gates,
        cards=stack["cards"] + stack["backlog"],
        now=_today(today_iso),
    )
    for card in stack["cards"] + stack["backlog"]:
        card["card_blockers"] = _card_blockers(card, data_health, gates)
        card["gate_notes"] = _card_gate_notes(card, gates, feed)
    all_cards = stack["cards"] + stack["backlog"]
    attach_conviction_displays(all_cards)
    fed_day_state = _fed_day_freshness(feed, today_iso)
    _attach_fed_day_context(all_cards, fed_day_state)
    honesty = dict(stack["honesty"])
    if fed_day_state.get("honesty"):
        honesty["fed_day_packet"] = fed_day_state["honesty"]
    if congruence_result.get("status") != "ok":
        honesty["congruence"] = congruence_result.get("reason", "not checked")
    if not last:
        honesty["dispositions"] = "none logged yet (C6 spine pending)"
    if orphan_honesty:
        for key, value in orphan_honesty.items():
            honesty.setdefault(f"orphan_wiring_{key}", value)
    rb = feed.get("reallocation_brief") or {}
    funding = stack.get("funding") or {}
    return {
        "built": today_iso,
        "goal_anchor": _goal_anchor(feed, goal, today_iso),
        "plan_line": {
            "pool_usd": funding.get("pool_usd"),
            "shortfall_usd": funding.get("shortfall_usd"),
            "positions_as_of": rb.get("positions_snapshot_date"),
        },
        "gates": [
            {k: g.get(k) for k in (
                "gate_id", "symbol", "state", "stored_state", "note", "confirm_rule",
                "stated", "live_price", "price_type", "live_evaluation",
            )}
            for g in gates
        ],
        "data_health": data_health,
        "trust_panel": _build_trust_panel(data_health),
        "cards": stack["cards"],
        "backlog": stack["backlog"],
        "watch_queue": _build_fed_day_watch_queue(fed_day_state, all_cards),
        "watch_queue_meta": {
            "freshness": fed_day_state.get("freshness") or "absent",
            "packet_as_of": fed_day_state.get("packet_as_of"),
            "caption": fed_day_state.get("caption") or "",
        },
        "fed_day_do_not_touch": [
            str(row) for row in ((fed_day_state.get("packet") or {}).get("do_not_touch_yet") or []) if row
        ],
        "congruence": congruence_result,
        "honesty": honesty,
    }

# ---------------------------------------------------------------------------
# HTML renderer â€” scoped, self-contained, zero network
# ---------------------------------------------------------------------------
_CSS = """
<style>
.td{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#0b1220;color:#e2e8f0;
  border:1px solid #1e293b;border-radius:12px;padding:18px;margin:0 0 18px 0}
.td h2{margin:0 0 4px 0;font-size:20px;letter-spacing:.04em}
.td .td-anchor{font-size:17px;margin:8px 0 2px 0}
.td .td-pace{color:#94a3b8;font-style:italic;font-size:11px;margin:0 0 10px 0}
.td .td-plan{color:#cbd5e1;font-size:13px;margin:0 0 10px 0}
.td .td-verdict{border:1px solid #334155;border-left:4px solid #38bdf8;border-radius:10px;
  background:#08111f;padding:10px 12px;margin:10px 0 12px}
.td .td-verdict-title{font-size:15px;color:#f8fafc;font-weight:850;margin-bottom:3px}
.td .td-verdict-line{font-size:12px;color:#cbd5e1;line-height:1.4}
.td .td-trust{border:1px solid #334155;border-radius:10px;background:#08111f;padding:10px 12px;margin:10px 0 12px}
.td .td-trust-alert{border-color:#f87171;background:#1f0d12}
.td .td-trust-warn{border-color:#fbbf24;background:#1b1607}
.td .td-trust-ok{border-color:#34d399;background:#071910}
.td .td-trust-head{font-size:15px;color:#f8fafc;font-weight:900;margin-bottom:8px}
.td .td-trust-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px}
.td .td-trust-item{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:8px}
.td .td-trust-label{font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:900;letter-spacing:.06em}
.td .td-trust-detail{font-size:13px;color:#e2e8f0;line-height:1.35;margin-top:3px}
.td .td-card{border:1px solid #243044;border-radius:10px;padding:12px;margin:10px 0;background:#0f172a}
.td .td-card.td-conflicted{border-color:#f59e0b}
.td details.td-card{padding:0}
.td details.td-card>summary{list-style:none;cursor:pointer;padding:12px;display:block}
.td details.td-card>summary::-webkit-details-marker{display:none}
.td .td-card-face{display:grid;gap:8px}
.td .td-face-top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.td .td-rank{font-size:12px;color:#94a3b8;font-weight:800;letter-spacing:.04em;text-transform:uppercase}
.td .td-face-status{font-size:12px;font-weight:900;letter-spacing:.06em;text-transform:uppercase}
.td .td-face-title{font-size:20px;font-weight:850;line-height:1.18;margin:1px 0;color:#f8fafc}
.td .td-face-subtitle{font-size:13px;color:#cbd5e1;line-height:1.35}
.td .td-face-sentence{font-size:14px;color:#e2e8f0;line-height:1.4;margin-top:7px;max-width:760px}
.td .td-face-gate{font-size:12px;color:#fde68a;line-height:1.35;margin-top:6px;max-width:760px}
.td .td-face-right{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;min-width:150px}
.td .td-face-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.td .td-score-chip{display:inline-flex;align-items:center;border-radius:999px;padding:4px 9px;font-size:12px;
  font-weight:850;color:#0b1220;white-space:nowrap}
.td .td-score-full{font-size:11px;color:#94a3b8}
.td .td-size-chip{display:inline-flex;align-items:center;border-radius:999px;padding:4px 9px;font-size:12px;
  font-weight:850;border:1px solid #334155;background:#0b1220;color:#cbd5e1;white-space:nowrap}
.td .td-size-material{border-color:#38bdf8;color:#bfdbfe;background:#061321}
.td .td-size-muted{border-color:#475569;color:#94a3b8;background:#0b1220}
.td .td-layer-line{font-size:12px;color:#a5b4fc;line-height:1.35;margin-top:4px}
.td .td-main-blocker{font-size:12px;color:#fde68a;line-height:1.35;margin-top:3px}
.td .td-face-tags{display:flex;flex-wrap:wrap;gap:6px}
.td .td-tag{display:inline-flex;align-items:center;border-radius:999px;border:1px solid #334155;
  color:#cbd5e1;background:#0b1220;padding:3px 8px;font-size:12px;font-weight:650}
.td .td-tag-warn{border-color:#f59e0b;color:#fde68a;background:#1f1606}
.td .td-tag-danger{border-color:#ef4444;color:#fecaca;background:#220b0b}
.td .td-tag-muted{border-color:#334155;color:#94a3b8}
.td .td-body{padding:10px 12px 12px 12px;border-top:1px solid #1e293b;margin-top:8px}
.td .td-readout{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:10px;margin:0 0 10px}
.td .td-readout-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}
.td .td-readout-k{font-size:10px;color:#94a3b8;font-weight:900;letter-spacing:.06em;text-transform:uppercase}
.td .td-readout-v{font-size:14px;color:#f8fafc;font-weight:750;margin-top:2px;line-height:1.3}
.td .td-section-title{font-size:11px;color:#94a3b8;font-weight:850;letter-spacing:.06em;text-transform:uppercase;margin:12px 0 6px}
.td .td-why-item{font-size:13px;color:#cbd5e1;margin:4px 0;line-height:1.35}
.td .td-why-item strong{color:#e2e8f0}
.td .td-factor-conflict{color:#fdba74}
.td .td-evidence-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}
.td .td-evidence{border:1px solid #334155;border-radius:8px;padding:8px;background:#0b1220}
.td .td-evidence-warn{border-color:#f59e0b;background:#1f1606}
.td .td-evidence-stale{border-color:#475569;background:#0b1220;opacity:.74}
.td .td-evidence-label{font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:900;letter-spacing:.05em}
.td .td-evidence-title{font-size:13px;color:#f8fafc;font-weight:800;margin-top:2px}
.td .td-evidence-text{font-size:12px;color:#cbd5e1;line-height:1.35;margin-top:3px}
.td .td-evidence-note{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:8px;
  font-size:13px;color:#cbd5e1;line-height:1.4;margin:0 0 8px}
.td .td-gate-note{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:8px;
  font-size:13px;color:#cbd5e1;line-height:1.4;margin:0 0 8px}
.td .td-gate-note-ok{border-color:#34d399;color:#bbf7d0;background:#071910}
.td .td-gate-note-warn{border-color:#fbbf24;color:#fde68a;background:#1b1607}
.td .td-layer-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}
.td .td-layer-card{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:8px}
.td .td-layer-label{font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:900;letter-spacing:.05em}
.td .td-layer-value{font-size:14px;color:#f8fafc;font-weight:800;margin-top:2px}
.td .td-layer-detail{font-size:12px;color:#cbd5e1;line-height:1.35;margin-top:3px}
.td .td-layer-compact{border:1px solid #334155;border-radius:8px;background:#0b1220;
  padding:8px;font-size:13px;color:#cbd5e1;line-height:1.35}
.td .td-action-columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
.td .td-action-column{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:8px}
.td .td-action-column-title{font-size:10px;color:#94a3b8;font-weight:900;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px}
.td .td-card-section-title{font-size:11px;color:#94a3b8;text-transform:uppercase;font-weight:900;
  letter-spacing:.08em;margin:14px 0 5px}
.td .td-subqueue{border-top:1px solid #1e293b;margin-top:14px;padding-top:10px}
.td .td-queue-card{border:1px solid #334155;border-radius:9px;background:#07101e;padding:10px;margin:8px 0}
.td .td-queue-top{display:flex;gap:8px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.td .td-queue-rank{font-size:14px;font-weight:900;color:#f8fafc}
.td .td-queue-label{font-size:10px;color:#93c5fd;text-transform:uppercase;font-weight:900;letter-spacing:.06em;margin-bottom:3px}
.td .td-queue-summary{font-size:13px;color:#cbd5e1;line-height:1.4;margin-top:4px}
.td .td-queue-meta{font-size:12px;color:#94a3b8;line-height:1.4;margin-top:5px}
.td .td-queue-score{font-size:12px;color:#f8fafc;border:1px solid #334155;border-radius:999px;padding:3px 7px;background:#0f172a}
.td .td-pill{display:inline-block;border-radius:6px;padding:1px 8px;font-size:12px;
  font-weight:600;margin-left:8px;color:#0b1220}
.td .td-row{font-size:13px;color:#cbd5e1;margin:4px 0}
.td .td-chip{border:1px solid #f59e0b;color:#fdba74;border-radius:8px;padding:6px 8px;
  font-size:12px;margin:6px 0}
.td .td-dossier{border:1px solid #334155;border-radius:8px;padding:8px;margin:8px 0;background:#0b1220}
.td .td-dossier-head{font-size:12px;color:#e2e8f0;font-weight:800;margin-bottom:4px}
.td .td-dossier-meta{font-size:11px;color:#94a3b8;margin:2px 0 6px}
.td .td-dossier-read{font-size:12px;color:#cbd5e1;margin:3px 0}
.td .td-dossier-read strong{color:#e2e8f0}
.td .td-muted-details{border:1px solid #243044;border-radius:8px;background:#0b1220;padding:8px;margin:8px 0}
.td .td-muted-details>summary{cursor:pointer;color:#94a3b8;font-size:12px;font-weight:750}
.td details{margin:4px 0;font-size:12px;color:#94a3b8}
.td .td-health{margin:8px 0 4px 0;line-height:2}
.td .td-health-compact{display:none}
.td .td-compact-strip{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:7px 9px;margin:6px 0;color:#cbd5e1}
.td .td-compact-strip>summary{cursor:pointer;font-size:12px;font-weight:800;color:#e2e8f0}
.td .td-compact-body{margin-top:7px;line-height:1.8}
.td .td-hlabel{font-size:11px;color:#64748b;font-weight:700;letter-spacing:.03em}
.td .td-hchip{display:inline-block;border:1px solid;border-radius:7px;padding:1px 7px;font-size:11px;color:#cbd5e1;margin:0 4px 4px 0;background:#0b1220}
.td .td-checkfirst{color:#f87171;font-weight:700;font-size:12px;margin-bottom:6px;letter-spacing:.03em}
.td .td-rail{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;
  padding:6px 12px;margin:6px 8px 0 0;cursor:pointer;font-size:13px}
.td .td-rail-muted{background:#111827;color:#cbd5e1;border-color:#64748b}
.td .td-rail.td-on{background:#34d399;color:#0b1220;font-weight:700}
.td .td-rail.td-copy-fail{background:#7f1d1d;color:#fecaca;border-color:#ef4444;font-weight:700}
.td .td-cong{font-size:13px;margin:3px 0}
.td .td-honesty{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#94a3b8;
  border-top:1px solid #1e293b;margin-top:12px;padding-top:8px}
@media (max-width: 620px){
  .td{padding:12px}
  .td .td-anchor{font-size:16px}
  .td .td-pace{font-size:10px;margin-bottom:8px}
  .td .td-plan{font-size:12px;margin-bottom:6px}
  .td .td-health-full{display:none}
  .td .td-health-compact{display:block}
  .td .td-face-top{display:block}
  .td .td-face-right{justify-content:flex-start;margin-top:7px}
  .td .td-face-title{font-size:18px}
  .td .td-readout-grid{grid-template-columns:1fr}
}
</style>
"""

_JS = """
<script>
function tdCopyFallback(t){var a=document.createElement('textarea');a.value=t;
a.setAttribute('readonly','');a.style.position='fixed';a.style.left='-9999px';a.style.top='0';
document.body.appendChild(a);a.focus();a.select();var ok=false;
try{ok=document.execCommand('copy');}catch(e){ok=false;}document.body.removeChild(a);return ok;}
async function tdCopy(t){if(navigator.clipboard&&navigator.clipboard.writeText){
try{await navigator.clipboard.writeText(t);return true;}catch(e){}}
return tdCopyFallback(t);}
async function tdRail(btn){var on=btn.getAttribute('data-on')==='1';var id=btn.getAttribute('data-card');
var verb=btn.getAttribute('data-verb');var text=on?'UNDO '+id:btn.getAttribute('data-copy');
btn.disabled=true;var ok=await tdCopy(text);btn.disabled=false;
if(!ok){btn.classList.add('td-copy-fail');btn.textContent='COPY FAILED (tap retry)';btn.title=text;return;}
btn.classList.remove('td-copy-fail');btn.title='';
if(!on){btn.setAttribute('data-on','1');btn.classList.add('td-on');btn.textContent=verb+' \u2713 (tap to undo)';}
else{btn.setAttribute('data-on','0');btn.classList.remove('td-on');btn.textContent=verb;}}
</script>
"""

def _esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_group_breakdown(display: dict[str, Any]) -> str:
    groups = ((display.get("why") or {}).get("groups") or [])
    if not groups:
        return '<div class="td-why-item">No scored group has moved the conviction yet.</div>'
    bits = []
    for row in groups:
        points = float(row.get("points") or 0.0)
        bits.append(
            f'<div class="td-why-item"><strong>{_esc(row.get("label") or row.get("key"))}</strong> '
            f'{points:+.2f}</div>'
        )
    return "".join(bits)


def _factor_dates(factors: list[dict[str, Any]]) -> list[str]:
    dates: set[str] = set()
    for row in factors:
        text = f"{row.get('value_str') or ''} {row.get('source') or ''}"
        for match in re.findall(r"20\d{2}-\d{2}-\d{2}", text):
            dates.add(match)
    return sorted(dates)


def _factor_as_of(row: dict[str, Any]) -> str | None:
    text = f"{row.get('value_str') or ''} {row.get('source') or ''}"
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    return match.group(0) if match else None


def _factor_is_stale_context(row: dict[str, Any], built_date: str | None) -> bool:
    if not built_date:
        return False
    key_source = str(row.get("key") or "") + " " + str(row.get("source") or "")
    if "uw_opportunity" not in key_source:
        return False
    as_of = _factor_as_of(row)
    return bool(as_of and as_of != built_date)


def _shown_not_counted_note(display: dict[str, Any], factors: list[dict[str, Any]], built_date: str | None = None) -> str:
    groups = ((display.get("why") or {}).get("groups") or [])
    group_points = sum(abs(float(row.get("points") or 0.0)) for row in groups)
    has_context_flow = any(
        "uw_opportunity" in str(row.get("key") or row.get("source") or "")
        for row in factors
    )
    needs_same_session = any(
        "same-session" in str(item).lower() or "uw proof" in str(item).lower()
        for item in display.get("raises") or []
    )
    if not factors or group_points >= 0.1 or not (has_context_flow or needs_same_session):
        return ""
    dates = _factor_dates(factors)
    date_text = ", ".join(dates) if dates else "earlier cached evidence"
    if any(_factor_is_stale_context(row, built_date) for row in factors):
        return (
            f"Stale context, not current edge: these UW signals are from {date_text}, not this session's "
            "9:40 gate. Treat them as already-played or expired until refreshed; they are not moving the score "
            "and should not pull action."
        )
    return (
        f"Shown but not counted: these signals are from {date_text} and have not been "
        "re-confirmed this session (9:40 gate), so they are context only and are not moving the score yet."
    )


def _factor_tag(row: dict[str, Any], card: dict[str, Any] | None, built_date: str | None = None) -> str:
    if _factor_is_stale_context(row, built_date):
        direction = str(row.get("direction") or "").lower()
        if direction in {"bull", "bear"}:
            return f"stale {_direction_signal_word(direction)} context"
        return "stale context"
    direction = str(row.get("direction") or "").lower()
    if card and _is_funding_leg(card) and direction in {"bull", "bear"}:
        return f"{_direction_signal_word(direction)} name signal"
    if row.get("conflict"):
        return "opposes card action"
    if direction in {"bull", "bear"}:
        return f"{_direction_signal_word(direction)} setup"
    return "context"


def _render_factor_breakdown(
    display: dict[str, Any],
    card: dict[str, Any] | None = None,
    *,
    built_date: str | None = None,
) -> str:
    factors = ((display.get("why") or {}).get("decisive_factors") or [])
    if not factors:
        return '<div class="td-why-item">Battery decisive factors: none surfaced.</div>'
    bits = []
    note = _shown_not_counted_note(display, factors, built_date)
    if note:
        bits.append(f'<div class="td-evidence-note">{_esc(note)}</div>')
    bits.append('<div class="td-evidence-grid">')
    for row in factors[:4]:
        stale = _factor_is_stale_context(row, built_date)
        cls = " td-evidence-stale" if stale else (" td-evidence-warn" if row.get("conflict") else "")
        tag = _factor_tag(row, card, built_date)
        bits.append(
            f'<div class="td-evidence{cls}">'
            f'<div class="td-evidence-label">{_esc(tag)}</div>'
            f'<div class="td-evidence-title">{_esc(row.get("label") or row.get("key"))}</div>'
            f'<div class="td-evidence-text">{_esc(_short_text(row.get("value_str") or "", 130))}</div>'
            '</div>'
        )
    bits.append('</div>')
    return "".join(bits)


def _render_layer_breakdown(display: dict[str, Any]) -> str:
    layers = display.get("layers") or {}
    rows = layers.get("rows") or []
    if not rows or layers.get("mode") == "off":
        return ""
    bits = ['<div class="td-section-title">Name / sector split</div>']
    if _layers_empty(display):
        return (
            "".join(bits)
            + '<div class="td-layer-compact">Name/sector evidence not fed yet; no positive layer is active.</div>'
        )
    bits.append('<div class="td-layer-grid">')
    for row in rows:
        status = row.get("status") or "not_checked"
        points = _layer_points_text(row.get("points"))
        detail = str(row.get("detail") or "").strip()
        bits.append(
            '<div class="td-layer-card">'
            f'<div class="td-layer-label">{_esc(row.get("label") or row.get("key"))}</div>'
            f'<div class="td-layer-value">{_esc(row.get("read") or "LOW")} {points}</div>'
            f'<div class="td-layer-detail">{_esc(status)}'
            + (f' | {_esc(detail)}' if detail else "")
            + '</div></div>'
        )
    bits.append('</div>')
    if layers.get("conflict"):
        bits.append(f'<div class="td-chip">Layer guard: {_esc(layers.get("conflict"))}</div>')
    for reason in layers.get("clamped_reasons") or []:
        bits.append(f'<div class="td-row">Layer guard: {_esc(reason)}</div>')
    recheck = layers.get("sector_only_recheck") or {}
    if recheck.get("eligible"):
        suffix = "alert disabled in shadow mode" if not recheck.get("alert_enabled") else "alert enabled"
        bits.append(
            f'<div class="td-row">Sector-only recheck: {_esc(recheck.get("next_step") or "re-check")} '
            f'({_esc(suffix)})</div>'
        )
    return "".join(bits)


def _render_iv_hint(display: dict[str, Any]) -> str:
    hint = display.get("iv_hint") or {}
    if not isinstance(hint, dict):
        return f'<div class="td-row">IV options-vs-shares: {_esc(hint)}</div>'
    text = hint.get("hint") or hint.get("value") or hint.get("status") or "not_checked"
    status = hint.get("status")
    prefix = "IV options-vs-shares"
    if status:
        prefix += f" ({_esc(status)})"
    return f'<div class="td-row">{prefix}: {_esc(text)}</div>'


def _short_text(value: Any, limit: int = 150) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _action_gerund(direction: str) -> str:
    direction = str(direction or "act").upper()
    return {
        "BUY": "buying",
        "ADD": "adding",
        "SELL": "selling",
        "TRIM": "trimming",
        "REDUCE": "trimming",
    }.get(direction, "acting on")


def _score_text(display: dict[str, Any]) -> str:
    label = str(display.get("text") or "")
    score_match = re.search(r"([1-5])\s*/\s*5", label)
    band_match = re.search(r"\((LOW|MODERATE|HIGH)\)", label, flags=re.IGNORECASE)
    x5 = display.get("x5")
    if x5 is None:
        x5 = score_match.group(1) if score_match else 1
    band = str(display.get("band") or (band_match.group(1) if band_match else "LOW")).upper()
    return f"Conviction {x5}/5 {band}"


def _money_text(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"${float(value):,.0f}"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "size n/a"


def _is_material(card: dict[str, Any]) -> bool:
    return bool((card.get("impact") or {}).get("material"))


def _is_funding_leg(card: dict[str, Any]) -> bool:
    direction = _card_action_direction(card).upper()
    if direction not in {"SELL", "TRIM", "REDUCE"}:
        return False
    win = card.get("window") or {}
    reasons = " ".join(str(row or "") for row in win.get("reasons") or []).lower()
    if "funding leg" in reasons or "paired with the adds" in reasons:
        return True
    execn = card.get("execution") or {}
    if execn.get("legs") and not _is_material(card):
        return True
    return False


def _size_label(card: dict[str, Any]) -> str:
    size = _money_text(card.get("dollars"))
    material = "material" if _is_material(card) else "immaterial"
    return f"{size} / {material}"


def _funding_sell_label(card: dict[str, Any]) -> str:
    return f"{_money_text(card.get('dollars'))} funding sell — only if paired with the buy it funds"


def _funded_adds(card: dict[str, Any]) -> list[dict[str, str]]:
    links = (((card.get("decision_card") or {}).get("evidence") or {}).get("links") or [])
    out: list[dict[str, str]] = []
    for link in links:
        label = str((link or {}).get("label") or "")
        if "funds" not in label.lower():
            continue
        match = re.search(r"\b([A-Z]{1,6})\b\s+\$?([0-9][0-9,]*(?:\.\d+)?)", label)
        if not match:
            continue
        out.append({"ticker": match.group(1), "amount": f"${match.group(2)}"})
    return out


def _funded_add_text(card: dict[str, Any]) -> str:
    adds = _funded_adds(card)
    if not adds:
        return "the paired add it funds"
    first = adds[0]
    return f"the {first['ticker']} {first['amount']} add"


def _direction_signal_word(direction: str) -> str:
    value = str(direction or "").lower()
    if value == "bull":
        return "bullish"
    if value == "bear":
        return "bearish"
    return "neutral"


def _strongest_directional_factor(display: dict[str, Any]) -> dict[str, Any] | None:
    factors = ((display.get("why") or {}).get("decisive_factors") or [])
    directional = [
        row for row in factors
        if str(row.get("direction") or "").lower() in {"bull", "bear"}
    ]
    if not directional:
        return None
    return sorted(
        directional,
        key=lambda row: (bool(row.get("decisive")), float(row.get("strength") or 0.0)),
        reverse=True,
    )[0]


def _name_signal_text(card: dict[str, Any], display: dict[str, Any]) -> str:
    factor = _strongest_directional_factor(display)
    if factor:
        word = _direction_signal_word(str(factor.get("direction") or ""))
        label = str(factor.get("label") or factor.get("key") or "evidence")
        return f"Name signal: {word} ({label})"
    groups = ((display.get("why") or {}).get("groups") or [])
    moved = [row for row in groups if abs(float(row.get("points") or 0.0)) >= 0.25]
    if moved:
        row = moved[0]
        direction = str(row.get("direction") or "neutral").lower()
        label = str(row.get("label") or row.get("key") or "source")
        return f"Name signal: {direction} ({label})"
    return "Name signal: not fed yet"


def _layer_status_word(row: dict[str, Any] | None) -> str:
    if not row:
        return "off"
    status = str(row.get("status") or "not_checked")
    direction = str(row.get("direction") or "NEUTRAL").upper()
    read = str(row.get("read") or "LOW").upper()
    points = abs(float(row.get("points") or 0.0))
    if status == "not_checked":
        return "unfed"
    if status == "checked_no_signal" or (points < 0.005 and direction == "NEUTRAL"):
        return "quiet"
    if status == "not_applicable":
        return "n/a"
    if direction in {"BUY", "BULL"}:
        return f"supportive {read}"
    if direction in {"SELL", "TRIM", "BEAR"}:
        return f"bearish {read}"
    return read


def _layer_rows(display: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layers = display.get("layers") or {}
    return {
        str(row.get("key") or ""): row
        for row in layers.get("rows") or []
        if isinstance(row, dict)
    }


def _layer_summary_text(display: dict[str, Any]) -> str:
    rows = _layer_rows(display)
    if not rows:
        return "Name/sector layer: off"
    return (
        f"Name: {_layer_status_word(rows.get('name'))} | "
        f"Sector: {_layer_status_word(rows.get('sector'))} | "
        f"Shadow: {str((rows.get('overall') or {}).get('read') or 'LOW').upper()}"
    )


def _layers_empty(display: dict[str, Any]) -> bool:
    layers = display.get("layers") or {}
    rows = layers.get("rows") or []
    if not rows or layers.get("mode") == "off" or layers.get("conflict"):
        return False
    name = next((row for row in rows if row.get("key") == "name"), {})
    sector = next((row for row in rows if row.get("key") == "sector"), {})
    actionable_statuses = {"active"}
    if name.get("status") in actionable_statuses or sector.get("status") in actionable_statuses:
        return False
    return all(abs(float(row.get("points") or 0.0)) < 0.005 for row in rows)


def _card_is_evidence_starved(card: dict[str, Any], display: dict[str, Any]) -> bool:
    groups = ((display.get("why") or {}).get("groups") or [])
    group_points = sum(abs(float(row.get("points") or 0.0)) for row in groups)
    rows = _layer_rows(display)
    name_status = str((rows.get("name") or {}).get("status") or "not_checked")
    missing = set(str(row) for row in display.get("not_checked") or [])
    return group_points < 0.1 and (name_status == "not_checked" or bool(missing))


def _primary_blocker_text(
    card: dict[str, Any],
    display: dict[str, Any],
    *,
    check_first: bool,
    window_class: str,
) -> str:
    if _is_funding_leg(card):
        return "Funding sell only; pair it with the add it pays for and do not sell the stock on its own."
    sizing = card.get("sizing") or {}
    if sizing.get("heat") == "ABOVE_CAP":
        return "Above cap; no size room until thesis/cap is revisited."
    if sizing.get("heat") == "CAP_CLIPPED":
        return "Cap clipped; staged size must stay within room."
    blockers = card.get("card_blockers") or []
    if blockers:
        return f"{blockers[0]} blocks full action."
    if display.get("conflict"):
        return str(display.get("conflict"))
    if window_class == "STAGE-ONLY":
        return "Stage only; wait for trigger before full action."
    return "No blocking reason surfaced."


def _face_sentence(
    card: dict[str, Any],
    display: dict[str, Any],
    *,
    status: str,
    blocker: str,
) -> str:
    ticker = str(card.get("ticker") or "").upper()
    if _is_funding_leg(card):
        factor = _strongest_directional_factor(display)
        paired = _funded_add_text(card)
        if str((factor or {}).get("direction") or "").lower() == "bull":
            return (
                f"Funding sell. Only do this alongside {paired}; "
                "the stock itself looks bullish on flow, so don't sell it on its own."
            )
        return f"Funding sell. Only do this alongside {paired}; don't sell it on its own."
    if status == "stage material buy":
        return f"Material buy candidate. Stage {ticker} only after the blocker clears: {blocker}"
    if status == "needs feed":
        return f"Not actionable yet. Feed the missing evidence first; {blocker}"
    if status == "resolve direction":
        return f"Do not act yet. Resolve the conflicting evidence first: {blocker}"
    if status == "stage only":
        return f"Stage-only candidate. Keep it queued until the trigger and blocker checks clear."
    if status == "lean-in candidate":
        return f"Lean-in candidate. Evidence is clear enough to consider action inside the stated rails."
    return f"Review first. {blocker}"


def _split_raise_actions(display: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    operator: list[str] = []
    waiting: list[str] = []
    system: list[str] = []
    for item in display.get("raises") or []:
        text = str(item)
        low = text.lower()
        if any(token in low for token in ("dated entry", "entry/stop/target", "tier a", "analyst call")):
            waiting.append(text)
        elif any(token in low for token in ("13f", "insider", "lane goes live", "uw proof", "same-session", "wired")):
            system.append(text)
        else:
            operator.append(text)
    if not operator:
        operator.append("Decide whether the surfaced signal is real enough to write or refresh the thesis.")
    if not system:
        system.append("No separate system wiring task surfaced for this card.")
    return operator[:3], waiting[:3], system[:3]


def _shadow_lift_text(display: dict[str, Any]) -> str:
    layers = display.get("layers") or {}
    for row in layers.get("rows") or []:
        if row.get("key") == "overall":
            detail = str(row.get("detail") or "").strip()
            if detail:
                return detail.replace("sector lift ", "shadow ")
    return "shadow layer present"


def _conflict_tags(display: dict[str, Any], card: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    conflict = str(display.get("conflict") or "").lower()
    if "battery" in conflict or "opposes" in conflict or "opposition" in conflict:
        tags.append("positive signal conflicts" if _is_funding_leg(card) else "flow opposes move")
    if "no directional evidence" in conflict:
        tags.append("no direct score support")
    if display.get("conflict") and not tags:
        tags.append("evidence conflict")
    if card.get("conflicts"):
        tags.append("another lane disagrees")
    return tags


def _card_face_model(
    card: dict[str, Any],
    display: dict[str, Any],
    posture: dict[str, str],
    *,
    check_first: bool,
    window_class: str,
    direction: str,
) -> dict[str, Any]:
    ticker = str(card.get("ticker") or "").upper()
    blockers = card.get("card_blockers") or []
    conflict_tags = _conflict_tags(display, card)
    has_directional_conflict = any(tag != "no direct score support" for tag in conflict_tags)
    no_directional_support = "no direct score support" in conflict_tags and not has_directional_conflict
    funding_leg = _is_funding_leg(card)
    material = _is_material(card)
    blockers_are_gates = bool(blockers) and all("gate" in str(blocker).lower() for blocker in blockers)
    stage_material = str(direction or "").upper() in {"BUY", "ADD"} and material and window_class == "STAGE-ONLY"
    blocker = _primary_blocker_text(card, display, check_first=check_first, window_class=window_class)
    if funding_leg:
        status = "funding sell only"
        title = _funding_sell_label(card)
    elif has_directional_conflict:
        status = "resolve direction"
        title = f"Resolve signal before {_action_gerund(direction)} {ticker}"
    elif stage_material and (not blockers or blockers_are_gates):
        status = "stage material buy"
        title = f"Stage {_money_text(card.get('dollars'))} {ticker} buy"
    elif check_first or blockers or no_directional_support:
        status = "needs feed"
        title = f"Feed evidence before {_action_gerund(direction)} {ticker}"
    elif window_class == "STAGE-ONLY":
        status = "stage only"
        title = f"Stage {direction.lower()} candidate for {ticker}"
    elif posture.get("state_verb") == "ACT":
        status = "lean-in candidate"
        title = f"{direction.title()} {ticker} can be considered"
    else:
        status = "review"
        title = f"Review {ticker} before acting"

    tags: list[tuple[str, str]] = []
    tags.append(("material" if material else "muted", _size_label(card)))
    if funding_leg:
        tags.append(("muted", "funding only"))
    gate_note = _first_gate_note(card)
    return {
        "status": status,
        "title": title,
        "subtitle": "",
        "signal": _name_signal_text(card, display),
        "layer": _layer_summary_text(display),
        "blocker": blocker,
        "sentence": _face_sentence(card, display, status=status, blocker=blocker),
        "gate_note": gate_note.get("summary") if gate_note else "",
        "tags": tags,
    }


def _first_raise(display: dict[str, Any]) -> str:
    operator_actions, waiting_actions, system_actions = _split_raise_actions(display)
    if operator_actions:
        return operator_actions[0]
    if waiting_actions:
        return f"Waiting on: {waiting_actions[0]}"
    if system_actions:
        return system_actions[0]
    return "Fresh confirming evidence that clears the current blocker."


def _decision_reason(card: dict[str, Any], display: dict[str, Any], *, check_first: bool, window_class: str) -> str:
    tags = [tag for _, tag in _card_face_model(
        card,
        display,
        _review_posture(
            card,
            check_first=check_first,
            window_class=window_class,
            direction=_card_action_direction(card),
        ),
        check_first=check_first,
        window_class=window_class,
        direction=_card_action_direction(card),
    )["tags"]]
    return "; ".join(tags[:3]) if tags else "No blocker surfaced in the rendered card."


def _render_decision_readout(
    card: dict[str, Any],
    display: dict[str, Any],
    posture: dict[str, str],
    *,
    check_first: bool,
    window_class: str,
    direction: str,
) -> str:
    face = _card_face_model(
        card,
        display,
        posture,
        check_first=check_first,
        window_class=window_class,
        direction=direction,
    )
    if face["status"] == "funding sell only":
        answer = "Do not treat as a standalone trade"
    elif posture.get("copy_verb") == "ACT" and not check_first and not display.get("conflict"):
        answer = "Lean-in candidate"
    elif face["status"] == "stage only":
        answer = "Stage only"
    elif face["status"] == "stage material buy":
        answer = "Stage material buy; full action still blocked"
    elif face["status"] == "needs feed":
        answer = "Feed evidence before action"
    elif face["status"] == "resolve direction":
        answer = "Do not act yet"
    else:
        answer = "Review first"
    why = face.get("blocker") or _decision_reason(card, display, check_first=check_first, window_class=window_class)
    return (
        '<div class="td-readout"><div class="td-readout-grid">'
        f'<div><div class="td-readout-k">Current answer</div><div class="td-readout-v">{_esc(answer)}</div></div>'
        f'<div><div class="td-readout-k">Why</div><div class="td-readout-v">{_esc(why)}</div></div>'
        f'<div><div class="td-readout-k">Next check</div><div class="td-readout-v">{_esc(_first_raise(display))}</div></div>'
        f'<div><div class="td-readout-k">Score</div><div class="td-readout-v">{_esc(_score_text(display))}</div></div>'
        '</div></div>'
    )


def _render_face(
    card: dict[str, Any],
    rank: int,
    display: dict[str, Any],
    posture: dict[str, str],
    *,
    check_first: bool,
    window_class: str,
    direction: str,
) -> str:
    face = _card_face_model(
        card,
        display,
        posture,
        check_first=check_first,
        window_class=window_class,
        direction=direction,
    )
    tag_html = []
    for kind, label in face["tags"]:
        cls = {
            "warn": "td-tag td-tag-warn",
            "danger": "td-tag td-tag-danger",
            "material": "td-size-chip td-size-material",
            "muted": "td-size-chip td-size-muted",
        }.get(kind, "td-tag td-tag-muted")
        tag_html.append(f'<span class="{cls}">{_esc(label)}</span>')
    return (
        '<div class="td-card-face">'
        '<div class="td-face-top">'
        '<div>'
        f'<div class="td-rank">#{rank} { _esc(str(card.get("ticker") or "")) }</div>'
        f'<div class="td-face-status">{_esc(face["status"])}</div>'
        f'<div class="td-face-title">{_esc(face["title"])}</div>'
        f'<div class="td-face-sentence">{_esc(face["sentence"])}</div>'
        + (f'<div class="td-face-gate">{_esc(face["gate_note"])}</div>' if face.get("gate_note") else "")
        + '</div>'
        '<div class="td-face-right">'
        f'<span class="td-score-chip" style="background:{_esc(display.get("band_color") or "#94a3b8")}">{_esc(_score_text(display))}</span>'
        '</div></div>'
        f'<div class="td-face-tags">{"".join(tag_html)}</div>'
        '</div>'
    )


def _render_dossier_block(card: dict[str, Any]) -> str:
    dossier = card.get("dossier") or {}
    if not isinstance(dossier, dict):
        return ""
    reads = dossier.get("reads") or {}
    if not isinstance(reads, dict):
        return ""
    all_unknown = True
    for read in reads.values():
        if not isinstance(read, dict):
            continue
        freshness = read.get("freshness") or {}
        text = str(read.get("text") or "UNKNOWN").upper()
        status = str(freshness.get("status") or "not_checked")
        if status != "not_checked" or text != "UNKNOWN":
            all_unknown = False
            break
    read_labels = ("edge", "price", "timing", "avoid")
    shell_open = (
        f'<details class="td-muted-details"><summary>Decision dossier not checked for '
        f'{_esc(dossier.get("ticker") or card.get("ticker") or "")}</summary>'
        if all_unknown
        else '<div class="td-dossier">'
    )
    shell_close = "</details>" if all_unknown else "</div>"
    lines = [
        shell_open,
        f'<div class="td-dossier-head">Decision dossier: {_esc(dossier.get("ticker") or card.get("ticker") or "")}</div>',
        f'<div class="td-dossier-meta">status: {_esc(dossier.get("status") or "not_checked")}'
        f' | reviewed: {_esc(dossier.get("last_reviewed") or "not_checked")}'
        f' | due: {_esc(dossier.get("next_review_due") or "not_checked")}'
        f' | synced: {_esc(dossier.get("synced_at") or "not_checked")}</div>',
    ]
    if dossier.get("one_liner"):
        lines.append(f'<div class="td-row">{_esc(dossier.get("one_liner"))}</div>')
    if dossier.get("notion_url"):
        lines.append(
            f'<div class="td-row"><a href="{_esc(dossier.get("notion_url"))}" '
            f'style="color:#93c5fd">open full dossier</a></div>'
        )
    for key in read_labels:
        read = reads.get(key) or {}
        if not isinstance(read, dict):
            continue
        freshness = read.get("freshness") or {}
        suffix = freshness.get("status") or "not_checked"
        lines.append(
            f'<div class="td-dossier-read"><strong>{_esc(read.get("label") or key)}'
            f' ({_esc(suffix)}):</strong> {_esc(read.get("text") or "UNKNOWN")}</div>'
        )
    lines.append(shell_close)
    return "".join(lines)


def _render_not_checked(display: dict[str, Any]) -> str:
    rows = display.get("not_checked") or []
    text = ", ".join(str(row) for row in rows) if rows else "none"
    return f'<div class="td-row">not checked: {_esc(text)}</div>'


def _lookthrough_rationale(card: dict[str, Any]) -> str:
    lookthrough = card.get("lookthrough") or {}
    contains = str(lookthrough.get("contains_line") or "").strip()
    if not contains:
        return ""
    return (
        "Rationale: this funding sell rotates out of MAG7 basket exposure "
        f"({contains.replace('contains ', '')}) to fund the paired single-name add."
    )


def _render_funding_pair_block(card: dict[str, Any]) -> str:
    if not _is_funding_leg(card):
        return ""
    adds = _funded_adds(card)
    if adds:
        links = []
        for add in adds:
            ticker = _esc(add["ticker"])
            amount = _esc(add["amount"])
            links.append(f'<a href="#td-card-{ticker}" style="color:#93c5fd">{ticker} {amount} add</a>')
        paired = ", ".join(links)
    else:
        paired = "the paired add it funds"
    rationale = _lookthrough_rationale(card)
    return (
        '<div class="td-evidence-note">'
        f'<strong>Pair this sell with:</strong> {paired}. '
        'Do not do the sell by itself.'
        + (f'<br/>{_esc(rationale)}' if rationale else "")
        + '</div>'
    )


def _render_fed_day_context_block(card: dict[str, Any]) -> str:
    context = card.get("fed_day_context") or {}
    if not isinstance(context, dict) or not context:
        return ""
    row = context.get("row") or {}
    if not isinstance(row, dict):
        return ""
    summary = _fed_day_card_summary(context)
    disconfirmation = str(row.get("disconfirmation") or "").strip()
    do_nothing = str(row.get("do_nothing_cost") or "").strip()
    label = str(context.get("label") or "Fed-day packet").strip()
    freshness = str(context.get("freshness") or "fresh")
    packet_as_of = str(context.get("packet_as_of") or "").strip()
    lines = [
        '<div class="td-evidence-note">',
        f'<strong>{_esc(label)}:</strong> {_esc(summary)}',
    ]
    if freshness == "stale":
        lines.append(
            f'<br/><strong>Shown but not counted:</strong> packet as of {_esc(packet_as_of or "unknown")} '
            '- STALE/not_checked; research context only, prices not current.'
        )
    if do_nothing:
        lines.append(f'<br/><strong>Why it matters:</strong> {_esc(do_nothing)}')
    if disconfirmation:
        lines.append(f'<br/><strong>Do not act if:</strong> {_esc(disconfirmation)}')
    lines.append("</div>")
    return "".join(lines)

def _health_strip_summary(items: list[dict[str, Any]]) -> str:
    alert_statuses = {"behind", "stale", "missing", "empty"}
    alerts = sum(1 for item in items if item.get("status") in alert_statuses)
    fresh = sum(1 for item in items if item.get("status") == "fresh")
    not_checked = sum(1 for item in items if item.get("status") == "not_checked")
    parts = []
    if alerts:
        parts.append(f"{alerts} alert{'s' if alerts != 1 else ''}")
    if fresh:
        parts.append(f"{fresh} fresh")
    if not_checked:
        parts.append(f"{not_checked} not checked")
    return "data freshness: " + (", ".join(parts) if parts else f"{len(items)} checked")

def _gate_strip_summary(gates: list[dict[str, Any]]) -> str:
    if not gates:
        return "gates: none"
    bits = []
    for gate in gates[:3]:
        state = str(gate.get("state") or "unknown").replace("_", " ").upper()
        symbol = str(gate.get("symbol") or "").upper()
        bits.append(f"{state} {symbol}".strip())
    if len(gates) > 3:
        bits.append(f"+{len(gates) - 3} more")
    return "gates: " + "; ".join(bits)


def _top_verdict(payload: dict[str, Any]) -> dict[str, str]:
    cards = list(payload.get("cards") or []) + list(payload.get("backlog") or [])
    material = [card for card in cards if _is_material(card) and not _is_funding_leg(card)]
    funding = [card for card in cards if _is_funding_leg(card)]
    watch_queue = payload.get("watch_queue") or []
    lean_ready = []
    starved = []
    signals = []
    for card in cards:
        display = card.get("conviction_display") or build_conviction_display(card)
        if _card_is_evidence_starved(card, display):
            starved.append(card)
        if not _is_funding_leg(card) and _strongest_directional_factor(display):
            signals.append(f"{card.get('ticker')}: {_name_signal_text(card, display).replace('Name signal: ', '')}")
        win = card.get("window") or {}
        if (
            _is_material(card)
            and not card.get("card_blockers")
            and not display.get("conflict")
            and str(win.get("class") or "") == "OPEN-NOW"
        ):
            lean_ready.append(card)

    dh_items = (payload.get("data_health") or {}).get("items") or []
    stale_or_unfed = [
        item for item in dh_items
        if item.get("status") in {"behind", "stale", "missing", "empty", "not_checked"}
    ]
    cap_cards = [
        card for card in material
        if str(((card.get("sizing") or {}).get("heat") or "")) == "ABOVE_CAP"
    ]
    lever_parts: list[str] = []
    material_tickers = [str(card.get("ticker") or "").upper() for card in material if not _is_funding_leg(card)]
    if material_tickers:
        lever_parts.append(f"fresh-check material names ({'/'.join(material_tickers[:3])})")
    if stale_or_unfed or starved:
        lever_parts.append("load the FS inbox / get a graded call")
    if cap_cards:
        lever_parts.append(f"revisit the {str(cap_cards[0].get('ticker') or '').upper()} cap if conviction warrants")
    if not lever_parts:
        lever_parts.append("write or refresh the dated thesis that would change the action")

    if lean_ready:
        title = f"{len(lean_ready)} lean-in-ready material card{'s' if len(lean_ready) != 1 else ''}."
    else:
        title = (
            "Nothing actionable yet: scorer is starved or blocked, not bearish. "
            f"Next lever: {' or '.join(lever_parts)}."
        )
    line_parts = [
        f"{len(material)} material decision{'s' if len(material) != 1 else ''}",
        f"{len(funding)} funding-only leg{'s' if len(funding) != 1 else ''}",
        f"{len(starved)} evidence-starved card{'s' if len(starved) != 1 else ''}",
    ]
    if watch_queue:
        line_parts.append(f"{len(watch_queue)} watchlist/pullback candidate{'s' if len(watch_queue) != 1 else ''}")
    if stale_or_unfed:
        line_parts.append(f"{len(stale_or_unfed)} stale/not-checked lane{'s' if len(stale_or_unfed) != 1 else ''}")
    if signals:
        line_parts.append("strongest evidence: " + "; ".join(signals[:2]))
    return {"title": title, "line": " | ".join(line_parts)}


def _render_top_verdict(payload: dict[str, Any]) -> str:
    verdict = _top_verdict(payload)
    return (
        '<div class="td-verdict">'
        f'<div class="td-verdict-title">{_esc(verdict["title"])}</div>'
        f'<div class="td-verdict-line">{_esc(verdict["line"])}</div>'
        '</div>'
    )


def _render_trust_panel(payload: dict[str, Any]) -> str:
    panel = payload.get("trust_panel") or {}
    if not panel:
        panel = _build_trust_panel(payload.get("data_health") or {})
    status = str(panel.get("status") or "info")
    cls = {
        "alert": "td-trust td-trust-alert",
        "warn": "td-trust td-trust-warn",
        "ok": "td-trust td-trust-ok",
    }.get(status, "td-trust")
    headline = str(panel.get("headline") or "Trust status not checked")
    bits = [f'<div class="{cls}"><div class="td-trust-head">Can I trust this screen? {_esc(headline)}</div>']
    bits.append('<div class="td-trust-grid">')
    for item in panel.get("items") or []:
        color = _TRUST_COLORS.get(str(item.get("status") or "info"), "#94a3b8")
        bits.append(
            '<div class="td-trust-item">'
            f'<div class="td-trust-label" style="color:{color}">{_esc(item.get("label") or "status")}</div>'
            f'<div class="td-trust-detail">{_esc(item.get("detail") or "")}</div>'
            '</div>'
        )
    bits.append('</div></div>')
    return "".join(bits)


def _first_gate_note(card: dict[str, Any]) -> dict[str, str] | None:
    notes = [row for row in card.get("gate_notes") or [] if isinstance(row, dict)]
    if not notes:
        return None
    def note_rank(row: dict[str, str]) -> int:
        return {"alert": 0, "warn": 1, "ok": 2, "context": 3, "info": 4}.get(str(row.get("status") or "info"), 4)

    ranked = sorted(notes, key=note_rank)
    return ranked[0]


def _render_gate_notes(card: dict[str, Any]) -> str:
    notes = [row for row in card.get("gate_notes") or [] if isinstance(row, dict)]
    if not notes:
        return ""
    bits = []
    for note in notes:
        cls = {
            "ok": "td-gate-note td-gate-note-ok",
            "warn": "td-gate-note td-gate-note-warn",
        }.get(str(note.get("status") or "info"), "td-gate-note")
        bits.append(
            f'<div class="{cls}"><strong>{_esc(note.get("label") or "Sizing gate")}:</strong> '
            f'{_esc(note.get("summary") or "")}</div>'
        )
    return "".join(bits)


def _review_posture(card: dict[str, Any], *, check_first: bool, window_class: str, direction: str) -> dict[str, str]:
    if _is_funding_leg(card):
        return {
            "label": "PAIR & FUND",
            "state_verb": "RECHECK",
            "copy_verb": "RECHECK",
            "copy_suffix": " funding sell only; pair with funded add",
            "reason": "funding sell only; do not sell standalone",
        }
    if check_first or card.get("conflicts") or window_class in {"GATED", "WAIT"}:
        return {
            "label": "RECHECK",
            "state_verb": "RECHECK",
            "copy_verb": "RECHECK",
            "copy_suffix": " resolve blockers before action",
            "reason": f"candidate {direction}; blockers or conflicts must clear first",
        }
    if window_class == "STAGE-ONLY":
        return {
            "label": "CANDIDATE",
            "state_verb": "CANDIDATE",
            "copy_verb": "RECHECK",
            "copy_suffix": " candidate only; confirm gates before action",
            "reason": f"candidate {direction}; stage-only until gates confirm",
        }
    return {"label": direction, "state_verb": "ACT", "copy_verb": "ACT", "copy_suffix": "", "reason": ""}

def _render_card(
    card: dict[str, Any],
    rank: int,
    check_first: bool = False,
    *,
    built_date: str | None = None,
) -> list[str]:
    dcard = card.get("decision_card") or {}
    move = dcard.get("move") or {}
    display = card.get("conviction_display") or build_conviction_display(card)
    win = card.get("window") or {}
    execn = card.get("execution") or {}
    impact = card.get("impact") or {}
    sizing = card.get("sizing") or {}
    cid = _esc(card.get("card_id"))
    conflicted = " td-conflicted" if card.get("conflicts") or display.get("conflict") else ""
    anchor = f'td-card-{_esc(str(card.get("ticker") or "").upper())}'
    h = [f'<details id="{anchor}" class="td-card{conflicted}">', '<summary class="td-sum">']
    cls = win.get("class", "WAIT")
    direction = str(move.get("direction") or "")
    posture = _review_posture(card, check_first=check_first, window_class=cls, direction=direction)
    h.append(_render_face(
        card,
        rank,
        display,
        posture,
        check_first=check_first,
        window_class=cls,
        direction=direction,
    ))
    h.append('</summary><div class="td-body">')
    h.append(_render_decision_readout(
        card,
        display,
        posture,
        check_first=check_first,
        window_class=cls,
        direction=direction,
    ))
    h.append(_render_gate_notes(card))
    h.append(_render_funding_pair_block(card))
    h.append(_render_fed_day_context_block(card))
    h.append('<div class="td-section-title">Evidence that matters</div>')
    h.append(_render_factor_breakdown(display, card, built_date=built_date))
    h.append(_render_layer_breakdown(display))
    for c in card.get("conflicts") or []:
        if _is_funding_leg(card):
            h.append(
                f'<div class="td-chip">Signal/action split: {_esc(c["with"])} says "{_esc(c["their_claim"])}"; '
                f'this card is only a funding sell paired with the buy it funds.</div>'
            )
        else:
            h.append(f'<div class="td-chip">Source conflict: {_esc(c["with"])} says "{_esc(c["their_claim"])}"; '
                     f'this card says {_esc(c["card_claim"])}. Resolve before acting.</div>')
    h.append('<details class="td-muted-details"><summary>Scoring inputs</summary>')
    h.append(_render_group_breakdown(display))
    h.append('</details>')
    h.append('<div class="td-section-title">What would make this actionable</div>')
    operator_actions, waiting_actions, system_actions = _split_raise_actions(display)
    h.append('<div class="td-action-columns">')
    h.append('<div class="td-action-column"><div class="td-action-column-title">Operator can do now</div>')
    h.extend(f'<div class="td-row">{_esc(r)}</div>' for r in operator_actions)
    h.append('</div>')
    if waiting_actions:
        h.append('<div class="td-action-column"><div class="td-action-column-title">Waiting on</div>')
        h.extend(f'<div class="td-row">{_esc(r)}</div>' for r in waiting_actions)
        h.append('</div>')
    h.append('<div class="td-action-column"><div class="td-action-column-title">System still needs wired</div>')
    h.extend(f'<div class="td-row">{_esc(r)}</div>' for r in system_actions)
    h.append('</div></div>')
    h.append(_render_dossier_block(card))
    if posture["reason"]:
        h.append(f'<div class="td-row"><strong>Rail:</strong> {_esc(posture["reason"])}</div>')
    primary_verb = posture["copy_verb"]
    primary_state_verb = posture["state_verb"]
    primary_label = posture["label"] if primary_verb != "ACT" else "ACT"
    primary_copy = (
        f"ACT {cid}" if primary_verb == "ACT"
        else f'{primary_verb} {cid}{_esc(posture["copy_suffix"])}'
    )
    primary_class = "td-rail" if primary_verb == "ACT" else "td-rail td-rail-muted"
    h.append(
        f'<button class="{primary_class}" data-card="{cid}" data-verb="{primary_state_verb}" data-copy="{_esc(primary_copy)}" '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">{_esc(primary_label)}</button>'
        f'<button class="td-rail" data-card="{cid}" data-verb="PASS" data-copy="PASS {cid} â€” reason: " '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">PASS</button>'
    )
    if primary_state_verb != "RECHECK":
        h.append(
        f'<button class="td-rail" data-card="{cid}" data-verb="RECHECK" '
        f'data-copy="RECHECK {cid} resurface {_esc(card.get("recheck_date"))}" '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">RECHECK</button>'
        )
    if win.get("named_trigger"):
        h.append(f'<div class="td-row">trigger: {_esc(win["named_trigger"])}'
                 + (f' Â· deadline {_esc(win.get("deadline"))}' if win.get("deadline") else "") + "</div>")
    for reason in (win.get("reasons") or [])[:2]:
        h.append(f'<div class="td-row">â€¢ {_esc(reason)}</div>')
    flips = win.get("flips") or []
    if flips:
        h.append("<details><summary>what changes this</summary>"
                 + "".join(f"<div>flip: {_esc(f)}</div>" for f in flips)
                 + "</details>")
    suggested = execn.get("suggested")
    if suggested:
        h.append(f'<div class="td-row">execute: {_esc(suggested.get("owner"))} {_esc(suggested.get("broker"))} '
                 f'{_esc(suggested.get("account"))} Â· {_esc(suggested.get("tax_flag"))} Â· {_esc(suggested.get("why"))}</div>')
    for leg in (execn.get("legs") or []):
        line = (f'sell ${leg.get("sell_usd", 0):,.0f} in {_esc(leg.get("owner"))} {_esc(leg.get("broker"))} '
                f'{_esc(leg.get("account"))} Â· {_esc(leg.get("tax_flag"))}')
        if leg.get("proceeds_constraint"):
            line += f' Â· âš  {_esc(leg["proceeds_constraint"])}'
        h.append(f'<div class="td-row">execute: {line}</div>')
    for ex in (execn.get("excluded") or []):
        h.append(f'<div class="td-row">excluded: {_esc(ex.get("account"))} â€” {_esc(ex.get("why_not"))}</div>')
    lookthrough = card.get("lookthrough") or {}
    if lookthrough:
        h.append(f'<div class="td-row">look-through: {_esc(lookthrough.get("contains_line"))}</div>')
        h.append(f'<div class="td-chip">{_esc(lookthrough.get("overlap_line"))}</div>')
        if lookthrough.get("source"):
            h.append(f'<div class="td-row">look-through source: {_esc(lookthrough.get("source"))}</div>')
    if execn.get("transfer_note"):
        h.append(f'<div class="td-chip">TRANSFER NEEDED: {_esc(execn["transfer_note"])}</div>')
    if execn.get("cash"):
        h.append(f'<div class="td-row">cash: {_esc(execn["cash"])}</div>')
    if sizing:
        suggested = sizing.get("suggested_usd")
        suggested_txt = f'${float(suggested):,.0f}' if isinstance(suggested, (int, float)) else "n/a"
        h.append(f'<div class="td-row">sizing: {_esc(sizing.get("source", "unknown"))} suggested {suggested_txt} '
                 f'Â· heat {_esc(sizing.get("heat", "unknown"))}</div>')
        if sizing.get("cap_basis"):
            h.append(f'<div class="td-row">cap basis: {_esc(sizing["cap_basis"])}</div>')
    h.append(f'<div class="td-row">impact: {_esc(impact.get("band"))} Â· material: '
             f'{"yes" if impact.get("material") else "no"}</div>')
    if card.get("last_disposition"):
        ld = card["last_disposition"]
        h.append(f'<div class="td-row">last disposition: {_esc(ld.get("verb"))} on {_esc(ld.get("et_date"))}</div>')
    h.append('<details class="td-muted-details"><summary>Not checked / optional context</summary>')
    h.append(_render_iv_hint(display))
    h.append(_render_not_checked(display))
    h.append('</details>')
    h.append("</div></details>")
    return h


def _card_dollars(card: dict[str, Any]) -> float:
    try:
        return float(card.get("dollars") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _visible_card_sections(cards: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    material = [card for card in cards if _is_material(card) and not _is_funding_leg(card)]
    other = [card for card in cards if not _is_material(card) and not _is_funding_leg(card)]
    funding = [card for card in cards if _is_funding_leg(card)]
    sections: list[tuple[str, list[dict[str, Any]]]] = []
    if material:
        sections.append(("Material decisions", material))
    if other:
        sections.append(("Other rechecks", other))
    if funding:
        sections.append(("Funding / paired sells", funding))
    return sections


def _render_watch_queue(payload: dict[str, Any]) -> str:
    queue = payload.get("watch_queue") or []
    meta = payload.get("watch_queue_meta") or {}
    freshness = str(meta.get("freshness") or ("fresh" if queue else "absent"))
    caption = str(meta.get("caption") or "These are ranked research/recheck candidates from the fed-day packet. They are visible so discounted or watched names do not disappear, but they do not outrank executable decisions without fresh confirmation.")
    if not queue and freshness != "absent":
        return ""
    h = [
        '<div class="td-subqueue">',
        f'<div class="td-card-section-title">Watchlist / pullback impact queue ({len(queue)})</div>',
        f'<div class="td-row">{_esc(caption)}</div>',
    ]
    for idx, row in enumerate(queue, 1):
        tags = []
        exposure = _coerce_money(row.get("current_exposure_usd"))
        if exposure is not None:
            tags.append(f"exposure ${exposure:,.0f}")
        discount = _coerce_float(row.get("pct_below_high"))
        if discount is not None:
            tags.append(f"{discount:.1f}% below 52w high")
        research = str(row.get("research_status") or "").strip()
        if research:
            tags.append(f"research {research}")
        sources = ", ".join(str(tag) for tag in row.get("source_tags") or [] if tag)
        if sources:
            tags.append(sources)
        if str(row.get("freshness") or "") == "stale":
            tags.append(f"as of {row.get('packet_as_of') or 'unknown'} - STALE, research context only")
        h.append(
            '<div class="td-queue-card">'
            '<div class="td-queue-top">'
            f'<div><div class="td-queue-label">{_esc(row.get("label") or "watch")}</div>'
            f'<div class="td-queue-rank">#{idx} {_esc(row.get("ticker") or "")}</div></div>'
            f'<div class="td-queue-score">impact {_esc(row.get("impact_score"))}</div>'
            '</div>'
            f'<div class="td-queue-summary">{_esc(row.get("summary") or "")}</div>'
            + (f'<div class="td-queue-meta">{" | ".join(_esc(tag) for tag in tags)}</div>' if tags else "")
            + (f'<div class="td-queue-meta"><strong>Do not promote if:</strong> {_esc(row.get("disconfirmation") or "")}</div>' if row.get("disconfirmation") else "")
            + '</div>'
        )
    return "".join(h) + "</div>"


def _render_do_not_touch(payload: dict[str, Any]) -> str:
    rows = payload.get("fed_day_do_not_touch") or []
    if not rows:
        return ""
    return (
        '<details class="td-muted-details">'
        f'<summary>Do-not-touch / research-only guardrails ({len(rows)})</summary>'
        + "".join(f'<div class="td-row">{_esc(row)}</div>' for row in rows)
        + '</details>'
    )


def render_today_decide_html(payload: dict[str, Any]) -> str:
    ga = payload["goal_anchor"]
    pl = payload["plan_line"]
    h: list[str] = [_CSS, _JS, '<section id="today-decide" class="td">']
    h.append(f'<h2>TODAY â€” DECIDE <span style="color:#94a3b8;font-size:12px">built {_esc(payload["built"])}</span></h2>')
    if ga.get("book_value") is not None:
        h.append(f'<div class="td-anchor">${ga["book_value"]:,.0f} â†’ ${ga["fi_target"]:,.0f} '
                 f'Â· {ga["pct_to_target"]}% there</div>')
    else:
        h.append('<div class="td-anchor">book value: not readable â€” honest absence</div>')
    h.append(f'<div class="td-pace">{_esc(ga["pace_line"])}</div>')
    pool = pl.get("pool_usd")
    short = pl.get("shortfall_usd")
    h.append('<div class="td-plan">plan: '
             + (f'funding pool ${pool:,.0f}' if isinstance(pool, (int, float)) else 'funding pool n/a')
             + (f' Â· shortfall ${short:,.0f}' if isinstance(short, (int, float)) else '')
             + f' Â· positions as of {_esc(pl.get("positions_as_of"))}</div>')
    h.append(_render_trust_panel(payload))
    h.append(_render_top_verdict(payload))
    rank = 1
    for label, cards in _visible_card_sections(payload["cards"]):
        h.append(f'<div class="td-card-section-title">{_esc(label)}</div>')
        for card in cards:
            h.extend(_render_card(card, rank, check_first=bool(card.get("card_blockers")), built_date=str(payload.get("built") or "")))
            rank += 1
    backlog = payload["backlog"]
    if backlog:
        h.append(f'<div class="td-subqueue"><div class="td-card-section-title">More impact-ranked decisions ({len(backlog)})</div>')
        for label, cards in _visible_card_sections(backlog):
            h.append(f'<div class="td-card-section-title">{_esc(label)}</div>')
            for card in cards:
                h.extend(_render_card(card, rank, check_first=bool(card.get("card_blockers")), built_date=str(payload.get("built") or "")))
                rank += 1
        h.append("</div>")
    h.append(_render_watch_queue(payload))
    h.append(_render_do_not_touch(payload))
    cong = payload["congruence"]
    h.append('<details class="td-muted-details"><summary>Portfolio thesis context</summary>')
    if cong.get("status") == "ok":
        for row in cong.get("rows") or []:
            flag = "\U0001f6a9 " if row.get("flagged") else ""
            h.append(f'<div class="td-cong">{flag}{_esc(row["insight_id"])} Â· {_esc(row["line"])}</div>')
    else:
        h.append(f'<div class="td-cong">congruence: not checked â€” {_esc(cong.get("reason", ""))}</div>')
    h.append("</details>")
    h.append('<details class="td-muted-details"><summary>System honesty / data caveats</summary><div class="td-honesty">'
             + "<br/>".join(f"{_esc(k)}: {_esc(v)}" for k, v in payload["honesty"].items())
             + "</div></details>")
    h.append("</section>")
    return "\n".join(h)

def build_and_render(**kwargs: Any) -> str:
    return render_today_decide_html(build_today_decide_payload(**kwargs))
