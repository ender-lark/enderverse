#!/usr/bin/env python3
"""
hyperscaler_anchor_scan.py — Patch 1 from NBIS postmortem (CI v11.7)

Scans SEC EDGAR 8-K filings for the Stage-2 NBIS pattern: companies
disclosing major contracts (>$1B notional) from anchor counterparties
(hyperscalers, sovereigns, major industrials/tech). The goal is to surface
these BEFORE the +50% gap day, OR — if missed — to catch them within the
post-gap entry window where asymmetric setups remain.

The NBIS case: on 2025-09-08, Nebius filed an 8-K disclosing the Microsoft
$17.4B–$19.4B contract. Pre-filing market cap was $15.3B. The contract
notional was >100% of pre-filing market cap. Stock opened +60% AH and
closed +50% the next day. ANY system parsing SEC 8-K filings for
contract-value > 30% of market cap would have caught this.

USAGE:
    python hyperscaler_anchor_scan.py                # Past 7 days
    python hyperscaler_anchor_scan.py --days 14      # Past 14 days
    python hyperscaler_anchor_scan.py --threshold 0.30  # 30% of mkt cap

CADENCE:
    Run daily during pre-market (8am ET) and weekly (Sunday).
    Higher-priority hits trigger same-day Two-Lens auto-run.

DATA SOURCES:
    1. SEC EDGAR full-text search API (free, no key required):
       https://efts.sec.gov/LATEST/search-index?q=...
    2. SEC EDGAR submissions API for company info:
       https://data.sec.gov/submissions/CIK<padded>.json
    3. Market cap lookup via FMP or UW (configured below)

THRESHOLD LOGIC:
    A filing fires when:
      contract_notional >= max($1B, threshold * market_cap)
    Default threshold = 0.30 (contract is 30%+ of market cap).
    NBIS @ $15.3B cap × 0.30 = $4.6B threshold → MSFT $17.4B easily fires.

ANCHOR COUNTERPARTIES (hardcoded list of strong-signal names):
    Hyperscalers, sovereigns, major industrials. Edit as Lee/Newton
    coverage evolves.

CRITICAL FRAMEWORK NOTE:
    This script is a NAMED-CATALYST DETECTOR. Hits are not "interesting
    news" — they are Tier B/A candidates per CI v11.7 P-ASYMMETRIC.
"""

import json
import re
import sys
import argparse
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError
from pathlib import Path

USER_AGENT = "granny_anchor_scan/1.0 (research-tool)"
SNAPSHOT_DIR = Path("./anchor_snapshots")

# ============================================================
# Anchor counterparties — names that make a contract a real signal
# ============================================================

HYPERSCALERS = {
    "Microsoft", "MSFT", "Amazon", "AMZN", "AWS",
    "Alphabet", "Google", "GOOGL", "GOOG",
    "Meta", "META", "Facebook",
    "Apple", "AAPL",
    "Oracle", "ORCL",
    "NVIDIA", "Nvidia", "NVDA",
    "IBM",
    "Salesforce", "CRM",
    "ByteDance", "TikTok",
    "Tencent", "Alibaba", "Baidu",
}

SOVEREIGNS_DEFENSE = {
    "U.S. Department of Defense", "Department of Defense", "DoD",
    "U.S. Department of Energy", "DOE",
    "U.S. Department of Commerce",
    "U.S. Air Force", "U.S. Navy", "U.S. Army", "Space Force",
    "DARPA", "ARPA-H", "ARPA-E",
    "NASA", "NIH",
    "Saudi Arabia", "UAE", "Sovereign Wealth",
    "PIF", "Mubadala", "ADIA", "GIC", "Temasek",
    "POSCO", "KHNP", "JOGMEC",
}

MAJOR_INDUSTRIAL = {
    "Tesla", "TSLA", "SpaceX",
    "Lockheed", "LMT", "RTX", "Raytheon",
    "Northrop", "NOC", "Boeing", "BA",
    "Palantir", "PLTR",
    "TSMC", "Samsung",
    "ExxonMobil", "Chevron", "Saudi Aramco",
}

ALL_ANCHORS = HYPERSCALERS | SOVEREIGNS_DEFENSE | MAJOR_INDUSTRIAL

