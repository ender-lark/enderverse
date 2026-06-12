#!/usr/bin/env python3
"""
open_opportunities.py — E5: the open-opportunity PERSISTENCE store
(the cockpit's memory of un-acted ideas across daily builds).

THE 2.0 SPLIT  (same line as the parabolic / uw_opportunity caches)
-------------------------------------------------------------------
  • WRITER  (the FULL cockpit-build cloud routine): each build it reads the prior
    store, derives today's open opportunities from the feed (the buy_now / lean_in /
    reentry_zone actions for names NOT already held), records new ones with their
    first-flagged date + flag price, refreshes `last_seen` on ones still open, and
    DROPS any that were acted on (now held) or invalidated (stop / thesis / expiry).
    Writes conviction_engine/open_opportunities.json. Pure gather — never decides.
  • READER  (the engine, E2): reads the store to attach age / move-since fields to
    actions and emit the `decision_aging` cue ("FN — flagged 5/28, +12%, day 5").

WHY a persisted store (not the daily uw_opportunity scan): the scan is regenerated
every build and has NO memory. To say "un-acted for 5 days, +12% since the flag"
the cockpit must REMEMBER when each idea first appeared and at what price. That
memory is this file.

THE MONITOR GUARDRAIL  (hard, structural)
-----------------------------------------
Burned / MONITOR-stance sleeves (crypto-ETH, nuclear/uranium, critical-minerals)
are NEVER tracked here. An aging cue is an "act on this" nudge, and burned sleeves
get loud ONLY via the re-entry path (a genuine ≥3-source convergence / named
catalyst / regime turn), never via under-deployment/aging. Both the writer
(`update_open_opportunities`) and the reader (`open_opportunity_aging`) SKIP any
MONITOR ticker even if the caller passes one — so E2 can never age a burned name.
(The engine's action stream already excludes them; this is belt-and-suspenders.)

TOLERANT: malformed rows are skipped, never raised — a bad store degrades to "no
aging", it never poisons the build.

SCHEMA  (open_opportunities.json)
---------------------------------
  {
    "schema_version": "1.0",
    "as_of":        "2026-06-02",            # last build date
    "generated_at": "2026-06-02T10:30:00Z",
    "opportunities": [
      {
        "ticker":        "FN",               # REQUIRED
        "first_flagged": "2026-05-28",       # REQUIRED (ISO date) — when first surfaced
        "flag_price":    580.0,              # price at first flag (null if unknown)
        "source":        "fundstrat_top5",   # who/what surfaced it (free text)
        "kind":          "lean_in",          # the action kind that surfaced it
        "last_seen":     "2026-06-02",       # last build that still saw it open
        "status":        "open"              # open | acted | invalidated (only open persists/emits)
      }
    ]
  }
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone

SCHEMA_VERSION = "1.0"

# Action kinds that represent an OPEN opportunity worth aging (acquire-and-not-yet-held).
# EXCLUDES monitor_reentry (burned — guardrail), catalyst_imminent (held-position review),
# watch_entry (entry not confirmed yet), and the macro / red_gate / stale_critical kinds.
# (FS "act now" lands as buy_now via E3, so it is already covered here.)
TRACKABLE_KINDS = ("buy_now", "lean_in", "reentry_zone")

VALID_STATUS = ("open", "acted", "invalidated", "ignored", "deferred", "missed", "expired", "dropped")
RESOLVED_STATUS = ("acted", "invalidated", "ignored", "deferred", "missed", "expired", "dropped")
REVIEW_DUE_DAYS = 2
REVIEW_STALE_DAYS = 5

# Position statuses (feed holdings `pos[].st`) that count as actually HELD — used to
# detect "acted" (an opportunity that became a position).
OWNED_STATUSES = ("Owned",)


# ───────────────────────── helpers ─────────────────────────

def _parse_date(s):
    """Tolerant ISO-date parse → date | None (accepts datetimes, trims to 10 chars)."""
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def age_business_days(first_flagged, as_of):
    """Trading days (weekdays) elapsed from first_flagged to as_of.

    Same day → 0. Bad / future-flag dates → None. NOTE: weekends excluded; market
    holidays are NOT (a minor over-count around holidays) — refinement backlog.
    """
    d0 = _parse_date(first_flagged)
    d1 = _parse_date(as_of)
    if not d0 or not d1 or d1 < d0:
        return None
    days = 0
    cur = d0
    while cur < d1:
        cur += timedelta(days=1)
        if cur.weekday() < 5:  # Mon–Fri
            days += 1
    return days


def compute_move_since(flag_price, current_price) -> str:
    """'+12% since flag' / '-3% since flag' / '' when either price is missing/bad."""
    try:
        fp = float(flag_price)
        cp = float(current_price)
    except (TypeError, ValueError):
        return ""
    if fp <= 0:
        return ""
    pct = (cp - fp) / fp * 100.0
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.0f}% since flag"


def review_age_state(age_days, *, due_days=REVIEW_DUE_DAYS, stale_days=REVIEW_STALE_DAYS) -> dict:
    """Classify an open action-memory row for backlog cleanup surfaces."""
    try:
        age = int(age_days)
    except (TypeError, ValueError):
        age = 0
    if age >= stale_days:
        return {
            "review_state": "stale",
            "review_label": "stale review",
            "cleanup_priority": "high",
            "stale": True,
            "due": True,
            "next_step": "Resolve now: acted, invalidated, ignored, missed, expired, or explicitly defer.",
        }
    if age >= due_days:
        return {
            "review_state": "review_due",
            "review_label": "review due",
            "cleanup_priority": "medium",
            "stale": False,
            "due": True,
            "next_step": "Review soon: act, invalidate, ignore, or explicitly defer.",
        }
    return {
        "review_state": "new",
        "review_label": "new",
        "cleanup_priority": "low",
        "stale": False,
        "due": False,
        "next_step": "Keep visible; no cleanup pressure yet.",
    }


def _clean_opp(o):
    """Normalize one stored opportunity → canonical dict, or None if unusable."""
    if not isinstance(o, dict):
        return None
    tk = o.get("ticker")
    ff = _parse_date(o.get("first_flagged"))
    if not tk or not ff:
        return None
    st = o.get("status") if o.get("status") in VALID_STATUS else "open"
    last = _parse_date(o.get("last_seen")) or ff
    return {
        "ticker": str(tk),
        "first_flagged": ff.isoformat(),
        "flag_price": o.get("flag_price"),
        "source": o.get("source") or "",
        "kind": o.get("kind") or "",
        "last_seen": last.isoformat(),
        "status": st,
    }


# ───────────────────────── load / save ─────────────────────────

def load_open_opportunities(path) -> dict:
    """Read the store; missing / malformed → an empty, valid store (never raises)."""
    empty = {"schema_version": SCHEMA_VERSION, "opportunities": []}
    if not path or not os.path.exists(path):
        return dict(empty)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    if not isinstance(data.get("opportunities"), list):
        data["opportunities"] = []
    if not isinstance(data.get("history"), list):
        data["history"] = []
    return data


def save_open_opportunities(store, path) -> str:
    with open(path, "w") as fh:
        json.dump(store, fh, indent=2)
    return path


def _resolution_map(resolutions):
    out = {}
    for r in (resolutions or []):
        if isinstance(r, str):
            out[r.upper()] = {"status": "ignored", "reason": "operator ignored"}
        elif isinstance(r, dict) and r.get("ticker"):
            status = r.get("status") if r.get("status") in RESOLVED_STATUS else "ignored"
            out[str(r["ticker"]).upper()] = {
                "status": status,
                "reason": r.get("reason") or status,
            }
    return out


def _history_row(c, *, status, reason, as_of):
    return {
        "ticker": c.get("ticker"),
        "first_flagged": c.get("first_flagged"),
        "last_seen": c.get("last_seen"),
        "resolved_at": as_of,
        "status": status,
        "reason": reason,
        "source": c.get("source") or "",
        "kind": c.get("kind") or "",
        "flag_price": c.get("flag_price"),
    }


# ───────────────────── WRITER side (the routine) ─────────────────────

def _resolved_today_keys(history, today_iso):
    """Return ticker/kind/source keys explicitly resolved today."""
    keys = set()
    for raw in history or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("status") not in RESOLVED_STATUS or not raw.get("ticker"):
            continue
        resolved_at = _parse_date(raw.get("resolved_at")) or _parse_date(raw.get("last_seen"))
        if not resolved_at or resolved_at.isoformat() != today_iso:
            continue
        keys.add((
            str(raw.get("ticker")).upper(),
            str(raw.get("kind") or ""),
            str(raw.get("source") or ""),
        ))
    return keys


def update_open_opportunities(store, todays_candidates, held_tickers, prices, as_of, *,
                              monitor_tickers=None, invalidations=None, resolutions=None,
                              max_age_days=None):
    """Merge today's candidates into the store; age the survivors; drop the resolved.

    Inputs
    ------
    store            : prior store dict (use load_open_opportunities()).
    todays_candidates: [{ticker, kind, source?, price?}] — usually candidates_from_feed(feed).
    held_tickers     : iterable of currently-held tickers (acted-detection).
    prices           : {ticker: price} — current prices (sets flag_price on NEW rows).
    as_of            : ISO date for this build.
    monitor_tickers  : iterable of MONITOR/burned tickers — NEVER tracked (guardrail).
    invalidations    : iterable of tickers explicitly invalidated (stop / thesis break).
    max_age_days     : optional auto-drop after N trading days unacted (default None = never).

    Returns (new_store, dropped) where dropped = [{ticker, status, reason}, …].
    """
    held = {str(t).upper() for t in (held_tickers or set())}
    monitor = {str(t).upper() for t in (monitor_tickers or set())}
    invalid = {str(t).upper() for t in (invalidations or set())}
    resolved = _resolution_map(resolutions)
    prices = prices or {}
    today_iso = (_parse_date(as_of) or date.today()).isoformat()

    kept, dropped, seen = [], [], set()
    history = list((store or {}).get("history") or [])
    resolved_today = _resolved_today_keys(history, today_iso)

    # 1) age / keep / drop existing OPEN opportunities
    for raw in (store or {}).get("opportunities", []) or []:
        c = _clean_opp(raw)
        if not c or c["status"] != "open":
            continue
        up = c["ticker"].upper()
        if up in resolved:
            rr = resolved[up]
            history.append(_history_row(c, status=rr["status"], reason=rr["reason"], as_of=today_iso))
            dropped.append({"ticker": c["ticker"], "status": rr["status"], "reason": rr["reason"]})
            continue
        if up in monitor:
            history.append(_history_row(c, status="dropped", reason="monitor_excluded", as_of=today_iso))
            dropped.append({"ticker": c["ticker"], "status": "dropped", "reason": "monitor_excluded"})
            continue
        if up in held:
            history.append(_history_row(c, status="acted", reason="now held", as_of=today_iso))
            dropped.append({"ticker": c["ticker"], "status": "acted", "reason": "now held"})
            continue
        if up in invalid:
            history.append(_history_row(c, status="invalidated", reason="invalidated", as_of=today_iso))
            dropped.append({"ticker": c["ticker"], "status": "invalidated", "reason": "invalidated"})
            continue
        if max_age_days is not None:
            age = age_business_days(c["first_flagged"], as_of)
            if age is not None and age > max_age_days:
                history.append(_history_row(c, status="expired", reason=f">{max_age_days}d unacted", as_of=today_iso))
                dropped.append({"ticker": c["ticker"], "status": "expired",
                                "reason": f">{max_age_days}d unacted"})
                continue
        c["last_seen"] = today_iso
        kept.append(c)
        seen.add(up)

    # 2) add NEW candidates (acquire kinds, not held, not burned, not already tracked)
    for cand in (todays_candidates or []):
        if not isinstance(cand, dict):
            continue
        tk = cand.get("ticker")
        kind = cand.get("kind")
        if not tk or kind not in TRACKABLE_KINDS:
            continue
        up = str(tk).upper()
        if up in monitor:            # GUARDRAIL: never age a burned sleeve
            continue
        if up in held or up in invalid or up in seen:
            continue
        source = cand.get("source") or kind or ""
        if (up, str(kind or ""), str(source or "")) in resolved_today:
            continue
        price = cand.get("price")
        if price is None:
            price = prices.get(tk)
        kept.append({
            "ticker": str(tk),
            "first_flagged": today_iso,
            "flag_price": price,
            "source": source,
            "kind": kind or "",
            "last_seen": today_iso,
            "status": "open",
        })
        seen.add(up)

    new_store = {
        "schema_version": SCHEMA_VERSION,
        "as_of": today_iso,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "opportunities": kept,
        "history": history,
    }
    return new_store, dropped


def seed_open_opportunities(seeds, as_of=None) -> dict:
    """Build an initial store from known-open names.

    seeds: [{ticker, first_flagged, flag_price?, source?, kind?}]. Rows missing a
    ticker or a valid first_flagged date are skipped. MONITOR/burned names should
    simply not be passed (their loudness comes via the re-entry path, not aging).
    """
    as_of = as_of or date.today().isoformat()
    opps = []
    for s in (seeds or []):
        if not isinstance(s, dict):
            continue
        c = _clean_opp({
            "ticker": s.get("ticker"),
            "first_flagged": s.get("first_flagged"),
            "flag_price": s.get("flag_price"),
            "source": s.get("source"),
            "kind": s.get("kind") or "lean_in",
            "last_seen": s.get("first_flagged"),
            "status": "open",
        })
        if c:
            opps.append(c)
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "opportunities": opps,
        "history": [],
    }


# ───────────────────── READER side (the engine, E2) ─────────────────────

def open_opportunity_aging(store, prices, as_of, *, threshold_days=3, monitor_tickers=None):
    """Aging records for OPEN opportunities at/over the threshold (the E2 source).

    Returns [{ticker, age_days, first_flagged, move_since, source, kind}, …]. E2
    wraps each into a `decision_aging` action row. MONITOR names are excluded here
    too (defensive). Below-threshold / acted / invalidated rows are not emitted.
    """
    monitor = {str(t).upper() for t in (monitor_tickers or set())}
    prices = prices or {}
    out = []
    for raw in (store or {}).get("opportunities", []) or []:
        c = _clean_opp(raw)
        if not c or c["status"] != "open":
            continue
        if c["ticker"].upper() in monitor:
            continue
        age = age_business_days(c["first_flagged"], as_of)
        if age is None or age < threshold_days:
            continue
        out.append({
            "ticker": c["ticker"],
            "age_days": age,
            "first_flagged": c["first_flagged"],
            "move_since": compute_move_since(c["flag_price"], prices.get(c["ticker"])),
            "source": c["source"],
            "kind": c["kind"],
        })
    return out


# ───────────────────── feed adapters (tolerant) ─────────────────────

def held_tickers_from_feed(feed) -> set:
    """Set of tickers actually held (pos.st in OWNED_STATUSES) across holdings groups."""
    held = set()
    for grp in (feed or {}).get("holdings", []) or []:
        if not isinstance(grp, dict):
            continue
        for p in grp.get("pos", []) or []:
            if isinstance(p, dict) and p.get("t") and p.get("st") in OWNED_STATUSES:
                held.add(p["t"])
    return held


def candidates_from_feed(feed) -> list:
    """Today's trackable open-opportunity candidates from the feed's `actions`."""
    out = []
    for a in (feed or {}).get("actions", []) or []:
        if not isinstance(a, dict):
            continue
        k = a.get("kind")
        tk = a.get("ticker")
        if k in TRACKABLE_KINDS and tk:
            out.append({"ticker": tk, "kind": k, "source": a.get("source") or k, "price": None})
    return out


# ───────────────────── smoke selftest ─────────────────────

def _selftest() -> int:
    today = "2026-06-02"
    store = seed_open_opportunities(
        [{"ticker": "FN", "first_flagged": "2026-05-28", "flag_price": 580.0, "source": "fundstrat_top5"}],
        as_of=today,
    )
    assert store["opportunities"][0]["ticker"] == "FN"
    # FN flagged Thu 5/28 → Tue 6/2 = 3 trading days
    assert age_business_days("2026-05-28", today) == 3, age_business_days("2026-05-28", today)
    aging = open_opportunity_aging(store, {"FN": 650.0}, today, threshold_days=3)
    assert aging and aging[0]["age_days"] == 3 and aging[0]["move_since"] == "+12% since flag", aging
    # guardrail: a MONITOR candidate is never tracked
    ns, _ = update_open_opportunities(store, [{"ticker": "LEU", "kind": "lean_in"}],
                                      held_tickers=set(), prices={}, as_of=today,
                                      monitor_tickers={"LEU"})
    assert all(o["ticker"] != "LEU" for o in ns["opportunities"]), "MONITOR leaked into store"
    # acted: FN now held → dropped
    ns2, dropped = update_open_opportunities(store, [], held_tickers={"FN"}, prices={}, as_of=today)
    assert all(o["ticker"] != "FN" for o in ns2["opportunities"]) and dropped[0]["status"] == "acted"
    print("SELFTEST PASS — seed/age/move/guardrail/acted OK")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
