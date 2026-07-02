"""
cockpit_html_gen.py — Conviction Cockpit static HTML generator.

Produces a self-contained docs/index.html from a build feed dict.
Pure Python stdlib — no external deps.

Usage (from src/, after STEP 5):
    from cockpit_html_gen import generate_html
    html = generate_html(feed)
    import os; os.makedirs("../docs", exist_ok=True)
    open("../docs/index.html", "w", encoding="utf-8").write(html)
"""
from __future__ import annotations
import argparse
import html as _html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import today_decide
from tunables import load_conviction_weights, load_goal_tunables


def _e(s: Any) -> str:
    """HTML-escape a value."""
    return _html.escape("" if s is None else str(s))


def _strip_trailing_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


ET = ZoneInfo("America/New_York")
DEFERRED_OPTIONAL_SOURCE_KEYS = {"social_watch"}
ACCOUNT_POSITIONS_PATH = Path(__file__).with_name("account_positions.json")
FUNDSTRAT_BIBLE_PATH = Path(__file__).with_name("fundstrat_bible.json")
HELD_DECISIONS_PATH = Path(__file__).with_name("held_decisions.json")


def _fmt_et_stamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ET).strftime("%Y-%m-%d %H:%M ET")
    except ValueError:
        return f"{text[:16].replace('T', ' ')} ET"


_DISPLAY_REPLACEMENTS = (
    ("Ã‚Â·", " | "),
    ("Â·", " | "),
    ("â€”", "-"),
    ("â€“", "-"),
    ("â†’", "->"),
    ("â€¦", "..."),
    ("Ã¢Å¡Â ", "!"),
    ("Ã¢Å¡â„¢", "#"),
)



def _compact_stamp(staleness: dict) -> str:
    """One-line source stamp: cluster sources sharing the newest/common date, amber the laggards."""
    entries = staleness.get("entries") or []
    if not entries:
        return _e(staleness.get("stamp") or "")
    abbrev = {"portfolio": "port", "uw_price": "px", "uw_macro": "macro",
              "fundstrat_bible": "FS bible", "fundstrat_daily": "FS daily"}
    from collections import Counter
    norm = lambda e: str(e.get("date") or "")[:10]
    dates = [norm(e) for e in entries if e.get("date")]
    if not dates:
        return _e(staleness.get("stamp") or "")
    core = Counter(dates).most_common(1)[0][0]
    md = lambda d: d[5:] if len(d) == 10 else d
    core_srcs = [_e(abbrev.get(str(e.get("source")), str(e.get("source"))))
                 for e in entries if norm(e) == core]
    out = [f'data {md(core)}: ' + "&middot;".join(core_srcs)]
    for e in entries:
        d = norm(e)
        if d == core or not d:
            continue
        name = _e(abbrev.get(str(e.get("source")), str(e.get("source"))))
        color = "#b08930" if d < core else "#7d8590"
        out.append(f'<span style="color:{color}">{name} {md(d)}</span>')
    return " &#9474; ".join(out)

def _ascii_display_safe(text: str) -> str:
    """Keep the generated export readable even if old symbols are mojibaked."""
    for old, new in _DISPLAY_REPLACEMENTS:
        text = text.replace(old, new)
    return "".join(ch if ord(ch) < 128 else "" for ch in text)


def _pct(v: Any) -> str:
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return str(v or "-")


def _rel(v: Any) -> str:
    try:
        f = float(v) * 100
        sign = "+" if f >= 0 else ""
        return f"{sign}{f:.1f}%"
    except Exception:
        return "-"


def _placement_tone(row: dict[str, Any] | None) -> str:
    status = str((row or {}).get("status") or "").lower()
    if status == "blocked":
        return "red"
    if status in {"needs_review", "not_checked"}:
        return "amber"
    if status == "candidate":
        return "green"
    return "gray"


def _action_tone(row: dict[str, Any]) -> str:
    refresh = row.get("assumption_refresh") or {}
    fresh = row.get("freshness_judgment") or {}
    refresh_status = str(refresh.get("status") or "").lower()
    fresh_label = str(fresh.get("label") or "").lower()
    if row.get("action_state") == "ACT_NOW" or row.get("decision_group") == "key_now":
        return "red"
    if (
        row.get("decision_group") == "recheck_before_acting"
        or refresh_status in {"changed_recheck", "stale", "invalidated"}
        or fresh_label in {"stale", "not checked", "fast-moving"}
    ):
        return "amber"
    if row.get("decision_group") == "important_backlog":
        return "blue"
    if (row.get("account_placement") or {}).get("status") == "candidate":
        return "green"
    return "gray"


def _packet_tone(row: dict[str, Any]) -> str:
    kind = str(row.get("kind") or "")
    refresh = str(row.get("refresh_status") or "")
    if kind == "gate_key_now":
        return "red"
    if kind in {"recheck_first", "positions_blocker", "dark_lane", "uw_check"} or refresh in {"changed_recheck", "stale", "invalidated"}:
        return "amber"
    if kind == "reallocation_review":
        return "green"
    if kind in {"important_backlog", "open_reviews"}:
        return "blue"
    return "gray"


REFRESH_STATUS_META = {
    "upgraded": {
        "label": "Checked: still urgent",
        "tone": "t-conf",
        "title": "The assumption-refresh pass kept this item prominent. It is not a trade command; run the relevant source, position, and pre-trade gate before capital moves.",
    },
    "changed_recheck": {
        "label": "Needs re-check",
        "tone": "t-warn",
        "title": "Something important is missing, old, or changed. Confirm same-session price, flow, position, source, or event-risk evidence before acting.",
    },
    "still_valid": {
        "label": "Still valid watch",
        "tone": "t-conf",
        "title": "Available feed evidence did not break this setup. Keep it visible, but use the normal gate before acting.",
    },
    "stale": {
        "label": "Stale: refresh first",
        "tone": "t-warn",
        "title": "The evidence has aged past its useful window. Refresh the source before treating this as actionable.",
    },
    "invalidated": {
        "label": "Invalidated: do not act",
        "tone": "t-red",
        "title": "Available evidence broke the setup. Do not act from this row unless it is rebuilt from fresh evidence.",
    },
}


def _refresh_status_badge(status: Any) -> str:
    if not status:
        return ""
    key = str(status).lower()
    meta = REFRESH_STATUS_META.get(key) or {
        "label": "Checked: " + str(status).replace("_", " "),
        "tone": "t-cat",
        "title": "Assumption-refresh status from the feed. It explains the row's current review posture; it does not execute or authorize a trade.",
    }
    return (
        f'<span class="tag {meta["tone"]}" title="{_e(meta["title"])}">'
        f'{_e(meta["label"])}</span>'
    )


def _freshness_title(row: dict[str, Any]) -> str:
    value = str(row.get("freshness_label") or "").lower()
    evidence = f' Evidence date: {row.get("evidence_date")}.' if row.get("evidence_date") else ""
    checked = f' Last checked: {row.get("last_checked")}.' if row.get("last_checked") else ""
    decay = f' Decay window: {row.get("decay_window")}.' if row.get("decay_window") else ""
    if value == "fresh":
        return f"Fresh enough to keep this decision prompt visible; still run the gate before capital moves.{evidence}{checked}{decay}"
    if value == "fast-moving":
        return f"Fast-moving evidence can go stale intraday. Re-check same-session levels/headlines before acting.{evidence}{checked}{decay}"
    if value == "stale":
        return f"Stale evidence. Refresh this source before treating the row as actionable.{evidence}{checked}{decay}"
    if value == "not checked":
        return f"This source was not checked. Do not infer all-clear from missing data.{evidence}{checked}{decay}"
    return f"Freshness context for this row.{evidence}{checked}{decay}"


def _freshness_badge(row: dict[str, Any]) -> str:
    if not (row.get("freshness_label") or row.get("evidence_date") or row.get("decay_window")):
        return ""
    fresh_cls = f"t-{_freshness_tone(row.get('freshness_label'))}"
    label = row.get("freshness_label") or "freshness"
    detail = (
        f' <span class="small-muted">Freshness: {_e(row.get("freshness_label") or "")}'
        f' | evidence {_e(row.get("evidence_date") or "n/a")}'
        f' | checked {_e(row.get("last_checked") or "n/a")}'
        f' | decays {_e(row.get("decay_window") or "source dependent")}</span>'
    )
    return (
        f'<span class="tag {fresh_cls}" title="{_e(_freshness_title(row))}">'
        f'{_e(label)}</span>{detail}'
    )


def _freshness_tone(label: Any) -> str:
    value = str(label or "").lower()
    if value in {"stale", "not checked"}:
        return "red"
    if value in {"fast-moving", "archive"}:
        return "amber"
    if value == "fresh":
        return "green"
    return "gray"


def _newest_first(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get("date") or row.get("evidence_date") or ""), reverse=True)


