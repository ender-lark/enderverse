#!/usr/bin/env python3
"""Refresh Decision Dossier dynamic reads from existing repo evidence.

This module performs no live fetches. It updates only ticker-matched `price`
and `timing` reads from already-present UW price/opportunity/battery evidence.
Absent evidence leaves the prior read unchanged, so missing data cannot become
a checked-clear dossier read.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import battery_evidence as be
import decision_dossiers as dd
from full_build_runner import normalize_closes_cache
from tunables import load_conviction_weights
from uw_price import uw_price_rotation_reader


SRC = Path(__file__).resolve().parent
DEFAULT_LIVE_SOURCE_CONFIG = SRC / "live_source_config.json"
DEFAULT_UW_PRICES_PATH = SRC / "uw_closes.json"
DEFAULT_UW_OPPORTUNITY_PATH = SRC / "uw_opportunity_signals.json"
DEFAULT_FEED_PATH = SRC / "latest_cockpit_feed.json"


def _today(value: str | date | None = None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _iso_day(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _ticker(value: Any) -> str:
    return str(value or "").upper().strip()


def _live_source_as_of(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    uw = ((payload.get("connectors") or {}).get("unusual_whales") or {})
    return (
        _iso_day(uw.get("market_state_date"))
        or _iso_day(uw.get("market_tide_latest_timestamp"))
        or _iso_day(uw.get("verified_at"))
        or _iso_day(payload.get("verified_at"))
    )


def _price_rows(uw_price_cache: Any, *, as_of: str | None) -> list[dict[str, Any]]:
    if not isinstance(uw_price_cache, dict):
        return []
    closes = normalize_closes_cache(uw_price_cache)
    if not closes:
        return []
    return uw_price_rotation_reader(closes, as_of=as_of)


def _price_row_for_ticker(ticker: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    tick = _ticker(ticker)
    for row in rows:
        if _ticker(row.get("proxy") or row.get("ticker") or row.get("subject")) == tick:
            if row.get("label") != "NO DATA" and row.get("rel_3m") is not None:
                return row
    return None


def _opportunity_signals_for_ticker(ticker: str, payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(payload, dict):
        return [], None
    tick = _ticker(ticker)
    rows = [
        row for row in payload.get("signals") or []
        if isinstance(row, dict) and _ticker(row.get("ticker")) == tick
    ]
    return rows, _iso_day(payload.get("as_of")) or _iso_day(payload.get("generated_at"))


def _group_rotation_for_ticker(ticker: str, feed: Any) -> dict[str, Any] | None:
    if not isinstance(feed, dict):
        return None
    tick = _ticker(ticker)
    holdings = feed.get("holdings")
    if not isinstance(holdings, list):
        return None
    for group in holdings:
        if not isinstance(group, dict):
            continue
        positions = group.get("pos")
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            if _ticker(pos.get("t") or pos.get("ticker")) != tick:
                continue
            rot = group.get("rot") if isinstance(group.get("rot"), dict) else {}
            return {
                "status": "checked",
                "ticker": tick,
                "category": group.get("cat"),
                "rot_w": rot.get("w"),
                "cd": pos.get("cd"),
                "cd_note": pos.get("cdNote"),
            }
    return None


def _battery_for_ticker(
    ticker: str,
    *,
    price_rows: list[dict[str, Any]],
    opportunity_signals: list[dict[str, Any]],
    opportunity_as_of: str | None,
    group_rotation: dict[str, Any] | None,
    weights: dict[str, Any],
) -> dict[str, Any]:
    opportunity_payload = None
    if opportunity_signals:
        opportunity_payload = {
            "status": "checked",
            "ticker": _ticker(ticker),
            "as_of": opportunity_as_of,
            "signals": opportunity_signals,
        }
    return be.build_battery_evidence(
        ticker,
        uw_price=price_rows,
        uw_opportunity=opportunity_payload,
        group_rotation=group_rotation,
        battery_source_config=weights.get("battery_sources"),
    )


def _factor_by_key(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    for row in payload.get("factors") or []:
        if isinstance(row, dict) and row.get("key") == key:
            return row
    return None


def _actual_opportunity_factors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in payload.get("factors") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        if key.startswith("uw_opportunity_") and key not in {
            "uw_opportunity_none",
            "uw_opportunity_not_checked",
        }:
            out.append(row)
    return out


def _read(label: str, text: str, *, as_of: str, source: str) -> dict[str, Any]:
    return {
        "label": label,
        "text": text,
        "as_of": as_of,
        "max_age_days": 1,
        "source": source,
    }


def _price_text(ticker: str, row: dict[str, Any], factor: dict[str, Any] | None) -> str:
    value = str((factor or {}).get("value_str") or "").strip()
    if not value:
        value = (
            f"{row.get('label')}; rel_3m {_fmt_pct(row.get('rel_3m'))}; "
            f"rel_1m {_fmt_pct(row.get('rel_1m'))}"
        )
    return (
        f"{_ticker(ticker)} current price context checked, not a valuation clearance: "
        f"{value}. No buy-price target is inferred; re-check live price, valuation, "
        "and order book before action."
    )


def _timing_text(ticker: str, battery: dict[str, Any], factors: list[dict[str, Any]]) -> str:
    decisive = []
    for row in factors[:3]:
        label = str(row.get("label") or row.get("key") or "").strip()
        value = str(row.get("value_str") or "").strip()
        if label and value:
            decisive.append(f"{label}: {value}")
    suffix = f" Key flow factors: {'; '.join(decisive)}." if decisive else ""
    return (
        f"{_ticker(ticker)} current timing battery checked from ticker-matched UW "
        f"opportunity evidence: {battery.get('verdict_line') or 'battery checked'}.{suffix} "
        "Re-check gates/catalysts before action; this context does not create a trade signal."
    )


def _refresh_status(row: dict[str, Any], today: date) -> str:
    ticker = _ticker(row.get("ticker"))
    try:
        card = dd.card_dossier(ticker, dossiers={ticker: row}, today=today)
    except Exception:
        return str(row.get("status") or "not_checked")
    return str((card or {}).get("status") or row.get("status") or "not_checked")


def refresh_payload(
    payload: dict[str, Any],
    *,
    uw_price_cache: Any = None,
    opportunity_cache: Any = None,
    feed: Any = None,
    live_source_config: Any = None,
    today: str | date | None = None,
    as_of: str | None = None,
    tickers: list[str] | None = None,
    weights: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    day = _today(today)
    day_text = day.isoformat()
    source_as_of = _iso_day(as_of) or _live_source_as_of(live_source_config) or day_text
    out = copy.deepcopy(payload)
    dossiers = out.setdefault("dossiers", {})
    wanted = {_ticker(t) for t in tickers or [] if _ticker(t)}
    price_rows = _price_rows(uw_price_cache, as_of=source_as_of)
    cfg = weights if isinstance(weights, dict) else load_conviction_weights()

    rows: list[dict[str, Any]] = []
    updated_total = 0
    for ticker, row in sorted(dossiers.items()):
        tick = _ticker(ticker)
        if wanted and tick not in wanted:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("status") == "pending_sync":
            rows.append({"ticker": tick, "updated_reads": [], "skipped": "pending_sync"})
            continue

        reads = row.setdefault("reads", {})
        before = copy.deepcopy(reads)
        updated_reads: list[str] = []
        opportunity_rows, opportunity_as_of = _opportunity_signals_for_ticker(tick, opportunity_cache)
        group_rotation = _group_rotation_for_ticker(tick, feed)
        battery = _battery_for_ticker(
            tick,
            price_rows=price_rows,
            opportunity_signals=opportunity_rows,
            opportunity_as_of=opportunity_as_of,
            group_rotation=group_rotation,
            weights=cfg,
        )

        price_row = _price_row_for_ticker(tick, price_rows)
        if price_row is not None:
            reads["price"] = _read(
                "Good buy price?",
                _price_text(tick, price_row, _factor_by_key(battery, "price_rotation")),
                as_of=source_as_of,
                source="decision_dossier_refresh:uw_price_rotation",
            )
            if reads["price"] != before.get("price"):
                updated_reads.append("price")

        timing_factors = _actual_opportunity_factors(battery)
        timing_as_of = opportunity_as_of or source_as_of
        if timing_factors and timing_as_of:
            reads["timing"] = _read(
                "Good timing?",
                _timing_text(tick, battery, timing_factors),
                as_of=timing_as_of,
                source="decision_dossier_refresh:battery_evidence",
            )
            if reads["timing"] != before.get("timing"):
                updated_reads.append("timing")

        row["status"] = _refresh_status(row, day)
        if updated_reads:
            row["synced_at"] = day_text
            updated_total += 1
        rows.append({
            "ticker": tick,
            "updated_reads": updated_reads,
            "price_evidence": bool(price_row),
            "timing_evidence": bool(timing_factors),
        })

    if updated_total:
        source = out.setdefault("source", {})
        if isinstance(source, dict):
            source["dynamic_refresh_status"] = "refreshed_from_cached_evidence"
            source["dynamic_refresh_note"] = (
                "Only ticker-matched checked evidence updates price/timing reads; "
                "missing evidence leaves stale/not_checked reads unchanged."
            )
        out["generated_at"] = day_text
    dd.assert_valid_payload(out)
    summary = {
        "valid": True,
        "generated_at": day_text,
        "as_of": source_as_of,
        "updated_dossiers": updated_total,
        "rows": rows,
    }
    return out, summary


def write_payload(payload: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip().upper() for item in raw.replace(",", " ").split() if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_path", default=str(dd.DEFAULT_DOSSIERS_PATH))
    parser.add_argument("--out", default=str(dd.DEFAULT_DOSSIERS_PATH))
    parser.add_argument("--uw-prices", default=str(DEFAULT_UW_PRICES_PATH))
    parser.add_argument("--uw-opportunity", default=str(DEFAULT_UW_OPPORTUNITY_PATH))
    parser.add_argument("--feed", default=str(DEFAULT_FEED_PATH))
    parser.add_argument("--live-source-config", default=str(DEFAULT_LIVE_SOURCE_CONFIG))
    parser.add_argument("--today")
    parser.add_argument("--as-of")
    parser.add_argument("--tickers", help="Optional comma/space-separated ticker allowlist")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = dd.load_payload(args.input_path)
    refreshed, summary = refresh_payload(
        payload,
        uw_price_cache=_read_json(args.uw_prices, {}),
        opportunity_cache=_read_json(args.uw_opportunity, {}),
        feed=_read_json(args.feed, {}),
        live_source_config=_read_json(args.live_source_config, {}),
        today=args.today,
        as_of=args.as_of,
        tickers=_parse_tickers(args.tickers),
    )
    if not args.dry_run:
        write_payload(refreshed, args.out)
    summary["written"] = not args.dry_run
    summary["out"] = args.out
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
