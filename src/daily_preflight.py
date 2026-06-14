#!/usr/bin/env python3
"""
daily_preflight.py — v11.26 daily session-open wrapper

PURPOSE
    One-command entry point for daily session-open pre-flight.  Wraps
    session_orchestrator.py with sensible default input paths so the
    operator can run:

        python3 daily_preflight.py

    ...and get the full v11.26 dashboard without re-specifying file paths.

DEFAULTS
    Resolves each input by: CLI arg > env var > ./sample_inputs/<file> >
    ./<file> (cwd).  v11.33 H1 fix: the canonical JSON inputs historically
    live at the project/working-dir root, not in a sample_inputs/ subdir, so
    resolution falls back to the cwd when sample_inputs/ is absent or a file
    is missing from it.  Env-var overrides:
      INVEST_POSITIONS      → positions.json
      INVEST_THESES         → theses.json
      INVEST_MACRO          → macro_state.json
      INVEST_SOURCE_RATES   → source_rates.json
      INVEST_INSIDER_DATA   → insider_data.json
      INVEST_CATALYSTS      → catalysts.json
      INVEST_SOURCE_CALLS   → source_calls.json
      INVEST_RATIONALES     → rationales.json
      INVEST_PRIOR          → prior_snapshot.json
      INVEST_PARABOLIC      → parabolic_setups.json
      INVEST_SLEEVE_TOTAL   → numeric sleeve total (default $1,875,000)

    Each optional input is loaded if file exists, otherwise skipped (the
    orchestrator handles missing inputs gracefully).

OUTPUT
    Text dashboard (default) or JSON via --json.

USAGE
    python3 daily_preflight.py
    python3 daily_preflight.py --json
    python3 daily_preflight.py --inputs-dir /path/to/inputs
    INVEST_POSITIONS=/tmp/p.json python3 daily_preflight.py
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path


def _configure_stdio():
    """Prefer UTF-8 console output so warning symbols cannot crash preflight."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_stdio()


# ============================================================================
# DEFAULTS
# ============================================================================

DEFAULT_INPUTS_DIR = "sample_inputs"
DEFAULT_SLEEVE_TOTAL = 1875000.0


def _default_inputs_dir():
    """v11.33 H1 fix — pick the default --inputs-dir.

    Prefer ./sample_inputs/ when that directory actually exists; otherwise
    fall back to '.' (cwd).  The canonical JSON inputs historically sit at
    the project/working-dir root, not in a sample_inputs/ subdir, so the
    old hard default of 'sample_inputs' crashed `daily_preflight.py` on a
    clean checkout.  Per-file fallback in `_resolve()` handles the mixed
    case where only some inputs live in sample_inputs/.
    """
    return DEFAULT_INPUTS_DIR if Path(DEFAULT_INPUTS_DIR).is_dir() else "."

DEFAULT_FILES = {
    "positions":     "positions.json",
    "theses":        "theses.json",
    "macro":         "macro_state.json",
    "source_rates":  "source_rates.json",
    "insider_data":  "insider_data.json",
    "catalysts":     "catalysts.json",
    "source_calls":  "source_calls.json",
    "rationales":    "rationales.json",
    "prior":         "prior_snapshot.json",
    "parabolic":     "parabolic_setups.json",
    "inbox_dates":   "inbox_call_dates.json",
    "log_dates":     "log_call_dates.json",
    "position_reconciliation": "position_reconciliation.json",
}

ENV_OVERRIDES = {
    "positions":    "INVEST_POSITIONS",
    "theses":       "INVEST_THESES",
    "macro":        "INVEST_MACRO",
    "source_rates": "INVEST_SOURCE_RATES",
    "insider_data": "INVEST_INSIDER_DATA",
    "catalysts":    "INVEST_CATALYSTS",
    "source_calls": "INVEST_SOURCE_CALLS",
    "rationales":   "INVEST_RATIONALES",
    "prior":        "INVEST_PRIOR",
    "parabolic":    "INVEST_PARABOLIC",
    "inbox_dates":  "INVEST_INBOX_CALL_DATES",
    "log_dates":    "INVEST_LOG_CALL_DATES",
    "position_reconciliation": "INVEST_POSITION_RECONCILIATION",
}


