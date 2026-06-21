#!/usr/bin/env python3
"""
options_surface.py — the producer that turns a set of conviction names into feed-ready,
ranked, defined-risk options ideas plus an honest roll-up.

This is the thin glue the SURFACING layer (cockpit / Today-Decide / conversation) consumes so it
never has to re-derive anything: give it a bundle of UW data per name + the conviction/account
context, and it returns the ideas (strongest ACT first) + a summarize_run() roll-up that is never
silent. Mirrors the repo's producer/bundle pattern (uw_opportunity_scan): the live UW MCP pulls
happen UPSTREAM (routine / chat session) and feed the bundle; this core is pure + token-safe.

CONSUMES (never reimplements):
  • options_uw_adapter.normalize_market / normalize_chain / assemble_subject
  • options_expression.build_expression / summarize_run
  • options_shadow_log.append_rejections (IO, via persist_shadow_log)

Engine + scope: src/options_expression.py,
docs/codex_tasks/options_opportunity_surfacing_scope_2026_06_18.md.

DESIGN NOTES
  • LEAD WITH THE STRONGEST: ideas are ranked ACT > WAIT > WATCH > SKIP, then by edge
    (expected_move − break-even) so the loudest real opportunity sorts to the top. Ranking is a
    transparent key, not a hidden score; the render still leads with each idea's own `move`.
  • DATA-GAP HONESTY: a name with no chain pulled becomes a WATCH "re-pull the chain", NOT a false
    "illiquid" SKIP — we never let missing data masquerade as a real read (dark-lane discipline).
  • NEVER SILENT: the roll-up always speaks (summarize_run's honest-empty headline).
  • PURE CORE + SEPARATE IO: surface_options() does no file IO; persist_shadow_log() is the thin
    writer the routine calls to log near-misses for later dial-tuning.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Optional

import options_expression as oe
import options_shadow_log as osl
import options_uw_adapter as ad

SOURCE = "options_surface"

# disposition sort order (loudest first) — a transparent ranking key, not a score
_DISP_ORDER = {"ACT": 0, "WAIT": 1, "WATCH": 2, "SKIP": 3}
# within a disposition tier: prefer the cleaner/cheaper expression of the STRONGER conviction.
_IV_QUALITY_RANK = {"cheap": 0, "normal": 1, "unknown": 2, "rich": 3}   # cheap long premium beats rich
_STRUCTURE_RANK = {"long_call": 0, "long_put": 0, "debit_call_spread": 1, "debit_put_spread": 1}  # clean long beats spread
# broad ETFs are a TIEBREAKER (single-name conviction sorts first), never a gate — a strong ETF sleeve still ACTs.
BROAD_ETFS = frozenset({
    "SPY", "QQQ", "IWM", "DIA", "SMH", "SOXX", "IGV", "XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI",
    "XLU", "XLB", "XLRE", "XLC", "GDX", "GDXJ", "MAGS", "GRNY", "GRNJ", "VOLT", "IVES", "IBIT", "ETHA",
    "ARKK", "VOO", "VTI", "EEM", "EFA", "TLT", "HYG",
})


def _is_broad_etf(ticker) -> bool:
    return bool(ticker) and str(ticker).upper() in BROAD_ETFS


def _edge(idea: dict) -> float:
    """Expected move beyond the break-even (bigger = more room to be right). Missing -> sinks."""
    em, be = idea.get("expected_move_pct"), idea.get("break_even_pct")
    if em is None or be is None:
        return -1e9
    return em - abs(be)


def _rank_key(idea: dict):
    """Transparent multi-key, conviction-first, disposition ALWAYS leading (a real ACT is never demoted
    below a WAIT). Within a tier: strongest conviction → cheapest-IV expression (cheap long > rich spread)
    → clean long > spread → single-name > broad ETF → wider edge → ticker (deterministic). No hidden score."""
    cs = idea.get("conviction_strength")
    cs = cs if isinstance(cs, (int, float)) else 0.0
    return (
        _DISP_ORDER.get(idea.get("disposition"), 9),
        -cs,
        _IV_QUALITY_RANK.get(idea.get("iv_environment"), 2),
        _STRUCTURE_RANK.get(idea.get("structure"), 0),
        1 if _is_broad_etf(idea.get("ticker")) else 0,
        -_edge(idea),
        idea.get("ticker") or "",
    )


def _data_gap(ticker: str, as_of, reason: str) -> dict:
    """A non-actionable hold for a name we couldn't read — honest, never a fake 'illiquid'."""
    return {
        "schema_version": oe.SCHEMA_VERSION, "ticker": ticker, "as_of": as_of,
        "disposition": "WATCH", "move": None, "when": None, "timing": None, "tripwire_note": None,
        "structure": None, "legs": None, "iv_environment": "unknown", "iv_tax_brake": False,
        "brake_reason": None, "why": None, "the_catch": None, "filter_reason": reason, "glossary": {},
        "honesty": "A 100% loss of the premium is a realistic outcome — this is sized for that.",
    }


