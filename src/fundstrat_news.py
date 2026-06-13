"""Fundstrat News feed block for the cockpit.

This module does not ingest new Fundstrat content. It summarizes the compact
repo caches that the Fundstrat monthly and daily routines already own, then
labels gaps honestly when expected dashboard fields are not captured yet.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fundstrat_lanes import classify_fundstrat_lane


def _date_text(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if text else ""


def _age_days(source_date: Any, as_of: str | None) -> int | None:
    source_text = _date_text(source_date)
    as_of_text = _date_text(as_of)
    if not source_text or not as_of_text:
        return None
    try:
        return (date.fromisoformat(as_of_text) - date.fromisoformat(source_text)).days
    except ValueError:
        return None


def _ticker(item: Any) -> tuple[str, str]:
    if isinstance(item, dict):
        return str(item.get("ticker") or item.get("symbol") or "").strip().upper(), str(
            item.get("note") or item.get("name") or ""
        ).strip()
    return str(item or "").strip().upper(), ""


def _prospect_for(ticker: str, top_prospects: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(top_prospects, dict):
        return {}
    row = top_prospects.get(ticker) or top_prospects.get(ticker.upper())
    return row if isinstance(row, dict) else {}


def _price_label(value: Any) -> str:
    if value is None or value == "":
        return "not captured"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _monthly_rows(
    items: list[Any],
    *,
    list_name: str,
    direction: str,
    top_prospects: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(items or [], start=1):
        ticker, note = _ticker(item)
        if not ticker:
            continue
        prospect = _prospect_for(ticker, top_prospects)
        add_price = prospect.get("add_price")
        add_date = prospect.get("add_date")
        item_meta = item if isinstance(item, dict) else {}
        rows.append(
            {
                "rank": rank,
                "ticker": ticker,
                "direction": direction,
                "list": list_name,
                "note": note,
                "name": item_meta.get("name") or "",
                "report_move_pct": item_meta.get("report_move_pct"),
                "carry_over": bool(item_meta.get("carry_over")),
                "add_date": add_date or "",
                "add_price": add_price,
                "add_price_label": _price_label(add_price),
                "add_price_source": prospect.get("add_price_source") or "",
                "add_price_market_time": prospect.get("add_price_market_time") or "",
                "provenance": prospect.get("provenance") or "",
                "summary": prospect.get("summary") or "",
                "urgency": prospect.get("urgency") or "",
                "conviction": prospect.get("conviction") or "",
            }
        )
    return rows


def _find_rows_by_keys(
    deck: dict[str, Any] | None,
    top_prospects: dict[str, Any] | None,
    *,
    keys: tuple[str, ...],
    list_name: str,
    direction: str,
) -> list[dict[str, Any]]:
    deck = deck if isinstance(deck, dict) else {}
    for key in keys:
        if isinstance(deck.get(key), list) and deck.get(key):
            return _monthly_rows(
                deck.get(key) or [],
                list_name=list_name,
                direction=direction,
                top_prospects=top_prospects,
            )
    return []


def _find_smid_rows(
    deck: dict[str, Any] | None,
    top_prospects: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    deck = deck if isinstance(deck, dict) else {}
    found = _find_rows_by_keys(
        deck,
        top_prospects,
        keys=("top5_smid", "smid_top5", "top5_smidcap", "smid"),
        list_name="Top 5 SMID",
        direction="long",
    )
    if found:
        return found
    if not isinstance(top_prospects, dict):
        return []
    rows = []
    for ticker, prospect in top_prospects.items():
        if not isinstance(prospect, dict):
            continue
        blob = " ".join(
            str(prospect.get(key) or "")
            for key in ("provenance", "summary", "direction")
        )
        blob += " " + " ".join(
            str(event.get("note") or event.get("source") or event.get("category") or "")
            for event in prospect.get("events") or []
            if isinstance(event, dict)
        )
        if "SMID" not in blob.upper():
            continue
        row = _monthly_rows(
            [ticker],
            list_name="Top 5 SMID",
            direction=str(prospect.get("direction") or "long"),
            top_prospects=top_prospects,
        )[0]
        rows.append(row)
    rows.sort(key=lambda r: (r.get("rank") or 99, r.get("ticker") or ""))
    return rows


def _find_bottom_smid_rows(
    deck: dict[str, Any] | None,
    top_prospects: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return _find_rows_by_keys(
        deck if isinstance(deck, dict) else {},
        top_prospects,
        keys=("bottom5_smid", "smid_bottom5", "bottom5_smidcap"),
        list_name="Bottom 5 SMID",
        direction="avoid",
    )


def _daily_implication(row: dict[str, Any], lane: dict[str, Any]) -> str:
    direction = str(row.get("direction") or "").lower()
    domain = str(lane.get("source_domain") or "").lower()
    use_case = str(lane.get("use_case") or "").lower()
    if direction in {"avoid", "trim", "sell"}:
        return "avoid/re-check"
    if use_case == "risk_posture":
        return "hedge/re-check"
    if direction in {"watch", "wait"} or domain == "technical_timing":
        return "re-check timing"
    if direction in {"buy", "add", "long"}:
        return "research/size"
    return "context only"


def _daily_rows(calls: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in calls or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        lane = classify_fundstrat_lane(
            author=row.get("author") or "",
            text=row.get("quote") or "",
            ticker=ticker,
            subject=row.get("subject") or "",
            entry=row.get("entry"),
            stop=row.get("stop"),
            target=row.get("target"),
            window=row.get("window"),
        )
        out.append(
            {
                "date": _date_text(row.get("date")),
                "ticker": ticker,
                "author": row.get("author") or "Fundstrat",
                "direction": row.get("direction") or "",
                "subject": row.get("subject") or "",
                "quote": row.get("quote") or "",
                "fundstrat_lane": lane.get("fundstrat_lane") or "",
                "source_domain": lane.get("source_domain") or "",
                "author_role": lane.get("author_role") or "",
                "source_weight_note": lane.get("source_weight_note") or "",
                "confidence_policy": lane.get("confidence_policy") or "",
                "publication_type": lane.get("publication_type") or row.get("publication_type") or "",
                "capture_policy": lane.get("capture_policy") or row.get("capture_policy") or "",
                "use_case": lane.get("use_case") or row.get("use_case") or "",
                "decision_usefulness": lane.get("decision_usefulness") or row.get("decision_usefulness") or "",
                "capture_reason": lane.get("capture_reason") or row.get("capture_reason") or "",
                "action_implication": _daily_implication(row, lane),
            }
        )
    return sorted(out, key=lambda r: (r.get("date") or "", r.get("ticker") or ""), reverse=True)


def build_fundstrat_news(
    *,
    fundstrat_bible: dict[str, Any] | None = None,
    fundstrat_daily_calls: list[Any] | None = None,
    top_prospects: dict[str, Any] | None = None,
    intake_summary: dict[str, Any] | None = None,
    ingest_findings: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Build the feed block rendered by the Fundstrat News tab."""
    bible = fundstrat_bible if isinstance(fundstrat_bible, dict) else {}
    prospects = top_prospects if isinstance(top_prospects, dict) else {}
    summary = intake_summary if isinstance(intake_summary, dict) else {}
    deck_date = _date_text(bible.get("deck_date"))
    top_large = _monthly_rows(
        bible.get("top5") or [],
        list_name="Top 5 large cap",
        direction="long",
        top_prospects=prospects,
    )
    top_smid = _find_smid_rows(bible, prospects)
    bottom_large = _monthly_rows(
        bible.get("bottom5") or [],
        list_name="Bottom 5 large cap",
        direction="avoid",
        top_prospects=prospects,
    )
    bottom_smid = _find_bottom_smid_rows(bible, prospects)
    daily = _daily_rows(fundstrat_daily_calls if isinstance(fundstrat_daily_calls, list) else [])
    missing_prices = [
        row["ticker"]
        for row in top_large + top_smid + bottom_large + bottom_smid
        if row.get("add_price") is None
    ]
    gaps = []
    if top_large and missing_prices:
        gaps.append(
            {
                "key": "missing_add_prices",
                "severity": "warn",
                "line": (
                    f"Price when added is not captured for {len(missing_prices)} monthly list row(s): "
                    + ", ".join(missing_prices[:12])
                    + ("." if len(missing_prices) <= 12 else f" +{len(missing_prices)-12}.")
                ),
                "next_step": "Backfill from an approved historical price cache before using since-added performance.",
            }
        )
    if not top_smid:
        gaps.append(
            {
                "key": "missing_smid_top5",
                "severity": "warn",
                "line": "Top 5 SMID is not present in the live monthly bible/prospect caches.",
                "next_step": "Re-read the May 28 monthly material or supplied PDF text and store the SMID rows explicitly.",
            }
        )
    snippet_only = int(summary.get("snippet_only_entries") or 0)
    if snippet_only:
        gaps.append(
            {
                "key": "snippet_only_entries",
                "severity": "info",
                "line": f"{snippet_only} Fundstrat inbox item(s) were snippet-only in the latest intake summary.",
                "next_step": "Snippet-only discovery cannot be treated as synthesized full-body evidence.",
            }
        )
    for finding in ingest_findings or []:
        if not isinstance(finding, dict):
            continue
        gaps.append(
            {
                "key": finding.get("key") or "fs_ingest_guard",
                "severity": finding.get("severity") or "warn",
                "line": finding.get("line") or "",
                "next_step": finding.get("next_step") or "Complete the Fundstrat ingest inventory.",
                "source_id": finding.get("source_id") or "",
            }
        )
    daily_latest = daily[0]["date"] if daily else ""
    monthly_age = _age_days(deck_date, as_of)
    status = "has_data" if bible or daily else "not_checked"
    line = (
        f"Fundstrat News: monthly {deck_date or 'not checked'}; "
        f"Top 5 large cap {len(top_large)}, Top 5 SMID {len(top_smid) if top_smid else 'not captured'}, "
        f"daily calls {len(daily)}{f' latest {daily_latest}' if daily_latest else ''}."
    )
    return {
        "status": status,
        "line": line,
        "as_of": _date_text(as_of),
        "monthly": {
            "deck_date": deck_date,
            "source_file": bible.get("source_file") or "",
            "age_days": monthly_age,
            "freshness_label": "monthly baseline" if deck_date else "not checked",
            "freshness_judgment": (
                "Use as thesis/allocation baseline; do not treat as fresh tactical evidence without daily/tape confirmation."
                if deck_date
                else "Monthly source not checked."
            ),
            "allocation_plan": list(bible.get("what_to_own") or []),
            "top_large_cap": top_large,
            "top_smid": top_smid,
            "bottom5": bottom_large,
            "bottom5_smid": bottom_smid,
            "price_coverage": {
                "total_rows": len(top_large) + len(top_smid) + len(bottom_large) + len(bottom_smid),
                "missing_count": len(missing_prices),
                "missing_tickers": missing_prices,
            },
        },
        "daily": {
            "latest_date": daily_latest,
            "rows": daily,
            "count": len(daily),
            "full_body_entries": int(summary.get("full_body_entries") or 0),
            "snippet_only_entries": snippet_only,
            "stored_daily_calls": int(summary.get("stored_daily_calls") or len(daily)),
            "freshness_judgment": (
                "Daily calls are faster-decay tactical input; re-check price/tape before using them for capital timing."
                if daily
                else "No full-body daily calls are currently stored."
            ),
        },
        "gaps": gaps,
        "honesty_rule": (
            "Fundstrat is the baseline source of truth, but monthly list membership is not an execution trigger; "
            "stale, missing, or snippet-only data stays labeled."
        ),
    }


