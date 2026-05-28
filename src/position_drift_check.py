"""
position_drift_check.py
========================
v11.16 Patch 3 Position-Size Verification vs Memory Baseline.

Operationalizes the v11.16 Patch 3 framework: on every session-open / continuation-
autopilot turn, cross-reference position-size baselines stated in operator memory
against actual Live Theses Position % values and Latest Portfolio computed %s.
Any drift >10% from memory baseline triggers pre-flight surface.

Would have caught BMNR memory 5% baseline vs actual 3.87% portfolio (-23% drift)
automatically on 5/14/26 without operator-side surfacing.

Architecture:
- Pure-logic core (parse_memory_baselines, compute_drift, classify_drift) is testable
  without API access. Tests in test_position_drift_check.py.
- CLI wrapper at __main__ takes memory text + Latest Portfolio JSON and outputs
  drift table.

CLI usage:
  python position_drift_check.py --memory memory.txt --portfolio latest_portfolio.json
  python position_drift_check.py --memory memory.txt --portfolio latest_portfolio.json \
      --threshold 0.10
  python position_drift_check.py --memory memory.txt --portfolio latest_portfolio.json \
      --total-wealth 1879245

Author: Investing 2026 framework v11.16
Date: 2026-05-14
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DRIFT_THRESHOLD = 0.10        # 10% relative drift flag
ALARM_DRIFT_THRESHOLD = 0.25          # 25% drift = additional flag

# Memory-baseline patterns (heuristic — extracts explicit numeric/tier claims)
# Examples matched:
#   "BMNR T2 at 5% baseline"
#   "LEU is 5.1% position"
#   "BMNR T1 generational ~10%"
#   "NVDA 7.4% portfolio"
PCT_PATTERN = re.compile(
    r"\b([A-Z]{1,6})\b"                      # ticker (uppercase, 1-6 chars)
    r"(?:[^.\n]*?)"                          # any non-newline non-period chars
    r"(?:at\s+|=\s+|is\s+|baseline\s+|target\s+)?"
    r"(\d+(?:\.\d+)?)\s*%",                  # the percentage value
    re.IGNORECASE
)

# Tier patterns map T1/T2/T3 → typical sizing midpoints per memory framework
# T1 Generational 8-12% → 10%
# T2 High-conviction 4-7% → 5.5%
# T3 Tactical 1.5-3% → 2.25%
# T4 Speculative <1% → 0.5%
TIER_MIDPOINTS = {
    "T1": 0.10,
    "T2": 0.055,
    "T3": 0.0225,
    "T4": 0.005,
    "Generational": 0.10,
    "GENERATIONAL": 0.10,
}
TIER_PATTERN = re.compile(
    r"\b([A-Z]{1,6})\b"
    r"(?:[^.\n]*?)\b"
    r"(T[1-4]|Generational)\b"
)

# Common false-positive tickers to filter (acronyms that look like tickers)
FALSE_POSITIVE_TICKERS = {
    "CI", "AI", "BUY", "SELL", "USD", "ETF", "ATH", "USA", "FOMC",
    "GDP", "EPS", "PE", "ETH", "BTC", "USDC", "GBP", "EUR", "DOE",
    "FDA", "FCC", "SEC", "EOD", "AH", "PM", "AM", "BE", "API", "MCP",
    "ARC", "RSU", "ROI", "MS", "JPM", "RBC",  # ambiguous — could be real tickers; allow them through
    "AND", "OR", "FOR", "AT", "BY", "TO", "ON", "IN", "OF", "IS",
    "P", "S", "T", "Q", "M", "C", "K",
    "HALEU", "CLARITY", "JANUS", "MERIDIAN",
    "NEW", "LIVE", "FRESH", "DEFI",
    "BLOCKED", "ROLL", "OW", "EW", "SP",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MemoryBaseline:
    """A memory-stated position-size baseline."""
    ticker: str
    baseline_pct: float                # e.g. 0.05 for 5%
    source_text: str                   # the original phrase
    inferred_from_tier: bool = False   # True if extracted from T1/T2/T3 vs explicit %


@dataclass
class ActualPosition:
    """A position's actual sizing from Latest Portfolio."""
    ticker: str
    market_value: float
    pct_of_portfolio: float            # e.g. 0.0387 for 3.87%


