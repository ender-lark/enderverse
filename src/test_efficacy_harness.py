"""Efficacy harness -- regression proof that the shipped safety nets catch the
documented misses they were built for.

PRs #15-#19 shipped a trigger spine (`trigger_check.py` + `trigger_registry.json`)
and a caps-based sizing block (`directive_recs.py`) to fix real failures where
"the system knew but nobody pinged". This module replays those misses:

  * ASTS re-entry (5/5 + 5/12)  -> level_touch zone 65-70   (real registry)
  * EWRE tactical trigger (6/12) -> price_cross weekly_close (real registry)
  * GOOGL tranche-2 (6/19)       -> date_event              (real registry)
  * generic 6/9 re-check         -> iv_threshold            (representative)
  * MU parabolic (5/27)          -> acceleration            (real registry)

Each expressible scenario feeds a synthetic quote series through the live
`trigger_check.evaluate()` and asserts the trigger fires exactly once, emits a
push payload, and is idempotent on a second pass. The honest path is asserted
too: when quote data is missing the status is `not_checked`, never a false
"all clear". The MU parabolic miss used to be an unexpressible coverage gap;
the PARABOLIC-TRIGGER slice added the `acceleration` condition type and an
auto-arm hook in `parabolic_setup_screener.py`, so docs/efficacy_gaps.md GAP 1
is now RESOLVED and all four documented misses are proven-caught.

This file is regression scaffolding only: it imports and exercises the existing
modules, and never rebuilds the spine, the registry, or the card path.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trigger_check
from directive_recs import build_directive_cards
from tunables import load_conviction_weights, load_goal_tunables

SCENARIOS_PATH = Path(__file__).with_name("efficacy_scenarios.json")
SCENARIOS_DOC = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
SCENARIOS = SCENARIOS_DOC["scenarios"]

EXPRESSIBLE = [s for s in SCENARIOS if s["coverage"] == "expressible"]
GAP = [s for s in SCENARIOS if s["coverage"] == "gap"]
NON_DATE_EXPRESSIBLE = [s for s in EXPRESSIBLE if s["condition_type"] != "date_event"]
REAL_REGISTRY = [s for s in SCENARIOS if s["provenance"] == "real_registry"]


def _ids(scenarios: list[dict]) -> list[str]:
    return [s["id"] for s in scenarios]


def _live_registry() -> list[dict]:
    """The committed registry the spine ships with -- read-only here."""
    return trigger_check.load_registry(trigger_check.DEFAULT_REGISTRY)


def _build_trigger(scenario: dict) -> dict:
    """Build the trigger a scenario describes.

    Real-registry scenarios replay the *actual* armed trigger (deep-copied so the
    replay never mutates the shared rows); reconstructed scenarios build from the
    scenario's own spec via the public `make_trigger`.
    """
    if scenario["provenance"] == "real_registry":
        match = [r for r in _live_registry() if r.get("id") == scenario["registry_id"]]
        assert match, f"registry id {scenario['registry_id']!r} not found in live registry"
        replay = copy.deepcopy(match[0])
        # The live registry is allowed to move on. Historical efficacy scenarios
        # replay the trigger condition from an armed state, even after the real
        # production trigger has legitimately fired.
        replay["status"] = "armed"
        replay.pop("fired_at", None)
        replay.pop("fire_reason", None)
        return replay
    build = scenario["build"]
    return trigger_check.make_trigger(
        trigger_id=scenario["id"],
        ticker=scenario["ticker"],
        condition_type=build["condition_type"],
        params=dict(build["params"]),
        source=f"efficacy harness replay: {scenario['miss_class']}",
    )


def _quotes_for(scenario: dict, pass_key: str) -> dict:
    """Map a scenario pass (no_fire / fire / fire_again) into a quote map."""
    spec = scenario[pass_key]
    quote = spec.get("quote")
    if quote is None:
        return {}
    return {scenario["ticker"].upper(): quote}


def _assert_push_emitted(monkeypatch, fired: list[dict], ticker: str) -> None:
    """Prove a push payload is built from the fired triggers.

    `send_message` builds its payload from Pushover env config, so we supply
    dummy credentials and dry-run to exercise the real emit path without sending.
    """
    monkeypatch.setenv("PUSHOVER_APP_TOKEN", "efficacy-test-token")
    monkeypatch.setenv("PUSHOVER_USER_KEY", "efficacy-test-user")
    delivery = trigger_check.send_fired_notifications(fired, dry_run=True)
    assert delivery["attempted"] is True
    payload = delivery.get("payload")
    assert payload, f"no push payload built for fired {ticker} trigger: {delivery!r}"
    assert ticker in payload.get("message", ""), "push payload did not name the ticker"
    assert payload.get("priority") == "1", "fired-trigger push should be high priority"
    # The message content also derives from the fired rows themselves.
    assert ticker in trigger_check._notification_message(fired)


# ---------------------------------------------------------------------------
# Scenario file integrity
# ---------------------------------------------------------------------------

def test_scenarios_file_wellformed_and_covers_the_four_misses():
    assert SCENARIOS_DOC["schema"] == "efficacy_scenarios.v1"
    miss_classes = {s["miss_class"] for s in SCENARIOS}
    for required in ("asts_reentry", "mu_parabolic", "ewre_tactical", "generic_6_9"):
        assert required in miss_classes, f"missing documented miss: {required}"

    # GAP 1 resolved: the MU parabolic class is now expressible via the
    # `acceleration` condition type, so no coverage gaps remain -- all four
    # documented misses are proven-caught.
    assert GAP == [], f"unexpected unresolved coverage gap(s): {[g['id'] for g in GAP]}"
    assert "mu_parabolic" in {s["miss_class"] for s in EXPRESSIBLE}

    for s in SCENARIOS:
        assert s["id"] and s["ticker"] and s["dates"]
        assert s["condition_type"]
        assert s["coverage"] in {"expressible", "gap"}
        if s["coverage"] == "expressible":
            assert "no_fire" in s and "fire" in s
            assert s["expected"]["fired"] is True
            assert s["expected"]["push_emitted"] is True
        else:
            assert "gap_probe" in s
            assert s["expected"]["expressible"] is False

    # Every spine condition type is exercised by at least one expressible scenario,
    # so a silent regression in any one of them is caught here.
    exercised = {s["condition_type"] for s in EXPRESSIBLE}
    assert set(SCENARIOS_DOC["spine_condition_types"]) <= exercised


@pytest.mark.parametrize("scenario", REAL_REGISTRY, ids=_ids(REAL_REGISTRY))
def test_real_registry_scenarios_match_live_registry(scenario):
    """Keep the replay honest: real-registry scenarios must match the live row,
    so the harness can't drift away from what is actually armed."""
    match = [r for r in _live_registry() if r.get("id") == scenario["registry_id"]]
    assert match, f"{scenario['registry_id']!r} not in live registry"
    cond = match[0].get("condition") or {}
    assert cond.get("type") == scenario["condition_type"]
    params = cond.get("params") or {}
    for key, value in scenario["expected_params_subset"].items():
        assert params.get(key) == value, (
            f"{scenario['registry_id']}.{key} = {params.get(key)!r}, "
            f"scenario expects {value!r}"
        )


