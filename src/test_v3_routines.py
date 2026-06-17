"""V3 routine + registration tests (Task 8 / C-final).

Covers:
* `post_open_evidence_gate.evaluate_all_gates` — per-gate timing_engine
  evaluation, propose-and-stamp on state changes, honest-empty when a price
  is unavailable.
* `morning_scan.run_morning_scan` — flows through pattern_engine.detect_patterns
  and applies the two guards (factor-overlap, parabolic-chase) without
  emitting new cards.
* `morning_scan.load_parabolic_tickers` — pulls flagged tickers from
  parabolic_setups.json shape.
* The cloud-routine commit allowlist registers the V3 state files
  (dispositions.jsonl, timing_gates.json, prediction_signals.json) and the
  trigger registry artifacts.
* `state_ownership_map.json` registers dispositions + prediction_signals
  + trigger_registry
  with the required ownership fields and still validates.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cloud_routine_commit
import morning_scan as ms
import post_open_evidence_gate as gate_routine
import state_ownership_map as som
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()


# ---------------------------------------------------------------------------
# Cloud commit allowlist
# ---------------------------------------------------------------------------
def test_cloud_routine_allowlist_includes_v3_state_files():
    paths = cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/dispositions.jsonl" in paths
    assert "src/timing_gates.json" in paths
    assert "src/prediction_signals.json" in paths
    assert "src/trigger_registry.json" in paths
    assert "src/trigger_check_summary.json" in paths


def test_cloud_routine_allowlist_preserves_v2_entries():
    """Additive change must not remove V2 entries operators rely on."""
    paths = set(cloud_routine_commit.DEFAULT_ALLOWED_PATHS)
    for must_keep in (
        "src/cloud_routine_receipts.json",
        "src/latest_cockpit_feed.json",
        "src/heartbeat.json",
        "src/positions.json",
        "src/source_calls.json",
        "src/source_rates.json",
        "src/uw_endpoint_results.json",
        "src/uw_endpoint_interpretations.json",
        "src/top_prospects.json",
        "src/parabolic_setups.json",
        "src/fs_ingest_inventory.json",
    ):
        assert must_keep in paths


# ---------------------------------------------------------------------------
# State ownership map
# ---------------------------------------------------------------------------
def test_state_ownership_map_registers_v3_artifacts():
    payload = json.loads(
        (Path(__file__).resolve().parent / "state_ownership_map.json").read_text("utf-8")
    )
    ids = {obj.get("id") for obj in payload["objects"]}
    assert "dispositions" in ids
    assert "prediction_signals" in ids
    assert "timing_gates" in ids
    assert "trigger_registry" in ids


def test_state_ownership_map_still_validates_after_v3_additions():
    payload = json.loads(
        (Path(__file__).resolve().parent / "state_ownership_map.json").read_text("utf-8")
    )
    assert som.validate_ownership_map(payload) == []


# ---------------------------------------------------------------------------
# post_open_evidence_gate
# ---------------------------------------------------------------------------
def _gate(state="red_but_tested", lo=695.0, hi=705.0):
    return {
        "gate_id": "QQQ-NEWTON", "symbol": "QQQ", "kind": "support_band",
        "level_low": lo, "level_high": hi, "state": state,
        "source": "newton", "stated": "2026-06-08", "note": "band",
        "confirm_rule": "holds above ~705", "applies_to": ["*"],
        "blocks_full_size": True,
    }


def test_evidence_gate_proposes_green_when_price_clears_band():
    out = gate_routine.evaluate_all_gates(
        gates=[_gate(state="red_but_tested")],
        price_fn=lambda symbol: 710.0,
        as_of="2026-06-10T13:40:00+00:00",
    )
    assert len(out["evaluations"]) == 1
    row = out["evaluations"][0]
    assert row["current_state"] == "red_but_tested"
    assert row["suggested_state"] == "green"
    assert row["changed"] is True
    assert row["stamped_at"] == "2026-06-10T13:40:00+00:00"
    assert out["any_change"] is True
    assert out["gates_after"][0]["state"] == "green"
    assert out["gates_after"][0]["last_evaluated_at"] == "2026-06-10T13:40:00+00:00"


def test_evidence_gate_reports_no_change_when_price_inside_band():
    out = gate_routine.evaluate_all_gates(
        gates=[_gate(state="red_but_tested")],
        price_fn=lambda symbol: 700.0,
    )
    assert out["evaluations"][0]["changed"] is False
    assert out["any_change"] is False
    assert out["gates_after"][0].get("last_evaluated_at") is None


def test_evidence_gate_missing_price_records_honest_gap():
    out = gate_routine.evaluate_all_gates(
        gates=[_gate()],
        price_fn=lambda symbol: None,
    )
    assert out["honesty"]["prices_missing"] == ["QQQ-NEWTON"]
    assert "no evaluable" in out["evaluations"][0]["why"]


def test_evidence_gate_invokes_writer_only_on_state_change():
    captured: dict[str, object] = {}

    def writer(gates_after, evals):
        captured["gates_after"] = gates_after
        captured["evals"] = evals

    # No change: writer NOT called.
    gate_routine.evaluate_all_gates(
        gates=[_gate(state="red_but_tested")],
        price_fn=lambda s: 700.0,  # inside band
        writer=writer,
    )
    assert captured == {}

    # Change: writer IS called.
    gate_routine.evaluate_all_gates(
        gates=[_gate(state="red_but_tested")],
        price_fn=lambda s: 720.0,  # above band → green
        writer=writer,
    )
    assert "evals" in captured
    assert captured["gates_after"][0]["state"] == "green"


def test_evidence_gate_writer_failure_captured_but_does_not_raise():
    def bad_writer(gates_after, evals):
        raise OSError("disk full")

    out = gate_routine.evaluate_all_gates(
        gates=[_gate(state="red_but_tested")],
        price_fn=lambda s: 720.0,
        writer=bad_writer,
    )
    assert "stamp_error" in out["evaluations"][0]
    assert "OSError" in out["evaluations"][0]["stamp_error"]


def test_evidence_gate_file_writer_round_trip(tmp_path):
    gates_payload = {
        "gates": [_gate(state="red_but_tested")],
        "as_of": "2026-06-09",
    }
    path = tmp_path / "timing_gates.json"
    path.write_text(json.dumps(gates_payload), encoding="utf-8")
    writer = gate_routine.file_writer(path)
    out = gate_routine.evaluate_all_gates(
        gates=gates_payload["gates"],
        price_fn=lambda s: 720.0,
        writer=writer,
    )
    assert out["any_change"] is True
    rewritten = json.loads(path.read_text(encoding="utf-8"))
    assert rewritten["gates"][0]["state"] == "green"
    # Other top-level keys preserved.
    assert rewritten["as_of"] == "2026-06-09"


# ---------------------------------------------------------------------------
# morning_scan
# ---------------------------------------------------------------------------
def test_morning_scan_returns_summary_with_pattern_lanes():
    prospects = {
        "AMD": {"add_date": "2026-06-01", "add_price": 100.0,
                "add_price_date": "2026-06-01",
                "conviction": "BUILDING", "direction": "long"},
    }
    out = ms.run_morning_scan(
        prospects=prospects, source_calls=[],
        current_prices={"AMD": 80.0},
        weights=W, goal=G, as_of="2026-06-10T12:35:00+00:00",
    )
    summary = out["summary"]
    assert "endorsed_dip" in summary
    assert "tier_b_side_play" in summary
    # The BUILDING prospect must surface as a Tier-B side-play.
    assert summary["tier_b_side_play"] >= 1


def test_morning_scan_applies_parabolic_chase_dampener():
    prospects = {
        "AMD": {"add_date": "2026-06-01", "add_price": 100.0,
                "add_price_date": "2026-06-01",
                "conviction": "BUILDING", "direction": "long"},
    }
    out = ms.run_morning_scan(
        prospects=prospects, source_calls=[],
        current_prices={"AMD": 80.0},
        weights=W, goal=G,
        parabolic_tickers=["AMD"],
        as_of="2026-06-10T12:35:00+00:00",
    )
    # All emitted AMD cards must be flagged by the dampener.
    flagged = []
    for lane_cards in out["patterns"]["cards"].values():
        for card in lane_cards:
            if card["ticker"] == "AMD" and card.get("parabolic_chase_dampener"):
                flagged.append(card)
    assert flagged, "AMD parabolic flag should reach the cards"
    assert "AMD" in out["guards_applied"]["parabolic_chase_dampener"]


def test_morning_scan_applies_factor_overlap_caveat():
    prospects = {
        "AMD": {"add_date": "2026-06-01", "add_price": 100.0,
                "add_price_date": "2026-06-01",
                "conviction": "BUILDING", "direction": "long"},
    }
    out = ms.run_morning_scan(
        prospects=prospects, source_calls=[],
        current_prices={"AMD": 80.0},
        weights=W, goal=G,
        factor_exposures={"AMD": 45.0},
        as_of="2026-06-10T12:35:00+00:00",
    )
    # AMD endorsed_dip + tier_b cards should both pick up the caveat.
    caveated = []
    for lane_cards in out["patterns"]["cards"].values():
        for card in lane_cards:
            if card.get("factor_overlap_caveat"):
                caveated.append(card)
    assert caveated
    assert "AMD" in out["guards_applied"]["factor_overlap_caveat"]


def test_morning_scan_honest_empty_when_no_inputs():
    out = ms.run_morning_scan(
        prospects={}, source_calls=[], current_prices={},
        weights=W, goal=G, parabolic_tickers=[],
        fundstrat_bible={
            "deck_date": "2026-06-11",
            "sector_allocation": {"as_of": "2026-06-11"},
        },
        fs_ingest_inventory={"entries": []},
        as_of="2026-06-10T12:35:00+00:00",
    )
    assert out["summary"] == {
        "endorsed_dip": 0, "explicit_add": 0, "drumbeat": 0,
        "stale_leaps": 0, "overexposure_rotation": 0, "tier_b_side_play": 0,
    }
    assert out["honesty"]["parabolic_cache"].startswith("not_checked")
    assert out["warnings"][0]["key"] == "fs_ingest_inventory_missing"


def test_morning_scan_load_parabolic_tickers_extracts_phase_3_and_skip(tmp_path):
    payload = {
        "as_of": "2026-06-09",
        "results": [
            {"ticker": "AEHR", "phase": "Phase 3 (parabola)", "surface_tier": "SKIP"},
            {"ticker": "ZZZ", "phase": "Phase 1", "surface_tier": "REVIEW"},
            {"ticker": "Y", "phase": "Phase 2", "surface_tier": "SKIP"},
        ],
    }
    p = tmp_path / "parabolic_setups.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    flagged = ms.load_parabolic_tickers(p)
    assert sorted(flagged) == ["AEHR", "Y"]


def test_morning_scan_load_parabolic_tickers_honest_empty_when_absent(tmp_path):
    assert ms.load_parabolic_tickers(tmp_path / "missing.json") == []
