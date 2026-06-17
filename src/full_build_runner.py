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
from zoneinfo import ZoneInfo

from collection import collect
from collection_gate import validate_collection_gate
from feed_assembler import assemble_feed
import fs_ingest_guard
import integration_debt_sweep
from fundstrat_bible import build_fundstrat_bible_source
from fundstrat_daily import build_fundstrat_daily_source
from fundstrat_news import build_fundstrat_news, build_if_i_were_you
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
from decision_support import enrich_actions, build_asymmetric_opportunities
from decision_dossier_coverage import build_decision_dossier_coverage
from operator_hardening import build_operator_hardening
from uw_routing_recommendations import build_uw_routing_recommendations
from uw_action_runbook import build_uw_action_runbook
from uw_endpoint_result_proof import build_uw_endpoint_result_proof, load_uw_endpoint_results
from reallocation_brief import build_reallocation_brief
from account_trade_placement import annotate_actions, annotate_reallocation_brief
from social_watch import build_social_watch
from market_open_packet import build_market_open_packet
from alert_policy import build_alert_policy
import cloud_routine_receipts
import execution_plan as ep
import today_decide
from tunables import load_conviction_weights, load_goal_tunables


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
    "social_watch": ("social_watch.json", "reddit_watch.json", "reddit_signals.json"),
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

SOURCE_GAP_LABELS = {
    "account_positions": "Account Positions",
    "meridian": "Meridian",
    "heartbeat": "Routine Heartbeat",
    "open_opportunities": "Action Memory",
    "inbox_call_dates": "Inbox Call Dates",
    "log_call_dates": "Log Call Dates",
}


def _lane_counts(rows: list[dict]) -> dict[str, int]:
    counts = {
        "failed": 0,
        "not_checked": 0,
        "has_data": 0,
        "stale": 0,
        "checked_clear": 0,
    }
    for row in rows:
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _source_gap_row(input_row: dict) -> dict:
    key = str(input_row.get("key") or "")
    label = SOURCE_GAP_LABELS.get(key) or key.replace("_", " ").title()
    candidates = [
        str(path)
        for path in input_row.get("candidate_paths") or []
        if path
    ]
    expected = candidates[0] if candidates else ""
    next_step = (
        f"Supply {expected} through the owning source routine or manual live-source drop."
        if expected
        else "Supply the owning live source before treating this input as checked."
    )
    missing_impact = (
        str(input_row.get("missing_behavior") or "")
        or "This live-capable source input is not checked; absence is not a clear read."
    )
    return {
        "key": key,
        "label": label,
        "status": "not_checked",
        "detail": "missing live source input",
        "count": 0,
        "checked_at": "",
        "next_step": next_step,
        "missing_impact": missing_impact,
    }


def _append_missing_source_gap_rows(feed: dict, input_rows: list[dict]) -> None:
    """Expose missing live-source convention inputs as dark lane-status rows."""
    lane_status = feed.setdefault("lane_status", {})
    rows = lane_status.setdefault("rows", [])
    if not isinstance(rows, list):
        return
    existing = {
        str(row.get("key") or "")
        for row in rows
        if isinstance(row, dict)
    }
    for input_row in input_rows:
        key = str(input_row.get("key") or "")
        if not key or key in existing:
            continue
        if input_row.get("status") != "missing_optional":
            continue
        source_text = (
            str(input_row.get("source") or "")
            + " "
            + str(input_row.get("missing_behavior") or "")
        ).lower()
        if "archived" in source_text or "archive" in source_text:
            continue
        if not input_row.get("missing_behavior"):
            continue
        rows.append(_source_gap_row(input_row))
        existing.add(key)

    counts = _lane_counts([row for row in rows if isinstance(row, dict)])
    lane_status["counts"] = counts
    lane_status["has_dark_lanes"] = counts.get("not_checked", 0) > 0
    lane_status["has_stale_or_failed"] = (
        counts.get("stale", 0) + counts.get("failed", 0)
    ) > 0


