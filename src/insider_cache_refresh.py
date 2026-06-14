#!/usr/bin/env python3
"""
Refresh the normalized insider_data.json cache from Unusual Whales.

The output is the convention shape consumed by insider_activity_scan:
    ticker -> [normalized Form 4 transaction rows]

Metadata lives under _meta so session_orchestrator can distinguish a real
zero-row live check from the old empty stub.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import insider_activity_scan as ias
from codex_uw.endpoints import UWEndpoints
from codex_uw.rest_client import UWConfigError, UWRequestError, UWRestClient, unwrap_uw_rows


VALID_STATUSES = {"has_data", "checked_clear", "not_checked", "failed"}


def _atomic_write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _load_json(path: str | Path) -> Any:
    with open(path) as fh:
        return json.load(fh)


def _position_rows(payload: Any) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("positions"), list):
        return payload["positions"]
    if isinstance(payload, list):
        return payload
    return []


def tickers_from_positions(payload: Any) -> list[str]:
    tickers = []
    seen = set()
    for row in _position_rows(payload):
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers


def _csv_tickers(raw: str | None) -> list[str]:
    seen = set()
    out = []
    for part in (raw or "").split(","):
        ticker = part.upper().strip()
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)
    return out


def _meta(status: str, *, tickers: Iterable[str], checked_at: str, reason: str | None = None,
          source_count: int = 0) -> dict:
    payload = {
        "status": status,
        "source": "unusual_whales.insider_transactions",
        "endpoint": "UWEndpoints.INSIDER_TRANSACTIONS",
        "checked_at": checked_at,
        "ticker_count": len(list(tickers)),
        "transaction_count": int(source_count),
    }
    if reason:
        payload["reason"] = reason
    return payload


def _empty_payload(status: str, *, tickers: list[str], checked_at: str,
                   reason: str | None = None) -> dict:
    payload = {ticker: [] for ticker in tickers}
    payload["_meta"] = _meta(status, tickers=tickers, checked_at=checked_at,
                             reason=reason, source_count=0)
    return payload


def fetch_insider_cache(
    tickers: list[str],
    *,
    client: Optional[UWRestClient] = None,
    client_factory: Callable[..., UWRestClient] = UWRestClient,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    checked_at: str | None = None,
    retries: int = 1,
    timeout: float = 30.0,
) -> dict:
    checked_at = checked_at or date.today().isoformat()
    tickers = [t.upper().strip() for t in tickers if t and t.strip()]
    if not tickers:
        return _empty_payload("not_checked", tickers=[], checked_at=checked_at,
                              reason="no tickers supplied")

    try:
        client = client or client_factory(retries=retries, timeout=timeout)
        raw = client.get_json(
            UWEndpoints.INSIDER_TRANSACTIONS,
            params={
                "ticker_symbol": ",".join(tickers),
                "limit": max(1, min(int(limit), 500)),
                "page": 0,
                "group": "true",
                "common_stock_only": "true",
                "start_date": start_date,
                "end_date": end_date,
            },
        )
    except (UWConfigError, UWRequestError) as exc:
        return _empty_payload("not_checked", tickers=tickers, checked_at=checked_at,
                              reason=str(exc))

    rows = unwrap_uw_rows(raw)
    normalized = ias.normalize_uw_insider(rows)
    for ticker in tickers:
        normalized.setdefault(ticker, [])
    n_txns = sum(len(v) for v in normalized.values() if isinstance(v, list))
    status = "has_data" if n_txns else "checked_clear"
    normalized["_meta"] = _meta(status, tickers=tickers, checked_at=checked_at,
                                source_count=n_txns)
    return normalized


def validate_cache(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["cache must be a JSON object"]
    meta = payload.get("_meta")
    if not isinstance(meta, dict):
        problems.append("missing _meta")
    else:
        status = meta.get("status")
        if status not in VALID_STATUSES:
            problems.append(f"invalid _meta.status {status!r}")
        if not meta.get("source"):
            problems.append("missing _meta.source")
        if not meta.get("checked_at"):
            problems.append("missing _meta.checked_at")
    for ticker, rows in payload.items():
        if ticker == "_meta":
            continue
        if not isinstance(rows, list):
            problems.append(f"{ticker}: rows must be a list")
            continue
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                problems.append(f"{ticker}[{idx}]: row must be an object")
                continue
            if not row.get("date"):
                problems.append(f"{ticker}[{idx}]: missing date")
            if not row.get("transaction_code"):
                problems.append(f"{ticker}[{idx}]: missing transaction_code")
    return problems


def refresh_from_paths(
    *,
    positions_path: str | None,
    tickers_csv: str | None,
    out_path: str,
    summary_path: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    days_back: int = 120,
    limit: int = 500,
    retries: int = 1,
    timeout: float = 30.0,
) -> dict:
    tickers = _csv_tickers(tickers_csv)
    if not tickers and positions_path:
        tickers = tickers_from_positions(_load_json(positions_path))
    if start_date is None and days_back:
        start_date = (date.today() - timedelta(days=int(days_back))).isoformat()
    payload = fetch_insider_cache(
        tickers,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        retries=retries,
        timeout=timeout,
    )
    _atomic_write_json(out_path, payload)
    summary = {
        "status": (payload.get("_meta") or {}).get("status"),
        "checked_at": (payload.get("_meta") or {}).get("checked_at"),
        "ticker_count": (payload.get("_meta") or {}).get("ticker_count"),
        "transaction_count": (payload.get("_meta") or {}).get("transaction_count"),
        "reason": (payload.get("_meta") or {}).get("reason"),
        "out": out_path,
    }
    if summary_path:
        _atomic_write_json(summary_path, summary)
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh insider_data.json from UW insider/Form 4 transactions.")
    p.add_argument("--positions", default="src/positions.json",
                   help="Positions JSON used to derive tickers when --tickers is omitted.")
    p.add_argument("--tickers", help="Comma-separated ticker override.")
    p.add_argument("--out", default="src/insider_data.json")
    p.add_argument("--summary", default="src/insider_cache_summary.json")
    p.add_argument("--start-date", help="YYYY-MM-DD transaction start date.")
    p.add_argument("--end-date", help="YYYY-MM-DD transaction end date.")
    p.add_argument("--days-back", type=int, default=120)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--retries", type=int, default=1)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--validate", metavar="CACHE_JSON")
    args = p.parse_args()

    if args.validate:
        problems = validate_cache(_load_json(args.validate))
        if problems:
            for problem in problems:
                print(f"ERROR: {problem}")
            return 1
        print(f"valid insider cache: {args.validate}")
        return 0

    summary = refresh_from_paths(
        positions_path=args.positions,
        tickers_csv=args.tickers,
        out_path=args.out,
        summary_path=args.summary,
        start_date=args.start_date,
        end_date=args.end_date,
        days_back=args.days_back,
        limit=args.limit,
        retries=args.retries,
        timeout=args.timeout,
    )
    line = (
        f"insider cache {summary['status']}: tickers={summary['ticker_count']} "
        f"transactions={summary['transaction_count']} -> {summary['out']}"
    )
    if summary.get("reason"):
        line += f" ({summary['reason']})"
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
