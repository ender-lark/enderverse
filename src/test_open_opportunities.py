#!/usr/bin/env python3
"""Tests for open_opportunities.py (E5 — the open-opportunity persistence store)."""
import json
import os
import tempfile

import open_opportunities as oo

TODAY = "2026-06-02"


# ── helpers / dates ──

def test_age_business_days_basic():
    # Thu 5/28 → Tue 6/2 = Fri, Mon, Tue = 3 trading days (weekend excluded)
    assert oo.age_business_days("2026-05-28", TODAY) == 3
    assert oo.age_business_days(TODAY, TODAY) == 0          # same day
    assert oo.age_business_days("2026-06-03", TODAY) is None  # future flag
    assert oo.age_business_days("garbage", TODAY) is None     # bad date


def test_compute_move_since():
    assert oo.compute_move_since(580.0, 650.0) == "+12% since flag"
    assert oo.compute_move_since(100.0, 97.0) == "-3% since flag"
    assert oo.compute_move_since(100.0, 100.0) == "+0% since flag"
    assert oo.compute_move_since(None, 100.0) == ""    # no flag price
    assert oo.compute_move_since(0, 100.0) == ""       # bad flag price


# ── load / save ──

def test_load_missing_and_malformed():
    assert oo.load_open_opportunities("/no/such/path.json")["opportunities"] == []
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "bad.json")
        open(p, "w").write("{ not json")
        assert oo.load_open_opportunities(p)["opportunities"] == []


def test_save_roundtrip():
    store = oo.seed_open_opportunities(
        [{"ticker": "FN", "first_flagged": "2026-05-28", "flag_price": 580.0}], as_of=TODAY)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.json")
        oo.save_open_opportunities(store, p)
        back = oo.load_open_opportunities(p)
    assert back["opportunities"][0]["ticker"] == "FN"


# ── seed ──

def test_seed_skips_bad_rows():
    store = oo.seed_open_opportunities([
        {"ticker": "FN", "first_flagged": "2026-05-28"},
        {"ticker": "NODATE"},               # no first_flagged → skipped
        {"first_flagged": "2026-05-28"},    # no ticker → skipped
        "junk",                              # not a dict → skipped
    ], as_of=TODAY)
    tks = [o["ticker"] for o in store["opportunities"]]
    assert tks == ["FN"]


# ── writer: add / refresh / drop ──

def _seed_fn():
    return oo.seed_open_opportunities(
        [{"ticker": "FN", "first_flagged": "2026-05-28", "flag_price": 580.0, "source": "fundstrat_top5"}],
        as_of="2026-05-28")


def test_new_candidate_added_with_flag_price_and_date():
    ns, dropped = oo.update_open_opportunities(
        {"opportunities": []},
        todays_candidates=[{"ticker": "AVGO", "kind": "lean_in", "source": "lean_in"}],
        held_tickers=set(), prices={"AVGO": 1400.0}, as_of=TODAY)
    opp = next(o for o in ns["opportunities"] if o["ticker"] == "AVGO")
    assert opp["first_flagged"] == TODAY and opp["flag_price"] == 1400.0
    assert opp["status"] == "open" and dropped == []


def test_existing_open_refreshed_preserves_first_flag():
    store = _seed_fn()
    ns, _ = oo.update_open_opportunities(
        store, todays_candidates=[{"ticker": "FN", "kind": "lean_in"}],
        held_tickers=set(), prices={"FN": 650.0}, as_of=TODAY)
    fn = next(o for o in ns["opportunities"] if o["ticker"] == "FN")
    assert fn["first_flagged"] == "2026-05-28"   # original flag date preserved
    assert fn["flag_price"] == 580.0             # original flag price preserved
    assert fn["last_seen"] == TODAY              # last_seen advanced


def test_acted_when_now_held_is_dropped():
    store = _seed_fn()
    ns, dropped = oo.update_open_opportunities(
        store, todays_candidates=[], held_tickers={"FN"}, prices={}, as_of=TODAY)
    assert all(o["ticker"] != "FN" for o in ns["opportunities"])
    assert dropped and dropped[0]["ticker"] == "FN" and dropped[0]["status"] == "acted"
    assert ns["history"][0]["ticker"] == "FN" and ns["history"][0]["status"] == "acted"