def _src_dir() -> Path:
    return Path(__file__).resolve().parent


def _manifest_path() -> Path:
    return _src_dir() / "codex_routine_manifest.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ET = ZoneInfo("America/New_York")


def _et_day(value: str | None = None) -> str:
    if value:
        text = str(value).strip()
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ET)
            return parsed.astimezone(ET).date().isoformat()
        except ValueError:
            try:
                return date.fromisoformat(text[:10]).isoformat()
            except ValueError:
                pass
    return datetime.now(ET).date().isoformat()


def _et_timestamp(value: str | None = None) -> str:
    text = str(value or "").strip()
    if text:
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ET)
            return parsed.astimezone(ET).isoformat()
        except ValueError:
            pass
    return datetime.now(ET).isoformat()


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


def _fundstrat_daily_checked(src_dir: Path, calls: Any) -> bool:
    if calls:
        return True
    summary = _read_json(src_dir / "fundstrat_intake_summary.json", default={})
    if not isinstance(summary, dict):
        return False
    return int(summary.get("full_body_entries") or 0) > 0


def _build_fundstrat_audit(src_dir: Path) -> dict[str, Any]:
    summary = _read_json(src_dir / "fundstrat_intake_summary.json", default={})
    inbox_entries = _read_json(src_dir / "fundstrat_inbox_entries.json", default=[])
    daily_calls_cache = _read_json(src_dir / "fundstrat_daily_calls.json", default=[])
    inbox_entries = inbox_entries if isinstance(inbox_entries, list) else []
    daily_calls_cache = daily_calls_cache if isinstance(daily_calls_cache, list) else []
    stored_full_body = sum(
        1
        for row in inbox_entries
        if isinstance(row, dict) and bool(row.get("body_fetched"))
    )
    stored_snippet = sum(
        1
        for row in inbox_entries
        if isinstance(row, dict) and not bool(row.get("body_fetched"))
    )
    if not isinstance(summary, dict) or not summary:
        if inbox_entries or daily_calls_cache:
            return {
                "status": "has_data",
                "line": (
                    f"Fundstrat stored cache: {len(inbox_entries)} inbox entries "
                    f"({stored_full_body} full-body, {stored_snippet} snippet-only), "
                    f"{len(daily_calls_cache)} daily calls; latest intake summary is missing."
                ),
                "entries": 0,
                "full_body_entries": 0,
                "snippet_only_entries": 0,
                "daily_calls": 0,
                "stored_entries": len(inbox_entries),
                "stored_full_body_entries": stored_full_body,
                "stored_snippet_only_entries": stored_snippet,
                "stored_daily_calls": len(daily_calls_cache),
                "rows": [],
                "snippet_rule": "Snippet-only Gmail results are discovery only; they do not make a lane checked clear.",
            }
        return {
            "status": "not_checked",
            "line": "Fundstrat intake summary is not present.",
            "rows": [],
        }
    entries = int(summary.get("entries") or 0)
    full_body = int(summary.get("full_body_entries") or 0)
    snippets = int(summary.get("snippet_only_entries") or 0)
    daily_calls = int(summary.get("daily_calls") or 0)
    candidates = int(summary.get("source_call_candidates") or 0)
    stored_candidates = int(summary.get("stored_source_call_candidates") or 0)
    line = (
        f"Fundstrat latest intake: {full_body} full-body, {snippets} snippet-only, "
        f"{daily_calls} daily calls; stored cache: {len(inbox_entries)} inbox entries "
        f"({stored_full_body} full-body, {stored_snippet} snippet-only), "
        f"{len(daily_calls_cache)} daily calls, {stored_candidates} stored source-call candidates."
    )
    return {
        "status": "has_data" if entries or full_body or snippets else "checked_clear",
        "line": line,
        "entries": entries,
        "full_body_entries": full_body,
        "snippet_only_entries": snippets,
        "daily_calls": daily_calls,
        "source_call_candidates": candidates,
        "stored_entries": int(summary.get("stored_entries") or 0),
        "stored_cache_entries": len(inbox_entries),
        "stored_full_body_entries": stored_full_body,
        "stored_snippet_only_entries": stored_snippet,
        "stored_daily_calls": int(summary.get("stored_daily_calls") or 0),
        "stored_daily_call_rows": len(daily_calls_cache),
        "stored_source_call_candidates": stored_candidates,
        "bodies_redacted": bool(summary.get("bodies_redacted")),
        "snippet_rule": "Snippet-only Gmail results are discovery only; they do not make a lane checked clear.",
    }


