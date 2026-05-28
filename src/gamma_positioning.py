#!/usr/bin/env python3
"""
gamma_positioning.py — dealer-gamma / market-positioning context overlay.

Investing 2026 framework  ·  Signal Research Backlog idea #3  ·  pure-logic,
deterministic, no API calls.

WHY THIS EXISTS
---------------
This is NOT a stock-finder. It is a positioning CONTEXT OVERLAY. It reads how
options dealers are positioned in gamma and turns that into a coarse, plain-
language regime call — which sharpens timing, sizing, and options-structure on
trades you are ALREADY considering. It informs trades; it does not generate
them.

Two modes, one script:
  Market mode  — SPY / QQQ / index data: the broad-tape regime read (the spine).
  Name mode    — any single ticker you are about to trade: same logic, same
                 schema. Single-name gamma data is thinner, so the read is
                 flagged lower-confidence.

THE READ — a deliberately coarse 3-state output
-----------------------------------------------
  🟢 Long-gamma / Pinned     dealers hedge AGAINST moves -> chop, mean-
                             reversion, pinning. Fade extremes; defined-range
                             structures; smaller chase size.
  ⚪ Neutral / Transitional  near the flip, or signals disagree -> no tilt.
  🔴 Short-gamma / Trending  dealers hedge WITH moves -> trend, vol expansion,
                             violent moves. Momentum entries; longer-dated
                             directional structures; size for wider swings.

Precision here is over-fitting bait, so the classifier is intentionally coarse:
two signals vote, the vote picks one of three states.

  Signal 1 — net GEX ratio.  (sum call_gex + sum put_gex) / (sum |gex|).
             Scale-free, ticker-agnostic.  >= +0.15 votes long, <= -0.15 votes
             short, in-between abstains.
  Signal 2 — spot vs gamma flip.  Above the flip votes long, below votes short,
             within 1% of the flip abstains.  If the book never crosses zero
             (uniformly one-signed) the flip vote follows the net-GEX sign.

  vote = sig1 + sig2 (range -2..+2).  >=+1 long  ·  0 neutral  ·  <=-1 short.
  strength: |vote|==2 clear · |vote|==1 lean · signals oppose -> conflicted ·
            else -> flat.

KEY LEVELS
----------
  Gamma flip (proxy)  the cumulative-net-GEX zero-crossing strike nearest spot
                      — a coarse boundary between the put-gamma-heavy zone
                      (below) and call-gamma-heavy zone (above). Labelled a
                      PROXY: a by-strike snapshot can only approximate it.
  Magnet strikes      strikes with the largest total dealer gamma — the pin
                      levels price is drawn toward.

Every threshold below is a PROVISIONAL starting point, flagged for the 6/28
retrospective. This is a context tool validated by observation (were the
regime calls right?), not a P&L strategy. It stays OUT of the CI.

CLI
---
  python gamma_positioning.py --self-test
  python gamma_positioning.py --input greek.json
  python gamma_positioning.py --input greek.json --json

greek.json : {"ticker":"SPY","spot":745.20,"date":"2026-05-26",
              "strikes":[ <UW get_greek_exposure_by_strike rows> ]}
  each strike row needs at least: strike, call_gex, put_gex (extra UW fields
  such as call_delta / put_vanna are ignored). Values may be strings.
"""

import argparse
import json
import sys

# ---- Provisional thresholds — retune at the 6/28 retrospective -------------
RATIO_LONG_THRESHOLD = 0.15     # net-GEX ratio >= this -> long-gamma vote
RATIO_SHORT_THRESHOLD = -0.15   # net-GEX ratio <= this -> short-gamma vote
FLIP_PROXIMITY_PCT = 0.01       # spot within this % of the flip -> abstain
MAGNET_WINDOW_PCT = 0.10        # search magnets within +/- this % of spot
# ---------------------------------------------------------------------------

INDEX_TICKERS = {"SPY", "QQQ", "IWM", "DIA", "SPX", "NDX", "RUT", "XSP"}

