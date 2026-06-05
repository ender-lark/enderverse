#!/usr/bin/env python3
"""
session_orchestrator.py — v11.26 NEW ARCHITECTURE

PURPOSE
    Single entry point that runs the entire v11.26 pre-flight stack and
    produces one unified surface block.  Replaces ad-hoc invocation of
    individual scripts.

    Wires together (in order):
      1. Macro pulse        — reads cached macro_state.json
      2. Source calibration — reads cached source_rates.json
      3. Outcome diff       — runs outcome_logger if prior+current available
      4. Conviction sizing  — runs conviction_sizing_calibrator
      5. Factor exposure    — runs portfolio_factor_exposure
      6. Insider activity   — runs insider_activity_scan if data available
      7. Aggregates surface lines

OUTPUT FORMAT
    For consumption at session-open (Patch N step 1.5).  Produces:
      • One surface block (text or JSON)
      • A "look-at-first" priority list (which subsystems have actionable
        items)
      • Optional unified JSON for downstream pretrade_gate evaluation

USAGE
    python session_orchestrator.py --self-test
    python session_orchestrator.py \\
        --positions current.json --theses theses.json \\
        --sleeve-total 1875000 \\
        [--prior prior.json] \\
        [--macro macro_state.json] \\
        [--source-rates source_rates.json] \\
        [--insider-data insider_data.json] \\
        [--catalysts catalysts.json] \\
        [--source-calls pending_source_calls.json]
"""

import argparse
import datetime
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Any

sys.path.insert(0, "/home/claude/build")
sys.path.insert(0, "/mnt/project")
# v12.0 ISSUE-10 fix: prefer this module's own directory over /mnt/project so
# local/staged copies are importable (the hardcoded inserts above shadowed them).
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
try:
    import outcome_logger as ol
    import conviction_sizing_calibrator as csc
    import portfolio_factor_exposure as pfe
    import insider_activity_scan as ias
    import source_call_tracker as sct
    import position_drift_check as pdc
except ImportError as e:
    print(f"WARNING: import failure — {e}")
    ol = csc = pfe = ias = None
    sct = None
    pdc = None

try:
    from runtime_adapters import catalysts_from_calendar_rows
except ImportError:
    catalysts_from_calendar_rows = None


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class SubsystemResult:
    name: str
    available: bool
    surface_line: str
    priority: str = "INFO"          # CRIT / HIGH / MED / INFO / NONE
    actionable_count: int = 0
    payload: Optional[Dict] = None  # for JSON output


@dataclass
class SessionDashboard:
    macro_regime: Optional[str] = None
    sleeve_total: float = 0
    subsystems: List[SubsystemResult] = field(default_factory=list)
    priority_order: List[str] = field(default_factory=list)  # subsystem names by priority
    summary_block: str = ""


# ============================================================================
# SUBSYSTEM RUNNERS
# ============================================================================

def _parse_date(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s).strip())
    except (ValueError, AttributeError):
        return None


def macro_freshness(snapshot_date: Optional[str],
                    today: Optional[str] = None) -> Dict:
    """Is macro_state.json current? (v12.0 staleness guard.)

    Strict per the operator's call: macro moves daily, so 'fresh' means the
    snapshot is the current trading day. Weekends accept the most recent Friday;
    market holidays are not special-cased (the guard errs toward flagging, which
    is the safe direction). Returns {fresh, age_days, snapshot_date, label}.
    """
    today_d = _parse_date(today) or datetime.date.today()
    snap_d = _parse_date(snapshot_date)
    if snap_d is None:
        return {"fresh": False, "age_days": None,
                "snapshot_date": snapshot_date, "label": "STALE (no snapshot_date)"}
    ref = today_d                       # most recent trading day on/before today
    if ref.weekday() == 5:              # Saturday -> Friday
        ref -= datetime.timedelta(days=1)
    elif ref.weekday() == 6:            # Sunday -> Friday
        ref -= datetime.timedelta(days=2)
    age = (today_d - snap_d).days
    if snap_d >= ref:
        return {"fresh": True, "age_days": age,
                "snapshot_date": snapshot_date, "label": f"fresh ({snapshot_date})"}
    return {"fresh": False, "age_days": age,
            "snapshot_date": snapshot_date,
            "label": f"STALE {age}d (snapshot {snapshot_date})"}


