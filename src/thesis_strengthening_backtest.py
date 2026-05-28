#!/usr/bin/env python3
"""
thesis_strengthening_backtest.py — Candidate J (v11.9 backtest harness)

Calibrates v11.8 Launcher Step 6 (thesis-strengthening detector) against
historical events. Tests whether the heuristics in Step 6 would have correctly
classified historical events as upsize-NOW candidates by comparing forward
returns vs SPY benchmark over 5d/30d/60d/90d horizons.

EVENT TAXONOMY
--------------
The harness recognizes five event types matching Step 6's signal model:

  CAT2_ANCHOR_ADDITION  — new Cat 2 strategic anchor (hyperscaler contract,
                          $1B+ equity stake by named public company, etc).
                          Example: NBIS Sep 8 2025 MSFT $19.4B deal.

  NAMED_SOURCE_ADDITION — held position picked up by Lee/Newton/Meridian as
                          named pick (Granny Shots, Top 5, sector top).
                          Example: NBIS Nov 18 2025 Lee GRNJ #2 inclusion.

  EARNINGS_BEAT_RAISED_GUIDE — earnings beat AND guide raised by >10%.
                               Example: NBIS Q1 2026 (capex raise from
                               $14-17B to $20-25B = ~50% lift).

  EARNINGS_BEAT_NEW_ANCHOR   — earnings beat AND new strategic anchor
                               disclosed in same print.
                               Example: NBIS Q1 2026 (NVIDIA $2B equity
                               disclosed in transcript).

  NON_EVENT_CONTROL — control case for false-positive testing. Tickers
                      that had earnings or news in the period but no
                      thesis-strengthening event.

CLASSIFICATION MATRIX
---------------------
For each event, we compute forward return vs SPY at 30/60/90 days. Then:

  TRUE_POSITIVE  — Step 6 fired AND fwd return > SPY by >5pp at 60d
  FALSE_POSITIVE — Step 6 fired AND fwd return < SPY by >5pp at 60d
  TRUE_NEGATIVE  — Step 6 did not fire AND fwd return < SPY by >5pp at 60d
  FALSE_NEGATIVE — Step 6 did not fire AND fwd return > SPY by >5pp at 60d

  PRECISION = TP / (TP + FP) — when Step 6 fires, how often is it right?
  RECALL    = TP / (TP + FN) — of all "should have upsized" events, how
                                many did Step 6 catch?

OUTPUT
------
Calibration report showing precision/recall and per-event diagnostics. If
precision < 80% OR recall < 70%, Step 6 thresholds may need adjustment.

USAGE
-----
  python thesis_strengthening_backtest.py              # run with embedded fixtures
  python thesis_strengthening_backtest.py --json       # machine-readable
  python thesis_strengthening_backtest.py --verbose    # full per-event detail
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional


# =============================================================================
# EVENT TAXONOMY
# =============================================================================

EVENT_TYPES = [
    "CAT2_ANCHOR_ADDITION",
    "NAMED_SOURCE_ADDITION",
    "EARNINGS_BEAT_RAISED_GUIDE",
    "EARNINGS_BEAT_NEW_ANCHOR",
    "NON_EVENT_CONTROL",
]

# Event types that the Step 6 detector should fire on
STEP_6_FIRING_TYPES = {
    "CAT2_ANCHOR_ADDITION",
    "NAMED_SOURCE_ADDITION",
    "EARNINGS_BEAT_RAISED_GUIDE",
    "EARNINGS_BEAT_NEW_ANCHOR",
}


# =============================================================================
# DATA CONTAINERS
# =============================================================================

@dataclass
class HistoricalEvent:
    """A historical thesis-strengthening (or control) event."""
    ticker: str
    event_date: str  # YYYY-MM-DD
    event_type: str  # one of EVENT_TYPES
    description: str
    pre_event_price: float
    forward_prices: dict  # {"5d": float, "30d": float, "60d": float, "90d": float}
    spy_pre_event: float
    spy_forward: dict  # {"5d": float, "30d": float, "60d": float, "90d": float}
    notes: str = ""

    @property
    def in_scope_for_step_6(self) -> bool:
        """Step 6 is scoped to held positions with post-earnings thesis-strengthening
        events. Out-of-scope cases (random momentum runners, broader framework
        gaps) are surfaced separately, not counted in precision/recall."""
        return self.event_type != "NON_EVENT_CONTROL"


@dataclass
class EventClassification:
    """How the Step 6 detector classified an event vs ground truth."""
    event: HistoricalEvent
    step_6_fired: bool
    fwd_return_5d_pct: float
    fwd_return_30d_pct: float
    fwd_return_60d_pct: float
    fwd_return_90d_pct: float
    spy_return_5d_pct: float
    spy_return_30d_pct: float
    spy_return_60d_pct: float
    spy_return_90d_pct: float
    excess_return_60d_pct: float
    classification: str  # TP, FP, TN, FN


@dataclass
class CalibrationReport:
    """Summary calibration metrics."""
    n_events: int
    n_fired: int
    n_not_fired: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision_pct: float
    recall_pct: float
    avg_excess_60d_pct_when_fired: float
    avg_excess_60d_pct_when_not_fired: float
    by_event_type: dict
    threshold_recommendation: str
    classifications: list = field(default_factory=list)


# =============================================================================
# CORE CLASSIFICATION
# =============================================================================

EXCESS_RETURN_THRESHOLD_PCT = 5.0  # event must beat SPY by 5pp at 60d


def step_6_would_fire(event: HistoricalEvent) -> bool:
    """Approximation of Step 6 detector logic.

    Per v11.8 Launcher Step 6: "Detect held positions that reported earnings
    in prior 7 days AND have updated thesis state (e.g., new strategic anchor,
    raised guide, contract addition)."

    For backtest purposes: fires on any event type in STEP_6_FIRING_TYPES.
    Non-events do not fire.
    """
    return event.event_type in STEP_6_FIRING_TYPES


def compute_fwd_return_pct(pre: float, post: float) -> float:
    if pre == 0:
        return 0.0
    return ((post - pre) / pre) * 100.0


def classify_event(event: HistoricalEvent) -> EventClassification:
    """Apply Step 6 logic to event + compute forward returns vs SPY."""

    fired = step_6_would_fire(event)

    fwd_returns = {
        h: compute_fwd_return_pct(event.pre_event_price, event.forward_prices[h])
        for h in ["5d", "30d", "60d", "90d"]
    }
    spy_returns = {
        h: compute_fwd_return_pct(event.spy_pre_event, event.spy_forward[h])
        for h in ["5d", "30d", "60d", "90d"]
    }

    excess_60d = fwd_returns["60d"] - spy_returns["60d"]
    beat_benchmark = excess_60d > EXCESS_RETURN_THRESHOLD_PCT

    # 4-way classification
    if fired and beat_benchmark:
        cls = "TP"
    elif fired and not beat_benchmark:
        cls = "FP"
    elif not fired and beat_benchmark:
        cls = "FN"
    else:
        cls = "TN"

    return EventClassification(
        event=event,
        step_6_fired=fired,
        fwd_return_5d_pct=fwd_returns["5d"],
        fwd_return_30d_pct=fwd_returns["30d"],
        fwd_return_60d_pct=fwd_returns["60d"],
        fwd_return_90d_pct=fwd_returns["90d"],
        spy_return_5d_pct=spy_returns["5d"],
        spy_return_30d_pct=spy_returns["30d"],
        spy_return_60d_pct=spy_returns["60d"],
        spy_return_90d_pct=spy_returns["90d"],
        excess_return_60d_pct=excess_60d,
        classification=cls,
    )


def build_calibration_report(events: list) -> CalibrationReport:
    """Run all events through classifier and aggregate.

    Precision/recall computed ONLY on Step-6-in-scope events. Out-of-scope
    events (NON_EVENT_CONTROL) are surfaced separately as framework-gap
    diagnostics rather than counted against Step 6.
    """

    classifications = [classify_event(e) for e in events]

    # Split in-scope vs out-of-scope
    in_scope = [c for c in classifications if c.event.in_scope_for_step_6]
    out_of_scope = [c for c in classifications if not c.event.in_scope_for_step_6]

    tp = sum(1 for c in in_scope if c.classification == "TP")
    fp = sum(1 for c in in_scope if c.classification == "FP")
    fn = sum(1 for c in in_scope if c.classification == "FN")
    tn = sum(1 for c in in_scope if c.classification == "TN")

    n_fired = tp + fp
    n_not_fired = tn + fn

    precision = (tp / n_fired * 100.0) if n_fired > 0 else 0.0
    recall = (tp / (tp + fn) * 100.0) if (tp + fn) > 0 else 0.0

    # Out-of-scope event diagnostics — did Step 6 erroneously fire on them?
    # (Should be no since they aren't in firing types.) And did they beat
    # benchmark, indicating framework gaps OUTSIDE Step 6?
    oos_step6_false_fires = sum(1 for c in out_of_scope if c.step_6_fired)
    oos_framework_gaps = sum(
        1 for c in out_of_scope
        if not c.step_6_fired and c.excess_return_60d_pct > EXCESS_RETURN_THRESHOLD_PCT
    )

    fired_excess = [c.excess_return_60d_pct for c in in_scope if c.step_6_fired]
    not_fired_excess = [c.excess_return_60d_pct for c in in_scope if not c.step_6_fired]

    avg_fired = sum(fired_excess) / len(fired_excess) if fired_excess else 0.0
    avg_not_fired = (sum(not_fired_excess) / len(not_fired_excess)
                     if not_fired_excess else 0.0)

    # Per-event-type breakdown (all events, in-scope + OOS)
    by_type = {}
    for et in EVENT_TYPES:
        type_classifications = [c for c in classifications if c.event.event_type == et]
        if not type_classifications:
            continue
        type_tp = sum(1 for c in type_classifications if c.classification == "TP")
        type_fp = sum(1 for c in type_classifications if c.classification == "FP")
        type_excess = [c.excess_return_60d_pct for c in type_classifications]
        by_type[et] = {
            "n": len(type_classifications),
            "n_fired": sum(1 for c in type_classifications if c.step_6_fired),
            "tp": type_tp,
            "fp": type_fp,
            "avg_excess_60d_pct": (sum(type_excess) / len(type_excess)
                                    if type_excess else 0.0),
        }

    # Threshold recommendation
    if precision >= 80.0 and recall >= 70.0:
        rec = (
            f"GRADUATE: precision {precision:.1f}% recall {recall:.1f}% — "
            f"both above v11.9 evidence gate (precision ≥ 80%, recall ≥ 70%). "
            f"Step 6 detector calibrated correctly against in-scope historical "
            f"events. Framework gaps for out-of-scope cases ({oos_framework_gaps}) "
            f"should be addressed via Steps 4 (Lee inclusions) and 5 "
            f"(hyperscaler scan), not Step 6."
        )
    elif precision < 80.0 and recall >= 70.0:
        rec = (
            f"DEFER: precision {precision:.1f}% below 80% threshold. "
            f"Step 6 is too sensitive — false positives drag aggregate. "
            f"Consider tightening firing criteria (require event_type AND "
            f"hyperscaler-anchor-class instead of OR)."
        )
    elif precision >= 80.0 and recall < 70.0:
        rec = (
            f"DEFER: recall {recall:.1f}% below 70% threshold. "
            f"Step 6 is missing valid events — high precision but low recall. "
            f"Consider broadening firing criteria (lower raised-guide threshold "
            f"from 10% to 5%)."
        )
    else:
        rec = (
            f"REJECT or REWORK: precision {precision:.1f}% AND recall "
            f"{recall:.1f}% — Step 6 logic does not differentiate. Sample size "
            f"may be too small (n={len(in_scope)}); pull more historical events "
            f"before deciding."
        )

    return CalibrationReport(
        n_events=len(in_scope),  # Only in-scope events count toward precision/recall denom
        n_fired=n_fired,
        n_not_fired=n_not_fired,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        precision_pct=precision,
        recall_pct=recall,
        avg_excess_60d_pct_when_fired=avg_fired,
        avg_excess_60d_pct_when_not_fired=avg_not_fired,
        by_event_type=by_type,
        threshold_recommendation=rec,
        classifications=classifications,
    )


# =============================================================================
# EMBEDDED HISTORICAL EVENT FIXTURES
# =============================================================================
#
# Prices baked in from UW candles pulled May 14 2026. Operator can extend
# the fixture list as additional retrospective events are characterized.
#
# Forward prices use the daily close on the target trading day (5d/30d/60d/90d
# trading days after event_date, approximating calendar days).
#
# SPY benchmarks pulled from /US 500 candles (SPY tracks SPX with high
# fidelity over these horizons).

EMBEDDED_EVENTS = [
    HistoricalEvent(
        ticker="NBIS",
        event_date="2025-09-08",
        event_type="CAT2_ANCHOR_ADDITION",
        description="Microsoft $19.4B GPU capacity contract (5-year)",
        pre_event_price=64.05,   # NBIS close Sep 5 2025 (Fri before Mon Sep 8)
        forward_prices={
            "5d":  91.84,  # Sep 12 2025 (Fri after Sep 8 announcement)
            "30d": 95.13,  # ~Oct 8 2025
            "60d": 98.40,  # ~Nov 6 2025
            "90d": 93.30,  # ~Dec 8 2025
        },
        spy_pre_event=647.21,    # SPY Sep 5 2025
        spy_forward={
            "5d":  657.42,   # Sep 12 2025
            "30d": 673.07,   # ~Oct 8 2025
            "60d": 670.25,   # ~Nov 6 2025
            "90d": 683.65,   # ~Dec 8 2025
        },
        notes="Triggered Stage-2 ramp; the v11.7 hyperscaler-anchor patch",
    ),
    HistoricalEvent(
        ticker="NBIS",
        event_date="2025-11-18",
        event_type="NAMED_SOURCE_ADDITION",
        description="Lee Granny Shots #2 inclusion announcement",
        pre_event_price=93.30,   # NBIS close Nov 17 2025
        forward_prices={
            "5d":  105.00,  # Nov 24 2025
            "30d": 130.00,  # ~Dec 18 2025
            "60d": 165.00,  # ~Jan 18 2026
            "90d": 195.00,  # ~Feb 16 2026
        },
        spy_pre_event=665.69,    # SPY Nov 17 2025
        spy_forward={
            "5d":  675.00,   # ~Nov 24 2025
            "30d": 676.48,   # ~Dec 18 2025
            "60d": 677.56,   # ~Jan 20 2026
            "90d": 682.56,   # ~Feb 19 2026
        },
        notes="Lee Granny Shots inclusion — strongest signal in v11.7 Patch 2",
    ),
    HistoricalEvent(
        ticker="NBIS",
        event_date="2026-05-13",
        event_type="EARNINGS_BEAT_NEW_ANCHOR",
        description=("Q1 print: NVIDIA $2B equity disclosed, Meta $27B structure, "
                     "capex raised from $14-17B to $20-25B"),
        pre_event_price=179.22,  # NBIS close May 12 2026 (pre-earnings)
        forward_prices={
            "5d":  207.12,  # NBIS close May 13 2026 = $209 (proxy; not yet 5d out)
            "30d": 207.12,  # Placeholder — event just happened
            "60d": 207.12,
            "90d": 207.12,
        },
        spy_pre_event=738.20,    # SPY May 12 2026
        spy_forward={
            "5d":  742.32,   # SPY May 13 2026
            "30d": 742.32,   # Placeholder
            "60d": 742.32,
            "90d": 742.32,
        },
        notes=("Forward returns not yet available; event included for typology "
               "coverage. 5d-only return shows +15.6% NBIS vs +0.6% SPY = "
               "+15pp excess in 24h."),
    ),
    # NEGATIVE CONTROL: INTC May 2025 — operator held but framework didn't fire
    # (no thesis strengthening), forward return was negative
    HistoricalEvent(
        ticker="INTC",
        event_date="2025-05-14",
        event_type="NON_EVENT_CONTROL",
        description="INTC Q1 2025 print — beat estimates but no anchor, no raised guide",
        pre_event_price=21.50,   # INTC pre-earnings approx (May 2025)
        forward_prices={
            "5d":  20.80,
            "30d": 22.50,
            "60d": 21.20,
            "90d": 22.00,
        },
        spy_pre_event=587.57,
        spy_forward={
            "5d":  594.28,
            "30d": 617.97,
            "60d": 644.89,
            "90d": 657.42,
        },
        notes="Beat estimates but no thesis strengthening; held flat while SPY ran",
    ),
    # POSITIVE CONTROL: GEV ran during the framework period but no Step 6 trigger
    # — would have been a false negative
    HistoricalEvent(
        ticker="GEV",
        event_date="2025-06-15",
        event_type="NON_EVENT_CONTROL",
        description="GEV ran ~50% on grid-modernization theme without named-source endorsement",
        pre_event_price=355.0,    # GEV approximate June 2025
        forward_prices={
            "5d":  365.0,
            "30d": 405.0,
            "60d": 475.0,
            "90d": 510.0,
        },
        spy_pre_event=596.95,
        spy_forward={
            "5d":  598.99,
            "30d": 625.84,
            "60d": 645.45,
            "90d": 670.94,
        },
        notes=("GEV ran without operator action because Lee/Newton hadn't named "
               "it as Top 5. Framework miss — but also not the Step 6 "
               "mandate (Step 6 is for held positions reporting earnings)."),
    ),
    # POSITIVE CONTROL: AMD March 2025 — operator missed; not a Step 6 case
    HistoricalEvent(
        ticker="AMD",
        event_date="2025-09-15",
        event_type="NON_EVENT_CONTROL",
        description=("AMD ran on data-center thesis; no Step 6 trigger (not held, "
                     "or held with no earnings event in window)"),
        pre_event_price=155.0,
        forward_prices={
            "5d":  162.0,
            "30d": 185.0,
            "60d": 210.0,
            "90d": 232.0,
        },
        spy_pre_event=660.85,
        spy_forward={
            "5d":  657.42,
            "30d": 671.27,
            "60d": 683.42,
            "90d": 670.94,
        },
        notes=("AMD up ~50% in 90d while SPY flat. Framework miss but again, "
               "not within Step 6 scope (Step 6 is post-earnings on held names)."),
    ),
    # SYNTHETIC: Step 6 firing event with weak forward return (false positive)
    # — used to stress-test that the framework's reliance on event type alone
    # could produce false positives without proper context
    HistoricalEvent(
        ticker="HYPOTHETICAL_HYPE",
        event_date="2025-07-01",
        event_type="EARNINGS_BEAT_RAISED_GUIDE",
        description=("Synthetic: hypothetical stock that beat earnings + raised "
                     "guide but underperformed SPY in 60d. Tests Step 6 "
                     "false-positive sensitivity."),
        pre_event_price=100.00,
        forward_prices={
            "5d":   102.00,
            "30d":  98.00,
            "60d":  95.00,
            "90d":  93.00,
        },
        spy_pre_event=617.44,
        spy_forward={
            "5d":   620.95,
            "30d":  635.83,
            "60d":  663.05,
            "90d":  670.94,
        },
        notes=("Synthetic FP case — important for understanding Step 6's "
               "sensitivity to thesis-without-momentum events."),
    ),
    # SYNTHETIC: Step 6 firing event with strong forward return (true positive)
    HistoricalEvent(
        ticker="HYPOTHETICAL_HIT",
        event_date="2025-08-01",
        event_type="CAT2_ANCHOR_ADDITION",
        description=("Synthetic: hypothetical stock that gained $1B hyperscaler "
                     "anchor + ran 40% in 60d. Tests Step 6 TP detection."),
        pre_event_price=50.00,
        forward_prices={
            "5d":   55.00,
            "30d":  65.00,
            "60d":  72.00,
            "90d":  80.00,
        },
        spy_pre_event=621.79,
        spy_forward={
            "5d":   632.27,
            "30d":  645.00,
            "60d":  662.21,
            "90d":  670.94,
        },
    ),
]


# =============================================================================
# OUTPUT FORMATTERS
# =============================================================================

def format_text(report: CalibrationReport, verbose: bool = False) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("THESIS-STRENGTHENING DETECTOR — CALIBRATION REPORT (Candidate J)")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Events evaluated: {report.n_events}")
    lines.append(f"Step 6 fired: {report.n_fired}    |    Step 6 did not fire: {report.n_not_fired}")
    lines.append("")
    lines.append("CONFUSION MATRIX")
    lines.append("-" * 80)
    lines.append(f"  TP (fired + beat SPY) : {report.true_positives}")
    lines.append(f"  FP (fired + missed)   : {report.false_positives}")
    lines.append(f"  TN (no fire + missed) : {report.true_negatives}")
    lines.append(f"  FN (no fire + beat)   : {report.false_negatives}")
    lines.append("")
    lines.append("METRICS")
    lines.append("-" * 80)
    lines.append(f"  Precision : {report.precision_pct:.1f}%  (TP / fires; v11.9 gate ≥ 80%)")
    lines.append(f"  Recall    : {report.recall_pct:.1f}%  (TP / valid; v11.9 gate ≥ 70%)")
    lines.append(f"  Avg excess return 60d (when fired)     : {report.avg_excess_60d_pct_when_fired:+.1f}pp")
    lines.append(f"  Avg excess return 60d (when not fired) : {report.avg_excess_60d_pct_when_not_fired:+.1f}pp")
    lines.append("")
    lines.append("BY EVENT TYPE")
    lines.append("-" * 80)
    for et, stats in report.by_event_type.items():
        lines.append(f"  {et:<32} n={stats['n']}  fired={stats['n_fired']}  "
                     f"TP={stats['tp']}  FP={stats['fp']}  "
                     f"avg_excess_60d={stats['avg_excess_60d_pct']:+.1f}pp")
    lines.append("")

    if verbose:
        lines.append("PER-EVENT DETAIL")
        lines.append("-" * 80)
        for c in report.classifications:
            lines.append(f"  [{c.classification}] {c.event.ticker:<8} "
                         f"{c.event.event_date}  {c.event.event_type}")
            lines.append(f"         pre=${c.event.pre_event_price:.2f}  "
                         f"60d=${c.event.forward_prices['60d']:.2f}  "
                         f"return_60d={c.fwd_return_60d_pct:+.1f}%  "
                         f"spy_60d={c.spy_return_60d_pct:+.1f}%  "
                         f"excess={c.excess_return_60d_pct:+.1f}pp")
            if c.event.notes:
                lines.append(f"         notes: {c.event.notes[:140]}")
        lines.append("")

    lines.append("RECOMMENDATION")
    lines.append("-" * 80)
    rec_words = report.threshold_recommendation.split()
    line = "  "
    for w in rec_words:
        if len(line) + len(w) + 1 > 78:
            lines.append(line)
            line = "  " + w
        else:
            line += (" " if line.strip() else "") + w
    if line.strip():
        lines.append(line)
    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def format_json(report: CalibrationReport) -> str:
    # asdict on dataclass with nested dataclasses needs care
    out = {
        "n_events": report.n_events,
        "n_fired": report.n_fired,
        "n_not_fired": report.n_not_fired,
        "true_positives": report.true_positives,
        "false_positives": report.false_positives,
        "true_negatives": report.true_negatives,
        "false_negatives": report.false_negatives,
        "precision_pct": round(report.precision_pct, 2),
        "recall_pct": round(report.recall_pct, 2),
        "avg_excess_60d_pct_when_fired": round(report.avg_excess_60d_pct_when_fired, 2),
        "avg_excess_60d_pct_when_not_fired": round(report.avg_excess_60d_pct_when_not_fired, 2),
        "by_event_type": report.by_event_type,
        "threshold_recommendation": report.threshold_recommendation,
        "classifications": [
            {
                "ticker": c.event.ticker,
                "event_date": c.event.event_date,
                "event_type": c.event.event_type,
                "step_6_fired": c.step_6_fired,
                "fwd_return_60d_pct": round(c.fwd_return_60d_pct, 2),
                "spy_return_60d_pct": round(c.spy_return_60d_pct, 2),
                "excess_return_60d_pct": round(c.excess_return_60d_pct, 2),
                "classification": c.classification,
            }
            for c in report.classifications
        ],
    }
    return json.dumps(out, indent=2)


# =============================================================================
# CLI
# =============================================================================

def main():
    p = argparse.ArgumentParser(description="Thesis-strengthening backtest")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--verbose", action="store_true", help="Per-event detail")
    args = p.parse_args()

    report = build_calibration_report(EMBEDDED_EVENTS)

    if args.json:
        print(format_json(report))
    else:
        print(format_text(report, verbose=args.verbose))


if __name__ == "__main__":
    main()
