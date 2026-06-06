#!/usr/bin/env python3
"""Conservative broker-position PDF/text extractor.

This is the first repo-owned extractor stage for broker position uploads. It is
deliberately narrow: it extracts selectable PDF text when pypdf is available,
parses only high-confidence selectable-text rows, and marks each file failed
when the text or row confidence is insufficient. Downstream cache writers
already honor validation.passed == False under --strict.
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
CURRENCY_RE = re.compile(r"\(?\$\s*-?\d[\d,]*(?:\.\d+)?\)?")
NUMBER_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
PERCENT_RE = re.compile(r"^[+\-]?\d[\d,]*(?:\.\d+)?%$")

HEADER_WORDS = {
    "symbol", "ticker", "description", "quantity", "qty", "price", "value",
    "market", "cash", "account", "holdings", "positions", "total",
}
SECURITY_WORDS = {
    "INC", "CORP", "LTD", "PLC", "CO", "COMPANY", "CLASS", "CL", "COM",
    "ETF", "ETN", "FUND", "TRUST", "ISHARES", "VANGUARD", "FIDELITY",
    "SCHWAB", "SPDR", "INVESCO", "ISH", "ADR", "ORD", "UNIT",
    "THE", "MARCH", "SHARES", "SHARE", "RATINGS", "MORE", "PRICE",
    "TECNOL", "LARG", "SMAL",
}
CONCAT_DESCRIPTION_STARTERS = (
    "ACOUSTIS", "ADVISORSHARES", "ALPHABET", "AMAZON", "ARDEA", "ASML",
    "AST", "BITMINE", "BLOOM", "BROADCOM", "BWX", "CAMECO", "CENTRUS",
    "CIES", "COINBASE", "COMFORT", "DAN", "ENERGY", "FABRINET",
    "FIDELITY", "FIRST", "FUCORE", "FUNDSTRAT", "GE", "GLOBAL",
    "GOLDMAN", "HELD", "ISHARES", "INTUITIVE", "INVESCO", "JPMORGAN",
    "LUMENTUM", "LYNAS", "MICROSOFT", "MICRON", "MP", "NEBIUS",
    "NVIDIA", "NEXTPOWER", "ORACLE", "PALANTIR", "PERSHING", "POET",
    "QUANTA", "REDDIT", "ROUNDHILL", "SELECT", "SOFI", "STATE",
    "STERLING", "TALON", "TEMA", "TEMPUS", "TIDAL", "UNUSUAL", "VANECK",
    "WEDBUSH", "WHEATON",
)


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
    return token if _looks_like_ticker(token) else None


def _clean_token(token: str) -> str:
    return token.strip().upper().strip(",:;()[]{}").replace("$", "")


def _symbol_from_token(token: str) -> str | None:
    cleaned = _clean_token(token)
    if _looks_like_ticker(cleaned):
        return cleaned
    if cleaned.isalpha():
        return None
    matches = re.findall(r"[A-Z]{1,6}(?:\.[A-Z]{1,4})?", cleaned)
    for match in reversed(matches):
        if _looks_like_ticker(match):
            return match
    return None


def _looks_like_ticker(token: str) -> bool:
    token = _clean_token(token)
    if token.lower() in HEADER_WORDS or token in SECURITY_WORDS or token in {"CASH", "USD"}:
        return False
    return bool(TICKER_RE.match(token))


def _is_noise_line(line: str) -> bool:
    text = line.strip().lower()
    if not text:
        return True
    if any(text.startswith(word) for word in ("page ", "total ", "cash ", "account ")):
        return True
    if text in {"--", "?", "? ?", "good"}:
        return True
    return False


def _looks_like_fidelity_portfolio_pdf(text: str) -> bool:
    low = (text or "").lower()
    return (
        "digital.fidelity.com" in low
        and "portfolio positions" in low
        and "currentvalue" in low
    )


def _looks_like_schwab_account_pdf(text: str) -> bool:
    low = (text or "").lower()
    return (
        "client.schwab.com" in low
        or ("symbol / name" in low and "ratings" in low and "reinvest" in low)
    )


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


def _first_money_value(line: str) -> float | None:
    match = CURRENCY_RE.search(line or "")
    return _num(match.group(0)) if match else None


def _split_leading_concatenated_symbol(token: str) -> tuple[str, str] | None:
    cleaned = _clean_token(token)
    if not cleaned.isalpha() or len(cleaned) <= 6:
        return None
    for idx in range(min(6, len(cleaned) - 2), 0, -1):
        symbol = cleaned[:idx]
        description_start = cleaned[idx:]
        if not _looks_like_ticker(symbol):
            continue
        if any(description_start.startswith(starter) for starter in CONCAT_DESCRIPTION_STARTERS):
            return symbol, description_start
    return None


def _quantity_before_first_money(line: str) -> tuple[float, list[str]] | None:
    money = CURRENCY_RE.search(line or "")
    if not money:
        return None
    before = line[:money.start()].strip()
    tokens = before.split()
    if len(tokens) < 2:
        return None
    quantity = _num(tokens[-1])
    if quantity is None:
        return None
    return quantity, tokens[:-1]


def _position_from_robinhood_line(line: str, *, account_name: str | None = None) -> dict[str, Any] | None:
    money_matches = list(MONEY_RE.finditer(line or ""))
    if len(money_matches) < 4:
        return None
    market_value = _num(money_matches[-1].group(0))
    if market_value is None or market_value <= 0:
        return None
    quantity_info = _quantity_before_first_money(line)
    if not quantity_info:
        return None
    quantity, before_quantity_tokens = quantity_info
    if not before_quantity_tokens:
        return None
    symbol = _symbol_from_token(before_quantity_tokens[-1])
    if not symbol:
        return None
    description = " ".join(before_quantity_tokens[:-1]).strip()
    if not description:
        return None
    return {
        "symbol": symbol,
        "description": description,
        "quantity": quantity,
        "market_value": market_value,
        "account_name": account_name or "Unknown",
    }


def _position_from_schwab_compact_line(
    line: str,
    next_line: str,
    *,
    account_name: str | None = None,
) -> dict[str, Any] | None:
    quantity_info = _quantity_before_first_money(line)
    if not quantity_info:
        return None
    quantity, before_quantity_tokens = quantity_info
    if not before_quantity_tokens:
        return None
    first = before_quantity_tokens[0]
    split = _split_leading_concatenated_symbol(first)
    if split:
        symbol, first_description = split
        description_tokens = [first_description] + before_quantity_tokens[1:]
    else:
        symbol = _symbol_from_token(first)
        description_tokens = before_quantity_tokens[1:]
    if not symbol or not description_tokens:
        return None
    market_value = _first_money_value(next_line)
    if market_value is None or market_value <= 0:
        return None
    return {
        "symbol": symbol,
        "description": " ".join(description_tokens).strip(),
        "quantity": quantity,
        "market_value": market_value,
        "account_name": account_name or "Unknown",
    }


def _parse_schwab_lines(text: str, *, account_name: str | None = None) -> list[dict[str, Any]]:
    source_lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    lines = [line for line in source_lines if line and not _is_noise_line(line)]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    consumed: set[int] = set()
    for idx, line in enumerate(lines):
        if idx in consumed:
            continue
        if idx + 1 >= len(lines):
            continue
        low = line.lower()
        if (
            "total" in low
            or "symbol / name" in low
            or line.startswith("(")
            or PERCENT_RE.match(_clean_token(line))
        ):
            continue

        row: dict[str, Any] | None = None
        symbol = _symbol_from_token(line)
        if symbol and line.strip() == symbol and idx + 2 < len(lines):
            row = _position_from_schwab_compact_line(
                f"{symbol} {lines[idx + 1]}",
                lines[idx + 2],
                account_name=account_name,
            )
            if row:
                consumed.update({idx + 1, idx + 2})
        else:
            row = _position_from_schwab_compact_line(line, lines[idx + 1], account_name=account_name)

        if not row:
            continue
        key = (row["symbol"], round(row["quantity"], 6), round(row["market_value"], 2))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _position_from_line(line: str, *, account_name: str | None = None) -> dict[str, Any] | None:
    """Parse one selectable-text position row.

    Accepts both ticker-led rows ("NVDA NVIDIA 12 ... $2,040") and broker rows
    where the description precedes the symbol ("NVIDIA CORP NVDA 12 ...").
    A candidate ticker must be followed by a numeric quantity and a positive
    market value, keeping image/OCR/no-symbol text as an honest failure.
    """
    tokens = line.split()
    if not tokens:
        return None
    money_matches = list(MONEY_RE.finditer(line))
    if not money_matches:
        return None
    market_value = _num(money_matches[-1].group(0))
    if market_value is None or market_value <= 0:
        return None

    before_value = line[:money_matches[-1].start()].strip()
    tokens_before_value = before_value.split()
    candidates: list[tuple[int, int, str, float, int]] = []
    for ticker_idx, token in enumerate(tokens_before_value):
        ticker = _symbol_from_token(token)
        if not ticker:
            continue
        if len(ticker) == 1 and ticker_idx > 0:
            continue

        trailing = tokens_before_value[ticker_idx + 1:]
        quantity: float | None = None
        quantity_idx: int | None = None
        for idx, qtoken in enumerate(trailing):
            cleaned = qtoken.replace(",", "")
            if NUMBER_RE.match(cleaned):
                quantity = _num(cleaned)
                quantity_idx = idx
                break
        if quantity is None or quantity_idx is None:
            continue
        if quantity_idx == 0 and ticker_idx > 0:
            priority = 0
        elif ticker_idx == 0 and quantity_idx > 0 and trailing and _clean_token(trailing[0]) not in SECURITY_WORDS:
            priority = 1
        elif quantity_idx == 0:
            priority = 2
        else:
            continue
        candidates.append((priority, ticker_idx, ticker, quantity, quantity_idx))

    if candidates:
        priority, ticker_idx, ticker, quantity, quantity_idx = sorted(candidates)[0]
        trailing = tokens_before_value[ticker_idx + 1:]

        desc_tokens = (
            tokens_before_value[:ticker_idx]
            if ticker_idx > 0
            else trailing[:quantity_idx]
        )
        description = " ".join(desc_tokens).strip()
        return {
            "symbol": ticker,
            "description": description,
            "quantity": quantity,
            "market_value": market_value,
            "account_name": account_name or "Unknown",
        }
    return None


def parse_position_lines(
    text: str,
    *,
    account_name: str | None = None,
    broker: str | None = None,
) -> list[dict[str, Any]]:
    broker_key = (broker or "").strip().lower()
    if broker_key == "robinhood":
        rows = []
        seen: set[tuple[str, float, float]] = set()
        for raw_line in (text or "").splitlines():
            line = " ".join(raw_line.split())
            if _is_noise_line(line):
                continue
            row = _position_from_robinhood_line(line, account_name=account_name)
            if not row:
                continue
            key = (row["symbol"], round(row["quantity"], 6), round(row["market_value"], 2))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        return rows
    if broker_key == "schwab" and _looks_like_schwab_account_pdf(text):
        return _parse_schwab_lines(text, account_name=account_name)
    if broker_key == "fidelity" and _looks_like_fidelity_portfolio_pdf(text):
        return []

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    for raw_line in (text or "").splitlines():
        line = " ".join(raw_line.split())
        if _is_noise_line(line):
            continue
        row = _position_from_line(line, account_name=account_name)
        if not row:
            continue
        ticker = row["symbol"]
        quantity = row["quantity"]
        market_value = row["market_value"]
        key = (ticker, round(quantity, 6), round(market_value, 2))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
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
    broker = infer_broker(str(p), text)
    positions = parse_position_lines(text, account_name=account, broker=broker)
    passed = bool(text.strip()) and bool(positions) and error is None
    validation = {
        "passed": passed,
        "text_chars": len(text or ""),
        "positions_found": len(positions),
    }
    if error:
        validation["error"] = error
    elif broker == "Fidelity" and _looks_like_fidelity_portfolio_pdf(text) and not positions:
        validation["error"] = "Fidelity selectable text uses separated value/symbol blocks; stronger extractor required"
    if text.strip() and not positions:
        validation.setdefault("error", "no confident ticker/symbol position rows found")
    return {
        "source_file": str(p),
        "broker": broker,
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
            if not _looks_like_ticker(str(row.get("symbol") or "")):
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
