#!/usr/bin/env python3
"""Account-placement guidance for candidate trade recommendations.

This module never executes trades. It adds a simple, explicit account suggestion
to review prompts so the operator can decide faster while still checking cash,
tax, permissions, wash-sale, and same-session trade gates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


PARENT_SCHWAB_RULE = "Parents Schwab/PCRA Trust ETF-only"
CRYPTO_TICKERS = {"AAVE", "BTC", "ETH", "HYPE", "SOL", "TRUMP"}
KNOWN_ETFS = {
    "ARKK", "BITO", "DIA", "DRIV", "ETHA", "FBGKX", "FDRXX", "FTXL",
    "GDX", "GLD", "GRNJ", "GRNY", "IBIT", "IGV", "ITA", "IVES", "IWM",
    "LIT", "MAGS", "QQQ", "RPG", "RYF", "SIL", "SLV", "SMH", "SPY", "VOLT",
    "XLE", "XLF", "XLK", "XLP", "XLU", "XLV", "XOP",
}


def _rows(account_positions: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(account_positions, dict):
        raw = account_positions.get("account_positions") or []
    else:
        raw = account_positions or []
    return [row for row in raw if isinstance(row, dict)]


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_parent_schwab(row: dict[str, Any]) -> bool:
    owner = str(row.get("owner") or "").strip().lower()
    broker = str(row.get("broker") or "").strip().lower()
    account = str(row.get("account") or "").strip().lower()
    return owner == "parents" and broker == "schwab" and ("pcra" in account or "trust" in account)


def _instrument_class(ticker: str, held_rows: list[dict[str, Any]], all_rows: list[dict[str, Any]]) -> str:
    asset_types = [
        str(row.get("asset_type") or "").strip().lower()
        for row in held_rows
        if str(row.get("asset_type") or "").strip()
    ]
    if any("crypto" in value for value in asset_types) or ticker in CRYPTO_TICKERS:
        return "crypto"
    if held_rows and all(row.get("option") or "option" in str(row.get("asset_type") or "").lower() for row in held_rows):
        return "option"
    if any("etf" in value or "exchange traded" in value for value in asset_types):
        return "ETF"
    if ticker in KNOWN_ETFS:
        return "ETF"
    held_etf_tickers = {
        _ticker(row.get("ticker"))
        for row in all_rows
        if "etf" in str(row.get("asset_type") or "").lower()
    }
    if ticker in held_etf_tickers:
        return "ETF"
    if any("stock" in value or "depositary" in value for value in asset_types):
        return "stock"
    return "unknown"


def _side_from_item(item: dict[str, Any]) -> str:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("action", "capital_effect", "action_label", "your_move", "what", "kind")
    ).lower()
    if any(word in text for word in ("trim", "sell", "reduce", "funding candidate")):
        return "trim/sell"
    if any(word in text for word in ("hedge", "protect")):
        return "hedge/review"
    if any(word in text for word in ("add", "buy", "start", "size", "rotate", "act")):
        return "buy/add"
    return "review"


def _account_value(row: dict[str, Any]) -> float:
    try:
        return float(row.get("market_value") or 0)
    except (TypeError, ValueError):
        return 0.0


def _account_identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "owner": row.get("owner") or "",
        "broker": row.get("broker") or "",
        "account": row.get("account") or "",
    }


def _account_key(row: dict[str, Any]) -> tuple[str, str, str]:
    ident = _account_identity(row)
    return (
        str(ident["owner"]),
        str(ident["broker"]),
        str(ident["account"]),
    )


def _aggregate_accounts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accounts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = _account_key(row)
        cur = accounts.setdefault(key, {
            **_account_identity(row),
            "market_value": 0.0,
            "parent_schwab_etf_only": _is_parent_schwab(row),
        })
        cur["market_value"] += _account_value(row)
    return sorted(accounts.values(), key=lambda row: float(row.get("market_value") or 0), reverse=True)


def _format_account(row: dict[str, Any]) -> str:
    owner = str(row.get("owner") or "").strip()
    broker = str(row.get("broker") or "").strip()
    account = str(row.get("account") or "").strip()
    prefix = " ".join(part for part in (owner, broker) if part)
    return f"{prefix}: {account}" if prefix and account else account or prefix or "Unspecified account"


def _alternatives(rows: list[dict[str, Any]], chosen: dict[str, Any] | None, *, max_items: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    chosen_key = _account_key(chosen) if chosen else None
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = _account_key(row)
        if key == chosen_key or key in seen:
            continue
        seen.add(key)
        out.append({
            **_account_identity(row),
            "label": _format_account(row),
            "market_value": round(_account_value(row), 2),
        })
        if len(out) >= max_items:
            break
    return out


def recommend_account_placement(
    item: dict[str, Any],
    account_positions: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return account-placement guidance for one action/reallocation item."""
    ticker = _ticker(item.get("ticker"))
    all_rows = _rows(account_positions)
    if not ticker:
        return {
            "status": "not_applicable",
            "summary": "No account selected: portfolio/event item has no ticker.",
            "caveats": ["Review portfolio-level exposure before choosing an account."],
        }
    if not all_rows:
        return {
            "status": "not_checked",
            "ticker": ticker,
            "summary": "No account selected: account positions are not checked.",
            "caveats": ["Refresh SnapTrade/account positions before choosing trade location."],
        }

    held = [row for row in all_rows if _ticker(row.get("ticker")) == ticker]
    instrument = _instrument_class(ticker, held, all_rows)
    side = _side_from_item(item)
    accounts = _aggregate_accounts(all_rows)
    parent_schwab_accounts = [row for row in accounts if bool(row.get("parent_schwab_etf_only"))]
    non_parent_schwab_accounts = [row for row in accounts if not bool(row.get("parent_schwab_etf_only"))]
    held_accounts = _aggregate_accounts(held)
    held_non_parent_schwab = [row for row in held_accounts if not bool(row.get("parent_schwab_etf_only"))]
    chosen: dict[str, Any] | None = None
    reason = ""

    if side == "trim/sell":
        chosen = held_accounts[0] if held_accounts else None
        reason = (
            "Trim/sell where the position is already held; largest current account position is simplest."
            if chosen else
            "No current holding found for this ticker in the checked account book."
        )
    elif instrument == "crypto":
        crypto_accounts = [
            row for row in accounts
            if str(row.get("broker") or "").lower() == "robinhood"
            and "crypto" in str(row.get("account") or "").lower()
        ]
        chosen = crypto_accounts[0] if crypto_accounts else (held_accounts[0] if held_accounts else None)
        reason = "Crypto candidates belong in the Robinhood Crypto account when used at all."
    elif instrument == "option":
        chosen = held_non_parent_schwab[0] if held_non_parent_schwab else None
        reason = "Options require explicit account permission/liquidity review; use an existing non-PCRA holding account only after approval."
    elif instrument == "ETF" and side in {"buy/add", "hedge/review", "review"}:
        chosen = parent_schwab_accounts[0] if parent_schwab_accounts else (held_accounts[0] if held_accounts else None)
        reason = "ETF candidate: prioritize Parents Schwab/PCRA Trust so stock-capable accounts stay free for individual names."
    elif side == "buy/add":
        chosen = held_non_parent_schwab[0] if held_non_parent_schwab else None
        if not chosen:
            preferred = [
                row for row in non_parent_schwab_accounts
                if str(row.get("owner") or "").lower() == "skb" and str(row.get("broker") or "").lower() == "schwab"
            ]
            chosen = preferred[0] if preferred else (non_parent_schwab_accounts[0] if non_parent_schwab_accounts else None)
        reason = (
            "Individual-stock candidate: avoid Parents Schwab/PCRA Trust; add where already held if possible, otherwise use a stock-capable account."
        )
    else:
        chosen = held_non_parent_schwab[0] if held_non_parent_schwab else (held_accounts[0] if held_accounts else None)
        reason = "Review account placement against existing holdings; no capital move is implied yet."

    if not chosen:
        if side == "trim/sell" and not held_accounts:
            return {
                "status": "not_held",
                "ticker": ticker,
                "side": side,
                "instrument_class": instrument,
                "summary": "No current position in the checked account book.",
                "why": "No sell/trim action is needed from checked accounts; treat this as avoid-new-exposure context unless an off-book position exists.",
                "rule": PARENT_SCHWAB_RULE,
                "caveats": [
                    "If trades happened after the book timestamp, refresh account positions before acting.",
                    "No order is placed or sized from this recommendation.",
                ],
            }
        return {
            "status": "needs_review",
            "ticker": ticker,
            "side": side,
            "instrument_class": instrument,
            "summary": "No account selected: no eligible account could be inferred from current holdings.",
            "why": reason,
            "rule": PARENT_SCHWAB_RULE,
            "caveats": [
                "Check cash, taxes, wash-sale rules, account permissions, and live trade gate before acting.",
            ],
        }

    label = _format_account(chosen)
    if instrument != "ETF" and bool(chosen.get("parent_schwab_etf_only")) and side != "trim/sell":
        return {
            "status": "blocked",
            "ticker": ticker,
            "side": side,
            "instrument_class": instrument,
            "summary": f"Do not use {label}: Parents Schwab/PCRA Trust is ETF-only.",
            "why": reason,
            "rule": PARENT_SCHWAB_RULE,
            "caveats": [
                "Choose a non-PCRA account and re-run account-placement review.",
            ],
        }

    return {
        "status": "candidate",
        "ticker": ticker,
        "side": side,
        "instrument_class": instrument,
        "owner": chosen.get("owner") or "",
        "broker": chosen.get("broker") or "",
        "account": chosen.get("account") or "",
        "label": label,
        "summary": f"Suggested account: {label}.",
        "why": reason,
        "rule": PARENT_SCHWAB_RULE,
        "alternatives": _alternatives(held_accounts or accounts, chosen),
        "caveats": [
            "Guidance only; check available cash, taxes, wash-sale rules, account permissions, and live trade gate before acting.",
            "No order is placed or sized from this recommendation.",
        ],
    }


