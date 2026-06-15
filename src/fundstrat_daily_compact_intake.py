#!/usr/bin/env python3
"""Write compact, full-body-derived Fundstrat daily calls without raw bodies."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fs_ingest_guard
from fundstrat_lanes import classify_fundstrat_lane, classify_fundstrat_publication


DEFAULT_OUT_DIR = Path(__file__).resolve().parent
MAX_QUOTE_CHARS = 320
VALID_DIRECTIONS = {"buy", "add", "accumulate", "hold", "watch", "sell", "trim", "reduce", "avoid"}
PROMOTING_DIRECTIONS = {"buy", "add", "accumulate", "sell", "trim", "reduce", "avoid"}
ACTION_RELEVANCE_TERMS = {
    "breakout",
    "breakdown",
    "break above",
    "break below",
    "support",
    "resistance",
    "entry",
    "stop",
    "target",
    "tgt",
    "objective",
    "upside",
    "downside",
    "risk/reward",
    "taking profits",
    "take profits",
    "rebalance",
    "rotation",
    "rotate",
    "hedge",
    "trim",
    "avoid",
    "add",
    "accumulate",
    "buy",
    "sell",
    "reduce",
    "near-term",
    "short-term",
    "today",
    "intraday",
}
LOW_VALUE_TERMS = {
    "webinar",
    "podcast",
    "replay",
    "survey",
    "registration",
    "register",
    "event invite",
    "join us",
    "subscribe",
    "sponsored",
    "promotion",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.is_file():
        return default
    with path.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fs_daily_compact.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _rows_from_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("calls", "daily_calls", "rows", "items", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
        return [payload]
    return []


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def is_low_value_compact_call(row: dict) -> bool:
    """Return true when a compact Fundstrat row is context, not a useful call."""
    quote = " ".join(_text(row.get("quote") or row.get("summary") or row.get("call")).split())
    subject = _text(row.get("subject") or row.get("source_title"))
    direction = _text(row.get("direction") or row.get("bias")).lower()
    combined = f"{subject} {quote}".lower()
    if any(term in combined for term in LOW_VALUE_TERMS):
        publication = classify_fundstrat_publication(
            author=_text(row.get("author") or row.get("analyst") or "Fundstrat"),
            text=quote,
            ticker=_text(row.get("ticker") or row.get("symbol")).upper(),
            subject=subject,
            direction=direction,
            entry=_num(row.get("entry")),
            stop=_num(row.get("stop")),
            target=_num(row.get("target")),
            window=_text(row.get("window") or row.get("horizon")) or None,
        )
        return publication.get("capture_policy") != "daily_call"
    publication = classify_fundstrat_publication(
        author=_text(row.get("author") or row.get("analyst") or "Fundstrat"),
        text=quote,
        ticker=_text(row.get("ticker") or row.get("symbol")).upper(),
        subject=subject,
        direction=direction,
        entry=_num(row.get("entry")),
        stop=_num(row.get("stop")),
        target=_num(row.get("target")),
        window=_text(row.get("window") or row.get("horizon")) or None,
    )
    capture_policy = publication.get("capture_policy")
    if capture_policy in {"suppress", "audit_only", "monthly_baseline"}:
        return True
    if capture_policy == "daily_call":
        return False
    if direction in PROMOTING_DIRECTIONS:
        return False
    return not any(term in combined for term in ACTION_RELEVANCE_TERMS)


def normalize_compact_call(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    if is_low_value_compact_call(row):
        return None
    ticker = _text(row.get("ticker") or row.get("symbol")).upper()
    if not ticker:
        return None
    quote = " ".join(_text(row.get("quote") or row.get("summary") or row.get("call")).split())
    if not quote:
        return None
    direction = _text(row.get("direction") or row.get("bias")).lower() or None
    if direction and direction not in VALID_DIRECTIONS:
        direction = "watch"
    publication = classify_fundstrat_publication(
        author=_text(row.get("author") or row.get("analyst") or "Fundstrat"),
        text=quote,
        ticker=ticker,
        subject=_text(row.get("subject") or row.get("source_title") or "Fundstrat compact daily call"),
        direction=direction,
        entry=_num(row.get("entry")),
        stop=_num(row.get("stop")),
        target=_num(row.get("target")),
        window=_text(row.get("window") or row.get("horizon")) or None,
    )
    out = {
        "author": _text(row.get("author") or row.get("analyst") or "Fundstrat"),
        "ticker": ticker,
        "direction": direction,
        "entry": _num(row.get("entry")),
        "stop": _num(row.get("stop")),
        "target": _num(row.get("target")),
        "window": _text(row.get("window") or row.get("horizon")) or None,
        "quote": quote,
        "date": _text(row.get("date") or row.get("published_at"))[:10],
        "subject": _text(row.get("subject") or row.get("source_title") or "Fundstrat compact daily call"),
        "source_message_id": _text(row.get("source_message_id") or row.get("message_id") or row.get("id")),
        "source": _text(row.get("source") or "Fundstrat compact daily intake"),
        "publication_type": publication.get("publication_type") or "",
        "capture_policy": publication.get("capture_policy") or "",
        "use_case": publication.get("use_case") or "",
        "decision_usefulness": publication.get("decision_usefulness") or "",
        "capture_reason": publication.get("capture_reason") or "",
    }
    if isinstance(row.get("evidence_detail"), dict):
        out["evidence_detail"] = row["evidence_detail"]
    return out


def normalize_compact_calls(payload: Any) -> list[dict]:
    out = [
        normalized
        for normalized in (normalize_compact_call(row) for row in _rows_from_payload(payload))
        if normalized
    ]
    out.sort(key=lambda r: (r.get("date") or "", r.get("author") or "", r.get("ticker") or "", r.get("quote") or ""))
    return out


def validate_compact_calls(calls: Any) -> list[str]:
    if not isinstance(calls, list):
        return ["compact calls must be a list"]
    problems: list[str] = []
    for idx, row in enumerate(calls):
        if not isinstance(row, dict):
            problems.append(f"calls[{idx}] must be a dict")
            continue
        for field in ("author", "ticker", "quote", "date", "source"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                problems.append(f"calls[{idx}].{field} must be a non-empty string")
        if len(str(row.get("quote") or "")) > MAX_QUOTE_CHARS:
            problems.append(f"calls[{idx}].quote must be <= {MAX_QUOTE_CHARS} chars")
        if row.get("direction") not in (None, *sorted(VALID_DIRECTIONS)):
            problems.append(f"calls[{idx}].direction must be compact/known")
    return problems


def _merge_by_key(existing: list[dict], incoming: list[dict]) -> list[dict]:
    out = []
    seen = {}
    for row in [*(existing or []), *(incoming or [])]:
        key = (row.get("date"), row.get("author"), row.get("ticker"), row.get("quote"))
        if key in seen:
            if row.get("evidence_detail") and not out[seen[key]].get("evidence_detail"):
                out[seen[key]]["evidence_detail"] = row["evidence_detail"]
            continue
        seen[key] = len(out)
        out.append(row)
    out.sort(key=lambda r: (r.get("date") or "", r.get("author") or "", r.get("ticker") or ""))
    return out


def _merge_audit_entries(existing: list[dict], incoming: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in [*(existing or []), *(incoming or [])]:
        key = (
            row.get("message_id") or "",
            row.get("date") or "",
            row.get("author") or "",
            row.get("subject") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def classify_compact_source_call_candidates(
    calls: list[dict],
    *,
    generated_at: str | None = None,
) -> list[dict]:
    """Classify compact full-body-derived rows for source-call calibration.

    Compact rows are already redacted, action-relevant summaries. Keeping their
    Source Call Log classification in step with `inbox_call_dates.json` prevents
    preflight from treating a checked daily row as unclassified.
    """
    if not calls:
        return []
    try:
        import source_call_tracker as tracker
    except Exception:
        return []
    raw = [
        {
            "source": call.get("author") or "Fundstrat",
            "ticker": call.get("ticker"),
            "date": call.get("date"),
            "text": call.get("quote") or call.get("subject") or "",
            "evidence_detail": call.get("evidence_detail"),
        }
        for call in calls
        if call.get("ticker") and (call.get("quote") or call.get("subject"))
    ]
    rows = tracker.batch_classify(raw, now=(generated_at or "")[:10] or None)
    detail_by_key = {
        (
            str(item.get("source") or "").strip().lower(),
            str(item.get("ticker") or "").strip().upper(),
            str(item.get("date") or "")[:10],
            str(item.get("text") or "").strip(),
        ): item.get("evidence_detail")
        for item in raw
        if item.get("evidence_detail")
    }
    enriched = []
    for row in rows:
        lane = classify_fundstrat_lane(
            author=row.get("source") or "",
            text=row.get("verbatim_quote") or row.get("text") or "",
            ticker=row.get("ticker") or "",
        )
        enriched_row = {
            **row,
            "fundstrat_lane": lane["fundstrat_lane"],
            "source_domain": lane["source_domain"],
            "source_weight_note": lane["source_weight_note"],
            "confidence_policy": lane["confidence_policy"],
            "publication_type": lane.get("publication_type"),
            "capture_policy": lane.get("capture_policy"),
            "use_case": lane.get("use_case"),
            "decision_usefulness": lane.get("decision_usefulness"),
            "capture_reason": lane.get("capture_reason"),
        }
        detail = detail_by_key.get((
            str(row.get("source") or "").strip().lower(),
            str(row.get("ticker") or "").strip().upper(),
            str(row.get("date") or "")[:10],
            str(row.get("verbatim_quote") or row.get("text") or "").strip(),
        ))
        if detail:
            enriched_row["evidence_detail"] = detail
        enriched.append(enriched_row)
    return enriched


def _candidate_key(row: dict) -> tuple:
    text = (
        row.get("verbatim_quote")
        or row.get("text")
        or row.get("call_summary")
        or row.get("id")
        or row.get("tier")
        or ""
    )
    return (
        str(row.get("source") or "").strip().lower(),
        str(row.get("ticker") or "").strip().upper(),
        str(row.get("date") or "")[:10],
        str(text).strip(),
    )


def _merge_source_call_candidates(existing: list[dict], incoming: list[dict]) -> list[dict]:
    out = []
    seen = {}
    for row in [*(existing or []), *(incoming or [])]:
        if not isinstance(row, dict):
            continue
        key = _candidate_key(row)
        if not key[0] or not (key[1] or key[3]):
            continue
        if key in seen:
            if row.get("evidence_detail") and not out[seen[key]].get("evidence_detail"):
                out[seen[key]]["evidence_detail"] = row["evidence_detail"]
            continue
        seen[key] = len(out)
        out.append(row)
    return out


def _merge_source_call_cache(
    candidates: list[dict],
    out_dir: Path,
    *,
    generated_at: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    if not candidates:
        return {}, {"updated": False, "candidates": 0}
    try:
        import source_call_cache_merge
    except Exception as exc:
        return {}, {"updated": False, "candidates": len(candidates), "error": str(exc)}

    source_calls_path = out_dir / "source_calls.json"
    log_dates_path = out_dir / "log_call_dates.json"
    summary_path = out_dir / "source_call_cache_summary.json"
    existing = source_call_cache_merge._read_json(source_calls_path, default=[])
    merged, summary = source_call_cache_merge.merge_source_calls(
        existing,
        candidates,
        generated_at=generated_at,
    )
    source_call_cache_merge._atomic_write_json(source_calls_path, merged)
    source_call_cache_merge._atomic_write_json(log_dates_path, summary["log_call_dates"])
    source_call_cache_merge._atomic_write_json(summary_path, summary)
    return (
        {
            "source_calls": str(source_calls_path),
            "log_call_dates": str(log_dates_path),
            "source_call_cache_summary": str(summary_path),
        },
        {
            "updated": summary["added"] > 0,
            "candidates": summary["candidates"],
            "added": summary["added"],
            "stored": summary["stored"],
            "log_call_dates": len(summary["log_call_dates"]),
        },
    )


def _state_from_calls(prior: dict | None, calls: list[dict], *, generated_at: str) -> dict:
    prior = prior if isinstance(prior, dict) else {}
    processed = set(prior.get("processed_full_body_message_ids") or prior.get("processed_message_ids") or [])
    snippet_seen = set(prior.get("snippet_discovery_message_ids") or [])
    for call in calls:
        msg_id = _text(call.get("source_message_id"))
        if msg_id:
            processed.add(msg_id)
    dates = sorted({call.get("date") for call in calls if call.get("date")})
    return {
        "last_run_at": generated_at,
        "last_inbox_date": max(dates) if dates else prior.get("last_inbox_date", ""),
        "last_discovery_date": prior.get("last_discovery_date", ""),
        "processed_message_ids": sorted(processed),
        "processed_full_body_message_ids": sorted(processed),
        "snippet_discovery_message_ids": sorted(snippet_seen),
    }


def write_compact_outputs(
    calls: list[dict],
    out_dir: str | Path,
    *,
    merge_existing: bool = False,
    generated_at: str | None = None,
    inventory_path: str | Path | None = None,
) -> dict[str, str]:
    out = Path(out_dir)
    generated_at = generated_at or _utc_now_iso()
    existing = _read_json(out / "fundstrat_daily_calls.json", default=[]) if merge_existing else []
    stored_calls = _merge_by_key(existing, calls) if merge_existing else calls
    prior_dates = _read_json(out / "inbox_call_dates.json", default=[]) if merge_existing else []
    dates = sorted({*(d for d in prior_dates or [] if d), *(call.get("date") for call in stored_calls if call.get("date"))})
    prior_state = _read_json(out / "fundstrat_intake_state.json", default={})
    state = _state_from_calls(prior_state, calls, generated_at=generated_at)
    new_candidates = classify_compact_source_call_candidates(calls, generated_at=generated_at)
    prior_candidates = _read_json(out / "source_call_candidates.json", default=[]) if merge_existing else []
    source_call_candidates = _merge_source_call_candidates(prior_candidates, new_candidates)
    summary = {
        "entries": len(calls),
        "full_body_entries": len({call.get("source_message_id") or f"{call.get('date')}|{call.get('subject')}" for call in calls}),
        "snippet_only_entries": 0,
        "mentions": len(calls),
        "daily_calls": len(calls),
        "source_call_candidates": len(new_candidates),
        "merged": bool(merge_existing),
        "bodies_redacted": True,
        "compact_full_body_derived": True,
        "stored_entries": len(calls),
        "stored_daily_calls": len(stored_calls),
        "stored_source_call_candidates": len(source_call_candidates),
    }
    new_audit_entries = [
        {
            "subject": call.get("subject", ""),
            "date": call.get("date", ""),
            "author": call.get("author", ""),
            "source_path": "compact_full_body_derived",
            "message_id": call.get("source_message_id", ""),
            "body_source": "compact_full_body_derived",
            "body_fetched": True,
            "body_redacted": True,
            "body_chars": 0,
            "body_sha256": "",
        }
        for call in calls
    ]
    prior_entries = _read_json(out / "fundstrat_inbox_entries.json", default=[]) if merge_existing else []
    audit_entries = _merge_audit_entries(prior_entries, new_audit_entries) if merge_existing else new_audit_entries
    written = {
        "fundstrat_daily_calls": _atomic_write_json(out / "fundstrat_daily_calls.json", stored_calls),
        "inbox_call_dates": _atomic_write_json(out / "inbox_call_dates.json", dates),
        "source_call_candidates": _atomic_write_json(out / "source_call_candidates.json", source_call_candidates),
        "fundstrat_inbox_entries": _atomic_write_json(out / "fundstrat_inbox_entries.json", audit_entries),
        "fundstrat_intake_summary": _atomic_write_json(out / "fundstrat_intake_summary.json", summary),
        "fundstrat_intake_state": _atomic_write_json(out / "fundstrat_intake_state.json", state),
    }
    source_call_written, source_call_summary = _merge_source_call_cache(
        source_call_candidates,
        out,
        generated_at=generated_at,
    )
    summary["source_calls"] = source_call_summary
    _atomic_write_json(out / "fundstrat_intake_summary.json", summary)
    written.update(source_call_written)
    inventory_target = Path(inventory_path) if inventory_path else out / "fs_ingest_inventory.json"
    inventory_entries = fs_ingest_guard.daily_note_inventory_entries(
        new_audit_entries,
        ingested_at=generated_at,
    )
    if inventory_entries:
        written["fs_ingest_inventory"] = fs_ingest_guard.upsert_inventory(
            inventory_target,
            inventory_entries,
        )
    return {key: str(path) for key, path in written.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write compact Fundstrat daily calls")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--generated-at")
    parser.add_argument("--inventory")
    parser.add_argument("--validate", metavar="CALLS_JSON")
    args = parser.parse_args(argv)

    if args.validate:
        rows = normalize_compact_calls(_read_json(args.validate, default=[]))
        problems = validate_compact_calls(rows)
        print(json.dumps({"valid": not problems, "problems": problems, "rows": len(rows)}, indent=2))
        return 0 if not problems else 2

    payloads = [_read_json(path, default=[]) for path in args.files]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))
    if not payloads:
        parser.error("provide at least one compact calls file or --stdin-json")
    calls: list[dict] = []
    for payload in payloads:
        calls.extend(normalize_compact_calls(payload))
    problems = validate_compact_calls(calls)
    if problems:
        print(json.dumps({"written": False, "problems": problems}, indent=2))
        return 2
    written = write_compact_outputs(
        calls,
        args.out_dir,
        merge_existing=args.merge_existing,
        generated_at=args.generated_at,
        inventory_path=args.inventory,
    )
    print(json.dumps({"written": True, "calls": len(calls), "out_dir": args.out_dir, "files": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
