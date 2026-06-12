#!/usr/bin/env python3
"""Tests for E2 — the decision_aging cue (apply_decision_aging + assemble_feed wiring)."""
import json
import os

import validators
from analyst_judgment import apply_decision_aging
from feed_assembler import assemble_feed
import open_opportunities as oo

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_AS_OF = "2026-05-29"  # golden_snapshot as_of (Fri)


def _bundle():
    snap = json.load(open(os.path.join(HERE, "golden_snapshot.json")))
    return {"as_of": snap["as_of"], "snapshot": snap["snapshot"], "theses": snap["theses"]}


def _aging(ticker, age_days=7, move="+12% since flag", first="2026-05-20"):
    return [{"ticker": ticker, "age_days": age_days, "first_flagged": first,
             "move_since": move, "source": "fundstrat_top5", "kind": "lean_in"}]


def _row(kind, tk, conf="Moderate", rank=1):
    return {"rank": rank, "kind": kind, "ticker": tk, "what": "x", "confidence": conf,
            "your_move": "y", "gate": None, "source": "s", "why": "w"}


def _lean_item(ticker):
    return {
        "ticker": ticker,
        "owned": True,
        "stance_gate": "open",
        "conviction": "Promising",
        "cd": "up",
        "rotation": "LEADING",
        "lean": "lean_in",
        "headline": f"{ticker}: Promising and leading",
        "evidence": [],
        "next_evidence": [],
        "opportunity_cost": "",
        "ceiling": "",
        "caveats": [],
        "freshness": f"as-of {GOLDEN_AS_OF}",
        "action": "NONE",
    }


# ── apply_decision_aging units ──

def test_apply_noop_when_empty_returns_same_object():
    acts = [_row("buy_now", "ITA", "High")]
    out = apply_decision_aging(acts, [], {})
    assert out is acts  # untouched, same object → golden-safe


def test_apply_enriches_existing_row():
    out = apply_decision_aging([_row("watch_entry", "FN")], _aging("FN"), {})
    fn = next(a for a in out if a["ticker"] == "FN")
    assert fn["age_days"] == 7 and fn["move_since"] == "+12% since flag"
    assert fn["first_flagged"] == "2026-05-20"
    assert fn["kind"] == "watch_entry"  # kind unchanged — just enriched


def test_apply_emits_standalone_row():
    out = apply_decision_aging([_row("buy_now", "ITA", "High")], _aging("FN"), {})
    fn = next((a for a in out if a["ticker"] == "FN"), None)
    assert fn and fn["kind"] == "decision_aging"
    assert fn["age_days"] == 7 and fn["move_since"] == "+12% since flag"


def test_aging_sort_boost_lifts_above_same_kind():
    # non-aging lean_in (AAA) vs aging lean_in (BBB): BBB → eff priority 2, ranks first
    out = apply_decision_aging([_row("lean_in", "AAA", rank=1), _row("lean_in", "BBB", rank=2)],
                               _aging("BBB"), {})
    ranks = {a["ticker"]: a["rank"] for a in out}
    assert ranks["BBB"] < ranks["AAA"]


def test_standalone_confidence_escalates_with_age():
    hi = apply_decision_aging([], _aging("FN", age_days=6), {})
    lo = apply_decision_aging([], _aging("FN", age_days=3), {})
    assert next(a for a in hi if a["ticker"] == "FN")["confidence"] == "High"
    assert next(a for a in lo if a["ticker"] == "FN")["confidence"] == "Moderate"


def test_emitted_row_passes_action_contract():
    row = next(a for a in apply_decision_aging([], _aging("FN"), {}) if a["ticker"] == "FN")
    assert validators._validate_action(row) == []  # Contract C clean


# ── assemble_feed integration (real golden bundle) ──

def test_feed_without_store_has_no_aging():
    feed = assemble_feed(_bundle())
    assert all(a["kind"] != "decision_aging" for a in feed["actions"])
    assert all("age_days" not in a for a in feed["actions"])
    assert validators.validate_cockpit_feed(feed) == []


def test_feed_suppresses_resolved_lean_in_review_from_today_backlog():
    store = {
        "opportunities": [],
        "history": [{
            "ticker": "ANET",
            "status": "expired",
            "source": "lean_in",
            "kind": "lean_in",
            "resolved_at": GOLDEN_AS_OF,
            "reason": "old stale review; remove from active dashboard prompts",
        }],
    }
    feed = assemble_feed(
        _bundle(),
        lean_in=[_lean_item("ANET"), _lean_item("MAGS")],
        open_opportunities=store,
    )
    assert all(item.get("ticker") != "ANET" for item in feed["lean_in"])
    assert any(item.get("ticker") == "MAGS" for item in feed["lean_in"])
    assert all(not (a.get("kind") == "lean_in" and a.get("ticker") == "ANET") for a in feed["actions"])
    assert any(a.get("kind") == "lean_in" and a.get("ticker") == "MAGS" for a in feed["actions"])
    assert validators.validate_cockpit_feed(feed) == []


def test_feed_with_store_emits_decision_aging_and_validates():
    store = oo.seed_open_opportunities(
        [{"ticker": "ZZTEST", "first_flagged": "2026-05-20", "flag_price": 100.0,
          "source": "fundstrat_top5", "kind": "lean_in"}], as_of=GOLDEN_AS_OF)
    feed = assemble_feed(_bundle(), open_opportunities=store, opp_prices={"ZZTEST": 112.0})
    zz = next((a for a in feed["actions"] if a["ticker"] == "ZZTEST"), None)
    assert zz and zz["kind"] == "decision_aging"
    assert zz["age_days"] == 7 and zz["move_since"] == "+12% since flag"
    assert validators.validate_cockpit_feed(feed) == []


def test_feed_enriches_real_action_row_FN():
    # FN is watch_entry in the golden actions; seeding it ENRICHES that row (no dup)
    store = oo.seed_open_opportunities(
        [{"ticker": "FN", "first_flagged": "2026-05-20", "flag_price": 100.0,
          "source": "fundstrat_top5", "kind": "lean_in"}], as_of=GOLDEN_AS_OF)
    feed = assemble_feed(_bundle(), open_opportunities=store, opp_prices={"FN": 112.0})
    fn = next(a for a in feed["actions"] if a["ticker"] == "FN")
    assert fn["age_days"] == 7 and fn["move_since"] == "+12% since flag"
    assert sum(1 for a in feed["actions"] if a["ticker"] == "FN") == 1
    assert validators.validate_cockpit_feed(feed) == []


def test_feed_monitor_opportunity_excluded():
    # LEU is MONITOR in the golden theses — seeding it must NOT produce a decision_aging row
    store = oo.seed_open_opportunities(
        [{"ticker": "LEU", "first_flagged": "2026-05-20", "flag_price": 190.0,
          "source": "x", "kind": "lean_in"}], as_of=GOLDEN_AS_OF)
    feed = assemble_feed(_bundle(), open_opportunities=store, opp_prices={"LEU": 210.0})
    assert all(a["kind"] != "decision_aging" for a in feed["actions"])
    for a in feed["actions"]:
        if a["ticker"] == "LEU":
            assert a.get("age_days") is None  # never aged by E2
    assert validators.validate_cockpit_feed(feed) == []


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
