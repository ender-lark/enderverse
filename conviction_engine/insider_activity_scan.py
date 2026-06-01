#!/usr/bin/env python3
"""
insider_activity_scan.py — v11.26 rebuild

PURPOSE
    Portfolio-wide batch insider activity scan.  Filter noise (RSU vesting,
    10b5-1 sales, option exercises, gifts, sub-$500K transactions) and
    classify each ticker as BULLISH / BEARISH / CLUSTER / NOISE / FLAGGED.

CLASSIFICATION RULES (per operator memory)
    BULLISH   ≥1 discretionary purchase >$500K by C-suite (NOT 10b5-1)
    BEARISH   ≥1 discretionary sale 30d before known catalyst (NOT 10b5-1)
    CLUSTER   ≥3 distinct insiders trading same direction within 90 days
    NOISE     only RSU/10b5-1/option exercise/gift, OR all sub-$500K
    FLAGGED   Trump-ally tagged purchase OR sale 30d pre-catalyst

V11.26 ENHANCEMENTS
    1. Macro-regime tag (v11.25) on signals — BULLISH purchases in
       duration_WEAK regime on rate-sensitive names = stronger signal
    2. Catalysts integration — sales 30d before known catalyst auto-FLAGGED
    3. Trump-ally pass-through (Cat 8 Two-Lens hook)

NOT IN SCOPE
    - Live data fetching — pre-fetched insider_data dict expected as input
    - Form 4 parsing — assumes upstream normalization
    - Equity grant analysis — only acquisitions/dispositions in scope

USAGE
    python insider_activity_scan.py --self-test
    python insider_activity_scan.py --positions P.json --insider-data D.json \\
        [--catalysts C.json] [--macro M.json] [--surface]
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any


# ============================================================================
# CONSTANTS
# ============================================================================

DISCRETIONARY_BUY_THRESHOLD = 500_000.0  # $500K+ discretionary buy = bullish
CLUSTER_THRESHOLD = 3                     # ≥3 distinct insiders = cluster
CLUSTER_WINDOW_DAYS = 90
PRE_CATALYST_FLAG_DAYS = 30               # sale within 30d of catalyst = flag

# Transaction codes to filter as noise (SEC Form 4 codes)
# Code semantics: A=grant/award, M=exempt option exercise, F=tax payment,
#   G=gift, P=purchase, S=sale, X=option exercise (in-the-money)
NOISE_CODES = {"A", "F", "G", "M", "X"}
RSU_VEST_TRANSACTION_TYPES = {"RSU_VEST", "AWARD", "TAX_WITHHOLD"}
RULE_10B5_1_PLAN_FLAG = "rule_10b5_1"

RATE_SENSITIVE_FACTORS = {
    "long_duration_growth", "ai_complex", "long_duration", "high_pe",
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class InsiderSignal:
    ticker: str
    classification: str  # BULLISH / BEARISH / CLUSTER / NOISE / FLAGGED
    bullish_count: int = 0
    bearish_count: int = 0
    cluster_count: int = 0
    largest_buy_value: float = 0.0
    largest_sale_value: float = 0.0
    trump_ally_buys: List[Dict] = field(default_factory=list)
    pre_catalyst_sales: List[Dict] = field(default_factory=list)
    distinct_insiders: int = 0

    macro_context: Optional[str] = None  # v11.26
    flags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class InsiderReport:
    bullish: List[InsiderSignal] = field(default_factory=list)
    bearish: List[InsiderSignal] = field(default_factory=list)
    cluster: List[InsiderSignal] = field(default_factory=list)
    flagged: List[InsiderSignal] = field(default_factory=list)
    noise: List[InsiderSignal] = field(default_factory=list)
    summary: str = ""


# ============================================================================
# HELPERS
# ============================================================================

def _is_noise(txn: Dict) -> bool:
    """
    True if this transaction is structural noise (vesting, gifts, exempt
    exercises, 10b5-1 plans).
    """
    code = (txn.get("transaction_code") or "").upper().strip()
    if code in NOISE_CODES:
        return True
    txn_type = (txn.get("transaction_type") or "").upper().strip()
    if txn_type in RSU_VEST_TRANSACTION_TYPES:
        return True
    if txn.get(RULE_10B5_1_PLAN_FLAG) is True:
        return True
    if (txn.get("is_10b5_1_plan") or "").lower() in ("true", "yes", "1"):
        return True
    return False


def _is_csuite(txn: Dict) -> bool:
    title = (txn.get("insider_title") or "").upper()
    csuite_keywords = ("CEO", "CFO", "COO", "CTO", "PRESIDENT", "CHAIRMAN",
                       "CHIEF EXECUTIVE", "CHIEF FINANCIAL", "CHIEF OPERATING",
                       "CHIEF TECHNOLOGY", "DIRECTOR")
    return any(k in title for k in csuite_keywords)


def _txn_value(txn: Dict) -> float:
    """Notional value of transaction."""
    try:
        v = txn.get("value") or txn.get("notional_usd")
        if v is not None:
            return float(v)
        shares = float(txn.get("shares") or 0)
        price = float(txn.get("price") or 0)
        return abs(shares * price)
    except (TypeError, ValueError):
        return 0.0


def _is_purchase(txn: Dict) -> bool:
    code = (txn.get("transaction_code") or "").upper().strip()
    side = (txn.get("side") or "").lower()
    if code == "P":
        return True
    if side in ("buy", "purchase", "acquire"):
        return True
    if (txn.get("shares") or 0) > 0 and not _is_noise(txn):
        # Heuristic: positive share count without noise code → assume buy
        if code in ("", "P"):
            return True
    return False


def _is_sale(txn: Dict) -> bool:
    code = (txn.get("transaction_code") or "").upper().strip()
    side = (txn.get("side") or "").lower()
    if code == "S":
        return True
    if side in ("sell", "sale", "dispose"):
        return True
    return False


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


def _days_until_catalyst(txn_date: datetime,
                         catalysts: Optional[List[Dict]],
                         ticker: str) -> Optional[int]:
    """Return # days from txn_date until nearest known catalyst (or None)."""
    if not catalysts:
        return None
    min_days = None
    for c in catalysts:
        if (c.get("ticker") or "").upper() != ticker.upper():
            continue
        cd = _parse_date(c.get("date"))
        if not cd:
            continue
        days = (cd - txn_date).days
        if days >= 0:
            if min_days is None or days < min_days:
                min_days = days
    return min_days


