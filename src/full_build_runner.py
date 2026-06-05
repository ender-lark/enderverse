#!/usr/bin/env python3
"""Repo-owned full cockpit build runner.

This is the replacement control point for prompt-only FULL-build wiring. It
loads convention files from src/, adapts cached positions into the existing
source rails, calls the same feed assembler used by the runtime, and optionally
publishes through the existing publish gate.

No network calls happen here. Live routines should fetch/parse data elsewhere,
write the convention files, then run this module.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from collection import collect
from collection_gate import validate_collection_gate
from feed_assembler import assemble_feed
from fundstrat_bible import build_fundstrat_bible_source
from fundstrat_daily import build_fundstrat_daily_source
from meridian import build_meridian_source
from portfolio_views import build_portfolio_views
from portfolio import build_portfolio_source
from position_drift_check import target_weight_drift_summary
from publish_cockpit_feed import publish_cockpit_feed
from runtime_adapters import catalysts_from_calendar_rows, closes_by_ticker_from_uw
from sources import SourceRegistry
from uw_macro import build_uw_macro_source
from uw_price import build_uw_price_source
from validators import validate_cockpit_feed


class FullBuildError(RuntimeError):
    """The full build could not produce a safe Contract-C feed."""


_MISSING = object()

DEFAULT_FILES = {
    "positions": ("positions.json",),
    "account_positions": ("account_positions.json",),
    "theses": ("theses.json",),
    "uw_prices": ("uw_closes.json", "uw_price_responses.json", "prices.json"),
    "macro": ("macro_state.json",),
    "fs_bible": ("fundstrat_bible.json", "fs_bible.json"),
    "fs_daily": ("fundstrat_daily_calls.json", "fs_daily_calls.json"),
    "meridian": ("meridian_items.json",),
    "heartbeat": ("heartbeat.json",),
    "signal_log": ("signal_log.json", "morning_signal_log.json"),
    "event_risk": ("event_risks.json", "event_risk.json"),
    "synthesis": ("daily_synthesis.json", "synthesis.json"),
    "research": ("research_queue.json", "research.json"),
    "catalysts": ("catalysts.json", "catalyst_calendar.json"),
    "uw_opportunity": ("uw_opportunity_signals.json",),
    "open_opportunities": ("open_opportunities.json",),
    "top_prospects": ("top_prospects.json",),
    "source_calls": ("source_calls.json",),
    "inbox_call_dates": ("inbox_call_dates.json",),
    "log_call_dates": ("log_call_dates.json",),
    "parabolic": ("parabolic_setups.json",),
}


def _src_dir() -> Path:
    return Path(__file__).resolve().parent


def _manifest_path() -> Path:
    return _src_dir() / "codex_routine_manifest.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_comments(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_comments(v)
            for k, v in obj.items()
            if not (isinstance(k, str) and k.startswith("_"))
        }
    if isinstance(obj, list):
        return [_strip_comments(x) for x in obj]
    return obj


def _read_json(path: Path, *, required: bool = False, default: Any = _MISSING) -> Any:
    if not path or not path.is_file():
        if required:
            raise FileNotFoundError(f"required input not found: {path}")
        return None if default is _MISSING else default
    with path.open(encoding="utf-8") as fh:
        return _strip_comments(json.load(fh))


def _atomic_write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".full_build.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _resolve(src_dir: Path, key: str, override: str | Path | None = None) -> Path | None:
    if override:
        return Path(override)
    for name in DEFAULT_FILES[key]:
        path = src_dir / name
        if path.is_file():
            return path
    return None


def _daily_convention_contract(manifest_path: str | Path | None = None) -> dict[str, dict]:
    path = Path(manifest_path) if manifest_path else _manifest_path()
    try:
        manifest = _read_json(path, default={})
    except Exception:
        manifest = {}
    routines = manifest.get("routines") if isinstance(manifest, dict) else []
    daily = next(
        (r for r in routines or [] if isinstance(r, dict) and r.get("id") == "daily_full_build"),
        {},
    )
    rows = daily.get("convention_inputs") if isinstance(daily, dict) else []
    return {
        str(row.get("key")): row
        for row in rows or []
        if isinstance(row, dict) and row.get("key")
    }


def convention_input_status(
    src_dir: str | Path | None = None,
    *,
    overrides: dict[str, str | Path | None] | None = None,
    manifest_path: str | Path | None = None,
) -> list[dict]:
    """Report which daily full-build convention inputs are present.

    This is routine-side evidence, not engine judgment: it explains why a lane is
    dark and which source routine/cache owns the missing input.
    """
    src = Path(src_dir) if src_dir else _src_dir()
    overrides = overrides or {}
    contract = _daily_convention_contract(manifest_path)
    rows: list[dict] = []
    for key, default_names in DEFAULT_FILES.items():
        row = contract.get(key, {})
        if key in overrides and overrides[key]:
            candidate_paths = [str(Path(overrides[key]))]
        else:
            candidate_paths = [str(src / name) for name in default_names]
        resolved = _resolve(src, key, overrides.get(key))
        required = bool(row.get("required")) if row else key in {"positions", "theses"}
        present = bool(resolved and resolved.is_file())
        rows.append({
            "key": key,
            "required": required,
            "present": present,
            "status": "present" if present else "missing_required" if required else "missing_optional",
            "resolved_path": str(resolved) if present else "",
            "candidate_paths": candidate_paths,
            "source": row.get("source") or "",
            "missing_behavior": row.get("missing_behavior") or "",
        })
    return rows


def _load_optional(src_dir: Path, key: str, override: str | Path | None = None) -> Any:
    path = _resolve(src_dir, key, override)
    if path is None:
        return None
    return _read_json(path, default=None)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_positions_cache(cache: Any) -> tuple[list[dict], str | None]:
    """positions.json shape -> portfolio plug position shape.

    Accepts either a bare list or the cached wrapper:
    {snapshot_date, sleeve_value, positions:[{ticker, market_value, ...}]}.
    """
    if isinstance(cache, dict):
        rows = cache.get("positions") or []
        snapshot_date = cache.get("snapshot_date")
        sleeve_total = _num(cache.get("sleeve_value"))
    else:
        rows = cache or []
        snapshot_date = None
        sleeve_total = None

    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        value = _num(row.get("value") or row.get("market_value") or row.get("mv"))
        pct = _num(row.get("pct") or row.get("percent") or row.get("weight"))
        if pct is None and value is not None and sleeve_total:
            pct = value / sleeve_total * 100.0
        out.append({
            "ticker": ticker,
            "pct": pct,
            "shares": _num(row.get("shares")),
            "value": value,
            "account": row.get("account"),
            "owner": row.get("owner") or row.get("owners"),
            "sleeve": row.get("sleeve"),
        })
    return out, str(snapshot_date)[:10] if snapshot_date else None


def normalize_closes_cache(cache: Any) -> dict:
    """Load either {ticker:[closes]} or {ticker:{data:[{c,date}]}} price caches."""
    if not isinstance(cache, dict):
        return {}
    closes: dict[str, list[float]] = {}
    uw_like: dict[str, dict] = {}
    for ticker, value in cache.items():
        tk = str(ticker).strip().upper()
        if not tk:
            continue
        if isinstance(value, list):
            if value and all(isinstance(v, dict) for v in value):
                pts = [
                    (v.get("date") or "", _num(v.get("c") or v.get("close")))
                    for v in value
                ]
                pts = [(d, c) for d, c in pts if c is not None]
                pts.sort(key=lambda dc: dc[0])
                closes[tk] = [float(c) for _, c in pts]
            else:
                nums = [_num(v) for v in value]
                closes[tk] = [float(v) for v in nums if v is not None]
        elif isinstance(value, dict) and isinstance(value.get("data"), list):
            uw_like[tk] = value
    closes.update(closes_by_ticker_from_uw(uw_like))
    return {tk: vals for tk, vals in closes.items() if vals}


def latest_prices_from_closes(closes: dict) -> dict:
    prices = {}
    for ticker, values in (closes or {}).items():
        if values:
            prices[ticker] = values[-1]
    return prices


def active_parabolic_tickers(cache: Any, tiers=("AUTOFIRE", "WATCHLIST")) -> set[str]:
    if not isinstance(cache, dict):
        return set()
    active = set()
    for row in cache.get("results") or []:
        if not isinstance(row, dict):
            continue
        if row.get("surface_tier") in tiers and row.get("ticker"):
            active.add(str(row["ticker"]).strip().upper())
    return active


def build_full_feed_from_files(
    *,
    src_dir: str | Path | None = None,
    positions_path: str | Path | None = None,
    theses_path: str | Path | None = None,
    uw_prices_path: str | Path | None = None,
    as_of: str | None = None,
    run_timestamp: str | None = None,
    generated_at: str | None = None,
) -> dict:
    """Load convention files and build a validated cockpit feed."""
    src = Path(src_dir) if src_dir else _src_dir()
    now = run_timestamp or _utc_now_iso()
    today = as_of or date.today().isoformat()

    positions_file = _resolve(src, "positions", positions_path)
    theses_file = _resolve(src, "theses", theses_path)
    positions_cache = _read_json(positions_file, required=True)
    account_positions = _load_optional(src, "account_positions")
    theses = _read_json(theses_file, required=True)
    positions, positions_as_of = normalize_positions_cache(positions_cache)
    if not positions:
        raise FullBuildError("positions cache produced no portfolio rows")

    closes_cache = _load_optional(src, "uw_prices", uw_prices_path)
    closes = normalize_closes_cache(closes_cache)
    macro = _load_optional(src, "macro")
    fs_bible = _load_optional(src, "fs_bible")
    fs_daily = _load_optional(src, "fs_daily")
    meridian = _load_optional(src, "meridian")
    heartbeat = _load_optional(src, "heartbeat")
    signal_log = _load_optional(src, "signal_log")
    event_risk = _load_optional(src, "event_risk")
    synthesis = _load_optional(src, "synthesis")
    research = _load_optional(src, "research")
    catalyst_rows = _load_optional(src, "catalysts")
    uw_opportunity = _load_optional(src, "uw_opportunity")
    open_opportunities = _load_optional(src, "open_opportunities")
    top_prospects = _load_optional(src, "top_prospects")
    source_calls = _load_optional(src, "source_calls")
    inbox_call_dates = _load_optional(src, "inbox_call_dates")
    log_call_dates = _load_optional(src, "log_call_dates")
    parabolic_cache = _load_optional(src, "parabolic")
    target_drift = target_weight_drift_summary(positions_cache)

    catalysts = None
    if catalyst_rows is not None:
        catalysts = catalysts_from_calendar_rows(catalyst_rows, as_of=today)

    reg = SourceRegistry()
    reg.register(build_portfolio_source(positions, as_of=positions_as_of or now))
    if closes_cache is not None:
        reg.register(build_uw_price_source(closes, as_of=now))
    if macro is not None:
        reg.register(build_uw_macro_source(macro, as_of=now))
    if fs_bible is not None:
        reg.register(build_fundstrat_bible_source(fs_bible))
    if fs_daily is not None:
        reg.register(build_fundstrat_daily_source(fs_daily))
    if meridian is not None:
        reg.register(build_meridian_source(meridian))

    critical_sources = ("portfolio", "uw_price") if closes_cache is not None else ("portfolio",)
    snap = collect(reg, critical=critical_sources, run_timestamp=now)
    collection_problems = validate_collection_gate(snap)
    if collection_problems:
        raise FullBuildError(f"snapshot failed L2->L3 collection gate: {collection_problems}")

    feed = assemble_feed(
        {
            "as_of": today,
            "snapshot": dataclasses.asdict(snap),
            "theses": theses or [],
        },
        parabolic=active_parabolic_tickers(parabolic_cache),
        generated_at=generated_at or now,
        heartbeat=heartbeat,
        signal_log=signal_log,
        event_risk=event_risk,
        synthesis=synthesis,
        research=research,
        catalysts=catalysts,
        uw_opportunity=uw_opportunity,
        open_opportunities=open_opportunities,
        opp_prices=latest_prices_from_closes(closes),
        top_prospects=top_prospects,
        source_calls=source_calls,
        inbox_call_dates=inbox_call_dates,
        log_call_dates=log_call_dates,
        target_drift=target_drift,
    )
    portfolio_views = build_portfolio_views(account_positions)
    if portfolio_views:
        feed["portfolio_views"] = portfolio_views
    problems = validate_cockpit_feed(feed)
    if problems:
        raise FullBuildError(f"feed failed Contract-C validation: {problems}")
    return feed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the cockpit FEED from repo convention files."
    )
    parser.add_argument("--src-dir", default=str(_src_dir()))
    parser.add_argument("--positions")
    parser.add_argument("--theses")
    parser.add_argument("--uw-prices")
    parser.add_argument("--as-of")
    parser.add_argument("--run-timestamp")
    parser.add_argument("--generated-at")
    parser.add_argument("--feed-out", help="Write the built feed JSON")
    parser.add_argument("--publish", action="store_true",
                        help="Run publish gate, write --feed-out, and update action memory")
    parser.add_argument("--store", help="open_opportunities.json path for publish memory")
    parser.add_argument("--no-memory", action="store_true")
    args = parser.parse_args(argv)

    feed = build_full_feed_from_files(
        src_dir=args.src_dir,
        positions_path=args.positions,
        theses_path=args.theses,
        uw_prices_path=args.uw_prices,
        as_of=args.as_of,
        run_timestamp=args.run_timestamp,
        generated_at=args.generated_at,
    )

    if args.publish:
        closes = normalize_closes_cache(
            _load_optional(Path(args.src_dir), "uw_prices", args.uw_prices)
        )
        summary = publish_cockpit_feed(
            feed,
            feed_out=args.feed_out,
            store_path=args.store or str(Path(args.src_dir) / "open_opportunities.json"),
            prices=latest_prices_from_closes(closes),
            update_memory=not args.no_memory,
        )
        print(json.dumps(summary, indent=2))
        return 0 if summary.get("published") else 2

    if args.feed_out:
        _atomic_write_json(Path(args.feed_out), feed)
    lane_rows = feed.get("lane_status", {}).get("rows", [])
    dark_lane_keys = [
        row.get("key")
        for row in lane_rows
        if isinstance(row, dict) and row.get("status") == "not_checked"
    ]
    dark_lane_details = [
        {
            "key": row.get("key"),
            "label": row.get("label") or row.get("key"),
            "next_step": row.get("next_step") or "",
            "missing_impact": row.get("missing_impact") or "",
        }
        for row in lane_rows
        if isinstance(row, dict) and row.get("status") == "not_checked"
    ]
    input_rows = convention_input_status(
        args.src_dir,
        overrides={
            "positions": args.positions,
            "theses": args.theses,
            "uw_prices": args.uw_prices,
        },
    )
    print(json.dumps({
        "built": True,
        "feed_out": args.feed_out or "",
        "actions": len(feed.get("actions") or []),
        "research_actions": len(feed.get("research_actions") or []),
        "dark_lanes": feed.get("lane_status", {}).get("counts", {}).get("not_checked", 0),
        "dark_lane_keys": dark_lane_keys,
        "dark_lane_details": dark_lane_details,
        "missing_required_inputs": [row for row in input_rows if row["status"] == "missing_required"],
        "missing_optional_inputs": [row for row in input_rows if row["status"] == "missing_optional"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
