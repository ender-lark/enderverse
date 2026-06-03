#!/usr/bin/env python3
"""
test_uw_opportunity.py — Strand 3, Chunks 1 + 2.

Chunk 1 (contract): the cache→cards adapter shape, enums, tolerance.
Chunk 2 (live): a FRESH UW opportunity signal becomes a DIRECTION event and a
lean-in evidence row — with the load-bearing guardrails proven in code:
  • flow moves DIRECTION, never conviction QUALITY,
  • flow cannot manufacture a lean-in on a no-conviction name,
  • a burned (MONITOR) sleeve stays gated unless a high-conf re-entry cleared,
  • stale flow is ignored.
"""
from datetime import date, timedelta

from uw_opportunity import (uw_opportunity_cards, sample_opportunity_cache,
                            SIGNAL_TYPES, DIRECTIONS, UW_OPP_KIND, UW_OPP_SOURCE,
                            UW_OPP_INDEPENDENCE_GROUP, UW_OPP_DEFAULT_STRENGTH)
from analyst_config import UW_OPP_STRENGTH_TRUST, UW_OPP_FRESH_DAYS
from analyst_judgment import (conviction_read, conviction_direction_read,
                              lean_in_read)
from feed_assembler import _ns

AS_OF = "2026-05-29"


def _opp_card(ticker, *, direction="bullish", strength="strong", signal_type="sweep",
              age_days=0, content=None):
    """Build one cache SIGNAL dict aged `age_days` before AS_OF."""
    d = (date.fromisoformat(AS_OF) - timedelta(days=age_days)).isoformat()
    sig = {"ticker": ticker, "signal_type": signal_type, "direction": direction,
           "strength": strength, "as_of": d}
    if content:
        sig["evidence"] = content
    return sig


def _ns_cards(*signals):
    """Signals -> the SimpleNamespace cards the readers consume (the real path:
    adapter -> _ns)."""
    return _ns(uw_opportunity_cards({"signals": list(signals)}))


# ==================== Chunk 1 - adapter contract ====================

def test_signal_maps_to_full_sourceitem_shape():
    cache = {"generated_at": "2026-05-29T10:30:00Z",
             "signals": [{"ticker": "ANET", "signal_type": "sweep",
                          "direction": "bullish", "strength": "strong",
                          "evidence": "ask-side sweeps $2.1M",
                          "as_of": "2026-05-29T15:30:00Z",
                          "detail": {"premium": 2100000, "side": "ask"}}]}
    (card,) = uw_opportunity_cards(cache)
    assert set(card) == {"source", "kind", "subject", "content", "timestamp",
                         "trust_weight", "independence_group", "data"}
    assert card["kind"] == UW_OPP_KIND == "uw_opportunity"
    assert card["source"] == UW_OPP_SOURCE
    assert card["subject"] == "ANET"
    assert card["content"] == "ask-side sweeps $2.1M"
    assert card["timestamp"] == "2026-05-29T15:30:00Z"
    assert card["trust_weight"] == UW_OPP_STRENGTH_TRUST["strong"] == 0.9
    assert card["independence_group"] == UW_OPP_INDEPENDENCE_GROUP == "uw_flow"
    assert card["data"]["signal_type"] == "sweep"
    assert card["data"]["direction"] == "bullish"
    assert card["data"]["strength"] == "strong"
    assert card["data"]["premium"] == 2100000


def test_bare_list_accepted():
    cards = uw_opportunity_cards([{"ticker": "MU", "signal_type": "oi_build",
                                   "direction": "bullish"}])
    assert len(cards) == 1 and cards[0]["subject"] == "MU"


def test_none_and_empty_yield_no_cards():
    assert uw_opportunity_cards(None) == []
    assert uw_opportunity_cards({}) == []
    assert uw_opportunity_cards({"signals": []}) == []
    assert uw_opportunity_cards("garbage") == []