# ---------------------------------------------------------------------------
# The core proof: each documented miss now fires once, pushes, and is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", EXPRESSIBLE, ids=_ids(EXPRESSIBLE))
def test_documented_miss_fires_once_emits_push_and_is_idempotent(scenario, monkeypatch):
    registry = [_build_trigger(scenario)]
    trigger_id = registry[0]["id"]
    ticker = scenario["ticker"].upper()

    # 1) Before the signal prints, nothing fires and the trigger stays armed.
    pre = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map(_quotes_for(scenario, "no_fire")),
        as_of=scenario["no_fire"]["as_of"],
    )
    assert pre["fired_count"] == 0, f"{scenario['id']} fired before its condition was met"
    assert registry[0]["status"] == "armed"

    # 2) The documented signal prints -> fires exactly once.
    fired = trigger_check.evaluate(
        registry,
        trigger_check.quote_fn_from_map(_quotes_for(scenario, "fire")),
        as_of=scenario["fire"]["as_of"],
    )
    assert [row["id"] for row in fired] == [trigger_id], (
        f"{scenario['id']} did not fire exactly once (got {[r['id'] for r in fired]})"
    )
    assert registry[0]["status"] == "fired"
    reason_substr = scenario["fire"].get("expected_fire_reason_contains")
    if reason_substr:
        assert reason_substr in (fired[0].get("fire_reason") or ""), (
            f"{scenario['id']} fire_reason {fired[0].get('fire_reason')!r} "
            f"missing {reason_substr!r}"
        )

    # 3) A push payload is emitted from the fire.
    _assert_push_emitted(monkeypatch, fired, ticker)

    # 4) Idempotent: a second satisfying pass emits nothing new (no double-ping),
    #    and the emit path sends nothing when there are no newly fired triggers.
    again_key = "fire_again" if "fire_again" in scenario else "fire"
    refired = trigger_check.evaluate(
        registry,
        trigger_check.quote_fn_from_map(_quotes_for(scenario, again_key)),
        as_of=scenario[again_key]["as_of"],
    )
    assert refired == [], f"{scenario['id']} re-fired on a second pass (not idempotent)"
    assert trigger_check.send_fired_notifications(refired, dry_run=True)["attempted"] is False


