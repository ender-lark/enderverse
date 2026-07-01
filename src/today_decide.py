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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import data_health as _dh
import congruence as cg
import conviction_engine as ce
import directive_recs as dr
import insight_register as ir
import lookthrough_disclosure as ltd
import timing_engine as te
import disposition_log
import options_surface as opt_surface
import volatility_opportunity_converter as voc

SRC = Path(__file__).resolve().parent
FEED_PATH = SRC / "latest_cockpit_feed.json"

_GATE_COLORS = {"red": "#f87171", "red_but_tested": "#fbbf24", "green": "#34d399", "context": "#94a3b8"}
_CLASS_COLORS = {"OPEN-NOW": "#34d399", "STAGE-ONLY": "#fbbf24", "GATED": "#f87171", "WAIT": "#94a3b8"}
_BAND_COLORS = {"LOW": "#94a3b8", "MODERATE": "#fbbf24", "HIGH": "#34d399"}
_SELL_BAND_COLORS = {"LOW": "#94a3b8", "MODERATE": "#fbbf24", "HIGH": "#f87171"}
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
    options: dict[str, Any] | None = None,
    volatility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feed = _load_feed(feed)
    today_iso = today or date.today().isoformat()
    insights_payload = insights_payload or ir.load_insights()
    gates = gates if gates is not None else te.load_gates()
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
    attach_conviction_displays(stack["cards"] + stack["backlog"])
    honesty = dict(stack["honesty"])
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
            {k: g.get(k) for k in ("gate_id", "symbol", "state", "note", "confirm_rule", "stated")}
            for g in gates
        ],
        "data_health": data_health,
        "cards": stack["cards"],
        "backlog": stack["backlog"],
        "congruence": congruence_result,
        # Options-expression surface (opt-in): a produce/surface_options() result, or None when
        # this build didn't screen options. Rendered LOUD (lead with the move) below congruence.
        "options": options,
        # Volatility opportunity surface (opt-in): a volatility_opportunity_converter result that
        # fuses Fundstrat calls + tape + target gaps + flow + event-risk into ONE staged command,
        # or None when this build didn't run the converter. Rendered LOUD (lead with the move).
        "volatility": volatility,
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
.td .td-gate{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;
  margin:0 6px 8px 0;border:1px solid}
