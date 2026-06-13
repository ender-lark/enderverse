#!/usr/bin/env python3
"""
deepdive_runner.py — v11.18 Patch 2 implementation

Renders a structured markdown checklist of Tier 1 + Tier 2 UW endpoints that
should be pulled on every Deepdive launcher invocation. Provides the forcing
function for the 16-item auto-pull mandate documented in CI v11.18 and
Operational_Reference_-_SKB.md.

DESIGN PHILOSOPHY:
  Pure-logic checklist generator by default. Optional --battery mode can pull
  or process bounded UW evidence for the target ticker, but missing/failing
  lanes remain explicit not_checked rows.

  Mirrors v11.17 session_open_preflight.py pattern: "pure-logic core,
  JSON in / markdown out, no external dependencies."

WHY THIS EXISTS:
  Pre-v11.18, the 16-item Deepdive auto-pull mandate lived in CI text and
  the UW Capability Inventory. With no rendered checklist at the top of
  Deepdive responses, items quietly fell off when Claude focused on
  narrative synthesis. Per P-SIMPLICITY: "forcing function — does it rely
  on memory alone? if yes, it gets bypassed."

  The ANET deepdive (5/15/26) hit 5 of 16 items before operator pushback
  surfaced the gap — missing dark pool until prompted, congressional
  trades, Greek exposure, fundamental breakdown, earnings transcript
  auto-pull on a -17% post-print move (v11.8 mandate), Piotroski/Altman,
  8Q surprise history, sector PE comp, and SEC 8-K scan.

USAGE:
    python deepdive_runner.py --ticker ANET
    python deepdive_runner.py --ticker LEU --mode tier1
    python deepdive_runner.py --ticker NBIS --mode full --tier-a

  --mode deepdive (default): Tier 1 always + Tier 2 Deepdive add-on
  --mode tier1:              Tier 1 only (Two-Lens 3+ signals fire)
  --mode full:               Tier 1 + Tier 2 + Tier 3 ($50K+ / ≥2 accts)

  --tier-a:    Force Tier A conditional items (earnings transcript, etc)
  --post-er:   Post-earnings ≥1σ flag — fires earnings transcript per v11.8
  --json:      Output JSON instead of markdown
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional


@dataclass
class ChecklistItem:
    tier: str
    label: str
    endpoint: str
    condition: str
    notes: str = ""

    def applies(self, mode: str, tier_a: bool, post_er: bool) -> bool:
        if self.tier == "T1":
            return True
        if self.tier == "T3":
            return mode == "full"
        if self.tier == "T2":
            if mode == "tier1":
                return False
            if self.condition == "conditional_tier_a_or_post_er":
                return tier_a or post_er
            return True
        return False


CHECKLIST: List[ChecklistItem] = [
    # ---- Tier 1: Auto-fire on Two-Lens 3+ OR any Deepdive ----
    ChecklistItem(
        "T1", "Current price + company info",
        "UW:get_company_info", "always",
        "Verify price is fresh; never quote stale without timestamp"
    ),
    ChecklistItem(
        "T1", "Insider 90d (discretionary C-suite filtered)",
        "UW:get_insider_transactions", "always",
        "Filter 10b5-1, RSU sell-to-cover, exercise-and-sell. >$500K open-market buys = bullish. Coordinated multi-insider same-day = top flag."
    ),
    ChecklistItem(
        "T1", "Institutional 13F snapshot + QoQ delta",
        "UW:get_institutions", "always",
        "Tier 1 if whale delta >$100M; Tier 2 if >20% prior; CLUSTER if 3+ same direction same Q"
    ),
    ChecklistItem(
        "T1", "Congressional/Senate trades (30d)",
        "UW:get_congress_trades", "always",
        "30-45d STOCK Act lag inherent. Filter Trump-allied/Cabinet per v11.14 Cat 8."
    ),
    ChecklistItem(
        "T1", "Options flow snapshot (7d)",
        "UW:get_flow_alerts", "always",
        "Net call/put + OI deltas. Two-Lens forward signal #7."
    ),
    ChecklistItem(
        "T1", "Dark pool prints (30d)",
        "UW:get_dark_pool_trades", "always",
        "Accumulation/distribution skew. Rising-price + block flow = institutional accumulation pattern."
    ),
    ChecklistItem(
        "T1", "Correlations vs top 3 holdings",
        "UW:get_correlations", "always",
        "Feeds P-REASONING-ARCH Component 4 portfolio coherence; >0.7 triggers discount"
    ),
    ChecklistItem(
        "T1", "SEC 8-K filings (90d)",
        "web_search OR SEC EDGAR", "always",
        "Free public source. UW does not have native 8-K endpoint."
    ),

    # ---- Tier 2: Deepdive launcher OR ≥$25K OR Two-Lens 5/8+ OR P-REASONING-ARCH fires ----
    ChecklistItem(
        "T2", "Greek exposure (dealer positioning)",
        "UW:get_greek_exposure_by_strike OR _by_expiry", "deepdive_or_tierA",
        "Gamma flip levels, vanna/charm exposure. AI complex timing context."
    ),
    ChecklistItem(
        "T2", "Full options chain + IV term structure",
        "UW:get_options_chain", "deepdive_or_tierA",
        "Tier A/B ticket construction. Check IV term structure for backwardation."
    ),
    ChecklistItem(
        "T2", "Fundamental breakdown (latest 4Q + segmentation)",
        "UW:get_fundamental_breakdown", "deepdive_or_tierA",
        "Consumption rule: latest 4Q + segmentation snapshot only. Discard pre-2024. Never echo full JSON."
    ),
    ChecklistItem(
        "T2", "Technical indicators (RSI, MACD, MA)",
        "UW:get_ticker_indicator_series", "deepdive_or_tierA",
        "Light validation. Newton handles primary technicals externally."
    ),
    ChecklistItem(
        "T2", "Earnings transcript",
        "UW:get_earnings_report", "conditional_tier_a_or_post_er",
        "FIRES IF: Tier A capital action OR Generational Lane OR held post-earnings ≥1σ from implied move. v11.8 mandate."
    ),
    ChecklistItem(
        "T2", "Piotroski F-score + Altman Z-score",
        "compute_from_fundamentals", "deepdive_or_tierA",
        "Computed via helper from UW basic fundamentals. F≥7 strong / ≤3 weak. Z>3 safe / <1.81 distress."
    ),
    ChecklistItem(
        "T2", "8-quarter earnings surprise history",
        "UW:get_earnings_history", "deepdive_or_tierA",
        "Trend in beat/miss magnitude; flag deceleration"
    ),
    ChecklistItem(
        "T2", "Analyst PT consensus with dates",
        "UW:get_analyst_ratings", "always",
        "Operator preference: PT vs current = upside; rating label secondary (Zacks=algo not thesis)."
    ),

    # ---- Tier 3: ≥$50K OR ≥2 accounts OR Generational Lane + capital action ----
    ChecklistItem(
        "T3", "Full financial statements (5Y)",
        "UW:get_fundamental_breakdown extended", "full_mode_only",
        "Beyond Tier 2 4Q snapshot — full 5Y for Generational decisions"
    ),
    ChecklistItem(
        "T3", "5-year insider history",
        "UW:get_insider_transactions extended", "full_mode_only",
        "Behavioral pattern analysis on management team"
    ),
    ChecklistItem(
        "T3", "Peer comparison table (3-5 names)",
        "UW:get_company_info × peers", "full_mode_only",
        "Manual assembly. PE, fwd PE, EV/EBITDA, gross margin, growth rates."
    ),
    ChecklistItem(
        "T3", "SEC 10-K (exec comp / M&A / segmentation)",
        "web_fetch SEC EDGAR 10-K", "full_mode_only",
        "On-demand when exec comp / M&A history specifically matters for Generational decision"
    ),
]


def iv_overlay_items(ivr: Optional[float], atm_iv: Optional[float]) -> List[ChecklistItem]:
    if ivr is None and atm_iv is None:
        return []
    return [
        ChecklistItem(
            "T2-IV", "IV classification (cheap/normal/expensive)",
            "uw_iv_context.py", "iv_available",
            f"IVR={ivr if ivr is not None else 'pending'}, ATM_IV={atm_iv if atm_iv is not None else 'pending'}. Cheap → LEAP +15%, Expensive → DIAGONAL/VERTICAL -20%"
        ),
    ]


def _arr(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("data", "results", "signals", "result"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return _arr(value)
    return []


def _f(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _today(now: datetime | date | str | None) -> date:
    if isinstance(now, datetime):
        return now.date()
    if isinstance(now, date):
        return now
    parsed = _date(now)
    if parsed:
        return parsed
    return datetime.now(timezone.utc).date()


def _occ_expiry(symbol: Any) -> date | None:
    text = str(symbol or "").strip().upper().replace(" ", "")
    import re
    match = re.search(r"(\d{2})(\d{2})(\d{2})[CP]\d{6,8}$", text)
    if not match:
        return None
    yy, mm, dd = match.groups()
    try:
        return date(2000 + int(yy), int(mm), int(dd))
    except ValueError:
        return None


def _option_side(row: dict[str, Any]) -> str:
    raw = str(_first(row, "type", "option_type", "put_call") or "").strip().lower()
    if raw.startswith("c"):
        return "call"
    if raw.startswith("p"):
        return "put"
    symbol = str(_first(row, "option_symbol", "option_chain", "symbol") or "").upper().replace(" ", "")
    if "C" in symbol[-9:]:
        return "call"
    if "P" in symbol[-9:]:
        return "put"
    return "unknown"


def _dte(row: dict[str, Any], as_of: date) -> int | None:
    explicit = _f(_first(row, "dte", "days_to_expiration", "days_to_expiry"))
    if explicit is not None:
        return int(explicit)
    expiry = _date(_first(row, "expiry", "expiration", "expiration_date"))
    if expiry is None:
        expiry = _occ_expiry(_first(row, "option_symbol", "option_chain", "symbol"))
    if expiry is None:
        return None
    return (expiry - as_of).days


def _oi_delta(row: dict[str, Any]) -> float:
    return float(_f(_first(row, "oi_diff_plain", "oi_change_abs", "oi_diff", "change")) or 0.0)


def analyze_multi_day_oi_build(
    raw: Any,
    *,
    as_of: datetime | date | str | None = None,
    min_dte: int = 30,
) -> dict[str, Any]:
    rows = [row for row in _arr(raw) if isinstance(row, dict)]
    today = _today(as_of)
    positive_dates: set[str] = set()
    side_delta = {"call": 0.0, "put": 0.0, "unknown": 0.0}
    included = 0
    provided_increase_days = 0
    skipped_short_dte = 0
    skipped_undated = 0
    for row in rows:
        dte = _dte(row, today)
        if dte is not None and dte < min_dte:
            skipped_short_dte += 1
            continue
        row_date = _date(_first(row, "curr_date", "date", "as_of", "last_date", "executed_at", "created_at", "updated_at"))
        if row_date is None:
            skipped_undated += 1
            continue
        delta = _oi_delta(row)
        if delta <= 0:
            continue
        included += 1
        positive_dates.add(row_date.isoformat())
        provided_days = _f(_first(row, "days_of_oi_increases", "oi_increase_days"))
        if provided_days is not None:
            provided_increase_days = max(provided_increase_days, int(provided_days))
        side_delta[_option_side(row)] += delta
    dominant_side = max(side_delta, key=lambda key: abs(side_delta[key])) if any(side_delta.values()) else "unknown"
    days = max(len(positive_dates), provided_increase_days)
    return {
        "status": "fetched",
        "endpoint": "get_open_interest_changes",
        "min_dte": min_dte,
        "rows_seen": len(rows),
        "rows_included": included,
        "days_of_oi_increases": days,
        "flagged": days >= 3,
        "dominant_side": dominant_side,
        "positive_dates": sorted(positive_dates),
        "skipped_short_dte": skipped_short_dte,
        "skipped_undated": skipped_undated,
        "summary": f"multi-day OI build: {days} dated increase day(s), min_dte {min_dte}, side {dominant_side}",
    }


def _notional(row: dict[str, Any]) -> float:
    value = _f(_first(row, "premium", "notional", "value"))
    if value is not None:
        return abs(value)
    size = _f(_first(row, "size", "volume", "quantity")) or 0.0
    price = _f(_first(row, "price", "px", "fill_price")) or 0.0
    return abs(size * price)


def _dark_pool_sign(row: dict[str, Any]) -> float:
    rel = _first(row, "above_vwap", "vwap_side")
    if isinstance(rel, bool):
        return 1.0 if rel else -1.0
    if isinstance(rel, str):
        return -1.0 if rel.lower() in ("below", "under", "sell") else 1.0
    price = _f(_first(row, "price", "px", "fill_price"))
    ask = _f(_first(row, "nbbo_ask", "ask"))
    bid = _f(_first(row, "nbbo_bid", "bid"))
    if price is not None and ask is not None and bid is not None:
        return 1.0 if price >= (ask + bid) / 2.0 else -1.0
    return 1.0


def analyze_dark_pool_blocks(
    raw: Any,
    *,
    as_of: datetime | date | str | None = None,
    lookback_days: int = 10,
    min_notional: float = 5_000_000.0,
) -> dict[str, Any]:
    rows = [row for row in _arr(raw) if isinstance(row, dict)]
    today = _today(as_of)
    cutoff = today - timedelta(days=lookback_days)
    blocks: list[dict[str, Any]] = []
    skipped_old = 0
    skipped_small = 0
    skipped_undated = 0
    for row in rows:
        row_date = _date(_first(row, "executed_at", "date", "timestamp", "created_at"))
        if row_date is None:
            skipped_undated += 1
            continue
        if row_date < cutoff or row_date > today:
            skipped_old += 1
            continue
        notional = _notional(row)
        if notional < min_notional:
            skipped_small += 1
            continue
        signed = _dark_pool_sign(row) * notional
        blocks.append({
            "date": row_date.isoformat(),
            "notional": round(notional, 2),
            "signed_notional": round(signed, 2),
            "price": _f(_first(row, "price", "px", "fill_price")),
        })
    net = sum(float(row["signed_notional"]) for row in blocks)
    return {
        "status": "fetched",
        "endpoint": "get_dark_pool_trades",
        "lookback_days": lookback_days,
        "min_notional": min_notional,
        "rows_seen": len(rows),
        "qualifying_blocks": len(blocks),
        "flagged": bool(blocks),
        "total_notional": round(sum(float(row["notional"]) for row in blocks), 2),
        "net_signed_notional": round(net, 2),
        "blocks": blocks[:10],
        "skipped_old": skipped_old,
        "skipped_small": skipped_small,
        "skipped_undated": skipped_undated,
        "summary": (
            f"dark-pool blocks: {len(blocks)} block(s) >= ${min_notional / 1_000_000:.0f}M "
            f"inside {lookback_days}d, net ${net / 1_000_000:.1f}M"
        ),
    }


def _not_checked_lane(name: str, endpoint: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "endpoint": endpoint,
        "status": "not_checked",
        "flagged": False,
        "summary": f"not checked - {reason}",
    }


class UWDeepdiveFetcher:
    """Thin live adapter for --battery; tests use fakes instead."""
    def __init__(self, *, timeout: float = 20.0, retries: int = 1, limit: int = 500) -> None:
        from codex_uw.endpoints import UWEndpoints
        from codex_uw.rest_client import UWRestClient
        self._endpoints = UWEndpoints
        self._client = UWRestClient(timeout=timeout, retries=retries)
        self._limit = limit

    def get_open_interest_changes(self, ticker: str, *, min_dte: int = 30) -> Any:
        return self._client.get_json(
            self._endpoints.TICKER_OI_CHANGE,
            path_params={"ticker": ticker},
            params={"limit": self._limit, "min_dte": min_dte},
        )

    def get_dark_pool_trades(self, ticker: str, *, days: int = 10, min_notional: float = 5_000_000.0) -> Any:
        return self._client.get_json(
            self._endpoints.DARKPOOL_TICKER,
            path_params={"ticker": ticker},
            params={"limit": self._limit, "days": days, "min_notional": int(min_notional)},
        )


def build_evidence_battery(
    ticker: str,
    *,
    fetcher: Any = None,
    oi_raw: Any = None,
    dark_pool_raw: Any = None,
    as_of: datetime | date | str | None = None,
    min_dte: int = 30,
    lookback_days: int = 10,
    min_dark_pool_notional: float = 5_000_000.0,
) -> dict[str, Any]:
    ticker = ticker.upper()
    lanes: list[dict[str, Any]] = []

    if oi_raw is None and fetcher is not None:
        try:
            oi_raw = fetcher.get_open_interest_changes(ticker, min_dte=min_dte)
        except Exception as exc:
            lanes.append(_not_checked_lane(
                "multi_day_oi_build",
                "get_open_interest_changes",
                f"UW OI fetch failed: {str(exc)[:160]}",
            ))
    if oi_raw is None and not any(row.get("name") == "multi_day_oi_build" for row in lanes):
        lanes.append(_not_checked_lane(
            "multi_day_oi_build",
            "get_open_interest_changes",
            "no UW OI response supplied",
        ))
    elif oi_raw is not None:
        lanes.append({"name": "multi_day_oi_build", **analyze_multi_day_oi_build(oi_raw, as_of=as_of, min_dte=min_dte)})

    if dark_pool_raw is None and fetcher is not None:
        try:
            dark_pool_raw = fetcher.get_dark_pool_trades(
                ticker,
                days=lookback_days,
                min_notional=min_dark_pool_notional,
            )
        except Exception as exc:
            lanes.append(_not_checked_lane(
                "dark_pool_blocks",
                "get_dark_pool_trades",
                f"UW dark-pool fetch failed: {str(exc)[:160]}",
            ))
    if dark_pool_raw is None and not any(row.get("name") == "dark_pool_blocks" for row in lanes):
        lanes.append(_not_checked_lane(
            "dark_pool_blocks",
            "get_dark_pool_trades",
            "no UW dark-pool response supplied",
        ))
    elif dark_pool_raw is not None:
        lanes.append({
            "name": "dark_pool_blocks",
            **analyze_dark_pool_blocks(
                dark_pool_raw,
                as_of=as_of,
                lookback_days=lookback_days,
                min_notional=min_dark_pool_notional,
            ),
        })

    counts: dict[str, int] = {}
    for lane in lanes:
        status = str(lane.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return {
        "ticker": ticker,
        "as_of": _today(as_of).isoformat(),
        "source": "deepdive_runner",
        "lanes": lanes,
        "counts": counts,
        "honesty_rule": "Fetched lanes are evidence checks only; not_checked lanes never imply all clear.",
    }


def _battery_markdown(battery: dict[str, Any]) -> list[str]:
    lines = ["", "### UW Evidence Battery", ""]
    for lane in battery.get("lanes") or []:
        flag = " FLAG" if lane.get("flagged") else ""
        lines.append(f"- `{lane.get('name')}`: {lane.get('status')}{flag} - {lane.get('summary')}")
    lines.append("")
    lines.append(f"> {battery.get('honesty_rule')}")
    return lines


def render_markdown(
    ticker: str,
    mode: str = "deepdive",
    tier_a: bool = False,
    post_er: bool = False,
    iv_data: Optional[dict] = None,
    evidence_battery: Optional[dict] = None,
) -> str:
    items = [i for i in CHECKLIST if i.applies(mode, tier_a, post_er)]
    if iv_data:
        items.extend(iv_overlay_items(iv_data.get("ivr"), iv_data.get("atm_iv")))

    titles = {
        "deepdive": f"## 📋 Deepdive Auto-Pull Checklist — {ticker}",
        "tier1":    f"## 📋 Tier 1 Auto-Pull (Two-Lens 3+) — {ticker}",
        "full":     f"## 📋 FULL Auto-Pull (Tier 3 — ≥$50K / Generational) — {ticker}",
    }
    title = titles.get(mode, f"## 📋 Checklist — {ticker}")

    flags = []
    if tier_a:
        flags.append("Tier-A confirmed (earnings transcript auto-fires)")
    if post_er:
        flags.append("Post-earnings ≥1σ flag (earnings transcript auto-fires per v11.8)")
    if iv_data:
        flags.append(f"IV overlay: IVR={iv_data.get('ivr', 'pending')}")

    lines = [title, ""]
    if flags:
        lines.append("**Flags active:** " + " · ".join(flags))
        lines.append("")

    lines.append("| Tier | Item | Endpoint | Status | Notes |")
    lines.append("|---|---|---|:--:|---|")

    for item in items:
        notes = item.notes if item.notes else "—"
        if len(notes) > 90:
            notes = notes[:87] + "..."
        lines.append(f"| `{item.tier}` | {item.label} | `{item.endpoint}` | ⏳ | {notes} |")

    lines.append("")
    lines.append(f"**{len(items)} items.** Status: ⏳ pending · ✅ pulled · ⚠️ partial · ❌ null/error · ⏭️ N/A")
    lines.append("")
    lines.append("> Claude replaces ⏳ with status emoji as each item executes. Surface any ❌ or ⚠️ inline before synthesis. Per P-SIMPLICITY: explicit checklist beats memory-dependent recall.")

    if evidence_battery:
        lines.extend(_battery_markdown(evidence_battery))
    return "\n".join(lines)


def render_json(
    ticker: str,
    mode: str = "deepdive",
    tier_a: bool = False,
    post_er: bool = False,
    iv_data: Optional[dict] = None,
    evidence_battery: Optional[dict] = None,
) -> str:
    items = [i for i in CHECKLIST if i.applies(mode, tier_a, post_er)]
    if iv_data:
        items.extend(iv_overlay_items(iv_data.get("ivr"), iv_data.get("atm_iv")))
    output = {
        "ticker": ticker.upper(),
        "mode": mode,
        "flags": {"tier_a": tier_a, "post_er_1sigma": post_er, "iv_overlay": iv_data is not None},
        "item_count": len(items),
        "items": [asdict(i) for i in items],
    }
    if evidence_battery:
        output["evidence_battery"] = evidence_battery
    return json.dumps(output, indent=2)


def _read_json(path: str | None) -> Any:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def self_test() -> bool:
    failures = []
    for item in CHECKLIST:
        if item.tier == "T1" and not item.applies("deepdive", False, False):
            failures.append(f"T1 {item.label} did not fire in deepdive mode")
        if item.tier == "T1" and not item.applies("tier1", False, False):
            failures.append(f"T1 {item.label} did not fire in tier1 mode")

    transcript = next(i for i in CHECKLIST if "transcript" in i.label.lower())
    if not transcript.applies("deepdive", False, True):
        failures.append("Transcript did not fire with post_er=True")
    if not transcript.applies("deepdive", True, False):
        failures.append("Transcript did not fire with tier_a=True")
    if transcript.applies("deepdive", False, False):
        failures.append("Transcript fired without tier_a or post_er")

    for item in CHECKLIST:
        if item.tier == "T3" and item.applies("deepdive", True, True):
            failures.append(f"T3 {item.label} fired in deepdive mode")
        if item.tier == "T3" and not item.applies("full", False, False):
            failures.append(f"T3 {item.label} did not fire in full mode")

    deepdive_count = len([i for i in CHECKLIST if i.applies("deepdive", False, False)])
    if deepdive_count != 15:
        failures.append(f"Deepdive count {deepdive_count} != expected 15")

    deepdive_a_count = len([i for i in CHECKLIST if i.applies("deepdive", True, False)])
    if deepdive_a_count != 16:
        failures.append(f"Deepdive+tier_a count {deepdive_a_count} != expected 16")

    full_count = len([i for i in CHECKLIST if i.applies("full", True, False)])
    if full_count != 20:
        failures.append(f"Full+tier_a count {full_count} != expected 20")

    if failures:
        print("FAILED self-test:")
        for f in failures:
            print(f"  - {f}")
        return False

    print("PASSED self-test. Checklist contract holds.")
    print(f"  Tier 1: {len([i for i in CHECKLIST if i.tier == 'T1'])} items")
    print(f"  Tier 2: {len([i for i in CHECKLIST if i.tier == 'T2'])} items")
    print(f"  Tier 3: {len([i for i in CHECKLIST if i.tier == 'T3'])} items")
    print(f"  Deepdive (no flags): {deepdive_count} fire")
    print(f"  Deepdive + tier_a: {deepdive_a_count} fire (full T1+T2)")
    print(f"  Full + tier_a: {full_count} fire")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="v11.18 Deepdive auto-pull checklist generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ticker", help="Ticker symbol (e.g., ANET)")
    parser.add_argument("--mode", default="deepdive", choices=["deepdive", "tier1", "full"])
    parser.add_argument("--tier-a", action="store_true", help="Tier A — fires earnings transcript etc")
    parser.add_argument("--post-er", action="store_true", help="Post-earnings ≥1σ — fires transcript per v11.8")
    parser.add_argument("--ivr", type=float, default=None, help="IV Rank 0-100 — activates IV overlay")
    parser.add_argument("--atm-iv", type=float, default=None, help="ATM IV decimal — activates IV overlay")
    parser.add_argument("--battery", action="store_true", help="Attach bounded UW OI/dark-pool evidence battery")
    parser.add_argument("--oi-json", help="Saved get_open_interest_changes response for battery mode")
    parser.add_argument("--dark-pool-json", help="Saved get_dark_pool_trades response for battery mode")
    parser.add_argument("--battery-as-of", help="YYYY-MM-DD date for battery lookback tests/renders")
    parser.add_argument("--timeout", type=float, default=20.0, help="UW timeout for live --battery")
    parser.add_argument("--retries", type=int, default=1, help="UW retries for live --battery")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--self-test", action="store_true", help="Self-test and exit")

    args = parser.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    if not args.ticker:
        parser.error("--ticker is required (or use --self-test)")

    iv_data = None
    if args.ivr is not None or args.atm_iv is not None:
        iv_data = {"ivr": args.ivr, "atm_iv": args.atm_iv}

    battery = None
    if args.battery or args.oi_json or args.dark_pool_json:
        fetcher = None
        if not args.oi_json or not args.dark_pool_json:
            try:
                fetcher = UWDeepdiveFetcher(timeout=args.timeout, retries=args.retries)
            except Exception:
                fetcher = None
        battery = build_evidence_battery(
            args.ticker,
            fetcher=fetcher,
            oi_raw=_read_json(args.oi_json),
            dark_pool_raw=_read_json(args.dark_pool_json),
            as_of=args.battery_as_of,
        )

    if args.json:
        print(render_json(args.ticker, args.mode, args.tier_a, args.post_er, iv_data, evidence_battery=battery))
    else:
        print(render_markdown(args.ticker, args.mode, args.tier_a, args.post_er, iv_data, evidence_battery=battery))


if __name__ == "__main__":
    main()
