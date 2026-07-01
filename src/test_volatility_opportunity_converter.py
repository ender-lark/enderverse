"""Tests for the volatility opportunity converter using the frozen 2026-06-23/24 fixture.

The fixture is the AI/semis volatility regime: 6/23 semis -7% selloff, 6/24 MU beat,
Fundstrat buy-the-dip, QQQ/SMH held support but not reclaimed, oil/rates supportive.
These tests pin the doctrine rails the converter must never break:
  * the surface DECIDES/STAGES, it never nets out to a passive WATCH;
  * an already-overweight name (MU) does NOT become an ADD on a confirming beat;
  * neutral/inconclusive flow never counts as confirmation;
  * an unchecked lane (Social Watch) stays not_checked;
  * the protected sleeve (GRNJ) is never a funding source.
"""
import json
from pathlib import Path

import pytest

import volatility_opportunity_converter as voc

FIXTURE = Path(__file__).resolve().parent / "volatility_opportunity_fixture_2026_06_23.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _convert():
    fx = _fixture()
    return voc.convert(
        target_drift=fx["target_drift"], holdings=fx["holdings"], book_value=fx["book_value"],
        fundstrat_calls=fx["fundstrat_calls"], tape=fx["tape"], uw_proof=fx["uw_proof"],
        event_risk=fx["event_risk"], social_watch=fx["social_watch"],
        funding_policy=fx["funding_policy"], as_of=fx["_meta"]["as_of"],
        generated_at="2026-06-25T00:00:00Z",
    )


def _cmd(result):
    return {c["ticker"]: c for c in result["command"]}


# ── the central anti-passivity test ──────────────────────────────────────────

def test_fixture_produces_decide_stage_plan_not_watch_only():
    res = _convert()
    assert res["summary"]["decide_not_watch"] is True
    assert res["summary"]["stage_count"] >= 3            # GOOGL, AVGO, MSFT all staged
    assert res["regime"]["label"] == "SEMIS_SELLOFF_REBOUND_PENDING"
    # the headline leads with the regime + the sized command, never a "consider waiting"
    assert "staged add" in res["summary"]["headline"]


def test_under_target_quality_names_are_staged_and_sized():
    cmd = _cmd(_convert())
    for tk, target in (("GOOGL", 8.0), ("AVGO", 6.0), ("MSFT", 5.0)):
        assert tk in cmd, f"{tk} missing from command"
        assert cmd[tk]["disposition"] in ("STAGE-LEAD", "STAGE")
        assert cmd[tk]["target_pct"] == target
        assert cmd[tk]["size_to_target_usd"] > 0          # a real dollar size, not just a flag
    # GOOGL held up in the selloff -> it is a STAGE-LEAD (loud) row, and a lead row sorts first
    assert cmd["GOOGL"]["disposition"] == "STAGE-LEAD"
    assert _convert()["command"][0]["disposition"] == "STAGE-LEAD"


def test_mu_overweight_does_not_become_add():
    cmd = _cmd(_convert())
    assert cmd["MU"]["disposition"] == "CONFIRM-HOLD"
    assert cmd["MU"]["disposition"] not in ("STAGE", "STAGE-LEAD")
    assert "Do NOT chase MU" in cmd["MU"]["move"]
    assert "OVER target" in cmd["MU"]["move"]             # risk/over-size stays visible


def test_mu_beat_is_confirmation_and_funding_not_a_chase():
    res = _convert()
    fund = {f["ticker"]: f for f in res["funding"]}
    assert "MU" in fund                                   # the post-beat excess is a funding candidate
    assert fund["MU"]["confirmed_strength"] is True       # trimmed into strength, never weakness


