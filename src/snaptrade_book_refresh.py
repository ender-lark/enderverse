#!/usr/bin/env python3
"""Safely refresh the promoted book from SnapTrade.

This is the operator/routine entrypoint for the account API path. It stages the
raw SnapTrade pull, validates the combined broker-position shape, builds the
engine-facing and account-facing caches, then promotes only validated outputs.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import broker_pdf_extractor
import build_positions_cache
import position_reconciliation
import snaptrade_positions_import as snaptrade


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = ROOT / "src" / "snaptrade_profiles.local.json"
DEFAULT_RAW_OUT = ROOT / "tmp" / "snaptrade_raw.json"
DEFAULT_COMBINED_OUT = ROOT / "tmp" / "snaptrade_combined.json"
DEFAULT_POSITIONS_OUT = ROOT / "src" / "positions.json"
DEFAULT_ACCOUNT_OUT = ROOT / "src" / "account_positions.json"
DEFAULT_RECONCILE_OUT = ROOT / "src" / "position_reconciliation.json"
DEFAULT_THESES = ROOT / "src" / "theses.json"
STATED_BALANCE_TOLERANCE_PCT = 0.005


class BookRefreshError(RuntimeError):
    """Raised when the staged refresh cannot be safely promoted."""


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


def _date(value: Any) -> str:
    return str(value or "").split("T", 1)[0]


def _num(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _dollars(value: float) -> str:
    return f"${value:,.2f}"


def _account_ticker_values_from_prior(prior_account: dict[str, Any],
                                      account_name: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in (prior_account or {}).get("account_positions", []) or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("account") or "").strip() != account_name:
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        values[ticker] = values.get(ticker, 0.0) + float(row.get("market_value") or 0.0)
    return values


def _account_ticker_values_from_file(file_row: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in file_row.get("positions", []) or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        values[ticker] = values.get(ticker, 0.0) + float(row.get("market_value") or 0.0)
    return values


def _is_cash_like_position(row: dict[str, Any]) -> bool:
    ticker = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
    description = str(row.get("description") or "").strip().upper()
    return (
        bool(row.get("cash_equivalent"))
        or ticker in {"FCASH", "FDRXX", "SPAXX", "USD"}
        or "MONEY MARKET" in description
        or "CASH RESERVES" in description
    )


def _ticker_set_detail(file_row: dict[str, Any],
                       prior_account: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    account_name = str(file_row.get("account_name") or "Unknown").strip()
    prior_values = _account_ticker_values_from_prior(prior_account, account_name)
    current_values = _account_ticker_values_from_file(file_row)
    missing = [
        {"ticker": ticker, "prior_market_value": round(value, 2)}
        for ticker, value in prior_values.items()
        if ticker not in current_values
    ]
    new = [
        {"ticker": ticker, "current_market_value": round(value, 2)}
        for ticker, value in current_values.items()
        if ticker not in prior_values
    ]
    missing.sort(key=lambda r: (-abs(float(r["prior_market_value"])), r["ticker"]))
    new.sort(key=lambda r: (-abs(float(r["current_market_value"])), r["ticker"]))
    return {"missing_tickers": missing, "new_tickers": new}


def _format_ticker_detail(detail: dict[str, list[dict[str, Any]]]) -> str:
    parts: list[str] = []
    missing = detail.get("missing_tickers") or []
    if missing:
        formatted = [
            f"{row['ticker']} missing (prior {_dollars(float(row['prior_market_value']))})"
            for row in missing[:5]
        ]
        parts.append("missing: " + ", ".join(formatted))
    new = detail.get("new_tickers") or []
    if new:
        formatted = [
            f"{row['ticker']} new (current {_dollars(float(row['current_market_value']))})"
            for row in new[:5]
        ]
        parts.append("new: " + ", ".join(formatted))
    return "; ".join(parts)


def stated_balance_findings(combined: dict[str, Any],
                            prior_account: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return per-account broker-stated balance mismatches.

    This catches internally consistent SnapTrade snapshots where a row is
    dropped, doubled, or valued with the wrong option convention.
    """
    findings: list[dict[str, Any]] = []
    prior_account = prior_account or {}
    for file_row in combined.get("files", []) or []:
        if not isinstance(file_row, dict):
            continue
        validation = file_row.setdefault("validation", {})
        if not isinstance(validation, dict):
            continue
        reported_total = _num(file_row.get("reported_total") or validation.get("reported_total"))
        if reported_total is None:
            if str(validation.get("source") or "").lower() == "snaptrade":
                account_name = str(file_row.get("account_name") or "Unknown")
                line = f"{account_name}: stated-balance not checked - broker reported_total missing"
                validation["stated_balance_checked"] = False
                validation["passed"] = False
                validation["error"] = line
                findings.append({
                    "account": account_name,
                    "source_file": file_row.get("source_file"),
                    "line": line,
                    "missing_reported_total": True,
                })
            continue
        position_rows = [row for row in file_row.get("positions", []) or [] if isinstance(row, dict)]
        positions_total = sum(float(row.get("market_value") or 0.0) for row in position_rows)
        cash_like_total = sum(
            float(row.get("market_value") or 0.0)
            for row in position_rows
            if _is_cash_like_position(row)
        )
        cash = float(file_row.get("cash") or 0.0)
        adjusted_total = positions_total - cash_like_total + cash
        candidates = [
            ("non-cash positions + cash", adjusted_total),
            ("positions only", positions_total),
        ]
        basis, computed_total = min(candidates, key=lambda item: abs(item[1] - reported_total))
        delta = computed_total - reported_total
        tolerance = max(1.0, abs(reported_total) * STATED_BALANCE_TOLERANCE_PCT)
        validation.update({
            "stated_balance_checked": True,
            "computed_total": round(computed_total, 2),
            "computed_total_basis": basis,
            "cash_like_positions": round(cash_like_total, 2),
            "reported_total": round(reported_total, 2),
            "reported_total_delta": round(delta, 2),
            "reported_total_tolerance": round(tolerance, 2),
        })
        if abs(delta) <= tolerance:
            continue
        validation["passed"] = False
        account_name = str(file_row.get("account_name") or "Unknown")
        detail = _ticker_set_detail(file_row, prior_account)
        detail_line = _format_ticker_detail(detail)
        line = (
            f"{account_name}: stated-balance mismatch {basis} "
            f"{_dollars(computed_total)} vs broker stated {_dollars(reported_total)} "
            f"(delta {delta:+,.2f}, tolerance {_dollars(tolerance)})"
        )
        if detail_line:
            line += f"; {detail_line}"
        validation["error"] = line
        findings.append({
            "account": account_name,
            "source_file": file_row.get("source_file"),
            "computed_total": round(computed_total, 2),
            "reported_total": round(reported_total, 2),
            "delta": round(delta, 2),
            "tolerance": round(tolerance, 2),
            "computed_total_basis": basis,
            "line": line,
            **detail,
        })
    return findings


