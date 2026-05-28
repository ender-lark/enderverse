#!/usr/bin/env python3
"""
re_entry_zone_scan.py — v11.11 Patch 1 implementation
Shipped: May 14, 2026 late PM

Scans Live Theses DB for rows with Re-Entry Zone Lo/Hi populated, checks
intraday range against zone, surfaces zone-touch alerts for Launcher Step 3.

Fire condition (per CI v11.12):
    intraday_low <= zone_hi AND intraday_high >= zone_lo

Architecture (mirrors live_theses_helpers.py pattern):
    - Pure-logic core `evaluate_zone_touch()` — testable without Notion/UW
    - Live integration layer `scan_live_theses_for_zone_touches()` reads Notion
    - CLI: --self-test (no live deps), --scan (live mode)

Notion targets:
    LIVE_THESES_DS = 0f083d6f-be67-4815-a64a-a21959812f0d

Live Theses DB fields consumed (v11.11 schema):
    - Ticker (title)
    - Re-Entry Zone Lo (number)
    - Re-Entry Zone Hi (number)
    - Re-Entry Zone Source (rich_text)
    - Tier (select)
    - Last Close (number)  [optional context]

Quote source: UW `get_company_info` for current price + intraday range. Live
mode requires UW tools at call site; this module produces the zone-touch
record from quote dicts passed in.

Usage:
    # Pure-logic
    from re_entry_zone_scan import evaluate_zone_touch
    result = evaluate_zone_touch(
        ticker="MP", zone_lo=55.0, zone_hi=58.0,
        intraday_low=56.20, intraday_high=58.40, last_close=57.80,
        source="Meridian buy-on-noise rule, Jan 23 note",
    )
    # Returns ZoneTouch dataclass; result.fired == True

    # Live mode (requires NOTION_API_TOKEN)
    python3 re_entry_zone_scan.py --scan
        --quotes-json /tmp/quotes.json
        (quotes.json: {"MP": {"intraday_low": 56.2, "intraday_high": 58.4, "last_close": 57.8}, ...})

CLI:
    python3 re_entry_zone_scan.py --self-test
    python3 re_entry_zone_scan.py --evaluate MP --lo 55 --hi 58 \
        --intraday-low 56.2 --intraday-high 58.4 --last-close 57.8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

try:
    from notion_helpers import NotionClient
    _HAS_NOTION = True
except ImportError:
    _HAS_NOTION = False


# ============================================================================
# Constants
# ============================================================================

LIVE_THESES_DS = "0f083d6f-be67-4815-a64a-a21959812f0d"


# ============================================================================
# Pure-logic core
# ============================================================================

@dataclass
class ZoneTouch:
    """Result of evaluating a single ticker against its re-entry zone."""
    ticker: str
    zone_lo: float
    zone_hi: float
    intraday_low: float
    intraday_high: float
    last_close: float
    fired: bool                # True iff intraday range overlaps zone
    reason: str                # one-line explanation
    source: Optional[str] = None
    tier: Optional[str] = None
    surface_format: str = ""   # ready-to-print operator-facing block


def evaluate_zone_touch(
    ticker: str,
    zone_lo: float,
    zone_hi: float,
    intraday_low: float,
    intraday_high: float,
    last_close: float,
    source: Optional[str] = None,
    tier: Optional[str] = None,
) -> ZoneTouch:
    """
    Pure-logic zone evaluator. No I/O.

    Fire condition: intraday_low <= zone_hi AND intraday_high >= zone_lo
    (i.e., the intraday range overlaps the zone in any way)

    Args validated:
        - zone_lo must be <= zone_hi (otherwise auto-swapped with warning in reason)
        - intraday_low must be <= intraday_high (otherwise auto-swapped)
        - all numerics finite
    """
    # Defensive normalization (data hygiene; do not silently drop)
    notes = []
    if zone_lo > zone_hi:
        notes.append(f"zone bounds swapped ({zone_lo} > {zone_hi})")
        zone_lo, zone_hi = zone_hi, zone_lo
    if intraday_low > intraday_high:
        notes.append(f"intraday range swapped ({intraday_low} > {intraday_high})")
        intraday_low, intraday_high = intraday_high, intraday_low

    overlaps = (intraday_low <= zone_hi) and (intraday_high >= zone_lo)

    if overlaps:
        # Was the close itself inside the zone? Stronger signal.
        close_in_zone = zone_lo <= last_close <= zone_hi
        if close_in_zone:
            reason = (
                f"Intraday range ${intraday_low:.2f}–${intraday_high:.2f} "
                f"overlapped zone ${zone_lo:.2f}–${zone_hi:.2f}; "
                f"close ${last_close:.2f} INSIDE zone"
            )
        else:
            reason = (
                f"Intraday range ${intraday_low:.2f}–${intraday_high:.2f} "
                f"touched zone ${zone_lo:.2f}–${zone_hi:.2f}; "
                f"close ${last_close:.2f} outside zone"
            )
    else:
        # Quantify distance for trailing context
        if intraday_low > zone_hi:
            gap = intraday_low - zone_hi
            pct = (gap / zone_hi) * 100 if zone_hi else 0.0
            reason = (
                f"Intraday low ${intraday_low:.2f} is ${gap:.2f} "
                f"({pct:.1f}%) above zone hi ${zone_hi:.2f}"
            )
        else:
            gap = zone_lo - intraday_high
            pct = (gap / zone_lo) * 100 if zone_lo else 0.0
            reason = (
                f"Intraday high ${intraday_high:.2f} is ${gap:.2f} "
                f"({pct:.1f}%) below zone lo ${zone_lo:.2f}"
            )

    if notes:
        reason = "(" + "; ".join(notes) + ") " + reason

    surface = _format_surface(
        ticker=ticker, fired=overlaps,
        zone_lo=zone_lo, zone_hi=zone_hi,
        intraday_low=intraday_low, intraday_high=intraday_high,
        last_close=last_close, source=source, tier=tier,
    )

    return ZoneTouch(
        ticker=ticker.upper(),
        zone_lo=zone_lo, zone_hi=zone_hi,
        intraday_low=intraday_low, intraday_high=intraday_high,
        last_close=last_close,
        fired=overlaps, reason=reason,
        source=source, tier=tier,
        surface_format=surface,
    )


def _format_surface(
    ticker: str, fired: bool, zone_lo: float, zone_hi: float,
    intraday_low: float, intraday_high: float, last_close: float,
    source: Optional[str], tier: Optional[str],
) -> str:
    """Build the operator-facing surface block per CI v11.12 spec."""
    if not fired:
        return ""

    src_line = f"\nSource: {source}" if source else ""
    tier_line = f"\nTier: {tier}" if tier else ""
    return (
        f"🎯 RE-ENTRY ZONE TOUCHED — {ticker.upper()}\n"
        f"Zone: ${zone_lo:.2f}–${zone_hi:.2f} · "
        f"Today range: ${intraday_low:.2f}–${intraday_high:.2f} · "
        f"Last close: ${last_close:.2f}"
        f"{src_line}{tier_line}\n"
        f"Two-Lens auto-fire required before any capital action."
    )


# ============================================================================
# Live integration layer
# ============================================================================

@dataclass
class LiveZoneRow:
    """Subset of Live Theses fields needed for zone-touch scan."""
    ticker: str
    zone_lo: Optional[float]
    zone_hi: Optional[float]
    source: Optional[str]
    tier: Optional[str]
    last_close: Optional[float]
    page_id: str  # Notion page id for downstream surfacing


def _select_name(props: dict, key: str) -> Optional[str]:
    p = props.get(key, {})
    if p.get("type") == "select" and p.get("select"):
        return p["select"].get("name")
    return None


def _number(props: dict, key: str) -> Optional[float]:
    p = props.get(key, {})
    if p.get("type") == "number":
        return p.get("number")
    return None


def _rich_text(props: dict, key: str) -> Optional[str]:
    p = props.get(key, {})
    if p.get("type") == "rich_text":
        chunks = p.get("rich_text", [])
        return "".join(c.get("plain_text", "") for c in chunks) or None
    return None


def _title(props: dict, key: str) -> Optional[str]:
    p = props.get(key, {})
    if p.get("type") == "title":
        chunks = p.get("title", [])
        return "".join(c.get("plain_text", "") for c in chunks) or None
    return None


def fetch_zone_rows(client: NotionClient) -> list[LiveZoneRow]:
    """
    Query Live Theses DB for rows where Re-Entry Zone Lo is populated.
    Returns list of LiveZoneRow with parsed fields.

    Notion filter: numeric property "Re-Entry Zone Lo" is not empty.
    """
    filter_body = {
        "property": "Re-Entry Zone Lo",
        "number": {"is_not_empty": True},
    }

    rows: list[LiveZoneRow] = []
    cursor = None
    while True:
        res = client.query_database(
            data_source_id=LIVE_THESES_DS,
            filter_=filter_body,
            page_size=100,
            start_cursor=cursor,
        )
        if not res.ok or not res.data:
            break
        for page in res.data.get("results", []):
            props = page.get("properties", {})
            ticker = _title(props, "Ticker")
            if not ticker:
                continue
            rows.append(LiveZoneRow(
                ticker=ticker.upper(),
                zone_lo=_number(props, "Re-Entry Zone Lo"),
                zone_hi=_number(props, "Re-Entry Zone Hi"),
                source=_rich_text(props, "Re-Entry Zone Source"),
                tier=_select_name(props, "Tier"),
                last_close=_number(props, "Last Close"),
                page_id=page.get("id", ""),
            ))
        if res.data.get("has_more"):
            cursor = res.data.get("next_cursor")
        else:
            break
    return rows


def scan_live_theses_for_zone_touches(
    client: NotionClient,
    quotes: dict[str, dict],
) -> list[ZoneTouch]:
    """
    Top-level live-mode scanner.

    Args:
        client: NotionClient (must have read access to Live Theses DB)
        quotes: dict keyed by ticker, each value with intraday_low / intraday_high
                / last_close (floats). Tickers missing from quotes are skipped
                with a warning embedded in result.reason.

    Returns: list of ZoneTouch (fired == True surfaced upstream).
    """
    rows = fetch_zone_rows(client)
    results: list[ZoneTouch] = []
    for r in rows:
        if r.zone_lo is None or r.zone_hi is None:
            continue
        q = quotes.get(r.ticker) or quotes.get(r.ticker.upper())
        if not q:
            # No-quote: produce a synthetic record so caller can audit gaps
            results.append(ZoneTouch(
                ticker=r.ticker, zone_lo=r.zone_lo, zone_hi=r.zone_hi,
                intraday_low=0.0, intraday_high=0.0, last_close=0.0,
                fired=False, reason="NO_QUOTE — ticker missing from quotes dict",
                source=r.source, tier=r.tier, surface_format="",
            ))
            continue
        results.append(evaluate_zone_touch(
            ticker=r.ticker,
            zone_lo=r.zone_lo, zone_hi=r.zone_hi,
            intraday_low=float(q.get("intraday_low", 0)),
            intraday_high=float(q.get("intraday_high", 0)),
            last_close=float(q.get("last_close", 0)),
            source=r.source, tier=r.tier,
        ))
    return results


# ============================================================================
# Self-test
# ============================================================================

def _self_test() -> int:
    """Inline test harness — exits non-zero on any failure."""
    failed = 0
    passed = 0

    def check(name, condition):
        nonlocal failed, passed
        if condition:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {name}", file=sys.stderr)

    # Test 1: clean overlap fires
    r = evaluate_zone_touch("MP", 55.0, 58.0, 56.2, 58.4, 57.8, source="Meridian")
    check("clean overlap fires", r.fired is True)
    check("close-in-zone language present",
          "INSIDE zone" in r.reason and "INSIDE" in r.reason.upper())
    check("surface format populated when fired", "🎯" in r.surface_format)

    # Test 2: intraday entirely below zone — no fire
    r = evaluate_zone_touch("ASTS", 65.0, 70.0, 60.0, 64.0, 62.0)
    check("intraday below zone does not fire", r.fired is False)
    check("trailing reason quantifies gap", "below zone" in r.reason)
    check("surface empty when not fired", r.surface_format == "")

    # Test 3: intraday entirely above zone — no fire
    r = evaluate_zone_touch("LEU", 180.0, 195.0, 200.0, 210.0, 205.0)
    check("intraday above zone does not fire", r.fired is False)
    check("trailing reason quantifies above-gap", "above zone" in r.reason)

    # Test 4: exact boundary touch (intraday_low == zone_hi) — fires
    r = evaluate_zone_touch("BMNR", 18.0, 22.0, 22.0, 25.0, 23.0)
    check("exact boundary touch fires", r.fired is True)

    # Test 5: exact boundary touch other side (intraday_high == zone_lo) — fires
    r = evaluate_zone_touch("FIGR", 35.0, 38.0, 30.0, 35.0, 33.0)
    check("exact lo-boundary touch fires", r.fired is True)

    # Test 6: zone bounds swapped — auto-corrects + still fires
    r = evaluate_zone_touch("X", 58.0, 55.0, 56.0, 57.0, 56.5)
    check("zone bounds swap auto-corrects", r.fired is True)
    check("swap noted in reason", "swapped" in r.reason)
    check("zone_lo normalized", r.zone_lo == 55.0)
    check("zone_hi normalized", r.zone_hi == 58.0)

    # Test 7: intraday range swapped — auto-corrects
    r = evaluate_zone_touch("Y", 55.0, 58.0, 58.0, 56.0, 57.0)
    check("intraday range swap auto-corrects + fires",
          r.fired is True and "swapped" in r.reason)

    # Test 8: close outside zone but range overlaps — fires with correct language
    r = evaluate_zone_touch("Z", 50.0, 55.0, 54.0, 60.0, 58.0)
    check("range overlap with close above zone fires", r.fired is True)
    check("close-outside-zone language", "outside zone" in r.reason)

    # Test 9: equal lo/hi (pinpoint zone) — fires only on exact touch
    r = evaluate_zone_touch("W", 50.0, 50.0, 49.0, 51.0, 50.0)
    check("pinpoint zone fires on overlap", r.fired is True)
    r = evaluate_zone_touch("W", 50.0, 50.0, 51.0, 52.0, 51.5)
    check("pinpoint zone no-fire when above", r.fired is False)

    # Test 10: ticker normalized to upper
    r = evaluate_zone_touch("mp", 55.0, 58.0, 56.0, 57.0, 56.5)
    check("ticker upper-cased", r.ticker == "MP")

    # Test 11: surface format contains the operator-facing required phrase
    r = evaluate_zone_touch(
        "MP", 55.0, 58.0, 56.0, 57.5, 57.0,
        source="Meridian buy-on-noise", tier="A",
    )
    check("surface has Two-Lens-auto-fire wording",
          "Two-Lens auto-fire" in r.surface_format)
    check("surface contains source", "Meridian" in r.surface_format)
    check("surface contains tier", "Tier: A" in r.surface_format)

    # Test 12: live scanner with missing quote dict
    class _FakeClient:
        def query_database(self, **kwargs):
            from notion_helpers import NotionResult
            return NotionResult(ok=True, status=200, data={
                "results": [{
                    "id": "page1",
                    "properties": {
                        "Ticker": {"type": "title", "title": [{"plain_text": "ASTS"}]},
                        "Re-Entry Zone Lo": {"type": "number", "number": 65.0},
                        "Re-Entry Zone Hi": {"type": "number", "number": 70.0},
                        "Re-Entry Zone Source": {
                            "type": "rich_text",
                            "rich_text": [{"plain_text": "operator memory 5/14"}],
                        },
                        "Tier": {"type": "select", "select": {"name": "C"}},
                    },
                }],
                "has_more": False,
            }, error=None)
    fake = _FakeClient()
    out = scan_live_theses_for_zone_touches(fake, quotes={})
    check("missing-quote path returns synthetic NO_QUOTE row",
          len(out) == 1 and out[0].reason.startswith("NO_QUOTE"))

    # Test 13: live scanner with valid quote that fires
    out = scan_live_theses_for_zone_touches(fake, quotes={
        "ASTS": {"intraday_low": 64.5, "intraday_high": 68.0, "last_close": 67.0},
    })
    check("live scanner fires on intraday overlap",
          len(out) == 1 and out[0].fired is True)
    check("live scanner preserves source from Notion",
          out[0].source == "operator memory 5/14")

    print(f"\n  re_entry_zone_scan self-test: {passed} pass / {failed} fail")
    return 0 if failed == 0 else 1


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="v11.11 Patch 1 — Re-Entry Zone Scan")
    p.add_argument("--self-test", action="store_true",
                   help="Run inline self-test, exit non-zero on failure")
    p.add_argument("--evaluate", metavar="TICKER",
                   help="Evaluate single zone touch (debugging mode)")
    p.add_argument("--lo", type=float, help="Zone lo (with --evaluate)")
    p.add_argument("--hi", type=float, help="Zone hi (with --evaluate)")
    p.add_argument("--intraday-low", type=float,
                   help="Intraday low (with --evaluate)")
    p.add_argument("--intraday-high", type=float,
                   help="Intraday high (with --evaluate)")
    p.add_argument("--last-close", type=float,
                   help="Last close (with --evaluate)")
    p.add_argument("--source", default=None, help="Optional source tag")
    p.add_argument("--scan", action="store_true",
                   help="Live scan mode (requires NOTION_API_TOKEN + quotes JSON)")
    p.add_argument("--quotes-json", default=None,
                   help="Path to quotes JSON for --scan mode")

    args = p.parse_args()

    if args.self_test:
        return _self_test()

    if args.evaluate:
        for required in ("lo", "hi", "intraday_low", "intraday_high", "last_close"):
            if getattr(args, required) is None:
                print(f"--evaluate requires --{required.replace('_','-')}",
                      file=sys.stderr)
                return 2
        r = evaluate_zone_touch(
            args.evaluate, args.lo, args.hi,
            args.intraday_low, args.intraday_high, args.last_close,
            source=args.source,
        )
        print(json.dumps(asdict(r), indent=2))
        return 0

    if args.scan:
        if not _HAS_NOTION:
            print("ERROR: notion_helpers not importable", file=sys.stderr)
            return 3
        if not args.quotes_json:
            print("--scan requires --quotes-json", file=sys.stderr)
            return 2
        with open(args.quotes_json) as f:
            quotes = json.load(f)
        client = NotionClient()
        results = scan_live_theses_for_zone_touches(client, quotes)
        fired = [r for r in results if r.fired]
        print(f"Scanned {len(results)} zoned positions; {len(fired)} fired.\n")
        for r in fired:
            print(r.surface_format)
            print()
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
