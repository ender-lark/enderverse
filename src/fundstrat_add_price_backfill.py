#!/usr/bin/env python3
"""Backfill Fundstrat monthly add prices from approved OHLC rows."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from codex_uw.endpoints import UWEndpoints
from codex_uw.rest_client import UWRestClient, unwrap_uw_rows


MONTHLY_LIST_KEYS = ("top5", "bottom5", "top5_smid", "bottom5_smid")


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_add_price.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


def _ticker(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("ticker") or item.get("symbol") or "").strip().upper()
    return str(item or "").strip().upper()


def monthly_tickers(deck: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key in MONTHLY_LIST_KEYS:
        for item in deck.get(key) or []:
            ticker = _ticker(item)
            if ticker and ticker not in seen:
                seen.add(ticker)
                out.append(ticker)
    return out


def _close(row: dict[str, Any]) -> float | None:
    value = row.get("close")
    if value is None:
        value = row.get("c")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def select_add_price_row(
    ohlc_payload: Any,
    *,
    report_date: str,
    preferred_market_time: str = "pr",
) -> dict[str, Any] | None:
    """Select one OHLC row for a Fundstrat report-date add price.

    The May 28 source email was timestamped before the regular session, so the
    default prefers UW's premarket row on the report date. If that row is not
    available, use regular-session close on the report date, then any row on
    the report date with a usable close. This deliberately does not guess across
    dates unless the caller supplies a response that only has prior rows.
    """
    rows = [row for row in unwrap_uw_rows(ohlc_payload) if isinstance(row, dict)]
    dated = [row for row in rows if str(row.get("date") or "") == report_date and _close(row) is not None]
    if not dated:
        return None
    for market_time in (preferred_market_time, "r"):
        for row in dated:
            if str(row.get("market_time") or "").lower() == market_time:
                return row
    return dated[0]


def apply_add_price_backfill(
    prospects: dict[str, Any],
    responses_by_ticker: dict[str, Any],
    *,
    report_date: str,
    preferred_market_time: str = "pr",
    source_note: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    updated: list[str] = []
    missing: list[str] = []
    for ticker, payload in responses_by_ticker.items():
        tk = str(ticker or "").strip().upper()
        rec = prospects.get(tk)
        if not isinstance(rec, dict):
            missing.append(tk)
            continue
        if rec.get("add_price") is not None and not overwrite:
            continue
        row = select_add_price_row(
            payload,
            report_date=report_date,
            preferred_market_time=preferred_market_time,
        )
        price = _close(row or {})
        if row is None or price is None:
            missing.append(tk)
            continue
        rec["add_price"] = price
        selected = f"UW OHLC {row.get('market_time') or ''} {row.get('date') or report_date}".strip()
        rec["add_price_source"] = f"{selected}; {source_note}" if source_note else selected
        rec["add_price_date"] = str(row.get("date") or report_date)
        rec["add_price_market_time"] = str(row.get("market_time") or "")
        updated.append(tk)
    return {
        "updated": updated,
        "missing": missing,
        "updated_count": len(updated),
        "missing_count": len(missing),
    }


def fetch_uw_ohlc(tickers: list[str], *, timeframe: str = "1M", limit: int = 100) -> dict[str, Any]:
    client = UWRestClient(timeout=25, retries=1)
    responses: dict[str, Any] = {}
    for ticker in tickers:
        responses[ticker] = client.get_json(
            UWEndpoints.TICKER_OHLC,
            path_params={"ticker": ticker, "candle_size": "1d"},
            params={"timeframe": timeframe, "limit": limit},
        )
    return responses


def main(argv=None) -> int:
    src = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Backfill Fundstrat monthly add prices from UW OHLC rows")
    parser.add_argument("--bible", default=str(src / "fundstrat_bible.json"))
    parser.add_argument("--prospects", default=str(src / "top_prospects.json"))
    parser.add_argument("--responses", help="Optional JSON mapping ticker -> UW OHLC response")
    parser.add_argument("--fetch-uw", action="store_true")
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--preferred-market-time", default="pr")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    deck = _read_json(args.bible, default={}) or {}
    prospects = _read_json(args.prospects, default={}) or {}
    tickers = monthly_tickers(deck)
    if args.responses:
        responses = _read_json(args.responses, default={}) or {}
    elif args.fetch_uw:
        responses = fetch_uw_ohlc(tickers)
    else:
        raise SystemExit("Pass --responses or --fetch-uw")

    summary = apply_add_price_backfill(
        prospects,
        {ticker: responses.get(ticker) for ticker in tickers if responses.get(ticker) is not None},
        report_date=args.report_date,
        preferred_market_time=args.preferred_market_time,
        source_note="Fundstrat report timestamp pre-regular-session",
        overwrite=args.overwrite,
    )
    if not args.dry_run:
        _atomic_write_json(args.prospects, prospects)
    print(json.dumps({**summary, "tickers": tickers, "written": not args.dry_run}, indent=2))
    return 0 if not summary["missing"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