def _build_cloud_routine_audit(src_dir: Path, *, now: str | datetime | None = None) -> dict[str, Any]:
    proof = _read_json(src_dir / "cloud_automation_status.json", default={})
    expected = proof.get("routines") if isinstance(proof, dict) else []
    expected = [row for row in expected or [] if isinstance(row, dict)]
    expected = [cloud_routine_receipts.with_proof_scope(row) for row in expected]
    core_expected = cloud_routine_receipts.proof_required_automations(expected)
    support_expected = cloud_routine_receipts.support_automations(expected)
    receipts = cloud_routine_receipts.load_receipts(src_dir / "cloud_routine_receipts.json")
    summary = cloud_routine_receipts.summarize_receipts(
        receipts,
        expected_automations=core_expected,
    )
    support_summary = cloud_routine_receipts.summarize_receipts(
        receipts,
        expected_automations=support_expected,
    )
    due = cloud_routine_receipts.summarize_due_receipts(
        summary,
        core_expected,
        activated_at=proof.get("verified_at") if isinstance(proof, dict) else None,
        now=now,
    )
    support_due = cloud_routine_receipts.summarize_due_receipts(
        support_summary,
        support_expected,
        activated_at=proof.get("verified_at") if isinstance(proof, dict) else None,
        now=now,
    )
    expected_count = int(summary.get("expected_count") or 0)
    scheduled = int(summary.get("scheduled_success_count") or 0)
    manual_support_only_count = int(summary.get("manual_support_only_count") or 0)
    failed = int(summary.get("failed_latest_count") or 0)
    overdue_count = int(due.get("overdue_count") or 0)
    missing_rows = [
        {
            "routine_id": row.get("routine_id") or "",
            "routine_name": row.get("routine_name") or row.get("routine_id") or "",
            "schedule": row.get("schedule") or "",
            "last_status": row.get("last_status") or "",
            "last_scheduled_success_at": row.get("last_scheduled_success_at") or "",
            "last_manual_success_at": row.get("last_manual_success_at") or "",
            "manual_support_only": bool(row.get("manual_support_only")),
        }
        for row in (summary.get("missing_scheduled_success") or [])
        if isinstance(row, dict)
    ]
    status = (
        "overdue"
        if overdue_count
        else "live_run_proven"
        if expected_count and scheduled >= expected_count and not failed
        else "partial_live_run_proven"
        if scheduled and not failed
        else "not_proven"
    )
    due_text = f"; overdue={overdue_count}" if overdue_count else ""
    manual_text = f"; manual support only={manual_support_only_count}" if manual_support_only_count else ""
    support_overdue = int(support_due.get("overdue_count") or 0)
    support_text = (
        f"; support monitored={int(support_summary.get('expected_count') or 0)}"
        f", support overdue={support_overdue}"
    )
    return {
        "status": status,
        "line": (
            f"Core background cloud proof: {scheduled}/{expected_count} scheduled receipts proven"
            f"{manual_text}; failed latest={failed}{due_text}{support_text}."
        ),
        "scheduled_success_count": scheduled,
        "expected_count": expected_count,
        "core_expected_count": expected_count,
        "support_expected_count": int(support_summary.get("expected_count") or 0),
        "support_scheduled_success_count": int(support_summary.get("scheduled_success_count") or 0),
        "support_manual_support_only_count": int(support_summary.get("manual_support_only_count") or 0),
        "support_overdue_count": support_overdue,
        "manual_support_only_count": manual_support_only_count,
        "failed_latest_count": failed,
        "overdue_count": overdue_count,
        "due_waiting_count": int(due.get("due_waiting_count") or 0),
        "routine_receipt_due": due,
        "support_routine_receipt_due": support_due,
        "overdue": due.get("overdue") or [],
        "support_overdue": support_due.get("overdue") or [],
        "due_waiting": due.get("due_waiting") or [],
        "missing_scheduled_success_count": int(summary.get("missing_scheduled_success_count") or 0),
        "missing_scheduled_success": missing_rows,
        "manual_support_only": summary.get("manual_support_only") or [],
        "support_manual_support_only": support_summary.get("manual_support_only") or [],
        "rows": summary.get("rows") or [],
        "support_rows": support_summary.get("rows") or [],
    }


