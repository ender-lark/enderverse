#!/usr/bin/env python3
"""
Test suite for institutional_signals.py — Patches B/C/D/E/F unified.

Validates:
  PATCH B — Quality active manager whitelist matching (case-insensitive,
            substring), false positives on hedge funds and index funds
  PATCH C — Strategic anchor detection (is_strategic_anchor flag)
  PATCH D — Cohort initiation detection (single fund, 2+ thematic peers)
  PATCH E — Distribution warning (≥3 quality fund full closes)
  PATCH F — Index fund mechanical filter exclusion

Uses synthetic holding fixtures since UW data is live and varies. Real UW
integration is the operator's responsibility to wire in.
"""

import sys
sys.path.insert(0, '/home/claude/v11_9_update')

import institutional_signals as ins

print("=" * 80)
print("INSTITUTIONAL_SIGNALS TEST SUITE")
print("=" * 80)

passes = 0
fails = 0


def assert_eq(name, got, expected):
    global passes, fails
    if got == expected:
        passes += 1
        print(f"  PASS  {name}")
    else:
        fails += 1
        print(f"  FAIL  {name}")
        print(f"        expected: {expected!r}")
        print(f"        got:      {got!r}")


def assert_true(name, cond, hint=""):
    global passes, fails
    if cond:
        passes += 1
        print(f"  PASS  {name}")
    else:
        fails += 1
        print(f"  FAIL  {name}  {hint}")


# =============================================================================
# PATCH B — Quality manager whitelist
# =============================================================================
print("\n--- PATCH B: Quality manager whitelist ---")

assert_true("exact match", ins.is_quality_manager("Baillie Gifford"))
assert_true("case-insensitive lower", ins.is_quality_manager("baillie gifford"))
assert_true("case-insensitive upper", ins.is_quality_manager("BAILLIE GIFFORD & CO"))
assert_true("substring match", ins.is_quality_manager("Baillie Gifford Overseas Ltd"))
assert_true("T. Rowe Price Growth", ins.is_quality_manager("T. Rowe Price Associates"))
assert_true("Capital Group", ins.is_quality_manager("Capital Group Companies Inc"))
assert_true("GMO LLC", ins.is_quality_manager("GMO LLC Boston"))
assert_true("Fundsmith", ins.is_quality_manager("Fundsmith LLP"))

# Negative cases — common hedge funds and index funds must NOT match
assert_eq("Citadel not quality", ins.is_quality_manager("Citadel Advisors LLC"), False)
assert_eq("Renaissance not quality", ins.is_quality_manager("Renaissance Technologies LLC"), False)
assert_eq("Vanguard Total not quality",
          ins.is_quality_manager("Vanguard Total Stock Market"), False)
assert_eq("BlackRock not quality", ins.is_quality_manager("BlackRock Inc"), False)
assert_eq("State Street not quality", ins.is_quality_manager("State Street Corp"), False)

# =============================================================================
# PATCH F — Index fund mechanical filter
# =============================================================================
print("\n--- PATCH F: Index fund mechanical filter ---")

assert_true("Vanguard total market", ins.is_index_fund("Vanguard Total Stock Market ETF"))
assert_true("Vanguard 500 Index", ins.is_index_fund("Vanguard 500 Index Fund"))
assert_true("SPDR S&P 500", ins.is_index_fund("SPDR S&P 500 ETF Trust"))
assert_true("iShares Core S&P 500", ins.is_index_fund("iShares Core S&P 500 ETF"))

# Quality managers should NOT be flagged as index funds even though Vanguard
# also has actively managed funds — substring matching could collide.
# Verify Baillie Gifford does not collide.
assert_eq("Baillie Gifford not index",
          ins.is_index_fund("Baillie Gifford Overseas Ltd"), False)
assert_eq("Citadel not index",
          ins.is_index_fund("Citadel Advisors LLC"), False)

# =============================================================================
# PATCH C — Strategic anchor detection
# =============================================================================
print("\n--- PATCH C: Strategic anchor detection ---")

# Synthesize holdings including an NVIDIA-as-public-company holding of NBIS
strategic_holdings = [
    ins.InstitutionHolding(
        institution_name="NVIDIA Corp",
        institution_cik="0001045810",
        ticker="NBIS",
        shares=20_000_000,
        market_value_usd=2_000_000_000,
        report_date="2026-03-31",
        activity="open",
        is_strategic_anchor=True,  # public_companies tag fired
    ),
    ins.InstitutionHolding(
        institution_name="Vanguard Group Inc",
        institution_cik="0000102909",
        ticker="NBIS",
        shares=8_500_000,
        market_value_usd=850_000_000,
        report_date="2026-03-31",
        activity="added",
        is_strategic_anchor=False,
    ),
    ins.InstitutionHolding(
        institution_name="Baillie Gifford & Co",
        institution_cik="0001049408",
        ticker="NBIS",
        shares=3_000_000,
        market_value_usd=300_000_000,
        report_date="2026-03-31",
        activity="open",
        is_quality_manager=True,
    ),
]

