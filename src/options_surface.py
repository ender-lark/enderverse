#!/usr/bin/env python3
"""
options_surface.py — the producer that turns a set of conviction names into feed-ready,
ranked, defined-risk options ideas plus an honest roll-up.

This is the thin glue the SURFACING layer (cockpit / Today-Decide / conversation) consumes so it
never has to re-derive anything: give it a bundle of UW data per name + the conviction/account
context, and it returns the ideas (strongest ACT first) + a summarize_run() roll-up that is never
silent. Mirrors the repo's producer/bundle pattern (uw_opportunity_scan): the live UW MCP pulls
happen UPSTREAM (routine / chat session) and feed the bundle; this core is pure + token-safe.

CONSUMES (never reimplements):
  • options_uw_adapter.normalize_market / normalize_chain / assemble_subject
  • options_expression.build_expression / summarize_run
  • options_shadow_log.append_rejections (IO, via persist_shadow_log)

Engine + scope: src/options_expression.py,
docs/codex_tasks/options_opportunity_surfacing_scope_2026_06_18.md.

DESIGN NOTES
  • LEAD WITH THE STRONGEST: ideas are ranked ACT > WAIT > WATCH > SKIP, then by edge
    (expected_move − break-even) so the loudest real opportunity sorts to the top. Ranking is a
    transparent key, not a hidden score; the render still leads with each idea's own `move`.
  • DATA-GAP HONESTY: a name with no chain pulled becomes a WATCH "re-pull the chain", NOT a false
    "illiquid" SKIP — we never let missing data masquerade as a real read (dark-lane discipline).
  • NEVER SILENT: the roll-up always speaks (summarize_run's honest-empty headline).
  • PURE CORE + SEPARATE IO: surface_options() does no file IO; persist_shadow_log() is the thin
    writer the routine calls to log near-misses for later dial-tuning.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import options_expression as oe
import options_shadow_log as osl
import options_uw_adapter as ad

SOURCE = "options_surface"

# disposition sort order (loudest first) — a transparent ranking key, not a score
_DISP_ORDER = {"ACT": 0, "WAIT": 1, "WATCH": 2, "SKIP": 3}


def _edge(idea: dict) -> float:
    """Expected move beyond the break-even (bigger = more room to be right). Missing -> sinks."""
    em, be = idea.get("expected_move_pct"), idea.get("break_even_pct")
    if em is None or be is None:
        return -1e9
    return em - abs(be)


def _rank_key(idea: dict):
    # disposition is the LEADING key: a real ACT can never be demoted by the edge tiebreaker below
    # (a score must never masquerade as a recommendation). Edge only orders WITHIN a disposition tier.
    return (_DISP_ORDER.get(idea.get("disposition"), 9), -_edge(idea), idea.get("ticker") or "")


def _data_gap(ticker: str, as_of, reason: str) -> dict:
    """A non-actionable hold for a name we couldn't read — honest, never a fake 'illiquid'."""
    return {
        "schema_version": oe.SCHEMA_VERSION, "ticker": ticker, "as_of": as_of,
        "disposition": "WATCH", "move": None, "when": None, "timing": None, "tripwire_note": None,
        "structure": None, "legs": None, "iv_environment": "unknown", "iv_tax_brake": False,
        "brake_reason": None, "why": None, "the_catch": None, "filter_reason": reason, "glossary": {},
        "honesty": "A 100% loss of the premium is a realistic outcome — this is sized for that.",
    }


def surface_options(bundle: Optional[dict], *, conviction_lookup: Optional[dict] = None,
                    account: Optional[dict] = None, cfg: Optional[dict] = None,
                    as_of: Optional[str] = None, generated_at: Optional[str] = None) -> dict:
    """Pure producer: a bundle {ticker: {"screener": <raw>, "chain": <raw>}} + conviction/account
    context -> {source, as_of, generated_at, ideas (ranked), summary}. No network, no file IO.

    conviction_lookup maps TICKER -> {direction, conviction_intact, thesis_break,
    thesis_horizon_days, recent_options_loss}. account -> {portfolio_value, open_premium_at_risk}.
    """
    # Coerce every external arg: a truthy NON-dict must degrade to empty, never raise. The producer's
    # contract is to NEVER go silent — one malformed upstream payload can't be allowed to abort the
    # batch (that would invert the anti-passivity north star). `or {}` only catches falsy, not e.g. a
    # stray list/str/scalar, so we isinstance-coerce.
    bundle = bundle if isinstance(bundle, dict) else {}
    conviction_lookup = conviction_lookup if isinstance(conviction_lookup, dict) else {}
    account = account if isinstance(account, dict) else None
    ideas: list[dict] = []
    for raw_tk, data in bundle.items():
        tk = str(raw_tk).strip().upper()
        if not tk:
            continue
        a = as_of
        try:
            data = data if isinstance(data, dict) else {}
            screener = data.get("screener")
            chain = data.get("chain")
            market = ad.normalize_market(screener) if isinstance(screener, (dict, list)) else {}
            a = as_of or market.get("as_of")
            contracts = (ad.normalize_chain(chain, spot=market.get("spot"), as_of=a)
                         if isinstance(chain, (dict, list)) else [])
            if not contracts:
                if not isinstance(chain, (dict, list)):
                    reason = "No option chain was pulled for this name — re-pull the chain."
                elif not ad._arr(chain):
                    reason = "Option chain came back empty — re-pull the chain."
                else:
                    reason = "Option chain pulled but no usable contracts parsed — re-pull the chain."
                ideas.append(_data_gap(tk, a, reason))
                continue
            conv = conviction_lookup.get(tk) or conviction_lookup.get(raw_tk)
            conv = conv if isinstance(conv, dict) else None
            subject = ad.assemble_subject(ticker=tk, market=market, chain_contracts=contracts,
                                          conviction=conv, account=account, as_of=a)
            ideas.append(oe.build_expression(subject, cfg=cfg))
        except Exception as exc:  # noqa: BLE001 — a single bad name must NEVER abort the whole batch
            ideas.append(_data_gap(tk, a, f"Couldn't read this name's options data ({type(exc).__name__}) — re-pull."))
    ideas.sort(key=_rank_key)
    # envelope as_of: fall back to the ideas' own date when the caller omits it (the realistic routine
    # path, where as_of lives only inside each screener row) so the run is never mislabelled None.
    env_as_of = as_of or next((i.get("as_of") for i in ideas if i.get("as_of")), None)
    summary = oe.summarize_run(ideas, cfg=cfg)
    return {
        "source": SOURCE,
        "as_of": env_as_of,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "ideas": ideas,
        "summary": summary,
    }