def _summary_row(src_dir: Path, filename: str, label: str) -> dict[str, Any]:
    payload = _read_json(src_dir / filename, default={})
    if not isinstance(payload, dict) or not payload:
        return {
            "key": filename,
            "label": label,
            "status": "not_checked",
            "line": f"{label} summary missing.",
        }
    written = bool(payload.get("written"))
    problems = payload.get("problems") or []
    count = (
        payload.get("rows")
        or payload.get("action_count")
        or payload.get("hanging_count")
        or payload.get("stored")
        or 0
    )
    status = "failed" if problems else "has_data" if written or count else "checked_clear"
    return {
        "key": filename,
        "label": label,
        "status": status,
        "written": written,
        "count": count,
        "line": f"{label}: {'written' if written else 'checked'}; count={count}.",
        "problems": problems,
    }


def _build_notion_writeback_audit(src_dir: Path) -> dict[str, Any]:
    rows = [
        _summary_row(src_dir, "signal_log_intake_summary.json", "Signal Log cache"),
        _summary_row(src_dir, "daily_synthesis_intake_summary.json", "Daily Synthesis cache"),
        _summary_row(src_dir, "catalyst_intake_summary.json", "Catalyst Calendar cache"),
    ]
    failed = [row for row in rows if row.get("status") == "failed"]
    written = [row for row in rows if row.get("written")]
    return {
        "status": "failed" if failed else "has_data" if written else "not_checked",
        "line": (
            f"Notion/writeback audit: {len(written)} repo cache write(s) proven; "
            "connector writes must be verified by routine receipts when used."
        ),
        "connector_write_proven": False,
        "repo_cache_writes": len(written),
        "rows": rows,
        "honesty_rule": "A repo cache write is not the same as a verified Notion connector write.",
    }


def _build_notion_collision_audit(src_dir: Path) -> dict[str, Any]:
    path = src_dir / "notion_collision_audit.json"
    if not path.is_file():
        return {
            "status": "not_checked",
            "line": (
                "Notion collision audit: not checked; if another agent wrote shared "
                "Notion pages, verify live page state before treating repo caches as current."
            ),
            "rows": [],
            "honesty_rule": "Repo cache recency does not prove live Notion page ownership.",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {
            "status": "failed",
            "line": f"Notion collision audit: failed to read {path.name}: {exc}",
            "rows": [],
        }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "line": f"Notion collision audit: {path.name} must be a JSON object.",
            "rows": [],
        }
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    return {
        "status": payload.get("status") or "has_data",
        "line": payload.get("line") or f"Notion collision audit: {len(rows)} monitored shared page(s).",
        "rows": rows,
        "honesty_rule": payload.get("honesty_rule")
            or "Live Notion verification wins over local cache assumptions.",
    }