# ============================================================================
# HELPERS
# ============================================================================

def _strip_comments(obj):
    """Recursively remove _comment / _schema metadata keys from JSON for clean use."""
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items()
                if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(obj, list):
        return [_strip_comments(x) for x in obj]
    return obj


def _load(path, optional=True):
    """Load JSON; return None if file missing and optional, else raise."""
    if not path or not Path(path).is_file():
        if optional:
            return None
        raise FileNotFoundError(f"Required input not found: {path}")
    with open(path) as f:
        return _strip_comments(json.load(f))


def _resolve(key, args, inputs_dir):
    """Resolve path: CLI arg > env var > <inputs_dir>/<file> > ./<file>.

    v11.33 H1 fix: when the file is absent from inputs_dir, fall back to the
    cwd before giving up — the canonical JSONs historically sit at root.
    The primary (inputs_dir) path is still returned when neither exists, so
    `_load`'s FileNotFoundError message points at the expected location.
    """
    cli_attr = key.replace("-", "_")
    cli_val = getattr(args, cli_attr, None)
    if cli_val:
        return cli_val
    env_val = os.environ.get(ENV_OVERRIDES[key])
    if env_val:
        return env_val
    fname = DEFAULT_FILES[key]
    primary = Path(inputs_dir) / fname
    if primary.is_file():
        return str(primary)
    fallback = Path(".") / fname
    if fallback.is_file():
        return str(fallback)
    return str(primary)


def _sleeve_total(args):
    """Resolve sleeve total: CLI arg > env var > derive from positions > default."""
    if args.sleeve_total:
        return args.sleeve_total
    env_val = os.environ.get("INVEST_SLEEVE_TOTAL")
    if env_val:
        return float(env_val)
    return DEFAULT_SLEEVE_TOTAL


# ============================================================================
# POSITIONS-CACHE STALENESS GUARD (v12.0 — ISSUE-05 Part 2)
# ============================================================================

POSITIONS_MAX_AGE_DAYS = 7  # CI §3: flag for re-upload if the snapshot is > ~7 days old.


def _positions_freshness(positions_data, today=None, max_age_days=POSITIONS_MAX_AGE_DAYS):
    """Classify the positions cache's freshness from its snapshot_date.

    Returns (status, age_days, message); status is 'fresh' | 'stale' | 'unknown'.
    This is the Watchdog backstop for ISSUE-05: a silently old positions.json must
    surface loudly (re-upload + re-ingest) instead of feeding the calibrator
    unnoticed — exactly the failure that produced the false conviction CRIT on 6/1.
    Mirrors CI §3's ~7-day re-upload rule.
    """
    today = today or date.today()
    sd = positions_data.get("snapshot_date") if isinstance(positions_data, dict) else None
    if not sd:
        return ("unknown", None,
                "positions cache has no snapshot_date — cannot confirm it matches the live "
                "book; re-run the ingest (build_positions_cache) to stamp it.")
    try:
        snap = datetime.strptime(str(sd)[:10], "%Y-%m-%d").date()
    except ValueError:
        return ("unknown", None,
                f"positions snapshot_date is unparseable ({sd!r}); re-run the ingest.")
    age = (today - snap).days
    if age < 0:
        return ("unknown", age,
                f"positions snapshot_date {snap} is in the future — check the clock or the ingest.")
    if age > max_age_days:
        return ("stale", age,
                f"positions cache is {age} days old (snapshot {snap}, limit {max_age_days}d) — "
                "re-upload broker PDFs and re-run the ingest; conviction/sizing may be off the live book.")
    return ("fresh", age, f"positions cache is {age}d old (snapshot {snap}).")