def test_malformed_rows_skipped_not_raised():
    cache = {"signals": [
        "not-a-dict",
        {"signal_type": "sweep", "direction": "bullish"},          # no ticker
        {"ticker": "X", "signal_type": "rumor", "direction": "bullish"},   # bad type
        {"ticker": "Y", "signal_type": "sweep", "direction": "sideways"},  # bad dir
        {"ticker": "Z", "signal_type": "call_flow", "direction": "bearish"},  # valid
    ]}
    cards = uw_opportunity_cards(cache)
    assert [c["subject"] for c in cards] == ["Z"]
    assert cards[0]["data"]["direction"] == "bearish"


def test_strength_trust_map_and_default():
    def trust(strength):
        s = {"ticker": "T", "signal_type": "sweep", "direction": "bullish"}
        if strength is not None:
            s["strength"] = strength
        return uw_opportunity_cards([s])[0]["trust_weight"]
    assert trust("strong") == 0.9
    assert trust("moderate") == 0.7
    assert trust("weak") == 0.5
    assert trust(None) == UW_OPP_STRENGTH_TRUST[UW_OPP_DEFAULT_STRENGTH]
    assert trust("bogus") == UW_OPP_STRENGTH_TRUST[UW_OPP_DEFAULT_STRENGTH]


def test_timestamp_falls_back_to_cache_then_empty():
    assert uw_opportunity_cards({"generated_at": "2026-05-29T10:30:00Z",
        "signals": [{"ticker": "T", "signal_type": "sweep", "direction": "bullish",
                     "as_of": "2026-05-29T15:30:00Z"}]})[0]["timestamp"] == "2026-05-29T15:30:00Z"
    assert uw_opportunity_cards({"generated_at": "2026-05-29T10:30:00Z",
        "signals": [{"ticker": "T", "signal_type": "sweep", "direction": "bullish"}]}
        )[0]["timestamp"] == "2026-05-29T10:30:00Z"
    assert uw_opportunity_cards([{"ticker": "T", "signal_type": "sweep",
                                  "direction": "bullish"}])[0]["timestamp"] == ""


def test_evidence_defaults_to_generated_one_liner():
    (card,) = uw_opportunity_cards([{"ticker": "T", "signal_type": "dark_pool_accum",
                                     "direction": "bullish"}])
    assert card["content"] == "bullish dark pool accum"


def test_sample_cache_all_valid_and_in_enums():
    cards = uw_opportunity_cards(sample_opportunity_cache())
    assert len(cards) == 3
    for c in cards:
        assert c["data"]["signal_type"] in SIGNAL_TYPES
        assert c["data"]["direction"] in DIRECTIONS


def test_contract_enums():
    assert SIGNAL_TYPES == {"call_flow", "sweep", "oi_build", "dark_pool_accum", "gamma"}
    assert DIRECTIONS == {"bullish", "bearish"}


def test_card_has_no_event_key_reader_derives_from_direction():
    """The adapter stays neutral (no `event` marker); the DIRECTION read is what
    interprets a uw_opportunity card - so the contract layer carries no event."""
    for c in uw_opportunity_cards(sample_opportunity_cache()):
        assert "event" not in c["data"]


# ==================== Chunk 2 - flow -> direction event ====================

def test_fresh_bullish_flow_is_up_event():
    r = conviction_direction_read("NVDA", _ns_cards(_opp_card("NVDA", age_days=0)), AS_OF)
    assert r["cd"] == "up"
    assert r["events"] and r["events"][0]["sentiment"] == "bullish"


def test_fresh_bearish_flow_is_down_event():
    r = conviction_direction_read("NVDA",
        _ns_cards(_opp_card("NVDA", direction="bearish", age_days=0)), AS_OF)
    assert r["cd"] == "down"


def test_stale_flow_is_ignored():
    r = conviction_direction_read("NVDA",
        _ns_cards(_opp_card("NVDA", age_days=UW_OPP_FRESH_DAYS + 3)), AS_OF)
    assert r["cd"] == "flat" and r["events"] == []


def test_flow_at_window_boundary_counts():
    r = conviction_direction_read("NVDA",
        _ns_cards(_opp_card("NVDA", age_days=UW_OPP_FRESH_DAYS)), AS_OF)
    assert r["cd"] == "up"


