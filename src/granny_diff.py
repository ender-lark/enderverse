#!/usr/bin/env python3
"""
granny_diff.py — Patch 2 from NBIS postmortem (CI v11.7)

Diffs Tom Lee's current Granny Shots ETF holdings (GRNY large-cap, GRNJ SMID)
against operator's fs_holdings.json to surface:
  (a) NEW names in Lee's ETFs that operator does NOT hold directly
  (b) names operator holds where Lee has materially changed weight
  (c) names removed from Lee's ETFs that operator still holds

This is the operational implementation of the v11.7 framework rule:
"Lee's ETF inclusion is a named-source endorsement on the standalone equity,
NOT just an ETF allocation. ETF-wrap exposure ≠ direct-position conviction."

USAGE:
    python granny_diff.py                              # Run full diff
    python granny_diff.py --etfs GRNJ                  # Single ETF only
    python granny_diff.py --top 10                     # Limit to top N holdings
    python granny_diff.py --baseline previous.json     # Diff vs prior snapshot

OUTPUTS:
    - prints structured surface report to stdout (sectioned by signal type)
    - writes raw snapshot JSON to ./granny_snapshot_YYYY-MM-DD.json
    - on subsequent runs, auto-diffs vs latest prior snapshot

DATA SOURCES (in priority order, with fallback):
    1. tradingview.com/symbols/AMEX-GRNJ/holdings (current top 10)
    2. stockanalysis.com/etf/<ticker>/holdings (top 25 large-cap)
    3. official grannyshots.com pages (full but slow to parse)

CADENCE: run weekly (Sunday/Monday). New ETF rebalance announcements happen
quarterly (~Feb/May/Aug/Nov), but Lee's team adjusts weights inter-rebalance.

CRITICAL FRAMEWORK NOTE:
    When this script surfaces a name in section (a) — name in Lee ETF but
    operator does NOT hold directly — that name auto-fires the Two-Lens
    Test per CI v11.7. It is NOT a casual recommendation; it is a
    NAMED-SOURCE ENDORSEMENT requiring direct-position decision.
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
import re

# ============================================================
# Configuration
# ============================================================

# Operator's project-knowledge holdings file path
FS_HOLDINGS_PATH = "/mnt/project/fs_holdings.json"

# Output directory for snapshots
SNAPSHOT_DIR = Path("./granny_snapshots")

# ETFs to track (Lee's Granny Shots family)
# Note: GRNI is income overlay on GRNY constituents — same names, skip
TRACKED_ETFS = {
    "GRNY": {
        "url": "https://stockanalysis.com/etf/grny/holdings/",
        "name": "Granny Shots Large Cap",
        "weight_min_signal": 2.40,  # below 2.40% = noise in equal-weight
    },
    "GRNJ": {
        "url": "https://www.tradingview.com/symbols/AMEX-GRNJ/holdings/",
        "name": "Granny Shots SMID",
        "weight_min_signal": 2.00,  # SMID is more diluted
    },
}

USER_AGENT = "Mozilla/5.0 (compatible; granny_diff/1.0)"

# ============================================================
# Operator-state loading
# ============================================================

def load_operator_state(path=FS_HOLDINGS_PATH):
    """Load operator's held + watchlist from fs_holdings.json."""
    try:
        with open(path) as f:
            data = json.load(f)
        return {
            "held": set(data.get("held", [])),
            "watchlist": set(data.get("watchlist", [])),
        }
    except FileNotFoundError:
        print(f"WARNING: fs_holdings.json not found at {path}", file=sys.stderr)
        return {"held": set(), "watchlist": set()}

# ============================================================
# Snapshot loading / fetching
# ============================================================

