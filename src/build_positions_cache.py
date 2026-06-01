#!/usr/bin/env python3
"""
build_positions_cache.py — ISSUE-05 fix (v1, 2026-06-01)

Transform the portfolio-pdf-extractor --combined JSON into positions.json, the
cache the wired pre-flight (daily_preflight -> session_orchestrator ->
conviction_sizing_calibrator) reads.

WHY
    P-PORTFOLIO-INGEST updated the Latest Portfolio Notion page but did NOT
    refresh positions.json, so the cache drifted (a 5/15 snapshot vs the 5/31
    book) and produced a false CRITICALLY_BELOW conviction flag. Run this as the
    final step of ingest so positions.json always matches the latest broker PDFs.

MCP-FREE
    Reads local JSON only (the extractor output + theses.json). It does NOT call
    Notion or any network service, so it runs anywhere the ingest runs.

CONTRACT
    IN  combined.json (extractor schema_version "2.0"):
          files[] -> positions[] of {symbol, market_value, quantity, account_name?}
          portfolio_summary {total_market_value, total_cash, as_of}
    IN  theses.json: [{ticker, ...}, ...]   (the thesis'd universe to keep)
    OUT positions.json:
          {snapshot_date, sleeve_value, positions:[{ticker, shares, market_value, account}]}

DESIGN DECISIONS (confirmed 2026-06-01)
    1. sleeve_value = total_market_value + total_cash  (the full book, so each
       name's weight is a % of the total portfolio).
    2. positions[] = thesis'd-universe only (filtered by theses.json). Untracked
       holdings are excluded so they don't generate false below-floor gaps.
    3. account = "Multiple" when a ticker spans >1 account (or aggregate scope),
       else the single account_name.
    4. snapshot_date = date part of portfolio_summary.as_of.

SAFETY
    Surfaces extractor validation failures (Fidelity/Schwab validation.passed
    == False, or Robinhood all_visible_captured == False) as warnings on stderr
    and in an "_warnings" field. By default it still writes (operator decides);
    --strict turns any validation failure into a non-zero exit so a bad
    extraction can't silently refresh the cache.

USAGE
    python build_positions_cache.py --combined combined.json --theses theses.json --out positions.json
    python build_positions_cache.py --combined combined.json --theses theses.json --stdout
    python build_positions_cache.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------------------------------------------------------- helpers
def _date_only(as_of: Optional[str]) -> Optional[str]:
    """ISO 8601 timestamp -> date string. '2026-05-31T14:49:00' -> '2026-05-31'."""
    if not as_of:
        return None
    return str(as_of).split("T", 1)[0].strip() or None


def _thesis_universe(theses: List[Dict[str, Any]]) -> set:
    """Set of uppercased tickers from theses.json (the names to keep)."""
    out = set()
    for t in theses or []:
        tk = (t.get("ticker") or "").upper().strip()
        if tk:
            out.add(tk)
    return out


def _iter_position_rows(combined: Dict[str, Any]):
    """Yield every position row across all files (positions live in files[]->positions[])."""
    for f in combined.get("files", []) or []:
        for p in f.get("positions", []) or []:
            yield p


def _validation_warnings(combined: Dict[str, Any]) -> List[str]:
    """Collect human-readable warnings for any file whose extraction didn't validate."""
    warnings: List[str] = []
    for f in combined.get("files", []) or []:
        src = f.get("source_file") or "?"
        v = f.get("validation") or {}
        # Fidelity/Schwab: passed; Robinhood: all_visible_captured (passed may be absent)
        passed = v.get("passed")
        rh_ok = v.get("all_visible_captured")
        if passed is False:
            delta = v.get("delta")
            warnings.append(f"{src}: validation.passed == False"
                            + (f" (delta {delta})" if delta is not None else "")
                            + " -- parser may have missed/duplicated a row; investigate before trusting.")
        elif passed is None and rh_ok is False:
            warnings.append(f"{src}: Robinhood all_visible_captured == False -- a visible "
                            "position line was not extracted; investigate.")
    # Carry through any extractor-level warnings (e.g. files span >24h)
    for w in combined.get("warnings", []) or []:
        warnings.append(f"extractor: {w}")
    return warnings


