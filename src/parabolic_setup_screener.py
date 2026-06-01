#!/usr/bin/env python3
"""
parabolic_setup_screener.py — VIAV-pattern Phase 1 candidate screener (v11.10.1)

Codifies the 8-feature VIAV/LEU template into a runnable screener so we catch
the next 5x-in-12-months setup at Phase 1 ($13 VIAV in Oct 2025) instead of
Phase 3 ($52 VIAV in May 2026).

The 8 features and weights (max 13.0):

  Auto-computed from UW data:
  1. Revenue growth accel  (3Q sequential acceleration, >5pp per Q)  wt 2.0
  2. EPS surprise streak   (≥3 consecutive Q with surprise % >10%)    wt 2.0
  3. Operating margin exp  (op margin expanded ≥150bps YoY)            wt 1.5
  4. Forward PE vs growth  (PEG-like: fwd PE / 3Y rev CAGR <2.0)       wt 1.0
  5. Long pre-recog base   (price stayed <$25 for >24 of last 36 mo)   wt 1.5

  Manual-seeded (per ticker in CANDIDATE_PROFILES):
  6. Industry concentration (top 2-3 players >60% combined share)     wt 2.0
  7. Multi-node upgrade cadence (mandatory generational refresh)       wt 1.5
  8. Customer concentration (top 10 customers >50% rev, inelastic)     wt 1.5

  Two-Lens auto-fire threshold: score >= 9.0
  Watchlist threshold: 6.0 <= score < 9.0
  Skip: score < 6.0

Phase classification (separate from score):
  Phase 0  Boredom        24+ months sideways base, low PE, no analyst love
  Phase 1  Inflection     2-3 beats >10%, rev accel, +30-60% from base, OPTIMAL
  Phase 2  Recognition    PTs chasing, multiple expanding, +100-200%
  Phase 3  Parabola       Daily PT raises, IV>80%, CLUSTER INSIDER SELLING
  Phase 4  Distribution   Sideways-down on good news, multiple compresses

Per v11.10 framework: Phase 1 = entry. Phase 2 = last clean entry. Phase 3 =
skip (this is where VIAV is now). Score is independent of phase — a name can
be high-score AND in Phase 3, which means "thesis confirmed, you missed it."

Env vars:
  UW_API_KEY  Required. Unusual Whales bearer token.

Usage:
  python parabolic_setup_screener.py                    # screen default candidates
  python parabolic_setup_screener.py --tickers AAPL,MSFT,NVDA
  python parabolic_setup_screener.py --json             # JSON output
  python parabolic_setup_screener.py --verbose          # show per-feature
  python parabolic_setup_screener.py --min-score 6.0    # lower surface threshold

Exit codes:
  0  clean run
  1  config / API key error
  2  one or more tickers failed (other tickers still scored)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

UW_API_BASE = "https://api.unusualwhales.com/api"
ENDPOINT_EARNINGS_HISTORY = "/earnings/{ticker}"
ENDPOINT_CLOSE_PRICES = "/stock/{ticker}/ohlc/1d"
ENDPOINT_INCOME_STATEMENTS = "/stock/{ticker}/income-statements"
ENDPOINT_COMPANY_INFO = "/stock/{ticker}/info"
ENDPOINT_ANALYST_RATINGS = "/stock/{ticker}/analyst-ratings"

# Surface thresholds
THRESHOLD_AUTOFIRE = 9.0       # >= 9 → Two-Lens auto-fire candidate
THRESHOLD_WATCHLIST = 6.0      # 6.0–8.99 → watchlist
MAX_POSSIBLE = 13.0

# Feature weights (sum = 13.0)
W_REV_ACCEL = 2.0
W_EPS_STREAK = 2.0
W_OPMARGIN_EXP = 1.5
W_FWDPE_VS_GROWTH = 1.0
W_PRICE_BASE = 1.5
W_INDUSTRY_CONC = 2.0
W_MULTI_NODE = 1.5
W_CUSTOMER_CONC = 1.5

# ============================================================================
# CANDIDATE PROFILES — manual seed for features 6/7/8
# ============================================================================
# Features 6, 7, 8 cannot be reliably auto-computed from public APIs. They
# require sector knowledge. Each ticker that we want screened lives here with
# a 0/0.5/1.0 score per feature.
#
# Score convention:
#   1.0 = clean fire (e.g., true duopoly with >70% combined share)
#   0.5 = partial fire (e.g., top 3 with ~55% share, or duopoly w/ rising 3rd)
#   0.0 = no fire (fragmented industry, no node cadence, diffuse customers)
#
# When adding a ticker, justify each non-zero score in the comment.

CANDIDATE_PROFILES: dict[str, dict[str, Any]] = {
    # === Test/measurement & semi equipment (closest VIAV pattern) ===
    "VIAV": {
        "industry_conc": 1.0,   # duopoly w/ KEYS, ~40-45% share post-Spirent
        "multi_node":    1.0,   # 400G→800G→1.6T→3.2T mandatory refresh
        "customer_conc": 1.0,   # hyperscalers + NEMs concentrated, inelastic
        "thesis_tag":    "ai_dc_test",
    },
    "KEYS": {
        "industry_conc": 1.0,   # other side of VIAV duopoly
        "multi_node":    1.0,   # same 800G/1.6T cycle + 5G→6G + auto/EV
        "customer_conc": 0.5,   # broader customer base than VIAV; less concentrated
        "thesis_tag":    "ai_dc_test",
    },
    "ONTO": {
        "industry_conc": 0.5,   # top 3 metrology w/ KLAC, AMAT; ~55% combined
        "multi_node":    1.0,   # advanced packaging (HBM/CoWoS) node cadence
        "customer_conc": 1.0,   # TSMC/SK/Micron concentrated
        "thesis_tag":    "semi_metrology",
    },
    "CAMT": {
        "industry_conc": 0.5,   # advanced packaging inspection; semi-niche
        "multi_node":    1.0,   # HBM3→HBM3E→HBM4 + CoWoS variants
        "customer_conc": 1.0,   # SK Hynix, TSMC, Micron heavy concentration
        "thesis_tag":    "semi_metrology",
    },
    "FORM": {
        "industry_conc": 1.0,   # probe card duopoly w/ MJC (private/JP)
        "multi_node":    1.0,   # every NVDA wafer needs probe cards per node
        "customer_conc": 1.0,   # TSMC + foundry concentration
        "thesis_tag":    "semi_test",
    },
    "AEHR": {
        "industry_conc": 0.5,   # SiC burn-in niche; small total addressable mkt
        "multi_node":    0.5,   # SiC ramp tied to EV adoption, not strict nodes
        "customer_conc": 1.0,   # Onsemi was 70%+; diversifying slowly
        "thesis_tag":    "sic_test",
    },

    # === Optical components (JDSU's other split) ===
    "LITE": {
        "industry_conc": 0.5,   # top 3 optical w/ COHR, FN; fragmenting
        "multi_node":    1.0,   # same 800G/1.6T optical transceiver cycle
        "customer_conc": 1.0,   # GOOGL/META/MSFT hyperscaler concentration
        "thesis_tag":    "ai_optical",
    },
    "COHR": {
        "industry_conc": 0.5,   # broader optics conglomerate; less concentrated
        "multi_node":    1.0,   # 800G/1.6T + laser markets
        "customer_conc": 0.5,   # more diversified than LITE
        "thesis_tag":    "ai_optical",
    },

    # === Specialized defense / sovereign ===
    "AVAV": {
        "industry_conc": 1.0,   # AVAV + Anduril (private) duopoly in tactical drones
        "multi_node":    0.5,   # multi-year procurement, not strict nodes
        "customer_conc": 1.0,   # DoD concentration ~70%+
        "thesis_tag":    "defense_autonomy",
    },
    "KTOS": {
        "industry_conc": 0.5,   # crowded autonomous defense field
        "multi_node":    0.5,   # program of record cycles
        "customer_conc": 1.0,   # DoD + sovereign concentration
        "thesis_tag":    "defense_autonomy",
    },
    "MP": {
        "industry_conc": 1.0,   # only US-based vertically integrated rare earth
        "multi_node":    0.5,   # one-time reshoring, not recurring nodes
        "customer_conc": 1.0,   # DoD multi-year offtake contracts
        "thesis_tag":    "critical_minerals",
    },

    # === Nuclear fuel cycle ===
    "LEU": {
        "industry_conc": 1.0,   # HALEU monopoly via DOE Janus
        "multi_node":    0.5,   # reactor restart + SMR ramp, not strict nodes
        "customer_conc": 1.0,   # US govt + utilities concentrated
        "thesis_tag":    "nuclear_fuel",
    },
    "BWXT": {
        "industry_conc": 1.0,   # Navy nuclear fuel monopoly + SMR exposure
        "multi_node":    0.5,   # Columbia-class + Virginia-class cycles
        "customer_conc": 1.0,   # USN + DoE concentrated
        "thesis_tag":    "nuclear_fuel",
    },

    # === Hyperscaler-adjacent ===
    "VRT": {
        "industry_conc": 0.5,   # top 3 data center power/cooling
        "multi_node":    0.5,   # liquid cooling transition is real but lumpy
        "customer_conc": 1.0,   # hyperscaler concentration high
        "thesis_tag":    "dc_infra",
    },
    "PWR": {
        "industry_conc": 0.5,   # fragmented EPC market
        "multi_node":    0.0,   # not a node-driven business
        "customer_conc": 0.5,   # mixed util + dc customer base
        "thesis_tag":    "dc_infra",
    },
    "CLS": {
        "industry_conc": 0.5,   # EMS market competitive (FLEX, JBL, BHE)
        "multi_node":    0.5,   # tied to hyperscaler refresh cycles
        "customer_conc": 1.0,   # top customer ~30%+ of revenue
        "thesis_tag":    "dc_infra",
    },
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class FeatureScores:
    revenue_accel: float = 0.0
    eps_streak: float = 0.0
    opmargin_exp: float = 0.0
    fwdpe_vs_growth: float = 0.0
    price_base: float = 0.0
    industry_conc: float = 0.0
    multi_node: float = 0.0
    customer_conc: float = 0.0

    @property
    def weighted_total(self) -> float:
        return (
            self.revenue_accel * W_REV_ACCEL
            + self.eps_streak * W_EPS_STREAK
            + self.opmargin_exp * W_OPMARGIN_EXP
            + self.fwdpe_vs_growth * W_FWDPE_VS_GROWTH
            + self.price_base * W_PRICE_BASE
            + self.industry_conc * W_INDUSTRY_CONC
            + self.multi_node * W_MULTI_NODE
            + self.customer_conc * W_CUSTOMER_CONC
        )


@dataclass
class ScreenResult:
    ticker: str
    score: float
    surface_tier: str           # "AUTOFIRE" | "WATCHLIST" | "SKIP"
    phase: str                  # "Phase 0" .. "Phase 4" | "Unknown"
    features: FeatureScores
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["features"] = asdict(self.features)
        d["weighted_total"] = self.features.weighted_total
        return d


# ============================================================================
# UW API CLIENT
# ============================================================================

class UWClient:
    def __init__(self, api_key: str, verbose: bool = False):
        self.api_key = api_key
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = UW_API_BASE + path
        if self.verbose:
            print(f"  GET {url}  params={params}", file=sys.stderr)
        r = self.session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def earnings_history(self, ticker: str) -> list[dict]:
        path = ENDPOINT_EARNINGS_HISTORY.format(ticker=ticker)
        data = self._get(path)
        return data.get("data", data) if isinstance(data, dict) else data

    def close_prices(self, ticker: str, days_back: int = 1100) -> list[dict]:
        """Daily OHLC. We ask for ~3Y (1100 trading days) to assess the base."""
        path = ENDPOINT_CLOSE_PRICES.format(ticker=ticker)
        data = self._get(path, params={"limit": days_back})
        return data.get("data", data) if isinstance(data, dict) else data

    def income_statements(self, ticker: str) -> list[dict]:
        path = ENDPOINT_INCOME_STATEMENTS.format(ticker=ticker)
        data = self._get(path, params={"period": "quarterly", "limit": 12})
        return data.get("data", data) if isinstance(data, dict) else data

    def company_info(self, ticker: str) -> dict:
        path = ENDPOINT_COMPANY_INFO.format(ticker=ticker)
        data = self._get(path)
        return data.get("data", data) if isinstance(data, dict) else data

    def analyst_ratings(self, ticker: str) -> list[dict]:
        path = ENDPOINT_ANALYST_RATINGS.format(ticker=ticker)
        data = self._get(path)
        return data.get("data", data) if isinstance(data, dict) else data


# ============================================================================
# FEATURE COMPUTATIONS
# ============================================================================

def score_revenue_acceleration(income_stmts: list[dict]) -> tuple[float, str]:
    """
    Feature 1: Revenue growth accelerating across last 3 quarters.

    Compute YoY growth for each of the last 4 quarters. If each successive
    quarter's YoY growth is higher than the prior by ≥5pp → 1.0. If accelerating
    but smaller delta → 0.5. Decelerating or flat → 0.0.
    """
    if len(income_stmts) < 8:
        return 0.0, "insufficient data"

    # Most recent 4 quarters and the 4 prior (for YoY)
    rev = [float(q.get("revenue", 0) or 0) for q in income_stmts[:8]]
    if any(r <= 0 for r in rev):
        return 0.0, "missing revenue"

    yoy = []
    for i in range(4):
        prior = rev[i + 4]
        cur = rev[i]
        if prior > 0:
            yoy.append((cur / prior - 1) * 100)
    if len(yoy) < 3:
        return 0.0, "yoy compute failed"

    # yoy[0] is most recent, yoy[2] is oldest
    deltas = [yoy[0] - yoy[1], yoy[1] - yoy[2]]
    if all(d >= 5.0 for d in deltas):
        return 1.0, f"YoY accel {yoy[2]:.0f}→{yoy[1]:.0f}→{yoy[0]:.0f}%"
    if all(d >= 0 for d in deltas) and (yoy[0] - yoy[2]) >= 5.0:
        return 0.5, f"YoY mild accel {yoy[2]:.0f}→{yoy[0]:.0f}%"
    return 0.0, f"YoY {yoy[2]:.0f}→{yoy[1]:.0f}→{yoy[0]:.0f}% (no accel)"


def score_eps_surprise_streak(earnings: list[dict]) -> tuple[float, str]:
    """
    Feature 2: ≥3 consecutive quarterly EPS surprises >10%.

    1.0 if last 3+ quarters all show surprise_percentage > 10.
    0.5 if last 2 quarters all > 10 OR 3+ all > 5.
    0.0 otherwise.
    """
    if len(earnings) < 3:
        return 0.0, "insufficient earnings"

    surprises = []
    for q in earnings[:4]:
        s = q.get("surprise_percentage") or q.get("surprise_pct") or 0
        try:
            surprises.append(float(s))
        except (TypeError, ValueError):
            surprises.append(0)

    if len(surprises) >= 3 and all(s > 10 for s in surprises[:3]):
        return 1.0, f"3Q streak: {surprises[2]:.0f}/{surprises[1]:.0f}/{surprises[0]:.0f}%"
    if len(surprises) >= 2 and all(s > 10 for s in surprises[:2]):
        return 0.5, f"2Q streak: {surprises[1]:.0f}/{surprises[0]:.0f}%"
    if len(surprises) >= 3 and all(s > 5 for s in surprises[:3]):
        return 0.5, f"3Q soft streak: {surprises[2]:.0f}/{surprises[1]:.0f}/{surprises[0]:.0f}%"
    return 0.0, f"Latest: {surprises[0]:.0f}% (no streak)"


def score_opmargin_expansion(income_stmts: list[dict]) -> tuple[float, str]:
    """
    Feature 3: Operating margin expanding ≥150bps YoY.

    Compare most recent Q op margin to same Q a year ago. Op margin =
    operating_income / revenue. If margin not directly reported, derive from
    gross_profit minus opex if available.
    """
    if len(income_stmts) < 5:
        return 0.0, "insufficient data"

    def om(q):
        rev = float(q.get("revenue", 0) or 0)
        if rev <= 0:
            return None
        oi = q.get("operating_income")
        if oi is None or oi == 0:
            # try derive from gross_profit - sg&a - r&d
            gp = float(q.get("gross_profit", 0) or 0)
            sga = float(q.get("selling_general_and_administrative_expenses", 0) or 0)
            rd = float(q.get("research_and_development_expenses", 0) or 0)
            oi = gp - sga - rd
        try:
            return (float(oi) / rev) * 100
        except (TypeError, ValueError):
            return None

    cur = om(income_stmts[0])
    yoy = om(income_stmts[4])
    if cur is None or yoy is None:
        return 0.0, "margin compute failed"

    delta_bps = (cur - yoy) * 100
    if delta_bps >= 150:
        return 1.0, f"OM {yoy:.1f}%→{cur:.1f}% (+{delta_bps:.0f}bps)"
    if delta_bps >= 50:
        return 0.5, f"OM {yoy:.1f}%→{cur:.1f}% (+{delta_bps:.0f}bps)"
    return 0.0, f"OM {yoy:.1f}%→{cur:.1f}% ({delta_bps:+.0f}bps)"


def score_fwdpe_vs_growth(
    earnings: list[dict],
    income_stmts: list[dict],
    current_price: float,
) -> tuple[float, str]:
    """
    Feature 4: Forward PE / 3Y revenue CAGR < 2.0 → 1.0. < 3.0 → 0.5.

    Forward EPS estimated as: most recent reported EPS × 4 (rough run-rate;
    avoids needing analyst estimate endpoint).
    """
    if not earnings or current_price <= 0:
        return 0.0, "no data"

    eps_recent = earnings[0].get("reported_eps") or earnings[0].get("eps")
    try:
        eps_recent = float(eps_recent)
    except (TypeError, ValueError):
        return 0.0, "eps parse fail"

    fwd_eps = eps_recent * 4
    if fwd_eps <= 0:
        return 0.0, "negative/zero EPS"

    fwd_pe = current_price / fwd_eps

    # 3Y revenue CAGR
    if len(income_stmts) < 12:
        return 0.0, f"fwdPE {fwd_pe:.1f}x but no 3Y data"
    rev_now = float(income_stmts[0].get("revenue", 0) or 0)
    rev_3y = float(income_stmts[11].get("revenue", 0) or 0)
    if rev_3y <= 0 or rev_now <= 0:
        return 0.0, "revenue compute fail"
    cagr_3y = ((rev_now / rev_3y) ** (1 / 3) - 1) * 100
    if cagr_3y <= 0:
        return 0.0, f"fwdPE {fwd_pe:.1f}x, CAGR negative"

    peg = fwd_pe / cagr_3y
    if peg < 2.0:
        return 1.0, f"fwdPE {fwd_pe:.0f}x / CAGR {cagr_3y:.0f}% = PEG {peg:.2f}"
    if peg < 3.0:
        return 0.5, f"fwdPE {fwd_pe:.0f}x / CAGR {cagr_3y:.0f}% = PEG {peg:.2f}"
    return 0.0, f"fwdPE {fwd_pe:.0f}x / CAGR {cagr_3y:.0f}% = PEG {peg:.2f}"


def score_price_base(prices: list[dict]) -> tuple[float, str]:
    """
    Feature 5: Long pre-recognition base. Compute % of trading days in the
    PRIOR 12-36 months window (i.e., 12mo ago to 36mo ago) where price was
    below $25. The "boredom fuel" period before the recent move.

    >70% of days <$25 → 1.0 (deep base)
    >40% → 0.5
    else 0
    """
    if not prices or len(prices) < 252:
        return 0.0, "insufficient price history"

    # Sort prices oldest→newest based on date string
    sorted_prices = sorted(prices, key=lambda p: p.get("date") or "")

    # Use the chunk from ~756 trading days ago to ~252 days ago (months 12-36 back)
    if len(sorted_prices) < 756:
        # Not 3y of history. Use what we have, excluding most recent 252 days.
        base_window = sorted_prices[: max(0, len(sorted_prices) - 252)]
    else:
        base_window = sorted_prices[-756:-252]

    if not base_window:
        return 0.0, "base window empty"

    closes = [float(p.get("close", 0) or 0) for p in base_window]
    closes = [c for c in closes if c > 0]
    if not closes:
        return 0.0, "no valid closes"

    pct_under_25 = sum(1 for c in closes if c < 25) / len(closes)
    median = sorted(closes)[len(closes) // 2]
    if pct_under_25 > 0.70:
        return 1.0, f"{pct_under_25*100:.0f}% of base <$25 (median ${median:.0f})"
    if pct_under_25 > 0.40:
        return 0.5, f"{pct_under_25*100:.0f}% of base <$25 (median ${median:.0f})"
    return 0.0, f"only {pct_under_25*100:.0f}% of base <$25 (median ${median:.0f})"


def classify_phase(prices: list[dict], earnings: list[dict]) -> str:
    """
    Quick phase classification using price action + recent earnings.

    Phase 0  flat 24mo+, no recent surprise streak
    Phase 1  recent 2-3 beats, price up 30-60% from 12mo base
    Phase 2  price up 100-200% from 12mo base, PT chases
    Phase 3  price up >300% from 24mo base, parabolic last 60 days
    Phase 4  price down from recent ATH despite good news
    """
    if not prices or len(prices) < 60:
        return "Unknown"

    sorted_p = sorted(prices, key=lambda p: p.get("date") or "")
    closes = [float(p.get("close", 0) or 0) for p in sorted_p if p.get("close")]
    if len(closes) < 60:
        return "Unknown"

    current = closes[-1]
    # 60d, 252d, 504d ago
    px_60d = closes[-60] if len(closes) >= 60 else closes[0]
    px_1y = closes[-252] if len(closes) >= 252 else closes[0]
    px_2y = closes[-504] if len(closes) >= 504 else closes[0]

    ret_1y = (current / px_1y - 1) * 100 if px_1y > 0 else 0
    ret_2y = (current / px_2y - 1) * 100 if px_2y > 0 else 0
    ret_60d = (current / px_60d - 1) * 100 if px_60d > 0 else 0

    # Recent ATH check (max in last 252 days)
    recent_high = max(closes[-252:]) if len(closes) >= 252 else max(closes)
    pct_from_ath = (current / recent_high - 1) * 100 if recent_high > 0 else 0

    if ret_2y > 300 and ret_60d > 25:
        return "Phase 3 (parabola)"
    if ret_2y > 300 and pct_from_ath < -10:
        return "Phase 4 (distribution)"
    if ret_1y > 100 and ret_1y < 300:
        return "Phase 2 (recognition)"
    if 30 <= ret_1y <= 100:
        # check beats
        surprises = [float(q.get("surprise_percentage", 0) or 0) for q in earnings[:3]]
        if sum(1 for s in surprises if s > 10) >= 2:
            return "Phase 1 (inflection)"
        return "Phase 1 (early)"
    if abs(ret_2y) < 30:
        return "Phase 0 (boredom)"
    return "Phase 1/2 (transition)"


# ============================================================================
# MAIN SCREENER
# ============================================================================

def score_bundle(
    ticker: str,
    earnings: list[dict],
    prices: list[dict],
    income: list[dict],
    info: dict,
    profile: dict,
) -> ScreenResult:
    """Pure scoring core — run the 8-feature screen on ALREADY-FETCHED data.

    Shared by the live path (``screen_ticker`` fetches, then calls this) and the
    file-fed producer (``--from-bundle``). No network I/O happens here, so it is
    fully unit-testable with synthetic inputs and carries no UW credential.
    """
    feat = FeatureScores()
    notes: list[str] = []
    phase = "Unknown"
    error: str | None = None

    try:
        current_price = 0.0
        if isinstance(info, dict):
            current_price = float(info.get("price", 0) or 0)
        if current_price == 0.0 and prices:
            sorted_p = sorted(prices, key=lambda p: p.get("date") or "")
            current_price = float(sorted_p[-1].get("close", 0) or 0)

        # Feature 1 — revenue acceleration
        score, note = score_revenue_acceleration(income)
        feat.revenue_accel = score
        notes.append(f"  F1 rev_accel    = {score:.1f} | {note}")

        # Feature 2 — EPS surprise streak
        score, note = score_eps_surprise_streak(earnings)
        feat.eps_streak = score
        notes.append(f"  F2 eps_streak   = {score:.1f} | {note}")

        # Feature 3 — operating margin expansion
        score, note = score_opmargin_expansion(income)
        feat.opmargin_exp = score
        notes.append(f"  F3 opmargin_exp = {score:.1f} | {note}")

        # Feature 4 — forward PE vs growth
        score, note = score_fwdpe_vs_growth(earnings, income, current_price)
        feat.fwdpe_vs_growth = score
        notes.append(f"  F4 fwdpe_growth = {score:.1f} | {note}")

        # Feature 5 — pre-recognition base
        score, note = score_price_base(prices)
        feat.price_base = score
        notes.append(f"  F5 price_base   = {score:.1f} | {note}")

        # Features 6/7/8 — manual seed
        feat.industry_conc = profile.get("industry_conc", 0.0)
        feat.multi_node = profile.get("multi_node", 0.0)
        feat.customer_conc = profile.get("customer_conc", 0.0)
        notes.append(f"  F6 industry     = {feat.industry_conc:.1f} | seeded")
        notes.append(f"  F7 multi_node   = {feat.multi_node:.1f} | seeded")
        notes.append(f"  F8 customer     = {feat.customer_conc:.1f} | seeded")

        # Phase classification
        phase = classify_phase(prices, earnings)

    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    # Surface tier
    total = feat.weighted_total
    if total >= THRESHOLD_AUTOFIRE:
        tier = "AUTOFIRE"
    elif total >= THRESHOLD_WATCHLIST:
        tier = "WATCHLIST"
    else:
        tier = "SKIP"

    return ScreenResult(
        ticker=ticker,
        score=total,
        surface_tier=tier,
        phase=phase,
        features=feat,
        notes=notes,
        error=error,
    )


def screen_ticker(client: UWClient, ticker: str, profile: dict) -> ScreenResult:
    """Live path: fetch the 4 endpoints, then run the pure scoring core."""
    try:
        earnings = client.earnings_history(ticker)
        prices = client.close_prices(ticker, days_back=900)
        income = client.income_statements(ticker)
        info = client.company_info(ticker)
    except requests.HTTPError as e:
        return ScreenResult(
            ticker=ticker, score=0.0, surface_tier="SKIP", phase="Unknown",
            features=FeatureScores(), notes=[],
            error=f"HTTP {e.response.status_code}",
        )
    except Exception as e:
        return ScreenResult(
            ticker=ticker, score=0.0, surface_tier="SKIP", phase="Unknown",
            features=FeatureScores(), notes=[],
            error=f"{type(e).__name__}: {e}",
        )
    return score_bundle(ticker, earnings, prices, income, info or {}, profile or {})


def render_text_report(results: list[ScreenResult], verbose: bool = False) -> str:
    out = []
    out.append("=" * 78)
    out.append(
        f"PARABOLIC SETUP SCREENER — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    out.append("=" * 78)
    out.append(
        f"Threshold: AUTOFIRE >= {THRESHOLD_AUTOFIRE} | "
        f"WATCHLIST >= {THRESHOLD_WATCHLIST} | "
        f"SKIP < {THRESHOLD_WATCHLIST} | "
        f"MAX = {MAX_POSSIBLE}"
    )
    out.append("")

    by_tier: dict[str, list[ScreenResult]] = {"AUTOFIRE": [], "WATCHLIST": [], "SKIP": []}
    for r in results:
        by_tier[r.surface_tier].append(r)

    for tier in ("AUTOFIRE", "WATCHLIST", "SKIP"):
        if not by_tier[tier]:
            continue
        out.append(f"--- {tier} ({len(by_tier[tier])}) ---")
        for r in sorted(by_tier[tier], key=lambda x: -x.score):
            line = f"{r.ticker:6}  score {r.score:5.2f}/13.0  {r.phase}"
            if r.error:
                line += f"  [ERR: {r.error}]"
            out.append(line)
            if verbose and not r.error:
                out.extend(r.notes)
                out.append("")
        out.append("")
    return "\n".join(out)


# ============================================================================
# FILE-FED PRODUCER PATH (no live API; consumed by the session pre-flight)
# ============================================================================

def _empty_profile() -> dict:
    return {"industry_conc": 0.0, "multi_node": 0.0, "customer_conc": 0.0}


def screen_from_bundle(bundle: dict) -> list[ScreenResult]:
    """Score a bundle of PRE-FETCHED per-ticker data — the token-safe producer
    path. Bundle shape::

        {"as_of": "YYYY-MM-DD",
         "tickers": {"NVDA": {"earnings": [...], "prices": [...],
                              "income": [...], "info": {...},
                              "profile": {...}?}, ...}}

    Per-ticker ``profile`` is optional; falls back to CANDIDATE_PROFILES, then 0s.
    """
    out: list[ScreenResult] = []
    for raw_tkr, data in (bundle.get("tickers") or {}).items():
        t = str(raw_tkr).upper()
        data = data or {}
        profile = data.get("profile") or CANDIDATE_PROFILES.get(t, _empty_profile())
        out.append(score_bundle(
            t,
            data.get("earnings") or [],
            data.get("prices") or [],
            data.get("income") or [],
            data.get("info") or {},
            profile,
        ))
    return out


def build_emit_payload(results: list[ScreenResult], as_of: str | None) -> dict:
    """The producer output contract the session pre-flight consumes."""
    counts = {"AUTOFIRE": 0, "WATCHLIST": 0, "SKIP": 0}
    for r in results:
        counts[r.surface_tier] = counts.get(r.surface_tier, 0) + 1
    return {
        "as_of": as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [r.to_dict() for r in results],
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Raw-UW -> canonical bundle adapters (used by the bundle assembler / routine)
# ---------------------------------------------------------------------------
# UW MCP/REST field names differ from the canonical names score_bundle reads, so
# these adapters live at the PRODUCER BOUNDARY and the scoring core stays pure.
# Confirmed against live NVDA pulls (2026-06-01):
#   income   : "total_revenue" -> "revenue"; "selling_general_and_administrative"
#              and "research_and_development" -> "..._expenses" (op-margin derive
#              fallback only; primary path uses operating_income, which matches).
#   earnings : UW lists the UPCOMING unreported quarter at index 0 with
#              reported_eps == null; drop those so index 0 == most recent
#              reported quarter (what the scoring fns assume).
#   info     : UW returns {"data": {...company...}, "price": "<px>"} — price is
#              a TOP-LEVEL sibling of "data", not inside it.
#   prices   : UW close-price rows use "c" for close (+ "date"); daily on the
#              3M/1Y/5Y/10Y/YTD presets, usually wrapped as {"data": [...]}.
#              Confirmed live 2026-06-01 -> map "c" -> "close". (1Y gives ~252
#              rows; F5 base-window needs ~5Y for full depth, so the cloud
#              routine should pull 5Y/10Y; shorter windows just leave F5 = 0.)

_UW_INCOME_FIELD_MAP = {
    "total_revenue": "revenue",
    "selling_general_and_administrative": "selling_general_and_administrative_expenses",
    "research_and_development": "research_and_development_expenses",
}


def adapt_uw_income(rows: list[dict], limit: int = 12) -> list[dict]:
    out = []
    for r in (rows or [])[:limit]:
        rr = dict(r)
        for src, dst in _UW_INCOME_FIELD_MAP.items():
            if src in rr and dst not in rr:
                rr[dst] = rr[src]
        out.append(rr)
    return out


def adapt_uw_earnings(rows: list[dict], limit: int = 12) -> list[dict]:
    reported = [r for r in (rows or []) if r.get("reported_eps") not in (None, "")]
    return reported[:limit]


def adapt_uw_info(info_resp: dict) -> dict:
    if not isinstance(info_resp, dict):
        return {}
    out = dict(info_resp.get("data") or {})
    if "price" in info_resp:
        out["price"] = info_resp["price"]
    return out


def adapt_uw_prices(rows) -> list[dict]:
    # UW close-price rows use 'c' for close (+ 'date'); may arrive wrapped as
    # {"data": [...]}. score_price_base / classify_phase read 'close' + 'date'.
    if isinstance(rows, dict):
        rows = rows.get("data") or []
    out = []
    for r in (rows or []):
        rr = dict(r)
        if "close" not in rr and "c" in rr:
            rr["close"] = rr["c"]
        out.append(rr)
    return out


def bundle_entry_from_uw(earnings, prices, income, info, profile=None) -> dict:
    """Convert raw UW responses into a canonical bundle entry — the shape
    score_bundle / screen_from_bundle expects. Called by the bundle assembler."""
    entry = {
        "earnings": adapt_uw_earnings(earnings),
        "prices": adapt_uw_prices(prices),
        "income": adapt_uw_income(income),
        "info": adapt_uw_info(info),
    }
    if profile is not None:
        entry["profile"] = profile
    return entry


# ============================================================================
# SELF-TEST (golden-master fixtures + producer contract)
# ============================================================================

def _fixture_autofire() -> dict:
    # F1=1.0 accel, F2=1.0 (3x>10%), F3=1.0 (+500bps), F4=0 (<12 stmts),
    # F5=0 (no prices), profile 1/1/1 -> 2+2+1.5+0+0+2+1.5+1.5 = 10.5 -> AUTOFIRE
    return {
        "earnings": [{"surprise_percentage": 15}, {"surprise_percentage": 20},
                     {"surprise_percentage": 12}],
        "prices": [],
        "income": [
            {"revenue": 200, "operating_income": 40},
            {"revenue": 180}, {"revenue": 160}, {"revenue": 150},
            {"revenue": 100, "operating_income": 15},
            {"revenue": 95}, {"revenue": 92}, {"revenue": 100},
        ],
        "info": {},
        "profile": {"industry_conc": 1.0, "multi_node": 1.0, "customer_conc": 1.0},
    }


def _fixture_watchlist() -> dict:
    # F2=1.0 (2.0) + profile 1/1/1 (5.0) = 7.0 -> WATCHLIST; all else 0
    return {
        "earnings": [{"surprise_percentage": 15}, {"surprise_percentage": 20},
                     {"surprise_percentage": 30}],
        "prices": [],
        "income": [{"revenue": 100}, {"revenue": 100}],
        "info": {},
        "profile": {"industry_conc": 1.0, "multi_node": 1.0, "customer_conc": 1.0},
    }


def _fixture_skip() -> dict:
    # everything 0 -> SKIP
    return {
        "earnings": [{"surprise_percentage": 1}, {"surprise_percentage": 2},
                     {"surprise_percentage": 0}],
        "prices": [],
        "income": [{"revenue": 100}, {"revenue": 100}],
        "info": {},
        "profile": {"industry_conc": 0.0, "multi_node": 0.0, "customer_conc": 0.0},
    }


def _score_fixture(tkr: str, fx: dict) -> ScreenResult:
    return score_bundle(tkr, fx["earnings"], fx["prices"], fx["income"],
                        fx["info"], fx["profile"])


def _self_test() -> int:
    failures = 0

    def check(cond: bool, label: str) -> None:
        nonlocal failures
        if not cond:
            failures += 1
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("parabolic_setup_screener self-test")
    print("- golden-master: known fixtures -> known tiers")
    af = _score_fixture("AF", _fixture_autofire())
    check(abs(af.score - 10.5) < 1e-6, f"AUTOFIRE fixture score == 10.5 (got {af.score})")
    check(af.surface_tier == "AUTOFIRE", f"AUTOFIRE fixture tier (got {af.surface_tier})")
    wl = _score_fixture("WL", _fixture_watchlist())
    check(abs(wl.score - 7.0) < 1e-6, f"WATCHLIST fixture score == 7.0 (got {wl.score})")
    check(wl.surface_tier == "WATCHLIST", f"WATCHLIST fixture tier (got {wl.surface_tier})")
    sk = _score_fixture("SK", _fixture_skip())
    check(abs(sk.score - 0.0) < 1e-6, f"SKIP fixture score == 0.0 (got {sk.score})")
    check(sk.surface_tier == "SKIP", f"SKIP fixture tier (got {sk.surface_tier})")

    print("- contract: ScreenResult.to_dict() shape")
    d = af.to_dict()
    for k in ("ticker", "score", "surface_tier", "phase", "features",
              "weighted_total", "notes"):
        check(k in d, f"to_dict has '{k}'")
    check(isinstance(d["features"], dict) and "revenue_accel" in d["features"],
          "to_dict features expanded with revenue_accel")

    print("- producer: bundle -> results -> emit payload")
    bundle = {"as_of": "2026-06-01", "tickers": {
        "AF": _fixture_autofire(), "WL": _fixture_watchlist(),
        "SK": _fixture_skip()}}
    results = screen_from_bundle(bundle)
    check(len(results) == 3, f"screen_from_bundle returns 3 (got {len(results)})")
    payload = build_emit_payload(results, bundle.get("as_of"))
    check(payload.get("as_of") == "2026-06-01", "emit as_of preserved")
    check({"as_of", "results", "counts", "generated_at"} <= set(payload),
          "emit payload has required keys")
    check(payload["counts"] == {"AUTOFIRE": 1, "WATCHLIST": 1, "SKIP": 1},
          f"emit counts (got {payload['counts']})")
    check(len(payload["results"]) == 3, "emit has 3 results")

    print("- producer: CANDIDATE_PROFILES fallback when bundle omits profile")
    r2 = screen_from_bundle({"tickers": {"VIAV": {"earnings": [], "prices": [],
                                                  "income": [], "info": {}}}})
    check(bool(r2) and r2[0].features.industry_conc == 1.0,
          "VIAV uses CANDIDATE_PROFILES (industry_conc == 1.0)")

    print("- UW adapter: raw UW field names -> canonical (live-confirmed shapes)")
    raw_income = [{"total_revenue": "200", "operating_income": "40"},
                  {"total_revenue": "100"}]
    ai = adapt_uw_income(raw_income)
    check(ai[0].get("revenue") == "200", "income total_revenue -> revenue")
    raw_earn = [{"reported_eps": None, "surprise_percentage": None},
                {"reported_eps": "1.87", "surprise_percentage": "5.6"}]
    ae = adapt_uw_earnings(raw_earn)
    check(len(ae) == 1 and ae[0]["reported_eps"] == "1.87",
          "earnings drops null reported_eps (unreported quarter)")
    ainfo = adapt_uw_info({"data": {"sector": "Technology"}, "price": "212.49"})
    check(ainfo.get("price") == "212.49", "info pulls top-level price")
    entry = bundle_entry_from_uw(raw_earn, [], raw_income,
                                 {"data": {}, "price": "10"},
                                 profile={"industry_conc": 1.0})
    check(entry["income"][0].get("revenue") == "200"
          and len(entry["earnings"]) == 1
          and entry["info"]["price"] == "10"
          and entry["profile"]["industry_conc"] == 1.0,
          "bundle_entry_from_uw produces a canonical entry")
    ap = adapt_uw_prices({"data": [{"c": 211.14, "date": "2026-05-29"},
                                   {"c": 198.45, "date": "2026-05-01"}]})
    check(len(ap) == 2 and ap[0].get("close") == 211.14 and bool(ap[0].get("date")),
          "prices 'c' -> 'close' (+ unwraps {data:[...]})")

    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILED'}")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="VIAV-pattern parabolic setup screener")
    parser.add_argument("--tickers", help="Comma-separated tickers to screen (default: all candidates)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--verbose", action="store_true", help="Show per-feature breakdown")
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help=f"Override surface threshold (default {THRESHOLD_WATCHLIST})",
    )
    parser.add_argument(
        "--from-bundle",
        help="Score pre-fetched per-ticker data from a bundle JSON "
             "(token-safe producer path; no live UW calls).",
    )
    parser.add_argument(
        "--emit",
        help="Write the producer cache JSON (consumed by the session pre-flight) "
             "to this path.",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run the built-in self-test (golden-master + producer contract) and exit.",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    # ---- File-fed producer path (no UW_API_KEY required) ----
    if args.from_bundle:
        with open(args.from_bundle) as fh:
            bundle = json.load(fh)
        results = screen_from_bundle(bundle)
        payload = build_emit_payload(results, bundle.get("as_of"))
        if args.emit:
            with open(args.emit, "w") as fh:
                json.dump(payload, fh, indent=2)
            print(f"Emitted {len(results)} results -> {args.emit} "
                  f"(AUTOFIRE {payload['counts']['AUTOFIRE']}, "
                  f"WATCHLIST {payload['counts']['WATCHLIST']}, "
                  f"SKIP {payload['counts']['SKIP']})", file=sys.stderr)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(render_text_report(results, verbose=args.verbose))
        return 0

    # ---- Live path (requires UW_API_KEY) ----
    api_key = os.environ.get("UW_API_KEY")
    if not api_key:
        print("ERROR: UW_API_KEY env var not set", file=sys.stderr)
        return 1

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        # For ad-hoc tickers not in CANDIDATE_PROFILES, score features 6-8 as 0
        profiles = {
            t: CANDIDATE_PROFILES.get(
                t, {"industry_conc": 0.0, "multi_node": 0.0, "customer_conc": 0.0}
            )
            for t in tickers
        }
    else:
        profiles = CANDIDATE_PROFILES
        tickers = list(profiles.keys())

    client = UWClient(api_key=api_key, verbose=args.verbose)
    results: list[ScreenResult] = []
    failures = 0
    for t in tickers:
        if args.verbose:
            print(f"Screening {t}...", file=sys.stderr)
        r = screen_ticker(client, t, profiles.get(t, {}))
        if r.error:
            failures += 1
        results.append(r)

    if args.emit:
        payload = build_emit_payload(results, None)
        with open(args.emit, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"Emitted {len(results)} results -> {args.emit}", file=sys.stderr)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(render_text_report(results, verbose=args.verbose))

    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