REGIME_LABEL = {
    "long_gamma": "\U0001F7E2 Long-gamma / Pinned",
    "neutral":    "\u26AA Neutral / Transitional",
    "short_gamma": "\U0001F534 Short-gamma / Trending",
}

NAME_MODE_NOTE = ("Single-name gamma data is thinner and noisier than index "
                  "data — treat this as lower-confidence context, not a "
                  "standalone signal.")


# ---- parsing ---------------------------------------------------------------
def _to_float(x):
    """Parse a number that may arrive as a string (UW returns strings)."""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    return float(str(x).strip().replace(",", ""))


def parse_strikes(rows):
    """UW by-strike rows -> sorted list of (strike, call_gex, put_gex, net_gex).

    UW convention: call_gex is positive, put_gex is signed negative, so the
    per-strike net is simply call_gex + put_gex.
    """
    out = []
    for r in rows:
        try:
            s = _to_float(r.get("strike"))
            c = _to_float(r.get("call_gex"))
            p = _to_float(r.get("put_gex"))
        except (ValueError, AttributeError, TypeError):
            continue
        out.append((s, c, p, c + p))
    out.sort(key=lambda t: t[0])
    return out


# ---- core measures ---------------------------------------------------------
def total_net_gex(parsed):
    """Sum of net GEX across all strikes. Sign = overall gamma tilt."""
    return sum(n for (_s, _c, _p, n) in parsed)


def net_gex_ratio(parsed):
    """Net GEX divided by gross GEX. Scale-free, ticker-agnostic, range -1..+1."""
    gross = sum(abs(c) + abs(p) for (_s, c, p, _n) in parsed)
    if gross == 0:
        return 0.0
    return total_net_gex(parsed) / gross


def gamma_flip(parsed, spot):
    """Cumulative-net-GEX zero-crossing nearest spot — a PROXY for the flip.

    Walk strikes low-to-high accumulating net GEX; a sign change in the running
    total marks a crossing. Returns the interpolated strike of the crossing
    nearest spot, or None when the book never crosses zero.
    """
    if not parsed:
        return None
    crossings = []
    cum_prev = 0.0
    strike_prev = None
    for (strike, _c, _p, net) in parsed:
        cum_cur = cum_prev + net
        if strike_prev is not None:
            crossed = ((cum_prev < 0 and cum_cur >= 0) or
                       (cum_prev > 0 and cum_cur <= 0))
            if crossed:
                if cum_cur == cum_prev:
                    flip = strike
                else:
                    frac = (0.0 - cum_prev) / (cum_cur - cum_prev)
                    flip = strike_prev + frac * (strike - strike_prev)
                crossings.append(flip)
        cum_prev = cum_cur
        strike_prev = strike
    if not crossings:
        return None
    return min(crossings, key=lambda f: abs(f - spot))


def magnet_strikes(parsed, spot):
    """Largest dealer-gamma concentrations — the pin levels price is drawn to.

    'largest_overall' scans every strike; 'nearest_above' / 'nearest_below'
    scan only within +/- MAGNET_WINDOW_PCT of spot (near-term-relevant pins).
    """
    result = {"largest_overall": None, "nearest_above": None,
              "nearest_below": None}
    if not parsed:
        return result

    def entry(row):
        s, c, p, n = row
        flavor = ("call / resistance" if n > 0 else
                  "put / support" if n < 0 else "balanced")
        return {"strike": s, "gross_gex": abs(c) + abs(p),
                "net_gex": n, "flavor": flavor}

    all_e = [entry(r) for r in parsed]
    result["largest_overall"] = max(all_e, key=lambda e: e["gross_gex"])

    window = abs(spot) * MAGNET_WINDOW_PCT
    near = [entry(r) for r in parsed if abs(r[0] - spot) <= window]
    above = [e for e in near if e["strike"] > spot]
    below = [e for e in near if e["strike"] < spot]
    if above:
        result["nearest_above"] = max(above, key=lambda e: e["gross_gex"])
    if below:
        result["nearest_below"] = max(below, key=lambda e: e["gross_gex"])
    return result


