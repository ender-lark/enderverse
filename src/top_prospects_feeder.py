#!/usr/bin/env python3
"""
top_prospects_feeder.py - turn Fundstrat picks into 🎯 Top Prospects rows + signal-events.

PIPELINE
    FS note / monthly report
      -> fs_ranker.rank_entry()            (extracts tickers, analyst, timestamp)
      -> picks_from_ranked() / Pick[]      (this module: ticker + source + category + direction)
      -> merge into top_prospects.json     (dedupe by source|category|date|direction)
      -> conviction_stack.compute_stack()  (recompute conviction + urgency per name)
      -> upsert 🎯 Top Prospects (Notion)  (create new / update existing; log event in body)

    The cache (top_prospects.json) is the canonical signal-event store; the Notion DB
    is the surfacing mirror (conviction/urgency/scores + the operator-set corroboration,
    note, dossier fields). Performance columns (Current Price / % Since Add / % vs SPY /
    Days Held) are filled by the separate performance pass, not here.

    NEVER trades. Capture + display only.

USAGE
    python top_prospects_feeder.py --self-test
    python top_prospects_feeder.py --demo        # dry-run, prints what it WOULD write
    (live ingest is driven by the cloud routine, which supplies parsed picks + a token)
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from conviction_stack import SignalEvent, compute_stack

# ----------------------------------------------------------------------------
# Targets / config
# ----------------------------------------------------------------------------
TOP_PROSPECTS_DS = "60f1db4b-df3f-4154-9603-e33799f11943"   # 🎯 Top Prospects data source
CACHE_PATH = Path(__file__).parent / "top_prospects.json"

# analyst string -> Source select option
SOURCE_MAP = {
    "farrell": "FS-Farrell", "lee": "FS-Lee", "newton": "FS-Newton",
    "fundstrat": "FS-Monthly", "monthly": "FS-Monthly",
    "granny": "FS-Granny", "grannyshots": "FS-Granny", "meridian": "Meridian",
}

# Farrell's BROAD crypto read feeds these proxies (ETH tracks the complex -> BMNR direction).
CRYPTO_TICKERS = {"BTC", "ETH", "SOL", "HYPE", "BMNR", "COIN", "MSTR",
                  "MARA", "RIOT", "IBIT", "ETHA", "HOOD"}


def map_source(analyst: str, report_type: str = "note") -> str:
    if report_type == "monthly":
        return "FS-Monthly"
    if report_type == "granny":
        return "FS-Granny"
    return SOURCE_MAP.get((analyst or "").strip().lower(), "Other")


def classify_category(analyst: str, ticker: str, report_type: str = "note",
                      hint: Optional[str] = None) -> str:
    """Map (analyst, ticker, report) -> a conviction_stack category. Heuristic + overridable."""
    if hint:
        return hint
    a = (analyst or "").strip().lower()
    if report_type in ("monthly", "granny"):
        return "analyst_named"
    if a == "newton":
        return "technical"
    if a == "farrell" and ticker.upper() in CRYPTO_TICKERS:
        return "crypto_read"
    return "analyst_named"


# ----------------------------------------------------------------------------
# Pick -> SignalEvent
# ----------------------------------------------------------------------------
@dataclass
class Pick:
    ticker: str
    analyst: str = ""
    date: str = ""
    direction: str = "long"        # "long" | "avoid"  (bottom-5 = avoid)
    report_type: str = "note"      # "note" | "monthly" | "granny"
    provenance: str = ""           # e.g. "FS Top 5 - Jun 2026"
    add_price: Optional[float] = None
    strength: str = "moderate"
    substantive: bool = False
    category_hint: Optional[str] = None
    note: str = ""


def pick_to_event(p: Pick) -> SignalEvent:
    return SignalEvent(
        ticker=p.ticker.upper(),
        source=map_source(p.analyst, p.report_type),
        category=classify_category(p.analyst, p.ticker, p.report_type, p.category_hint),
        date=p.date, direction=p.direction, strength=p.strength,
        substantive=p.substantive, note=p.note,
    )


def picks_from_ranked(entry: dict, direction: str = "long",
                      report_type: str = "note", provenance: str = "") -> List[Pick]:
    """Convert one fs_ranker.rank_entry() output into Picks (named tickers only)."""
    analyst = entry.get("analyst", "")
    ts = entry.get("timestamp", "")
    tickers = (list(entry.get("held_hits", [])) + list(entry.get("watchlist_hits", []))
               + list(entry.get("unknown_hits", [])) + list(entry.get("thesis_hits", {}).keys()))
    prov = provenance or entry.get("subject", "")
    picks, seen = [], set()
    for t in tickers:
        if t in seen:
            continue
        seen.add(t)
        picks.append(Pick(ticker=t, analyst=analyst, date=ts, direction=direction,
                          report_type=report_type, provenance=prov))
    return picks


def picks_from_granny_diff(findings: dict, date: str = "") -> List[Pick]:
    """Convert granny_diff.analyze_diff() output into Picks (FS-Granny source).

    - additions_vs_baseline -> Long (substantive: a fresh add to Lee's ETF)
    - lee_named_not_held     -> Long (ongoing endorsement)
    - weight_changes (up)    -> Long (substantive: Lee strengthening the weight)
    - dropped_held           -> Avoid (sell-fast: Lee removed a name you still hold)

    Weight DECREASES are left informational (not stacked) for now - a trim is a
    rebalance, not a sell call; only a full drop (dropped_held) is an Avoid signal.
    """
    picks: List[Pick] = []
    for item in findings.get("additions_vs_baseline", []):
        picks.append(Pick(ticker=item["ticker"], analyst="grannyshots", date=date,
                          direction="long", report_type="granny", substantive=True,
                          provenance=f"Granny Shots add ({item.get('etf','')})"))
    for item in findings.get("lee_named_not_held", []):
        picks.append(Pick(ticker=item["ticker"], analyst="grannyshots", date=date,
                          direction="long", report_type="granny",
                          provenance=f"Granny Shots holding ({item.get('etf','')} "
                                     f"{item.get('weight_pct','')}%)"))
    for item in findings.get("weight_changes", []):
        if item.get("change_pct", 0) > 0:
            picks.append(Pick(ticker=item["ticker"], analyst="grannyshots", date=date,
                              direction="long", report_type="granny", substantive=True,
                              provenance=f"Granny weight +{item['change_pct']:.1f}% "
                                         f"({item.get('etf','')})"))
    for item in findings.get("dropped_held", []):
        picks.append(Pick(ticker=item["ticker"], analyst="grannyshots", date=date,
                          direction="avoid", report_type="granny", strength="moderate",
                          provenance=f"Dropped from Granny Shots ({item.get('etf','')})"))
    return picks


# ----------------------------------------------------------------------------
# Cache merge + recompute
# ----------------------------------------------------------------------------
def load_cache(path=CACHE_PATH) -> Dict[str, dict]:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def save_cache(cache: Dict[str, dict], path=CACHE_PATH) -> None:
    Path(path).write_text(json.dumps(cache, indent=2, sort_keys=True))


def _ekey(source, category, date_, direction) -> str:
    return f"{source}|{category}|{date_}|{direction}"


def merge_picks(cache: Dict[str, dict], picks: List[Pick]) -> Dict[str, dict]:
    """Append picks as signal-events into the cache, deduped. Mutates + returns cache."""
    for p in picks:
        e = pick_to_event(p)
        rec = cache.setdefault(e.ticker, {
            "ticker": e.ticker, "events": [], "page_id": None,
            "add_price": None, "add_date": None, "provenance": "",
            "corroboration": "Uncorroborated", "research_queue_page_id": None,
        })
        existing = {_ekey(ev["source"], ev["category"], ev["date"], ev.get("direction", "long"))
                    for ev in rec["events"]}
        if _ekey(e.source, e.category, e.date, e.direction) not in existing:
            rec["events"].append(asdict(e))
        if rec["add_price"] is None and p.add_price is not None:
            rec["add_price"] = p.add_price
        if not rec["add_date"] and p.date:
            rec["add_date"] = p.date
        if not rec["provenance"] and p.provenance:
            rec["provenance"] = p.provenance
    return cache


def recompute(cache: Dict[str, dict], now=None, weights=None) -> Dict[str, dict]:
    """Recompute conviction/urgency per name from its stored events. Mutates + returns cache."""
    for tk, rec in cache.items():
        events = [SignalEvent(
            ticker=tk, source=ev["source"], category=ev["category"], date=ev["date"],
            direction=ev.get("direction", "long"), strength=ev.get("strength", "moderate"),
            substantive=ev.get("substantive", False), judgment_mult=ev.get("judgment_mult", 1.0),
            note=ev.get("note", "")) for ev in rec["events"]]
        r = compute_stack(events, now=now, weights=weights)
        rec.update({
            "conviction": r.conviction_level, "urgency": r.urgency_level,
            "conviction_score": r.conviction, "urgency_score": r.urgency,
            "direction": r.direction, "summary": r.summary,
            "sources": sorted({ev["source"] for ev in rec["events"]}),
        })
    return cache


# ----------------------------------------------------------------------------
# Notion property payloads (raw REST format for notion_helpers)
# ----------------------------------------------------------------------------
def _title(s): return {"title": [{"text": {"content": s}}]}
def _txt(s): return {"rich_text": [{"text": {"content": (s or "")[:1990]}}]}
def _sel(name): return {"select": {"name": name}} if name else {"select": None}
def _msel(names): return {"multi_select": [{"name": n} for n in names]}
def _num(x): return {"number": x}
def _date(s): return {"date": {"start": s}} if s else {"date": None}
def _chk(b): return {"checkbox": bool(b)}


def notion_properties(rec: dict, new: bool) -> dict:
    dir_label = "Avoid" if rec.get("direction") == "avoid" else "Long"
    props = {
        "Ticker": _title(rec["ticker"]),
        "Direction": _sel(dir_label),
        "Sources": _msel(rec.get("sources", [])),
        "Conviction": _sel(rec.get("conviction", "QUIET")),
        "Urgency": _sel(rec.get("urgency", "QUIET")),
        "Conviction Score": _num(rec.get("conviction_score", 0)),
        "Urgency Score": _num(rec.get("urgency_score", 0)),
    }
    if rec.get("provenance"):
        props["Provenance"] = _txt(rec["provenance"])
    if rec.get("add_price") is not None:
        props["Add Price"] = _num(rec["add_price"])
    if rec.get("add_date"):
        props["Add Date"] = _date(rec["add_date"])
    # Performance columns (filled by prospect_performance; present only after a price pass)
    if rec.get("current_price") is not None:
        props["Current Price"] = _num(rec["current_price"])
    if rec.get("pct_since_add") is not None:
        props["% Since Add"] = _num(rec["pct_since_add"])
    if rec.get("pct_vs_spy") is not None:
        props["% vs SPY"] = _num(rec["pct_vs_spy"])
    if rec.get("days_held") is not None:
        props["Days Held"] = _num(rec["days_held"])
    if new:
        props["Corroboration"] = _sel("Uncorroborated")
        props["Still Listed"] = _chk(True)
    return props


def _extract_page_id(res) -> Optional[str]:
    for attr in ("page_id", "id"):
        v = getattr(res, attr, None)
        if v:
            return v
    data = getattr(res, "data", None)
    if isinstance(data, dict) and data.get("id"):
        return data["id"]
    if isinstance(res, dict) and res.get("id"):
        return res["id"]
    return None


def upsert(cache: Dict[str, dict], client, ds_id: str = TOP_PROSPECTS_DS,
           log_events: bool = True) -> Dict[str, dict]:
    """Create/update a Notion row per cached ticker via `client` (notion_helpers or dry_run).

    `client` needs create_page(parent, properties) and update_page_properties(page_id, props),
    and optionally safe_append_paragraph(page_id, text). Mutates cache (stores page_id).
    """
    for tk, rec in cache.items():
        is_new = not rec.get("page_id")
        props = notion_properties(rec, new=is_new)
        if is_new:
            res = client.create_page(
                parent={"type": "data_source_id", "data_source_id": ds_id}, properties=props)
            pid = _extract_page_id(res)
            if pid:
                rec["page_id"] = pid
        else:
            client.update_page_properties(rec["page_id"], props)
        # Log the latest event line into the page body (best-effort).
        if log_events and rec.get("page_id") and rec.get("events") and hasattr(client, "safe_append_paragraph"):
            last = rec["events"][-1]
            client.safe_append_paragraph(
                rec["page_id"],
                f"[{last['date']}] {last['source']} - {last['category']} "
                f"({last.get('direction','long')}) {last.get('note','')}".strip())
    return cache


def live_client(dry_run: bool = False):
    """Construct the real notion_helpers client (imported lazily; needs NOTION_API_TOKEN)."""
    import notion_helpers  # noqa: E402
    return notion_helpers.NotionClient(dry_run=dry_run)


def ingest(picks: List[Pick], client=None, now=None, persist: bool = True) -> Dict[str, dict]:
    """End-to-end: load cache -> merge picks -> recompute -> (optional) upsert -> save."""
    cache = load_cache()
    merge_picks(cache, picks)
    recompute(cache, now=now)
    if client is not None:
        upsert(cache, client)
    if persist:
        save_cache(cache)
    return cache


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
class _FakeClient:
    """Records calls so we can test upsert branching without a token or network."""
    def __init__(self):
        self.created, self.updated, self.appended = [], [], []
        self._n = 0

    def create_page(self, parent, properties, children=None):
        self._n += 1
        self.created.append((parent, properties))
        return {"id": f"page-{self._n}"}

    def update_page_properties(self, page_id, properties):
        self.updated.append((page_id, properties))
        return {"id": page_id}

    def safe_append_paragraph(self, page_id, text):
        self.appended.append((page_id, text))
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

    # 1. source mapping
    check("Farrell -> FS-Farrell", map_source("Farrell") == "FS-Farrell")
    check("Lee -> FS-Lee", map_source("Lee") == "FS-Lee")
    check("monthly overrides analyst", map_source("Lee", "monthly") == "FS-Monthly")
    check("unknown analyst -> Other", map_source("Bob") == "Other")

    # 2. category classification
    check("Newton -> technical", classify_category("Newton", "ANET") == "technical")
    check("Farrell+ETH -> crypto_read", classify_category("Farrell", "ETH") == "crypto_read")
    check("Farrell+ANET -> analyst_named", classify_category("Farrell", "ANET") == "analyst_named")
    check("monthly -> analyst_named", classify_category("", "X", "monthly") == "analyst_named")
    check("hint overrides", classify_category("Newton", "X", hint="catalyst") == "catalyst")

    # 3. pick_to_event
    e = pick_to_event(Pick("aapl", "Lee", "2026-06-01", provenance="x"))
    check("pick_to_event upper ticker", e.ticker == "AAPL")
    check("pick_to_event source", e.source == "FS-Lee")

    # 4. picks_from_ranked
    entry = {"analyst": "Newton", "timestamp": "2026-06-08", "subject": "Tech update",
             "held_hits": ["NVDA"], "watchlist_hits": ["ANET"], "unknown_hits": [],
             "thesis_hits": {}}
    picks = picks_from_ranked(entry)
    check("picks_from_ranked count", len(picks) == 2)
    check("picks_from_ranked provenance from subject", picks[0].provenance == "Tech update")

    # 5. merge + dedupe
    cache = {}
    merge_picks(cache, [Pick("AAA", "Lee", "2026-06-01")])
    merge_picks(cache, [Pick("AAA", "Lee", "2026-06-01")])   # exact dup -> not re-added
    check("merge dedupes exact event", len(cache["AAA"]["events"]) == 1)
    merge_picks(cache, [Pick("AAA", "Newton", "2026-06-05")])  # diff source -> added
    check("merge adds independent event", len(cache["AAA"]["events"]) == 2)

    # 6. recompute sets levels
    recompute(cache, now="2026-06-06")
    check("recompute sets conviction level", cache["AAA"]["conviction"] in
          ("QUIET", "BUILDING", "HOT", "ACT_NOW"))
    check("recompute records both sources", cache["AAA"]["sources"] == ["FS-Lee", "FS-Newton"])

    # 7. notion_properties shape (new row)
    rec = {"ticker": "AAA", "direction": "long", "sources": ["FS-Lee"],
           "conviction": "HOT", "urgency": "BUILDING", "conviction_score": 20,
           "urgency_score": 8, "provenance": "FS Top 5 - Jun 2026",
           "add_price": 123.4, "add_date": "2026-06-01"}
    props = notion_properties(rec, new=True)
    check("props Ticker title", props["Ticker"]["title"][0]["text"]["content"] == "AAA")
    check("props Direction select", props["Direction"]["select"]["name"] == "Long")
    check("props Sources multi", props["Sources"]["multi_select"][0]["name"] == "FS-Lee")
    check("props Conviction select", props["Conviction"]["select"]["name"] == "HOT")
    check("props Add Price number", props["Add Price"]["number"] == 123.4)
    check("props Add Date start", props["Add Date"]["date"]["start"] == "2026-06-01")
    check("new row gets Corroboration", props["Corroboration"]["select"]["name"] == "Uncorroborated")
    check("new row Still Listed true", props["Still Listed"]["checkbox"] is True)

    # 8. avoid direction -> Avoid label
    rec_av = {"ticker": "BBB", "direction": "avoid", "sources": ["FS-Monthly"],
              "conviction": "BUILDING", "urgency": "QUIET", "conviction_score": 10, "urgency_score": 0}
    check("avoid -> Direction Avoid", notion_properties(rec_av, new=False)["Direction"]["select"]["name"] == "Avoid")

    # 9. upsert branching with fake client: new -> create, existing -> update
    fc = _FakeClient()
    cache2 = {"NEW": {"ticker": "NEW", "events": [{"source": "FS-Lee", "category": "analyst_named",
              "date": "2026-06-01", "direction": "long"}], "page_id": None, "sources": ["FS-Lee"],
              "conviction": "BUILDING", "urgency": "QUIET", "conviction_score": 10, "urgency_score": 0,
              "direction": "long", "add_price": None, "add_date": "2026-06-01", "provenance": ""}}
    upsert(cache2, fc)
    check("upsert creates new row", len(fc.created) == 1)
    check("upsert stores page_id", cache2["NEW"]["page_id"] == "page-1")
    check("upsert logs event to body", len(fc.appended) == 1)
    upsert(cache2, fc)   # now has page_id -> update path
    check("upsert updates existing row", len(fc.updated) == 1 and len(fc.created) == 1)

    # 10. bottom-5 path: avoid picks recompute to avoid direction
    cb = {}
    merge_picks(cb, picks_from_ranked(
        {"analyst": "Fundstrat", "timestamp": "2026-06-01", "subject": "Bottom 5 Jun",
         "held_hits": ["XYZ"], "watchlist_hits": [], "unknown_hits": [], "thesis_hits": {}},
        direction="avoid", report_type="monthly", provenance="FS Bottom 5 - Jun 2026"))
    recompute(cb, now="2026-06-02")
    check("bottom-5 -> avoid direction", cb["XYZ"]["direction"] == "avoid")
    check("bottom-5 source FS-Monthly", cb["XYZ"]["sources"] == ["FS-Monthly"])

    # 11. granny adapter: additions/holdings -> Long, drops -> Avoid
    findings = {
        "additions_vs_baseline": [{"ticker": "PWR", "etf": "GRNY", "weight_pct": 2.1, "operator_holds": False}],
        "lee_named_not_held": [{"ticker": "NVDA", "etf": "GRNY", "rank": 1, "weight_pct": 5.0, "on_watchlist": True}],
        "weight_changes": [{"ticker": "VRT", "etf": "GRNY", "prior_weight": 1.0, "current_weight": 2.0, "change_pct": 1.0, "operator_holds": True},
                            {"ticker": "OLD", "etf": "GRNY", "prior_weight": 3.0, "current_weight": 2.0, "change_pct": -1.0, "operator_holds": True}],
        "dropped_held": [{"ticker": "LULU", "etf": "GRNY", "prior_weight": 1.5}],
    }
    gp = picks_from_granny_diff(findings, date="2026-06-03")
    gtix = {p.ticker: p for p in gp}
    check("granny addition -> Long substantive", gtix["PWR"].direction == "long" and gtix["PWR"].substantive)
    check("granny holding -> Long", gtix["NVDA"].direction == "long")
    check("granny weight-up -> Long substantive", gtix["VRT"].direction == "long" and gtix["VRT"].substantive)
    check("granny weight-down -> no pick", "OLD" not in gtix)
    check("granny drop -> Avoid", gtix["LULU"].direction == "avoid")
    check("granny source maps FS-Granny", pick_to_event(gtix["PWR"]).source == "FS-Granny")

    # 12. granny end-to-end: dropped name recomputes to avoid
    gc = {}
    merge_picks(gc, gp)
    recompute(gc, now="2026-06-04")
    check("granny e2e: LULU avoid direction", gc["LULU"]["direction"] == "avoid")
    check("granny e2e: PWR long direction", gc["PWR"]["direction"] == "long")

    print(f"\n{passed}/{passed + failed} assertions passed.")
    return failed == 0


def _demo() -> None:
    """Dry-run: show what the feeder would write for the ANET example."""
    fc = _FakeClient()
    cache = {}
    merge_picks(cache, picks_from_ranked(
        {"analyst": "Fundstrat", "timestamp": "2026-06-01", "subject": "Top 5 Jun 2026",
         "held_hits": [], "watchlist_hits": ["ANET"], "unknown_hits": [], "thesis_hits": {}},
        direction="long", report_type="monthly", provenance="FS Top 5 - Jun 2026"))
    merge_picks(cache, picks_from_ranked(
        {"analyst": "Newton", "timestamp": "2026-06-08", "subject": "Technicals strong",
         "held_hits": [], "watchlist_hits": ["ANET"], "unknown_hits": [], "thesis_hits": {}}))
    recompute(cache, now="2026-06-09")
    upsert(cache, fc)
    print("Would create rows:")
    for tk, rec in cache.items():
        print(f"  {tk}: {rec['summary']}  sources={rec['sources']}  "
              f"conv={rec['conviction_score']}({rec['conviction']}) urg={rec['urgency_score']}({rec['urgency']})")
    print(f"\n  create_page calls: {len(fc.created)} | body-log lines: {len(fc.appended)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Top Prospects feeder (FS picks -> rows + signal-events).")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true", help="Dry-run; print what it would write.")
    args = ap.parse_args()
    if args.self_test:
        return 0 if _self_test() else 1
    if args.demo:
        _demo()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