def build_staged_book(
    *,
    profiles_path: str | Path = DEFAULT_PROFILES,
    theses_path: str | Path = DEFAULT_THESES,
    raw_out: str | Path = DEFAULT_RAW_OUT,
    combined_out: str | Path = DEFAULT_COMBINED_OUT,
    positions_out: str | Path = DEFAULT_POSITIONS_OUT,
    account_out: str | Path = DEFAULT_ACCOUNT_OUT,
    reconcile_out: str | Path = DEFAULT_RECONCILE_OUT,
    promote: bool = True,
    strict: bool = False,
) -> dict[str, Any]:
    """Pull SnapTrade and promote validated book artifacts."""
    client = snaptrade.SnapTradeClient()
    profiles = snaptrade.read_profiles(profiles_path)
    raw = snaptrade.pull_profiles(client, profiles)
    combined = snaptrade.build_combined_from_snaptrade(raw)
    prior_account = _read_json(account_out, {})
    balance_findings = stated_balance_findings(combined, prior_account)
    if balance_findings:
        warnings = combined.setdefault("warnings", [])
        for finding in balance_findings:
            line = str(finding.get("line") or "")
            if line and line not in warnings:
                warnings.append(line)

    _write_json(raw_out, raw)
    _write_json(combined_out, combined)

    combined_problems = broker_pdf_extractor.validate_combined(combined)
    if combined_problems:
        raise BookRefreshError("combined validation failed: " + "; ".join(combined_problems))
    if strict and balance_findings:
        lines = [str(f.get("line") or f) for f in balance_findings]
        raise BookRefreshError("stated-balance validation failed: " + "; ".join(lines))

    theses_doc = _read_json(theses_path, [])
    theses = theses_doc.get("theses") if isinstance(theses_doc, dict) else theses_doc
    positions = build_positions_cache.build_positions(combined, theses or [])
    position_problems = build_positions_cache.validate_positions(positions)
    if position_problems:
        raise BookRefreshError("positions validation failed: " + "; ".join(position_problems))

    account_positions = position_reconciliation.build_account_positions(combined, theses or [])
    account_problems = position_reconciliation.validate_account_positions(account_positions)
    if account_problems:
        raise BookRefreshError("account-position validation failed: " + "; ".join(account_problems))
    reconciliation = position_reconciliation.reconcile_positions(prior_account, account_positions)

    stage_dir = Path(combined_out).parent
    staged_positions = stage_dir / "snaptrade_positions.staged.json"
    staged_account = stage_dir / "snaptrade_account_positions.staged.json"
    staged_reconcile = stage_dir / "snaptrade_position_reconciliation.staged.json"
    _write_json(staged_positions, positions)
    _write_json(staged_account, account_positions)
    _write_json(staged_reconcile, reconciliation)

    written: dict[str, str] = {
        "raw": str(raw_out),
        "combined": str(combined_out),
        "staged_positions": str(staged_positions),
        "staged_account_positions": str(staged_account),
        "staged_position_reconciliation": str(staged_reconcile),
    }
    if promote:
        written["positions"] = str(_write_json(positions_out, positions))
        written["account_positions"] = str(_write_json(account_out, account_positions))
        written["position_reconciliation"] = str(_write_json(reconcile_out, reconciliation))

    return {
        "valid": True,
        "promoted": promote,
        "profiles": len(raw.get("profiles", []) or []),
        "accounts": sum(len(p.get("accounts", []) or []) for p in raw.get("profiles", []) or []),
        "raw_positions": sum(len(f.get("positions", []) or []) for f in combined.get("files", []) or []),
        "snapshot_date": positions.get("snapshot_date"),
        "prior_snapshot_date": prior_account.get("snapshot_date"),
        "sleeve_value": positions.get("sleeve_value"),
        "thesis_positions": len(positions.get("positions") or []),
        "account_rows": len(account_positions.get("account_positions") or []),
        "position_diff_counts": reconciliation.get("counts") or {},
        "share_change_count": sum(
            int((reconciliation.get("counts") or {}).get(k) or 0)
            for k in ("NEW", "EXIT", "ADD", "TRIM")
        ),
        "warnings": combined.get("warnings", []),
        "stated_balance_findings": balance_findings,
        "written": written,
    }