def _macro_context_for(ticker: str, theses: Optional[List[Dict]],
                       macro_pulse: Optional[Dict]) -> Optional[str]:
    """Return macro context tag if ticker is rate-sensitive in current regime."""
    if not macro_pulse or not theses:
        return None
    regime = (macro_pulse.get("regime_label")
              or macro_pulse.get("regime") or "").lower()
    factor_tags = []
    for t in theses:
        if (t.get("ticker") or "").upper() == ticker.upper():
            factor_tags = [f.lower() for f in (t.get("factor_tags") or [])]
            break
    rate_sensitive = bool(set(factor_tags) & RATE_SENSITIVE_FACTORS)
    if rate_sensitive and "duration_weak" in regime:
        return "rate-sensitive + duration_WEAK"
    if rate_sensitive and "duration_strong" in regime:
        return "rate-sensitive + duration_STRONG"
    return None


# ============================================================================
# CORE SCANNER
# ============================================================================

def scan_ticker(ticker: str, transactions: List[Dict],
                catalysts: Optional[List[Dict]] = None,
                theses: Optional[List[Dict]] = None,
                macro_pulse: Optional[Dict] = None,
                today: Optional[datetime] = None) -> InsiderSignal:
    """
    Classify a single ticker's recent insider activity.
    """
    if today is None:
        today = datetime.now()
    cluster_cutoff = today - timedelta(days=CLUSTER_WINDOW_DAYS)

    signal = InsiderSignal(ticker=ticker, classification="NOISE")

    distinct_buyers = set()
    distinct_sellers = set()
    has_meaningful_signal = False

    for txn in transactions:
        txn_date = _parse_date(txn.get("date"))
        if txn_date is None:
            continue

        # Within cluster window?
        in_window = txn_date >= cluster_cutoff
        value = _txn_value(txn)
        insider_name = (txn.get("insider_name") or "").strip()
        trump_ally = bool(txn.get("trump_ally"))

        # Filter pure noise
        noise = _is_noise(txn)

        if _is_purchase(txn) and not noise:
            if value > signal.largest_buy_value:
                signal.largest_buy_value = value
            if in_window:
                distinct_buyers.add(insider_name)
            if value >= DISCRETIONARY_BUY_THRESHOLD and _is_csuite(txn):
                signal.bullish_count += 1
                has_meaningful_signal = True
            if trump_ally:  # any size — operator-spec: all ally buys visible
                signal.trump_ally_buys.append({
                    "name": insider_name,
                    "value": value,
                    "date": txn.get("date"),
                })
                has_meaningful_signal = True

        elif _is_sale(txn) and not noise:
            if value > signal.largest_sale_value:
                signal.largest_sale_value = value
            if in_window:
                distinct_sellers.add(insider_name)
            # Pre-catalyst check
            days = _days_until_catalyst(txn_date, catalysts, ticker)
            if days is not None and 0 <= days <= PRE_CATALYST_FLAG_DAYS:
                if value >= DISCRETIONARY_BUY_THRESHOLD:
                    signal.bearish_count += 1
                    signal.pre_catalyst_sales.append({
                        "name": insider_name,
                        "value": value,
                        "date": txn.get("date"),
                        "days_to_catalyst": days,
                    })
                    has_meaningful_signal = True

    signal.distinct_insiders = len(distinct_buyers) + len(distinct_sellers)

    # Cluster detection
    if len(distinct_buyers) >= CLUSTER_THRESHOLD:
        signal.cluster_count = len(distinct_buyers)
        if signal.classification != "FLAGGED":
            signal.classification = "CLUSTER"
            has_meaningful_signal = True
    elif len(distinct_sellers) >= CLUSTER_THRESHOLD:
        signal.cluster_count = len(distinct_sellers)
        if signal.classification != "FLAGGED":
            signal.classification = "CLUSTER"
            has_meaningful_signal = True

    # Classification precedence:
    # FLAGGED > CLUSTER > BEARISH > BULLISH > NOISE
    if signal.trump_ally_buys or signal.pre_catalyst_sales:
        signal.classification = "FLAGGED"
    elif signal.cluster_count >= CLUSTER_THRESHOLD:
        signal.classification = "CLUSTER"
    elif signal.bearish_count > 0:
        signal.classification = "BEARISH"
    elif signal.bullish_count > 0:
        signal.classification = "BULLISH"
    else:
        signal.classification = "NOISE"

    # v11.26 macro context
    signal.macro_context = _macro_context_for(ticker, theses, macro_pulse)
    if signal.macro_context and signal.classification == "BULLISH":
        signal.notes.append(f"BULLISH signal strengthened by macro: "
                            f"{signal.macro_context}")

    return signal


