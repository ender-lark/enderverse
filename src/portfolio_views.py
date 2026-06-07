#!/usr/bin/env python3
"""Build account/owner portfolio views for the cockpit Book tab."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from feed_assembler import NAME_SLEEVE, SLEEVE_CAT
from reallocate_config import ETF_LOOKTHROUGH, default_working_model


def _num(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _owner_key(owner: Any) -> str:
    text = str(owner or "").strip().lower()
    if "parent" in text:
        return "parents"
    if "skb" in text or "suraj" in text:
        return "skb"
    return "unknown"


def _sleeve_for(ticker: str) -> tuple[str, str]:
    sleeve = NAME_SLEEVE.get(ticker, "_other")
    return sleeve, SLEEVE_CAT.get(sleeve, "Other holdings")


def _working_model_targets_by_category() -> dict[str, float]:
    targets: dict[str, float] = defaultdict(float)
    for target in default_working_model().targets:
        _, category = _sleeve_for(target.ticker)
        targets[category] += float(target.target_pct or 0.0)
    return {category: round(pct, 2) for category, pct in targets.items()}


def _fundstrat_category_cues(fundstrat_bible: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(fundstrat_bible, dict):
        return {}
    deck_date = str(fundstrat_bible.get("deck_date") or "").strip()
    what_to_own = {str(v).strip().lower() for v in fundstrat_bible.get("what_to_own") or [] if v}
    top5 = {str(v).strip().upper() for v in fundstrat_bible.get("top5") or [] if v}
    bottom5 = {str(v).strip().upper() for v in fundstrat_bible.get("bottom5") or [] if v}
    theme_to_categories = {
        "mag7": ["AI / Semiconductors", "Software"],
        "ethereum": ["Crypto"],
        "software": ["Software"],
        "industrials": ["Electrification"],
        "financials": ["Financials"],
        "small-caps": ["Quality core"],
        "energy/basic materials": ["Nuclear", "Critical minerals"],
    }
    cues: dict[str, dict[str, Any]] = {}
    for theme, categories in theme_to_categories.items():
        if theme not in what_to_own:
            continue
        for category in categories:
            cues.setdefault(category, {
                "cue": "favored",
                "source_date": deck_date,
                "reason": f"Fundstrat what-to-own theme: {theme}",
                "tickers": [],
            })
    for ticker in sorted(top5 | bottom5):
        _, category = _sleeve_for(ticker)
        top = ticker in top5
        bottom = ticker in bottom5
        existing = cues.get(category)
        if top and bottom:
            cue = "mixed"
        elif top:
            cue = "favored"
        else:
            cue = "avoid"
        if existing:
            if existing.get("cue") != cue and cue != "favored":
                existing["cue"] = "mixed"
            existing.setdefault("tickers", []).append(ticker)
            existing["reason"] = "Fundstrat what-to-own/top-bottom cue"
        else:
            cues[category] = {
                "cue": cue,
                "source_date": deck_date,
                "reason": "Fundstrat top/bottom cue",
                "tickers": [ticker],
            }
    for row in cues.values():
        row["tickers"] = sorted(set(row.get("tickers") or []))
    return cues


def _account_rows(account_cache: dict[str, Any]) -> list[dict[str, Any]]:
    rows = account_cache.get("account_positions") if isinstance(account_cache, dict) else []
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        market_value = _num(row.get("market_value"))
        if not ticker or market_value is None or market_value <= 0:
            continue
        sleeve, category = _sleeve_for(ticker)
        out.append({
            "ticker": ticker,
            "description": str(row.get("description") or "").strip(),
            "shares": _num(row.get("shares")) or 0.0,
            "market_value": round(market_value, 2),
            "account": str(row.get("account") or "Unknown").strip(),
            "owner": str(row.get("owner") or "Unknown").strip(),
            "owner_key": _owner_key(row.get("owner")),
            "broker": str(row.get("broker") or "Unknown").strip(),
            "tracked": row.get("tracked"),
            "asset_type": row.get("asset_type"),
            "option": row.get("option") if isinstance(row.get("option"), dict) else None,
            "sleeve": sleeve,
            "category": category,
        })
    out.sort(key=lambda r: (-r["market_value"], r["ticker"], r["account"]))
    return out


def _combined_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    accounts: dict[tuple[str, str], set[str]] = defaultdict(set)
    owners: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        ticker = row["ticker"]
        is_option = row.get("asset_type") == "option" or bool(row.get("option"))
        description = row.get("description") or ""
        key = (ticker, description) if is_option and description else (ticker, "")
        rec = by_key.setdefault(key, {
            "ticker": ticker,
            "description": description,
            "shares": 0.0,
            "market_value": 0.0,
            "tracked": row.get("tracked"),
            "asset_type": row.get("asset_type"),
            "option": row.get("option") if isinstance(row.get("option"), dict) else None,
            "sleeve": row.get("sleeve"),
            "category": row.get("category"),
        })
        rec["shares"] += float(row.get("shares") or 0.0)
        rec["market_value"] += float(row.get("market_value") or 0.0)
        accounts[key].add(row.get("account") or "Unknown")
        owners[key].add(row.get("owner") or "Unknown")
        if row.get("tracked") is not None:
            rec["tracked"] = bool(row.get("tracked"))
    out = []
    for key, rec in by_key.items():
        acct = sorted(accounts[key])
        own = sorted(owners[key])
        out.append({
            **rec,
            "shares": round(rec["shares"], 4),
            "market_value": round(rec["market_value"], 2),
            "account": acct[0] if len(acct) == 1 else "Multiple",
            "owner": own[0] if len(own) == 1 else "Multiple",
        })
    out.sort(key=lambda r: (-r["market_value"], r["ticker"]))
    return out


def _category_summary(
    rows: list[dict[str, Any]],
    total_value: float,
    *,
    target_by_category: dict[str, float] | None = None,
    fundstrat_cues: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    by_category: dict[str, dict[str, Any]] = {}
    tickers: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        category = row.get("category") or "Other holdings"
        rec = by_category.setdefault(category, {
            "category": category,
            "sleeve": row.get("sleeve") or "_other",
            "market_value": 0.0,
            "pct": 0.0,
            "tickers": [],
        })
        rec["market_value"] += float(row.get("market_value") or 0.0)
        tickers[category].add(row.get("ticker"))
    out = []
    for category, rec in by_category.items():
        mv = round(rec["market_value"], 2)
        pct = round((mv / total_value * 100.0), 2) if total_value else 0.0
        target = (target_by_category or {}).get(category)
        cue = (fundstrat_cues or {}).get(category) or {}
        out.append({
            **rec,
            "market_value": mv,
            "pct": pct,
            "tickers": sorted(t for t in tickers[category] if t),
            "working_model_target_pct": target,
            "working_model_gap_pct": round((target or 0.0) - pct, 2) if target is not None else None,
            "fundstrat_cue": cue.get("cue") or "no_current_cue",
            "fundstrat_source_date": cue.get("source_date") or "",
            "fundstrat_reason": cue.get("reason") or "",
            "fundstrat_tickers": cue.get("tickers") or [],
        })
    out.sort(key=lambda r: (-r["market_value"], r["category"]))
    return out


def _effective_exposure(
    rows: list[dict[str, Any]],
    total_value: float,
    *,
    target_by_category: dict[str, float] | None = None,
    fundstrat_cues: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    direct_by_ticker: dict[str, float] = defaultdict(float)
    implied_by_ticker: dict[str, float] = defaultdict(float)
    sources_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        market_value = float(row.get("market_value") or 0.0)
        if not ticker or market_value <= 0:
            continue
        direct_by_ticker[ticker] += market_value
        for underlying, fraction in ETF_LOOKTHROUGH.get(ticker, {}).items():
            implied_value = market_value * float(fraction)
            if implied_value <= 0:
                continue
            implied_by_ticker[underlying] += implied_value
            sources_by_ticker[underlying].append({
                "etf": ticker,
                "fraction": round(float(fraction), 4),
                "market_value": round(implied_value, 2),
            })

    overlap_rows: list[dict[str, Any]] = []
    sleeve_rows: dict[str, dict[str, Any]] = {}
    for ticker in sorted(set(direct_by_ticker) | set(implied_by_ticker)):
        direct = round(direct_by_ticker.get(ticker, 0.0), 2)
        implied = round(implied_by_ticker.get(ticker, 0.0), 2)
        if direct <= 0 and implied <= 0:
            continue
        sleeve, category = _sleeve_for(ticker)
        effective = round(direct + implied, 2)
        if implied > 0:
            overlap_rows.append({
                "ticker": ticker,
                "category": category,
                "sleeve": sleeve,
                "direct_market_value": direct,
                "lookthrough_market_value": implied,
                "effective_market_value": effective,
                "effective_pct": round((effective / total_value * 100.0), 2) if total_value else 0.0,
                "sources": sources_by_ticker.get(ticker, []),
            })
        rec = sleeve_rows.setdefault(category, {
            "category": category,
            "sleeve": sleeve,
            "direct_market_value": 0.0,
            "lookthrough_market_value": 0.0,
            "effective_market_value": 0.0,
            "tickers": set(),
            "etfs": set(),
        })
        rec["direct_market_value"] += direct
        rec["lookthrough_market_value"] += implied
        rec["effective_market_value"] += effective
        rec["tickers"].add(ticker)
        for source in sources_by_ticker.get(ticker, []):
            rec["etfs"].add(source["etf"])

    sleeve_out = []
    for rec in sleeve_rows.values():
        direct = round(float(rec["direct_market_value"]), 2)
        implied = round(float(rec["lookthrough_market_value"]), 2)
        effective = round(float(rec["effective_market_value"]), 2)
        category = rec["category"]
        effective_pct = round((effective / total_value * 100.0), 2) if total_value else 0.0
        target = (target_by_category or {}).get(category)
        cue = (fundstrat_cues or {}).get(category) or {}
        sleeve_out.append({
            "category": category,
            "sleeve": rec["sleeve"],
            "direct_market_value": direct,
            "lookthrough_market_value": implied,
            "effective_market_value": effective,
            "direct_pct": round((direct / total_value * 100.0), 2) if total_value else 0.0,
            "lookthrough_pct": round((implied / total_value * 100.0), 2) if total_value else 0.0,
            "effective_pct": effective_pct,
            "working_model_target_pct": target,
            "working_model_gap_pct": round((target or 0.0) - effective_pct, 2) if target is not None else None,
            "fundstrat_cue": cue.get("cue") or "no_current_cue",
            "fundstrat_source_date": cue.get("source_date") or "",
            "fundstrat_reason": cue.get("reason") or "",
            "fundstrat_tickers": cue.get("tickers") or [],
            "tickers": sorted(t for t in rec["tickers"] if t),
            "etfs": sorted(t for t in rec["etfs"] if t),
        })

    overlap_rows.sort(key=lambda r: (-r["lookthrough_market_value"], r["ticker"]))
    sleeve_out.sort(key=lambda r: (-r["effective_market_value"], r["category"]))
    return {
        "basis": "direct_plus_estimated_etf_lookthrough",
        "caveat": "Effective exposure adds estimated ETF underlying overlap; percentages are not additive to book weight.",
        "source": "reallocate_config.ETF_LOOKTHROUGH",
        "overlap_rows": overlap_rows,
        "sleeves": sleeve_out,
    }


def _view(
    name: str,
    rows: list[dict[str, Any]],
    total_value: float | None = None,
    *,
    target_by_category: dict[str, float] | None = None,
    fundstrat_cues: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    total = float(total_value) if total_value is not None else sum(float(r["market_value"]) for r in rows)
    total = round(total, 2)
    out_rows = []
    for row in rows:
        mv = float(row.get("market_value") or 0.0)
        out_rows.append({
            **row,
            "pct": round((mv / total * 100.0), 2) if total else 0.0,
        })
    return {
        "key": name,
        "total_value": total,
        "rows": out_rows,
        "categories": _category_summary(
            out_rows,
            total,
            target_by_category=target_by_category,
            fundstrat_cues=fundstrat_cues,
        ),
        "effective_exposure": _effective_exposure(
            out_rows,
            total,
            target_by_category=target_by_category,
            fundstrat_cues=fundstrat_cues,
        ),
    }


def build_portfolio_views(
    account_cache: dict[str, Any] | None,
    *,
    fundstrat_bible: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build direct-holding views from account_positions.json shape.

    Direct rows/categories remain direct-only. Each view also carries a separate
    effective_exposure estimate that adds ETF look-through overlap.
    """
    if not isinstance(account_cache, dict):
        return None
    rows = _account_rows(account_cache)
    if not rows:
        return None
    sleeve_value = _num(account_cache.get("sleeve_value"))
    combined = _combined_rows(rows)
    skb_rows = [r for r in rows if r["owner_key"] == "skb"]
    parents_rows = [r for r in rows if r["owner_key"] == "parents"]
    target_by_category = _working_model_targets_by_category()
    fundstrat_cues = _fundstrat_category_cues(fundstrat_bible)
    return {
        "snapshot_date": account_cache.get("snapshot_date"),
        "basis": "direct_holdings_only",
        "caveat": "Rows and category weights are direct holdings only; effective_exposure is a separate ETF look-through estimate.",
        "allocation_guidance": {
            "working_model": "default_working_model",
            "basis": "visual guidance only; not an instruction to trade",
            "fundstrat_source_date": str((fundstrat_bible or {}).get("deck_date") or ""),
        },
        "views": {
            "combined": _view("combined", combined, sleeve_value, target_by_category=target_by_category, fundstrat_cues=fundstrat_cues),
            "skb": _view("skb", skb_rows, target_by_category=target_by_category, fundstrat_cues=fundstrat_cues),
            "parents": _view("parents", parents_rows, target_by_category=target_by_category, fundstrat_cues=fundstrat_cues),
        },
    }


