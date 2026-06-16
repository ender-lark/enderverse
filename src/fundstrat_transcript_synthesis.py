#!/usr/bin/env python3
"""Build action-oriented notes from private Fundstrat transcript packs.

This helper reads the private source vault, not the public repo, and emits
Notion-ready synthesis notes. It never copies raw transcript text into the
public output; the transcript itself remains in the private vault.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fundstrat_transcript_vault as vault_writer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "tmp" / "fundstrat_transcript_notion_notes.json"
NOTE_MD = "notion_action_note.md"
SYNTHESIS_JSON = "synthesis.json"
RAW_FORBIDDEN_KEYS = {
    "transcript",
    "transcript_text",
    "caption_text",
    "captions",
    "raw_transcript",
    "raw_text",
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
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_transcript_synthesis.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _atomic_write_text(path: str | Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_transcript_synthesis.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            if text and not text.endswith("\n"):
                fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clip(text: Any, max_chars: int = 500) -> str:
    compact = _text(text)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _vault_rel_from_ref(vault_ref: str) -> Path:
    prefix = "vault://"
    if not str(vault_ref or "").startswith(prefix):
        raise ValueError(f"unsupported vault_ref: {vault_ref}")
    return Path(str(vault_ref)[len(prefix):])


def _manifest_entries(vault: Path) -> list[dict[str, Any]]:
    manifest = _read_json(vault / vault_writer.MANIFEST_PATH, default={"items": []})
    rows = manifest.get("items") if isinstance(manifest, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _selected_entries(entries: list[dict[str, Any]], ids: list[str] | None, since: str | None, limit: int | None) -> list[dict[str, Any]]:
    selected = entries
    if ids:
        wanted = set(ids)
        selected = [row for row in selected if row.get("transcript_id") in wanted]
    if since:
        selected = [row for row in selected if str(row.get("source_date") or "") >= since]
    selected = sorted(selected, key=lambda row: (row.get("source_date") or "", row.get("captured_at") or "", row.get("transcript_id") or ""), reverse=True)
    if limit is not None:
        selected = selected[:limit]
    return selected


def _markdown_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = ""
    for raw in markdown.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.startswith("## "):
            current = _text(line[3:]).lower()
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _raw_transcript_from_md(text: str) -> str:
    marker = "\n## Transcript\n"
    idx = text.find(marker)
    if idx == -1:
        return ""
    return text[idx + len(marker):].strip()


def _transcript_hash_ok(folder: Path, source: dict[str, Any]) -> bool | None:
    transcript_path = folder / "transcript.md"
    if not transcript_path.is_file():
        return None
    raw = _raw_transcript_from_md(transcript_path.read_text(encoding="utf-8"))
    expected = _text(source.get("transcript_sha256"))
    if not raw or not expected:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() == expected


def _row_ticker(row: dict[str, Any]) -> str:
    return _text(row.get("ticker") or row.get("symbol") or row.get("asset")).upper()


def _extract_ticker(row: dict[str, Any]) -> str:
    return _text(row.get("ticker") or row.get("symbol") or row.get("asset")).upper()


def _action_items(compact_rows: list[dict[str, Any]], extracts: list[dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for row in compact_rows:
        if not isinstance(row, dict):
            continue
        ticker = _row_ticker(row)
        direction = _text(row.get("direction") or row.get("bias") or row.get("action_implication")).lower()
        quote = _clip(row.get("quote") or row.get("summary") or row.get("call") or row.get("action_implication"), 300)
        if not (ticker or quote):
            continue
        items.append({
            "ticker": ticker or "PORTFOLIO",
            "posture": direction or "watch",
            "why": quote,
            "timing": _clip(row.get("timing_horizon") or row.get("window") or row.get("horizon"), 160),
            "levels": _clip(row.get("key_levels") or row.get("levels"), 180),
            "next_step": _clip(row.get("action_implication") or row.get("implication"), 220),
        })
    seen = {(item["ticker"], item["why"]) for item in items}
    for row in extracts:
        if not isinstance(row, dict):
            continue
        ticker = _extract_ticker(row)
        implication = _clip(row.get("implication"), 240)
        claim = _clip(row.get("claim"), 240)
        if not (ticker or implication or claim):
            continue
        key = (ticker or "PORTFOLIO", implication or claim)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "ticker": ticker or "PORTFOLIO",
            "posture": "watch",
            "why": claim,
            "timing": "",
            "levels": "",
            "next_step": implication,
        })
    return items


def _priority(action_items: list[dict[str, str]], analysis: dict[str, str]) -> str:
    hot = {"buy", "add", "accumulate", "sell", "trim", "reduce", "avoid", "hedge"}
    if any(item.get("posture") in hot for item in action_items):
        return "high"
    combined = " ".join([json.dumps(action_items), analysis.get("portfolio impact", ""), analysis.get("levels / timing / invalidation", "")]).lower()
    if any(term in combined for term in ("risk", "invalidation", "fomc", "support", "resistance", "weekly close", "hedge")):
        return "medium"
    return "watch"


def _notion_title(source: dict[str, Any]) -> str:
    date = _text(source.get("source_date"))
    analyst = _text(source.get("analyst") or "Fundstrat")
    title = _clip(source.get("title"), 80)
    return f"Fundstrat transcript review - {date} - {analyst} - {title}"


def _note_content(source: dict[str, Any], analysis_sections: dict[str, str], action_items: list[dict[str, str]], extracts: list[dict[str, Any]], *, priority: str, transcript_hash_ok: bool | None) -> str:
    takeaway = _clip(analysis_sections.get("executive takeaway") or source.get("short_synthesis"), 900)
    portfolio = _clip(analysis_sections.get("portfolio impact"), 900)
    questions = [
        _clip(line.lstrip("- ").strip(), 220)
        for line in (analysis_sections.get("questions / follow-up") or "").splitlines()
        if _text(line)
    ]
    claims = [
        _clip(line.lstrip("- ").strip(), 240)
        for line in (analysis_sections.get("key claims") or "").splitlines()
        if _text(line)
    ]
    lines = [
        "## Decision Use",
        "",
        f"- Priority: {priority}",
        f"- Voice lane: {_text(source.get('voice_lane')) or vault_writer.voice_lane_for(_text(source.get('analyst')), _text(source.get('title')))}",
        f"- Takeaway: {takeaway or 'Needs analyst synthesis before action use.'}",
        f"- Portfolio impact: {portfolio or 'No portfolio-impact section supplied; treat as review-only until synthesized.'}",
        "",
        "## Action And Re-Check Items",
        "",
    ]
    if action_items:
        for item in action_items:
            pieces = [f"{item['ticker']} {item['posture']}: {item['why']}"]
            if item.get("levels"):
                pieces.append(f"Levels: {item['levels']}")
            if item.get("timing"):
                pieces.append(f"Timing: {item['timing']}")
            if item.get("next_step"):
                pieces.append(f"Next: {item['next_step']}")
            lines.append("- " + " | ".join(piece for piece in pieces if piece))
    else:
        lines.append("- No compact action item supplied; keep this note review-only.")
    lines.extend(["", "## Claims To Test", ""])
    if claims:
        lines.extend(f"- {claim}" for claim in claims[:8])
    else:
        for row in extracts[:8]:
            if isinstance(row, dict):
                claim = _clip(row.get("claim"), 240)
                implication = _clip(row.get("implication"), 240)
                if claim or implication:
                    lines.append(f"- {claim or implication}")
    if questions:
        lines.extend(["", "## Follow-Up Questions", ""])
        lines.extend(f"- {question}" for question in questions[:8])
    lines.extend([
        "",
        "## Source Metadata",
        "",
        f"- Transcript ID: {_text(source.get('transcript_id'))}",
        f"- Analyst: {_text(source.get('analyst'))}",
        f"- Source date: {_text(source.get('source_date'))}",
        f"- Published: {_text(source.get('published_at'))}",
        f"- Captured: {_text(source.get('captured_at'))}",
        f"- Source URL: {_text(source.get('source_url'))}",
        f"- Vault ref: vault://fundstrat/transcripts/{_text(source.get('source_date'))[:4]}/{_text(source.get('source_date'))[5:7]}/{_text(source.get('transcript_id'))}",
        f"- Transcript SHA-256: {_text(source.get('transcript_sha256'))}",
        f"- Transcript hash check: {transcript_hash_ok if transcript_hash_ok is not None else 'not_checked'}",
        "- Raw transcript text is intentionally not included in this Notion note.",
        "",
    ])
    return "\n".join(lines)


def _summary(source: dict[str, Any], analysis_sections: dict[str, str], action_items: list[dict[str, str]]) -> str:
    takeaway = _clip(analysis_sections.get("executive takeaway") or source.get("short_synthesis"), 260)
    tickers = ", ".join(item["ticker"] for item in action_items[:5] if item.get("ticker"))
    if tickers:
        return _clip(f"{takeaway} Action/re-check tickers: {tickers}.", 500)
    return takeaway


def synthesize_entry(vault: Path, entry: dict[str, Any]) -> dict[str, Any]:
    folder = vault / _vault_rel_from_ref(_text(entry.get("vault_ref")))
    source = _read_json(folder / "source.json", default={})
    if not isinstance(source, dict):
        raise RuntimeError(f"missing source.json for {entry.get('transcript_id')}")
    source = {**entry, **source}
    analysis_md = (folder / "analysis.md").read_text(encoding="utf-8") if (folder / "analysis.md").is_file() else ""
    analysis_sections = _markdown_sections(analysis_md)
    extracts_payload = _read_json(folder / "extracts.json", default={})
    extracts = extracts_payload.get("extracts") if isinstance(extracts_payload, dict) else []
    compact_rows = extracts_payload.get("compact_rows") if isinstance(extracts_payload, dict) else []
    extracts = [row for row in extracts if isinstance(row, dict)]
    compact_rows = [row for row in compact_rows if isinstance(row, dict)]
    action_items = _action_items(compact_rows, extracts)
    transcript_hash_ok = _transcript_hash_ok(folder, source)
    priority = _priority(action_items, analysis_sections)
    content = _note_content(source, analysis_sections, action_items, extracts, priority=priority, transcript_hash_ok=transcript_hash_ok)
    summary = _summary(source, analysis_sections, action_items)
    note = {
        "transcript_id": source["transcript_id"],
        "source_date": source.get("source_date"),
        "title": source.get("title"),
        "analyst": source.get("analyst"),
        "voice_lane": source.get("voice_lane"),
        "source_url": source.get("source_url"),
        "vault_ref": entry.get("vault_ref"),
        "transcript_sha256": source.get("transcript_sha256"),
        "transcript_chars": source.get("transcript_chars"),
        "priority": priority,
        "summary": summary,
        "action_items": action_items,
        "extract_count": len(extracts),
        "compact_row_count": len(compact_rows),
        "transcript_hash_ok": transcript_hash_ok,
        "notion": {
            "title": _notion_title(source),
            "properties": {
                "Name": _notion_title(source),
                "date:Date:start": source.get("source_date"),
                "date:Date:is_datetime": 0,
                "Status": "Ready for Review",
                "Summary": summary,
                "Type": "Fundstrat Transcript Review",
            },
            "content": content,
        },
    }
    return note


def validate_notes_payload(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["notes payload must be an object"]
    notes = payload.get("items")
    if not isinstance(notes, list):
        return ["items must be a list"]
    dumped = json.dumps(payload, ensure_ascii=False)
    if "## Transcript\n" in dumped or "WEBVTT" in dumped:
        problems.append("notes payload appears to contain raw transcript material")
    for idx, note in enumerate(notes):
        if not isinstance(note, dict):
            problems.append(f"items[{idx}] must be an object")
            continue
        forbidden = sorted(key for key in RAW_FORBIDDEN_KEYS if key in note)
        if forbidden:
            problems.append(f"items[{idx}] contains raw transcript keys: {', '.join(forbidden)}")
        if not _text(note.get("transcript_id")):
            problems.append(f"items[{idx}].transcript_id is required")
        notion = note.get("notion") if isinstance(note.get("notion"), dict) else {}
        if not _text(notion.get("content")):
            problems.append(f"items[{idx}].notion.content is required")
    return problems


def _write_vault_notes(vault: Path, notes: list[dict[str, Any]]) -> list[Path]:
    written: list[Path] = []
    for note in notes:
        folder = vault / _vault_rel_from_ref(_text(note.get("vault_ref")))
        private_note = {
            key: value
            for key, value in note.items()
            if key != "notion"
        }
        private_note["notion_title"] = note["notion"]["title"]
        private_note["notion_status"] = "notion_write_pending"
        written.append(_atomic_write_json(folder / SYNTHESIS_JSON, private_note))
        written.append(_atomic_write_text(folder / NOTE_MD, note["notion"]["content"]))
    return written


def _commit_vault(vault: Path, paths: list[Path], *, push: bool) -> dict[str, Any]:
    rels = [str(path.relative_to(vault)).replace("\\", "/") for path in paths]
    subprocess.run(["git", "add", "--", *rels], cwd=vault, text=True, capture_output=True, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=vault, text=True, capture_output=True, check=True).stdout.splitlines()
    if not staged:
        return {"committed": False, "pushed": False, "reason": "no staged vault synthesis diff"}
    subprocess.run(["git", "commit", "-m", "Add Fundstrat transcript synthesis notes"], cwd=vault, text=True, capture_output=True, check=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=vault, text=True, capture_output=True, check=True).stdout.strip()
    pushed = False
    if push:
        subprocess.run(["git", "push"], cwd=vault, text=True, capture_output=True, check=True)
        pushed = True
    return {"committed": True, "pushed": pushed, "commit": commit, "paths": rels}


def build_notes(
    *,
    vault_path: str | Path | None = None,
    transcript_ids: list[str] | None = None,
    since: str | None = None,
    limit: int | None = None,
    out_path: str | Path = DEFAULT_OUT,
    write_vault_notes: bool = False,
    commit_vault: bool = False,
    push_vault: bool = False,
) -> dict[str, Any]:
    vault = vault_writer.get_vault_path(vault_path)
    entries = _selected_entries(_manifest_entries(vault), transcript_ids, since, limit)
    notes = [synthesize_entry(vault, entry) for entry in entries]
    payload = {
        "generated_at": _utc_now_iso(),
        "policy": "Notion notes are compact transcript-derived synthesis only; raw transcripts remain in the private vault.",
        "items": notes,
    }
    problems = validate_notes_payload(payload)
    if problems:
        raise ValueError("; ".join(problems))
    out_file = _atomic_write_json(out_path, payload)
    written: list[Path] = []
    vault_commit = {"committed": False, "pushed": False, "reason": "not requested"}
    if write_vault_notes or commit_vault or push_vault:
        written = _write_vault_notes(vault, notes)
    if commit_vault or push_vault:
        vault_commit = _commit_vault(vault, written, push=push_vault)
    return {
        "valid": True,
        "out": str(out_file),
        "notes": len(notes),
        "transcript_ids": [note["transcript_id"] for note in notes],
        "vault_notes_written": len(written),
        "vault_commit": vault_commit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Notion-ready Fundstrat transcript synthesis notes")
    parser.add_argument("--vault-path")
    parser.add_argument("--id", action="append", dest="transcript_ids", help="Transcript id to synthesize; repeatable")
    parser.add_argument("--since", help="Only synthesize source_date >= YYYY-MM-DD")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--write-vault-notes", action="store_true")
    parser.add_argument("--commit-vault", action="store_true")
    parser.add_argument("--push-vault", action="store_true")
    parser.add_argument("--validate", help="Validate a generated notes JSON file")
    args = parser.parse_args(argv)

    if args.validate:
        problems = validate_notes_payload(_read_json(args.validate, default={}))
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
        return 0 if not problems else 2

    report = build_notes(
        vault_path=args.vault_path,
        transcript_ids=args.transcript_ids,
        since=args.since,
        limit=args.limit,
        out_path=args.out,
        write_vault_notes=args.write_vault_notes,
        commit_vault=args.commit_vault,
        push_vault=args.push_vault,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