def test_signal_type_and_source_show_in_cdnote():
    note = conviction_direction_read("NVDA",
        _ns_cards(_opp_card("NVDA", signal_type="oi_build", age_days=1)), AS_OF)["cdNote"]
    assert "oi_build" in note and "uw_opportunity" in note


def test_strong_flow_outweighs_weak_opposing_flow():
    cards = _ns_cards(_opp_card("NVDA", direction="bullish", strength="strong", age_days=0),
                      _opp_card("NVDA", direction="bearish", strength="weak", age_days=0))
    assert conviction_direction_read("NVDA", cards, AS_OF)["cd"] == "up"


# ==================== Chunk 2 - the guardrails (in code) ====================

def test_quality_read_ignores_flow():
    """GUARDRAIL: flow is confirmation/timing - it never changes conviction QUALITY
    (uw_opportunity is not in ENDORSEMENT_KINDS)."""
    thesis = {"ticker": "NVDA", "source": "fundstrat", "stance": "ACTIVE"}
    flow = list(_ns_cards(_opp_card("NVDA")))
    assert conviction_read("NVDA", thesis, flow) == conviction_read("NVDA", thesis, [])


def test_flow_is_not_an_independence_stream():
    thesis = {"ticker": "NVDA", "source": "fundstrat", "stance": "ACTIVE"}
    flow = list(_ns_cards(_opp_card("NVDA"), _opp_card("NVDA", signal_type="oi_build")))
    assert conviction_read("NVDA", thesis, flow)["streams"] == 0


def test_flow_alone_no_thesis_not_surfaced():
    """GUARDRAIL: flow cannot manufacture a lean-in - no conviction floor, no row."""
    cards = list(_ns_cards(_opp_card("XYZ")))
    drs = [{"ticker": "XYZ", "cd": "up", "cdNote": "x"}]
    out = lean_in_read(drs, [], cards, AS_OF, held=set(), underweight=set())
    assert all(i["ticker"] != "XYZ" for i in out["lean_in"])


# ==================== Chunk 2 - lean-in evidence + flags ====================

def test_lean_in_evidence_includes_uw_flow_and_no_auto_buy():
    theses = [{"ticker": "NVDA", "tier": "T1", "source": "fundstrat", "stance": "ACTIVE"}]
    cards = list(_ns_cards(_opp_card("NVDA", content="ask-side call sweeps $2.1M")))
    drs = [{"ticker": "NVDA", "cd": "up", "cdNote": "05-29 uw_opportunity sweep"}]
    out = lean_in_read(drs, theses, cards, AS_OF, held={"NVDA"}, underweight={"NVDA"})
    item = next(i for i in out["lean_in"] if i["ticker"] == "NVDA")
    assert any(e.startswith("UW") and "$2.1M" in e for e in item["evidence"])
    assert item["action"] == "NONE"


def test_already_moved_caveat_is_flow_aware():
    theses = [{"ticker": "NVDA", "tier": "T1", "source": "fundstrat", "stance": "ACTIVE"}]
    cards = list(_ns_cards(_opp_card("NVDA")))
    drs = [{"ticker": "NVDA", "cd": "up", "cdNote": "x"}]
    out = lean_in_read(drs, theses, cards, AS_OF, held={"NVDA"}, underweight={"NVDA"},
                       rotation_by_name={"NVDA": {"subject": "SMH", "label": "LEADING",
                                                  "rel_3m_vs_smh": 0.5}})
    item = next(i for i in out["lean_in"] if i["ticker"] == "NVDA")
    assert any("already moved" in c and "flow is confirming" in c for c in item["caveats"])


def test_monitor_name_with_flow_stays_gated_until_reentry():
    theses = [{"ticker": "BMNR", "tier": "T3", "source": "fundstrat", "stance": "MONITOR"}]
    cards = list(_ns_cards(_opp_card("BMNR")))
    drs = [{"ticker": "BMNR", "cd": "up", "cdNote": "x"}]
    gated = lean_in_read(drs, theses, cards, AS_OF, held={"BMNR"})
    assert all(i["ticker"] != "BMNR" for i in gated["lean_in"])
    cleared = lean_in_read(drs, theses, cards, AS_OF, held={"BMNR"},
                           high_conf_reentry={"BMNR"})
    assert any(i["ticker"] == "BMNR" for i in cleared["lean_in"])


