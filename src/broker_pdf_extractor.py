#!/usr/bin/env python3
"""Conservative broker-position PDF/text extractor.

This is the first repo-owned extractor stage for broker position uploads. It is
deliberately narrow: it extracts selectable PDF text when pypdf is available,
parses rows that begin with an explicit ticker, and marks each file failed when
the text or row confidence is insufficient. Downstream cache writers already
honor validation.passed == False under --strict.
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


TICKER_RE = re.compile(r"^[A-Z]{1,6}(?:\.[A-Z]{1,4})?$")
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2})\b")
ACCOUNT_RE = re.compile(r"\b(?:account|acct)\s*(?:name|number|#)?\s*[:\-]\s*(.+)$", re.I)
MONEY_RE = re.compile(r"\(?\$?\s*-?\d[\d,]*(?:\.\d{2})?\)?")
NUMBER_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")

HEADER_WORDS = {
    "symbol", "ticker", "description", "quantity", "qty", "price", "value",
    "market", "cash", "account", "holdings", "positions", "total",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _num(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    neg = text.startswith("(") and text.endswith(")")
    text = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
    if not text:
        return None
    try:
        n = float(text)
    except ValueError:
        return None
    return -n if neg else n


def _date_iso(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.match(r"^20\d{2}-\d{2}-\d{2}$", text):
        return text
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(20\d{2})$", text)
    if not m:
        return None
    month, day, year = m.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _ticker_token(line: str) -> str | None:
    parts = line.strip().split()
    if not parts:
        return None
    token = parts[0].strip().upper().replace("$", "")
    if token.lower() in HEADER_WORDS:
        return None
    return token if TICKER_RE.match(token) and token not in {"CASH", "USD"} else None


def _is_noise_line(line: str) -> bool:
    text = line.strip().lower()
    if not text:
        return True
    if any(text.startswith(word) for word in ("page ", "total ", "cash ", "account ")):
        return True
    return False


def infer_account_name(text: str, source_file: str) -> str:
    for line in text.splitlines():
        m = ACCOUNT_RE.search(line.strip())
        if m:
            account = " ".join(m.group(1).split())
            if account:
                return account[:120]
    stem = Path(source_file).stem.replace("_", " ").replace("-", " ").strip()
    return stem or "Unknown"


def infer_broker(source_file: str, text: str = "") -> str:
    low = f"{source_file} {text[:2000]}".lower()
    for broker in ("fidelity", "schwab", "robinhood", "etrade", "vanguard"):
        if broker in low:
            return broker.title()
    return "Unknown"


def infer_as_of(text: str, fallback: str | None = None) -> str:
    for match in DATE_RE.finditer(text or ""):
        iso = _date_iso(match.group(1))
        if iso:
            return iso
    return fallback or datetime.now(timezone.utc).date().isoformat()


def infer_cash(text: str) -> float:
    for line in text.splitlines():
        low = line.lower()
        if "cash" not in low:
            continue
        values = [_num(m.group(0)) for m in MONEY_RE.finditer(line)]
        values = [v for v in values if v is not None]
        if values:
            return float(values[-1])
    return 0.0


def parse_position_lines(text: str, *, account_name: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    for raw_line in (text or "").splitlines():
        line = " ".join(raw_line.split())
        if _is_noise_line(line):
            continue
        ticker = _ticker_token(line)
        if not ticker:
            continue
        money_matches = list(MONEY_RE.finditer(line))
        if not money_matches:
            continue
        market_value = _num(money_matches[-1].group(0))
        if market_value is None or market_value <= 0:
            continue

        before_value = line[:money_matches[-1].start()].strip()
        tokens_after_ticker = before_value.split()[1:]
        quantity: float | None = None
        quantity_idx: int | None = None
        for idx, token in enumerate(tokens_after_ticker):
            cleaned = token.replace(",", "")
            if NUMBER_RE.match(cleaned):
                quantity = _num(cleaned)
                quantity_idx = idx
                break
        if quantity is None:
            continue
        desc_tokens = tokens_after_ticker[:quantity_idx]
        description = " ".join(desc_tokens).strip()
        key = (ticker, round(quantity, 6), round(market_value, 2))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "symbol": ticker,
            "description": description,
            "quantity": quantity,
            "market_value": market_value,
            "account_name": account_name or "Unknown",
        })
    return rows


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


def extract_file(path: str | Path, *, as_of: str | None = None) -> dict[str, Any]:
    p = Path(path)
    text, error = extract_text(p)
    account = infer_account_name(text, str(p))
    positions = parse_position_lines(text, account_name=account)
    passed = bool(text.strip()) and bool(positions) and error is None
    validation = {
        "passed": passed,
        "text_chars": len(text or ""),
        "positions_found": len(positions),
    }
    if error:
        validation["error"] = error
    if text.strip() and not positions:
        validation["error"] = "no confident ticker-led position rows found"
    return {
        "source_file": str(p),
        "broker": infer_broker(str(p), text),
        "positions_scope": "per_account",
        "account_name": account,
        "as_of": infer_as_of(text, fallback=as_of),
        "extraction_method": "pypdf_text" if p.suffix.lower() == ".pdf" else "plain_text",
        "validation": validation,
        "positions": positions,
    }


def build_combined(paths: list[str | Path], *, as_of: str | None = None,
                   generated_at: str | None = None) -> dict[str, Any]:
    files = [extract_file(path, as_of=as_of) for path in paths]
    total_market_value = sum(
        float(pos.get("market_value") or 0.0)
        for file_row in files
        for pos in file_row.get("positions", []) or []
    )
    total_cash = 0.0
    for path in paths:
        text, _ = extract_text(path)
        total_cash += infer_cash(text)
    dates = sorted({f.get("as_of") for f in files if f.get("as_of")})
    warnings = [
        f"{f.get('source_file')}: {f.get('validation', {}).get('error') or 'validation failed'}"
        for f in files
        if not (f.get("validation") or {}).get("passed")
    ]
    return {
        "schema_version": "2.0",
        "generated_at": generated_at or _utc_now_iso(),
        "extractor": "broker_pdf_extractor",
        "files": files,
        "portfolio_summary": {
            "total_market_value": round(total_market_value, 2),
            "total_cash": round(total_cash, 2),
            "as_of": (dates[-1] if dates else (as_of or datetime.now(timezone.utc).date().isoformat())),
        },
        "warnings": warnings,
    }


def validate_combined(combined: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(combined, dict):
        return ["top-level must be an object"]
    files = combined.get("files")
    if not isinstance(files, list) or not files:
        problems.append("files must be a non-empty list")
        return problems
    for idx, file_row in enumerate(files):
        if not isinstance(file_row, dict):
            problems.append(f"files[{idx}] must be an object")
            continue
        validation = file_row.get("validation")
        if not isinstance(validation, dict):
            problems.append(f"files[{idx}].validation must be an object")
        positions = file_row.get("positions")
        if not isinstance(positions, list):
            problems.append(f"files[{idx}].positions must be a list")
            continue
        for j, row in enumerate(positions):
            if not isinstance(row, dict):
                problems.append(f"files[{idx}].positions[{j}] must be an object")
                continue
            if not TICKER_RE.match(str(row.get("symbol") or "")):
                problems.append(f"files[{idx}].positions[{j}].symbol invalid")
            for field in ("quantity", "market_value"):
                value = row.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    problems.append(f"files[{idx}].positions[{j}].{field} must be numeric")
    return problems


def _read_json(path: str | Path, default=None):
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".broker_pdf_extractor.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


def _self_test() -> int:
    text = "\n".join([
        "Account: SKB Fidelity Taxable",
        "Statement Date 06/05/2026",
        "Symbol Description Quantity Last Price Market Value",
        "NVDA NVIDIA CORP 12 170.00 $2,040.00",
        "GOOGL ALPHABET INC 4 180.00 $720.00",
        "Cash Core $100.00",
    ])
    rows = parse_position_lines(text, account_name="SKB Fidelity Taxable")
    assert [r["symbol"] for r in rows] == ["NVDA", "GOOGL"], rows
    assert rows[0]["quantity"] == 12
    assert rows[0]["market_value"] == 2040.0
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "skb_fidelity.txt"
        p.write_text(text, encoding="utf-8")
        combined = build_combined([p], as_of="2026-06-05", generated_at="2026-06-05T14:00:00Z")
        assert validate_combined(combined) == []
        assert combined["files"][0]["validation"]["passed"] is True
        assert combined["portfolio_summary"]["total_market_value"] == 2760.0
        assert combined["portfolio_summary"]["total_cash"] == 100.0
    print("broker_pdf_extractor self-test: PASS")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extract text-based broker PDFs into combined.json")
    parser.add_argument("inputs", nargs="*", help="Broker PDFs or plain text exports")
    parser.add_argument("--out", help="Write combined extractor JSON")
    parser.add_argument("--as-of", help="Fallback snapshot date")
    parser.add_argument("--generated-at")
    parser.add_argument("--validate", help="Validate an existing combined.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.validate:
        problems = validate_combined(_read_json(args.validate, {}))
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
        return 0 if not problems else 2
    if not args.inputs:
        parser.error("provide at least one PDF/text input or use --self-test/--validate")

    combined = build_combined(args.inputs, as_of=args.as_of, generated_at=args.generated_at)
    problems = validate_combined(combined)
    if args.out:
        _atomic_write_json(args.out, combined)
    print(json.dumps({
        "extracted": True,
        "files": len(combined["files"]),
        "positions": sum(len(f.get("positions", []) or []) for f in combined["files"]),
        "failed_files": len([f for f in combined["files"] if not f.get("validation", {}).get("passed")]),
        "valid_shape": not problems,
        "written": args.out or None,
    }, indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
