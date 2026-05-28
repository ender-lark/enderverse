#!/usr/bin/env python3
"""
13f_best_ideas.py — 13F best-ideas discovery scorer.

Investing 2026 framework  ·  Signal Research Backlog idea #1  ·  pure-logic,
deterministic, no API calls.

WHY THIS EXISTS
---------------
This is a DISCOVERY tool — the smart-money counterpart to v0's insider-cluster
spine. It scans the 13F holdings of a curated universe of elite, long-horizon,
fundamental managers (see 13f_managers.json) and surfaces the names they hold
with the most conviction — names the operator does NOT already own.

It is the discovery half of the framework's 13F work. The existing
13f_quarterly_pull.py is the MONITORING half: what whales do with names already
held. This module asks the opposite question — what high-conviction names
should be on the radar that aren't yet.

The research that justifies it (5/27/26 dig): a manager's highest-conviction
positions outperform by ~2.8-4.5%/yr; the edge survives the 45-day filing lag
IF the manager universe is filtered to long-horizon fundamental funds (quant /
high-turnover 13Fs are noise at a lag). Conviction + consensus is the signal.

THE SCORE — three inputs, summed, sorted into three bands (mirrors v0_score.py)
------------------------------------------------------------------------------
  Conviction  the largest weight any curated manager assigns the name
              (perc_of_share_value).  >=10% of a book = 3 · 5-10% = 2 ·
              2-5% = 1 · <2% = 0 -> filtered out (not a real best idea).
  Consensus   how many curated managers hold it.  3+ = 3 · 2 = 2 · 1 = 1.
  Direction   aggregate quarter-over-quarter move across the holders.
              net accumulation (adds+new > trims) = 2 · mixed = 1 ·
              net distribution = 0.

  Raw score = sum, range 2-8.
  Bands:  High 6-8  ·  Moderate 4-5  ·  Watch 2-3.

LANE is mechanical: if an activist-tagged manager has newly initiated or added
the name -> Activist lane (the 13D-flavored continuation play); otherwise ->
Best-Ideas lane.

FILTER: names already held (held_tickers) are dropped — this is a discovery
tool; held names belong to the monitoring script.

LOGGED, NOT SCORED: quarters-held and earliest first-buy date (persistence).
Recorded as context so the 6/28 retrospective can see whether persistence
earns its way in as a 4th input. v0 discipline — don't score it until the
data says it matters.

Every threshold is a PROVISIONAL starting point, flagged for the 6/28
retrospective.

CLI
---
  python 13f_best_ideas.py --self-test
  python 13f_best_ideas.py --input holdings.json
  python 13f_best_ideas.py --input holdings.json --json

holdings.json : {
    "as_of": "2026-03-31",
    "held_tickers": ["BMNR", "LEU", "MU"],
    "managers": [
      {"name": "...", "style": "...", "is_activist": false,
       "holdings": [ <UW get_institution_holdings data rows> ]},
      ...
    ]
  }
  Each manager's "holdings" is the data array straight from UW
  get_institution_holdings; the name / style / is_activist come from
  13f_managers.json. The caller merges the two.
"""

import argparse
import json
import sys

# ---- Provisional thresholds — retune at the 6/28 retrospective -------------
CONVICTION_HIGH = 0.10     # weight >= this -> conviction score 3
CONVICTION_MID = 0.05      # weight >= this -> conviction score 2
CONVICTION_MIN = 0.02      # weight >= this -> conviction score 1 ; below -> 0 (filtered)
BAND_HIGH_MIN = 6          # raw >= this -> High
BAND_MODERATE_MIN = 4      # raw >= this -> Moderate ; below -> Watch
HIST_WINDOW = 4            # quarters in UW historical_units
# ---------------------------------------------------------------------------