def _build_connector_evidence(src_dir: Path, live_source_capability_module: Any) -> dict[str, Any]:
    report = live_source_capability_module.capability_report(src_dir)
    rows = [
        {
            "key": row.get("key") or "",
            "status": row.get("status") or "",
            "present": bool(row.get("present")),
            "primary_mode": row.get("primary_mode") or "",
            "modes": row.get("modes") or [],
            "source": row.get("source") or "",
            "missing_behavior": row.get("missing_behavior") or "",
        }
        for row in report.get("rows") or []
        if isinstance(row, dict)
    ]
    config = report.get("live_source_config") or {}
    return {
        "status": "has_data",
        "line": (
            f"Connector/supplied evidence: present={report.get('present_inputs')}/"
            f"{report.get('total_inputs')}; missing live-capable={report.get('missing_live_capable_count')}."
        ),
        "present_inputs": report.get("present_inputs") or 0,
        "total_inputs": report.get("total_inputs") or 0,
        "missing_live_capable_count": report.get("missing_live_capable_count") or 0,
        "missing_live_capable_keys": report.get("missing_live_capable_keys") or [],
        "live_source_config": {
            "configured_count": config.get("configured_count") or 0,
            "total_count": config.get("total_count") or 0,
            "stale_count": config.get("stale_count") or 0,
            "missing_count": config.get("missing_count") or 0,
        },
        "rows": rows,
    }


def _build_trigger_registry_audit(src_dir: Path) -> dict[str, Any]:
    registry = _read_json(src_dir / "trigger_registry.json", default=[])
    triggers = registry.get("triggers") if isinstance(registry, dict) else registry
    triggers = [row for row in triggers or [] if isinstance(row, dict)]
    armed = [
        row
        for row in triggers
        if str(row.get("status") or "armed").lower() in {"armed", "active"}
    ]
    summary = _read_json(src_dir / "trigger_check_summary.json", default={})
    if not isinstance(summary, dict) or not summary:
        return {
            "status": "not_checked" if triggers else "checked_clear",
            "line": (
                f"Trigger registry: {len(armed)} armed trigger(s); not checked this build."
                if triggers else "Trigger registry: no registered triggers."
            ),
            "armed_count": len(armed),
            "fired_count": 0,
            "not_checked_count": len(armed),
            "rows": armed,
            "honesty_rule": "Missing trigger-check proof is not a checked-clear trigger lane.",
        }
    fired = int(summary.get("fired_count") or 0)
    not_checked = int(summary.get("not_checked_count") or 0)
    status = "fired" if fired else "not_checked" if not_checked else "checked_clear"
    return {
        "status": status,
        "line": summary.get("line")
            or f"Trigger check: fired={fired}; not_checked={not_checked}; armed={len(armed)}.",
        "checked_at": summary.get("checked_at") or "",
        "armed_count": int(summary.get("armed_count") or len(armed)),
        "fired_count": fired,
        "not_checked_count": not_checked,
        "expired_count": int(summary.get("expired_count") or 0),
        "fired": summary.get("fired") or [],
        "not_checked": summary.get("not_checked") or [],
        "rows": triggers,
        "honesty_rule": "Unfetched trigger quotes remain not_checked; never infer all clear.",
    }


