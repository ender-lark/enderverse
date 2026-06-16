#!/usr/bin/env python3
"""Write full Fundstrat video transcripts to the private source vault.

The public Investing OS repo keeps only metadata, hashes, and short synthesis.
Full transcript text belongs in the private vault pointed to by
INVESTING_OS_SOURCE_VAULT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLIC_INDEX = Path(__file__).resolve().parent / "fundstrat_transcript_index.json"
VAULT_ENV = "INVESTING_OS_SOURCE_VAULT"
TRANSCRIPT_ROOT = Path("fundstrat") / "transcripts"
MANIFEST_PATH = Path("fundstrat") / "manifests" / "fundstrat_transcripts.json"
RAW_TRANSCRIPT_KEYS = {"transcript", "transcript_text", "caption_text", "captions", "raw_transcript"}
PUBLIC_ALLOWED_KEYS = {
    "transcript_id",
    "vault_ref",
    "transcript_sha256",
    "transcript_chars",
    "title",
    "analyst",
    "source_url",
    "source_date",
    "published_at",
    "captured_at",
    "capture_method",
    "capture_status",
    "completeness_notes",
    "short_synthesis",
    "voice_lane",
    "extract_count",
    "compact_row_count",
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
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_transcript.", suffix=".tmp", dir=str(path.parent))
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
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_transcript.", suffix=".tmp", dir=str(path.parent))
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


def _multiline(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _env_from_user_registry(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value or "")
    except OSError:
        return ""


def get_vault_path(explicit: str | Path | None = None) -> Path:
    raw = str(explicit or os.environ.get(VAULT_ENV) or _env_from_user_registry(VAULT_ENV) or "").strip()
    if not raw:
        raise RuntimeError(f"{VAULT_ENV} is not set")
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise RuntimeError(f"{VAULT_ENV} path does not exist: {path}")
    return path


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(text: str, *, max_len: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _text(text).lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return (slug or "untitled")[:max_len].strip("-") or "untitled"


def _source_date(payload: dict[str, Any]) -> str:
    for key in ("source_date", "date", "published_at", "published"):
        text = _text(payload.get(key))
        if len(text) >= 10:
            return text[:10]
    return _utc_now_iso()[:10]


def _analyst_slug(analyst: str) -> str:
    lowered = analyst.lower()
    if "newton" in lowered:
        return "newton"
    if "tom" in lowered and "lee" in lowered:
        return "tom-lee"
    if "farrell" in lowered:
        return "farrell"
    return _slug(analyst, max_len=24)


def transcript_id_for(payload: dict[str, Any]) -> str:
    date = _source_date(payload)
    analyst = _analyst_slug(_text(payload.get("analyst") or payload.get("author") or "fundstrat"))
    title = _slug(payload.get("title") or payload.get("video_title") or payload.get("subject"), max_len=64)
    return f"fundstrat-{date}-{analyst}-{title}"


def voice_lane_for(analyst: str, title: str = "") -> str:
    text = f"{analyst} {title}".lower()
    if "newton" in text or "technical" in text:
        return "mark_newton_technical"
    if "tom lee" in text or "macro" in text or "first word" in text:
        return "tom_lee_macro"
    if "farrell" in text or "crypto" in text or "digital asset" in text:
        return "crypto_strategy"
    return "fundstrat_general"


def _extract_transcript(payload: dict[str, Any]) -> str:
    for key in ("transcript_text", "transcript", "caption_text", "captions"):
        text = _multiline(payload.get(key))
        if text:
            return text
    return ""


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("items", "rows", "videos", "transcripts", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [payload]
    return []


def _first_sentence(text: str, *, max_chars: int = 500) -> str:
    compact = _text(text)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _analysis_text(payload: dict[str, Any], *, extract_count: int, compact_count: int) -> str:
    explicit = _multiline(payload.get("analysis_md") or payload.get("analysis_text"))
    if explicit:
        return explicit
    analysis = payload.get("analysis")
    if isinstance(analysis, str):
        return _multiline(analysis)
    if isinstance(analysis, dict):
        sections = [
            ("Executive Takeaway", analysis.get("executive_takeaway") or analysis.get("takeaway")),
            ("Key Claims", analysis.get("key_claims") or analysis.get("claims")),
            ("Tickers / Assets Mentioned", analysis.get("tickers") or analysis.get("assets")),
            ("Levels / Timing / Invalidation", analysis.get("levels") or analysis.get("timing")),
            ("Portfolio Impact", analysis.get("portfolio_impact")),
            ("Questions / Follow-Up", analysis.get("questions") or analysis.get("follow_up")),
            ("Derived Investing OS Outputs", analysis.get("derived_outputs")),
        ]
    else:
        sections = [
            ("Executive Takeaway", payload.get("short_synthesis")),
            ("Key Claims", "See extracts.json."),
            ("Tickers / Assets Mentioned", ""),
            ("Levels / Timing / Invalidation", ""),
            ("Portfolio Impact", ""),
            ("Questions / Follow-Up", ""),
            ("Derived Investing OS Outputs", f"{extract_count} extract(s); {compact_count} compact row(s)."),
        ]
    lines = ["# Fundstrat Transcript Analysis", ""]
    for title, value in sections:
        lines.extend([f"## {title}", ""])
        if isinstance(value, list):
            lines.extend(f"- {_text(item)}" for item in value if _text(item))
        elif isinstance(value, dict):
            lines.append(json.dumps(value, indent=2, ensure_ascii=False))
        elif _text(value):
            lines.append(_text(value))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _transcript_markdown(payload: dict[str, Any], transcript: str) -> str:
    lines = [
        "# Fundstrat Transcript",
        "",
        "## Source",
        "",
        f"- Title: {_text(payload.get('title') or payload.get('video_title') or payload.get('subject'))}",
        f"- Analyst: {_text(payload.get('analyst') or payload.get('author') or 'Fundstrat')}",
        f"- Published: {_text(payload.get('published_at') or payload.get('published') or payload.get('date'))}",
        f"- Captured: {_text(payload.get('captured_at')) or _utc_now_iso()}",
        f"- Source URL: {_text(payload.get('source_url') or payload.get('url'))}",
        f"- Capture method: {_text(payload.get('capture_method') or 'chrome_visible_transcript')}",
        "",
        "## Transcript",
        "",
        transcript,
        "",
    ]
    return "\n".join(lines)


def _source_payload(payload: dict[str, Any], transcript: str, transcript_id: str) -> dict[str, Any]:
    title = _text(payload.get("title") or payload.get("video_title") or payload.get("subject"))
    analyst = _text(payload.get("analyst") or payload.get("author") or "Fundstrat")
    captured_at = _text(payload.get("captured_at")) or _utc_now_iso()
    return {
        "transcript_id": transcript_id,
        "title": title,
        "analyst": analyst,
        "source_url": _text(payload.get("source_url") or payload.get("url")),
        "source_date": _source_date(payload),
        "published_at": _text(payload.get("published_at") or payload.get("published") or payload.get("date")),
        "captured_at": captured_at,
        "capture_method": _text(payload.get("capture_method") or "chrome_visible_transcript"),
        "capture_status": "captured_and_analyzed",
        "completeness_notes": _text(payload.get("completeness_notes") or payload.get("completeness") or ""),
        "transcript_chars": len(transcript),
        "transcript_sha256": _sha256(transcript),
        "voice_lane": _text(payload.get("voice_lane") or voice_lane_for(analyst, title)),
    }


def public_index_entry(source: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    entry = {
        key: source.get(key)
        for key in (
            "transcript_id",
            "title",
            "analyst",
            "source_url",
            "source_date",
            "published_at",
            "captured_at",
            "capture_method",
            "capture_status",
            "completeness_notes",
            "transcript_chars",
            "transcript_sha256",
            "voice_lane",
        )
    }
    entry["vault_ref"] = f"vault://{TRANSCRIPT_ROOT.as_posix()}/{source['source_date'][:4]}/{source['source_date'][5:7]}/{source['transcript_id']}"
    entry["short_synthesis"] = _first_sentence(payload.get("short_synthesis") or payload.get("summary") or "")
    entry["extract_count"] = len(payload.get("extracts") or [])
    entry["compact_row_count"] = len(payload.get("compact_rows") or [])
    return entry


def validate_public_index_payload(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["public index must be an object"]
    rows = payload.get("items")
    if not isinstance(rows, list):
        return ["public index items must be a list"]
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"items[{idx}] must be an object")
            continue
        forbidden = sorted(set(row) - PUBLIC_ALLOWED_KEYS)
        if forbidden:
            problems.append(f"items[{idx}] has non-public keys: {', '.join(forbidden)}")
        raw = sorted(key for key in RAW_TRANSCRIPT_KEYS if _text(row.get(key)))
        if raw:
            problems.append(f"items[{idx}] contains raw transcript keys: {', '.join(raw)}")
    return problems


def _merge_index(existing: dict[str, Any] | None, entry: dict[str, Any]) -> dict[str, Any]:
    payload = existing if isinstance(existing, dict) else {}
    rows = payload.get("items") if isinstance(payload.get("items"), list) else []
    out: list[dict[str, Any]] = []
    replaced = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        same_id = row.get("transcript_id") == entry.get("transcript_id")
        same_url_hash = (
            row.get("source_url")
            and row.get("source_url") == entry.get("source_url")
            and row.get("transcript_sha256") == entry.get("transcript_sha256")
        )
        if same_id or same_url_hash:
            if not replaced:
                out.append(entry)
                replaced = True
            continue
        out.append(row)
    if not replaced:
        out.append(entry)
    out.sort(key=lambda r: (r.get("source_date") or "", r.get("analyst") or "", r.get("title") or ""))
    merged = {
        "generated_at": _utc_now_iso(),
        "policy": "Full Fundstrat transcripts are stored only in the private source vault.",
        "items": out,
    }
    problems = validate_public_index_payload(merged)
    if problems:
        raise ValueError("; ".join(problems))
    return merged


def _merge_manifest(vault: Path, entry: dict[str, Any]) -> dict[str, Any]:
    path = vault / MANIFEST_PATH
    existing = _read_json(path, default={"items": []})
    merged = _merge_index(existing, entry)
    merged["policy"] = "Private vault manifest may point to full local transcript artifacts."
    return merged


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)


def _commit_vault(vault: Path, paths: list[Path], *, message: str, push: bool) -> dict[str, Any]:
    rels = [str(path.relative_to(vault)).replace("\\", "/") for path in paths]
    _run_git(["add", "--", *rels], cwd=vault)
    staged = _run_git(["diff", "--cached", "--name-only"], cwd=vault).stdout.splitlines()
    if not staged:
        return {"committed": False, "pushed": False, "reason": "no staged vault diff"}
    _run_git(["commit", "-m", message], cwd=vault)
    commit = _run_git(["rev-parse", "--short", "HEAD"], cwd=vault).stdout.strip()
    pushed = False
    if push:
        _run_git(["push"], cwd=vault)
        pushed = True
    return {"committed": True, "pushed": pushed, "commit": commit, "paths": rels}


def write_transcript_pack(
    payload: dict[str, Any],
    *,
    vault_path: str | Path | None = None,
    public_index_path: str | Path = DEFAULT_PUBLIC_INDEX,
    commit_vault: bool = False,
    push_vault: bool = False,
) -> dict[str, Any]:
    transcript = _extract_transcript(payload)
    if not transcript:
        raise ValueError("transcript_text, transcript, caption_text, or captions is required")
    vault = get_vault_path(vault_path)
    transcript_id = _text(payload.get("transcript_id")) or transcript_id_for(payload)
    source = _source_payload(payload, transcript, transcript_id)
    year = source["source_date"][:4]
    month = source["source_date"][5:7]
    folder = vault / TRANSCRIPT_ROOT / year / month / transcript_id
    extracts = payload.get("extracts") if isinstance(payload.get("extracts"), list) else []
    compact_rows = payload.get("compact_rows") if isinstance(payload.get("compact_rows"), list) else []

    transcript_path = _atomic_write_text(folder / "transcript.md", _transcript_markdown(payload, transcript))
    source_path = _atomic_write_json(folder / "source.json", source)
    analysis_path = _atomic_write_text(folder / "analysis.md", _analysis_text(payload, extract_count=len(extracts), compact_count=len(compact_rows)))
    extracts_payload = {
        "transcript_id": transcript_id,
        "source_url": source["source_url"],
        "extracts": extracts,
        "compact_rows": compact_rows,
    }
    extracts_path = _atomic_write_json(folder / "extracts.json", extracts_payload)

    public_entry = public_index_entry(source, payload)
    manifest = _merge_manifest(vault, public_entry)
    manifest_path = _atomic_write_json(vault / MANIFEST_PATH, manifest)

    public_index_file = Path(public_index_path)
    public_index = _merge_index(_read_json(public_index_file, default={"items": []}), public_entry)
    _atomic_write_json(public_index_file, public_index)

    vault_commit: dict[str, Any] = {"committed": False, "pushed": False, "reason": "not requested"}
    if commit_vault or push_vault:
        vault_commit = _commit_vault(
            vault,
            [transcript_path, source_path, analysis_path, extracts_path, manifest_path],
            message=f"Add Fundstrat transcript {transcript_id}",
            push=push_vault,
        )
    return {
        "valid": True,
        "transcript_id": transcript_id,
        "vault_folder": str(folder),
        "public_index": str(public_index_file),
        "vault_ref": public_entry["vault_ref"],
        "transcript_sha256": source["transcript_sha256"],
        "transcript_chars": source["transcript_chars"],
        "extract_count": len(extracts),
        "compact_row_count": len(compact_rows),
        "vault_commit": vault_commit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Store Fundstrat transcripts in the private source vault")
    parser.add_argument("files", nargs="*", help="JSON payload file(s)")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--vault-path")
    parser.add_argument("--public-index", default=str(DEFAULT_PUBLIC_INDEX))
    parser.add_argument("--commit-vault", action="store_true")
    parser.add_argument("--push-vault", action="store_true")
    parser.add_argument("--validate-public-index", action="store_true")
    args = parser.parse_args(argv)

    if args.validate_public_index:
        problems = validate_public_index_payload(_read_json(args.public_index, default={"items": []}))
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
        return 0 if not problems else 2

    payloads = [_read_json(path, default={}) for path in args.files]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        rows.extend(_rows_from_payload(payload))
    if not rows:
        parser.error("provide at least one transcript payload file or --stdin-json")

    reports = [
        write_transcript_pack(
            row,
            vault_path=args.vault_path,
            public_index_path=args.public_index,
            commit_vault=args.commit_vault,
            push_vault=args.push_vault,
        )
        for row in rows
    ]
    print(json.dumps({"valid": True, "reports": reports}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