def _calibration_chain_banner(source_calls_data, inbox_call_dates, log_call_dates, today=None):
    """Surface source-calibration chain staleness at session-open (Issue #10 §3 wiring).

    The chain live Inbox -> Source Call Log -> source_calls.json cache is only as fresh
    as its stalest hop (the 2026-05-28 failure: Inbox->Log read clean while hit-rates were
    9d stale). The gauge functions already exist in source_call_tracker (v11.35/11.36);
    this wires them into the pre-flight so a silently-stale calibration becomes LOUD.

    cache_call_dates is read offline from source_calls.json. The LIVE side (inbox/log
    dates) is Notion-only and supplied by the routine; when it is absent we report
    'not checked / PROVISIONAL' rather than implying the chain is clean (Dark-Lane-Honesty).
    Returns a banner string ('' only when the chain is CONFIRMED fresh).
    """
    import source_call_tracker as sct
    calls = source_calls_data if isinstance(source_calls_data, list) else []
    cache_dates = [c["date"] for c in calls if isinstance(c, dict) and c.get("date")]
    newest_cache = max(cache_dates) if cache_dates else None
    bar = "=" * 66

    if not inbox_call_dates and not log_call_dates:
        return "\n".join(["", bar,
            "⚠️  SOURCE CALIB CHAIN NOT CHECKED — live Inbox/Log not supplied this run; "
            f"cache as-of {newest_cache or 'unknown'}. Treat calibration as PROVISIONAL "
            "until the routine passes Inbox/Log dates.", bar, ""])

    chain = sct.calibration_chain_staleness(
        inbox_call_dates or [], log_call_dates or [], cache_dates, now=today)
    if not chain.get("stale"):
        return ""
    return "\n".join(["", bar,
        f"⚠️  SOURCE CALIB CHAIN STALE ({chain['worst_days_behind']}d behind) — PROVISIONAL",
        sct.chain_staleness_surface(chain), bar, ""])


# ============================================================================
# MAIN
# ============================================================================