def _run_macro(macro_pulse: Optional[Dict],
               today: Optional[str] = None) -> SubsystemResult:
    if not macro_pulse:
        return SubsystemResult(
            name="MACRO PULSE",
            available=False,
            surface_line="MACRO: (no macro_state.json supplied)",
            priority="INFO",
        )
    regime = (macro_pulse.get("regime_label") or macro_pulse.get("regime")
              or "unknown")
    alerts = macro_pulse.get("alerts", []) or []
    n_alerts = len(alerts)

    # v12.0 freshness guard — stale macro feeds 4 consumers + the macro-headwind
    # gate, so a stale/undated cache is surfaced loudly and never read as current.
    fresh = macro_freshness(macro_pulse.get("snapshot_date"), today=today)
    stale = not fresh["fresh"]

    priority = "HIGH" if (n_alerts >= 1 or stale) else "INFO"
    surface = f"MACRO: {regime}"
    if n_alerts:
        surface += f"  [{n_alerts} alert(s)]"
    if stale:
        surface += (f"  \u26a0\ufe0f {fresh['label']} \u2014 refresh before any Tier A/B "
                    f"(macro confidence downgraded)")

    return SubsystemResult(
        name="MACRO PULSE",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=(max(n_alerts, 1) if stale else n_alerts),
        payload={"regime": regime, "alerts": alerts,
                 "snapshot_date": macro_pulse.get("snapshot_date"),
                 "freshness": fresh},
    )


def _run_source_calibration(source_rates: Optional[Dict]) -> SubsystemResult:
    if not source_rates:
        return SubsystemResult(
            name="SOURCE CALIBRATION",
            available=False,
            surface_line="SOURCE CALIBRATION: (no source_rates.json supplied)",
            priority="INFO",
        )

    miss_count = 0
    below_count = 0
    high_count = 0
    bands_summary = []
    for source, by_tier in source_rates.items():
        if not isinstance(by_tier, dict):
            continue  # skip metadata fields like snapshot_date
        for tier, info in by_tier.items():
            if not isinstance(info, dict):
                continue
            n = info.get("n", 0)
            band = info.get("band", "INSUFFICIENT_DATA")
            if n >= 15:
                if band == "CONSISTENT_MISS":
                    miss_count += 1
                    bands_summary.append(f"{source}×{tier}: MISS (n={n})")
                elif band == "BELOW_BREAKEVEN":
                    below_count += 1
                    bands_summary.append(f"{source}×{tier}: BELOW (n={n})")
                elif band == "HIGH_CONVICTION":
                    high_count += 1
                    bands_summary.append(f"{source}×{tier}: HIGH (n={n})")

    actionable = miss_count + below_count
    if miss_count:
        priority = "CRIT"
    elif below_count:
        priority = "HIGH"
    elif high_count:
        priority = "INFO"
    else:
        priority = "INFO"

    if bands_summary:
        surface = f"SOURCE CALIBRATION: " + "; ".join(bands_summary[:4])
        if len(bands_summary) > 4:
            surface += f" (+{len(bands_summary)-4} more)"
    else:
        surface = "SOURCE CALIBRATION: all sources INSUFFICIENT_DATA (n<15)"

    return SubsystemResult(
        name="SOURCE CALIBRATION",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=actionable,
        payload={"miss": miss_count, "below": below_count, "high": high_count,
                 "bands": bands_summary},
    )


def _run_outcomes(prior: Optional[Dict], current: Dict,
                  rationales: Optional[List[Dict]],
                  theses: Optional[List[Dict]],
                  macro_pulse: Optional[Dict],
                  source_calls: Optional[List[Dict]]) -> SubsystemResult:
    if ol is None or not prior:
        return SubsystemResult(
            name="OUTCOMES",
            available=False,
            surface_line="OUTCOMES: (no prior snapshot to diff)",
            priority="INFO",
        )
    report = ol.diff_snapshots(prior, current, rationales, theses,
                               macro_pulse, source_calls)
    n_changes = (len(report.full_exits) + len(report.partial_exits)
                 + len(report.size_increases) + len(report.new_positions))
    actionable = n_changes
    if n_changes >= 5:
        priority = "HIGH"
    elif n_changes >= 1:
        priority = "MED"
    else:
        priority = "INFO"
    surface = f"OUTCOMES: {report.summary}"
    return SubsystemResult(
        name="OUTCOMES",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=actionable,
        payload={"summary": report.summary,
                 "n_changes": n_changes,
                 "realized_pnl": report.total_realized_pnl,
                 "source_cluster_events": report.source_cluster_events},
    )


def _run_conviction(positions: List[Dict], theses: List[Dict],
                    sleeve_total: float,
                    macro_pulse: Optional[Dict],
                    source_rates: Optional[Dict]) -> SubsystemResult:
    if csc is None:
        return SubsystemResult(
            name="CONVICTION SIZING",
            available=False,
            surface_line="CONVICTION SIZING: (script not loaded)",
            priority="INFO",
        )
    report = csc.calibrate(positions, theses, sleeve_total,
                           macro_pulse, source_rates)
    critical = len(report.critically_below)
    below = len(report.below_floor)
    actionable = critical + below
    if critical > 0:
        priority = "CRIT"
    elif below > 0:
        priority = "HIGH"
    else:
        priority = "INFO"
    surface = csc.surface_line(report)
    return SubsystemResult(
        name="CONVICTION SIZING",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=actionable,
        payload={"critical_count": critical, "below_count": below,
                 "gap_total": report.gap_to_close_total,
                 "gap_discounted": report.gap_to_close_discounted,
                 "deepwork_count": report.deepwork_required_count},
    )


