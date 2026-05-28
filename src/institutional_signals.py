#!/usr/bin/env python3
"""
institutional_signals.py — UW 13F signal layer
Candidate G (v11.9) — Patches B/C/D/E/F unified

Patches:
  B — Quality active manager whitelist (case-insensitive, substring)
  C — Strategic anchor detection (is_strategic_anchor flag handling)
  D — Cohort initiation detection (2+ thematic peers same fund same quarter)
  E — Distribution warning (≥3 quality fund full closes same quarter)
  F — Index fund mechanical filter exclusion

Data flow:
  UW /institutions endpoint -> normalize -> InstitutionHolding instances
  -> apply quality/index/strategic flags -> aggregate by ticker
  -> build_ticker_report() -> Tier 1 surface for two-lens runs

The whitelists and theme groups are intentionally conservative. False positives
on quality_manager flag are worse than false negatives because the framework
weights quality_manager activity heavily.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

# ============================================================================
# Whitelists / blacklists
# ============================================================================

# Quality active managers. Substring match, case-insensitive.
# Sourced from operator framework: Baillie Gifford, T. Rowe Price, Capital Group,
# GMO, Fundsmith, and similar long-horizon active managers with thematic
# conviction.
QUALITY_MANAGER_PATTERNS = [
    "baillie gifford",
    "t. rowe price",
    "t rowe price",
    "capital group",
    "capital research",
    "gmo llc",
    "gmo, llc",
    "fundsmith",
    "fundsmith llp",
    "wellington management",
    "primecap management",
    "lone pine capital",
    "tiger global",
    "fundsmith equity",
]

# Index fund / passive vehicles. Detected by NAME patterns, not by AUM size
# (an actively-managed fund can be huge; that doesn't make it passive).
INDEX_FUND_PATTERNS = [
    " index ",
    "index fund",
    "total stock market",
    "total market",
    " 500 index",
    " s&p 500",
    "ftse all",
    "russell 1000",
    "russell 2000",
    "russell 3000",
    "etf trust",
    "spdr",
    "ishares core",
    "vanguard total",
    "vanguard 500",
    "vti",
    "voo",
    "vxus",
]

# Explicit blacklist — these are managers that should NEVER tag as quality
# even if a substring would accidentally match. Hedge funds, market makers,
# and pure-passive providers.
NEVER_QUALITY = [
    "citadel",
    "renaissance technologies",
    "two sigma",
    "millennium",
    "de shaw",
    "blackrock",
    "state street",
    "vanguard group",
    "vanguard total",
    "vanguard 500",
    "fidelity index",
    "fidelity 500",
    "schwab us broad",
]


def is_quality_manager(name: str) -> bool:
    """
    Returns True iff `name` substring-matches the quality whitelist and does
    NOT match the explicit never-quality list.
    """
    if not name:
        return False
    n = name.lower()
    for blocked in NEVER_QUALITY:
        if blocked in n:
            return False
    for pat in QUALITY_MANAGER_PATTERNS:
        if pat in n:
            return True
    return False


def is_index_fund(name: str) -> bool:
    """
    Returns True iff `name` matches a known index-fund pattern.
    """
    if not name:
        return False
    n_lower = name.lower()
    n_padded = " " + n_lower + " "  # word-boundary-ish matching
    for pat in INDEX_FUND_PATTERNS:
        if pat in n_padded:
            return True
    return False


# ============================================================================
# Theme groups
# ============================================================================

# Ticker -> list of themes. Multi-theme tickers are intentional (a name can
# belong to AI_HARDWARE AND SEMI simultaneously).
THEME_GROUPS = {
    "AI_HARDWARE": ["NVDA", "AVGO", "AMD", "MU", "SNDK", "ASML", "TSM", "AMAT", "LRCX", "KLAC"],
    "SEMI": ["NVDA", "AVGO", "AMD", "MU", "INTC", "TSM", "AMAT", "LRCX", "KLAC", "ASML", "MRVL"],
    "AI_PICKS_N_SHOVELS": ["NBIS", "CRWV", "ORCL", "DELL", "VRT", "ANET", "CLS"],
    "SOFTWARE": ["MSFT", "ORCL", "PLTR", "CRM", "NOW", "ADBE", "DDOG", "SNOW", "FTNT", "PANW", "CRWD"],
    "NUCLEAR": ["LEU", "UUUU", "CCJ", "BWXT", "OKLO", "SMR", "NRG"],
    "CRITICAL_MIN": ["MP", "USAR", "TMQ", "LAC", "LYSDY", "TLOFF"],
    "ETH_COMPLEX": ["BMNR", "ETHA", "COIN"],
    "BTC_COMPLEX": ["MSTR", "COIN"],
    "MAG7": ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "TSLA"],
    "FINANCIALS": ["GS", "JPM", "MS", "BAC", "WFC", "C"],
    "ELECTRIFICATION": ["VOLT", "GEV", "BE", "PWR", "NXT", "FIX", "AEP"],
    "DEFENSE": ["ITA", "BWXT", "LMT", "RTX", "NOC"],
}


def get_theme_for_ticker(ticker: str) -> Optional[str]:
    """Returns the first matching theme name for ticker (or None)."""
    if not ticker:
        return None
    t = ticker.upper()
    for theme, members in THEME_GROUPS.items():
        if t in members:
            return theme
    return None


def get_all_themes_for_ticker(ticker: str) -> list[str]:
    """Returns all matching theme names for ticker."""
    if not ticker:
        return []
    t = ticker.upper()
    return [theme for theme, members in THEME_GROUPS.items() if t in members]


# ============================================================================
# Data model
# ============================================================================

@dataclass
class InstitutionHolding:
    """One row from a UW /institutions response (normalized)."""
    institution_name: str
    institution_cik: Optional[str]
    ticker: str
    shares: int
    market_value_usd: float
    report_date: str  # YYYY-MM-DD
    activity: str  # 'open' | 'added' | 'reduced' | 'closed' | 'unchanged'
    is_strategic_anchor: bool = False  # operator-tagged (public_companies)
    is_quality_manager: bool = False  # auto-detected via is_quality_manager()
    is_index_fund: bool = False  # auto-detected via is_index_fund()
    units_change_pct: Optional[float] = None  # for reduced/added: % change

    def __post_init__(self):
        # Auto-populate flags from name if not explicitly set
        if not self.is_quality_manager and is_quality_manager(self.institution_name):
            self.is_quality_manager = True
        if not self.is_index_fund and is_index_fund(self.institution_name):
            self.is_index_fund = True


@dataclass
class CohortSignal:
    """Detected: one fund initiated 2+ thematic peers in same quarter."""
    fund_name: str
    theme: str
    tickers_initiated: list[str]
    report_date: str
    rationale: str = ""

    def __post_init__(self):
        if not self.rationale:
            self.rationale = (
                f"{self.fund_name} initiated {len(self.tickers_initiated)} names in "
                f"{self.theme} theme on {self.report_date} — thematic bet signal."
            )


@dataclass
class DistributionWarning:
    """Detected: ≥N quality funds fully closed a ticker in same quarter."""
    ticker: str
    quality_exits_count: int
    exiting_funds: list[str]
    report_date: str


@dataclass
class TickerReport:
    """Aggregated 13F view of one ticker."""
    ticker: str
    total_holders: int
    quality_holders: int
    index_holders: int
    strategic_anchors: list[tuple[str, str, int]]  # (fund, ticker, shares)
    cohort_signals: list[CohortSignal]
    distribution_warning: Optional[DistributionWarning]
    themes: list[str] = field(default_factory=list)


# ============================================================================
# Detection logic
# ============================================================================

def detect_strategic_anchors(
    holdings: list[InstitutionHolding],
) -> list[tuple[str, str, int]]:
    """
    PATCH C. Returns (institution_name, ticker, shares) for each holding
    flagged is_strategic_anchor=True.
    """
    return [
        (h.institution_name, h.ticker, h.shares)
        for h in holdings
        if h.is_strategic_anchor
    ]


def detect_cohort_initiations(
    initiations_by_fund: dict[str, list[tuple[str, str]]],
    min_cohort_size: int = 2,
) -> list[CohortSignal]:
    """
    PATCH D. Given {fund_name: [(ticker, report_date), ...]}, returns a
    CohortSignal for each (fund, theme) pair where the fund initiated
    >= min_cohort_size names in the same theme during the same quarter.

    Cross-theme and single-name initiations don't fire.
    """
    signals: list[CohortSignal] = []
    for fund_name, tick_dates in initiations_by_fund.items():
        # Group by (theme, report_date), counting member tickers
        by_theme_date: dict[tuple[str, str], list[str]] = {}
        for ticker, report_date in tick_dates:
            themes = get_all_themes_for_ticker(ticker)
            for theme in themes:
                by_theme_date.setdefault((theme, report_date), []).append(ticker)
        for (theme, report_date), tickers in by_theme_date.items():
            # Deduplicate (a ticker in multiple themes only counts once per
            # theme, but we may have re-added it; uniq here)
            uniq_tickers = sorted(set(tickers))
            if len(uniq_tickers) >= min_cohort_size:
                signals.append(CohortSignal(
                    fund_name=fund_name,
                    theme=theme,
                    tickers_initiated=uniq_tickers,
                    report_date=report_date,
                ))
    return signals


def detect_distribution_warning(
    ticker: str,
    holdings: list[InstitutionHolding],
    min_quality_exits: int = 3,
) -> Optional[DistributionWarning]:
    """
    PATCH E. Returns DistributionWarning if ≥min_quality_exits quality funds
    fully closed `ticker` in the holdings data. Reductions don't count;
    closure of non-quality funds doesn't count.
    """
    quality_closes = [
        h for h in holdings
        if h.ticker.upper() == ticker.upper()
        and h.activity == "closed"
        and h.is_quality_manager
    ]
    if len(quality_closes) < min_quality_exits:
        return None
    return DistributionWarning(
        ticker=ticker.upper(),
        quality_exits_count=len(quality_closes),
        exiting_funds=[h.institution_name for h in quality_closes],
        report_date=quality_closes[0].report_date if quality_closes else "",
    )


# ============================================================================
# Ticker report builder
# ============================================================================

def build_ticker_report(
    ticker: str,
    holdings: list[InstitutionHolding],
    initiations_by_fund_global: Optional[dict[str, list[tuple[str, str]]]] = None,
) -> TickerReport:
    """
    Build a complete ticker-level 13F summary from a list of holdings.

    Cohort signals are detected from the optional global initiations dict
    (because a cohort requires knowledge of ALL initiations by a fund, not
    just the ones touching `ticker`).
    """
    rel = [h for h in holdings if h.ticker.upper() == ticker.upper()]

    quality_count = sum(1 for h in rel if h.is_quality_manager)
    index_count = sum(1 for h in rel if h.is_index_fund)
    anchors = detect_strategic_anchors(rel)

    cohort_signals: list[CohortSignal] = []
    if initiations_by_fund_global:
        all_signals = detect_cohort_initiations(initiations_by_fund_global)
        cohort_signals = [
            s for s in all_signals
            if ticker.upper() in [t.upper() for t in s.tickers_initiated]
        ]

    dist_warning = detect_distribution_warning(ticker, holdings)

    return TickerReport(
        ticker=ticker.upper(),
        total_holders=len(rel),
        quality_holders=quality_count,
        index_holders=index_count,
        strategic_anchors=anchors,
        cohort_signals=cohort_signals,
        distribution_warning=dist_warning,
        themes=get_all_themes_for_ticker(ticker),
    )


# ============================================================================
# Formatters
# ============================================================================

def format_json(report: TickerReport) -> str:
    """Serialize to JSON (round-trippable)."""
    def _enc(o):
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        if isinstance(o, tuple):
            return list(o)
        return str(o)
    d = asdict(report)
    return json.dumps(d, indent=2, default=_enc)


def format_text(report: TickerReport) -> str:
    """Human-readable text report."""
    lines = [
        f"=== {report.ticker} institutional 13F summary ===",
        f"Total holders: {report.total_holders}",
        f"Quality active managers: {report.quality_holders}",
        f"Index-fund holders: {report.index_holders}",
    ]
    if report.themes:
        lines.append(f"Themes: {', '.join(report.themes)}")

    if report.strategic_anchors:
        lines.append("")
        lines.append("Strategic anchors:")
        for fund, t, sh in report.strategic_anchors:
            lines.append(f"  - {fund} -> {t}: {sh:,} sh")
    else:
        lines.append("Strategic anchors: none")

    if report.cohort_signals:
        lines.append("")
        lines.append("Cohort initiation signals:")
        for cs in report.cohort_signals:
            lines.append(f"  - {cs.fund_name} on {cs.theme}: {cs.tickers_initiated} ({cs.report_date})")

    if report.distribution_warning:
        dw = report.distribution_warning
        lines.append("")
        lines.append(f"⚠️  Distribution warning: {dw.quality_exits_count} quality funds")
        lines.append(f"   closed {dw.ticker} on {dw.report_date}:")
        for f in dw.exiting_funds:
            lines.append(f"  - {f}")

    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    print("institutional_signals.py — Candidate G (v11.9). Use via import.")
    print("For tests: python3 -m unittest test_institutional_signals  (or run directly)")
    sys.exit(0)