def main():
    p = argparse.ArgumentParser(
        description="v11.26 daily pre-flight wrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--inputs-dir", default=_default_inputs_dir(),
                   help="Directory for default input files "
                        "(default: ./sample_inputs/ if it exists, else cwd)")
    p.add_argument("--positions", help="Override positions JSON path")
    p.add_argument("--theses", help="Override theses JSON path")
    p.add_argument("--macro", help="Override macro state JSON path")
    p.add_argument("--source-rates", help="Override source rates JSON path")
    p.add_argument("--insider-data", help="Override insider data JSON path")
    p.add_argument("--refresh-insider-data", action="store_true",
                   help="Refresh insider_data.json from UW before running preflight.")
    p.add_argument("--insider-days-back", type=int, default=120,
                   help="Lookback window for --refresh-insider-data.")
    p.add_argument("--catalysts", help="Override catalysts JSON path")
    p.add_argument("--source-calls", help="Override pending source calls JSON path")
    p.add_argument("--rationales", help="Override rationales JSON path")
    p.add_argument("--prior", help="Override prior snapshot JSON path")
    p.add_argument("--parabolic", help="Override parabolic setups JSON path")
    p.add_argument("--sleeve-total", type=float, help="Sleeve total $ (default: derived)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--verbose", action="store_true", help="Print loaded paths")
    args = p.parse_args()

    # Import the orchestrator (works from outputs/, build/, or project/)
    script_dir = Path(__file__).parent.resolve()
    # v12.0 ISSUE-10 fix: prefer the script's OWN directory for imports, with
    # /home/claude/build and /mnt/project as lower-priority fallbacks. The old
    # order pinned imports to /mnt/project, shadowing local/staged code.
    sys.path.insert(0, "/mnt/project")
    sys.path.insert(0, "/home/claude/build")
    sys.path.insert(0, str(script_dir))

    try:
        import session_orchestrator as so
    except ImportError as e:
        print(f"FATAL: cannot import session_orchestrator — {e}")
        print("Place session_orchestrator.py + dependencies in same dir as this script.")
        sys.exit(2)

    # Resolve all paths
    paths = {k: _resolve(k, args, args.inputs_dir) for k in DEFAULT_FILES}

    if args.verbose:
        print("INPUT PATHS:")
        for k, v in paths.items():
            exists = "✓" if Path(v).is_file() else "✗"
            print(f"  {exists} {k:14} → {v}")
        print()

    # Load inputs (all optional except positions + theses)
    positions_data = _load(paths["positions"], optional=False)
    theses_data    = _load(paths["theses"], optional=False)

    # positions.json may have {snapshot_date, positions} wrapper or be a bare list
    if isinstance(positions_data, dict) and "positions" in positions_data:
        positions = positions_data["positions"]
        sleeve_from_file = positions_data.get("sleeve_value")
    else:
        positions = positions_data
        sleeve_from_file = None

    # v12.0 ISSUE-05 Part 2: positions-cache staleness guard. A silently old cache
    # is what produced the false conviction CRIT on 6/1 — surface it loudly here.
    _pf_status, _pf_age, _pf_msg = _positions_freshness(positions_data)
    if _pf_status != "fresh":
        _banner = "\n".join(["", "=" * 66,
                             f"⚠️  POSITIONS CACHE {_pf_status.upper()} — {_pf_msg}",
                             "=" * 66, ""])
        print(_banner, file=(sys.stderr if args.json else sys.stdout))

    macro_data        = _load(paths["macro"])
    source_rates_data = _load(paths["source_rates"])
    if args.refresh_insider_data:
        try:
            import insider_cache_refresh as icr
            _summary = icr.refresh_from_paths(
                positions_path=paths["positions"],
                tickers_csv=None,
                out_path=paths["insider_data"],
                summary_path=str(Path(paths["insider_data"]).with_name("insider_cache_summary.json")),
                days_back=args.insider_days_back,
            )
            _line = (
                f"INSIDER CACHE REFRESH: {_summary.get('status')} | "
                f"tickers={_summary.get('ticker_count')} | "
                f"transactions={_summary.get('transaction_count')}"
            )
            if _summary.get("reason"):
                _line += f" | {_summary.get('reason')}"
            print(_line, file=(sys.stderr if args.json else sys.stdout))
        except Exception as exc:
            _fallback = {
                "_meta": {
                    "status": "not_checked",
                    "source": "unusual_whales.insider_transactions",
                    "checked_at": date.today().isoformat(),
                    "reason": f"preflight refresh failed: {type(exc).__name__}: {exc}",
                }
            }
            Path(paths["insider_data"]).parent.mkdir(parents=True, exist_ok=True)
            with open(paths["insider_data"], "w") as f:
                json.dump(_fallback, f, indent=2)
                f.write("\n")
    insider_data_full = _load(paths["insider_data"])
    catalysts_data    = _load(paths["catalysts"])
    source_calls_data = _load(paths["source_calls"])
    rationales_data   = _load(paths["rationales"])
    prior_data        = _load(paths["prior"])
    parabolic_data    = _load(paths["parabolic"])
    position_reconciliation_data = _load(paths["position_reconciliation"])

    # v12.5 Issue #10 §3: source-calibration chain staleness at boot. The gauges exist in
    # source_call_tracker (v11.35/11.36) but were unwired; surface them, or say "not checked"
    # when the live Inbox/Log dates aren't supplied. One small hardened read — never breaks boot.
    _inbox_dates = None
    _log_dates = None
    try:
        _inbox_dates = _load(paths["inbox_dates"]) if paths.get("inbox_dates") else None
        _log_dates   = _load(paths["log_dates"]) if paths.get("log_dates") else None
        _cc_banner = _calibration_chain_banner(source_calls_data, _inbox_dates, _log_dates)
    except Exception:
        _cc_banner = ""
    if _cc_banner:
        print(_cc_banner, file=(sys.stderr if args.json else sys.stdout))

    # Resolve sleeve total
    sleeve_total = _sleeve_total(args) if args.sleeve_total or os.environ.get("INVEST_SLEEVE_TOTAL") \
                   else (sleeve_from_file or DEFAULT_SLEEVE_TOTAL)

    # Run orchestrator
    dashboard = so.orchestrate(
        positions=positions,
        theses=theses_data,
        sleeve_total=sleeve_total,
        prior_snapshot=prior_data,
        rationales=rationales_data,
        macro_pulse=macro_data,
        source_rates=source_rates_data,
        insider_data=insider_data_full,
        catalysts=catalysts_data,
        source_calls=source_calls_data,
        parabolic_data=parabolic_data,
        position_reconciliation=position_reconciliation_data,
        inbox_call_dates=_inbox_dates,
        log_call_dates=_log_dates,
    )

    if args.json:
        print(so.format_json(dashboard))
    else:
        print(so.format_text(dashboard))


if __name__ == "__main__":
    main()