# ---- classification --------------------------------------------------------
def classify_regime(ratio, spot, flip, total_net):
    """Two-signal vote -> (regime, strength, distance_to_flip_pct, sig_ratio, sig_flip)."""
    # Signal 1 — net gamma tilt.
    if ratio >= RATIO_LONG_THRESHOLD:
        sig_ratio = 1
    elif ratio <= RATIO_SHORT_THRESHOLD:
        sig_ratio = -1
    else:
        sig_ratio = 0

    # Signal 2 — spot vs flip.
    dist_pct = None
    if flip is not None and spot:
        dist_pct = (spot - flip) / spot
        if abs(dist_pct) < FLIP_PROXIMITY_PCT:
            sig_flip = 0
        elif spot > flip:
            sig_flip = 1
        else:
            sig_flip = -1
    else:
        # No crossing: the book is uniformly one-signed -> flip vote follows
        # the net-GEX sign (the whole curve is one regime).
        sig_flip = 1 if total_net > 0 else (-1 if total_net < 0 else 0)

    vote = sig_ratio + sig_flip
    if vote >= 1:
        regime = "long_gamma"
    elif vote <= -1:
        regime = "short_gamma"
    else:
        regime = "neutral"

    if abs(vote) == 2:
        strength = "clear"
    elif abs(vote) == 1:
        strength = "lean"
    elif sig_ratio != 0 and sig_flip != 0 and sig_ratio != sig_flip:
        strength = "conflicted"
    else:
        strength = "flat"

    return regime, strength, dist_pct, sig_ratio, sig_flip


def build_implication(regime, strength, flip, magnets):
    """Plain-language read for the operator."""
    flip_txt = ("%.2f" % flip) if flip is not None else "\u2014"
    mag = magnets.get("largest_overall")
    mag_txt = ("%.0f" % mag["strike"]) if mag else "\u2014"

    if regime == "long_gamma":
        lead = "clearly long-gamma" if strength == "clear" else "leaning long-gamma"
        return ("Dealers are %s: they hedge against moves, so expect chop, "
                "mean-reversion and pinning. Fade extremes; favor defined-range "
                "structures over directional bets. The %s gamma node is the "
                "magnet to watch; flip line at %s." % (lead, mag_txt, flip_txt))

    if regime == "short_gamma":
        lead = "clearly short-gamma" if strength == "clear" else "leaning short-gamma"
        return ("Dealers are %s: they hedge with moves, so expect trending and "
                "volatility expansion — moves can run and reverse violently. "
                "Momentum entries favored; size for wider swings; directional / "
                "longer-dated structures over tight ranges. Flip line at %s."
                % (lead, flip_txt))

    if strength == "conflicted":
        return ("Mixed signal — overall gamma tilt and price-vs-flip disagree. "
                "Transitional; wait for price to settle one side of the flip at "
                "%s before leaning on a regime read." % flip_txt)

    return ("Dealer gamma is roughly balanced / price sits near the gamma flip "
            "at %s — no strong regime tilt. Treat the tape as regime-agnostic; "
            "the flip is the line to watch." % flip_txt)


def analyze(payload):
    """Top-level: UW Greek payload -> full positioning read."""
    ticker = str(payload.get("ticker", "?"))
    date = str(payload.get("date", "?"))
    spot_raw = payload.get("spot")
    if spot_raw is None:
        raise ValueError("input must include 'spot' (the underlying price)")
    spot = _to_float(spot_raw)

    rows = payload.get("strikes") or payload.get("data") or []
    parsed = parse_strikes(rows)
    if not parsed:
        raise ValueError("input 'strikes' is empty or unparseable")

    total = total_net_gex(parsed)
    ratio = net_gex_ratio(parsed)
    flip = gamma_flip(parsed, spot)
    regime, strength, dist_pct, _sr, _sf = classify_regime(ratio, spot, flip, total)
    magnets = magnet_strikes(parsed, spot)
    mode = "market" if ticker.upper() in INDEX_TICKERS else "name"

    return {
        "ticker": ticker,
        "date": date,
        "spot": spot,
        "mode": mode,
        "regime": regime,
        "regime_label": REGIME_LABEL[regime],
        "strength": strength,
        "total_net_gex": total,
        "net_gex_ratio": ratio,
        "gamma_flip": flip,
        "distance_to_flip_pct": dist_pct,
        "magnets": magnets,
        "implication": build_implication(regime, strength, flip, magnets),
        "notes": NAME_MODE_NOTE if mode == "name" else "",
    }