def test_invalidated_is_dropped():
    store = _seed_fn()
    ns, dropped = oo.update_open_opportunities(
        store, todays_candidates=[], held_tickers=set(), prices={}, as_of=TODAY,
        invalidations={"FN"})
    assert all(o["ticker"] != "FN" for o in ns["opportunities"])
    assert dropped[0]["status"] == "invalidated"
    assert ns["history"][0]["status"] == "invalidated"


def test_explicit_resolution_ignored_deferred_missed_persist_to_history():
    store = oo.seed_open_opportunities([
        {"ticker": "FN", "first_flagged": "2026-05-28"},
        {"ticker": "AVGO", "first_flagged": "2026-05-28"},
        {"ticker": "MU", "first_flagged": "2026-05-28"},
    ], as_of="2026-05-28")
    ns, dropped = oo.update_open_opportunities(
        store, todays_candidates=[], held_tickers=set(), prices={}, as_of=TODAY,
        resolutions=[
            {"ticker": "FN", "status": "ignored", "reason": "passed after review"},
            {"ticker": "AVGO", "status": "deferred", "reason": "wait for earnings"},
            {"ticker": "MU", "status": "missed", "reason": "ran before action"},
        ])
    assert ns["opportunities"] == []
    assert {d["status"] for d in dropped} == {"ignored", "deferred", "missed"}
    hist = {h["ticker"]: h for h in ns["history"]}
    assert hist["FN"]["reason"] == "passed after review"
    assert hist["AVGO"]["status"] == "deferred"
    assert hist["MU"]["status"] == "missed"


def test_same_day_resolution_is_not_reopened_by_publish_refresh():
    store = {
        "opportunities": [],
        "history": [{
            "ticker": "ANET",
            "first_flagged": "2026-06-07",
            "last_seen": "2026-06-12",
            "resolved_at": "2026-06-12",
            "status": "expired",
            "reason": "old review",
            "source": "lean_in",
            "kind": "lean_in",
            "flag_price": None,
        }],
    }

    ns, dropped = oo.update_open_opportunities(
        store,
        todays_candidates=[{"ticker": "ANET", "kind": "lean_in", "source": "lean_in"}],
        held_tickers=set(),
        prices={},
        as_of="2026-06-12",
    )

    assert ns["opportunities"] == []
    assert dropped == []
    assert ns["history"][0]["status"] == "expired"


def test_review_age_state_classifies_new_due_and_stale_backlog():
    assert oo.review_age_state(0)["review_state"] == "new"
    due = oo.review_age_state(2)
    stale = oo.review_age_state(5)

    assert due["review_state"] == "review_due"
    assert due["cleanup_priority"] == "medium"
    assert stale["review_state"] == "stale"
    assert stale["cleanup_priority"] == "high"
    assert stale["stale"] is True


def test_max_age_expiry_optional():
    store = _seed_fn()  # FN flagged 5/28 → 3 trading days by 6/2
    # no expiry by default
    ns, _ = oo.update_open_opportunities(store, [], set(), {}, TODAY)
    assert any(o["ticker"] == "FN" for o in ns["opportunities"])
    # expire past 2 trading days
    ns2, dropped = oo.update_open_opportunities(store, [], set(), {}, TODAY, max_age_days=2)
    assert all(o["ticker"] != "FN" for o in ns2["opportunities"])
    assert dropped[0]["status"] == "expired"


def test_non_trackable_kinds_not_added():
    ns, _ = oo.update_open_opportunities(
        {"opportunities": []},
        todays_candidates=[
            {"ticker": "X", "kind": "watch_entry"},      # not confirmed → skip
            {"ticker": "Y", "kind": "monitor_reentry"},  # burned path → skip
            {"ticker": "Z", "kind": "catalyst_imminent"},  # held review → skip
            {"ticker": "M", "kind": "macro_alert"},      # not an acquire → skip
        ],
        held_tickers=set(), prices={}, as_of=TODAY)
    assert ns["opportunities"] == []


