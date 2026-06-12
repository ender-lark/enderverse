"""Execution planner â€” every directive carries its per-account legs.

Reads the SnapTrade position cache (``account_positions.json``) and the
account rules (``account_rules.json``) to turn "BUY GOOGL â‰ˆ $151k" into
account-level legs the operator can actually place â€” with the constraints
that matter surfaced, never silently absorbed:

* **PCRA hard rule** (operator doctrine, 2026-06-10): the Parents Schwab PCRA
  Trust is ETF-ONLY. Individual-stock buy legs never route there. PCRA sale
  proceeds can only fund ETF buys or sit in cash; moving them anywhere else is
  an operator transfer, and any plan depending on one carries an explicit
  ``transfer_dependency`` flag.
* Tax flags per leg: taxable vs traditional/roth/HSA (v1 informs, never
  optimizes â€” taxes are flagged, not modeled).
* Cash honesty: this cache carries **no cash rows**, so plans state
  ``cash: not_checked`` rather than inventing buying power.

Sell legs drain largest holders first (fewer tickets); buy legs prefer the
account already holding the name (add-to-position), then capacity.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parent
ACCOUNT_POSITIONS_PATH = SRC / "account_positions.json"
ACCOUNT_RULES_PATH = SRC / "account_rules.json"

ETF_LIKE_TYPES = {"ETF", "Open Ended Fund"}
ACCOUNT_ID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
TAX_STATUS_TO_TYPE = {
    "taxable": "taxable",
    "roth": "roth",
    "traditional": "traditional_ira",
    "traditional_ira": "traditional_ira",
    "retirement_plan": "retirement_plan",
    "hsa": "hsa",
}
DEFAULT_TAX_STATUS_LABELS = {
    "taxable": "TAXABLE - gains realize",
    "roth": "tax-advantaged Roth",
    "traditional": "tax-advantaged traditional",
    "traditional_ira": "tax-advantaged traditional",
    "retirement_plan": "tax-advantaged retirement plan",
    "hsa": "tax-advantaged HSA",
}

class AccountsMissingError(Exception):
    pass

def load_rules(path: Path | str = ACCOUNT_RULES_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise AccountsMissingError(f"{path.name} absent â€” account rules NOT loaded.")
    return json.loads(path.read_text(encoding="utf-8"))

def _norm(value: Any) -> str:
    return str(value or "").casefold()

def _extract_account_id(source_file: Any) -> str | None:
    match = ACCOUNT_ID_RE.search(str(source_file or ""))
    return match.group(0).lower() if match else None

def _account_rule(
    name: str,
    broker: str,
    rules: dict[str, Any],
    *,
    account_id: str | None = None,
) -> dict[str, Any] | None:
    """Prefer exact SnapTrade account ids, then use broker/name fallback."""
    account_rules = [r for r in rules.get("accounts", []) if isinstance(r, dict)]
    if account_id:
        wanted = _norm(account_id)
        for rule in account_rules:
            if _norm(rule.get("account_id")) == wanted:
                return rule
    broker_text = _norm(broker)
    account_text = _norm(name)
    for rule in account_rules:
        rule_broker = _norm(rule.get("broker"))
        if rule_broker and rule_broker != broker_text:
            continue
        needle = _norm(rule.get("name_contains"))
        if needle and needle in account_text:
            return rule
    return None

def _tax_from_status(status: Any, rules: dict[str, Any]) -> tuple[str, str, str] | None:
    tax_status = _norm(status)
    if not tax_status:
        return None
    tax_type = TAX_STATUS_TO_TYPE.get(tax_status, tax_status)
    labels = dict(DEFAULT_TAX_STATUS_LABELS)
    labels.update({str(k).casefold(): str(v) for k, v in rules.get("tax_status_labels", {}).items()})
    return tax_type, labels.get(tax_status, DEFAULT_TAX_STATUS_LABELS.get(tax_type, tax_type)), tax_status

def classify_account(
    name: str,
    owner: str,
    broker: str,
    rules: dict[str, Any],
    *,
    account_id: str | None = None,
) -> dict[str, Any]:
    text = f"{name}"
    rule = _account_rule(name, broker, rules, account_id=account_id)
    flags = {str(f).casefold() for f in (rule or {}).get("flags", [])}
    etf_only = "etf_only" in flags or any(s in text for s in rules.get("etf_only_account_substrings", []))
    crypto_only = "crypto_account" in flags or any(s in text for s in rules.get("crypto_only_substrings", []))
    tax_advantaged = any(s in text for s in rules.get("tax_advantaged_substrings", []))
    roth = any(s in text for s in rules.get("roth_substrings", []))
    explicit_tax = _tax_from_status((rule or {}).get("tax_status"), rules)
    if explicit_tax:
        tax_type, tax_flag, tax_status = explicit_tax
    elif tax_advantaged:
        tax_type = "roth" if roth else ("hsa" if "Health Savings" in text else "traditional_ira")
        tax_status = "roth" if roth else ("hsa" if "Health Savings" in text else "traditional")
        tax_flag = "tax-advantaged (no cap-gains)"
    else:
        tax_type = "taxable"
        tax_status = "taxable"
        tax_flag = "TAXABLE â€” gains realize"
    return {
        "owner": owner,
        "broker": broker,
        "account": name,
        "account_id": account_id or (rule or {}).get("account_id"),
        "owner_group_rule": (rule or {}).get("owner_group"),
        "etf_only": etf_only,
        "crypto_only": crypto_only,
        "tax_status": tax_status,
        "tax_type": tax_type,
        "tax_flag": tax_flag,
    }

def load_accounts(
    positions_path: Path | str = ACCOUNT_POSITIONS_PATH,
    rules_path: Path | str = ACCOUNT_RULES_PATH,
) -> list[dict[str, Any]]:
    """Aggregate the flat SnapTrade rows into account objects with holdings."""
    positions_path = Path(positions_path)
    if not positions_path.exists():
        raise AccountsMissingError(
            f"{positions_path.name} absent â€” execution planning NOT possible (honest absence)."
        )
    rows = json.loads(positions_path.read_text(encoding="utf-8")).get("account_positions") or []
    rules = load_rules(rules_path)
    accounts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("owner")), str(row.get("broker")), str(row.get("account")))
        acct = accounts.get(key)
        if acct is None:
            acct = classify_account(
                key[2],
                key[0],
                key[1],
                rules,
                account_id=_extract_account_id(row.get("source_file")),
            )
            acct.update(total_value=0.0, holdings={}, option_value=0.0)
            accounts[key] = acct
        value = float(row.get("market_value") or 0.0)
        acct["total_value"] += value
        ticker = str(row.get("ticker") or "").upper()
        if row.get("option"):
            acct["option_value"] += value
        elif ticker:
            acct["holdings"][ticker] = acct["holdings"].get(ticker, 0.0) + value
    out = sorted(accounts.values(), key=lambda a: -a["total_value"])
    for a in out:
        a["total_value"] = round(a["total_value"], 2)
    return out

def _short(name: str) -> str:
    return name[:34] + ("â€¦" if len(name) > 34 else "")

def plan_buy(
    ticker: str,
    dollars: float,
    *,
    accounts: list[dict[str, Any]],
    is_etf: bool,
    prefer_owner: str | None = None,
) -> dict[str, Any]:
    tick = ticker.upper()
    legs: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for acct in accounts:
        if acct["crypto_only"]:
            excluded.append({"account": _short(acct["account"]), "why_not": "crypto-only account"})
            continue
        if acct["etf_only"] and not is_etf:
            excluded.append(
                {
                    "account": _short(acct["account"]),
                    "why_not": "PCRA is ETF-ONLY â€” individual stocks cannot trade here (hard rule)",
                }
            )
            continue
        legs.append(
            {
                "owner": acct["owner"],
                "broker": acct["broker"],
                "account": _short(acct["account"]),
                "held_value": round(acct["holdings"].get(tick, 0.0), 2),
                "account_value": acct["total_value"],
                "tax_flag": acct["tax_flag"],
                "eligible": True,
            }
        )
    if prefer_owner:
        legs.sort(key=lambda l: (l["owner"] != prefer_owner, -l["held_value"], -l["account_value"]))
    else:
        legs.sort(key=lambda l: (-l["held_value"], -l["account_value"]))
    suggested = legs[0] if legs else None
    if suggested:
        suggested = dict(suggested)
        suggested["suggested_usd"] = round(dollars, 2)
        suggested["why"] = (
            f"largest existing {tick} position (add-to-position)"
            if suggested["held_value"] > 0
            else "largest eligible account (no existing position anywhere)"
        )
    return {
        "direction": "BUY",
        "ticker": tick,
        "dollars": round(dollars, 2),
        "suggested": suggested,
        "eligible": legs,
        "excluded": excluded,
        "cash": "not_checked â€” cash balances are not in the positions cache; confirm buying power before placing",
    }

def plan_sell(
    ticker: str,
    dollars: float,
    *,
    accounts: list[dict[str, Any]],
    funded_buys_are_etf: bool | None = None,
) -> dict[str, Any]:
    tick = ticker.upper()
    holders = [a for a in accounts if a["holdings"].get(tick, 0.0) > 0]
    holders.sort(key=lambda a: -a["holdings"][tick])
    remaining = dollars
    legs: list[dict[str, Any]] = []
    pcra_proceeds = 0.0
    for acct in holders:
        if remaining <= 0:
            break
        held = acct["holdings"][tick]
        take = round(min(held, remaining), 2)
        remaining -= take
        leg = {
            "owner": acct["owner"],
            "broker": acct["broker"],
            "account": _short(acct["account"]),
            "held_value": round(held, 2),
            "sell_usd": take,
            "tax_flag": acct["tax_flag"],
        }
        if acct["etf_only"]:
            pcra_proceeds += take
            leg["proceeds_constraint"] = (
                "PCRA proceeds stay in PCRA: ETF-rebuy or cash only; "
                "moving them out is an operator transfer"
            )
        legs.append(leg)
    unfilled = round(max(0.0, remaining), 2)
    transfer_dependency = pcra_proceeds > 0 and funded_buys_are_etf is False
    out = {
        "direction": "SELL",
        "ticker": tick,
        "dollars": round(dollars, 2),
        "legs": legs,
        "unfilled_usd": unfilled,
        "pcra_proceeds_usd": round(pcra_proceeds, 2),
        "transfer_dependency": transfer_dependency,
    }
    if transfer_dependency:
        out["transfer_note"] = (
            f"${pcra_proceeds:,.0f} of these proceeds land inside PCRA and CANNOT buy "
            "individual stocks â€” the funded buys need either an operator transfer out of "
            "PCRA (flag: operator action) or different funding."
        )
    if unfilled:
        out["unfilled_note"] = f"only ${dollars - unfilled:,.0f} of ${dollars:,.0f} is held across accounts"
    return out

def funding_reality_check(
    trims: list[dict[str, Any]],
    adds: list[dict[str, Any]],
    *,
    accounts: list[dict[str, Any]],
    etf_tickers: set[str],
) -> dict[str, Any]:
    """The PCRA-proceeds catch, computed: how much of the funding pool is
    trapped in the ETF-only account while the adds are individual stocks."""
    add_is_etf = {str(a.get("ticker", "")).upper() in etf_tickers for a in adds}
    any_stock_adds = False in add_is_etf if add_is_etf else False
    trapped = 0.0
    detail = []
    for trim in trims:
        plan = plan_sell(
            str(trim.get("ticker")),
            float(trim.get("notional_usd") or 0.0),
            accounts=accounts,
            funded_buys_are_etf=not any_stock_adds,
        )
        trapped += plan["pcra_proceeds_usd"]
        detail.append({"ticker": plan["ticker"], "pcra_proceeds_usd": plan["pcra_proceeds_usd"]})
    return {
        "pcra_trapped_usd": round(trapped, 2),
        "stock_adds_present": any_stock_adds,
        "transfer_required_for_full_plan": any_stock_adds and trapped > 0,
        "by_trim": detail,
        "note": (
            "PCRA proceeds can fund ETF buys in-place; funding individual-stock adds "
            "with them requires an operator transfer (explicit operator action)."
        ),
    }
