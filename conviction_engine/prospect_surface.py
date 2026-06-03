#!/usr/bin/env python3
"""
prospect_surface.py - turn the 🎯 Top Prospects cache into things the operator SEES.

Three surfaces (logic only; the cockpit .jsx + build_full_feed wiring is a separate step):
    1. build_prospects_lane(cache)  -> the cockpit "Top Prospects" lane payload
       (ACT_NOW/HOT names first, best/worst alpha vs SPY, sell-fast list, uncorroborated count)
    2. stack_callout(ticker, prev, new) -> an FS-Digest line when a new signal STACKS on a name
       ("STACKS on X -> conviction HOT, urgency ACT_NOW - act")
    3. sell_fast_list(cache) -> held/tracked names carrying Avoid signals (move fast)

This is the "don't just collect it - show it to me in time" layer. Never trades.

    python prospect_surface.py --self-test
    python prospect_surface.py --demo
"""
from __future__ import annotations

import argparse
from typing import Dict, List, Optional

_LEVEL_RANK = {"QUIET": 0, "BUILDING": 1, "HOT": 2, "ACT_NOW": 3}


def _entry(rec: dict) -> dict:
    """The compact view of a prospect used on every surface."""
    return {
        "ticker": rec.get("ticker"),
        "direction": rec.get("direction", "long"),
        "conviction": rec.get("conviction", "QUIET"),
        "urgency": rec.get("urgency", "QUIET"),
        "conviction_score": rec.get("conviction_score", 0),
        "urgency_score": rec.get("urgency_score", 0),
        "pct_since_add": rec.get("pct_since_add"),
        "pct_vs_spy": rec.get("pct_vs_spy"),
        "sources": rec.get("sources", []),
        "corroboration": rec.get("corroboration", "Uncorroborated"),
        "provenance": rec.get("provenance", ""),
        "summary": rec.get("summary", ""),
    }


def build_prospects_lane(cache: Dict[str, dict], top_n: int = 8) -> dict:
    """Assemble the cockpit Top Prospects lane: hottest first, alpha movers, sell-fast, counts."""
    longs = [r for r in cache.values() if r.get("direction") != "avoid"]
    avoids = [r for r in cache.values() if r.get("direction") == "avoid"]

    hot = sorted(
        (r for r in longs if r.get("urgency") in ("HOT", "ACT_NOW")),
        key=lambda r: (-_LEVEL_RANK.get(r.get("urgency", "QUIET"), 0),
                       -r.get("urgency_score", 0)))
    with_alpha = [r for r in longs if r.get("pct_vs_spy") is not None]
    movers_best = sorted(with_alpha, key=lambda r: -r["pct_vs_spy"])[:3]
    movers_worst = sorted(with_alpha, key=lambda r: r["pct_vs_spy"])[:3]
    sell_fast = sorted(avoids, key=lambda r: -r.get("urgency_score", 0))

    uncorroborated = sum(1 for r in cache.values()
                         if r.get("corroboration", "Uncorroborated") == "Uncorroborated")

    return {
        "hot": [_entry(r) for r in hot[:top_n]],
        "movers_best": [_entry(r) for r in movers_best],
        "movers_worst": [_entry(r) for r in movers_worst],
        "sell_fast": [_entry(r) for r in sell_fast[:top_n]],
        "counts": {
            "total": len(cache), "long": len(longs), "avoid": len(avoids),
            "act_now": sum(1 for r in longs if r.get("urgency") == "ACT_NOW"),
            "hot": sum(1 for r in longs if r.get("urgency") == "HOT"),
            "uncorroborated": uncorroborated,
        },
    }


def stack_callout(ticker: str, prev: Optional[dict], new: dict) -> str:
    """FS-Digest line when a new signal stacks on a name. `prev`/`new` are stack results
    (dicts with conviction_level/urgency_level or a rec with conviction/urgency)."""
    def lv(d, key):
        return (d or {}).get(key) or (d or {}).get(key.replace("_level", "")) or "QUIET"

    new_conv = lv(new, "conviction_level")
    new_urg = lv(new, "urgency_level")
    old_conv = lv(prev, "conviction_level") if prev else "QUIET"
    old_urg = lv(prev, "urgency_level") if prev else "QUIET"

    conv_rose = _LEVEL_RANK.get(new_conv, 0) > _LEVEL_RANK.get(old_conv, 0)
    urg_rose = _LEVEL_RANK.get(new_urg, 0) > _LEVEL_RANK.get(old_urg, 0)

    head = f"🎯 {ticker} STACKS"
    conv_txt = f"conviction {old_conv}→{new_conv}" if conv_rose else f"conviction {new_conv}"
    urg_txt = f"urgency {old_urg}→{new_urg}" if urg_rose else f"urgency {new_urg}"
    tail = ""
    if new_urg == "ACT_NOW":
        tail = " — ACT NOW."
    elif new_urg == "HOT" and urg_rose:
        tail = " — look now."
    return f"{head}: {conv_txt}, {urg_txt}.{tail}"


def sell_fast_list(cache: Dict[str, dict]) -> List[dict]:
    """Names carrying Avoid signals, hottest urgency first (the move-fast list)."""
    avoids = [r for r in cache.values() if r.get("direction") == "avoid"]
    return [_entry(r) for r in sorted(avoids, key=lambda r: -r.get("urgency_score", 0))]


def _pct(x):
    return "—" if x is None else f"{x * 100:+.1f}%"