@dataclass
class DriftResult:
    """Drift computation result for one ticker."""
    ticker: str
    memory_baseline_pct: float
    actual_pct: float
    drift_relative: float              # (actual - memory) / memory, signed
    drift_absolute_pct: float          # actual - memory (pp)
    direction: str                     # 'UNDERSIZED' or 'OVERSIZED' or 'IN_BAND'
    flags: list[str] = field(default_factory=list)
    inferred_from_tier: bool = False

    @property
    def is_flagged(self) -> bool:
        return self.direction != "IN_BAND"


# ---------------------------------------------------------------------------
# Pure-logic core
# ---------------------------------------------------------------------------

def parse_memory_baselines(memory_text: str) -> list[MemoryBaseline]:
    """Extract explicit percentage baselines from memory text.

    Returns list of (ticker, pct, source) entries. Filters false-positive tickers.
    """
    out = []
    seen = set()

    # First pass: explicit percentages
    for m in PCT_PATTERN.finditer(memory_text):
        ticker = m.group(1).upper()
        if ticker in FALSE_POSITIVE_TICKERS:
            continue
        try:
            pct = float(m.group(2)) / 100.0
        except ValueError:
            continue
        if pct <= 0 or pct > 1:
            continue  # implausible baseline
        # Context capture: 50 chars before + the match
        start = max(0, m.start() - 50)
        end = min(len(memory_text), m.end() + 20)
        source = memory_text[start:end].replace("\n", " ").strip()
        key = (ticker, round(pct, 4))
        if key in seen:
            continue
        seen.add(key)
        out.append(MemoryBaseline(
            ticker=ticker,
            baseline_pct=pct,
            source_text=source,
            inferred_from_tier=False,
        ))

    # Second pass: tier-only mentions (T1/T2/T3 without explicit %)
    for m in TIER_PATTERN.finditer(memory_text):
        ticker = m.group(1).upper()
        if ticker in FALSE_POSITIVE_TICKERS:
            continue
        tier = m.group(2)
        # Skip if we already have an explicit % for this ticker
        if any(b.ticker == ticker and not b.inferred_from_tier for b in out):
            continue
        midpoint = TIER_MIDPOINTS.get(tier)
        if midpoint is None:
            continue
        start = max(0, m.start() - 50)
        end = min(len(memory_text), m.end() + 20)
        source = memory_text[start:end].replace("\n", " ").strip()
        key = (ticker, round(midpoint, 4))
        if key in seen:
            continue
        seen.add(key)
        out.append(MemoryBaseline(
            ticker=ticker,
            baseline_pct=midpoint,
            source_text=source,
            inferred_from_tier=True,
        ))

    return out