def scan(positions: List[Dict], insider_data: Dict[str, List[Dict]],
         catalysts: Optional[List[Dict]] = None,
         theses: Optional[List[Dict]] = None,
         macro_pulse: Optional[Dict] = None,
         today: Optional[datetime] = None) -> InsiderReport:
    """Run insider scan across all positions."""
    report = InsiderReport()
    tickers_seen = set()
    for p in positions:
        t = (p.get("ticker") or "").upper().strip()
        if not t or t in tickers_seen:
            continue
        tickers_seen.add(t)
        txns = insider_data.get(t, []) or []
        signal = scan_ticker(t, txns, catalysts, theses, macro_pulse, today)

        if signal.classification == "FLAGGED":
            report.flagged.append(signal)
        elif signal.classification == "CLUSTER":
            report.cluster.append(signal)
        elif signal.classification == "BEARISH":
            report.bearish.append(signal)
        elif signal.classification == "BULLISH":
            report.bullish.append(signal)
        else:
            report.noise.append(signal)

    report.summary = (
        f"{len(report.bullish)} BULLISH, {len(report.bearish)} BEARISH, "
        f"{len(report.cluster)} CLUSTER, {len(report.flagged)} FLAGGED, "
        f"{len(report.noise)} NOISE."
    )
    return report


