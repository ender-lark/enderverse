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
from pathlib import Path
from typing import Any


def _e(s: Any) -> str:
    """HTML-escape a value."""
    return _html.escape("" if s is None else str(s))


def _strip_trailing_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


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
.card-title{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.9px;color:#8b949e;margin-bottom:9px;display:flex;
  align-items:center;gap:6px}
.card-title .icon{font-size:14px}

/* ── heartbeat strip ── */
.hb{display:flex;flex-wrap:wrap;gap:5px}
.hb-badge{padding:2px 9px;border-radius:99px;font-size:10px;
  font-family:monospace;white-space:nowrap}
.ok  {background:#0d2b16;color:#3fb950;border:1px solid #238636}
.stale{background:#2b1e0a;color:#d29922;border:1px solid #9e6a03}
.down{background:#2b0d0d;color:#f85149;border:1px solid #da3633}

/* summary/export honesty */
.summary-caveat{border-left:3px solid #d29922}
.summary-line{font-size:12px;color:#c9d1d9;margin-bottom:5px}
.summary-line:last-child{margin-bottom:0}
.summary-muted{color:#8b949e}
.lane-counts{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.lane-row{display:flex;align-items:center;gap:8px;font-size:12px;
  padding:5px 0;border-bottom:1px solid #1c2128}
.lane-row:last-child{border-bottom:none}
.lane-key{font-weight:700;color:#c9d1d9;min-width:130px}
.lane-status{font-family:monospace;font-size:10px;padding:1px 7px;border-radius:99px}
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
.tab-bar{display:flex;gap:2px;margin-bottom:12px;border-bottom:1px solid #21262d;padding-bottom:0}
.tab-btn{padding:7px 14px;font-size:12px;font-weight:600;color:#8b949e;background:none;border:none;
  border-bottom:2px solid transparent;cursor:pointer;margin-bottom:-1px;letter-spacing:.3px}
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
  .hero-num{font-size:24px}
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


def _summary_notice(feed: dict) -> str:
    lane = feed.get("lane_status") or {}
    counts = lane.get("counts") or {}
    dark = int(counts.get("not_checked") or 0)
    stale = int(counts.get("stale") or 0)
    failed = int(counts.get("failed") or 0)
    actions = feed.get("actions") or []
    lines = [
        "Action-first summary view. The full JSX cockpit still has the deepest drill-downs, but today's decisions are surfaced here.",
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
    feedback = feed.get("feedback") or {}
    open_actions = (feedback.get("open_actions") or {}).get("count") or 0
    source_calls = feedback.get("source_calls") or {}
    source_call_pending = source_calls.get("pending_count") or 0
    source_call_overdue = source_calls.get("overdue_count") or 0
    lane_gaps = int(counts.get("not_checked") or 0) + int(counts.get("stale") or 0) + int(counts.get("failed") or 0)
    source_label = (
        f"{source_call_overdue} overdue"
        if source_call_overdue
        else f"{source_call_pending} pending"
        if source_call_pending
        else "clear"
    )
    return f"""
<div class="quick-nav">
  <a class="quick-link" href="#today-actions"><strong>{len(feed.get("actions") or [])}</strong> actions</a>
  <a class="quick-link" href="#operator-status"><strong>status</strong> check</a>
  <a class="quick-link" href="#asymmetric-opportunities"><strong>{_e((feed.get("asymmetric_opportunities") or {}).get("count") or 0)}</strong> asymmetry</a>
  <a class="quick-link" href="#feedback-loops"><strong>{_e(open_actions)}</strong> open reviews</a>
  <a class="quick-link" href="#lane-status"><strong>{_e(lane_gaps)}</strong> source gaps</a>
  <a class="quick-link" href="#feedback-loops"><strong>{_e(source_label)}</strong> source calls</a>
  <a class="quick-link" href="#source-audits"><strong>audit</strong> proof</a>
</div>"""


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
        row_html += f"""
<div class="lane-row">
  <span class="lane-key">{_e(label)}</span>
  <span class="lane-status ls-{_e(status)}">{_e(status.replace("_", " "))}</span>
  <span class="summary-muted">{_e(detail_txt)}</span>
</div>"""
    more = len(ordered) - len(visible)
    more_html = f'<div class="feedback-line">+{more} more lane rows in the canonical cockpit.</div>' if more > 0 else ""
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
        detail = f"{age}d open" if age is not None else "open"
        if source:
            detail += f" | {source}"
        if move:
            detail += f" | {move}"
        command = (
            f'python src/action_memory_resolve.py --ticker {ticker} '
            f'--status deferred --reason "keep watching"'
        )
        lines.append(
            f'<div class="feedback-item"><span class="context-ticker">{ticker}</span>{_e(detail)}'
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
    feedback = feed.get("feedback") or {}
    open_actions = feedback.get("open_actions") or {}
    source_calls = feedback.get("source_calls") or {}
    actions = feed.get("actions") or []
    dark = int(counts.get("not_checked") or 0)
    stale = int(counts.get("stale") or 0)
    failed = int(counts.get("failed") or 0)
    open_count = int(open_actions.get("count") or 0)
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
    schedule_wait = bool(cloud_expected and cloud_scheduled < cloud_expected and not cloud_failed)
    if source_call_fail:
        source_call_value = f"{source_call_overdue} overdue"
    elif source_call_warn:
        source_call_value = f"{source_call_observed} unscored"
    elif source_call_pending:
        source_call_value = f"{source_call_pending} pending"
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
        trigger_html = f'<div class="operator-event-trigger">Trigger: {_e(trigger)}</div>' if trigger else ""
        event_watch_html = f"""
  <div class="operator-event-watch">
    <div class="operator-label">Active event watch</div>
    <div class="operator-event-title">{_e(event_watch.get("title") or "")}</div>
    <div class="operator-event-meta">{_e(meta)}</div>
    {trigger_html}
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
    status = (
        "FAIL"
        if failed or source_call_fail
        else "WARN"
        if dark or stale or open_count or source_call_warn or live_config_missing
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
    build_cls = "operator-fail" if build_blockers else "operator-pass"
    wait_parts = []
    source_waits = dark + (1 if live_config_missing else 0)
    if source_waits:
        wait_parts.append(f"{source_waits} source wait{'s' if source_waits != 1 else ''}")
    if schedule_wait:
        wait_parts.append(f"cloud proof {cloud_scheduled}/{cloud_expected}")
    if open_count:
        wait_parts.append(f"{open_count} review{'s' if open_count != 1 else ''}")
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
    lane_value = ", ".join(lane_detail) if lane_detail else "clear"
    return f"""
<div class="card" id="operator-status">
  <div class="card-title"><span class="icon">!</span> Operator status
    <span class="{cls}" style="font-size:11px;margin-left:auto">{status}</span>
  </div>
  <div class="operator-grid">
    <a class="operator-pill" href="#today-actions"><div class="operator-label">Today actions</div><div class="operator-value">{_e(action_count)}</div></a>
    <a class="operator-pill" href="#feedback-loops"><div class="operator-label">Open reviews</div><div class="operator-value {_e('operator-warn' if open_count else 'operator-pass')}">{_e(open_count)}</div></a>
    <a class="operator-pill" href="#lane-status"><div class="operator-label">Source lanes</div><div class="operator-value {_e('operator-warn' if lane_detail else 'operator-pass')}">{_e(lane_value)}</div></a>
    <a class="operator-pill" href="#feedback-loops"><div class="operator-label">Source calls</div><div class="operator-value {_e('operator-fail' if source_call_fail else 'operator-warn' if source_call_warn else 'operator-pass')}">{_e(source_call_value)}</div></a>
    <a class="operator-pill" href="#operator-status"><div class="operator-label">Live fetch</div><div class="operator-value {_e('operator-warn' if live_config_missing else 'operator-pass')}">{_e(f'{live_configured}/{live_config_total}' if live_config_total else 'unknown')}</div></a>
    <a class="operator-pill" href="#operator-status"><div class="operator-label">Build blockers</div><div class="operator-value {_e(build_cls)}">{_e(build_blockers)}</div></a>
  </div>
  <div class="operator-readiness"><strong class="{_e(build_cls)}">{_e(build_state)}</strong> | {_e(wait_text)}</div>
  <div class="operator-command">python src/completion_audit.py --format text</div>
  <div class="operator-command">python src/go_live_checklist.py --format text</div>
  {live_config_html}
  {event_watch_html}
  <div class="operator-command">python src/sudden_event_refresh.py --title &quot;&lt;event headline&gt;&quot; --channels &quot;oil,rates,volatility&quot; --tickers &quot;XOP,TNX&quot; --why &quot;&lt;why exposure, hedges, or new-buy timing changes&gt;&quot; --trigger &quot;&lt;what confirms or changes the risk&gt;&quot;</div>
</div>"""


def _hero(hero: dict) -> str:
    needs = hero.get("needs_you") or {}
    count = needs.get("count", 0)
    items = needs.get("items") or []
    book_count = (hero.get("hero") or {}).get("count", 0)
    leading = ", ".join((hero.get("hero") or {}).get("leading_sleeves") or [])
    leading_str = f" | leading: {_e(leading)}" if leading else ""

    hero_items_html = ""
    for it in items:
        reason = _e(it.get("reason", "").replace("_", " ").title())
        detail = _e(it.get("detail", ""))
        note   = _e(it.get("note") or it.get("label") or "")
        hero_items_html += f'<div class="hero-item"><strong>{detail}</strong> - {reason} | {note}</div>'

    return f"""
<div class="hero">
  <div class="hero-row">
    <div class="hero-num">{count}</div>
    <div>
      <div style="font-size:13px;font-weight:600;color:#f0f6fc">
        thing{"s" if count != 1 else ""} need{"" if count != 1 else "s"} you
      </div>
      <div class="hero-label">{book_count} names on the book{leading_str}</div>
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
    impact = _e(a.get("goal_impact") or "")
    source = _e(a.get("source") or "")
    freshness = _e(a.get("freshness") or "")
    freshness_judgment = a.get("freshness_judgment") or {}
    why_matters = _e(a.get("why_this_matters") or a.get("why_it_moves_goal") or "")
    gate = _gate_tag(a.get("gate"))
    cls = "action-act" if a.get("action_state") == "ACT_NOW" else "action-watch"
    meta = ""
    for value, css in (
        (state, "t-cat"),
        (label, "t-cat"),
        (capital, "t-gate-a"),
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
    if channels or capital or a.get("goal_score") is not None:
        score = a.get("goal_score")
        score_txt = f" | score {score}/100" if score is not None else ""
        detail_lines.append(
            f"<strong>Goal/capital:</strong> {_e(channels or 'n/a')} "
            f"| capital {_e(capital or 'n/a')}{_e(score_txt)}"
        )
    if missing:
        detail_lines.append(f"<strong>Missing/re-check:</strong> {_e(missing)}")
    details = ""
    if detail_lines:
        details = f"""
  <details class="action-details">
    <summary>Why this matters</summary>
    <div class="action-detail-body">{'<br>'.join(detail_lines)}</div>
  </details>"""

    return f"""
<div class="action {cls}" id="{_e(prefix)}-{_e(rank)}">
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
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{direction}'
                f'{f"<span class=\"context-sub\">{summary}</span>" if summary else ""}</div>'
            )
        columns.append(("Prospects", rows))

    radar_rows = (feed.get("radar") or [])[:3]
    if radar_rows:
        rows = []
        for row in radar_rows:
            ticker = _e(row.get("ticker") or "")
            direction = _e(row.get("direction") or "")
            author = _e(row.get("author") or "")
            detail = " | ".join(part for part in (author, _e(row.get("date") or "")) if part)
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{direction}'
                f'{f"<span class=\"context-sub\">{detail}</span>" if detail else ""}</div>'
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
            rows.append(
                f'<div class="context-row"><span class="context-ticker">{ticker}</span>{direction} {strength}'
                f'{f"<span class=\"context-sub\">{_e(types)}</span>" if types else ""}</div>'
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
<div class="card">
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
        ("connector_evidence", "Connector evidence"),
        ("fundstrat", "Fundstrat intake"),
        ("notion_writeback", "Notion/writeback"),
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
        missing_html = f'<div class="feedback-line">Unproven scheduled routines: {names}{f" +{more} more" if more else ""}</div>'
    return f"""
<div class="card" id="source-audits">
  <div class="card-title"><span class="icon">!</span> Source proof and audits</div>
  {''.join(rows)}
  {missing_html}
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
            rows += f"""<tr>
  <td><strong>{t}</strong>{lock_html}</td>
  <td>{pct}</td>
  <td class="{cv_cls}">{_e(cv)}</td>
  <td style="color:#484f58;font-size:11px">{nr[:60]}{"..." if len(nr)>60 else ""}</td>
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
        <tr><th>Name</th><th>Weight</th><th>Conviction</th><th>Read</th></tr>
        {rows}
      </table>
    </div>
  </div>
</details>"""




def _book_tab(holdings: list, book_asof: str = "") -> str:
    """Full book as a flat table for the Book tab — no collapsible wrapper."""
    if not holdings:
        return '<div style="padding:20px;text-align:center;color:#484f58;font-size:12px">No holdings data in this feed build.</div>'
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
            rows += f'''<tr>
  <td><strong>{t}</strong>{lock_html}</td>
  <td>{pct_str}</td>
  <td class="{cv_cls}">{_e(cv)}</td>
  <td style="color:#484f58;font-size:11px">{nr[:72]}{"..." if len(nr)>72 else ""}</td>
</tr>'''
    asof_str = f'as-of {_e(book_asof)}' if book_asof else ""
    return f'''
<div class="card" style="margin-bottom:10px">
  <div class="card-title">
    <span class="icon">📚</span> Full book
    {f'<span style="font-size:10px;color:#484f58;font-weight:400;margin-left:auto">{asof_str}</span>' if asof_str else ""}
  </div>
  <div class="book-wrap">
    <table class="book">
      <tr><th>Name</th><th>Weight</th><th>Conviction</th><th>Read</th></tr>
      {rows}
      <tr style="border-top:1px solid #30363d">
        <td style="color:#8b949e;font-size:11px">Total shown</td>
        <td style="font-family:monospace;color:#8b949e">{_pct(round(total_pct,1))}</td>
        <td colspan="2"></td>
      </tr>
    </table>
  </div>
</div>'''


_COMMANDS = [
    ("dash / dashboard",   "Live conviction cockpit — gist-first, instant render"),
    ("pulse",              "What changed since last build — FS Inbox, Signal Log, catalysts, synthesis delta"),
    ("top 5",              "Today's ranked action list with gate badges"),
    ("deepdive [ticker]",  "Full due-diligence on a stock — or just start talking about it"),
    ("reallocate",         "Full-book reallocation candidates (trim ETF wrappers → single names)"),
    ("fs digest",          "Process a Fundstrat note — act / watch / no-action verdict"),
    ("queue",              "Research Queue Working items, ranked by priority + age"),
    ("theses",             "Live Theses ACTIVE/MONITOR breakdown, flags no-stop names"),
    ("nav",                "Tappable Notion links — all key pages, instant, no fetch"),
    ("reconcile [Nd]",     "Triage open chat threads — DONE / OPEN-MATERIAL / OPEN-MINOR / DEAD"),
    ("morning scan",       "Manual full world sweep — weekends / ad-hoc re-sweep"),
    ("menu",               "This command list (auto-shows on short opening messages)"),
    ("fresh run",          "Full cockpit rebuild from live sources (manual fallback only)"),
]

_SYSTEM_CHECKS = [
    ("build audit", "python src/completion_audit.py --format text", "Current build blockers vs source/cloud/review waits"),
    ("go-live check", "python src/go_live_checklist.py --format text", "Checklist for dashboard, source, event, and review readiness"),
    ("live status", "python src/live_status.py --format text", "Fast current dashboard/source status"),
]

_NAV_LINKS = [
    ("📊 Portfolio",        "https://www.notion.so/35ac50314bb681fcb792e50bf86d63f4", ""),
    ("📈 Live Theses",      "https://www.notion.so/1286877d625f4b3eb2bedcce9bb81266", "type: theses"),
    ("🎯 Trade Rationales", "https://www.notion.so/c854a4187c7a438ea9e31ed9137cb448", ""),
    ("🚨 Exit Triggers",    "https://www.notion.so/b739b1210584411fabab06ad87bf5603", ""),
    ("📡 Signal Log",       "https://www.notion.so/4bf2f38e30dc4088bb314912167f052e", ""),
    ("📞 Source Calls",     "https://www.notion.so/7aa11ab3219d4373996e5b3e756375dd", ""),
    ("📧 FS Inbox",         "https://www.notion.so/354c50314bb681b5b88cf7cdb0e81731", "type: fs digest"),
    ("📚 Research Queue",   "https://www.notion.so/16b90c918e6a44049a8ba2b658943f25", "type: queue"),
    ("📖 Decisions Log",    "https://www.notion.so/d287d06184a74b7793ad26b42f33fd40", ""),
    ("💹 Trade Outcomes",   "https://www.notion.so/ab0817a74c654694ba834089febe1c74", ""),
    ("🧠 Synthesis Log",    "https://www.notion.so/c414bc41c37248d09df2591ab160fe0f", ""),
    ("🛰️ Routines Hub",     "https://www.notion.so/36ec50314bb681eb84bee946ef956048", ""),
    ("🛸 Pilot Status",     "https://www.notion.so/36dc50314bb681a5913bf0f70da71ae9", ""),
    ("🏗️ Command Center",   "https://www.notion.so/36dc50314bb68163ad59dc2fbfac6cad", ""),
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
    <div class="cmd-section-title">Claude commands</div>
    {cmd_rows}
  </div>
  <div class="cmd-section">
    <div class="cmd-section-title">System checks</div>
    {system_rows}
  </div>
  <div class="cmd-section">
    <div class="cmd-section-title">Notion quick links</div>
    {nav_rows}
  </div>
  <div class="cmd-section">
    <div class="cmd-section-title">GitHub Pages dashboard</div>
    <div class="nav-row">
      <span class="nav-label">
        <a href="https://ender-lark.github.io/enderverse/" style="color:#c9d1d9">
          ⚡ Live dashboard
        </a>
      </span>
      <span class="nav-hint">auto-refreshes hourly</span>
    </div>
  </div>
</div>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def generate_html(feed: dict) -> str:
    """Generate a self-contained HTML dashboard from a conviction feed dict."""

    gen_at   = _e(feed.get("generated_at") or "")
    btype    = _e(feed.get("build_type") or "")
    book_asof = _e(feed.get("book_as_of") or "")
    stamp_str = (feed.get("staleness") or {}).get("stamp") or ""

    # stale check
    stale_entries = (feed.get("staleness") or {}).get("stale") or []
    stale_warn = ""
    if stale_entries:
        names = ", ".join(_e(s.get("source","")) for s in stale_entries)
        stale_warn = f'<div class="stale-warn">⚠ Stale sources: {names}</div>'

    # sections
    summary_html = _summary_notice(feed)
    quick_html = _quick_nav(feed)
    operator_html = _operator_status(feed)
    lane_html   = _lane_status_summary(feed.get("lane_status") or {})
    feedback_html = _feedback_summary(feed.get("feedback") or {})
    hb_html     = _heartbeat(feed.get("heartbeat") or [])
    hero_html   = _hero(feed.get("hero") or {})
    actions_html = _actions(feed.get("actions") or [], feed.get("action_decision_groups") or {})
    asymmetric_html = _asymmetric_opportunities(feed.get("asymmetric_opportunities") or {})
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
    book_tab_html = _book_tab(feed.get("holdings") or [], book_asof)

    cmds_html = _commands_tab()

    return _ascii_display_safe(_strip_trailing_ws(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>Conviction Cockpit</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">

  <div class="hdr">
    <div class="hdr-left">
      <h1>⚡ Conviction Cockpit</h1>
      <div class="stamp">
        {f'built {gen_at[:16].replace("T"," ")} ET' if gen_at else ""}
        {f' · {btype}' if btype else ""}
      </div>
      {f'<div class="stamp">{_e(stamp_str)}</div>' if stamp_str else ""}
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
    <button class="tab-btn active" onclick="showTab('dashboard',this)">⚡ Cockpit</button>
    <button class="tab-btn" onclick="showTab('book',this)">📚 Book</button>
    <button class="tab-btn" onclick="showTab('commands',this)">📋 Commands</button>
  </div>

  <div id="tab-dashboard">
    {summary_html}
    {quick_html}
    {actions_html}
    {operator_html}
    {asymmetric_html}
    {research_actions_html}
    {context_html}
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
  </div>

  <div id="tab-book" style="display:none">
    {book_tab_html}
  </div>

  {cmds_html}

  <div class="footer">
    Conviction Cockpit · auto-refreshes hourly ·
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
