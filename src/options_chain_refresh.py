#!/usr/bin/env python3
"""Options-chain acquisition for the options-expression surface.

Mirrors the ``uw_cache_refresh`` acquisition pattern: the token-heavy LIVE pulls happen
UPSTREAM (a routine, or a chat session with the Unusual Whales MCP), and this module's job is
the pure, token-safe assembly + cache write that the full build reads. ``full_build_runner``
NEVER touches the network -- it only reads ``src/options_chain_cache.json``.

Per conviction name we want two cheap UW reads:

    get_stock_screener(ticker=T, limit=1)            -> screener row (iv_rank, iv30d,
                                                        implied_move_perc, next_earnings_date,
                                                        close, prev_close, 52w high/low)
    get_options_chain(ticker=T, expiry=<~30-90 DTE>) -> chain (states[] with greeks)

and bundle them as ``{TICKER: {"screener": <raw>, "chain": <raw>}}``.

Two ways to produce the cache:

  * **file-driven** (this CLI, testable, token-safe): hand a JSON of raw responses captured from
    the MCP and let ``--from-responses`` assemble + write the cache. This is the routine/CI path::

        python src/options_chain_refresh.py --from-responses raw.json --out src/options_chain_cache.json

  * **inline** (a chat with MCP access): call the two endpoints for each
    ``select_universe(theses)`` name at ``target_expiry(...)`` DTE, build the bundle with
    ``assemble_bundle``/``build_cache``, and ``write_cache(...)``.

The acquisition stays separate from the producer so one malformed name never blocks the build,
and so the build path stays pure. The raw screener/chain shapes are passed through verbatim --
``options_surface``/``options_uw_adapter`` does the normalization.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# DTE target for the chain pull -- the nearest listed expiry past ~30 days, capped under ~90, so
# the surfaced expression has enough time value to express a thesis without paying for LEAPS.
DEFAULT_DTE = 45
# Bound the live pull -- the conviction universe is small by design; never fan out unbounded.
DEFAULT_CAP = 24
DEFAULT_OUT = Path(__file__).resolve().parent / "options_chain_cache.json"

# Stances that mean "hold for awareness, do NOT add" -- excluded from the live pull universe by
# default (mirrors full_build_runner._OPTIONS_NO_ADD_STANCES; the surface re-applies a no-add rail
# defensively even if one slips through).
NO_ADD_STANCES = {"MONITOR", "BURNED", "EXIT", "TRIM"}


def _norm_ticker(tk: Any) -> str:
    return str(tk or "").strip().upper()


def select_universe(
    theses: Optional[Iterable[dict]],
    *,
    extra: Iterable[Any] = (),
    include_no_add: bool = False,
    cap: int = DEFAULT_CAP,
) -> list[str]:
    """The conviction universe to pull options for: ACTIVE thesis names + any ``extra`` tickers
    (watchlist / lean-in / Fundstrat), de-duplicated in priority order and capped.

    No-add sleeves (MONITOR/BURNED/EXIT/TRIM) are excluded unless ``include_no_add`` -- we don't
    spend a live pull on a sleeve we won't add to. ``extra`` is appended after theses so explicit
    conviction names win the cap.
    """
    out: list[str] = []
    seen: set[str] = set()
    for t in theses or []:
        if not isinstance(t, dict):
            continue
        tk = _norm_ticker(t.get("ticker"))
        if not tk or tk in seen:
            continue
        stance = str(t.get("stance", "") or "").upper()
        if not include_no_add and stance in NO_ADD_STANCES:
            continue
        seen.add(tk)
        out.append(tk)
    for raw in extra or ():
        tk = _norm_ticker(raw)
        if tk and tk not in seen:
            seen.add(tk)
            out.append(tk)
    if cap is not None and cap >= 0:
        out = out[:cap]
    return out


def _third_friday(year: int, month: int) -> datetime:
    """Standard US monthly options expiration: the 3rd Friday of the month."""
    first = datetime(year, month, 1)
    first_friday = 1 + (4 - first.weekday()) % 7   # weekday(): Mon=0..Sun=6, Fri=4
    return datetime(year, month, first_friday + 14)


def target_expiry(as_of: str, *, dte: int = DEFAULT_DTE) -> str:
    """A real, liquid expiry (YYYY-MM-DD) to pass to ``get_options_chain``: the standard monthly
    expiration (3rd Friday) of the month ``dte`` days past ``as_of``.

    NOTE: ``get_options_chain`` returns an EMPTY chain for a date that is not an actual listed
    expiration, so a raw ``as_of + dte`` calendar date does not work -- snap to the monthly opex
    (the most liquid expiry, and the one that carries full greeks; ~30-60 DTE for the default).
    Fallback for the caller: pass ``expiry="init"`` to let the endpoint return the nearest listed
    chain when the monthly is unavailable.
    """
    base = datetime.strptime(str(as_of)[:10], "%Y-%m-%d") + timedelta(days=int(dte))
    return _third_friday(base.year, base.month).strftime("%Y-%m-%d")


def assemble_bundle(responses: Any) -> dict[str, dict]:
    """Turn captured raw responses into the ``{TICKER: {screener, chain}}`` bundle the producer
    consumes. Accepts a per-ticker map or a ``{"responses": {...}}``/``{"bundle": {...}}`` wrapper.

    Keeps only entries that carry a usable (dict/list) screener or chain; a name with neither is
    dropped (nothing to surface). Never raises on a malformed entry -- it is simply skipped.
    """
    if isinstance(responses, dict):
        for key in ("bundle", "responses", "responses_by_ticker"):
            inner = responses.get(key)
            if isinstance(inner, dict):
                responses = inner
                break
    if not isinstance(responses, dict):
        return {}
    bundle: dict[str, dict] = {}
    for raw_tk, data in responses.items():
        tk = _norm_ticker(raw_tk)
        if not tk or tk.startswith("_") or not isinstance(data, dict):
            continue
        screener = data.get("screener")
        chain = data.get("chain")
        entry: dict[str, Any] = {}
        if isinstance(screener, (dict, list)):
            entry["screener"] = screener
        if isinstance(chain, (dict, list)):
            entry["chain"] = chain
        if entry:
            bundle[tk] = entry
    return bundle


def build_cache(
    bundle: dict[str, dict],
    *,
    as_of: Optional[str] = None,
    generated_at: Optional[str] = None,
    expiry_target: Optional[str] = None,
) -> dict:
    """Wrap a bundle with auditable ``_meta`` for the cache file. ``full_build_runner`` strips the
    ``_meta`` key (and any ``_``-prefixed key) back out before surfacing."""
    bundle = bundle if isinstance(bundle, dict) else {}
    meta = {
        "source": "unusual_whales",
        "endpoints": ["get_stock_screener", "get_options_chain"],
        "as_of": as_of,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "expiry_target": expiry_target,
        "count": len(bundle),
        "tickers": sorted(bundle),
        "note": (
            "Raw UW screener+chain per conviction name; consumed by "
            "full_build_runner -> options_surface.surface_options. Not a trade order."
        ),
    }
    return {"_meta": meta, **bundle}


def write_cache(path: str | Path, cache: dict) -> Path:
    """Atomically write the cache JSON (tmp + replace) so a partial write never lands."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    return path


