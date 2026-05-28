"""
session_open_preflight.py
==========================
v11.17 Unified Session-Open Pre-Flight Runner.

Single entry point for all v11.16 + v11.17 pre-flight checks. Runs in sequence:
  1. recommendations_digest  (v11.17 Active Recommendations Digest)
  2. options_expiry_preflight (v11.16 Patch 2 Options <30 DTE)
  3. position_drift_check    (v11.16 Patch 3 Memory baseline vs actual)
  4. inbox_audit_summary     (v11.16 Patch 1 — placeholder; full audit done via Notion MCP)

Composes the v11.17 unified pre-flight format:
  'Pre-flight: N rationales (M flagged). ... OPTIONS EXPIRY: S options <30 DTE
   (T action-required <5 DTE). POSITION DRIFT: U checked, V drift-flagged.
   RECOMMENDATIONS DIGEST: W FRESH, X MEDIUM, Y OLDER, Z STALE; W2 duplicates,
   W3 superseded, W4 untitled.'

CLI usage:
  python session_open_preflight.py \
      --rationales rationales.json \
      --portfolio latest_portfolio.json \
      --memory memory.txt \
      --prices '{"IVES":36.84,"BMNR":21.91}'

  # Or for just the one-line summary:
  python session_open_preflight.py --rationales rationales.json \
      --portfolio latest_portfolio.json --memory memory.txt --summary-only

Author: Investing 2026 framework v11.17
Date: 2026-05-14
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime

# Import sibling modules
from recommendations_digest import (
    Rationale,
    enrich_rationales,
    group_by_freshness,
    detect_duplicates,
    detect_likely_superseded,
    detect_untitled,
    detect_expired_unmarked,
    render_markdown as render_digest_md,
)
from options_expiry_preflight import (
    load_positions_from_portfolio,
    scan_positions,
    render_markdown as render_options_md,
)
from position_drift_check import (
    parse_memory_baselines,
    load_actuals_from_portfolio,
    cross_reference,
    render_markdown as render_drift_md,
)


def run_preflight(
    rationales_path: str,
    portfolio_path: str,
    memory_path: str,
    prices: dict,
    as_of: date,
    drift_threshold: float = 0.10,
) -> dict:
    """Run all pre-flight checks and return structured results.

    Returns dict with keys: digest, options, drift, summary_line
    """
    results = {}

    # 1. Recommendations digest
    with open(rationales_path) as f:
        raw_rationales = json.load(f)
    rationales = [Rationale.from_dict(d) for d in raw_rationales]
    enrich_rationales(rationales, as_of)
    active = [r for r in rationales if r.status == "Active"]
    freshness_groups = group_by_freshness(active)
    duplicates = detect_duplicates(active)
    superseded = detect_likely_superseded(duplicates)
    untitled = detect_untitled(active)
    stale_unmarked = detect_expired_unmarked(active, as_of)

    results["digest"] = {
        "total_active": len(active),
        "total_all": len(rationales),
        "fresh": len(freshness_groups.get("FRESH", [])),
        "medium": len(freshness_groups.get("MEDIUM", [])),
        "older": len(freshness_groups.get("OLDER", [])),
        "stale": len(freshness_groups.get("STALE", [])),
        "duplicates_tickers": len(duplicates),
        "superseded_pairs": len(superseded),
        "untitled": len(untitled),
        "stale_unmarked": len(stale_unmarked),
        "markdown": render_digest_md(rationales, as_of),
    }

    # 2. Options expiry pre-flight
    with open(portfolio_path) as f:
        portfolio = json.load(f)
    option_positions = load_positions_from_portfolio(portfolio)
    scan_positions(option_positions, prices, as_of)

    action_required = [p for p in option_positions if p.action_band == "ACTION_REQUIRED"]
    watch = [p for p in option_positions if p.action_band == "WATCH"]
    expired = [p for p in option_positions if p.action_band == "EXPIRED"]

    results["options"] = {
        "total_options": len(option_positions),
        "under_30_dte": len(action_required) + len(watch),
        "action_required": len(action_required),
        "expired": len(expired),
        "markdown": render_options_md(option_positions, as_of),
    }

    # 3. Position drift check
    with open(memory_path) as f:
        memory_text = f.read()
    baselines = parse_memory_baselines(memory_text)
    actuals = load_actuals_from_portfolio(portfolio)
    drift, unmatched_b, unmatched_a = cross_reference(baselines, actuals, drift_threshold)

    flagged = [d for d in drift if d.is_flagged]
    alarm = [d for d in drift if "ALARM_DRIFT" in d.flags]

    results["drift"] = {
        "baselines_parsed": len(baselines),
        "positions_checked": len(drift),
        "drift_flagged": len(flagged),
        "alarm_drifts": len(alarm),
        "unmatched_baselines": len(unmatched_b),
        "markdown": render_drift_md(drift, unmatched_b, unmatched_a, drift_threshold),
    }

    # 4. Inbox audit placeholder (full audit requires Notion MCP — done by caller)
    results["inbox_audit"] = {
        "status": "pending_mcp_fetch",
        "note": "Full 7-day Inbox audit requires Notion MCP; not callable from CLI",
    }

    # Compose summary line (v11.17 pre-flight format)
    d = results["digest"]
    o = results["options"]
    dr = results["drift"]
    results["summary_line"] = (
        f"Pre-flight: {d['total_active']} Active rationales "
        f"({d['duplicates_tickers']} dup-tickers, {d['superseded_pairs']} superseded, "
        f"{d['untitled']} untitled, {d['stale_unmarked']} stale-unmarked). "
        f"Recommendations Digest: {d['fresh']} FRESH / {d['medium']} MEDIUM / "
        f"{d['older']} OLDER / {d['stale']} STALE. "
        f"Options Expiry: {o['under_30_dte']} options <30 DTE "
        f"({o['action_required']} ACTION REQUIRED, {o['expired']} expired). "
        f"Position Drift: {dr['positions_checked']} checked, "
        f"{dr['drift_flagged']} flagged ({dr['alarm_drifts']} alarm), "
        f"{dr['unmatched_baselines']} unmatched baselines."
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="v11.17 Unified Session-Open Pre-Flight Runner"
    )
    parser.add_argument("--rationales", required=True,
                        help="Path to Active Trade Rationales JSON export")
    parser.add_argument("--portfolio", required=True,
                        help="Path to Latest Portfolio JSON")
    parser.add_argument("--memory", required=True,
                        help="Path to operator memory text file")
    parser.add_argument("--prices", default="{}",
                        help='JSON dict of underlying ticker → price')
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--drift-threshold", type=float, default=0.10)
    parser.add_argument("--summary-only", action="store_true",
                        help="Output only the one-line pre-flight summary")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    prices = json.loads(args.prices)
    as_of = datetime.fromisoformat(args.as_of).date()

    results = run_preflight(
        args.rationales,
        args.portfolio,
        args.memory,
        prices,
        as_of,
        args.drift_threshold,
    )

    if args.summary_only:
        print(results["summary_line"])
        return

    if args.format == "json":
        # Strip the markdown subkeys for JSON output
        out = {
            k: {k2: v2 for k2, v2 in v.items() if k2 != "markdown"}
            for k, v in results.items()
            if k != "summary_line"
        }
        out["summary_line"] = results["summary_line"]
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"# 🛫 Session-Open Pre-Flight\n")
        print(f"**As of: {as_of.isoformat()}**\n")
        print(f"## One-line summary\n\n> {results['summary_line']}\n\n---\n")
        print(results["digest"]["markdown"])
        print("\n---\n")
        print(results["options"]["markdown"])
        print("\n---\n")
        print(results["drift"]["markdown"])


if __name__ == "__main__":
    main()
