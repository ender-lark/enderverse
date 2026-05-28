#!/usr/bin/env python3
"""
source_call_tracker.py — Source Call Calibration tracker
                         (v11.26 P-SOURCE-CALIBRATION · v11.29 Fix B · v11.33)

Tracks Newton/Lee/Meridian/Farrell calls by structural quality tier so we can
score whether their calls actually have edge (rather than pattern-matching on
their hits and forgetting their misses).

TIER LADDER:
- Tier A: named ticker + specific entry/stop/target + timeframe <=30 days
- Tier B: if/then conditional with named price levels and specific outcome
- Tier C: theme/sector with timeframe >=3 months
- Tier D: "should" / "favor" / "looking for" language with no falsification

USE:
- Pre-register call BEFORE outcome is known (prevents post-hoc retrofitting)
- Score Win/Loss/Push at window end
- Compute rolling hit rate by source x tier
- Discount source signal weight in Two-Lens Cat 1 based on hit rate band

v11.29 Fix B — single-source persistence detection:
- persistence_scan() — tier-blind count of one source repeating one ticker in a
  rolling window. Catches the *soloist* the >=3-independent-streams convergence
  trigger is structurally deaf to. LOUD on a non-core ticker (-> P-WAKE-UP +
  Signal Log), QUIET on a core-monitored ticker (logged only).
- compute_hit_rate() backfill guard — backfill:true rows excluded from the
  scored A+B denominator (Hard Rule 7), still feed the persistence detector.

v11.33:
- MACRO_INDEX_TICKERS — broad index / rate tickers route persistence clusters
  to QUIET (a macro strategist references the index they cover on nearly every
  note; a cluster on it is baseline activity, not a single-name escalation).
- hit_rates_report() + --hit-rates — generates source_rates.json (the shape
  pretrade_gate.py consumes), making the prior CI reference real.

CLI:
    python source_call_tracker.py --self-test
    python source_call_tracker.py --classify "verbatim quote" --source newton
    python source_call_tracker.py --persistence --calls source_calls.json \\
        [--core-tickers BMNR,LEU,MU] [--now YYYY-MM-DD] \\
        [--window-days 30] [--loud-threshold 3] \\
        [--accel-window 14] [--accel-threshold 2]
    python source_call_tracker.py --hit-rates --calls source_calls.json \\
        [--out source_rates.json]
"""

import re
import json
import sys
from datetime import datetime, timedelta
from typing import Optional


# ==============================================================================
# Classifier heuristics
# ==============================================================================

TIER_A_ACTION_KEYWORDS = [
    'stop', 'target', 'entry', 'buy at', 'sell at', 'add at', 'trim at',
    'buy ', 'sell ', 'add ', 'trim '
]

TIER_B_CONDITIONAL_LANG = [
    'if ', 'should close', 'breaks below', 'breaks above',
    'closes below', 'closes above', 'trades below', 'trades above',
    'weekly close', 'daily close', 'confirms', 'breakout above',
    'breakdown below'
]

TIER_C_LONG_TIMEFRAME = [
    'quarter', 'months', '3-6 months', 'next 6 months',
    'rest of year', 'h2', 'second half', 'into 2027', 'over the year',
    'over the next year'
]

TIER_C_BROAD_LANG = [
    'sector', 'theme', 'space', 'group', 'broad market', 'asset class',
    'rotation into', 'positioning'
]

TIER_D_SOFT_LANG = [
    'should ', 'favor', 'looking for', 'expect', 'anticipate',
    'leaning toward', 'continues to', 'in our view',
    'bias remains', 'view remains', 'we think', 'we believe', 'likely '
]

SHORT_TIMEFRAME_LANG = [
    'this week', 'next week', '5 days', '10 days', '30 days', '2 weeks',
    'by friday', 'by month-end', 'mid-may', 'late may', 'early june',
    'into late may', '5/26', 'by 5/'
]

# Filter false-positive tickers (common 2-3 letter English words)
TICKER_FALSE_POSITIVES = {
    'US', 'A', 'I', 'IF', 'AT', 'TO', 'IS', 'BE', 'OR', 'AS', 'BY', 'IN',
    'ON', 'WE', 'IT', 'AM', 'PM', 'AI', 'TV', 'CEO', 'CFO', 'EPS', 'OEM',
    'AND', 'THE', 'FOR', 'ANY', 'NEW', 'OUR', 'NOT', 'ALL', 'CAN', 'HAS',
    'HAD', 'WAS', 'BUT', 'YOU', 'HIS', 'HER', 'OUT', 'WHO', 'GET', 'SEE',
    'NOW', 'MAY', 'EOM', 'GDP', 'CPI', 'PPI', 'FED', 'ECB', 'FOMC',
    'YTD', 'QTD', 'WTD', 'DTE', 'ATH', 'ATL', 'PT'
}

