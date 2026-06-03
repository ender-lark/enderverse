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
from uw_macro import build_uw_macro_source
from fundstrat_bible import build_fundstrat_bible_source
from fundstrat_daily import build_fundstrat_daily_source
from meridian import build_meridian_source
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


def build_full_feed(
    portfolio_page_text: str,
    uw_responses_by_ticker: dict,
    theses: list,
    *,
    macro_snapshot: dict | None = None,
    fs_bible_deck: dict | None = None,
    fs_daily_calls: list | None = None,
    meridian_items: list | None = None,
    heartbeat: list | None = None,
    synthesis: dict | None = None,
    research: dict | None = None,
    radar: list | None = None,
    catalysts: list | None = None,
    uw_opportunity: dict | None = None,
    open_opportunities: dict | None = None,
    opp_prices: dict | None = None,
    top_prospects: dict | None = None,
    aging_threshold_days: int = 3,
    parabolic=None,
    as_of: str | None = None,
    run_timestamp: str | None = None,
    generated_at: str | None = None,
) -> dict:
    """Live fetch output (2 critical + up to 4 optional plugs) -> a validated
    Contract-C cockpit feed. The full-feed sibling of build_skeleton_feed.

    Critical sources = portfolio + uw_price (SAME gate as the skeleton: a missing
    critical source aborts). The four optional plugs are registered ONLY when
    their data is supplied; an omitted OR empty optional plug degrades that
    section gracefully — never an error.

    radar threads through assemble_feed into feed["radar"] (the endorsed-but-not-
    owned watch lane). Left None it defaults to the engine-derived list off the
    fundstrat_daily calls — empty when none qualify, so omitting it is a no-op.

    catalysts threads through assemble_feed into feed["catalysts"] (the near-term
    event lane, read off the Catalyst Calendar by the cockpit-build step). Left
    None it defaults to [] — an unsourced/dark lane, never "no catalysts".

    uw_opportunity is the daily UW opportunity-signals cache (Strand 3): the
    cockpit-build step loads conviction_engine/uw_opportunity_signals.json (written
    by the uw_opportunity_scan SCOUT routine) and passes it here. assemble_feed
    folds it into the card stream as kind="uw_opportunity" cards; fresh bullish flow
    becomes a direction up-event + a lean-in "UW ▲" evidence row on names that
    ALREADY have conviction quality — never an auto-buy, never a quality bump. Left
    None it is inert (default-None → byte-identical feed; the golden bundle carries
    no flow cache, so the golden master stays drift-free).

    Optional inputs (all produced by the in-session / SCOUT fetch step):
      macro_snapshot  -> runtime_adapters.uw_macro_snapshot_from_uw(...)   {rates, levels}
      fs_bible_deck   -> Claude-read FS Bible summary  {deck_date, macro_stance, what_to_own, top5, bottom5}
      fs_daily_calls  -> Claude-read FS Inbox 7d       [{author,ticker,direction,entry,stop,target,window,quote,date}]
      meridian_items  -> Claude-read Meridian doc      [{subject,item_type,direction,...,theme,quote,date}]

    MERIDIAN IS A STATIC BASELINE (frozen ~Mar 2026): each item MUST carry its
    real `date` so the cockpit shows true age. It feeds background thesis only —
    model trades come through as kind="model_trade" (non-actionable), never as
    fresh buy signals. Supplement those sleeves with live price/flow + Fundstrat.
    """
    positions = portfolio_positions_from_page(portfolio_page_text)
    closes = closes_by_ticker_from_uw(uw_responses_by_ticker)

    reg = SourceRegistry()
    reg.register(build_portfolio_source(positions))       # critical
    reg.register(build_uw_price_source(closes))            # critical
    if macro_snapshot is not None:
        reg.register(build_uw_macro_source(macro_snapshot))
    if fs_bible_deck is not None:
        reg.register(build_fundstrat_bible_source(fs_bible_deck))
    if fs_daily_calls is not None:
        reg.register(build_fundstrat_daily_source(fs_daily_calls))
    if meridian_items is not None:
        reg.register(build_meridian_source(meridian_items))

    snap = collect(reg, run_timestamp=run_timestamp)
    if snap.critical_missing:
        raise SkeletonFeedError(
            f"critical source(s) delivered no data: {snap.critical_missing} "
            "— not rendering a partial cockpit"
        )

    feed = assemble_feed(
        {
            "as_of": as_of or _as_of_from_snapshot(snap),
            "snapshot": dataclasses.asdict(snap),
            "theses": theses or [],
        },
        parabolic=parabolic,
        generated_at=generated_at,
        heartbeat=heartbeat,
        synthesis=synthesis,
        research=research,
        radar=radar,
        catalysts=catalysts,
        uw_opportunity=uw_opportunity,
        open_opportunities=open_opportunities,
        opp_prices=opp_prices,
        top_prospects=top_prospects,
        aging_threshold_days=aging_threshold_days,
    )
    errs = validate_cockpit_feed(feed)
    if errs:
        raise SkeletonFeedError(f"feed failed Contract-C validation: {errs}")
    return feed