# ---- parsing helpers -------------------------------------------------------
def _to_float(x):
    """Parse a number that may arrive as a string."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).strip().replace(",", ""))
    except ValueError:
        return None


def _to_int(x):
    f = _to_float(x)
    return int(f) if f is not None else None


# ---- per-holding classification -------------------------------------------
def is_exited(holding):
    """A position the manager has fully closed — not a current holding."""
    units = _to_int(holding.get("units"))
    value = _to_float(holding.get("value"))
    return (units is not None and units == 0) or (value is not None and value == 0)


def classify_holding_direction(holding):
    """One manager's quarter-over-quarter move on one name.

    Returns NEW (opened this quarter) / ADD / HOLD / TRIM.
    """
    hist = holding.get("historical_units") or []
    cur = _to_int(hist[0]) if len(hist) >= 1 else None
    prev = _to_int(hist[1]) if len(hist) >= 2 else None

    if cur is not None and prev is not None and cur > 0 and prev == 0:
        return "NEW"

    units_change = _to_int(holding.get("units_change"))
    if units_change is None and cur is not None and prev is not None:
        units_change = cur - prev
    if units_change is None:
        return "HOLD"
    if units_change > 0:
        return "ADD"
    if units_change < 0:
        return "TRIM"
    return "HOLD"


def quarters_held(holding):
    """Count of the trailing-window quarters in which the name was held."""
    hist = holding.get("historical_units") or []
    return sum(1 for u in hist[:HIST_WINDOW] if (_to_int(u) or 0) > 0)


# ---- scoring ---------------------------------------------------------------
def conviction_score(max_weight):
    """Largest book-weight any manager assigns -> 0-3. 0 means 'not a best idea'."""
    if max_weight is None:
        return 0
    if max_weight >= CONVICTION_HIGH:
        return 3
    if max_weight >= CONVICTION_MID:
        return 2
    if max_weight >= CONVICTION_MIN:
        return 1
    return 0


def consensus_score(n_managers):
    """How many curated managers hold it -> 1-3."""
    if n_managers >= 3:
        return 3
    if n_managers == 2:
        return 2
    return 1


def direction_score(n_new, n_add, n_trim):
    """Aggregate accumulation vs distribution -> 0-2. New initiations count as adds."""
    total_adds = n_new + n_add
    if total_adds > n_trim:
        return 2
    if total_adds == n_trim:
        return 1
    return 0


def band(raw):
    if raw >= BAND_HIGH_MIN:
        return "High"
    if raw >= BAND_MODERATE_MIN:
        return "Moderate"
    return "Watch"


def build_summary(rec):
    """Plain-language one-liner for a discovered name."""
    n = rec["n_managers"]
    mgr_word = "manager" if n == 1 else "managers"
    verb = "holds" if n == 1 else "hold"
    flow = ("net accumulation" if rec["direction_score"] == 2 else
            "mixed flow" if rec["direction_score"] == 1 else "net distribution")
    lane_txt = ("Activist lane — an activist manager is initiating or adding"
                if rec["lane"] == "Activist" else "Best-Ideas lane")
    qh = rec["max_quarters_held"]
    qtxt = ("%d+ quarters" % qh if qh >= HIST_WINDOW
            else "%d quarter%s" % (qh, "" if qh == 1 else "s"))
    return ("%d elite %s %s it (top conviction %.1f%% of a book); "
            "%d new / %d add / %d trim — %s. %s. Longest-held: %s."
            % (n, mgr_word, verb, rec["max_conviction_weight"] * 100,
               rec["n_new"], rec["n_add"], rec["n_trim"], flow, lane_txt, qtxt))


def score_universe(payload):
    """Merged universe + holdings payload -> sorted list of discovery records."""
    held = {str(t).upper() for t in (payload.get("held_tickers") or [])}
    managers = payload.get("managers") or []

    # ticker -> list of per-manager holding records
    by_ticker = {}
    for mgr in managers:
        mname = str(mgr.get("name", "?"))
        is_activist = bool(mgr.get("is_activist", False))
        for h in (mgr.get("holdings") or []):
            ticker = h.get("ticker")
            if not ticker:
                continue
            ticker = str(ticker).upper()
            if is_exited(h):
                continue
            weight = _to_float(h.get("perc_of_share_value"))
            by_ticker.setdefault(ticker, []).append({
                "manager": mname,
                "is_activist": is_activist,
                "weight": weight if weight is not None else 0.0,
                "direction": classify_holding_direction(h),
                "quarters_held": quarters_held(h),
                "first_buy": h.get("first_buy"),
                "sector": h.get("sector"),
            })

    records = []
    for ticker, holders in by_ticker.items():
        if ticker in held:
            continue  # discovery only — held names belong to the monitoring tool

        max_weight = max(h["weight"] for h in holders)
        c_score = conviction_score(max_weight)
        if c_score == 0:
            continue  # not a real best idea for anyone — filtered out

        n_managers = len(holders)
        n_new = sum(1 for h in holders if h["direction"] == "NEW")
        n_add = sum(1 for h in holders if h["direction"] == "ADD")
        n_trim = sum(1 for h in holders if h["direction"] == "TRIM")
        n_hold = sum(1 for h in holders if h["direction"] == "HOLD")

        cons_score = consensus_score(n_managers)
        dir_score = direction_score(n_new, n_add, n_trim)
        raw = c_score + cons_score + dir_score

        lane = ("Activist" if any(h["is_activist"] and h["direction"] in ("NEW", "ADD")
                                  for h in holders) else "Best-Ideas")

        first_buys = [h["first_buy"] for h in holders if h["first_buy"]]
        sectors = [h["sector"] for h in holders if h["sector"]]

        rec = {
            "ticker": ticker,
            "band": band(raw),
            "raw_score": raw,
            "conviction_score": c_score,
            "consensus_score": cons_score,
            "direction_score": dir_score,
            "lane": lane,
            "n_managers": n_managers,
            "managers": [h["manager"] for h in holders],
            "max_conviction_weight": max_weight,
            "n_new": n_new, "n_add": n_add, "n_trim": n_trim, "n_hold": n_hold,
            "max_quarters_held": max(h["quarters_held"] for h in holders),
            "earliest_first_buy": min(first_buys) if first_buys else None,
            "sector": sectors[0] if sectors else None,
        }
        rec["summary"] = build_summary(rec)
        records.append(rec)

    records.sort(key=lambda r: (r["raw_score"], r["consensus_score"],
                                r["max_conviction_weight"]), reverse=True)
    return records


# ---- human-readable output -------------------------------------------------
def format_discoveries(records, as_of="?"):
    if not records:
        return "13F BEST-IDEAS DISCOVERY (%s)\n  No qualifying discoveries." % as_of
    lines = ["13F BEST-IDEAS DISCOVERY  (holdings as of %s)" % as_of,
             "  %d name(s) surfaced — ranked by score." % len(records), ""]
    for r in records:
        lines.append("  [%s · raw %d] %s   (%s lane)"
                      % (r["band"], r["raw_score"], r["ticker"], r["lane"]))
        lines.append("     conviction %d · consensus %d · direction %d"
                      % (r["conviction_score"], r["consensus_score"],
                         r["direction_score"]))
        lines.append("     " + r["summary"])
        lines.append("     managers: " + ", ".join(r["managers"]))
        lines.append("")
    return "\n".join(lines).rstrip()


# ---- self-test -------------------------------------------------------------
def run_self_test():
    """Deterministic fixtures with hand-computed expected outcomes."""
    passed = [0]
    failed = [0]

    def check(label, cond):
        if cond:
            passed[0] += 1
        else:
            failed[0] += 1
            print("  FAIL: %s" % label)

    def hold(ticker, weight, hist, units_change, first_buy="2025-01-01",
             value=1_000_000_000, sector="Technology"):
        return {"ticker": ticker, "perc_of_share_value": weight,
                "historical_units": hist, "units_change": units_change,
                "units": hist[0], "value": value if hist[0] > 0 else 0,
                "first_buy": first_buy, "sector": sector}

    payload = {
        "as_of": "2026-03-31",
        "held_tickers": ["HELD1"],
        "managers": [
            {"name": "Alpha Capital", "style": "concentrated_value",
             "is_activist": False, "holdings": [
                 hold("AAA", 0.12, [100, 90, 80, 70], 10, "2023-06-30"),
                 hold("BBB", 0.03, [20, 25, 30, 35], -5),
                 hold("DDD", 0.015, [3, 2, 1, 0], 1),
                 hold("EXIT1", 0.0, [0, 50, 60, 70], -50)]},
            {"name": "Beta Partners", "style": "long_horizon_growth",
             "is_activist": False, "holdings": [
                 hold("AAA", 0.06, [50, 40, 0, 0], 10, "2024-09-30"),
                 hold("CCC", 0.07, [10, 10, 10, 10], 0),
                 hold("HELD1", 0.20, [200, 100, 0, 0], 100)]},
            {"name": "Gamma Activist", "style": "concentrated_value",
             "is_activist": True, "holdings": [
                 hold("AAA", 0.08, [30, 0, 0, 0], 30, "2026-03-31"),
                 hold("EEE", 0.09, [40, 40, 40, 40], 0)]},
            {"name": "Delta Fund", "style": "concentrated_value",
             "is_activist": False, "holdings": [
                 hold("CCC", 0.04, [5, 8, 10, 0], -3),
                 hold("EEE", 0.11, [60, 55, 50, 45], 5)]},
        ],
    }

    recs = score_universe(payload)
    by = {r["ticker"]: r for r in recs}

    # AAA — 3 managers, top conviction 12%, 1 new + 2 adds, activist initiating.
    check("AAA present", "AAA" in by)
    check("AAA band High", by["AAA"]["band"] == "High")
    check("AAA raw 8", by["AAA"]["raw_score"] == 8)
    check("AAA conviction 3", by["AAA"]["conviction_score"] == 3)
    check("AAA consensus 3", by["AAA"]["consensus_score"] == 3)
    check("AAA direction 2", by["AAA"]["direction_score"] == 2)
    check("AAA lane Activist", by["AAA"]["lane"] == "Activist")
    check("AAA n_managers 3", by["AAA"]["n_managers"] == 3)
    check("AAA n_new 1", by["AAA"]["n_new"] == 1)
    check("AAA n_add 2", by["AAA"]["n_add"] == 2)
    check("AAA max_quarters_held 4", by["AAA"]["max_quarters_held"] == 4)
    check("AAA earliest_first_buy 2023-06-30",
          by["AAA"]["earliest_first_buy"] == "2023-06-30")

    # BBB — 1 manager, 3% conviction, trimming.
    check("BBB present", "BBB" in by)
    check("BBB band Watch", by["BBB"]["band"] == "Watch")
    check("BBB raw 2", by["BBB"]["raw_score"] == 2)
    check("BBB direction 0", by["BBB"]["direction_score"] == 0)
    check("BBB lane Best-Ideas", by["BBB"]["lane"] == "Best-Ideas")

    # CCC — 2 managers, top conviction 7%, one holds + one trims -> direction 0.
    check("CCC present", "CCC" in by)
    check("CCC band Moderate", by["CCC"]["band"] == "Moderate")
    check("CCC raw 4", by["CCC"]["raw_score"] == 4)
    check("CCC conviction 2", by["CCC"]["conviction_score"] == 2)
    check("CCC consensus 2", by["CCC"]["consensus_score"] == 2)
    check("CCC direction 0", by["CCC"]["direction_score"] == 0)

    # DDD — only holder at 1.5% (< 2% floor) -> filtered out.
    check("DDD filtered out (sub-floor conviction)", "DDD" not in by)

    # HELD1 — in held_tickers -> filtered out even though high conviction.
    check("HELD1 filtered out (already held)", "HELD1" not in by)

    # EXIT1 — fully closed position -> not a current holding, filtered out.
    check("EXIT1 filtered out (exited)", "EXIT1" not in by)

    # EEE — activist HOLDS (not new/add); other manager adds -> Best-Ideas lane.
    check("EEE present", "EEE" in by)
    check("EEE band High", by["EEE"]["band"] == "High")
    check("EEE raw 7", by["EEE"]["raw_score"] == 7)
    check("EEE conviction 3", by["EEE"]["conviction_score"] == 3)
    check("EEE direction 2", by["EEE"]["direction_score"] == 2)
    check("EEE lane Best-Ideas (activist only HOLDS)",
          by["EEE"]["lane"] == "Best-Ideas")

    # Ranking — AAA(8) > EEE(7) > CCC(4) > BBB(2).
    check("ranking order", [r["ticker"] for r in recs] == ["AAA", "EEE", "CCC", "BBB"])

    # Component / helper checks.
    check("conviction_score 10% -> 3", conviction_score(0.10) == 3)
    check("conviction_score 5% -> 2", conviction_score(0.05) == 2)
    check("conviction_score 2% -> 1", conviction_score(0.02) == 1)
    check("conviction_score 1.9% -> 0", conviction_score(0.019) == 0)
    check("consensus_score 3+ -> 3", consensus_score(5) == 3)
    check("consensus_score 1 -> 1", consensus_score(1) == 1)
    check("direction adds>trims -> 2", direction_score(1, 1, 1) == 2)
    check("direction adds==trims -> 1", direction_score(0, 1, 1) == 1)
    check("direction trims>adds -> 0", direction_score(0, 0, 2) == 0)
    check("band 6 -> High", band(6) == "High")
    check("band 4 -> Moderate", band(4) == "Moderate")
    check("band 3 -> Watch", band(3) == "Watch")
    check("direction NEW from historical_units",
          classify_holding_direction({"historical_units": [10, 0, 0, 0],
                                       "units_change": 10}) == "NEW")
    check("direction TRIM",
          classify_holding_direction({"historical_units": [8, 10, 10, 10],
                                      "units_change": -2}) == "TRIM")
    check("quarters_held counts nonzero",
          quarters_held({"historical_units": [5, 8, 0, 0]}) == 2)
    check("is_exited true on zero units",
          is_exited({"units": 0, "value": 0}) is True)
    check("_to_float parses string", _to_float("1,234.5") == 1234.5)

    total = passed[0] + failed[0]
    print("\nself-test: %d/%d checks passed." % (passed[0], total))
    return failed[0] == 0


# ---- CLI -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="13F best-ideas discovery scorer.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the built-in deterministic test suite")
    ap.add_argument("--input", metavar="FILE",
                    help="merged universe + UW holdings JSON")
    ap.add_argument("--json", action="store_true",
                    help="emit discoveries as JSON instead of a text block")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if run_self_test() else 1)

    if not args.input:
        ap.error("provide --input FILE or --self-test")

    with open(args.input) as fh:
        payload = json.load(fh)
    records = score_universe(payload)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(format_discoveries(records, payload.get("as_of", "?")))


if __name__ == "__main__":
    main()