def surface_options(bundle: Optional[dict], *, conviction_lookup: Optional[dict] = None,
                    account: Optional[dict] = None, cfg: Optional[dict] = None,
                    as_of: Optional[str] = None, generated_at: Optional[str] = None) -> dict:
    """Pure producer: a bundle {ticker: {"screener": <raw>, "chain": <raw>}} + conviction/account
    context -> {source, as_of, generated_at, ideas (ranked), summary}. No network, no file IO.

    conviction_lookup maps TICKER -> {direction, conviction_intact, thesis_break,
    thesis_horizon_days, recent_options_loss}. account -> {portfolio_value, open_premium_at_risk}.
    """
    # Coerce every external arg: a truthy NON-dict must degrade to empty, never raise. The producer's
    # contract is to NEVER go silent — one malformed upstream payload can't be allowed to abort the
    # batch (that would invert the anti-passivity north star). `or {}` only catches falsy, not e.g. a
    # stray list/str/scalar, so we isinstance-coerce.
    bundle = bundle if isinstance(bundle, dict) else {}
    conviction_lookup = conviction_lookup if isinstance(conviction_lookup, dict) else {}
    account = account if isinstance(account, dict) else None
    ideas: list[dict] = []
    for raw_tk, data in bundle.items():
        tk = str(raw_tk).strip().upper()
        if not tk:
            continue
        a = as_of
        try:
            data = data if isinstance(data, dict) else {}
            screener = data.get("screener")
            chain = data.get("chain")
            market = ad.normalize_market(screener) if isinstance(screener, (dict, list)) else {}
            a = as_of or market.get("as_of")
            contracts = (ad.normalize_chain(chain, spot=market.get("spot"), as_of=a)
                         if isinstance(chain, (dict, list)) else [])
            if not contracts:
                if not isinstance(chain, (dict, list)):
                    reason = "No option chain was pulled for this name — re-pull the chain."
                elif not ad._arr(chain):
                    reason = "Option chain came back empty — re-pull the chain."
                else:
                    reason = "Option chain pulled but no usable contracts parsed — re-pull the chain."
                ideas.append(_data_gap(tk, a, reason))
                continue
            conv = conviction_lookup.get(tk) or conviction_lookup.get(raw_tk)
            conv = conv if isinstance(conv, dict) else None
            subject = ad.assemble_subject(ticker=tk, market=market, chain_contracts=contracts,
                                          conviction=conv, account=account, as_of=a)
            ideas.append(oe.build_expression(subject, cfg=cfg))
        except Exception as exc:  # noqa: BLE001 — a single bad name must NEVER abort the whole batch
            ideas.append(_data_gap(tk, a, f"Couldn't read this name's options data ({type(exc).__name__}) — re-pull."))
    ideas.sort(key=_rank_key)
    # envelope as_of: fall back to the ideas' own date when the caller omits it (the realistic routine
    # path, where as_of lives only inside each screener row) so the run is never mislabelled None.
    env_as_of = as_of or next((i.get("as_of") for i in ideas if i.get("as_of")), None)
    summary = oe.summarize_run(ideas, cfg=cfg)
    return {
        "source": SOURCE,
        "as_of": env_as_of,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "ideas": ideas,
        "summary": summary,
    }


