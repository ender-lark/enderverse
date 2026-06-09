#!/usr/bin/env python3
"""Accept compact Fundstrat web rows after authenticated Chrome review.

This helper is intentionally not a scraper. Codex/Chrome reads the logged-in
Fundstrat page, then supplies only compact source-backed rows here. Raw article
text, screenshots, snippets, push notifications, and video-only titles are
rejected before they can touch the Fundstrat daily-call caches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from fundstrat_daily_compact_intake import (
    _atomic_write_json,
    _read_json,
    normalize_compact_calls,
    validate_compact_calls,
    write_compact_outputs,
)


DEFAULT_OUT_DIR = Path(__file__).resolve().parent

ALLOWED_SURFACES = {
    "flashinsights_feed",
    "flashinsights_detail",
    "article_detail",
    "video_transcript",
    "video_captions",
    "companion_article",
    "supplied_compact_notes",
}
DISCOVERY_ONLY_SURFACES = {
    "push_notification",
    "ios_push",
    "listing_card",
    "search_result",
    "article_listing",
    "video_only",
    "video_embed",
    "thumbnail",
    "email_snippet",
}
RAW_TEXT_FIELDS = {
    "body",
    "html",
    "raw_body",
    "raw_html",
    "raw_text",
    "article_text",
    "page_text",
    "transcript_text",
    "screenshot_text",
}
VIDEO_SURFACES = {"video_transcript", "video_captions"}


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("calls", "items", "rows", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [payload]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _surface(row: dict[str, Any]) -> str:
    return _text(row.get("source_surface") or row.get("surface") or row.get("source_type")).lower()


def _has_raw_text(row: dict[str, Any]) -> list[str]:
    return sorted(field for field in RAW_TEXT_FIELDS if _text(row.get(field)))


def _full_content_basis(row: dict[str, Any]) -> str:
    return _text(row.get("full_content_basis") or row.get("content_basis") or row.get("evidence_basis"))


def _source_id(row: dict[str, Any], surface: str) -> str:
    explicit = _text(row.get("source_message_id") or row.get("message_id") or row.get("id"))
    if explicit:
        return explicit
    parts = [
        "fundstrat-web",
        surface,
        _text(row.get("date") or row.get("published_at"))[:10],
        _text(row.get("published_time_et") or row.get("time_et")),
        _text(row.get("ticker") or row.get("symbol")).upper(),
        _text(row.get("subject") or row.get("title")),
        _text(row.get("source_url") or row.get("url")),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return "-".join(part for part in parts[:5] if part).replace(" ", "-").lower() + f"-{digest}"


def validate_web_row(row: dict[str, Any], idx: int = 0) -> tuple[bool, str]:
    raw_fields = _has_raw_text(row)
    if raw_fields:
        return False, f"items[{idx}] contains raw text fields: {', '.join(raw_fields)}"
    surface = _surface(row)
    if not surface:
        return False, f"items[{idx}] missing source_surface"
    if surface in DISCOVERY_ONLY_SURFACES:
        return False, f"items[{idx}] source_surface {surface!r} is discovery-only"
    if surface not in ALLOWED_SURFACES:
        return False, f"items[{idx}] source_surface {surface!r} is not allowed"
    if not _full_content_basis(row):
        return False, f"items[{idx}] missing full_content_basis"
    if surface == "article_detail" and "detail" not in _full_content_basis(row).lower():
        return False, f"items[{idx}] article_detail must state detail-page evidence"
    if surface in VIDEO_SURFACES:
        basis = _full_content_basis(row).lower()
        if "transcript" not in basis and "caption" not in basis:
            return False, f"items[{idx}] video rows require transcript/caption evidence"
    return True, ""


def compact_row_from_web(row: dict[str, Any], surface: str) -> dict[str, Any]:
    source_label = {
        "flashinsights_feed": "Fundstrat Chrome FlashInsights feed",
        "flashinsights_detail": "Fundstrat Chrome FlashInsights detail page",
        "article_detail": "Fundstrat Chrome article detail page",
        "video_transcript": "Fundstrat Chrome video transcript",
        "video_captions": "Fundstrat Chrome video captions",
        "companion_article": "Fundstrat Chrome companion article",
        "supplied_compact_notes": "Fundstrat supplied compact notes",
    }.get(surface, "Fundstrat Chrome web intake")
    return {
        "author": _text(row.get("author") or row.get("analyst") or "Fundstrat"),
        "ticker": _text(row.get("ticker") or row.get("symbol")).upper(),
        "direction": _text(row.get("direction") or row.get("bias")).lower() or None,
        "entry": row.get("entry"),
        "stop": row.get("stop"),
        "target": row.get("target"),
        "window": _text(row.get("window") or row.get("horizon")) or None,
        "quote": _text(row.get("quote") or row.get("summary") or row.get("call")),
        "date": _text(row.get("date") or row.get("published_at"))[:10],
        "subject": _text(row.get("subject") or row.get("title") or "Fundstrat web compact call"),
        "source_message_id": _source_id(row, surface),
        "source": _text(row.get("source") or source_label),
    }


def normalize_web_compact_rows(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    compact_inputs: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    problems: list[str] = []
    for idx, row in enumerate(_rows_from_payload(payload)):
        ok, problem = validate_web_row(row, idx)
        surface = _surface(row)
        if not ok:
            if "discovery-only" in problem:
                suppressed.append({
                    "index": idx,
                    "source_surface": surface,
                    "reason": problem,
                    "subject": _text(row.get("subject") or row.get("title")),
                })
                continue
            problems.append(problem)
            continue
        compact_inputs.append(compact_row_from_web(row, surface))
    if problems:
        return [], suppressed, problems
    calls = normalize_compact_calls(compact_inputs)
    compact_keys = {
        (call.get("date"), call.get("author"), call.get("ticker"), call.get("quote"))
        for call in calls
    }
    for row in compact_inputs:
        key = (row.get("date"), row.get("author"), row.get("ticker"), row.get("quote"))
        if key not in compact_keys:
            suppressed.append({
                "source_surface": row.get("source_surface") or row.get("source"),
                "reason": "compact row suppressed by Fundstrat publication policy",
                "ticker": row.get("ticker"),
                "subject": row.get("subject"),
            })
    problems.extend(validate_compact_calls(calls))
    return calls, suppressed, problems


def write_web_outputs(
    calls: list[dict[str, Any]],
    out_dir: str | Path,
    *,
    merge_existing: bool = False,
    generated_at: str | None = None,
    suppressed: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    written = write_compact_outputs(
        calls,
        out_dir,
        merge_existing=merge_existing,
        generated_at=generated_at,
    )
    summary_path = Path(out_dir) / "fundstrat_intake_summary.json"
    summary = _read_json(summary_path, default={})
    summary["web_compact_intake"] = {
        "source": "authenticated_fundstrat_chrome",
        "checked_rows": len(calls),
        "suppressed_rows": len(suppressed or []),
        "raw_bodies_stored": False,
    }
    _atomic_write_json(summary_path, summary)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize compact Fundstrat web rows")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--generated-at")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payloads = [_read_json(path, default=[]) for path in args.files]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))
    if not payloads:
        parser.error("provide at least one compact web payload file or --stdin-json")

    calls: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    problems: list[str] = []
    for payload in payloads:
        payload_calls, payload_suppressed, payload_problems = normalize_web_compact_rows(payload)
        calls.extend(payload_calls)
        suppressed.extend(payload_suppressed)
        problems.extend(payload_problems)

    if problems:
        print(json.dumps({"written": False, "problems": problems, "suppressed": suppressed}, indent=2))
        return 2
    if args.dry_run or not calls:
        print(json.dumps({
            "written": False,
            "dry_run": bool(args.dry_run),
            "calls": len(calls),
            "suppressed": suppressed,
            "reason": "no compact checked rows" if not calls else "",
        }, indent=2))
        return 0

    written = write_web_outputs(
        calls,
        args.out_dir,
        merge_existing=args.merge_existing,
        generated_at=args.generated_at,
        suppressed=suppressed,
    )
    print(json.dumps({
        "written": True,
        "calls": len(calls),
        "suppressed": suppressed,
        "out_dir": args.out_dir,
        "files": written,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