anchors = ins.detect_strategic_anchors(strategic_holdings)
assert_eq("strategic anchor count", len(anchors), 1)
assert_eq("strategic anchor company", anchors[0][0], "NVIDIA Corp")
assert_eq("strategic anchor ticker", anchors[0][1], "NBIS")
assert_eq("strategic anchor shares", anchors[0][2], 20_000_000)

# Edge: no strategic anchors among holdings
no_anchor_holdings = [
    ins.InstitutionHolding(
        institution_name="Renaissance Technologies LLC",
        institution_cik="0001037389",
        ticker="GS",
        shares=500_000,
        market_value_usd=300_000_000,
        report_date="2026-03-31",
        activity="open",
        is_strategic_anchor=False,
    ),
]
anchors = ins.detect_strategic_anchors(no_anchor_holdings)
assert_eq("no strategic anchors", len(anchors), 0)

# =============================================================================
# PATCH D — Cohort initiation detection
# =============================================================================
print("\n--- PATCH D: Cohort initiation detection ---")

# Synthesize initiations: Baillie Gifford initiates NVDA, AVGO, AMD
# in same quarter — that's a cohort signal on AI_HARDWARE/SEMI theme.
initiations = {
    "Baillie Gifford & Co": [
        ("NVDA", "2026-03-31"),
        ("AVGO", "2026-03-31"),
        ("AMD", "2026-03-31"),
    ],
    # Single-name initiation, should NOT fire
    "T. Rowe Price Associates": [
        ("NBIS", "2026-03-31"),
    ],
    # Cross-theme initiations (no 2+ in single theme), should NOT fire
    "Capital Group": [
        ("LEU", "2026-03-31"),     # nuclear
        ("GS", "2026-03-31"),      # financials
        ("XLF", "2026-03-31"),     # ETF, not in theme groups
    ],
}

cohort_signals = ins.detect_cohort_initiations(initiations)

# Baillie Gifford should fire on at least one theme (AI_HARDWARE has NVDA/AVGO/AMD)
bg_signals = [s for s in cohort_signals if s.fund_name == "Baillie Gifford & Co"]
assert_true("Baillie Gifford fires", len(bg_signals) >= 1,
            f"got {len(bg_signals)}")

if bg_signals:
    # Verify the theme captured has multiple tickers
    bg_sig = bg_signals[0]
    assert_true("cohort has 2+ tickers", len(bg_sig.tickers_initiated) >= 2,
                f"got {len(bg_sig.tickers_initiated)}: {bg_sig.tickers_initiated}")
    assert_true("rationale mentions thematic",
                "thematic bet" in bg_sig.rationale.lower())

# T. Rowe should NOT fire (single name)
tr_signals = [s for s in cohort_signals if s.fund_name == "T. Rowe Price Associates"]
assert_eq("T. Rowe single-name no fire", len(tr_signals), 0)

# Capital Group should NOT fire (no 2+ in single theme)
cg_signals = [s for s in cohort_signals if s.fund_name == "Capital Group"]
assert_eq("Capital Group cross-theme no fire", len(cg_signals), 0)

# Threshold variation: min_cohort_size=3 should require 3+
strict_signals = ins.detect_cohort_initiations(initiations, min_cohort_size=3)
bg_strict = [s for s in strict_signals if s.fund_name == "Baillie Gifford & Co"]
# Baillie Gifford initiated NVDA + AVGO + AMD — all in AI_HARDWARE; should fire
# at threshold 3
assert_true("Baillie Gifford fires at strict threshold 3",
            len(bg_strict) >= 1, f"got {len(bg_strict)}")

# =============================================================================
# PATCH E — Distribution warning
# =============================================================================
print("\n--- PATCH E: Distribution warning ---")

# Synthesize: 4 quality managers close NVDA in same quarter
distribution_holdings = [
    ins.InstitutionHolding(
        institution_name="Baillie Gifford & Co",
        institution_cik="0001049408", ticker="NVDA", shares=0,
        market_value_usd=0, report_date="2026-03-31",
        activity="closed", is_quality_manager=True,
    ),
    ins.InstitutionHolding(
        institution_name="T. Rowe Price Associates",
        institution_cik="0000080255", ticker="NVDA", shares=0,
        market_value_usd=0, report_date="2026-03-31",
        activity="closed", is_quality_manager=True,
    ),
    ins.InstitutionHolding(
        institution_name="Capital Group Companies",
        institution_cik="0000813828", ticker="NVDA", shares=0,
        market_value_usd=0, report_date="2026-03-31",
        activity="closed", is_quality_manager=True,
    ),
    ins.InstitutionHolding(
        institution_name="GMO LLC",
        institution_cik="0000814375", ticker="NVDA", shares=0,
        market_value_usd=0, report_date="2026-03-31",
        activity="closed", is_quality_manager=True,
    ),
    # Reductions should NOT count
    ins.InstitutionHolding(
        institution_name="Fundsmith LLP",
        institution_cik="0001572083", ticker="NVDA", shares=100_000,
        market_value_usd=50_000_000, report_date="2026-03-31",
        activity="reduced", is_quality_manager=True,
        units_change_pct=-50.0,
    ),
]

