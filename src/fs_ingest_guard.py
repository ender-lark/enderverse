"""FundStrat ingest completeness guard.

The dashboard can lean on FundStrat monthly/Bible layers only as far as those
layers were actually distilled. This module keeps that honesty check
machine-readable: ingest routines append/update section inventories, and build
surfaces warn when an active Bible layer is missing inventory or has skipped
sections.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SRC = Path(__file__).resolve().parent
DEFAULT_INVENTORY_PATH = SRC / "fs_ingest_inventory.json"

SECTION_STATUSES = {"distilled", "skipped", "empty"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_id(prefix: str, value: Any) -> str:
    text = _text(value) or "unknown"
    return f"{prefix}:{text}"


def _section(name: str, status: str, note: str = "") -> dict[str, str]:
    clean_status = status if status in SECTION_STATUSES else "skipped"
    row = {"name": str(name), "status": clean_status}
    if note:
        row["note"] = str(note)
    return row


def _entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("entries")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def inventory_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "entries": sorted(entries, key=lambda row: str(row.get("source_id") or "")),
    }


def load_inventory(path: str | Path = DEFAULT_INVENTORY_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"generated_at": "", "entries": []}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fs_ingest_inventory.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    sections = [
        _section(
            _text(section.get("name")),
            _text(section.get("status")),
            _text(section.get("note")),
        )
        for section in entry.get("sections") or []
        if isinstance(section, dict) and _text(section.get("name"))
    ]
    skipped_count = sum(1 for section in sections if section.get("status") == "skipped")
    return {
        "source_id": _text(entry.get("source_id")),
        "title": _text(entry.get("title")),
        "ingested_at": _text(entry.get("ingested_at")) or _now_iso(),
        "total_sections": int(entry.get("total_sections") or len(sections)),
        "sections": sections,
        "skipped_count": int(entry.get("skipped_count") if entry.get("skipped_count") is not None else skipped_count),
    }


def upsert_inventory(path: str | Path, new_entries: dict[str, Any] | list[dict[str, Any]]) -> Path:
    incoming = [new_entries] if isinstance(new_entries, dict) else list(new_entries)
    existing = _entries(load_inventory(path))
    by_id = {str(row.get("source_id") or ""): row for row in existing if row.get("source_id")}
    for entry in incoming:
        normalized = normalize_entry(entry)
        if normalized.get("source_id"):
            by_id[normalized["source_id"]] = normalized
    return _atomic_write_json(path, inventory_payload(list(by_id.values())))


def active_bible_layers(bible: dict[str, Any] | None) -> list[dict[str, str]]:
    bible = bible if isinstance(bible, dict) else {}
    out: list[dict[str, str]] = []
    sector = bible.get("sector_allocation") if isinstance(bible.get("sector_allocation"), dict) else {}
    sector_date = _text(sector.get("as_of") or bible.get("deck_date"))
    if sector:
        out.append({
            "source_id": _source_id("fundstrat_sector_allocation", sector_date),
            "title": f"Fundstrat Sector Allocation {sector_date}" if sector_date else "Fundstrat Sector Allocation",
        })
    core_date = _text(bible.get("core_stock_ideas_as_of") or bible.get("deck_date"))
    has_core = any(bible.get(key) for key in ("top5", "bottom5", "top5_smid", "bottom5_smid", "what_to_own"))
    if has_core:
        out.append({
            "source_id": _source_id("fundstrat_core_stock_ideas", core_date),
            "title": f"Fundstrat Core Stock Ideas {core_date}" if core_date else "Fundstrat Core Stock Ideas",
        })
    return out


def check(inventory: Any, active_layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {
        str(row.get("source_id") or ""): normalize_entry(row)
        for row in _entries(inventory)
        if row.get("source_id")
    }
    findings: list[dict[str, Any]] = []
    for layer in active_layers or []:
        source_id = _text(layer.get("source_id"))
        title = _text(layer.get("title") or source_id)
        entry = by_id.get(source_id)
        if not entry:
            findings.append({
                "key": "fs_ingest_inventory_missing",
                "severity": "warn",
                "source_id": source_id,
                "title": title,
                "line": f"{title}: ingest inventory missing - verdicts leaning on this source are partial",
                "next_step": "Write fs_ingest_inventory.json for this active FundStrat layer before treating it as fully checked.",
            })
            continue
        skipped = int(entry.get("skipped_count") or 0)
        total = int(entry.get("total_sections") or len(entry.get("sections") or []))
        if skipped > 0:
            skipped_names = [
                str(section.get("name") or "")
                for section in entry.get("sections") or []
                if section.get("status") == "skipped"
            ]
            findings.append({
                "key": "fs_ingest_partial",
                "severity": "warn",
                "source_id": source_id,
                "title": title,
                "skipped_count": skipped,
                "total_sections": total,
                "skipped_sections": skipped_names,
                "line": f"{title}: {skipped} of {total} sections never distilled - verdicts leaning on this source are partial",
                "next_step": (
                    "Distill or mark empty the skipped section(s): "
                    + ", ".join(skipped_names[:8])
                    + ("." if len(skipped_names) <= 8 else f" +{len(skipped_names) - 8}.")
                ),
            })
    return findings


def findings_for_bible(inventory: Any, bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    return check(inventory, active_bible_layers(bible))


def bible_upload_inventory_entries(deck: dict[str, Any], summary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build inventory entries for a direct monthly/Bible upload.

    Parser-produced sections are "distilled"; sections absent from the compact
    output are "skipped" because the current parser cannot prove the source
    lacked them.
    """
    summary = summary if isinstance(summary, dict) else {}
    deck_date = _text(deck.get("deck_date") or summary.get("deck_date"))
    entries: list[dict[str, Any]] = []
    sector = deck.get("sector_allocation") if isinstance(deck.get("sector_allocation"), dict) else {}
    if sector:
        sector_date = _text(sector.get("as_of") or deck_date)
        sector_sections = []
        for key, label in (
            ("newton_rating_changes", "Newton rating changes"),
            ("agreement", "Lee/Newton agreement"),
            ("june_etf_basket", "June ETF basket"),
            ("may_basket_grade", "May basket grade"),
            ("named_levels", "named levels"),
        ):
            sector_sections.append(_section(label, "distilled" if sector.get(key) else "skipped"))
        tactical_done = bool(sector.get("tactical_top3")) and bool(sector.get("tactical_bottom3"))
        sector_sections.append(_section("tactical top/bottom", "distilled" if tactical_done else "skipped"))
        entries.append(normalize_entry({
            "source_id": _source_id("fundstrat_sector_allocation", sector_date),
            "title": f"Fundstrat Sector Allocation {sector_date}" if sector_date else "Fundstrat Sector Allocation",
            "ingested_at": _text(summary.get("generated_at")) or _now_iso(),
            "sections": sector_sections,
        }))
    sections = []
    for key, label in (
        ("macro_stance", "macro stance"),
        ("what_to_own", "what to own"),
        ("consider", "consider list"),
        ("top5", "large-cap top 5"),
        ("bottom5", "large-cap bottom 5"),
        ("top5_smid", "SMID top 5"),
        ("bottom5_smid", "SMID bottom 5"),
    ):
        sections.append(_section(label, "distilled" if deck.get(key) else "skipped"))
    entries.append(normalize_entry({
        "source_id": _source_id("fundstrat_core_stock_ideas", deck_date),
        "title": f"Fundstrat Core Stock Ideas {deck_date}" if deck_date else "Fundstrat Core Stock Ideas",
        "ingested_at": _text(summary.get("generated_at")) or _now_iso(),
        "sections": sections,
    }))
    return entries


def daily_note_inventory_entries(entries: list[dict[str, Any]], *, ingested_at: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in entries or []:
        if not isinstance(row, dict):
            continue
        source_id = _text(row.get("message_id") or row.get("source_message_id"))
        if not source_id:
            digest = hashlib.sha256(
                "|".join(_text(row.get(key)) for key in ("date", "author", "subject")).encode("utf-8")
            ).hexdigest()[:12]
            source_id = f"fundstrat_note:{digest}"
        title = _text(row.get("subject")) or f"Fundstrat note {source_id}"
        full_body = (
            bool(row.get("body_fetched"))
            or _text(row.get("body_source")) in {"body", "text", "compact_full_body_derived"}
            or int(row.get("body_chars") or 0) > 0
        )
        out.append(normalize_entry({
            "source_id": source_id,
            "title": title,
            "ingested_at": ingested_at or _now_iso(),
            "sections": [
                _section("full body", "distilled" if full_body else "skipped"),
                _section("decision-call extraction", "distilled" if full_body else "skipped"),
            ],
        }))
    return out