# ------------------------------------------------------------------------------
# v11.33 — broad index / rate tickers. A persistence cluster on one of these
# routes QUIET regardless of held/core status: a macro strategist references
# the index they cover on nearly every note, so a cluster on it is baseline
# activity, not a single-name escalation signal. Tunable.
# ------------------------------------------------------------------------------
MACRO_INDEX_TICKERS = {
    # equity indices / index ETFs / index futures
    'SPX', 'SPY', 'ES', 'SP500', 'SP', 'QQQ', 'NQ', 'NDX', 'IWM', 'RUT',
    'DIA', 'DJI', 'DJIA', 'MID', 'MDY', 'VTI', 'OEF',
    # volatility
    'VIX', 'VX', 'VXX', 'UVXY', 'MOVE',
    # rates / treasuries
    '2Y', '5Y', '7Y', '10Y', '20Y', '30Y', 'US2Y', 'US5Y', 'US10Y',
    'US30Y', 'TNX', 'TYX', 'IRX', 'FVX', 'UST',
    'TLT', 'IEF', 'SHY', 'GOVT', 'BND', 'AGG', 'TBT',
    # credit / dollar (macro overlays a strategist cites constantly)
    'HYG', 'LQD', 'JNK', 'DXY', 'UUP',
}


def classify_call(text: str) -> dict:
    """
    Classify a verbatim source call into tier A/B/C/D.
    Returns dict: tier, confidence, indicators, falsification, window_days, window_end.
    """
    text_lower = text.lower()

    tickers_raw = re.findall(r'\b([A-Z]{2,5})\b', text)
    tickers = [t for t in tickers_raw if t not in TICKER_FALSE_POSITIVES]
    prices_dollar = re.findall(r'\$\d+(?:\.\d+)?', text)
    levels_bare = re.findall(r'\b\d{2,5}(?:\.\d+)?\b', text)
    has_level = bool(prices_dollar or levels_bare)

    has_action = any(kw in text_lower for kw in TIER_A_ACTION_KEYWORDS)
    has_conditional = any(c in text_lower for c in TIER_B_CONDITIONAL_LANG)
    has_short_tf = any(tf in text_lower for tf in SHORT_TIMEFRAME_LANG)
    has_long_tf = any(tf in text_lower for tf in TIER_C_LONG_TIMEFRAME)
    has_broad = any(bl in text_lower for bl in TIER_C_BROAD_LANG)
    has_soft = any(sl in text_lower for sl in TIER_D_SOFT_LANG)

    # Decision tree — order matters
    if tickers and has_action and has_level and has_short_tf:
        tier, confidence = 'A', 'HIGH'
    elif has_conditional and has_level:
        tier, confidence = 'B', 'HIGH'
    elif tickers and has_action and has_level:
        tier, confidence = 'A', 'MED'  # Missing tight timeframe
    elif (has_broad or has_long_tf) and not has_action:
        tier, confidence = 'C', 'MED'
    elif has_soft and not (has_action and has_level):
        tier, confidence = 'D', 'HIGH'
    elif tickers and has_level:
        tier, confidence = 'B', 'MED'
    else:
        tier, confidence = 'D', 'LOW'

    # Falsification text
    if tier == 'A':
        falsification = (
            f"FALSIFIED if {tickers[:3]} fails to reach stated target within window, "
            f"OR stop hit before target"
        )
    elif tier == 'B':
        first_level = (prices_dollar or levels_bare)[0] if has_level else 'stated level'
        if any(x in text_lower for x in ['close below', 'closes below', 'breaks below',
                                          'trades below', 'breakdown below']):
            falsification = f"FALSIFIED if price closes ABOVE {first_level} within window"
        elif any(x in text_lower for x in ['close above', 'closes above', 'breaks above',
                                            'trades above', 'breakout above']):
            falsification = f"FALSIFIED if price closes BELOW {first_level} within window"
        else:
            falsification = f"FALSIFIED if stated condition does not produce stated outcome within window"
    elif tier == 'C':
        falsification = "Hard to falsify; score directional accuracy only at window end"
    else:
        falsification = "Unfalsifiable narrative — DO NOT SCORE; track for hit-rate denominator transparency only"

    # Window
    if has_short_tf:
        window_days = 14
    elif has_conditional:
        window_days = 30
    elif has_long_tf:
        window_days = 120
    else:
        window_days = 60

    return {
        'tier': tier,
        'confidence': confidence,
        'tickers_detected': tickers,
        'indicators': {
            'action_keyword': has_action,
            'conditional_lang': has_conditional,
            'has_level': has_level,
            'short_timeframe': has_short_tf,
            'long_timeframe': has_long_tf,
            'broad_language': has_broad,
            'soft_language': has_soft,
        },
        'falsification': falsification,
        'window_days': window_days,
        'window_end': (datetime.now() + timedelta(days=window_days)).strftime('%Y-%m-%d'),
    }


# ==============================================================================
# Schema adapter (v11.29/v11.33) — tolerant of both the canonical and the
# legacy `sample_inputs/` field names. Confirmed 5/27/26: the shipped
# source_calls.json used named_ticker/call_date/status/scoring_deadline, which
# the tracker never read — the calibration layer was silently parsing nothing.
# These helpers make the script robust to whichever schema it is fed.
# ==============================================================================

