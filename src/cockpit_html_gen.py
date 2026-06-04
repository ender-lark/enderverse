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
import html as _html
from typing import Any


def _e(s: Any) -> str:
    """HTML-escape a value."""
    return _html.escape(str(s or ""))


def _pct(v: Any) -> str:
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return str(v or "—")


def _rel(v: Any) -> str:
    try:
        f = float(v) * 100
        sign = "+" if f >= 0 else ""
        return f"{sign}{f:.1f}%"
    except Exception:
        return "—"


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
.action{border-radius:6px;padding:10px 12px;margin-bottom:7px;
  background:#1c2128;border-left:3px solid #30363d}
.action-header{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.rank-badge{font-size:10px;font-family:monospace;color:#484f58;
  min-width:22px}
.ticker-tag{font-size:14px;font-weight:700;color:#f0f6fc}
.action-what{font-size:12px;color:#8b949e;margin-left:auto}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}
.tag{display:inline-block;padding:1px 7px;border-radius:99px;
  font-size:10px;font-family:monospace}
.t-cat   {background:#0d2339;color:#58a6ff}
.t-conf  {background:#0d2b16;color:#3fb950}
.t-gate-g{background:#0d2b16;color:#3fb950}
.t-gate-a{background:#2b1e0a;color:#d29922}
.t-gate-r{background:#2b0d0d;color:#f85149}
.action-move{font-size:12px;color:#8b949e;line-height:1.4}

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
        last = _e(layer.get("last_run") or "—")
        title = f"{name} · {last}" + (f" · {note}" if note else "")
        badges += f'<span class="hb-badge {cls}" title="{title}">{name}</span>'
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">📡</span> System layers</div>
  <div class="hb">{badges}</div>
</div>"""


def _hero(hero: dict) -> str:
    needs = hero.get("needs_you") or {}
    count = needs.get("count", 0)
    items = needs.get("items") or []
    book_count = (hero.get("hero") or {}).get("count", 0)
    leading = ", ".join((hero.get("hero") or {}).get("leading_sleeves") or [])
    leading_str = f" · leading: {_e(leading)}" if leading else ""

    hero_items_html = ""
    for it in items:
        reason = _e(it.get("reason", "").replace("_", " ").title())
        detail = _e(it.get("detail", ""))
        note   = _e(it.get("note") or it.get("label") or "")
        hero_items_html += f'<div class="hero-item"><strong>{detail}</strong> — {reason} · {note}</div>'

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


def _actions(actions: list) -> str:
    if not actions:
        return ""
    rows = ""
    for a in actions:
        rank     = a.get("rank", "")
        ticker   = _e(a.get("ticker", ""))
        what     = _e(a.get("what", ""))
        conf     = _e(a.get("confidence", ""))
        move     = _e(a.get("your_move", ""))
        kind_raw = (a.get("kind") or "").replace("_", " ").title()
        gate     = _gate_tag(a.get("gate"))

        rows += f"""
<div class="action">
  <div class="action-header">
    <span class="rank-badge">#{rank}</span>
    <span class="ticker-tag">{ticker}</span>
    <span class="action-what">{what}</span>
  </div>
  <div class="tags">
    <span class="tag t-cat">{_e(kind_raw)}</span>
    <span class="tag t-conf">conf: {conf}</span>
    {gate}
  </div>
  {f'<div class="action-move">{move}</div>' if move else ""}
</div>"""
    return f"""
<div class="card">
  <div class="card-title"><span class="icon">⚡</span> Today&#39;s actions</div>
  {rows}
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
  {f'<div class="s-label">24–48h delta</div><div class="s-body">{delta}</div>' if delta else ""}
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
            cv  = pos.get("cv") or "—"
            lock = pos.get("lock") or ""
            nr  = _e(pos.get("nr") or "")
            cv_cls = "cv-yes" if cv == "Promising" else ""
            lock_html = f'<span class="lock-tag">{_e(lock)}</span>' if lock else ""
            rows += f"""<tr>
  <td><strong>{t}</strong>{lock_html}</td>
  <td>{pct}</td>
  <td class="{cv_cls}">{_e(cv) if cv != "—" else "—"}</td>
  <td style="color:#484f58;font-size:11px">{nr[:60]}{"…" if len(nr)>60 else ""}</td>
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
    hb_html     = _heartbeat(feed.get("heartbeat") or [])
    hero_html   = _hero(feed.get("hero") or {})
    actions_html = _actions(feed.get("actions") or [])
    synth_html  = _synthesis(feed.get("synthesis") or {})
    rot_html    = _rotation(feed.get("rotation") or [])
    macro_html  = _macro(feed.get("macro") or {})
    cats_html   = _catalysts(feed.get("catalysts") or [])
    res_html    = _research(feed.get("research") or {})
    lean_html   = _lean_in(feed.get("lean_in") or [])
    book_html   = _book(feed.get("holdings") or [])

    return f"""<!DOCTYPE html>
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
      <div class="book-as-of">book as-of {book_asof}</div>
      <div style="margin-top:4px">
        <a href="." style="font-size:11px;color:#484f58">↻ refresh</a>
      </div>
    </div>
  </div>

  {hb_html}
  {hero_html}
  {actions_html}
  {synth_html}

  <div class="two-col">
    {rot_html}
    <div>
      {macro_html}
      {cats_html}
    </div>
  </div>

  {res_html}
  {lean_html}
  {book_html}

  <div class="footer">
    Conviction Cockpit · auto-refreshes hourly ·
    <a href="https://github.com/ender-lark/enderverse">enderverse</a>
  </div>

</div>
</body>
</html>"""