warning = ins.detect_distribution_warning("NVDA", distribution_holdings,
                                           min_quality_exits=3)
assert_true("warning fires on 4 closes", warning is not None)
if warning:
    assert_eq("warning ticker", warning.ticker, "NVDA")
    assert_eq("warning exit count", warning.quality_exits_count, 4)
    assert_eq("exiting funds count", len(warning.exiting_funds), 4)

# Below threshold: 2 closes shouldn't fire (default min=3)
below_threshold = distribution_holdings[:2]
warning = ins.detect_distribution_warning("NVDA", below_threshold,
                                           min_quality_exits=3)
assert_true("no warning at 2 closes (below threshold)", warning is None)

# Reductions only — even many — should NOT fire
reductions_only = [
    ins.InstitutionHolding(
        institution_name=f"Fund {i}", institution_cik=None, ticker="NVDA",
        shares=100_000, market_value_usd=50_000_000,
        report_date="2026-03-31", activity="reduced",
        is_quality_manager=True, units_change_pct=-50.0,
    )
    for i in range(5)
]
warning = ins.detect_distribution_warning("NVDA", reductions_only,
                                           min_quality_exits=3)
assert_true("no warning on reductions only", warning is None)

# Non-quality closes should NOT count (Patch E is quality-fund-specific)
non_quality_closes = [
    ins.InstitutionHolding(
        institution_name="Renaissance Technologies LLC",
        institution_cik="0001037389", ticker="NVDA", shares=0,
        market_value_usd=0, report_date="2026-03-31",
        activity="closed", is_quality_manager=False,
    )
    for _ in range(5)
]
warning = ins.detect_distribution_warning("NVDA", non_quality_closes,
                                           min_quality_exits=3)
assert_true("no warning on non-quality closes", warning is None)

# =============================================================================
# Theme group resolution
# =============================================================================
print("\n--- Theme group resolution ---")

# Known tickers should resolve to themes
nvda_theme = ins.get_theme_for_ticker("NVDA")
assert_true("NVDA has theme", nvda_theme is not None,
            f"got {nvda_theme}")

# Multi-theme ticker support
nvda_themes = ins.get_all_themes_for_ticker("NVDA")
assert_true("NVDA in at least 1 theme", len(nvda_themes) >= 1)

# Unknown ticker should return None / empty
unknown = ins.get_theme_for_ticker("XYZNEVERHEARDOFTHIS")
assert_eq("unknown ticker no theme", unknown, None)
unknown_all = ins.get_all_themes_for_ticker("XYZNEVERHEARDOFTHIS")
assert_eq("unknown ticker no themes list", unknown_all, [])

# =============================================================================
# Build ticker report integration
# =============================================================================
print("\n--- Build ticker report integration ---")

# Run the full pipeline on synthetic NBIS holdings
all_nbis_holdings = strategic_holdings  # from Patch C section
nbis_initiations = {
    "NVIDIA Corp": [("NBIS", "2026-03-31")],
    "Baillie Gifford & Co": [("NBIS", "2026-03-31")],
}
report = ins.build_ticker_report(
    ticker="NBIS",
    holdings=all_nbis_holdings,
    initiations_by_fund_global=nbis_initiations,
)
assert_eq("report ticker", report.ticker, "NBIS")
assert_eq("report total holders", report.total_holders, 3)
assert_eq("report quality holders count", report.quality_holders, 1)
assert_eq("report strategic anchors count", len(report.strategic_anchors), 1)

# JSON round-trip
js = ins.format_json(report)
import json
parsed = json.loads(js)
assert_eq("json round-trip ticker", parsed["ticker"], "NBIS")

# Text formatter
txt = ins.format_text(report)
assert_true("text contains ticker", "NBIS" in txt)
assert_true("text contains strategic anchor section",
            "strategic" in txt.lower() or "anchor" in txt.lower())

# =============================================================================
# RESULTS
# =============================================================================
print("\n" + "=" * 80)
print(f"RESULT: {passes}/{passes + fails} tests passed")
print("=" * 80)

if fails > 0:
    sys.exit(1)