# ============================================================================
# OUTPUT FORMATTERS
# ============================================================================

def format_text_report(r: InsiderReport) -> str:
    out = []
    out.append("=" * 70)
    out.append("INSIDER ACTIVITY SCAN")
    out.append("=" * 70)
    out.append(r.summary)
    out.append("")

    def _section(label: str, items: List[InsiderSignal], symbol: str) -> None:
        if not items:
            return
        out.append(f"-- {symbol} {label} ({len(items)}) " + "-" * 40)
        for s in items:
            extras = []
            if s.bullish_count: extras.append(f"+{s.bullish_count}B")
            if s.bearish_count: extras.append(f"-{s.bearish_count}S")
            if s.cluster_count: extras.append(f"cluster n={s.cluster_count}")
            if s.largest_buy_value: extras.append(f"largest buy ${s.largest_buy_value:,.0f}")
            if s.largest_sale_value: extras.append(f"largest sale ${s.largest_sale_value:,.0f}")
            out.append(f"  {s.ticker:8} {'  '.join(extras)}")
            if s.trump_ally_buys:
                for b in s.trump_ally_buys:
                    out.append(f"        trump-ally buy: {b['name']} "
                               f"${b['value']:,.0f} on {b['date']}")
            if s.pre_catalyst_sales:
                for sale in s.pre_catalyst_sales:
                    out.append(f"        pre-catalyst sale: {sale['name']} "
                               f"${sale['value']:,.0f} on {sale['date']} "
                               f"({sale['days_to_catalyst']}d to catalyst)")
            if s.macro_context:
                out.append(f"        macro: {s.macro_context}")
            if s.notes:
                for n in s.notes:
                    out.append(f"        note: {n}")
        out.append("")

    _section("FLAGGED (Cat 8 hooks)", r.flagged, "🚩")
    _section("BULLISH", r.bullish, "🟢")
    _section("BEARISH", r.bearish, "🔴")
    _section("CLUSTER", r.cluster, "📊")

    if r.noise:
        out.append(f"-- NOISE ({len(r.noise)}) (filtered, not reported in detail) "
                   + "-" * 5)
        out.append("    " + ", ".join(s.ticker for s in r.noise))
        out.append("")

    return "\n".join(out)


def format_json_report(r: InsiderReport) -> str:
    return json.dumps(asdict(r), indent=2, default=str)


