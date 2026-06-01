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

v11.35 — Inbox->Log staleness gauge:
- inbox_log_staleness() + staleness_surface_line() — pure-logic gauge that
  compares newest live-Inbox call date vs newest call represented in the Log.
  Root-cause fix for the 2026-05-28 Farrell->HYPE false-negative: the layer
  could run silently behind the Inbox because classification (Inbox->Log) was
  not forced before a calibration read. The gauge makes the lag visible; the
  surface line stamps SOURCE CALIB output PROVISIONAL while the lag is open.
  Recency must be anchored to the live Inbox, never the cache's max date.

v11.36 - Log->Cache staleness gauge + chain orchestrator (fix #1):
- log_cache_staleness() - sibling to inbox_log_staleness(); watches the
  Source-Call-Log -> source_calls.json (cache) hop, the one the v11.35 gauge
  could not see. On 2026-05-28 the Log was current (5/28) but the cache was
  stuck at 5/19, so Inbox->Log read clean while hit-rates were 9d stale.
- calibration_chain_staleness() - checks the whole Inbox->Log->Cache chain in
  one call so a reader can never inspect one hop and miss the other.
- chain_staleness_surface() - names whichever hop(s) are stale + PROVISIONAL.

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
# Inbox -> Source-Call-Log staleness gauge (v11.35)
# ==============================================================================

def find_ingestion_gaps(upstream_dates, downstream_dates) -> dict:
    """Find upstream call dates not represented downstream (v11.36, fix #2).

    The frontier gauges (inbox_log_staleness / log_cache_staleness) count only
    items dated AFTER the newest downstream item. A date sitting BELOW the newest
    downstream item but never ingested is invisible to them. Live 2026-05-28: the
    Log's newest row was the 5/28 monthly batch, but Newton's 5/26 + 5/27 daily
    calls were never classified -- being <= 5/28 they scored as 0 'un-ingested'.
    This finds those interior holes.

    Returns dict:
        frontier_new     : sorted list[str] -- upstream dates strictly AFTER the
                           newest downstream date (what the frontier gauge sees)
        interior_missing : sorted list[str] -- upstream dates <= newest downstream
                           date but ABSENT from the downstream set (what the
                           frontier gauge MISSES -- this is fix #2)
        all_missing      : sorted list[str] -- union of the two
        any_missing      : bool

    LIMITATION (date granularity): a date with SOME downstream representation but
    missing OTHER calls from that same day will NOT flag -- detecting that needs
    call-level IDs, not date lists (a separate, larger change). This reliably
    catches the clear case: a day with ZERO downstream representation.
    """
    up = sorted({d for d in (_parse_date(x) for x in (upstream_dates or [])) if d})
    down = sorted({d for d in (_parse_date(x) for x in (downstream_dates or [])) if d})
    down_set = set(down)
    newest_down = down[-1] if down else None

    if newest_down is None:
        frontier_new = list(up)
        interior_missing = []
    else:
        frontier_new = [d for d in up if d > newest_down]
        interior_missing = [d for d in up if d <= newest_down and d not in down_set]

    all_missing = sorted(set(frontier_new) | set(interior_missing))
    return {
        'frontier_new': [d.isoformat() for d in frontier_new],
        'interior_missing': [d.isoformat() for d in interior_missing],
        'all_missing': [d.isoformat() for d in all_missing],
        'any_missing': bool(all_missing),
    }


def inbox_log_staleness(inbox_call_dates, log_call_dates, now=None) -> dict:
    """Detect Inbox -> Source-Call-Log classification lag (v11.35).

    Root cause of the 2026-05-28 Farrell->HYPE false-negative: the calibration
    layer reads source_calls.json, which is regenerated from the 📊 Source Call
    Log; the Log is only as current as the last Inbox-audit classification pass,
    and nothing forced that pass before a calibration read. So persistence /
    recency / hit-rate output could run silently behind the live 📧 Fundstrat
    Inbox.

    PURE LOGIC, no Notion call (Patch P philosophy). At session-open Claude
    already fetches both the live Inbox (7-day audit) and the Log (v11.33 sync);
    it passes the two date lists here to make the lag visible and unmissable.

    Recency is measured apples-to-apples: newest *call date* visible in the
    Inbox vs newest *call date represented in the Log*. A calibration consumer's
    recency must never be read off the cache's max date alone -- that is exactly
    the trap that dismissed the live 5/21 HYPE note.

    Args:
        inbox_call_dates: iterable of date / ISO-str -- dates of FS-source calls
            (Newton/Lee/Farrell) visible in the live Inbox.
        log_call_dates:   iterable of date / ISO-str -- 'Date Made' of rows
            already classified into the Source Call Log.
        now: optional date / ISO-str; defaults to today (reporting only).

    Returns dict:
        un_ingested  : int  -- inbox calls dated strictly after the newest call
                               represented in the Log (all inbox calls if the
                               Log is empty).
        newest_inbox : 'YYYY-MM-DD' | None
        newest_log   : 'YYYY-MM-DD' | None
        stale        : bool -- un_ingested > 0
        days_behind  : int  -- (newest_inbox - newest_log).days, clamped >= 0;
                               0 when not stale or baseline unknown.
    """
    inbox = sorted({d for d in (_parse_date(x) for x in (inbox_call_dates or [])) if d})
    logd = sorted({d for d in (_parse_date(x) for x in (log_call_dates or [])) if d})

    newest_inbox = inbox[-1] if inbox else None
    newest_log = logd[-1] if logd else None

    if newest_log is None:
        un_ingested = len(inbox)
    else:
        un_ingested = sum(1 for d in inbox if d > newest_log)

    frontier_stale = un_ingested > 0
    interior_gaps = find_ingestion_gaps(inbox_call_dates, log_call_dates)['interior_missing']
    stale = frontier_stale or bool(interior_gaps)   # v11.36 #2: interior holes count too
    if frontier_stale and newest_inbox and newest_log:
        days_behind = max(0, (newest_inbox - newest_log).days)
    else:
        days_behind = 0  # frontier lag only; interior gaps are a count, not a lag

    return {
        'un_ingested': un_ingested,
        'interior_gaps': interior_gaps,   # v11.36 #2: dates classified-into-Log-late, below the frontier
        'newest_inbox': newest_inbox.isoformat() if newest_inbox else None,
        'newest_log': newest_log.isoformat() if newest_log else None,
        'stale': stale,
        'days_behind': days_behind,
    }


def staleness_surface_line(gauge: dict) -> str:
    """One-line pre-flight surface for the staleness gauge (v11.35).

    Quiet-output discipline: returns '' when not stale, so the warning appears
    only on a hit. When stale, it reports *Inbox* recency (never the Log/cache
    max date) and carries ⚠️ + the PROVISIONAL stamp that tells the SOURCE
    CALIB block its output is provisional until classification clears the lag.
    """
    if not gauge or not gauge.get('stale'):
        return ''
    parts = []
    if gauge.get('un_ingested', 0) > 0:
        parts.append(
            f"{gauge['un_ingested']} un-ingested (newest Inbox "
            f"{gauge['newest_inbox']} vs newest Log {gauge['newest_log']}, "
            f"{gauge['days_behind']}d behind)")
    interior = gauge.get('interior_gaps') or []
    if interior:
        parts.append(f"{len(interior)} interior-gap call(s) below the frontier "
                     f"({', '.join(interior)})")
    return (f"⚠️ INBOX→LOG STALE: " + " + ".join(parts) +
            " — classify before any calibration-cited capital action; "
            "SOURCE CALIB output is PROVISIONAL until cleared")




def log_cache_staleness(log_call_dates, cache_call_dates, now=None) -> dict:
    """Detect Source-Call-Log -> source_calls.json CACHE lag (v11.36, fix #1).

    Sibling to inbox_log_staleness(). v11.35 watches Inbox->Log, but the
    calibration scripts (persistence_scan / compute_hit_rate) actually READ THE
    CACHE file source_calls.json -- which the session-open sync regenerates from
    the Source Call Log. If that regen lags the Log, calibration runs on stale
    data even when Inbox->Log is current. That was the live 2026-05-28 state:
    Log newest 5/28, cache newest 5/19 -> the Inbox->Log gauge read CLEAN while
    hit-rates were silently 9 days stale. This gauge watches THAT hop.

    PURE LOGIC, no Notion call. Claude holds both lists at session-open:
    log_call_dates from the Log fetch, cache_call_dates from the loaded
    source_calls.json.

    Args:
        log_call_dates:   iterable of date / ISO-str -- 'Date Made' of rows in
            the live Source Call Log.
        cache_call_dates: iterable of date / ISO-str -- 'date' field of entries
            in the source_calls.json the calibration scripts will read.
        now: optional date / ISO-str; defaults to today (reporting only).

    Returns dict (mirror of inbox_log_staleness):
        un_cached    : int  -- log calls dated strictly after the newest cache
                               date (all log calls if the cache is empty).
        newest_log   : 'YYYY-MM-DD' | None
        newest_cache : 'YYYY-MM-DD' | None
        stale        : bool -- un_cached > 0
        days_behind  : int  -- (newest_log - newest_cache).days, clamped >= 0;
                               0 when not stale or baseline unknown.
    """
    logd = sorted({d for d in (_parse_date(x) for x in (log_call_dates or [])) if d})
    cache = sorted({d for d in (_parse_date(x) for x in (cache_call_dates or [])) if d})

    newest_log = logd[-1] if logd else None
    newest_cache = cache[-1] if cache else None

    if newest_cache is None:
        un_cached = len(logd)
    else:
        un_cached = sum(1 for d in logd if d > newest_cache)

    frontier_stale = un_cached > 0
    interior_gaps = find_ingestion_gaps(log_call_dates, cache_call_dates)['interior_missing']
    stale = frontier_stale or bool(interior_gaps)   # v11.36 #2: interior holes count too
    if frontier_stale and newest_log and newest_cache:
        days_behind = max(0, (newest_log - newest_cache).days)
    else:
        days_behind = 0  # frontier lag only; interior gaps are a count, not a lag

    return {
        'un_cached': un_cached,
        'interior_gaps': interior_gaps,   # v11.36 #2: Log dates not in the cache, below the frontier
        'newest_log': newest_log.isoformat() if newest_log else None,
        'newest_cache': newest_cache.isoformat() if newest_cache else None,
        'stale': stale,
        'days_behind': days_behind,
    }


def calibration_chain_staleness(inbox_call_dates, log_call_dates,
                                cache_call_dates, now=None) -> dict:
    """Check the WHOLE source-calibration freshness chain in one call (v11.36).

    The chain is:  live Inbox  ->  Source Call Log  ->  source_calls.json cache.
    Calibration output is only as fresh as the STALEST hop. The 2026-05-28 bug
    was looking at one hop (Inbox->Log, which was clean) and missing the other
    (Log->Cache, which was 9d stale). Calling THIS single function instead of
    either gauge alone is the forcing function that prevents recurrence -- it
    can never point at the wrong hop because it checks both.

    Returns dict:
        inbox_log         : the inbox_log_staleness() dict (hop 1)
        log_cache         : the log_cache_staleness() dict (hop 2)
        stale             : bool -- True if EITHER hop is stale
        stale_hops        : list[str] -- any of ['inbox_log', 'log_cache']
        worst_days_behind : int  -- max days_behind across stale hops (0 if fresh)
        provisional       : bool -- alias of stale; when True, SOURCE CALIB
                                    output is PROVISIONAL until the hop(s) clear
    """
    h1 = inbox_log_staleness(inbox_call_dates, log_call_dates, now=now)
    h2 = log_cache_staleness(log_call_dates, cache_call_dates, now=now)

    stale_hops = []
    if h1['stale']:
        stale_hops.append('inbox_log')
    if h2['stale']:
        stale_hops.append('log_cache')

    stale = bool(stale_hops)
    worst = max(h1['days_behind'], h2['days_behind']) if stale else 0

    return {
        'inbox_log': h1,
        'log_cache': h2,
        'stale': stale,
        'stale_hops': stale_hops,
        'worst_days_behind': worst,
        'provisional': stale,
    }


def chain_staleness_surface(chain: dict) -> str:
    """Multi-line pre-flight surface for the full calibration chain (v11.36).

    Quiet when the whole chain is fresh (returns ''). Otherwise emits one
    warning line per stale hop, each naming its own dates, so the reader sees
    exactly WHICH hop is behind. Reuses staleness_surface_line() for the
    Inbox->Log hop so that wording stays identical to v11.35.
    """
    if not chain or not chain.get('stale'):
        return ''
    lines = []
    if chain['inbox_log']['stale']:
        lines.append(staleness_surface_line(chain['inbox_log']))
    if chain['log_cache']['stale']:
        lc = chain['log_cache']
        parts = []
        if lc.get('un_cached', 0) > 0:
            parts.append(
                f"{lc['un_cached']} un-cached (newest Log {lc['newest_log']} "
                f"vs newest cache {lc['newest_cache']}, {lc['days_behind']}d behind)")
        interior = lc.get('interior_gaps') or []
        if interior:
            parts.append(f"{len(interior)} interior-gap call(s) below the frontier "
                         f"({', '.join(interior)})")
        lines.append(
            f"\u26a0\ufe0f LOG\u2192CACHE STALE: " + " + ".join(parts) +
            " \u2014 regenerate source_calls.json from the Log before any "
            "calibration-cited capital action; SOURCE CALIB output is "
            "PROVISIONAL until cleared")
    return "\n".join(lines)


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

    # --- Block 7: inbox_log_staleness gauge + surface (v11.35) ---
    # Fresh: inbox newest == log newest -> not stale
    g = inbox_log_staleness(['2026-05-19', '2026-05-15'],
                            ['2026-05-19', '2026-05-15'], now='2026-05-28')
    check("gauge: fresh (inbox==log) -> not stale", g['stale'] is False)
    check("gauge: fresh -> un_ingested 0", g['un_ingested'] == 0)
    check("gauge: surface line empty when fresh",
          staleness_surface_line(g) == '')

    # 2026-05-28 regression fixture: Log newest 5/19, Inbox carries 5/21 + 5/28
    g = inbox_log_staleness(
        ['2026-05-15', '2026-05-19', '2026-05-21', '2026-05-28'],
        ['2026-05-15', '2026-05-19'], now='2026-05-28')
    check("gauge[5/28]: un_ingested == 2", g['un_ingested'] == 2)
    check("gauge[5/28]: newest_inbox 2026-05-28",
          g['newest_inbox'] == '2026-05-28')
    check("gauge[5/28]: newest_log 2026-05-19", g['newest_log'] == '2026-05-19')
    check("gauge[5/28]: stale True", g['stale'] is True)
    check("gauge[5/28]: days_behind 9", g['days_behind'] == 9)
    check("gauge[5/28]: surface warns + PROVISIONAL",
          'PROVISIONAL' in staleness_surface_line(g)
          and '⚠️' in staleness_surface_line(g))

    # Empty log, non-empty inbox -> everything un-ingested
    g = inbox_log_staleness(['2026-05-21', '2026-05-28'], [], now='2026-05-28')
    check("gauge: empty log -> all inbox un-ingested", g['un_ingested'] == 2)
    check("gauge: empty log -> stale, days_behind 0 (no baseline)",
          g['stale'] is True and g['days_behind'] == 0)

    # Empty inbox -> not stale
    g = inbox_log_staleness([], ['2026-05-19'], now='2026-05-28')
    check("gauge: empty inbox -> not stale", g['stale'] is False)

    # Recency-anchoring FP guard: 6 backfill HYPE rows, HYPE held/core -> QUIET
    hype_rows = [_m('farrell', 'HYPE', d, tier='D', backfill=True)
                 for d in ('2026-04-29', '2026-05-08', '2026-05-14',
                           '2026-05-15', '2026-05-18', '2026-05-19')]
    cl = persistence_scan(hype_rows, core_tickers=['HYPE', 'BMNR', 'LEU'],
                          now='2026-05-28')
    check("persistence[5/28]: 6 backfill HYPE fire as one cluster",
          len(cl) == 1 and cl[0]['count'] == 6)
    check("persistence[5/28]: held HYPE backfill -> QUIET not LOUD",
          cl[0]['loud'] is False and cl[0]['quiet_reason'] == 'core')

    # ----------------------------------------------------------------------
    # Block 8: log_cache_staleness + calibration_chain_staleness (v11.36, #1)
    # The Log->Cache hop the v11.35 Inbox->Log gauge could not see.
    # ----------------------------------------------------------------------
    lc = log_cache_staleness(['2026-05-19', '2026-05-15'],
                             ['2026-05-19', '2026-05-15'], now='2026-05-28')
    check("log_cache: fresh -> not stale", lc['stale'] is False)
    check("log_cache: fresh -> un_cached 0", lc['un_cached'] == 0)

    # 2026-05-28 live fixture: Log carries 5/28, cache stuck at 5/19 -> 9d stale
    lc = log_cache_staleness(
        ['2026-05-15', '2026-05-19', '2026-05-28'],
        ['2026-05-15', '2026-05-19'], now='2026-05-28')
    check("log_cache[5/28]: un_cached == 1", lc['un_cached'] == 1)
    check("log_cache[5/28]: newest_log 2026-05-28", lc['newest_log'] == '2026-05-28')
    check("log_cache[5/28]: newest_cache 2026-05-19", lc['newest_cache'] == '2026-05-19')
    check("log_cache[5/28]: stale True", lc['stale'] is True)
    check("log_cache[5/28]: days_behind 9", lc['days_behind'] == 9)

    lc = log_cache_staleness(['2026-05-19', '2026-05-28'], [], now='2026-05-28')
    check("log_cache: empty cache -> all log un-cached", lc['un_cached'] == 2)
    check("log_cache: empty cache -> stale, days_behind 0 (no baseline)",
          lc['stale'] is True and lc['days_behind'] == 0)

    lc = log_cache_staleness([], ['2026-05-19'], now='2026-05-28')
    check("log_cache: empty log -> not stale", lc['stale'] is False)

    # chain orchestrator: the EXACT 5/28 trap -> Inbox->Log clean, Log->Cache stale
    chain = calibration_chain_staleness(
        inbox_call_dates=['2026-05-19', '2026-05-28'],
        log_call_dates=['2026-05-19', '2026-05-28'],
        cache_call_dates=['2026-05-15', '2026-05-19'],
        now='2026-05-28')
    check("chain[5/28]: inbox_log hop clean", chain['inbox_log']['stale'] is False)
    check("chain[5/28]: log_cache hop stale", chain['log_cache']['stale'] is True)
    check("chain[5/28]: chain stale (the hop old gauge missed)", chain['stale'] is True)
    check("chain[5/28]: stale_hops == ['log_cache']",
          chain['stale_hops'] == ['log_cache'])
    check("chain[5/28]: worst_days_behind 9", chain['worst_days_behind'] == 9)
    check("chain[5/28]: provisional True", chain['provisional'] is True)
    check("chain[5/28]: surface names LOG->CACHE + PROVISIONAL",
          'LOG\u2192CACHE STALE' in chain_staleness_surface(chain)
          and 'PROVISIONAL' in chain_staleness_surface(chain))

    chain = calibration_chain_staleness(
        ['2026-05-28'], ['2026-05-28'], ['2026-05-28'], now='2026-05-28')
    check("chain: all fresh -> not stale", chain['stale'] is False)
    check("chain: all fresh -> surface empty", chain_staleness_surface(chain) == '')

    chain = calibration_chain_staleness(
        ['2026-05-28'], ['2026-05-19'], ['2026-05-15'], now='2026-05-28')
    check("chain: both hops stale", set(chain['stale_hops']) == {'inbox_log', 'log_cache'})
    _surf = chain_staleness_surface(chain)
    check("chain: both-stale surface names both hops",
          'INBOX\u2192LOG STALE' in _surf and 'LOG\u2192CACHE STALE' in _surf)

    # ----------------------------------------------------------------------
    # Block 9: interior-gap detection (v11.36, fix #2) -- the hole BELOW the
    # frontier that the v11.35 / #1 gauges could not see.
    # ----------------------------------------------------------------------
    # find_ingestion_gaps: the live 5/28 shape (5/26, 5/27 missing under 5/28 frontier)
    g = find_ingestion_gaps(['2026-05-15', '2026-05-26', '2026-05-27', '2026-05-28'],
                            ['2026-05-15', '2026-05-28'])
    check("gaps[5/28]: frontier_new empty (all <= 5/28)", g['frontier_new'] == [])
    check("gaps[5/28]: interior_missing == 5/26, 5/27",
          g['interior_missing'] == ['2026-05-26', '2026-05-27'])
    check("gaps[5/28]: any_missing True", g['any_missing'] is True)

    # date with SOME representation does not flag (date-granularity limitation, documented)
    g = find_ingestion_gaps(['2026-05-26'], ['2026-05-26', '2026-05-28'])
    check("gaps: date present downstream -> not missing", g['any_missing'] is False)

    # empty downstream -> all frontier_new, none interior
    g = find_ingestion_gaps(['2026-05-26', '2026-05-27'], [])
    check("gaps: empty downstream -> all frontier_new",
          g['frontier_new'] == ['2026-05-26', '2026-05-27'] and g['interior_missing'] == [])

    # inbox_log_staleness now FLAGS the interior gap (the 5/28 regression, fixed)
    g = inbox_log_staleness(['2026-05-15', '2026-05-26', '2026-05-27', '2026-05-28'],
                            ['2026-05-15', '2026-05-28'], now='2026-05-28')
    check("inbox_log[#2]: un_ingested 0 (frontier-blind)", g['un_ingested'] == 0)
    check("inbox_log[#2]: interior_gaps == 5/26, 5/27",
          g['interior_gaps'] == ['2026-05-26', '2026-05-27'])
    check("inbox_log[#2]: stale True via interior (was False pre-#2)", g['stale'] is True)
    _line = staleness_surface_line(g)
    check("inbox_log[#2]: surface names interior dates + PROVISIONAL",
          '2026-05-26' in _line and 'interior-gap' in _line and 'PROVISIONAL' in _line)

    # log_cache_staleness interior gap
    g = log_cache_staleness(['2026-05-15', '2026-05-22', '2026-05-26'],
                            ['2026-05-15', '2026-05-26'], now='2026-05-28')
    check("log_cache[#2]: interior 5/22 flagged", g['interior_gaps'] == ['2026-05-22'])
    check("log_cache[#2]: stale True via interior", g['stale'] is True)

    # chain catches an interior-only gap on the inbox->log hop
    chain = calibration_chain_staleness(
        inbox_call_dates=['2026-05-15', '2026-05-26', '2026-05-27', '2026-05-28'],
        log_call_dates=['2026-05-15', '2026-05-28'],     # 5/26, 5/27 never ingested
        cache_call_dates=['2026-05-15', '2026-05-28'],   # cache matches log
        now='2026-05-28')
    check("chain[#2]: inbox_log stale via interior", chain['inbox_log']['stale'] is True)
    check("chain[#2]: chain stale", chain['stale'] is True)
    check("chain[#2]: surface names interior gap",
          'interior-gap' in chain_staleness_surface(chain))

    return passed, total


# ==============================================================================
# CLI
# ==============================================================================

def batch_classify(raw_calls, now=None):
    """Batch-classify raw Inbox calls into Source-Call-Log-ready entries.

    Each raw call is a dict: {source, text|verbatim_quote, ticker(optional),
    date|call_date(optional)}. Runs classify_call on the text, then emits the
    canonical Log schema with the falsification condition + scoring window filled
    and outcome left 'Pending' — pre-registered BEFORE the outcome is known,
    which is the whole point of the calibration layer.

    Returns a list of dicts ready to create as Source Call Log rows. Does NOT
    write to Notion; the routine/operator creates the rows. This is the throughput
    helper for the n=0 bottleneck: many Inbox calls -> many Log-ready entries.
    """
    today = now or datetime.now().strftime('%Y-%m-%d')
    out = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        text = (raw.get('verbatim_quote') or raw.get('text') or '').strip()
        src = raw.get('source')
        if not src or not text:
            continue
        cls = classify_call(text)
        call_date = raw.get('date') or raw.get('call_date') or today
        window_end = raw.get('window_end')
        if not window_end:
            base = _parse_date(call_date) or _parse_date(today)
            window_end = ((base + timedelta(days=cls['window_days'])).strftime('%Y-%m-%d')
                          if base else cls['window_end'])
        ticker = raw.get('ticker') or raw.get('named_ticker')
        if not ticker and cls.get('tickers_detected'):
            ticker = cls['tickers_detected'][0]
        out.append({
            'source': str(src).strip().lower(),
            'ticker': (str(ticker).strip().upper() if ticker else None),
            'tier': cls['tier'],
            'confidence_in_tier': cls['confidence'],
            'verbatim_quote': text,
            'falsification_condition': cls['falsification'],
            'date': call_date,
            'window_end': window_end,
            'window_days': cls['window_days'],
            'outcome': 'Pending',
            'backfill': False,
            'classified_at': today,
        })
    return out


# Ladders that are expected to be scored Win/Loss/Push. D = unfalsifiable
# narrative ("DO NOT SCORE"), so it is never flagged as scoring-overdue.
SCORABLE_LADDERS = {'A', 'B', 'C'}


def scoring_lag_sweep(calls, now=None):
    """Find calls whose scoring window has CLOSED but are still unscored.

    Distinct from the Inbox->Log->cache propagation gauges: this catches calls
    that propagated fine but were never scored Win/Loss/Push after window_end
    passed — so the hit-rate denominator never grows even as windows close.
    Backfill rows and Tier-D (unfalsifiable) calls are excluded.

    Returns {due, count, oldest_overdue_days, by_source}; `due` is sorted most
    overdue first, each row carrying an 'overdue_days' field.
    """
    now_d = _parse_date(now) or datetime.now().date()
    due = []
    for c in (_normalize_call(c) for c in calls):
        if not c or c.get('backfill'):
            continue
        tier = (c.get('tier') or '').upper()
        if tier and tier not in SCORABLE_LADDERS:
            continue
        outcome = (c.get('outcome') or '').strip().lower()
        if outcome in ('win', 'loss', 'push'):
            continue
        we = _parse_date(c.get('window_end'))
        if not we or we >= now_d:
            continue
        due.append({**c, 'overdue_days': (now_d - we).days})
    due.sort(key=lambda c: -c['overdue_days'])
    by_source = {}
    for c in due:
        by_source[c['source']] = by_source.get(c['source'], 0) + 1
    return {
        'due': due,
        'count': len(due),
        'oldest_overdue_days': (due[0]['overdue_days'] if due else 0),
        'by_source': by_source,
    }


def scoring_lag_surface_line(sweep):
    if not sweep or sweep.get('count', 0) == 0:
        return "SCORING LAG: clean \u2014 no calls past window-end awaiting a score."
    bysrc = ", ".join(f"{s}:{n}" for s, n in sorted(sweep['by_source'].items()))
    return (f"SCORING LAG: \u26a0\ufe0f {sweep['count']} call(s) past window-end still "
            f"unscored (oldest {sweep['oldest_overdue_days']}d; {bysrc}) \u2014 "
            f"score Win/Loss/Push so the hit-rate denominator grows.")


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

    if cmd == '--batch-classify':
        raw_path = (sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--')
                    else _cli_arg('--raw'))
        if not raw_path:
            print("ERROR: --batch-classify needs a raw calls JSON path "
                  "(positional or --raw)", file=sys.stderr)
            sys.exit(1)
        try:
            with open(raw_path) as f:
                raw = json.load(f)
        except FileNotFoundError:
            print(f"ERROR: raw calls file not found: {raw_path}", file=sys.stderr)
            sys.exit(1)
        if isinstance(raw, dict):
            raw = raw.get('calls') or raw.get('data') or [raw]
        entries = batch_classify(raw, now=_cli_arg('--now'))
        out_text = json.dumps(entries, indent=2, default=str)
        out_path = _cli_arg('--out')
        if out_path:
            with open(out_path, 'w') as f:
                f.write(out_text + '\n')
            print(f"{len(entries)} Log-ready entries written to {out_path}")
        else:
            print(out_text)
        sys.exit(0)

    if cmd == '--scoring-lag':
        calls_path = _cli_arg('--calls', 'source_calls.json')
        try:
            calls = load_calls(calls_path)
        except FileNotFoundError:
            print(f"ERROR: --calls file not found: {calls_path}", file=sys.stderr)
            sys.exit(1)
        sweep = scoring_lag_sweep(calls, now=_cli_arg('--now'))
        print(json.dumps({
            'calls_loaded': len(calls),
            'count': sweep['count'],
            'oldest_overdue_days': sweep['oldest_overdue_days'],
            'by_source': sweep['by_source'],
            'due': sweep['due'],
            'surface_line': scoring_lag_surface_line(sweep),
        }, indent=2, default=str))
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