def persist_shadow_log(result: Optional[dict], *, path: Any = osl.DEFAULT_PATH,
                       as_of: Optional[str] = None) -> int:
    """Append every near-miss/hold from a surface_options() result to the shadow log (IO).
    Returns the count written. The routine calls this so we can later tune dials from real misses."""
    result = result or {}
    return osl.append_rejections(result.get("ideas"), path=path, as_of=as_of or result.get("as_of"))


# ════════════════════════════════════════════════════════════════════════════
# SURFACE  — turn a surface_options() result into LOUD, plain-language renders.
# Doctrine: LEAD WITH THE MOVE (line 1 = idea["move"]); a score never masquerades as a
# recommendation; every term defined inline via idea["glossary"]; risk loud (max-loss in
# $ AND %); honest-empty NEVER silent; freshness stamped; a sized idea is never an order.
# ════════════════════════════════════════════════════════════════════════════

# Disposition -> cockpit promotion score. ORDERING METADATA ONLY — this decides where a row
# sorts; it is NEVER shown as the recommendation (the recommendation is always idea["move"]).
# ACT / WAIT-with-flip clear the cockpit's score>=80 promotion bar; WATCH / SKIP do not.
_PROMO_SCORE = {"ACT": 88, "WAIT": 80, "WATCH": 60, "SKIP": 40}

# Stances meaning "hold for awareness, do NOT add" — an ACT is demoted so we never yell a
# buy on a sleeve we're not adding to (honors 'Respect MONITOR no-add').
_NO_ADD_STANCES = {"MONITOR", "BURNED", "TRIM", "EXIT"}

# Conservative fallback only (the case_file caller passes is_equity); obvious non-single-name
# macros with no optionable single-name chain.
_MACRO_FALLBACK = {"DXY", "US10Y", "US02Y", "US30Y", "WTI", "BRENT", "USDJPY", "EURUSD"}


def _num(x) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _money(x) -> str:
    x = _num(x)
    if x is None:
        return "?"
    return f"${x:,.0f}" if abs(x) >= 100 else f"${x:,.2f}"


def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _summary(surface: Optional[dict]) -> dict:
    return (surface or {}).get("summary") or {}


def _headline(surface: Optional[dict]) -> Optional[str]:
    return _summary(surface).get("headline")


def loud_ideas(surface: Optional[dict]) -> list[dict]:
    """The names that earn a LOUD top-line row: an ACT, or a WAIT that carries a named
    flip-condition (a 'wait' that knows exactly what turns it into an act). Order preserved
    from the producer's ranking (ACT already sorts first)."""
    ideas = (surface or {}).get("ideas") or []
    acts = [i for i in ideas if i.get("disposition") == "ACT"]
    waits = [i for i in ideas if i.get("disposition") == "WAIT"
             and (i.get("timing") or {}).get("flip_condition")]
    return acts + waits


def _closest_call(surface: Optional[dict]) -> Optional[dict]:
    near = _summary(surface).get("near_misses") or []
    if not near:
        return None
    n = near[0]
    return {"ticker": n.get("ticker"),
            "reason": n.get("filter_reason") or n.get("the_catch"),
            "structure": n.get("structure"), "when": n.get("when")}


