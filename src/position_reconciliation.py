#!/usr/bin/env python3
"""Account-level position cache and trade-diff reconciliation.

Input is the same broker-PDF extractor combined JSON used by
build_positions_cache.py. This module preserves account-level detail and can
compare the new extract against a prior account-position cache.

No PDF parsing happens here. The extractor remains the source of raw rows; this
module owns the clean, auditable state shape after extraction.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_MIN_SHARE_DELTA = 0.0001
DEFAULT_MIN_VALUE_DELTA = 1.0


def _date_only(value: Any) -> str | None:
    if not value:
        return None
    return str(value).split("T", 1)[0].strip() or None


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
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


def _round_shares(value: float | None) -> float:
    return round(float(value or 0.0), 4)


def _round_dollars(value: float | None) -> float:
    return round(float(value or 0.0), 2)


def _thesis_universe(theses: list[dict[str, Any]] | dict[str, Any] | None) -> set[str]:
    rows = theses or []
    if isinstance(rows, dict):
        rows = rows.get("theses") or rows.get("positions") or []
    out = set()
    for row in rows:
        if isinstance(row, dict) and row.get("ticker"):
            out.add(str(row["ticker"]).strip().upper())
    return out


def _owner_from(source_file: str, account: str, row: dict[str, Any], file_row: dict[str, Any]) -> str:
    explicit = row.get("owner") or row.get("account_owner") or file_row.get("owner")
    if explicit:
        return str(explicit).strip()
    text = f"{source_file} {account}".lower()
    stem = Path(source_file or "").stem.lower()
    if stem.startswith(("s-", "s_", "suraj")):
        return "SKB"
    if stem.startswith(("p-", "p_", "parent", "parents")):
        return "Parents"
    if "skb" in text or "suraj" in text:
        return "SKB"
    if "parent" in text or "parents" in text or "rambalusu" in text:
        return "Parents"
    return "Unknown"


def _account_from(source_file: str, row: dict[str, Any], file_row: dict[str, Any]) -> str:
    account = (
        row.get("account_name")
        or row.get("account")
        or file_row.get("account_name")
        or file_row.get("account")
    )
    if account:
        return str(account).strip()
    scope = str(file_row.get("positions_scope") or "").strip().lower()
    if scope == "aggregate":
        return "Aggregate"
    stem = Path(source_file or "").stem
    return stem or "Unknown"


def _broker_from(source_file: str, file_row: dict[str, Any]) -> str:
    broker = file_row.get("broker") or file_row.get("custodian")
    if broker:
        return str(broker).strip()
    text = (source_file or "").lower()
    for name in ("fidelity", "schwab", "robinhood", "etrade", "vanguard"):
        if name in text:
            return name.title()
    return "Unknown"


def account_position_rows(combined: dict[str, Any],
                          theses: list[dict[str, Any]] | dict[str, Any] | None = None,
                          *,
                          include_unpriced: bool = False) -> list[dict[str, Any]]:
    """Return normalized account-level position rows from extractor output."""
    universe = _thesis_universe(theses)
    rows: list[dict[str, Any]] = []
    for file_row in combined.get("files", []) or []:
        source_file = str(file_row.get("source_file") or "")
        broker = _broker_from(source_file, file_row)
        for pos in file_row.get("positions", []) or []:
            if not isinstance(pos, dict):
                continue
            ticker = str(pos.get("symbol") or pos.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            market_value = _num(pos.get("market_value") or pos.get("current_value") or pos.get("value"))
            if market_value is None and not include_unpriced:
                continue
            if market_value is not None and market_value <= 0 and not include_unpriced:
                continue
            account = _account_from(source_file, pos, file_row)
            rows.append({
                "ticker": ticker,
                "description": str(pos.get("description") or pos.get("name") or "").strip(),
                "shares": _round_shares(_num(pos.get("quantity") or pos.get("shares"))),
                "market_value": _round_dollars(market_value),
                "account": account,
                "owner": _owner_from(source_file, account, pos, file_row),
                "broker": broker,
                "source_file": source_file,
                "tracked": (ticker in universe) if universe else None,
            })
    rows.sort(key=lambda r: (r["owner"], r["broker"], r["account"], r["ticker"]))
    return rows


def combined_positions(rows: list[dict[str, Any]], *, tracked_only: bool = False) -> list[dict[str, Any]]:
    """Aggregate account-level rows by ticker."""
    by_ticker: dict[str, dict[str, Any]] = {}
    accounts: dict[str, set[str]] = defaultdict(set)
    owners: dict[str, set[str]] = defaultdict(set)
    tracked_map: dict[str, bool | None] = {}
    for row in rows:
        if tracked_only and row.get("tracked") is False:
            continue
        ticker = row["ticker"]
        rec = by_ticker.setdefault(ticker, {
            "ticker": ticker,
            "shares": 0.0,
            "market_value": 0.0,
            "tracked": row.get("tracked"),
        })
        rec["shares"] += float(row.get("shares") or 0.0)
        rec["market_value"] += float(row.get("market_value") or 0.0)
        accounts[ticker].add(row.get("account") or "Unknown")
        owners[ticker].add(row.get("owner") or "Unknown")
        if row.get("tracked") is not None:
            tracked_map[ticker] = bool(row.get("tracked"))

    out = []
    for ticker, rec in by_ticker.items():
        acct = sorted(accounts[ticker])
        own = sorted(owners[ticker])
        out.append({
            "ticker": ticker,
            "shares": _round_shares(rec["shares"]),
            "market_value": round(rec["market_value"]),
            "account": acct[0] if len(acct) == 1 else "Multiple",
            "owners": own,
            "tracked": tracked_map.get(ticker, rec.get("tracked")),
        })
    out.sort(key=lambda r: (-float(r["market_value"] or 0), r["ticker"]))
    return out


def build_account_positions(combined: dict[str, Any],
                            theses: list[dict[str, Any]] | dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the account-level holdings artifact."""
    summary = combined.get("portfolio_summary", {}) or {}
    total_mv = _num(summary.get("total_market_value")) or 0.0
    total_cash = _num(summary.get("total_cash")) or 0.0
    rows = account_position_rows(combined, theses)
    return {
        "snapshot_date": _date_only(summary.get("as_of")),
        "sleeve_value": round(total_mv + total_cash),
        "account_positions": rows,
        "combined_positions": combined_positions(rows),
        "tracked_combined_positions": combined_positions(rows, tracked_only=True),
    }