@pytest.mark.parametrize("scenario", NON_DATE_EXPRESSIBLE, ids=_ids(NON_DATE_EXPRESSIBLE))
def test_honest_path_missing_quote_is_not_checked_never_clear(scenario):
    """When quote_fn returns no data, the trigger is `not_checked` and stays
    armed -- never a false all-clear and never a silent fire."""
    registry = [_build_trigger(scenario)]
    report = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map({}),  # no data for the ticker
        as_of=scenario["fire"]["as_of"],
    )
    assert report["fired_count"] == 0
    assert report["not_checked_count"] == 1
    assert report["status"] == "not_checked"
    assert report["status"] != "checked_clear"
    assert registry[0]["status"] == "armed"
    assert "quote not checked" in report["not_checked"][0]["reason"]


# ---------------------------------------------------------------------------
# GAP 1 resolved: parabolic acceleration is now expressible and proven-caught
# ---------------------------------------------------------------------------

def test_mu_parabolic_now_caught_by_acceleration_condition_type():
    """The miss that used to be an unexpressible gap now fires.

    The spine has an `acceleration` condition type, the MU scenario is armed in
    the live registry, a slow grind to the same price does NOT fire, and the
    documented 5/27 acceleration fires it exactly once -- flipping GAP 1 from
    "armed but dead" to caught.
    """
    scenario = [s for s in SCENARIOS if s["miss_class"] == "mu_parabolic"][0]
    assert scenario["coverage"] == "expressible"
    assert scenario["condition_type"] == "acceleration"
    assert "acceleration" in trigger_check.CONDITION_TYPES

    registry = [_build_trigger(scenario)]
    trigger_id = registry[0]["id"]

    # A slow grind to the same price level (small percent move, lower phase) does
    # NOT fire -- the false positive the gaps doc warned about.
    pre = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map(_quotes_for(scenario, "no_fire")),
        as_of=scenario["no_fire"]["as_of"],
    )
    assert pre["fired_count"] == 0
    assert registry[0]["status"] == "armed"

    # The documented 5/27 acceleration prints -> fires exactly once.
    fired = trigger_check.evaluate(
        registry,
        trigger_check.quote_fn_from_map(_quotes_for(scenario, "fire")),
        as_of=scenario["fire"]["as_of"],
    )
    assert [row["id"] for row in fired] == [trigger_id]
    assert registry[0]["status"] == "fired"


def test_efficacy_gaps_doc_marks_parabolic_gap_resolved():
    doc = Path(__file__).resolve().parents[1] / "docs" / "efficacy_gaps.md"
    assert doc.is_file(), "docs/efficacy_gaps.md is missing"
    text = doc.read_text(encoding="utf-8").lower()
    assert "parabolic" in text
    assert "mu parabolic" in text
    assert "acceleration" in text
    assert "resolved" in text
    assert "condition type" in text


# ---------------------------------------------------------------------------
# Sizing-block regression: BUY/ADD cards must carry the caps-sourced sizing block
# ---------------------------------------------------------------------------
# Fixtures mirror the proven shapes in test_directive_recs.py so build_directive_cards
# runs against the real card path. The 4.5-7.6x under-sizing fix (T2/PR#18) put a
# caps-sourced sizing block on every BUY/ADD card; this guard fails if it ever
# silently drops off again.

def _sizing_accounts() -> list[dict]:
    base = {"crypto_only": False, "tax_type": "taxable",
            "tax_flag": "TAXABLE - gains realize", "option_value": 0.0}
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


def _sizing_insights() -> dict:
    return {"insights": [{
        "insight_id": "INSIGHT-950", "statement": "s", "polarity": "bullish",
        "belief_strength": 50, "status": "ACTIVE", "stated": "2026-06-10",
        "last_reviewed": "2026-06-10", "sectors": [], "keywords": [],
        "tickers_mapped": ["GOOGL"], "tickers_adjacent": [], "watch_tickers": [],
        "factor_tags": [], "evidence_for": [], "evidence_against": [],
    }]}


def _sizing_gate() -> dict:
    return {
        "gate_id": "QQQ-TEST", "symbol": "QQQ", "kind": "support_band",
        "level_low": 695.0, "level_high": 705.0, "state": "red_but_tested",
        "source": "newton", "stated": "2026-06-08", "note": "band",
        "confirm_rule": "holds above ~705", "applies_to": ["ai_semis"],
        "blocks_full_size": True,
    }


