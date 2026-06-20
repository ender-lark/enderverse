#!/usr/bin/env python3
"""Watch-only political trade disclosure intake.

The default target is Donald J Trump executive-branch disclosure flow from
Unusual Whales. This lane captures disclosed trades as research prompts only.
Disclosure rows are lagged, incomplete, and never a standalone buy/sell signal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_uw.endpoints import UWEndpoints
from codex_uw.rest_client import UWConfigError, UWRequestError, UWRestClient, unwrap_uw_rows


DEFAULT_TARGET = "Donald J Trump"
DEFAULT_OUT = Path(__file__).resolve().parent / "political_trade_watch.json"
UTC = timezone.utc


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _date_text(value: Any) -> str:
    parsed = _parse_dt(value)
    if parsed:
        return parsed.date().isoformat()
    return str(value or "").strip()


def _iso(dt: datetime | None) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z") if dt else ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _amount(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = _text(value).replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _target_slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _row_matches_target(row: dict[str, Any], target: str) -> bool:
    if not target:
        return True
    target_norm = target.lower().replace(".", "").strip()
    values = [
        row.get("name"),
        row.get("reporter"),
        row.get("politician"),
        row.get("name_slug"),
    ]
    for value in values:
        text = _text(value).lower().replace(".", "")
        if target_norm and target_norm in text:
            return True
        if text and text in target_norm:
            return True
    slug = _target_slug(target)
    return bool(slug and slug == _text(row.get("name_slug")).lower())


def _stable_id(row: dict[str, Any], target: str) -> str:
    explicit = _text(row.get("file_record_id") or row.get("id"))
    seed = "|".join(
        [
            explicit,
            target,
            _text(row.get("ticker") or row.get("symbol")),
            _text(row.get("transaction_date")),
            _text(row.get("filed_at_date") or row.get("created_at")),
            _text(row.get("txn_type") or row.get("transaction_type")),
            _text(row.get("notes") or row.get("description")),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:14]
    return f"political-trade-{digest}"


def _lag_days(transaction_date: str, filed_at_date: str) -> int | None:
    txn = _parse_dt(transaction_date)
    filed = _parse_dt(filed_at_date)
    if not txn or not filed:
        return None
    return (filed.date() - txn.date()).days


def _score(*, ticker: str, txn_type: str, mid_value: float | None, filed_at: str, generated_at: datetime) -> float:
    score = 25.0
    if ticker:
        score += 25.0
    if txn_type.lower() in {"buy", "purchase", "sell", "sale"}:
        score += 15.0
    if mid_value is not None:
        score += min(mid_value / 25_000.0, 35.0)
    filed = _parse_dt(filed_at)
    if filed:
        age_days = max((generated_at.date() - filed.date()).days, 0)
        if age_days <= 3:
            score += 20.0
        elif age_days <= 14:
            score += 10.0
        elif age_days <= 45:
            score += 5.0
    return round(score, 2)


def _unwrap_payloads(payloads: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        for row in unwrap_uw_rows(payload):
            if isinstance(row, dict):
                rows.append(row)
    return rows


def normalize_trade_row(
    row: dict[str, Any],
    *,
    target: str = DEFAULT_TARGET,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now()
    ticker = _text(row.get("ticker") or row.get("symbol")).upper()
    txn_type = _text(row.get("txn_type") or row.get("transaction_type") or row.get("type"))
    transaction_date = _date_text(row.get("transaction_date") or row.get("txn_date"))
    filed_at_date = _date_text(row.get("filed_at_date") or row.get("filing_date") or row.get("created_at"))
    low_value = _amount(row.get("low_value"))
    high_value = _amount(row.get("high_value"))
    mid_value = _amount(row.get("mid_value"))
    if mid_value is None and low_value is not None and high_value is not None:
        mid_value = round((low_value + high_value) / 2.0, 2)
    amount_label = _text(row.get("amounts") or row.get("amount"))
    notes = _text(row.get("notes") or row.get("description"))
    issuer = _text(row.get("issuer") or notes)
    reporter = _text(row.get("reporter") or row.get("name") or target)
    target_label = reporter or target
    asset = _text(row.get("asset") or row.get("asset_type"))
    member_type = _text(row.get("member_type") or row.get("current_chamber") or row.get("chamber"))
    agency = _text(row.get("current_agency") or row.get("agency"))
    link_url = _text(row.get("link_url") or row.get("file"))
    lag = _lag_days(transaction_date, filed_at_date)
    label = ticker or issuer or notes or "undisclosed asset"
    action = txn_type or "disclosed"
    summary = (
        f"{target_label} {action} {label}"
        f"{f' ({amount_label})' if amount_label else ''}; "
        f"transaction {transaction_date or 'unknown'}, filed {filed_at_date or 'unknown'}."
    )
    route = "Research Queue candidate" if ticker and txn_type.lower() in {"buy", "purchase", "sell", "sale"} else "Quiet Watch"
    score = _score(ticker=ticker, txn_type=txn_type, mid_value=mid_value, filed_at=filed_at_date, generated_at=generated)
    return {
        "id": _stable_id(row, target),
        "source": "unusual_whales_political_disclosures",
        "source_group": "trump_trade_watch",
        "target": target_label,
        "target_slug": _text(row.get("name_slug")) or _target_slug(target_label),
        "member_type": member_type,
        "agency": agency,
        "party": _text(row.get("current_party") or row.get("party")),
        "ticker": ticker,
        "tickers": [ticker] if ticker else [],
        "issuer": issuer,
        "notes": notes,
        "asset": asset,
        "transaction_type": txn_type,
        "transaction_date": transaction_date,
        "filed_at_date": filed_at_date,
        "created_at": _iso(_parse_dt(row.get("created_at"))),
        "notification_date": _date_text(row.get("notification_date")),
        "amounts": amount_label,
        "low_value": low_value,
        "high_value": high_value,
        "mid_value": mid_value,
        "lag_days": lag,
        "owner": _text(row.get("owner")),
        "ownership": _text(row.get("ownership")),
        "file_record_id": _text(row.get("file_record_id")),
        "link_url": link_url,
        "summary": summary,
        "evidence": [
            item
            for item in [
                "Unusual Whales political-disclosure row",
                f"OGE/source filing: {link_url}" if link_url else "",
                f"Transaction date: {transaction_date}" if transaction_date else "",
                f"Filed date: {filed_at_date}" if filed_at_date else "",
                f"Disclosure lag days: {lag}" if lag is not None else "",
                f"Value range: {amount_label}" if amount_label else "",
            ]
            if item
        ],
        "independent_confirmation": [
            "Primary-source disclosure row captured through Unusual Whales; verify linked filing before action."
        ],
        "escalation": route,
        "score": score,
        "confidence": "medium source capture, low timing value",
        "decay_speed": "fast for news/policy context; disclosure timing is lagged and cannot prove current intent",
        "why_it_matters": (
            "Executive/political disclosures can identify policy-linked exposures, conflict risk, and research leads, "
            "but they are lagged and incomplete."
        ),
        "portfolio_implication": (
            "Compare against current holdings, targets, sector exposure, and policy catalysts. Treat as a research "
            "or risk prompt, not a trade."
        ),
        "risk": (
            "Disclosure lag, trust/owner ambiguity, missing exact prices, and political headline reflexivity. "
            "Do not chase without independent market and thesis confirmation."
        ),
        "confirmation_required": (
            "Verify the filing, then check same-session UW flow/price/news/Fundstrat/catalyst evidence before "
            "any action card or sizing review."
        ),
        "blocker_before_action": (
            "Political disclosure is not a trade trigger; needs current market evidence, thesis fit, account fit, "
            "and pre-trade gate review."
        ),
        "suggested_next_check": (
            f"Check {ticker or label} with price/news/UW flow and portfolio exposure; read the linked filing first."
        ),
        "captured_at": _iso(generated),
    }


def build_research_queue_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        ticker = _text(row.get("ticker"))
        if not ticker or row.get("escalation") != "Research Queue candidate":
            continue
        mid_value = row.get("mid_value")
        priority = "high" if isinstance(mid_value, (int, float)) and mid_value >= 250_000 else "med"
        out.append({
            "ticker": ticker,
            "r": f"{ticker} - Vet Trump disclosure before any action",
            "pr": priority,
            "status": "Working",
            "source": "political_trade_watch",
            "notes": (
                f"{row.get('summary')}. Blocker before action: {row.get('blocker_before_action')} "
                f"Evidence: {'; '.join(row.get('evidence') or [])}"
            ),
        })
    return out


def build_political_trade_watch(
    payloads: list[Any],
    *,
    target: str = DEFAULT_TARGET,
    generated_at: datetime | None = None,
    failures: list[dict[str, Any]] | None = None,
    max_rows: int = 100,
) -> dict[str, Any]:
    generated = generated_at or _utc_now()
    failure_rows = failures or []
    raw_rows = [row for row in _unwrap_payloads(payloads) if _row_matches_target(row, target)]
    rows = [
        normalize_trade_row(row, target=target, generated_at=generated)
        for row in raw_rows
    ]
    rows.sort(
        key=lambda row: (
            _parse_dt(row.get("filed_at_date")) or datetime.min.replace(tzinfo=UTC),
            float(row.get("score") or 0.0),
        ),
        reverse=True,
    )
    rows = rows[:max_rows]
    if not rows and failure_rows:
        status = "not_checked"
        line = f"Trump trade watch not checked: political disclosure fetch failed for {target}."
    elif rows:
        status = "has_data"
        line = f"Trump trade watch: {len(rows)} disclosed trade row(s) for {target}; watch-only until verified."
    else:
        status = "checked_clear"
        line = f"Trump trade watch checked clear: no supplied disclosure rows matched {target}."
    tickers = sorted({row["ticker"] for row in rows if row.get("ticker")})
    buys = sum(1 for row in rows if str(row.get("transaction_type") or "").lower() in {"buy", "purchase"})
    sells = sum(1 for row in rows if str(row.get("transaction_type") or "").lower() in {"sell", "sale"})
    research_queue_candidates = build_research_queue_rows(rows)
    return {
        "schema_version": 1,
        "generated_at": _iso(generated),
        "checked_at": _iso(generated),
        "source": "unusual_whales_political_disclosures",
        "source_group": "trump_trade_watch",
        "status": status,
        "line": line,
        "target": target,
        "target_slug": _target_slug(target),
        "counts": {
            "rows": len(rows),
            "tickers": len(tickers),
            "buys": buys,
            "sells": sells,
            "research_queue_candidates": len(research_queue_candidates),
        },
        "tickers": tickers,
        "failures": failure_rows,
        "rows": rows,
        "top": rows[:5],
        "research_queue_candidates": research_queue_candidates,
        "honesty_rule": "Political disclosures are watch-only research prompts; never standalone trade, sizing, or execution signals.",
        "promotion_rule": (
            "Action surfacing requires filing verification plus current UW/price/news/Fundstrat/catalyst evidence, "
            "portfolio fit, and pre-trade gate review."
        ),
        "command": "python src/political_trade_watch.py --cache src/political_trade_watch.json --format text",
    }


def build_political_trade_watch_block(cache: Any, *, target: str = DEFAULT_TARGET) -> dict[str, Any]:
    if cache is None:
        checked_at = _iso(_utc_now())
        return {
            "schema_version": 1,
            "generated_at": checked_at,
            "checked_at": checked_at,
            "source": "unusual_whales_political_disclosures",
            "source_group": "trump_trade_watch",
            "status": "not_checked",
            "line": "Trump trade watch not checked: no political disclosure cache supplied.",
            "target": target,
            "target_slug": _target_slug(target),
            "counts": {"rows": 0, "tickers": 0, "buys": 0, "sells": 0, "research_queue_candidates": 0},
            "tickers": [],
            "failures": [],
            "rows": [],
            "top": [],
            "research_queue_candidates": [],
            "honesty_rule": "Political disclosures are watch-only research prompts; never standalone trade, sizing, or execution signals.",
            "promotion_rule": (
                "Action surfacing requires filing verification plus current UW/price/news/Fundstrat/catalyst evidence, "
                "portfolio fit, and pre-trade gate review."
            ),
            "command": "python src/political_trade_watch.py --fetch-live --out src/political_trade_watch.json --format text",
        }
    if isinstance(cache, dict) and cache.get("source_group") == "trump_trade_watch" and "status" in cache:
        block = dict(cache)
        block.setdefault("rows", [])
        block.setdefault("top", (block.get("rows") or [])[:5])
        block.setdefault("research_queue_candidates", build_research_queue_rows(block.get("rows") or []))
        block.setdefault("honesty_rule", "Political disclosures are watch-only research prompts; never standalone trade, sizing, or execution signals.")
        block.setdefault(
            "promotion_rule",
            "Action surfacing requires filing verification plus current UW/price/news/Fundstrat/catalyst evidence, portfolio fit, and pre-trade gate review.",
        )
        block.setdefault("command", "python src/political_trade_watch.py --cache src/political_trade_watch.json --format text")
        return block
    return build_political_trade_watch([cache], target=target)


def fetch_live_trades(
    *,
    politician: str = DEFAULT_TARGET,
    limit: int = 100,
    client: UWRestClient | None = None,
) -> Any:
    client = client or UWRestClient()
    return client.get_json(
        UWEndpoints.CONGRESS_TRADER,
        params={
            "name": politician,
            "limit": min(max(int(limit), 1), 200),
            "page": 0,
        },
    )


def _load_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _payloads_from_inputs(paths: list[str]) -> list[Any]:
    payloads: list[Any] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in sorted(path.glob("*.json")):
                payloads.append(_load_json(child))
        else:
            payloads.append(_load_json(path))
    return payloads


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".political_trade_watch.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


def write_research_queue(rows: list[dict[str, Any]], *, out: str, merge_existing: bool = True) -> dict[str, Any]:
    from research_queue_intake import build_research_queue, merge_queues, validate_research_queue

    queue = build_research_queue(
        rows,
        generated_at=_iso(_utc_now()),
    )
    if merge_existing and Path(out).is_file():
        queue = merge_queues(_load_json(out), queue)
    problems = validate_research_queue(queue)
    if problems:
        return {"written": False, "problems": problems, "path": out}
    _atomic_write_json(out, queue)
    return {"written": True, "path": out, "pending": len(queue.get("pending") or [])}


def format_text(block: dict[str, Any], *, max_rows: int = 20) -> str:
    lines = [block.get("line") or "Trump trade watch"]
    lines.append(f"status: {block.get('status') or 'unknown'}")
    counts = block.get("counts") or {}
    if counts:
        lines.append(
            "counts: "
            f"rows={counts.get('rows', 0)} tickers={counts.get('tickers', 0)} "
            f"buys={counts.get('buys', 0)} sells={counts.get('sells', 0)} "
            f"rq={counts.get('research_queue_candidates', 0)}"
        )
    if block.get("failures"):
        lines.append(f"failures: {len(block.get('failures') or [])}")
    rows = [row for row in block.get("rows") or [] if isinstance(row, dict)]
    for row in rows[:max_rows]:
        label = row.get("ticker") or row.get("issuer") or "DISCLOSURE"
        lag = row.get("lag_days")
        lag_text = f" lag={lag}d" if lag is not None else ""
        lines.append(
            f"- {label}: {row.get('transaction_type') or 'disclosed'} {row.get('amounts') or ''} "
            f"txn={row.get('transaction_date') or 'unknown'} filed={row.get('filed_at_date') or 'unknown'}"
            f"{lag_text} | {row.get('escalation')} | score={row.get('score')}"
        )
        lines.append(f"  summary: {row.get('summary')}")
        lines.append(f"  blocker: {row.get('blocker_before_action')}")
    if len(rows) > max_rows:
        lines.append(f"... {len(rows) - max_rows} more disclosure row(s) in cache")
    if block.get("honesty_rule"):
        lines.append(f"honesty: {block['honesty_rule']}")
    if block.get("promotion_rule"):
        lines.append(f"promotion: {block['promotion_rule']}")
    return "\n".join(lines)


def _read_stdin_json() -> Any:
    text = sys.stdin.read()
    if not text.strip():
        return None
    return json.loads(text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build or inspect political_trade_watch.json")
    parser.add_argument("--cache", help="Existing political_trade_watch.json to validate/print")
    parser.add_argument("--input", action="append", default=[], help="UW congress-trade JSON file or directory")
    parser.add_argument("--stdin-json", action="store_true", help="Read UW congress-trade JSON from stdin")
    parser.add_argument("--fetch-live", action="store_true", help="Fetch live UW political-disclosure rows using UW_API_KEY")
    parser.add_argument("--politician", default=DEFAULT_TARGET)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--research-queue-out", help="Optional research_queue.json path for ticker rows")
    parser.add_argument("--no-merge-research-queue", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when the cache is not_checked")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.cache and not (args.input or args.stdin_json or args.fetch_live):
        block = _load_json(args.cache)
        if args.format == "json":
            print(json.dumps(block, indent=2, sort_keys=True))
        else:
            print(format_text(block))
        return 2 if args.strict and block.get("status") == "not_checked" else 0

    payloads = _payloads_from_inputs(args.input)
    if args.stdin_json:
        stdin_payload = _read_stdin_json()
        if stdin_payload is not None:
            payloads.append(stdin_payload)
    failures: list[dict[str, Any]] = []
    if args.fetch_live:
        try:
            payloads.append(fetch_live_trades(politician=args.politician, limit=args.limit))
        except (UWConfigError, UWRequestError) as exc:
            failures.append({
                "source": "unusual_whales_political_disclosures",
                "politician": args.politician,
                "error": str(exc),
            })
    if not payloads and not failures:
        parser.error("provide --cache, --input, --stdin-json, --fetch-live, or some combination")

    block = build_political_trade_watch(
        payloads,
        target=args.politician,
        failures=failures,
        max_rows=args.limit,
    )
    rq_report = None
    if args.research_queue_out and block.get("research_queue_candidates") and not args.dry_run:
        rq_report = write_research_queue(
            block["research_queue_candidates"],
            out=args.research_queue_out,
            merge_existing=not args.no_merge_research_queue,
        )
        block["research_queue_write"] = rq_report
    if not args.dry_run:
        _atomic_write_json(args.out, block)
    if args.format == "json":
        print(json.dumps({
            "cache": block,
            "written": None if args.dry_run else args.out,
            "research_queue": rq_report,
        }, indent=2, sort_keys=True))
    else:
        print(format_text(block))
        if not args.dry_run:
            print(f"wrote: {args.out}")
        if rq_report:
            print(f"research queue: {rq_report}")
    return 2 if args.strict and block.get("status") == "not_checked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