# ---- human-readable output -------------------------------------------------
def format_read(r):
    """Render an analyze() result as a clean text block."""
    def mag_line(m):
        if not m:
            return "\u2014"
        return "%.0f (%s)" % (m["strike"], m["flavor"])

    dist = r["distance_to_flip_pct"]
    if dist is None:
        flip_line = "Gamma flip (proxy):  none in range (book uniformly one-signed)"
    else:
        side = "above" if dist >= 0 else "below"
        flip_line = ("Gamma flip (proxy):  %.2f   ·   spot is %.2f%% %s the flip"
                     % (r["gamma_flip"], abs(dist) * 100, side))

    lines = [
        "GAMMA POSITIONING \u2014 %s  (%s)" % (r["ticker"], r["date"]),
        "  Spot %.2f   ·   mode: %s" % (r["spot"], r["mode"]),
        "  Regime:  %s   (%s)" % (r["regime_label"], r["strength"]),
        "  Net GEX ratio:  %+.3f      Total net GEX:  %s"
        % (r["net_gex_ratio"], "{:+,.0f}".format(r["total_net_gex"])),
        "  " + flip_line,
        "  Magnets:  largest %s  ·  above %s  ·  below %s"
        % (mag_line(r["magnets"]["largest_overall"]),
           mag_line(r["magnets"]["nearest_above"]),
           mag_line(r["magnets"]["nearest_below"])),
        "  Read: " + r["implication"],
    ]
    if r["notes"]:
        lines.append("  Note: " + r["notes"])
    return "\n".join(lines)


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

    def payload(spot, rows, ticker="TEST"):
        return {"ticker": ticker, "spot": spot, "date": "test",
                "strikes": [{"strike": s, "call_gex": c, "put_gex": p}
                            for (s, c, p) in rows]}

    # FIXTURE A — clear long-gamma (flip below spot, ratio strongly positive).
    A = analyze(payload(102, [
        (90, 0, -100), (92, 0, -120), (94, 10, -60), (96, 200, -20),
        (98, 300, -10), (100, 350, -10), (102, 300, -5), (104, 250, -5),
        (106, 150, -5)]))
    check("A regime long_gamma", A["regime"] == "long_gamma")
    check("A strength clear", A["strength"] == "clear")
    check("A flip ~96.6", A["gamma_flip"] is not None
          and abs(A["gamma_flip"] - 96.62) < 0.5)
    check("A ratio ~0.65", abs(A["net_gex_ratio"] - 0.6464) < 0.02)
    check("A magnet largest=100", A["magnets"]["largest_overall"]["strike"] == 100)
    check("A magnet above=104", A["magnets"]["nearest_above"]["strike"] == 104)
    check("A magnet below=100", A["magnets"]["nearest_below"]["strike"] == 100)

    # FIXTURE B — clear short-gamma, uniform book (no flip in range).
    B = analyze(payload(100, [
        (90, 5, -200), (95, 10, -250), (100, 15, -300), (105, 20, -260),
        (110, 30, -180)]))
    check("B regime short_gamma", B["regime"] == "short_gamma")
    check("B strength clear", B["strength"] == "clear")
    check("B no flip", B["gamma_flip"] is None)
    check("B ratio strongly negative", B["net_gex_ratio"] < -0.15)
    check("B dist None", B["distance_to_flip_pct"] is None)

    # FIXTURE C — neutral flat (spot within 1% of flip, ratio in dead-band).
    C = analyze(payload(101.5, [
        (96, 20, -260), (98, 60, -180), (100, 200, -40), (102, 230, -30),
        (104, 200, -30)]))
    check("C regime neutral", C["regime"] == "neutral")
    check("C strength flat", C["strength"] == "flat")
    check("C flip ~102", C["gamma_flip"] is not None
          and abs(C["gamma_flip"] - 102) < 0.5)
    check("C near flip <1%", C["distance_to_flip_pct"] is not None
          and abs(C["distance_to_flip_pct"]) < 0.01)

    # FIXTURE D — conflicted neutral (ratio votes long, spot-vs-flip votes short).
    D = analyze(payload(101, [
        (95, 5, -300), (100, 5, -250), (103, 50, -100), (106, 600, -10),
        (110, 700, -10)]))
    check("D regime neutral", D["regime"] == "neutral")
    check("D strength conflicted", D["strength"] == "conflicted")
    check("D flip ~106", D["gamma_flip"] is not None
          and abs(D["gamma_flip"] - 106) < 0.5)
    check("D ratio positive", D["net_gex_ratio"] > 0.15)

    # FIXTURE E — string inputs parse identically to numeric (FIXTURE A data).
    E = analyze(payload("102", [
        ("90", "0", "-100"), ("92", "0", "-120"), ("94", "10", "-60"),
        ("96", "200", "-20"), ("98", "300", "-10"), ("100", "350", "-10"),
        ("102", "300", "-5"), ("104", "250", "-5"), ("106", "150", "-5")]))
    check("E strings -> long_gamma", E["regime"] == "long_gamma")
    check("E string ratio == numeric",
          abs(E["net_gex_ratio"] - A["net_gex_ratio"]) < 1e-9)
    check("E string flip == numeric",
          abs(E["gamma_flip"] - A["gamma_flip"]) < 1e-9)

    # FIXTURE F — long-gamma, uniform book (no flip in range).
    F = analyze(payload(100, [(95, 300, -20), (100, 400, -30), (105, 350, -20)]))
    check("F regime long_gamma", F["regime"] == "long_gamma")
    check("F strength clear", F["strength"] == "clear")
    check("F no flip", F["gamma_flip"] is None)

    # Helper / structural checks.
    check("_to_float comma", abs(_to_float("1,234.5") - 1234.5) < 1e-9)
    check("_to_float number", _to_float(42) == 42.0)
    check("_to_float none", _to_float(None) == 0.0)
    check("ratio zero on zero gross", net_gex_ratio([(100, 0, 0, 0)]) == 0.0)
    p = parse_strikes([{"strike": "105", "call_gex": "3", "put_gex": "-1"},
                       {"strike": "95", "call_gex": "2", "put_gex": "-1"}])
    check("parse_strikes sorts ascending", p[0][0] == 95 and p[1][0] == 105)
    check("INDEX -> market mode", analyze(payload(
        100, [(95, 300, -20), (100, 400, -30), (105, 350, -20)],
        "SPY"))["mode"] == "market")
    check("non-index -> name mode", F["mode"] == "name")
    check("name mode carries caveat", F["notes"] != "")

    # Error handling.
    try:
        analyze({"ticker": "X", "strikes": [{"strike": 1, "call_gex": 1,
                                             "put_gex": -1}]})
        check("missing spot raises", False)
    except ValueError:
        check("missing spot raises", True)
    try:
        analyze({"ticker": "X", "spot": 100, "strikes": []})
        check("empty strikes raises", False)
    except ValueError:
        check("empty strikes raises", True)

    total = passed[0] + failed[0]
    print("\nself-test: %d/%d checks passed." % (passed[0], total))
    return failed[0] == 0


# ---- CLI -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Dealer-gamma / market-positioning context overlay.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the built-in deterministic test suite")
    ap.add_argument("--input", metavar="FILE",
                    help="JSON file with ticker / spot / strikes (UW schema)")
    ap.add_argument("--json", action="store_true",
                    help="emit the read as JSON instead of a text block")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if run_self_test() else 1)

    if not args.input:
        ap.error("provide --input FILE or --self-test")

    with open(args.input) as fh:
        payload = json.load(fh)
    result = analyze(payload)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_read(result))


if __name__ == "__main__":
    main()
