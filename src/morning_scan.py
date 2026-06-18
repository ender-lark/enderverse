"""Morning Scan routine (Task 8 / C-final).

The 8:35 AM ET cloud routine ("investing-os-morning-scan" in
:mod:`cloud_ops_status`). This is the consumer wrapper around
:func:`pattern_engine.detect_patterns` — it gathers state from the V2 caches
that already exist on disk (top_prospects, source_calls, parabolic_setups,
etc.) and runs the V3 detectors, producing a single payload the L5 wrapper
can persist as a receipt and the cockpit can fold into the TODAY—DECIDE
surface.

Pure: state is supplied by the caller. Disk reads happen ONLY when the
caller does not pass a particular cache (and even then only against the
project's repo-convention paths). The default :func:`run_morning_scan`
returns a JSON-serialisable dict so receipts can record it without further
massage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fs_ingest_guard
import pattern_engine as pe
from tunables import load_conviction_weights, load_goal_tunables

SRC = Path(__file__).resolve().parent
TOP_PROSPECTS_PATH = SRC / "top_prospects.json"
SOURCE_CALLS_PATH = SRC / "source_calls.json"
PARABOLIC_PATH = SRC.parent / "parabolic_setups.json"
FUNDSTRAT_BIBLE_PATH = SRC / "fundstrat_bible.json"
FS_INGEST_INVENTORY_PATH = SRC / "fs_ingest_inventory.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def load_parabolic_tickers(path: Path | str = PARABOLIC_PATH) -> list[str]:
    """Extract the tickers flagged as parabolic from ``parabolic_setups.json``.

    Honest-empty when the file is absent or unreadable.
    """
    payload = _read_json(Path(path), default={})
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase") or "").lower()
        # Only the operator-canonical "Phase 3 (parabola)" phase means
        # "extended -- don't chase." A SKIP surface_tier is NOT a chase signal:
        # it merely means the name did not qualify as a momentum setup, which
        # INCLUDES beaten-down discount names (e.g. VRT, a -21% pullback, scored
        # SKIP; so did LEU and MP). Dampening on SKIP wrongly capped vetted
        # discount BUYs to STAGE-ONLY -- the buy-side surfacing miss
        # (docs/codex_tasks/vrt_miss_rootcause_2026_06_18.md, Rail E). Key the
        # chase-dampener on the parabola phase only, matching
        # full_build_runner.active_parabolic_tickers (which already excludes SKIP).
        if "parabola" in phase:
            ticker = str(row.get("ticker") or "").upper()
            if ticker:
                out.append(ticker)
    return out


def run_morning_scan(
    *,
    prospects: dict[str, Any] | None = None,
    source_calls: list[dict[str, Any]] | None = None,
    current_prices: dict[str, float] | None = None,
    source_conflicts: set[str] | None = None,
    weights: dict[str, Any] | None = None,
    goal: dict[str, Any] | None = None,
    held_options: list[dict[str, Any]] | None = None,
    drift_rows: list[dict[str, Any]] | None = None,
    sleeve_states: dict[str, str] | None = None,
    smid_top5: list[str] | None = None,
    parabolic_tickers: list[str] | None = None,
    factor_exposures: dict[str, float] | None = None,
    fundstrat_bible: dict[str, Any] | None = None,
    fs_ingest_inventory: dict[str, Any] | None = None,
    as_of: str | None = None,
    top_prospects_path: Path | str = TOP_PROSPECTS_PATH,
    source_calls_path: Path | str = SOURCE_CALLS_PATH,
    parabolic_path: Path | str = PARABOLIC_PATH,
    fundstrat_bible_path: Path | str = FUNDSTRAT_BIBLE_PATH,
    fs_ingest_inventory_path: Path | str = FS_INGEST_INVENTORY_PATH,
) -> dict[str, Any]:
    """Run all pattern_engine detectors + the two guards. Returns a
    routine-receipt-shaped payload.

    Absent caches are honest-empty. The caller may inject any subset of
    state; everything else falls back to the repo-convention path (or
    honest-empty when the file is missing).
    """
    as_of = as_of or _now_iso()
    weights = weights or load_conviction_weights()
    goal = goal or load_goal_tunables()
    prospects = prospects if prospects is not None else _read_json(Path(top_prospects_path), {})
    source_calls = source_calls if source_calls is not None else _read_json(
        Path(source_calls_path), [])
    if parabolic_tickers is None:
        parabolic_tickers = load_parabolic_tickers(parabolic_path)
    fundstrat_bible = fundstrat_bible if fundstrat_bible is not None else _read_json(
        Path(fundstrat_bible_path), {})
    fs_ingest_inventory = (
        fs_ingest_inventory
        if fs_ingest_inventory is not None
        else _read_json(Path(fs_ingest_inventory_path), {})
    )

    patterns = pe.detect_patterns(
        prospects=prospects, source_calls=source_calls,
        current_prices=current_prices, source_conflicts=source_conflicts,
        weights=weights, goal=goal,
        held_options=held_options, drift_rows=drift_rows,
        sleeve_states=sleeve_states, smid_top5=smid_top5,
        today=as_of[:10],
    )

    # Flatten cards so the parabolic-chase dampener + factor-overlap caveat
    # can act on every emitted card in one pass.
    all_cards: list[dict[str, Any]] = []
    for lane_cards in patterns["cards"].values():
        all_cards.extend(lane_cards)
    if parabolic_tickers:
        pe.apply_parabolic_chase_dampener(all_cards, parabolic_tickers,
                                          weights=weights)
    if factor_exposures:
        pe.apply_factor_overlap_caveat(all_cards, factor_exposures,
                                       weights=weights)

    summary = {
        lane: len(cards) for lane, cards in patterns["cards"].items()
    }
    fs_findings = fs_ingest_guard.findings_for_bible(fs_ingest_inventory, fundstrat_bible)

    return {
        "as_of": as_of,
        "summary": summary,
        "patterns": patterns,
        "warnings": fs_findings,
        "guards_applied": {
            "parabolic_chase_dampener": sorted(set(parabolic_tickers or [])),
            "factor_overlap_caveat": sorted((factor_exposures or {}).keys()),
        },
        "honesty": {
            "weights_source": "conviction_weights.json",
            "goal_source": "goal_tunables.json",
            "parabolic_cache": (str(Path(parabolic_path)) if parabolic_tickers
                                else "not_checked — parabolic cache empty/absent"),
            "factor_exposure_supplied": bool(factor_exposures),
            "fs_ingest_guard": (
                f"{len(fs_findings)} warning(s)" if fs_findings else "checked - no active-layer ingest gaps"
            ),
        },
    }
