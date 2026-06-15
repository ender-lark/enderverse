#!/usr/bin/env python3
"""
uw_bundle_acquisition.py - normalized UW bundle builders.

This is the producer boundary. Raw UW payloads enter here, are immediately
adapted through the existing scorer adapters, and callers receive only canonical
bundle entries/observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from parabolic_setup_screener import CANDIDATE_PROFILES, bundle_entry_from_uw
from .endpoints import PARABOLIC_ENDPOINTS, UW_OPPORTUNITY_ENDPOINTS
from uw_opportunity_scan import observation_from_uw, normalize_oi
from .rest_client import UWRestClient, unwrap_uw_rows


@dataclass
class NormalizedPull:
    ticker: str
    mode: str
    ok: bool
    entry: Optional[dict] = None
    observation: Optional[dict] = None
    source_counts: Optional[dict] = None
    non_actionable_sources: Optional[list[str]] = None
    error: Optional[str] = None

    def to_jsonable(self) -> dict:
        out = {
            "ticker": self.ticker,
            "mode": self.mode,
            "ok": self.ok,
            "source_counts": self.source_counts or {},
        }
        if self.entry is not None:
            out["entry"] = self.entry
        if self.observation is not None:
            out["observation"] = self.observation
        if self.non_actionable_sources:
            out["non_actionable_sources"] = self.non_actionable_sources
        if self.error:
            out["error"] = self.error
        return out


def _count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("data", "results", "signals", "result"):
            if key in payload:
                return _count(payload.get(key))
        return 1 if payload else 0
    return 1 if payload else 0


def _floatish(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _oi_rows_are_non_actionable(raw: Any) -> bool:
    """True when UW returned OI rows, but none show a measurable OI build.

    The availability gate should still block malformed rows, but a live endpoint
    response full of zero-change contracts is a checked no-signal source, not a
    normalization failure.
    """
    rows = unwrap_uw_rows(raw)
    if not rows:
        return False
    saw_numeric = False
    for row in rows:
        if not isinstance(row, dict):
            return False
        change_values = [
            row.get("oi_diff_plain"),
            row.get("oi_change_abs"),
            row.get("oi_diff"),
            row.get("change"),
            row.get("oi_change"),
            row.get("oi_change_perc"),
            row.get("oi_change_pct"),
            row.get("pct_change"),
            row.get("oi_pct"),
        ]
        nums = [_floatish(v) for v in change_values if v is not None]
        if not nums:
            return False
        saw_numeric = True
        if any(v != 0 for v in nums):
            return False
    return saw_numeric


def build_parabolic_entry(
    client: UWRestClient,
    ticker: str,
    *,
    price_timeframe: str = "5Y",
    price_limit: int = 1400,
    profile: Optional[dict] = None,
) -> NormalizedPull:
    """Fetch and normalize one ticker for parabolic_setup_screener."""
    tk = ticker.strip().upper()
    try:
        earnings = client.get_json(PARABOLIC_ENDPOINTS["earnings"],
                                   path_params={"ticker": tk})
        prices = client.get_json(PARABOLIC_ENDPOINTS["prices"],
                                 path_params={"ticker": tk, "candle_size": "1d"},
                                 params={"timeframe": price_timeframe, "limit": price_limit})
        income = client.get_json(PARABOLIC_ENDPOINTS["income"],
                                 path_params={"ticker": tk})
        info = client.get_json(PARABOLIC_ENDPOINTS["info"],
                               path_params={"ticker": tk})
        prof = profile if profile is not None else CANDIDATE_PROFILES.get(tk)
        entry = bundle_entry_from_uw(unwrap_uw_rows(earnings), prices,
                                     unwrap_uw_rows(income), info, profile=prof)
        return NormalizedPull(
            ticker=tk,
            mode="parabolic",
            ok=True,
            entry=entry,
            source_counts={
                "earnings": _count(earnings),
                "prices": _count(prices),
                "income": _count(income),
                "info": _count(info),
            },
        )
    except Exception as exc:  # noqa: BLE001 - fail one ticker, not the run
        return NormalizedPull(ticker=tk, mode="parabolic", ok=False, error=str(exc))


def build_opportunity_observation(
    client: UWRestClient,
    ticker: str,
    *,
    flow_limit: int = 100,
    oi_limit: int = 100,
    dark_pool_limit: int = 500,
    include_modifiers: bool = False,
) -> NormalizedPull:
    """Fetch and normalize one ticker for uw_opportunity_scan."""
    tk = ticker.strip().upper()
    try:
        flow = client.get_json(UW_OPPORTUNITY_ENDPOINTS["flow"],
                               path_params={"ticker": tk},
                               params={"limit": flow_limit})
        oi = client.get_json(UW_OPPORTUNITY_ENDPOINTS["oi"],
                             path_params={"ticker": tk},
                             params={"limit": oi_limit})
        dark_pool = client.get_json(UW_OPPORTUNITY_ENDPOINTS["dark_pool"],
                                    path_params={"ticker": tk},
                                    params={"limit": dark_pool_limit})
        greek = iv = info = None
        spot = None
        if include_modifiers:
            greek = client.get_json(UW_OPPORTUNITY_ENDPOINTS["greek"],
                                    path_params={"ticker": tk})
            iv = client.get_json(UW_OPPORTUNITY_ENDPOINTS["iv"],
                                 path_params={"ticker": tk})
            info = client.get_json(PARABOLIC_ENDPOINTS["info"],
                                   path_params={"ticker": tk})
            if isinstance(info, dict):
                spot = info.get("price") or (info.get("data") or {}).get("price")
        obs = observation_from_uw(flow=flow, oi=oi, dark_pool=dark_pool,
                                  greek=greek, iv=iv, spot=spot, ticker=tk)
        counts = {"flow": _count(flow), "oi": _count(oi), "dark_pool": _count(dark_pool)}
        non_actionable_sources = []
        if counts["oi"] and "oi" not in obs and normalize_oi(oi) is None and _oi_rows_are_non_actionable(oi):
            non_actionable_sources.append("oi")
        if include_modifiers:
            counts.update({"greek": _count(greek), "iv": _count(iv), "info": _count(info)})
        return NormalizedPull(ticker=tk, mode="opportunity", ok=True,
                              observation=obs, source_counts=counts,
                              non_actionable_sources=non_actionable_sources)
    except Exception as exc:  # noqa: BLE001 - fail one ticker, not the run
        return NormalizedPull(ticker=tk, mode="opportunity", ok=False, error=str(exc))
