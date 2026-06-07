#!/usr/bin/env python3
"""Capture bounded Unusual Whales endpoint result proof from the current runbook.

This is a read-only evidence capture utility. It does not score trades or
promote actions. Successful endpoint fetches are recorded as neutral proof rows
until a separate interpretation step explicitly confirms or contradicts the
dashboard thesis.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_uw.endpoints import UWEndpoints, validate_endpoint_path
from codex_uw.rest_client import UWConfigError, UWRequestError, UWRestClient, unwrap_uw_rows


SUPPORTED_DEFAULTS = {
    "candle_size": "1d",
}

LIMIT_ENDPOINTS = {
    "FLOW_ALERTS",
    "TICKER_FLOW_ALERTS",
    "TICKER_FLOW_RECENT",
    "TICKER_OPTIONS_VOLUME",
    "TICKER_OI_CHANGE",
    "DARKPOOL_TICKER",
    "DARKPOOL_RECENT",
    "LIT_FLOW_TICKER",
    "LIT_FLOW_RECENT",
    "MARKET_MOVERS",
}

OHLC_ENDPOINTS = {"TICKER_OHLC"}


@dataclass(frozen=True)
class EndpointCheck:
    mode: str
    label: str
    endpoint: str
    ticker: str
    path_template: str
    path_params: dict[str, Any]
    params: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


def _endpoint_catalog() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(UWEndpoints).items()
        if name.isupper() and isinstance(value, str)
    }


def _ticker(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if len(text) > 12:
        return ""
    if not all(ch.isalnum() or ch in {".", "-"} for ch in text):
        return ""
    return text


def _params_for_endpoint(endpoint: str, *, limit: int, tickers: list[str] | None = None) -> dict[str, Any]:
    tickers = tickers or []
    if endpoint == "MARKET_CORRELATIONS" and tickers:
        return {"tickers": ",".join(tickers[:8])}
    if endpoint in OHLC_ENDPOINTS:
        return {"timeframe": "1M", "limit": min(limit, 60)}
    if endpoint in LIMIT_ENDPOINTS:
        return {"limit": limit}
    return {}


def _path_params_for_endpoint(endpoint: str, path_template: str, ticker: str) -> tuple[dict[str, Any] | None, str]:
    path_params: dict[str, Any] = {}
    if "{ticker}" in path_template:
        if not ticker:
            return None, "requires ticker scope"
        path_params["ticker"] = ticker
    for key, value in SUPPORTED_DEFAULTS.items():
        if "{" + key + "}" in path_template:
            path_params[key] = value
    unsupported = []
    for part in path_template.split("{")[1:]:
        name = part.split("}", 1)[0]
        if name and name not in path_params:
            unsupported.append(name)
    if unsupported:
        return None, "unsupported path parameter(s): " + ", ".join(sorted(set(unsupported)))
    return path_params, ""


def _missing_row(mode: str, endpoint: str, summary: str, *, ticker: str = "", checked_at: str = "") -> dict[str, Any]:
    return {
        "mode": mode,
        "endpoint": endpoint,
        "ticker": ticker,
        "status": "missing",
        "checked_at": checked_at or _utc_now(),
        "summary": summary,
        "source": "uw_endpoint_result_capture",
    }


def _safe_summary(text: Any, *, limit: int = 240) -> str:
    cleaned = str(text or "").replace("{", "(").replace("}", ")")
    return cleaned[:limit]


def plan_endpoint_checks(
    runbook: dict[str, Any],
    *,
    max_modes: int = 3,
    max_tickers_per_mode: int = 4,
    max_checks: int = 12,
    limit: int = 25,
) -> tuple[list[EndpointCheck], list[dict[str, Any]]]:
    catalog = _endpoint_catalog()
    planned: list[EndpointCheck] = []
    missing: list[dict[str, Any]] = []
    rows = [row for row in runbook.get("rows") or [] if isinstance(row, dict)]
    rows = sorted(rows, key=lambda row: int(row.get("priority") or 99))[:max_modes]
    for row in rows:
        mode = str(row.get("mode") or "").strip()
        label = str(row.get("label") or mode)
        tickers = [_ticker(ticker) for ticker in row.get("ticker_scope") or []]
        tickers = [ticker for ticker in tickers if ticker][:max_tickers_per_mode]
        endpoints = []
        endpoints.extend(str(v) for v in row.get("market_checks") or [] if v)
        endpoints.extend(str(v) for v in row.get("ticker_checks") or [] if v)
        seen: set[tuple[str, str]] = set()
        for endpoint in endpoints:
            path_template = catalog.get(endpoint)
            if not path_template:
                missing.append(_missing_row(mode, endpoint, "endpoint is not in the approved UW catalog"))
                continue
            validate_endpoint_path(path_template)
            target_tickers = tickers if "{ticker}" in path_template else [""]
            if "{ticker}" in path_template and not target_tickers:
                missing.append(_missing_row(mode, endpoint, "endpoint requires ticker scope but none was present"))
                continue
            for ticker in target_tickers:
                key = (endpoint, ticker)
                if key in seen:
                    continue
                seen.add(key)
                path_params, problem = _path_params_for_endpoint(endpoint, path_template, ticker)
                if problem:
                    missing.append(_missing_row(mode, endpoint, problem, ticker=ticker))
                    continue
                planned.append(EndpointCheck(
                    mode=mode,
                    label=label,
                    endpoint=endpoint,
                    ticker=ticker,
                    path_template=path_template,
                    path_params=path_params or {},
                    params=_params_for_endpoint(endpoint, limit=limit, tickers=tickers),
                ))
                if len(planned) >= max_checks:
                    return planned, missing
    return planned, missing


def _row_count(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("data", "results", "signals", "result"):
            if key in payload and isinstance(payload.get(key), list):
                return len(payload.get(key) or [])
    rows = unwrap_uw_rows(payload)
    if rows:
        return len(rows)
    if isinstance(payload, dict) and payload:
        return 1
    if isinstance(payload, list):
        return len(payload)
    return 0


def _success_summary(check: EndpointCheck, row_count: int) -> tuple[str, str]:
    if row_count <= 0:
        return "missing", f"Fetched {check.endpoint} but captured no result rows."
    ticker = f" for {check.ticker}" if check.ticker else ""
    return "neutral", (
        f"Fetched {check.endpoint}{ticker}; row_count={row_count}. "
        "Result requires operator interpretation before any promotion."
    )


def capture_endpoint_results(
    runbook: dict[str, Any],
    client: UWRestClient,
    *,
    max_modes: int = 3,
    max_tickers_per_mode: int = 4,
    max_checks: int = 12,
    limit: int = 25,
    checked_at: str | None = None,
) -> dict[str, Any]:
    checked_at = checked_at or _utc_now()
    planned, missing = plan_endpoint_checks(
        runbook,
        max_modes=max_modes,
        max_tickers_per_mode=max_tickers_per_mode,
        max_checks=max_checks,
        limit=limit,
    )
    rows: list[dict[str, Any]] = []
    rows.extend({**row, "checked_at": checked_at} for row in missing)
    for check in planned:
        try:
            payload = client.get_json(
                check.path_template,
                path_params=check.path_params,
                params=check.params,
            )
            row_count = _row_count(payload)
            status, summary = _success_summary(check, row_count)
        except (UWRequestError, Exception) as exc:  # noqa: BLE001 - each endpoint fails closed
            status = "failed"
            summary = f"UW fetch failed for {check.endpoint}: {_safe_summary(exc)}"
            row_count = 0
        rows.append({
            "mode": check.mode,
            "endpoint": check.endpoint,
            "ticker": check.ticker,
            "status": status,
            "checked_at": checked_at,
            "summary": summary,
            "source": "uw_endpoint_result_capture",
            "row_count": row_count,
        })
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return {
        "generated_at": checked_at,
        "source": "uw_endpoint_result_capture",
        "runbook_line": runbook.get("line") or "",
        "planned_checks": len(planned),
        "rows": rows,
        "counts": counts,
        "honesty_rule": "Rows prove endpoint fetch status only; neutral rows do not confirm a trade thesis.",
    }


def _load_runbook(feed_path: str | Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(Path(feed_path).read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and isinstance(payload.get("uw_action_runbook"), dict):
        return payload["uw_action_runbook"], str(payload.get("generated_at") or "")
    if isinstance(payload, dict):
        return payload, ""
    return {}, ""


def _format_text(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") or []
    counts = payload.get("counts") or {}
    lines = [
        (
            f"UW endpoint capture: {len(rows)} result row(s); "
            f"neutral={counts.get('neutral', 0)}, missing={counts.get('missing', 0)}, failed={counts.get('failed', 0)}."
        ),
        payload.get("honesty_rule") or "",
    ]
    for row in rows[:20]:
        ticker = f" {row.get('ticker')}" if row.get("ticker") else ""
        lines.append(f"- {row.get('mode')} {row.get('endpoint')}{ticker}: {row.get('status')} - {row.get('summary')}")
    return "\n".join(line for line in lines if line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture UW endpoint result proof from the current runbook.")
    parser.add_argument("--feed", default=str(Path(__file__).resolve().parent / "latest_cockpit_feed.json"))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "uw_endpoint_results.json"))
    parser.add_argument("--max-modes", type=int, default=3)
    parser.add_argument("--max-tickers-per-mode", type=int, default=4)
    parser.add_argument("--max-checks", type=int, default=12)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    runbook, _ = _load_runbook(args.feed)
    if args.dry_run:
        planned, missing = plan_endpoint_checks(
            runbook,
            max_modes=args.max_modes,
            max_tickers_per_mode=args.max_tickers_per_mode,
            max_checks=args.max_checks,
            limit=args.limit,
        )
        payload = {
            "planned_checks": len(planned),
            "missing_rows": missing,
            "checks": [check.__dict__ for check in planned],
        }
        print(json.dumps(payload, indent=2) if args.format == "json" else f"planned={len(planned)} missing={len(missing)}")
        return 0

    try:
        client = UWRestClient(timeout=args.timeout, retries=args.retries)
    except UWConfigError as exc:
        print(f"UW endpoint capture not run: {exc}")
        return 2
    payload = capture_endpoint_results(
        runbook,
        client,
        max_modes=args.max_modes,
        max_tickers_per_mode=args.max_tickers_per_mode,
        max_checks=args.max_checks,
        limit=args.limit,
    )
    _atomic_write_json(args.out, payload)
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(_format_text(payload))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
