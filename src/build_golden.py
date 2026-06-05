"""Conviction Engine · regenerate the golden oracle (committed build tool).

ONE command rebuilds both frozen fixtures from source and re-freezes them:
  • golden_snapshot.json — the 5/27–5/29 inputs behind cockpit v4 (literal cards
    + the 14 theses.json names + IBIT, with the burned-sleeve stance overlay).
  • golden_feed.json     — the corrected-v4 oracle, produced by feed_assembler
    over the snapshot.

It self-checks at every step (validates each item, the snapshot, and the feed;
runs the reads through to confirm the cv/cd enums + the fresh-set; only writes if
everything passes). This is the *source of truth* for the oracle — when a rule or
prose change is INTENTIONAL, re-run `python build_golden.py` and re-commit the two
JSONs. The golden-master test (test_golden_master.py) is the wall that catches
UNintentional drift. Never hand-edit the JSONs.

Usage:
    python build_golden.py            # rebuild + freeze (writes the two JSONs)
    python build_golden.py --check    # rebuild in memory, fail on drift, write nothing
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from validators import validate_source_item, validate_collected_snapshot, validate_cockpit_feed
import analyst_judgment as J
from feed_assembler import assemble_feed

AS_OF = "2026-05-29"
PARABOLIC = {"MU"}

# the cv·cd the oracle must reproduce (independently verified at A5 against the
# hand-derived cockpit-v4 expectations + the 3 operator decisions)
ENUM_TARGETS = {
    "SMH": ("Strong", "flat"), "MAGS": ("Strong", "flat"), "NVDA": ("Strong", "flat"),
    "MU": ("Strong", "flat"), "GRNY": ("Strong", "flat"), "AVGO": ("—", "flat"),
    "ANET": ("Promising", "flat"), "XLF": ("Promising", "up"), "LEU": ("Promising", "flat"),
    "MP": ("Promising", "flat"), "UUUU": ("Mixed", "down"), "BMNR": ("Mixed", "flat"),
    "IBIT": ("Promising", "up"), "VOLT": ("Promising", "flat"), "ITA": ("Promising", "up"),
    "AMZN": ("—", "flat"), "COST": ("—", "flat"), "MSFT": ("—", "flat"),
}
FRESH_TARGET = sorted([("ITA", "act"), ("FN", "watch")])


# --------------------------------------------------------------------------- #
# 1) build the snapshot inputs (literal cards)
# --------------------------------------------------------------------------- #
def build_snapshot_bundle() -> dict:
    items = []

    def card(source, kind, subject, content, ts, trust, grp, **data):
        items.append({"source": source, "kind": kind, "subject": subject,
                      "content": content, "timestamp": ts, "trust_weight": trust,
                      "independence_group": grp, "data": dict(data)})

    # ── ROTATION (uw_price · 5/29) ──
    rot = [("SMH", 0.08, 0.37, 0.47), ("IGV", 0.20, 0.14, 0.24), ("GRNY", 0.00, 0.00, 0.10),
           ("VOLT", -0.06, 0.01, 0.05), ("IBIT", -0.09, 0.10, 0.18), ("XLF", -0.03, -0.10, -0.02),
           ("REMX", -0.02, -0.10, 0.01), ("URA", -0.08, -0.17, -0.12), ("GDX", -0.10, -0.33, -0.20)]
    for s, r1, r3, a3 in rot:
        card("uw_price", "rotation", s, f"{s} {r3:+.0%}/3M vs mkt", "2026-05-29", 0.95,
             "market_data", rel_1m=r1, rel_3m=r3, abs_3m=a3, rel_3m_vs_smh=round(r3 - 0.37, 2))

    # ── MACRO (uw_macro · 5/29) ──
    card("uw_macro", "macro", "10Y", "10Y 4.45% (-1bp 5d)", "2026-05-29", 0.95, "market_data",
         value=4.45, value_5d_ago=4.46, chg_5d=-1, unit="%", metric="10Y")
    card("uw_macro", "macro", "2s10s", "2s10s +46bp (+1bp 5d)", "2026-05-29", 0.95, "market_data",
         value=46, value_5d_ago=45, chg_5d=1, unit="bp", metric="2s10s")
    card("uw_macro", "macro", "30Y", "30Y 4.98%", "2026-05-29", 0.95, "market_data",
         value=4.98, value_5d_ago=4.99, chg_5d=-1, unit="%", metric="30Y")
    card("uw_macro", "macro", "DXY", "DXY 99.5 (flat 5d)", "2026-05-29", 0.95, "market_data",
         value=99.5, value_5d_ago=99.4, chg_5d=0.1, unit="pt", metric="DXY")

    # ── FUNDSTRAT BIBLE (5/28) ──
    card("fundstrat_bible", "stance", "FS macro", "Risk-on; FS Tech double-overweight",
         "2026-05-28", 0.70, "fundstrat", date="2026-05-28")
    for tk in ("SMH", "MAGS", "NVDA", "MU", "GRNY"):
        card("fundstrat_bible", "analyst_call", tk, f"{tk} <- FS Tech double-OW (5/28)",
             "2026-05-28", 0.70, "fundstrat", direction="overweight", date="2026-05-28")
    card("fundstrat_bible", "analyst_call", "ANET", "ANET — current FS Top-5 (AI networking)",
         "2026-05-28", 0.70, "fundstrat", direction="top_5", rank=3, date="2026-05-28")
    card("fundstrat_bible", "analyst_call", "FN", "FN — newly named FS Top-5 SMID (AI optical)",
         "2026-05-28", 0.70, "fundstrat", direction="top_5", event="new_top5", rank=5, date="2026-05-28")
    card("fundstrat_bible", "what_to_own", "XLF", "Financials (XLF) added to What-to-Own (5/28)",
         "2026-05-28", 0.70, "fundstrat", event="favorable_shift", date="2026-05-28")
    card("fundstrat_bible", "analyst_call", "UUUU", "UUUU in FS Bottom-5 (5/28)",
         "2026-05-28", 0.70, "fundstrat", direction="bottom_5", event="new_bottom5", date="2026-05-28")

    # ── FUNDSTRAT DAILY (5/28) ──
    card("fundstrat_daily", "analyst_call", "ITA",
         "ITA cleared a multi-month downtrend — Newton 5/28 (breakout)", "2026-05-28", 0.70,
         "fundstrat", analyst="Newton", direction="breakout", event="breakout", date="2026-05-28")
    card("fundstrat_daily", "analyst_call", "BMNR", "BMNR — Lee: bottom likely in (5/28)",
         "2026-05-28", 0.70, "fundstrat", analyst="Lee", direction="bottom_in",
         event="bottom_in", date="2026-05-28")
    card("fundstrat_daily", "analyst_call", "BMNR", "BMNR — Farrell: still struggling (5/28)",
         "2026-05-28", 0.65, "fundstrat", analyst="Farrell", direction="struggling",
         event="unfavorable_shift", date="2026-05-28")
    card("fundstrat_daily", "analyst_call", "IBIT", "IBIT — Lee: crypto bottom likely in (5/28)",
         "2026-05-28", 0.70, "fundstrat", analyst="Lee", direction="bottom_in",
         event="bottom_in", date="2026-05-28")

    # ── MERIDIAN (static baseline · 3/15) ──
    card("meridian", "analyst_call", "LEU", "LEU — HALEU enrichment monopoly (Meridian)",
         "2026-03-15", 0.75, "thematic_research", direction="bullish", date="2026-03-15")
    card("meridian", "analyst_call", "MP", "MP — rare-earth magnet vertical integration (Meridian)",
         "2026-03-15", 0.75, "thematic_research", direction="bullish", date="2026-03-15")
    card("meridian", "analyst_call", "UUUU", "UUUU — uranium + REE optionality (Meridian)",
         "2026-03-15", 0.75, "thematic_research", direction="bullish", date="2026-03-15")

    # ── PORTFOLIO (the 5/27 book) ──
    book = [("SMH", 9.90, "p,s"), ("MAGS", 9.09, "p,s"), ("NVDA", 6.73, "p,s"), ("MU", 2.0, "s"),
            ("AVGO", 3.5, "p,s"), ("ANET", 0.29, "s"), ("GRNY", 5.0, "p,s"), ("XLF", 3.0, "p"),
            ("LEU", 1.5, "s"), ("MP", 1.2, "s"), ("UUUU", 0.8, "s"), ("BMNR", 2.5, "s"),
            ("IBIT", 1.5, "p"), ("VOLT", 1.0, "s"), ("ITA", 0.6, "s"), ("AMZN", 2.0, "p"),
            ("COST", 1.8, "p"), ("MSFT", 2.2, "p,s")]
    for tk, pct, own in book:
        card("portfolio", "position", tk, f"{tk} {pct:.2f}% Owned", "2026-05-27", 0.95,
             "own", ticker=tk, pct=pct, owner=own)

    # ── theses (theses.json 14 + IBIT) with stance overlay ──
    theses = json.load(open(os.path.join(HERE, "theses.json")))
    theses.append({"ticker": "IBIT", "tier": "T2", "lane": "Generational",
                   "source": "operator", "factor_tags": ["crypto"]})
    monitor = {"BMNR", "LEU", "UUUU", "MP", "IBIT"}   # the burned sleeves
    for t in theses:
        t["stance"] = "MONITOR" if t["ticker"] in monitor else "ACTIVE"

    snapshot = {
        "run_id": "golden-2026-05-29", "run_timestamp": "2026-05-29T16:00:00",
        "items": items,
        "sources_ok": ["uw_price", "uw_macro", "fundstrat_bible", "fundstrat_daily",
                       "meridian", "portfolio"],
        "sources_failed": [],
        "staleness": {"uw_price": "2026-05-29", "uw_macro": "2026-05-29",
                      "fundstrat_bible": "2026-05-28", "fundstrat_daily": "2026-05-28",
                      "meridian": "2026-03-15", "portfolio": "2026-05-27"},
        "critical_missing": [],
    }
    return {"as_of": AS_OF, "snapshot": snapshot, "theses": theses}


# --------------------------------------------------------------------------- #
# 2) self-checks: validate inputs, run reads through, validate feed + enums
# --------------------------------------------------------------------------- #
def check(bundle) -> tuple[dict, list[str]]:
    problems = []
    snap = bundle["snapshot"]
    for i, it in enumerate(snap["items"]):
        problems += [f"item[{i}] {it['subject']}: {p}" for p in validate_source_item(it)]
    problems += [f"snapshot: {p}" for p in validate_collected_snapshot(snap)]

    feed = assemble_feed(bundle, parabolic=PARABOLIC)
    problems += [f"feed: {p}" for p in validate_cockpit_feed(feed)]

    pos = {p["t"]: p for h in feed["holdings"] for p in h["pos"]}
    for tk, (xcv, xcd) in ENUM_TARGETS.items():
        got = (pos.get(tk, {}).get("cv"), pos.get(tk, {}).get("cd"))
        if got != (xcv, xcd):
            problems.append(f"enum {tk}: got {got} want {(xcv, xcd)}")
    fr = sorted((s["ticker"], s["urgency"]) for s in feed["fresh_signals"])
    if fr != FRESH_TARGET:
        problems.append(f"fresh-set: got {fr} want {FRESH_TARGET}")
    return feed, problems


def main(write: bool):
    bundle = build_snapshot_bundle()
    feed, problems = check(bundle)
    print("SELF-CHECK:", "ALL PASS" if not problems else f"{len(problems)} PROBLEM(S)")
    for p in problems:
        print("  ✗", p)
    if problems:
        print("\n⚠️  not written.")
        return 1
    print(f"OK — {len(bundle['snapshot']['items'])} items · {len(bundle['theses'])} theses · "
          f"{sum(len(h['pos']) for h in feed['holdings'])} positions · {len(feed['fresh_signals'])} fresh")
    if write:
        json.dump(bundle, open(os.path.join(HERE, "golden_snapshot.json"), "w"), indent=2)
        json.dump(feed, open(os.path.join(HERE, "golden_feed.json"), "w"), indent=2)
        print("OK - froze golden_snapshot.json + golden_feed.json")
    else:
        print("--check: not written (drift-free).")
    return 0


if __name__ == "__main__":
    sys.exit(main(write="--check" not in sys.argv))
