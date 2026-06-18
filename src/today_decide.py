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
import subprocess
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
HELD_DECISIONS_PATH = SRC / "held_decisions.json"

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
        f"(display-only) gap ${gap:,.0f} Â| {months} months to {goal['window_horizon']}"
        f" Â| â‰ˆ ${per_month:,.0f}/month â€” pace never feeds ranking or urgency"
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
            "detail": f"routine fired proof {scheduled}/{expected_count}; {missing} core routine(s) not proven; boundary data not implied",
        }
    return {
        "label": "Automations",
        "status": "ok",
        "detail": f"routine fired proof {scheduled}/{expected_count}; boundary data not implied",
    }


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
        "conflicted": bool(conviction.get("conflicted")),
        "conflict_detail": conviction.get("conflict_detail"),
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


def _fed_packet_display_label(packet: dict[str, Any] | None = None) -> str:
    label = str((packet or {}).get("display_label") or "").strip()
    return label or "Daily pullback packet"


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
        label = _fed_packet_display_label()
        return {
            "packet": {},
            "freshness": "absent",
            "packet_as_of": None,
            "caption": f"{label} not_checked - no packet on disk; no pullback rows fabricated.",
            "honesty": "not_checked - no packet on disk",
        }
    label = _fed_packet_display_label(packet)
    as_of_raw = str(packet.get("as_of") or "").strip()
    as_of = _date_string(as_of_raw)
    today_day = _date_string(today_iso) or today_iso
    if as_of and as_of == today_day:
        return {
            "packet": packet,
            "freshness": "fresh",
            "packet_as_of": as_of,
            "caption": f"{label} current as of {as_of}. Research/recheck rows stay rail-free until separately confirmed.",
            "honesty": "",
        }
    display_as_of = as_of or as_of_raw or "unknown"
    return {
        "packet": packet,
        "freshness": "stale",
        "packet_as_of": display_as_of,
        "caption": f"{label} STALE/not_checked as of {display_as_of}; rows are research context only and prices are not current.",
        "honesty": f"stale (as_of {display_as_of}) - research context only, prices not current",
    }