def test_neutral_or_unchecked_flow_never_becomes_support():
    cmd = _cmd(_convert())
    # GOOGL flow is NEUTRAL, AVGO/MSFT inconclusive/not-checked -> none may read as confirmation
    for tk in ("GOOGL", "AVGO", "MSFT"):
        assert cmd[tk]["uw_verdict"] in ("NEUTRAL", "NOT_CHECKED")
        assert "NOT counted" in (cmd[tk]["support_note"] or "")
        assert "confirms" not in (cmd[tk]["support_note"] or "")


def test_social_watch_stays_not_checked():
    res = _convert()
    assert res["honesty"].get("social_watch", "").startswith("not checked")


def test_grnj_protected_sleeve_never_funds():
    res = _convert()
    funded = {f["ticker"] for f in res["funding"]}
    assert "GRNJ" not in funded
    assert "GRNJ" in res["honesty"].get("protected_sleeves", "")
    # GRNJ also never shows up as a command move
    assert "GRNJ" not in _cmd(res)


def test_grny_excess_is_primary_funding():
    res = _convert()
    assert res["funding"][0]["ticker"] == "GRNY"          # biggest over-target sleeve funds first
    assert res["funding"][0]["excess_usd"] > 100_000


def test_nvda_conditional_funding_not_used_by_default():
    res = _convert()
    nvda = next((f for f in res["funding"] if f["ticker"] == "NVDA"), None)
    assert nvda is not None
    assert "not used by default" in nvda["note"]
    assert nvda["excess_usd"] is None                     # in-band; no excess to harvest


def test_gate_is_pending_because_reclaim_not_confirmed():
    res = _convert()
    assert res["gate"]["status"] in ("ARMED", "PENDING")  # NOT OPEN: QQQ/SMH have not reclaimed
    assert res["gate"]["reclaimed"] is False
    assert res["gate"]["macro_supportive"] is True


def test_dollar_sizing_matches_the_gaps():
    cmd = _cmd(_convert())
    book = _fixture()["book_value"]
    # GOOGL gap = (8.0 - 3.7627)% of 1,923,513 ~= $81.5k
    assert cmd["GOOGL"]["size_to_target_usd"] == round((8.0 - 3.7627) / 100 * book)
    assert 80_000 < cmd["GOOGL"]["size_to_target_usd"] < 83_000


# ── demote no-position sell-fast rows ────────────────────────────────────────

def test_demote_no_position_sells():
    actions = [
        {"ticker": "RYF", "kind": "sell_fast", "what": "Avoid-new-exposure watch"},
        {"ticker": "XOP", "kind": "sell_fast", "what": "Sell fast — momentum gone"},
        {"ticker": "EWY", "kind": "avoid", "what": "Avoid new exposure (Korea)"},
        {"ticker": "GRNY", "kind": "trim", "what": "Trim the overweight"},
        {"ticker": "MAGS", "kind": "lean_in", "what": "Lean-in"},
    ]
    out = {a["ticker"]: a for a in voc.demote_no_position_sells(actions, {"GRNY", "MU"})}
    # avoid-new-exposure rows: kept, but quiet context (they gate new-buy timing)
    assert out["RYF"]["surface_role"] == "context" and out["RYF"]["demoted"] is True
    assert out["EWY"]["surface_role"] == "context"
    # pure no-position sell -> demoted to backlog
    assert out["XOP"]["surface_role"] == "backlog" and out["XOP"]["demoted"] is True
    # a sell on a HELD ticker stays loud; a non-sell lane is untouched
    assert "demoted" not in out["GRNY"]
    assert "demoted" not in out["MAGS"]


def test_demote_never_mutates_caller_rows():
    actions = [{"ticker": "XOP", "kind": "sell_fast", "what": "Sell fast"}]
    voc.demote_no_position_sells(actions, set())
    assert "demoted" not in actions[0]                    # the original row is untouched


# ── honesty / robustness rails ───────────────────────────────────────────────

