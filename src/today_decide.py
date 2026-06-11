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

import congruence as cg
import directive_recs as dr
import insight_register as ir
import timing_engine as te
import disposition_log

SRC = Path(__file__).resolve().parent
FEED_PATH = SRC / "latest_cockpit_feed.json"

_GATE_COLORS = {"red": "#f87171", "red_but_tested": "#fbbf24", "green": "#34d399", "context": "#94a3b8"}
_CLASS_COLORS = {"OPEN-NOW": "#34d399", "STAGE-ONLY": "#fbbf24", "GATED": "#f87171", "WAIT": "#94a3b8"}

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
        card["recheck_date"] = recheck
        card["last_disposition"] = last.get(card["card_id"])
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
        "cards": stack["cards"],
        "backlog": stack["backlog"],
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
.td .td-gate{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;
  margin:0 6px 8px 0;border:1px solid}
.td .td-card{border:1px solid #1e293b;border-radius:10px;padding:12px;margin:10px 0;background:#0f172a}
.td .td-card.td-conflicted{border-color:#fb923c}
.td .td-move{font-size:16px;font-weight:600}
.td .td-pill{display:inline-block;border-radius:6px;padding:1px 8px;font-size:12px;
  font-weight:600;margin-left:8px;color:#0b1220}
.td .td-row{font-size:13px;color:#cbd5e1;margin:4px 0}
.td .td-chip{border:1px solid #fb923c;color:#fdba74;border-radius:8px;padding:6px 8px;
  font-size:12px;margin:6px 0}
.td details{margin:4px 0;font-size:12px;color:#94a3b8}
.td details.td-card{padding:0}
.td details.td-card>summary{list-style:none;cursor:pointer;padding:12px;display:block}
.td details.td-card>summary::-webkit-details-marker{display:none}
.td .td-chev{display:inline-block;font-size:11px;color:#64748b;margin:6px 0 0 2px}
.td details.td-card[open] .td-chev{color:#334155}
.td .td-body{padding:2px 12px 12px 12px;border-top:1px solid #1e293b;margin-top:10px;padding-top:8px}
.td .td-rail{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;
  padding:6px 12px;margin:6px 8px 0 0;cursor:pointer;font-size:13px}
.td .td-rail.td-on{background:#34d399;color:#0b1220;font-weight:700}
.td .td-cong{font-size:13px;margin:3px 0}
.td .td-honesty{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#94a3b8;
  border-top:1px solid #1e293b;margin-top:12px;padding-top:8px}
</style>
"""

_JS = """
<script>
function tdCopy(t){if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t);}
else{var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();
try{document.execCommand('copy');}catch(e){}document.body.removeChild(a);}}
function tdRail(btn){var on=btn.getAttribute('data-on')==='1';var id=btn.getAttribute('data-card');
var verb=btn.getAttribute('data-verb');
if(!on){tdCopy(btn.getAttribute('data-copy'));btn.setAttribute('data-on','1');
btn.classList.add('td-on');btn.textContent=verb+' \u2713 (tap to undo)';}
else{tdCopy('UNDO '+id);btn.setAttribute('data-on','0');btn.classList.remove('td-on');
btn.textContent=verb;}}
</script>
"""

def _esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _render_card(card: dict[str, Any], rank: int) -> list[str]:
    dcard = card.get("decision_card") or {}
    move = dcard.get("move") or {}
    conv = card.get("conviction") or {}
    win = card.get("window") or {}
    execn = card.get("execution") or {}
    impact = card.get("impact") or {}
    cid = _esc(card.get("card_id"))
    conflicted = " td-conflicted" if card.get("conflicts") else ""
    h = [f'<details class="td-card{conflicted}">', '<summary class="td-sum">']
    cls = win.get("class", "WAIT")
    h.append(
        f'<div class="td-move">#{rank} <span style="color:{ {"BUY": "#34d399", "SELL": "#f87171"}.get(str(move.get("direction")), "#e2e8f0") };font-weight:700">{_esc(move.get("direction"))}</span> {_esc(card.get("ticker"))}'
        f' Â· {_esc(move.get("band"))}'
        f'<span class="td-pill" style="background:{_CLASS_COLORS.get(cls, "#94a3b8")}">{_esc(cls)}</span>'
        f'<span class="td-pill" style="background:#818cf8">{_esc(conv.get("read"))} {conv.get("points", 0)}</span>'
        "</div>"
    )
    for c in card.get("conflicts") or []:
        h.append(f'<div class="td-chip">SOURCE-CONFLICT â€” {_esc(c["with"])}: â€œ{_esc(c["their_claim"])}â€ '
                 f'vs this card: {_esc(c["card_claim"])} Â· resolve before acting</div>')
    h.append(
        f'<button class="td-rail" data-card="{cid}" data-verb="ACT" data-copy="ACT {cid}" '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">ACT</button>'
        f'<button class="td-rail" data-card="{cid}" data-verb="PASS" data-copy="PASS {cid} â€” reason: " '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">PASS</button>'
        f'<button class="td-rail" data-card="{cid}" data-verb="RECHECK" '
        f'data-copy="RECHECK {cid} resurface {_esc(card.get("recheck_date"))}" '
        f'onclick="event.preventDefault();event.stopPropagation();tdRail(this)">RECHECK</button>'
    )
    h.append('<span class="td-chev">&#9656; details</span>')
    h.append('</summary><div class="td-body">')
    groups = conv.get("groups") or {}
    h.append('<div class="td-row">evidence: '
             + " Â· ".join(f"{_esc(k)} {v:+.2f}" for k, v in groups.items()) + "</div>")
    if win.get("named_trigger"):
        h.append(f'<div class="td-row">trigger: {_esc(win["named_trigger"])}'
                 + (f' Â· deadline {_esc(win.get("deadline"))}' if win.get("deadline") else "") + "</div>")
    for reason in (win.get("reasons") or [])[:2]:
        h.append(f'<div class="td-row">â€¢ {_esc(reason)}</div>')
    flips = win.get("flips") or []
    raises = conv.get("raises") or []
    if flips or raises:
        h.append("<details><summary>what changes this</summary>"
                 + "".join(f"<div>flip: {_esc(f)}</div>" for f in flips)
                 + "".join(f"<div>raise: {_esc(r)}</div>" for r in raises)
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
    if execn.get("transfer_note"):
        h.append(f'<div class="td-chip">TRANSFER NEEDED: {_esc(execn["transfer_note"])}</div>')
    if execn.get("cash"):
        h.append(f'<div class="td-row">cash: {_esc(execn["cash"])}</div>')
    h.append(f'<div class="td-row">impact: {_esc(impact.get("band"))} Â· material: '
             f'{"yes" if impact.get("material") else "no"}</div>')
    if card.get("last_disposition"):
        ld = card["last_disposition"]
        h.append(f'<div class="td-row">last disposition: {_esc(ld.get("verb"))} on {_esc(ld.get("et_date"))}</div>')
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
    for g in payload["gates"]:
        color = _GATE_COLORS.get(g.get("state"), "#94a3b8")
        h.append(f'<span class="td-gate" style="border-color:{color};color:{color}">'
                 f'<b>{_esc(str(g.get("state") or "").replace("_"," ").upper())}</b> {_esc(g.get("symbol"))} Â· {_esc(g.get("confirm_rule"))} '
                 f'(as of {_esc(g.get("stated"))})</span>')
    for i, card in enumerate(payload["cards"], 1):
        h.extend(_render_card(card, i))
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
    h.append('<div class="td-honesty">'
             + "<br/>".join(f"{_esc(k)}: {_esc(v)}" for k, v in payload["honesty"].items())
             + "</div>")
    h.append("</section>")
    return "\n".join(h)

def build_and_render(**kwargs: Any) -> str:
    return render_today_decide_html(build_today_decide_payload(**kwargs))
