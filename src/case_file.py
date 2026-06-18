#!/usr/bin/env python3
"""Per-ticker case file - a pure, read-only assembler.

`build_case_file(ticker, today)` fans in the repo's existing per-ticker stores at
read time and returns ONE dict with six lanes:

    identity, earliest_record, verdict, fundstrat_calls, news, decisions

so that when a ticker comes up we never restart from zero - one call shows what
we already know and have done on it.

Design rules (why this shape - see docs/investing_os_storage_and_synthesis_audit_2026_06_17.md):

  * DERIVED, NOT A NEW STORE. It persists nothing. The repo already carries a
    documented stale-as-live / orphaned-store problem; a 7th hand-maintained
    per-ticker mirror would recreate it. Every lane is computed on demand from
    stores that are already maintained for other reasons.

  * NOT AN EXTENSION OF decision_dossiers. That module is a Notion-authored,
    one-row-per-ticker, point-in-time MIRROR with a fixed 4-read validator
    (edge/price/timing/avoid). It is the wrong host for local append-only
    history; we READ it (via its freshness helper) as one input, never widen its
    schema.

  * PURE ASSEMBLER. No printing, no HTML, no file writes inside build_case_file.
    The agent calling it mid-conversation, the CLI, and any future dashboard /
    Notion render are all thin consumers of the same dict.

  * HONESTY RAILS. Every lane degrades to an explicit empty / UNKNOWN / missing
    block (blocks=False, alert_eligible=False, honesty_rule) - never a fabricated
    value, never empty-as-clean. A stale verdict self-degrades and cannot read as
    current. "do not fabricate verdicts" (docs/research_dossiers/README.md)
    applies to the assembler too.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import decision_dossiers as dd


SRC = Path(__file__).resolve().parent
REPO = SRC.parent

SOURCE_CALLS_PATH = SRC / "source_calls.json"
SIGNAL_LOG_PATH = SRC / "signal_log.json"
TOP_PROSPECTS_PATH = SRC / "top_prospects.json"
OPEN_OPPS_PATH = SRC / "open_opportunities.json"
DISPOSITIONS_PATH = SRC / "dispositions.jsonl"
DOSSIER_DIR = REPO / "docs" / "research_dossiers"

# A thesis-of-record older than this (calendar days) self-degrades to UNKNOWN so
# a stale verdict can never read as current. Function-default constant on
# purpose: v1 adds no tunables.py key (honesty rails are not tunable).
VERDICT_MAX_AGE_DAYS = 45

# Macro / index / crypto proxies that leak into the "of interest" set. These get
# a case file shaped as macro context, not an equity thesis-of-record. Kept
# deliberately small so a real equity/ETF holding is never misread as macro.
MACRO_TICKERS = {"SPX", "SOX", "TNX", "VIX", "DXY", "SPY", "QQQ", "BTC", "ETH", "SOL"}

# Attached to every lane so a thin case file can never imply a trade/no-trade.
_HONESTY = {"blocks": False, "alert_eligible": False}

_VERDICT_RE = re.compile(r"\*\*CURRENT VERDICT \((\d{4}-\d{2}-\d{2})\):\*\*\s*(.+)")

# Verdict verb vocabulary. HELD names carry a position posture; NON-HELD names of
# interest carry a buy-side DISPOSITION (decide-and-direct — a "HOLD" on a name we
# don't own is a category error and reads as a posture that doesn't exist). The
# parser stays verb-agnostic (nothing downstream gates on the word, only on
# status), so these sets are for honesty/classification only.
HELD_VERBS = {"HOLD", "ADD", "TRIM", "EXIT", "SELL", "REDUCE", "SIZE", "SIZE UP", "RECONSIDER"}
BUY_SIDE_VERBS = {"BUY-CANDIDATE", "WATCH", "PASS"}


def _disposition_kind(action_hint: str | None) -> str:
    """Classify the verdict verb as a held posture vs a non-held buy-side disposition."""
    hint = (action_hint or "").strip().upper()
    if hint in BUY_SIDE_VERBS:
        return "buy_side"
    if hint in HELD_VERBS or hint.split(" ", 1)[0] in HELD_VERBS:
        return "held"
    return "other"


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _load_json(path: Path | str, default: Any) -> Any:
    p = Path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _strip_md(text: str) -> str:
    return text.replace("**", "").strip()


def parse_verdict_header(text: str) -> dict[str, Any]:
    """Parse the documented '**CURRENT VERDICT (YYYY-MM-DD):** ...' header.

    Returns {date, verdict_line, action_hint, conviction}. Defensive: if no header
    matches, date is None (caller treats the file as present-but-unparsed rather
    than dropping the name). The FULL verdict_line is the authoritative text;
    action_hint is best-effort only and must not be relied on.
    """
    for line in text.splitlines():
        m = _VERDICT_RE.search(line)
        if not m:
            continue
        verdict_date, rest = m.group(1), m.group(2).strip()
        action_hint = None
        bold = re.match(r"\*\*(.+?)\*\*", rest)
        if bold:
            action_hint = bold.group(1).strip().strip("-.: ").upper() or None
        else:
            head = rest.split()
            action_hint = head[0].strip("-.,: ").upper() if head else None
        # Defense-in-depth: a size / number must NEVER land in the (best-effort)
        # action_hint, so a "$8k" can't later be mistaken for a wired buy signal.
        if action_hint and ("$" in action_hint or any(c.isdigit() for c in action_hint)):
            clean = [t for t in re.split(r"[\s/]+", action_hint) if t and "$" not in t and not any(c.isdigit() for c in t)]
            action_hint = clean[0] if clean else None
        conviction = None
        conv = re.search(r"conviction\s+\*\*(.+?)\*\*", rest)
        if conv:
            conviction = conv.group(1).strip()
        return {
            "date": verdict_date,
            "verdict_line": _strip_md(rest),
            "action_hint": action_hint,
            "conviction": conviction,
        }
    return {"date": None, "verdict_line": "", "action_hint": None, "conviction": None}


def load_verdict(ticker: str, today: str | date | None, *, dossier_dir: Path | str | None = None) -> dict[str, Any]:
    """Verdict lane: the operator thesis-of-record, with loud absence + staleness."""
    tick = _ticker(ticker)
    base_dir = Path(dossier_dir) if dossier_dir else DOSSIER_DIR
    path = base_dir / f"{tick}.md"
    if not path.exists():
        return {
            "status": "missing",
            "present": False,
            "line": (
                f"NO THESIS-OF-RECORD on file for {tick} - this is missing, not neutral; "
                f"do not size from this case file."
            ),
            "path": str(path),
            **_HONESTY,
            "honesty_rule": "Absence of a thesis-of-record is a flagged gap, never a clean/neutral read.",
        }
    text = path.read_text(encoding="utf-8")
    parsed = parse_verdict_header(text)
    if not parsed["date"]:
        return {
            "status": "unparsed",
            "present": True,
            "line": (
                f"Thesis-of-record file present but the CURRENT VERDICT header is not parseable - "
                f"open {path.name} and read it directly."
            ),
            "path": str(path),
            **_HONESTY,
            "honesty_rule": "File on record but unparsed; treat as needs-manual-read, not covered.",
        }
    today_d = dd._today(today)
    freshness = dd._freshness({"as_of": parsed["date"], "max_age_days": VERDICT_MAX_AGE_DAYS}, today_d)
    out: dict[str, Any] = {
        "present": True,
        "verdict_date": parsed["date"],
        "verdict_line": parsed["verdict_line"],
        "action_hint": parsed["action_hint"],
        "conviction": parsed["conviction"],
        "disposition_kind": _disposition_kind(parsed["action_hint"]),
        "age_days": freshness.get("age_days"),
        "path": str(path),
        "freshness": freshness,
        **_HONESTY,
    }
    if freshness["fresh"]:
        out["status"] = "fresh"
        out["line"] = parsed["verdict_line"]
        if out["disposition_kind"] == "buy_side":
            out["honesty_rule"] = (
                "Non-held watchlist name — this is a buy-side DISPOSITION "
                "(BUY-CANDIDATE/WATCH/PASS), not a position posture; any size/trigger is "
                "judgment within survival rails, never a screen score."
            )
        else:
            out["honesty_rule"] = "Operator thesis-of-record; current within the verdict freshness window."
    else:
        out["status"] = "stale"
        out["line"] = (
            f"UNKNOWN - verdict dated {parsed['date']} is STALE "
            f"({freshness.get('age_days')}d > {VERDICT_MAX_AGE_DAYS}d); re-confirm the thesis-of-record "
            f"before sizing. (Last read: {parsed['verdict_line']})"
        )
        out["honesty_rule"] = "Stale verdict cannot drive a decision; shown as UNKNOWN with the last read preserved."
    return out


def fundstrat_calls_lane(ticker: str, *, source_calls: list[dict] | None = None) -> dict[str, Any]:
    """Dated Fundstrat / analyst calls for this exact ticker, newest first."""
    tick = _ticker(ticker)
    rows = source_calls if source_calls is not None else _load_json(SOURCE_CALLS_PATH, [])
    rows = rows if isinstance(rows, list) else []
    all_dates = [r.get("date") for r in rows if isinstance(r, dict) and r.get("date")]
    floor = min(all_dates) if all_dates else None
    events = [
        {
            "date": r.get("date"),
            "source": r.get("source"),
            "tier": r.get("tier"),
            "outcome": r.get("outcome"),
            "direction": r.get("direction"),
            "text": r.get("verbatim_quote") or r.get("call_summary") or "",
            "window_end": r.get("window_end"),
            "id": r.get("id"),
        }
        for r in rows
        if isinstance(r, dict) and _ticker(r.get("ticker")) == tick
    ]
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    if events:
        line = f"{len(events)} Fundstrat call(s) in cache for {tick}."
        status = "ok"
    else:
        line = (
            f"No Fundstrat calls in cache for {tick} "
            f"(cache begins {floor}; absence = not captured, not 'no view')."
        )
        status = "empty"
    return {
        "status": status,
        "line": line,
        "cache_floor": floor,
        "count": len(events),
        "events": events,
        **_HONESTY,
        "honesty_rule": "Fundstrat call cache; absence is not-captured, never a clean no-signal.",
    }


def case_file_news_lane(ticker: str, *, signal_log: list[dict] | None = None) -> dict[str, Any]:
    """News/insight rows touching this ticker, with basket rows tagged + demoted.

    signal_log 'ticker' keys are frequently comma-joined multi-ticker baskets (a
    macro headline stamped on many names). We split them and mark any multi-ticker
    row as macro/basket context, ranked BELOW name-specific rows, so a 10-name
    macro headline never masquerades as ticker-specific conviction.
    """
    tick = _ticker(ticker)
    rows = signal_log if signal_log is not None else _load_json(SIGNAL_LOG_PATH, [])
    rows = rows if isinstance(rows, list) else []
    events = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        tickers = [t.strip().upper() for t in str(r.get("ticker", "")).split(",") if t.strip()]
        if tick not in tickers:
            continue
        n = len(tickers)
        name_specific = n <= 1
        events.append(
            {
                "date": r.get("date"),
                "signal": r.get("signal"),
                "note": r.get("note"),
                "source": r.get("source"),
                "priority": r.get("priority"),
                "ticker_count": n,
                "name_specific": name_specific,
                "scope": "name-specific" if name_specific else f"macro/basket context ({n} tickers)",
                "basket_tickers": None if name_specific else tickers,
            }
        )
    name_rows = sorted([e for e in events if e["name_specific"]], key=lambda e: e.get("date") or "", reverse=True)
    basket_rows = sorted([e for e in events if not e["name_specific"]], key=lambda e: e.get("date") or "", reverse=True)
    ordered = name_rows + basket_rows
    if ordered:
        line = f"{len(name_rows)} name-specific + {len(basket_rows)} basket/macro news row(s) for {tick}."
        status = "ok"
    else:
        line = (
            f"No news rows reference {tick} "
            f"(signal log is sweep-driven; absence = not captured, not 'no news')."
        )
        status = "empty"
    return {
        "status": status,
        "line": line,
        "name_specific_count": len(name_rows),
        "basket_count": len(basket_rows),
        "events": ordered,
        **_HONESTY,
        "honesty_rule": "Sweep-driven; basket rows are macro context stamped on many names, never name-specific conviction.",
    }


def decisions_lane(
    ticker: str,
    *,
    dispositions_path: Path | str | None = None,
    open_opportunities: dict | None = None,
) -> dict[str, Any]:
    """Dated decisions (disposition spine) + flag/resolve events (action memory)."""
    tick = _ticker(ticker)
    dpath = Path(dispositions_path) if dispositions_path else DISPOSITIONS_PATH
    disp_present = dpath.exists()
    disp_events: list[dict[str, Any]] = []
    if disp_present:
        try:
            import disposition_log as dl

            for row in dl._parse_dispositions(dpath):
                if _ticker(row.get("ticker")) != tick:
                    continue
                disp_events.append(
                    {
                        "date": row.get("et_date"),
                        "kind": "disposition",
                        "verb": row.get("verb"),
                        "reason": row.get("reason"),
                        "card_id": row.get("card_id"),
                        "ts": row.get("ts"),
                    }
                )
        except Exception:
            disp_present = False

    opps = open_opportunities if open_opportunities is not None else _load_json(OPEN_OPPS_PATH, {})
    history = opps.get("history") if isinstance(opps, dict) else None
    mem_events: list[dict[str, Any]] = []
    for row in history or []:
        if not isinstance(row, dict) or _ticker(row.get("ticker")) != tick:
            continue
        if row.get("first_flagged"):
            mem_events.append(
                {
                    "date": row.get("first_flagged"),
                    "kind": "flagged",
                    "status_label": "flagged",
                    "reason": row.get("reason"),
                    "source": row.get("source"),
                }
            )
        if row.get("resolved_at"):
            mem_events.append(
                {
                    "date": row.get("resolved_at"),
                    "kind": "resolved",
                    "status_label": row.get("status"),
                    "reason": row.get("reason"),
                    "source": row.get("source"),
                }
            )

    events = sorted(disp_events + mem_events, key=lambda e: e.get("date") or "", reverse=True)
    if events:
        status, line = "ok", f"{len(events)} decision/flag event(s) on record for {tick}."
    elif not disp_present and not mem_events:
        status = "empty"
        line = (
            f"No decision log yet for {tick} "
            f"(dispositions.jsonl absent - C6 disposition spine pending; auto-populates when wired)."
        )
    else:
        status, line = "empty", f"No decision/flag events on record for {tick}."
    return {
        "status": status,
        "line": line,
        "dispositions_present": disp_present,
        "events": events,
        **_HONESTY,
        "honesty_rule": "Decision history; empty/absent never means 'no decision' - it means not yet logged.",
    }


def earliest_record_lane(
    ticker: str,
    *,
    source_calls: list[dict] | None = None,
    top_prospects: dict | None = None,
    verdict: dict | None = None,
) -> dict[str, Any]:
    """Provenance-stamped 'earliest record we hold' - NOT a synthesized first-seen.

    Each origin record is labeled with the store it came from; the Fundstrat cache
    floor bounds what we can possibly know, so an older true coverage date is never
    implied.
    """
    tick = _ticker(ticker)
    rows = source_calls if source_calls is not None else _load_json(SOURCE_CALLS_PATH, [])
    rows = rows if isinstance(rows, list) else []
    tp = top_prospects if top_prospects is not None else _load_json(TOP_PROSPECTS_PATH, {})
    tp = tp if isinstance(tp, dict) else {}

    cache_floor = min(
        [r.get("date") for r in rows if isinstance(r, dict) and r.get("date")], default=None
    )
    records: list[dict[str, Any]] = []

    fs_dates = [r.get("date") for r in rows if isinstance(r, dict) and _ticker(r.get("ticker")) == tick and r.get("date")]
    if fs_dates:
        records.append({"date": min(fs_dates), "source": "fundstrat_call_cache", "label": "earliest Fundstrat call in cache"})

    tp_rec = tp.get(tick)
    if isinstance(tp_rec, dict) and tp_rec.get("add_date"):
        records.append(
            {
                "date": tp_rec.get("add_date"),
                "source": "top_prospects",
                "label": "added to prospect list",
                "add_price": tp_rec.get("add_price"),
            }
        )

    if verdict and verdict.get("verdict_date"):
        records.append({"date": verdict["verdict_date"], "source": "research_dossier", "label": "thesis-of-record written"})

    records.sort(key=lambda r: r.get("date") or "")
    if records:
        earliest = records[0]
        status = "ok"
        line = (
            f"Earliest record we hold for {tick}: {earliest['date']} "
            f"(source: {earliest['source']} - {earliest['label']}). "
            f"Fundstrat call cache begins {cache_floor}; earlier history is not captured."
        )
    else:
        status = "empty"
        line = (
            f"No dated record on file for {tick} yet. "
            f"Fundstrat call cache begins {cache_floor}; earlier history is not captured."
        )
    return {
        "status": status,
        "line": line,
        "records": records,
        "cache_floor": cache_floor,
        **_HONESTY,
        "honesty_rule": "Provenance-stamped earliest record, not a synthesized 'first seen'; the cache floor bounds what we can know.",
    }


def identity_lane(ticker: str) -> dict[str, Any]:
    tick = _ticker(ticker)
    kind = "macro" if tick in MACRO_TICKERS else "equity"
    return {
        "status": "ok",
        "ticker": tick,
        "kind": kind,
        "is_equity": kind == "equity",
        "line": (
            f"{tick} - equity/ETF case file."
            if kind == "equity"
            else f"{tick} is a macro/index/crypto proxy - not an equity thesis case file."
        ),
        "note": "v1 keeps common/options/wrapper as separate labeled queries; no alias map.",
        **_HONESTY,
        "honesty_rule": "Identity is the literal ticker; wrappers/options/underliers are not silently merged.",
    }


def build_case_file(
    ticker: str,
    today: str | date | None = None,
    *,
    source_calls: list[dict] | None = None,
    signal_log: list[dict] | None = None,
    dossier_dir: Path | str | None = None,
    dispositions_path: Path | str | None = None,
    top_prospects: dict | None = None,
    open_opportunities: dict | None = None,
) -> dict[str, Any]:
    """Assemble the per-ticker case file. Pure: reads only, writes nothing."""
    tick = _ticker(ticker)
    today_iso = dd._today(today).isoformat()
    identity = identity_lane(tick)
    base: dict[str, Any] = {
        "ticker": tick,
        "today": today_iso,
        "is_equity": identity["is_equity"],
        "identity": identity,
        "generated_note": "Derived, read-only case file assembled on demand; persists nothing.",
    }
    if not tick:
        base["error"] = "empty ticker"
        return base

    # Always-factual lanes (apply to macro proxies too).
    base["fundstrat_calls"] = fundstrat_calls_lane(tick, source_calls=source_calls)
    base["news"] = case_file_news_lane(tick, signal_log=signal_log)

    if not identity["is_equity"]:
        skip = {**_HONESTY, "honesty_rule": "n/a for a macro/index/crypto proxy."}
        base["verdict"] = {"status": "skipped", "line": "macro/index/crypto - no equity thesis-of-record.", **skip}
        base["earliest_record"] = {"status": "skipped", "line": "n/a for a macro/index/crypto proxy.", **skip}
        base["decisions"] = {"status": "skipped", "line": "n/a for a macro/index/crypto proxy.", **skip}
        return base

    verdict = load_verdict(tick, today, dossier_dir=dossier_dir)
    base["verdict"] = verdict
    base["earliest_record"] = earliest_record_lane(
        tick, source_calls=source_calls, top_prospects=top_prospects, verdict=verdict
    )
    base["decisions"] = decisions_lane(
        tick, dispositions_path=dispositions_path, open_opportunities=open_opportunities
    )
    return base


def render_text(case_file: dict[str, Any]) -> str:
    """Human/agent-readable render, verdict first. A thin consumer of the dict."""
    lines = [f"=== {case_file.get('ticker')} - case file (as of {case_file.get('today')}) ==="]
    lines.append(case_file.get("identity", {}).get("line", ""))
    if not case_file.get("is_equity", True):
        for key in ("fundstrat_calls", "news"):
            lines.append(f"[{key}] {case_file.get(key, {}).get('line', '')}")
        return "\n".join(lines)

    v = case_file.get("verdict", {})
    lines += ["", f"VERDICT ({v.get('status', '?')}): {v.get('line', '')}"]
    lines.append(f"EARLIEST RECORD: {case_file.get('earliest_record', {}).get('line', '')}")

    fs = case_file.get("fundstrat_calls", {})
    lines += ["", f"FUNDSTRAT CALLS - {fs.get('line', '')}"]
    for e in fs.get("events", [])[:8]:
        lines.append(f"  {e.get('date')}  [{e.get('source')}/{e.get('tier')}] {e.get('text', '')}")

    nw = case_file.get("news", {})
    lines.append(f"NEWS - {nw.get('line', '')}")
    for e in nw.get("events", [])[:8]:
        tag = "" if e.get("name_specific") else f" [{e.get('scope')}]"
        lines.append(f"  {e.get('date')}{tag}  {e.get('signal', '')}")

    dec = case_file.get("decisions", {})
    lines.append(f"DECISIONS - {dec.get('line', '')}")
    for e in dec.get("events", [])[:8]:
        lines.append(f"  {e.get('date')}  {e.get('verb') or e.get('status_label')}  {e.get('reason') or ''}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="case_file", description="Per-ticker case file (derived, read-only).")
    parser.add_argument("ticker")
    parser.add_argument("--today")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)
    case_file = build_case_file(args.ticker, args.today)
    if args.format == "json":
        print(json.dumps(case_file, indent=2, ensure_ascii=False))
    else:
        print(render_text(case_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