def _run_factor(positions: List[Dict], theses: List[Dict],
                sleeve_total: float,
                macro_pulse: Optional[Dict]) -> SubsystemResult:
    if pfe is None:
        return SubsystemResult(
            name="FACTOR EXPOSURE",
            available=False,
            surface_line="FACTOR EXPOSURE: (script not loaded)",
            priority="INFO",
        )
    report = pfe.analyze(positions, theses, sleeve_total, macro_pulse)
    warn = len(report.concentration_warnings)
    src_stacks = len(report.source_factor_stacks)
    macro_stacks = len(report.macro_regime_stacks)
    st_conc = len(report.source_tier_concentrations)
    actionable = warn + src_stacks + macro_stacks + st_conc
    if any(s.direction == "headwind" and s.pct_of_sleeve > 0.30
           for s in report.macro_regime_stacks):
        priority = "HIGH"   # 30%+ in macro headwind
    elif warn > 0 or src_stacks > 0:
        priority = "MED"
    else:
        priority = "INFO"
    surface = pfe.surface_line(report)
    return SubsystemResult(
        name="FACTOR EXPOSURE",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=actionable,
        payload={
            "n_warnings": warn,
            "n_source_stacks": src_stacks,
            "n_macro_stacks": macro_stacks,
            "n_source_tier_concs": st_conc,
            "effective_n": report.effective_n_factors,
        },
    )


def _run_insider(positions: List[Dict],
                 insider_data: Optional[Dict],
                 catalysts: Optional[List[Dict]],
                 theses: Optional[List[Dict]],
                 macro_pulse: Optional[Dict]) -> SubsystemResult:
    if ias is None or insider_data is None:
        return SubsystemResult(
            name="INSIDER ACTIVITY",
            available=False,
            surface_line="INSIDER ACTIVITY: (no insider data supplied)",
            priority="INFO",
        )
    # v12.0 honesty guard — a present-but-empty cache (the stub) must not read as
    # "evaluated, nothing found." Surface the empty state explicitly so the insider
    # line can never be a silent false all-clear (Cat-5 stays honestly dark).
    n_txns = sum(len(v) for v in insider_data.values() if isinstance(v, list))
    if n_txns == 0:
        return SubsystemResult(
            name="INSIDER ACTIVITY",
            available=False,
            surface_line=("INSIDER ACTIVITY: \u26a0\ufe0f cache empty (stub) \u2014 not "
                          "evaluated; populate via the insider refresh routine"),
            priority="INFO",
        )
    report = ias.scan(positions, insider_data,
                      _normalize_catalysts_for_routine(catalysts),
                      theses, macro_pulse)
    actionable = (len(report.bullish) + len(report.bearish)
                  + len(report.cluster) + len(report.flagged))
    if len(report.flagged):
        priority = "HIGH"
    elif len(report.bearish) or len(report.cluster):
        priority = "MED"
    elif len(report.bullish):
        priority = "MED"
    else:
        priority = "INFO"
    surface = ias.surface_line(report)
    return SubsystemResult(
        name="INSIDER ACTIVITY",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=actionable,
        payload={"bullish": len(report.bullish),
                 "bearish": len(report.bearish),
                 "cluster": len(report.cluster),
                 "flagged": len(report.flagged)},
    )


# ============================================================================
# CORE ORCHESTRATOR
# ============================================================================

def _run_parabolic(parabolic_data: Optional[Dict]) -> SubsystemResult:
    if parabolic_data is None:
        return SubsystemResult(
            name="PARABOLIC SETUPS",
            available=False,
            surface_line="PARABOLIC SETUPS: (no parabolic data supplied)",
            priority="INFO",
        )
    results = parabolic_data.get("results")
    # v12.0 honesty guard — a present-but-empty cache (no results at all) must
    # not read as "evaluated, nothing setup." Only a non-empty results list is
    # "evaluated"; an all-SKIP results list IS evaluated (nothing firing today).
    if not results:
        return SubsystemResult(
            name="PARABOLIC SETUPS",
            available=False,
            surface_line=("PARABOLIC SETUPS: \u26a0\ufe0f cache empty (stub) \u2014 not "
                          "evaluated; populate via the parabolic screener routine"),
            priority="INFO",
        )
    autofire = [r.get("ticker") or "?" for r in results
                if r.get("surface_tier") == "AUTOFIRE"]
    watchlist = [r.get("ticker") or "?" for r in results
                 if r.get("surface_tier") == "WATCHLIST"]
    n_screened = len(results)
    if autofire:
        priority = "HIGH"
    elif watchlist:
        priority = "MED"
    else:
        priority = "INFO"
    actionable = len(autofire) + len(watchlist)
    if autofire or watchlist:
        parts = []
        if autofire:
            parts.append(f"{len(autofire)} AUTOFIRE ({', '.join(autofire)})")
        if watchlist:
            parts.append(f"{len(watchlist)} WATCHLIST ({', '.join(watchlist)})")
        surface = "PARABOLIC SETUPS: " + "; ".join(parts)
    else:
        surface = f"PARABOLIC SETUPS: none firing ({n_screened} screened, all SKIP)"
    return SubsystemResult(
        name="PARABOLIC SETUPS",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=actionable,
        payload={"autofire": len(autofire), "watchlist": len(watchlist),
                 "screened": n_screened},
    )


