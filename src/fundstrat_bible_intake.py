#!/usr/bin/env python3
"""Direct-upload Fundstrat monthly/Bible intake.

Monthly Fundstrat updates arrive as uploaded PDFs, not daily emails. This
parser converts selectable-text PDFs, text exports, or already-structured JSON
decks into the existing `fundstrat_bible.json` contract consumed by
fundstrat_bible.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BLACKLIST = {
    "AI", "API", "CEO", "CFO", "CPI", "ETF", "EPS", "EU", "FOMC", "GDP",
    "IPO", "PMI", "QOQ", "SEC", "THE", "USA", "USD", "VIX", "YOY",
    "BUY", "SELL", "LONG", "SHORT", "CALL", "PUT", "PUTS", "CALLS",
}

RE_BARE = re.compile(r"\b([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\b")
RE_CASHTAG = re.compile(r"\$([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\b")
RE_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}|20\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2})\b")
RE_SECTION = re.compile(
    r"\b(?P<label>"
    r"macro\s+stance|market\s+stance|investment\s+stance|"
    r"what[-\s]+to[-\s]+own|sectors?\s+to\s+own|"
    r"core\s+lists?|consider\s+lists?|"
    r"top[-\s]*5|top\s+five|bottom[-\s]*5|bottom\s+five"
    r")\b\s*[:\-\u2013\u2014]\s*(?P<body>.*?)(?=\b(?:"
    r"macro\s+stance|market\s+stance|investment\s+stance|"
    r"what[-\s]+to[-\s]+own|sectors?\s+to\s+own|"
    r"core\s+lists?|consider\s+lists?|"
    r"top[-\s]*5|top\s+five|bottom[-\s]*5|bottom\s+five"
    r")\b\s*[:\-\u2013\u2014]|$)",
    re.I | re.S,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_iso(value: str | None, fallback: str | None = None) -> str:
    text = str(value or "").strip()
    if re.match(r"^20\d{2}-\d{2}-\d{2}$", text):
        return text
    if re.match(r"^20\d{2}-\d{2}$", text):
        return text
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(20\d{2})$", text)
    if m:
        month, day, year = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return fallback or datetime.now(timezone.utc).date().isoformat()


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_bible.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


def _extract_pdf_text(path: Path) -> tuple[str, str | None]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        return "", f"pypdf unavailable: {exc}"
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages), None
    except Exception as exc:
        return "", f"pdf text extraction failed: {exc}"


def extract_text(path: str | Path) -> tuple[str, str | None]:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return _extract_pdf_text(p)
    try:
        return p.read_text(encoding="utf-8", errors="replace"), None
    except Exception as exc:
        return "", f"text read failed: {exc}"


def _clean(text: Any) -> str:
    text = re.sub(r"^[\s\-\u2022*]+", "", str(text or ""))
    return " ".join(text.split()).strip(" ;,")


def _section_key(label: str) -> str | None:
    low = " ".join(str(label or "").lower().replace("-", " ").split())
    if low in {"macro stance", "market stance", "investment stance"}:
        return "macro_stance"
    if low in {"what to own", "sector to own", "sectors to own"}:
        return "what_to_own"
    if low in {"consider list", "consider lists"}:
        return "consider"
    if low in {"top 5", "top five", "top5"}:
        return "top5"
    if low in {"bottom 5", "bottom five", "bottom5"}:
        return "bottom5"
    return None


def _split_items(text: str) -> list[str]:
    raw = str(text or "")
    if ";" in raw or "\n" in raw:
        parts = re.split(r"[;\n]+", raw)
    else:
        parts = re.split(r",\s*(?=\$?[A-Z][A-Z0-9.]{0,6}\b|[A-Z][a-z])", raw)
    return [item for item in (_clean(p) for p in parts) if item]


def _sector_items(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in _split_items(text):
        item = re.sub(r"\s+[-\u2013\u2014:]\s+.*$", "", item).strip()
        if not item or item.upper() in BLACKLIST:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _ticker_item(text: str) -> str | dict | None:
    item = _clean(text)
    if not item:
        return None
    m = RE_CASHTAG.search(item) or RE_BARE.search(item)
    if not m:
        return None
    ticker = m.group(1).upper()
    if ticker in BLACKLIST:
        return None
    note = _clean(item[m.end():])
    note = re.sub(r"^[-\u2013\u2014:]\s*", "", note).strip()
    note = _useful_note(note)
    if note:
        return {"ticker": ticker, "note": note}
    return ticker


def _useful_note(note: str) -> str:
    note = _clean(note)
    if not note:
        return ""
    low = note.lower()
    if any(word in low for word in ("chart", "figure", "source:", "performance table")):
        return ""
    if len(note) > 140:
        return ""
    numeric_tokens = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", note))
    if numeric_tokens > 4:
        return ""
    return note


def _ticker_items(text: str) -> list[str | dict]:
    out: list[str | dict] = []
    seen: set[str] = set()
    for item in _split_items(text):
        parsed = _ticker_item(item)
        if not parsed:
            continue
        ticker = parsed["ticker"] if isinstance(parsed, dict) else parsed
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append(parsed)
    return out


def _cashtag_items(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for ticker in RE_CASHTAG.findall(text or ""):
        ticker = ticker.upper()
        if ticker in BLACKLIST or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def _large_cap_idea_lists(text: str) -> dict[str, list[str]]:
    title = re.search(r"Top\s*5\s+and\s+Bottom\s*5\s+Large[-\s]+cap\s+Core\s+Ideas", text or "", re.I)
    if not title:
        return {}
    segment = text[title.end():]
    bottom_label = re.search(r"Bottom\s*5\s+Large[-\s]+cap\s+ideas", segment, re.I)
    if not bottom_label:
        return {}
    top_label = re.search(r"Top\s*5\s+Large[-\s]+cap\s+ideas", segment[bottom_label.end():], re.I)
    if not top_label:
        return {}
    bottom_block = segment[:bottom_label.start()]
    top_block = segment[bottom_label.end():bottom_label.end() + top_label.start()]
    out = {
        "bottom5": _cashtag_items(bottom_block),
        "top5": _cashtag_items(top_block),
    }
    return {k: v for k, v in out.items() if v}


def _infer_date(text: str, fallback: str | None = None) -> str:
    match = RE_DATE.search(text or "")
    if match:
        return _date_iso(match.group(1), fallback=fallback)
    return fallback or datetime.now(timezone.utc).date().isoformat()


def parse_bible_text(text: str, *, source_file: str = "", as_of: str | None = None) -> dict:
    deck = {
        "deck_date": _infer_date(text, fallback=as_of),
        "macro_stance": [],
        "what_to_own": [],
        "consider": [],
        "top5": [],
        "bottom5": [],
    }
    seen = {"macro_stance": set(), "what_to_own": set(), "consider": set(), "top5": set(), "bottom5": set()}

    def add(key: str, values: list[Any]) -> None:
        for value in values:
            if not value:
                continue
            marker = (
                str(value.get("ticker") or value.get("sector") or value.get("note") or "").upper()
                if isinstance(value, dict)
                else str(value).upper()
            )
            if not marker or marker in seen[key]:
                continue
            seen[key].add(marker)
            deck[key].append(value)

    for match in RE_SECTION.finditer(text or ""):
        key = _section_key(match.group("label"))
        body = _clean(match.group("body"))
        if not key or not body:
            continue
        if key == "macro_stance":
            add(key, [body])
        elif key == "what_to_own":
            add(key, _sector_items(body))
        elif key == "consider":
            add(key, _ticker_items(body))
        else:
            add(key, _ticker_items(body))

    ideas = _large_cap_idea_lists(text or "")
    for key in ("top5", "bottom5"):
        if not deck[key] and ideas.get(key):
            add(key, ideas[key])

    if len(deck["macro_stance"]) == 1:
        deck["macro_stance"] = deck["macro_stance"][0]
    if source_file:
        deck["source_file"] = source_file
    return {k: v for k, v in deck.items() if v not in ([], "", None)}


def normalize_deck(deck: dict, *, source_file: str = "", as_of: str | None = None) -> dict:
    out = {
        "deck_date": str(deck.get("deck_date") or as_of or datetime.now(timezone.utc).date().isoformat()),
    }
    if deck.get("macro_stance"):
        out["macro_stance"] = deck["macro_stance"]
    if deck.get("what_to_own"):
        out["what_to_own"] = deck["what_to_own"]
    if deck.get("consider"):
        out["consider"] = deck["consider"]
    for key in ("top5", "bottom5"):
        if deck.get(key):
            out[key] = deck[key]
    if source_file:
        out["source_file"] = source_file
    return out


def validate_bible_deck(deck: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(deck, dict):
        return ["deck must be an object"]
    if not deck.get("deck_date"):
        problems.append("deck_date missing")
    if not any(deck.get(k) for k in ("macro_stance", "what_to_own", "consider", "top5", "bottom5")):
        problems.append("no stance, what_to_own, consider, top5, or bottom5 sections found")
    for key in ("consider", "top5", "bottom5"):
        for idx, item in enumerate(deck.get(key) or []):
            ticker = item.get("ticker") if isinstance(item, dict) else item
            if not RE_BARE.fullmatch(str(ticker or "").upper()):
                problems.append(f"{key}[{idx}] ticker invalid")
    return problems


def merge_decks(existing: dict | None, new: dict) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    out = {"deck_date": max(str(existing.get("deck_date") or ""), str(new.get("deck_date") or ""))}

    def as_list(value):
        if value in (None, ""):
            return []
        return value if isinstance(value, list) else [value]

    def merge_items(key: str, marker_key: str | None = None) -> list:
        merged = []
        seen = set()
        for value in as_list(existing.get(key)) + as_list(new.get(key)):
            if isinstance(value, dict):
                marker = str(value.get(marker_key or "ticker") or value.get("note") or "").upper()
            else:
                marker = str(value).upper()
            if not marker or marker in seen:
                continue
            seen.add(marker)
            merged.append(value)
        return merged

    macro = merge_items("macro_stance")
    if len(macro) == 1:
        out["macro_stance"] = macro[0]
    elif macro:
        out["macro_stance"] = macro
    sectors = merge_items("what_to_own", "sector")
    if sectors:
        out["what_to_own"] = sectors
    for key in ("consider", "top5", "bottom5"):
        items = merge_items(key, "ticker")
        if items:
            out[key] = items
    if new.get("source_file"):
        out["source_file"] = new["source_file"]
    elif existing.get("source_file"):
        out["source_file"] = existing["source_file"]
    return out


def load_deck_from_path(path: str | Path, *, as_of: str | None = None) -> tuple[dict, dict]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        payload = _read_json(p, default={})
        deck = payload.get("fundstrat_bible") if isinstance(payload, dict) else None
        if deck is None:
            deck = payload
        deck = normalize_deck(deck if isinstance(deck, dict) else {}, source_file=str(p), as_of=as_of)
        return deck, {"source_file": str(p), "input_type": "json", "text_chars": 0, "error": ""}

    text, error = extract_text(p)
    deck = parse_bible_text(text, source_file=str(p), as_of=as_of)
    return deck, {
        "source_file": str(p),
        "input_type": "pdf" if p.suffix.lower() == ".pdf" else "text",
        "text_chars": len(text or ""),
        "error": error or "",
    }


def build_deck_from_paths(paths: list[str | Path], *, as_of: str | None = None,
                          merge_existing: dict | None = None) -> tuple[dict, dict]:
    deck = merge_existing if isinstance(merge_existing, dict) else {}
    files = []
    for path in paths:
        next_deck, info = load_deck_from_path(path, as_of=as_of)
        files.append({**info, "sections": [k for k in ("macro_stance", "what_to_own", "consider", "top5", "bottom5") if next_deck.get(k)]})
        if next_deck:
            deck = merge_decks(deck, next_deck) if deck else next_deck
    problems = validate_bible_deck(deck)
    summary = {
        "generated_at": _utc_now_iso(),
        "source": "fundstrat_bible_intake",
        "files": files,
        "valid": not problems,
        "problems": problems,
        "top5": len(deck.get("top5") or []),
        "bottom5": len(deck.get("bottom5") or []),
        "consider": len(deck.get("consider") or []),
        "what_to_own": len(deck.get("what_to_own") or []),
    }
    return deck, summary


def update_top_prospects_from_bible(deck: dict, path: str | Path, *,
                                    generated_at: str | None = None) -> dict:
    picks = []
    try:
        from top_prospects_feeder import Pick, load_cache, merge_picks, recompute, save_cache
    except Exception as exc:
        return {"updated": False, "picks": 0, "error": str(exc)}

    date_s = str(deck.get("deck_date") or (generated_at or "")[:10] or "")
    for key, direction, provenance, category_hint in (
        ("top5", "long", "FS Top 5", None),
        ("bottom5", "avoid", "FS Bottom 5", None),
        ("consider", "long", "FS Consider List", "consider_list"),
    ):
        for item in deck.get(key) or []:
            ticker = item.get("ticker") if isinstance(item, dict) else item
            ticker = str(ticker or "").strip().upper()
            if not ticker:
                continue
            picks.append(Pick(
                ticker=ticker,
                analyst="Fundstrat",
                date=date_s,
                direction=direction,
                report_type="monthly",
                provenance=f"{provenance} - {date_s}" if date_s else provenance,
                substantive=isinstance(item, dict) and bool(item.get("note")),
                category_hint=category_hint,
            ))
    if not picks:
        return {"updated": False, "picks": 0}
    cache_path = Path(path)
    cache = load_cache(cache_path)
    cache = merge_picks(cache, picks)
    cache = recompute(cache, now=(generated_at or "")[:10] or None)
    save_cache(cache, cache_path)
    return {"updated": True, "picks": len(picks), "path": str(cache_path)}


def write_outputs(deck: dict, summary: dict, *, out: str | Path,
                  summary_path: str | Path | None = None,
                  top_prospects_path: str | Path | None = None) -> dict:
    written = {
        "fundstrat_bible": str(_atomic_write_json(out, deck)),
    }
    if top_prospects_path:
        top_summary = update_top_prospects_from_bible(
            deck,
            top_prospects_path,
            generated_at=summary.get("generated_at"),
        )
        summary["top_prospects"] = top_summary
        if top_summary.get("updated"):
            written["top_prospects"] = str(top_prospects_path)
    if summary_path:
        written["fundstrat_bible_intake_summary"] = str(_atomic_write_json(summary_path, summary))
    return written


def _self_test() -> int:
    text = "\n".join([
        "Fundstrat Monthly Strategy 2026-06",
        "Macro Stance: Risk-on, buy dips into mid-year.",
        "What to Own: Technology, Industrials, Financials",
        "Core List: ANET - AI networking; VRT",
        "Top 5: NVDA - secular AI leader; GOOGL; GS",
        "Bottom 5: XYZ; ABC - funding source",
    ])
    deck = parse_bible_text(text, source_file="monthly.txt")
    assert deck["deck_date"] == "2026-06"
    assert deck["macro_stance"] == "Risk-on, buy dips into mid-year."
    assert deck["what_to_own"] == ["Technology", "Industrials", "Financials"]
    assert "core_list" not in deck
    assert "consider" not in deck
    assert deck["top5"][0] == {"ticker": "NVDA", "note": "secular AI leader"}
    assert deck["bottom5"][1] == {"ticker": "ABC", "note": "funding source"}
    assert validate_bible_deck(deck) == []
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "monthly.txt"
        out = Path(d) / "fundstrat_bible.json"
        p.write_text(text, encoding="utf-8")
        built, summary = build_deck_from_paths([p], as_of="2026-06")
        write_outputs(built, summary, out=out, summary_path=Path(d) / "summary.json")
        assert out.is_file()
    print("fundstrat_bible_intake self-test: PASS")
    return 0


def main(argv=None) -> int:
    src = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Parse direct Fundstrat monthly PDF/text uploads")
    parser.add_argument("inputs", nargs="*", help="Fundstrat monthly PDFs, text exports, or JSON deck files")
    parser.add_argument("--out", default=str(src / "fundstrat_bible.json"))
    parser.add_argument("--summary", default=str(src / "fundstrat_bible_intake_summary.json"))
    parser.add_argument("--top-prospects", nargs="?", const=str(src / "top_prospects.json"))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--as-of")
    parser.add_argument("--validate", help="Validate an existing fundstrat_bible.json")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.validate:
        problems = validate_bible_deck(_read_json(args.validate, default={}))
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
        return 0 if not problems else 2
    if not args.inputs:
        parser.error("provide at least one monthly PDF/text/JSON input or use --validate/--self-test")

    existing = _read_json(args.out, default={}) if args.merge_existing else None
    deck, summary = build_deck_from_paths(args.inputs, as_of=args.as_of, merge_existing=existing)
    written = {} if args.dry_run else write_outputs(
        deck,
        summary,
        out=args.out,
        summary_path=args.summary,
        top_prospects_path=args.top_prospects,
    )
    print(json.dumps({"parsed": True, **summary, "written": written}, indent=2))
    return 0 if summary["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