def load_actuals_from_portfolio(
    portfolio_json: dict,
    total_wealth: Optional[float] = None,
) -> list[ActualPosition]:
    """Aggregate Latest Portfolio JSON into per-ticker actual sizing.

    Sums across accounts (operator pattern: same ticker can appear in multiple accounts).
    If total_wealth not provided, computes from portfolio.
    """
    by_ticker = {}
    accounts = portfolio_json.get("accounts", [])
    all_positions = []
    for acct in accounts:
        all_positions.extend(acct.get("positions", []))
    all_positions.extend(portfolio_json.get("positions", []))

    if total_wealth is None:
        # Sum market values to infer total wealth
        total_wealth = sum(
            (p.get("current_value") or p.get("market_value") or 0)
            for p in all_positions
        )
        # Plus cash if present
        for acct in accounts:
            cash = acct.get("cash") or acct.get("cash_balance") or 0
            total_wealth += cash
    if total_wealth <= 0:
        return []

    for p in all_positions:
        ticker = (p.get("symbol") or p.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        mv = p.get("current_value") or p.get("market_value") or 0
        if mv <= 0:
            continue
        by_ticker[ticker] = by_ticker.get(ticker, 0) + mv

    return [
        ActualPosition(
            ticker=t,
            market_value=mv,
            pct_of_portfolio=mv / total_wealth,
        )
        for t, mv in by_ticker.items()
    ]


def compute_drift(
    baseline: MemoryBaseline,
    actual: ActualPosition,
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
    alarm_threshold: float = ALARM_DRIFT_THRESHOLD,
) -> DriftResult:
    """Compute drift result for a single (baseline, actual) pair."""
    if baseline.baseline_pct == 0:
        drift_rel = 0.0
    else:
        drift_rel = (actual.pct_of_portfolio - baseline.baseline_pct) / baseline.baseline_pct
    drift_abs = actual.pct_of_portfolio - baseline.baseline_pct

    flags = []
    if abs(drift_rel) <= threshold:
        direction = "IN_BAND"
    elif drift_rel < 0:
        direction = "UNDERSIZED"
        flags.append("P_UNDERSIZE_CANDIDATE")
    else:
        direction = "OVERSIZED"
        flags.append("CONCENTRATION_CHECK")

    if abs(drift_rel) >= alarm_threshold:
        flags.append("ALARM_DRIFT")

    if baseline.inferred_from_tier:
        flags.append("BASELINE_FROM_TIER_INFERENCE")

    return DriftResult(
        ticker=baseline.ticker,
        memory_baseline_pct=baseline.baseline_pct,
        actual_pct=actual.pct_of_portfolio,
        drift_relative=drift_rel,
        drift_absolute_pct=drift_abs,
        direction=direction,
        flags=flags,
        inferred_from_tier=baseline.inferred_from_tier,
    )


def cross_reference(
    baselines: list[MemoryBaseline],
    actuals: list[ActualPosition],
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
    alarm_threshold: float = ALARM_DRIFT_THRESHOLD,
) -> tuple[list[DriftResult], list[MemoryBaseline], list[ActualPosition]]:
    """Cross-reference baselines vs actuals.

    Returns:
      - drift_results: per-ticker drift outcomes (matched)
      - unmatched_baselines: memory said to have but not in portfolio (P-UNDERSIZE-EXTREME)
      - unmatched_actuals: in portfolio but no memory baseline (could be intentional)
    """
    actual_by_ticker = {a.ticker: a for a in actuals}
    baseline_by_ticker = {b.ticker: b for b in baselines}

    drift_results = []
    for b in baselines:
        a = actual_by_ticker.get(b.ticker)
        if a is None:
            continue  # handled in unmatched_baselines below
        drift_results.append(compute_drift(b, a, threshold, alarm_threshold))

    unmatched_baselines = [b for b in baselines if b.ticker not in actual_by_ticker]
    unmatched_actuals = [a for a in actuals if a.ticker not in baseline_by_ticker]

    return drift_results, unmatched_baselines, unmatched_actuals


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_markdown(
    drift_results: list[DriftResult],
    unmatched_baselines: list[MemoryBaseline],
    unmatched_actuals: list[ActualPosition],
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> str:
    lines = []
    lines.append("# 📐 Position-Size Drift Check")
    flagged = [d for d in drift_results if d.is_flagged]
    alarm = [d for d in drift_results if "ALARM_DRIFT" in d.flags]
    undersized = [d for d in drift_results if d.direction == "UNDERSIZED"]
    oversized = [d for d in drift_results if d.direction == "OVERSIZED"]

    lines.append(
        f"\nChecked: {len(drift_results)} memory-baseline / actual pairs · "
        f"Flagged: {len(flagged)} · ALARM (>25% drift): {len(alarm)}"
    )
    lines.append(
        f"Undersized: {len(undersized)} · Oversized: {len(oversized)} · "
        f"Unmatched baselines (memory had, portfolio doesn't): {len(unmatched_baselines)}"
    )

    if alarm:
        lines.append("\n## 🚨 ALARM DRIFT (>25%)\n")
        for d in sorted(alarm, key=lambda x: -abs(x.drift_relative)):
            lines.append(_render_drift(d))

    if undersized:
        lines.append("\n## 📉 UNDERSIZED — P-UNDERSIZE candidate\n")
        for d in sorted(undersized, key=lambda x: x.drift_relative):
            if "ALARM_DRIFT" not in d.flags:
                lines.append(_render_drift(d))

    if oversized:
        lines.append("\n## 📈 OVERSIZED — concentration check\n")
        for d in sorted(oversized, key=lambda x: -x.drift_relative):
            if "ALARM_DRIFT" not in d.flags:
                lines.append(_render_drift(d))

    if unmatched_baselines:
        lines.append("\n## ⚠️ Unmatched baselines (memory mentioned, not in portfolio)\n")
        for b in unmatched_baselines:
            tier_tag = " [tier-inferred]" if b.inferred_from_tier else ""
            lines.append(
                f"- **{b.ticker}** memory baseline {b.baseline_pct*100:.1f}%{tier_tag} "
                f"— position not found in portfolio (sold? wrong ticker?)"
            )

    if not flagged and not unmatched_baselines:
        lines.append(f"\n✅ All memory baselines within ±{threshold*100:.0f}% of actual.\n")

    return "\n".join(lines)


def _render_drift(d: DriftResult) -> str:
    direction_emoji = {"UNDERSIZED": "📉", "OVERSIZED": "📈", "IN_BAND": "✅"}[d.direction]
    tier_tag = " [tier-inferred]" if d.inferred_from_tier else ""
    return (
        f"- {direction_emoji} **{d.ticker}** memory {d.memory_baseline_pct*100:.2f}% "
        f"/ actual {d.actual_pct*100:.2f}% / drift {d.drift_relative*100:+.1f}% "
        f"({d.drift_absolute_pct*100:+.2f}pp){tier_tag}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="v11.16 Patch 3 Position-Size Verification vs Memory Baseline"
    )
    parser.add_argument(
        "--memory",
        required=True,
        help="Path to memory text file (operator memory dump)"
    )
    parser.add_argument(
        "--portfolio",
        required=True,
        help="Path to Latest Portfolio JSON"
    )
    parser.add_argument(
        "--total-wealth",
        type=float,
        default=None,
        help="Total portfolio wealth (if known; else auto-computed from portfolio)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_DRIFT_THRESHOLD,
        help="Relative drift threshold for flagging (default 0.10 = 10%)"
    )
    parser.add_argument(
        "--alarm-threshold",
        type=float,
        default=ALARM_DRIFT_THRESHOLD,
        help="Alarm-level drift threshold (default 0.25 = 25%)"
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown"
    )
    args = parser.parse_args()

    with open(args.memory) as f:
        memory_text = f.read()
    with open(args.portfolio) as f:
        portfolio = json.load(f)

    baselines = parse_memory_baselines(memory_text)
    actuals = load_actuals_from_portfolio(portfolio, args.total_wealth)
    drift, unmatched_b, unmatched_a = cross_reference(
        baselines, actuals, args.threshold, args.alarm_threshold
    )

    if args.format == "json":
        out = {
            "drift_results": [asdict(d) for d in drift],
            "unmatched_baselines": [asdict(b) for b in unmatched_b],
            "unmatched_actuals": [asdict(a) for a in unmatched_a],
        }
        print(json.dumps(out, indent=2))
    else:
        print(render_markdown(drift, unmatched_b, unmatched_a, args.threshold))


if __name__ == "__main__":
    main()