def _run_persistence(source_calls, theses, calibration_fresh,
                     core_tickers=None, now=None) -> SubsystemResult:
    """SOURCE PERSISTENCE — single-source soloist detector (v11.29), wired as the
    8th subsystem (v12.5). STALENESS GUARD: when the source-calibration chain is
    NOT confirmed fresh, LOUD clusters are downgraded to PROVISIONAL — still
    surfaced (never silently dropped), but not firing P-WAKE-UP on their own,
    because the underlying calls may be stale / un-ingested (Issue #10). Core
    (non-MONITOR T1/T2) names are the quiet set; MONITOR names stay loud-eligible
    so re-entry persistence still surfaces (AI-Momentum / Monitor-Stance)."""
    if sct is None:
        return SubsystemResult(name="SOURCE PERSISTENCE", available=False,
            surface_line="SOURCE PERSISTENCE: (source_call_tracker unavailable)",
            priority="INFO")
    if not source_calls:
        return SubsystemResult(name="SOURCE PERSISTENCE", available=False,
            surface_line="SOURCE PERSISTENCE: (no source calls supplied)",
            priority="INFO")
    if core_tickers is None:
        core_tickers = {(t.get("ticker") or "").upper() for t in (theses or [])
                        if (t.get("stance") or "").upper() != "MONITOR"
                        and (t.get("tier") or "").upper() in ("T1", "T2")}
    clusters = sct.persistence_scan(source_calls, core_tickers=core_tickers, now=now)

    guarded = False
    if not calibration_fresh:
        for c in clusters:
            if c.get("loud"):
                c["loud"] = False
                c["quiet_reason"] = "calib_provisional"
                c["provisional"] = True
                guarded = True

    if not clusters:
        return SubsystemResult(name="SOURCE PERSISTENCE", available=True,
            surface_line="SOURCE PERSISTENCE: none firing", priority="INFO")

    loud_n = sum(1 for c in clusters if c.get("loud"))
    prov_n = sum(1 for c in clusters if c.get("provisional"))
    surface = sct.persistence_surface_line(clusters)
    if guarded:
        surface += ("  \u26a0\ufe0f PROVISIONAL — calibration chain not confirmed "
                    "fresh; LOUD held until calibration refreshes (Issue #10 guard)")
    priority = "HIGH" if loud_n else ("MED" if prov_n else "INFO")
    return SubsystemResult(name="SOURCE PERSISTENCE", available=True,
        surface_line=surface, priority=priority,
        actionable_count=loud_n + prov_n,
        payload={"clusters": len(clusters), "loud": loud_n,
                 "provisional": prov_n, "guarded": guarded})


def _run_target_drift(positions: List[Dict], sleeve_total: float) -> SubsystemResult:
    """TARGET DRIFT - current book vs explicit reallocation target model.

    This is separate from conviction sizing. Conviction says how large a name can
    reasonably be; target drift says whether the current book is actually lined
    up with the operator's working model.
    """
    if pdc is None:
        return SubsystemResult(
            name="TARGET DRIFT",
            available=False,
            surface_line="TARGET DRIFT: (position_drift_check unavailable)",
            priority="INFO",
        )
    if not positions or not sleeve_total:
        return SubsystemResult(
            name="TARGET DRIFT",
            available=False,
            surface_line="TARGET DRIFT: (no positions supplied)",
            priority="INFO",
        )

    wrapper = {"positions": positions, "sleeve_value": sleeve_total}
    drift, unmatched, _untracked = pdc.target_weight_drift(wrapper, sleeve_total)
    flagged = [d for d in drift if d.is_flagged]
    alarm = [d for d in flagged if "ALARM_DRIFT" in d.flags]
    undersized = [d for d in flagged if d.direction == "UNDERSIZED"]
    oversized = [d for d in flagged if d.direction == "OVERSIZED"]
    missing = list(unmatched)
    actionable = len(flagged) + len(missing)

    if actionable == 0:
        return SubsystemResult(
            name="TARGET DRIFT",
            available=True,
            surface_line="TARGET DRIFT: book is within target-weight bands",
            priority="INFO",
            actionable_count=0,
            payload={"flagged": 0, "missing_targets": 0},
        )

    priority = "HIGH" if (alarm or missing) else "MED"
    top_bits = []
    for d in sorted(flagged, key=lambda x: -abs(x.drift_relative))[:4]:
        top_bits.append(
            f"{d.ticker} {d.direction.lower()} "
            f"{d.actual_pct*100:.1f}% vs {d.memory_baseline_pct*100:.1f}%"
        )
    remaining_slots = max(0, 4 - len(top_bits))
    for b in missing[:remaining_slots]:
        top_bits.append(f"{b.ticker} missing vs {b.baseline_pct*100:.1f}% target")
    more = actionable - len(top_bits)
    suffix = ("; " + "; ".join(top_bits)) if top_bits else ""
    if more > 0:
        suffix += f"; +{more} more"
    surface = (
        "TARGET DRIFT: "
        f"{actionable} sizing gap(s) vs AI working model "
        f"({len(undersized)} under, {len(oversized)} over, {len(missing)} missing)"
        f"{suffix}"
    )
    return SubsystemResult(
        name="TARGET DRIFT",
        available=True,
        surface_line=surface,
        priority=priority,
        actionable_count=actionable,
        payload={
            "flagged": len(flagged),
            "alarm": len(alarm),
            "undersized": len(undersized),
            "oversized": len(oversized),
            "missing_targets": len(missing),
            "top": top_bits,
        },
    )