def _sizing_feed() -> dict:
    return {
        "portfolio_views": {"views": {"combined": {
            "rows": [{"ticker": "NVDA", "market_value": 50000}],
            "total_value": 1890000,
        }}},
        "actions": [
            {"ticker": "GOOGL", "goal_score": 80, "kind": "lean_in"},
            {"ticker": "MAGS", "goal_score": 70, "kind": "trim"},
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


def test_buy_add_cards_carry_caps_sourced_sizing_block():
    out = build_directive_cards(
        feed=_sizing_feed(),
        weights=load_conviction_weights(),
        goal=load_goal_tunables(),
        insights_payload=_sizing_insights(),
        accounts=_sizing_accounts(),
        gates=[_sizing_gate()],
        uw_states={},
        entry_zones={},
        today="2026-06-10",
    )
    cards = out["cards"] + out["backlog"]
    buys = [c for c in cards if c.get("direction") in {"BUY", "ADD"}]
    assert buys, "no BUY/ADD card generated -- sizing regression guard cannot run"
    for card in buys:
        sizing = card.get("sizing")
        assert sizing is not None, (
            f"{card.get('ticker')} BUY/ADD card has no sizing block "
            "(this is exactly the under-sizing regression we are guarding against)"
        )
        assert sizing["source"] == "caps", (
            f"{card.get('ticker')} sizing is not caps-sourced: {sizing!r}"
        )
        assert isinstance(sizing.get("suggested_usd"), (int, float))
        assert sizing.get("cap_basis")


# ---------------------------------------------------------------------------
# Meta: a malformed trigger can't sit silently armed-but-dead
# ---------------------------------------------------------------------------

def _coalesce(*values):
    for value in values:
        if value is not None:
            return value
    return None


_REQUIRED_PARAMS = {
    "price_cross": lambda p: trigger_check._num(_coalesce(p.get("level"), p.get("threshold"))) is not None,
    "level_touch": lambda p: (
        trigger_check._num(_coalesce(p.get("zone_low"), p.get("low"))) is not None
        and trigger_check._num(_coalesce(p.get("zone_high"), p.get("high"))) is not None
    ),
    "iv_threshold": lambda p: trigger_check._num(_coalesce(p.get("threshold"), p.get("level"))) is not None,
    "date_event": lambda p: trigger_check._date_from_text(_coalesce(p.get("date"), p.get("event_date"))) is not None,
    "acceleration": lambda p: any(
        value is not None
        for value in (
            trigger_check._num(_coalesce(p.get("threshold"), p.get("level"))),
            trigger_check._num(p.get("min_consecutive_up_days")),
            trigger_check._num(p.get("min_phase")),
        )
    ),
}


def test_every_armed_registry_trigger_is_resolvable_and_unexpired():
    rows = _live_registry()
    armed = [r for r in rows if str(r.get("status") or "armed").lower() in trigger_check.ARMED_STATUSES]
    assert armed, "live registry has no armed triggers to validate"

    for row in armed:
        rid = row.get("id")
        cond = row.get("condition") if isinstance(row.get("condition"), dict) else {}
        ctype = cond.get("type")
        params = cond.get("params") if isinstance(cond.get("params"), dict) else {}

        # Resolvable condition type -- an unknown type would route to not_checked
        # forever (armed but dead).
        assert ctype in trigger_check.CONDITION_TYPES, (
            f"{rid}: condition type {ctype!r} is not supported -- armed but dead"
        )
        assert str(row.get("ticker") or "").strip(), f"{rid}: missing ticker"

        # Required params for known types must be present and parseable, so the
        # evaluator won't silently drop the trigger to not_checked on "missing X".
        checker = _REQUIRED_PARAMS.get(ctype)
        if checker is not None:
            assert checker(params), f"{rid}: {ctype} has missing/unparseable params {params!r}"

        # A real, forward-looking arming window. We assert expires parses and is
        # on/after registered_at rather than comparing to wall-clock today --
        # comparing to today would turn this into a time-bomb that breaks the day
        # any real trigger legitimately expires.
        expires = trigger_check._date_from_text(row.get("expires"))
        assert expires is not None, f"{rid}: missing/unparseable expires {row.get('expires')!r}"
        registered = trigger_check._date_from_text(row.get("registered_at"))
        if registered is not None:
            assert expires >= registered, (
                f"{rid}: expires {expires} predates registered_at {registered} (born expired)"
            )