def surface_line(r: InsiderReport) -> str:
    """Pre-flight surface line."""
    parts = []
    if r.flagged:
        parts.append(f"{len(r.flagged)} FLAGGED")
    if r.bullish:
        parts.append(f"{len(r.bullish)} BULLISH")
    if r.bearish:
        parts.append(f"{len(r.bearish)} BEARISH")
    if r.cluster:
        parts.append(f"{len(r.cluster)} CLUSTER")
    if not parts:
        return "INSIDER ACTIVITY: no signal (all NOISE after filtering)"
    return f"INSIDER ACTIVITY: " + ", ".join(parts) + " (rest filtered as noise)"


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

    # ----- Test 1: discretionary C-suite buy >$500K → BULLISH
    r = scan(
        [{"ticker": "AAA"}],
        {"AAA": [{
            "date": "2026-05-15",
            "transaction_code": "P",
            "insider_title": "CEO",
            "insider_name": "Alice",
            "shares": 10000, "price": 100,  # $1M
        }]},
        today=today
    )
    assert_eq(len(r.bullish), 1, "$1M C-suite buy → BULLISH")
    assert_eq(r.bullish[0].bullish_count, 1, "bullish_count = 1")

    # ----- Test 2: sub-$500K buy → NOISE (not bullish)
    r = scan(
        [{"ticker": "BBB"}],
        {"BBB": [{
            "date": "2026-05-15",
            "transaction_code": "P",
            "insider_title": "CEO",
            "insider_name": "Bob",
            "shares": 1000, "price": 100,  # $100K
        }]},
        today=today
    )
    assert_eq(len(r.bullish), 0, "$100K buy not bullish")
    assert_eq(len(r.noise), 1, "$100K buy classified as NOISE")

    # ----- Test 3: RSU vest filtered as noise
    r = scan(
        [{"ticker": "CCC"}],
        {"CCC": [{
            "date": "2026-05-15",
            "transaction_code": "A",  # award
            "insider_title": "CEO",
            "shares": 10000, "price": 100,
        }]},
        today=today
    )
    assert_eq(len(r.noise), 1, "RSU/award filtered as NOISE")

    # ----- Test 4: 10b5-1 plan sale filtered
    r = scan(
        [{"ticker": "DDD"}],
        {"DDD": [{
            "date": "2026-05-15",
            "transaction_code": "S",
            "insider_title": "CEO",
            "shares": 10000, "price": 100,  # $1M
            "rule_10b5_1": True,
        }]},
        today=today
    )
    assert_eq(len(r.noise), 1, "10b5-1 sale filtered as NOISE")
    assert_eq(len(r.bearish), 0, "10b5-1 not bearish")

    # ----- Test 5: cluster — 3 distinct insiders buy in 90d window
    r = scan(
        [{"ticker": "EEE"}],
        {"EEE": [
            {"date": "2026-05-10", "transaction_code": "P",
             "insider_name": "A", "shares": 100, "price": 100},
            {"date": "2026-04-20", "transaction_code": "P",
             "insider_name": "B", "shares": 100, "price": 100},
            {"date": "2026-04-01", "transaction_code": "P",
             "insider_name": "C", "shares": 100, "price": 100},
        ]},
        today=today
    )
    assert_eq(len(r.cluster), 1, "3 insiders buying → CLUSTER")
    assert_eq(r.cluster[0].cluster_count, 3, "cluster_count = 3")

    # ----- Test 6: cluster threshold — 2 insiders NOT a cluster
    r = scan(
        [{"ticker": "FFF"}],
        {"FFF": [
            {"date": "2026-05-10", "transaction_code": "P",
             "insider_name": "A", "shares": 100, "price": 100},
            {"date": "2026-04-20", "transaction_code": "P",
             "insider_name": "B", "shares": 100, "price": 100},
        ]},
        today=today
    )
    assert_eq(len(r.cluster), 0, "2 insiders ≠ CLUSTER")
    assert_eq(len(r.noise), 1, "2 insiders sub-$500K → NOISE")

    # ----- Test 7: cluster window — buys >90d old don't count
    r = scan(
        [{"ticker": "GGG"}],
        {"GGG": [
            {"date": "2026-05-10", "transaction_code": "P",
             "insider_name": "A", "shares": 100, "price": 100},
            {"date": "2026-04-20", "transaction_code": "P",
             "insider_name": "B", "shares": 100, "price": 100},
            {"date": "2025-12-01", "transaction_code": "P",  # >90d ago
             "insider_name": "C", "shares": 100, "price": 100},
        ]},
        today=today
    )
    assert_eq(len(r.cluster), 0, "Old buy outside window → no cluster")

    # ----- Test 8: pre-catalyst sale → FLAGGED + BEARISH
    catalysts = [{"ticker": "HHH", "date": "2026-06-05"}]  # 17d after sale
    r = scan(
        [{"ticker": "HHH"}],
        {"HHH": [{
            "date": "2026-05-19",
            "transaction_code": "S",
            "insider_title": "CFO",
            "insider_name": "X",
            "shares": 10000, "price": 100,  # $1M
        }]},
        catalysts=catalysts,
        today=today
    )
    assert_eq(len(r.flagged), 1, "pre-catalyst sale → FLAGGED")
    assert_true(r.flagged[0].pre_catalyst_sales,
                "pre_catalyst_sales list populated")

    # ----- Test 9: Trump-ally tag → FLAGGED
    r = scan(
        [{"ticker": "III"}],
        {"III": [{
            "date": "2026-05-15",
            "transaction_code": "P",
            "insider_title": "Director",
            "insider_name": "Y",
            "shares": 1000, "price": 100,  # $100K (sub-threshold for normal)
            "trump_ally": True,
        }]},
        today=today
    )
    assert_eq(len(r.flagged), 1, "Trump-ally → FLAGGED even at sub-threshold")
    assert_eq(len(r.flagged[0].trump_ally_buys), 1, "trump_ally_buys list populated")

    # ----- Test 10: macro context tag on BULLISH rate-sensitive in duration_WEAK
    theses = [{"ticker": "NVDA", "factor_tags": ["AI_complex", "long_duration_growth"]}]
    macro = {"regime_label": "duration_WEAK"}
    r = scan(
        [{"ticker": "NVDA"}],
        {"NVDA": [{
            "date": "2026-05-15",
            "transaction_code": "P",
            "insider_title": "CEO",
            "insider_name": "JH",
            "shares": 10000, "price": 100,
        }]},
        theses=theses,
        macro_pulse=macro,
        today=today
    )
    assert_eq(len(r.bullish), 1, "NVDA BULLISH on $1M CEO buy")
    assert_true(r.bullish[0].macro_context is not None,
                "macro_context populated")
    assert_true(any("rate-sensitive" in n for n in r.bullish[0].notes),
                "rate-sensitive note added")

    # ----- Test 11: empty insider data → all NOISE
    r = scan([{"ticker": "JJJ"}], {"JJJ": []}, today=today)
    assert_eq(len(r.noise), 1, "Empty insider data → NOISE")

    # ----- Test 12: missing ticker in insider_data dict
    r = scan([{"ticker": "KKK"}], {}, today=today)
    assert_eq(len(r.noise), 1, "Missing ticker → NOISE")

    # ----- Test 13: duplicates removed from positions
    r = scan(
        [{"ticker": "LLL"}, {"ticker": "LLL"}],
        {"LLL": []},
        today=today
    )
    total = len(r.bullish) + len(r.bearish) + len(r.cluster) + \
            len(r.flagged) + len(r.noise)
    assert_eq(total, 1, "Duplicate ticker scanned once")

    # ----- Test 14: surface_line with no signal
    r = scan([{"ticker": "MMM"}], {"MMM": []}, today=today)
    line = surface_line(r)
    assert_true("no signal" in line, "no-signal surface")

    # ----- Test 15: surface_line with multiple signals
    r = scan(
        [{"ticker": "X1"}, {"ticker": "X2"}],
        {
            "X1": [{
                "date": "2026-05-15", "transaction_code": "P",
                "insider_title": "CEO", "insider_name": "A",
                "shares": 10000, "price": 100,
            }],
            "X2": [{
                "date": "2026-05-15", "transaction_code": "P",
                "insider_title": "Director", "insider_name": "B",
                "shares": 100, "price": 100, "trump_ally": True,
            }],
        },
        today=today
    )
    line = surface_line(r)
    assert_true("BULLISH" in line, "surface mentions BULLISH")
    assert_true("FLAGGED" in line, "surface mentions FLAGGED")

    # ----- Test 16: text + JSON formatters run
    text = format_text_report(r)
    assert_true("INSIDER ACTIVITY SCAN" in text, "text report header")
    js = format_json_report(r)
    parsed = json.loads(js)
    assert_eq(len(parsed["bullish"]), 1, "JSON parses")

    # ----- Test 17: pre-catalyst window — sale 60d before catalyst NOT flagged
    catalysts = [{"ticker": "Z", "date": "2026-07-19"}]  # 60d after sale
    r = scan(
        [{"ticker": "Z"}],
        {"Z": [{
            "date": "2026-05-19", "transaction_code": "S",
            "insider_title": "CEO", "insider_name": "X",
            "shares": 10000, "price": 100,
        }]},
        catalysts=catalysts, today=today
    )
    assert_eq(len(r.flagged), 0, "Sale 60d before catalyst NOT flagged")

    # ----- Test 18: realistic operator portfolio scan
    positions = [
        {"ticker": "NVDA"}, {"ticker": "LEU"}, {"ticker": "MP"},
        {"ticker": "BMNR"}, {"ticker": "MU"},
    ]
    insider_data = {
        "NVDA": [
            {"date": "2026-05-10", "transaction_code": "S",
             "insider_title": "Director", "insider_name": "JF",
             "shares": 5000, "price": 250, "rule_10b5_1": True},
        ],
        "LEU": [
            {"date": "2026-05-12", "transaction_code": "P",
             "insider_title": "CEO", "insider_name": "AP",
             "shares": 4000, "price": 200},  # $800K
        ],
        "MP": [
            {"date": "2026-04-15", "transaction_code": "A",
             "insider_title": "CEO", "shares": 1000, "price": 60},
        ],
        "BMNR": [],
        "MU": [
            {"date": "2026-05-15", "transaction_code": "S",
             "insider_title": "CFO", "insider_name": "XX",
             "shares": 5000, "price": 200},  # $1M sale, no catalyst data
        ],
    }
    catalysts = [{"ticker": "MU", "date": "2026-06-10"}]  # 26d after sale
    r = scan(positions, insider_data, catalysts=catalysts, today=today)
    # NVDA = 10b5-1 → NOISE
    # LEU = $800K CEO buy → BULLISH
    # MP = award → NOISE
    # BMNR = empty → NOISE
    # MU = $1M sale 26d pre-catalyst → FLAGGED
    assert_eq(len(r.bullish), 1, "realistic: LEU bullish")
    assert_eq(r.bullish[0].ticker, "LEU", "realistic: LEU is bullish")
    assert_eq(len(r.flagged), 1, "realistic: MU flagged")
    assert_eq(r.flagged[0].ticker, "MU", "realistic: MU flagged")

    # ----- Test 19: F code (tax payment) filtered as noise
    r = scan(
        [{"ticker": "NN"}],
        {"NN": [{
            "date": "2026-05-15", "transaction_code": "F",
            "insider_title": "CEO", "shares": 1000, "price": 100,
        }]},
        today=today
    )
    assert_eq(len(r.noise), 1, "F (tax withhold) → NOISE")

    # ----- Test 20: BULLISH (not CLUSTER) when 1 distinct insider does multi-buy
    r = scan(
        [{"ticker": "PP"}],
        {"PP": [
            {"date": "2026-05-15", "transaction_code": "P",
             "insider_title": "CEO", "insider_name": "Same",
             "shares": 10000, "price": 100},  # $1M
            {"date": "2026-05-10", "transaction_code": "P",
             "insider_title": "CEO", "insider_name": "Same",
             "shares": 5000, "price": 100},  # $500K
        ]},
        today=today
    )
    # 1 distinct insider → not cluster; >$500K → bullish
    assert_eq(len(r.bullish), 1, "single insider multi-buy → BULLISH not CLUSTER")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return failed == 0


