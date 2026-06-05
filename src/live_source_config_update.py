#!/usr/bin/env python3
"""Write non-secret live-source connector proof metadata.

This helper intentionally stores only proof metadata such as connector name,
verification time, market date, and latest market-tide timestamp. It does not
store raw market payload rows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_OUT = Path(__file__).resolve().parent / "live_source_config.json"
ET = ZoneInfo("America/New_York")


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".live_source_config.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ET)


def _iso_dt(value: str | None = None) -> str:
    parsed = _parse_dt(value) if value else None
    return (parsed or datetime.now(ET)).astimezone(ET).replace(microsecond=0).isoformat()


def _as_dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _market_state_date(payload: Any) -> str:
    row = _as_dict(payload)
    if isinstance(row.get("market_state"), dict):
        row = row["market_state"]
    if row.get("date") and (
        "call_volume" in row
        or "put_volume" in row
        or "put_call_ratio" in row
        or "is_open" in row
    ):
        return str(row.get("date") or "")[:10]
    return ""


def _market_tide_latest(payload: Any) -> str:
    row = _as_dict(payload)
    if isinstance(row.get("market_tide"), dict):
        row = row["market_tide"]
    data = row.get("data")
    if not isinstance(data, list):
        return ""
    timestamps = [
        str(item.get("timestamp") or "")
        for item in data
        if isinstance(item, dict) and item.get("timestamp")
    ]
    return max(timestamps) if timestamps else ""


def _collect_proof(payloads: list[Any]) -> dict[str, str]:
    market_state_dates: list[str] = []
    market_tide_timestamps: list[str] = []
    for payload in payloads:
        if isinstance(payload, dict):
            market_state = _market_state_date(payload)
            market_tide = _market_tide_latest(payload)
            if market_state:
                market_state_dates.append(market_state)
            if market_tide:
                market_tide_timestamps.append(market_tide)
            for key in ("market_state", "market_tide"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    nested_state = _market_state_date(nested)
                    nested_tide = _market_tide_latest(nested)
                    if nested_state:
                        market_state_dates.append(nested_state)
                    if nested_tide:
                        market_tide_timestamps.append(nested_tide)
    return {
        "market_state_date": max(market_state_dates) if market_state_dates else "",
        "market_tide_latest_timestamp": max(market_tide_timestamps) if market_tide_timestamps else "",
    }


def build_live_source_config(payloads: list[Any], *, verified_at: str | None = None) -> dict[str, Any]:
    proof = _collect_proof(payloads)
    if not proof["market_state_date"] and not proof["market_tide_latest_timestamp"]:
        raise ValueError("no recognized Unusual Whales market_state or market_tide proof supplied")

    verification_bits: list[str] = []
    if proof["market_state_date"]:
        verification_bits.append(
            f"get_market_state returned market-wide daily options snapshot for {proof['market_state_date']}"
        )
    if proof["market_tide_latest_timestamp"]:
        verification_bits.append(
            "get_market_tide returned market-wide rows through "
            f"{proof['market_tide_latest_timestamp']}"
        )

    verified = _iso_dt(verified_at)
    connector = {
        "available": True,
        "verified_at": verified,
        "verified_by": "Codex app Unusual Whales connector",
        "verification": "; ".join(verification_bits),
        "notes": [
            "No API key or secret is stored in this file.",
            "This proves connector availability, not that a specific cache was freshly rebuilt.",
        ],
    }
    if proof["market_state_date"]:
        connector["market_state_date"] = proof["market_state_date"]
    if proof["market_tide_latest_timestamp"]:
        connector["market_tide_latest_timestamp"] = proof["market_tide_latest_timestamp"]
    return {
        "schema_version": 1,
        "verified_at": verified,
        "connectors": {
            "unusual_whales": connector,
        },
    }


def validate_config(payload: Any) -> list[str]:
    problems: list[str] = []
    config = _as_dict(payload)
    if config.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    if not _parse_dt(config.get("verified_at")):
        problems.append("verified_at must be an ISO datetime")
    connectors = config.get("connectors")
    if not isinstance(connectors, dict):
        problems.append("connectors must be an object")
        return problems
    uw = connectors.get("unusual_whales")
    if not isinstance(uw, dict):
        problems.append("connectors.unusual_whales must be an object")
        return problems
    if uw.get("available") is not True:
        problems.append("connectors.unusual_whales.available must be true")
    if not _parse_dt(uw.get("verified_at")):
        problems.append("connectors.unusual_whales.verified_at must be an ISO datetime")
    if not uw.get("market_state_date") and not uw.get("market_tide_latest_timestamp"):
        problems.append("connectors.unusual_whales must include market_state_date or market_tide_latest_timestamp")
    forbidden = {"data", "call_volume", "put_volume", "call_premium", "put_premium", "net_call_premium", "net_put_premium"}
    present_forbidden = sorted(key for key in forbidden if key in uw)
    if present_forbidden:
        problems.append("raw market payload fields are not allowed: " + ", ".join(present_forbidden))
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write non-secret live-source connector proof metadata")
    parser.add_argument("files", nargs="*", help="Connector output JSON files")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--verified-at", help="Proof timestamp; defaults to current ET")
    parser.add_argument("--validate", metavar="LIVE_SOURCE_CONFIG_JSON")
    args = parser.parse_args(argv)

    if args.validate:
        payload = _read_json(args.validate)
        problems = validate_config(payload)
        print(json.dumps({"valid": not problems, "problems": problems, "path": args.validate}, indent=2))
        return 0 if not problems else 2

    if not args.files and not args.stdin_json:
        print("no input files or --stdin-json supplied", file=sys.stderr)
        return 2

    payloads = [_read_json(path) for path in args.files]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))
    try:
        config = build_live_source_config(payloads, verified_at=args.verified_at)
    except ValueError as exc:
        print(json.dumps({"valid": False, "written": False, "problems": [str(exc)]}, indent=2))
        return 2
    problems = validate_config(config)
    if problems:
        print(json.dumps({"valid": False, "written": False, "problems": problems}, indent=2))
        return 2
    _atomic_write_json(args.out, config)
    print(json.dumps({"valid": True, "written": True, "out": args.out, "verified_at": config["verified_at"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