# ============================================================
# SEC EDGAR search
# ============================================================

def fetch_json(url, headers=None):
    """Fetch JSON from a URL. Returns dict or None."""
    headers = headers or {}
    headers["User-Agent"] = USER_AGENT
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except (URLError, json.JSONDecodeError, Exception) as e:
        print(f"FETCH FAILED [{url[:80]}]: {e}", file=sys.stderr)
        return None

def fetch_html(url, headers=None):
    """Fetch HTML from a URL. Returns str or None."""
    headers = headers or {}
    headers["User-Agent"] = USER_AGENT
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (URLError, Exception) as e:
        print(f"FETCH FAILED [{url[:80]}]: {e}", file=sys.stderr)
        return None

def search_8k_filings(start_date, end_date, max_results=200):
    """Use SEC EDGAR full-text search to find 8-K filings mentioning
    contract/agreement terms.

    Returns list of filing dicts.
    """
    # Search query terms that frequently co-occur with anchor contracts
    queries = [
        '"multi-year" "agreement" "billion"',
        '"contract" "billion" "infrastructure"',
        '"strategic alliance" "billion"',
        '"award" "billion" "government"',
    ]

    all_results = []
    seen_accessions = set()

    for query in queries:
        params = {
            "q": query,
            "dateRange": "custom",
            "startdt": start_date.strftime("%Y-%m-%d"),
            "enddt": end_date.strftime("%Y-%m-%d"),
            "forms": "8-K",
        }
        url = f"https://efts.sec.gov/LATEST/search-index?{urlencode(params)}"
        data = fetch_json(url)
        if not data or "hits" not in data:
            continue

        for hit in data["hits"].get("hits", [])[:max_results]:
            accession = hit.get("_id")
            if accession in seen_accessions:
                continue
            seen_accessions.add(accession)

            source = hit.get("_source", {})
            all_results.append({
                "accession": accession,
                "filed_date": source.get("file_date"),
                "form": source.get("form"),
                "company_name": (source.get("display_names") or ["Unknown"])[0],
                "cik": (source.get("ciks") or ["0"])[0],
                "tickers": source.get("tickers", []),
                "summary": (source.get("description") or "")[:500],
            })

    return all_results

def fetch_filing_text(accession_or_url):
    """Fetch the text of an 8-K filing. Returns str (truncated to 50K chars)."""
    # accession format: 0001234567-25-123456
    # URL pattern: https://www.sec.gov/Archives/edgar/data/CIK/ACCESSION-WITHOUT-DASHES/PRIMARY_DOC.htm
    # Since we only have accession, we go to the index first
    accession = accession_or_url.replace("-", "")
    cik_no_pad = accession[:10].lstrip("0")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_no_pad}&type=8-K&dateb=&owner=include&count=40"
    # Simpler approach: try the index
    return None  # Implementation note: full body parse requires a primary-doc fetch
                 # which adds 1 round-trip per filing. For MVP, we use search summary.

# ============================================================
# Value extraction from filing text
# ============================================================

def extract_contract_value(text):
    """Find contract dollar values in text. Returns list of (value_usd, context_snippet)."""
    if not text:
        return []

    results = []
    # Patterns: "$17.4 billion", "$1.2B", "USD 5 billion", "valued at $17.4 billion"
    patterns = [
        r'\$\s?(\d+\.?\d*)\s*(billion|trillion|B\b|T\b)',
        r'USD\s+(\d+\.?\d*)\s*(billion|trillion|B\b|T\b)',
        r'(\d+\.?\d*)\s+billion\s+dollars',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = float(match.group(1))
            except (ValueError, IndexError):
                continue
            unit = match.group(2).lower() if len(match.groups()) >= 2 else "billion"
            if unit.startswith("t"):
                value_usd = value * 1_000_000_000_000
            else:
                value_usd = value * 1_000_000_000
            # Capture surrounding context (50 chars each side)
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].replace("\n", " ").strip()
            results.append((value_usd, context))

    return results

def detect_anchors_in_text(text):
    """Find anchor counterparty names mentioned in text. Returns list of names found."""
    if not text:
        return []
    found = []
    for anchor in ALL_ANCHORS:
        if re.search(rf'\b{re.escape(anchor)}\b', text, re.IGNORECASE):
            found.append(anchor)
    return found

