"""Stage-5 skeleton runtime: the 2 critical plugs -> a validated cockpit feed.

The entry point the Claude-orchestrated cloud routine calls once it has fetched
the live data:

    page = <notion-fetch 📊 Latest Portfolio>                       # Claude fetches
    uw   = {t: <get_ticker_close_prices(t, "1Y")>                    # Claude fetches
            for t in runtime_adapters.UW_ROTATION_TICKERS}
    feed = build_skeleton_feed(page, uw, theses)                     # this module
    # -> render <ConvictionCockpit feed={feed} />

Skeleton = only the two CRITICAL_SOURCES (portfolio + uw_price). The other plugs
(uw_macro, fundstrat, meridian) come in later phases; until then the macro,
fresh-signal, and per-name-conviction sections render thin or empty — expected,
and still passes Contract-C validation.
"""
from __future__ import annotations

import dataclasses

from collection import collect
from feed_assembler import assemble_feed
from validators import validate_cockpit_feed
from portfolio import build_portfolio_source
from uw_price import build_uw_price_source
from sources import SourceRegistry
from runtime_adapters import portfolio_positions_from_page, closes_by_ticker_from_uw


class SkeletonFeedError(RuntimeError):
    """A critical source delivered no data, or the feed failed validation —
    the routine must NOT render a partial / invalid cockpit."""


def _as_of_from_snapshot(snap) -> str:
    ts = getattr(snap, "run_timestamp", None) or ""
    return ts[:10] if ts else ""


def build_skeleton_feed(
    portfolio_page_text: str,
    uw_responses_by_ticker: dict,
    theses: list,
    *,
    parabolic=None,
    as_of: str | None = None,
    run_timestamp: str | None = None,
    generated_at: str | None = None,
) -> dict:
    """Live fetch output -> a validated Contract-C cockpit feed (2 critical plugs).

    Raises SkeletonFeedError if a critical source delivered no data or the feed
    fails validation."""
    # 1. live fetch output -> plug inputs (the S5.1 / S5.2 adapters)
    positions = portfolio_positions_from_page(portfolio_page_text)
    closes = closes_by_ticker_from_uw(uw_responses_by_ticker)

    # 2. register the two critical plugs
    reg = SourceRegistry()
    reg.register(build_portfolio_source(positions))
    reg.register(build_uw_price_source(closes))

    # 3. collect into a CollectedSnapshot (Contract B)
    snap = collect(reg, run_timestamp=run_timestamp)

    # 4. critical-missing gate — abort rather than render a partial cockpit
    if snap.critical_missing:
        raise SkeletonFeedError(
            f"critical source(s) delivered no data: {snap.critical_missing} "
            "— not rendering a partial cockpit"
        )

    # 5. assemble the Contract-C feed
    feed = assemble_feed(
        {
            "as_of": as_of or _as_of_from_snapshot(snap),
            "snapshot": dataclasses.asdict(snap),
            "theses": theses or [],
        },
        parabolic=parabolic,
        generated_at=generated_at,
    )

    # 6. validate before handing to the cockpit
    errs = validate_cockpit_feed(feed)
    if errs:
        raise SkeletonFeedError(f"feed failed Contract-C validation: {errs}")
    return feed
