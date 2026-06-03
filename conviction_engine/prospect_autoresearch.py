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
from typing import Dict, List, Optional

import top_prospects_feeder as tpf

RESEARCH_QUEUE_DS = "cab89576-0933-40b0-ad2e-6f9a6188e804"   # 📚 Research Queue (data-source handle)
TOP_PROSPECTS_DS = tpf.TOP_PROSPECTS_DS

# Urgency -> Research Queue Priority (High/Med/Low)
PRIORITY_FROM_URGENCY = {"ACT_NOW": "High", "HOT": "High", "BUILDING": "Med", "QUIET": "Low"}


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


def queue_uncorroborated(cache: Dict[str, dict], client,
                         rq_ds: str = RESEARCH_QUEUE_DS) -> List[str]:
    """Queue every uncorroborated, not-yet-queued prospect for Off-Hours research.

    Mutates cache (sets research_queue_page_id + corroboration). Returns queued tickers.
    `client` needs create_page(parent, properties) and update_page_properties(page_id, props).
    """
    queued: List[str] = []
    for tk, rec in cache.items():
        if rec.get("corroboration", "Uncorroborated") != "Uncorroborated":
            continue
        if rec.get("research_queue_page_id"):
            continue
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


def run(cache_path=None, client=None):
    """Load cache -> queue uncorroborated -> save. Live client from feeder.live_client()."""
    cache = tpf.load_cache(cache_path or tpf.CACHE_PATH)
    if client is None:
        client = tpf.live_client()
    queued = queue_uncorroborated(cache, client)
    tpf.save_cache(cache, cache_path or tpf.CACHE_PATH)
    return queued


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
    }
    queued = queue_uncorroborated(cache, fc)
    check("queues the uncorroborated one", queued == ["ANET"])
    check("skips the Vetted-Buy one", "DONE" not in queued)
    check("creates exactly one RQ row", len(fc.created) == 1)
    check("RQ row goes to Research Queue ds",
          fc.created[0][0]["data_source_id"] == RESEARCH_QUEUE_DS)
    check("stores research_queue_page_id", cache["ANET"]["research_queue_page_id"] == "rq-1")
    check("flips corroboration", cache["ANET"]["corroboration"] == "Auto-research queued")
    check("updates prospect row Corroboration",
          fc.updated and fc.updated[0][1]["Corroboration"]["select"]["name"] == "Auto-research queued")

    # idempotent: running again queues nothing
    fc2 = _FakeClient()
    again = queue_uncorroborated(cache, fc2)
    check("idempotent: no re-queue", again == [] and len(fc2.created) == 0)

    print(f"\n{passed}/{passed + failed} assertions passed.")
    return failed == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-queue uncorroborated Top Prospects for research.")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return 0 if _self_test() else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
