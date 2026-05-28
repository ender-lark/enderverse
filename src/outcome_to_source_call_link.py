#!/usr/bin/env python3
"""
outcome_to_source_call_link.py — v11.26 NEW ARCHITECTURE

PURPOSE
    Closes the calibration loop.  When outcome_logger.py detects an exit
    (FULL_EXIT or PARTIAL_EXIT) that matches a PENDING Tier-A or Tier-B
    source call, this script produces structured Notion update payloads
    to write the resolution (WIN / LOSS / PUSH) back to 📊 Source Call Log
    (ds e7def40e-1492-458a-9de8-bd77cd3f8471).

    Without this loop closure, the source calibration data set stagnates
    at n=6 forever and never crosses the n≥15 threshold needed to trigger
    P-SOURCE-CALIBRATION discount bands.

ROLE IN v11.26 SYSTEM
    outcome_logger.py    →  (exits + source-call matches)
                              ↓
    outcome_to_source_call_link.py    (produces Notion update payloads)
                              ↓
    📊 Source Call Log (Notion DB)    (writes via notion-update-page)
                              ↓
    source_call_tracker.py    (re-derives hit rates from updated log)
                              ↓
    pretrade_gate.py + conviction_sizing_calibrator.py    (apply discounts)

OUTPUT
    A list of Notion update payloads.  Each payload identifies the source
    call to update + the suggested Status field + Outcome Tag + the
    triggering trade outcome for audit.

    DOES NOT auto-write to Notion.  The operator MUST review and approve
    each suggested resolution before the write happens (per AEM Cat C
    rules — affects calibration data which feeds downstream framework
    decisions).

USAGE
    python outcome_to_source_call_link.py --self-test
    python outcome_to_source_call_link.py \\
        --outcomes outcomes.json --source-calls source_calls.json
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Dict, Optional


# ============================================================================
# CONSTANTS
# ============================================================================

# Minimum window (days) between source call date and exit date for the
# resolution to be considered valid.  Calls older than this are "stale" —
# the position may have moved for unrelated reasons.
MAX_CALL_AGE_DAYS = 180

# Tier-A calls have a 14d resolution window; Tier-B have 30d; Tier-C 120d.
# (Mirrors P-SOURCE-CALIBRATION spec from v11.26 docs.)
TIER_RESOLUTION_WINDOW_DAYS = {
    "A": 14,
    "B": 30,
    "C": 120,
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class LinkProposal:
    source_call_id: str
    source_call_tier: str
    source_call_ticker: str
    source: Optional[str]
    suggested_resolution: str  # WIN / LOSS / PUSH / STALE
    confidence: str            # HIGH / MEDIUM / LOW

    triggering_outcome: Dict
    notion_payload: Dict
    rationale: str
    flags: List[str] = field(default_factory=list)


@dataclass
class LinkReport:
    proposals: List[LinkProposal] = field(default_factory=list)
    unmatched_outcomes: List[Dict] = field(default_factory=list)
    summary: str = ""


# ============================================================================
# HELPERS
# ============================================================================

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _build_notion_payload(call: Dict, resolution: str,
                          outcome: Dict, rationale: str) -> Dict:
    """
    Notion update payload for 📊 Source Call Log.
    Field names match presumed schema; operator can adjust to live schema.
    """
    return {
        "page_id": call.get("id") or call.get("call_id"),
        "command": "update_properties",
        "properties": {
            "Status": "RESOLVED",
            "Outcome": resolution,
            "Resolution Date": outcome.get("event_date") or outcome.get("snapshot_date_new"),
            "Auto-Linked Trade Outcome": outcome.get("ticker", ""),
            "Resolution Rationale": rationale,
        }
    }


# ============================================================================
# CORE LINKER
# ============================================================================

def link(outcomes: List[Dict], source_calls: List[Dict],
         today: Optional[datetime] = None) -> LinkReport:
    """
    Given outcome rows (as produced by outcome_logger.py to_notion_payloads
    or the raw OutcomeReport JSON) + pending source calls, produce link
    proposals.

    outcomes: list of trade outcome dicts.  Each should have:
        - ticker
        - change_type (FULL_EXIT or PARTIAL_EXIT or NEW_POSITION/SIZE_INCREASE)
        - source_call_id_match (str, from outcome_logger v11.26)
        - source_call_resolution_suggested (str: WIN/LOSS/PUSH)
        - snapshot_date_new
        - shares_delta, estimated_exit_value, etc.

    source_calls: list of pending Tier A/B/C source calls.  Each should have:
        - id
        - tier
        - named_ticker
        - direction (long/short)
        - target_price
        - call_date (when the call was made)
        - source (Newton/Lee/Meridian/Farrell)
    """
    if today is None:
        today = datetime.now()

    # Index source calls by id for quick lookup
    calls_by_id: Dict[str, Dict] = {}
    for c in source_calls:
        cid = c.get("id") or c.get("call_id")
        if cid:
            calls_by_id[cid] = c

    report = LinkReport()

    for outcome in outcomes:
        match_id = outcome.get("source_call_id_match")
        suggestion = outcome.get("source_call_resolution_suggested")

        if not match_id or not suggestion:
            # No source call match — outcome is not linkable
            if outcome.get("change_type") in ("FULL_EXIT", "PARTIAL_EXIT"):
                report.unmatched_outcomes.append({
                    "ticker": outcome.get("ticker"),
                    "change_type": outcome.get("change_type"),
                    "snapshot_date": outcome.get("snapshot_date_new"),
                })
            continue

        call = calls_by_id.get(match_id)
        if not call:
            # Match ID present but the source call isn't in our pending list
            # — could be already-resolved or wrong ID
            continue

        tier = (call.get("tier") or "").upper()
        confidence = "HIGH"
        flags = []

        # Check resolution window
        call_date = _parse_date(call.get("call_date"))
        exit_date = _parse_date(outcome.get("snapshot_date_new") or outcome.get("event_date"))

        if call_date and exit_date:
            age_days = (exit_date - call_date).days
            window = TIER_RESOLUTION_WINDOW_DAYS.get(tier, MAX_CALL_AGE_DAYS)
            if age_days > MAX_CALL_AGE_DAYS:
                suggestion = "STALE"
                confidence = "LOW"
                flags.append(f"call_age_{age_days}d_exceeds_max")
            elif age_days > window:
                # Outside tier window — confidence reduced but still linkable
                confidence = "MEDIUM"
                flags.append(f"outside_tier_window_{age_days}d_vs_{window}d")

        rationale = _build_rationale(outcome, call, suggestion, confidence, flags)
        payload = _build_notion_payload(call, suggestion, outcome, rationale)

        report.proposals.append(LinkProposal(
            source_call_id=match_id,
            source_call_tier=tier,
            source_call_ticker=call.get("named_ticker", ""),
            source=call.get("source"),
            suggested_resolution=suggestion,
            confidence=confidence,
            triggering_outcome={
                "ticker": outcome.get("ticker"),
                "change_type": outcome.get("change_type"),
                "exit_date": outcome.get("snapshot_date_new")
                             or outcome.get("event_date"),
                "exit_value": outcome.get("estimated_exit_value"),
                "realized_pnl": outcome.get("estimated_realized_pnl"),
            },
            notion_payload=payload,
            rationale=rationale,
            flags=flags,
        ))

    n_win = sum(1 for p in report.proposals if p.suggested_resolution == "WIN")
    n_loss = sum(1 for p in report.proposals if p.suggested_resolution == "LOSS")
    n_push = sum(1 for p in report.proposals if p.suggested_resolution == "PUSH")
    n_stale = sum(1 for p in report.proposals if p.suggested_resolution == "STALE")

    report.summary = (
        f"{len(report.proposals)} link proposal(s): "
        f"{n_win} WIN, {n_loss} LOSS, {n_push} PUSH, {n_stale} STALE. "
        f"{len(report.unmatched_outcomes)} unmatched exit(s)."
    )
    return report


def _build_rationale(outcome: Dict, call: Dict, suggestion: str,
                     confidence: str, flags: List[str]) -> str:
    ticker = call.get("named_ticker", "?")
    direction = call.get("direction", "?")
    target = call.get("target_price")
    exit_val = outcome.get("estimated_exit_value")
    shares_delta = outcome.get("shares_delta") or 0
    exit_price = None
    if shares_delta and exit_val:
        try:
            exit_price = exit_val / abs(shares_delta)
        except ZeroDivisionError:
            pass

    parts = []
    if direction == "long":
        if target is not None and exit_price is not None:
            if suggestion == "WIN":
                parts.append(f"{ticker} LONG call (target ${target:.2f}) "
                             f"resolved WIN: exit @ ${exit_price:.2f} "
                             f">= target")
            elif suggestion == "LOSS":
                parts.append(f"{ticker} LONG call (target ${target:.2f}) "
                             f"resolved LOSS: exit @ ${exit_price:.2f} "
                             f"< target")
            elif suggestion == "PUSH":
                parts.append(f"{ticker} LONG call (target ${target:.2f}) "
                             f"resolved PUSH: exit @ ${exit_price:.2f} "
                             f"~= target (within 2%)")
    elif direction == "short":
        if target is not None and exit_price is not None:
            if suggestion == "WIN":
                parts.append(f"{ticker} SHORT call (target ${target:.2f}) "
                             f"resolved WIN: exit @ ${exit_price:.2f} <= target")
            elif suggestion == "LOSS":
                parts.append(f"{ticker} SHORT call (target ${target:.2f}) "
                             f"resolved LOSS: exit @ ${exit_price:.2f} > target")

    if suggestion == "STALE":
        parts.append(f"{ticker} call too old to resolve confidently "
                     f"({'; '.join(flags) if flags else ''})")

    parts.append(f"confidence: {confidence}")
    if flags and suggestion != "STALE":
        parts.append("flags: " + "; ".join(flags))
    return ". ".join(parts) + "."


# ============================================================================
# OUTPUT FORMATTERS
# ============================================================================

def format_text_report(r: LinkReport) -> str:
    out = []
    out.append("=" * 70)
    out.append("OUTCOME → SOURCE CALL LINK PROPOSALS")
    out.append("=" * 70)
    out.append(r.summary)
    out.append("")

    if r.proposals:
        out.append("-- PROPOSALS " + "-" * 50)
        for p in r.proposals:
            icon = {"WIN": "🟢", "LOSS": "🔴", "PUSH": "🟡", "STALE": "⚪"}.get(
                p.suggested_resolution, "•")
            out.append(f"  {icon} {p.source_call_ticker} (call {p.source_call_id})")
            out.append(f"        tier={p.source_call_tier}, source={p.source}, "
                       f"resolution={p.suggested_resolution}, "
                       f"confidence={p.confidence}")
            out.append(f"        rationale: {p.rationale}")
            if p.flags:
                out.append(f"        flags: {', '.join(p.flags)}")
        out.append("")

    if r.unmatched_outcomes:
        out.append("-- UNMATCHED EXITS (no source call link) " + "-" * 20)
        for o in r.unmatched_outcomes:
            out.append(f"  {o['ticker']:8} {o['change_type']:<14} "
                       f"on {o['snapshot_date']}")
        out.append("")

    return "\n".join(out)


def format_json_report(r: LinkReport) -> str:
    return json.dumps(asdict(r), indent=2, default=str)


def to_notion_payloads(r: LinkReport) -> List[Dict]:
    """Return only the Notion update payloads (for direct write-back)."""
    return [p.notion_payload for p in r.proposals]


# ============================================================================
# SELF-TEST
# ============================================================================

def _self_test() -> bool:
    passed = 0
    failed = 0

    def assert_eq(actual, expected, label):
        nonlocal passed, failed
        if actual == expected:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}: expected {expected!r}, got {actual!r}")

    def assert_true(condition, label):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    today = datetime(2026, 5, 19)

    # ----- Test 1: WIN resolution
    outcomes = [{
        "ticker": "LEU",
        "change_type": "FULL_EXIT",
        "source_call_id_match": "call_xyz",
        "source_call_resolution_suggested": "WIN",
        "snapshot_date_new": "2026-05-19",
        "estimated_exit_value": 96000,
        "shares_delta": -500,  # exit price = 192
    }]
    calls = [{
        "id": "call_xyz", "tier": "A", "named_ticker": "LEU",
        "direction": "long", "target_price": 180.0,
        "call_date": "2026-05-10",
        "source": "Newton",
    }]
    r = link(outcomes, calls, today=today)
    assert_eq(len(r.proposals), 1, "WIN proposal created")
    p = r.proposals[0]
    assert_eq(p.suggested_resolution, "WIN", "resolution WIN")
    assert_eq(p.confidence, "HIGH", "HIGH confidence (within window)")
    assert_eq(p.source, "Newton", "source pass-through")
    assert_eq(p.source_call_tier, "A", "tier A")
    assert_eq(p.notion_payload["properties"]["Status"], "RESOLVED",
              "notion payload status")
    assert_eq(p.notion_payload["properties"]["Outcome"], "WIN", "notion outcome")

    # ----- Test 2: LOSS resolution
    outcomes = [{
        "ticker": "MP",
        "change_type": "FULL_EXIT",
        "source_call_id_match": "call_mp",
        "source_call_resolution_suggested": "LOSS",
        "snapshot_date_new": "2026-05-19",
        "estimated_exit_value": 39680,
        "shares_delta": -660,  # exit price ~60
    }]
    calls = [{
        "id": "call_mp", "tier": "B", "named_ticker": "MP",
        "direction": "long", "target_price": 80.0,
        "call_date": "2026-04-25",
        "source": "Newton",
    }]
    r = link(outcomes, calls, today=today)
    assert_eq(r.proposals[0].suggested_resolution, "LOSS", "LOSS resolution")
    # 24 days old, Tier B window is 30d → still HIGH confidence
    assert_eq(r.proposals[0].confidence, "HIGH",
              "B tier 24d window: HIGH confidence")

    # ----- Test 3: outside tier window → MEDIUM confidence
    calls[0]["call_date"] = "2026-04-01"  # 48 days ago for Tier B (>30d)
    r = link(outcomes, calls, today=today)
    assert_eq(r.proposals[0].confidence, "MEDIUM",
              "outside tier window → MEDIUM")
    assert_true(any("outside_tier_window" in f for f in r.proposals[0].flags),
                "outside_tier_window flag")

    # ----- Test 4: stale call (>180d) → STALE resolution
    calls[0]["call_date"] = "2025-10-15"  # ~210d ago
    r = link(outcomes, calls, today=today)
    assert_eq(r.proposals[0].suggested_resolution, "STALE",
              "STALE for >180d old call")
    assert_eq(r.proposals[0].confidence, "LOW", "STALE = LOW confidence")

    # ----- Test 5: outcome without source_call_id_match → unmatched
    outcomes = [{
        "ticker": "X",
        "change_type": "FULL_EXIT",
        "source_call_id_match": None,
        "source_call_resolution_suggested": None,
        "snapshot_date_new": "2026-05-19",
    }]
    r = link(outcomes, [], today=today)
    assert_eq(len(r.proposals), 0, "no proposal when no match_id")
    assert_eq(len(r.unmatched_outcomes), 1, "unmatched exit recorded")

    # ----- Test 6: outcome with match_id but call not in pending list
    outcomes = [{
        "ticker": "Y",
        "change_type": "FULL_EXIT",
        "source_call_id_match": "ghost_call",
        "source_call_resolution_suggested": "WIN",
        "snapshot_date_new": "2026-05-19",
    }]
    r = link(outcomes, [], today=today)  # empty calls list
    assert_eq(len(r.proposals), 0, "no proposal when call not in pending")

    # ----- Test 7: NEW_POSITION outcomes not in unmatched list
    outcomes = [{
        "ticker": "Z",
        "change_type": "NEW_POSITION",
        "source_call_id_match": None,
        "snapshot_date_new": "2026-05-19",
    }]
    r = link(outcomes, [], today=today)
    assert_eq(len(r.unmatched_outcomes), 0,
              "NEW_POSITION not in unmatched (only exits)")

    # ----- Test 8: rationale text quality
    outcomes = [{
        "ticker": "LEU",
        "change_type": "FULL_EXIT",
        "source_call_id_match": "call_a",
        "source_call_resolution_suggested": "WIN",
        "snapshot_date_new": "2026-05-19",
        "estimated_exit_value": 96000,
        "shares_delta": -500,
    }]
    calls = [{
        "id": "call_a", "tier": "A", "named_ticker": "LEU",
        "direction": "long", "target_price": 180.0,
        "call_date": "2026-05-10", "source": "Newton",
    }]
    r = link(outcomes, calls, today=today)
    rationale = r.proposals[0].rationale
    assert_true("LEU" in rationale, "rationale mentions ticker")
    assert_true("180" in rationale, "rationale mentions target")
    assert_true("192" in rationale, "rationale mentions exit price")
    assert_true("WIN" in rationale, "rationale mentions WIN")
    assert_true("HIGH" in rationale, "rationale mentions confidence")

    # ----- Test 9: text + JSON formatters
    text = format_text_report(r)
    assert_true("LINK PROPOSALS" in text, "text report header")
    assert_true("LEU" in text, "text mentions ticker")
    js = format_json_report(r)
    parsed = json.loads(js)
    assert_eq(len(parsed["proposals"]), 1, "JSON has proposal")

    # ----- Test 10: to_notion_payloads helper
    payloads = to_notion_payloads(r)
    assert_eq(len(payloads), 1, "1 payload")
    assert_eq(payloads[0]["properties"]["Outcome"], "WIN", "payload outcome WIN")
    assert_eq(payloads[0]["command"], "update_properties", "payload command")

    # ----- Test 11: short call (SHORT direction)
    outcomes = [{
        "ticker": "SPY",
        "change_type": "FULL_EXIT",
        "source_call_id_match": "spy_short",
        "source_call_resolution_suggested": "WIN",
        "snapshot_date_new": "2026-05-19",
        "estimated_exit_value": 71000,
        "shares_delta": -100,  # exit price = 710
    }]
    calls = [{
        "id": "spy_short", "tier": "A", "named_ticker": "SPY",
        "direction": "short", "target_price": 720.0,
        "call_date": "2026-05-10", "source": "Newton",
    }]
    r = link(outcomes, calls, today=today)
    rationale = r.proposals[0].rationale
    assert_true("SHORT" in rationale, "short call rationale mentions SHORT")

    # ----- Test 12: multiple outcomes, mixed results
    outcomes = [
        {"ticker": "A", "change_type": "FULL_EXIT",
         "source_call_id_match": "c1",
         "source_call_resolution_suggested": "WIN",
         "snapshot_date_new": "2026-05-19",
         "estimated_exit_value": 10000, "shares_delta": -100},
        {"ticker": "B", "change_type": "FULL_EXIT",
         "source_call_id_match": "c2",
         "source_call_resolution_suggested": "LOSS",
         "snapshot_date_new": "2026-05-19",
         "estimated_exit_value": 5000, "shares_delta": -100},
        {"ticker": "C", "change_type": "FULL_EXIT",
         "source_call_id_match": None,
         "source_call_resolution_suggested": None,
         "snapshot_date_new": "2026-05-19"},
    ]
    calls = [
        {"id": "c1", "tier": "A", "named_ticker": "A",
         "direction": "long", "target_price": 90.0,
         "call_date": "2026-05-12", "source": "Newton"},
        {"id": "c2", "tier": "B", "named_ticker": "B",
         "direction": "long", "target_price": 100.0,
         "call_date": "2026-05-01", "source": "Lee"},
    ]
    r = link(outcomes, calls, today=today)
    assert_eq(len(r.proposals), 2, "2 proposals from 2 matched outcomes")
    assert_eq(len(r.unmatched_outcomes), 1, "1 unmatched exit")
    n_win = sum(1 for p in r.proposals if p.suggested_resolution == "WIN")
    n_loss = sum(1 for p in r.proposals if p.suggested_resolution == "LOSS")
    assert_eq(n_win, 1, "1 WIN")
    assert_eq(n_loss, 1, "1 LOSS")
    assert_true("1 WIN, 1 LOSS" in r.summary, "summary line accurate")

    # ----- Test 13: empty inputs
    r = link([], [], today=today)
    assert_eq(len(r.proposals), 0, "empty: no proposals")
    assert_eq(len(r.unmatched_outcomes), 0, "empty: no unmatched")

    # ----- Test 14: PUSH resolution
    outcomes = [{
        "ticker": "X",
        "change_type": "FULL_EXIT",
        "source_call_id_match": "call_push",
        "source_call_resolution_suggested": "PUSH",
        "snapshot_date_new": "2026-05-19",
        "estimated_exit_value": 17800,  # exit @ $178, target $180 → within 2%
        "shares_delta": -100,
    }]
    calls = [{
        "id": "call_push", "tier": "A", "named_ticker": "X",
        "direction": "long", "target_price": 180.0,
        "call_date": "2026-05-15", "source": "Newton",
    }]
    r = link(outcomes, calls, today=today)
    assert_eq(r.proposals[0].suggested_resolution, "PUSH", "PUSH resolution")

    # ----- Test 15: realistic operator scenario (MP loss case)
    outcomes = [{
        "ticker": "MP",
        "change_type": "FULL_EXIT",
        "source_call_id_match": "newton_mp_long",
        "source_call_resolution_suggested": "LOSS",
        "snapshot_date_new": "2026-05-19",
        "estimated_exit_value": 39680,
        "shares_delta": -660,
    }]
    calls = [{
        "id": "newton_mp_long",
        "tier": "B",
        "named_ticker": "MP",
        "direction": "long",
        "target_price": 80.0,
        "call_date": "2026-05-05",
        "source": "Newton",
    }]
    r = link(outcomes, calls, today=today)
    p = r.proposals[0]
    assert_eq(p.suggested_resolution, "LOSS", "MP exit = LOSS")
    assert_eq(p.notion_payload["properties"]["Status"], "RESOLVED",
              "MP notion status RESOLVED")
    assert_true(p.notion_payload["page_id"] == "newton_mp_long",
                "page_id propagated for notion-update-page")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return failed == 0


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="Outcome→Source Call Linker v11.26")
    p.add_argument("--outcomes", help="Outcomes JSON")
    p.add_argument("--source-calls", help="Pending source calls JSON")
    p.add_argument("--json", action="store_true")
    p.add_argument("--notion-payloads", action="store_true",
                   help="Output only Notion update payloads")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if not (args.outcomes and args.source_calls):
        p.error("--outcomes and --source-calls required (or --self-test)")

    with open(args.outcomes) as f:
        outcomes = json.load(f)
    with open(args.source_calls) as f:
        source_calls = json.load(f)

    # If outcomes file is an OutcomeReport (has full_exits etc), flatten
    if isinstance(outcomes, dict):
        flat = []
        for key in ("full_exits", "partial_exits", "size_increases", "new_positions"):
            flat.extend(outcomes.get(key, []))
        outcomes = flat

    r = link(outcomes, source_calls)

    if args.notion_payloads:
        print(json.dumps(to_notion_payloads(r), indent=2))
    elif args.json:
        print(format_json_report(r))
    else:
        print(format_text_report(r))


if __name__ == "__main__":
    main()