def test_already_held_candidate_not_added():
    ns, _ = oo.update_open_opportunities(
        {"opportunities": []},
        todays_candidates=[{"ticker": "SMH", "kind": "lean_in"}],
        held_tickers={"SMH"}, prices={}, as_of=TODAY)
    assert ns["opportunities"] == []


# ── the MONITOR guardrail (the critical one) ──

def test_monitor_candidate_never_tracked():
    ns, _ = oo.update_open_opportunities(
        {"opportunities": []},
        todays_candidates=[{"ticker": "LEU", "kind": "lean_in"},
                           {"ticker": "FN", "kind": "lean_in"}],
        held_tickers=set(), prices={}, as_of=TODAY, monitor_tickers={"LEU"})
    tks = {o["ticker"] for o in ns["opportunities"]}
    assert "LEU" not in tks and "FN" in tks


def test_monitor_in_store_is_dropped_on_update():
    # even if a burned name somehow got persisted, an update purges it
    poisoned = {"opportunities": [
        {"ticker": "BMNR", "first_flagged": "2026-05-28", "status": "open"}]}
    ns, dropped = oo.update_open_opportunities(
        poisoned, [], held_tickers=set(), prices={}, as_of=TODAY, monitor_tickers={"BMNR"})
    assert ns["opportunities"] == []
    assert dropped[0]["reason"] == "monitor_excluded"


def test_aging_excludes_monitor():
    store = {"opportunities": [
        {"ticker": "LEU", "first_flagged": "2026-05-28", "flag_price": 190.0, "status": "open"}]}
    aging = oo.open_opportunity_aging(store, {"LEU": 200.0}, TODAY,
                                      threshold_days=3, monitor_tickers={"LEU"})
    assert aging == []


# ── reader: threshold + fields ──

def test_aging_emits_over_threshold_with_fields():
    store = _seed_fn()
    aging = oo.open_opportunity_aging(store, {"FN": 650.0}, TODAY, threshold_days=3)
    assert len(aging) == 1
    a = aging[0]
    assert a["ticker"] == "FN" and a["age_days"] == 3
    assert a["first_flagged"] == "2026-05-28" and a["move_since"] == "+12% since flag"


def test_aging_below_threshold_not_emitted():
    # flagged Mon 6/1 → 1 trading day by Tue 6/2, threshold 3 → nothing
    store = oo.seed_open_opportunities(
        [{"ticker": "FN", "first_flagged": "2026-06-01", "flag_price": 600.0}], as_of=TODAY)
    assert oo.open_opportunity_aging(store, {"FN": 610.0}, TODAY, threshold_days=3) == []


def test_aging_skips_resolved_status():
    store = {"opportunities": [
        {"ticker": "FN", "first_flagged": "2026-05-28", "status": "acted"}]}
    assert oo.open_opportunity_aging(store, {}, TODAY, threshold_days=3) == []


# ── feed adapters ──

def test_held_tickers_from_feed():
    feed = {"holdings": [
        {"cat": "AI", "pos": [{"t": "SMH", "st": "Owned"}, {"t": "FN", "st": "Watchlist"}]},
        {"cat": "X", "pos": [{"t": "GS", "st": "Owned"}]},
        "junk",
    ]}
    assert oo.held_tickers_from_feed(feed) == {"SMH", "GS"}  # Watchlist FN excluded


def test_candidates_from_feed_only_trackable():
    feed = {"actions": [
        {"kind": "buy_now", "ticker": "ITA"},
        {"kind": "lean_in", "ticker": "NVDA"},
        {"kind": "watch_entry", "ticker": "FN"},     # excluded
        {"kind": "monitor_reentry", "ticker": "LEU"},  # excluded
        {"kind": "red_gate", "ticker": None},        # excluded
    ]}
    tks = {c["ticker"] for c in oo.candidates_from_feed(feed)}
    assert tks == {"ITA", "NVDA"}


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
