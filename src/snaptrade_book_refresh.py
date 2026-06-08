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
) -> dict[str, Any]:
    """Pull SnapTrade and promote validated book artifacts."""
    client = snaptrade.SnapTradeClient()
    profiles = snaptrade.read_profiles(profiles_path)
    raw = snaptrade.pull_profiles(client, profiles)
    combined = snaptrade.build_combined_from_snaptrade(raw)

    _write_json(raw_out, raw)
    _write_json(combined_out, combined)

    combined_problems = broker_pdf_extractor.validate_combined(combined)
    if combined_problems:
        raise BookRefreshError("combined validation failed: " + "; ".join(combined_problems))

    theses_doc = _read_json(theses_path, [])
    theses = theses_doc.get("theses") if isinstance(theses_doc, dict) else theses_doc
    positions = build_positions_cache.build_positions(combined, theses or [])
    position_problems = build_positions_cache.validate_positions(positions)
    if position_problems:
        raise BookRefreshError("positions validation failed: " + "; ".join(position_problems))

    prior_account = _read_json(account_out, {})
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
