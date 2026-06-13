#!/usr/bin/env python3
"""Classify untracked account positions for thesis/sleeve cleanup.

The account-position cache is the source of truth for current holdings. This
module keeps the triage deterministic and data-only: it reads the cache,
cross-references the current Fundstrat bible, and writes review artifacts.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_POSITIONS = ROOT / "account_positions.json"
DEFAULT_BIBLE = ROOT / "fundstrat_bible.json"
DEFAULT_JSON_OUT = ROOT / "orphan_triage.json"
DEFAULT_MD_OUT = ROOT / "orphan_triage.md"

DUST_MAX = 2_000.0
SMALL_MAX = 10_000.0

CASH_EQUIV = {"SPAXX", "FDRXX", "FBGKX"}
ETF_OR_FUND = {
    "ARKG", "CIBR", "DRIV", "ETHA", "FBGKX", "FDRXX", "FCASH", "FTXL",
    "GDX", "IBIT", "IHF", "ITA", "IYT", "LIT", "MSOS", "PBW", "RPG",
    "SIL", "SNSR", "SOXX", "SPAXX", "XLI",
}

THEME_MAP: dict[str, list[str]] = {
    "AMD": ["semis", "AI-infra"],
    "ANET": ["AI-infra"],
    "AMZN": ["AI-infra"],
    "ASML": ["semis", "AI-infra"],
    "AVGO": ["semis", "AI-infra"],
    "BE": ["AI-infra"],
    "CIBR": ["AI-infra"],
    "CRWD": ["AI-infra"],
    "DRIV": ["AI-infra"],
    "FN": ["AI-infra"],
    "FTXL": ["semis", "AI-infra"],
    "GEV": ["AI-infra"],
    "GOOGL": ["AI-infra"],
    "LITE": ["AI-infra"],
    "MSFT": ["AI-infra"],
    "NBIS": ["AI-infra"],
    "NXT": ["AI-infra"],
    "ORCL": ["AI-infra"],
    "PANW": ["AI-infra"],
    "POET": ["semis", "AI-infra"],
    "PWR": ["AI-infra"],
    "SOXX": ["semis", "AI-infra"],
    "TSM": ["semis", "AI-infra"],
    "BWXT": ["nuclear"],
    "CCJ": ["nuclear"],
    "UURAF": ["nuclear"],
    "TLOFF": ["nuclear"],
    "GDX": ["precious-metals"],
    "SIL": ["precious-metals"],
    "WPM": ["precious-metals"],
    "AAVE": ["crypto"],
    "COIN": ["crypto"],
    "ETH": ["crypto"],
    "ETHA": ["crypto"],
    "IBIT": ["crypto"],
    "MSTR": ["crypto"],
    "ORBS": ["crypto"],
    "SOL": ["crypto"],
    "TRUMP": ["crypto"],
    "FBGKX": ["cash-equiv"],
    "FDRXX": ["cash-equiv"],
    "SPAXX": ["cash-equiv"],
}

WHAT_TO_OWN_THEME_MAP: dict[str, set[str]] = {
    "mag7": {"AMZN", "GOOGL", "MSFT", "TSLA"},
    "ethereum": {"ETH", "ETHA"},
    "software": {"CIBR", "CRWD", "MSFT", "ORCL", "PANW"},
    "industrials": {"BWXT", "FIX", "GEV", "IESC", "ITA", "NXT", "PWR", "STRL", "XLI"},
    "financials": {"GS", "HOOD", "JPM"},
    "small-caps": {"ASTS", "CRS", "FIX", "FN", "IESC", "LUNR", "POET", "STRL", "UMAC"},
    "energy/basic materials": {
        "ARRRF", "CCJ", "GDX", "LIT", "LYSDY", "NUE", "PBW", "SIL", "TLOFF", "UURAF", "WPM",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: Any) -> float:
    if value in (None, "") or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _ticker_from_item(item: Any) -> str | None:
    if isinstance(item, dict):
        value = item.get("ticker")
    else:
        value = item
    ticker = str(value or "").strip().upper()
    return ticker or None


def _fs_references(bible: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "direct_lists": [],
        "what_to_own": [],
        "june_basket": [],
    })

    for list_name in ("top5", "bottom5", "top5_smid", "bottom5_smid"):
        for rank, item in enumerate(bible.get(list_name) or [], start=1):
            ticker = _ticker_from_item(item)
            if not ticker:
                continue
            refs[ticker]["direct_lists"].append({"list": list_name, "rank": rank})

    sector_allocation = bible.get("sector_allocation") or {}
    for item in sector_allocation.get("june_etf_basket") or []:
        ticker = _ticker_from_item(item)
        if not ticker:
            continue
        refs[ticker]["june_basket"].append({
            "status": item.get("status") if isinstance(item, dict) else "",
            "theme": item.get("theme") if isinstance(item, dict) else "",
        })

    current_themes = {
        str(theme or "").strip().lower()
        for theme in (bible.get("what_to_own") or [])
        if theme
    }
    for theme, tickers in WHAT_TO_OWN_THEME_MAP.items():
        if theme not in current_themes:
            continue
        for ticker in tickers:
            refs[ticker]["what_to_own"].append(theme)

    return {ticker: dict(ref) for ticker, ref in refs.items()}


def _account_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    accounts: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        account = str(row.get("account") or "Unknown").strip()
        if ticker:
            accounts[ticker].add(account)
    return {ticker: len(values) for ticker, values in accounts.items()}


def _size_bucket(market_value: float) -> str:
    if market_value < DUST_MAX:
        return "<$2K dust"
    if market_value <= SMALL_MAX:
        return "$2-10K small"
    return ">$10K material"


def _is_fund_like(ticker: str, row: dict[str, Any]) -> bool:
    asset_type = str(row.get("asset_type") or "").lower()
    description = str(row.get("description") or "").lower()
    if ticker in ETF_OR_FUND or ticker in CASH_EQUIV:
        return True
    return any(token in asset_type or token in description for token in ("etf", "fund", "trust"))


def _suggest_disposition(
    ticker: str,
    row: dict[str, Any],
    fs_status: dict[str, Any],
    themes: list[str],
    market_value: float,
) -> str:
    if "cash-equiv" in themes or ticker in CASH_EQUIV:
        return "WATCH"
    if market_value < DUST_MAX and not fs_status.get("direct_lists"):
        return "DUST"
    if _is_fund_like(ticker, row):
        return "MERGE-INTO-SLEEVE"
    if market_value > SMALL_MAX:
        return "NEEDS-THESIS"
    if fs_status.get("direct_lists"):
        return "NEEDS-THESIS"
    return "WATCH"


def classify_orphans(
    account_positions: dict[str, Any],
    fundstrat_bible: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return deterministic orphan triage payload."""
    fs_refs = _fs_references(fundstrat_bible)
    account_rows = account_positions.get("account_positions") or []
    account_count = _account_counts(account_rows)
    sleeve_value = _num(account_positions.get("sleeve_value"))

    orphans: list[dict[str, Any]] = []
    for row in account_positions.get("combined_positions") or []:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or row.get("tracked") is not False:
            continue
        market_value = round(_num(row.get("market_value")), 2)
        themes = sorted(THEME_MAP.get(ticker, []))
        fs_status = fs_refs.get(ticker, {"direct_lists": [], "what_to_own": [], "june_basket": []})
        size_bucket = _size_bucket(market_value)
        disposition = _suggest_disposition(ticker, row, fs_status, themes, market_value)
        pct_of_sleeve = round(market_value / sleeve_value * 100.0, 2) if sleeve_value else 0.0
        orphans.append({
            "ticker": ticker,
            "market_value": market_value,
            "pct_of_sleeve": pct_of_sleeve,
            "shares": row.get("shares") or 0,
            "account_count": account_count.get(ticker, 0),
            "owners": row.get("owners") or [],
            "size_bucket": size_bucket,
            "themes": themes,
            "fs_pick_status": fs_status,
            "suggested_disposition": disposition,
        })

    orphans.sort(key=lambda item: (-float(item["market_value"] or 0), item["ticker"]))
    disposition_counts: dict[str, int] = defaultdict(int)
    theme_counts: dict[str, int] = defaultdict(int)
    material_count = 0
    for item in orphans:
        disposition_counts[item["suggested_disposition"]] += 1
        for theme in item["themes"]:
            theme_counts[theme] += 1
        if item["size_bucket"] == ">$10K material":
            material_count += 1

    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "snapshot_date": account_positions.get("snapshot_date"),
        "sleeve_value": round(sleeve_value, 2),
        "fundstrat_bible_deck_date": fundstrat_bible.get("deck_date"),
        "core_stock_ideas_as_of": fundstrat_bible.get("core_stock_ideas_as_of"),
        "sector_allocation_as_of": (fundstrat_bible.get("sector_allocation") or {}).get("as_of"),
        "counts": {
            "orphans": len(orphans),
            "material": material_count,
            "by_disposition": dict(sorted(disposition_counts.items())),
            "by_theme": dict(sorted(theme_counts.items())),
        },
        "orphans": orphans,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("counts") or {}
    by_disp = counts.get("by_disposition") or {}
    lines = [
        "# Orphan Position Triage",
        "",
        f"Generated: {payload.get('generated_at')}",
        f"Positions snapshot: {payload.get('snapshot_date')}",
        f"Portfolio sleeve value: ${payload.get('sleeve_value', 0):,.0f}",
        (
            "Fundstrat layers: sector allocation "
            f"{payload.get('sector_allocation_as_of') or 'n/a'}; "
            f"core stock ideas {payload.get('core_stock_ideas_as_of') or payload.get('fundstrat_bible_deck_date') or 'n/a'}"
        ),
        "",
        (
            f"Summary: {counts.get('orphans', 0)} untracked tickers; "
            f"{counts.get('material', 0)} material >$10K; "
            + ", ".join(f"{k} {v}" for k, v in by_disp.items())
        ),
        "",
        "| Ticker | Value | % sleeve | Accounts | Size | Themes | FS status | Suggested |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for item in payload.get("orphans") or []:
        fs_status = item.get("fs_pick_status") or {}
        direct = [
            f"{row['list']}#{row['rank']}"
            for row in fs_status.get("direct_lists") or []
        ]
        wto = [f"what_to_own:{theme}" for theme in fs_status.get("what_to_own") or []]
        basket = [
            "june_basket" + (f":{row.get('status')}" if row.get("status") else "")
            for row in fs_status.get("june_basket") or []
        ]
        fs_text = ", ".join(direct + basket + wto) or "none"
        theme_text = ", ".join(item.get("themes") or []) or "unmapped"
        lines.append(
            f"| {item['ticker']} | ${item['market_value']:,.0f} | "
            f"{item['pct_of_sleeve']:.2f}% | {item['account_count']} | "
            f"{item['size_bucket']} | {theme_text} | {fs_text} | "
            f"{item['suggested_disposition']} |"
        )
    lines.append("")
    lines.append("Disposition meanings: NEEDS-THESIS = material individual name needs an explicit thesis row; MERGE-INTO-SLEEVE = fund/wrapper or obvious sleeve exposure should be grouped rather than left orphaned; WATCH = keep visible but not thesis-critical; DUST = sub-$2K non-core cleanup candidate.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify untracked account positions.")
    parser.add_argument("--positions", type=Path, default=DEFAULT_POSITIONS)
    parser.add_argument("--bible", type=Path, default=DEFAULT_BIBLE)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    parser.add_argument("--format", choices=("write", "json", "markdown"), default="write")
    args = parser.parse_args(argv)

    payload = classify_orphans(_load_json(args.positions), _load_json(args.bible))
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.format == "markdown":
        print(render_markdown(payload), end="")
        return 0

    args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.md_out.write_text(render_markdown(payload), encoding="utf-8")
    print(f"wrote {args.json_out} and {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