def _risk_line(idea: dict) -> Optional[str]:
    """Max-loss in $ AND % — risk loud. Falls back to the engine's plain size note."""
    ml, pct = idea.get("max_loss_dollars"), idea.get("max_loss_pct_book")
    if ml is not None and pct is not None:
        return f"Most you can lose: {_money(ml)} ({_num(pct):.1f}% of book)"
    if ml is not None:
        return f"Most you can lose (one contract): {_money(ml)}"
    if idea.get("size_note"):
        return f"Size: {idea['size_note']}"
    return None


def _detail_bits(idea: dict) -> list[str]:
    bits = []
    iv = idea.get("iv_environment")
    if iv and iv != "unknown":
        bits.append(f"IV {iv}")
    if idea.get("expected_move_pct") is not None:
        bits.append(f"expected move {idea['expected_move_pct']}%")
    if idea.get("break_even_pct") is not None:
        bits.append(f"break-even {idea['break_even_pct']}%")
    return bits


def _idea_text_block(idea: dict) -> list[str]:
    """One idea, plain text, LEADING WITH THE MOVE; checklist + glossary one tap deep."""
    out: list[str] = [f"▶ {idea.get('move') or '(no sized move — see the catch below)'}"]  # LINE 1
    flip = (idea.get("timing") or {}).get("flip_condition")
    if idea.get("when"):
        out.append(f"  When: {idea['when']}" + (f" (flips when {flip})" if flip else ""))
    if idea.get("why"):
        out.append(f"  Why: {idea['why']}")
    if idea.get("the_catch"):
        out.append(f"  ⚠ The catch: {idea['the_catch']}")
    rl = _risk_line(idea)
    if rl:
        out.append(f"  {rl}")
    if idea.get("tripwire_note"):
        out.append(f"  ⚠ {idea['tripwire_note']}")
    # ── one tap deep ──
    bits = _detail_bits(idea)
    if bits:
        out.append("  — checklist: " + " · ".join(bits))
    gl = idea.get("glossary") or {}
    if gl:
        out.append("  — plain terms: " + "; ".join(f"{t} = {d}" for t, d in gl.items()))
    if idea.get("honesty"):
        out.append(f"  — {idea['honesty']}")
    return out


def render_surface_text(surface: Optional[dict]) -> str:
    """The whole block as plain text — for in-conversation recall and any text channel.
    Leads with the decisions; falls to an honest-empty line that names the closest call;
    never silent; always stamped with freshness (honesty rail)."""
    surface = surface or {}
    lines = ["\U0001f3af OPTIONS EXPRESSION"]
    loud = loud_ideas(surface)
    if loud:
        for idea in loud:
            lines += _idea_text_block(idea)
            lines.append("")
    else:
        lines.append(_headline(surface)
                     or "No conviction name had a clean options setup. Nothing hidden.")
        cc = _closest_call(surface)
        if cc and cc.get("ticker"):
            lines.append(f"Closest call — {cc['ticker']}: {cc.get('reason') or 'waiting on a trigger'}")
    lines.append(f"(as of {surface.get('as_of')}; pulled {surface.get('generated_at')})")
    return "\n".join(lines).rstrip()