.td .td-card{border:1px solid #1e293b;border-radius:10px;padding:12px;margin:10px 0;background:#0f172a}
.td .td-card.td-conflicted{border-color:#fb923c}
.td details.td-card{padding:0}
.td details.td-card>summary{list-style:none;cursor:pointer;padding:12px;display:block}
.td details.td-card>summary::-webkit-details-marker{display:none}
.td .td-body{padding:2px 12px 12px 12px;border-top:1px solid #1e293b;margin-top:10px;padding-top:8px}
.td .td-move{font-size:18px;font-weight:750;line-height:1.25}
.td .td-conv-line{display:block;border-radius:8px;padding:8px 10px;color:#0b1220}
.td .td-section-title{font-size:11px;color:#94a3b8;font-weight:800;letter-spacing:.04em;text-transform:uppercase;margin:8px 0 4px}
.td .td-why-item{font-size:13px;color:#cbd5e1;margin:3px 0}
.td .td-why-item strong{color:#e2e8f0}
.td .td-factor-conflict{color:#fdba74}
.td .td-pill{display:inline-block;border-radius:6px;padding:1px 8px;font-size:12px;
  font-weight:600;margin-left:8px;color:#0b1220}
.td .td-row{font-size:13px;color:#cbd5e1;margin:4px 0}
.td .td-chip{border:1px solid #fb923c;color:#fdba74;border-radius:8px;padding:6px 8px;
  font-size:12px;margin:6px 0}
.td .td-dossier{border:1px solid #334155;border-radius:8px;padding:8px;margin:8px 0;background:#0b1220}
.td .td-dossier-head{font-size:12px;color:#e2e8f0;font-weight:800;margin-bottom:4px}
.td .td-dossier-meta{font-size:11px;color:#94a3b8;margin:2px 0 6px}
.td .td-dossier-read{font-size:12px;color:#cbd5e1;margin:3px 0}
.td .td-dossier-read strong{color:#e2e8f0}
.td details{margin:4px 0;font-size:12px;color:#94a3b8}
.td .td-health{margin:8px 0 4px 0;line-height:2}
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


def _render_factor_breakdown(display: dict[str, Any]) -> str:
    factors = ((display.get("why") or {}).get("decisive_factors") or [])
    if not factors:
        return '<div class="td-why-item">Battery decisive factors: none surfaced.</div>'
    bits = []
    for row in factors:
        cls = " td-factor-conflict" if row.get("conflict") else ""
        tag = "conflicting" if row.get("conflict") else "decisive" if row.get("decisive") else "factor"
        bits.append(
            f'<div class="td-why-item{cls}"><strong>{_esc(tag)}:</strong> '
            f'{_esc(row.get("label") or row.get("key"))} - {_esc(row.get("value_str") or "")}</div>'
        )
    return "".join(bits)


def _render_layer_breakdown(display: dict[str, Any]) -> str:
    layers = display.get("layers") or {}
    rows = layers.get("rows") or []
    if not rows or layers.get("mode") == "off":
        return ""
    bits = ['<div class="td-section-title">Name / sector split</div>']
    for row in rows:
        status = row.get("status") or "not_checked"
        points = _layer_points_text(row.get("points"))
        detail = str(row.get("detail") or "").strip()
        detail_html = f' - {_esc(detail)}' if detail else ""
        bits.append(
            f'<div class="td-why-item"><strong>{_esc(row.get("label") or row.get("key"))}</strong> '
            f'{points} {_esc(row.get("read") or "LOW")} ({_esc(status)}){detail_html}</div>'
        )
    if layers.get("conflict"):
        bits.append(f'<div class="td-chip">LAYER CONFLICT - {_esc(layers.get("conflict"))}</div>')
    for reason in layers.get("clamped_reasons") or []:
        bits.append(f'<div class="td-row">layer guard: {_esc(reason)}</div>')
    recheck = layers.get("sector_only_recheck") or {}
    if recheck.get("eligible"):
        suffix = "alert disabled in shadow mode" if not recheck.get("alert_enabled") else "alert enabled"
        bits.append(
            f'<div class="td-row">sector-only recheck: {_esc(recheck.get("next_step") or "re-check")} '
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


def _render_dossier_block(card: dict[str, Any]) -> str:
    dossier = card.get("dossier") or {}
    if not isinstance(dossier, dict):
        return ""
    reads = dossier.get("reads") or {}
    if not isinstance(reads, dict):
        return ""
    read_labels = ("edge", "price", "timing", "avoid")
    lines = [
        '<div class="td-dossier">',
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
    lines.append("</div>")
    return "".join(lines)


def _render_not_checked(display: dict[str, Any]) -> str:
    rows = display.get("not_checked") or []
    text = ", ".join(str(row) for row in rows) if rows else "none"
    return f'<div class="td-row">not checked: {_esc(text)}</div>'

def _review_posture(card: dict[str, Any], *, check_first: bool, window_class: str, direction: str) -> dict[str, str]:
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

def _render_card(card: dict[str, Any], rank: int, check_first: bool = False) -> list[str]:
    dcard = card.get("decision_card") or {}
    move = dcard.get("move") or {}
    display = card.get("conviction_display") or build_conviction_display(card)
    win = card.get("window") or {}
    execn = card.get("execution") or {}
    impact = card.get("impact") or {}
    sizing = card.get("sizing") or {}
    cid = _esc(card.get("card_id"))
    conflicted = " td-conflicted" if card.get("conflicts") or display.get("conflict") else ""
    h = [f'<details class="td-card{conflicted}">', '<summary class="td-sum">']
    if check_first:
        h.append('<div class="td-checkfirst">&#9888; CHECK DATA FIRST - inputs behind/stale (see freshness strip)</div>')
    cls = win.get("class", "WAIT")
    direction = str(move.get("direction") or "")
    posture = _review_posture(card, check_first=check_first, window_class=cls, direction=direction)
    h.append(
        f'<div class="td-move"><span class="td-conv-line" style="background:{_esc(display.get("band_color") or "#94a3b8")}">'
        f'#{rank} {_esc(display.get("text") or "")}</span></div>'
    )
    if display.get("conflict"):
        h.append(f'<div class="td-chip">CONFLICT - {_esc(display["conflict"])}</div>')
    h.append('</summary><div class="td-body">')
    h.append('<div class="td-section-title">Why it is this</div>')
    h.append(_render_factor_breakdown(display))
    h.append(_render_group_breakdown(display))
    h.append(_render_layer_breakdown(display))
    for c in card.get("conflicts") or []:
        h.append(f'<div class="td-chip">SOURCE-CONFLICT â€” {_esc(c["with"])}: â€œ{_esc(c["their_claim"])}â€ '
                 f'vs this card: {_esc(c["card_claim"])} Â· resolve before acting</div>')
    h.append('<div class="td-section-title">What would make it a confident move</div>')
    raises = display.get("raises") or []
    if raises:
        h.extend(f'<div class="td-row">raise: {_esc(r)}</div>' for r in raises)
    else:
        h.append('<div class="td-row">No raise condition surfaced.</div>')
    h.append('<div class="td-section-title">IV options-vs-shares</div>')
    h.append(_render_iv_hint(display))
    h.append(_render_dossier_block(card))
    if posture["reason"]:
        h.append(f'<div class="td-row"><strong>posture:</strong> {_esc(posture["reason"])}</div>')
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
    if primary_label != "RECHECK":
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
    h.append(_render_not_checked(display))
    h.append("</div></details>")
    return h

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
    dh = payload.get("data_health") or {}
    if dh.get("items"):
        chips = []
        for item in dh["items"]:
            color = {
                "fresh": "#34d399",
                "aging": "#fbbf24",
                "behind": "#f87171",
                "stale": "#f87171",
                "missing": "#f87171",
                "empty": "#fbbf24",
                "not_checked": "#94a3b8",
                "context": "#94a3b8",
            }.get(item.get("status"), "#94a3b8")
            chips.append(
                f'<span class="td-hchip" style="border-color:{color}">'
                f'{_esc(item.get("label"))}: <span style="color:{color}">{_esc(item.get("detail"))}</span></span>'
            )
        h.append('<div class="td-health"><span class="td-hlabel">data freshness:</span> ' + ''.join(chips) + '</div>')
    for g in payload["gates"]:
        color = _GATE_COLORS.get(g.get("state"), "#94a3b8")
        h.append(f'<span class="td-gate" style="border-color:{color};color:{color}">'
                 f'<b>{_esc(str(g.get("state") or "").replace("_"," ").upper())}</b> {_esc(g.get("symbol"))} Â· {_esc(g.get("confirm_rule"))} '
                 f'(as of {_esc(g.get("stated"))})</span>')
    for i, card in enumerate(payload["cards"], 1):
        h.extend(_render_card(card, i, check_first=bool(card.get("card_blockers"))))
    backlog = payload["backlog"]
    h.append(f"<details><summary>Backlog ({len(backlog)})</summary>")
    for c in backlog:
        h.append(f'<div class="td-row">{_esc(c["ticker"])} Â· {_esc(c["direction"])} Â· '
                 f'${float(c.get("dollars") or 0):,.0f} Â· p{c.get("priority")}</div>')
    h.append("</details>")
    cong = payload["congruence"]
    if cong.get("status") == "ok":
        for row in cong.get("rows") or []:
            flag = "\U0001f6a9 " if row.get("flagged") else ""
            h.append(f'<div class="td-cong">{flag}{_esc(row["insight_id"])} Â· {_esc(row["line"])}</div>')
    else:
        h.append(f'<div class="td-cong">congruence: not checked â€” {_esc(cong.get("reason", ""))}</div>')
    # Volatility opportunity block (opt-in): LOUD staged command — leads with the sized move,
    # gate + funding + honesty visible; honest-empty never silent. Rendered only when this build
    # ran the converter (payload key present). Placed above options: the regime command is the
    # most decision-forward element when a volatility event is live.
    volatility_payload = payload.get("volatility")
    if volatility_payload is not None:
        h.append(voc.render_command_html(volatility_payload))
    # Options-expression block (opt-in): LOUD, leads with the sized move; honest-empty when checked
    # but nothing is actionable. Rendered only when this build screened options (payload key present).
    options_payload = payload.get("options")
    if options_payload is not None:
        h.append(opt_surface.render_options_block_html(options_payload))
    h.append('<div class="td-honesty">'
             + "<br/>".join(f"{_esc(k)}: {_esc(v)}" for k, v in payload["honesty"].items())
             + "</div>")
    h.append("</section>")
    return "\n".join(h)

def build_and_render(**kwargs: Any) -> str:
    return render_today_decide_html(build_today_decide_payload(**kwargs))
