"""Publish gate — the L5 -> L3 write contract for the cockpit feed.

Contract-C (validators.validate_cockpit_feed) proves the feed is STRUCTURALLY
valid. It does NOT prove the feed is SAFE TO PUBLISH AS CURRENT — that takes two
more checks that the 6/1 bugs slipped past while Contract-C stayed green:

  1. the build stamp is REAL (generated_at agrees with the live-source clock),
     not a canned value;  [6/1: generated_at 10:10 vs real run 17:48]
  2. labeled macro levels are PLAUSIBLE (a ~$28 value under the "DXY" label is a
     mislabeled proxy, not the dollar index).  [6/1: "DXY 27.76" = UUP's price]

This module is the cockpit feed-build routine's pre-publish gate: run it, and if
it returns problems, ABORT the publish (leave the prior good feed). The live
session can run it on read too. Policy thresholds live HERE (tunable), kept out
of the structural validator on purpose — they are the publish *policy*, not the
Contract-C shape. Pure logic; the only engine import is the structural validator.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

try:  # flat import inside conviction_engine/ (house convention)
    from validators import validate_cockpit_feed
except ImportError:  # pragma: no cover - package-style import fallback
    from conviction_engine.validators import validate_cockpit_feed

# ── Publish policy (tunable — this is the L5->L3 contract, not Contract-C) ─────
STAMP_TOLERANCE_HOURS = 2.0
# Plausibility bands for labeled levels parsed out of the macro `line` string.
# An absent level is fine (it drops gracefully); only a PRESENT, out-of-band
# value flags — that is the mislabeled-proxy signature.
MACRO_BANDS: dict[str, tuple[float, float]] = {
    "DXY": (90.0, 115.0),
    # The dollar slot now renders as "USD (UUP)" (uw_macro._LEVEL_DISPLAY) — UUP
    # the ETF (~$28), not the DXY index. Band it so a ~99 (a re-mislabeled DXY)
    # or a ~0 glitch still flags. Label string must match _LEVEL_DISPLAY exactly.
    "USD (UUP)": (20.0, 40.0),
    "VIX": (5.0, 90.0),
    "10Y": (0.0, 10.0),
    "30Y": (0.0, 10.0),
    "2Y": (0.0, 10.0),
}


def _parse_dt(s: Any) -> "datetime | None":
    """Parse an ISO-ish datetime to aware UTC, or None if not a datetime."""
    if not isinstance(s, str) or "T" not in s:
        return None
    txt = s.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _staleness_now(feed: dict) -> "datetime | None":
    """The real build clock: the most-recent full-datetime staleness entry.
    The live-sourced rows (portfolio / uw_price / uw_macro) carry datetime.now();
    date-only rows (e.g. fundstrat_daily '2026-05-29') are ignored here."""
    stale = feed.get("staleness")
    if not isinstance(stale, dict):
        return None
    cands = []
    for e in stale.get("entries", []) or []:
        if isinstance(e, dict):
            dt = _parse_dt(e.get("date"))
            if dt is not None:
                cands.append(dt)
    return max(cands) if cands else None


def _check_stamp(feed: dict) -> list[str]:
    """generated_at must agree with the live-source clock within tolerance."""
    problems: list[str] = []
    ga = _parse_dt(feed.get("generated_at"))
    if ga is None:
        # validate_cockpit_feed already owns "missing/empty". Only flag here if
        # it is present-but-unparseable as a datetime.
        raw = feed.get("generated_at")
        if isinstance(raw, str) and "T" in raw:
            problems.append(f"generated_at present but not a parseable datetime: {raw!r}")
        return problems
    now_ref = _staleness_now(feed)
    if now_ref is None:
        problems.append(
            "cannot verify stamp: no datetime staleness entry to compare generated_at against"
        )
        return problems
    gap_h = abs((ga - now_ref).total_seconds()) / 3600.0
    if gap_h > STAMP_TOLERANCE_HOURS:
        problems.append(
            f"stamp not from the clock: generated_at {ga.isoformat()} vs live-source "
            f"now {now_ref.isoformat()} differ by {gap_h:.1f}h (> {STAMP_TOLERANCE_HOURS}h tolerance)"
        )
    return problems


# label -> regex capturing its leading signed number in the macro line
_LEVEL_RE: dict[str, "re.Pattern[str]"] = {
    lbl: re.compile(rf"\b{re.escape(lbl)}\s+([+-]?\d+(?:\.\d+)?)")
    for lbl in MACRO_BANDS
}


def _check_macro(feed: dict) -> list[str]:
    """Each PRESENT labeled level in macro.line must sit in its plausible band."""
    problems: list[str] = []
    macro = feed.get("macro")
    if not isinstance(macro, dict):
        return problems  # validate_cockpit_feed owns "macro must be a dict"
    line = macro.get("line")
    if not isinstance(line, str) or not line:
        return problems
    for lbl, (lo, hi) in MACRO_BANDS.items():
        m = _LEVEL_RE[lbl].search(line)
        if not m:
            continue  # absent level drops gracefully
        val = float(m.group(1))
        if not (lo <= val <= hi):
            problems.append(
                f"macro {lbl} implausible: {val} outside [{lo}, {hi}] "
                f"(likely a mislabeled proxy) in line: {line!r}"
            )
    return problems


def validate_publish_gate(feed: Any) -> list[str]:
    """The L5 -> L3 publish contract. Empty list == safe to publish.

    Layers three checks, in order:
      (1) Contract-C structure  — reused from validators.validate_cockpit_feed
      (2) real-clock stamp       — generated_at agrees with the live-source now()
      (3) macro plausibility     — labeled levels inside their bands

    Does NOT raise. The caller (the feed-build routine) decides: ABORT the
    publish on a non-empty result and leave the prior good feed in place.
    """
    if not isinstance(feed, dict):
        return [f"feed must be a dict, got {type(feed).__name__}"]
    problems = list(validate_cockpit_feed(feed))  # structural first
    problems += _check_stamp(feed)
    problems += _check_macro(feed)
    return problems


def is_valid_publish_gate(feed: Any) -> bool:
    return not validate_publish_gate(feed)


def assert_valid_publish_gate(feed: Any) -> None:
    problems = validate_publish_gate(feed)
    if problems:
        raise ValueError(
            "feed failed publish gate (do NOT publish): " + "; ".join(problems)
        )