def _by_key(cache: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = cache.get("account_positions") if isinstance(cache, dict) else []
    out = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        account = str(row.get("account") or "Unknown").strip()
        if ticker:
            out[(account, ticker)] = row
    return out


def classify_change(prev: dict[str, Any] | None,
                    curr: dict[str, Any] | None,
                    *,
                    min_share_delta: float = DEFAULT_MIN_SHARE_DELTA,
                    min_value_delta: float = DEFAULT_MIN_VALUE_DELTA) -> dict[str, Any] | None:
    """Classify one account+ticker change."""
    prev = prev or {}
    curr = curr or {}
    ticker = str((curr or prev).get("ticker") or "").strip().upper()
    account = str((curr or prev).get("account") or "Unknown").strip()
    if not ticker:
        return None
    prev_sh = float(prev.get("shares") or 0.0)
    curr_sh = float(curr.get("shares") or 0.0)
    prev_mv = float(prev.get("market_value") or 0.0)
    curr_mv = float(curr.get("market_value") or 0.0)
    share_delta = curr_sh - prev_sh
    value_delta = curr_mv - prev_mv

    if abs(share_delta) <= min_share_delta and abs(value_delta) <= min_value_delta:
        return None
    if prev_sh <= min_share_delta and curr_sh > min_share_delta:
        action = "NEW"
    elif curr_sh <= min_share_delta and prev_sh > min_share_delta:
        action = "EXIT"
    elif share_delta > min_share_delta:
        action = "ADD"
    elif share_delta < -min_share_delta:
        action = "TRIM"
    else:
        action = "VALUE_CHANGE"

    return {
        "ticker": ticker,
        "account": account,
        "owner": (curr or prev).get("owner") or "Unknown",
        "broker": (curr or prev).get("broker") or "Unknown",
        "action": action,
        "shares_before": _round_shares(prev_sh),
        "shares_after": _round_shares(curr_sh),
        "share_delta": _round_shares(share_delta),
        "market_value_before": _round_dollars(prev_mv),
        "market_value_after": _round_dollars(curr_mv),
        "market_value_delta": _round_dollars(value_delta),
        "tracked": (curr or prev).get("tracked"),
    }


def reconcile_positions(prior_cache: dict[str, Any] | None,
                        current_cache: dict[str, Any],
                        *,
                        min_share_delta: float = DEFAULT_MIN_SHARE_DELTA,
                        min_value_delta: float = DEFAULT_MIN_VALUE_DELTA) -> dict[str, Any]:
    """Diff prior and current account-position caches."""
    prior_by_key = _by_key(prior_cache or {})
    current_by_key = _by_key(current_cache)
    changes = []
    for key in sorted(set(prior_by_key) | set(current_by_key)):
        change = classify_change(
            prior_by_key.get(key),
            current_by_key.get(key),
            min_share_delta=min_share_delta,
            min_value_delta=min_value_delta,
        )
        if change:
            changes.append(change)
    action_order = {"NEW": 0, "EXIT": 1, "ADD": 2, "TRIM": 3, "VALUE_CHANGE": 4}
    changes.sort(key=lambda r: (action_order.get(r["action"], 9), r["ticker"], r["account"]))
    counts: dict[str, int] = {}
    for change in changes:
        counts[change["action"]] = counts.get(change["action"], 0) + 1
    return {
        "prior_snapshot_date": (prior_cache or {}).get("snapshot_date"),
        "current_snapshot_date": current_cache.get("snapshot_date"),
        "changes": changes,
        "counts": counts,
    }


def validate_account_positions(cache: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(cache, dict):
        return ["top-level must be an object"]
    rows = cache.get("account_positions")
    if not isinstance(rows, list):
        return ["account_positions must be a list"]
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"account_positions[{idx}] must be an object")
            continue
        for field in ("ticker", "account", "owner", "broker"):
            if not isinstance(row.get(field), str) or not row.get(field):
                problems.append(f"account_positions[{idx}].{field} must be a non-empty string")
        for field in ("shares", "market_value"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"account_positions[{idx}].{field} must be numeric")
    return problems


def _read_json(path: str | Path | None, default=None):
    if not path:
        return default
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".position_reconciliation.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _self_test() -> int:
    combined = {
        "files": [{
            "source_file": "SKB_fidelity.pdf",
            "broker": "Fidelity",
            "positions": [
                {"symbol": "NVDA", "market_value": 1000, "quantity": 10, "account_name": "Taxable"},
                {"symbol": "GS", "market_value": 500, "quantity": 1, "account_name": "Taxable"},
            ],
        }],
        "portfolio_summary": {"total_market_value": 1500, "total_cash": 100, "as_of": "2026-06-05T12:00:00"},
    }
    current = build_account_positions(combined, [{"ticker": "NVDA"}])
    assert validate_account_positions(current) == []
    assert len(current["account_positions"]) == 2
    assert current["tracked_combined_positions"][0]["ticker"] == "NVDA"
    prior = {
        "snapshot_date": "2026-06-04",
        "account_positions": [
            {"ticker": "NVDA", "shares": 5, "market_value": 500, "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "tracked": True}
        ],
    }
    report = reconcile_positions(prior, current)
    assert report["counts"]["ADD"] == 1
    assert report["counts"]["NEW"] == 1
    print("position_reconciliation self-test: PASS")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build account positions and position diff from broker extractor JSON.")
    parser.add_argument("--combined", help="Current extractor combined JSON")
    parser.add_argument("--theses", help="Optional theses.json for tracked flags")
    parser.add_argument("--prior-account-positions", help="Prior account_positions.json")
    parser.add_argument("--account-out", help="Write account_positions.json")
    parser.add_argument("--reconcile-out", help="Write position_reconciliation.json")
    parser.add_argument("--validate", help="Validate an account_positions.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.validate:
        problems = validate_account_positions(_read_json(args.validate, {}))
        if problems:
            print(json.dumps({"valid": False, "problems": problems}, indent=2))
            return 2
        print(json.dumps({"valid": True}, indent=2))
        return 0
    if not args.combined:
        parser.error("--combined is required unless --self-test or --validate is used")

    combined = _read_json(args.combined, {})
    theses = _read_json(args.theses, []) if args.theses else []
    current = build_account_positions(combined, theses)
    problems = validate_account_positions(current)
    if problems:
        print(json.dumps({"valid": False, "problems": problems}, indent=2))
        return 2
    written: dict[str, str] = {}
    if args.account_out:
        written["account_positions"] = str(_atomic_write_json(args.account_out, current))
    report = None
    if args.prior_account_positions:
        if Path(args.prior_account_positions).is_file():
            prior = _read_json(args.prior_account_positions, {})
            report = reconcile_positions(prior, current)
        else:
            report = {
                "status": "not_checked",
                "reason": "prior account-position cache missing",
                "prior_snapshot_date": None,
                "current_snapshot_date": current.get("snapshot_date"),
                "changes": [],
                "counts": {},
            }
        if args.reconcile_out:
            written["position_reconciliation"] = str(_atomic_write_json(args.reconcile_out, report))
    print(json.dumps({
        "built": True,
        "account_rows": len(current["account_positions"]),
        "combined_positions": len(current["combined_positions"]),
        "tracked_combined_positions": len(current["tracked_combined_positions"]),
        "changes": len((report or {}).get("changes", [])),
        "written": written,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