def test_renders_are_loud_and_never_silent():
    res = _convert()
    text = voc.render_command_text(res)
    html_block = voc.render_command_html(res)
    assert text.startswith("\U0001f6a6")
    assert "VOLATILITY OPPORTUNITY" in html_block
    assert "Do NOT chase MU" in text                      # the no-chase call is on the face
    assert "never an order" in text                       # the no-execution rail is visible
    # honest-empty still speaks
    empty = voc.convert(target_drift=None, holdings=None)
    assert voc.render_command_text(empty).startswith("\U0001f6a6")
    assert empty["summary"]["decide_not_watch"] is False


def test_malformed_inputs_degrade_never_raise():
    res = voc.convert(target_drift=[1, 2, 3], holdings="junk", book_value="x",
                      fundstrat_calls="y", tape=5, uw_proof=7, event_risk=True)
    assert res["source"] == voc.SOURCE
    assert res["command"] == [] and res["funding"] == []


def test_from_feed_smoke_does_not_raise():
    feed = {
        "generated_at": "2026-06-24T20:00:00Z",
        "target_drift": _fixture()["target_drift"],
        "portfolio_views": {"views": {"combined": {
            "total_value": 1923513,
            "rows": [{"ticker": t["ticker"], "market_value": t["market_value"]}
                     for t in _fixture()["holdings"]],
        }}},
        "event_risk": [{"what": "Event risk: Middle East oil/rates shock can affect new-buy timing"}],
        "lean_in": [{"ticker": "MAGS", "what": "Lean-in"}],
        "radar": [{"ticker": "GOOGL", "pct_1d": -0.24}],
        "social_watch": {"status": "not_checked"},
    }
    res = voc.from_feed(feed)
    assert res["source"] == voc.SOURCE
    # the fixed drift read still classifies GOOGL/AVGO/MSFT as staged adds, not missing
    cmd = _cmd(res)
    assert {"GOOGL", "AVGO", "MSFT"} <= set(cmd)


# ── regression tests for the adversarially-found rail breaks (2026-06-25) ─────

def test_mislabeled_oversized_row_is_never_staged():
    # a row mislabels an over-target name as UNDERSIZED; its OWN numbers (3.67 >= 3.0) must win.
    res = voc.convert(
        target_drift={"rows": [{"ticker": "MU", "direction": "UNDERSIZED", "actual_pct": 3.67, "target_pct": 3.0}]},
        holdings=[{"ticker": "MU", "market_value": 100000}], book_value=1_000_000,
        tape={"MU": {"held_up": True, "event_confirmation": True}}, event_risk={"state": "SUPPORTIVE"})
    disp = {c["ticker"]: c["disposition"] for c in res["command"]}
    assert disp.get("MU") != "STAGE-LEAD" and disp.get("MU") != "STAGE"


def test_ticker_cannot_occupy_both_loops():
    # MU present as BOTH an undersized and an oversized row -> never both STAGE and CONFIRM-HOLD.
    res = voc.convert(
        target_drift={"rows": [
            {"ticker": "MU", "direction": "UNDERSIZED", "actual_pct": 3.67, "target_pct": 3.0},
            {"ticker": "MU", "direction": "OVERSIZED", "actual_pct": 3.67, "target_pct": 3.0},
        ]},
        holdings=[{"ticker": "MU", "market_value": 100000}], book_value=1_000_000,
        tape={"MU": {"event_confirmation": True}}, event_risk={"state": "SUPPORTIVE"})
    mu_rows = [c for c in res["command"] if c["ticker"] == "MU"]
    assert all(c["disposition"] not in ("STAGE", "STAGE-LEAD") for c in mu_rows)


def test_protected_sleeve_in_conditional_never_funds():
    res = voc.convert(target_drift={"rows": []}, holdings=[{"ticker": "GRNJ", "market_value": 100000}],
                      book_value=1_000_000, funding_policy={"protected": ["GRNJ"], "conditional": {"GRNJ": "rail"}})
    assert "GRNJ" not in {f["ticker"] for f in res["funding"]}