def refresh_from_responses(
    responses: Any,
    *,
    out: str | Path = DEFAULT_OUT,
    as_of: Optional[str] = None,
    generated_at: Optional[str] = None,
    expiry_target: Optional[str] = None,
) -> dict:
    """File-driven path: assemble captured responses into a cache and write it. Returns a small
    summary (token-safe -- no raw payloads)."""
    bundle = assemble_bundle(responses)
    cache = build_cache(bundle, as_of=as_of, generated_at=generated_at, expiry_target=expiry_target)
    path = write_cache(out, cache)
    return {"path": str(path), "count": len(bundle), "tickers": sorted(bundle)}


def _self_test() -> int:
    # universe: ACTIVE kept, MONITOR dropped, extra appended, dedup + cap honored.
    uni = select_universe(
        [{"ticker": "nvda", "stance": "ACTIVE"}, {"ticker": "MU", "stance": "MONITOR"},
         {"ticker": "NVDA", "stance": "ACTIVE"}],
        extra=["AVGO", "nvda"], cap=10)
    assert uni == ["NVDA", "AVGO"], uni
    assert "MU" in select_universe([{"ticker": "MU", "stance": "MONITOR"}], include_no_add=True)
    # expiry snaps to the standard monthly opex (3rd Friday) ~DTE out, not a raw calendar date.
    assert target_expiry("2026-06-18", dte=45) == "2026-08-21", target_expiry("2026-06-18", dte=45)
    assert target_expiry("2026-06-18", dte=30) == "2026-07-17", target_expiry("2026-06-18", dte=30)
    # assembly: drops the no-data name, keeps the real one, never raises on junk.
    b = assemble_bundle({"NVDA": {"screener": {"result": [{}]}, "chain": {"states": []}},
                         "ZZZ": {"screener": 5, "chain": None}, "_meta": {"x": 1}, "bad": [1, 2]})
    assert set(b) == {"NVDA"}, b
    cache = build_cache(b, as_of="2026-06-18", generated_at="x", expiry_target="2026-08-02")
    assert cache["_meta"]["count"] == 1 and cache["_meta"]["tickers"] == ["NVDA"]
    assert "NVDA" in cache and "_meta" in cache
    assert assemble_bundle([1, 2, 3]) == {} and assemble_bundle(None) == {}
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Assemble + write the options-chain cache.")
    p.add_argument("--from-responses", help="JSON of captured raw {ticker: {screener, chain}} responses")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="cache path to write")
    p.add_argument("--as-of", help="positions/screener as-of date (YYYY-MM-DD)")
    p.add_argument("--generated-at", help="ISO timestamp override (determinism)")
    p.add_argument("--expiry", help="expiry target used for the chain pulls (YYYY-MM-DD)")
    p.add_argument("--self-test", action="store_true", help="run the in-module self test")
    args = p.parse_args(argv)

    if args.self_test:
        rc = _self_test()
        print("options_chain_refresh self-test:", "ok" if rc == 0 else "FAIL")
        return rc
    if not args.from_responses:
        p.error("supply --from-responses <json> (or --self-test)")
    responses = json.loads(Path(args.from_responses).read_text(encoding="utf-8"))
    summary = refresh_from_responses(
        responses, out=args.out, as_of=args.as_of,
        generated_at=args.generated_at, expiry_target=args.expiry)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