_STATUS_MAP = {
    'pending': 'Pending', 'win': 'Win', 'loss': 'Loss',
    'push': 'Push', 'unscored': 'Unscored',
}


def _parse_date(s):
    """Parse 'YYYY-MM-DD' or a full ISO timestamp -> date. None on failure."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s.date()
    s = str(s).strip()
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        pass
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _is_backfill(c) -> bool:
    """Normalize a backfill flag: bool / 'true' / '__YES__' / 'yes' / '1' -> bool.
    Missing key -> False (backward-compatible with pre-v11.29 call dicts)."""
    v = c.get('backfill', False)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ('true', 'yes', '__yes__', '1', 'y')
    return bool(v)


def _status_to_outcome(status):
    """Map a legacy `status` value to the canonical `outcome` vocabulary."""
    if not status:
        return None
    return _STATUS_MAP.get(str(status).strip().lower())


def _normalize_call(raw: dict) -> Optional[dict]:
    """Map a source-call dict (legacy OR canonical schema) to the canonical
    schema source_call_tracker keys on.

    Canonical : source / ticker / date / outcome / window_end / tier / backfill
    Legacy    : Source / named_ticker / call_date / status / scoring_deadline

    Returns None for non-dicts or dicts with no `source` (e.g. comment rows).
    """
    if not isinstance(raw, dict):
        return None
    src = raw.get('source')
    if not src:
        return None

    ticker = raw.get('ticker') or raw.get('named_ticker')
    if ticker:
        ticker = str(ticker).strip().upper()
        if ticker in ('', 'TBD', 'N/A', 'NA', 'NONE'):
            ticker = None

    date = raw.get('date') or raw.get('call_date')
    outcome = raw.get('outcome') or _status_to_outcome(raw.get('status'))
    window_end = raw.get('window_end') or raw.get('scoring_deadline')

    tier = raw.get('tier')
    if tier:
        tier = str(tier).strip().upper()

    return {
        'source': str(src).strip().lower(),
        'ticker': ticker,
        'tickers_touched': raw.get('tickers_touched'),
        'tier': tier,
        'outcome': outcome,
        'date': date,
        'window_end': window_end,
        'backfill': _is_backfill(raw),
        'verbatim_quote': raw.get('verbatim_quote'),
        'falsification_condition': raw.get('falsification_condition'),
        'call_summary': raw.get('call_summary'),
        'confidence_in_tier': raw.get('confidence_in_tier'),
        'classified_at': raw.get('classified_at'),
        'notion_url': raw.get('notion_url'),
        'id': raw.get('id'),
    }


def load_calls(path: str) -> list:
    """Load and normalize a source_calls JSON file.

    Accepts a top-level list (canonical) or a {'calls': [...]} object. Each
    entry is passed through _normalize_call; comment / non-call entries
    (anything without a `source`) are skipped.
    """
    with open(path) as f:
        data = json.load(f)
    raw_list = data if isinstance(data, list) else data.get('calls', [])
    out = []
    for r in raw_list:
        nc = _normalize_call(r)
        if nc is not None:
            out.append(nc)
    return out


# ==============================================================================
# Hit rate computation
# ==============================================================================

DISCOUNT_BANDS = [
    # (max_hit_rate, band_label, discount_factor)
    (0.40, 'CONSISTENT_MISS', 0.25),
    (0.50, 'BELOW_BREAKEVEN', 0.50),
    (0.70, 'NORMAL', 1.00),
    (1.01, 'HIGH_CONVICTION', 1.25),
]

MIN_N_FOR_BANDING = 15


def compute_hit_rate(calls: list, source: Optional[str] = None,
                     tiers: Optional[list] = None) -> dict:
    """
    Rolling hit rate by source x tier. Default scores A+B only.
    Pushes excluded from denominator (neither win nor loss).

    v11.29 Hard Rule 7 — backfill guard: a call logged AFTER its outcome is
    already known carries backfill:true and is excluded from the scored
    denominator (logging an outcome-known call into the rate would be marking
    our own homework). Backfill rows still feed persistence_scan().
    """
    if tiers is None:
        tiers = ['A', 'B']

    scored = [c for c in calls
              if c.get('outcome') in {'Win', 'Loss', 'Push'}
              and c.get('tier') in tiers
              and not _is_backfill(c)
              and (source is None or c.get('source') == source)]

    wins = sum(1 for c in scored if c['outcome'] == 'Win')
    losses = sum(1 for c in scored if c['outcome'] == 'Loss')
    pushes = sum(1 for c in scored if c['outcome'] == 'Push')
    n = wins + losses

    if n == 0:
        return {'n': 0, 'wins': 0, 'losses': 0, 'pushes': pushes,
                'hit_rate': None, 'tier_band': 'NO_DATA',
                'discount_factor': 1.0, 'source': source,
                'tiers_filtered': tiers,
                'note': 'No scored calls in this source x tier slice'}

    hit_rate = wins / n

    if n < MIN_N_FOR_BANDING:
        band = 'INSUFFICIENT_DATA'
        discount = 1.0
    else:
        band, discount = next(
            (label, disc) for (cap, label, disc) in DISCOUNT_BANDS
            if hit_rate < cap
        )

    return {
        'n': n,
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'hit_rate': round(hit_rate, 4),
        'tier_band': band,
        'discount_factor': discount,
        'source': source,
        'tiers_filtered': tiers,
    }


def surface_line(calls: list) -> str:
    """One-line pre-flight surface (SOURCE CALIB)."""
    sources = sorted(set(c.get('source', '?') for c in calls))
    parts = []
    for src in sources:
        r = compute_hit_rate(calls, source=src, tiers=['A', 'B'])
        if r['n'] == 0:
            parts.append(f"{src}: 0 scored")
        elif r['tier_band'] == 'INSUFFICIENT_DATA':
            parts.append(f"{src}: {r['n']}/{MIN_N_FOR_BANDING} A+B")
        else:
            hr_pct = int(r['hit_rate'] * 100)
            parts.append(f"{src}: {hr_pct}% A+B (n={r['n']}, {r['tier_band']})")

    today = datetime.now().strftime('%Y-%m-%d')
    pending = sum(1 for c in calls if c.get('outcome') == 'Pending')
    overdue = sum(1 for c in calls
                  if c.get('outcome') == 'Pending'
                  and c.get('window_end', '9999-12-31') < today)
    return (f"SOURCE CALIB: {' · '.join(parts)} · "
            f"{pending} pending ({overdue} overdue for scoring)")


# ==============================================================================
# Single-source persistence detection (v11.29 Fix B)
# ==============================================================================

def persistence_scan(calls: list, core_tickers=None, now=None,
                     window_days: int = 30, loud_threshold: int = 3,
                     accel_window: int = 14, accel_threshold: int = 2,
                     macro_index_tickers=None) -> list:
    """
    Tier-blind single-source persistence detector (v11.29 Fix B).

    Counts, per (source, ticker), how many times one source mentioned one
    ticker inside a trailing rolling window. Catches the *soloist* the
    >=3-independent-streams convergence trigger is structurally deaf to.

    Fire conditions (per source x ticker):
      - count >= loud_threshold within window_days, OR
      - count >= accel_threshold within accel_window AND any of those
        mentions is Tier A/B (a structured call repeated even twice is
        higher-signal than soft narrative repeated thrice).

    Escalation gate — core-monitored, NOT held-vs-unheld:
      - ticker in core_tickers          -> QUIET (quiet_reason 'core')
      - ticker in macro_index_tickers   -> QUIET (quiet_reason 'macro_index', v11.33)
      - otherwise                       -> LOUD (fires P-WAKE-UP + Signal Log row)

    Tier-blind by design: crypto / long-horizon thematic theses arrive as
    Tier C/D; counting them regardless of tier is the point. Backfill rows DO
    feed this detector (only excluded from hit-rate scoring, never persistence).

    All four thresholds are parameters — flagged for recalibration at the 6/28
    retrospective once the Source Call Log has density.

    Returns: list of cluster dicts, LOUD first then count desc. Each cluster:
      {source, ticker, count, within_days, has_ab, loud, quiet_reason, fired_on}
    """
    # Resolve `now` to a date
    if now is None:
        now_d = datetime.now().date()
    elif isinstance(now, str):
        now_d = _parse_date(now) or datetime.now().date()
    elif isinstance(now, datetime):
        now_d = now.date()
    else:
        now_d = now  # assume date

    core = {str(t).strip().upper() for t in (core_tickers or [])}
    macro = {str(t).strip().upper() for t in
             (macro_index_tickers if macro_index_tickers is not None
              else MACRO_INDEX_TICKERS)}

    # Group normalized calls by (source, ticker)
    groups: dict = {}
    for c in calls:
        nc = _normalize_call(c)
        if nc is None:
            continue
        src = nc.get('source')
        tkr = nc.get('ticker')
        d = _parse_date(nc.get('date'))
        if not src or not tkr or d is None:
            continue
        groups.setdefault((src, tkr), []).append({
            'date': d, 'tier': (nc.get('tier') or '').upper(),
        })

    clusters = []
    for (src, tkr), mentions in groups.items():
        in_window = [m for m in mentions
                     if 0 <= (now_d - m['date']).days <= window_days]
        in_accel = [m for m in mentions
                    if 0 <= (now_d - m['date']).days <= accel_window]
        count_w = len(in_window)
        count_a = len(in_accel)
        accel_has_ab = any(m['tier'] in ('A', 'B') for m in in_accel)

        fires_main = count_w >= loud_threshold
        fires_accel = count_a >= accel_threshold and accel_has_ab
        if not (fires_main or fires_accel):
            continue

        if fires_main:
            count, within, fired_on = count_w, window_days, 'main'
            has_ab = any(m['tier'] in ('A', 'B') for m in in_window)
        else:
            count, within, fired_on = count_a, accel_window, 'accel'
            has_ab = accel_has_ab

        if tkr in core:
            loud, reason = False, 'core'
        elif tkr in macro:
            loud, reason = False, 'macro_index'
        else:
            loud, reason = True, None

        clusters.append({
            'source': src,
            'ticker': tkr,
            'count': count,
            'within_days': within,
            'has_ab': has_ab,
            'loud': loud,
            'quiet_reason': reason,
            'fired_on': fired_on,
        })

    # LOUD first, then by count descending
    clusters.sort(key=lambda c: (not c['loud'], -c['count']))
    return clusters


def persistence_surface_line(clusters: list) -> str:
    """One-line SOURCE PERSISTENCE pre-flight surface (v11.29).

    Quiet-output discipline: returns '' when there are no clusters, so the
    line only appears on a hit. LOUD clusters add the P-WAKE-UP + Signal Log
    routing note to the header.
    """
    if not clusters:
        return ''
    n = len(clusters)
    loud = sum(1 for c in clusters if c['loud'])
    head = f"SOURCE PERSISTENCE: {n} cluster(s), {loud} LOUD"
    if loud:
        head += " -> P-WAKE-UP + Signal Log"
    parts = []
    for c in clusters:
        tag = 'LOUD' if c['loud'] else 'quiet'
        if c['has_ab']:
            tag += ', has A/B'
        parts.append(f"{c['source']}->{c['ticker']} "
                     f"{c['count']}x in {c['within_days']}d [{tag}]")
    return f"{head}: {' · '.join(parts)}"


# ==============================================================================
# Hit-rate report (v11.33) — generates the source_rates.json structure
# ==============================================================================

CANONICAL_SOURCES = ['newton', 'lee', 'meridian', 'farrell']


def hit_rates_report(calls: list, sources=None) -> dict:
    """
    Build the source_rates.json structure (v11.33) — per source x tier band/n,
    the exact shape pretrade_gate.py consumes ({<source>: {<tier>: {band, n,
    ...}}}). Tier D -> NOT_SCORED; n<15 -> INSUFFICIENT_DATA. Backfill rows are
    excluded from scored n via compute_hit_rate()'s backfill guard.
    """
    norm = [n for n in (_normalize_call(c) for c in calls) if n is not None]
    present = sorted({c['source'] for c in norm if c.get('source')})
    if sources is None:
        sources = list(dict.fromkeys(CANONICAL_SOURCES + present))

    report = {
        '_comment': ('Source x tier hit-rate calibration state. Generated by '
                     'source_call_tracker.py --hit-rates. Backfill rows '
                     'excluded from scored n (Hard Rule 7). n<15 per '
                     'source x tier -> INSUFFICIENT_DATA.'),
        'snapshot_date': datetime.now().strftime('%Y-%m-%d'),
    }
    for src in sources:
        tiers = {}
        for tier in ('A', 'B', 'C', 'D'):
            if tier == 'D':
                tiers['D'] = {'band': 'NOT_SCORED', 'n': 0,
                              'wins': 0, 'losses': 0, 'pushes': 0,
                              'hit_rate': None}
                continue
            r = compute_hit_rate(norm, source=src, tiers=[tier])
            band = r['tier_band']
            if band == 'NO_DATA':
                band = 'INSUFFICIENT_DATA'
            tiers[tier] = {
                'band': band,
                'n': r['n'],
                'wins': r['wins'],
                'losses': r['losses'],
                'pushes': r['pushes'],
                'hit_rate': r['hit_rate'],
            }
        report[src] = tiers
    return report


# ==============================================================================
# Self-test
# ==============================================================================

def run_self_test():
    passed, total = 0, 0

    def check(name, condition):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
        else:
            print(f"  FAIL: {name}")

    # ----------------------------------------------------------------------
    # v11.26 baseline (27 checks) — unchanged
    # ----------------------------------------------------------------------

    # Tier A
    r = classify_call("Buy NVDA at $215 with stop $208 target $245 by end of next week")
    check("Tier A — named ticker + entry/stop/target + short TF", r['tier'] == 'A')

    r = classify_call("Add LEU at $170 stop $160 target $235 in 30 days")
    check("Tier A — LEU named with full spec", r['tier'] == 'A')

    # Tier B
    r = classify_call("If SPX closes below 7375, expect 3-5% pullback into late May")
    check("Tier B — conditional + level", r['tier'] == 'B')

    r = classify_call("30Y weekly close above 5.15 confirms triangle breakout")
    check("Tier B — Newton 30Y breakout call", r['tier'] == 'B')

    r = classify_call("QQQ breaks below 707.64 confirms correction setup")
    check("Tier B — QQQ break level", r['tier'] == 'B')

    # Tier C
    r = classify_call("Software sector remains attractive over the next 3-6 months")
    check("Tier C — sector + long TF", r['tier'] == 'C')

    # Tier D
    r = classify_call("We should see a rebound by mid-July to August")
    check("Tier D — 'should' + broad window", r['tier'] == 'D')

    r = classify_call("Looking for a low to develop here")
    check("Tier D — 'looking for'", r['tier'] == 'D')

    r = classify_call("Bias remains constructive on small caps")
    check("Tier D — 'bias remains'", r['tier'] == 'D')

    r = classify_call("We continue to favor the AI theme into 2027")
    check("Tier D — 'continue to favor' (soft, no action)", r['tier'] in ('C', 'D'))

    # Falsification direction
    r = classify_call("If SPX closes below 7375, expect pullback")
    check("Falsification flips direction (below->above)",
          'ABOVE' in r['falsification'])

    r = classify_call("Weekly close above 5.15 confirms breakout")
    check("Falsification flips direction (above->below)",
          'BELOW' in r['falsification'])

    # Hit rate math
    sample = [
        {'source': 'newton', 'tier': 'A', 'outcome': 'Win'},
        {'source': 'newton', 'tier': 'A', 'outcome': 'Win'},
        {'source': 'newton', 'tier': 'A', 'outcome': 'Loss'},
        {'source': 'newton', 'tier': 'B', 'outcome': 'Win'},
        {'source': 'newton', 'tier': 'B', 'outcome': 'Loss'},
        {'source': 'newton', 'tier': 'D', 'outcome': 'Win'},  # excluded
    ]
    r = compute_hit_rate(sample, source='newton')
    check("Hit rate n excludes Tier D", r['n'] == 5)
    check("Hit rate wins counts correctly", r['wins'] == 3)
    check("Hit rate = 60%", r['hit_rate'] == 0.6)
    check("Below MIN_N → INSUFFICIENT_DATA", r['tier_band'] == 'INSUFFICIENT_DATA')
    check("Insufficient data → no discount", r['discount_factor'] == 1.0)

    # Below breakeven banding (n>=15, hit_rate 7/17 = 41%)
    big_low = [{'source': 'newton', 'tier': 'A', 'outcome': 'Loss'} for _ in range(10)] + \
              [{'source': 'newton', 'tier': 'A', 'outcome': 'Win'} for _ in range(7)]
    r = compute_hit_rate(big_low, source='newton')
    check("Below-breakeven band fires at 41% n=17", r['tier_band'] == 'BELOW_BREAKEVEN')
    check("Below-breakeven discount = 0.50", r['discount_factor'] == 0.50)

    # Consistent miss banding (n>=15, hit_rate < 40%)
    big_miss = [{'source': 'newton', 'tier': 'A', 'outcome': 'Loss'} for _ in range(12)] + \
               [{'source': 'newton', 'tier': 'A', 'outcome': 'Win'} for _ in range(5)]
    r = compute_hit_rate(big_miss, source='newton')
    check("Consistent-miss band fires at 29%", r['tier_band'] == 'CONSISTENT_MISS')
    check("Consistent-miss discount = 0.25", r['discount_factor'] == 0.25)

    # High conviction banding (n>=15, hit_rate >= 70%)
    big_hc = [{'source': 'newton', 'tier': 'A', 'outcome': 'Win'} for _ in range(15)] + \
             [{'source': 'newton', 'tier': 'A', 'outcome': 'Loss'} for _ in range(5)]
    r = compute_hit_rate(big_hc, source='newton')
    check("High-conviction band fires at 75%", r['tier_band'] == 'HIGH_CONVICTION')
    check("High-conviction discount = 1.25", r['discount_factor'] == 1.25)

    # Push handling
    push_sample = [
        {'source': 'lee', 'tier': 'A', 'outcome': 'Win'},
        {'source': 'lee', 'tier': 'A', 'outcome': 'Push'},
        {'source': 'lee', 'tier': 'A', 'outcome': 'Loss'},
    ]
    r = compute_hit_rate(push_sample, source='lee')
    check("Push excluded from n", r['n'] == 2)
    check("Push counted in pushes field", r['pushes'] == 1)

    # Surface line
    line = surface_line(sample)
    check("Surface line includes SOURCE CALIB tag", 'SOURCE CALIB' in line)
    check("Surface line includes source name", 'newton' in line)

    # ----------------------------------------------------------------------
    # v11.29 / v11.33 additions
    # ----------------------------------------------------------------------

    # --- Block 1: _normalize_call schema adapter (5) ---
    nc = _normalize_call({'source': 'Newton', 'named_ticker': 'NVDA',
                          'call_date': '2026-05-15', 'status': 'pending',
                          'tier': 'a'})
    check("normalize: legacy named_ticker -> ticker", nc['ticker'] == 'NVDA')
    check("normalize: legacy call_date -> date", nc['date'] == '2026-05-15')
    check("normalize: legacy status 'pending' -> outcome 'Pending'",
          nc['outcome'] == 'Pending')
    check("normalize: source lowercased + tier uppercased",
          nc['source'] == 'newton' and nc['tier'] == 'A')
    nc_bf = _normalize_call({'source': 'farrell', 'ticker': 'HYPE',
                             'date': '2026-05-01', 'backfill': '__YES__'})
    check("normalize: backfill '__YES__' -> True", nc_bf['backfill'] is True)

    # --- Block 2: _is_backfill + compute_hit_rate backfill guard (4) ---
    check("_is_backfill: missing key -> False",
          _is_backfill({'source': 'x'}) is False)
    check("_is_backfill: bool True -> True",
          _is_backfill({'backfill': True}) is True)
    bf_calls = [
        {'source': 'newton', 'tier': 'A', 'outcome': 'Win'},
        {'source': 'newton', 'tier': 'A', 'outcome': 'Loss'},
        {'source': 'newton', 'tier': 'A', 'outcome': 'Win', 'backfill': True},
    ]
    r = compute_hit_rate(bf_calls, source='newton')
    check("backfill guard: backfill row excluded from n", r['n'] == 2)
    check("backfill guard: backfill Win not counted in wins", r['wins'] == 1)

    # --- Block 3: persistence_scan (14) ---
    NOW = '2026-05-27'

    def _m(src, tkr, d, tier='C', backfill=False):
        return {'source': src, 'ticker': tkr, 'date': d, 'tier': tier,
                'backfill': backfill}

    cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27'),
         _m('farrell', 'HYPE', '2026-05-18'),
         _m('farrell', 'HYPE', '2026-05-08')], now=NOW)
    check("persistence: 3-in-30d non-core fires", len(cl) == 1)
    check("persistence: non-core cluster is LOUD", bool(cl) and cl[0]['loud'] is True)
    check("persistence: LOUD cluster quiet_reason is None",
          bool(cl) and cl[0]['quiet_reason'] is None)

    cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27'),
         _m('farrell', 'HYPE', '2026-05-08')], now=NOW)
    check("persistence: 2-in-30d does not fire", len(cl) == 0)

    cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27', tier='A'),
         _m('farrell', 'HYPE', '2026-05-20', tier='C')], now=NOW)
    check("persistence: 2-in-14d with Tier A fires (accel)", len(cl) == 1)
    check("persistence: accel cluster reports has_ab",
          bool(cl) and cl[0]['has_ab'] is True)

    cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27', tier='D'),
         _m('farrell', 'HYPE', '2026-05-20', tier='D')], now=NOW)
    check("persistence: 2-in-14d all C/D does not fire", len(cl) == 0)

    cl = persistence_scan(
        [_m('newton', 'BMNR', '2026-05-27'),
         _m('newton', 'BMNR', '2026-05-18'),
         _m('newton', 'BMNR', '2026-05-08')],
        core_tickers={'BMNR'}, now=NOW)
    check("persistence: core ticker -> QUIET (loud False)",
          bool(cl) and cl[0]['loud'] is False)
    check("persistence: core QUIET reason is 'core'",
          bool(cl) and cl[0]['quiet_reason'] == 'core')

    cl = persistence_scan(
        [_m('lee', 'SPX', '2026-05-27'),
         _m('lee', 'SPX', '2026-05-18'),
         _m('lee', 'SPX', '2026-05-08')], now=NOW)
    check("persistence: macro index -> QUIET reason 'macro_index'",
          bool(cl) and cl[0]['quiet_reason'] == 'macro_index')

    cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27', tier='D'),
         _m('farrell', 'HYPE', '2026-05-18', tier='D'),
         _m('farrell', 'HYPE', '2026-05-08', tier='D')], now=NOW)
    check("persistence: tier-blind — 3 Tier-D mentions fire", len(cl) == 1)

    cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27'), _m('farrell', 'HYPE', '2026-05-18'),
         _m('farrell', 'HYPE', '2026-05-08'),
         _m('newton', 'MU', '2026-05-27'), _m('newton', 'MU', '2026-05-18'),
         _m('newton', 'MU', '2026-05-08')], now=NOW)
    check("persistence: two distinct groups -> 2 clusters", len(cl) == 2)

    cl = persistence_scan(
        [_m('farrell', 'OLDX', '2026-05-27'),
         _m('farrell', 'OLDX', '2026-05-20'),
         _m('farrell', 'OLDX', '2026-01-01')], now=NOW)
    check("persistence: mention outside 30d window excluded (no fire at 2)",
          len(cl) == 0)

    cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27'),
         _m('farrell', 'HYPE', '2026-05-18'),
         _m('farrell', 'HYPE', '2026-05-08', backfill=True)], now=NOW)
    check("persistence: backfill mentions feed the detector", len(cl) == 1)

    # --- Block 4: persistence_surface_line (5) ---
    check("surface line: empty clusters -> '' (quiet-output)",
          persistence_surface_line([]) == '')
    loud_cl = persistence_scan(
        [_m('farrell', 'HYPE', '2026-05-27'), _m('farrell', 'HYPE', '2026-05-18'),
         _m('farrell', 'HYPE', '2026-05-08')], now=NOW)
    line = persistence_surface_line(loud_cl)
    check("surface line: contains SOURCE PERSISTENCE tag",
          'SOURCE PERSISTENCE' in line)
    check("surface line: LOUD cluster mentions P-WAKE-UP", 'P-WAKE-UP' in line)
    quiet_cl = persistence_scan(
        [_m('newton', 'BMNR', '2026-05-27'), _m('newton', 'BMNR', '2026-05-18'),
         _m('newton', 'BMNR', '2026-05-08')], core_tickers={'BMNR'}, now=NOW)
    qline = persistence_surface_line(quiet_cl)
    check("surface line: all-quiet -> no P-WAKE-UP", 'P-WAKE-UP' not in qline)
    check("surface line: per-cluster format has '->' and 'x in'",
          '->' in line and 'x in' in line)

    # --- Block 5: hit_rates_report (8) ---
    hr_calls = (
        [{'source': 'newton', 'tier': 'A', 'outcome': 'Win'} for _ in range(15)] +
        [{'source': 'lee', 'tier': 'A', 'outcome': 'Win'} for _ in range(5)] +
        [{'source': 'meridian', 'tier': 'A', 'outcome': 'Win'} for _ in range(14)] +
        [{'source': 'meridian', 'tier': 'A', 'outcome': 'Win', 'backfill': True}]
    )
    rep = hit_rates_report(hr_calls)
    check("hit_rates_report: has snapshot_date", 'snapshot_date' in rep)
    check("hit_rates_report: has all 4 canonical sources",
          all(s in rep for s in ('newton', 'lee', 'meridian', 'farrell')))
    check("hit_rates_report: source has A/B/C/D keys",
          all(t in rep['newton'] for t in ('A', 'B', 'C', 'D')))
    check("hit_rates_report: Tier D -> NOT_SCORED",
          rep['newton']['D']['band'] == 'NOT_SCORED')
    check("hit_rates_report: 15 A-wins -> HIGH_CONVICTION",
          rep['newton']['A']['band'] == 'HIGH_CONVICTION')
    check("hit_rates_report: n<15 -> INSUFFICIENT_DATA",
          rep['lee']['A']['band'] == 'INSUFFICIENT_DATA')
    check("hit_rates_report: backfill excluded from report n (14 not 15)",
          rep['meridian']['A']['n'] == 14)
    check("hit_rates_report: tier dict carries n/wins/losses keys",
          all(k in rep['newton']['A'] for k in ('n', 'wins', 'losses')))

    # --- Block 6: MACRO_INDEX_TICKERS (5) ---
    check("MACRO_INDEX_TICKERS: SPX present", 'SPX' in MACRO_INDEX_TICKERS)
    check("MACRO_INDEX_TICKERS: QQQ present", 'QQQ' in MACRO_INDEX_TICKERS)
    check("MACRO_INDEX_TICKERS: 30Y present", '30Y' in MACRO_INDEX_TICKERS)
    check("MACRO_INDEX_TICKERS: VIX present", 'VIX' in MACRO_INDEX_TICKERS)
    check("MACRO_INDEX_TICKERS: NVDA not in set", 'NVDA' not in MACRO_INDEX_TICKERS)

    return passed, total


# ==============================================================================
# CLI
# ==============================================================================

def _cli_arg(name, default=None):
    """Fetch the value following a --flag in sys.argv, else default."""
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == '--self-test':
        p, t = run_self_test()
        print(f"\n{p}/{t} assertions passed")
        sys.exit(0 if p == t else 1)

    if cmd == '--classify':
        text = sys.argv[2] if len(sys.argv) > 2 else ''
        source = _cli_arg('--source', 'unknown') or 'unknown'
        result = classify_call(text)
        result['source'] = source
        result['verbatim'] = text
        result['classified_at'] = datetime.now().isoformat()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    if cmd == '--persistence':
        calls_path = _cli_arg('--calls', 'source_calls.json')
        try:
            calls = load_calls(calls_path)
        except FileNotFoundError:
            print(f"ERROR: --calls file not found: {calls_path}", file=sys.stderr)
            sys.exit(1)
        core_arg = _cli_arg('--core-tickers')
        core = ({t.strip().upper() for t in core_arg.split(',') if t.strip()}
                if core_arg else set())
        now = _cli_arg('--now')
        kw = {}
        for flag, key in [('--window-days', 'window_days'),
                          ('--loud-threshold', 'loud_threshold'),
                          ('--accel-window', 'accel_window'),
                          ('--accel-threshold', 'accel_threshold')]:
            v = _cli_arg(flag)
            if v is not None:
                kw[key] = int(v)
        clusters = persistence_scan(calls, core_tickers=core, now=now, **kw)
        print(json.dumps({
            'calls_loaded': len(calls),
            'clusters': clusters,
            'surface_line': persistence_surface_line(clusters),
        }, indent=2, default=str))
        sys.exit(0)

    if cmd == '--hit-rates':
        calls_path = _cli_arg('--calls', 'source_calls.json')
        try:
            calls = load_calls(calls_path)
        except FileNotFoundError:
            print(f"ERROR: --calls file not found: {calls_path}", file=sys.stderr)
            sys.exit(1)
        report = hit_rates_report(calls)
        out_text = json.dumps(report, indent=2)
        out_path = _cli_arg('--out')
        if out_path:
            with open(out_path, 'w') as f:
                f.write(out_text + '\n')
            print(f"source_rates written to {out_path} "
                  f"({len(calls)} calls processed)")
        else:
            print(out_text)
        sys.exit(0)

    print(f"Unknown command: {cmd}")
    sys.exit(1)


if __name__ == '__main__':
    main()