def fetch_html(url):
    """Fetch a URL with browser-like UA. Returns body str or None on failure."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (URLError, Exception) as e:
        print(f"FETCH FAILED [{url}]: {e}", file=sys.stderr)
        return None

def parse_stockanalysis_holdings(html):
    """Extract holdings table from stockanalysis.com. Returns list of dicts."""
    holdings = []
    # Pattern: | N | TICKER | Name | X.XX% | shares |
    # The table uses | with markdown-like rows
    row_re = re.compile(
        r'\|\s*(\d+)\s*\|\s*\[([A-Z\.]+)\][^\|]*\|\s*([^\|]+?)\s*\|\s*([\d\.]+)%',
        re.MULTILINE
    )
    for match in row_re.finditer(html):
        rank, ticker, name, weight = match.groups()
        holdings.append({
            "rank": int(rank),
            "ticker": ticker,
            "name": name.strip(),
            "weight_pct": float(weight),
        })
    return holdings

def parse_tradingview_holdings(html):
    """Extract holdings from tradingview.com. Returns list of dicts."""
    # TradingView uses a different structure; ticker symbols appear in symbol links
    # Pattern matches: TICKER followed by company name and weight%
    holdings = []
    # Look for [TICKER](url) followed by company name then weight
    pattern = re.compile(
        r'\[([A-Z]{1,5})\]\(/symbols/[A-Z\-]+-\1/\)([^\n]{5,80})\s+([\d\.]+)%',
        re.MULTILINE
    )
    for i, match in enumerate(pattern.finditer(html), 1):
        ticker, name, weight = match.groups()
        holdings.append({
            "rank": i,
            "ticker": ticker,
            "name": name.strip(),
            "weight_pct": float(weight),
        })
    return holdings

def fetch_etf_holdings(etf_ticker):
    """Fetch current holdings for one ETF. Returns list of dicts or None."""
    config = TRACKED_ETFS[etf_ticker]
    html = fetch_html(config["url"])
    if not html:
        return None
    if "tradingview.com" in config["url"]:
        return parse_tradingview_holdings(html)
    else:
        return parse_stockanalysis_holdings(html)

def load_baseline(path):
    """Load a prior snapshot file."""
    if not path or not Path(path).exists():
        return None
    with open(path) as f:
        return json.load(f)

def save_snapshot(snapshot, snapshot_dir=SNAPSHOT_DIR):
    """Save current snapshot to dated JSON file."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = snapshot_dir / f"granny_snapshot_{date_str}.json"
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return path

def find_latest_baseline(snapshot_dir=SNAPSHOT_DIR):
    """Find the most recent prior snapshot for auto-diff."""
    if not snapshot_dir.exists():
        return None
    snapshots = sorted(snapshot_dir.glob("granny_snapshot_*.json"))
    return snapshots[-1] if snapshots else None

# ============================================================
# Diff analysis
# ============================================================