def _refresh_dashboard() -> int:
    proc = subprocess.run([sys.executable, "src/live_dashboard_refresh.py"], cwd=ROOT)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILES))
    parser.add_argument("--theses", default=str(DEFAULT_THESES))
    parser.add_argument("--raw-out", default=str(DEFAULT_RAW_OUT))
    parser.add_argument("--combined-out", default=str(DEFAULT_COMBINED_OUT))
    parser.add_argument("--positions-out", default=str(DEFAULT_POSITIONS_OUT))
    parser.add_argument("--account-out", default=str(DEFAULT_ACCOUNT_OUT))
    parser.add_argument("--reconcile-out", default=str(DEFAULT_RECONCILE_OUT))
    parser.add_argument("--no-promote", action="store_true", help="stage and validate only; do not replace src book files")
    parser.add_argument("--strict", action="store_true", help="block promotion on stated-balance warnings")
    parser.add_argument("--refresh-dashboard", action="store_true", help="run live_dashboard_refresh.py after successful promotion")
    args = parser.parse_args(argv)

    try:
        report = build_staged_book(
            profiles_path=args.profiles,
            theses_path=args.theses,
            raw_out=args.raw_out,
            combined_out=args.combined_out,
            positions_out=args.positions_out,
            account_out=args.account_out,
            reconcile_out=args.reconcile_out,
            promote=not args.no_promote,
            strict=args.strict,
        )
    except (BookRefreshError, snaptrade.SnapTradeError, OSError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    if args.refresh_dashboard and not args.no_promote:
        report["dashboard_refresh_returncode"] = _refresh_dashboard()
        if report["dashboard_refresh_returncode"] != 0:
            report["valid"] = False
            print(json.dumps(report, indent=2))
            return int(report["dashboard_refresh_returncode"])

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
