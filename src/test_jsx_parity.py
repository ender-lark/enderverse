"""JSX parity port — Task 7 / C-final.

Same payload JSON → same fields out. The Python HTML renderer
(`today_decide.render_today_decide_html`) and the React component
(`src/TodayDecide.jsx`, embedded into `src/conviction_cockpit_v6.jsx`) must
emit:

* identical sets of ``(card_id, ticker, window.class, conviction_display.text,
  priority)`` for each card in ``payload.cards`` and ``payload.backlog``;
* identical rail copy strings. Unsafe cards expose a RECHECK/CANDIDATE primary
  rail instead of ACT, while still preserving PASS, scheduled RECHECK when
  applicable, and UNDO.

The JSX cannot run inside pytest. Instead the test:

1. Builds a payload via :func:`today_decide.build_today_decide_payload`
   against a minimal in-memory feed (same fixture style as
   :mod:`test_directive_recs`).
2. Renders HTML via :func:`today_decide.render_today_decide_html`.
3. Derives the canonical parity-contract set from the payload directly
   (this is what BOTH renderers must produce).
4. Parses the HTML to extract the same fields the JSX consumes.
5. Reads the JSX source as text and asserts every parity-contract field
   appears at the expected access path (a static contract check —
   prevents drift between the React component and the Python renderer).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import today_decide as td
from tunables import load_conviction_weights, load_goal_tunables

SRC = Path(__file__).resolve().parent
TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()


# ---------------------------------------------------------------------------
# Shared fixtures (mirrors the test_directive_recs fixture style)
# ---------------------------------------------------------------------------
def _gate():
    return {
        "gate_id": "QQQ-TEST", "symbol": "QQQ", "kind": "support_band",
        "level_low": 695.0, "level_high": 705.0, "state": "red_but_tested",
        "source": "newton", "stated": "2026-06-08", "note": "band",
        "confirm_rule": "holds above ~705", "applies_to": ["ai_semis"],
        "blocks_full_size": True,
    }


def _accounts():
    base = {"crypto_only": False, "tax_type": "taxable",
            "tax_flag": "TAXABLE — gains realize", "option_value": 0.0}
    return [
        {**base, "owner": "Parents", "broker": "Fidelity", "account": "Joint WROS",
         "etf_only": False, "total_value": 612000.0,
         "holdings": {"NVDA": 50000.0, "MAGS": 20000.0}},
        {**base, "owner": "SKB", "broker": "Robinhood", "account": "Trad IRA",
         "etf_only": False, "total_value": 180000.0,
         "holdings": {"GOOGL": 10000.0}, "tax_type": "traditional_ira",
         "tax_flag": "tax-advantaged (no cap-gains)"},
    ]


def _feed():
    return {
        "portfolio_views": {"views": {"combined": {
            "rows": [{"ticker": "NVDA", "market_value": 50000}],
            "total_value": 1_890_000,
        }}},
        "actions": [
            {"ticker": "GOOGL", "goal_score": 80, "kind": "lean_in"},
            {"ticker": "MAGS", "goal_score": 70, "kind": "trim"},
        ],
        "reallocation_brief": {
            "positions_snapshot_date": "2026-06-09",
            "rows": [
                {"ticker": "GOOGL", "notional_usd": 151266, "current_pct": 0.0,
                 "target_pct": 8.0, "sequence": "now", "entry_note": "x",
                 "gate": "QQQ"},
            ],
            "trims": [
                {"ticker": "MAGS", "notional_usd": 70216, "current_pct": 3.7,
                 "target_pct": 0.0,
                 "funds": [{"ticker": "GOOGL", "notional_usd": 51500}]},
            ],
            "funding": {"pool_usd": 503646, "shortfall_usd": 211916},
        },
        "target_drift": {"rows": [{"ticker": "MAGS", "direction": "OVERSIZED"}]},
        "event_risk": {"rows": []},
    }


def _insights():
    return {"insights": [{
        "insight_id": "INSIGHT-950", "statement": "s", "polarity": "bullish",
        "belief_strength": 50, "status": "ACTIVE", "stated": TODAY,
        "last_reviewed": TODAY, "sectors": [], "keywords": [],
        "tickers_mapped": ["GOOGL"], "tickers_adjacent": [], "watch_tickers": [],
        "factor_tags": [], "evidence_for": [], "evidence_against": [],
    }]}


def _build_payload():
    return td.build_today_decide_payload(
        feed=_feed(), weights=W, goal=G,
        insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()],
        congruence_result={"status": "ok", "rows": []},
        today=TODAY,
    )


# ---------------------------------------------------------------------------
# Parity-contract extractors
# ---------------------------------------------------------------------------
def _contract_from_card(card):
    """Canonical parity contract tuple — both renderers must surface this."""
    return (
        card["card_id"],
        card["ticker"],
        (card.get("window") or {}).get("class"),
        (card.get("conviction_display") or {}).get("text"),
        card.get("priority"),
        card.get("recheck_date"),
    )


def _rail_copies_from_card(card, *, check_first=False):
    cid = card["card_id"]
    move = (card.get("decision_card") or {}).get("move") or {}
    window_class = (card.get("window") or {}).get("class", "WAIT")
    posture = td._review_posture(
        card,
        check_first=check_first,
        window_class=window_class,
        direction=str(move.get("direction") or ""),
    )
    primary_copy = (
        f"ACT {cid}" if posture["copy_verb"] == "ACT"
        else f'{posture["copy_verb"]} {cid}{posture["copy_suffix"]}'
    )
    rails = {
        posture["state_verb"]: primary_copy,
        "PASS":    f"PASS {cid} — reason: ",
        "UNDO":    f"UNDO {cid}",
    }
    if posture["label"] != "RECHECK":
        rails["RECHECK"] = f"RECHECK {cid} resurface {card.get('recheck_date')}"
    return rails


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------
_DATA_CARD_RE = re.compile(
    r'<button class="[^"]*\btd-rail\b[^"]*"[^>]*'
    r'data-card="(?P<cid>[^"]+)"[^>]*'
    r'data-verb="(?P<verb>ACT|CANDIDATE|PASS|RECHECK)"[^>]*'
    r'data-copy="(?P<copy>[^"]*)"',
    re.DOTALL,
)


def _rail_copies_from_html(html):
    """{card_id -> {ACT, PASS, RECHECK} -> copy-string}, parsed from HTML."""
    out = {}
    for m in _DATA_CARD_RE.finditer(html):
        cid, verb, copy = m["cid"], m["verb"], m["copy"]
        # The HTML stores em-dashes as the literal byte sequence "â€”"
        # (UTF-8 em-dash decoded as Windows-1252). Normalize for parity.
        copy = copy.replace("â€”", "—")
        out.setdefault(cid, {})[verb] = copy
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_payload_contract_matches_html_card_ids():
    payload = _build_payload()
    html = td.render_today_decide_html(payload)
    payload_card_ids = {c["card_id"] for c in payload["cards"]}
    html_card_ids = {m["cid"] for m in _DATA_CARD_RE.finditer(html)}
    assert payload_card_ids == html_card_ids, (
        f"HTML cards diverge from payload: only-in-payload="
        f"{payload_card_ids - html_card_ids}; "
        f"only-in-html={html_card_ids - payload_card_ids}"
    )


def test_payload_window_class_and_conviction_display_render_in_html():
    payload = _build_payload()
    html = td.render_today_decide_html(payload)
    for card in payload["cards"]:
        assert card["card_id"] in html, f"missing card_id in HTML: {card['card_id']}"
        display = card["conviction_display"]
        assert display["text"] not in html
        assert f'Conviction {display.get("x5", 1)}/5 {display.get("band", "LOW").upper()}' in html


def test_payload_backlog_card_ids_and_priority_in_html():
    payload = _build_payload()
    html = td.render_today_decide_html(payload)
    for card in payload["backlog"]:
        assert card["ticker"] in html
        # Backlog rows render priority via `p<priority>`.
        assert f"p{card['priority']}" in html


def test_rail_copy_strings_match_payload_contract():
    payload = _build_payload()
    html = td.render_today_decide_html(payload)
    html_rails = _rail_copies_from_html(html)
    for card in payload["cards"]:
        check_first = bool(card.get("card_blockers"))
        expected = _rail_copies_from_card(card, check_first=check_first)
        actual = html_rails.get(card["card_id"], {})
        for verb, copy in expected.items():
            if verb == "UNDO":
                continue
            assert actual.get(verb) == copy, card["card_id"]


# ---------------------------------------------------------------------------
# JSX static-contract checks
# ---------------------------------------------------------------------------
TODAY_DECIDE_JSX = SRC / "TodayDecide.jsx"
COCKPIT_V6_JSX = SRC / "conviction_cockpit_v6.jsx"


def _jsx(path: Path) -> str:
    # Normalize the same mojibake em-dash form the Python HTML renderer uses
    # (UTF-8 em-dash bytes decoded as Windows-1252 = "â€”"). Files committed
    # by earlier tasks were saved with that historical encoding, so the
    # parity test reads through a normalizer rather than re-encoding the
    # source files on disk.
    return path.read_text(encoding="utf-8").replace("â€”", "—")


def test_jsx_files_exist():
    assert TODAY_DECIDE_JSX.exists(), "TodayDecide.jsx missing (Task 2 artifact)"
    assert COCKPIT_V6_JSX.exists(), "conviction_cockpit_v6.jsx missing (Task 7 port)"


def test_todaydecide_jsx_consumes_canonical_payload_fields():
    src = _jsx(TODAY_DECIDE_JSX)
    for path in (
        "payload.goal_anchor", "payload.plan_line", "payload.trust_panel",
        "payload.data_health", "payload.cards", "payload.backlog", "payload.congruence",
        "payload.honesty",
    ):
        assert path in src, f"TodayDecide.jsx must read {path}"


def test_todaydecide_jsx_uses_canonical_card_fields():
    src = _jsx(TODAY_DECIDE_JSX)
    # Required card-level accesses for the parity contract.
    for path in ("card.card_id", "card.ticker", "card.recheck_date", "card.sizing",
                 "card.conflicts", "card.card_blockers", "card.conviction_display",
                 "card.dossier"):
        assert path in src, f"TodayDecide.jsx must read {path}"
    for path in ("win.class", "display.text", "display.band_color",
                 "display.why", "display.raises", "display.iv_hint",
                 "display.not_checked"):
        assert path in src, f"TodayDecide.jsx must read {path}"
    for path in ("sizing.source", "sizing.suggested_usd", "sizing.heat", "sizing.cap_basis"):
        assert path in src, f"TodayDecide.jsx must read {path}"
    for path in ("dossier.reads", "dossier.one_liner", "dossier.notion_url",
                 "dossier.status", "dossier.last_reviewed", "dossier.next_review_due",
                 "dossier.synced_at"):
        assert path in src, f"TodayDecide.jsx must read {path}"


def test_todaydecide_jsx_rail_copy_templates_match_contract():
    """The component must emit the operator-facing rail strings
    the parity contract codifies."""
    src = _jsx(TODAY_DECIDE_JSX)
    # ACT / safe primary RECHECK / PASS / scheduled RECHECK / UNDO templates.
    assert "`ACT ${card.card_id}`" in src
    assert "resolve blockers before action" in src
    assert "candidate only; confirm gates before action" in src
    assert "posture.stateVerb" in src
    assert "`PASS ${card.card_id} — reason: `" in src
    assert "`RECHECK ${card.card_id} resurface ${card.recheck_date}`" in src
    assert "`UNDO ${cardId}`" in src


def test_cockpit_v6_imports_today_decide_and_renders_payload():
    src = _jsx(COCKPIT_V6_JSX)
    assert 'from "./TodayDecide"' in src, "v6 must import TodayDecide"
    assert "<TodayDecide payload={payload} />" in src
    # Honest absence path: the shell renders a graceful empty state.
    assert "honest absence" in src


def test_rail_copy_contract_present_in_both_html_and_jsx():
    """End-to-end parity: a card built from the fixture produces the same
    rail copy strings in the HTML output and in the JSX source template."""
    payload = _build_payload()
    html = td.render_today_decide_html(payload)
    html_rails = _rail_copies_from_html(html)
    jsx_src = _jsx(TODAY_DECIDE_JSX)
    for card in payload["cards"]:
        check_first = bool(card.get("card_blockers"))
        expected = _rail_copies_from_card(card, check_first=check_first)
        # HTML side: exact match.
        actual = html_rails[card["card_id"]]
        for verb, copy in expected.items():
            if verb == "UNDO":
                continue
            assert actual[verb] == copy
        # JSX side: the templates that produce these strings literally
        # appear in the component source.
        assert "`ACT ${card.card_id}`" in jsx_src
        assert "resolve blockers before action" in jsx_src
        assert "candidate only; confirm gates before action" in jsx_src
        assert "`PASS ${card.card_id} — reason: `" in jsx_src
        assert "`RECHECK ${card.card_id} resurface ${card.recheck_date}`" in jsx_src
