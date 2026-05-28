#!/usr/bin/env python3
"""
outcome_logger.py — v11.26 rebuild

PURPOSE
    Diff a prior portfolio snapshot against a current snapshot (from broker-PDF
    ingest) and infer FULL_EXIT / PARTIAL_EXIT / SIZE_INCREASE / NEW_POSITION
    events.  Write inferred outcomes to the 📊 Trade Outcomes Notion DB with
    Outcome Tag = "Pending Operator Review".  Fires from P-PORTFOLIO-INGEST
    steps 3–5.

V11.26 ENHANCEMENTS OVER V11.20 ORIGINAL
    1. Macro regime tag on every outcome (consumes macro_pulse arg / v11.25)
    2. Auto-resolution suggestions for 📊 Source Call Log (v11.26):
       when an exit ticker matches a pending Tier-A/B source call with a
       named price target, suggest a Win/Loss/Push classification for that
       call based on exit price vs target
    3. P-DEEPWORK flag: outcomes ≥$25K notional get a `deepwork_threshold`
       flag so the operator can confirm Phase 4 exit triggers fired
    4. Source-cluster-3 flag: when ≥3 outcomes share the same named source
       anchor in the same diff window, surface as coordinated-thesis-event

NOT IN SCOPE
    - Unrealized PnL tracking (already covered by 📊 Latest Portfolio)
    - Tax-lot specific accounting (use broker tools)
    - Cost-basis reconciliation against statements (operator's tax concern)
    - Position-size optimization recommendations (descriptive not prescriptive)

USAGE
    python outcome_logger.py --self-test
    python outcome_logger.py --prior prior.json --current current.json
    python outcome_logger.py --prior P.json --current C.json \\
        --rationales R.json --theses T.json --macro M.json --source-calls S.json
    python outcome_logger.py --prior P.json --current C.json --notion-payloads

SNAPSHOT JSON SCHEMA (input — both --prior and --current)
    {
      "snapshot_date": "2026-05-15",
      "sleeve_value": 1875000.0,
      "positions": [
        {"ticker": "BMNR", "shares": 3262, "market_value": 71500,
         "cost_basis": 71374, "account": "Fidelity_Joint"},
        ...
      ]
    }
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Any


# ============================================================================
# CONSTANTS
# ============================================================================

PARTIAL_EXIT_THRESHOLD = 0.20          # ≥20% share reduction = PARTIAL_EXIT
SIZE_INCREASE_THRESHOLD = 0.20         # ≥20% share increase = SIZE_INCREASE
NOISE_FLOOR_SHARES = 0.001             # below this is rounding noise
NOISE_FLOOR_VALUE = 50.0               # below $50 absolute change = noise
DEEPWORK_NOTIONAL_THRESHOLD = 25000.0  # v11.24 P-DEEPWORK auto-fire threshold
SOURCE_CLUSTER_THRESHOLD = 3           # ≥3 outcomes on same source = cluster
ROUND_TRIP_VALUE_TOLERANCE = 0.05      # 5% value-match → split/merger suspect


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TradeOutcome:
    ticker: str
    change_type: str  # FULL_EXIT / PARTIAL_EXIT / SIZE_INCREASE / NEW_POSITION
    shares_old: float
    shares_new: float
    shares_delta: float
    snapshot_date_old: str
    snapshot_date_new: str

    # Value fields
    market_value_old: float
    market_value_new: float
    cost_basis_old: Optional[float] = None

    # Computed
    estimated_exit_value: Optional[float] = None
    estimated_entry_value: Optional[float] = None
    estimated_realized_pnl: Optional[float] = None
    estimated_realized_pnl_pct: Optional[float] = None

    # Context from related DBs
    tier_at_event: Optional[str] = None
    lane: Optional[str] = None
    source_at_entry: Optional[str] = None
    rationale_ids: List[str] = field(default_factory=list)
    thesis_id: Optional[str] = None

    # v11.25 — macro context
    macro_regime_at_event: Optional[str] = None

    # v11.26 — source call auto-resolution suggestion
    source_call_id_match: Optional[str] = None
    source_call_resolution_suggested: Optional[str] = None  # WIN / LOSS / PUSH

    # Status + integrity
    outcome_tag: str = "Pending Operator Review"
    auto_inferred: bool = True
    flags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class OutcomeReport:
    snapshot_date_old: str
    snapshot_date_new: str
    full_exits: List[TradeOutcome] = field(default_factory=list)
    partial_exits: List[TradeOutcome] = field(default_factory=list)
    size_increases: List[TradeOutcome] = field(default_factory=list)
    new_positions: List[TradeOutcome] = field(default_factory=list)
    flagged_for_review: List[TradeOutcome] = field(default_factory=list)
    source_cluster_events: List[str] = field(default_factory=list)  # source names with ≥3 hits
    total_realized_pnl: float = 0.0
    summary: str = ""


# ============================================================================
# HELPERS
# ============================================================================

def _aggregate_positions(snapshot: Dict) -> Dict[str, Dict]:
    """
    Aggregate positions by ticker across accounts.  Critical: prevents
    false-positive FULL_EXIT detections on internal account-to-account transfers.
    Sums shares, market_value, cost_basis; records account list for traceability.
    """
    agg: Dict[str, Dict] = {}
    for p in snapshot.get("positions", []):
        t = (p.get("ticker") or "").upper().strip()
        if not t:
            continue
        if t not in agg:
            agg[t] = {
                "ticker": t,
                "shares": 0.0,
                "market_value": 0.0,
                "cost_basis": 0.0,
                "cost_basis_complete": True,
                "accounts": [],
            }
        agg[t]["shares"] += float(p.get("shares", 0) or 0)
        agg[t]["market_value"] += float(p.get("market_value", 0) or 0)
        cb = p.get("cost_basis")
        if cb is None or cb == "" or cb == 0:
            agg[t]["cost_basis_complete"] = False
        else:
            agg[t]["cost_basis"] += float(cb)
        acct = p.get("account")
        if acct and acct not in agg[t]["accounts"]:
            agg[t]["accounts"].append(acct)
    return agg


def _est_pnl(market_value_old: float, cost_basis_old: float,
             shares_old: float, shares_exited: float) -> Optional[float]:
    """
    Prorated cost-basis PnL.  Returns realized PnL on exited shares only.
    """
    if shares_old <= 0 or cost_basis_old <= 0:
        return None
    exit_fraction = shares_exited / shares_old
    prorated_cost = cost_basis_old * exit_fraction
    # exit value ≈ market value at prior snapshot * exit fraction (approximation;
    # operator's actual fill may differ — flag if needed)
    exit_value = market_value_old * exit_fraction
    return exit_value - prorated_cost


def _lookup_rationale(ticker: str, rationales: Optional[List[Dict]]) -> List[str]:
    """Find Active Rationale IDs for ticker.  Returns empty list if none."""
    if not rationales:
        return []
    hits = []
    for r in rationales:
        if (r.get("ticker") or "").upper() == ticker.upper():
            rid = r.get("id") or r.get("rationale_id")
            if rid:
                hits.append(rid)
    return hits


def _lookup_thesis(ticker: str, theses: Optional[List[Dict]]) -> Optional[Dict]:
    """Find Live Theses row for ticker.  Returns None if absent."""
    if not theses:
        return None
    for t in theses:
        if (t.get("ticker") or "").upper() == ticker.upper():
            return t
    return None


def _match_source_call(ticker: str, exit_price: Optional[float],
                       source_calls: Optional[List[Dict]]) -> Optional[Dict]:
    """
    v11.26: if exit ticker matches a PENDING Tier-A or Tier-B source call
    that names this ticker with a price target, return that call (so we can
    suggest Win/Loss/Push).
    """
    if not source_calls or not ticker:
        return None
    for sc in source_calls:
        if (sc.get("status") or "").lower() != "pending":
            continue
        if (sc.get("tier") or "").upper() not in ("A", "B"):
            continue
        if (sc.get("named_ticker") or "").upper() != ticker.upper():
            continue
        return sc
    return None


def _suggest_source_call_resolution(call: Dict, exit_price: Optional[float],
                                    change_type: str) -> Optional[str]:
    """
    Suggest WIN / LOSS / PUSH for a pending source call based on the outcome.
    """
    if not call or exit_price is None:
        return None
    target = call.get("target_price")
    direction = (call.get("direction") or "").lower()  # "long" or "short"
    if target is None or not direction:
        return None
    try:
        target = float(target)
    except (TypeError, ValueError):
        return None

    # Long call: WIN if price reached target (>=target); LOSS if didn't
    # Short call: WIN if price fell to target (<=target); LOSS if didn't
    if direction == "long":
        if exit_price >= target * 0.98:  # within 2% counts as PUSH near target
            return "WIN" if exit_price >= target else "PUSH"
        return "LOSS"
    elif direction == "short":
        if exit_price <= target * 1.02:
            return "WIN" if exit_price <= target else "PUSH"
        return "LOSS"
    return None


# ============================================================================
# CORE DIFF ENGINE
# ============================================================================

def diff_snapshots(prior: Dict, current: Dict,
                   rationales: Optional[List[Dict]] = None,
                   theses: Optional[List[Dict]] = None,
                   macro_pulse: Optional[Dict] = None,
                   source_calls: Optional[List[Dict]] = None) -> OutcomeReport:
    """
    Diff two portfolio snapshots and return an OutcomeReport.
    """
    old_agg = _aggregate_positions(prior)
    new_agg = _aggregate_positions(current)

    snapshot_date_old = prior.get("snapshot_date", "unknown")
    snapshot_date_new = current.get("snapshot_date", "unknown")

    macro_regime = None
    if macro_pulse and isinstance(macro_pulse, dict):
        macro_regime = macro_pulse.get("regime_label") or macro_pulse.get("regime")

    report = OutcomeReport(snapshot_date_old, snapshot_date_new)
    source_hit_counter: Dict[str, int] = {}

    all_tickers = set(old_agg.keys()) | set(new_agg.keys())

    for t in sorted(all_tickers):
        old = old_agg.get(t)
        new = new_agg.get(t)

        if old and not new:
            outcome = _build_full_exit(t, old, snapshot_date_old, snapshot_date_new)
        elif new and not old:
            outcome = _build_new_position(t, new, snapshot_date_old, snapshot_date_new)
        elif old and new:
            outcome = _build_change(t, old, new, snapshot_date_old, snapshot_date_new)
            if outcome is None:
                continue
        else:
            continue

        # Enrich with rationale, thesis, macro, source call
        _enrich(outcome, rationales, theses, macro_regime, source_calls)

        # Track source clustering
        if outcome.source_at_entry:
            source_hit_counter[outcome.source_at_entry] = \
                source_hit_counter.get(outcome.source_at_entry, 0) + 1

        # Bucket
        if outcome.change_type == "FULL_EXIT":
            report.full_exits.append(outcome)
        elif outcome.change_type == "PARTIAL_EXIT":
            report.partial_exits.append(outcome)
        elif outcome.change_type == "SIZE_INCREASE":
            report.size_increases.append(outcome)
        elif outcome.change_type == "NEW_POSITION":
            report.new_positions.append(outcome)

        # Flag anything weird for separate review
        if outcome.flags:
            report.flagged_for_review.append(outcome)

        # Total realized PnL
        if outcome.estimated_realized_pnl is not None:
            report.total_realized_pnl += outcome.estimated_realized_pnl

    # v11.24 + v11.26 — source cluster detection
    for source, hits in source_hit_counter.items():
        if hits >= SOURCE_CLUSTER_THRESHOLD:
            report.source_cluster_events.append(f"{source} (n={hits})")

    # Summary line
    report.summary = (
        f"{len(report.full_exits)} full / {len(report.partial_exits)} partial "
        f"exits, {len(report.size_increases)} size increases, "
        f"{len(report.new_positions)} new positions, "
        f"${report.total_realized_pnl:,.0f} realized PnL"
    )
    return report


def _build_full_exit(ticker: str, old: Dict,
                     date_old: str, date_new: str) -> TradeOutcome:
    o = TradeOutcome(
        ticker=ticker,
        change_type="FULL_EXIT",
        shares_old=old["shares"],
        shares_new=0.0,
        shares_delta=-old["shares"],
        snapshot_date_old=date_old,
        snapshot_date_new=date_new,
        market_value_old=old["market_value"],
        market_value_new=0.0,
        estimated_exit_value=old["market_value"],
    )
    if old.get("cost_basis_complete") and old.get("cost_basis", 0) > 0:
        o.cost_basis_old = old["cost_basis"]
        o.estimated_realized_pnl = old["market_value"] - old["cost_basis"]
        if old["cost_basis"] > 0:
            o.estimated_realized_pnl_pct = \
                (o.estimated_realized_pnl / old["cost_basis"]) * 100.0
    else:
        o.flags.append("partial_basis_data")
    if old["market_value"] >= DEEPWORK_NOTIONAL_THRESHOLD:
        o.flags.append("deepwork_threshold")
    return o


def _build_new_position(ticker: str, new: Dict,
                        date_old: str, date_new: str) -> TradeOutcome:
    o = TradeOutcome(
        ticker=ticker,
        change_type="NEW_POSITION",
        shares_old=0.0,
        shares_new=new["shares"],
        shares_delta=new["shares"],
        snapshot_date_old=date_old,
        snapshot_date_new=date_new,
        market_value_old=0.0,
        market_value_new=new["market_value"],
        estimated_entry_value=new["market_value"],
    )
    if new["market_value"] >= DEEPWORK_NOTIONAL_THRESHOLD:
        o.flags.append("deepwork_threshold")
    return o


def _build_change(ticker: str, old: Dict, new: Dict,
                  date_old: str, date_new: str) -> Optional[TradeOutcome]:
    """Return a TradeOutcome or None if change is below noise."""
    share_delta = new["shares"] - old["shares"]
    value_delta = new["market_value"] - old["market_value"]

    # Noise filter
    if (abs(share_delta) < NOISE_FLOOR_SHARES
            and abs(value_delta) < NOISE_FLOOR_VALUE):
        return None
    if old["shares"] <= 0:
        return None  # avoid divide-by-zero on phantom prior positions

    pct_change = share_delta / old["shares"]

    # Round-trip / split/merger detection: huge share change, value preserved
    if (abs(pct_change) >= 0.50 and old["market_value"] > 0
            and abs(value_delta) / old["market_value"] < ROUND_TRIP_VALUE_TOLERANCE):
        o = TradeOutcome(
            ticker=ticker,
            change_type="PARTIAL_EXIT" if share_delta < 0 else "SIZE_INCREASE",
            shares_old=old["shares"],
            shares_new=new["shares"],
            shares_delta=share_delta,
            snapshot_date_old=date_old,
            snapshot_date_new=date_new,
            market_value_old=old["market_value"],
            market_value_new=new["market_value"],
        )
        o.flags.append("round_trip_suspected")
        o.notes.append("Large share change with preserved value — split/merger?")
        return o

    if pct_change <= -PARTIAL_EXIT_THRESHOLD:
        # PARTIAL_EXIT
        shares_exited = abs(share_delta)
        o = TradeOutcome(
            ticker=ticker,
            change_type="PARTIAL_EXIT",
            shares_old=old["shares"],
            shares_new=new["shares"],
            shares_delta=share_delta,
            snapshot_date_old=date_old,
            snapshot_date_new=date_new,
            market_value_old=old["market_value"],
            market_value_new=new["market_value"],
        )
        # Estimate exit value: prorate prior market_value over exited shares
        o.estimated_exit_value = (old["market_value"] * (shares_exited / old["shares"]))
        if old.get("cost_basis_complete") and old.get("cost_basis", 0) > 0:
            o.cost_basis_old = old["cost_basis"]
            pnl = _est_pnl(old["market_value"], old["cost_basis"],
                           old["shares"], shares_exited)
            o.estimated_realized_pnl = pnl
            prorated_cost = old["cost_basis"] * (shares_exited / old["shares"])
            if prorated_cost > 0:
                o.estimated_realized_pnl_pct = (pnl / prorated_cost) * 100.0
        else:
            o.flags.append("partial_basis_data")
        if (o.estimated_exit_value or 0) >= DEEPWORK_NOTIONAL_THRESHOLD:
            o.flags.append("deepwork_threshold")
        return o

    if pct_change >= SIZE_INCREASE_THRESHOLD:
        # SIZE_INCREASE
        o = TradeOutcome(
            ticker=ticker,
            change_type="SIZE_INCREASE",
            shares_old=old["shares"],
            shares_new=new["shares"],
            shares_delta=share_delta,
            snapshot_date_old=date_old,
            snapshot_date_new=date_new,
            market_value_old=old["market_value"],
            market_value_new=new["market_value"],
            estimated_entry_value=value_delta if value_delta > 0 else None,
        )
        if value_delta >= DEEPWORK_NOTIONAL_THRESHOLD:
            o.flags.append("deepwork_threshold")
        return o

    # Below thresholds → no event
    return None


def _enrich(outcome: TradeOutcome,
            rationales: Optional[List[Dict]],
            theses: Optional[List[Dict]],
            macro_regime: Optional[str],
            source_calls: Optional[List[Dict]]) -> None:
    """Mutate outcome to add rationale / thesis / macro / source call links."""
    # Rationales
    rids = _lookup_rationale(outcome.ticker, rationales)
    if rids:
        outcome.rationale_ids = rids
    elif outcome.change_type in ("FULL_EXIT", "PARTIAL_EXIT") and rationales is not None:
        outcome.flags.append("no_active_rationale")

    # Thesis
    thesis = _lookup_thesis(outcome.ticker, theses)
    if thesis:
        outcome.thesis_id = thesis.get("id") or thesis.get("thesis_id")
        outcome.tier_at_event = thesis.get("tier")
        outcome.lane = thesis.get("lane")
        outcome.source_at_entry = thesis.get("source") or thesis.get("source_at_entry")

    # Macro regime
    if macro_regime:
        outcome.macro_regime_at_event = macro_regime

    # v11.26 — source call auto-resolution
    if outcome.change_type in ("FULL_EXIT", "PARTIAL_EXIT"):
        # Estimate exit price per share
        exit_price = None
        if outcome.shares_delta != 0 and outcome.estimated_exit_value is not None:
            try:
                exit_price = outcome.estimated_exit_value / abs(outcome.shares_delta)
            except ZeroDivisionError:
                exit_price = None
        match = _match_source_call(outcome.ticker, exit_price, source_calls)
        if match:
            outcome.source_call_id_match = match.get("id") or match.get("call_id")
            outcome.source_call_resolution_suggested = \
                _suggest_source_call_resolution(match, exit_price, outcome.change_type)


# ============================================================================
# OUTPUT FORMATTERS
# ============================================================================

def format_text_report(r: OutcomeReport) -> str:
    out = []
    out.append("=" * 70)
    out.append(f"OUTCOME REPORT — {r.snapshot_date_old} → {r.snapshot_date_new}")
    out.append("=" * 70)
    out.append(r.summary)
    out.append("")

    def _section(label: str, items: List[TradeOutcome]) -> None:
        if not items:
            return
        out.append(f"-- {label} ({len(items)}) " + "-" * 50)
        for o in items:
            pnl_str = (f"${o.estimated_realized_pnl:,.0f} "
                       f"({o.estimated_realized_pnl_pct:+.1f}%)"
                       if o.estimated_realized_pnl is not None
                       else "PnL n/a (no cost basis)")
            line = (f"  {o.ticker:8} {o.shares_delta:+>10.0f} sh "
                    f"@ ${o.market_value_old:>10,.0f}→${o.market_value_new:<10,.0f} "
                    f"{pnl_str}")
            out.append(line)
            if o.source_at_entry or o.tier_at_event:
                out.append(f"           source: {o.source_at_entry or '?'}  "
                           f"tier: {o.tier_at_event or '?'}  "
                           f"lane: {o.lane or '?'}")
            if o.macro_regime_at_event:
                out.append(f"           macro: {o.macro_regime_at_event}")
            if o.source_call_id_match:
                out.append(f"           📊 source call match: "
                           f"{o.source_call_id_match} → "
                           f"suggest {o.source_call_resolution_suggested}")
            if o.flags:
                out.append(f"           flags: {', '.join(o.flags)}")
        out.append("")

    _section("FULL EXITS", r.full_exits)
    _section("PARTIAL EXITS", r.partial_exits)
    _section("SIZE INCREASES", r.size_increases)
    _section("NEW POSITIONS", r.new_positions)

    if r.source_cluster_events:
        out.append(f"-- SOURCE CLUSTER EVENTS (≥{SOURCE_CLUSTER_THRESHOLD} outcomes "
                   "share source) --")
        for s in r.source_cluster_events:
            out.append(f"  • {s}")
        out.append("")

    return "\n".join(out)


def format_json_report(r: OutcomeReport) -> str:
    def _convert(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return obj
    return json.dumps(asdict(r), indent=2, default=_convert)


def to_notion_payloads(r: OutcomeReport) -> List[Dict[str, Any]]:
    """
    Convert outcomes to Notion DB row payloads for 📊 Trade Outcomes
    (ds 3d8a17df-0ece-474e-88a3-8efd1f3f0865).  Field names align with
    typical Notion property naming; operator should adjust to match
    actual DB schema if it differs.
    """
    payloads = []
    all_outcomes = (r.full_exits + r.partial_exits +
                    r.size_increases + r.new_positions)
    for o in all_outcomes:
        p = {
            "properties": {
                "Ticker": o.ticker,
                "Event Type": o.change_type,
                "date:Event Date:start": o.snapshot_date_new,
                "date:Event Date:is_datetime": 0,
                "Shares Delta": o.shares_delta,
                "Market Value Old": o.market_value_old,
                "Market Value New": o.market_value_new,
                "Estimated Realized PnL": o.estimated_realized_pnl,
                "Realized PnL %": o.estimated_realized_pnl_pct,
                "Source At Entry": o.source_at_entry,
                "Tier At Event": o.tier_at_event,
                "Lane": o.lane,
                "Macro Regime At Event": o.macro_regime_at_event,
                "Source Call Match": o.source_call_id_match,
                "Source Call Resolution Suggested": o.source_call_resolution_suggested,
                "Outcome Tag": o.outcome_tag,
                "Auto Inferred": "Yes" if o.auto_inferred else "No",
                "Flags": ", ".join(o.flags) if o.flags else None,
                "Notes": "; ".join(o.notes) if o.notes else None,
            }
        }
        # Strip None values for cleaner Notion writes
        p["properties"] = {k: v for k, v in p["properties"].items() if v is not None}
        payloads.append(p)
    return payloads


def to_source_call_resolutions(r: OutcomeReport) -> List[Dict[str, Any]]:
    """
    v11.26 — output suggested Win/Loss/Push resolutions for pending source
    calls.  Operator reviews before write-back to 📊 Source Call Log.
    """
    out = []
    all_outcomes = (r.full_exits + r.partial_exits +
                    r.size_increases + r.new_positions)
    for o in all_outcomes:
        if o.source_call_id_match and o.source_call_resolution_suggested:
            out.append({
                "source_call_id": o.source_call_id_match,
                "suggested_outcome": o.source_call_resolution_suggested,
                "triggered_by": {
                    "ticker": o.ticker,
                    "event": o.change_type,
                    "event_date": o.snapshot_date_new,
                    "exit_value": o.estimated_exit_value,
                }
            })
    return out


# ============================================================================
# SELF-TEST
# ============================================================================

def _self_test() -> bool:
    """30 assertions covering core behaviors."""
    passed = 0
    failed = 0

    def assert_eq(actual, expected, label):
        nonlocal passed, failed
        if actual == expected:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}: expected {expected!r}, got {actual!r}")

    def assert_close(actual, expected, label, tol=1.0):
        nonlocal passed, failed
        if actual is None:
            failed += 1
            print(f"  FAIL: {label}: actual is None")
            return
        if abs(actual - expected) <= tol:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}: expected ~{expected}, got {actual}")

    def assert_true(condition, label):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    # ----- Test 1: FULL_EXIT detection
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "AAA", "shares": 100, "market_value": 10000,
             "cost_basis": 8000, "account": "Fid"}
        ]
    }
    current = {"snapshot_date": "2026-05-15", "positions": []}
    r = diff_snapshots(prior, current)
    assert_eq(len(r.full_exits), 1, "full_exit count")
    assert_eq(r.full_exits[0].ticker, "AAA", "full_exit ticker")
    assert_eq(r.full_exits[0].change_type, "FULL_EXIT", "full_exit type")
    assert_close(r.full_exits[0].estimated_realized_pnl, 2000, "full_exit pnl")
    assert_close(r.full_exits[0].estimated_realized_pnl_pct, 25.0, "full_exit pnl %", 0.5)

    # ----- Test 2: PARTIAL_EXIT detection
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "BBB", "shares": 100, "market_value": 10000,
             "cost_basis": 8000, "account": "Fid"}
        ]
    }
    current = {
        "snapshot_date": "2026-05-15",
        "positions": [
            {"ticker": "BBB", "shares": 50, "market_value": 5000,
             "cost_basis": 4000, "account": "Fid"}
        ]
    }
    r = diff_snapshots(prior, current)
    assert_eq(len(r.partial_exits), 1, "partial_exit count")
    assert_eq(r.partial_exits[0].change_type, "PARTIAL_EXIT", "partial_exit type")
    assert_close(r.partial_exits[0].shares_delta, -50, "partial_exit shares_delta")

    # ----- Test 3: SIZE_INCREASE detection
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "CCC", "shares": 100, "market_value": 10000,
             "cost_basis": 10000, "account": "Fid"}
        ]
    }
    current = {
        "snapshot_date": "2026-05-15",
        "positions": [
            {"ticker": "CCC", "shares": 150, "market_value": 15000,
             "cost_basis": 14000, "account": "Fid"}
        ]
    }
    r = diff_snapshots(prior, current)
    assert_eq(len(r.size_increases), 1, "size_increase count")
    assert_eq(r.size_increases[0].change_type, "SIZE_INCREASE", "size_increase type")

    # ----- Test 4: NEW_POSITION detection
    prior = {"snapshot_date": "2026-05-01", "positions": []}
    current = {
        "snapshot_date": "2026-05-15",
        "positions": [
            {"ticker": "DDD", "shares": 100, "market_value": 30000,
             "cost_basis": 30000, "account": "Fid"}
        ]
    }
    r = diff_snapshots(prior, current)
    assert_eq(len(r.new_positions), 1, "new_position count")
    assert_true("deepwork_threshold" in r.new_positions[0].flags,
                "new_position fires deepwork_threshold at $30K")

    # ----- Test 5: cross-account aggregation (no false-positive exit on transfer)
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "EEE", "shares": 100, "market_value": 10000,
             "cost_basis": 8000, "account": "Fid_A"},
        ]
    }
    current = {
        "snapshot_date": "2026-05-15",
        "positions": [
            {"ticker": "EEE", "shares": 100, "market_value": 10500,
             "cost_basis": 8000, "account": "Fid_B"},  # transferred account
        ]
    }
    r = diff_snapshots(prior, current)
    assert_eq(len(r.full_exits), 0, "no false full_exit on transfer")
    assert_eq(len(r.partial_exits), 0, "no false partial_exit on transfer")
    assert_eq(len(r.size_increases), 0, "no false size_increase on transfer")

    # ----- Test 6: missing cost basis → partial_basis_data flag
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "FFF", "shares": 100, "market_value": 10000,
             "cost_basis": None, "account": "Fid"}
        ]
    }
    current = {"snapshot_date": "2026-05-15", "positions": []}
    r = diff_snapshots(prior, current)
    assert_eq(len(r.full_exits), 1, "full_exit with missing basis")
    assert_true("partial_basis_data" in r.full_exits[0].flags,
                "partial_basis_data flag fires")
    assert_eq(r.full_exits[0].estimated_realized_pnl, None, "PnL is None when basis missing")

    # ----- Test 7: noise filter — tiny change ignored
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "GGG", "shares": 100, "market_value": 10000,
             "cost_basis": 10000, "account": "Fid"}
        ]
    }
    current = {
        "snapshot_date": "2026-05-15",
        "positions": [
            {"ticker": "GGG", "shares": 100.0001, "market_value": 10000.05,
             "cost_basis": 10000, "account": "Fid"}
        ]
    }
    r = diff_snapshots(prior, current)
    assert_eq(len(r.full_exits), 0, "noise: no full_exit")
    assert_eq(len(r.partial_exits), 0, "noise: no partial_exit")
    assert_eq(len(r.size_increases), 0, "noise: no size_increase")

    # ----- Test 8: round_trip_suspected (suggests split/merger)
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "HHH", "shares": 100, "market_value": 10000,
             "cost_basis": 8000, "account": "Fid"}
        ]
    }
    current = {
        "snapshot_date": "2026-05-15",
        "positions": [
            {"ticker": "HHH", "shares": 25, "market_value": 10000,
             "cost_basis": 8000, "account": "Fid"}  # 4-for-1 reverse split
        ]
    }
    r = diff_snapshots(prior, current)
    found_round_trip = False
    for o in r.partial_exits + r.size_increases:
        if "round_trip_suspected" in o.flags:
            found_round_trip = True
            break
    assert_true(found_round_trip, "round_trip_suspected flag fires on split")

    # ----- Test 9: macro_regime tag propagates
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "III", "shares": 100, "market_value": 10000,
             "cost_basis": 8000, "account": "Fid"}
        ]
    }
    current = {"snapshot_date": "2026-05-15", "positions": []}
    macro = {"regime_label": "duration_WEAK · credit_COMPLACENT · vol_COMPLACENT"}
    r = diff_snapshots(prior, current, macro_pulse=macro)
    assert_eq(r.full_exits[0].macro_regime_at_event,
              "duration_WEAK · credit_COMPLACENT · vol_COMPLACENT",
              "macro regime tagged on outcome")

    # ----- Test 10: source call auto-resolution (LONG, WIN)
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "LEU", "shares": 100, "market_value": 19000,
             "cost_basis": 15000, "account": "Fid"}
        ]
    }
    current = {"snapshot_date": "2026-05-15", "positions": []}
    source_calls = [{
        "id": "call_abc123",
        "status": "pending",
        "tier": "A",
        "named_ticker": "LEU",
        "direction": "long",
        "target_price": 180.0,
    }]
    r = diff_snapshots(prior, current, source_calls=source_calls)
    # exit price = $19000 / 100 = $190 → above $180 target = WIN
    assert_eq(r.full_exits[0].source_call_id_match, "call_abc123",
              "source call matched")
    assert_eq(r.full_exits[0].source_call_resolution_suggested, "WIN",
              "source call WIN suggested")

    # ----- Test 11: source call auto-resolution (LONG, LOSS — exit below target)
    source_calls = [{
        "id": "call_xyz",
        "status": "pending",
        "tier": "A",
        "named_ticker": "LEU",
        "direction": "long",
        "target_price": 250.0,  # target $250, but exit @ $190
    }]
    r = diff_snapshots(prior, current, source_calls=source_calls)
    assert_eq(r.full_exits[0].source_call_resolution_suggested, "LOSS",
              "source call LOSS when exit far below target")

    # ----- Test 12: source cluster detection (≥3 outcomes share source)
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "X1", "shares": 100, "market_value": 5000, "cost_basis": 5000},
            {"ticker": "X2", "shares": 100, "market_value": 5000, "cost_basis": 5000},
            {"ticker": "X3", "shares": 100, "market_value": 5000, "cost_basis": 5000},
        ]
    }
    current = {"snapshot_date": "2026-05-15", "positions": []}
    theses = [
        {"ticker": "X1", "source": "Newton", "tier": "B"},
        {"ticker": "X2", "source": "Newton", "tier": "B"},
        {"ticker": "X3", "source": "Newton", "tier": "B"},
    ]
    r = diff_snapshots(prior, current, theses=theses)
    assert_true(any("Newton" in s for s in r.source_cluster_events),
                "source cluster detected when ≥3 outcomes share source")

    # ----- Test 13: deepwork_threshold flag fires at ≥$25K
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "BIG", "shares": 100, "market_value": 30000,
             "cost_basis": 25000, "account": "Fid"}
        ]
    }
    current = {"snapshot_date": "2026-05-15", "positions": []}
    r = diff_snapshots(prior, current)
    assert_true("deepwork_threshold" in r.full_exits[0].flags,
                "deepwork_threshold fires on $30K exit")

    # ----- Test 14: deepwork_threshold does NOT fire below $25K
    prior = {
        "snapshot_date": "2026-05-01",
        "positions": [
            {"ticker": "SML", "shares": 100, "market_value": 10000,
             "cost_basis": 8000, "account": "Fid"}
        ]
    }
    current = {"snapshot_date": "2026-05-15", "positions": []}
    r = diff_snapshots(prior, current)
    assert_true("deepwork_threshold" not in r.full_exits[0].flags,
                "deepwork_threshold does not fire on $10K exit")

    # ----- Test 15: Notion payload formatter
    payloads = to_notion_payloads(r)
    assert_eq(len(payloads), 1, "one payload for one outcome")
    assert_eq(payloads[0]["properties"]["Ticker"], "SML", "payload ticker")
    assert_eq(payloads[0]["properties"]["Event Type"], "FULL_EXIT", "payload event type")
    assert_eq(payloads[0]["properties"]["Outcome Tag"], "Pending Operator Review",
              "default outcome tag")

    # ----- Test 16: source call resolutions output empty when no matches
    resolutions = to_source_call_resolutions(r)
    assert_eq(len(resolutions), 0, "no resolutions when no source call match")

    # ----- Test 17: realistic operator-portfolio simulation
    prior = {
        "snapshot_date": "2026-05-15",
        "sleeve_value": 1875000,
        "positions": [
            {"ticker": "BMNR", "shares": 3262, "market_value": 71500,
             "cost_basis": 71374, "account": "Fid_Joint"},
            {"ticker": "LEU", "shares": 511, "market_value": 96000,
             "cost_basis": 75000, "account": "Fid_Joint"},
            {"ticker": "NVDA", "shares": 596, "market_value": 139000,
             "cost_basis": 90000, "account": "Sch_PCRA"},
            {"ticker": "MP", "shares": 660, "market_value": 39680,
             "cost_basis": 36000, "account": "Fid_Joint"},
        ]
    }
    current = {
        "snapshot_date": "2026-05-20",
        "sleeve_value": 1850000,
        "positions": [
            {"ticker": "BMNR", "shares": 3262, "market_value": 73000,
             "cost_basis": 71374, "account": "Fid_Joint"},
            {"ticker": "LEU", "shares": 511, "market_value": 95000,
             "cost_basis": 75000, "account": "Fid_Joint"},
            {"ticker": "NVDA", "shares": 596, "market_value": 142000,
             "cost_basis": 90000, "account": "Sch_PCRA"},
            # MP fully exited
        ]
    }
    r = diff_snapshots(prior, current)
    assert_eq(len(r.full_exits), 1, "realistic sim: 1 full exit (MP)")
    assert_eq(r.full_exits[0].ticker, "MP", "realistic sim: MP exited")
    assert_close(r.full_exits[0].estimated_realized_pnl, 3680, "MP realized PnL", 100)

    # ----- Test 18: full output formatter runs without crashing
    text = format_text_report(r)
    assert_true("OUTCOME REPORT" in text, "text report renders")
    assert_true("MP" in text, "text report contains exit ticker")

    # ----- Test 19: JSON output formatter
    js = format_json_report(r)
    parsed = json.loads(js)
    assert_eq(parsed["full_exits"][0]["ticker"], "MP", "JSON output ticker")

    # ----- Test 20: empty diff
    r_empty = diff_snapshots(
        {"snapshot_date": "2026-05-01", "positions": []},
        {"snapshot_date": "2026-05-15", "positions": []},
    )
    assert_eq(len(r_empty.full_exits), 0, "empty diff full")
    assert_eq(len(r_empty.partial_exits), 0, "empty diff partial")
    assert_eq(r_empty.total_realized_pnl, 0.0, "empty diff PnL = 0")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return failed == 0


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="Outcome Logger v11.26")
    p.add_argument("--prior", help="Path to prior portfolio snapshot JSON")
    p.add_argument("--current", help="Path to current portfolio snapshot JSON")
    p.add_argument("--rationales", help="Active Trade Rationales JSON (optional)")
    p.add_argument("--theses", help="Live Theses JSON (optional)")
    p.add_argument("--macro", help="Macro pulse JSON (optional, v11.25)")
    p.add_argument("--source-calls", help="Pending Source Call Log rows JSON (optional, v11.26)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--notion-payloads", action="store_true",
                   help="Output Notion DB row payloads (JSON)")
    p.add_argument("--source-call-resolutions", action="store_true",
                   help="Output suggested Win/Loss/Push for matched source calls")
    p.add_argument("--self-test", action="store_true", help="Run self-test and exit")
    args = p.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if not args.prior or not args.current:
        p.error("--prior and --current required (or --self-test)")

    with open(args.prior) as f:
        prior = json.load(f)
    with open(args.current) as f:
        current = json.load(f)

    rationales = None
    if args.rationales:
        with open(args.rationales) as f:
            rationales = json.load(f)
    theses = None
    if args.theses:
        with open(args.theses) as f:
            theses = json.load(f)
    macro = None
    if args.macro:
        with open(args.macro) as f:
            macro = json.load(f)
    source_calls = None
    if args.source_calls:
        with open(args.source_calls) as f:
            source_calls = json.load(f)

    report = diff_snapshots(prior, current, rationales, theses, macro, source_calls)

    if args.notion_payloads:
        print(json.dumps(to_notion_payloads(report), indent=2))
    elif args.source_call_resolutions:
        print(json.dumps(to_source_call_resolutions(report), indent=2))
    elif args.json:
        print(format_json_report(report))
    else:
        print(format_text_report(report))


if __name__ == "__main__":
    main()