def test_protected_sleeve_undersized_is_never_staged():
    res = voc.convert(
        target_drift={"rows": [{"ticker": "GRNJ", "direction": "UNDERSIZED", "actual_pct": 1.0, "target_pct": 8.0}]},
        holdings=[{"ticker": "GRNJ", "market_value": 100000}], book_value=1_000_000,
        tape={"GRNJ": {"held_up": True}}, funding_policy={"protected": ["GRNJ"], "conditional": {}})
    assert "GRNJ" not in {c["ticker"] for c in res["command"]}


def test_missing_percent_field_does_not_crash_the_producer():
    # a structural STAGE-LEAD row whose actual_pct is missing must NOT raise (never-silent rail).
    res = voc.convert(
        target_drift={"rows": [{"ticker": "GOOGL", "direction": "UNDERSIZED", "target_pct": 8.0}]},
        holdings=[{"ticker": "GOOGL", "market_value": 100}], book_value=1_923_513,
        tape={"GOOGL": {"held_up": True}})
    assert res["summary"]["headline"]                       # still speaks
    assert "target gap" in res["command"][0]["move"]        # honest fallback, not a crash


def test_string_false_reclaim_does_not_open_the_gate():
    for val in ("false", "0", "no", "False"):
        gate = voc.gate_state({"QQQ": {"reclaimed": val, "held_support": True},
                               "SMH": {"reclaimed": val, "held_support": True}}, {"state": "SUPPORTIVE"})
        assert gate["status"] != "OPEN" and gate["reclaimed"] is False


def test_oversized_unheld_name_is_not_a_phantom_trim():
    # a drift row says FAKE is oversized, but we own no FAKE -> never a funding/CONFIRM-HOLD row.
    res = voc.convert(
        target_drift={"rows": [{"ticker": "FAKE", "direction": "OVERSIZED", "actual_pct": 9.0, "target_pct": 3.0}]},
        holdings=[{"ticker": "REAL", "market_value": 100000}], book_value=1_000_000,
        tape={"FAKE": {"event_confirmation": True}})
    assert "FAKE" not in {f["ticker"] for f in res["funding"]}
    assert "FAKE" not in {c["ticker"] for c in res["command"]}


def test_demote_keeps_held_zero_value_sell_loud():
    # a held name with market_value 0 (written-down/unpriced) passed as a holdings LIST stays loud.
    actions = [{"ticker": "ABC", "kind": "sell_fast", "what": "Sell fast"}]
    out = voc.demote_no_position_sells(actions, [{"ticker": "ABC", "market_value": 0}])
    assert "demoted" not in out[0]


def test_demote_catches_liquidate_and_dump_kinds():
    actions = [{"ticker": "ZZZ", "kind": "liquidate", "what": "Liquidate"},
               {"ticker": "YYY", "kind": "dump", "what": "Dump it"}]
    out = {a["ticker"]: a for a in voc.demote_no_position_sells(actions, set())}
    assert out["ZZZ"]["demoted"] is True and out["YYY"]["demoted"] is True


def test_missing_targets_surface_in_honesty_never_silent():
    res = voc.convert(
        target_drift={"rows": [{"ticker": "VRT", "direction": "MISSING", "actual_pct": 0.0, "target_pct": 2.0}]},
        holdings=[{"ticker": "NVDA", "market_value": 100000}], book_value=1_000_000)
    assert "VRT" in res["honesty"].get("missing_targets", "")


def test_elevated_event_risk_is_visible_in_honesty():
    res = voc.convert(target_drift={"rows": []}, holdings=[{"ticker": "NVDA", "market_value": 1}],
                      event_risk={"state": "ELEVATED"})
    assert "ELEVATED" in res["honesty"].get("event_risk", "")


def test_derived_book_value_is_flagged_in_honesty():
    res = voc.convert(target_drift={"rows": []}, holdings=[{"ticker": "NVDA", "market_value": 50}])
    assert "derived" in res["honesty"].get("book_value", "")