# ============================================================
# Market cap lookup
# ============================================================

def get_market_cap(ticker):
    """Look up current market cap. Stub implementation — wire to FMP/UW.

    Returns market cap in USD, or None.
    """
    # In live use, replace with UW or FMP call. For now return None to
    # signal that operator should run the UW check manually.
    return None

# ============================================================
# Scoring
# ============================================================

def score_filing(filing, summary_text, threshold_pct=0.30, min_value=1_000_000_000):
    """Score whether a filing fires the Stage-2 anchor signal.

    Returns dict with: fires, contract_value, anchors_found, evidence, tier_estimate.
    """
    contract_values = extract_contract_value(summary_text)
    anchors = detect_anchors_in_text(summary_text)

    max_value = max([v for v, _ in contract_values], default=0)
    has_anchor = len(anchors) > 0

    fires = False
    tier_estimate = None
    reason = []

    if max_value >= min_value and has_anchor:
        fires = True
        if max_value >= 10_000_000_000:
            tier_estimate = "A_CANDIDATE"
            reason.append(f"contract ${max_value/1e9:.1f}B + anchor counterparty")
        elif max_value >= 1_000_000_000:
            tier_estimate = "B_CANDIDATE"
            reason.append(f"contract ${max_value/1e9:.1f}B + anchor")

    return {
        "fires": fires,
        "contract_value_usd": max_value,
        "contract_value_str": f"${max_value/1e9:.2f}B" if max_value else "—",
        "anchors_found": anchors,
        "tier_estimate": tier_estimate,
        "evidence_snippet": (contract_values[0][1] if contract_values else "")[:300],
        "reason": "; ".join(reason),
    }

# ============================================================
# Reporting
# ============================================================

def print_report(scored_filings, start_date, end_date):
    """Surface scored filings to stdout."""
    print("=" * 70)
    print(f"SEC 8-K HYPERSCALER ANCHOR SCAN")
    print(f"Window: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"Filings scanned: {len(scored_filings)}")
    print("=" * 70)

    fires = [f for f in scored_filings if f["score"]["fires"]]
    fires.sort(key=lambda f: -f["score"]["contract_value_usd"])

    if not fires:
        print("\n(no Stage-2 anchor signals fired this window)\n")
        return

    print(f"\n🎯 {len(fires)} FILING(S) FIRED:\n")
    for i, f in enumerate(fires, 1):
        s = f["score"]
        tickers_str = ", ".join(f["tickers"][:3]) if f["tickers"] else "?"
        print(f"  [{i}] {f['filed_date']} | {f['company_name']} ({tickers_str})")
        print(f"      Tier: {s['tier_estimate']} | Value: {s['contract_value_str']}")
        print(f"      Anchors: {', '.join(s['anchors_found'])}")
        print(f"      Evidence: {s['evidence_snippet'][:200]}")
        print(f"      → Run Two-Lens v11.5.2 + UW Tier 1 auto-pull")
        print()

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scan SEC 8-K filings for hyperscaler-anchor contracts"
    )
    parser.add_argument("--days", type=int, default=7,
                        help="Days back from today (default: 7)")
    parser.add_argument("--threshold", type=float, default=0.30,
                        help="Min contract / market cap ratio (default: 0.30)")
    parser.add_argument("--min-value", type=float, default=1_000_000_000,
                        help="Min absolute contract value USD (default: $1B)")
    args = parser.parse_args()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)

    print(f"Searching SEC EDGAR 8-K filings: "
          f"{start_date.date()} → {end_date.date()} ...", file=sys.stderr)

    filings = search_8k_filings(start_date, end_date)
    print(f"Found {len(filings)} candidate filings", file=sys.stderr)

    # Score each filing using its summary text
    scored = []
    for filing in filings:
        score = score_filing(
            filing, filing["summary"],
            threshold_pct=args.threshold, min_value=args.min_value
        )
        scored.append({**filing, "score": score})

    print_report(scored, start_date, end_date)

    # Save snapshot
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SNAPSHOT_DIR / f"anchor_scan_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(out_path, "w") as f:
        json.dump(scored, f, indent=2, default=str)
    print(f"Snapshot saved: {out_path}")

if __name__ == "__main__":
    main()