def format_lane_text(lane: dict) -> str:
    """Plain-text render of the lane (for previews / the skeleton fallback)."""
    c = lane["counts"]
    lines = [f"🎯 TOP PROSPECTS  ({c['total']} tracked · {c['act_now']} ACT_NOW · "
             f"{c['hot']} HOT · {c['uncorroborated']} uncorroborated)"]
    if lane["hot"]:
        lines.append("  ACT / HOT:")
        for e in lane["hot"]:
            lines.append(f"    {e['ticker']:<6} {e['urgency']:<8} vsSPY {_pct(e['pct_vs_spy'])}"
                         f"  [{','.join(e['sources'])}]  {e['corroboration']}")
    if lane["movers_best"]:
        lines.append("  BEST vs SPY: " + ", ".join(
            f"{e['ticker']} {_pct(e['pct_vs_spy'])}" for e in lane["movers_best"]))
    if lane["movers_worst"]:
        lines.append("  WORST vs SPY: " + ", ".join(
            f"{e['ticker']} {_pct(e['pct_vs_spy'])}" for e in lane["movers_worst"]))
    if lane["sell_fast"]:
        lines.append("  ⚠ SELL-FAST (FS says avoid, you hold): " + ", ".join(
            f"{e['ticker']} ({e['urgency']})" for e in lane["sell_fast"]))
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _sample_cache() -> Dict[str, dict]:
    return {
        "NVDA": {"ticker": "NVDA", "direction": "long", "conviction": "ACT_NOW", "urgency": "ACT_NOW",
                 "conviction_score": 32, "urgency_score": 30, "pct_vs_spy": 0.14, "pct_since_add": 0.22,
                 "sources": ["FS-Monthly", "FS-Newton"], "corroboration": "Vetted-Buy", "summary": "x"},
        "ANET": {"ticker": "ANET", "direction": "long", "conviction": "HOT", "urgency": "HOT",
                 "conviction_score": 21, "urgency_score": 24, "pct_vs_spy": 0.06, "pct_since_add": 0.11,
                 "sources": ["FS-Monthly", "FS-Newton"], "corroboration": "Uncorroborated", "summary": "x"},
        "PWR":  {"ticker": "PWR", "direction": "long", "conviction": "BUILDING", "urgency": "QUIET",
                 "conviction_score": 10, "urgency_score": 0, "pct_vs_spy": -0.04, "pct_since_add": 0.02,
                 "sources": ["FS-Granny"], "corroboration": "Auto-research queued", "summary": "x"},
        "LULU": {"ticker": "LULU", "direction": "avoid", "conviction": "BUILDING", "urgency": "BUILDING",
                 "conviction_score": 10, "urgency_score": 8, "pct_vs_spy": -0.09, "pct_since_add": -0.05,
                 "sources": ["FS-Granny"], "corroboration": "Uncorroborated", "summary": "x"},
    }


def _self_test() -> bool:
    passed = failed = 0

    def check(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    cache = _sample_cache()
    lane = build_prospects_lane(cache)

    check("hot lane ACT_NOW first", lane["hot"][0]["ticker"] == "NVDA")
    check("hot lane includes HOT", any(e["ticker"] == "ANET" for e in lane["hot"]))
    check("hot lane excludes QUIET long", all(e["ticker"] != "PWR" for e in lane["hot"]))
    check("best mover = NVDA (highest alpha)", lane["movers_best"][0]["ticker"] == "NVDA")
    check("worst mover = LULU? no - avoid excluded from longs",
          all(e["ticker"] != "LULU" for e in lane["movers_best"] + lane["movers_worst"]))
    check("worst long mover = PWR", lane["movers_worst"][0]["ticker"] == "PWR")
    check("sell_fast has LULU", lane["sell_fast"][0]["ticker"] == "LULU")
    check("counts total 4", lane["counts"]["total"] == 4)
    check("counts act_now 1", lane["counts"]["act_now"] == 1)
    check("counts uncorroborated 2", lane["counts"]["uncorroborated"] == 2)

    # stack_callout
    co = stack_callout("ANET", {"conviction_level": "BUILDING", "urgency_level": "QUIET"},
                       {"conviction_level": "HOT", "urgency_level": "ACT_NOW"})
    check("callout shows conviction rise", "BUILDING→HOT" in co)
    check("callout shows ACT NOW tail", "ACT NOW" in co)
    co2 = stack_callout("PWR", None, {"conviction_level": "BUILDING", "urgency_level": "QUIET"})
    check("callout from no-prev works", "PWR STACKS" in co2)
    co3 = stack_callout("ANET", {"conviction_level": "BUILDING", "urgency_level": "BUILDING"},
                        {"conviction_level": "HOT", "urgency_level": "HOT"})
    check("callout HOT rise says look now", "look now" in co3)

    # sell_fast_list
    sf = sell_fast_list(cache)
    check("sell_fast_list has LULU", sf and sf[0]["ticker"] == "LULU")

    # text render doesn't crash + mentions key bits
    txt = format_lane_text(lane)
    check("text render has header", "TOP PROSPECTS" in txt)
    check("text render has sell-fast", "SELL-FAST" in txt)

    print(f"\n{passed}/{passed + failed} assertions passed.")
    return failed == 0


def _demo() -> None:
    print(format_lane_text(build_prospects_lane(_sample_cache())))
    print("\nFS-Digest call-out example:")
    print("  " + stack_callout("ANET", {"conviction_level": "BUILDING", "urgency_level": "QUIET"},
                                {"conviction_level": "HOT", "urgency_level": "ACT_NOW"}))


def main() -> int:
    ap = argparse.ArgumentParser(description="Top Prospects surfacing (cockpit lane + Digest call-out + sell-fast).")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true")
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