def test_from_feed_blocking_event_risk_is_reachable():
    feed = {
        "target_drift": {"rows": []},
        "portfolio_views": {"views": {"combined": {"total_value": 1_000_000, "rows": [
            {"ticker": "NVDA", "market_value": 100000}]}}},
        "event_risk": [{"what": "Halt new exposure — risk-off until the macro clears"}],
    }
    res = voc.from_feed(feed)
    assert res["gate"]["status"] == "BLOCKED"


def test_from_feed_regime_is_neutral_on_a_bare_cached_feed():
    # locks the documented production limitation: the cached feed lacks structured tape/stances,
    # so the adapter reports NEUTRAL. If this ever changes (feed enriched), this test should be updated.
    feed = {"target_drift": {"rows": []},
            "portfolio_views": {"views": {"combined": {"total_value": 1_000_000, "rows": []}}},
            "event_risk": []}
    res = voc.from_feed(feed)
    assert res["regime"]["label"] == "NEUTRAL"


# ── second adversarial pass (2026-06-25) — deeper edge cases ──────────────────

def test_string_shaped_protected_config_is_coerced_not_iterated_by_char():
    # funding_policy={"protected": "GRNJ"} (a typo) must still protect GRNJ, not {'G','R','N','J'}.
    res = voc.convert(
        target_drift={"rows": [{"ticker": "GRNJ", "direction": "OVERSIZED", "actual_pct": 9.0, "target_pct": 3.0}]},
        holdings=[{"ticker": "GRNJ", "market_value": 100}], book_value=1000, funding_policy={"protected": "GRNJ"})
    assert "GRNJ" not in {f["ticker"] for f in res["funding"]}
    assert "G, J, N, R" not in res["honesty"].get("protected_sleeves", "")


@pytest.mark.parametrize("bad_book", [float("nan"), float("inf"), float("-inf"), "nan"])
def test_non_finite_book_value_never_takes_the_producer_dark(bad_book):
    res = voc.convert(
        target_drift={"rows": [{"ticker": "GOOGL", "direction": "UNDERSIZED", "actual_pct": 3.0, "target_pct": 8.0}]},
        book_value=bad_book, tape={"GOOGL": {"held_up": True}})
    assert res["summary"]["headline"]                        # speaks, never raises
    assert res["book_value"] is None                         # honest absence, not a junk number


@pytest.mark.parametrize("flag", ["not reclaimed", "pending", "-1", "0.0", "f", "nope", {"x": 1}, ["a"]])
def test_non_affirmative_reclaim_flag_never_opens_the_gate(flag):
    gate = voc.gate_state({"QQQ": {"reclaimed": flag, "held_support": True},
                           "SMH": {"reclaimed": flag, "held_support": True}}, {"state": "SUPPORTIVE"})
    assert gate["status"] != "OPEN" and gate["reclaimed"] is False


def test_genuine_reclaim_token_still_opens_the_gate():
    gate = voc.gate_state({"QQQ": {"reclaimed": "true", "held_support": True},
                           "SMH": {"reclaimed": True, "held_support": True}}, {"state": "SUPPORTIVE"})
    assert gate["status"] == "OPEN"


def test_missing_actual_oversized_row_never_funds_and_never_double_books():
    res = voc.convert(
        target_drift={"rows": [
            {"ticker": "MU", "direction": "UNDERSIZED", "actual_pct": 1.0, "target_pct": 3.0},
            {"ticker": "MU", "direction": "OVERSIZED", "actual_pct": None, "target_pct": 3.0}]},
        holdings=[{"ticker": "MU", "market_value": 100}], book_value=1000)
    assert "MU" not in {f["ticker"] for f in res["funding"]}              # no unproven excess funded
    assert all(c["disposition"] not in ("STAGE", "STAGE-LEAD")
               for c in res["command"] if c["ticker"] == "MU")           # not in both loops
    assert "MU" in res["honesty"].get("conflicted_drift", "")            # surfaced, not silently dropped