def _build_source_audits(
    src_dir: Path,
    live_source_capability_module: Any,
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    integration_debt = integration_debt_sweep.build_report(
        root_dir=src_dir.parent,
        src_dir=src_dir,
        generated_at=_utc_now_iso(),
    )
    return {
        "fundstrat": _build_fundstrat_audit(src_dir),
        "cloud_routines": _build_cloud_routine_audit(src_dir, now=now),
        "trigger_registry": _build_trigger_registry_audit(src_dir),
        "integration_debt": {
            "status": integration_debt.get("status") or "not_checked",
            "line": integration_debt.get("line") or "",
            "warning_count": int(integration_debt.get("warning_count") or 0),
            "finding_count": int(integration_debt.get("finding_count") or 0),
            "rows": integration_debt.get("findings") or [],
            "honesty_rule": "Missing Notion queue input stays not_checked; repo evidence does not prove live queue state.",
        },
        "notion_writeback": _build_notion_writeback_audit(src_dir),
        "notion_collision": _build_notion_collision_audit(src_dir),
        "connector_evidence": _build_connector_evidence(src_dir, live_source_capability_module),
    }


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


def material_tickers_from_state(positions_cache: dict[str, Any], theses: list[dict[str, Any]] | None) -> set[str]:
    tickers = {
        str(row.get("ticker") or "").strip().upper()
        for row in (positions_cache.get("positions") or [])
        if isinstance(row, dict) and row.get("ticker")
    }
    tickers |= {
        str(row.get("ticker") or "").strip().upper()
        for row in (theses or [])
        if isinstance(row, dict)
        and row.get("ticker")
        and str(row.get("stance") or "").upper() != "MONITOR"
        and str(row.get("tier") or "").upper() in {"T1", "T2", "T3"}
    }
    return {ticker for ticker in tickers if ticker}


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
    today = as_of or _et_day(now)
    live_source_stamp = _et_timestamp(now)

    positions_file = _resolve(src, "positions", positions_path)
    theses_file = _resolve(src, "theses", theses_path)
    positions_cache = _read_json(positions_file, required=True)
    account_positions = _load_optional(src, "account_positions")
    account_positions_file = _resolve(src, "account_positions")
    execution_accounts = (
        ep.load_accounts(account_positions_file)
        if account_positions_file is not None and account_positions_file.is_file()
        else None
    )
    theses = _read_json(theses_file, required=True)
    positions, positions_as_of = normalize_positions_cache(positions_cache)
    if not positions:
        raise FullBuildError("positions cache produced no portfolio rows")

    closes_cache = _load_optional(src, "uw_prices", uw_prices_path)
    closes = normalize_closes_cache(closes_cache)
    macro = _load_optional(src, "macro")
    fs_bible = _load_optional(src, "fs_bible")
    fs_ingest_inventory = _read_json(src / "fs_ingest_inventory.json", default={})
    fs_daily = _load_optional(src, "fs_daily")
    fs_intake_summary = _read_json(src / "fundstrat_intake_summary.json", default={})
    meridian = _load_optional(src, "meridian")
    heartbeat = _load_optional(src, "heartbeat")
    signal_log = _load_optional(src, "signal_log")
    social_watch_cache = _load_optional(src, "social_watch")
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
    social_watch = build_social_watch(
        social_watch_cache,
        material_tickers=material_tickers_from_state(positions_cache, theses),
    )

    catalysts = None
    if catalyst_rows is not None:
        catalysts = catalysts_from_calendar_rows(catalyst_rows, as_of=today)

    reg = SourceRegistry()
    reg.register(build_portfolio_source(positions, as_of=positions_as_of or now))
    if closes_cache is not None:
        reg.register(build_uw_price_source(closes, as_of=live_source_stamp))
    if macro is not None:
        reg.register(build_uw_macro_source(macro, as_of=live_source_stamp))
    if fs_bible is not None:
        reg.register(build_fundstrat_bible_source(fs_bible))
    if fs_daily is not None and _fundstrat_daily_checked(src, fs_daily):
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
        social_watch=(social_watch.get("rows") or []) if social_watch_cache is not None else None,
        event_risk=event_risk,
        synthesis=synthesis,
        research=research,
        catalysts=catalysts,
        uw_opportunity=uw_opportunity,
        open_opportunities=open_opportunities,
        opp_prices=latest_prices_from_closes(closes),
        top_prospects=top_prospects,
        source_calls=source_calls,
        source_call_observations=fs_daily,
        inbox_call_dates=inbox_call_dates,
        log_call_dates=log_call_dates,
        target_drift=target_drift,
    )
    feed["actions"] = annotate_actions(feed.get("actions") or [], account_positions)
    feed["research_actions"] = annotate_actions(feed.get("research_actions") or [], account_positions)
    feed["asymmetric_opportunities"] = build_asymmetric_opportunities(feed)
    feed["social_watch"] = social_watch
    portfolio_views = build_portfolio_views(account_positions, fundstrat_bible=fs_bible)
    if portfolio_views:
        feed["portfolio_views"] = portfolio_views
    _append_missing_source_gap_rows(feed, convention_input_status(src))
    import live_source_capability

    feed["live_source_config"] = live_source_capability.live_config_report()
    feed["source_audits"] = _build_source_audits(src, live_source_capability, now=now)
    fs_ingest_findings = fs_ingest_guard.findings_for_bible(fs_ingest_inventory, fs_bible)
    feed["fs_ingest_guard"] = {
        "active_layers": fs_ingest_guard.active_bible_layers(fs_bible),
        "findings": fs_ingest_findings,
        "status": "warn" if fs_ingest_findings else "ok",
    }
    feed["operator_hardening"] = build_operator_hardening(feed)
    feed["uw_routing"] = build_uw_routing_recommendations(feed)
    feed["uw_action_runbook"] = build_uw_action_runbook(feed)
    uw_result_payload, uw_result_path, uw_result_problems = load_uw_endpoint_results(src)
    feed["uw_endpoint_proof"] = build_uw_endpoint_result_proof(
        uw_result_payload,
        feed.get("uw_action_runbook") or {},
        generated_at=feed.get("generated_at") or now,
        result_path=uw_result_path,
        load_problems=uw_result_problems,
    )
    feed["uw_action_runbook"]["endpoint_proof"] = {
        "status": feed["uw_endpoint_proof"].get("status") or "",
        "line": feed["uw_endpoint_proof"].get("line") or "",
        "blockers": feed["uw_endpoint_proof"].get("blockers") or [],
        "newest_checked_at": feed["uw_endpoint_proof"].get("newest_checked_at") or "",
    }
    feed["actions"], feed["action_decision_groups"] = enrich_actions(
        feed.get("actions") or [],
        staleness=feed.get("staleness") or {},
        synthesis=feed.get("synthesis") or {},
        event_risk=feed.get("event_risk") or [],
        uw_endpoint_proof=feed.get("uw_endpoint_proof") or {},
        generated_at=feed.get("generated_at") or now,
    )
    feed["asymmetric_opportunities"] = build_asymmetric_opportunities(feed)
    feed["operator_hardening"] = build_operator_hardening(feed)
    feed["fundstrat_news"] = build_fundstrat_news(
        fundstrat_bible=fs_bible,
        fundstrat_daily_calls=fs_daily,
        top_prospects=top_prospects,
        intake_summary=fs_intake_summary if isinstance(fs_intake_summary, dict) else {},
        ingest_findings=fs_ingest_findings,
        as_of=today,
    )
    feed["reallocation_brief"] = annotate_reallocation_brief(
        build_reallocation_brief(feed, positions_cache, as_of=today),
        account_positions,
    )
    feed["market_open_packet"] = build_market_open_packet(feed)
    feed["if_i_were_you"] = build_if_i_were_you(feed)
    feed["today_decide"] = today_decide.build_today_decide_payload(
        feed=feed,
        weights=load_conviction_weights(),
        goal=load_goal_tunables(),
        accounts=execution_accounts,
        today=today,
    )
    feed["source_audits"]["decision_dossier_coverage"] = build_decision_dossier_coverage(
        feed,
        dossier_path=src / "decision_dossiers.json",
        today=today,
    )
    feed["alert_policy"] = build_alert_policy(feed)
    feed["source_audits"]["uw_routing"] = feed.get("uw_routing") or {}
    feed["source_audits"]["uw_action_runbook"] = feed.get("uw_action_runbook") or {}
    feed["source_audits"]["uw_endpoint_proof"] = feed.get("uw_endpoint_proof") or {}
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
