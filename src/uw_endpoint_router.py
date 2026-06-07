#!/usr/bin/env python3
"""
uw_endpoint_router.py - scenario-specific Unusual Whales endpoint routing.

This module does not fetch UW data. It maps an operator scenario to the
official endpoint constants that should be considered for that scenario, then
validates that every path is from the approved catalog. The point is to keep
"what should we query now?" explicit, testable, and resistant to hallucinated
endpoint paths.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from typing import Any

from codex_uw.endpoints import UWEndpoints, validate_endpoint_path


def _ep(name: str) -> dict[str, str]:
    path = getattr(UWEndpoints, name)
    return {"name": name, "path": path}


def _group(
    key: str,
    *,
    priority: int,
    scope: str,
    endpoints: list[str],
    why: str,
    decision_use: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "priority": priority,
        "scope": scope,
        "endpoints": [_ep(name) for name in endpoints],
        "why": why,
        "decision_use": decision_use,
    }


UW_ROUTING_PROFILES: dict[str, dict[str, Any]] = {
    "pre_market_crash_triage": {
        "label": "Pre-market crash triage",
        "purpose": "Separate forced-risk reduction from a watch/rebound plan after a fast drawdown.",
        "trigger": "Use before the open after a broad AI/crypto/market shock or a major overnight policy/geopolitical move.",
        "default_cadence": "Pre-market and again near the first 30-60 minutes if market internals keep changing.",
        "freshness_requirement": "Market/flow lanes should be same-session; Friday evidence is stale by Monday pre-market.",
        "operator_question": "Do we need to cut exposure, hedge, wait, or prepare add-on entries after forced selling?",
        "groups": [
            _group(
                "broad_tape",
                priority=1,
                scope="market",
                endpoints=[
                    "MARKET_TIDE",
                    "TOP_NET_IMPACT",
                    "TOTAL_OPTIONS_VOLUME",
                    "MARKET_MOVERS",
                    "MARKET_CORRELATIONS",
                ],
                why="A single-name signal is unsafe if the whole tape is under forced deleveraging.",
                decision_use="Classify the morning as risk-off continuation, relief bounce, or mixed tape.",
            ),
            _group(
                "index_and_sector_pressure",
                priority=2,
                scope="sector_or_etf",
                endpoints=["ETF_TIDE", "SECTOR_TIDE"],
                why="AI/semis/software can diverge from the broad market after a crash.",
                decision_use="Identify whether exposure should be cut by factor wrapper, single name, or not at all.",
            ),
            _group(
                "position_specific_flow",
                priority=3,
                scope="ticker",
                endpoints=[
                    "TICKER_FLOW_RECENT",
                    "TICKER_FLOW_ALERTS",
                    "TICKER_OPTIONS_VOLUME",
                    "DARKPOOL_TICKER",
                    "TICKER_OI_CHANGE",
                ],
                why="Confirms whether the names we own are seeing capitulation, dip buying, or continuing sell pressure.",
                decision_use="Promote only evidence-backed trim/add/recheck prompts for owned names.",
            ),
            _group(
                "dealer_and_volatility_context",
                priority=4,
                scope="ticker",
                endpoints=[
                    "TICKER_GREEK_EXPOSURE_STRIKE",
                    "TICKER_SPOT_EXPOSURES_STRIKE",
                    "TICKER_IV_RANK",
                    "TICKER_VOL_TERM_STRUCTURE",
                    "TICKER_REALIZED_VOL",
                ],
                why="Fast markets can be dealer-flow driven; entry quality depends on gamma/vol context.",
                decision_use="Avoid chasing unstable rebounds; prefer re-check prompts when vol or strike pressure is unresolved.",
            ),
            _group(
                "price_state",
                priority=5,
                scope="ticker",
                endpoints=["TICKER_OHLC", "TICKER_STOCK_STATE", "TICKER_TECHNICAL_INDICATOR"],
                why="The dashboard needs live price context before it recommends time-sensitive sizing changes.",
                decision_use="Convert thesis-level ideas into current-entry, pullback, or no-action states.",
            ),
        ],
    },
    "fundstrat_signal_confirmation": {
        "label": "Fundstrat signal confirmation",
        "purpose": "Check whether live market structure supports, contradicts, or delays a Fundstrat call.",
        "trigger": "Use after a fresh Fundstrat Inbox/radar/deck call, especially sell triggers or top-name adds.",
        "default_cadence": "Immediately after intake, then intraday only if the call is time-sensitive.",
        "freshness_requirement": "Fundstrat evidence can be dated; UW confirmation should be same-day when action is promoted.",
        "operator_question": "Is this Fundstrat call actionable now, stale, contradicted, or better queued for review?",
        "groups": [
            _group(
                "tactical_confirmation",
                priority=1,
                scope="ticker",
                endpoints=[
                    "TICKER_FLOW_RECENT",
                    "TICKER_FLOW_ALERTS",
                    "DARKPOOL_TICKER",
                    "TICKER_OPTIONS_VOLUME",
                    "TICKER_OI_CHANGE",
                ],
                why="Fresh Fundstrat timing calls need current tape confirmation before the cockpit promotes action.",
                decision_use="Upgrade to Key Now only when flow/price evidence supports the call or the risk of delay is high.",
            ),
            _group(
                "entry_quality",
                priority=2,
                scope="ticker",
                endpoints=[
                    "TICKER_OHLC",
                    "TICKER_STOCK_STATE",
                    "TICKER_GREEK_EXPOSURE_STRIKE",
                    "TICKER_SPOT_EXPOSURES_STRIKE",
                    "TICKER_IV_RANK",
                ],
                why="A correct thesis can still be a bad entry if the name is extended or dealer pressure is unstable.",
                decision_use="Tag recommendation timing as act now, scale, wait for pullback, or re-check before acting.",
            ),
            _group(
                "thesis_context",
                priority=3,
                scope="ticker_or_company",
                endpoints=["ANALYST_RATINGS", "NEWS_HEADLINES", "COMPANY_PROFILE", "TICKER_INFO"],
                why="Explains why the recommendation matters without mistaking context for fresh tactical evidence.",
                decision_use="Populate rationale drawers and disconfirmation notes.",
            ),
        ],
    },
    "asymmetric_discovery": {
        "label": "Asymmetric discovery",
        "purpose": "Find evidence-backed review prompts that may be large upside/downside opportunities.",
        "trigger": "Use during quiet periods, after volatility shocks, or when the opportunity lane is thin.",
        "default_cadence": "Daily during active markets; more often only when the dashboard is in high-volatility mode.",
        "freshness_requirement": "Discovery can tolerate 1-3 trading days, but promoted action still needs fresh confirmation.",
        "operator_question": "What deserves scarce review time because the upside/downside skew may be unusually large?",
        "groups": [
            _group(
                "market_wide_unusual_activity",
                priority=1,
                scope="market",
                endpoints=[
                    "FLOW_ALERTS",
                    "TOP_NET_IMPACT",
                    "DARKPOOL_RECENT",
                    "LIT_FLOW_RECENT",
                    "MARKET_MOVERS",
                    "OPTION_CONTRACT_SCREENER",
                    "STOCK_SCREENER",
                ],
                why="Asymmetric ideas often start outside the current book before they hit thesis files.",
                decision_use="Create review prompts, not trade instructions, until thesis and freshness checks pass.",
            ),
            _group(
                "sponsor_and_information_edge",
                priority=2,
                scope="market_or_ticker",
                endpoints=[
                    "ANALYST_RATINGS",
                    "INSIDER_TRANSACTIONS",
                    "CONGRESS_RECENT_TRADES",
                    "CONGRESS_UNUSUAL_BY_TICKERS",
                    "NEWS_HEADLINES",
                ],
                why="Flow alone is noisy; sponsor, insider, policy, and news context help rank what is worth reading.",
                decision_use="Boost review priority only when independent evidence supports the flow anomaly.",
            ),
            _group(
                "ticker_followup",
                priority=3,
                scope="ticker",
                endpoints=[
                    "TICKER_FLOW_PER_EXPIRY",
                    "TICKER_FLOW_PER_STRIKE",
                    "TICKER_GREEK_FLOW",
                    "TICKER_VOL_TERM_STRUCTURE",
                    "TICKER_INFO",
                ],
                why="Follow-up endpoints explain whether an anomaly is directional, hedging, calendar-specific, or noisy.",
                decision_use="Decide whether to send to Research Queue, Quiet Watch, or Key Now re-check.",
            ),
        ],
    },
    "portfolio_reallocation": {
        "label": "Portfolio reallocation",
        "purpose": "Decide what to trim, hold, add, or leave alone after current positions are supplied.",
        "trigger": "Use when account positions are refreshed, after major market moves, or before Monday planning.",
        "default_cadence": "Weekly by default; immediately after a large drawdown or new Fundstrat timing call.",
        "freshness_requirement": "Positions must be latest supplied; price/flow should be same-session for any action-sized leg.",
        "operator_question": "Which portfolio changes maximize early-retirement impact per unit of risk and time?",
        "groups": [
            _group(
                "exposure_and_price_state",
                priority=1,
                scope="ticker",
                endpoints=["TICKER_OHLC", "TICKER_STOCK_STATE", "TICKER_INFO", "COMPANY_PROFILE"],
                why="Target gaps are meaningless if the live book or price state is stale.",
                decision_use="Build the current exposure, drawdown, and entry-quality map for each material holding.",
            ),
            _group(
                "factor_and_wrapper_context",
                priority=2,
                scope="sector_or_etf",
                endpoints=["ETF_TIDE", "SECTOR_TIDE", "MARKET_CORRELATIONS", "TOTAL_OPTIONS_VOLUME"],
                why="Reallocation must avoid accidentally increasing the same factor through wrappers and single names.",
                decision_use="Separate factor-flat rotations from net-new risk increases.",
            ),
            _group(
                "conviction_and_sponsorship",
                priority=3,
                scope="ticker_or_company",
                endpoints=[
                    "ANALYST_RATINGS",
                    "INSTITUTION_OWNERSHIP",
                    "TICKER_INSIDERS",
                    "TICKER_INSIDER_FLOW",
                    "NEWS_HEADLINES",
                ],
                why="Sizing changes should be tied to thesis strength, sponsorship, and current contradictory evidence.",
                decision_use="Rank add/trim legs by conviction, disconfirmation, and impact rather than gap size alone.",
            ),
            _group(
                "flow_and_risk_confirmation",
                priority=4,
                scope="ticker",
                endpoints=[
                    "TICKER_FLOW_RECENT",
                    "DARKPOOL_TICKER",
                    "TICKER_OPTIONS_VOLUME",
                    "TICKER_IV_RANK",
                    "TICKER_VOL_STATS",
                    "TICKER_GREEK_EXPOSURE_STRIKE",
                ],
                why="A high-conviction reallocation still needs live timing and risk checks.",
                decision_use="Promote legs to act-now, stage, or wait states.",
            ),
        ],
    },
    "post_close_review": {
        "label": "Post-close review",
        "purpose": "Compress the day into what changed, what aged out, and what must be checked before the next open.",
        "trigger": "Use after close and after late Fundstrat/UW evidence arrives.",
        "default_cadence": "Post-close on market days.",
        "freshness_requirement": "Close-of-day data is fresh for the next pre-market plan, but not enough for intraday action.",
        "operator_question": "What should be resolved, rechecked, or carried into tomorrow's Key Now lane?",
        "groups": [
            _group(
                "daily_flow_summary",
                priority=1,
                scope="ticker",
                endpoints=[
                    "TICKER_FLOW_PER_EXPIRY",
                    "TICKER_FLOW_PER_STRIKE",
                    "TICKER_OI_CHANGE",
                    "DARKPOOL_TICKER",
                    "LIT_FLOW_TICKER",
                ],
                why="Post-close is the best time to convert noisy intraday flow into durable evidence.",
                decision_use="Update action memory, open-review aging, and source-call calibration.",
            ),
            _group(
                "risk_and_vol_reset",
                priority=2,
                scope="ticker",
                endpoints=[
                    "TICKER_REALIZED_VOL",
                    "TICKER_VOL_TERM_STRUCTURE",
                    "TICKER_IV_RANK",
                    "TICKER_GREEK_EXPOSURE_EXPIRY",
                ],
                why="Volatility changes whether a next-day action should be direct equity, defined-risk, or no action.",
                decision_use="Prepare the next-day action cards without pretending the data is still intraday-fresh.",
            ),
            _group(
                "calendar_and_news",
                priority=3,
                scope="market_or_ticker",
                endpoints=["ECONOMIC_CALENDAR", "TICKER_EARNINGS", "NEWS_HEADLINES"],
                why="Next-day gaps often come from scheduled catalysts and late headlines.",
                decision_use="Move relevant items into Re-check Before Acting with explicit trigger levels.",
            ),
        ],
    },
    "event_risk_political_macro": {
        "label": "Event-risk and political macro",
        "purpose": "Track external shocks that can overpower normal thesis and flow signals.",
        "trigger": "Use for tariff/policy/geopolitical/rates/oil/liquidity headlines.",
        "default_cadence": "When event watch is high; otherwise as part of pre-market/post-close routines.",
        "freshness_requirement": "Intraday to one trading day; stale event evidence must force re-check before acting.",
        "operator_question": "Is the external shock changing new-buy timing, hedges, or position sizing?",
        "groups": [
            _group(
                "macro_tape",
                priority=1,
                scope="market",
                endpoints=[
                    "MARKET_TIDE",
                    "TOP_NET_IMPACT",
                    "MARKET_MOVERS",
                    "ECONOMIC_CALENDAR",
                    "NEWS_HEADLINES",
                ],
                why="Event risk is first a tape/liquidity problem before it is a single-name thesis problem.",
                decision_use="Determine whether to keep actions in watch/re-check or promote protective action.",
            ),
            _group(
                "factor_transmission",
                priority=2,
                scope="sector_or_etf",
                endpoints=["SECTOR_TIDE", "ETF_TIDE", "MARKET_CORRELATIONS"],
                why="Political/macro shocks often transmit through rates, oil, semis, crypto, or software factors.",
                decision_use="Identify which exposure sleeves are actually at risk.",
            ),
            _group(
                "policy_and_sponsor_context",
                priority=3,
                scope="market_or_ticker",
                endpoints=["CONGRESS_RECENT_TRADES", "CONGRESS_UNUSUAL_BY_TICKERS", "NEWS_HEADLINES"],
                why="Political flow is weak evidence alone, but it can explain why an external shock is persistent.",
                decision_use="Add context to rationale drawers without using it as standalone tactical proof.",
            ),
        ],
    },
    "reddit_escalation_vetting": {
        "label": "Reddit escalation vetting",
        "purpose": "Vet a Reddit velocity signal before it reaches the Research Queue or action dashboard.",
        "trigger": "Use only after the Reddit Signal Module logs an eligible velocity anomaly.",
        "default_cadence": "On anomaly; never continuous trade promotion.",
        "freshness_requirement": "Reddit anomaly and UW vetting should be same-day for any Key Now escalation.",
        "operator_question": "Is this crowd signal early information, a lagging echo, or noise?",
        "groups": [
            _group(
                "crowd_signal_confirmation",
                priority=1,
                scope="ticker",
                endpoints=[
                    "TICKER_FLOW_RECENT",
                    "DARKPOOL_TICKER",
                    "TICKER_OPTIONS_VOLUME",
                    "NEWS_HEADLINES",
                    "MARKET_MOVERS",
                ],
                why="Reddit data is noisy and reflexive; it needs independent live evidence before action surfacing.",
                decision_use="Escalate to Research Queue or Quiet Watch, not direct execution.",
            ),
            _group(
                "avoid_echo_and_chase",
                priority=2,
                scope="ticker",
                endpoints=[
                    "TICKER_OHLC",
                    "TICKER_STOCK_STATE",
                    "TICKER_IV_RANK",
                    "TICKER_VOL_TERM_STRUCTURE",
                    "TICKER_GREEK_EXPOSURE_STRIKE",
                ],
                why="Many social spikes happen after a move; entry quality must be checked before surfacing action.",
                decision_use="Classify as early signal, lagging echo, chase risk, or disconfirmed.",
            ),
        ],
    },
}


def routing_profiles() -> dict[str, dict[str, Any]]:
    """Return a deep copy so callers cannot mutate the canonical routing map."""
    return deepcopy(UW_ROUTING_PROFILES)


def profile_for_mode(mode: str) -> dict[str, Any]:
    profiles = routing_profiles()
    if mode not in profiles:
        known = ", ".join(sorted(profiles))
        raise KeyError(f"Unknown UW routing mode {mode!r}; expected one of: {known}")
    return profiles[mode]


def endpoint_names_for_mode(mode: str) -> list[str]:
    profile = profile_for_mode(mode)
    names: list[str] = []
    for group in profile["groups"]:
        for endpoint in group["endpoints"]:
            names.append(endpoint["name"])
    return names


def validate_profiles(profiles: dict[str, dict[str, Any]] | None = None) -> None:
    profiles = profiles or UW_ROUTING_PROFILES
    for mode, profile in profiles.items():
        if not profile.get("groups"):
            raise ValueError(f"UW routing mode {mode} has no endpoint groups")
        for group in profile["groups"]:
            if not group.get("endpoints"):
                raise ValueError(f"UW routing mode {mode} group {group.get('key')} has no endpoints")
            for endpoint in group["endpoints"]:
                validate_endpoint_path(endpoint["path"])


def _format_text(mode: str | None) -> str:
    validate_profiles()
    profiles = routing_profiles()
    selected = {mode: profile_for_mode(mode)} if mode else profiles
    lines = ["UW Endpoint Routing Profiles"]
    for profile_key, profile in selected.items():
        lines.append("")
        lines.append(f"{profile_key}: {profile['label']}")
        lines.append(f"  purpose: {profile['purpose']}")
        lines.append(f"  trigger: {profile['trigger']}")
        lines.append(f"  operator question: {profile['operator_question']}")
        lines.append(f"  freshness: {profile['freshness_requirement']}")
        for group in sorted(profile["groups"], key=lambda row: row["priority"]):
            endpoint_names = ", ".join(endpoint["name"] for endpoint in group["endpoints"])
            lines.append(f"  [{group['priority']}] {group['key']} ({group['scope']}): {endpoint_names}")
            lines.append(f"      why: {group['why']}")
            lines.append(f"      use: {group['decision_use']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print validated UW endpoint routing profiles.")
    parser.add_argument("--mode", choices=sorted(UW_ROUTING_PROFILES), help="Single routing profile to print.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    validate_profiles()
    payload: Any = profile_for_mode(args.mode) if args.mode else routing_profiles()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_format_text(args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