def test_phantom_trim_withheld_when_positions_lane_is_empty():
    # an OVERSIZED row with NO holdings (stale/failed positions sync) must not fabricate a trim.
    res = voc.convert(
        target_drift={"rows": [{"ticker": "PHANTOM", "direction": "OVERSIZED", "actual_pct": 9.0, "target_pct": 3.0}]},
        holdings=None, book_value=1_000_000)
    assert res["funding"] == [] and res["command"] == []
    assert res["summary"]["total_funding_usd"] == 0                       # no phantom capital invented
    assert "WITHHELD" in res["honesty"].get("funding", "")               # absence stated, not silent


def test_negative_derived_book_value_is_honest_absence():
    res = voc.convert(
        target_drift={"rows": [{"ticker": "A", "direction": "UNDERSIZED", "actual_pct": 1.0, "target_pct": 8.0}]},
        holdings=[{"ticker": "A", "market_value": -500000}, {"ticker": "B", "market_value": 100000}])
    assert res["book_value"] is None                                     # never size off a negative book


# ── third adversarial pass (2026-06-25) — exotic config shapes + confirmation path ──

@pytest.mark.parametrize("policy", [
    {"protected": {"sleeve": "GRNJ"}},   # dict — must protect values, not keys
    {"protected": [["GRNJ"]]},           # nested list — must flatten
    {"protected": 123},                  # scalar — must not crash
])
def test_protected_sleeve_survives_exotic_config_shapes(policy):
    res = voc.convert(
        target_drift={"rows": [{"ticker": "GRNJ", "direction": "OVERSIZED", "actual_pct": 9.0, "target_pct": 3.0}]},
        holdings=[{"ticker": "GRNJ", "market_value": 100000}], book_value=1_000_000, funding_policy=policy)
    if policy["protected"] != 123:       # the dict/nested shapes still name GRNJ → must stay protected
        assert "GRNJ" not in {f["ticker"] for f in res["funding"]}
    assert res["summary"]["headline"]    # scalar shape: never raises, still speaks


@pytest.mark.parametrize("kwargs", [
    {"target_drift": None, "fundstrat_calls": 1},
    {"target_drift": None, "holdings": 1},
    {"target_drift": {"rows": [{"ticker": "X", "direction": "UNDERSIZED", "actual_pct": 1.0, "target_pct": 8.0}]},
     "holdings": [{"ticker": "X", "market_value": 100}], "book_value": 1000, "tranches": "3"},
])
def test_non_iterable_lane_arguments_never_raise(kwargs):
    res = voc.convert(**kwargs)
    assert res["source"] == voc.SOURCE and res["summary"]["headline"]


def test_from_feed_non_iterable_lanes_never_raise():
    assert voc.from_feed({"lean_in": 1, "radar": 2})["source"] == voc.SOURCE
    assert voc.demote_no_position_sells(1, None) == []


def test_false_event_confirmation_string_does_not_manufacture_confirmation():
    res = voc.convert(
        target_drift={"rows": [{"ticker": "ZZ", "direction": "OVERSIZED", "actual_pct": 10.0, "target_pct": 3.0}]},
        holdings=[{"ticker": "ZZ", "market_value": 1}], book_value=100, tape={"ZZ": {"event_confirmation": "false"}})
    assert not any(c["disposition"] == "CONFIRM-HOLD" for c in res["command"])
    assert not any(f.get("confirmed_strength") for f in res["funding"])


def test_bearish_beat_headline_is_not_read_as_confirmation():
    # "couldn't beat" is a MISS — must never flip the funding note to "trim into post-event strength".
    feed = {
        "target_drift": {"rows": [{"ticker": "ZZ", "direction": "OVERSIZED", "actual_pct": 10.0, "target_pct": 3.0}]},
        "portfolio_views": {"views": {"combined": {"total_value": 100, "rows": [{"ticker": "ZZ", "market_value": 1}]}}},
        "fundstrat_news": {"rows": [{"ticker": "ZZ", "stance": "BEARISH", "headline": "ZZ couldn't beat lowered bar; downgrade"}]},
    }
    res = voc.from_feed(feed)
    assert not any(f.get("confirmed_strength") for f in res["funding"])