def _run_position_diff(position_reconciliation: Optional[Dict]) -> SubsystemResult:
    """POSITION DIFF - recent account-level changes from broker PDF ingest."""
    if not position_reconciliation:
        return SubsystemResult(
            name="POSITION DIFF",
            available=False,
            surface_line="POSITION DIFF: (no position_reconciliation.json supplied)",
            priority="INFO",
        )
    if position_reconciliation.get("status") == "not_checked":
        reason = position_reconciliation.get("reason") or "not checked"
        return SubsystemResult(
            name="POSITION DIFF",
            available=False,
            surface_line=f"POSITION DIFF: ({reason})",
            priority="INFO",
            payload={"status": "not_checked", "reason": reason},
        )
    changes = position_reconciliation.get("changes") or []
    if not isinstance(changes, list):
        return SubsystemResult(
            name="POSITION DIFF",
            available=False,
            surface_line="POSITION DIFF: malformed reconciliation file",
            priority="MED",
            actionable_count=1,
            payload={"error": "changes must be a list"},
        )
    counts = position_reconciliation.get("counts") or {}
    trade_actions = ["NEW", "EXIT", "ADD", "TRIM"]
    trade_count = sum(int(counts.get(k, 0) or 0) for k in trade_actions)
    value_count = int(counts.get("VALUE_CHANGE", 0) or 0)
    if not changes:
        return SubsystemResult(
            name="POSITION DIFF",
            available=True,
            surface_line="POSITION DIFF: no account-level changes since prior snapshot",
            priority="INFO",
            actionable_count=0,
            payload={"counts": counts},
        )

    top = []
    for row in changes[:5]:
        if not isinstance(row, dict):
            continue
        try:
            delta = f"{float(row.get('share_delta') or 0):+g}sh"
        except (TypeError, ValueError):
            delta = "share change"
        acct = row.get("account") or "account"
        top.append(f"{row.get('ticker')} {row.get('action')} {delta} ({acct})")
    more = max(0, len(changes) - len(top))
    suffix = "; " + "; ".join(top) if top else ""
    if more:
        suffix += f"; +{more} more"
    priority = "HIGH" if trade_count else "INFO"
    return SubsystemResult(
        name="POSITION DIFF",
        available=True,
        surface_line=(
            "POSITION DIFF: "
            f"{trade_count} trade-like change(s), {value_count} value-only change(s)"
            f"{suffix}"
        ),
        priority=priority,
        actionable_count=trade_count,
        payload={"counts": counts, "changes": len(changes)},
    )


PRIORITY_RANK = {"CRIT": 0, "HIGH": 1, "MED": 2, "INFO": 3, "NONE": 4}


def _normalize_catalysts_for_routine(catalysts, today=None) -> list:
    """Normalize Catalyst Calendar input for preflight subsystem consumers."""
    if not catalysts:
        return []
    rows = catalysts.get("catalysts") if isinstance(catalysts, dict) else catalysts
    if not isinstance(rows, list):
        return []
    if catalysts_from_calendar_rows is None:
        return rows
    return catalysts_from_calendar_rows(rows, as_of=today)