def render_options_block_html(surface: Optional[dict]) -> str:
    """A LOUD 'OPTIONS EXPRESSION' HTML block for the Today-Decide surface. Always renders a
    labeled container (never silent); the move leads each row; checklist + glossary sit in a
    <details> one tap deep; max-loss shows in $ AND %. Self-contained inline styles so it needs
    none of today_decide's shared CSS — a caller appends it as-is."""
    title = ('<div class="td-section-title" style="font-size:14px;letter-spacing:.04em;'
             'margin:14px 0 6px 0;color:#e2e8f0">\U0001f3af OPTIONS EXPRESSION</div>')
    if not surface:
        body = ('<div class="td-opt" style="color:#94a3b8;font-size:13px">'
                'options expression: not checked this build — no conviction names were screened.</div>')
        return f'<div class="td-options">{title}{body}</div>'

    parts = [f'<div class="td-options">{title}']
    loud = loud_ideas(surface)
    if loud:
        for idea in loud:
            parts.append(_idea_html_block(idea))
    else:
        headline = _esc(_headline(surface)
                        or "No conviction name has a clean, liquid options setup today. Nothing hidden.")
        parts.append(f'<div class="td-opt" style="color:#cbd5e1;font-size:13px;margin:4px 0">{headline}</div>')
        cc = _closest_call(surface)
        if cc and cc.get("ticker"):
            parts.append('<div class="td-opt" style="color:#94a3b8;font-size:12px">'
                         f'closest call — <b>{_esc(cc["ticker"])}</b>: {_esc(cc.get("reason"))}</div>')
    parts.append('<div class="td-opt-stamp" style="color:#64748b;font-size:11px;margin-top:6px">'
                 f'as of {_esc(surface.get("as_of"))} · pulled {_esc(surface.get("generated_at"))} · '
                 'a sized idea, never an order — you place the trade.</div>')
    parts.append("</div>")
    return "".join(parts)


def _idea_html_block(idea: dict) -> str:
    move = _esc(idea.get("move") or "(no sized move — see the catch)")
    rows = [f'<div class="td-opt-move" style="font-size:15px;font-weight:700;color:#e2e8f0;'
            f'margin:8px 0 2px 0">▶ {move}</div>']  # LEAD WITH THE MOVE
    flip = (idea.get("timing") or {}).get("flip_condition")
    if idea.get("when"):
        when = _esc(idea["when"]) + (f' <span style="color:#94a3b8">(flips when {_esc(flip)})</span>' if flip else "")
        rows.append(f'<div style="font-size:12px;color:#cbd5e1">When: {when}</div>')
    if idea.get("why"):
        rows.append(f'<div style="font-size:12px;color:#cbd5e1">Why: {_esc(idea["why"])}</div>')
    if idea.get("the_catch"):
        rows.append(f'<div style="font-size:12px;color:#fbbf24">⚠ The catch: {_esc(idea["the_catch"])}</div>')
    rl = _risk_line(idea)
    if rl:
        rows.append(f'<div style="font-size:12px;color:#f87171;font-weight:600">{_esc(rl)}</div>')
    if idea.get("tripwire_note"):
        rows.append(f'<div style="font-size:12px;color:#f87171">⚠ {_esc(idea["tripwire_note"])}</div>')
    det = []
    bits = _detail_bits(idea)
    if bits:
        det.append('<div style="font-size:12px;color:#cbd5e1;margin-top:4px">' + _esc(" · ".join(bits)) + "</div>")
    for term, defn in (idea.get("glossary") or {}).items():
        det.append(f'<div style="font-size:11px;color:#94a3b8"><b>{_esc(term)}</b>: {_esc(defn)}</div>')
    if idea.get("honesty"):
        det.append(f'<div style="font-size:11px;color:#94a3b8;margin-top:3px">{_esc(idea["honesty"])}</div>')
    if det:
        rows.append('<details style="margin:4px 0 2px 0"><summary style="font-size:11px;color:#94a3b8;'
                    'cursor:pointer">checklist &amp; plain-English terms</summary>' + "".join(det) + "</details>")
    return ('<div class="td-opt-card" style="border-left:3px solid #475569;padding:2px 0 2px 10px;'
            'margin:8px 0">' + "".join(rows) + "</div>")


def cockpit_feed_block(surface: Optional[dict]) -> dict:
    """A feed-ready 'options_expression' block mirroring asymmetric_opportunities' row shape
    (extended for derivatives) so the existing cockpit promotion can read it. `action` carries
    the sized MOVE so the row leads with the decision; `score` is promotion-ordering metadata
    ONLY. We RETURN the dict; we never write the shared feed file (a build output)."""
    surface = surface or {}
    rows = [_feed_row(i) for i in loud_ideas(surface)]
    status = "has_data" if rows else ("checked" if surface.get("ideas") else "pending")
    return {
        "status": status,
        "count": len(rows),
        "as_of": surface.get("as_of"),
        "generated_at": surface.get("generated_at"),
        "line": _headline(surface),
        "rows": rows,
        "honest_empty": _summary(surface).get("honest_empty", True),
        "closest_call": _closest_call(surface),
        "_score_note": ("`score` is promotion-ordering metadata only — never a recommendation; "
                        "the call is the `action`/move."),
    }