def test_genuine_event_confirmation_still_confirms():
    res = voc.convert(
        target_drift={"rows": [{"ticker": "ZZ", "direction": "OVERSIZED", "actual_pct": 10.0, "target_pct": 3.0}]},
        holdings=[{"ticker": "ZZ", "market_value": 1}], book_value=100, tape={"ZZ": {"event_confirmation": True}})
    assert any(c["disposition"] == "CONFIRM-HOLD" for c in res["command"])


# ── positions-freshness guard + conditional-funding precedence (2026-06-25 goal) ──

def test_stale_positions_snapshot_is_stamped_loud():
    # the exact bug: a 6/17 snapshot driving a 6/25 call must be stamped, never presented as current.
    res = voc.convert(
        target_drift={"rows": [{"ticker": "GOOGL", "direction": "UNDERSIZED", "actual_pct": 5.0, "target_pct": 8.0}]},
        holdings=[{"ticker": "GOOGL", "market_value": 100000}], book_value=1_000_000,
        tape={"GOOGL": {"held_up": True}}, positions_as_of="2026-06-17", today="2026-06-25")
    assert res["positions_freshness"]["stale"] is True
    assert res["positions_freshness"]["days_old"] == 8
    assert res["summary"]["headline"].startswith("⚠ STALE POSITIONS")     # loudest, first thing seen
    assert "positions_freshness" in res["honesty"]


def test_fresh_positions_snapshot_is_not_flagged():
    res = voc.convert(target_drift={"rows": []}, holdings=[{"ticker": "X", "market_value": 1}],
                      positions_as_of="2026-06-24", today="2026-06-25")
    assert res["positions_freshness"]["stale"] is False
    assert not res["summary"]["headline"].startswith("⚠ STALE")


def test_unparseable_dates_do_not_flag_or_crash():
    res = voc.convert(target_drift={"rows": []}, holdings=[{"ticker": "X", "market_value": 1}],
                      positions_as_of="unknown", today=None)
    assert res["positions_freshness"] is None and res["summary"]["headline"]


def test_conditional_funder_over_target_is_last_resort_not_a_routine_trim():
    # NVDA over target (13.32% vs 12%) must surface as funding-ONLY-if-rail-breached, ranked LAST,
    # and excluded from the headline funding total (honors "don't trim NVDA unless concentration forces it").
    res = voc.convert(
        target_drift={"rows": [
            {"ticker": "GRNY", "direction": "OVERSIZED", "actual_pct": 6.9, "target_pct": 3.0},
            {"ticker": "NVDA", "direction": "OVERSIZED", "actual_pct": 13.32, "target_pct": 12.0}]},
        holdings=[{"ticker": "GRNY", "market_value": 1}, {"ticker": "NVDA", "market_value": 1}],
        book_value=1_856_472, funding_policy={"protected": ["GRNJ"], "conditional": {"NVDA": "concentration_rail"}})
    fund = {f["ticker"]: f for f in res["funding"]}
    assert res["funding"][0]["ticker"] == "GRNY"                          # GRNY funds first
    assert res["funding"][-1]["ticker"] == "NVDA"                         # NVDA sinks to last-resort
    assert fund["NVDA"]["conditional"] is True
    assert "not used by default" in fund["NVDA"]["note"]
    assert fund["NVDA"]["excess_usd"] > 0                                  # honest: it IS over target
    # NVDA is NOT a CONFIRM-HOLD command, and its excess is excluded from the funding total
    assert "NVDA" not in {c["ticker"] for c in res["command"]}
    assert res["summary"]["total_funding_usd"] == round(fund["GRNY"]["excess_usd"])