def orchestrate(positions: List[Dict], theses: List[Dict],
                sleeve_total: float,
                prior_snapshot: Optional[Dict] = None,
                rationales: Optional[List[Dict]] = None,
                macro_pulse: Optional[Dict] = None,
                source_rates: Optional[Dict] = None,
                insider_data: Optional[Dict] = None,
                catalysts: Optional[List[Dict]] = None,
                source_calls: Optional[List[Dict]] = None,
                parabolic_data: Optional[Dict] = None,
                position_reconciliation: Optional[Dict] = None,
                inbox_call_dates: Optional[List] = None,
                log_call_dates: Optional[List] = None
                ) -> SessionDashboard:
    """Run all subsystems and produce dashboard."""
    current_snapshot = {
        "snapshot_date": "current",
        "positions": positions,
        "sleeve_value": sleeve_total,
    }
    catalysts = _normalize_catalysts_for_routine(catalysts)

    # v12.5 Issue #10: confirm the source-calibration chain is fresh before letting
    # SOURCE PERSISTENCE fire LOUD. Live Inbox/Log dates are routine-supplied; absent
    # them the chain is "not checked" -> persistence stays PROVISIONAL (safe default).
    calibration_fresh = False
    if sct is not None and inbox_call_dates and log_call_dates:
        try:
            _cache_dates = [c.get("date") for c in (source_calls or [])
                            if isinstance(c, dict) and c.get("date")]
            calibration_fresh = not sct.calibration_chain_staleness(
                inbox_call_dates, log_call_dates, _cache_dates).get("stale")
        except Exception:
            calibration_fresh = False

    subs = [
        _run_macro(macro_pulse),
        _run_source_calibration(source_rates),
        _run_outcomes(prior_snapshot, current_snapshot, rationales, theses,
                      macro_pulse, source_calls),
        _run_conviction(positions, theses, sleeve_total, macro_pulse, source_rates),
        _run_target_drift(positions, sleeve_total),
        _run_position_diff(position_reconciliation),
        _run_factor(positions, theses, sleeve_total, macro_pulse),
        _run_insider(positions, insider_data, catalysts, theses, macro_pulse),
        _run_parabolic(parabolic_data),
        _run_persistence(source_calls, theses, calibration_fresh),
    ]

    # Priority-ordered list of subsystem names that have actionable items
    actionable_subs = [s for s in subs if s.actionable_count > 0]
    actionable_subs.sort(key=lambda s: (PRIORITY_RANK.get(s.priority, 5),
                                        -s.actionable_count))

    dashboard = SessionDashboard(
        macro_regime=(macro_pulse or {}).get("regime_label")
                     or (macro_pulse or {}).get("regime"),
        sleeve_total=sleeve_total,
        subsystems=subs,
        priority_order=[s.name for s in actionable_subs],
    )

    # Build summary block
    lines = []
    lines.append("=" * 70)
    lines.append("SESSION PRE-FLIGHT DASHBOARD — v11.26")
    lines.append("=" * 70)
    if dashboard.macro_regime:
        lines.append(f"Macro regime: {dashboard.macro_regime}")
    lines.append(f"Sleeve total: ${sleeve_total:,.0f}")
    lines.append("")
    for s in subs:
        icon = {"CRIT": "🔴", "HIGH": "🟠", "MED": "🟡",
                "INFO": "•",    "NONE": "·"}.get(s.priority, "•")
        avail = "" if s.available else "  (unavailable)"
        lines.append(f"{icon} [{s.priority:4}] {s.surface_line}{avail}")
    lines.append("")
    if dashboard.priority_order:
        lines.append("LOOK AT FIRST (priority order):")
        for i, n in enumerate(dashboard.priority_order, 1):
            lines.append(f"  {i}. {n}")
    else:
        lines.append("(No actionable items — passive session.)")
    dashboard.summary_block = "\n".join(lines)
    return dashboard


# ============================================================================
# OUTPUT FORMATTERS
# ============================================================================

def format_text(d: SessionDashboard) -> str:
    return d.summary_block


def format_json(d: SessionDashboard) -> str:
    return json.dumps(asdict(d), indent=2, default=str)


# ============================================================================
# SELF-TEST
# ============================================================================