def _fed_day_rows_by_ticker(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packet = state.get("packet") or {}
    out: dict[str, dict[str, Any]] = {}
    packet_label = _fed_packet_display_label(packet)
    labels = {
        "act_if_green": f"{packet_label} act-if-green candidate",
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


def _watch_row_key(row: dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or "").strip().upper() or "UNKNOWN"
    section = str(row.get("section") or row.get("label") or "watch").strip() or "watch"
    return f"{ticker}|{section}"


def _read_held_decisions(path: Path | str | None) -> tuple[list[dict[str, Any]], str]:
    if path is None:
        return [], "not_checked"
    p = Path(path)
    if not p.exists():
        return [], "missing"
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], "unreadable"
    if not isinstance(payload, list):
        return [], "unreadable"
    return [row for row in payload if isinstance(row, dict)], "ok"


def _held_review_due_rows(today_iso: str, held_decisions_path: Path | str | None) -> tuple[list[dict[str, Any]], str]:
    rows, status = _read_held_decisions(held_decisions_path)
    if status != "ok":
        return [], status
    today_day = _today(today_iso)
    due: list[dict[str, Any]] = []
    for row in rows:
        state = str(row.get("status") or "").strip().lower()
        if state not in {"held", "reparked"}:
            continue
        review_by = _date_string(row.get("review_by"))
        if not review_by:
            continue
        review_day = _today(review_by)
        if review_day > today_day:
            continue
        decision_id = str(row.get("id") or row.get("title") or "held-decision").strip()
        title = str(row.get("title") or decision_id).strip()
        age_days = max(0, (today_day - review_day).days)
        due.append({
            "kind": "held_review_due",
            "state": "DECIDE",
            "decision_key": f"HELD|{decision_id}",
            "ticker": "HELD",
            "title": f"Review due: {title}",
            "prompt": "Keep held, pass, or recheck with a new review date.",
            "detail": f"review_by {review_by}; parked {row.get('parked_date') or 'unknown'}; {age_days} day(s) overdue",
            "review_by": review_by,
            "age_days": age_days,
            "notion_url": str(row.get("notion_url") or ""),
            "actions": [
                {"label": "KEEP HELD", "verb": "KEEP_HELD", "copy": f"KEEP_HELD {decision_id} reason: "},
                {"label": "PASS", "verb": "PASS", "copy": f"PASS {decision_id} reason: "},
                {"label": "RECHECK", "verb": "RECHECK", "copy": f"RECHECK {decision_id} new_review_by: "},
            ],
        })
    due.sort(key=lambda item: (str(item.get("review_by") or ""), str(item.get("title") or "")))
    return due, "ok"


def _watch_promotion_kind(row: dict[str, Any]) -> str:
    if str(row.get("freshness") or "") != "fresh":
        return ""
    score = _coerce_float(row.get("impact_score")) or 0.0
    blob = _text_blob(
        row.get("section"),
        row.get("label"),
        row.get("status"),
        row.get("research_status"),
        row.get("summary"),
        row.get("disconfirmation"),
        row.get("source_tags") or [],
    ).lower()
    if "monitor" in blob or "research-only" in blob or "research only" in blob:
        return ""
    if str(row.get("section") or "") == "act_if_green" and score >= 50:
        return "size_review"
    if score < 90:
        return ""
    if any(token in blob for token in ("sell_fast", "sell-fast", "avoid", "dropped")):
        return "avoid_review"
    if any(token in blob for token in ("lean", "bullish_flow", "bullish flow", "add candidate")):
        return "size_review"
    return ""


def _watch_decision_pressure_rows(watch_queue: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    promoted_keys: list[str] = []
    for row in watch_queue or []:
        kind = _watch_promotion_kind(row)
        if not kind:
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        key = _watch_row_key(row)
        promoted_keys.append(key)
        if kind == "avoid_review":
            title = f"Decide {ticker}: avoid new exposure?"
            prompt = "Avoid new exposure, pass, or recheck after the setup changes."
            primary = {"label": "AVOID NEW", "verb": "AVOID_NEW", "copy": f"AVOID_NEW {ticker} reason: "}
        else:
            title = f"Decide {ticker}: size/recheck setup?"
            prompt = "Size only after the named gate clears, pass, or recheck after confirmation."
            primary = {"label": "SIZE REVIEW", "verb": "SIZE_REVIEW", "copy": f"SIZE_REVIEW {ticker} after gate: "}
        rows.append({
            "kind": "watch_promoted",
            "state": "DECIDE",
            "decision_key": key,
            "ticker": ticker,
            "title": title,
            "prompt": prompt,
            "detail": f"impact {row.get('impact_score')}; {row.get('summary') or ''}",
            "source_label": str(row.get("label") or "watch queue"),
            "actions": [
                primary,
                {"label": "PASS", "verb": "PASS", "copy": f"PASS {ticker} reason: "},
                {"label": "RECHECK", "verb": "RECHECK", "copy": f"RECHECK {ticker} after gate/source refresh"},
            ],
        })
    rows.sort(key=lambda item: (str(item.get("kind") or ""), str(item.get("ticker") or "")))
    return rows, promoted_keys


def _build_disposition_pressure(
    watch_queue: list[dict[str, Any]],
    today_iso: str,
    held_decisions_path: Path | str | None,
) -> dict[str, Any]:
    held_rows, held_status = _held_review_due_rows(today_iso, held_decisions_path)
    watch_rows, promoted_keys = _watch_decision_pressure_rows(watch_queue)
    rows = held_rows + watch_rows
    counts = {
        "review_due": len(held_rows),
        "promoted_watch": len(watch_rows),
        "total": len(rows),
    }
    if rows:
        line = (
            f"{counts['total']} DECIDE prompt(s): {counts['review_due']} overdue held review(s), "
            f"{counts['promoted_watch']} high-impact watch promotion(s)."
        )
    elif held_status == "ok":
        line = "No overdue held reviews or high-impact watch rows promoted."
    else:
        line = f"Held decisions {held_status}; high-impact watch promotions checked from render payload."
    return {
        "status": "active" if rows else ("not_checked" if held_status != "ok" else "clear"),
        "line": line,
        "rows": rows,
        "counts": counts,
        "promoted_watch_keys": promoted_keys,
        "held_status": held_status,
        "honesty_rule": (
            "Display-only disposition pressure; rows add yes/pass/recheck prompts but do not change "
            "scoring, sizing, gates, trades, or source grading."
        ),
    }


def _source_family(source: str) -> str:
    low = source.lower()
    if "fundstrat" in low or low.startswith("fs") or "feed.actions" in low:
        return "fundstrat"
    if "uw" in low or "asymmetric" in low:
        return "uw"
    if "reallocation" in low or "portfolio" in low or "positions" in low:
        return "portfolio"
    if "source_conflict" in low or "market_open" in low or "event" in low:
        return "risk"
    if "watch" in low or "pullback" in low:
        return "watch"
    return "system"


def _candidate_index_add(
    records: dict[str, dict[str, Any]],
    *,
    decision_key: str,
    ticker: str,
    lane: str,
    state: str,
    title: str,
    source: str,
    evidence: str,
) -> None:
    key = str(decision_key or "").strip()
    if not key:
        return
    state = state if state in COMMAND_STATE_RANK else "WATCH"
    rec = records.setdefault(key, {
        "decision_key": key,
        "ticker": str(ticker or "").strip().upper() or "SYSTEM",
        "lane": str(lane or "context").strip() or "context",
        "state": state,
        "title": str(title or key).strip() or key,
        "sources": [],
        "source_families": [],
        "evidence": [],
    })
    if COMMAND_STATE_RANK.get(state, 99) < COMMAND_STATE_RANK.get(str(rec.get("state") or "WATCH"), 99):
        rec["state"] = state
    if title and len(str(title)) > len(str(rec.get("title") or "")):
        rec["title"] = str(title)
    source_text = str(source or "source").strip()
    if source_text and source_text not in rec["sources"]:
        rec["sources"].append(source_text)
    family = _source_family(source_text)
    if family not in rec["source_families"]:
        rec["source_families"].append(family)
    evidence_text = str(evidence or "").strip()
    if evidence_text and evidence_text not in rec["evidence"]:
        rec["evidence"].append(evidence_text)


def _build_candidate_feed_index(
    feed: dict[str, Any],
    cards: list[dict[str, Any]],
    watch_queue: list[dict[str, Any]],
    disposition_pressure: dict[str, Any],
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}

    for card in cards or []:
        state = str(card.get("command_state") or _card_command_state(card))
        ticker = str(card.get("ticker") or "").strip().upper()
        lane = _card_lane(card)
        display = card.get("conviction_display") or {}
        _candidate_index_add(
            records,
            decision_key=card.get("decision_key") or _decision_key(card),
            ticker=ticker,
            lane=lane,
            state=state,
            title=_primary_command_title(card, state),
            source="today_decide_card",
            evidence=str(
                display.get("conflict")
                or (card.get("blocker_taxonomy") or {}).get("line")
                or (card.get("readiness") or {}).get("summary")
                or ""
            ),
        )

    for row in (disposition_pressure or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("decision_key") or "").strip()
        ticker = str(row.get("ticker") or "SYSTEM").strip().upper() or "SYSTEM"
        lane = str(row.get("kind") or "disposition_pressure").strip()
        _candidate_index_add(
            records,
            decision_key=key,
            ticker=ticker,
            lane=lane,
            state=str(row.get("state") or "DECIDE"),
            title=str(row.get("title") or key),
            source=lane,
            evidence=str(row.get("detail") or row.get("prompt") or ""),
        )

    for row in _source_decide_prompts(feed):
        _candidate_index_add(
            records,
            decision_key=row["decision_key"],
            ticker=row["ticker"],
            lane=row["lane"],
            state="DECIDE",
            title=row["label"],
            source=row["source"],
            evidence=row["label"],
        )

    for row in watch_queue or []:
        if not isinstance(row, dict):
            continue
        _candidate_index_add(
            records,
            decision_key=_watch_row_key(row),
            ticker=str(row.get("ticker") or "").upper(),
            lane=str(row.get("section") or "watch"),
            state="WATCH",
            title=f"Watch {str(row.get('ticker') or '').upper()}",
            source="watch_queue",
            evidence=str(row.get("summary") or ""),
        )

    for row in ((feed.get("source_conflicts") or {}).get("rows") or []):
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        _candidate_index_add(
            records,
            decision_key=f"{ticker}|source_conflict",
            ticker=ticker,
            lane="source_conflict",
            state="RESOLVE",
            title=f"Resolve {ticker} source conflict",
            source="source_conflicts",
            evidence=str(row.get("action_posture") or row.get("decision_effect") or row.get("summary") or ""),
        )

    for row in ((feed.get("asymmetric_opportunities") or {}).get("rows") or []):
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        _candidate_index_add(
            records,
            decision_key=f"{ticker}|asymmetric_opportunity",
            ticker=ticker,
            lane="asymmetric_opportunity",
            state="WATCH",
            title=f"Watch {ticker} asymmetric setup",
            source=str(row.get("source") or "asymmetric_opportunities"),
            evidence=str(row.get("reason") or row.get("evidence") or ""),
        )

    rb = feed.get("reallocation_brief") or {}
    for row in rb.get("rows") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        _candidate_index_add(
            records,
            decision_key=f"{ticker}|reallocation_add",
            ticker=ticker,
            lane="reallocation_add",
            state="RESOLVE",
            title=f"Resolve {ticker} add",
            source="reallocation_brief",
            evidence=str(row.get("entry_note") or row.get("disconfirmation") or ""),
        )
    for row in rb.get("trims") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        _candidate_index_add(
            records,
            decision_key=f"{ticker}|funding_trim",
            ticker=ticker,
            lane="funding_trim",
            state="RESOLVE",
            title=f"Resolve {ticker} trim",
            source="reallocation_brief",
            evidence=str(row.get("funds") or row.get("disconfirmation") or ""),
        )

    for row in ((feed.get("uw_action_runbook") or {}).get("rows") or []):
        if not isinstance(row, dict):
            continue
        for ticker_raw in row.get("ticker_scope") or []:
            ticker = str(ticker_raw or "").upper()
            if not ticker:
                continue
            _candidate_index_add(
                records,
                decision_key=f"{ticker}|uw_runbook",
                ticker=ticker,
                lane="uw_runbook",
                state="RESOLVE",
                title=f"Resolve {ticker} UW check",
                source="uw_action_runbook",
                evidence=str(row.get("blocks_action_if") or row.get("why") or ""),
            )

    rows = sorted(
        records.values(),
        key=lambda rec: (
            COMMAND_STATE_RANK.get(str(rec.get("state") or "WATCH"), 99),
            str(rec.get("ticker") or ""),
            str(rec.get("lane") or ""),
        ),
    )
    for row in rows:
        row["source_count"] = len(row.get("sources") or [])
        row["independent_source_count"] = len(row.get("source_families") or [])
        row["evidence"] = (row.get("evidence") or [])[:4]
    return {
        "rows": rows,
        "counts": {
            "total": len(rows),
            **{state: sum(1 for row in rows if row.get("state") == state) for state in COMMAND_STATES},
        },
        "honesty_rule": (
            "Display-only merged feeder index keyed by ticker|lane; source families are shown for context only "
            "and never counted as conviction or sizing."
        ),
    }


PASSIVITY_BUCKET_LABELS = {
    "operator_owned_actionable_now": "yours to decide now",
    "waiting_market_price_tape_gate": "waiting on market/price/tape gate",
    "waiting_source_data_freshness": "waiting on source/data freshness",
    "research_watch_only": "research/watch-only",
    "cap_risk_cash_constrained": "cap/risk/cash constrained",
    "system_blocked_not_checked": "system-blocked/not_checked",
}

BLOCKER_CATEGORY_LABELS = {
    "price_tape_gate": "price/tape gate",
    "source_freshness": "source freshness",
    "flow_evidence_conflict": "flow/evidence conflict",
    "cap_room": "cap room",
    "cash_funding": "cash/funding",
    "concentration_leverage": "concentration/leverage rail",
    "account_sleeve_eligibility": "account/sleeve eligibility",
    "research_disconfirmation": "research/disconfirmation missing",
}


COMMAND_STATES = ("ACT", "DECIDE", "RESOLVE", "WATCH")
COMMAND_STATE_RANK = {"ACT": 0, "DECIDE": 1, "RESOLVE": 2, "WATCH": 3}
COMMAND_STATE_COPY = {
    "ACT": "all rails clear",
    "DECIDE": "operator yes/no/recheck needed",
    "RESOLVE": "named blocker must clear",
    "WATCH": "weak, early, or research-only",
}

READINESS_LAYERS = (
    "routine_fired",
    "boundary_artifact",
    "signal_interpreted",
    "decision_eligible",
    "trade_executable",
)
READINESS_LAYER_LABELS = {
    "routine_fired": "Routine fired",
    "boundary_artifact": "Boundary artifact",
    "signal_interpreted": "Signal interpreted",
    "decision_eligible": "Decision eligible",
    "trade_executable": "Trade executable",
}
READINESS_CHECK_LABELS = {
    "uw_interpreted": "UW interpreted",
    "cash_buying_power": "Cash/buying power",
    "account_eligibility": "Account eligibility",
    "cap_room": "Cap room",
    "research_disconfirmation": "Research/disconfirmation",
    "event_risk": "Event risk",
}
READINESS_DARK_STATUSES = {"not_checked", "behind", "stale", "missing", "empty"}


def _readiness_entry(key: str, label: str, status: str, detail: str) -> dict[str, str]:
    if status not in {"ok", "blocked", "unknown"}:
        status = "unknown"
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": str(detail or "").strip(),
    }


def _trust_item_by_label(trust_panel: dict[str, Any], label: str) -> dict[str, Any] | None:
    want = label.strip().lower()
    for item in trust_panel.get("items") or []:
        if isinstance(item, dict) and str(item.get("label") or "").strip().lower() == want:
            return item
    return None


def _taxonomy_unmet(card: dict[str, Any]) -> list[dict[str, Any]]:
    taxonomy = card.get("blocker_taxonomy") or {}
    return [row for row in taxonomy.get("unmet") or [] if isinstance(row, dict)]


def _taxonomy_categories(card: dict[str, Any]) -> set[str]:
    return {str(row.get("category") or "").strip() for row in _taxonomy_unmet(card)}


def _taxonomy_detail(card: dict[str, Any], *categories: str) -> str:
    wanted = set(categories)
    for row in _taxonomy_unmet(card):
        if str(row.get("category") or "") in wanted:
            return str(row.get("evidence") or row.get("label") or "").strip()
    return ""


def _data_health_dark_items(data_health: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in data_health.get("items") or []
        if isinstance(item, dict) and str(item.get("status") or "") in READINESS_DARK_STATUSES
    ]


def _dark_item_line(items: list[dict[str, Any]], *, limit: int = 3) -> str:
    labels = [
        str(item.get("label") or item.get("source") or "lane").strip()
        for item in items
        if str(item.get("label") or item.get("source") or "").strip()
    ]
    if not labels:
        return "no dark boundary lanes visible"
    line = ", ".join(labels[:limit])
    if len(labels) > limit:
        line += f", +{len(labels) - limit} more"
    return line


def _routine_fired_layer(trust_panel: dict[str, Any]) -> dict[str, str]:
    item = _trust_item_by_label(trust_panel, "Automations")
    if not item:
        return _readiness_entry(
            "routine_fired",
            READINESS_LAYER_LABELS["routine_fired"],
            "unknown",
            "routine receipt layer not checked",
        )
    detail = str(item.get("detail") or "").strip() or "routine proof not detailed"
    status = str(item.get("status") or "info")
    if status == "ok":
        return _readiness_entry("routine_fired", READINESS_LAYER_LABELS["routine_fired"], "ok", detail)
    if status == "alert":
        return _readiness_entry("routine_fired", READINESS_LAYER_LABELS["routine_fired"], "blocked", detail)
    return _readiness_entry("routine_fired", READINESS_LAYER_LABELS["routine_fired"], "unknown", detail)


def _boundary_artifact_layer(card: dict[str, Any], data_health: dict[str, Any]) -> dict[str, str]:
    blockers = [str(row or "").strip() for row in card.get("card_blockers") or [] if str(row or "").strip()]
    if blockers:
        return _readiness_entry(
            "boundary_artifact",
            READINESS_LAYER_LABELS["boundary_artifact"],
            "blocked",
            "; ".join(blockers[:2]),
        )
    dark_items = _data_health_dark_items(data_health)
    if dark_items:
        return _readiness_entry(
            "boundary_artifact",
            READINESS_LAYER_LABELS["boundary_artifact"],
            "unknown",
            f"dark boundary lane(s): {_dark_item_line(dark_items)}",
        )
    return _readiness_entry(
        "boundary_artifact",
        READINESS_LAYER_LABELS["boundary_artifact"],
        "ok",
        "render-visible boundary artifacts are fresh",
    )


def _signal_interpreted_layer(card: dict[str, Any], display: dict[str, Any]) -> dict[str, str]:
    categories = _taxonomy_categories(card)
    if {"source_freshness", "flow_evidence_conflict", "research_disconfirmation"} & categories:
        return _readiness_entry(
            "signal_interpreted",
            READINESS_LAYER_LABELS["signal_interpreted"],
            "blocked",
            _taxonomy_detail(card, "source_freshness", "flow_evidence_conflict", "research_disconfirmation")
            or "source or interpretation blocker visible",
        )
    if card.get("conflicts") or display.get("conflict"):
        return _readiness_entry(
            "signal_interpreted",
            READINESS_LAYER_LABELS["signal_interpreted"],
            "blocked",
            str(display.get("conflict") or "source conflict visible"),
        )
    if _card_is_evidence_starved(card, display):
        return _readiness_entry(
            "signal_interpreted",
            READINESS_LAYER_LABELS["signal_interpreted"],
            "unknown",
            "evidence exists only as weak, stale, or not-checked context",
        )
    return _readiness_entry(
        "signal_interpreted",
        READINESS_LAYER_LABELS["signal_interpreted"],
        "ok",
        "directional read is render-visible",
    )


def _decision_eligible_layer(card: dict[str, Any], base_state: str) -> dict[str, str]:
    taxonomy = card.get("blocker_taxonomy") or {}
    if taxonomy.get("unmet"):
        return _readiness_entry(
            "decision_eligible",
            READINESS_LAYER_LABELS["decision_eligible"],
            "blocked",
            str(taxonomy.get("line") or "named blocker still visible"),
        )
    if base_state == "WATCH":
        return _readiness_entry(
            "decision_eligible",
            READINESS_LAYER_LABELS["decision_eligible"],
            "unknown",
            "watch/research-only state; no yes/no capital call yet",
        )
    return _readiness_entry(
        "decision_eligible",
        READINESS_LAYER_LABELS["decision_eligible"],
        "ok",
        "yes/no/recheck disposition is allowed in this render",
    )


def _readiness_checklist(card: dict[str, Any], display: dict[str, Any]) -> list[dict[str, str]]:
    blob = _card_text_blob(card, display)
    execn = card.get("execution") or {}
    sizing = card.get("sizing") or {}
    checks: list[dict[str, str]] = []

    uw_detail = _taxonomy_detail(card, "flow_evidence_conflict")
    if "uw" in blob and uw_detail:
        checks.append(_readiness_entry(
            "uw_interpreted",
            READINESS_CHECK_LABELS["uw_interpreted"],
            "blocked",
            uw_detail or "UW lane is present but not directional",
        ))
    elif "uw" in blob:
        checks.append(_readiness_entry(
            "uw_interpreted",
            READINESS_CHECK_LABELS["uw_interpreted"],
            "ok",
            "UW-dependent blocker not visible",
        ))
    else:
        checks.append(_readiness_entry(
            "uw_interpreted",
            READINESS_CHECK_LABELS["uw_interpreted"],
            "ok",
            "no UW-dependent blocker visible",
        ))

    cash_detail = _taxonomy_detail(card, "cash_funding")
    cash_text = str(execn.get("cash") or "").lower()
    if cash_detail or "not_checked" in cash_text or "not checked" in cash_text or _is_funding_leg(card):
        checks.append(_readiness_entry(
            "cash_buying_power",
            READINESS_CHECK_LABELS["cash_buying_power"],
            "blocked",
            cash_detail or execn.get("cash") or "funding leg must stay paired",
        ))
    elif execn.get("suggested") or execn.get("legs"):
        checks.append(_readiness_entry(
            "cash_buying_power",
            READINESS_CHECK_LABELS["cash_buying_power"],
            "ok",
            "cash rail has no render-visible blocker",
        ))
    else:
        checks.append(_readiness_entry(
            "cash_buying_power",
            READINESS_CHECK_LABELS["cash_buying_power"],
            "unknown",
            "buying power not represented on this card",
        ))

    account_detail = _taxonomy_detail(card, "account_sleeve_eligibility")
    if account_detail or execn.get("hard_flags") or execn.get("transfer_dependency"):
        checks.append(_readiness_entry(
            "account_eligibility",
            READINESS_CHECK_LABELS["account_eligibility"],
            "blocked",
            account_detail or "account or transfer blocker visible",
        ))
    elif execn.get("suggested") or execn.get("eligible") or execn.get("legs"):
        checks.append(_readiness_entry(
            "account_eligibility",
            READINESS_CHECK_LABELS["account_eligibility"],
            "ok",
            "eligible account lane is render-visible",
        ))
    else:
        checks.append(_readiness_entry(
            "account_eligibility",
            READINESS_CHECK_LABELS["account_eligibility"],
            "unknown",
            "account lane not represented on this card",
        ))

    cap_detail = _taxonomy_detail(card, "cap_room")
    heat = str(sizing.get("heat") or "").strip()
    if cap_detail or heat in {"ABOVE_CAP", "CAP_CLIPPED"}:
        checks.append(_readiness_entry(
            "cap_room",
            READINESS_CHECK_LABELS["cap_room"],
            "blocked",
            cap_detail or heat or "cap room blocked",
        ))
    elif sizing:
        checks.append(_readiness_entry(
            "cap_room",
            READINESS_CHECK_LABELS["cap_room"],
            "ok",
            _cap_room_text(sizing),
        ))
    else:
        checks.append(_readiness_entry(
            "cap_room",
            READINESS_CHECK_LABELS["cap_room"],
            "unknown",
            "no sizing/cap lane on this card",
        ))

    research_detail = _taxonomy_detail(card, "research_disconfirmation", "source_freshness")
    if research_detail or display.get("not_checked"):
        checks.append(_readiness_entry(
            "research_disconfirmation",
            READINESS_CHECK_LABELS["research_disconfirmation"],
            "blocked",
            research_detail or "not-checked source or research lane visible",
        ))
    elif _card_is_evidence_starved(card, display):
        checks.append(_readiness_entry(
            "research_disconfirmation",
            READINESS_CHECK_LABELS["research_disconfirmation"],
            "unknown",
            "evidence is still thin",
        ))
    else:
        checks.append(_readiness_entry(
            "research_disconfirmation",
            READINESS_CHECK_LABELS["research_disconfirmation"],
            "ok",
            "no research/disconfirmation blocker visible",
        ))

    if "event risk" in blob or "event-risk" in blob:
        checks.append(_readiness_entry(
            "event_risk",
            READINESS_CHECK_LABELS["event_risk"],
            "blocked",
            "event-risk blocker visible",
        ))
    else:
        checks.append(_readiness_entry(
            "event_risk",
            READINESS_CHECK_LABELS["event_risk"],
            "ok",
            "no event-risk blocker visible",
        ))
    return checks


def _trade_executable_layer(
    card: dict[str, Any],
    base_state: str,
    prior_layers: list[dict[str, str]],
    checklist: list[dict[str, str]],
) -> dict[str, str]:
    blockers = [row for row in prior_layers + checklist if row.get("status") == "blocked"]
    unknowns = [row for row in prior_layers + checklist if row.get("status") == "unknown"]
    if base_state == "ACT" and not blockers and not unknowns:
        return _readiness_entry(
            "trade_executable",
            READINESS_LAYER_LABELS["trade_executable"],
            "ok",
            "all readiness layers clear",
        )
    if base_state == "ACT":
        first_gap = blockers[0] if blockers else unknowns[0]
        return _readiness_entry(
            "trade_executable",
            READINESS_LAYER_LABELS["trade_executable"],
            "blocked" if blockers else "unknown",
            f"ACT held until {first_gap.get('label')} clears",
        )
    if base_state == "WATCH":
        return _readiness_entry(
            "trade_executable",
            READINESS_LAYER_LABELS["trade_executable"],
            "unknown",
            "watch state has no executable trade rail",
        )
    return _readiness_entry(
        "trade_executable",
        READINESS_LAYER_LABELS["trade_executable"],
        "blocked",
        f"{base_state} state is not executable",
    )


def _card_readiness_model(
    card: dict[str, Any],
    trust_panel: dict[str, Any],
    data_health: dict[str, Any],
) -> dict[str, Any]:
    display = card.get("conviction_display") or build_conviction_display(card)
    base_state = str(card.get("command_state") or _card_command_state(card))
    checklist = _readiness_checklist(card, display)
    prior_layers = [
        _routine_fired_layer(trust_panel),
        _boundary_artifact_layer(card, data_health),
        _signal_interpreted_layer(card, display),
        _decision_eligible_layer(card, base_state),
    ]
    trade_layer = _trade_executable_layer(card, base_state, prior_layers, checklist)
    layers = prior_layers + [trade_layer]
    counts = {
        "ok": sum(1 for row in layers if row.get("status") == "ok"),
        "blocked": sum(1 for row in layers if row.get("status") == "blocked"),
        "unknown": sum(1 for row in layers if row.get("status") == "unknown"),
    }
    first_gap = next((row for row in layers if row.get("status") != "ok"), None)
    return {
        "layers": layers,
        "checklist": checklist,
        "counts": counts,
        "summary": (
            f"Blocked at {first_gap.get('label')}: {first_gap.get('detail')}"
            if first_gap else "All readiness layers clear"
        ),
        "base_command_state": base_state,
        "honesty_rule": "Routine proof is only the first layer; it never means fresh boundary data or executable trade.",
    }


def _annotate_readiness_models(
    cards: list[dict[str, Any]],
    trust_panel: dict[str, Any],
    data_health: dict[str, Any],
) -> None:
    for card in cards:
        readiness = _card_readiness_model(card, trust_panel, data_health)
        card["readiness"] = readiness
        state = str(card.get("command_state") or _card_command_state(card))
        trade_layer = next(
            (row for row in readiness.get("layers") or [] if row.get("key") == "trade_executable"),
            None,
        )
        if state == "ACT" and (trade_layer or {}).get("status") != "ok":
            downgrade = "RESOLVE" if any(row.get("status") == "blocked" for row in readiness.get("layers") or []) else "DECIDE"
            card["command_state"] = downgrade
            card["command_state_detail"] = "readiness ladder incomplete"
        else:
            card["command_state_detail"] = COMMAND_STATE_COPY.get(state, card.get("command_state_detail") or "")


def _card_lane(card: dict[str, Any]) -> str:
    move = (card.get("decision_card") or {}).get("move") or {}
    lane = str(move.get("lane") or card.get("lane") or card.get("kind") or "").strip()
    if lane:
        return lane
    direction = _card_action_direction(card).lower()
    return direction or "decision"


def _decision_key(card: dict[str, Any]) -> str:
    ticker = str(card.get("ticker") or "").strip().upper() or "UNKNOWN"
    return f"{ticker}|{_card_lane(card)}"


def _decision_key_from_any(card: dict[str, Any]) -> str:
    if card.get("decision_key"):
        return str(card["decision_key"])
    parts = card.get("decision_key_parts") or {}
    ticker = str(parts.get("ticker") or card.get("ticker") or "").strip().upper() or "UNKNOWN"
    move = (card.get("decision_card") or {}).get("move") or {}
    lane = str(
        parts.get("lane")
        or move.get("lane")
        or card.get("lane")
        or card.get("kind")
        or move.get("direction")
        or card.get("direction")
        or "decision"
    ).strip()
    return f"{ticker}|{lane or 'decision'}"


def _card_text_blob(card: dict[str, Any], display: dict[str, Any]) -> str:
    move = (card.get("decision_card") or {}).get("move") or {}
    window = card.get("window") or {}
    sizing = card.get("sizing") or {}
    return _text_blob(
        move,
        window.get("class"),
        window.get("reasons") or [],
        window.get("flips") or [],
        card.get("card_blockers") or [],
        card.get("gate_notes") or [],
        display.get("raises") or [],
        display.get("not_checked") or [],
        display.get("conflict") or "",
        sizing,
    ).lower()


def _card_is_operator_actionable(
    card: dict[str, Any],
    display: dict[str, Any],
    *,
    window_class: str,
    posture: dict[str, str],
) -> bool:
    return (
        not _is_funding_leg(card)
        and posture.get("copy_verb") == "ACT"
        and window_class == "OPEN-NOW"
        and not card.get("card_blockers")
        and not card.get("conflicts")
        and not display.get("conflict")
    )


def _ownership_bucket_for_card(card: dict[str, Any], display: dict[str, Any]) -> dict[str, Any]:
    window = card.get("window") or {}
    window_class = str(window.get("class") or "WAIT")
    direction = _card_action_direction(card)
    posture = _review_posture(
        card,
        check_first=bool(card.get("card_blockers")),
        window_class=window_class,
        direction=direction,
    )
    blob = _card_text_blob(card, display)
    sizing = card.get("sizing") or {}
    if _card_is_operator_actionable(card, display, window_class=window_class, posture=posture):
        return {
            "bucket": "operator_owned_actionable_now",
            "label": PASSIVITY_BUCKET_LABELS["operator_owned_actionable_now"],
            "reason": "No card blocker, conflict, or wait gate is visible in this render.",
            "operator_latency": True,
            "open_days": 0,
        }
    if _is_funding_leg(card) or sizing.get("heat") in {"ABOVE_CAP", "CAP_CLIPPED"} or any(
        token in blob for token in ("cap", "cash", "funding", "concentration", "leverage", "margin", "eligibility")
    ):
        return {
            "bucket": "cap_risk_cash_constrained",
            "label": PASSIVITY_BUCKET_LABELS["cap_risk_cash_constrained"],
            "reason": "Capital, funding, account, or risk rail constrains this item.",
            "operator_latency": False,
        }
    if any(token in blob for token in ("not_checked", "not checked", "source", "13f", "insider", "fs inbox", "fundstrat", "uw proof", "same-session", "graded call")):
        return {
            "bucket": "waiting_source_data_freshness",
            "label": PASSIVITY_BUCKET_LABELS["waiting_source_data_freshness"],
            "reason": "Source, same-session proof, or data freshness is still missing.",
            "operator_latency": False,
        }
    if window_class in {"WAIT", "GATED", "STAGE-ONLY"} or any(
        token in blob for token in ("gate", "price", "tape", "trigger", "market", "flow")
    ):
        return {
            "bucket": "waiting_market_price_tape_gate",
            "label": PASSIVITY_BUCKET_LABELS["waiting_market_price_tape_gate"],
            "reason": "Market, price, tape, or timing gate is still waiting.",
            "operator_latency": False,
        }
    if any(token in blob for token in ("wired", "system", "lane goes live")):
        return {
            "bucket": "system_blocked_not_checked",
            "label": PASSIVITY_BUCKET_LABELS["system_blocked_not_checked"],
            "reason": "The system has not checked or wired one required lane.",
            "operator_latency": False,
        }
    return {
        "bucket": "research_watch_only",
        "label": PASSIVITY_BUCKET_LABELS["research_watch_only"],
        "reason": "Visible for research/watch context; not an operator-latency item.",
        "operator_latency": False,
    }


def _annotate_action_first_fields(cards: list[dict[str, Any]]) -> None:
    for card in cards:
        display = card.get("conviction_display") or build_conviction_display(card)
        key = _decision_key(card)
        card["decision_key"] = key
        card["decision_key_parts"] = {
            "ticker": str(card.get("ticker") or "").strip().upper() or "UNKNOWN",
            "lane": _card_lane(card),
        }
        card["ownership"] = _ownership_bucket_for_card(card, display)


def _passivity_summary(cards: list[dict[str, Any]], watch_queue: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {key: 0 for key in PASSIVITY_BUCKET_LABELS}
    rows: list[dict[str, Any]] = []
    for card in cards:
        ownership = card.get("ownership") or {}
        bucket = ownership.get("bucket") or "research_watch_only"
        counts[bucket] = counts.get(bucket, 0) + 1
        row = {
            "decision_key": card.get("decision_key") or _decision_key(card),
            "ticker": str(card.get("ticker") or "").strip().upper(),
            "lane": _card_lane(card),
            "bucket": bucket,
            "label": PASSIVITY_BUCKET_LABELS.get(bucket, bucket),
            "reason": ownership.get("reason") or "",
        }
        if ownership.get("operator_latency"):
            row["open_days"] = int(ownership.get("open_days") or 0)
        rows.append(row)
    if watch_queue:
        counts["research_watch_only"] = counts.get("research_watch_only", 0) + len(watch_queue)
    line = (
        f"{counts.get('operator_owned_actionable_now', 0)} are yours to decide now; "
        f"{counts.get('waiting_market_price_tape_gate', 0)} waiting on market/price/tape; "
        f"{counts.get('waiting_source_data_freshness', 0)} waiting on source/data; "
        f"{counts.get('research_watch_only', 0)} research/watch-only; "
        f"{counts.get('cap_risk_cash_constrained', 0)} cap/risk/cash constrained; "
        f"{counts.get('system_blocked_not_checked', 0)} system-blocked/not_checked."
    )
    return {
        "line": line,
        "counts": counts,
        "operator_latency_count": counts.get("operator_owned_actionable_now", 0),
        "rows": rows,
        "honesty_rule": "Only bucket operator_owned_actionable_now is operator latency; all other buckets are waiting on rails, markets, data, or research state.",
    }


def _add_blocker_category(
    rows: list[dict[str, str]],
    seen: set[str],
    category: str,
    evidence: str,
) -> None:
    if category in seen:
        return
    seen.add(category)
    rows.append({
        "category": category,
        "label": BLOCKER_CATEGORY_LABELS[category],
        "evidence": evidence.strip() or BLOCKER_CATEGORY_LABELS[category],
    })


def _blocker_taxonomy(card: dict[str, Any], display: dict[str, Any]) -> dict[str, Any]:
    blockers = [str(row or "").strip() for row in card.get("card_blockers") or [] if str(row or "").strip()]
    window = card.get("window") or {}
    window_class = str(window.get("class") or "WAIT")
    sizing = card.get("sizing") or {}
    execn = card.get("execution") or {}
    dossier = card.get("dossier") or {}
    blob = _text_blob(
        blockers,
        display.get("conflict"),
        display.get("not_checked") or [],
        card.get("conflicts") or [],
        window.get("reasons") or [],
        window.get("flips") or [],
        card.get("gate_notes") or [],
        sizing,
        execn,
        dossier,
    ).lower()
    has_hard_context = bool(
        blockers
        or display.get("conflict")
        or card.get("conflicts")
        or window_class in {"WAIT", "GATED", "STAGE-ONLY"}
        or sizing.get("heat") in {"ABOVE_CAP", "CAP_CLIPPED"}
        or _is_funding_leg(card)
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for blocker in blockers:
        low = blocker.lower()
        if any(token in low for token in ("gate", "price", "tape", "trigger", "qqq", "market")):
            _add_blocker_category(rows, seen, "price_tape_gate", blocker)
        elif any(token in low for token in ("source", "inbox", "fundstrat", "analyst", "track record", "dossier", "positions", "fresh")):
            _add_blocker_category(rows, seen, "source_freshness", blocker)
    if window_class in {"WAIT", "GATED", "STAGE-ONLY"} and any(token in blob for token in ("gate", "price", "tape", "trigger", "market")):
        _add_blocker_category(rows, seen, "price_tape_gate", window_class.replace("-", " ").lower())
    if display.get("conflict") or card.get("conflicts"):
        _add_blocker_category(rows, seen, "flow_evidence_conflict", str(display.get("conflict") or "conflicting decision lane"))
    if sizing.get("heat") in {"ABOVE_CAP", "CAP_CLIPPED"}:
        _add_blocker_category(rows, seen, "cap_room", str(sizing.get("heat")))
    if _is_funding_leg(card) or any(token in blob for token in ("cash", "funding", "funds")):
        _add_blocker_category(rows, seen, "cash_funding", "funding or cash rail")
    if has_hard_context and any(token in blob for token in ("concentration", "leverage", "margin")):
        _add_blocker_category(rows, seen, "concentration_leverage", "concentration/leverage rail")
    if has_hard_context and any(token in blob for token in ("eligibility", "sleeve", "account", "etf-only", "etf only")):
        _add_blocker_category(rows, seen, "account_sleeve_eligibility", "account/sleeve eligibility")
    if has_hard_context and (display.get("not_checked") or any(token in blob for token in ("disconfirmation", "research", "dossier"))):
        _add_blocker_category(rows, seen, "research_disconfirmation", "research or disconfirmation lane")

    uncategorized = [blocker for blocker in blockers if not any(blocker == row["evidence"] for row in rows)]
    if rows:
        total = len(rows)
        blocked_by = rows[0]["label"]
        waiting = ", ".join(row["label"] for row in rows[1:]) or rows[0]["label"]
        return {
            "enumerable": True,
            "met": 0,
            "total": total,
            "line": f"0 of {total} blockers cleared; blocked by {blocked_by}; waiting on {waiting}.",
            "unmet": rows,
            "uncategorized": uncategorized,
            "honesty_rule": "Count uses only currently visible unmet blocker categories; it never means the move is ready.",
        }
    if blockers:
        return {
            "enumerable": False,
            "met": None,
            "total": None,
            "line": f"Blocked by {blockers[0]}.",
            "unmet": [],
            "uncategorized": blockers,
            "honesty_rule": "Blocker was visible but not cleanly enumerable, so no M-of-N count is shown.",
        }
    return {
        "enumerable": False,
        "met": None,
        "total": None,
        "line": "No blocker count; no current blocker surfaced.",
        "unmet": [],
        "uncategorized": [],
        "honesty_rule": "No M-of-N count is shown without visible unmet blockers.",
    }


def _annotate_blocker_taxonomy(cards: list[dict[str, Any]]) -> None:
    for card in cards:
        display = card.get("conviction_display") or build_conviction_display(card)
        card["blocker_taxonomy"] = _blocker_taxonomy(card, display)


def _has_named_resolve_blocker(card: dict[str, Any], display: dict[str, Any] | None = None) -> bool:
    display = display or card.get("conviction_display") or build_conviction_display(card)
    taxonomy = card.get("blocker_taxonomy") or {}
    window_class = str((card.get("window") or {}).get("class") or "WAIT")
    sizing = card.get("sizing") or {}
    return bool(
        taxonomy.get("unmet")
        or (taxonomy.get("enumerable") and int(taxonomy.get("total") or 0) > 0)
        or card.get("card_blockers")
        or card.get("conflicts")
        or display.get("conflict")
        or window_class in {"WAIT", "GATED", "STAGE-ONLY"}
        or str(sizing.get("heat") or "") in {"ABOVE_CAP", "CAP_CLIPPED"}
        or _is_funding_leg(card)
    )


def _card_command_state(card: dict[str, Any]) -> str:
    display = card.get("conviction_display") or build_conviction_display(card)
    if _has_named_resolve_blocker(card, display):
        return "RESOLVE"
    if not _is_material(card):
        return "WATCH"
    ownership = card.get("ownership") or {}
    window_class = str((card.get("window") or {}).get("class") or "WAIT")
    if ownership.get("bucket") == "operator_owned_actionable_now" and window_class == "OPEN-NOW":
        return "ACT"
    return "DECIDE"


def _annotate_command_states(cards: list[dict[str, Any]]) -> None:
    for card in cards:
        state = _card_command_state(card)
        card["command_state"] = state
        card["command_state_detail"] = COMMAND_STATE_COPY[state]


def _command_action_label(card: dict[str, Any]) -> str:
    lane = _card_lane(card).replace("_", " ").lower()
    direction = _card_action_direction(card).lower()
    if "trim" in lane:
        return "trim"
    if "sell" in lane or direction == "sell":
        return "sell"
    if "add" in lane or direction in {"add", "buy"}:
        return "add" if "add" in lane else "buy"
    if lane and lane != "decision":
        return lane
    return direction or "decision"


def _primary_command_title(card: dict[str, Any], state: str) -> str:
    ticker = str(card.get("ticker") or "").strip().upper() or "decision"
    action = _command_action_label(card)
    if state == "ACT":
        return f"{_card_action_direction(card).upper() or 'ACT'} {ticker}"
    if state == "DECIDE":
        return f"Decide {ticker} {action}"
    if state == "RESOLVE":
        return f"Resolve {ticker} {action}"
    return f"Watch {ticker}"


def _primary_leverage_score(card: dict[str, Any]) -> tuple[float, float]:
    dollars = _coerce_float(card.get("dollars")) or 0.0
    suggested = _coerce_float((card.get("sizing") or {}).get("suggested_usd")) or 0.0
    priority = _coerce_float(card.get("priority")) or 0.0
    return max(dollars, suggested), priority


def _primary_capital_decision(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = list(cards)
    if not ranked:
        return None

    def sort_key(card: dict[str, Any]) -> tuple[int, int, int, float, float]:
        state = str(card.get("command_state") or _card_command_state(card))
        leverage, priority = _primary_leverage_score(card)
        return (
            COMMAND_STATE_RANK.get(state, 99),
            1 if _is_funding_leg(card) else 0,
            0 if _is_material(card) else 1,
            -leverage,
            -priority,
        )

    ranked.sort(key=sort_key)
    return ranked[0]


def _source_decide_prompts(feed: dict[str, Any]) -> list[dict[str, str]]:
    prompts: list[dict[str, str]] = []
    for row in _candidate_rows(feed.get("actions")):
        ticker = str(row.get("ticker") or row.get("symbol") or "SYSTEM").strip().upper() or "SYSTEM"
        lane = str(row.get("kind") or row.get("decision_group") or "action_prompt").strip() or "action_prompt"
        label = str(row.get("what") or row.get("your_move") or row.get("action_label") or lane).strip()
        prompts.append({
            "ticker": ticker,
            "lane": lane,
            "decision_key": f"{ticker}|{lane}",
            "label": label,
            "source": "feed.actions",
        })
    return prompts


def _build_command_strip(
    feed: dict[str, Any],
    cards: list[dict[str, Any]],
    watch_queue: list[dict[str, Any]],
    trust_panel: dict[str, Any],
    disposition_pressure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counts = {state: 0 for state in COMMAND_STATES}
    for card in cards:
        state = str(card.get("command_state") or _card_command_state(card))
        if state not in counts:
            state = "WATCH"
        counts[state] += 1
    decide_prompts = _source_decide_prompts(feed)
    counts["DECIDE"] += len(decide_prompts)
    for row in (disposition_pressure or {}).get("rows") or []:
        state = str(row.get("state") or "DECIDE")
        if state not in counts:
            state = "DECIDE"
        counts[state] += 1
    counts["WATCH"] += len(watch_queue or [])
    rows = [
        {"state": state, "count": counts[state], "detail": COMMAND_STATE_COPY[state]}
        for state in COMMAND_STATES
    ]
    system_state = "confident" if counts["ACT"] else "starved"
    system_line = (
        "Confident: at least one visible command has cleared all render-visible survival rails."
        if counts["ACT"]
        else "Starved: no executable command has cleared the rails; surface the highest-leverage unblock."
    )
    trust_status = str(trust_panel.get("status") or "info")
    trust_headline = str(trust_panel.get("headline") or "").strip()
    if trust_status in {"warn", "alert"} and trust_headline:
        system_line = f"{system_line} System caveat: {trust_headline}"
    return {
        "counts": counts,
        "rows": rows,
        "line": " | ".join(f"{counts[state]} {state}" for state in COMMAND_STATES),
        "system_state": system_state,
        "system_line": system_line,
        "source_decide_prompts": decide_prompts[:8],
        "honesty_rule": "Render-only command surface; counts do not change scoring, sizing, gates, ranking, or dispositions.",
    }


def _command_button_for_state(card: dict[str, Any], state: str, cid: str) -> dict[str, str]:
    if state == "DECIDE":
        return {
            "card_id": cid,
            "label": "RECHECK",
            "state_verb": "RECHECK",
            "copy": f"RECHECK {cid} choose yes/pass/recheck before any action",
            "muted": "1",
        }
    if state == "RESOLVE":
        return {
            "card_id": cid,
            "label": "RESOLVE",
            "state_verb": "RECHECK",
            "copy": f"RECHECK {cid} resolve named blockers before action",
            "muted": "1",
        }
    return {
        "card_id": cid,
        "label": "KEEP WATCH",
        "state_verb": "WATCH",
        "copy": f"WATCH {cid} keep quiet until evidence strengthens",
        "muted": "1",
    }


def _rail_line_for_card(card: dict[str, Any]) -> str:
    sizing = card.get("sizing") or {}
    execn = card.get("execution") or {}
    parts = []
    if sizing.get("cap_basis"):
        parts.append(str(sizing["cap_basis"]))
    if sizing.get("heat"):
        parts.append(f"heat {sizing['heat']}")
    if execn.get("cash"):
        parts.append(f"cash {execn['cash']}")
    if execn.get("suggested"):
        suggested = execn["suggested"]
        parts.append(
            "account "
            + " ".join(str(suggested.get(key) or "").strip() for key in ("owner", "broker", "account")).strip()
        )
    if _is_funding_leg(card):
        parts.append("funding leg must stay paired")
    return "; ".join(part for part in parts if part) or "Normal source, sizing, concentration, and account rails still apply."


def _cap_room_text(sizing: dict[str, Any]) -> str:
    cap_basis = str(sizing.get("cap_basis") or "")
    match = re.search(r"cap room\s+\$([0-9,]+)", cap_basis, flags=re.IGNORECASE)
    room = f"${match.group(1)}" if match else None
    heat = str(sizing.get("heat") or "not_checked")
    if room:
        return f"cap room {room} (heat {heat})"
    suggested = sizing.get("suggested_usd")
    if suggested is not None:
        return f"cap room not parsed; cap-suggested {_money_text(suggested)} (heat {heat})"
    return f"cap room not_checked (heat {heat})"


def _funding_source_text(card: dict[str, Any], cards: list[dict[str, Any]]) -> str:
    ticker = str(card.get("ticker") or "").strip().upper()
    sources = []
    for candidate in cards:
        if not _is_funding_leg(candidate):
            continue
        funds = str(candidate.get("funds") or "")
        if ticker and ticker in funds.upper():
            sources.append(f"{str(candidate.get('ticker') or '').upper()} trim -> {funds}")
    if sources:
        return "funding source " + "; ".join(sources[:2])
    cash = str((card.get("execution") or {}).get("cash") or "").strip()
    if cash:
        return f"funding source cash/buying power {cash}"
    return "funding source not_checked; confirm cash/buying power before trade"


def _concentration_rail_text(card: dict[str, Any]) -> str:
    sizing = card.get("sizing") or {}
    current = sizing.get("current_pct")
    ceiling = sizing.get("ceiling_pct")
    floor = sizing.get("floor_pct")
    if current is not None or ceiling is not None:
        parts = []
        if current is not None:
            parts.append(f"current {float(current):.1f}%")
        if floor is not None:
            parts.append(f"floor {float(floor):.1f}%")
        if ceiling is not None:
            parts.append(f"ceiling {float(ceiling):.1f}%")
        return "concentration rail " + " / ".join(parts)
    lookthrough = card.get("lookthrough") or {}
    if lookthrough.get("overlap_line"):
        return f"concentration rail {lookthrough['overlap_line']}"
    return "concentration rail not_checked"


def _account_eligibility_text(card: dict[str, Any]) -> str:
    execn = card.get("execution") or {}
    suggested = execn.get("suggested") or {}
    if suggested:
        acct = " ".join(
            str(suggested.get(key) or "").strip()
            for key in ("owner", "broker", "account")
            if str(suggested.get(key) or "").strip()
        )
        eligible = "eligible" if suggested.get("eligible", True) else "not eligible"
        flags = ", ".join(str(flag) for flag in suggested.get("account_flags") or suggested.get("leg_flags") or [])
        suffix = f"; flags {flags}" if flags else ""
        return f"account eligibility {acct or 'suggested account'} {eligible}{suffix}"
    hard_flags = execn.get("hard_flags") or []
    if hard_flags:
        return f"account eligibility blocked: {hard_flags[0].get('detail') or hard_flags[0].get('code')}"
    return "account eligibility not_checked"


def _leverage_margin_text(card: dict[str, Any]) -> str:
    cash = str((card.get("execution") or {}).get("cash") or "").strip()
    if cash:
        return f"leverage/margin: {cash}; no margin expansion assumed"
    return "leverage/margin: no margin expansion assumed; confirm buying power"


def _size_to_goal_model(
    card: dict[str, Any],
    *,
    goal_anchor: dict[str, Any],
    cards: list[dict[str, Any]],
) -> dict[str, Any] | None:
    direction = _card_action_direction(card)
    if direction not in {"BUY", "ADD"}:
        return None
    dollars = _coerce_float(card.get("dollars"))
    gap = _coerce_float(goal_anchor.get("gap_usd"))
    if dollars is None:
        tranche = "tranche not readable"
        pct = None
    else:
        tranche = f"{_money_text(dollars)} tranche"
        pct = round(100.0 * dollars / gap, 1) if gap and gap > 0 else None
    contribution = f"{tranche} = {pct:.1f}% of goal gap" if pct is not None else f"{tranche}; goal gap unavailable"
    line = (
        f"{contribution}; "
        f"{_cap_room_text(card.get('sizing') or {})}; "
        f"{_funding_source_text(card, cards)}; "
        f"{_concentration_rail_text(card)}; "
        f"{_account_eligibility_text(card)}; "
        f"{_leverage_margin_text(card)}."
    )
    return {
        "line": line,
        "goal_gap_pct": pct,
        "tranche_usd": dollars,
        "honesty_rule": "Goal contribution is render-only and always shown with survival rails.",
    }


def _annotate_size_to_goal(cards: list[dict[str, Any]], goal_anchor: dict[str, Any]) -> None:
    for card in cards:
        model = _size_to_goal_model(card, goal_anchor=goal_anchor, cards=cards)
        if model:
            card["size_to_goal"] = model


def _parse_iso_day(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _after_action_model(card: dict[str, Any], today_iso: str) -> dict[str, Any]:
    last = card.get("last_disposition") or {}
    if not last:
        next_review = str(card.get("recheck_date") or "")
        return {
            "status": "open",
            "open": True,
            "outcome_status": "pending_disposition",
            "source_grading_status": "not_eligible_until_disposition",
            "line": f"after action: no ACT/PASS/RECHECK logged; open; next review {next_review or 'not scheduled'}",
            "outcome_line": "outcome: pending disposition; source grading unchanged",
            "next_review_date": next_review,
        }
    verb = str(last.get("verb") or "").upper()
    et_date = str(last.get("et_date") or "")
    today_day = _parse_iso_day(today_iso)
    then = _parse_iso_day(et_date)
    age = (today_day - then).days if today_day and then else None
    open_state = verb in {"RECHECK", "UNDO"}
    next_review = str(last.get("resurface_date") or (card.get("recheck_date") if open_state else "") or "")
    age_text = f"{age}d ago" if age is not None else "age unknown"
    state_text = "open" if open_state else "closed"
    outcome = str(last.get("outcome") or last.get("result") or "").strip()
    if outcome:
        outcome_status = "logged"
        source_grading_status = "eligible_for_review"
        outcome_line = f"outcome: {outcome}; source grading can review this disposition"
    elif verb in {"ACT", "PASS"}:
        outcome_status = "missing"
        source_grading_status = "not_graded_no_outcome"
        outcome_line = "outcome: not logged; source grading unchanged"
    else:
        outcome_status = "pending_recheck"
        source_grading_status = "not_eligible_until_outcome"
        outcome_line = "outcome: pending recheck; source grading unchanged"
    return {
        "verb": verb,
        "et_date": et_date,
        "age_days": age,
        "open": open_state,
        "next_review_date": next_review,
        "status": state_text,
        "outcome_status": outcome_status,
        "source_grading_status": source_grading_status,
        "line": (
            f"last disposition: {verb} on {et_date}; {age_text}; "
            f"next review {next_review or 'not scheduled'}; {state_text}"
        ),
        "outcome_line": outcome_line,
    }


def _annotate_after_action(cards: list[dict[str, Any]], today_iso: str) -> None:
    for card in cards:
        card["after_action"] = _after_action_model(card, today_iso)


def _candidate_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("rows", "items", "actions", "research_actions", "prospects", "watch"):
        rows = value.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return [row for row in value.values() if isinstance(row, dict)]


def _candidate_label(row: dict[str, Any], fallback: str) -> str:
    return str(
        row.get("what")
        or row.get("label")
        or row.get("title")
        or row.get("summary")
        or row.get("name")
        or row.get("ticker")
        or fallback
    ).strip()


def _build_disposition_coverage(
    feed: dict[str, Any],
    cards: list[dict[str, Any]],
    watch_queue: list[dict[str, Any]],
) -> dict[str, Any]:
    covered_tickers = {str(card.get("ticker") or "").strip().upper() for card in cards if card.get("ticker")}
    rows: list[dict[str, str]] = []

    def add_row(source: str, row: dict[str, Any], status: str, reason: str) -> None:
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        label = _candidate_label(row, source)
        rows.append({
            "source": source,
            "ticker": ticker,
            "label": label,
            "status": status,
            "reason": reason,
        })

    for row in _candidate_rows(feed.get("actions")):
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and ticker in covered_tickers:
            continue
        kind = str(row.get("kind") or "").strip().lower()
        promotable = kind in {"lean_in", "buy", "add", "trim", "reduce", "sell", "exit"}
        add_row(
            "feed.actions",
            row,
            "could_promote_to_today_decide" if promotable else "intentionally_watch_research_only",
            "uncovered action-lane row" if promotable else "action row is not a capital-decision kind",
        )

    for source in ("research_actions", "prospects", "research", "social_watch"):
        for row in _candidate_rows(feed.get(source)):
            ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
            if ticker and ticker in covered_tickers:
                continue
            add_row(source, row, "intentionally_watch_research_only", f"{source} stays watch/research-only")

    for row in watch_queue:
        add_row("watch_queue", row, "intentionally_watch_research_only", "pullback/watch queue is not an action card")

    promote = sum(1 for row in rows if row["status"] == "could_promote_to_today_decide")
    watch_only = sum(1 for row in rows if row["status"] == "intentionally_watch_research_only")
    line = (
        f"{len(rows)} visible item{'s' if len(rows) != 1 else ''} not disposition-covered; "
        f"{promote} could promote to Today/Decide; "
        f"{watch_only} intentionally watch/research-only."
    )
    return {
        "line": line,
        "counts": {
            "not_covered": len(rows),
            "could_promote_to_today_decide": promote,
            "intentionally_watch_research_only": watch_only,
        },
        "rows": rows[:10],
        "total_count": len(rows),
        "honesty_rule": "Coverage is render-only; social/watch/research rows are not promoted into trade cards here.",
    }


def _primary_button_model(card: dict[str, Any] | None) -> dict[str, str]:
    if not card:
        return {}
    state = str(card.get("command_state") or _card_command_state(card))
    cid = str(card.get("card_id") or "")
    if state != "ACT":
        return _command_button_for_state(card, state, cid)
    display = card.get("conviction_display") or build_conviction_display(card)
    window_class = str((card.get("window") or {}).get("class") or "WAIT")
    direction = _card_action_direction(card)
    posture = _review_posture(
        card,
        check_first=bool(card.get("card_blockers")),
        window_class=window_class,
        direction=direction,
    )
    copy = (
        f"ACT {cid}" if posture["copy_verb"] == "ACT"
        else f'{posture["copy_verb"]} {cid}{posture["copy_suffix"]}'
    )
    return {
        "card_id": cid,
        "label": posture.get("label") or posture.get("copy_verb") or "RECHECK",
        "state_verb": posture.get("state_verb") or posture.get("copy_verb") or "RECHECK",
        "copy": copy,
        "muted": "0" if posture.get("copy_verb") == "ACT" else "1",
    }


_DARK_LANE_STATUSES = {"not_checked", "behind", "stale", "missing", "empty"}


def _load_committed_dashboard_feed() -> dict[str, Any] | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(SRC.parent), "show", "HEAD:src/latest_cockpit_feed.json"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _baseline_today_decide(feed: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(feed, dict):
        return {}
    return feed.get("today_decide") or {}


def _gate_key(row: dict[str, Any]) -> str:
    return str(row.get("gate_id") or row.get("symbol") or "").strip()


def _gate_state(row: dict[str, Any]) -> str:
    return str(row.get("state") or row.get("stored_state") or "unknown").strip()


def _health_key(row: dict[str, Any]) -> str:
    return "|".join(
        part for part in (
            str(row.get("source") or "").strip(),
            str(row.get("ticker") or "").strip().upper(),
            str(row.get("symbol") or "").strip().upper(),
            str(row.get("gate_id") or "").strip(),
            str(row.get("label") or "").strip(),
        )
        if part
    )


def _watch_key(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("name") or "").strip().upper()


def _build_change_delta(
    *,
    current_cards: list[dict[str, Any]],
    current_watch_queue: list[dict[str, Any]],
    current_gates: list[dict[str, Any]],
    current_data_health: dict[str, Any],
    baseline_feed: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline = _baseline_today_decide(baseline_feed)
    if not baseline:
        return {
            "label": "since last committed build",
            "status": "no_baseline",
            "line": "No prior reliable committed build baseline yet.",
            "items": [],
            "honesty_rule": "Display-only delta; it is not read by scoring, ranking, gates, sizing, or dispositions.",
        }

    items: list[dict[str, str]] = []
    previous_cards = (baseline.get("cards") or []) + (baseline.get("backlog") or [])
    previous_decisions = {_decision_key_from_any(card) for card in previous_cards if isinstance(card, dict)}
    current_decisions = {_decision_key_from_any(card) for card in current_cards if isinstance(card, dict)}
    by_key = {_decision_key_from_any(card): card for card in current_cards if isinstance(card, dict)}
    for key in sorted(current_decisions - previous_decisions):
        card = by_key.get(key) or {}
        ticker = str(card.get("ticker") or key.split("|", 1)[0]).upper()
        lane = key.split("|", 1)[1] if "|" in key else _card_lane(card)
        items.append({"kind": "new_decision", "key": key, "label": f"New decision: {ticker} / {lane}"})

    previous_watch = {_watch_key(row) for row in baseline.get("watch_queue") or [] if isinstance(row, dict)}
    current_watch = {_watch_key(row) for row in current_watch_queue if isinstance(row, dict)}
    for key in sorted(k for k in current_watch - previous_watch if k):
        items.append({"kind": "new_watch", "key": key, "label": f"New watch name: {key}"})

    previous_gates = {
        _gate_key(row): _gate_state(row)
        for row in baseline.get("gates") or []
        if isinstance(row, dict) and _gate_key(row)
    }
    for gate in current_gates:
        if not isinstance(gate, dict):
            continue
        key = _gate_key(gate)
        if not key or key not in previous_gates:
            continue
        old = previous_gates[key]
        new = _gate_state(gate)
        if old and new and old != new:
            items.append({"kind": "gate_flip", "key": key, "label": f"Gate flipped: {key} {old} -> {new}"})

    previous_health = {
        _health_key(row): str(row.get("status") or "").strip()
        for row in (baseline.get("data_health") or {}).get("items") or []
        if isinstance(row, dict) and _health_key(row)
    }
    for row in (current_data_health.get("items") or []):
        if not isinstance(row, dict):
            continue
        key = _health_key(row)
        status = str(row.get("status") or "").strip()
        if not key or status not in _DARK_LANE_STATUSES:
            continue
        previous = previous_health.get(key)
        if previous != status:
            label = str(row.get("label") or row.get("source") or key)
            old = previous or "not present"
            items.append({"kind": "lane_dark", "key": key, "label": f"Lane went stale/dark: {label} {old} -> {status}"})

    capped = items[:8]
    overflow = len(items) - len(capped)
    if not capped:
        line = "No decision, watch, gate, or dark-lane change versus the last committed dashboard build."
    else:
        line = "; ".join(item["label"] for item in capped)
        if overflow > 0:
            line += f"; +{overflow} more."
    return {
        "label": "since last committed build",
        "status": "changed" if items else "unchanged",
        "line": line,
        "items": capped,
        "total_count": len(items),
        "honesty_rule": "Display-only delta; it is not read by scoring, ranking, gates, sizing, or dispositions.",
    }


def _first_viewport_model(
    cards: list[dict[str, Any]],
    watch_queue: list[dict[str, Any]],
    passivity: dict[str, Any],
    change_delta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card = _primary_capital_decision(cards)
    if not card:
        return {
            "status": "empty",
            "decision": "No capital-changing decision surfaced in TODAY/DECIDE.",
            "size": "No tranche implied.",
            "blocker": "No visible decision card.",
            "changed": (change_delta or {}).get("line") or "No prior reliable build baseline yet.",
            "risk_rail": "Normal survival rails still apply.",
            "safe_wait": f"{len(watch_queue)} research/watch-only item(s) can wait.",
            "button": {},
        }
    display = card.get("conviction_display") or build_conviction_display(card)
    window_class = str((card.get("window") or {}).get("class") or "WAIT")
    taxonomy = card.get("blocker_taxonomy") or {}
    blocker = taxonomy.get("line") or _primary_blocker_text(card, display, check_first=bool(card.get("card_blockers")), window_class=window_class)
    state = str(card.get("command_state") or _card_command_state(card))
    return {
        "status": "has_primary",
        "command_state": state,
        "command_state_detail": card.get("command_state_detail") or COMMAND_STATE_COPY.get(state, ""),
        "decision_key": card.get("decision_key") or _decision_key(card),
        "ticker": str(card.get("ticker") or "").upper(),
        "lane": _card_lane(card),
        "decision": _primary_command_title(card, state),
        "size": ((card.get("size_to_goal") or {}).get("line") or f"{_money_text(card.get('dollars'))} tranche; {_size_label(card)}"),
        "blocker": blocker,
        "changed": (change_delta or {}).get("line") or "No prior reliable build baseline yet.",
        "risk_rail": _rail_line_for_card(card),
        "safe_wait": (
            f"{passivity.get('counts', {}).get('research_watch_only', 0)} research/watch-only "
            f"and {passivity.get('counts', {}).get('cap_risk_cash_constrained', 0)} rail-constrained item(s) can wait."
        ),
        "readiness": card.get("readiness") or {},
        "button": _primary_button_model(card),
    }


def _account_placement_text(ap: Any) -> str:
    if not isinstance(ap, dict):
        return ""
    owner = str(ap.get("owner") or "").strip()
    broker = str(ap.get("broker") or "").strip()
    account = str(ap.get("account") or "").strip()
    # the engine account string occasionally repeats the account token; collapse it
    if account:
        half = len(account) // 2
        if account[:half].strip() and account[:half].strip() == account[half:].strip():
            account = account[:half].strip()
        else:
            seen: list[str] = []
            for tok in account.split():
                if not seen or seen[-1] != tok:
                    seen.append(tok)
            account = " ".join(seen)
    head = " ".join(p for p in (owner, broker) if p)
    if head and account:
        return f"{head} - {account}"
    return head or account or str(ap.get("label") or "").strip()


def _build_trade_plan(feed: dict[str, Any]) -> dict[str, Any]:
    """Display-only trade-plan content lifted from ``reallocation_brief`` so the hero
    and next-move faces can render in the operator's trade-plan format. No ranking or
    sizing computed here - the values are the engine's own brief rows."""
    rb = feed.get("reallocation_brief") or {}
    moves: dict[str, dict[str, Any]] = {}
    for r in rb.get("rows") or []:
        if not isinstance(r, dict):
            continue
        tk = str(r.get("ticker") or "").upper()
        if not tk:
            continue
        moves[tk] = {
            "action": str(r.get("action") or ""),
            "notional_usd": _coerce_money(r.get("notional_usd")),
            "current_pct": _coerce_float(r.get("current_pct")),
            "target_pct": _coerce_float(r.get("target_pct")),
            "funded_by": [
                {"ticker": str(f.get("ticker") or "").upper(), "notional_usd": _coerce_money(f.get("notional_usd"))}
                for f in (r.get("funded_by") or []) if isinstance(f, dict)
            ],
            "rationale": str(r.get("rationale") or ""),
            "entry_note": str(r.get("entry_note") or ""),
            "gate": str(r.get("gate") or ""),
            "gate_reason": str(r.get("gate_reason") or ""),
            "caveats": [str(c) for c in (r.get("caveats") or []) if c],
            "blockers": [str(b) for b in (r.get("blockers") or []) if b],
            "disconfirmation": str(r.get("disconfirmation") or ""),
            "account": _account_placement_text(r.get("account_placement")),
            "rank": r.get("rank"),
            "sequence": str(r.get("sequence") or ""),
        }
    trims: dict[str, dict[str, Any]] = {}
    for t in rb.get("trims") or []:
        if not isinstance(t, dict):
            continue
        tk = str(t.get("ticker") or "").upper()
        if not tk:
            continue
        trims[tk] = {
            "notional_usd": _coerce_money(t.get("notional_usd")),
            "current_pct": _coerce_float(t.get("current_pct")),
            "target_pct": _coerce_float(t.get("target_pct")),
            "funds": [
                {"ticker": str(f.get("ticker") or "").upper(), "notional_usd": _coerce_money(f.get("notional_usd"))}
                for f in (t.get("funds") or []) if isinstance(f, dict)
            ],
        }
    return {
        "moves": moves,
        "trims": trims,
        "status": str(rb.get("status") or ""),
        "positions_as_of": rb.get("positions_snapshot_date"),
    }


def _load_sizing_tunables(path: Path | str | None = None) -> dict[str, Any]:
    """Operator-tunable sizing dials (F2). RENDER-IF-PRESENT: returns ``{}`` until
    the engine (F2) lands ``src/sizing_tunables.json``. The render NEVER authors this
    schema or computes a size - it only DISPLAYS the dials and persists operator edits."""
    p = Path(path) if path is not None else (SRC / "sizing_tunables.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _good_price_trusted(source_tags: Any, summary: Any) -> bool:
    blob = " ".join(str(t) for t in (source_tags or [])).lower() + " " + str(summary or "").lower()
    return any(k in blob for k in ("fundstrat", "top-list", "top list", "trusted", "analyst"))


def _build_good_price_tier(
    watch_queue: list[dict[str, Any]],
    fed_day_state: dict[str, Any],
    exclude_tickers: set[str] | None,
) -> dict[str, Any]:
    """Shape the good-price / lower-conviction tier (display-only) from the fed-day
    pullback queue, enriched with 52-week-high context from the packet. Excludes any
    ticker already leading as a funded move so the tier never duplicates a hero/face.
    No scoring/ranking here - impact is the packet's already-computed discount-priority
    score, surfaced honestly as "worth a look," never a buy signal."""
    packet = (fed_day_state or {}).get("packet") or {}
    freshness = str((fed_day_state or {}).get("freshness") or "absent")
    pidx: dict[str, dict[str, Any]] = {}
    for sect in ("higher_quality_pullbacks", "deep_discount_research", "act_if_green"):
        for r in packet.get(sect) or []:
            if isinstance(r, dict):
                tk = str(r.get("ticker") or "").upper()
                if tk and tk not in pidx:
                    pidx[tk] = r
    screen = packet.get("watchlist_discount_screen") or {}
    screen_count = int(screen.get("row_count") or len(screen.get("rows") or []))
    exclude = {str(t).upper() for t in (exclude_tickers or set())}
    higher: list[dict[str, Any]] = []
    deep: list[dict[str, Any]] = []
    for row in watch_queue or []:
        tk = str(row.get("ticker") or "").upper()
        if not tk or tk in exclude:
            continue
        praw = pidx.get(tk, {})
        research = str(row.get("research_status") or praw.get("research_status") or "").strip()
        section = str(row.get("section") or "")
        is_deep = (row.get("bucket") == 2) or section == "deep_discount_research" or research.upper() == "MONITOR"
        exposure_usd = _coerce_money(row.get("current_exposure_usd"))
        if exposure_usd is None:
            exposure_usd = _coerce_money(praw.get("current_exposure_usd"))
        exposure_pct = _coerce_float(praw.get("current_exposure_pct"))
        shaped = {
            "ticker": tk,
            "tier": "deep" if is_deep else "higher",
            "label": str(row.get("label") or "Pullback"),
            "impact": row.get("impact_score"),
            "pct_below_high": _coerce_float(row.get("pct_below_high")),
            "price": _coerce_float(row.get("price")),
            "fifty_two_week_high": _coerce_float(praw.get("fifty_two_week_high")),
            "high_date": str(praw.get("high_date") or ""),
            "exposure_usd": exposure_usd,
            "exposure_pct": exposure_pct,
            "disconfirmation": str(row.get("disconfirmation") or ""),
            "research_status": research,
            "source_tags": [str(t) for t in (row.get("source_tags") or []) if t],
            "summary": str(row.get("summary") or ""),
            "trusted": _good_price_trusted(row.get("source_tags"), row.get("summary")),
            "monitor": research.upper() == "MONITOR",
            "freshness": str(row.get("freshness") or freshness),
        }
        meaningful = (exposure_pct is not None and exposure_pct >= 3.0) or (
            exposure_usd is not None and exposure_usd >= 60000)
        if meaningful:
            shaped["sellgate_note"] = (
                "already a meaningful position - hold/monitor; do not sell a live "
                "thesis into weakness, and a discount alone is not a fresh add (sell-gate doctrine)")
        (deep if is_deep else higher).append(shaped)
    deep_visible = deep[:2]
    deep_more = deep[2:]
    return {
        "freshness": freshness,
        "packet_as_of": (fed_day_state or {}).get("packet_as_of"),
        "caption": str((fed_day_state or {}).get("caption") or ""),
        "honesty": str((fed_day_state or {}).get("honesty") or ""),
        "higher": higher,
        "deep_visible": deep_visible,
        "deep_more": deep_more,
        "deep_more_tickers": [r["ticker"] for r in deep_more],
        "screen_count": screen_count,
    }


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
    held_decisions_path: Path | str | None = HELD_DECISIONS_PATH,
    today: str | None = None,
    baseline_feed: dict[str, Any] | None = None,
    load_committed_baseline: bool = True,
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
    _annotate_after_action(all_cards, today_iso)
    attach_conviction_displays(all_cards)
    fed_day_state = _fed_day_freshness(feed, today_iso)
    _attach_fed_day_context(all_cards, fed_day_state)
    watch_queue = _build_fed_day_watch_queue(fed_day_state, all_cards)
    disposition_pressure = _build_disposition_pressure(watch_queue, today_iso, held_decisions_path)
    promoted_watch_keys = set(disposition_pressure.get("promoted_watch_keys") or [])
    if promoted_watch_keys:
        watch_queue = [row for row in watch_queue if _watch_row_key(row) not in promoted_watch_keys]
    _annotate_action_first_fields(all_cards)
    _annotate_blocker_taxonomy(all_cards)
    _annotate_command_states(all_cards)
    trust_panel = _build_trust_panel(data_health)
    _annotate_readiness_models(all_cards, trust_panel, data_health)
    goal_anchor = _goal_anchor(feed, goal, today_iso)
    _annotate_size_to_goal(all_cards, goal_anchor)
    passivity = _passivity_summary(all_cards, watch_queue)
    disposition_coverage = _build_disposition_coverage(feed, all_cards, watch_queue)
    command_strip = _build_command_strip(feed, all_cards, watch_queue, trust_panel, disposition_pressure)
    candidate_feed_index = _build_candidate_feed_index(feed, all_cards, watch_queue, disposition_pressure)
    gate_rows = [
        {k: g.get(k) for k in (
            "gate_id", "symbol", "state", "stored_state", "note", "confirm_rule",
            "stated", "live_price", "price_type", "live_evaluation",
        )}
        for g in gates
    ]
    if baseline_feed is None and load_committed_baseline:
        baseline_feed = _load_committed_dashboard_feed()
    change_delta = _build_change_delta(
        current_cards=all_cards,
        current_watch_queue=watch_queue,
        current_gates=gate_rows,
        current_data_health=data_health,
        baseline_feed=baseline_feed,
    )
    first_viewport = _first_viewport_model(all_cards, watch_queue, passivity, change_delta)
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
    # Good-price / lower-conviction tier (display-only) sourced from the fed-day
    # pullback packet. Exclude tickers that already lead as funded moves so the
    # tier never duplicates a hero/next-move card.
    move_tickers = {str(c.get("ticker") or "").upper() for c in all_cards
                    if _is_material(c) and not _is_funding_leg(c)}
    move_tickers |= {str(r.get("ticker") or "").upper() for r in (rb.get("rows") or [])}
    good_price_tier = _build_good_price_tier(watch_queue, fed_day_state, move_tickers)
    trade_plan = _build_trade_plan(feed)
    sizing_tunables = _load_sizing_tunables()
    return {
        "built": today_iso,
        "goal_anchor": goal_anchor,
        "plan_line": {
            "pool_usd": funding.get("pool_usd"),
            "shortfall_usd": funding.get("shortfall_usd"),
            "positions_as_of": rb.get("positions_snapshot_date"),
        },
        "gates": gate_rows,
        "data_health": data_health,
        "trust_panel": trust_panel,
        "command_strip": command_strip,
        "first_viewport": first_viewport,
        "change_delta": change_delta,
        "disposition_pressure": disposition_pressure,
        "candidate_feed_index": candidate_feed_index,
        "passivity": passivity,
        "disposition_coverage": disposition_coverage,
        "cards": stack["cards"],
        "backlog": stack["backlog"],
        "watch_queue": watch_queue,
        "watch_queue_meta": {
            "freshness": fed_day_state.get("freshness") or "absent",
            "packet_as_of": fed_day_state.get("packet_as_of"),
            "caption": fed_day_state.get("caption") or "",
        },
        "fed_day_do_not_touch": [
            str(row) for row in ((fed_day_state.get("packet") or {}).get("do_not_touch_yet") or []) if row
        ],
        "good_price_tier": good_price_tier,
        "trade_plan": trade_plan,
        "sizing_tunables": sizing_tunables,
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
.td .td-command{border:1px solid #334155;border-radius:10px;background:#08111f;padding:10px 12px;margin:10px 0 12px}
.td .td-command-head{display:flex;gap:10px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.td .td-command-line{font-size:16px;color:#f8fafc;font-weight:900;letter-spacing:.02em}
.td .td-command-state{font-size:11px;text-transform:uppercase;font-weight:900;letter-spacing:.08em}
.td .td-command-state-starved{color:#fbbf24}
.td .td-command-state-confident{color:#34d399}
.td .td-command-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:6px;margin-top:8px}
.td .td-command-cell{border:1px solid #243044;border-radius:8px;background:#0b1220;padding:7px}
.td .td-command-count{font-size:18px;color:#f8fafc;font-weight:900}
.td .td-command-label{font-size:10px;color:#93c5fd;text-transform:uppercase;font-weight:900;letter-spacing:.06em}
.td .td-command-detail{font-size:11px;color:#94a3b8;line-height:1.3;margin-top:2px}
.td .td-command-system{font-size:12px;color:#cbd5e1;line-height:1.35;margin-top:8px}
.td .td-first{border:1px solid #475569;border-left:5px solid #38bdf8;border-radius:12px;
  background:#07101e;padding:12px;margin:10px 0 12px}
.td .td-first-kicker{font-size:10px;color:#93c5fd;text-transform:uppercase;font-weight:900;letter-spacing:.08em}
.td .td-first-main{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap}
.td .td-first-decision{font-size:23px;color:#f8fafc;font-weight:900;line-height:1.12;margin:3px 0 8px}
.td .td-first-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.td .td-first-cell{border:1px solid #243044;border-radius:8px;background:#0b1220;padding:8px;min-width:0}
.td .td-first-label{font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:900;letter-spacing:.06em}
.td .td-first-value{font-size:13px;color:#e2e8f0;line-height:1.35;margin-top:3px}
.td .td-first-rail{margin:8px 0 9px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.td .td-readiness{border:1px solid #243044;border-radius:8px;background:#08111f;padding:8px;margin:9px 0}
.td .td-readiness-title{font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:900;letter-spacing:.06em;margin-bottom:6px}
.td .td-readiness-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:6px}
.td .td-ready-chip{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:6px;min-width:0}
.td .td-ready-ok{border-color:#166534;background:#071910}
.td .td-ready-blocked{border-color:#ef4444;background:#220b0b}
.td .td-ready-unknown{border-color:#f59e0b;background:#1f1606}
.td .td-ready-label{font-size:10px;color:#cbd5e1;text-transform:uppercase;font-weight:900;letter-spacing:.04em}
.td .td-ready-status{font-size:11px;color:#f8fafc;font-weight:900;margin-top:2px;text-transform:uppercase}
.td .td-ready-detail{font-size:11px;color:#94a3b8;line-height:1.25;margin-top:2px}
.td .td-pressure{border:1px solid #334155;border-left:4px solid #60a5fa;border-radius:10px;background:#08111f;padding:10px 12px;margin:10px 0 12px}
.td .td-pressure-title{font-size:12px;color:#f8fafc;font-weight:900;text-transform:uppercase;letter-spacing:.06em}
.td .td-pressure-line{font-size:12px;color:#cbd5e1;line-height:1.35;margin-top:3px}
.td .td-pressure-row{border:1px solid #243044;border-radius:8px;background:#0b1220;padding:8px;margin-top:8px}
.td .td-pressure-head{display:flex;gap:8px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}
.td .td-pressure-state{font-size:10px;color:#93c5fd;text-transform:uppercase;font-weight:900;letter-spacing:.06em}
.td .td-pressure-name{font-size:14px;color:#f8fafc;font-weight:850;line-height:1.25;margin-top:2px}
.td .td-pressure-detail{font-size:12px;color:#94a3b8;line-height:1.35;margin-top:3px}
.td .td-pressure-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}
.td .td-feeder{border:1px solid #243044;border-radius:9px;background:#08111f;padding:9px;margin:9px 0}
.td .td-feeder>summary{cursor:pointer;color:#e2e8f0;font-size:12px;font-weight:850}
.td .td-feeder-row{border:1px solid #243044;border-radius:8px;background:#0b1220;padding:7px;margin-top:7px}
.td .td-feeder-top{display:flex;gap:8px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}
.td .td-feeder-key{font-size:10px;color:#93c5fd;text-transform:uppercase;font-weight:900;letter-spacing:.05em}
.td .td-feeder-title{font-size:13px;color:#f8fafc;font-weight:800;margin-top:2px}
.td .td-feeder-meta{font-size:11px;color:#94a3b8;line-height:1.35;margin-top:3px}
.td .td-passivity{border:1px solid #334155;border-radius:10px;background:#08111f;padding:10px 12px;margin:10px 0 12px}
.td .td-passivity-title{font-size:12px;color:#f8fafc;font-weight:850;margin-bottom:4px}
.td .td-passivity-line{font-size:12px;color:#cbd5e1;line-height:1.4}
.td .td-passivity-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px;margin-top:8px}
.td .td-passivity-bucket{border:1px solid #243044;border-radius:8px;background:#0b1220;padding:7px}
.td .td-passivity-count{font-size:16px;color:#f8fafc;font-weight:900}
.td .td-passivity-label{font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:850;letter-spacing:.04em}
.td .td-coverage{border:1px solid #334155;border-radius:10px;background:#08111f;padding:10px 12px;margin:10px 0 12px}
.td .td-coverage-title{font-size:12px;color:#f8fafc;font-weight:850;margin-bottom:4px}
.td .td-coverage-line{font-size:12px;color:#cbd5e1;line-height:1.4}
.td .td-coverage-row{font-size:12px;color:#94a3b8;line-height:1.35;margin-top:3px}
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
.td .td-blocker-tax{border:1px solid #334155;border-radius:8px;background:#0b1220;padding:8px;margin:0 0 8px}
.td .td-blocker-tax-title{font-size:10px;color:#94a3b8;text-transform:uppercase;font-weight:900;letter-spacing:.06em}
.td .td-blocker-tax-line{font-size:13px;color:#f8fafc;font-weight:750;line-height:1.35;margin-top:3px}
.td .td-blocker-tax-row{font-size:12px;color:#cbd5e1;line-height:1.35;margin-top:3px}
.td .td-size-goal{border:1px solid #1f3b57;border-radius:8px;background:#071426;padding:8px;margin:0 0 8px}
.td .td-size-goal-title{font-size:10px;color:#93c5fd;text-transform:uppercase;font-weight:900;letter-spacing:.06em}
.td .td-size-goal-line{font-size:13px;color:#e2e8f0;font-weight:750;line-height:1.35;margin-top:3px}
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

/* ===== RENDER-REDESIGN: decision-led surface (2026-06-18) ===== */
/* freshness chip + section leads */
.td .td-fresh{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12.5px;color:#94a3b8;
  border:1px solid #243044;background:#0b1220;border-radius:10px;padding:9px 12px;margin:4px 0 8px}
.td .td-fresh b{color:#e2e8f0}
.td .td-dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.td .td-dot-g{background:#34d399} .td .td-dot-a{background:#f5b955}
.td .td-fresh .td-warn{color:#f5b955}
.td .td-sectlead{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#94a3b8;
  font-weight:850;margin:22px 2px 9px}
.td .td-sectlead .td-q{color:#64748b;text-transform:none;letter-spacing:0;font-weight:400;font-size:12px}
/* HERO move card */
.td .td-hero{border:1px solid #2b4a86;background:linear-gradient(180deg,#10203c,#0f1828);
  border-radius:14px;padding:16px 16px 14px;box-shadow:0 0 0 1px #18305c inset;margin:0 0 12px}
/* collapsible hero: the loud headline lives in the summary (always visible); one tap
   folds the move so it never owns the whole screen */
.td details.td-hero[open]{padding-bottom:14px}
.td details.td-hero>summary.td-herosum{cursor:pointer;list-style:none;display:block}
.td details.td-hero>summary.td-herosum::-webkit-details-marker{display:none}
.td details.td-hero>summary.td-herosum::marker{content:""}
.td .td-herobody{margin-top:12px}
.td .td-hero-toggle{font-size:10px;color:#5b9cff;text-transform:none;letter-spacing:0;font-weight:600;margin-left:6px;opacity:.85}
.td details.td-hero:not([open])>summary .td-hero-sub{display:none}
.td .td-hero-kicker{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#5b9cff;font-weight:800;margin-bottom:6px}
.td .td-hl{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.td .td-verb{font-weight:850;font-size:15px;letter-spacing:.04em;color:#34d399}
.td .td-verb-sell{color:#f87171}
.td .td-tk{font-weight:850;font-size:28px;letter-spacing:.5px;color:#f8fafc}
.td .td-amt{font-weight:850;font-size:28px;color:#f8fafc}
.td .td-hero-sub{color:#9fb0c7;font-size:13px;margin-top:3px}
.td .td-kv{display:grid;grid-template-columns:104px 1fr;gap:6px 12px;margin-top:13px;font-size:14px}
.td .td-kv .td-k{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.06em;padding-top:2px}
.td .td-kv .td-v{color:#e8eef7;line-height:1.4} .td .td-kv .td-v .td-tag{color:#9fb0c7}
.td .td-gate-chip{display:inline-flex;align-items:center;gap:6px;border-radius:7px;padding:3px 8px;font-size:12px;font-weight:650}
.td .td-gate-amber{background:rgba(245,185,85,.13);color:#f5b955;border:1px solid rgba(245,185,85,.32)}
.td .td-gate-green{background:rgba(52,211,153,.12);color:#34d399;border:1px solid rgba(52,211,153,.3)}
.td .td-gate-red{background:rgba(248,113,113,.12);color:#f87171;border:1px solid rgba(248,113,113,.32)}
.td .td-caveat{margin-top:11px;font-size:13px;color:#f5b955;background:rgba(245,185,85,.07);
  border:1px solid rgba(245,185,85,.18);border-radius:9px;padding:8px 11px}
.td .td-caveat b{color:#ffd479}
/* DO IT / STAGE / PASS rail (these buttons KEEP class td-rail for the disposition wiring + parity) */
.td .td-actionrail{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;align-items:center}
.td .td-rail.td-do{background:#10391f;border-color:#1e6b3a;color:#d7ffe6;font-weight:750}
.td .td-rail.td-do.td-on{background:#16a34a;color:#04140a}
.td .td-rail.td-stage{background:#2c2410;border-color:#6b551e;color:#ffeccb;font-weight:700}
.td .td-rail.td-stage.td-on{background:#d6a93a;color:#1b1404}
.td .td-rail.td-pass{background:#1a1320;border-color:#4a3a5a;color:#e9d7ff;font-weight:700}
.td .td-rail.td-pass.td-on{background:#7c5bd0;color:#0c0717}
/* good-but-gated primary: reads as a confident "do it", with the final check flagged */
.td .td-rail.td-docheck{background:#11341f;border:1px solid #2f7d4a;color:#d7ffe6;font-weight:750}
.td .td-rail.td-docheck:hover{background:#155029}
.td .td-rail.td-docheck.td-on{background:#16a34a;color:#04140a}
.td .td-finalcheck{margin-top:13px;font-size:13px;color:#cfe8d6;background:rgba(52,211,153,.06);
  border:1px solid rgba(52,211,153,.26);border-radius:10px;padding:9px 12px;line-height:1.45}
.td .td-finalcheck b{color:#86efac}
.td .td-finalcheck ul{margin:6px 0 6px;padding-left:20px} .td .td-finalcheck li{margin:2px 0;color:#e8eef7}
.td .td-finalcheck.td-cleared{color:#bbf7d0;background:rgba(52,211,153,.1);border-color:rgba(52,211,153,.4)}
.td .td-fb{margin-top:9px;font-size:12.5px;color:#34d399;min-height:17px}
.td .td-fb.td-fb-muted{color:#64748b}
/* ask / comment + notes */
.td details.td-ask,.td details.td-evi{margin-top:12px;border-top:1px solid #243044;padding-top:9px}
.td details.td-ask>summary,.td details.td-evi>summary{cursor:pointer;color:#9fb0c7;font-size:12.5px;list-style:none}
.td details.td-ask>summary::-webkit-details-marker,.td details.td-evi>summary::-webkit-details-marker{display:none}
.td details.td-ask>summary:before{content:"\1f4ac  ask / comment on this card";color:#5b9cff}
.td details.td-evi>summary:before{content:"\25b8  evidence / what could make this wrong";color:#64748b}
.td details.td-evi[open]>summary:before{content:"\25be  evidence / what could make this wrong";color:#64748b}
.td .td-ask textarea{width:100%;margin-top:8px;background:#0a1322;border:1px solid #243044;border-radius:8px;
  color:#e8eef7;font:inherit;font-size:13px;padding:8px 10px;resize:vertical;min-height:50px;box-sizing:border-box}
.td .td-askrow{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
.td .td-mini{appearance:none;border:1px solid #334155;background:#131f33;color:#e8eef7;font-weight:650;
  font-size:12px;border-radius:8px;padding:6px 11px;cursor:pointer}
.td .td-mini:hover{border-color:#33507f}
.td .td-askfb{font-size:12px;color:#64748b} .td .td-askfb.td-ok{color:#34d399} .td .td-askfb.td-warn{color:#f5b955}
.td .td-notes{margin-top:8px}
.td .td-note{font-size:12px;color:#9fb0c7;background:#0a1322;border:1px solid #243044;border-radius:8px;
  padding:6px 9px;margin-top:6px}
/* sizing transparency panel */
.td .td-sizing{border:1px solid #1f3b57;border-radius:9px;background:#071426;padding:10px 11px;margin:12px 0 0}
.td details.td-sizing>summary.td-sizing-title{cursor:pointer;list-style:none}
.td details.td-sizing>summary.td-sizing-title::-webkit-details-marker{display:none}
.td details.td-sizing>summary.td-sizing-title::marker{content:""}
.td details.td-sizing>summary.td-sizing-title:before{content:"▸ ";color:#5b9cff}
.td details.td-sizing[open]>summary.td-sizing-title:before{content:"▾ "}
.td .td-sizing-title{font-size:10px;color:#93c5fd;text-transform:uppercase;font-weight:850;letter-spacing:.06em}
.td .td-sizing-live{font-size:18px;color:#f8fafc;font-weight:850;margin:4px 0 2px}
.td .td-sizing-note{font-size:12px;color:#9fb0c7;line-height:1.4;margin-top:3px}
.td .td-sizing-formula{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#cbd5e1;
  background:#0a1322;border:1px solid #243044;border-radius:7px;padding:7px 9px;margin-top:7px;line-height:1.5}
.td .td-dialrow{display:grid;grid-template-columns:160px 1fr 86px;gap:8px 10px;align-items:center;margin-top:8px}
.td .td-dial-label{font-size:12px;color:#cbd5e1} .td .td-dial-label i{font-style:normal;color:#64748b;font-size:11px}
.td .td-dial input[type=range]{width:100%}
.td .td-dial-val{font-size:12.5px;color:#f8fafc;font-weight:700;text-align:right}
/* good price / lower conviction tier */
.td .td-tiernote{font-size:12.5px;color:#9fb0c7;margin:0 2px 6px;line-height:1.5}
.td .td-tiernote b{color:#f5b955}
.td details.td-opp{border:1px solid #243044;border-left:3px solid #3a5560;background:rgba(255,255,255,.012);border-radius:10px;margin-top:7px}
.td details.td-opp.td-opp-deep{border-left-color:#5a3a3a}
.td summary.td-oppsum{cursor:pointer;list-style:none;display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:9px 12px;font-size:13px}
.td summary.td-oppsum::-webkit-details-marker{display:none}
.td .td-otk{font-weight:850;font-size:15px;min-width:48px;color:#f8fafc}
.td .td-m{display:flex;flex-direction:column;line-height:1.15;cursor:help}
.td .td-m .td-val{color:#e8eef7}
.td .td-m.td-disc .td-val{color:#f5b955;font-weight:650}
.td .td-m.td-imp .td-val{color:#9fb0c7}
.td .td-m i{font-style:normal;font-size:9.5px;letter-spacing:.03em;color:#64748b;text-transform:uppercase;margin-top:1px}
.td .td-caret{margin-left:auto;color:#64748b;font-size:11.5px}
.td details.td-opp[open] .td-caret:after{content:" \25be"} .td details.td-opp:not([open]) .td-caret:after{content:" \25b8"}
.td .td-stat{font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:#0b1220;background:#9fb0c7;border-radius:4px;padding:1px 5px;font-weight:750;align-self:center}
.td .td-oppbody{padding:2px 13px 12px;font-size:12.5px;color:#9fb0c7;border-top:1px solid #243044}
.td .td-oppbody>div{margin:8px 0} .td .td-oppbody b{color:#e8eef7;font-weight:600}
.td .td-askmini textarea{width:100%;margin-top:4px;background:#0a1322;border:1px solid #243044;border-radius:8px;color:#e8eef7;font:inherit;font-size:12.5px;padding:7px 9px;min-height:40px;resize:vertical;box-sizing:border-box}
.td .td-screenline{font-size:12.5px;color:#64748b;margin:12px 2px 0;line-height:1.5}
.td .td-screenline b{color:#9fb0c7}
/* collapsed machinery */
.td details.td-machine{margin-top:22px;border:1px dashed #243044;border-radius:12px;background:rgba(255,255,255,.012)}
.td details.td-machine>summary{cursor:pointer;color:#64748b;font-size:12.5px;padding:12px 14px;list-style:none}
.td details.td-machine>summary::-webkit-details-marker{display:none}
.td details.td-machine>summary:before{content:"\25b8  "} .td details.td-machine[open]>summary:before{content:"\25be  "}
.td .td-machinebody{padding:0 14px 14px}
.td .td-dechist{font-size:12px;color:#94a3b8;line-height:1.4;margin-top:9px}
@media (max-width: 620px){
  .td{padding:12px}
  .td .td-anchor{font-size:16px}
  .td .td-pace{font-size:10px;margin-bottom:8px}
  .td .td-plan{font-size:12px;margin-bottom:6px}
  .td .td-health-full{display:none}
  .td .td-health-compact{display:block}
  .td .td-first-grid{grid-template-columns:1fr}
  .td .td-first-rail .td-row{display:none}
  .td .td-face-top{display:block}
  .td .td-face-right{justify-content:flex-start;margin-top:7px}
  .td .td-face-title{font-size:18px}
  .td .td-readout-grid{grid-template-columns:1fr}
  .td .td-tk,.td .td-amt{font-size:23px}
  .td .td-kv{grid-template-columns:1fr}
  .td .td-kv .td-k{padding-top:6px}
  .td .td-dialrow{grid-template-columns:1fr 1fr}
}
</style>
"""

_JS = """
<script>
/* Clipboard (chat-sync command) \u2014 kept as a secondary effect; persistence below
   does NOT depend on it, so a tap is recorded even when copy is blocked. */
function tdCopyFallback(t){var a=document.createElement('textarea');a.value=t;
a.setAttribute('readonly','');a.style.position='fixed';a.style.left='-9999px';a.style.top='0';
document.body.appendChild(a);a.focus();a.select();var ok=false;
try{ok=document.execCommand('copy');}catch(e){ok=false;}document.body.removeChild(a);return ok;}
async function tdCopy(t){if(navigator.clipboard&&navigator.clipboard.writeText){
try{await navigator.clipboard.writeText(t);return true;}catch(e){}}
return tdCopyFallback(t);}
/* ---- disposition spine (client) ----
   Every tap persists durably in localStorage (survives refresh, shown on reload)
   AND best-effort POSTs to the disposition_log spine when served live; the copied
   command lets the operator sync the tap into dispositions.jsonl from chat. */
function tdTicker(id){return String(id||'').split('-')[0];}
function tdBuilt(){var s=document.getElementById('today-decide');return (s&&s.getAttribute('data-built'))||new Date().toISOString().slice(0,10);}
function tdDispKey(id){return 'td:disp:'+id;}
function tdGetDisp(id){try{return JSON.parse(localStorage.getItem(tdDispKey(id))||'null');}catch(e){return null;}}
function tdRenderDisp(id){
  var cur=tdGetDisp(id);
  var btns=document.querySelectorAll('button.td-rail[data-card="'+id+'"]');
  [].forEach.call(btns,function(b){b.classList.toggle('td-on',!!cur&&b.getAttribute('data-verb')===cur.verb);});
  var fb=document.getElementById('tdfb-'+id);
  if(fb){
    if(cur){fb.className='td-fb';fb.textContent='\u2713 '+(cur.label||cur.verb)+' logged '+cur.t+'  \u00b7  tap again to undo';}
    else{fb.className='td-fb td-fb-muted';fb.textContent='no decision logged yet';}
  }
}
async function tdRail(btn){
  var id=btn.getAttribute('data-card');var verb=btn.getAttribute('data-verb');
  var label=(btn.getAttribute('data-label')||btn.textContent||verb).trim();
  var cur=tdGetDisp(id);var undo=!!cur&&cur.verb===verb;
  /* persist on-device first \u2014 a tap never evaporates even with no server */
  if(undo){localStorage.removeItem(tdDispKey(id));}
  else{localStorage.setItem(tdDispKey(id),JSON.stringify({verb:verb,label:label,t:new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}));}
  tdRenderDisp(id);
  /* secondary: copy the chat-ready command so it can also be synced via chat */
  tdCopy(undo?('UNDO '+id):(btn.getAttribute('data-copy')||(verb+' '+id)));
  /* fully automatic: write straight to the permanent disposition log when served live */
  var fb=document.getElementById('tdfb-'+id);
  try{
    var r=await fetch('/td/disposition',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({card_id:id,ticker:tdTicker(id),verb:(undo?'UNDO':verb),et_date:tdBuilt(),source:'dashboard'})});
    if(fb&&!undo){fb.textContent+=(r&&r.ok)?'  \u00b7  \u2713 saved to your log':'  \u00b7  saved on this device (paste the copied line into chat to make it permanent)';}
  }catch(e){
    if(fb&&!undo){fb.textContent+='  \u00b7  saved on this device (paste the copied line into chat to make it permanent)';}
  }
}
/* ---- per-card notes / ask ---- */
function tdNotesKey(id){return 'td:notes:'+id;}
function tdGetNotes(id){try{return JSON.parse(localStorage.getItem(tdNotesKey(id))||'[]');}catch(e){return [];}}
function tdRenderNotes(id){
  var box=document.getElementById('tdnotes-'+id);if(!box)return;
  var ns=tdGetNotes(id);box.innerHTML='';
  ns.forEach(function(n,i){var d=document.createElement('div');d.className='td-note';
    d.textContent=n.t+' \u00b7 '+n.q;box.appendChild(d);});
}
function tdAskSave(btn){
  var id=btn.getAttribute('data-card');
  var ta=document.getElementById('tdq-'+id);var t=((ta&&ta.value)||'').trim();
  var fb=document.getElementById('tdqfb-'+id);
  if(!t){if(fb){fb.className='td-askfb td-warn';fb.textContent='type a question first';}return;}
  var a=tdGetNotes(id);a.push({q:t,t:new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})});
  localStorage.setItem(tdNotesKey(id),JSON.stringify(a));
  ta.value='';if(fb){fb.className='td-askfb td-ok';fb.textContent='saved on card';}tdRenderNotes(id);
  /* fully automatic: write the note to the permanent per-card notes log when served live */
  try{fetch('/td/note',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({card_id:id,ticker:tdTicker(id),note:t,source:'dashboard'})}).then(function(r){
      if(fb&&r&&r.ok)fb.textContent='saved on card | ✓ logged';}).catch(function(){});}catch(e){}
}
function tdAskCopy(btn){
  var id=btn.getAttribute('data-card');var headline=btn.getAttribute('data-headline')||'';
  var ta=document.getElementById('tdq-'+id);var t=((ta&&ta.value)||'').trim();
  var fb=document.getElementById('tdqfb-'+id);
  if(!t){if(fb){fb.className='td-askfb td-warn';fb.textContent='type a question first';}return;}
  tdCopy('[CARD '+id+'] '+headline+'\\nQ: '+t).then(function(ok){
    if(fb){fb.className='td-askfb td-ok';fb.textContent=ok?'\u2713 copied \u2014 paste into chat':'select + copy manually';}
  });
}
/* ---- sizing tunables (dials): persist + live client-side recompute ----
   Defaults come from the engine (sizing_tunables.json). The render mirrors the
   documented formula; the operator can drag a dial and the shown size updates
   immediately, with the override persisted + a chat-ready sync command emitted. */
function tdTunKey(){return 'td:tunables';}
function tdGetTun(){try{return JSON.parse(localStorage.getItem(tdTunKey())||'{}');}catch(e){return {};}}
function tdDial(inp){
  var key=inp.getAttribute('data-key');var cid=inp.getAttribute('data-card');
  var val=parseFloat(inp.value);
  var lab=document.getElementById('tddialval-'+cid+'-'+key);if(lab)lab.textContent=inp.value;
  var ov=tdGetTun();ov[key]=val;localStorage.setItem(tdTunKey(),JSON.stringify(ov));
  tdRecompute(cid);
  tdCopy('SET-TUNABLE '+key+' '+val+'  (sync to src/sizing_tunables.json)');
}
function tdRecompute(cid){
  var el=document.getElementById('tdsize-'+cid);if(!el||el.getAttribute('data-formula')!=='f2')return;
  var anchor=parseFloat(el.getAttribute('data-anchor')||'0');
  var strength=parseFloat(el.getAttribute('data-strength')||'0');
  var ov=tdGetTun();
  /* mirror the F2 engine formula: size = anchor*(1 + slope*strength), then optional
     soft-max clamp. anchor falls back to base_size_usd only when there is no anchor. */
  var slope=(ov.conviction_size_slope!=null)?ov.conviction_size_slope:parseFloat(el.getAttribute('data-slope')||'1');
  var base=(ov.base_size_usd!=null)?ov.base_size_usd:parseFloat(el.getAttribute('data-base')||'0');
  var softmax=(ov.per_name_soft_max_usd!=null)?ov.per_name_soft_max_usd:parseFloat(el.getAttribute('data-softmax')||'0');
  var a=anchor>0?anchor:base;
  var size=a*(1+slope*strength);
  if(softmax>0&&size>softmax)size=softmax;
  el.textContent='live size $'+Math.round(size).toLocaleString();
}
function tdInit(){
  document.querySelectorAll('button.td-rail[data-card]').forEach(function(b){
    var id=b.getAttribute('data-card');tdRenderDisp(id);});
  document.querySelectorAll('[id^="tdnotes-"]').forEach(function(box){
    tdRenderNotes(box.id.slice('tdnotes-'.length));});
  document.querySelectorAll('[id^="tdsize-"]').forEach(function(el){
    tdRecompute(el.id.slice('tdsize-'.length));});
}
if(document.readyState!=='loading')tdInit();else document.addEventListener('DOMContentLoaded',tdInit);
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
    return f"{_money_text(card.get('dollars'))} funding sell - only if paired with the buy it funds"


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


def _render_blocker_taxonomy(card: dict[str, Any]) -> str:
    taxonomy = card.get("blocker_taxonomy") or {}
    line = str(taxonomy.get("line") or "").strip()
    if not line or not taxonomy.get("unmet"):
        return ""
    rows = taxonomy.get("unmet") or []
    return (
        '<div class="td-blocker-tax">'
        '<div class="td-blocker-tax-title">Distance to actionable</div>'
        f'<div class="td-blocker-tax-line">{_esc(line)}</div>'
        + "".join(
            f'<div class="td-blocker-tax-row">{_esc(row.get("label") or row.get("category") or "")}: '
            f'{_esc(row.get("evidence") or "")}</div>'
            for row in rows
        )
        + f'<div class="td-blocker-tax-row">{_esc(taxonomy.get("honesty_rule") or "")}</div>'
        + '</div>'
    )


def _render_size_to_goal(card: dict[str, Any]) -> str:
    model = card.get("size_to_goal") or {}
    line = str(model.get("line") or "").strip()
    if not line:
        return ""
    return (
        '<div class="td-size-goal">'
        '<div class="td-size-goal-title">Size to goal with rails</div>'
        f'<div class="td-size-goal-line">{_esc(line)}</div>'
        f'<div class="td-blocker-tax-row">{_esc(model.get("honesty_rule") or "")}</div>'
        '</div>'
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
    label = str(context.get("label") or "Daily pullback packet").strip()
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


def _render_command_strip(payload: dict[str, Any]) -> str:
    strip = payload.get("command_strip") or {}
    if not strip:
        return ""
    rows = strip.get("rows") or []
    state = str(strip.get("system_state") or "starved")
    state_cls = "td-command-state-confident" if state == "confident" else "td-command-state-starved"
    ga = payload.get("goal_anchor") or {}
    if ga.get("book_value") is not None:
        goal_line = f"${ga['book_value']:,.0f} to ${ga['fi_target']:,.0f}; {ga['pct_to_target']}% there"
    else:
        goal_line = "goal anchor not readable"
    return (
        '<div class="td-command">'
        '<div class="td-command-head">'
        f'<div><div class="td-command-line">{_esc(strip.get("line") or "")}</div>'
        f'<div class="td-command-system">goal: {_esc(goal_line)}</div></div>'
        f'<div class="td-command-state {state_cls}">{_esc(state)}</div>'
        '</div>'
        '<div class="td-command-grid">'
        + "".join(
            '<div class="td-command-cell">'
            f'<div class="td-command-count">{int(row.get("count") or 0)}</div>'
            f'<div class="td-command-label">{_esc(row.get("state") or "")}</div>'
            f'<div class="td-command-detail">{_esc(row.get("detail") or "")}</div>'
            '</div>'
            for row in rows
        )
        + '</div>'
        f'<div class="td-command-system">{_esc(strip.get("system_line") or "")}</div>'
        f'<div class="td-command-system">{_esc(strip.get("honesty_rule") or "")}</div>'
        '</div>'
    )


def _render_readiness_model(readiness: dict[str, Any] | None) -> str:
    model = readiness or {}
    layers = [row for row in model.get("layers") or [] if isinstance(row, dict)]
    checklist = [row for row in model.get("checklist") or [] if isinstance(row, dict)]
    if not layers and not checklist:
        return ""

    def chip(row: dict[str, Any]) -> str:
        status = str(row.get("status") or "unknown")
        cls = {
            "ok": "td-ready-chip td-ready-ok",
            "blocked": "td-ready-chip td-ready-blocked",
            "unknown": "td-ready-chip td-ready-unknown",
        }.get(status, "td-ready-chip td-ready-unknown")
        return (
            f'<div class="{cls}">'
            f'<div class="td-ready-label">{_esc(row.get("label") or row.get("key") or "")}</div>'
            f'<div class="td-ready-status">{_esc(status)}</div>'
            f'<div class="td-ready-detail">{_esc(row.get("detail") or "")}</div>'
            '</div>'
        )

    return (
        '<div class="td-readiness">'
        '<div class="td-readiness-title">Readiness layers</div>'
        '<div class="td-readiness-grid">'
        + "".join(chip(row) for row in layers)
        + '</div>'
        '<div class="td-readiness-title" style="margin-top:8px">Resolve checklist</div>'
        '<div class="td-readiness-grid">'
        + "".join(chip(row) for row in checklist)
        + '</div>'
        f'<div class="td-ready-detail">{_esc(model.get("honesty_rule") or "")}</div>'
        '</div>'
    )


def _render_first_viewport(payload: dict[str, Any], *, rails: bool = True) -> str:
    model = payload.get("first_viewport") or {}
    decision = str(model.get("decision") or "No capital-changing decision surfaced.")
    button = model.get("button") or {}
    button_html = ""
    if rails and button and model.get("status") == "has_primary":
        muted = " td-rail-muted" if button.get("muted") == "1" else ""
        button_html = (
            f'<button class="td-rail{muted}" data-card="{_esc(button.get("card_id") or "")}" '
            f'data-verb="{_esc(button.get("state_verb") or "RECHECK")}" data-copy="{_esc(button.get("copy") or "")}" '
            f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">{_esc(button.get("label") or "RECHECK")}</button>'
        )
    cells = [
        ("Size/tranche", model.get("size") or "No tranche implied."),
        ("Blocked by", model.get("blocker") or "No blocker surfaced."),
        ("Changed", model.get("changed") or "No prior reliable build baseline yet."),
        ("Risk rail", model.get("risk_rail") or "Normal survival rails still apply."),
        ("Can wait", model.get("safe_wait") or "Research/watch-only items can wait."),
    ]
    return (
        '<div class="td-first">'
        f'<div class="td-first-kicker">Primary command'
        + (f' - {_esc(model.get("command_state") or "")}' if model.get("command_state") else "")
        + '</div>'
        '<div class="td-first-main">'
        f'<div class="td-first-decision">{_esc(decision)}</div>'
        + (f'<div class="td-first-rail">{button_html}<span class="td-row">Rail copy is render-only; no trade executes.</span></div>' if button_html else "")
        + '</div>'
        + '<div class="td-first-grid">'
        + "".join(
            '<div class="td-first-cell">'
            f'<div class="td-first-label">{_esc(label)}</div>'
            f'<div class="td-first-value">{_esc(value)}</div>'
            '</div>'
            for label, value in cells
        )
        + '</div>'
        + _render_readiness_model(model.get("readiness") or {})
        + '</div>'
    )


def _render_disposition_pressure(payload: dict[str, Any], *, rails: bool = True) -> str:
    pressure = payload.get("disposition_pressure") or {}
    rows = [row for row in pressure.get("rows") or [] if isinstance(row, dict)]
    if not rows:
        return ""
    bits = [
        '<div class="td-pressure">',
        '<div class="td-pressure-title">Decision pressure</div>',
        f'<div class="td-pressure-line">{_esc(pressure.get("line") or "")}</div>',
    ]
    for row in rows:
        actions = []
        for action in (row.get("actions") or []) if rails else []:
            if not isinstance(action, dict):
                continue
            actions.append(
                f'<button class="td-rail td-rail-muted" data-card="{_esc(row.get("decision_key") or "")}" '
                f'data-verb="{_esc(action.get("verb") or action.get("label") or "RECHECK")}" '
                f'data-copy="{_esc(action.get("copy") or "")}" '
                f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">{_esc(action.get("label") or "RECHECK")}</button>'
            )
        bits.append(
            '<div class="td-pressure-row">'
            '<div class="td-pressure-head">'
            f'<div><div class="td-pressure-state">{_esc(row.get("state") or "DECIDE")} | {_esc(row.get("kind") or "")}</div>'
            f'<div class="td-pressure-name">{_esc(row.get("title") or "")}</div></div>'
            f'<div class="td-pressure-state">{_esc(row.get("ticker") or "")}</div>'
            '</div>'
            f'<div class="td-pressure-detail">{_esc(row.get("prompt") or "")}</div>'
            f'<div class="td-pressure-detail">{_esc(row.get("detail") or "")}</div>'
            + (f'<div class="td-pressure-detail"><a href="{_esc(row.get("notion_url") or "")}">source</a></div>' if row.get("notion_url") else "")
            + f'<div class="td-pressure-actions">{"".join(actions)}</div>'
            + '</div>'
        )
    bits.append(f'<div class="td-pressure-detail">{_esc(pressure.get("honesty_rule") or "")}</div>')
    bits.append('</div>')
    return "".join(bits)


def _render_candidate_feed_index(payload: dict[str, Any]) -> str:
    index = payload.get("candidate_feed_index") or {}
    rows = [row for row in index.get("rows") or [] if isinstance(row, dict)]
    if not rows:
        return ""
    counts = index.get("counts") or {}
    summary = (
        f"Merged candidate feeder index ({int(counts.get('total') or len(rows))}): "
        + " | ".join(f"{int(counts.get(state) or 0)} {state}" for state in COMMAND_STATES)
    )
    bits = [
        '<details class="td-feeder">',
        f'<summary>{_esc(summary)}</summary>',
    ]
    for row in rows[:12]:
        evidence = "; ".join(_esc(item) for item in (row.get("evidence") or [])[:2] if item)
        bits.append(
            '<div class="td-feeder-row">'
            '<div class="td-feeder-top">'
            f'<div><div class="td-feeder-key">{_esc(row.get("state") or "")} | {_esc(row.get("decision_key") or "")}</div>'
            f'<div class="td-feeder-title">{_esc(row.get("title") or "")}</div></div>'
            f'<div class="td-feeder-key">{_esc(row.get("independent_source_count") or 0)} independent</div>'
            '</div>'
            f'<div class="td-feeder-meta">sources: {_esc(", ".join(row.get("sources") or []))}</div>'
            + (f'<div class="td-feeder-meta">evidence: {evidence}</div>' if evidence else "")
            + '</div>'
        )
    if len(rows) > 12:
        bits.append(f'<div class="td-feeder-meta">+{len(rows) - 12} more merged rows in payload.</div>')
    bits.append(f'<div class="td-feeder-meta">{_esc(index.get("honesty_rule") or "")}</div>')
    bits.append('</details>')
    return "".join(bits)


def _render_passivity_panel(payload: dict[str, Any]) -> str:
    passivity = payload.get("passivity") or {}
    counts = passivity.get("counts") or {}
    buckets = [
        "operator_owned_actionable_now",
        "waiting_market_price_tape_gate",
        "waiting_source_data_freshness",
        "research_watch_only",
        "cap_risk_cash_constrained",
        "system_blocked_not_checked",
    ]
    return (
        '<div class="td-passivity">'
        '<div class="td-passivity-title">Ownership-aware passivity</div>'
        f'<div class="td-passivity-line">{_esc(passivity.get("line") or "")}</div>'
        '<div class="td-passivity-grid">'
        + "".join(
            '<div class="td-passivity-bucket">'
            f'<div class="td-passivity-count">{int(counts.get(bucket) or 0)}</div>'
            f'<div class="td-passivity-label">{_esc(PASSIVITY_BUCKET_LABELS.get(bucket, bucket))}</div>'
            '</div>'
            for bucket in buckets
        )
        + '</div>'
        f'<div class="td-row">{_esc(passivity.get("honesty_rule") or "")}</div>'
        '</div>'
    )


def _render_disposition_coverage(payload: dict[str, Any]) -> str:
    coverage = payload.get("disposition_coverage") or {}
    rows = coverage.get("rows") or []
    sample = rows[:5]
    return (
        '<div class="td-coverage">'
        '<div class="td-coverage-title">Disposition coverage</div>'
        f'<div class="td-coverage-line">{_esc(coverage.get("line") or "")}</div>'
        + "".join(
            f'<div class="td-coverage-row">{_esc(row.get("ticker") or row.get("source") or "")}: '
            f'{_esc(row.get("status") or "")} - {_esc(row.get("reason") or row.get("label") or "")}</div>'
            for row in sample
        )
        + f'<div class="td-coverage-row">{_esc(coverage.get("honesty_rule") or "")}</div>'
        + '</div>'
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
    if card.get("conflict_recheck") or (card.get("conviction_display") or {}).get("conflicted") or card.get("conviction_conflict"):
        return {
            "label": "RECHECK",
            "state_verb": "RECHECK",
            "copy_verb": "RECHECK",
            "copy_suffix": " bull/bear evidence both live; resolve before sizing",
            "reason": f"conflicted {direction}; opposing evidence must be resolved first",
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
    plan: dict[str, Any] | None = None,
    tunables: dict[str, Any] | None = None,
) -> list[str]:
    dcard = card.get("decision_card") or {}
    move = dcard.get("move") or {}
    display = card.get("conviction_display") or build_conviction_display(card)
    win = card.get("window") or {}
    execn = card.get("execution") or {}
    impact = card.get("impact") or {}
    sizing = card.get("sizing") or {}
    raw_cid = str(card.get("card_id") or "")
    cid = _esc(raw_cid)
    # A non-conflicted material buy/add with a trade-plan row leads as a loud MOVE:
    # the trade-plan header + sizing transparency + rail surface above the engine card.
    is_conflicted_card = bool(display.get("conflicted") or display.get("conflict")
                              or card.get("conflicts") or display.get("band") == "CONFLICTED")
    show_trade_plan = (bool(plan) and _is_material(card) and not _is_funding_leg(card)
                       and not is_conflicted_card
                       and _card_action_direction(card).upper() not in {"SELL", "TRIM", "REDUCE", "BEAR"})
    conflicted = " td-conflicted" if card.get("conflicts") or display.get("conflict") else ""
    anchor = f'td-card-{_esc(str(card.get("ticker") or "").upper())}'
    h = [f'<details id="{anchor}" class="td-card{conflicted}">', '<summary class="td-sum">']
    cls = win.get("class", "WAIT")
    direction = str(move.get("direction") or "")
    posture = _review_posture(card, check_first=check_first, window_class=cls, direction=direction)
    command_state = str(card.get("command_state") or _card_command_state(card))
    if command_state != "ACT" and posture.get("copy_verb") == "ACT":
        button_model = _command_button_for_state(card, command_state, raw_cid)
        posture = {
            "label": str(button_model.get("label") or "RECHECK"),
            "state_verb": str(button_model.get("state_verb") or "RECHECK"),
            "copy_verb": "WATCH" if command_state == "WATCH" else "RECHECK",
            "copy_suffix": " " + str(card.get("command_state_detail") or COMMAND_STATE_COPY.get(command_state, "")).strip(),
            "reason": f"{command_state}: {card.get('command_state_detail') or COMMAND_STATE_COPY.get(command_state, '')}",
        }
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
    h.append(_render_readiness_model(card.get("readiness") or {}))
    h.append(_render_blocker_taxonomy(card))
    h.append(_render_size_to_goal(card))
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
    if command_state != "ACT" and posture.get("copy_verb") == "ACT":
        button_model = _command_button_for_state(card, command_state, raw_cid)
        primary_verb = "RECHECK"
        primary_state_verb = str(button_model.get("state_verb") or "RECHECK")
        primary_label = str(button_model.get("label") or "RECHECK")
        primary_copy = str(button_model.get("copy") or f"RECHECK {raw_cid}")
        primary_class = "td-rail td-rail-muted"
    else:
        primary_verb = posture["copy_verb"]
        primary_state_verb = posture["state_verb"]
        primary_label = posture["label"] if primary_verb != "ACT" else "ACT"
        primary_copy = (
            f"ACT {cid}" if primary_verb == "ACT"
            else f'{primary_verb} {cid}{_esc(posture["copy_suffix"])}'
        )
        primary_class = "td-rail" if primary_verb == "ACT" else "td-rail td-rail-muted"
    # Build the canonical rail buttons ONCE (data-verb/data-copy unchanged -> parity +
    # mojibake stable). For a move, the rail surfaces in the loud header; otherwise it
    # stays inline in the card body. Visible labels get plain wording for moves only.
    primary_hero_cls = (" td-do" if primary_state_verb == "ACT" else " td-docheck") if show_trade_plan else ""
    rail_parts = [
        f'<button class="{primary_class}{primary_hero_cls}" data-card="{cid}" data-verb="{primary_state_verb}" '
        f'data-label="{_esc(_friendly_label(primary_state_verb, primary_label, show_trade_plan))}" '
        f'data-copy="{_esc(primary_copy)}" '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">'
        f'{_esc(_friendly_label(primary_state_verb, primary_label, show_trade_plan))}</button>',
        f'<button class="td-rail{" td-pass" if show_trade_plan else ""}" data-card="{cid}" data-verb="PASS" '
        f'data-label="PASS" data-copy="PASS {cid} â€” reason: " '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">PASS</button>',
    ]
    if primary_state_verb != "RECHECK":
        rail_parts.append(
            f'<button class="td-rail" data-card="{cid}" data-verb="RECHECK" data-label="RECHECK" '
            f'data-copy="RECHECK {cid} resurface {_esc(card.get("recheck_date"))}" '
            f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">RECHECK</button>'
        )
    rail_html = ('<div class="td-actionrail">' + "".join(rail_parts) + '</div>') if show_trade_plan else "".join(rail_parts)
    feedback_html = f'<div class="td-fb td-fb-muted" id="tdfb-{cid}">no decision logged yet</div>'
    if not show_trade_plan:
        h.append(rail_html)
        h.append(feedback_html)
    if win.get("named_trigger"):
        h.append(f'<div class="td-row">trigger: {_esc(win["named_trigger"])}'
                 + (f' Â| deadline {_esc(win.get("deadline"))}' if win.get("deadline") else "") + "</div>")
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
                 f'{_esc(suggested.get("account"))} Â| {_esc(suggested.get("tax_flag"))} Â| {_esc(suggested.get("why"))}</div>')
    for leg in (execn.get("legs") or []):
        line = (f'sell ${leg.get("sell_usd", 0):,.0f} in {_esc(leg.get("owner"))} {_esc(leg.get("broker"))} '
                f'{_esc(leg.get("account"))} Â| {_esc(leg.get("tax_flag"))}')
        if leg.get("proceeds_constraint"):
            line += f' Â| âš  {_esc(leg["proceeds_constraint"])}'
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
                 f'Â| heat {_esc(sizing.get("heat", "unknown"))}</div>')
        if sizing.get("cap_basis"):
            h.append(f'<div class="td-row">cap basis: {_esc(sizing["cap_basis"])}</div>')
    h.append(f'<div class="td-row">impact: {_esc(impact.get("band"))} Â| material: '
             f'{"yes" if impact.get("material") else "no"}</div>')
    after_action = card.get("after_action") or {}
    if after_action.get("line"):
        h.append(f'<div class="td-row">{_esc(after_action["line"])}</div>')
    if after_action.get("outcome_line"):
        h.append(f'<div class="td-row">{_esc(after_action["outcome_line"])}</div>')
    h.append('<details class="td-muted-details"><summary>Not checked / optional context</summary>')
    h.append(_render_iv_hint(display))
    h.append(_render_not_checked(display))
    h.append('</details>')
    h.append("</div></details>")
    if show_trade_plan:
        ticker = str(card.get("ticker") or "").upper()
        amount = plan.get("notional_usd")
        if amount is None:
            amount = card.get("dollars")
        headline = _hero_headline_text(_move_verb(card, plan), ticker, amount, plan)
        # The hero is a <details open>: the loud headline stays in the summary (always
        # visible, even collapsed), and one tap folds the whole move away so it never
        # owns the whole screen. The tall sizing panel is its own collapsed sub-details.
        header = (
            '<details class="td-hero" open>'
            '<summary class="td-herosum">' + _render_hero_summary(card, plan, rank) + '</summary>'
            '<div class="td-herobody">'
            + _render_trade_plan_header(card, plan, rank)
            + _render_sizing_transparency(card, tunables or {})
            + _render_final_check(card, plan, gated=(primary_state_verb != "ACT"))
            + rail_html + feedback_html
            + _render_ask_block(raw_cid, headline)
            + '<div class="td-row" style="margin-top:10px;color:#64748b;font-size:12px">▾ full engine card - face, conviction read &amp; evidence - below</div>'
            + '</div></details>'
        )
        h.insert(0, header)
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
    caption = str(meta.get("caption") or "These are ranked research/recheck candidates from the daily pullback packet. They are visible so discounted or watched names do not disappear, but they do not outrank executable decisions without fresh confirmation.")
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


# ---------------------------------------------------------------------------
# RENDER-REDESIGN: decision-led surface (hero move, faces, good-price tier)
# ---------------------------------------------------------------------------
def _gate_color_class(gate: Any) -> str:
    g = str(gate or "").upper()
    if "GREEN" in g:
        return "td-gate-green"
    if "RED" in g:
        return "td-gate-red"
    return "td-gate-amber"


def _pct_text(value: Any) -> str:
    v = _coerce_float(value)
    return f"{v:.1f}%" if v is not None else "n/a"


def _move_verb(card: dict[str, Any], plan: dict[str, Any]) -> str:
    action = str((plan or {}).get("action") or "").lower()
    direction = _card_action_direction(card).upper()
    if "add" in action:
        return "ADD"
    if "buy" in action:
        return "BUY"
    if direction in {"SELL", "TRIM", "REDUCE"}:
        return direction
    return direction or "ADD"


def _friendly_label(state_verb: str, default: str, hero: bool) -> str:
    """Plain-language rail labels for the loud move surface (no shorthand). The
    visible text changes; data-verb / data-copy stay canonical so the parity +
    persistence contracts are untouched. A cleared move reads 'DO IT'; a move the
    engine still gates reads 'DO IT - final check first' (a good move, with one
    recommended check spelled out beside the rail), never the cryptic 'STAGE'."""
    if not hero:
        return default
    return {
        "ACT": "DO IT",
        "CANDIDATE": "DO IT - final check first",
        "RECHECK": "DO IT - final check first",
        "WATCH": "WATCH",
    }.get(state_verb, default)


_BLOCKER_PLAIN = {
    "same-session uw price/flow": "a fresh live options/flow check (Unusual Whales) this session",
    "funding source confirmation": "the sells that fund it (above) actually clear",
    "pre-trade gate": "the pre-trade price gate holds (see the gate line above)",
}


def _final_check_items(card: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    """Plain-language 'final check' list for a good-but-gated move. Faithful to the
    engine's own blocker labels (humanized where known, verbatim otherwise) - never
    fabricated."""
    raw = list((plan or {}).get("blockers") or []) or list(card.get("card_blockers") or [])
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        out.append(_BLOCKER_PLAIN.get(text.lower(), text))
    return out


def _render_final_check(card: dict[str, Any], plan: dict[str, Any], gated: bool) -> str:
    """A positive, plain-language note by the move rail. Gated -> 'looks like a good
    move; one final check recommended before you place the order'. Cleared -> 'good to
    go'. Replaces the old cryptic STAGE affordance with a clear recommended-check."""
    if not gated:
        return ('<div class="td-finalcheck td-cleared"><b>✓ Cleared - good to go.</b> '
                'The pre-trade checks are met; place the order when you are ready.</div>')
    items = _final_check_items(card, plan)
    body = (
        '<ul>' + "".join(f'<li>{_esc(it)}</li>' for it in items) + '</ul>'
        if items else
        '<div>Confirm the pre-trade gate above before you place the order.</div>'
    )
    return (
        '<div class="td-finalcheck">'
        '<b>✓ This looks like a good move.</b> One final check is <b>recommended</b> before you place the order:'
        f'{body}'
        'Tap <b>DO IT - final check first</b> to record that you are committing; it becomes a plain '
        '<b>DO IT</b> once these clear.</div>'
    )


def _render_hero_summary(card: dict[str, Any], plan: dict[str, Any], rank: int) -> str:
    """The always-visible loud headline that stays on the collapsed hero: kicker +
    verb/ticker/$amount + the percent-of-book line. So even collapsed, you still see
    exactly what the move is."""
    plan = plan or {}
    ticker = str(card.get("ticker") or "").upper()
    verb = _move_verb(card, plan)
    amount = plan.get("notional_usd")
    if amount is None:
        amount = card.get("dollars")
    verb_cls = "td-verb td-verb-sell" if verb in {"SELL", "TRIM", "REDUCE"} else "td-verb"
    h = [f'<div class="td-hero-kicker">#{rank} funded move | trade plan | highest impact leads '
         '<span class="td-hero-toggle">tap to collapse / expand</span></div>']
    h.append(
        f'<div class="td-hl"><span class="{verb_cls}">{_esc(verb)}</span>'
        f'<span class="td-tk">{_esc(ticker)}</span><span class="td-amt">{_money_text(amount)}</span></div>'
    )
    cur, tgt = plan.get("current_pct"), plan.get("target_pct")
    if cur is not None or tgt is not None:
        h.append(f'<div class="td-hero-sub">{_pct_text(cur)} -> {_pct_text(tgt)} of book | funded position-builder (candidate)</div>')
    return "".join(h)


def _render_trade_plan_header(card: dict[str, Any], plan: dict[str, Any], rank: int) -> str:
    """The trade-plan body for a funded move: funded-by (sums) -> why -> timing ->
    gate (color) -> one caveat. Display-only; the engine card with its canonical rail,
    conviction read, and evidence renders just below."""
    plan = plan or {}
    h: list[str] = []
    h.append('<div class="td-kv">')
    h.append('<div class="td-k">Funded by</div>' + _render_funded_by(plan))
    if plan.get("rationale"):
        h.append(f'<div class="td-k">Why</div><div class="td-v">{_esc(plan["rationale"])}</div>')
    if plan.get("entry_note"):
        h.append(f'<div class="td-k">Timing</div><div class="td-v">{_esc(plan["entry_note"])}</div>')
    gate = plan.get("gate")
    if gate:
        reason = f' {_esc(plan.get("gate_reason"))}' if plan.get("gate_reason") else ''
        h.append(
            f'<div class="td-k">Gate</div><div class="td-v">'
            f'<span class="td-gate-chip {_gate_color_class(gate)}">● {_esc(str(gate).upper())}</span>{reason}</div>'
        )
    if plan.get("account"):
        h.append(f'<div class="td-k">Account</div><div class="td-v">{_esc(plan["account"])} <span class="td-tag">check available cash first</span></div>')
    h.append('</div>')
    caveats = plan.get("caveats") or []
    if caveats:
        h.append(f'<div class="td-caveat"><b>Caveat:</b> {_esc(caveats[0])}</div>')
    return "".join(h)


def _render_ask_block(raw_cid: str, headline: str) -> str:
    cid = _esc(raw_cid)
    return (
        '<details class="td-ask"><summary></summary>'
        f'<textarea id="tdq-{cid}" placeholder="ask or comment on this card - saved against the card, and one tap copies a chat-ready [CARD] tag"></textarea>'
        '<div class="td-askrow">'
        f'<button class="td-mini" data-card="{cid}" data-headline="{_esc(headline)}" onclick="tdAskCopy(this)">Copy for chat</button>'
        f'<button class="td-mini" data-card="{cid}" onclick="tdAskSave(this)">Save note on card</button>'
        f'<span class="td-askfb" id="tdqfb-{cid}"></span>'
        '</div>'
        f'<div class="td-notes" id="tdnotes-{cid}"></div>'
        '</details>'
    )


def _humanize_tunable(key: str) -> str:
    return str(key).replace("_usd", " ($)").replace("_pct", " (%)").replace("_", " ").strip()


def _render_sizing_transparency(card: dict[str, Any], tunables: dict[str, Any]) -> str:
    """Show the LIVE size and every input that produced it - no shorthand, no hidden
    caps. RENDER-IF-PRESENT: when F2's ``sizing_tunables.json`` exists, render the dials
    (editable + live client recompute) + the formula; until then, show the engine's real
    current sizing inputs honestly and say the dials arrive with F2 - never fabricate them."""
    sizing = card.get("sizing") or {}
    if not sizing and not tunables:
        return ""
    raw_cid = str(card.get("card_id") or "")
    cid = _esc(raw_cid)
    source = sizing.get("source")
    suggested = sizing.get("suggested_usd")
    heat = sizing.get("heat")
    cap = sizing.get("cap_basis")
    conv = (card.get("conviction_display") or {}).get("x5") or 1
    out = ['<details class="td-sizing"><summary class="td-sizing-title">How this size is set - every input, no hidden caps (tap)</summary>']
    if tunables:
        # F2 (conviction->size) is live. DISPLAY the engine's real breakdown - the live
        # size, the conviction lift it applied (or didn't), the soft-reference tier band,
        # the cash reality - then expose every dial from sizing_tunables.json (editable +
        # persisted) and recompute the shown size client-side with the ENGINE'S formula.
        try:
            mult = float(sizing.get("size_lift_mult")) if sizing.get("size_lift_mult") is not None else 1.0
        except (TypeError, ValueError):
            mult = 1.0
        try:
            strength = float(sizing.get("size_lift_strength") or 0.0)
        except (TypeError, ValueError):
            strength = 0.0
        try:
            anchor = (float(suggested) / mult) if (isinstance(suggested, (int, float)) and mult) else float(suggested or 0.0)
        except (TypeError, ValueError):
            anchor = 0.0
        base_def = float(tunables.get("base_size_usd") or 0.0)
        slope_def = float(tunables.get("conviction_size_slope") or 0.0)
        softmax_def = tunables.get("per_name_soft_max_usd")
        softmax_def = float(softmax_def) if isinstance(softmax_def, (int, float)) else 0.0
        out.append(
            f'<div class="td-sizing-live" id="tdsize-{cid}" data-formula="f2" '
            f'data-anchor="{anchor:.2f}" data-strength="{strength:.6g}" data-base="{base_def:.2f}" '
            f'data-slope="{slope_def:.6g}" data-softmax="{softmax_def:.2f}">live size {_money_text(suggested)}</div>'
        )
        lift_phrase = ("converging, independent evidence - conviction lift applied"
                       if strength > 0 else
                       "single-group / not converging - NO lift (the F1 honesty rail; size never keys off echo)")
        out.append(
            '<div class="td-sizing-formula">live size = anchor × (1 + conviction_size_slope × conviction strength). '
            f'This card: anchor {_money_text(anchor)} × {mult:.2f} (conviction strength {strength:.2f} - {lift_phrase}) '
            f'= {_money_text(suggested)}. Soft caps apply only if set below (default off); the tier ceiling is a soft '
            'reference, not a clip - no hidden caps.</div>'
        )
        if cap:
            out.append(f'<div class="td-sizing-formula">engine breakdown: {_esc(cap)}</div>')
        ctx = []
        if heat:
            ctx.append(f'heat {_esc(heat)}')
        if sizing.get("floor_pct") is not None and sizing.get("ceiling_pct") is not None:
            ctx.append(f'tier floor {_pct_text(sizing.get("floor_pct"))} / ceiling {_pct_text(sizing.get("ceiling_pct"))} (soft reference)')
        if sizing.get("current_pct") is not None:
            ctx.append(f'you currently hold {_pct_text(sizing.get("current_pct"))} of book')
        if sizing.get("available_cash") is not None:
            cash = f'available cash {_esc(sizing.get("available_cash"))}'
            if sizing.get("exceeds_cash"):
                cash += ' - ⚠ suggested size EXCEEDS available cash'
            ctx.append(cash)
        if ctx:
            out.append(f'<div class="td-sizing-note">{" | ".join(ctx)}</div>')
        for key in ("base_size_usd", "conviction_size_slope", "per_name_soft_max_usd",
                    "concentration_soft_max_pct", "min_converging_groups", "max_conviction_strength"):
            if key not in tunables:
                continue
            val = tunables.get(key)
            is_off = val is None
            num = 0.0 if is_off else float(val)
            if "usd" in key:
                top = max(num * 3.0, 200000.0)
            elif "slope" in key:
                top = max(num * 3.0, 3.0)
            elif "pct" in key:
                top = max(num * 3.0, 25.0)
            elif "groups" in key:
                top = 6.0
            else:
                top = max(num * 3.0, 2.0)
            default_txt = "off" if is_off else f"{val}"
            out.append(
                '<div class="td-dialrow"><div class="td-dial-label">'
                f'{_esc(_humanize_tunable(key))} <i>engine default {_esc(default_txt)}</i></div>'
                f'<div class="td-dial"><input type="range" min="0" max="{top:.6g}" step="any" value="{num:.6g}" '
                f'data-key="{_esc(key)}" data-card="{cid}" oninput="tdDial(this)"></div>'
                f'<div class="td-dial-val" id="tddialval-{cid}-{_esc(key)}">{_esc(default_txt)}</div></div>'
            )
        bools = {k: v for k, v in tunables.items() if isinstance(v, bool)}
        if bools:
            out.append('<div class="td-sizing-note">Engine switches (shown so nothing is hidden): '
                       + ' | '.join(f'{_esc(_humanize_tunable(k))} = {"ON" if v else "OFF"}' for k, v in bools.items())
                       + '</div>')
        crw = tunables.get("conviction_read_weights")
        if isinstance(crw, dict):
            out.append('<div class="td-sizing-note">conviction read -> strength weights: '
                       + ' | '.join(f'{_esc(k)} = {_esc(v)}' for k, v in crw.items()) + '</div>')
        out.append(
            '<div class="td-sizing-note">Drag a dial: the live size recomputes immediately (mirroring the engine '
            'formula) and your override is saved with a chat-ready sync command for <code>src/sizing_tunables.json</code>. '
            f'Engine default size for this card: {_money_text(suggested)}. (base_size_usd only applies when a card has '
            'no reallocation anchor; the slope only lifts a converging, non-conflicted read.)</div>'
        )
    else:
        # F2 absent fallback (kept for robustness) - honest degrade, never fabricate dials.
        out.append(
            '<div class="td-sizing-note">Live conviction->size dials (F2) are not present in this build, '
            'so there are no tunable knobs to show - and none are invented. What the engine reports for this card '
            'right now:</div>'
        )
        cap_txt = f' | cap basis: {_esc(cap)}' if cap else ''
        out.append(
            f'<div class="td-sizing-formula">conviction read: Conviction {_esc(conv)}/5 | '
            f'engine suggested size: {_money_text(suggested)} | basis: {_esc(source or "unknown")} | '
            f'heat: {_esc(heat or "unknown")}{cap_txt}</div>'
        )
        out.append(
            '<div class="td-sizing-note">With <code>src/sizing_tunables.json</code> present, this panel shows the '
            'live conviction-driven size, every dial (base size, conviction slope, soft caps - no hidden ceilings), '
            'and the formula - each editable here, persisted, and recomputing the number as you drag.</div>'
        )
    out.append('</details>')
    return "".join(out)


def _render_funded_by(plan: dict[str, Any]) -> str:
    legs = [leg for leg in (plan.get("funded_by") or []) if leg.get("ticker")]
    if not legs:
        return '<div class="td-v">Funding: not yet assigned</div>'
    parts = " | ".join(f'{_esc(leg["ticker"])} {_money_text(leg.get("notional_usd"))}' for leg in legs)
    total = sum(float(leg.get("notional_usd") or 0.0) for leg in legs)
    return f'<div class="td-v">{parts} <span class="td-tag">( = {_money_text(total)}, dollar-for-dollar )</span></div>'


def _hero_headline_text(verb: str, ticker: str, amount: Any, plan: dict[str, Any]) -> str:
    funders = ", ".join(str(leg.get("ticker")) for leg in (plan.get("funded_by") or []) if leg.get("ticker"))
    base = f"{verb} {ticker} {_money_text(amount)}"
    return f"{base} (funded by {funders})" if funders else base


def _render_good_price_row(row: dict[str, Any]) -> str:
    tk = str(row.get("ticker") or "").upper()
    deep = row.get("tier") == "deep"
    monitor = bool(row.get("monitor"))
    disc = _coerce_float(row.get("pct_below_high"))
    price = _coerce_float(row.get("price"))
    impact = row.get("impact")
    exposure = _coerce_money(row.get("exposure_usd"))
    exposure_pct = _coerce_float(row.get("exposure_pct"))
    high = _coerce_float(row.get("fifty_two_week_high"))
    high_date = str(row.get("high_date") or "")
    disc_txt = f"{disc:.1f}%" if disc is not None else "n/a"
    high_tip = (f"{abs(disc):.1f}% below its 52-week high of {_money_text(high)}"
                + (f" (set {high_date})" if high_date else "")) if disc is not None and high is not None else "off its 52-week high"
    own_txt = _money_text(exposure) if exposure is not None else "$0"
    own_tip = (f"You currently hold {own_txt} of {tk}"
               + (f" ({exposure_pct:.2f}% of book)" if exposure_pct is not None else "")) if exposure is not None and exposure > 0 else f"You hold none of {tk} - a new position"
    own_lab = "you own" if (exposure is not None and exposure > 0) else "you own (new)"
    impact_tip = ("Impact = a discount-priority score: how far off its 52-week high, plus a boost if a trusted "
                  "list flags it, minus a little for crowding or source disagreement. It is NOT conviction and "
                  "NOT a buy signal - high means 'worth a look,' not 'buy now.'")
    stat = ''
    if monitor:
        stat = '<span class="td-stat">monitor</span>'
    deep_cls = ' td-opp-deep' if deep else ''
    h = [f'<details class="td-opp{deep_cls}"><summary class="td-oppsum">']
    h.append(f'<span class="td-otk">{_esc(tk)}</span>')
    h.append(f'<span class="td-m td-disc" title="{_esc(high_tip)}"><span class="td-val">{_esc(disc_txt)}</span><i>off 52w high</i></span>')
    h.append(f'<span class="td-m" title="Latest share price"><span class="td-val">{_money_text(price)}</span><i>per share</i></span>')
    h.append(f'<span class="td-m td-imp" title="{_esc(impact_tip)}"><span class="td-val">impact {_esc(round(float(impact)) if isinstance(impact,(int,float)) else impact)}</span><i>what\'s this?</i></span>')
    h.append(f'<span class="td-m" title="{_esc(own_tip)}"><span class="td-val">{_esc(own_txt)}</span><i>{_esc(own_lab)}</i></span>')
    h.append(f'{stat}<span class="td-caret">details</span></summary>')
    h.append('<div class="td-oppbody">')
    why = []
    tags = row.get("source_tags") or []
    if tags:
        why.append("flagged by " + ", ".join(_esc(str(t)) for t in tags))
    elif row.get("trusted"):
        why.append("on a trusted research list")
    else:
        why.append("flagged on the discount alone (no analyst/Notion tag)")
    if high is not None and disc is not None:
        why.append(f"52-week high {_money_text(high)}{(' ('+_esc(high_date)+')') if high_date else ''} -> {_money_text(price)} now, {disc_txt} from that high")
    h.append(f'<div><b>Why it\'s flagged:</b> {"; ".join(why)}.</div>')
    h.append(
        '<div><b>What "impact" means:</b> a discount-priority / "worth a look" score - '
        '<b>not conviction, not a buy signal.</b> It rises with the depth of the discount and a trusted-list '
        'boost, and falls for crowding (a big position you already hold) or source disagreement. '
        'A high number on a distressed name reads "look," not "buy."</div>'
    )
    if row.get("disconfirmation"):
        h.append(f'<div><b>Promote to a real buy only if:</b> {_esc(row["disconfirmation"])}</div>')
    pos_line = own_tip + "."
    if row.get("sellgate_note"):
        pos_line += f' <b>{_esc(row["sellgate_note"])}.</b>'
    h.append(f'<div><b>Your position:</b> {pos_line}</div>')
    h.append('<div><b>Options &amp; flow:</b> not in this packet - pull a live Unusual Whales options/flow check on demand (never shown faked when absent).</div>')
    cid = f'WATCH-{_esc(tk)}'
    headline = (f"{tk} - {disc_txt} off 52w high, {_money_text(price)}/share, impact "
                f"{round(float(impact)) if isinstance(impact,(int,float)) else impact}, {own_lab} {own_txt}")
    h.append(
        '<div class="td-askmini">'
        f'<textarea id="tdq-{cid}" placeholder="ask about {_esc(tk)} - e.g. is the discount enough to start a small starter, or wait for flow?"></textarea>'
        '<div class="td-askrow">'
        f'<button class="td-mini" data-card="{cid}" data-headline="{_esc(headline)}" onclick="tdAskCopy(this)">Copy for chat</button>'
        f'<span class="td-askfb" id="tdqfb-{cid}"></span></div></div>'
    )
    h.append('</div></details>')
    return "".join(h)


def _render_good_price_tier(payload: dict[str, Any]) -> str:
    tier = payload.get("good_price_tier") or {}
    higher = tier.get("higher") or []
    deep_visible = tier.get("deep_visible") or []
    deep_more = tier.get("deep_more") or []
    if not higher and not deep_visible and not deep_more:
        return ""
    h = ['<div class="td-sectlead">Good price, lower conviction <span class="td-q">- don\'t let these rot in the queue</span></div>']
    note = ('At good prices and worth watching, but <b>not funded / high-conviction</b> like the moves above. '
            'Shown so you don\'t miss them - <b>not</b> dressed up to look urgent. Hover any number for what it '
            'means; <b>click a name</b> for its thesis, where it came from, and what would have to be true to buy it.')
    if str(tier.get("freshness")) == "stale":
        note += f' <b>Packet STALE as of {_esc(tier.get("packet_as_of"))} - research context only, prices not current.</b>'
    h.append(f'<div class="td-tiernote">{note}</div>')
    for row in higher:
        h.append(_render_good_price_row(row))
    if deep_visible:
        h.append('<div class="td-screenline">Deeper discounts - <b>research-only</b> until the thesis clears (these are not buys):</div>')
        for row in deep_visible:
            h.append(_render_good_price_row(row))
    more_tickers = tier.get("deep_more_tickers") or []
    screen_count = tier.get("screen_count") or 0
    tail_bits = []
    if more_tickers:
        tail_bits.append(f"+ {len(more_tickers)} more deep-discount name(s) ({', '.join(_esc(t) for t in more_tickers)})")
    if screen_count:
        tail_bits.append(f"a <b>{screen_count}-name discount screen</b> behind the daily pullback packet")
    if tail_bits:
        h.append(f'<div class="td-screenline">{" and ".join(tail_bits)} - surfaced here as the top of the queue; the rest stays one tap deep in the machinery so nothing rots unseen.</div>')
    return "".join(h)


def _render_freshness_chip(payload: dict[str, Any]) -> str:
    built = payload.get("built")
    honesty = payload.get("honesty") or {}
    pl = payload.get("plan_line") or {}
    positions = honesty.get("positions_as_of") or pl.get("positions_as_of")
    gates = honesty.get("gates_as_of")
    disp_state = "none logged yet" if honesty.get("dispositions") else "logged - see cards"
    fresh = []
    if positions:
        fresh.append(f"positions {_esc(positions)}")
    if gates:
        fresh.append(f"gates {_esc(gates)}")
    warn = []
    if honesty.get("cash"):
        warn.append("cash not checked")
    warn.append(f"dispositions: {disp_state}")
    h = ['<div class="td-fresh">', f'<b>Conviction Dashboard</b><span>| built {_esc(built)}</span>']
    if fresh:
        h.append(f'<span><span class="td-dot td-dot-g"></span> {" | ".join(fresh)}</span>')
    h.append(f'<span class="td-warn"><span class="td-dot td-dot-a"></span> {" | ".join(warn)} | full trust panel ▾ in machinery below</span>')
    h.append('</div>')
    return "".join(h)


def _render_machinery(payload: dict[str, Any]) -> str:
    # first_viewport's primary-command rail duplicates the hero card's rail for the same
    # card_id with a non-canonical copy; suppress it so the card's canonical, persisting
    # rail above is the single source. disposition_pressure rails act on WATCH-promotion
    # rows (non-card decision keys), so they keep their own actions.
    body = [
        _render_command_strip(payload),
        _render_first_viewport(payload, rails=False),
        _render_disposition_pressure(payload),
        _render_candidate_feed_index(payload),
        _render_passivity_panel(payload),
        _render_disposition_coverage(payload),
        _render_trust_panel(payload),
        _render_top_verdict(payload),
        _render_watch_queue(payload),
        _render_do_not_touch(payload),
    ]
    body_html = "".join(b for b in body if b)
    if not body_html:
        return ""
    return (
        '<details class="td-machine"><summary>System state, queues &amp; coverage - the machinery '
        '(collapsed on purpose; none of it shouts over a real move)</summary>'
        f'<div class="td-machinebody">{body_html}</div></details>'
    )


def render_today_decide_html(payload: dict[str, Any]) -> str:
    ga = payload["goal_anchor"]
    pl = payload["plan_line"]
    built = _esc(payload["built"])
    built_date = str(payload.get("built") or "")
    moves_plans = (payload.get("trade_plan") or {}).get("moves") or {}
    tunables = payload.get("sizing_tunables") or {}

    def _plan_for(card: dict[str, Any]) -> dict[str, Any] | None:
        return moves_plans.get(str(card.get("ticker") or "").upper())

    h: list[str] = [_CSS, _JS, f'<section id="today-decide" class="td" data-built="{built}">']
    h.append(f'<h2>TODAY â€” DECIDE <span style="color:#94a3b8;font-size:12px">built {built}</span></h2>')
    # 1. freshness chip - title + build stamp + fresh/stale; trust panel collapses below
    h.append(_render_freshness_chip(payload))
    # goal context - display-only, never feeds ranking or urgency (pace line carries the
    # single "display-only" marker; do not add another)
    if ga.get("book_value") is not None:
        h.append(f'<div class="td-anchor">${ga["book_value"]:,.0f} â†’ ${ga["fi_target"]:,.0f} '
                 f'Â| {ga["pct_to_target"]}% there</div>')
    else:
        h.append('<div class="td-anchor">book value: not readable â€” honest absence</div>')
    h.append(f'<div class="td-pace">{_esc(ga["pace_line"])}</div>')
    pool = pl.get("pool_usd")
    short = pl.get("shortfall_usd")
    h.append('<div class="td-plan">plan: '
             + (f'funding pool ${pool:,.0f}' if isinstance(pool, (int, float)) else 'funding pool n/a')
             + (f' Â| shortfall ${short:,.0f}' if isinstance(short, (int, float)) else '')
             + f' Â| positions as of {_esc(pl.get("positions_as_of"))}</div>')

    # 2. THE MOVE leads -> next moves -> funding trims -> other decisions. Render-side
    #    grouping only: actual buys/adds lead as MOVES (the first is the hero), funding
    #    and rebalancing trims group together, everything else (resolve/recheck, incl.
    #    F1 CONFLICTED non-buys) follows. Engine priority, scoring, sizing, and ranking
    #    are untouched - this just stops a high-priority funding trim from masquerading
    #    as "the move." Each material buy renders the loud trade-plan header (inside
    #    _render_card) above its canonical engine card.
    def _decision_group(card: dict[str, Any]) -> str:
        d = card.get("conviction_display") or {}
        f1 = bool(d.get("conflicted") or d.get("band") == "CONFLICTED")
        if _card_action_direction(card).upper() in {"SELL", "TRIM", "REDUCE"}:
            return "trim"
        if _is_material(card) and not f1 and _plan_for(card):
            return "move"
        return "other"

    groups: dict[str, list[dict[str, Any]]] = {"move": [], "trim": [], "other": []}
    for card in payload["cards"]:
        groups[_decision_group(card)].append(card)
    rank = 1

    def _emit(card: dict[str, Any]) -> None:
        nonlocal rank
        h.extend(_render_card(card, rank, check_first=bool(card.get("card_blockers")),
                              built_date=built_date, plan=_plan_for(card), tunables=tunables))
        rank += 1

    h.append('<div class="td-sectlead">The move - do this first</div>')
    if groups["move"]:
        for i, card in enumerate(groups["move"]):
            if i == 1:
                h.append('<div class="td-sectlead">Next moves</div>')
            _emit(card)
    else:
        # honest starvation - never a confident grid of zeros
        h.append(
            '<div class="td-hero"><div class="td-hero-kicker">no funded high-conviction move is live</div>'
            '<div class="td-hero-sub">No high-conviction, funded move is live right now. The strongest things on '
            'the board are the trims, rechecks, and good-price watches below - shown plainly, not dressed up as '
            'urgent. Nothing here is one tap from a buy without fresh confirmation.</div></div>'
        )
    if groups["trim"]:
        h.append('<div class="td-sectlead">Funding &amp; rebalancing trims '
                 '<span class="td-q">- execute paired with the moves they fund; no standalone urgency</span></div>')
        for card in groups["trim"]:
            _emit(card)
    if groups["other"]:
        h.append('<div class="td-sectlead">Other decisions '
                 '<span class="td-q">- resolve / recheck before acting</span></div>')
        for card in groups["other"]:
            _emit(card)
    backlog = payload["backlog"]
    if backlog:
        h.append(f'<div class="td-subqueue"><div class="td-card-section-title">More impact-ranked decisions ({len(backlog)})</div>')
        for label, cards in _visible_card_sections(backlog):
            h.append(f'<div class="td-card-section-title">{_esc(label)}</div>')
            for card in cards:
                h.extend(_render_card(card, rank, check_first=bool(card.get("card_blockers")),
                                      built_date=built_date, plan=_plan_for(card), tunables=tunables))
                rank += 1
        h.append("</div>")

    # 3. good price, lower conviction tier (visible-but-quiet; never one tap from a buy)
    h.append(_render_good_price_tier(payload))

    # 4. machinery (collapsed) - system health, queues, coverage moved below the decisions
    h.append(_render_machinery(payload))

    # 5. honesty / caveats / conflicts (collapsed, bottom)
    cong = payload["congruence"]
    h.append('<details class="td-muted-details"><summary>Portfolio thesis context</summary>')
    if cong.get("status") == "ok":
        for row in cong.get("rows") or []:
            flag = "\U0001f6a9 " if row.get("flagged") else ""
            h.append(f'<div class="td-cong">{flag}{_esc(row["insight_id"])} Â| {_esc(row["line"])}</div>')
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