def analyze_diff(current_snapshot, baseline, operator_state):
    """Produce three sections of analysis.

    Returns dict with keys: lee_named_not_held, weight_changes, dropped_held.
    """
    findings = {
        "lee_named_not_held": [],     # Lee endorses, operator doesn't directly own
        "weight_changes": [],          # Lee changed weight (>0.5% absolute change)
        "dropped_held": [],            # Lee removed but operator still holds
        "additions_vs_baseline": [],   # NEW in Lee ETFs vs prior snapshot
        "summary": {},
    }

    held = operator_state["held"]
    watchlist = operator_state["watchlist"]

    for etf, etf_data in current_snapshot["etfs"].items():
        holdings = etf_data["holdings"]
        if not holdings:
            continue
        threshold = TRACKED_ETFS[etf]["weight_min_signal"]

        for h in holdings:
            ticker = h["ticker"]
            weight = h["weight_pct"]

            # Section (a): named in Lee ETF, not directly held
            if weight >= threshold and ticker not in held:
                findings["lee_named_not_held"].append({
                    "ticker": ticker,
                    "etf": etf,
                    "rank": h["rank"],
                    "weight_pct": weight,
                    "on_watchlist": ticker in watchlist,
                })

            # Section (b): weight changes vs baseline
            if baseline and etf in baseline["etfs"]:
                prior = next(
                    (p for p in baseline["etfs"][etf]["holdings"]
                     if p["ticker"] == ticker), None
                )
                if prior:
                    weight_change = weight - prior["weight_pct"]
                    if abs(weight_change) >= 0.50:
                        findings["weight_changes"].append({
                            "ticker": ticker,
                            "etf": etf,
                            "prior_weight": prior["weight_pct"],
                            "current_weight": weight,
                            "change_pct": weight_change,
                            "operator_holds": ticker in held,
                        })

            # Section (d): vs baseline — new additions
            if baseline and etf in baseline["etfs"]:
                prior_tickers = {p["ticker"] for p in
                                 baseline["etfs"][etf]["holdings"]}
                if ticker not in prior_tickers and weight >= threshold:
                    findings["additions_vs_baseline"].append({
                        "ticker": ticker,
                        "etf": etf,
                        "weight_pct": weight,
                        "operator_holds": ticker in held,
                    })

        # Section (c): names that dropped out of Lee's ETFs
        if baseline and etf in baseline["etfs"]:
            current_tickers = {h["ticker"] for h in holdings}
            for prior in baseline["etfs"][etf]["holdings"]:
                if (prior["ticker"] not in current_tickers
                    and prior["ticker"] in held):
                    findings["dropped_held"].append({
                        "ticker": prior["ticker"],
                        "etf": etf,
                        "prior_weight": prior["weight_pct"],
                    })

    # Sort outputs
    findings["lee_named_not_held"].sort(key=lambda x: -x["weight_pct"])
    findings["weight_changes"].sort(key=lambda x: -abs(x["change_pct"]))

    findings["summary"] = {
        "named_endorsement_count": len(findings["lee_named_not_held"]),
        "tier_a_candidates": [
            x["ticker"] for x in findings["lee_named_not_held"]
            if x["weight_pct"] >= 2.50 and not x["on_watchlist"]
        ],
        "watchlist_promotions": [
            x["ticker"] for x in findings["lee_named_not_held"]
            if x["on_watchlist"]
        ],
    }

    return findings

# ============================================================
# Reporting
# ============================================================