def annotate_actions(
    actions: list[dict[str, Any]] | None,
    account_positions: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for action in actions or []:
        row = dict(action)
        placement = recommend_account_placement(row, account_positions)
        if placement.get("status") != "not_applicable":
            row["account_placement"] = placement
            if placement.get("status") == "not_held" and placement.get("side") == "trim/sell":
                ticker = str(placement.get("ticker") or row.get("ticker") or "").strip().upper()
                prefix = f"{ticker}: " if ticker else ""
                row["what"] = "Avoid-new-exposure watch"
                row["your_move"] = (
                    f"{prefix}checked account book shows no current position. "
                    "No sell/trim task from checked accounts; keep this as avoid-new-exposure context unless an off-book position exists."
                )
                row["action_state"] = "WATCH"
                row["action_label"] = "NO POSITION"
                row["capital_effect"] = "no_capital_yet"
        out.append(row)
    return out


def annotate_reallocation_brief(
    block: dict[str, Any],
    account_positions: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if not isinstance(block, dict):
        return block
    result = deepcopy(block)
    for key in ("rows", "trims", "special_reviews"):
        rows = result.get(key)
        if not isinstance(rows, list):
            continue
        annotated = []
        for row in rows:
            if isinstance(row, dict):
                updated = dict(row)
                placement = recommend_account_placement(updated, account_positions)
                if placement.get("status") != "not_applicable":
                    updated["account_placement"] = placement
                annotated.append(updated)
            else:
                annotated.append(row)
        result[key] = annotated
    result["account_placement_rule"] = {
        "summary": "Account-placement guidance uses current account-position rows and does not execute trades.",
        "parent_schwab": PARENT_SCHWAB_RULE,
        "caveat": "Cash, taxes, wash-sale rules, account permissions, and final sizing remain operator checks.",
    }
    return result