def _feed_row(idea: dict) -> dict:
    return {
        "ticker": idea.get("ticker"),
        "source": SOURCE,
        "score": _PROMO_SCORE.get(idea.get("disposition"), 40),  # promotion ordering ONLY
        "disposition": idea.get("disposition"),
        "action": idea.get("move"),            # LEAD WITH THE MOVE
        "reason": idea.get("why"),
        "evidence": idea.get("the_catch"),
        "decay_window": idea.get("when"),
        "timing": idea.get("timing"),
        "implied_structure": idea.get("structure"),
        "legs": idea.get("legs"),
        "risk_amount_usd": idea.get("max_loss_dollars"),
        "risk_pct_book": idea.get("max_loss_pct_book"),
        "the_catch": idea.get("the_catch"),
        "tripwire_note": idea.get("tripwire_note"),
        "iv_environment": idea.get("iv_environment"),
        "expected_move_pct": idea.get("expected_move_pct"),
        "break_even_pct": idea.get("break_even_pct"),
        "glossary": idea.get("glossary"),
        "honesty": idea.get("honesty"),
    }


# ── no-add rail (surface-level): never yell ACT on a MONITOR/trim/exit sleeve ──
def _apply_no_add_rail(idea: dict, conviction: Optional[dict]) -> dict:
    if not isinstance(idea, dict):
        return idea
    stance = str((conviction or {}).get("stance") or "").upper()
    if stance in _NO_ADD_STANCES and idea.get("disposition") == "ACT":
        idea = dict(idea)
        note = (f"This name is on {stance} — we don't add to this sleeve. "
                "Shown for awareness, not as a buy.")
        idea["disposition"] = "WATCH"
        idea["filter_reason"] = note
        idea["timing"] = {"verdict": "WATCH", "label": "Awareness only (no-add sleeve)",
                          "flip_condition": "the name comes off the no-add list (thesis re-promoted)"}
        idea["when"] = idea["timing"]["label"]
    return idea


def apply_no_add_rails(surface: Optional[dict], conviction_lookup: Optional[dict]) -> dict:
    """Return a copy of the surface with the no-add rail applied per name, then re-ranked.
    Optional helper for the producer-fed cockpit/today_decide path (the conviction context the
    producer drops is re-applied here). Recall applies the rail inline."""
    surface = dict(surface or {})
    lookup = conviction_lookup if isinstance(conviction_lookup, dict) else {}
    new_ideas = []
    for idea in surface.get("ideas") or []:
        tk = idea.get("ticker")
        conv = lookup.get(tk) or lookup.get(str(tk).upper() if tk else None)
        new_ideas.append(_apply_no_add_rail(idea, conv if isinstance(conv, dict) else None))
    new_ideas.sort(key=_rank_key)
    surface["ideas"] = new_ideas
    surface["summary"] = oe.summarize_run(new_ideas)
    return surface