def persist_shadow_log(result: Optional[dict], *, path: Any = osl.DEFAULT_PATH,
                       as_of: Optional[str] = None) -> int:
    """Append every near-miss/hold from a surface_options() result to the shadow log (IO).
    Returns the count written. The routine calls this so we can later tune dials from real misses."""
    result = result or {}
    return osl.append_rejections(result.get("ideas"), path=path, as_of=as_of or result.get("as_of"))


# ─────────────────────────────────── self-test ───────────────────────────────
def _self_test() -> int:
    """Real UW shapes (NVDA, 2026-06-18) through the full producer; plus a data-gap name."""
    fails: list[str] = []

    def chk(c, label):
        if not c:
            fails.append(label)

    screener = {"result": [{
        "ticker": "NVDA", "iv_rank": "23.6105", "iv30d": "0.358", "implied_move_perc": "0.070000",
        "next_earnings_date": "2026-08-26", "close": "210.69", "prev_close": "204.65",
        "week_52_high": "236.54", "week_52_low": "142.03", "date": "2026-06-18"}]}
    chain = {"states": [
        {"option_symbol": "NVDA260821C00205000", "strike": "205", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4152, "delta": 0.5979, "theo": 17.4998, "open_interest": 10123, "volume": 1326},
        {"option_symbol": "NVDA260821C00210000", "strike": "210", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4091, "delta": 0.5432, "theo": 14.7750, "open_interest": 18035, "volume": 3825},
        {"option_symbol": "NVDA260821C00220000", "strike": "220", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4007, "delta": 0.4325, "theo": 10.2750, "open_interest": 28817, "volume": 3258}],
        "price_data": {"price": "210.69"}}

    bundle = {
        "NVDA": {"screener": screener, "chain": chain},
        "ZZZ": {"screener": {"result": [{"ticker": "ZZZ", "close": "50", "prev_close": "49", "date": "2026-06-18"}]}},  # no chain -> data gap
    }
    conv = {"NVDA": {"direction": "bullish", "conviction_intact": True, "thesis_horizon_days": 60}}
    res = surface_options(bundle, conviction_lookup=conv, account={"portfolio_value": 100000},
                          as_of="2026-06-18", generated_at="2026-06-18T21:50:00Z")

    chk(res["source"] == SOURCE and res["generated_at"] == "2026-06-18T21:50:00Z", "envelope")
    chk(len(res["ideas"]) == 2, "two ideas produced")
    chk(res["ideas"][0]["ticker"] == "NVDA" and res["ideas"][0]["disposition"] == "ACT",
        "strongest (NVDA ACT) ranked first")
    chk(res["ideas"][0]["structure"] == "long_call" and res["ideas"][0]["move"].startswith("Buy "),
        "NVDA leads with a buy move")
    zzz = [i for i in res["ideas"] if i["ticker"] == "ZZZ"][0]
    chk(zzz["disposition"] == "WATCH" and "re-pull" in (zzz["filter_reason"] or ""),
        "no-chain name -> honest data-gap WATCH, not a fake illiquid")
    chk(res["summary"]["act"] and res["summary"]["headline"], "roll-up surfaces the ACT, never silent")

    # determinism: same inputs -> byte-identical (sans generated_at)
    res2 = surface_options(bundle, conviction_lookup=conv, account={"portfolio_value": 100000},
                           as_of="2026-06-18", generated_at="2026-06-18T21:50:00Z")
    chk(res2["ideas"] == res["ideas"], "deterministic ideas")

    # empty bundle -> still an honest, non-silent roll-up
    empty = surface_options({}, generated_at="x")
    chk(empty["ideas"] == [] and empty["summary"]["honest_empty"] and empty["summary"]["headline"],
        "empty bundle -> honest-empty roll-up")

    # shadow log persistence: only the non-ACT (ZZZ) is logged
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "shadow.jsonl"
        n = persist_shadow_log(res, path=p)
        chk(n == 1 and osl.open_misses(p)[0]["ticker"] == "ZZZ", "shadow log records only the near-miss")

    # never raises on malformed input — one bad name can't abort the batch (anti-passivity contract)
    bad = surface_options({"X": [1, 2, 3], "Y": {"screener": 5, "chain": True}, "Z": {"chain": {"states": []}}},
                          conviction_lookup="junk", account=7, generated_at="x")
    chk(len(bad["ideas"]) == 3 and all(i["disposition"] == "WATCH" for i in bad["ideas"]),
        "malformed inputs -> honest WATCH, never raises")
    chk(surface_options([1, 2, 3], generated_at="x")["ideas"] == [], "non-dict bundle -> empty, no raise")

    if fails:
        print("options_surface self-test: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("options_surface self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
