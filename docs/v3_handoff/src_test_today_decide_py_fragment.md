# src/test_today_decide.py (C5 exact fragment)

**C5 EXACT FRAGMENT.** Write to `src/test_today_decide.py`. **10 tests**, written against the verbatim archived modules + the `today_decide.py` sibling fragment. Covers every Task-2 required test: section present, card max, PCRA exclusion, MAGS conflict chip, pace isolation.

```python
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from today_decide import (
    build_today_decide_payload,
    detect_source_conflicts,
    render_today_decide_html,
)
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()

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
        {**base, "owner": "Parents", "broker": "Schwab", "account": "PCRA Trust",
         "etf_only": True, "total_value": 368000.0,
         "holdings": {"MAGS": 19710.0}, "tax_type": "traditional_ira",
         "tax_flag": "tax-advantaged (no cap-gains)"},
        {**base, "owner": "SKB", "broker": "Robinhood", "account": "Trad IRA",
         "etf_only": False, "total_value": 180000.0,
         "holdings": {"GOOGL": 10000.0}, "tax_type": "traditional_ira",
         "tax_flag": "tax-advantaged (no cap-gains)"},
    ]

def _insights():
    return {"insights": [{
        "insight_id": "INSIGHT-950", "statement": "s", "polarity": "bullish",
        "belief_strength": 50, "status": "ACTIVE", "stated": TODAY,
        "last_reviewed": TODAY, "sectors": [], "keywords": [],
        "tickers_mapped": ["GOOGL"], "tickers_adjacent": [], "watch_tickers": [],
        "factor_tags": [], "evidence_for": [], "evidence_against": [],
    }]}

def _feed():
    return {
        "portfolio_views": {"views": {"combined": {
            "rows": [{"ticker": "NVDA", "market_value": 50000}],
            "total_value": 1890000,
        }}},
        "actions": [
            {"ticker": "GOOGL", "goal_score": 80, "kind": "lean_in",
             "what": "FS lean-in: GOOGL"},
            {"ticker": "MAGS", "goal_score": 70, "kind": "lean_in",
             "what": "FS lean-in: hold/add MAGS"},
        ],
        "reallocation_brief": {
            "positions_snapshot_date": "2026-06-09",
            "rows": [
                {"ticker": "GOOGL", "notional_usd": 151266, "current_pct": 0.0,
                 "target_pct": 8.0, "sequence": "now", "entry_note": "x", "gate": "QQQ"},
                {"ticker": "NVDA", "notional_usd": 56609, "current_pct": 5.0,
                 "target_pct": 8.0},
            ],
            "trims": [
                {"ticker": "MAGS", "notional_usd": 70216, "current_pct": 3.7,
                 "target_pct": 0.0,
                 "funds": [{"ticker": "NVDA", "notional_usd": 51500}]},
            ],
            "funding": {"pool_usd": 503646, "shortfall_usd": 211916},
        },
        "target_drift": {"rows": [{"ticker": "MAGS", "direction": "OVERSIZED"}]},
        "event_risk": {"rows": []},
    }

def _congruence(flagged=True):
    return {
        "status": "ok", "total_value": 1890000.0, "flag_threshold_named_pct": 1.0,
        "rows": [{
            "insight_id": "INSIGHT-950", "statement": "s", "belief_strength": 50,
            "stale": False, "named_pct": 0.23, "combined_pct": 0.23,
            "flagged": flagged,
            "flag_note": "STRONGEST BELIEF · SMALLEST EXPOSURE" if flagged else "",
            "line": "named $4,268 (0.23%) — TSM",
        }],
        "flagged_ids": ["INSIGHT-950"] if flagged else [],
    }

def _payload(goal=None, congruence_result=None, tmp_path=None):
    return build_today_decide_payload(
        feed=_feed(), weights=W, goal=goal or G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()], uw_states={}, entry_zones={},
        congruence_result=congruence_result or _congruence(),
        dispositions_path=(tmp_path / "none.jsonl") if tmp_path else "_no_dispositions_.jsonl",
        today=TODAY,
    )

def test_payload_builds_and_goal_anchor_math():
    p = _payload()
    ga = p["goal_anchor"]
    assert ga["book_value"] == 1890000.0 and ga["fi_target"] == 3000000.0
    assert ga["pct_to_target"] == 63.0 and ga["gap_usd"] == 1110000.0
    assert "display-only" in ga["pace_line"]
    assert p["plan_line"]["positions_as_of"] == "2026-06-09"

def test_pace_is_display_only_and_isolated():
    p1 = _payload()
    g2 = copy.deepcopy(G)
    g2["fi_target"] = 6_000_000
    p2 = _payload(goal=g2)
    pri1 = [c["priority"] for c in p1["cards"] + p1["backlog"]]
    pri2 = [c["priority"] for c in p2["cards"] + p2["backlog"]]
    assert pri1 == pri2  # fi_target moved, ranking untouched
    assert p1["goal_anchor"]["pace_line"] != p2["goal_anchor"]["pace_line"]
    html = render_today_decide_html(p1)
    assert html.count("display-only") == 1  # pace appears once, in the anchor only

def test_html_renders_header_and_built_date():
    html = render_today_decide_html(_payload())
    assert "TODAY — DECIDE" in html and f"built {TODAY}" in html
    assert 'id="today-decide"' in html

def test_card_count_respects_daily_max():
    p = _payload()
    assert len(p["cards"]) <= G["daily_card_max"]
    assert len(p["cards"]) + len(p["backlog"]) == 3

def test_pcra_exclusion_rendered_on_stock_buys():
    html = render_today_decide_html(_payload())
    assert "ETF-ONLY" in html and "PCRA" in html

def test_mags_source_conflict_chip_renders():
    p = _payload()
    mags = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "MAGS"][0]
    assert mags["conflicts"] and mags["conflicts"][0]["with"] == "lean_in lane"
    html = render_today_decide_html(p)
    assert "SOURCE-CONFLICT" in html and "hold/add MAGS" in html

def test_rails_carry_exact_copy_payloads():
    p = _payload()
    html = render_today_decide_html(p)
    cid = p["cards"][0]["card_id"]
    assert f'data-copy="ACT {cid}"' in html
    assert f'data-copy="PASS {cid} — reason: "' in html
    assert f"resurface 2026-06-15" in html  # TODAY + recheck_default_days(5)
    assert "UNDO " in html  # second-tap undo path in the script

def test_backlog_is_collapsed_in_details():
    html = render_today_decide_html(_payload())
    assert "<details><summary>Backlog (" in html

def test_congruence_strip_flag_and_not_checked():
    flagged_html = render_today_decide_html(_payload())
    assert "\U0001f6a9" in flagged_html and "INSIGHT-950" in flagged_html
    nc = _payload(congruence_result={"status": "not_checked",
                                     "reason": "no positions cache", "rows": []})
    nc_html = render_today_decide_html(nc)
    assert "congruence: not checked" in nc_html

def test_honesty_footer_lists_all_lanes():
    p = _payload()
    assert p["honesty"]["dispositions"].startswith("none logged")
    html = render_today_decide_html(p)
    assert "not_checked" in html and "institutional" in html and "dispositions" in html
```