def _self_test() -> bool:
    if any(x is None for x in (ol, csc, pfe, ias)):
        print("FAIL: dependencies not available — ensure /home/claude/build "
              "is on sys.path and outcome_logger, conviction_sizing_calibrator, "
              "portfolio_factor_exposure, insider_activity_scan are present")
        return False

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

    # ----- Test 1: minimal — empty everything → no actionable items
    d = orchestrate([], [], sleeve_total=1)
    assert_eq(len(d.priority_order), 0, "empty: no actionable items")
    assert_eq(len(d.subsystems), 10, "10 subsystems always run")

    # ----- Test 2: realistic operator portfolio
    positions = [
        {"ticker": "BMNR", "market_value": 71500},
        {"ticker": "LEU", "market_value": 96000},
        {"ticker": "NVDA", "market_value": 139000},
        {"ticker": "MP", "market_value": 39680},
        {"ticker": "UUUU", "market_value": 43000},
    ]
    theses = [
        {"ticker": "BMNR", "tier": "T1", "source": "operator",
         "factor_tags": ["crypto", "eth"]},
        {"ticker": "LEU", "tier": "T1", "source": "Meridian",
         "factor_tags": ["critical_minerals", "nuclear"]},
        {"ticker": "NVDA", "tier": "T2", "source": "Lee",
         "factor_tags": ["AI_complex", "long_duration_growth"]},
        {"ticker": "MP", "tier": "T3", "source": "Meridian",
         "factor_tags": ["critical_minerals", "rare_earth"]},
        {"ticker": "UUUU", "tier": "T3", "source": "Meridian",
         "factor_tags": ["critical_minerals", "uranium"]},
    ]
    macro = {"regime_label": "duration_WEAK · dollar_STRONG · vol_COMPLACENT",
             "alerts": ["10Y broke above 4.6%"]}
    d = orchestrate(positions, theses, 1875000, macro_pulse=macro)
    assert_true(len(d.priority_order) > 0, "realistic: actionable items exist")
    # Critical conviction (BMNR critically_below) should be in top 2
    top2 = d.priority_order[:2]
    assert_true("CONVICTION SIZING" in top2,
                "CONVICTION SIZING in top 2 priorities")

    # ----- Test 3: source calibration with CONSISTENT_MISS → CRIT priority
    rates = {"newton": {"A": {"band": "CONSISTENT_MISS", "n": 20}}}
    d = orchestrate(positions, theses, 1875000, source_rates=rates)
    sc = next(s for s in d.subsystems if s.name == "SOURCE CALIBRATION")
    assert_eq(sc.priority, "CRIT", "CONSISTENT_MISS → CRIT")

    # ----- Test 4: outcomes diff
    prior = {
        "snapshot_date": "prior",
        "positions": positions + [{"ticker": "MU", "market_value": 50000,
                                   "cost_basis": 40000}]
    }
    d = orchestrate(positions, theses, 1875000, prior_snapshot=prior)
    outcomes = next(s for s in d.subsystems if s.name == "OUTCOMES")
    assert_true(outcomes.available, "outcomes available with prior")
    assert_true(outcomes.actionable_count >= 1, "MU exit counted")

    # ----- Test 5: insider data
    insider = {
        "LEU": [{"date": "2026-05-15", "transaction_code": "P",
                 "insider_title": "CEO", "insider_name": "X",
                 "shares": 5000, "price": 200}]
    }
    d = orchestrate(positions, theses, 1875000, insider_data=insider)
    ia = next(s for s in d.subsystems if s.name == "INSIDER ACTIVITY")
    assert_true(ia.available, "insider data available")
    assert_true(ia.actionable_count >= 1, "LEU bullish counted")

    # ----- Test 6: factor exposure detects macro stack
    d = orchestrate(positions, theses, 1875000, macro_pulse=macro)
    fe = next(s for s in d.subsystems if s.name == "FACTOR EXPOSURE")
    assert_true(fe.payload["n_macro_stacks"] >= 1,
                "macro stack detected in factor exposure")

    # ----- Test 7: priority ordering
    rates = {"newton": {"A": {"band": "CONSISTENT_MISS", "n": 20}}}  # CRIT
    macro2 = {"regime_label": "duration_WEAK", "alerts": ["alert1"]}  # HIGH
    d = orchestrate(positions, theses, 1875000,
                    source_rates=rates, macro_pulse=macro2)
    # CONVICTION (CRIT) and SOURCE CALIBRATION (CRIT) should both be top tier
    # MACRO (HIGH) should be below
    assert_true("CONVICTION SIZING" in d.priority_order[:2],
                "conviction CRIT in top 2")
    assert_true("SOURCE CALIBRATION" in d.priority_order[:2],
                "source calibration CRIT in top 2")

    # ----- Test 8: text format works
    text = format_text(d)
    assert_true("SESSION PRE-FLIGHT DASHBOARD" in text, "dashboard header")
    assert_true("Macro regime" in text, "macro regime line")
    assert_true("LOOK AT FIRST" in text, "priority list label")

    # ----- Test 9: JSON format
    js = format_json(d)
    parsed = json.loads(js)
    assert_eq(parsed["sleeve_total"], 1875000, "JSON sleeve_total")
    assert_true(len(parsed["subsystems"]) == 10, "JSON has 10 subsystems")

    # ----- Test 10: all-none scenario
    d = orchestrate([], [], 1)
    text = format_text(d)
    assert_true("passive session" in text or len(d.priority_order) == 0,
                "passive session when no signal")

    # ----- Test 11: high actionable count → MACRO highest
    macro_alerts = {"regime_label": "VOL_SPIKE",
                    "alerts": ["a1", "a2", "a3", "a4", "a5"]}
    d = orchestrate([], [], 1, macro_pulse=macro_alerts)
    macro_sub = next(s for s in d.subsystems if s.name == "MACRO PULSE")
    assert_eq(macro_sub.actionable_count, 5, "macro alert count")

    # ----- Test 12: actionable conviction with critical
    d = orchestrate(positions, theses, 1875000)
    conv = next(s for s in d.subsystems if s.name == "CONVICTION SIZING")
    assert_eq(conv.priority, "CRIT",
              "BMNR critically below → CRIT priority")

    # ----- Test 13: source rates with HIGH_CONVICTION → INFO
    rates = {"newton": {"A": {"band": "HIGH_CONVICTION", "n": 20}}}
    d = orchestrate([], [], 1, source_rates=rates)
    sc = next(s for s in d.subsystems if s.name == "SOURCE CALIBRATION")
    assert_eq(sc.priority, "INFO", "HIGH_CONVICTION alone → INFO")

    # ----- Test 14: source rates with all INSUFFICIENT_DATA
    rates = {"newton": {"A": {"band": "NORMAL", "n": 5}}}
    d = orchestrate([], [], 1, source_rates=rates)
    sc = next(s for s in d.subsystems if s.name == "SOURCE CALIBRATION")
    assert_eq(sc.actionable_count, 0, "INSUFFICIENT_DATA: no actionable")

    # ----- Test 15: dashboard has correct structure
    assert_true(hasattr(d, "subsystems"), "dashboard.subsystems")
    assert_true(hasattr(d, "priority_order"), "dashboard.priority_order")
    assert_true(hasattr(d, "summary_block"), "dashboard.summary_block")

    # ----- Test 16: parabolic — AUTOFIRE → HIGH + in priority_order
    parabolic = {"as_of": "2026-06-01",
                 "results": [
                     {"ticker": "VIAV", "surface_tier": "AUTOFIRE", "score": 10.5},
                     {"ticker": "MU", "surface_tier": "WATCHLIST", "score": 7.0},
                     {"ticker": "NVDA", "surface_tier": "SKIP", "score": 4.5}],
                 "counts": {"AUTOFIRE": 1, "WATCHLIST": 1, "SKIP": 1}}
    d = orchestrate([], [], 1, parabolic_data=parabolic)
    pb = next(s for s in d.subsystems if s.name == "PARABOLIC SETUPS")
    assert_true(pb.available, "parabolic available with data")
    assert_eq(pb.priority, "HIGH", "AUTOFIRE → HIGH priority")
    assert_eq(pb.actionable_count, 2, "AUTOFIRE+WATCHLIST counted")
    assert_true("PARABOLIC SETUPS" in d.priority_order,
                "parabolic in priority_order")
    assert_true("VIAV" in pb.surface_line, "autofire ticker in surface line")

    # ----- Test 17: parabolic honesty guard — present-but-empty → not evaluated
    d = orchestrate([], [], 1, parabolic_data={"results": [], "counts": {}})
    pb = next(s for s in d.subsystems if s.name == "PARABOLIC SETUPS")
    assert_true(not pb.available,
                "empty parabolic cache → unavailable (honesty guard)")
    assert_true("not evaluated" in pb.surface_line,
                "empty cache surfaces 'not evaluated'")

    # ----- Test 18: parabolic all-SKIP IS evaluated (nothing firing) → INFO
    d = orchestrate([], [], 1, parabolic_data={
        "results": [{"ticker": "X", "surface_tier": "SKIP", "score": 2.0}],
        "counts": {"AUTOFIRE": 0, "WATCHLIST": 0, "SKIP": 1}})
    pb = next(s for s in d.subsystems if s.name == "PARABOLIC SETUPS")
    assert_true(pb.available, "all-SKIP parabolic IS evaluated (available)")
    assert_eq(pb.priority, "INFO", "all-SKIP → INFO")
    assert_eq(pb.actionable_count, 0, "all-SKIP → 0 actionable")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return failed == 0


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="Session Orchestrator v11.26")
    p.add_argument("--positions", help="Current positions JSON")
    p.add_argument("--theses", help="Live Theses JSON")
    p.add_argument("--sleeve-total", type=float)
    p.add_argument("--prior", help="Prior snapshot JSON (optional)")
    p.add_argument("--macro", help="Macro state JSON (optional)")
    p.add_argument("--source-rates", help="Source rates JSON (optional)")
    p.add_argument("--insider-data", help="Insider data JSON (optional)")
    p.add_argument("--catalysts", help="Catalysts JSON (optional)")
    p.add_argument("--source-calls", help="Pending source calls JSON (optional)")
    p.add_argument("--rationales", help="Active rationales JSON (optional)")
    p.add_argument("--parabolic", help="Parabolic setups JSON (optional)")
    p.add_argument("--position-reconciliation", help="Position reconciliation JSON (optional)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if not all([args.positions, args.theses, args.sleeve_total]):
        p.error("--positions, --theses, --sleeve-total required (or --self-test)")

    with open(args.positions) as f:
        positions = json.load(f)
    if isinstance(positions, dict) and "positions" in positions:
        positions = positions["positions"]
    with open(args.theses) as f:
        theses = json.load(f)
    prior = json.load(open(args.prior)) if args.prior else None
    macro = json.load(open(args.macro)) if args.macro else None
    rates = json.load(open(args.source_rates)) if args.source_rates else None
    insider = json.load(open(args.insider_data)) if args.insider_data else None
    catalysts = json.load(open(args.catalysts)) if args.catalysts else None
    source_calls = json.load(open(args.source_calls)) if args.source_calls else None
    rationales = json.load(open(args.rationales)) if args.rationales else None
    parabolic = json.load(open(args.parabolic)) if args.parabolic else None
    position_reconciliation = json.load(open(args.position_reconciliation)) if args.position_reconciliation else None

    d = orchestrate(positions, theses, args.sleeve_total,
                    prior_snapshot=prior,
                    rationales=rationales,
                    macro_pulse=macro,
                    source_rates=rates,
                    insider_data=insider,
                    catalysts=catalysts,
                    source_calls=source_calls,
                    parabolic_data=parabolic,
                    position_reconciliation=position_reconciliation)
    if args.json:
        print(format_json(d))
    else:
        print(format_text(d))


if __name__ == "__main__":
    main()