# ════════════════════════════════════════════════════════════════════════════
# RECALL  — in-conversation, single ticker
# ════════════════════════════════════════════════════════════════════════════
def recall_for_ticker(ticker: str, *, screener=None, chain=None,
                      conviction: Optional[dict] = None, account: Optional[dict] = None,
                      as_of: Optional[str] = None, cfg: Optional[dict] = None) -> dict:
    """When a ticker is mentioned/assembled in conversation, surface its live options idea.
    Read-only: this never writes the shadow log (a casual lookup must not log a dial-tuning
    miss — the routine path calls persist_shadow_log explicitly). Applies the no-add rail.
    Returns {idea, surface, text} — `text` is the ready-to-speak plain-language block."""
    tk = str(ticker).upper()
    surface = surface_options({tk: {"screener": screener, "chain": chain}},
                              conviction_lookup=({tk: conviction} if conviction else None),
                              account=account, as_of=as_of, cfg=cfg)
    ideas = list(surface.get("ideas") or [])   # copy: never mutate the producer's returned list
    if ideas:
        ideas[0] = _apply_no_add_rail(ideas[0], conviction)
        surface["ideas"] = ideas
        surface["summary"] = oe.summarize_run(ideas)
    idea = ideas[0] if ideas else None
    return {"idea": idea, "surface": surface, "text": render_surface_text(surface)}


def build_options_lane(ticker: str, *, is_equity: bool = True, screener=None, chain=None,
                       conviction: Optional[dict] = None, account: Optional[dict] = None,
                       as_of: Optional[str] = None, cfg: Optional[dict] = None) -> dict:
    """A case_file-shaped 'options' lane for the Ticker-dossier session to attach.

    TODO(coordinate: case_file.py owner / Ticker-dossier session) — G6 options recall hook.
    case_file.py is owned by another session and must NOT be edited from here. To wire this,
    the owning session adds ONE line in build_case_file() (≈ src/case_file.py:482-488, after the
    verdict/earliest_record/decisions lanes, before `return base`):

        base["options"] = options_surface.build_options_lane(
            ticker, is_equity=base["is_equity"],
            screener=<live get_stock_screener row>, chain=<live get_options_chain>,
            conviction=<from verdict/thesis>, account=<book>, as_of=today)

    The lane follows case_file's honesty contract: blocks=False, alert_eligible=False ALWAYS (an
    options idea expresses an existing conviction; it never originates or blocks a decision).
    Macro/index tickers (is_equity=False) skip with an honest 'n/a' rule, matching case_file's
    macro short-circuit. v1 keeps options a separate labeled query — no silent merge of
    underlier/wrapper/options.
    """
    tk = str(ticker).upper()
    rail = {"blocks": False, "alert_eligible": False}
    if not is_equity or _looks_macro(tk):
        return {"status": "skipped",
                "line": "Options expression n/a for a macro / index / crypto proxy.",
                "idea": None,
                "honesty_rule": "options lane is skipped for non-single-name tickers (no chain to express).",
                **rail}
    if screener is None and chain is None:
        return {"status": "data_gap",
                "line": f"No options chain pulled for {tk} — ask me to pull the live chain.",
                "idea": None,
                "honesty_rule": "options lane needs a live screener + chain bundle; nothing was pulled.",
                **rail}
    rec = recall_for_ticker(tk, screener=screener, chain=chain, conviction=conviction,
                            account=account, as_of=as_of, cfg=cfg)
    idea = rec["idea"] or {}
    has_move = bool(idea.get("move"))
    return {
        "status": "ok" if has_move else "empty",
        "line": idea.get("move") or _headline(rec["surface"]),
        "idea": rec["idea"],
        "summary": _summary(rec["surface"]),
        "text": rec["text"],
        "honesty_rule": ("an options idea expresses an existing conviction — it never originates, "
                         "blocks, or alerts a decision on its own."),
        **rail,
    }


def _looks_macro(tk: str) -> bool:
    return str(tk).upper() in _MACRO_FALLBACK