# ── B1: read-only "Bullish flow" surface (uw_opportunity_surface) ──
import os as _os, json as _json
from uw_opportunity import uw_opportunity_surface, sample_opportunity_cache
import feed_assembler as _FA, validators as _V
_HERE = _os.path.dirname(_os.path.abspath(__file__))


def test_surface_groups_by_ticker_uw_flow_one_bucket():
    # multiple flow signals on ANET collapse to ONE row (uw_flow = one bucket/name)
    cache = {"as_of": "2026-05-29", "signals": [
        {"ticker": "ANET", "signal_type": "sweep", "direction": "bullish", "strength": "strong"},
        {"ticker": "ANET", "signal_type": "sweep", "direction": "bullish", "strength": "weak"},
        {"ticker": "ANET", "signal_type": "oi_build", "direction": "bullish", "strength": "moderate"},
        {"ticker": "MU", "signal_type": "call_flow", "direction": "bullish", "strength": "moderate"},
    ]}
    out = uw_opportunity_surface(cache)
    assert out["tickers"] == 2 and out["count"] == 4
    anet = next(r for r in out["rows"] if r["ticker"] == "ANET")
    assert anet["n"] == 3
    assert anet["strength"] == "strong"                         # strongest leads the bucket
    assert set(anet["signal_types"]) == {"sweep", "oi_build"}   # types de-duped


def test_surface_bullish_first_then_strength():
    cache = {"signals": [
        {"ticker": "AAA", "signal_type": "sweep", "direction": "bearish", "strength": "strong"},
        {"ticker": "BBB", "signal_type": "sweep", "direction": "bullish", "strength": "weak"},
        {"ticker": "CCC", "signal_type": "sweep", "direction": "bullish", "strength": "strong"},
    ]}
    rows = uw_opportunity_surface(cache)["rows"]
    assert rows[0]["ticker"] == "CCC"    # bullish + strongest first
    assert rows[-1]["ticker"] == "AAA"   # bearish last


def test_surface_tolerant_and_empty():
    assert uw_opportunity_surface(None) == {}
    assert uw_opportunity_surface({"signals": []}) == {}
    bad = {"signals": [
        {"ticker": "X", "signal_type": "NOT_A_TYPE", "direction": "bullish"},  # bad enum
        {"signal_type": "sweep", "direction": "bullish"},                       # no ticker
        "junk",                                                                  # not a dict
        {"ticker": "OK", "signal_type": "sweep", "direction": "bullish"},
    ]}
    out = uw_opportunity_surface(bad)
    assert out["tickers"] == 1 and out["rows"][0]["ticker"] == "OK"


def test_assemble_feed_emits_bullish_flow_and_validates():
    snap = _json.load(open(_os.path.join(_HERE, "golden_snapshot.json")))
    feed = _FA.assemble_feed(snap, uw_opportunity=sample_opportunity_cache())
    assert isinstance(feed["bullish_flow"], dict) and feed["bullish_flow"]["tickers"] >= 1
    assert _V.validate_cockpit_feed(feed) == []
    feed2 = _FA.assemble_feed(snap)                 # no cache -> {} and still valid
    assert feed2["bullish_flow"] == {}
    assert _V.validate_cockpit_feed(feed2) == []


def test_surface_tags_monitor_names_parked():
    cache = {"signals": [
        {"ticker": "ETH", "signal_type": "sweep", "direction": "bullish", "strength": "strong"},
        {"ticker": "NVDA", "signal_type": "sweep", "direction": "bullish", "strength": "strong"},
    ]}
    out = uw_opportunity_surface(cache, monitor_tickers={"ETH"})
    byk = {r["ticker"]: r for r in out["rows"]}
    assert byk["ETH"]["parked"] is True       # MONITOR/parked sleeve -> caution tag
    assert byk["NVDA"]["parked"] is False     # active name -> no tag