# ─── CSS ─────────────────────────────────────────────────────────────────────

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  background:#0d1117;color:#c9d1d9;font-size:14px;line-height:1.55;
}
a{color:#58a6ff;text-decoration:none}
.wrap{max-width:920px;margin:0 auto;padding:16px 14px}
.quick-nav{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.quick-link{display:inline-flex;align-items:center;gap:5px;background:#1c2128;
  border:1px solid #30363d;border-radius:6px;padding:5px 8px;
  font-size:11px;color:#c9d1d9}
.quick-link strong{color:#f0f6fc}

/* ── header ── */
.hdr{display:flex;align-items:flex-start;justify-content:space-between;
  flex-wrap:wrap;gap:8px;margin-bottom:14px}
.hdr-left h1{font-size:18px;font-weight:700;color:#f0f6fc;letter-spacing:-.3px}
.stamp{font-size:11px;color:#484f58;font-family:monospace;margin-top:3px}
.stale-warn{font-size:11px;color:#d29922;margin-top:3px}
.book-as-of{font-size:11px;color:#484f58;font-family:monospace}

/* ── section card ── */
.card{background:#161b22;border:1px solid #21262d;border-radius:8px;
  padding:12px 14px;margin-bottom:10px}
.tone-red{border-left:4px solid #f85149!important;background:#1f1518!important;border-color:#f8514955!important}
.tone-amber{border-left:4px solid #d29922!important;background:#1f1a12!important;border-color:#d2992255!important}
.tone-green{border-left:4px solid #3fb950!important;background:#111d16!important;border-color:#3fb95055!important}
.tone-blue{border-left:4px solid #58a6ff!important;background:#111923!important;border-color:#58a6ff55!important}
.tone-gray{border-left:4px solid #6e7681!important;background:#161b22!important;border-color:#30363d!important}
.card-title{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.9px;color:#8b949e;margin-bottom:9px;display:flex;
  align-items:center;gap:6px}
.card-title .icon{font-size:14px}
.card.is-collapsible>.card-title{cursor:pointer;margin-bottom:4px}
.card.is-collapsible>.card-title:before{content:"v";font-family:monospace;
  font-size:10px;color:#484f58;margin-right:2px}
.card.is-collapsible.is-collapsed>.card-title:before{content:">"}
.card.is-collapsible.is-collapsed>:not(.card-title):not(.card-mini){display:none}
.card.is-collapsible:not(.is-collapsed)>.card-mini{display:none}
.card-mini{font-size:12px;color:#8b949e;margin-top:4px;line-height:1.4;
  font-weight:400;text-transform:none;letter-spacing:0}

/* ── heartbeat strip ── */
.hb{display:flex;flex-wrap:wrap;gap:5px}
.hb-badge{padding:2px 9px;border-radius:99px;font-size:10px;
  font-family:monospace;white-space:nowrap}
.ok  {background:#0d2b16;color:#3fb950;border:1px solid #238636}
.stale{background:#2b1e0a;color:#d29922;border:1px solid #9e6a03}
.down{background:#2b0d0d;color:#f85149;border:1px solid #da3633}

/* held decisions strip */
.held-strip{border-color:#d2992255;background:#1f1a11}
.held-title-badge{margin-left:auto;border:1px solid #8b6f2f;border-radius:999px;
  padding:1px 7px;color:#f2cc60;background:#3b2c12;font-family:monospace}
.held-row{display:flex;gap:10px;align-items:flex-start;justify-content:space-between;
  border-left:4px solid #484f58;background:#0d1117;border-radius:7px;
  padding:9px 10px;margin-top:7px}
.held-main{min-width:0}
.held-main a{color:#c9d1d9;font-weight:700}
.held-main a:hover{color:#58a6ff}
.held-meta{font-size:11px;color:#8b949e;margin-top:3px}
.held-date{white-space:nowrap;font-size:11px;font-family:monospace}
.held-green{border-left-color:#238636}
.held-green .held-date{color:#7ee787}
.held-amber{border-left-color:#d29922}
.held-amber .held-date{color:#f2cc60}
.held-red{border-left-color:#da3633}
.held-red .held-date{color:#ff7b72}
.held-warning{border-color:#d2992255;background:#3b2c121f}
.feeder-drilldowns{background:#111923;border:1px solid #30363d;border-left:4px solid #58a6ff;
  border-radius:8px;padding:10px 12px;margin-bottom:10px}
.feeder-drilldowns>summary{cursor:pointer;color:#f0f6fc;font-size:12px;font-weight:800}
.feeder-drilldowns .summary-muted{margin-top:5px;margin-bottom:8px}
.feeder-drilldowns .card{margin-top:8px;margin-bottom:8px}

/* summary/export honesty */
.summary-caveat{border-left:3px solid #d29922}
.summary-line{font-size:12px;color:#c9d1d9;margin-bottom:5px}
.summary-line:last-child{margin-bottom:0}
.summary-muted{color:#8b949e}
.lane-counts{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.lane-row{display:flex;align-items:center;gap:8px;font-size:12px;flex-wrap:wrap;
  padding:5px 0;border-bottom:1px solid #1c2128}
.lane-row:last-child{border-bottom:none}
.lane-key{font-weight:700;color:#c9d1d9;min-width:130px}
.lane-status{font-family:monospace;font-size:10px;padding:1px 7px;border-radius:99px}
.lane-command-list{flex:1 0 100%;display:flex;flex-direction:column;gap:4px;margin-left:138px}
.ls-has_data{background:#0d2b16;color:#3fb950}
.ls-checked_clear{background:#1c2128;color:#8b949e}
.ls-not_checked{background:#2b1e0a;color:#d29922}
.ls-stale,.ls-failed{background:#2b0d0d;color:#f85149}
.feedback-line{font-size:12px;color:#8b949e;margin:5px 0}
.feedback-rec{font-size:12px;color:#c9d1d9;padding:4px 0;border-top:1px solid #1c2128}
.feedback-item{font-size:12px;color:#c9d1d9;padding:4px 0 4px 8px;border-left:2px solid #d29922;margin:5px 0;background:#1c2128}
.operator-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-bottom:8px}
.operator-pill{background:#1c2128;border:1px solid #21262d;border-radius:6px;padding:7px 8px;display:block;color:inherit}
.operator-pill:hover{border-color:#58a6ff;background:#20262e}
.operator-label{font-size:9px;text-transform:uppercase;letter-spacing:.6px;color:#484f58;margin-bottom:2px}
.operator-value{font-size:13px;font-weight:700;color:#f0f6fc}
.operator-pass{color:#3fb950}.operator-warn{color:#d29922}.operator-fail{color:#f85149}
.operator-command{font-family:monospace;font-size:11px;color:#8b949e;background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:6px 8px;overflow-x:auto}
.operator-readiness{font-size:11px;color:#8b949e;background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:7px 8px;margin-bottom:8px}
.operator-readiness strong{font-size:12px}
.operator-event-watch{background:#2b1e0a;border:1px solid #d2992244;border-radius:6px;padding:7px 8px;margin:7px 0}
.operator-event-title{font-size:12px;font-weight:700;color:#f0f6fc}
.operator-event-meta{font-family:monospace;font-size:10px;color:#8b949e;margin-top:3px}
.operator-event-trigger{font-size:11px;color:#8b949e;margin-top:4px}
.context-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}
.context-col{background:#1c2128;border:1px solid #21262d;border-radius:6px;padding:8px}
.context-label{font-size:9px;text-transform:uppercase;letter-spacing:.6px;color:#484f58;margin-bottom:6px}
.context-row{font-size:12px;color:#c9d1d9;padding:5px 0;border-top:1px solid #30363d}
.context-row:first-of-type{border-top:none;padding-top:0}
.context-ticker{font-family:monospace;font-weight:700;color:#f0f6fc;margin-right:5px}
.context-sub{display:block;color:#8b949e;font-size:11px;margin-top:2px}

/* ── needs-you hero ── */
.hero{background:#161b22;border:1px solid #21262d;border-radius:8px;
  padding:12px 14px;margin-bottom:10px;
  border-left:3px solid #d29922}
.hero-row{display:flex;align-items:center;gap:10px}
.hero-num{font-size:32px;font-weight:800;color:#d29922;min-width:40px}
.hero-label{font-size:11px;color:#8b949e;margin-top:2px}
.hero-items{margin-top:8px;display:flex;flex-direction:column;gap:5px}
.hero-item{font-size:12px;color:#c9d1d9;padding:5px 8px;
  background:#1c2128;border-radius:5px;
  border-left:2px solid #d29922}

/* ── actions ── */
.action{border-radius:6px;padding:11px 12px;margin-bottom:8px;
  background:#1c2128;border:1px solid #30363d;border-left:4px solid #30363d}
.action-act{border-left-color:#d29922;background:#1d2026}
.action-watch{border-left-color:#58a6ff}
.action-header{display:grid;grid-template-columns:auto minmax(70px,max-content) 1fr;
  align-items:start;gap:7px;margin-bottom:6px}
.rank-badge{font-size:10px;font-family:monospace;color:#484f58;
  min-width:22px}
.ticker-tag{font-size:14px;font-weight:700;color:#f0f6fc}
.action-what{font-size:13px;color:#f0f6fc;font-weight:600}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}
.tag{display:inline-block;padding:1px 7px;border-radius:99px;
  font-size:10px;font-family:monospace}
.t-cat   {background:#0d2339;color:#58a6ff}
.t-conf  {background:#0d2b16;color:#3fb950}
.t-warn  {background:#2b1e0a;color:#d29922}
.t-red   {background:#2b0d0d;color:#f85149}
.t-amber {background:#2b1e0a;color:#d29922}
.t-green {background:#0d2b16;color:#3fb950}
.t-blue  {background:#0d2339;color:#58a6ff}
.t-gray  {background:#1c2128;color:#8b949e}
.t-gate-g{background:#0d2b16;color:#3fb950}
.t-gate-a{background:#2b1e0a;color:#d29922}
.t-gate-r{background:#2b0d0d;color:#f85149}
.action-move{font-size:12px;color:#c9d1d9;line-height:1.45;margin-top:5px}
.action-why{font-size:11px;color:#8b949e;line-height:1.4;margin-top:6px;
  padding-top:6px;border-top:1px solid #30363d}
.action-foot{font-size:10px;color:#484f58;font-family:monospace;margin-top:6px}
.action-group{margin-bottom:10px}
.action-group-title{font-size:11px;font-weight:700;color:#f0f6fc;margin:2px 0 7px;
  display:flex;align-items:center;gap:6px}
.action-group-title span{font-family:monospace;font-size:10px;color:#8b949e;font-weight:400}
.action-details{margin-top:7px;border-top:1px solid #30363d;padding-top:6px}
.action-details summary{cursor:pointer;color:#58a6ff;font-size:11px;list-style:none}
.action-details summary::-webkit-details-marker{display:none}
.action-detail-body{font-size:11px;color:#8b949e;line-height:1.45;margin-top:6px}
.audit-row{font-size:12px;color:#c9d1d9;padding:5px 0;border-top:1px solid #1c2128}
.audit-row:first-of-type{border-top:none}
.audit-k{font-family:monospace;color:#f0f6fc;font-weight:700;margin-right:6px}
.small-list{display:flex;flex-direction:column;gap:5px}
.small-item{font-size:12px;color:#c9d1d9;background:#1c2128;border:1px solid #21262d;border-radius:6px;padding:7px 8px}
.small-muted{display:block;color:#8b949e;font-size:11px;margin-top:2px}

/* ── rotation table ── */
.rot-wrap{overflow-x:auto}
table.rot{width:100%;border-collapse:collapse;font-size:12px}
.rot th{color:#484f58;font-weight:600;padding:4px 8px;
  text-align:left;border-bottom:1px solid #21262d}
.rot td{padding:5px 8px;border-bottom:1px solid #1c2128;
  font-family:monospace}
.rot td:first-child{font-family:-apple-system,sans-serif;
  font-weight:600;color:#c9d1d9}
.lead{color:#3fb950}.lag{color:#f85149}.inl{color:#8b949e}

/* ── macro ── */
.macro-line{font-family:monospace;font-size:12px;color:#8b949e}
.regime-tag{display:inline-block;padding:2px 8px;border-radius:99px;
  font-size:10px;font-family:monospace;background:#161b22;
  border:1px solid #21262d;color:#8b949e;margin-top:5px}

/* ── synthesis ── */
.s-label{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.6px;color:#484f58;margin-top:10px;margin-bottom:3px}
.s-label:first-of-type{margin-top:0}
.s-body{font-size:13px;color:#c9d1d9}
.hang-list{list-style:none;margin-top:6px}
.hang-list li{font-size:12px;color:#8b949e;padding:4px 0;
  border-bottom:1px solid #1c2128}
.hang-list li:last-child{border-bottom:none}
.hang-list li::before{content:"⚠ ";color:#d29922;font-size:10px}

/* ── catalysts ── */
.cat-list{display:flex;flex-direction:column;gap:6px}
.cat-item{display:flex;align-items:center;gap:10px;font-size:12px;
  padding:5px 8px;background:#1c2128;border-radius:5px}
.cat-days{font-family:monospace;font-weight:700;color:#d29922;min-width:30px}
.cat-ticker{font-weight:700;color:#f0f6fc;min-width:40px}
.cat-label{color:#8b949e}

/* ── research pending ── */
.res-list{display:flex;flex-direction:column;gap:4px}
.res-item{display:flex;align-items:flex-start;gap:8px;font-size:12px;
  color:#8b949e;padding:4px 0;border-bottom:1px solid #1c2128}
.res-item:last-child{border-bottom:none}
.pr{font-family:monospace;font-size:10px;min-width:22px;
  padding:1px 5px;border-radius:3px;text-align:center}
.pr-h{background:#2b0d0d;color:#f85149}
.pr-m{background:#2b1e0a;color:#d29922}
.pr-l{background:#1c2128;color:#484f58}

/* ── book ── */
.book-wrap{overflow-x:auto}
table.book{width:100%;border-collapse:collapse;font-size:12px}
.book th{color:#484f58;font-weight:600;padding:4px 8px;
  text-align:left;border-bottom:1px solid #21262d}
.book td{padding:4px 8px;border-bottom:1px solid #1c2128}
.book-cat-row td{background:#161b22;color:#8b949e;font-size:10px;
  font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  padding:6px 8px 3px}
.book td:nth-child(2){font-family:monospace;color:#8b949e}
.book td:nth-child(3){color:#8b949e;font-size:11px}
.cv-yes{color:#3fb950}
.lock-tag{font-size:10px;color:#d29922;margin-left:3px}
.tab-badge{display:inline-block;margin-left:5px;padding:1px 5px;border-radius:999px;
  background:#3a2510;color:#d29922;font-size:10px;font-weight:700}
.hold-kpis{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.hold-kpi{background:#0d1117;border:1px solid #21262d;border-radius:7px;padding:7px 9px;
  font-size:11px;color:#8b949e}
.hold-kpi strong{display:block;color:#f0f6fc;font-size:14px;font-family:monospace}
.hold-flag{display:inline-block;border-radius:999px;padding:2px 7px;font-size:10px;
  font-weight:700;background:#0f2a1a;color:#3fb950;border:1px solid #2ea04355}
.hold-flag.untracked{background:#2b1e0a;color:#d29922;border-color:#d2992255}
.hold-stale{border:1px solid #d2992255;background:#2b1e0a;color:#d29922;
  border-radius:7px;padding:7px 9px;margin:8px 0;font-size:12px}
.holding-drill summary{cursor:pointer;color:#58a6ff;font-size:11px}
.holding-drill table{margin-top:6px}

/* ── lean-in ── */
.lean-item{padding:8px 0;border-bottom:1px solid #1c2128;font-size:12px}
.lean-item:last-child{border-bottom:none}
.lean-ticker{font-weight:700;color:#f0f6fc}
.lean-headline{color:#c9d1d9;margin:2px 0}
.lean-sub{color:#8b949e;font-size:11px}

/* ── footer ── */
.footer{text-align:center;font-size:10px;color:#30363d;
  margin-top:20px;padding:16px;border-top:1px solid #21262d}


/* ── tabs ── */
.tab-bar{display:flex;gap:2px;margin-bottom:12px;border-bottom:1px solid #21262d;padding-bottom:0;
  max-width:100%;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.tab-bar::-webkit-scrollbar{display:none}
.tab-btn{padding:7px 14px;font-size:12px;font-weight:600;color:#8b949e;background:none;border:none;
  border-bottom:2px solid transparent;cursor:pointer;margin-bottom:-1px;letter-spacing:.3px;flex:0 0 auto}
.tab-btn.active{color:#f0f6fc;border-bottom-color:#58a6ff}
/* ── commands panel ── */
.cmd-section{margin-bottom:16px}
.cmd-section-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.9px;
  color:#8b949e;margin-bottom:8px}
.cmd-row{display:flex;align-items:flex-start;gap:10px;padding:6px 0;
  border-bottom:1px solid #1c2128;font-size:12px}
.cmd-row:last-child{border-bottom:none}
.cmd-name{font-family:monospace;color:#58a6ff;min-width:110px;font-size:11px;flex-shrink:0}
.cmd-desc{color:#8b949e;line-height:1.4}
.nav-row{display:flex;align-items:center;gap:8px;padding:5px 0;
  border-bottom:1px solid #1c2128;font-size:12px}
.nav-row:last-child{border-bottom:none}
.nav-label{color:#c9d1d9;min-width:140px;flex-shrink:0}
.nav-hint{font-size:10px;color:#484f58;font-family:monospace;margin-left:4px}

/* ── responsive ── */
@media(max-width:600px){
  .wrap{padding:10px 8px}
  .hdr{flex-direction:column}
  .tab-bar{flex-wrap:wrap;overflow-x:visible;gap:4px}
  .tab-btn{padding:7px 10px}
  .hero-num{font-size:24px}
  .lane-command-list{margin-left:0}
}
@media(min-width:720px){
  .two-col{display:grid;grid-template-columns:1fr 1fr;gap:10px}
}
"""


# ─── Section builders ─────────────────────────────────────────────────────────

def _heartbeat(hb: list) -> str:
    if not hb:
        return ""
    badges = ""
    for layer in hb:
        st = (layer.get("status") or "down").lower()
        cls = {"ok": "ok", "stale": "stale"}.get(st, "down")
        name = _e(layer.get("layer", ""))
        note = _e(layer.get("note") or "")
        last = _e(layer.get("last_run") or "-")
        title = f"{name} | {last}" + (f" | {note}" if note else "")
        badges += f'<span class="hb-badge {cls}" title="{title}">{name}</span>'
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">📡</span> System layers</div>
  <div class="hb">{badges}</div>
</div>"""


def _operator_date(now: Any = None) -> datetime.date:
    if now is None:
        return datetime.now(ET).date()
    if isinstance(now, datetime):
        parsed = now
    else:
        text = str(now).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(ET).date()


def _held_review_tone(review_by: Any, today: datetime.date) -> str:
    try:
        review_date = datetime.fromisoformat(str(review_by or "")[:10]).date()
    except ValueError:
        return "red"
    if review_date > today:
        return "green"
    if review_date == today:
        return "amber"
    return "red"


def _held_decisions_strip(path: str | Path | None = None, *, now: Any = None) -> str:
    path = HELD_DECISIONS_PATH if path is None else Path(path)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list):
            raise ValueError("held decisions must be a list")
    except Exception:
        return """
<div class="card held-warning" id="held-decisions">
  <div class="feedback-line">held decisions: not checked</div>
</div>"""

    rows = [
        row for row in payload
        if isinstance(row, dict) and str(row.get("status") or "") in {"held", "reparked"}
    ]
    if not rows:
        return ""
    today = _operator_date(now)
    rows.sort(key=lambda row: (str(row.get("review_by") or ""), str(row.get("title") or "")))
    rendered = []
    for row in rows:
        tone = _held_review_tone(row.get("review_by"), today)
        title = _e(row.get("title") or row.get("id") or "held decision")
        url = _e(row.get("notion_url") or "#")
        review_by = _e(row.get("review_by") or "unknown")
        parked = _e(row.get("parked_date") or "unknown")
        status = _e(row.get("status") or "held")
        rendered.append(f"""
  <div class="held-row held-{tone}">
    <div class="held-main">
      <a href="{url}">{title}</a>
      <div class="held-meta">parked {parked} | status {status}</div>
    </div>
    <div class="held-date">review {review_by}</div>
  </div>""")
    return f"""
<div class="card held-strip" id="held-decisions">
  <div class="card-title"><span class="icon">&#9203;</span> Held for you
    <span class="held-title-badge">{len(rows)}</span>
  </div>
{''.join(rendered)}
</div>"""


def _summary_notice(feed: dict) -> str:
    lane = feed.get("lane_status") or {}
    counts = lane.get("counts") or {}
    rows = [row for row in (lane.get("rows") or []) if isinstance(row, dict)]
    dark_rows = [row for row in rows if row.get("status") == "not_checked"]
    deferred_dark = sum(
        1 for row in dark_rows
        if row.get("key") in DEFERRED_OPTIONAL_SOURCE_KEYS
    )
    dark = sum(
        1 for row in dark_rows
        if row.get("key") not in DEFERRED_OPTIONAL_SOURCE_KEYS
    )
    stale = int(counts.get("stale") or 0)
    failed = int(counts.get("failed") or 0)
    actions = feed.get("actions") or []
    lines = [
        "Action-first dashboard view. JSX remains available for internal validation, but today's decisions are surfaced here.",
    ]
    if not actions:
        lines.append("No Today's Actions are shown in this summary export.")
    if dark or stale or failed:
        parts = []
        if dark:
            parts.append(f"{dark} dark/not-checked lane{'s' if dark != 1 else ''}")
        if stale:
            parts.append(f"{stale} stale lane{'s' if stale != 1 else ''}")
        if failed:
            parts.append(f"{failed} failed lane{'s' if failed != 1 else ''}")
        lines.append("; ".join(parts) + " means this is not an all-clear read.")
        if deferred_dark:
            lines.append(
                f"{deferred_dark} deferred optional lane{'s' if deferred_dark != 1 else ''} "
                f"also {'remain' if deferred_dark != 1 else 'remains'} visible as not checked."
            )
    elif deferred_dark:
        lines.append(
            f"Core source lanes are clear; {deferred_dark} queued optional lane"
            f"{'s' if deferred_dark != 1 else ''} "
            f"{'remain' if deferred_dark != 1 else 'remains'} visible as not checked."
        )
    else:
        lines.append("No dark, stale, or failed lanes reported in the feed lane-status block.")
    body = "".join(f'<div class="summary-line">{_e(line)}</div>' for line in lines)
    return f"""
<div class="card summary-caveat">
  <div class="card-title"><span class="icon">âš </span> Summary/export caveat</div>
  {body}
</div>"""


def _quick_nav(feed: dict) -> str:
    lane = feed.get("lane_status") or {}
    counts = lane.get("counts") or {}
    lane_rows = [row for row in (lane.get("rows") or []) if isinstance(row, dict)]
    dark_rows = [row for row in lane_rows if row.get("status") == "not_checked"]
    deferred_dark = sum(
        1 for row in dark_rows
        if row.get("key") in DEFERRED_OPTIONAL_SOURCE_KEYS
    )
    actionable_dark = sum(
        1 for row in dark_rows
        if row.get("key") not in DEFERRED_OPTIONAL_SOURCE_KEYS
    )
    feedback = feed.get("feedback") or {}
    open_actions = (feedback.get("open_actions") or {}).get("count") or 0
    source_calls = feedback.get("source_calls") or {}
    source_call_pending = source_calls.get("pending_count") or 0
    source_call_overdue = source_calls.get("overdue_count") or 0
    lane_gaps = actionable_dark + int(counts.get("stale") or 0) + int(counts.get("failed") or 0)
    lane_label = f"{lane_gaps} gaps" if lane_gaps else (
        f"{deferred_dark} deferred" if deferred_dark else "green"
    )
    source_label = (
        f"{source_call_overdue} overdue"
        if source_call_overdue
        else f"{source_call_pending} scoring"
        if source_call_pending
        else "clear"
    )
    uw_proof = feed.get("uw_endpoint_proof") or {}
    uw_proof_label = "proof" if uw_proof.get("status") == "has_data" else "no proof"
    return f"""
<div class="quick-nav">
  <a class="quick-link" href="#today-actions"><strong>{len(feed.get("actions") or [])}</strong> actions</a>
  <a class="quick-link" href="#market-open-packet"><strong>open</strong> packet</a>
  <a class="quick-link" href="#opportunity-context"><strong>top</strong> prospects</a>
  <a class="quick-link" href="#asymmetric-opportunities"><strong>{_e((feed.get("asymmetric_opportunities") or {}).get("count") or 0)}</strong> asymmetry</a>
  <a class="quick-link" href="#reallocation-brief"><strong>realloc</strong> brief</a>
  <a class="quick-link" href="#operator-status"><strong>status</strong> check</a>
  <a class="quick-link" href="#uw-action-runbook"><strong>UW</strong> runbook</a>
  <a class="quick-link" href="#source-audits"><strong>{_e(uw_proof_label)}</strong> UW results</a>
  <a class="quick-link" href="#feedback-loops"><strong>{_e(open_actions)}</strong> open reviews</a>
  <a class="quick-link" href="#operator-hardening"><strong>hardening</strong> checks</a>
  <a class="quick-link" href="#lane-status"><strong>{_e(lane_label)}</strong> source lanes</a>
  <a class="quick-link" href="#feedback-loops"><strong>{_e(source_label)}</strong> source calls</a>
  <a class="quick-link" href="#source-audits"><strong>audit</strong> proof</a>
  <a class="quick-link" href="#social-watch"><strong>{_e((feed.get("social_watch") or {}).get("count") or 0)}</strong> social dark</a>
</div>"""


def _lane_intake_commands(key: str) -> list[tuple[str, str]]:
    if key in {"account_positions", "meridian"}:
        return [
            ("template", "docs/manual_live_source_drop.template.json (shape only; fill a separate drop file)"),
            ("validate", "python src/manual_source_drop.py manual-live-source-drop.json --src-dir src --validate-only"),
            ("apply", "python src/manual_source_drop.py manual-live-source-drop.json --src-dir src"),
        ]
    if key == "social_watch":
        return [
            ("cache", "write normalized cache to src/social_watch.json"),
            ("preview", "python src/social_watch.py --cache src/social_watch.json --format text"),
            ("refresh", "python src/live_dashboard_refresh.py"),
        ]
    return [
        ("validate", "python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only"),
        ("apply", "python src/manual_source_drop.py <manual-drop.json> --src-dir src"),
    ]


def _lane_status_summary(lane_status: dict) -> str:
    rows = lane_status.get("rows") or []
    if not rows:
        return ""
    counts = lane_status.get("counts") or {}
    count_badges = ""
    for key, label in (
        ("has_data", "has data"),
        ("checked_clear", "checked clear"),
        ("not_checked", "not checked"),
        ("stale", "stale"),
        ("failed", "failed"),
    ):
        count_badges += f'<span class="lane-status ls-{key}">{_e(label)}: {_e(counts.get(key, 0))}</span>'
    priority = {"failed": 0, "stale": 1, "not_checked": 2, "has_data": 3, "checked_clear": 4}
    ordered = sorted(
        [r for r in rows if isinstance(r, dict)],
        key=lambda r: (priority.get(r.get("status"), 9), r.get("label") or r.get("key") or ""),
    )
    visible = ordered[:10]
    row_html = ""
    for r in visible:
        status = r.get("status") or "not_checked"
        label = r.get("label") or r.get("key") or ""
        detail = r.get("detail") or ""
        next_step = r.get("next_step") or ""
        count = r.get("count") or 0
        count_txt = f" ({count})" if count else ""
        detail_txt = f"{detail}{count_txt}"
        if next_step:
            detail_txt = f"{detail_txt} | next: {next_step}"
        command_html = ""
        if status in {"not_checked", "stale", "failed"}:
            for action, command in _lane_intake_commands(str(r.get("key") or "")):
                command_html += (
                    f'<div class="operator-command">{_e(label)} {_e(action)}: '
                    f'{_e(command)}</div>'
                )
            if command_html:
                command_html = f'<div class="lane-command-list">{command_html}</div>'
        row_html += f"""
<div class="lane-row">
  <span class="lane-key">{_e(label)}</span>
  <span class="lane-status ls-{_e(status)}">{_e(status.replace("_", " "))}</span>
  <span class="summary-muted">{_e(detail_txt)}</span>
  {command_html}
</div>"""
    more = len(ordered) - len(visible)
    more_html = f'<div class="feedback-line">+{more} more lane rows available in dashboard drilldowns.</div>' if more > 0 else ""
    return f"""
<div class="card" id="lane-status">
  <div class="card-title"><span class="icon">âš™</span> Lane status</div>
  <div class="lane-counts">{count_badges}</div>
  {row_html}
  {more_html}
</div>"""


def _feedback_summary(feedback: dict) -> str:
    if not feedback:
        return ""
    sc = feedback.get("source_calls") or {}
    oa = feedback.get("open_actions") or {}
    cal = sc.get("calibration") or {}
    persistence = sc.get("persistence") or {}
    recs = feedback.get("recommendations") or []
    lines = []
    for line in (
        sc.get("line"),
        cal.get("line"),
        persistence.get("line"),
        oa.get("line"),
    ):
        if line:
            lines.append(f'<div class="feedback-line">{_e(line)}</div>')
    if recs:
        lines.extend(f'<div class="feedback-rec">{_e(r)}</div>' for r in recs[:4])
    for item in (oa.get("items") or [])[:4]:
        ticker = _e(item.get("ticker") or "")
        age = item.get("age_days")
        source = _e(item.get("source") or item.get("kind") or "")
        move = _e(item.get("move_since") or "")
        review_label = _e(item.get("review_label") or "")
        priority = _e(item.get("cleanup_priority") or "")
        next_step = _e(item.get("next_step") or "")
        detail = f"{age}d open" if age is not None else "open"
        if review_label:
            detail += f" | {review_label}"
        if priority and priority != "low":
            detail += f" | {priority} priority"
        if source:
            detail += f" | {source}"
        if move:
            detail += f" | {move}"
        command = (
            f'python src/action_memory_resolve.py --ticker {ticker} '
            f'--status deferred --reason "keep watching"'
        )
        next_step_html = f'<span class="context-sub">{next_step}</span>' if next_step else ""
        lines.append(
            f'<div class="feedback-item"><span class="context-ticker">{ticker}</span>{_e(detail)}'
            f'{next_step_html}'
            f'<span class="context-sub">{_e(command)}</span></div>'
        )
    if not lines:
        return ""
    badge = (
        int(sc.get("overdue_count") or 0)
        + int((persistence or {}).get("loud_count") or 0)
        + int((persistence or {}).get("provisional_count") or 0)
        + int(oa.get("count") or 0)
    )
    return f"""
<div class="card" id="feedback-loops">
  <div class="card-title"><span class="icon">ðŸ”</span> Feedback loops
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{badge} open signal(s)</span>
  </div>
  {''.join(lines)}
</div>"""


def _operator_status(feed: dict) -> str:
    lane = feed.get("lane_status") or {}
    counts = lane.get("counts") or {}
    lane_rows = [row for row in (lane.get("rows") or []) if isinstance(row, dict)]
    dark_rows = [row for row in lane_rows if row.get("status") == "not_checked"]
    deferred_dark_rows = [
        row for row in dark_rows
        if row.get("key") in DEFERRED_OPTIONAL_SOURCE_KEYS
    ]
    actionable_dark_rows = [
        row for row in dark_rows
        if row.get("key") not in DEFERRED_OPTIONAL_SOURCE_KEYS
    ]
    feedback = feed.get("feedback") or {}
    open_actions = feedback.get("open_actions") or {}
    source_calls = feedback.get("source_calls") or {}
    actions = feed.get("actions") or []
    dark = len(actionable_dark_rows)
    deferred_dark = len(deferred_dark_rows)
    stale = int(counts.get("stale") or 0)
    failed = int(counts.get("failed") or 0)
    open_count = int(open_actions.get("count") or 0)
    open_due = int(open_actions.get("due_count") or 0)
    open_stale = int(open_actions.get("stale_count") or 0)
    open_review_pressure = open_due + open_stale
    source_call_status = source_calls.get("status") or "not_checked"
    source_call_observed = int(source_calls.get("observed_count") or 0)
    source_call_pending = int(source_calls.get("pending_count") or 0)
    source_call_overdue = int(source_calls.get("overdue_count") or 0)
    live_config = feed.get("live_source_config") or {}
    live_config_missing = int(live_config.get("missing_count") or 0)
    live_config_total = int(live_config.get("total_count") or 0)
    live_configured = int(live_config.get("configured_count") or 0)
    source_call_warn = source_call_status == "not_checked" and source_call_observed > 0
    source_call_fail = source_call_overdue > 0
    audits = feed.get("source_audits") or {}
    cloud = audits.get("cloud_routines") or {}
    cloud_expected = int(cloud.get("expected_count") or 0)
    cloud_scheduled = int(cloud.get("scheduled_success_count") or 0)
    cloud_failed = int(cloud.get("failed_latest_count") or 0)
    cloud_overdue = int(cloud.get("overdue_count") or 0)
    cloud_manual_support = int(cloud.get("manual_support_only_count") or 0)
    schedule_wait = bool(cloud_expected and cloud_scheduled < cloud_expected and not cloud_failed and not cloud_overdue)
    if source_call_fail:
        source_call_value = f"{source_call_overdue} overdue"
    elif source_call_warn:
        source_call_value = f"{source_call_observed} unscored"
    elif source_call_pending:
        source_call_value = f"{source_call_pending} scoring"
    else:
        source_call_value = "clear"
    action_count = len(actions)
    event_rows = [
        row for row in (feed.get("event_risk") or [])
        if isinstance(row, dict) and row.get("title")
    ]
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    event_rows.sort(key=lambda row: severity_rank.get(str(row.get("severity") or "").lower(), 9))
    event_watch = event_rows[0] if event_rows else {}
    event_watch_html = ""
    if event_watch:
        channels = ", ".join(str(v) for v in (event_watch.get("channels") or []) if v)
        tickers = ", ".join(str(v) for v in (event_watch.get("tickers") or []) if v)
        meta = " | ".join(
            part for part in [
                str(event_watch.get("severity") or "watch").upper(),
                channels,
                tickers,
            ] if part
        )
        trigger = event_watch.get("trigger") or event_watch.get("summary") or ""
        compact_meta = " | ".join(part for part in [meta, f"trigger: {trigger}" if trigger else ""] if part)
        details_html = ""
        if trigger or event_watch.get("summary"):
            details_html = f"""
    <details class="action-details">
      <summary>details</summary>
      {f'<div class="operator-event-trigger">Trigger: {_e(trigger)}</div>' if trigger else ""}
      {f'<div class="operator-event-trigger">Source note: {_e(event_watch.get("summary") or "")}</div>' if event_watch.get("summary") else ""}
    </details>"""
        event_watch_html = f"""
  <div class="operator-event-watch">
    <div class="operator-label">Active event watch</div>
    <div class="operator-event-title">{_e(event_watch.get("title") or "")}</div>
    <div class="operator-event-meta">{_e(compact_meta)}</div>
    {details_html}
  </div>"""
    live_config_html = ""
    if live_config_missing:
        missing = [
            row for row in live_config.get("missing") or []
            if isinstance(row, dict)
        ]
        lines = []
        for row in missing[:3]:
            label = row.get("label") or row.get("key") or "Live source"
            impact = row.get("impact") or "live source fetch is not configured"
            lines.append(f"{label}: {impact}")
        live_config_html = f"""
  <div class="operator-event-watch">
    <div class="operator-label">Live source configuration</div>
    <div class="operator-event-title">{_e(live_config_missing)} missing live-fetch setting{'' if live_config_missing == 1 else 's'}</div>
    <div class="operator-event-trigger">{_e('; '.join(lines))}</div>
  </div>"""
    cloud_overdue_html = ""
    if cloud_overdue:
        overdue_rows = [
            row for row in cloud.get("overdue") or []
            if isinstance(row, dict)
        ]
        lines = []
        for row in overdue_rows[:3]:
            label = row.get("routine_name") or row.get("routine_id") or "Cloud routine"
            line = row.get("overdue_line") or (
                f"overdue: {label}, last scheduled success "
                f"{row.get('last_scheduled_success_label') or row.get('last_ran_label') or 'never'}"
            )
            lines.append(line)
        cloud_overdue_html = f"""
  <div class="operator-event-watch">
    <div class="operator-label">Cloud routine overdue</div>
    <div class="operator-event-title">{_e(cloud_overdue)} routine receipt{'' if cloud_overdue == 1 else 's'} overdue</div>
    <div class="operator-event-trigger">{_e('; '.join(lines))}</div>
  </div>"""
    cloud_manual_html = ""
    if cloud_manual_support:
        manual_rows = [
            row for row in cloud.get("manual_support_only") or []
            if isinstance(row, dict)
        ]
        names = ", ".join(
            str(row.get("routine_name") or row.get("routine_id") or "Cloud routine")
            for row in manual_rows[:3]
        )
        if len(manual_rows) > 3:
            names += f"; +{len(manual_rows) - 3} more"
        cloud_manual_html = f"""
  <div class="operator-event-watch">
    <div class="operator-label">Manual support only</div>
    <div class="operator-event-title">{_e(cloud_manual_support)} routine{'' if cloud_manual_support == 1 else 's'} need scheduled proof</div>
    <div class="operator-event-trigger">{_e(names or 'manual receipts do not count as unattended cloud proof')}</div>
  </div>"""
    status = (
        "FAIL"
        if failed or source_call_fail or cloud_failed or cloud_overdue
        else "WARN"
        if dark or stale or open_review_pressure or source_call_warn or live_config_missing or cloud_manual_support
        else "PASS"
    )
    cls = {"PASS": "operator-pass", "WARN": "operator-warn", "FAIL": "operator-fail"}[status]
    build_blockers = 0
    if failed:
        build_blockers += failed
    if source_call_fail:
        build_blockers += 1
    if cloud_failed:
        build_blockers += 1
    if cloud_overdue:
        build_blockers += cloud_overdue
    build_cls = "operator-fail" if build_blockers else "operator-pass"
    wait_parts = []
    source_waits = dark + (1 if live_config_missing else 0)
    if source_waits:
        wait_parts.append(f"{source_waits} source wait{'s' if source_waits != 1 else ''}")
    if schedule_wait:
        wait_parts.append(f"background cloud proof {cloud_scheduled}/{cloud_expected}")
    if cloud_manual_support:
        wait_parts.append(f"{cloud_manual_support} manual-support-only routine{'s' if cloud_manual_support != 1 else ''}")
    if cloud_overdue:
        wait_parts.append(f"{cloud_overdue} overdue cloud routine{'s' if cloud_overdue != 1 else ''}")
    if open_stale:
        wait_parts.append(f"{open_stale} stale review{'s' if open_stale != 1 else ''}")
    if open_due:
        wait_parts.append(f"{open_due} due review{'s' if open_due != 1 else ''}")
    if stale:
        wait_parts.append(f"{stale} re-check{'s' if stale != 1 else ''}")
    if source_call_warn:
        wait_parts.append(f"{source_call_observed} unscored source call{'s' if source_call_observed != 1 else ''}")
    wait_text = "; ".join(wait_parts) if wait_parts else "no waits"
    build_state = (
        "Blocked"
        if build_blockers
        else "Build clear, not all clear"
        if wait_parts
        else "All clear"
    )
    lane_detail = []
    if dark:
        lane_detail.append(f"{dark} dark")
    if stale:
        lane_detail.append(f"{stale} stale")
    if failed:
        lane_detail.append(f"{failed} failed")
    lane_value_parts = list(lane_detail)
    if deferred_dark:
        lane_value_parts.append(f"{deferred_dark} deferred")
    lane_value = ", ".join(lane_value_parts) if lane_value_parts else "clear"
    lane_cls = "operator-warn" if lane_detail else "operator-pass"
    if open_stale:
        open_review_value = f"{open_stale} stale"
    elif open_due:
        open_review_value = f"{open_due} due"
    elif open_count:
        open_review_value = f"{open_count} new"
    else:
        open_review_value = "0"
    operator_summary = f"{build_state} | {wait_text}"
    return f"""
<div class="card" id="operator-status" data-summary="{_e(operator_summary)}">
  <div class="card-title"><span class="icon">!</span> Operator status
    <span class="{cls}" style="font-size:11px;margin-left:auto">{status}</span>
  </div>
  <div class="operator-grid">
    <a class="operator-pill" href="#today-actions"><div class="operator-label">Today actions</div><div class="operator-value">{_e(action_count)}</div></a>
    <a class="operator-pill" href="#feedback-loops"><div class="operator-label">Open reviews</div><div class="operator-value {_e('operator-warn' if open_review_pressure else 'operator-pass')}">{_e(open_review_value)}</div></a>
    <a class="operator-pill" href="#lane-status"><div class="operator-label">Source lanes</div><div class="operator-value {_e(lane_cls)}">{_e(lane_value)}</div></a>
    <a class="operator-pill" href="#feedback-loops"><div class="operator-label">Source calls</div><div class="operator-value {_e('operator-fail' if source_call_fail else 'operator-warn' if source_call_warn else 'operator-pass')}">{_e(source_call_value)}</div></a>
    <a class="operator-pill" href="#operator-status"><div class="operator-label">Live fetch</div><div class="operator-value {_e('operator-warn' if live_config_missing else 'operator-pass')}">{_e(f'{live_configured}/{live_config_total}' if live_config_total else 'unknown')}</div></a>
    <a class="operator-pill" href="#operator-status"><div class="operator-label">Build blockers</div><div class="operator-value {_e(build_cls)}">{_e(build_blockers)}</div></a>
  </div>
  <div class="operator-readiness"><strong class="{_e(build_cls)}">{_e(build_state)}</strong> | {_e(wait_text)}</div>
  <div class="operator-command">python src/completion_audit.py --format text</div>
  <div class="operator-command">python src/go_live_checklist.py --format text</div>
  {live_config_html}
  {cloud_overdue_html}
  {cloud_manual_html}
  {event_watch_html}
  <div class="operator-command">python src/sudden_event_refresh.py --title &quot;&lt;event headline&gt;&quot; --channels &quot;oil,rates,volatility&quot; --tickers &quot;XOP,TNX&quot; --why &quot;&lt;why exposure, hedges, or new-buy timing changes&gt;&quot; --trigger &quot;&lt;what confirms or changes the risk&gt;&quot;</div>
</div>"""


def _hero(feed: dict) -> str:
    hero = feed.get("hero") or {}
    needs = hero.get("needs_you") or {}
    legacy_count = int(needs.get("count") or 0)
    items = needs.get("items") or []
    book_count = (hero.get("hero") or {}).get("count", 0)
    leading = ", ".join((hero.get("hero") or {}).get("leading_sleeves") or [])
    leading_str = f" | leading: {_e(leading)}" if leading else ""
    packet_counts = (feed.get("market_open_packet") or {}).get("counts") or {}
    key_now = int(packet_counts.get("key_now") or 0)
    recheck = int(packet_counts.get("recheck") or 0)
    backlog = int(packet_counts.get("backlog") or 0)
    blockers = int(packet_counts.get("blockers") or 0)
    action_count = len(feed.get("actions") or [])

    if key_now:
        display_count = str(key_now)
        title = f"{key_now} key review prompt{'s' if key_now != 1 else ''} ready"
        detail = "Start with the Market-Open Packet; run gates before capital moves."
        if blockers:
            detail += f" {blockers} blocker{'s' if blockers != 1 else ''} still listed."
    elif recheck:
        display_count = str(recheck)
        title = f"{recheck} re-check{'s' if recheck != 1 else ''} before acting"
        detail = "Start with the Market-Open Packet; refresh assumptions before capital moves."
        if backlog:
            detail += f" {backlog} backlog item{'s' if backlog != 1 else ''} remain visible."
    elif legacy_count:
        display_count = str(legacy_count)
        title = f"{legacy_count} item{'s' if legacy_count != 1 else ''} need{'s' if legacy_count == 1 else ''} attention"
        detail = "Time-sensitive items are in Today's actions below."
    elif action_count or backlog:
        display_count = str(action_count or backlog)
        title = f"{action_count or backlog} decision item{'s' if (action_count or backlog) != 1 else ''} visible"
        detail = "No Key Now items; review backlog only if it affects current capital priority."
    else:
        display_count = "OK"
        title = "No decisions need attention"
        detail = "No fresh action prompts in this feed build."

    hero_items_html = ""
    for it in items:
        reason = _e(it.get("reason", "").replace("_", " ").title())
        detail = _e(it.get("detail", ""))
        note   = _e(it.get("note") or it.get("label") or "")
        hero_items_html += f'<div class="hero-item"><strong>{detail}</strong> - {reason} | {note}</div>'

    return f"""
<div class="hero">
  <div class="hero-row">
    <div class="hero-num">{_e(display_count)}</div>
    <div>
      <div style="font-size:13px;font-weight:600;color:#f0f6fc">
        {_e(title)}
      </div>
      <div class="hero-label">{_e(detail)} | {_e(book_count)} names on the book{leading_str}</div>
    </div>
  </div>
  {f'<div class="hero-items">{hero_items_html}</div>' if hero_items_html else ""}
</div>"""


def _gate_tag(gate: dict | None) -> str:
    if not gate:
        return ""
    preview = gate.get("preview") or ""
    if "🟢" in preview:
        cls = "t-gate-g"
    elif "🔴" in preview:
        cls = "t-gate-r"
    else:
        cls = "t-gate-a"
    label = preview.replace("🟢", "").replace("🟡", "").replace("🔴", "").strip()
    return f'<span class="tag {cls}">{_e(label)}</span>'


def _action_card(a: dict, *, prefix: str = "action") -> str:
    rank = a.get("rank", "")
    ticker_raw = a.get("ticker") or ""
    if not ticker_raw:
        ticker_raw = "EVENT" if a.get("kind") == "event_risk" else "PORTFOLIO"
    ticker = _e(ticker_raw)
    what = _e(a.get("what", ""))
    conf = _e(a.get("confidence", ""))
    move = _e(a.get("your_move", ""))
    why = _e(a.get("why", ""))
    kind_raw = (a.get("kind") or "").replace("_", " ").title()
    state = _e(a.get("action_state") or a.get("urgency") or "")
    label = _e(a.get("action_label") or "")
    capital = _e(a.get("capital_effect") or "")
    synthesis_change = _e(a.get("synthesis_changes") or "")
    capital_priority = a.get("capital_priority_score")
    impact = _e(a.get("goal_impact") or "")
    source = _e(a.get("source") or "")
    freshness = _e(a.get("freshness") or "")
    freshness_judgment = a.get("freshness_judgment") or {}
    why_matters = _e(a.get("why_this_matters") or a.get("why_it_moves_goal") or "")
    disconfirmation = a.get("disconfirmation") or {}
    capital_efficiency = a.get("capital_efficiency") or {}
    assumption_refresh = a.get("assumption_refresh") or {}
    account_placement = a.get("account_placement") or {}
    gate = _gate_tag(a.get("gate"))
    cls = "action-act" if a.get("action_state") == "ACT_NOW" else "action-watch"
    tone_cls = f"tone-{_action_tone(a)}"
    meta = ""
    for value, css in (
        (state, "t-cat"),
        (label, "t-cat"),
        (capital, "t-gate-a"),
        (_e(f"capital: {capital_efficiency.get('label')}") if capital_efficiency.get("label") else "", "t-warn"),
        (_e(f"acct: {account_placement.get('label') or account_placement.get('account')}") if (account_placement.get("label") or account_placement.get("account")) else "", "t-conf"),
        (f"changes: {synthesis_change}" if synthesis_change else "", "t-conf"),
        (f"priority: {_e(capital_priority)}" if isinstance(capital_priority, int) else "", "t-muted"),
        (f"goal: {impact}" if impact else "", "t-conf"),
        (_e(a.get("decision_group_label") or ""), "t-cat"),
    ):
        if value:
            meta += f'<span class="tag {css}">{value}</span>'
    foot_bits = [bit for bit in (source, freshness) if bit]
    foot = " | ".join(foot_bits)
    channels = " / ".join(str(v) for v in (a.get("goal_channels") or []) if v)
    missing = " / ".join(str(v) for v in (a.get("missing_evidence") or []) if v)
    detail_lines = []
    if why_matters:
        detail_lines.append(f"<strong>Why this matters:</strong> {why_matters}")
    if why:
        detail_lines.append(f"<strong>Rationale:</strong> {why}")
    judgment = freshness_judgment.get("judgment") or ""
    if judgment:
        detail_lines.append(
            f"<strong>Freshness:</strong> {_e(judgment)} "
            f"({_e(freshness_judgment.get('evidence_date') or 'n/a')}; "
            f"{_e(freshness_judgment.get('decay_window') or 'source dependent')})"
        )
    if channels or capital or synthesis_change or a.get("goal_score") is not None or isinstance(capital_priority, int):
        score = a.get("goal_score")
        score_txt = f" | score {score}/100" if score is not None else ""
        change_txt = f" | changes {_e(synthesis_change)}" if synthesis_change else ""
        priority_txt = f" | priority {_e(capital_priority)}" if isinstance(capital_priority, int) else ""
        detail_lines.append(
            f"<strong>Goal/capital:</strong> {_e(channels or 'n/a')} "
            f"| capital {_e(capital or 'n/a')}{change_txt}{_e(score_txt)}{priority_txt}"
        )
    capital_bits = []
    if capital_efficiency.get("summary"):
        capital_bits.append(_e(capital_efficiency.get("summary")))
    if capital_efficiency.get("priority_reason"):
        capital_bits.append("Priority: " + _e(capital_efficiency.get("priority_reason")))
    if capital_efficiency.get("do_nothing_risk"):
        capital_bits.append("Do nothing: " + _e(capital_efficiency.get("do_nothing_risk")))
    if capital_efficiency.get("timing_balance"):
        capital_bits.append("Timing balance: " + _e(capital_efficiency.get("timing_balance")))
    compare_against = [
        str(v)
        for v in (capital_efficiency.get("compare_against") or [])
        if str(v).strip()
    ]
    if compare_against:
        capital_bits.append("Compare against: " + _e(" / ".join(compare_against)))
    if capital_bits:
        detail_lines.append(
            "<strong>Capital efficiency:</strong> "
            + "<br>".join(capital_bits)
        )
    placement_bits = []
    if account_placement.get("summary"):
        placement_bits.append(_e(account_placement.get("summary")))
    if account_placement.get("why"):
        placement_bits.append("Why: " + _e(account_placement.get("why")))
    if account_placement.get("rule"):
        placement_bits.append("Rule: " + _e(account_placement.get("rule")))
    placement_caveats = [
        str(v)
        for v in (account_placement.get("caveats") or [])
        if str(v).strip()
    ]
    if placement_caveats:
        placement_bits.append("Caveats: " + _e(" / ".join(placement_caveats)))
    if placement_bits:
        detail_lines.append(
            "<strong>Account placement:</strong> "
            + "<br>".join(placement_bits)
        )
    refresh_bits = []
    if assumption_refresh.get("status"):
        refresh_bits.append("Status: " + _e(str(assumption_refresh.get("status")).replace("_", " ")))
    if assumption_refresh.get("next_step"):
        refresh_bits.append("Next: " + _e(assumption_refresh.get("next_step")))
    changed = [
        str(v)
        for v in (assumption_refresh.get("what_changed") or [])
        if str(v).strip()
    ]
    if changed:
        refresh_bits.append("Changed: " + _e(" / ".join(changed)))
    invalidates_refresh = [
        str(v)
        for v in (assumption_refresh.get("invalidates_if") or [])
        if str(v).strip()
    ]
    if invalidates_refresh:
        refresh_bits.append("Invalidates if: " + _e(" / ".join(invalidates_refresh)))
    if refresh_bits:
        detail_lines.append(
            "<strong>Assumption refresh:</strong> "
            + "<br>".join(refresh_bits)
        )
    if missing:
        detail_lines.append(f"<strong>Missing/re-check:</strong> {_e(missing)}")
    disconfirm_bits = []
    if disconfirmation.get("summary"):
        disconfirm_bits.append(_e(disconfirmation.get("summary")))
    invalidates = [
        str(v)
        for v in (disconfirmation.get("invalidates_if") or [])
        if str(v).strip()
    ]
    confirm = [
        str(v)
        for v in (disconfirmation.get("confirm_before_acting") or [])
        if str(v).strip()
    ]
    if invalidates:
        disconfirm_bits.append("Invalidates if: " + _e(" / ".join(invalidates)))
    if confirm:
        disconfirm_bits.append("Confirm: " + _e(" / ".join(confirm)))
    if disconfirmation.get("downgrade_to"):
        disconfirm_bits.append("Downgrade to: " + _e(disconfirmation.get("downgrade_to")))
    if disconfirm_bits:
        detail_lines.append(
            "<strong>What could make this wrong?</strong> "
            + "<br>".join(disconfirm_bits)
        )
    details = ""
    if detail_lines:
        details = f"""
  <details class="action-details">
    <summary>Why this matters</summary>
    <div class="action-detail-body">{'<br>'.join(detail_lines)}</div>
  </details>"""

    return f"""
<div class="action {cls} {tone_cls}" id="{_e(prefix)}-{_e(rank)}">
  <div class="action-header">
    <span class="rank-badge">#{rank}</span>
    <span class="ticker-tag">{ticker}</span>
    <span class="action-what">{what}</span>
  </div>
  <div class="tags">
    <span class="tag t-cat">{_e(kind_raw)}</span>
    <span class="tag t-conf">conf: {conf}</span>
    {gate}
    {meta}
  </div>
  {f'<div class="action-move">{move}</div>' if move else ""}
  {details}
  {f'<div class="action-foot">{foot}</div>' if foot else ""}
</div>"""


def _actions(actions: list, groups: dict | None = None) -> str:
    if not actions:
        return ""
    by_rank = {a.get("rank"): a for a in actions if isinstance(a, dict)}
    sections = (groups or {}).get("sections") or []
    group_html = ""
    rendered: set[Any] = set()
    for section in sections:
        ranks = [rank for rank in (section.get("ranks") or []) if rank in by_rank]
        if not ranks:
            continue
        rendered.update(ranks)
        cards = "".join(_action_card(by_rank[rank]) for rank in ranks)
        group_html += f"""
<div class="action-group">
  <div class="action-group-title">{_e(section.get("label") or section.get("key") or "Actions")}
    <span>{_e(section.get("description") or "")}</span>
  </div>
  {cards}
</div>"""
    leftovers = [a for a in actions if a.get("rank") not in rendered]
    if leftovers:
        group_html += "".join(_action_card(a) for a in leftovers)
    return f"""
<div class="card" id="today-actions">
  <div class="card-title"><span class="icon">!</span> Today&#39;s actions
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{len(actions)} ranked item{'s' if len(actions) != 1 else ''}; no auto-trade</span>
  </div>
  {group_html}
</div>"""


def _source_conflicts(block: dict) -> str:
    rows = block.get("rows") or []
    body = ""
    for row in rows:
        body += f"""
<div class="small-item">
  <span class="context-ticker">{_e(row.get("ticker") or "PORTFOLIO")}</span>
  <span class="tag t-warn">{_e(row.get("label") or "source split")}</span>
  {f'<span class="small-muted">{_e(str(row.get("scope") or "").replace("_", " "))}</span>' if row.get("scope") else ""}
  {f'<span class="small-muted">Bull: {_e(row.get("bull_read") or "")}</span>' if row.get("bull_read") else ""}
  {f'<span class="small-muted">Bear: {_e(row.get("bear_read") or "")}</span>' if row.get("bear_read") else ""}
  {f'<span class="small-muted">Posture: {_e(row.get("action_posture") or "")}</span>' if row.get("action_posture") else ""}
  {f'<span class="small-muted">{_e(row.get("decision_effect") or "")}</span>' if row.get("decision_effect") else ""}
</div>"""
    if not body:
        body = '<div class="feedback-line">No current bull/bear source splits surfaced by the conviction engine.</div>'
    return f"""
<div class="card" id="source-conflicts">
  <div class="card-title"><span class="icon">!</span> Source conflicts
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{len(rows)} split{'s' if len(rows) != 1 else ''}; review-only</span>
  </div>
  <div class="small-list">{body}</div>
  <div class="feedback-line">{_e(block.get("honesty_rule") or "Conflicts downgrade action posture; they do not create buy/sell execution.")}</div>
</div>"""


def _market_open_packet(block: dict) -> str:
    if not block:
        return ""
    rows = block.get("rows") or []
    status = block.get("status") or "ready"
    status_cls = "t-conf" if status == "ready" else "t-warn"
    body = ""
    for row in rows:
        tone_cls = f"tone-{_packet_tone(row)}"
        body += f"""
<div class="small-item {tone_cls}">
  <span class="tag {status_cls}">#{_e(row.get("priority") or "")}</span>
  <span class="context-ticker">{_e(row.get("label") or "")}</span>
  {_refresh_status_badge(row.get("refresh_status"))}
  {f'<span class="small-muted">Priority: {_e(row.get("capital_priority_score"))}</span>' if row.get("capital_priority_score") is not None else ""}
  {_freshness_badge(row)}
  {f'<span class="small-muted">Changed: {_e(row.get("what_changed") or "")}</span>' if row.get("what_changed") else ""}
  {f'<span class="small-muted">Assumptions: {_e(row.get("key_assumptions") or "")}</span>' if row.get("key_assumptions") else ""}
  {f'<span class="small-muted">Why: {_e(row.get("why") or "")}</span>' if row.get("why") else ""}
  {f'<span class="small-muted">Capital priority: {_e(row.get("capital_priority_reason") or "")}</span>' if row.get("capital_priority_reason") else ""}
  {f'<span class="small-muted">Do nothing: {_e(row.get("do_nothing_risk") or "")}</span>' if row.get("do_nothing_risk") else ""}
  {f'<span class="small-muted">Next: {_e(row.get("next_step") or "")}</span>' if row.get("next_step") else ""}
  {f'<span class="small-muted">Invalidates: {_e(row.get("invalidates") or "")}</span>' if row.get("invalidates") else ""}
  {f'<span class="small-muted">Compare: {_e(row.get("compare_against") or "")}</span>' if row.get("compare_against") else ""}
  {f'<span class="small-muted">Account: {_e(row.get("account_placement_summary") or "")}</span>' if row.get("account_placement_summary") else ""}
  {f'<span class="small-muted">Account why: {_e(row.get("account_placement_why") or "")}</span>' if row.get("account_placement_why") else ""}
  {f'<span class="small-muted">Blocks: {_e(row.get("blocks") or "")}</span>' if row.get("blocks") else ""}
</div>"""
    if not body:
        body = '<div class="feedback-line">No market-open review rows in this feed build.</div>'
    return f"""
<div class="card" id="market-open-packet">
  <div class="card-title"><span class="icon">!</span> Market-open packet
    <span class="tag {status_cls}" style="margin-left:auto">{_e(status.replace("_", " "))}</span>
  </div>
  <div class="feedback-line">{_e(block.get("line") or "")}</div>
  <div class="small-list">{body}</div>
  {f'<div class="feedback-line">{_e(block.get("honesty_rule") or "")}</div>' if block.get("honesty_rule") else ""}
  <div class="cmd-row"><span class="cmd-name">print packet</span><span class="cmd-desc"><code>python src/market_open_packet.py --feed src/latest_cockpit_feed.json --format text</code></span></div>
</div>"""


def _today_recommendation_brief(block: dict) -> str:
    if not block:
        return ""
    status = str(block.get("status") or "review")
    status_cls = "t-conf" if status == "quiet" else "t-warn"
    rows = block.get("do_today") or []
    body = ""
    for idx, row in enumerate(rows[:5], start=1):
        body += f"""
<div class="small-item">
  <span class="tag {status_cls}">#{idx}</span>
  {f'<span class="context-ticker">{_e(row.get("ticker") or "")}</span>' if row.get("ticker") else ""}
  <span>{_e(row.get("title") or row.get("action") or row.get("kind") or "review")}</span>
  {f'<span class="small-muted">Risk: {_e(row.get("risk") or "")}</span>' if row.get("risk") else ""}
  {f'<span class="small-muted">Why: {_e(row.get("why") or "")}</span>' if row.get("why") else ""}
  {f'<span class="small-muted">Next: {_e(row.get("next_step") or "")}</span>' if row.get("next_step") else ""}
  {f'<span class="small-muted">Blocks: {_e(row.get("blocks") or "")}</span>' if row.get("blocks") else ""}
</div>"""
    if not body:
        body = '<div class="feedback-line">No daily recommendation rows in this feed build.</div>'
    options = block.get("options") or {}
    opportunities = block.get("opportunities") or {}
    social = block.get("social") or {}
    push_candidates = block.get("push_candidates") or []
    not_checked = block.get("not_checked") or []
    return f"""
<div class="card" id="today-recommendation-brief">
  <div class="card-title"><span class="icon">!</span> What should I do today?
    <span class="tag {status_cls}" style="margin-left:auto">{_e(status.replace("_", " "))}</span>
  </div>
  <div class="feedback-line">{_e(block.get("line") or "")}</div>
  <div class="small-list">{body}</div>
  <div class="small-item">
    <span class="tag t-conf">opportunity</span>
    <span>{_e(opportunities.get("count") or 0)} reallocation/opportunity review item{'s' if int(opportunities.get("count") or 0) != 1 else ''}</span>
  </div>
  <div class="small-item">
    <span class="tag t-conf">options</span>
    <span>{_e(options.get("line") or options.get("status") or "not checked")}</span>
  </div>
  <div class="small-item">
    <span class="tag t-warn">social</span>
    <span>{_e(social.get("line") or social.get("status") or "not checked")}</span>
  </div>
  <div class="small-item">
    <span class="tag t-warn">push</span>
    <span>{len(push_candidates)} review-only candidate{'s' if len(push_candidates) != 1 else ''}</span>
  </div>
  {f'<div class="feedback-line">Dark/stale: {_e(", ".join((row.get("label") or row.get("key") or "") for row in not_checked[:4]))}</div>' if not_checked else ""}
  {f'<div class="feedback-line">{_e(block.get("honesty_rule") or "")}</div>' if block.get("honesty_rule") else ""}
  <div class="cmd-row"><span class="cmd-name">print today brief</span><span class="cmd-desc"><code>python src/today_recommendation_brief.py --feed src/latest_cockpit_feed.json --format text</code></span></div>
</div>"""


def _alert_policy(block: dict) -> str:
    if not block:
        return ""
    rows = block.get("rows") or []
    system_health = block.get("system_health") or []
    suppressed = block.get("suppressed") or []
    if not rows and not system_health:
        return ""
    is_push = bool(rows)
    status = "notify" if is_push else "system"
    status_cls = "t-warn" if is_push or system_health else "t-conf"
    title = "Push alerts" if is_push else "System health"
    line = block.get("line") or ""
    if not is_push:
        line = "No push alert. System warning is visible for Ops review only."
    body = f'<div class="feedback-line">{_e(block.get("policy") or "")}</div>' if block.get("policy") else ""
    for row in rows[:6]:
        body += f"""
<div class="small-item">
  <span class="tag t-warn">{_e(row.get("severity") or "alert")}</span>
  {f'<span class="context-ticker">{_e(row.get("ticker") or "")}</span>' if row.get("ticker") else ""}
  <span>{_e(row.get("title") or "")}</span>
  {f'<span class="small-muted">Why: {_e(row.get("why") or "")}</span>' if row.get("why") else ""}
  {f'<span class="small-muted">Trigger: {_e(row.get("trigger") or "")}</span>' if row.get("trigger") else ""}
  {f'<span class="small-muted">Next: {_e(row.get("next_step") or "")}</span>' if row.get("next_step") else ""}
</div>"""
    if not rows and system_health:
        for row in system_health[:4]:
            body += f"""
<div class="small-item">
  <span class="tag t-warn">ops</span>
  <span>{_e(row.get("title") or "")}</span>
  {f'<span class="small-muted">Why: {_e(row.get("why") or "")}</span>' if row.get("why") else ""}
  {f'<span class="small-muted">Next: {_e(row.get("next_step") or "")}</span>' if row.get("next_step") else ""}
</div>"""
    elif not rows:
        for row in suppressed[:6]:
            body += f"""
<div class="small-item">
  <span class="tag t-conf">quiet</span>
  <span>{_e(str(row.get("reason") or "").replace("_", " "))}</span>
  {f'<span class="small-muted">Count: {_e(row.get("count"))}</span>' if row.get("count") is not None else ""}
  {f'<span class="small-muted">{_e(row.get("why") or "")}</span>' if row.get("why") else ""}
</div>"""
    return f"""
<div class="card" id="alert-policy">
  <div class="card-title"><span class="icon">!</span> {_e(title)}
    <span class="tag {status_cls}" style="margin-left:auto">{_e(status)}</span>
  </div>
  <div class="feedback-line">{_e(line)}</div>
  <div class="small-list">{body}</div>
  <div class="cmd-row"><span class="cmd-name">print push alert gate</span><span class="cmd-desc"><code>python src/alert_policy.py --feed src/latest_cockpit_feed.json --format text</code></span></div>
  <div class="cmd-row"><span class="cmd-name">Fundstrat alert dry-run</span><span class="cmd-desc"><code>python src/fundstrat_daytime_alert.py --dry-run --format text</code></span></div>
</div>"""


def _rotation(rot: list) -> str:
    if not rot:
        return ""
    rows = ""
    for r in rot:
        label = (r.get("label") or "").upper()
        cls   = {"LEADING": "lead", "LAGGING": "lag"}.get(label, "inl")
        sub   = _e(r.get("subject", ""))
        r1m   = _rel(r.get("rel_1m"))
        r3m   = _rel(r.get("rel_3m"))
        a3m   = _rel(r.get("abs_3m"))
        rows += f"""<tr>
      <td>{sub}</td>
      <td class="{cls}">{_e(label)}</td>
      <td>{a3m}</td>
      <td>{r3m}</td>
      <td>{r1m}</td>
    </tr>"""
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">🔄</span> Sleeve rotation vs SPY</div>
  <div class="rot-wrap">
    <table class="rot">
      <tr><th>Sleeve</th><th>Status</th><th>Abs 3M</th>
          <th>Rel 3M</th><th>Rel 1M</th></tr>
      {rows}
    </table>
  </div>
</div>"""


def _macro(macro: dict) -> str:
    if not macro:
        return ""
    line   = _e(macro.get("line", ""))
    regime = _e((macro.get("regime") or {}).get("label", ""))
    alerts = macro.get("alerts") or []
    alert_html = ""
    if alerts:
        alert_html = "<br>".join(f'<span style="color:#f85149">⚠ {_e(a)}</span>' for a in alerts)
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">📊</span> Macro</div>
  <div class="macro-line">{line}</div>
  {f'<span class="regime-tag">{regime}</span>' if regime else ""}
  {alert_html}
</div>"""


def _synthesis(synth: dict) -> str:
    if not synth:
        return ""
    sop   = _e(synth.get("state_of_play", ""))
    delta = _e(synth.get("delta", ""))
    hang  = synth.get("hanging") or []
    date  = _e(synth.get("date", ""))

    hang_html = ""
    if hang:
        items = "".join(f"<li>{_e(h)}</li>" for h in hang)
        hang_html = f"""
<div class="s-label">Hanging / unresolved</div>
<ul class="hang-list">{items}</ul>"""

    return f"""
<div class="card">
  <div class="card-title"><span class="icon">🧠</span> Today&#39;s read
    {f'<span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{date}</span>' if date else ""}
  </div>
  {f'<div class="s-label">State of play</div><div class="s-body">{sop}</div>' if sop else ""}
  {f'<div class="s-label">24-48h delta</div><div class="s-body">{delta}</div>' if delta else ""}
  {hang_html}
</div>"""


def _catalysts(cats: list) -> str:
    if not cats:
        return ""
    items = ""
    for c in cats:
        days   = c.get("days_out", "?")
        ticker = _e(c.get("ticker", ""))
        label  = _e(c.get("label", ""))
        day_str = f"T+{days}d" if isinstance(days, int) and days > 0 else ("TODAY" if days == 0 else f"{days}d")
        items += f"""
<div class="cat-item">
  <span class="cat-days">{_e(day_str)}</span>
  <span class="cat-ticker">{ticker}</span>
  <span class="cat-label">{label}</span>
</div>"""
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">📅</span> Catalysts (&le;14d)</div>
  <div class="cat-list">{items}</div>
</div>"""


def _research(res: dict) -> str:
    pending = (res or {}).get("pending") or []
    if not pending:
        return ""
    items = ""
    for p in pending:
        r  = _e(p.get("r", ""))
        pr = (p.get("pr") or "low").lower()
        cls = {"high": "pr-h", "med": "pr-m"}.get(pr, "pr-l")
        label = {"high": "HI", "med": "MD"}.get(pr, "LO")
        items += f"""
<div class="res-item">
  <span class="pr {cls}">{label}</span>
  <span>{r}</span>
</div>"""
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">🔎</span> Research queue</div>
  <div class="res-list">{items}</div>
</div>"""


def _lean_in(lean: list) -> str:
    if not lean:
        return ""
    items = ""
    for li in lean:
        ticker   = _e(li.get("ticker", ""))
        headline = _e(li.get("headline", ""))
        rotation = _e(li.get("rotation", ""))
        rot_cls  = {"LEADING": "lead", "LAGGING": "lag"}.get(rotation, "inl")
        next_ev  = _e(li.get("next_evidence", ""))
        items += f"""
<div class="lean-item">
  <span class="lean-ticker">{ticker}</span>
  <span class="tag {rot_cls}" style="margin-left:6px">{rotation}</span>
  <div class="lean-headline">{headline}</div>
  {f'<div class="lean-sub">Clears when: {next_ev}</div>' if next_ev else ""}
</div>"""
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">📈</span> Lean-in watchlist</div>
  {items}
</div>"""


def _opportunity_context(feed: dict) -> str:
    columns: list[tuple[str, list[str]]] = []

    target_rows = (((feed.get("target_drift") or {}).get("rows") or [])[:3])
    if target_rows:
        rows = []
        for row in target_rows:
            ticker = _e(row.get("ticker") or "")
            direction = _e(row.get("direction") or "")
            actual = _pct(row.get("actual_pct"))
            target = _pct(row.get("target_pct"))
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{direction}'
                f'<span class="context-sub">{actual} actual vs {target} target</span></div>'
            )
        columns.append(("Target drift", rows))

    interest_rows = [
        row for row in ((feed.get("watch_interest") or {}).get("rows") or [])
        if isinstance(row, dict) and row.get("manual_interest")
    ][:3]
    if interest_rows:
        rows = []
        for row in interest_rows:
            ticker = _e(row.get("ticker") or "")
            status = _e(row.get("status") or "interest")
            sources = int(row.get("source_count") or 0)
            ambiguity = _e(row.get("ambiguity") or row.get("next_step") or "")
            sub = f"{sources} linked source{'s' if sources != 1 else ''}"
            if ambiguity:
                sub += f" | {ambiguity}"
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{status}'
                f'<span class="context-sub">{sub}</span></div>'
            )
        columns.append(("Interest", rows))

    prospect_rows = (
        ((feed.get("prospects") or {}).get("hot") or [])
        + ((feed.get("prospects") or {}).get("movers_best") or [])
        + ((feed.get("prospects") or {}).get("sell_fast") or [])
    )[:3]
    if prospect_rows:
        rows = []
        for row in prospect_rows:
            ticker = _e(row.get("ticker") or "")
            direction = _e(row.get("direction") or row.get("urgency") or "")
            summary = _e(row.get("summary") or row.get("provenance") or "")
            sub_html = f'<span class="context-sub">{summary}</span>' if summary else ""
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{direction}'
                f'{sub_html}</div>'
            )
        columns.append(("Prospects", rows))

    radar_rows = _newest_first([row for row in (feed.get("radar") or []) if isinstance(row, dict)])[:3]
    if radar_rows:
        rows = []
        for row in radar_rows:
            ticker = _e(row.get("ticker") or "")
            direction = _e(row.get("direction") or "")
            author = _e(row.get("author") or "")
            detail = " | ".join(part for part in (author, _e(row.get("date") or "")) if part)
            detail_html = f'<span class="context-sub">{detail}</span>' if detail else ""
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{direction}'
                f'{detail_html}</div>'
            )
        columns.append(("Radar", rows))

    flow_rows = (((feed.get("bullish_flow") or {}).get("rows") or [])[:3])
    if flow_rows:
        rows = []
        for row in flow_rows:
            ticker = _e(row.get("ticker") or "")
            direction = _e(row.get("direction") or "")
            strength = _e(row.get("strength") or "")
            types = ", ".join(row.get("signal_types") or [])
            types_html = f'<span class="context-sub">{_e(types)}</span>' if types else ""
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{direction} {strength}'
                f'{types_html}</div>'
            )
        columns.append(("Bullish flow", rows))

    if not columns:
        return ""
    body = ""
    for label, rows in columns[:4]:
        body += f"""
<div class="context-col">
  <div class="context-label">{_e(label)}</div>
  {''.join(rows)}
</div>"""
    return f"""
<div class="card" id="opportunity-context">
  <div class="card-title"><span class="icon">+</span> Opportunity context
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">context, not orders</span>
  </div>
  <div class="context-grid">{body}</div>
</div>"""


def _asymmetric_opportunities(block: dict) -> str:
    rows = block.get("rows") or []
    if not rows:
        return ""
    body = ""
    for row in rows[:8]:
        body += f"""
<div class="small-item">
  <span class="context-ticker">{_e(row.get("ticker") or "")}</span>
  <span class="tag t-conf">score {_e(row.get("score") or "")}</span>
  <span class="tag t-cat">{_e(row.get("source") or "")}</span>
  <span class="small-muted">{_e(row.get("reason") or "")}</span>
  {f'<span class="small-muted">Evidence: {_e(row.get("evidence") or "")}</span>' if row.get("evidence") else ""}
  <span class="small-muted">Decay: {_e(row.get("decay_window") or "source dependent")} | {_e(row.get("action") or "review")}</span>
</div>"""
    return f"""
<div class="card" id="asymmetric-opportunities">
  <div class="card-title"><span class="icon">+</span> Asymmetric opportunities
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{_e(block.get("dedupe_rule") or "deduped")}</span>
  </div>
  <div class="small-list">{body}</div>
</div>"""


def _uw_action_runbook(block: dict) -> str:
    rows = block.get("rows") or []
    if not rows:
        return ""
    proof = block.get("endpoint_proof") or {}
    blockers = proof.get("blockers") or []
    proof_cls = (
        "t-conf" if proof.get("status") == "has_data" and not blockers
        else "t-warn" if proof.get("status") in {"has_data", "not_checked"}
        else "t-gate-r"
    )
    proof_html = ""
    if proof.get("line"):
        blocker_html = "".join(
            f'<span class="small-muted">Proof blocker: {_e(blocker)}</span>'
            for blocker in blockers[:3]
        )
        interpretation = proof.get("interpretation_counts") or {}
        interpretation_html = ""
        if interpretation:
            interpretation_html = (
                f'<span class="small-muted">Interpretation: '
                f'supports {_e(interpretation.get("supports") or 0)} | '
                f'contradicts {_e(interpretation.get("contradicts") or 0)} | '
                f'inconclusive {_e(interpretation.get("inconclusive") or 0)} | '
                f'missing {_e(interpretation.get("missing") or 0)}</span>'
            )
        proof_rows_html = ""
        for proof_row in (proof.get("rows") or [])[:5]:
            ticker = f' {_e(proof_row.get("ticker") or "")}' if proof_row.get("ticker") else ""
            proof_rows_html += (
                '<span class="small-muted">Endpoint: '
                f'{_e(proof_row.get("mode") or "")} / {_e(proof_row.get("endpoint") or "")}{ticker} - '
                f'{_e(proof_row.get("decision_interpretation") or proof_row.get("status") or "")} '
                f'({_e(proof_row.get("status") or "")})</span>'
            )
        proof_html = f"""
<div class="small-item">
  <span class="tag {proof_cls}">endpoint proof {_e(proof.get("status") or "unknown")}</span>
  <span class="small-muted">{_e(proof.get("line") or "")}</span>
  {interpretation_html}
  {blocker_html}
  {proof_rows_html}
</div>"""
    body = ""
    for row in rows[:5]:
        tickers = ", ".join(row.get("ticker_scope") or [])
        market_checks = ", ".join(row.get("market_checks") or [])
        ticker_checks = ", ".join(row.get("ticker_checks") or [])
        body += f"""
<div class="small-item">
  <span class="context-ticker">{_e(row.get("label") or row.get("mode") or "")}</span>
  <span class="tag t-conf">priority {_e(row.get("priority") or "")}</span>
  <span class="small-muted">{_e(row.get("why") or "")}</span>
  {f'<span class="small-muted">Tickers: {_e(tickers)}</span>' if tickers else ""}
  {f'<span class="small-muted">Market checks: {_e(market_checks)}</span>' if market_checks else ""}
  {f'<span class="small-muted">Ticker checks: {_e(ticker_checks)}</span>' if ticker_checks else ""}
  <span class="small-muted">Blocks action if: {_e(row.get("blocks_action_if") or "")}</span>
  <span class="small-muted">Promote when: {_e(row.get("promote_when") or "")}</span>
</div>"""
    return f"""
<div class="card" id="uw-action-runbook">
  <div class="card-title"><span class="icon">?</span> UW action runbook
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">checks, not proof</span>
  </div>
  <div class="feedback-line">{_e(block.get("line") or "")}</div>
  {proof_html}
  <div class="small-list">{body}</div>
  {f'<div class="feedback-line">{_e(block.get("honesty_rule") or "")}</div>' if block.get("honesty_rule") else ""}
  {f'<div class="cmd-row"><span class="cmd-name">print runbook</span><span class="cmd-desc"><code>{_e(block.get("command") or "")}</code></span></div>' if block.get("command") else ""}
</div>"""


def _social_watch(block: dict) -> str:
    if not block:
        return ""
    rows = block.get("rows") or []
    status = block.get("status") or "not_checked"
    status_cls = "t-conf" if status == "has_data" else "t-warn" if status == "not_checked" else "t-cat"
    body = ""
    if rows:
        for row in rows[:6]:
            label = row.get("ticker") or row.get("entity") or "SOCIAL"
            subreddits = ", ".join(row.get("subreddits") or [])
            evidence = "; ".join(row.get("evidence") or [])
            confirms = "; ".join(row.get("independent_confirmation") or [])
            body += f"""
<div class="small-item">
  <span class="context-ticker">{_e(label)}</span>
  <span class="tag {status_cls}">score {_e(row.get("score") or "")}</span>
  <span class="tag t-cat">{_e(row.get("escalation") or "Quiet Watch")}</span>
  <span class="small-muted">{_e(row.get("summary") or "")}</span>
  {f'<span class="small-muted">Subreddits: {_e(subreddits)}</span>' if subreddits else ""}
  {f'<span class="small-muted">Evidence: {_e(evidence)}</span>' if evidence else ""}
  {f'<span class="small-muted">Independent confirmation: {_e(confirms)}</span>' if confirms else ""}
  <span class="small-muted">Risk: {_e(row.get("risk") or "")}</span>
</div>"""
    else:
        body = f'<div class="feedback-line">{_e(block.get("line") or "Social Watch not checked.")}</div>'
    return f"""
<div class="card" id="social-watch">
  <div class="card-title"><span class="icon">*</span> Social Watch
    <span class="tag {status_cls}" style="margin-left:auto">{_e(status.replace("_", " "))}</span>
  </div>
  {f'<div class="feedback-line">{_e(block.get("line") or "")}</div>' if rows and block.get("line") else ""}
  <div class="small-list">{body}</div>
  {f'<div class="feedback-line">{_e(block.get("honesty_rule") or "")}</div>' if block.get("honesty_rule") else ""}
  {f'<div class="feedback-line">{_e(block.get("promotion_rule") or "")}</div>' if block.get("promotion_rule") else ""}
  {f'<div class="cmd-row"><span class="cmd-name">print social watch</span><span class="cmd-desc"><code>{_e(block.get("command") or "")}</code></span></div>' if block.get("command") else ""}
</div>"""


def _usd(value) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        try:
            return datetime.fromisoformat(text).replace(tzinfo=ET)
        except ValueError:
            return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        try:
            return datetime.fromisoformat(text[:10]).replace(tzinfo=ET)
        except ValueError:
            return None


def _account_positions_age_days(snapshot_date: Any, generated_at: Any) -> int | None:
    snap = _parse_dt(snapshot_date)
    built = _parse_dt(generated_at) or datetime.now(tz=ET)
    if not snap:
        return None
    return max(0, (built.astimezone(ET).date() - snap.astimezone(ET).date()).days)


def _feed_tracked_tickers(feed: dict[str, Any]) -> set[str]:
    tracked: set[str] = set()
    for cat in feed.get("holdings") or []:
        for pos in cat.get("pos") or []:
            ticker = str(pos.get("t") or "").upper().strip()
            if ticker:
                tracked.add(ticker)
    views = ((feed.get("portfolio_views") or {}).get("views") or {})
    for view in views.values():
        for row in (view or {}).get("rows") or []:
            ticker = str(row.get("ticker") or "").upper().strip()
            if ticker and row.get("tracked"):
                tracked.add(ticker)
    return tracked


def _load_account_positions() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with ACCOUNT_POSITIONS_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None, f"account positions file missing: {ACCOUNT_POSITIONS_PATH.name}"
    except json.JSONDecodeError as exc:
        return None, f"account positions file unreadable: {exc}"
    if not isinstance(data, dict):
        return None, "account positions file has unexpected shape"
    return data, None


def _aggregate_account_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        bucket = by_ticker.setdefault(
            ticker,
            {
                "ticker": ticker,
                "shares": 0.0,
                "market_value": 0.0,
                "account": "Multiple",
                "owners": set(),
                "tracked": False,
            },
        )
        try:
            bucket["shares"] += float(row.get("shares") or 0)
        except (TypeError, ValueError):
            pass
        try:
            bucket["market_value"] += float(row.get("market_value") or 0)
        except (TypeError, ValueError):
            pass
        if row.get("owner"):
            bucket["owners"].add(str(row.get("owner")))
        bucket["tracked"] = bool(bucket["tracked"] or row.get("tracked"))
    out = []
    for row in by_ticker.values():
        row["owners"] = sorted(row["owners"])
        out.append(row)
    return sorted(out, key=lambda r: float(r.get("market_value") or 0), reverse=True)


def _holdings_tab(feed: dict[str, Any]) -> tuple[str, int]:
    data, error = _load_account_positions()
    if error:
        return f"""
<div id="tab-holdings" style="display:none">
  <div class="card tone-amber">
    <div class="card-title"><span class="icon">#</span> Holdings</div>
    <div class="summary-line">Holdings not checked - {_e(error)}</div>
    <div class="summary-muted">Fail-soft: dashboard keeps rendering, but holdings are dark until the account book is refreshed.</div>
  </div>
</div>""", 0

    account_rows = [row for row in data.get("account_positions") or [] if isinstance(row, dict)]
    combined = [row for row in data.get("combined_positions") or [] if isinstance(row, dict)]
    if not combined:
        combined = _aggregate_account_positions(account_rows)
    sleeve_value = data.get("sleeve_value")
    try:
        sleeve = float(sleeve_value or 0)
    except (TypeError, ValueError):
        sleeve = 0.0
    snapshot = data.get("snapshot_date") or ""
    age_days = _account_positions_age_days(snapshot, feed.get("generated_at"))
    stale = age_days is None or age_days > 1
    tracked_from_feed = _feed_tracked_tickers(feed)

    accounts_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in account_rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        if ticker:
            accounts_by_ticker.setdefault(ticker, []).append(row)

    rows_html = ""
    untracked: list[str] = []
    total_value = 0.0
    for row in sorted(combined, key=lambda r: float(r.get("market_value") or 0), reverse=True):
        ticker = str(row.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        acct_rows = accounts_by_ticker.get(ticker) or []
        try:
            value = float(row.get("market_value") or 0)
        except (TypeError, ValueError):
            value = 0.0
        total_value += value
        pct = (value / sleeve * 100) if sleeve else 0.0
        tracked = bool(row.get("tracked")) or ticker in tracked_from_feed
        if not tracked:
            untracked.append(ticker)
        unique_accounts = sorted({str(r.get("account") or "") for r in acct_rows if r.get("account")})
        account_count = len(unique_accounts) if unique_accounts else int(row.get("account_count") or 0)
        detail_rows = ""
        for acct_row in sorted(acct_rows, key=lambda r: (str(r.get("owner") or ""), str(r.get("account") or ""))):
            try:
                shares = f"{float(acct_row.get('shares') or 0):,.3f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                shares = ""
            detail_rows += f"""<tr>
  <td>{_e(acct_row.get("owner") or "")}</td>
  <td>{_e(acct_row.get("broker") or "")}</td>
  <td>{_e(acct_row.get("account") or "")}</td>
  <td>{_e(acct_row.get("asset_type") or "")}</td>
  <td style="font-family:monospace">{_e(shares)}</td>
  <td style="font-family:monospace">{_usd(acct_row.get("market_value"))}</td>
</tr>"""
        drill = (
            f"""<details class="holding-drill">
  <summary>{account_count} account{'s' if account_count != 1 else ''}</summary>
  <div class="book-wrap">
    <table class="book">
      <tr><th>Owner</th><th>Broker</th><th>Account</th><th>Type</th><th>Shares</th><th>Value</th></tr>
      {detail_rows}
    </table>
  </div>
</details>"""
            if detail_rows
            else f"{account_count}"
        )
        flag_cls = "" if tracked else " untracked"
        flag = "TRACKED" if tracked else "UNTRACKED"
        rows_html += f"""<tr>
  <td><strong>{_e(ticker)}</strong></td>
  <td style="font-family:monospace">{_usd(value)}</td>
  <td style="font-family:monospace">{pct:.1f}%</td>
  <td>{drill}</td>
  <td><span class="hold-flag{flag_cls}">{flag}</span></td>
</tr>"""

    untracked = sorted(untracked)
    stale_html = ""
    if stale:
        age = "unknown age" if age_days is None else f"{age_days} day{'s' if age_days != 1 else ''} old"
        stale_html = (
            f'<div class="hold-stale">STALE HOLDINGS: snapshot {_e(snapshot or "missing date")} is {age}; '
            "refresh account_positions.json before relying on trade sizing.</div>"
        )
    orphan_line = (
        "Build log: untracked tickers in account_positions: " + ", ".join(untracked)
        if untracked
        else "Build log: no untracked account-position tickers."
    )
    return f"""
<div id="tab-holdings" style="display:none">
  <div class="card">
    <div class="card-title"><span class="icon">#</span> Holdings
      <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">snapshot {_e(snapshot or "not dated")}</span>
    </div>
    <div class="hold-kpis">
      <div class="hold-kpi"><strong>{len(combined)}</strong> tickers</div>
      <div class="hold-kpi"><strong>{len(account_rows)}</strong> account rows</div>
      <div class="hold-kpi"><strong>{_usd(total_value)}</strong> total shown</div>
      <div class="hold-kpi"><strong>{len(untracked)}</strong> untracked</div>
    </div>
    {stale_html}
    <div class="summary-muted">{_e(orphan_line)}</div>
  </div>
  <div class="card">
    <div class="card-title"><span class="icon">#</span> All account holdings</div>
    <div class="book-wrap">
      <table class="book">
        <tr><th>Ticker</th><th>Total $</th><th>% sleeve</th><th># accounts</th><th>Tracking</th></tr>
        {rows_html}
      </table>
    </div>
  </div>
</div>""", len(untracked)


def _reallocation_brief(block: dict) -> str:
    rows = block.get("rows") or []
    trims = block.get("trims") or []
    special_reviews = block.get("special_reviews") or []
    notes = block.get("notes") or []
    if not rows and not trims and not block.get("line"):
        return ""
    status = block.get("status") or "candidate_only"
    status_cls = "t-warn" if status == "test_data_only" else "t-conf"
    capital = block.get("capital_efficiency") or {}
    options_gate = block.get("options_gate") or {}
    body = ""
    for blocker in (block.get("blockers") or [])[:4]:
        body += f'<div class="feedback-line"><strong>Blocker:</strong> {_e(blocker)}</div>'
    for note in notes[:4]:
        body += f'<div class="feedback-line"><strong>Note:</strong> {_e(note)}</div>'
    for row in rows[:6]:
        tone_cls = f"tone-{_placement_tone(row.get('account_placement') or {'status': 'candidate'})}"
        funded = ", ".join(
            f"{item.get('ticker')} {_usd(item.get('notional_usd'))}"
            for item in row.get("funded_by") or []
        )
        blockers = ", ".join(row.get("blockers") or [])
        row_capital = row.get("capital_efficiency") or {}
        options = row.get("options_review_prompt") or {}
        placement = row.get("account_placement") or {}
        body += f"""
<div class="small-item {tone_cls}">
  <span class="context-ticker">{_e(row.get("ticker") or "")}</span>
  <span class="tag {status_cls}">add {_usd(row.get("notional_usd"))}</span>
  <span class="tag t-cat">{_e(row.get("sequence") or "")}</span>
  <span class="small-muted">{_e(row.get("entry_note") or "")}</span>
  {f'<span class="small-muted">Funded by: {_e(funded)}</span>' if funded else ""}
  {f'<span class="small-muted">Account: {_e(placement.get("summary") or "")}</span>' if placement.get("summary") else ""}
  {f'<span class="small-muted">Account why: {_e(placement.get("why") or "")}</span>' if placement.get("why") else ""}
  {f'<span class="small-muted">Capital: {_e(row_capital.get("summary") or "")}</span>' if row_capital.get("summary") else ""}
  {f'<span class="small-muted">Do nothing: {_e(row_capital.get("consequence_of_doing_nothing") or "")}</span>' if row_capital.get("consequence_of_doing_nothing") else ""}
  {f'<span class="small-muted">Options: {_e(options.get("label") or "")}; {_e(options.get("max_loss_gate") or "")}</span>' if options else ""}
  {f'<span class="small-muted">Blocks: {_e(blockers)}</span>' if blockers else ""}
  {f'<span class="small-muted">Disconfirm: {_e(row.get("disconfirmation") or "")}</span>' if row.get("disconfirmation") else ""}
</div>"""
    if trims:
        trim_bits = []
        for row in trims[:6]:
            funds = ", ".join(f"{item.get('ticker')} {_usd(item.get('notional_usd'))}" for item in row.get("funds") or [])
            trim_bits.append(f"{row.get('ticker')} {_usd(row.get('notional_usd'))}{f' -> {funds}' if funds else ''}")
        body += f'<div class="feedback-line"><strong>Funding trims:</strong> {_e("; ".join(trim_bits))}</div>'
    if special_reviews:
        special_bits = []
        for row in special_reviews[:5]:
            special_bits.append(
                f"{row.get('ticker')} {row.get('status')}: {row.get('next_step')}"
            )
        body += f'<div class="feedback-line"><strong>Special re-checks:</strong> {_e("; ".join(special_bits))}</div>'
    funding = block.get("funding") or {}
    funding_line = (
        f"pool {_usd(funding.get('pool_total_usd'))}; allocated {_usd(funding.get('allocated_usd'))}; "
        f"shortfall {_usd(funding.get('shortfall_usd'))}"
        if funding else ""
    )
    return f"""
<div class="card" id="reallocation-brief">
  <div class="card-title"><span class="icon">#</span> Candidate reallocation brief
    <span class="tag {status_cls}" style="margin-left:auto">{_e(status.replace("_", " "))}</span>
  </div>
  <div class="feedback-line">{_e(block.get("line") or "")}</div>
  {f'<div class="feedback-line">{_e(funding_line)}</div>' if funding_line else ""}
  {f'<div class="feedback-line"><strong>Capital efficiency:</strong> {_e(capital.get("summary") or "")}</div>' if capital.get("summary") else ""}
  {f'<div class="feedback-line"><strong>Timing:</strong> {_e(capital.get("timing_balance") or "")}</div>' if capital.get("timing_balance") else ""}
  {f'<div class="feedback-line"><strong>Do nothing:</strong> {_e(capital.get("do_nothing_risk") or "")}</div>' if capital.get("do_nothing_risk") else ""}
  {f'<div class="feedback-line"><strong>Options gate:</strong> {_e(options_gate.get("line") or "")}</div>' if options_gate.get("line") else ""}
  <div class="small-list">{body}</div>
  {f'<div class="feedback-line">{_e(block.get("honesty_rule") or "")}</div>' if block.get("honesty_rule") else ""}
  {f'<div class="cmd-row"><span class="cmd-name">print brief</span><span class="cmd-desc"><code>{_e(block.get("command") or "")}</code></span></div>' if block.get("command") else ""}
</div>"""


def _research_actions(actions: list) -> str:
    if not actions:
        return ""
    body = "".join(_action_card(a, prefix="research-action") for a in actions[:6])
    return f"""
<div class="card" id="research-actions">
  <div class="card-title"><span class="icon">?</span> From Research
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{len(actions)} candidate review{'s' if len(actions) != 1 else ''}</span>
  </div>
  {body}
</div>"""


def _fresh_signals(signals: list) -> str:
    if not signals:
        return ""
    body = ""
    for row in signals[:8]:
        body += f"""
<div class="small-item">
  <span class="context-ticker">{_e(row.get("ticker") or "")}</span>
  <span class="tag t-cat">{_e(row.get("urgency") or "")}</span>
  <span>{_e(row.get("what") or "")}</span>
  <span class="small-muted">{_e(row.get("why") or row.get("detail") or "")}</span>
  {f'<span class="small-muted">When: {_e(row.get("when") or "")}</span>' if row.get("when") else ""}
</div>"""
    return f"""
<div class="card" id="fresh-signals">
  <div class="card-title"><span class="icon">*</span> Fresh signals</div>
  <div class="small-list">{body}</div>
</div>"""


def _signal_log(rows: list) -> str:
    if not rows:
        return ""
    body = ""
    for row in rows[:8]:
        title = row.get("signal") or row.get("title") or row.get("what") or row.get("summary") or ""
        ticker = row.get("ticker") or row.get("subject") or ""
        body += f"""
<div class="small-item">
  {f'<span class="context-ticker">{_e(ticker)}</span>' if ticker else ""}
  <span>{_e(title)}</span>
  <span class="small-muted">{_e(row.get("source") or row.get("note") or row.get("detail") or "")}</span>
</div>"""
    return f"""
<div class="card" id="signal-log">
  <div class="card-title"><span class="icon">*</span> Signal Log
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">watch-only</span>
  </div>
  <div class="small-list">{body}</div>
</div>"""


def _operator_hardening(block: dict) -> str:
    if not block:
        return ""
    cards = []
    specs = [
        ("freshness_downgrades", "Freshness downgrades"),
        ("stale_action_cleanup", "Stale-action cleanup"),
        ("condition_checklist", "Pre-action condition checklist"),
        ("watch_only_why", "Why not acting"),
    ]
    for key, label in specs:
        section = block.get(key) or {}
        rows = section.get("rows") or []
        line = section.get("line") or ""
        if not line and not rows:
            continue
        body = f'<div class="feedback-line">{_e(line)}</div>' if line else ""
        for row in rows[:6]:
            if not isinstance(row, dict):
                continue
            title = row.get("title") or row.get("what") or row.get("ticker") or row.get("kind") or ""
            detail = (
                row.get("judgment")
                or row.get("check")
                or row.get("why_not_acting")
                or row.get("next_step")
                or row.get("why")
                or ""
            )
            meta = " | ".join(
                str(part)
                for part in (
                    row.get("source") or row.get("kind") or "",
                    row.get("date") or row.get("evidence_date") or "",
                    row.get("state") or row.get("action_state") or "",
                )
                if part
            )
            body += f"""
<div class="small-item">
  <span class="context-ticker">{_e(row.get("ticker") or "")}</span>
  <span>{_e(title)}</span>
  {f'<span class="small-muted">{_e(detail)}</span>' if detail else ""}
  {f'<span class="small-muted">{_e(meta)}</span>' if meta else ""}
</div>"""
        cards.append(f"""
<div class="card">
  <div class="card-title"><span class="icon">!</span> {_e(label)}</div>
  <div class="small-list">{body}</div>
</div>""")
    if not cards:
        return ""
    return f"""
<div id="operator-hardening">
  {''.join(cards)}
</div>"""


def _portfolio_views_summary(portfolio_views: dict | None) -> str:
    views = (portfolio_views or {}).get("views") or {}
    if not views:
        return ""
    body = ""
    for key in ("combined", "skb", "parents"):
        view = views.get(key) or {}
        if not view:
            continue
        total = view.get("total_value")
        rows = view.get("rows") or []
        body += f"""
<div class="audit-row">
  <span class="audit-k">{_e(key)}</span>
  {_e(len(rows))} row{'s' if len(rows) != 1 else ''}{f' | total ${float(total):,.0f}' if isinstance(total, (int, float)) else ''}
</div>"""
    if not body:
        return ""
    return f"""
<div class="card" id="portfolio-views">
  <div class="card-title"><span class="icon">#</span> Portfolio views</div>
  {body}
</div>"""


def _source_audits(audits: dict) -> str:
    if not audits:
        return ""
    rows = []
    for key, label in (
        ("cloud_routines", "Cloud routines"),
        ("trigger_registry", "Trigger registry"),
        ("integration_debt", "Integration debt"),
        ("connector_evidence", "Connector evidence"),
        ("decision_dossier_coverage", "Decision dossiers"),
        ("uw_routing", "UW routing"),
        ("uw_action_runbook", "UW action runbook"),
        ("uw_endpoint_proof", "UW endpoint proof"),
        ("fundstrat", "Fundstrat intake"),
        ("notion_writeback", "Notion/writeback"),
        ("notion_collision", "Notion collision"),
    ):
        block = audits.get(key) or {}
        if not block:
            continue
        rows.append(f"""
<div class="audit-row">
  <span class="audit-k">{_e(label)}</span>{_e(block.get("line") or block.get("status") or "")}
</div>""")
    if not rows:
        return ""
    cloud = audits.get("cloud_routines") or {}
    missing = cloud.get("missing_scheduled_success") or []
    missing_html = ""
    if missing:
        names = ", ".join(_e(row.get("routine_name") or row.get("routine_id") or "") for row in missing[:6])
        more = len(missing) - min(len(missing), 6)
        missing_html = f'<div class="feedback-line">Background scheduled receipts pending: {names}{f" +{more} more" if more else ""}</div>'
    manual_support = cloud.get("manual_support_only") or []
    manual_support_html = ""
    if manual_support:
        names = ", ".join(_e(row.get("routine_name") or row.get("routine_id") or "") for row in manual_support[:6])
        more = len(manual_support) - min(len(manual_support), 6)
        manual_support_html = (
            '<div class="feedback-line">Manual support receipts only, not unattended proof: '
            f'{names}{f" +{more} more" if more else ""}</div>'
        )
    overdue = cloud.get("overdue") or []
    overdue_html = ""
    if overdue:
        lines = []
        for row in overdue[:6]:
            if not isinstance(row, dict):
                continue
            label = row.get("routine_name") or row.get("routine_id") or "Cloud routine"
            lines.append(row.get("overdue_line") or (
                f"overdue: {label}, last scheduled success "
                f"{row.get('last_scheduled_success_label') or row.get('last_ran_label') or 'never'}"
            ))
        overdue_html = f'<div class="feedback-line">Overdue cloud receipts: {"; ".join(_e(line) for line in lines)}</div>' if lines else ""
    uw = audits.get("uw_routing") or {}
    routing_rows = uw.get("rows") or []
    routing_html = ""
    if routing_rows:
        bits = []
        for row in routing_rows[:3]:
            endpoints = ", ".join(str(v) for v in (row.get("top_endpoints") or [])[:5])
            bits.append(
                f"{_e(row.get('label') or row.get('mode') or '')}: "
                f"{_e(row.get('reason') or '')}"
                f"{f' [{_e(endpoints)}]' if endpoints else ''}"
            )
        routing_html = f'<div class="feedback-line">UW next checks: {"<br>".join(bits)}</div>'
    return f"""
<div class="card" id="source-audits">
  <div class="card-title"><span class="icon">!</span> Source proof and audits</div>
  {''.join(rows)}
  {overdue_html}
  {missing_html}
  {manual_support_html}
  {routing_html}
</div>"""


def _book(holdings: list) -> str:
    if not holdings:
        return ""
    rows = ""
    for cat_block in holdings:
        cat  = _e(cat_block.get("cat", ""))
        rot  = (cat_block.get("rot") or {}).get("w", "")
        rot_cls = {"LEADING": "lead", "LAGGING": "lag"}.get(rot, "inl")
        rows += f"""<tr class="book-cat-row">
  <td colspan="4">{cat}
    {f'<span class="{rot_cls}" style="font-size:10px;margin-left:6px">{_e(rot)}</span>' if rot else ""}
  </td></tr>"""
        for pos in (cat_block.get("pos") or []):
            t   = _e(pos.get("t", ""))
            pct = _pct(pos.get("pct"))
            cv  = pos.get("cv") or "-"
            lock = pos.get("lock") or ""
            nr  = _e(pos.get("nr") or "")
            cv_cls = "cv-yes" if cv == "Promising" else ""
            lock_html = f'<span class="lock-tag">{_e(lock)}</span>' if lock else ""
            display = pos.get("conviction_display") or {}
            display_text = _e(display.get("text") or cv) if isinstance(display, dict) else _e(cv)
            note_text = _e((display.get("conflict") or pos.get("nr") or "") if isinstance(display, dict) else pos.get("nr") or "")
            rows += f"""<tr>
  <td><strong>{t}</strong>{lock_html}</td>
  <td>{pct}</td>
  <td class="{cv_cls}">{display_text}</td>
  <td style="color:#484f58;font-size:11px">{note_text[:60]}{"..." if len(note_text)>60 else ""}</td>
</tr>"""

    return f"""
<details>
  <summary style="cursor:pointer;user-select:none;padding:12px 14px;
    background:#161b22;border:1px solid #21262d;border-radius:8px;
    margin-bottom:10px;font-size:10px;font-weight:700;text-transform:uppercase;
    letter-spacing:.9px;color:#8b949e;list-style:none">
    📚 Full book (click to expand)
  </summary>
  <div class="card" style="margin-top:-2px;border-radius:0 0 8px 8px">
    <div class="book-wrap">
      <table class="book">
        <tr><th>Name</th><th>Weight</th><th>Conviction read</th><th>Why / note</th></tr>
        {rows}
      </table>
    </div>
  </div>
</details>"""


def _portfolio_book_tab(portfolio_views: dict | None) -> str:
    views = (portfolio_views or {}).get("views") or {}
    if not views:
        return ""

    caveat = _e((portfolio_views or {}).get("caveat") or "Direct account rows from the current account-position source.")
    guidance = (portfolio_views or {}).get("allocation_guidance") or {}
    snapshot = _e((portfolio_views or {}).get("snapshot_date") or "")
    sections = []
    for key, label in (
        ("combined", "Combined account portfolio"),
        ("skb", "SKB account portfolio"),
        ("parents", "Parents account portfolio"),
    ):
        view = views.get(key) or {}
        rows = view.get("rows") or []
        if not rows:
            continue
        categories = view.get("categories") or []
        category_body = ""
        for cat in categories:
            name = _e(cat.get("category") or "")
            tickers = ", ".join(str(t) for t in (cat.get("tickers") or [])[:5] if t)
            target = cat.get("working_model_target_pct")
            gap = cat.get("working_model_gap_pct")
            if isinstance(target, (int, float)) and isinstance(gap, (int, float)):
                sign = "+" if gap > 0 else ""
                model = f"model target {float(target):.1f}% | gap {sign}{float(gap):.1f}pp"
            else:
                model = ""
            cue = str(cat.get("fundstrat_cue") or "no_current_cue").replace("_", " ")
            source_date = str(cat.get("fundstrat_source_date") or "")
            fs = f"Fundstrat {cue}{f' | {source_date}' if source_date else ''}"
            reason = str(cat.get("fundstrat_reason") or "")
            category_body += f"""<tr>
  <td><strong>{name}</strong>{f'<div style="color:#484f58;font-size:10.5px">{_e(tickers)}</div>' if tickers else ""}</td>
  <td style="font-family:monospace">{_pct(cat.get("pct"))}</td>
  <td style="font-family:monospace;color:#8b949e">{_e(model)}</td>
  <td style="color:#8b949e">{_e(fs)}{f'<div style="font-size:10.5px;color:#484f58">{_e(reason)}</div>' if reason else ""}</td>
</tr>"""
        body = ""
        for row in rows:
            ticker = _e(row.get("ticker") or "")
            desc = _e(row.get("description") or "")
            account = _e(row.get("account") or "")
            owner = _e(row.get("owner") or "")
            category = _e(row.get("category") or row.get("sleeve") or "")
            try:
                shares = f"{float(row.get('shares')):,.2f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                shares = ""
            body += f"""<tr>
  <td><strong>{ticker}</strong>{f'<div style="color:#484f58;font-size:10.5px">{desc}</div>' if desc else ""}</td>
  <td>{account}{f'<div style="color:#484f58;font-size:10.5px">{owner}</div>' if owner and owner != "Multiple" else ""}</td>
  <td>{category}</td>
  <td style="font-family:monospace">{_e(shares)}</td>
  <td style="font-family:monospace">{_usd(row.get("market_value"))}</td>
  <td style="font-family:monospace">{_pct(row.get("pct"))}</td>
</tr>"""
        total = view.get("total_value")
        total_text = f" | total {_usd(total)}" if total is not None else ""
        guidance_line = _e(
            " | ".join(
                part for part in (
                    "Allocation guide: working model target + Fundstrat cue",
                    str(guidance.get("basis") or ""),
                    f"Fundstrat {guidance.get('fundstrat_source_date')}" if guidance.get("fundstrat_source_date") else "",
                )
                if part
            )
        )
        sections.append(f"""
<div class="card" style="margin-bottom:10px">
  <div class="card-title">
    <span class="icon">#</span> {_e(label)}
    <span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{len(rows)} direct row{'s' if len(rows) != 1 else ''}{total_text}</span>
  </div>
  {f'<div style="font-family:monospace;font-size:10.5px;color:#8b949e;margin-bottom:7px">{guidance_line}</div>' if guidance_line else ""}
  {f'''<div class="book-wrap" style="margin-bottom:8px">
    <table class="book">
      <tr><th>Category</th><th>Actual</th><th>Model guide</th><th>Fundstrat cue</th></tr>
      {category_body}
    </table>
  </div>''' if category_body else ""}
  <div class="book-wrap">
    <table class="book">
      <tr><th>Name</th><th>Account</th><th>Sleeve</th><th>Shares</th><th>Value</th><th>Weight</th></tr>
      {body}
    </table>
  </div>
</div>""")
    if not sections:
        return ""
    return f"""
<div class="card" style="margin-bottom:10px;border-color:#1f6feb55;background:#1f6feb08">
  <div class="card-title"><span class="icon">#</span> Account portfolio source</div>
  <div style="font-size:11.5px;color:#8b949e">{caveat}{f' Snapshot {snapshot}.' if snapshot else ''}</div>
</div>
{''.join(sections)}"""


def _book_tab(holdings: list, portfolio_views: dict | None = None, book_asof: str = "") -> str:
    """Full book as a flat table for the Book tab — no collapsible wrapper."""
    portfolio_html = _portfolio_book_tab(portfolio_views)
    if not holdings:
        holdings_html = '<div style="padding:20px;text-align:center;color:#484f58;font-size:12px">No conviction-book data in this feed build.</div>'
        return portfolio_html + holdings_html if portfolio_html else holdings_html
    rows = ""
    total_pct = 0.0
    for cat_block in holdings:
        cat  = _e(cat_block.get("cat", ""))
        rot  = (cat_block.get("rot") or {}).get("w", "")
        rot_cls = {"LEADING": "lead", "LAGGING": "lag"}.get(rot, "inl")
        rows += f'''<tr class="book-cat-row">
  <td colspan="4">{cat}
    {f'<span class="{rot_cls}" style="font-size:10px;margin-left:6px">{_e(rot)}</span>' if rot else ""}
  </td></tr>'''
        for pos in (cat_block.get("pos") or []):
            t   = _e(pos.get("t", ""))
            pct = pos.get("pct", 0)
            total_pct += float(pct or 0)
            pct_str = _pct(pct)
            cv  = pos.get("cv") or "-"
            lock = pos.get("lock") or ""
            nr  = _e(pos.get("nr") or "")
            cv_cls = "cv-yes" if cv == "Promising" else ""
            lock_html = f'<span class="lock-tag">{_e(lock)}</span>' if lock else ""
            display = pos.get("conviction_display") or {}
            display_text = _e(display.get("text") or cv) if isinstance(display, dict) else _e(cv)
            note_text = _e((display.get("conflict") or pos.get("nr") or "") if isinstance(display, dict) else pos.get("nr") or "")
            rows += f'''<tr>
  <td><strong>{t}</strong>{lock_html}</td>
  <td>{pct_str}</td>
  <td class="{cv_cls}">{display_text}</td>
  <td style="color:#484f58;font-size:11px">{note_text[:72]}{"..." if len(note_text)>72 else ""}</td>
</tr>'''
    asof_str = f'as-of {_e(book_asof)}' if book_asof else ""
    holdings_html = f'''
<div class="card" style="margin-bottom:10px">
  <div class="card-title">
    <span class="icon">📚</span> Full conviction book
    {f'<span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{asof_str}</span>' if asof_str else ""}
  </div>
  <div class="book-wrap">
    <table class="book">
      <tr><th>Name</th><th>Weight</th><th>Conviction read</th><th>Why / note</th></tr>
      {rows}
      <tr style="border-top:1px solid #30363d">
        <td style="color:#8b949e;font-size:11px">Total shown</td>
        <td style="font-family:monospace;color:#8b949e">{_pct(round(total_pct,1))}</td>
        <td colspan="2"></td>
      </tr>
    </table>
  </div>
</div>'''
    return portfolio_html + holdings_html


def _fundstrat_list_table(title: str, rows: list[dict[str, Any]], empty: str) -> str:
    if not rows:
        body = f'<div class="small-item" style="color:#d29922">{_e(empty)}</div>'
    else:
        trs = ""
        for row in rows:
            add_date = row.get("add_date") or row.get("as_of") or row.get("date") or ""
            add_price = row.get("add_price_label") or row.get("price_label") or "not captured"
            move = ""
            if row.get("report_move_pct") is not None:
                try:
                    value = float(row.get("report_move_pct"))
                    move = f"{value:+g}%"
                except (TypeError, ValueError):
                    move = str(row.get("report_move_pct") or "")
            state = (
                f"{_e(row.get('conviction') or '')}{f' / {_e(row.get('urgency') or '')}' if row.get('urgency') else ''}"
                f"{' | ' if move and (row.get('conviction') or row.get('urgency')) else ''}{_e(move)}"
                f"{' | carry over' if row.get('carry_over') else ''}"
            )
            if not state:
                state = _e(row.get("note") or row.get("name") or "")
            trs += f"""<tr>
  <td>{_e(row.get("rank") or "")}</td>
  <td><strong>{_e(row.get("ticker") or "")}</strong></td>
  <td>{_e(add_date or "date n/a")}</td>
  <td>{_e(add_price)}</td>
  <td>{state}<span class="small-muted">{_e(row.get("name") or row.get("note") or "")}</span><span class="small-muted">{_e(row.get("add_price_source") or "")}</span></td>
</tr>"""
        body = f"""<div class="book-wrap">
  <table class="book">
    <tr><th>#</th><th>Ticker</th><th>Added</th><th>Price when added</th><th>State</th></tr>
    {trs}
  </table>
</div>"""
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">#</span> {_e(title)}</div>
  {body}
</div>"""


def _load_fundstrat_bible() -> tuple[dict[str, Any], str]:
    try:
        data = json.loads(FUNDSTRAT_BIBLE_PATH.read_text(encoding="utf-8"))
        return (data if isinstance(data, dict) else {}), ""
    except FileNotFoundError:
        return {}, "fundstrat_bible.json is missing."
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"fundstrat_bible.json is unreadable: {exc}"


def _bible_rows(items: list[Any], *, as_of: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(items or [], start=1):
        if isinstance(item, dict):
            row = dict(item)
        else:
            row = {"ticker": item}
        row["rank"] = row.get("rank") or rank
        row["as_of"] = row.get("as_of") or as_of
        rows.append(row)
    return rows


def _small_items(rows: list[Any], empty: str, *, title_key: str = "ticker", body_key: str = "theme") -> str:
    if not rows:
        return f'<div class="small-item" style="color:#d29922">{_e(empty)}</div>'
    out = ""
    for row in rows:
        if isinstance(row, dict):
            title = row.get(title_key) or row.get("sector") or row.get("label") or row.get("name") or ""
            body = row.get(body_key) or row.get("why") or row.get("note") or row.get("change") or ""
            meta = row.get("status") or row.get("type") or row.get("level") or ""
        else:
            title, body, meta = str(row), "", ""
        out += f"""
<div class="small-item">
  <strong>{_e(title)}</strong>
  {f'<span class="small-muted">{_e(meta)}</span>' if meta else ''}
  {f'<span class="small-muted">{_e(body)}</span>' if body else ''}
</div>"""
    return out


def _fundstrat_bible_layers(bible: dict[str, Any], bible_error: str) -> str:
    if bible_error:
        return f"""
<div class="card">
  <div class="card-title"><span class="icon">F</span> FundStrat Bible Layers</div>
  <div class="small-item" style="color:#f85149">{_e(bible_error)}</div>
</div>"""

    sector = bible.get("sector_allocation") if isinstance(bible.get("sector_allocation"), dict) else {}
    sector_as_of = sector.get("as_of") or bible.get("deck_date") or "not checked"
    core_as_of = bible.get("core_stock_ideas_as_of") or bible.get("deck_date") or "not checked"
    what_to_own = "".join(f'<span class="tag t-cat">{_e(item)}</span>' for item in bible.get("what_to_own") or [])
    ratings = ""
    for row in sector.get("newton_rating_changes") or []:
        if not isinstance(row, dict):
            continue
        ratings += f"""
<div class="small-item">
  <strong>{_e(row.get("sector") or "")}: {_e(row.get("change") or "")}</strong>
  <span class="small-muted">{_e(row.get("why") or "")}</span>
</div>"""
    if not ratings:
        ratings = '<div class="small-item" style="color:#d29922">Newton rating changes not captured in this bible layer.</div>'

    agreement = sector.get("agreement") if isinstance(sector.get("agreement"), dict) else {}
    agreement_html = f"""
<div class="small-item">
  <strong>Lee/Newton agreement</strong>
  <span class="small-muted">Overweight: {_e(", ".join(agreement.get("both_overweight") or []) or "not captured")}</span>
  <span class="small-muted">Underweight: {_e(", ".join(agreement.get("both_underweight") or []) or "not captured")}</span>
  <span class="small-muted">{_e(agreement.get("note") or "")}</span>
</div>"""

    basket_html = _small_items(
        sector.get("june_etf_basket") or [],
        "June ETF basket not captured.",
        title_key="ticker",
        body_key="theme",
    )
    tactical_top = _small_items(
        sector.get("tactical_top3") or bible.get("tactical_top3") or [],
        "Tactical Top 3 not captured in current bible file.",
        title_key="sector",
        body_key="reason",
    )
    tactical_bottom = _small_items(
        sector.get("tactical_bottom3") or bible.get("tactical_bottom3") or [],
        "Tactical Bottom 3 not captured in current bible file.",
        title_key="sector",
        body_key="reason",
    )
    named_levels = _small_items(
        sector.get("named_levels") or bible.get("named_levels") or [],
        "Named levels not captured in current bible file.",
        title_key="ticker",
        body_key="target",
    )

    return f"""
<div class="card">
  <div class="card-title"><span class="icon">F</span> FundStrat Bible Layers</div>
  <div class="summary-line">Deck {_e(bible.get("deck_date") or "not checked")} | sector allocation {_e(sector_as_of)} | core stock ideas {_e(core_as_of)}</div>
  <div class="summary-muted" style="font-size:11px">{_e(bible.get("layers_note") or "Monthly layers are not checked.")}</div>
</div>
<div class="two-col">
  <div class="card">
    <div class="card-title"><span class="icon">1</span> Sector Allocation Layer</div>
    <div class="summary-line">As of {_e(sector_as_of)} | {_e(sector.get("source") or "source not captured")}</div>
    <div class="small-list">{ratings}{agreement_html}</div>
    <div class="card-title" style="margin-top:12px"><span class="icon">T</span> Tactical Top 3</div>
    <div class="small-list">{tactical_top}</div>
    <div class="card-title" style="margin-top:12px"><span class="icon">B</span> Tactical Bottom 3</div>
    <div class="small-list">{tactical_bottom}</div>
    <div class="card-title" style="margin-top:12px"><span class="icon">E</span> June ETF Basket</div>
    <div class="small-list">{basket_html}</div>
    <div class="card-title" style="margin-top:12px"><span class="icon">L</span> Named Levels</div>
    <div class="small-list">{named_levels}</div>
    <div class="summary-muted" style="font-size:11px;margin-top:8px">{_e(sector.get("may_basket_grade") or "")}</div>
  </div>
  <div class="card">
    <div class="card-title"><span class="icon">2</span> Core Stock Ideas Layer</div>
    <div class="summary-line">As of {_e(core_as_of)} | source {_e(bible.get("source_file") or "not captured")}</div>
    <div class="summary-muted" style="font-size:11px;margin-bottom:8px">Core lists remain the stock-pick layer until a newer stock-ideas deck lands.</div>
    <div class="tags">{what_to_own or '<span class="tag t-warn">what-to-own not captured</span>'}</div>
  </div>
</div>
{_fundstrat_list_table("Core Top 5 large cap", _bible_rows(bible.get("top5") or [], as_of=core_as_of), "Top 5 large cap is not captured in the bible file.")}
{_fundstrat_list_table("Core Top 5 SMID", _bible_rows(bible.get("top5_smid") or [], as_of=core_as_of), "Top 5 SMID is not captured in the bible file.")}
{_fundstrat_list_table("Core Bottom 5 large cap", _bible_rows(bible.get("bottom5") or [], as_of=core_as_of), "Bottom 5 large cap is not captured in the bible file.")}
{_fundstrat_list_table("Core Bottom 5 SMID", _bible_rows(bible.get("bottom5_smid") or [], as_of=core_as_of), "Bottom 5 SMID is not captured in the bible file.")}
"""


def _if_i_were_you_html(block: dict[str, Any]) -> str:
    rows = [row for row in block.get("rows") or [] if isinstance(row, dict)]
    if not rows:
        return ""
    body = ""
    for row in rows:
        body += f"""
<div class="small-item">
  <strong>#{_e(row.get("rank") or "")} {_e(row.get("label") or "")}</strong>
  <span class="small-muted">{_e(row.get("posture") or "review")} | source: {_e(row.get("source") or "")}</span>
  <span class="small-muted">Why: {_e(row.get("why") or "")}</span>
  <span class="small-muted">What I would do: {_e(row.get("what_i_would_do") or "")}</span>
</div>"""
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">></span> If I Were You</div>
  <div class="summary-line">{_e(block.get("line") or "")}</div>
  <div class="summary-muted" style="font-size:11px;margin-bottom:8px">{_e(block.get("honesty_rule") or "")}</div>
  <div class="small-list">{body}</div>
</div>"""


def _fundstrat_tab(news: dict[str, Any], if_i_were_you: dict[str, Any]) -> str:
    if not isinstance(news, dict):
        news = {}
    bible, bible_error = _load_fundstrat_bible()
    daily = news.get("daily") if isinstance(news.get("daily"), dict) else {}
    gaps = [gap for gap in news.get("gaps") or [] if isinstance(gap, dict)]
    latest_date = daily.get("latest_date") or "n/a"
    daily_count = daily.get("count") or 0
    sector_as_of = ((bible.get("sector_allocation") or {}).get("as_of") if isinstance(bible, dict) else None)
    core_as_of = bible.get("core_stock_ideas_as_of") if isinstance(bible, dict) else None
    line = (
        f"FundStrat: sector allocation {sector_as_of or 'not checked'}; "
        f"core stock ideas {core_as_of or bible.get('deck_date') or 'not checked'}; "
        f"daily calls {daily_count} latest {latest_date}."
    )
    bible_html = _fundstrat_bible_layers(bible, bible_error)
    daily_rows = ""
    for row in (daily.get("rows") or [])[:5]:
        if not isinstance(row, dict):
            continue
        daily_rows += f"""
<div class="small-item">
  <strong>{_e(row.get("ticker") or "")}</strong>
  <span class="small-muted">{_e(row.get("date") or "")} | {_e(row.get("author") or "FundStrat")} | {_e(row.get("action_implication") or "context")}</span>
  <span class="small-muted">{_e(row.get("subject") or "")}</span>
  <span class="small-muted">{_e(row.get("quote") or "")}</span>
</div>"""
    if not daily_rows:
        daily_rows = '<div class="small-item">No full-body daily FundStrat calls in this feed build.</div>'
    gap_rows = ""
    for gap in gaps:
        gap_rows += f"""
<div class="small-item">
  <strong>{_e(gap.get("key") or "gap")}</strong>
  <span class="small-muted">{_e(gap.get("line") or "")}</span>
  <span class="small-muted">Next: {_e(gap.get("next_step") or "")}</span>
</div>"""
    if not gap_rows:
        gap_rows = '<div class="small-item" style="color:#3fb950">No FundStrat gaps surfaced.</div>'
    return f"""
<div id="tab-fundstrat" style="display:none">
  <div class="card">
    <div class="card-title"><span class="icon">F</span> FundStrat</div>
    <div class="summary-line">{_e(line)}</div>
    <div class="summary-muted" style="font-size:11px">{_e(news.get("honesty_rule") or "")}</div>
  </div>
  {bible_html}
  <div class="card">
    <div class="card-title"><span class="icon">D</span> Latest Daily Notes</div>
    <div class="summary-line">Latest {_e(latest_date)} | showing latest 5 of {_e(daily_count)}</div>
    <div class="summary-muted" style="font-size:11px;margin-bottom:8px">{_e(daily.get("freshness_judgment") or "")}</div>
    <div class="small-list">{daily_rows}</div>
  </div>
  <div class="card">
    <div class="card-title"><span class="icon">!</span> FundStrat Data Gaps</div>
    <div class="small-list">{gap_rows}</div>
  </div>
  {_if_i_were_you_html(if_i_were_you if isinstance(if_i_were_you, dict) else {})}
</div>"""


_COMMANDS = [
    ("open dashboard", "Use the local HTML dashboard first; it is the default operator dashboard."),
    ("open live dashboard", "Use GitHub Pages as the published shareable dashboard."),
    ("refresh dashboard", "Run the full local refresh package, then check the HTML dashboard and JSX parity surface."),
    ("refresh book", "Pull SnapTrade account positions, validate, promote the book, and rebuild the dashboard."),
    ("review market-open packet", "Start with Key Now, Re-check Before Acting, blockers, and assumption-refresh notes."),
    ("review full book", "Use Book for full SnapTrade account rows, then the conviction book below it."),
    ("review reallocation brief", "Candidate-only add/trim plan; run same-session gates before any capital action."),
    ("run UW check set", "Use the UW action runbook for same-session price, flow, tape, and event-risk confirmation."),
    ("inspect source proof", "Check source audits, dark lanes, routine receipts, and connector evidence before trusting outputs."),
    ("resolve action memory", "Only close ANET/GOOGL/etc. after act, invalidate, defer, ignore, or miss is explicit."),
]

_SYSTEM_CHECKS = [
    ("dashboard preview", "python src/dashboard_preview_server.py --check", "Confirms local HTML dashboard, local server, and JSX validation availability."),
    ("JSX validation preview", "python src/cockpit_jsx_preview.py", "Builds tmp/cockpit_jsx_preview.html for internal parity validation."),
    ("full refresh", "python src/live_dashboard_refresh.py", "Rebuilds feed, rendered JSX, JSX preview, local dashboard, and GitHub Pages HTML."),
    ("live status", "python src/live_status.py --format text", "Fast readiness, dark-lane, source-call, and preview status."),
    ("go-live checklist", "python src/go_live_checklist.py --format text", "Operating checklist for source, dashboard, event, and review gates."),
    ("action memory", "python src/action_memory_resolve.py --review-report", "Lists open reviews and stale/due cleanup candidates."),
    ("UW runbook", "python src/uw_action_runbook.py --feed src/latest_cockpit_feed.json --format text", "Same-session check sets; instructions only until endpoint proof is captured."),
    ("SnapTrade book refresh", "python src/snaptrade_book_refresh.py --refresh-dashboard", "Preferred daily/post-trade account refresh; stages, validates, promotes, then rebuilds."),
    ("SnapTrade stage only", "python src/snaptrade_book_refresh.py --no-promote", "Pull and validate account data without changing the live book."),
]

_NAV_LINKS = [
    ("Portfolio", "https://www.notion.so/35ac50314bb681fcb792e50bf86d63f4", "source of portfolio records when Notion is used"),
    ("Live Theses", "https://www.notion.so/1286877d625f4b3eb2bedcce9bb81266", "thesis context, not live tactical proof by itself"),
    ("Research Queue", "https://www.notion.so/16b90c918e6a44049a8ba2b658943f25", "research backlog and working items"),
    ("Signal Log", "https://www.notion.so/4bf2f38e30dc4088bb314912167f052e", "watch-only context, not direct trade promotion"),
    ("Source Calls", "https://www.notion.so/7aa11ab3219d4373996e5b3e756375dd", "analyst/source-call tracking"),
    ("FS Inbox", "https://www.notion.so/354c50314bb681b5b88cf7cdb0e81731", "Fundstrat intake and review queue"),
    ("Decisions Log", "https://www.notion.so/d287d06184a74b7793ad26b42f33fd40", "explicit operator decisions"),
    ("Routines Hub", "https://www.notion.so/36ec50314bb681eb84bee946ef956048", "cloud routine reference and secrets page neighborhood"),
    ("Pilot Status", "https://www.notion.so/36dc50314bb681a5913bf0f70da71ae9", "pilot/calibration state"),
    ("GitHub repo", "https://github.com/ender-lark/enderverse", "code and published artifact source"),
]


def _commands_tab() -> str:
    cmd_rows = "".join(
        f'<div class="cmd-row"><span class="cmd-name">{_e(n)}</span><span class="cmd-desc">{_e(d)}</span></div>'
        for n, d in _COMMANDS
    )
    system_rows = "".join(
        f'<div class="cmd-row"><span class="cmd-name">{_e(name)}</span><span class="cmd-desc"><code>{_e(command)}</code><span class="context-sub">{_e(desc)}</span></span></div>'
        for name, command, desc in _SYSTEM_CHECKS
    )
    nav_rows = "".join(
        f'<div class="nav-row"><span class="nav-label"><a href="{_e(url)}" style="color:#c9d1d9">{_e(label)}</a></span>' +
        (f'<span class="nav-hint">{_e(hint)}</span>' if hint else "") + "</div>"
        for label, url, hint in _NAV_LINKS
    )
    return f"""
<div id="tab-commands" style="display:none">
  <div class="cmd-section">
    <div class="cmd-section-title">Current operating actions</div>
    {cmd_rows}
  </div>
  <div class="cmd-section">
    <div class="cmd-section-title">System checks</div>
    {system_rows}
  </div>
  <div class="cmd-section">
    <div class="cmd-section-title">Useful links</div>
    {nav_rows}
  </div>
  <div class="cmd-section">
    <div class="cmd-section-title">Dashboard surfaces</div>
    <div class="nav-row">
      <span class="nav-label">
        <a href="http://127.0.0.1:8765/dashboard_preview.html" style="color:#c9d1d9">
          Local HTML dashboard
        </a>
      </span>
      <span class="nav-hint">default operator dashboard</span>
    </div>
    <div class="nav-row">
      <span class="nav-label">
        <a href="http://127.0.0.1:8765/cockpit_jsx_preview.html" style="color:#c9d1d9">
          JSX validation surface
        </a>
      </span>
      <span class="nav-hint">internal parity/deep-dive check</span>
    </div>
    <div class="nav-row">
      <span class="nav-label">
        <a href="https://ender-lark.github.io/enderverse/" style="color:#c9d1d9">
          GitHub Pages dashboard
        </a>
      </span>
      <span class="nav-hint">published static dashboard</span>
    </div>
  </div>
</div>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def _feeder_drilldowns(sections: list[str]) -> str:
    body = "".join(section for section in sections if str(section or "").strip())
    if not body:
        return ""
    return f"""
<details class="feeder-drilldowns">
  <summary>Feeder drill-downs / source panels</summary>
  <div class="summary-muted">Collapsed because TODAY/DECIDE now owns the merged action surface; these panels remain available for audit and drill-in.</div>
  {body}
</details>"""


def generate_html(feed: dict) -> str:
    """Generate a self-contained HTML dashboard from a conviction feed dict."""

    gen_at   = _e(feed.get("generated_at") or "")
    built_at = _e(_fmt_et_stamp(feed.get("generated_at") or ""))
    btype    = _e(feed.get("build_type") or "")
    book_asof = _e(feed.get("book_as_of") or "")
    stamp_str = (feed.get("staleness") or {}).get("stamp") or ""
    compact_stamp = _compact_stamp(feed.get("staleness") or {})
    built_short = built_at[5:] if len(built_at) > 5 and built_at[4] == "-" else built_at

    # stale check
    stale_entries = (feed.get("staleness") or {}).get("stale") or []
    stale_warn = ""
    if stale_entries:
        names = ", ".join(_e(s.get("source","") if isinstance(s, dict) else s) for s in stale_entries)
        stale_warn = f'<div class="stale-warn">⚠ Stale sources: {names}</div>'

    # sections
    today_decide_payload = feed.get("today_decide") if isinstance(feed.get("today_decide"), dict) else None
    if not today_decide_payload or "cards" not in today_decide_payload:
        today_decide_payload = today_decide.build_today_decide_payload(
            feed=feed,
            weights=load_conviction_weights(),
            goal=load_goal_tunables(),
        )
    today_decide_html = today_decide.render_today_decide_html(today_decide_payload)
    held_decisions_html = _held_decisions_strip()
    summary_html = _summary_notice(feed)
    quick_html = _quick_nav(feed)
    operator_html = _operator_status(feed)
    lane_html   = _lane_status_summary(feed.get("lane_status") or {})
    feedback_html = _feedback_summary(feed.get("feedback") or {})
    hb_html     = _heartbeat(feed.get("heartbeat") or [])
    hero_html   = _hero(feed)
    actions_html = _actions(feed.get("actions") or [], feed.get("action_decision_groups") or {})
    source_conflicts_html = _source_conflicts(feed.get("source_conflicts") or {})
    today_recommendation_html = _today_recommendation_brief(feed.get("today_recommendation_brief") or {})
    market_open_packet_html = _market_open_packet(feed.get("market_open_packet") or {})
    alert_policy_html = _alert_policy(feed.get("alert_policy") or {})
    asymmetric_html = _asymmetric_opportunities(feed.get("asymmetric_opportunities") or {})
    social_watch_html = _social_watch(feed.get("social_watch") or {})
    uw_action_runbook_html = _uw_action_runbook(feed.get("uw_action_runbook") or {})
    reallocation_brief_html = _reallocation_brief(feed.get("reallocation_brief") or {})
    operator_hardening_html = _operator_hardening(feed.get("operator_hardening") or {})
    research_actions_html = _research_actions(feed.get("research_actions") or [])
    fresh_html = _fresh_signals(feed.get("fresh_signals") or [])
    signal_log_html = _signal_log(feed.get("signal_log") or [])
    portfolio_views_html = _portfolio_views_summary(feed.get("portfolio_views") or {})
    source_audits_html = _source_audits(feed.get("source_audits") or {})
    context_html = _opportunity_context(feed)
    synth_html  = _synthesis(feed.get("synthesis") or {})
    rot_html    = _rotation(feed.get("rotation") or [])
    macro_html  = _macro(feed.get("macro") or {})
    cats_html   = _catalysts(feed.get("catalysts") or [])
    res_html    = _research(feed.get("research") or {})
    lean_html   = _lean_in(feed.get("lean_in") or [])
    book_html     = _book(feed.get("holdings") or [])
    book_tab_html = _book_tab(feed.get("holdings") or [], feed.get("portfolio_views") or {}, book_asof)
    holdings_tab_html, holdings_untracked_count = _holdings_tab(feed)
    holdings_badge = (
        f'<span class="tab-badge">{holdings_untracked_count}</span>'
        if holdings_untracked_count
        else ""
    )
    fundstrat_tab_html = _fundstrat_tab(feed.get("fundstrat_news") or {}, feed.get("if_i_were_you") or {})

    cmds_html = _commands_tab()
    feeder_drilldowns_html = _feeder_drilldowns([
        held_decisions_html,
        market_open_packet_html,
        actions_html,
        source_conflicts_html,
        context_html,
        asymmetric_html,
        reallocation_brief_html,
        uw_action_runbook_html,
        research_actions_html,
    ])

    return _ascii_display_safe(_strip_trailing_ws(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>Conviction Dashboard</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">

  <div class="hdr">
    <div class="hdr-left">
      <h1>⚡ Conviction Dashboard</h1>
      <div class="stamp" title="built {built_at} · {_e(stamp_str)}">{f'built {built_short}' if built_short else ""}{f' &middot; {btype}' if btype else ""}{f' &middot; {compact_stamp}' if compact_stamp else ""}</div>
      {stale_warn}
    </div>
    <div style="text-align:right">
      {f'<div class="book-as-of">book as-of {book_asof}</div>' if book_asof else ""}
      <div style="margin-top:4px">
        <a href="." style="font-size:11px;color:#484f58">↻ refresh</a>
      </div>
    </div>
  </div>

  <div class="tab-bar">
    <button class="tab-btn active" onclick="showTab('dashboard',this)">⚡ Dashboard</button>
    <button class="tab-btn" onclick="showTab('book',this)">📚 Book</button>
    <button class="tab-btn" onclick="showTab('holdings',this)">Holdings{holdings_badge}</button>
    <button class="tab-btn" onclick="showTab('fundstrat',this)">FundStrat</button>
    <button class="tab-btn" onclick="showTab('commands',this)">📋 Commands</button>
  </div>

  <div id="tab-dashboard">
    {today_decide_html}
    {today_recommendation_html}
    {summary_html}
    {quick_html}
    {feeder_drilldowns_html}
    {alert_policy_html}
    {operator_html}
    {operator_hardening_html}
    {lane_html}
    {source_audits_html}
    {feedback_html}
    {hb_html}
    {hero_html}
    {synth_html}
    {fresh_html}
    {signal_log_html}

    <div class="two-col">
      {rot_html}
      <div>
        {macro_html}
        {cats_html}
      </div>
    </div>

    {res_html}
    {lean_html}
    {portfolio_views_html}
    {social_watch_html}
  </div>

  <div id="tab-book" style="display:none">
    {book_tab_html}
  </div>

  {holdings_tab_html}

  {fundstrat_tab_html}

  {cmds_html}

  <div class="footer">
    Conviction Dashboard &middot; auto-refreshes hourly &middot;
    <a href="https://github.com/ender-lark/enderverse">enderverse</a>
  </div>

</div>
<script>
function showTab(name, btn) {{
  document.querySelectorAll('[id^="tab-"]').forEach(d => d.style.display = 'none');
  document.getElementById('tab-' + name).style.display = '';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}
function cardSummary(card) {{
  const explicit = card.getAttribute('data-summary');
  if (explicit) return explicit;
  const pieces = Array.from(card.children)
    .filter(el => !(el.classList && (el.classList.contains('card-title') || el.classList.contains('card-mini'))))
    .map(el => (el.textContent || '').replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  const text = pieces[0] || 'Open for details.';
  return text.length > 130 ? text.slice(0, 127).trim() + '...' : text;
}}
function setupCollapsibleCards() {{
  const keepOpen = new Set([]);
  document.querySelectorAll('#tab-dashboard > .card[id]').forEach(card => {{
    if (card.dataset.collapseReady) return;
    const title = Array.from(card.children).find(el => el.classList && el.classList.contains('card-title'));
    if (!title) return;
    card.dataset.collapseReady = '1';
    card.classList.add('is-collapsible');
    const mini = document.createElement('div');
    mini.className = 'card-mini';
    mini.textContent = cardSummary(card);
    title.insertAdjacentElement('afterend', mini);
    if (!keepOpen.has(card.id)) card.classList.add('is-collapsed');
    title.addEventListener('click', () => card.classList.toggle('is-collapsed'));
  }});
}}
setupCollapsibleCards();
</script>
</body>
</html>"""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate static cockpit HTML from a feed JSON file")
    parser.add_argument("feed_json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with Path(args.feed_json).open(encoding="utf-8") as fh:
        feed = json.load(fh)
    html = generate_html(feed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