def validate_portfolio_views(payload: dict[str, Any] | None) -> list[str]:
    problems: list[str] = []
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return ["portfolio_views must be a dict"]
    views = payload.get("views")
    if not isinstance(views, dict):
        return ["portfolio_views.views must be a dict"]
    for key in ("combined", "skb", "parents"):
        view = views.get(key)
        if not isinstance(view, dict):
            problems.append(f"portfolio_views.views.{key} must be a dict")
            continue
        if not isinstance(view.get("rows"), list):
            problems.append(f"portfolio_views.views.{key}.rows must be a list")
        if not isinstance(view.get("categories"), list):
            problems.append(f"portfolio_views.views.{key}.categories must be a list")
        total = view.get("total_value")
        if isinstance(total, bool) or not isinstance(total, (int, float)) or total < 0:
            problems.append(f"portfolio_views.views.{key}.total_value must be non-negative number")
        effective = view.get("effective_exposure")
        if effective is not None:
            if not isinstance(effective, dict):
                problems.append(f"portfolio_views.views.{key}.effective_exposure must be a dict")
            else:
                if not isinstance(effective.get("overlap_rows"), list):
                    problems.append(f"portfolio_views.views.{key}.effective_exposure.overlap_rows must be a list")
                if not isinstance(effective.get("sleeves"), list):
                    problems.append(f"portfolio_views.views.{key}.effective_exposure.sleeves must be a list")
    return problems


def _self_test() -> int:
    payload = {
        "snapshot_date": "2026-06-05",
        "sleeve_value": 3000,
        "account_positions": [
            {"ticker": "NVDA", "shares": 10, "market_value": 1000, "account": "A", "owner": "SKB", "broker": "Fidelity", "tracked": True},
            {"ticker": "SMH", "shares": 5, "market_value": 2000, "account": "B", "owner": "Parents", "broker": "Schwab", "tracked": True},
        ],
    }
    views = build_portfolio_views(payload)
    assert views and validate_portfolio_views(views) == []
    assert views["views"]["combined"]["total_value"] == 3000
    assert views["views"]["combined"]["effective_exposure"]["overlap_rows"][0]["ticker"] == "NVDA"
    assert views["views"]["skb"]["rows"][0]["ticker"] == "NVDA"
    assert views["views"]["parents"]["rows"][0]["ticker"] == "SMH"
    print("portfolio_views self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