# ─────────────────────────────────── self-test ───────────────────────────────
def _self_test() -> int:
    """Real UW shapes (NVDA, 2026-06-18) through the full producer; plus a data-gap name."""
    fails: list[str] = []

    def chk(c, label):
        if not c:
            fails.append(label)

    screener = {"result": [{
        "ticker": "NVDA", "iv_rank": "23.6105", "iv30d": "0.358", "implied_move_perc": "0.070000",
        "next_earnings_date": "2026-08-26", "close": "210.69", "prev_close": "204.65",
        "week_52_high": "236.54", "week_52_low": "142.03", "date": "2026-06-18"}]}
    chain = {"states": [
        {"option_symbol": "NVDA260821C00205000", "strike": "205", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4152, "delta": 0.5979, "theo": 17.4998, "open_interest": 10123, "volume": 1326},
        {"option_symbol": "NVDA260821C00210000", "strike": "210", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4091, "delta": 0.5432, "theo": 14.7750, "open_interest": 18035, "volume": 3825},
        {"option_symbol": "NVDA260821C00220000", "strike": "220", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4007, "delta": 0.4325, "theo": 10.2750, "open_interest": 28817, "volume": 3258}],
        "price_data": {"price": "210.69"}}

    bundle = {
        "NVDA": {"screener": screener, "chain": chain},
        "ZZZ": {"screener": {"result": [{"ticker": "ZZZ", "close": "50", "prev_close": "49", "date": "2026-06-18"}]}},  # no chain -> data gap
    }
    conv = {"NVDA": {"direction": "bullish", "conviction_intact": True, "thesis_horizon_days": 60}}
    res = surface_options(bundle, conviction_lookup=conv, account={"portfolio_value": 100000},
                          as_of="2026-06-18", generated_at="2026-06-18T21:50:00Z")

    chk(res["source"] == SOURCE and res["generated_at"] == "2026-06-18T21:50:00Z", "envelope")
    chk(len(res["ideas"]) == 2, "two ideas produced")
    chk(res["ideas"][0]["ticker"] == "NVDA" and res["ideas"][0]["disposition"] == "ACT",
        "strongest (NVDA ACT) ranked first")
    chk(res["ideas"][0]["structure"] == "long_call" and res["ideas"][0]["move"].startswith("Buy "),
        "NVDA leads with a buy move")
    zzz = [i for i in res["ideas"] if i["ticker"] == "ZZZ"][0]
    chk(zzz["disposition"] == "WATCH" and "re-pull" in (zzz["filter_reason"] or ""),
        "no-chain name -> honest data-gap WATCH, not a fake illiquid")
    chk(res["summary"]["act"] and res["summary"]["headline"], "roll-up surfaces the ACT, never silent")

    # determinism: same inputs -> byte-identical (sans generated_at)
    res2 = surface_options(bundle, conviction_lookup=conv, account={"portfolio_value": 100000},
                           as_of="2026-06-18", generated_at="2026-06-18T21:50:00Z")
    chk(res2["ideas"] == res["ideas"], "deterministic ideas")

    # empty bundle -> still an honest, non-silent roll-up
    empty = surface_options({}, generated_at="x")
    chk(empty["ideas"] == [] and empty["summary"]["honest_empty"] and empty["summary"]["headline"],
        "empty bundle -> honest-empty roll-up")

    # shadow log persistence: only the non-ACT (ZZZ) is logged
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "shadow.jsonl"
        n = persist_shadow_log(res, path=p)
        chk(n == 1 and osl.open_misses(p)[0]["ticker"] == "ZZZ", "shadow log records only the near-miss")

    # never raises on malformed input — one bad name can't abort the batch (anti-passivity contract)
    bad = surface_options({"X": [1, 2, 3], "Y": {"screener": 5, "chain": True}, "Z": {"chain": {"states": []}}},
                          conviction_lookup="junk", account=7, generated_at="x")
    chk(len(bad["ideas"]) == 3 and all(i["disposition"] == "WATCH" for i in bad["ideas"]),
        "malformed inputs -> honest WATCH, never raises")
    chk(surface_options([1, 2, 3], generated_at="x")["ideas"] == [], "non-dict bundle -> empty, no raise")

    if fails:
        print("options_surface self-test: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("options_surface self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