# ----------------------------------------------------------------------------- core
def build_positions(combined: Dict[str, Any],
                    theses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pure transform: combined-extractor-JSON + theses -> positions.json dict."""
    universe = _thesis_universe(theses)

    mv_by_ticker: Dict[str, float] = defaultdict(float)
    sh_by_ticker: Dict[str, float] = defaultdict(float)
    accts_by_ticker: Dict[str, set] = defaultdict(set)

    for p in _iter_position_rows(combined):
        sym = (p.get("symbol") or "").upper().strip()
        if not sym or sym not in universe:
            continue
        mv = p.get("market_value")
        if mv is None:
            # unpriced rights/warrants -> no MV to aggregate; skip from the cache
            continue
        mv_by_ticker[sym] += float(mv)
        q = p.get("quantity")
        if q is not None:
            sh_by_ticker[sym] += float(q)
        acct = (p.get("account_name") or "").strip()
        if acct:
            accts_by_ticker[sym].add(acct)

    positions: List[Dict[str, Any]] = []
    # Sort by market value desc so the cache reads top-down like the book.
    for sym in sorted(mv_by_ticker, key=lambda s: mv_by_ticker[s], reverse=True):
        accts = accts_by_ticker.get(sym, set())
        if len(accts) == 1:
            account = next(iter(accts))
        else:
            # >1 account, or aggregate scope (Schwab) where account_name is absent
            account = "Multiple"
        positions.append({
            "ticker": sym,
            "shares": round(sh_by_ticker.get(sym, 0.0), 4),
            "market_value": round(mv_by_ticker[sym]),
            "account": account,
        })

    summary = combined.get("portfolio_summary", {}) or {}
    total_mv = float(summary.get("total_market_value", 0) or 0)
    total_cash = float(summary.get("total_cash", 0) or 0)

    return {
        "snapshot_date": _date_only(summary.get("as_of")),
        "sleeve_value": round(total_mv + total_cash),
        "positions": positions,
    }


def build_from_paths(combined_path: str, theses_path: str
                     ) -> Tuple[Dict[str, Any], List[str]]:
    """Load inputs from disk, run the transform, and return (positions_dict, warnings)."""
    with open(combined_path) as fh:
        combined = json.load(fh)
    with open(theses_path) as fh:
        theses = json.load(fh)
    # theses.json may be a bare list or {"theses": [...]}
    if isinstance(theses, dict):
        theses = theses.get("theses") or theses.get("positions") or []
    warnings = _validation_warnings(combined)
    out = build_positions(combined, theses)
    if warnings:
        out["_warnings"] = warnings
    return out, warnings


# ----------------------------------------------------------------------------- validator
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_positions(out: Dict[str, Any]) -> List[str]:
    """Return a list of contract violations in a positions.json dict. Empty list == valid.

    The downstream consumer (conviction_sizing_calibrator via session_orchestrator)
    needs: a date string snapshot_date, a positive sleeve_value, and positions[]
    rows each carrying a non-empty ticker and a non-negative market_value. This is
    the seam validator so a producer can't silently hand the pre-flight a bad shape.
    """
    errs: List[str] = []
    if not isinstance(out, dict):
        return ["top-level is not an object"]

    sd = out.get("snapshot_date")
    if not isinstance(sd, str) or not _DATE_RE.match(sd):
        errs.append(f"snapshot_date must be a YYYY-MM-DD string (got {sd!r})")

    sv = out.get("sleeve_value")
    if isinstance(sv, bool) or not isinstance(sv, (int, float)) or sv <= 0:
        errs.append(f"sleeve_value must be a positive number (got {sv!r})")

    pos = out.get("positions")
    if not isinstance(pos, list):
        errs.append(f"positions must be a list (got {type(pos).__name__})")
        return errs

    seen = set()
    total = 0.0
    for i, p in enumerate(pos):
        if not isinstance(p, dict):
            errs.append(f"positions[{i}] is not an object")
            continue
        tk = p.get("ticker")
        if not isinstance(tk, str) or not tk.strip():
            errs.append(f"positions[{i}].ticker must be a non-empty string (got {tk!r})")
        else:
            if tk in seen:
                errs.append(f"positions[{i}].ticker duplicate: {tk} (aggregation should have merged it)")
            seen.add(tk)
        mv = p.get("market_value")
        if isinstance(mv, bool) or not isinstance(mv, (int, float)) or mv < 0:
            errs.append(f"positions[{i}].market_value must be a non-negative number (got {mv!r})")
        else:
            total += float(mv)
        if isinstance(p.get("shares"), bool) or not isinstance(p.get("shares"), (int, float)):
            errs.append(f"positions[{i}].shares must be a number (got {p.get('shares')!r})")
        if not isinstance(p.get("account"), str) or not p.get("account"):
            errs.append(f"positions[{i}].account must be a non-empty string")

    # Sanity: the thesis'd subset can never exceed the full book (+$1 rounding slack).
    if not isinstance(sv, bool) and isinstance(sv, (int, float)) and total > float(sv) + 1:
        errs.append(f"sum(positions market_value) {total:.0f} exceeds sleeve_value {sv} (impossible)")
    return errs


# ----------------------------------------------------------------------------- self-test
def _self_test() -> int:
    combined = {
        "schema_version": "2.0",
        "files": [
            {"source_file": "fidelity.pdf",
             "validation": {"passed": True},
             "positions": [
                 {"symbol": "NVDA", "market_value": 100000.0, "quantity": 470.0,
                  "account_name": "Joint"},
                 {"symbol": "nvda", "market_value": 26076.0, "quantity": 126.0,
                  "account_name": "Roth IRA"},
                 {"symbol": "GS", "market_value": 12253.0, "quantity": 12.0,
                  "account_name": "Joint"},  # NOT thesis'd -> excluded
                 {"symbol": "RIGHTS", "market_value": None, "quantity": None,
                  "account_name": "Joint"},  # unpriced -> skipped
             ]},
            {"source_file": "schwab.pdf",
             "validation": {"passed": True},
             "positions": [
                 # aggregate scope: no account_name
                 {"symbol": "LEU", "market_value": 93143.0, "quantity": 511.0},
             ]},
        ],
        "portfolio_summary": {"total_market_value": 1909389.0,
                              "total_cash": 12545.0,
                              "as_of": "2026-05-31T14:49:00"},
    }
    theses = [{"ticker": "NVDA"}, {"ticker": "LEU"}]  # GS intentionally absent
    out = build_positions(combined, theses)

    assert out["snapshot_date"] == "2026-05-31", out["snapshot_date"]
    assert out["sleeve_value"] == 1921934, out["sleeve_value"]          # 1,909,389 + 12,545
    tickers = {p["ticker"] for p in out["positions"]}
    assert tickers == {"NVDA", "LEU"}, tickers                          # GS filtered out
    nvda = next(p for p in out["positions"] if p["ticker"] == "NVDA")
    assert nvda["market_value"] == 126076, nvda                          # 100,000 + 26,076 aggregated
    assert nvda["shares"] == 596.0, nvda                                 # 470 + 126
    assert nvda["account"] == "Multiple", nvda                           # 2 accounts
    leu = next(p for p in out["positions"] if p["ticker"] == "LEU")
    assert leu["account"] == "Multiple", leu                             # aggregate scope -> Multiple
    # order: NVDA (126,076) before LEU (93,143)
    assert [p["ticker"] for p in out["positions"]] == ["NVDA", "LEU"], out["positions"]

    print("build_positions_cache self-test: PASS "
          "(aggregate-by-symbol, theses filter, sleeve+cash, symbol->ticker, account rule, sort)")
    return 0


# ----------------------------------------------------------------------------- cli
def main() -> int:
    ap = argparse.ArgumentParser(description="Build positions.json from extractor --combined JSON (ISSUE-05).")
    ap.add_argument("--combined", help="Path to the extractor --combined JSON.")
    ap.add_argument("--theses", help="Path to theses.json (the thesis'd universe).")
    ap.add_argument("--out", help="Path to write positions.json.")
    ap.add_argument("--stdout", action="store_true", help="Write the result to stdout instead of --out.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any file failed extractor validation.")
    ap.add_argument("--validate", help="Validate an existing positions.json against the contract, then exit.")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if args.validate:
        with open(args.validate) as fh:
            existing = json.load(fh)
        errs = validate_positions(existing)
        for e in errs:
            print(f"INVALID: {e}", file=sys.stderr)
        if errs:
            return 1
        print(f"VALID: {args.validate} conforms to the positions.json contract.")
        return 0

    if not args.combined or not args.theses:
        ap.error("--combined and --theses are required (or use --self-test / --validate)")

    out, warnings = build_from_paths(args.combined, args.theses)

    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    if warnings and args.strict:
        print("ERROR: --strict set and extractor validation failed; not writing cache.",
              file=sys.stderr)
        return 1

    text = json.dumps(out, indent=2)
    if args.stdout or not args.out:
        print(text)
    else:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        print(f"Wrote {args.out}: {len(out['positions'])} thesis'd names, "
              f"sleeve_value ${out['sleeve_value']:,}, snapshot {out['snapshot_date']}.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