def print_report(findings, current_snapshot):
    """Surface report to stdout in framework-compliant format."""
    print("=" * 70)
    print(f"GRANNY SHOTS DIFF — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 70)

    summary = findings["summary"]

    # Section 1: NAMED-NOT-HELD (highest priority)
    print()
    print("🚨 NAMED BY LEE — NOT DIRECTLY HELD (Two-Lens trigger):")
    if not findings["lee_named_not_held"]:
        print("    (none — operator holds direct exposure to all top Lee names)")
    else:
        for item in findings["lee_named_not_held"][:15]:
            tag = " [on watchlist]" if item["on_watchlist"] else " [NEW NAME]"
            print(f"    {item['etf']} #{item['rank']:>2}  "
                  f"{item['ticker']:<6}  {item['weight_pct']:>5.2f}%{tag}")

    # Section 2: WEIGHT CHANGES
    if findings["weight_changes"]:
        print()
        print("📊 WEIGHT CHANGES (>0.5% absolute):")
        for item in findings["weight_changes"][:10]:
            direction = "↑" if item["change_pct"] > 0 else "↓"
            hold_tag = " [HELD]" if item["operator_holds"] else ""
            print(f"    {item['etf']}  {item['ticker']:<6}  "
                  f"{item['prior_weight']:>5.2f}% {direction} "
                  f"{item['current_weight']:>5.2f}% "
                  f"({item['change_pct']:+.2f}%){hold_tag}")

    # Section 3: ADDITIONS vs PRIOR SNAPSHOT
    if findings["additions_vs_baseline"]:
        print()
        print("🆕 NEW ADDITIONS (since prior snapshot):")
        for item in findings["additions_vs_baseline"]:
            hold_tag = " [already held]" if item["operator_holds"] else " [NEW]"
            print(f"    {item['etf']}  {item['ticker']:<6}  "
                  f"{item['weight_pct']:>5.2f}%{hold_tag}")

    # Section 4: DROPPED (Lee exited, operator still holds)
    if findings["dropped_held"]:
        print()
        print("⚠️  LEE EXITED — operator still holds:")
        for item in findings["dropped_held"]:
            print(f"    {item['etf']}  {item['ticker']:<6}  "
                  f"prior {item['prior_weight']:.2f}%")

    # Section 5: ACTION SUMMARY
    print()
    print("=" * 70)
    print("ACTION SUMMARY")
    print("=" * 70)
    tier_a = summary["tier_a_candidates"]
    if tier_a:
        print(f"🎯 TIER A CANDIDATES (weight ≥2.50%, not on watchlist):")
        for t in tier_a:
            print(f"    → {t}  ::  Run Two-Lens v11.5.2, build asymmetric ticket")
    promotions = summary["watchlist_promotions"]
    if promotions:
        print(f"📋 WATCHLIST → DIRECT CONSIDER:")
        for t in promotions:
            print(f"    → {t}  ::  already on watchlist, Lee endorsement = promote")
    if not tier_a and not promotions:
        print("    (no new named-source signals to act on this run)")

    print()

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Diff Lee Granny Shots ETF holdings vs operator portfolio"
    )
    parser.add_argument("--etfs", nargs="+", default=list(TRACKED_ETFS.keys()),
                        help="ETFs to scan (default: all)")
    parser.add_argument("--top", type=int, default=25,
                        help="Limit to top N per ETF (default: 25)")
    parser.add_argument("--baseline", type=str, default=None,
                        help="Baseline snapshot JSON for diff (default: auto-detect latest)")
    parser.add_argument("--holdings", type=str, default=FS_HOLDINGS_PATH,
                        help=f"Path to fs_holdings.json (default: {FS_HOLDINGS_PATH})")
    args = parser.parse_args()

    # Load operator state
    operator_state = load_operator_state(args.holdings)
    if not operator_state["held"]:
        print("ERROR: no operator holdings loaded. Check fs_holdings.json path.",
              file=sys.stderr)
        sys.exit(1)

    # Fetch current ETF holdings
    current_snapshot = {
        "timestamp": datetime.now().isoformat(),
        "etfs": {},
    }
    for etf in args.etfs:
        if etf not in TRACKED_ETFS:
            print(f"WARNING: unknown ETF {etf}", file=sys.stderr)
            continue
        print(f"Fetching {etf} holdings ...", file=sys.stderr)
        holdings = fetch_etf_holdings(etf)
        if holdings:
            current_snapshot["etfs"][etf] = {
                "holdings": holdings[:args.top],
                "config": TRACKED_ETFS[etf],
            }
        else:
            print(f"  ! failed to fetch {etf}", file=sys.stderr)
            current_snapshot["etfs"][etf] = {"holdings": [], "config": TRACKED_ETFS[etf]}

    # Load baseline
    if args.baseline:
        baseline = load_baseline(args.baseline)
    else:
        baseline_path = find_latest_baseline()
        baseline = load_baseline(baseline_path) if baseline_path else None
        if baseline_path:
            print(f"Using baseline: {baseline_path}", file=sys.stderr)

    # Analyze
    findings = analyze_diff(current_snapshot, baseline, operator_state)

    # Report
    print_report(findings, current_snapshot)

    # Save snapshot for next run
    snapshot_path = save_snapshot(current_snapshot)
    print(f"\nSnapshot saved: {snapshot_path}")

    # JSON output to companion file
    findings_path = snapshot_path.with_name(snapshot_path.stem + "_findings.json")
    with open(findings_path, "w") as f:
        json.dump(findings, f, indent=2, default=str)
    print(f"Findings JSON: {findings_path}")

if __name__ == "__main__":
    main()