def build_if_i_were_you(feed: dict[str, Any]) -> dict[str, Any]:
    """Build a review-only prioritization block from the current feed."""
    actions = [row for row in feed.get("actions") or [] if isinstance(row, dict)]
    packet = feed.get("market_open_packet") or {}
    reallocation = feed.get("reallocation_brief") or {}
    fundstrat = feed.get("fundstrat_news") or {}
    rows: list[dict[str, Any]] = []

    top_action = actions[0] if actions else None
    if top_action:
        rows.append(
            {
                "rank": len(rows) + 1,
                "posture": "re-check/decide",
                "label": f"Start with {top_action.get('ticker') or 'the top action'}: {top_action.get('what') or 'top dashboard action'}",
                "why": top_action.get("why_this_matters") or top_action.get("why") or "It is the highest-ranked current action prompt.",
                "what_i_would_do": (
                    "Refresh the assumptions and either act through the gate, defer with a reason, or invalidate it. "
                    "I would not let it sit ambiguously."
                ),
                "source": top_action.get("source") or "actions",
            }
        )

    counts = packet.get("counts") if isinstance(packet, dict) else {}
    rechecks = int((counts or {}).get("recheck") or 0)
    if rechecks:
        rows.append(
            {
                "rank": len(rows) + 1,
                "posture": "wait/re-check",
                "label": f"Clear the {rechecks} re-check item(s) before moving meaningful capital.",
                "why": "Friday or fast-moving assumptions can become wrong after a Monday price/tape move.",
                "what_i_would_do": "Treat stale price-sensitive prompts as pending until same-session data confirms they are still asymmetric.",
                "source": "market_open_packet",
            }
        )

    realloc_rows = [
        row
        for row in reallocation.get("rows") or []
        if isinstance(row, dict) and row.get("action") == "ADD_CANDIDATE"
    ]
    if realloc_rows:
        top = realloc_rows[0]
        rows.append(
            {
                "rank": len(rows) + 1,
                "posture": "size/compare",
                "label": f"Compare the funded add candidates before parking capital: {top.get('ticker') or 'top candidate'} leads the current reallocation brief.",
                "why": reallocation.get("line") or "The reallocation brief ranks capital uses against funding legs.",
                "what_i_would_do": (
                    "Use the brief as a capital-efficiency screen: choose the best current use of capital, stage if confirmed, "
                    "and do not add a merely good idea ahead of a better one."
                ),
                "source": "reallocation_brief",
            }
        )

    fs_gaps = fundstrat.get("gaps") or []
    if fs_gaps:
        rows.append(
            {
                "rank": len(rows) + 1,
                "posture": "research/store",
                "label": "Fix Fundstrat storage gaps before over-weighting monthly list performance.",
                "why": "; ".join(str(g.get("line") or "") for g in fs_gaps[:2] if isinstance(g, dict)),
                "what_i_would_do": "Use the May 28 list as baseline context today, but backfill SMID rows and add prices before judging missed opportunity or since-added returns.",
                "source": "fundstrat_news",
            }
        )

    daily = (fundstrat.get("daily") or {}).get("rows") or []
    if daily:
        rows.append(
            {
                "rank": len(rows) + 1,
                "posture": "context/re-check",
                "label": "Use daily Fundstrat calls as timing filters, not standalone thesis changes.",
                "why": "The current stored daily rows are fast-decay technical/timing evidence.",
                "what_i_would_do": "Let them change add timing, hedge posture, or research priority only after live tape confirms the implication.",
                "source": "fundstrat_daily",
            }
        )

    if not rows:
        rows.append(
            {
                "rank": 1,
                "posture": "quiet watch",
                "label": "No capital-sized move is justified by the current feed alone.",
                "why": "The dashboard has no ranked action, reallocation, or Fundstrat prompt strong enough to promote.",
                "what_i_would_do": "Keep monitoring and preserve optionality until a sourced action changes posture.",
                "source": "feed",
            }
        )

    return {
        "status": "review_only",
        "line": f"If I were you: {len(rows)} review priority item(s), no execution from this section.",
        "rows": rows,
        "honesty_rule": "This is decision prioritization only; it does not place trades or bypass gates.",
    }
