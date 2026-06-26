#!/usr/bin/env python3
"""Build a shared watch/interest index across Investing OS list surfaces."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SRC = Path(__file__).resolve().parent
DEFAULT_OUT = DEFAULT_SRC / "watch_interest_index.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    tmp.replace(p)
    return p


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _ticker(value: Any) -> str:
    return _text(value).upper()


def _rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys or ("items", "rows", "pending", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _add_hit(index: dict[str, dict[str, Any]], ticker: str, source: str, detail: str, row: dict[str, Any] | None = None) -> None:
    tk = _ticker(ticker)
    if not tk:
        return
    bucket = index.setdefault(tk, {"ticker": tk, "sources": [], "source_details": [], "source_rows": {}})
    if source not in bucket["sources"]:
        bucket["sources"].append(source)
    if detail and detail not in bucket["source_details"]:
        bucket["source_details"].append(detail)
    if row is not None:
        bucket["source_rows"].setdefault(source, []).append(row)


def normalize_interest_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _rows(payload, "items", "rows", "interests", "watchlist"):
        tk = _ticker(row.get("ticker") or row.get("symbol"))
        if not tk:
            continue
        aliases = row.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        alt = row.get("alternate_candidates") or []
        rows.append({
            "ticker": tk,
            "name": _text(row.get("name") or row.get("company")),
            "aliases": [_text(alias) for alias in aliases if _text(alias)],
            "status": _text(row.get("status") or "interest").lower(),
            "priority": _text(row.get("priority") or "research").lower(),
            "first_added": _text(row.get("first_added") or row.get("date")),
            "source": _text(row.get("source") or "operator_interest_list"),
            "interest_reason": _text(row.get("interest_reason") or row.get("reason") or row.get("why")),
            "ambiguity": _text(row.get("ambiguity")),
            "alternate_candidates": [candidate for candidate in alt if isinstance(candidate, dict)],
            "next_step": _text(row.get("next_step") or row.get("next")),
        })
    return rows


def _position_rows(account_positions: Any) -> list[dict[str, Any]]:
    if not isinstance(account_positions, dict):
        return []
    rows = account_positions.get("combined_positions") or account_positions.get("account_positions") or []
    return [row for row in rows if isinstance(row, dict)]


def _feed_prospect_rows(feed: Any) -> list[dict[str, Any]]:
    if not isinstance(feed, dict):
        return []
    prospects = feed.get("prospects") if isinstance(feed.get("prospects"), dict) else {}
    rows: list[dict[str, Any]] = []
    for key in ("hot", "movers_best", "sell_fast"):
        rows.extend(row for row in prospects.get(key, []) if isinstance(row, dict))
    return rows


def build_watch_interest_index(
    *,
    manual: Any = None,
    theses: Any = None,
    top_prospects: Any = None,
    research: Any = None,
    account_positions: Any = None,
    parabolic: Any = None,
    feed: Any = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    index: dict[str, dict[str, Any]] = {}
    manual_rows = normalize_interest_rows(manual)

    for row in manual_rows:
        _add_hit(index, row["ticker"], "manual_interest", row.get("interest_reason") or row.get("source") or "manual interest", row)

    for row in _rows(theses):
        tk = row.get("ticker")
        detail = " / ".join(part for part in (_text(row.get("stance")), _text(row.get("tier")), _text(row.get("lane"))) if part)
        _add_hit(index, tk, "theses", detail, row)

    if isinstance(top_prospects, dict):
        for tk, row in top_prospects.items():
            if isinstance(row, dict):
                detail = " / ".join(part for part in (_text(row.get("direction")), _text(row.get("conviction")), _text(row.get("urgency")), _text(row.get("provenance"))) if part)
                _add_hit(index, row.get("ticker") or tk, "top_prospects", detail, row)

    for row in _rows(research, "pending"):
        detail = " / ".join(part for part in (_text(row.get("pr")), _text(row.get("status")), _text(row.get("r"))) if part)
        _add_hit(index, row.get("ticker"), "research_queue", detail, row)

    held_values: dict[str, float] = {}
    for row in _position_rows(account_positions):
        tk = _ticker(row.get("ticker"))
        if not tk:
            continue
        try:
            held_values[tk] = held_values.get(tk, 0.0) + float(row.get("market_value") or 0)
        except (TypeError, ValueError):
            held_values.setdefault(tk, 0.0)
    for tk, value in held_values.items():
        _add_hit(index, tk, "account_positions", f"held ${value:,.0f}", {"ticker": tk, "market_value": value})

    for row in _rows(parabolic, "results"):
        detail = " / ".join(part for part in (_text(row.get("surface_tier")), _text(row.get("score"))) if part)
        _add_hit(index, row.get("ticker"), "parabolic_setups", detail, row)

    if isinstance(feed, dict):
        for key in ("actions", "research_actions", "lean_in", "radar"):
            for row in _rows(feed.get(key)):
                detail = _text(row.get("what") or row.get("headline") or row.get("summary") or row.get("direction") or row.get("kind"))
                _add_hit(index, row.get("ticker"), f"feed.{key}", detail, row)
        for row in _feed_prospect_rows(feed):
            _add_hit(index, row.get("ticker"), "feed.prospects", _text(row.get("summary") or row.get("direction")), row)
        bullish = feed.get("bullish_flow") if isinstance(feed.get("bullish_flow"), dict) else {}
        for row in _rows(bullish, "rows"):
            _add_hit(index, row.get("ticker"), "feed.bullish_flow", _text(row.get("direction") or row.get("strength")), row)

    manual_tickers = {row["ticker"] for row in manual_rows}
    rows_out: list[dict[str, Any]] = []
    for tk, bucket in sorted(index.items()):
        manual_row = next((row for row in manual_rows if row["ticker"] == tk), {})
        rows_out.append({
            "ticker": tk,
            "name": manual_row.get("name") or "",
            "aliases": manual_row.get("aliases") or [],
            "status": manual_row.get("status") or ("held" if tk in held_values else "tracked"),
            "priority": manual_row.get("priority") or ("held" if tk in held_values else "context"),
            "interest_reason": manual_row.get("interest_reason") or "",
            "ambiguity": manual_row.get("ambiguity") or "",
            "alternate_candidates": manual_row.get("alternate_candidates") or [],
            "next_step": manual_row.get("next_step") or "",
            "manual_interest": tk in manual_tickers,
            "held_market_value": round(held_values.get(tk, 0.0), 2),
            "sources": sorted(bucket.get("sources") or []),
            "source_count": len(bucket.get("sources") or []),
            "source_details": (bucket.get("source_details") or [])[:8],
        })

    rows_out.sort(key=lambda row: (
        0 if row.get("manual_interest") else 1,
        0 if row.get("held_market_value") else 1,
        -int(row.get("source_count") or 0),
        row.get("ticker") or "",
    ))
    return {
        "schema_version": 1,
        "generated_at": generated_at or _utc_now_iso(),
        "source": "watch_interest_index",
        "status": "has_data" if rows_out else "not_checked",
        "manual_interest_count": len(manual_rows),
        "count": len(rows_out),
        "rows": rows_out,
    }


def validate_watch_interest(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["watch interest payload must be a dict"]
    rows = normalize_interest_rows(payload)
    if not rows:
        problems.append("watch interest payload must include at least one row with ticker")
    for idx, row in enumerate(rows):
        if not row["ticker"]:
            problems.append(f"items[{idx}].ticker is required")
        if row["status"] in {"buy", "sell", "trade"}:
            problems.append(f"items[{idx}].status must stay watch/research/interest, not {row['status']!r}")
    return problems


def _self_test() -> bool:
    manual = {"items": [{"ticker": "CISO", "aliases": ["Cerberus"], "interest_reason": "operator interest"}]}
    payload = build_watch_interest_index(
        manual=manual,
        theses=[{"ticker": "GOOGL", "stance": "ACTIVE", "tier": "T1"}],
        top_prospects={"CISO": {"ticker": "CISO", "direction": "long", "urgency": "QUIET"}},
        research={"pending": [{"ticker": "CISO", "r": "research it", "pr": "low"}]},
        account_positions={"account_positions": [{"ticker": "GOOGL", "market_value": 1234}]},
        parabolic={"results": [{"ticker": "CISO", "surface_tier": "WATCHLIST", "score": 7}]},
        feed={"lean_in": [{"ticker": "GOOGL", "headline": "Lean in"}]},
        generated_at="2026-06-26T00:00:00Z",
    )
    ciso = next(row for row in payload["rows"] if row["ticker"] == "CISO")
    assert ciso["manual_interest"] is True
    assert {"manual_interest", "top_prospects", "research_queue", "parabolic_setups"} <= set(ciso["sources"])
    googl = next(row for row in payload["rows"] if row["ticker"] == "GOOGL")
    assert googl["held_market_value"] == 1234
    assert validate_watch_interest(manual) == []
    print("watch_interest self-test: PASS")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build or validate watch-interest index")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--generated-at")
    parser.add_argument("--validate", help="Validate a watch_interest.json file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if _self_test() else 1
    if args.validate:
        problems = validate_watch_interest(_read_json(args.validate, default={}))
        if problems:
            print(json.dumps({"valid": False, "problems": problems}, indent=2))
            return 1
        print(json.dumps({"valid": True, "problems": []}, indent=2))
        return 0

    src = Path(args.src_dir)
    payload = build_watch_interest_index(
        manual=_read_json(src / "watch_interest.json", default={}),
        theses=_read_json(src / "theses.json", default=[]),
        top_prospects=_read_json(src / "top_prospects.json", default={}),
        research=_read_json(src / "research_queue.json", default={}),
        account_positions=_read_json(src / "account_positions.json", default={}),
        parabolic=_read_json(src / "parabolic_setups.json", default={}),
        feed=_read_json(src / "latest_cockpit_feed.json", default={}),
        generated_at=args.generated_at,
    )
    _atomic_write_json(args.out, payload)
    print(json.dumps({"written": str(args.out), "count": payload["count"], "manual_interest_count": payload["manual_interest_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
