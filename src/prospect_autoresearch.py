#!/usr/bin/env python3
"""
prospect_autoresearch.py - auto-queue uncorroborated 🎯 Top Prospects for research.

An UNCORROBORATED prospect automatically gets a 📚 Research Queue row (Status=Queued)
so the Off-Hours Worker dossiers it overnight - then its Corroboration flips to
"Auto-research queued" so it is never re-queued. This is the "auto-research every
top pick" hook; it reuses the Off-Hours Worker you already run (no change to it).

Idempotent: only prospects with corroboration == "Uncorroborated" AND no existing
research_queue_page_id are queued. Anything further along (Have notes / Vetted /
Acted) is left alone.

    python prospect_autoresearch.py --self-test
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import top_prospects_feeder as tpf

RESEARCH_QUEUE_DS = "cab89576-0933-40b0-ad2e-6f9a6188e804"   # 📚 Research Queue (data-source handle)
TOP_PROSPECTS_DS = tpf.TOP_PROSPECTS_DS

# Urgency -> Research Queue Priority (High/Med/Low)
PRIORITY_FROM_URGENCY = {"ACT_NOW": "High", "HOT": "High", "BUILDING": "Med", "QUIET": "Low"}
LEVEL_RANK = {"QUIET": 0, "BUILDING": 1, "HOT": 2, "ACT_NOW": 3}


def _level_rank(value: str | None) -> int:
    return LEVEL_RANK.get(str(value or "QUIET").upper(), 0)


def _is_unqueued_uncorroborated(rec: dict) -> bool:
    return (
        rec.get("corroboration", "Uncorroborated") == "Uncorroborated"
        and not rec.get("research_queue_page_id")
    )


def prospect_priority_key(item: tuple[str, dict]) -> tuple:
    """Sort key for picking the most useful prospects first."""
    tk, rec = item
    return (
        _level_rank(rec.get("urgency")),
        float(rec.get("urgency_score") or 0),
        _level_rank(rec.get("conviction")),
        float(rec.get("conviction_score") or 0),
        1 if rec.get("direction") == "avoid" else 0,
        str(tk),
    )


def select_prospects(
    cache: Dict[str, dict],
    *,
    max_items: int | None = None,
    min_urgency: str = "QUIET",
    min_conviction: str | None = None,
    include_avoid: bool = True,
) -> list[tuple[str, dict]]:
    """Return eligible Top Prospects in the order they should be queued."""
    min_urgency_rank = _level_rank(min_urgency)
    min_conviction_rank = _level_rank(min_conviction) if min_conviction else None
    rows: list[tuple[str, dict]] = []
    for tk, rec in cache.items():
        if not isinstance(rec, dict) or not _is_unqueued_uncorroborated(rec):
            continue
        if not include_avoid and rec.get("direction") == "avoid":
            continue
        if _level_rank(rec.get("urgency")) < min_urgency_rank:
            continue
        if min_conviction_rank is not None and _level_rank(rec.get("conviction")) < min_conviction_rank:
            continue
        rows.append((tk, rec))
    rows.sort(key=prospect_priority_key, reverse=True)
    if max_items and max_items > 0:
        rows = rows[:max_items]
    return rows


def build_rq_properties(rec: dict) -> dict:
    """Notion REST properties for a new Research Queue row from a prospect rec."""
    tk = rec["ticker"]
    sources = ", ".join(rec.get("sources", [])) or "FS"
    reason = (f"Auto-queued from 🎯 Top Prospects. {rec.get('summary', '')} "
              f"Sources: {sources}. Provenance: {rec.get('provenance', '')}. "
              f"Conviction {rec.get('conviction', '?')} / urgency {rec.get('urgency', '?')}. "
              f"Vet the thesis; corroborate or pass.").strip()
    return {
        "Topic": tpf._title(f"Vet prospect: {tk}"),
        "Ticker": tpf._txt(tk),
        "Reason": tpf._txt(reason),
        "Priority": tpf._sel(PRIORITY_FROM_URGENCY.get(rec.get("urgency", "QUIET"), "Low")),
        "Status": tpf._sel("Queued"),
    }


def queue_uncorroborated(
    cache: Dict[str, dict],
    client,
    rq_ds: str = RESEARCH_QUEUE_DS,
    *,
    max_items: int | None = None,
    min_urgency: str = "QUIET",
    min_conviction: str | None = None,
    include_avoid: bool = True,
) -> List[str]:
    """Queue every uncorroborated, not-yet-queued prospect for Off-Hours research.

    Mutates cache (sets research_queue_page_id + corroboration). Returns queued tickers.
    `client` needs create_page(parent, properties) and update_page_properties(page_id, props).
    """
    queued: List[str] = []
    for tk, rec in select_prospects(
        cache,
        max_items=max_items,
        min_urgency=min_urgency,
        min_conviction=min_conviction,
        include_avoid=include_avoid,
    ):
        # 1. create the Research Queue row (Queued)
        res = client.create_page(
            parent={"type": "data_source_id", "data_source_id": rq_ds},
            properties=build_rq_properties(rec))
        rq_pid = tpf._extract_page_id(res)
        rec["research_queue_page_id"] = rq_pid
        rec["corroboration"] = "Auto-research queued"
        # 2. flip the prospect row's Corroboration (only if it has a Notion page yet)
        if rec.get("page_id"):
            client.update_page_properties(
                rec["page_id"], {"Corroboration": tpf._sel("Auto-research queued")})
        queued.append(tk)
    return queued


def run(
    cache_path=None,
    client=None,
    *,
    max_items: int | None = None,
    min_urgency: str = "QUIET",
    min_conviction: str | None = None,
    include_avoid: bool = True,
):
    """Load cache -> queue uncorroborated -> save. Live client from feeder.live_client()."""
    cache = tpf.load_cache(cache_path or tpf.CACHE_PATH)
    if client is None:
        client = tpf.live_client()
    queued = queue_uncorroborated(
        cache,
        client,
        max_items=max_items,
        min_urgency=min_urgency,
        min_conviction=min_conviction,
        include_avoid=include_avoid,
    )
    tpf.save_cache(cache, cache_path or tpf.CACHE_PATH)
    return queued


def _preview_rows(rows: list[tuple[str, dict]]) -> list[dict]:
    return [
        {
            "ticker": tk,
            "direction": rec.get("direction"),
            "conviction": rec.get("conviction"),
            "urgency": rec.get("urgency"),
            "conviction_score": rec.get("conviction_score"),
            "urgency_score": rec.get("urgency_score"),
            "priority": PRIORITY_FROM_URGENCY.get(rec.get("urgency", "QUIET"), "Low"),
            "corroboration": rec.get("corroboration", "Uncorroborated"),
            "research_queue_page_id": rec.get("research_queue_page_id"),
        }
        for tk, rec in rows
    ]


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
class _FakeClient:
    def __init__(self):
        self.created, self.updated = [], []
        self._n = 0

    def create_page(self, parent, properties, children=None):
        self._n += 1
        self.created.append((parent, properties))
        return {"id": f"rq-{self._n}"}

    def update_page_properties(self, page_id, properties):
        self.updated.append((page_id, properties))
        return {"id": page_id}


def _self_test() -> bool:
    passed = failed = 0

    def check(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    # priority mapping
    check("HOT -> High", PRIORITY_FROM_URGENCY["HOT"] == "High")
    check("BUILDING -> Med", PRIORITY_FROM_URGENCY["BUILDING"] == "Med")
    check("QUIET -> Low", PRIORITY_FROM_URGENCY["QUIET"] == "Low")

    # RQ props shape
    rec = {"ticker": "ANET", "sources": ["FS-Monthly", "FS-Newton"], "summary": "ANET: conviction HOT",
           "provenance": "FS Top 5 - Jun 2026", "conviction": "HOT", "urgency": "HOT"}
    props = build_rq_properties(rec)
    check("RQ Topic title", props["Topic"]["title"][0]["text"]["content"] == "Vet prospect: ANET")
    check("RQ Ticker text", props["Ticker"]["rich_text"][0]["text"]["content"] == "ANET")
    check("RQ Status Queued", props["Status"]["select"]["name"] == "Queued")
    check("RQ Priority High (HOT)", props["Priority"]["select"]["name"] == "High")

    # queue an uncorroborated prospect
    fc = _FakeClient()
    cache = {
        "ANET": {"ticker": "ANET", "page_id": "pp-1", "corroboration": "Uncorroborated",
                 "research_queue_page_id": None, "sources": ["FS-Monthly"], "urgency": "HOT",
                 "conviction": "HOT", "summary": "s", "provenance": "p"},
        "DONE": {"ticker": "DONE", "page_id": "pp-2", "corroboration": "Vetted-Buy",
                 "research_queue_page_id": None, "sources": ["FS-Lee"], "urgency": "QUIET"},
        "GOOGL": {"ticker": "GOOGL", "page_id": "pp-3", "corroboration": "Uncorroborated",
                  "research_queue_page_id": None, "sources": ["FS-Monthly"], "urgency": "BUILDING",
                  "urgency_score": 8, "conviction": "BUILDING", "conviction_score": 12,
                  "summary": "s", "provenance": "p"},
    }
    selected = select_prospects(cache, max_items=1, min_urgency="BUILDING")
    check("selector caps and ranks highest urgency first", selected == [("ANET", cache["ANET"])])
    check("selector can find BUILDING backlog", [tk for tk, _ in select_prospects(cache, min_urgency="BUILDING")] == ["ANET", "GOOGL"])

    queued = queue_uncorroborated(cache, fc, max_items=1, min_urgency="BUILDING")
    check("queues the uncorroborated one", queued == ["ANET"])
    check("skips the Vetted-Buy one", "DONE" not in queued)
    check("creates exactly one RQ row", len(fc.created) == 1)
    check("RQ row goes to Research Queue ds",
          fc.created[0][0]["data_source_id"] == RESEARCH_QUEUE_DS)
    check("stores research_queue_page_id", cache["ANET"]["research_queue_page_id"] == "rq-1")
    check("flips corroboration", cache["ANET"]["corroboration"] == "Auto-research queued")
    check("updates prospect row Corroboration",
          fc.updated and fc.updated[0][1]["Corroboration"]["select"]["name"] == "Auto-research queued")
    check("cap leaves other eligible prospect untouched",
          cache["GOOGL"]["corroboration"] == "Uncorroborated")

    # idempotent for the already-queued HOT item.
    fc2 = _FakeClient()
    again = queue_uncorroborated(cache, fc2, max_items=1, min_urgency="HOT")
    check("idempotent: no re-queue", again == [] and len(fc2.created) == 0)

    # Broader later passes can still advance the next eligible item.
    fc3 = _FakeClient()
    next_batch = queue_uncorroborated(cache, fc3, max_items=1, min_urgency="BUILDING")
    check("later capped pass queues next eligible item", next_batch == ["GOOGL"])

    print(f"\n{passed}/{passed + failed} assertions passed.")
    return failed == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-queue uncorroborated Top Prospects for research.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--cache", default=str(tpf.CACHE_PATH))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-items", type=int, default=0, help="0 means no cap")
    ap.add_argument("--min-urgency", choices=sorted(LEVEL_RANK), default="QUIET")
    ap.add_argument("--min-conviction", choices=sorted(LEVEL_RANK))
    ap.add_argument("--exclude-avoid", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return 0 if _self_test() else 1
    cache_path = Path(args.cache)
    cache = tpf.load_cache(cache_path)
    max_items = args.max_items if args.max_items > 0 else None
    if args.dry_run:
        rows = select_prospects(
            cache,
            max_items=max_items,
            min_urgency=args.min_urgency,
            min_conviction=args.min_conviction,
            include_avoid=not args.exclude_avoid,
        )
        print(json.dumps({
            "dry_run": True,
            "selected": len(rows),
            "rows": _preview_rows(rows),
        }, indent=2))
        return 0
    queued = run(
        cache_path,
        max_items=max_items,
        min_urgency=args.min_urgency,
        min_conviction=args.min_conviction,
        include_avoid=not args.exclude_avoid,
    )
    print(json.dumps({"queued": queued, "count": len(queued)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