# ============================================================================
# CLI
# ============================================================================

def _safe_num(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def normalize_uw_insider(raw: Any,
                         trump_tickers: Optional[List[str]] = None
                         ) -> Dict[str, List[Dict]]:
    """Normalize raw UW get_insider_transactions output into the insider_data.json
    schema this scan consumes:
        ticker -> [{date, transaction_code, transaction_type, insider_title,
                    insider_name, shares, price, value, side, rule_10b5_1,
                    trump_ally}]

    Accepts a flat list of UW rows (each carrying a ticker), a {ticker: [rows]}
    dict, or a raw UW response dict with a "data" list.

    UW shape (confirmed against live MCP 5/14/26): `amount` = shares, `price` is
    per-share, and there is no `value` field — value is computed. TITLE handling
    matters: _is_csuite matches on the title string (CEO/CFO/COO/CTO/PRESIDENT/
    CHAIRMAN/CHIEF*/DIRECTOR), so UW's role/relationship field is preserved
    verbatim; the is_officer/is_director booleans are only a fallback and a bare
    "OFFICER" will NOT classify as C-suite. Verify UW's title field name on first
    live run.
    """
    trump = {t.upper().strip() for t in (trump_tickers or [])}

    rows: List[Dict] = []
    if isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            rows = raw["data"]
        else:
            for tk, lst in raw.items():
                if isinstance(lst, list):
                    for r in lst:
                        rr = dict(r)
                        rr.setdefault("ticker", tk)
                        rows.append(rr)
    elif isinstance(raw, list):
        rows = raw

    out: Dict[str, List[Dict]] = {}
    for r in rows:
        tk = (r.get("ticker") or r.get("symbol") or "").upper().strip()
        if not tk:
            continue
        shares = _safe_num(r.get("amount") if r.get("amount") is not None
                           else r.get("shares"))
        price = _safe_num(r.get("price"))
        value = _safe_num(r.get("value") if r.get("value") is not None
                          else r.get("notional_usd"))
        if value is None and shares is not None and price is not None:
            value = abs(shares * price)
        title = (r.get("insider_title") or r.get("officer_title")
                 or r.get("relationship") or r.get("title") or "")
        if not title:
            if r.get("is_director"):
                title = "DIRECTOR"
            elif r.get("is_officer"):
                title = "OFFICER"          # NOTE: not C-suite per _is_csuite
        code = (r.get("transaction_code") or r.get("code") or "").upper().strip()
        out.setdefault(tk, []).append({
            "date": r.get("transaction_date") or r.get("date"),
            "transaction_code": code or None,
            "transaction_type": r.get("transaction_type"),
            "insider_title": title,
            "insider_name": r.get("insider_name") or r.get("owner_name"),
            "shares": shares,
            "price": price,
            "value": value,
            "side": r.get("side"),
            "rule_10b5_1": bool(r.get("rule_10b5_1") or r.get("is_10b5_1_plan")
                                or r.get("is_10b5_1")),
            "trump_ally": bool(r.get("trump_ally")) or (tk in trump),
        })
    return out


def main():
    p = argparse.ArgumentParser(description="Insider Activity Scan v11.26")
    p.add_argument("--positions", help="Positions JSON")
    p.add_argument("--insider-data", help="Insider transaction data JSON (ticker -> txns)")
    p.add_argument("--catalysts", help="Catalysts JSON (optional)")
    p.add_argument("--theses", help="Live Theses JSON (optional)")
    p.add_argument("--macro", help="Macro pulse JSON (optional)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--surface", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--normalize-uw", metavar="RAW_JSON",
                   help="Normalize raw UW get_insider_transactions output (flat list "
                        "or ticker-keyed dict) into the insider_data.json schema")
    p.add_argument("--emit-data", metavar="OUT_JSON",
                   help="With --normalize-uw: write the normalized insider_data.json here")
    p.add_argument("--trump-tickers", metavar="CSV",
                   help="Comma-separated tickers to tag trump_ally=true during normalize")
    args = p.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if args.normalize_uw:
        with open(args.normalize_uw) as f:
            raw = json.load(f)
        trump = [t.strip() for t in (args.trump_tickers or "").split(",") if t.strip()]
        data = normalize_uw_insider(raw, trump_tickers=trump)
        if args.emit_data:
            with open(args.emit_data, "w") as f:
                json.dump(data, f, indent=2)
            n_txns = sum(len(v) for v in data.values())
            print(f"insider_data written -> {args.emit_data} "
                  f"({len(data)} tickers, {n_txns} transactions)")
        else:
            print(json.dumps(data, indent=2))
        return

    if not (args.positions and args.insider_data):
        p.error("--positions and --insider-data required (or --self-test)")

    with open(args.positions) as f:
        positions = json.load(f)
    if isinstance(positions, dict) and "positions" in positions:
        positions = positions["positions"]
    with open(args.insider_data) as f:
        insider_data = json.load(f)
    catalysts = json.load(open(args.catalysts)) if args.catalysts else None
    theses = json.load(open(args.theses)) if args.theses else None
    macro = json.load(open(args.macro)) if args.macro else None

    r = scan(positions, insider_data, catalysts, theses, macro)
    if args.surface:
        print(surface_line(r))
    elif args.json:
        print(format_json_report(r))
    else:
        print(format_text_report(r))


if __name__ == "__main__":
    main()
