"""Conviction Engine — contract validators (the seam guards).

S1: `validate_source_item` — Contract A (Sources -> Collection).

A contract validator is a tiny schema check at a seam so a component can't
SILENTLY hand the next one a wrong shape. Run it over `registry.fetch_all()`
output and a malformed plug fails LOUDLY, right at the boundary, instead of a
bad fact-card slipping downstream and corrupting an Analyst read.

Hard contract (per Build Plan P2):
    non-empty  source / kind / subject / timestamp ;  trust_weight in 0..1.
Plus structural shape checks (the other SourceItem fields present + typed) so a
genuinely broken row is caught, not just an empty string.

Duck-typed on purpose: validates a `SourceItem` dataclass OR a plain dict with
the same fields, so it can guard raw rows in tests too. Pure-logic, no imports
from the rest of the engine.
"""
from __future__ import annotations

from numbers import Real
from typing import Any

# Sentinel distinct from a legitimately-present None value.
_MISSING = object()

# The four fields the hard contract requires to be NON-EMPTY strings.
_REQUIRED_NONEMPTY_STR = ("source", "kind", "subject", "timestamp")


def _get(item: Any, name: str) -> Any:
    """Field access that works for both a dict and a dataclass/object."""
    if isinstance(item, dict):
        return item.get(name, _MISSING)
    return getattr(item, name, _MISSING)


def validate_source_item(item: Any) -> list[str]:
    """Return a list of problems with `item` as a SourceItem.

    Empty list == valid. This function does NOT raise — the caller decides
    (see `assert_valid_source_item`). Returning every problem (not just the
    first) makes a malformed plug fully diagnosable at the seam.
    """
    problems: list[str] = []

    # --- hard contract: four non-empty strings ---
    for fld in _REQUIRED_NONEMPTY_STR:
        val = _get(item, fld)
        if val is _MISSING:
            problems.append(f"missing field: {fld}")
        elif not isinstance(val, str):
            problems.append(f"{fld} must be a string, got {type(val).__name__}")
        elif val.strip() == "":
            problems.append(f"{fld} must be non-empty")

    # --- hard contract: trust_weight is a real number in [0, 1] ---
    tw = _get(item, "trust_weight")
    if tw is _MISSING:
        problems.append("missing field: trust_weight")
    elif isinstance(tw, bool) or not isinstance(tw, Real):
        # bool is a subclass of int — reject it explicitly (True/False is not a weight)
        problems.append(f"trust_weight must be a number, got {type(tw).__name__}")
    elif not (0.0 <= float(tw) <= 1.0):
        problems.append(f"trust_weight must be in [0, 1], got {tw}")

    # --- structural shape: independence_group present, non-empty string ---
    grp = _get(item, "independence_group")
    if grp is _MISSING:
        problems.append("missing field: independence_group")
    elif not isinstance(grp, str) or grp.strip() == "":
        problems.append("independence_group must be a non-empty string")

    # --- structural shape: content present + a string (MAY be empty) ---
    content = _get(item, "content")
    if content is _MISSING:
        problems.append("missing field: content")
    elif not isinstance(content, str):
        problems.append(f"content must be a string, got {type(content).__name__}")

    # --- structural shape: data present + a dict ---
    data = _get(item, "data")
    if data is _MISSING:
        problems.append("missing field: data")
    elif not isinstance(data, dict):
        problems.append(f"data must be a dict, got {type(data).__name__}")

    return problems


def is_valid_source_item(item: Any) -> bool:
    """True iff `item` satisfies the Contract-A shape."""
    return not validate_source_item(item)


def assert_valid_source_item(item: Any) -> None:
    """Raise ValueError (listing every problem) if `item` is malformed.
    Use this where a wrong shape should hard-stop the run."""
    problems = validate_source_item(item)
    if problems:
        raise ValueError("invalid SourceItem: " + "; ".join(problems))


def validate_items(items: Any) -> dict:
    """Validate a whole `fetch_all()` haul.

    Returns {"total": N, "ok": M, "bad": [(index, [problems]), ...]} so a single
    malformed plug surfaces loudly (with its index) without discarding the rest.
    """
    bad: list[tuple[int, list[str]]] = []
    ok = 0
    total = 0
    for i, it in enumerate(items):
        total += 1
        probs = validate_source_item(it)
        if probs:
            bad.append((i, probs))
        else:
            ok += 1
    return {"total": total, "ok": ok, "bad": bad}


# ---------------------------------------------------------------------------
# Contract B — CollectedSnapshot (Collection -> Analyst).  (C1)
# ---------------------------------------------------------------------------
_SNAPSHOT_REQUIRED_STR = ("run_id", "run_timestamp")


def validate_collected_snapshot(snap: Any) -> list[str]:
    """Return a list of problems with `snap` as a CollectedSnapshot (Contract B).

    Empty list == valid. Checks the snapshot SHAPE — required ids, items are
    valid SourceItems, sources_ok / sources_failed / staleness / critical_missing
    well-typed. (Cross-field consistency — does sources_ok match the items? — is
    the runner's job and is covered by the C2/C3 runner tests, not here.)
    """
    problems: list[str] = []

    for fld in _SNAPSHOT_REQUIRED_STR:
        val = _get(snap, fld)
        if val is _MISSING:
            problems.append(f"missing field: {fld}")
        elif not isinstance(val, str):
            problems.append(f"{fld} must be a string, got {type(val).__name__}")
        elif val.strip() == "":
            problems.append(f"{fld} must be non-empty")

    items = _get(snap, "items")
    if items is _MISSING:
        problems.append("missing field: items")
    elif not isinstance(items, list):
        problems.append(f"items must be a list, got {type(items).__name__}")
    else:
        for i, it in enumerate(items):
            ip = validate_source_item(it)
            if ip:
                problems.append(f"items[{i}] invalid SourceItem: " + "; ".join(ip))

    ok = _get(snap, "sources_ok")
    if ok is _MISSING:
        problems.append("missing field: sources_ok")
    elif not isinstance(ok, list) or not all(isinstance(s, str) for s in ok):
        problems.append("sources_ok must be a list of strings")

    failed = _get(snap, "sources_failed")
    if failed is _MISSING:
        problems.append("missing field: sources_failed")
    elif not isinstance(failed, list):
        problems.append("sources_failed must be a list")
    else:
        for i, f in enumerate(failed):
            if not isinstance(f, dict) or "name" not in f or "error" not in f:
                problems.append(
                    f"sources_failed[{i}] must be a dict with 'name' and 'error'")

    staleness = _get(snap, "staleness")
    if staleness is _MISSING:
        problems.append("missing field: staleness")
    elif not isinstance(staleness, dict):
        problems.append(f"staleness must be a dict, got {type(staleness).__name__}")

    cm = _get(snap, "critical_missing")
    if cm is _MISSING:
        problems.append("missing field: critical_missing")
    elif not isinstance(cm, list) or not all(isinstance(s, str) for s in cm):
        problems.append("critical_missing must be a list of strings")

    return problems


def is_valid_collected_snapshot(snap: Any) -> bool:
    return not validate_collected_snapshot(snap)


def assert_valid_collected_snapshot(snap: Any) -> None:
    problems = validate_collected_snapshot(snap)
    if problems:
        raise ValueError("invalid CollectedSnapshot: " + "; ".join(problems))


# =========================================================================== #
# Contract C — CockpitFeed (Analyst → Cockpit)
# =========================================================================== #
# The Analyst-EMITTED shape (the feed-assembler maps each read's own field names
# — type_read's type/why/break, ⑦'s ticker/urgency — into this canonical shape;
# the cockpit's raw v4 const names (t/urg, and pos without lock/fresh) are a K1
# display reconciliation). Checks SHAPE only; cross-field consistency (does a
# `fresh` flag match a held name?) is the assembler's job, not here.
_FEED_REQUIRED_DICT = ("staleness", "hero", "macro")
_FEED_REQUIRED_LIST = ("fresh_signals", "holdings", "rotation")
_FEED_OPTIONAL_LIST = ("catalysts", "questions")
# canonical per-position field set (Contract C)
_POS_REQUIRED = ("t", "n", "pct", "st", "cv", "ty", "own",
                 "lock", "fresh", "cd", "cdNote", "nr", "dr", "be")
_FRESH_REQUIRED = ("ticker", "urgency", "what", "why")
_VALID_URGENCY = {"act", "watch"}
# canonical action-row field set (Contract C, OPTIONAL block — like catalysts):
# validated only IF `actions` is present, so feeds that predate the block stay
# valid (forward-compatible). The assembler emits it; old/stored feeds may not.
_ACTION_REQUIRED = ("rank", "kind", "ticker", "what", "confidence", "your_move",
                    "gate", "source", "why", "goal_channels", "goal_impact",
                    "goal_score", "time_window", "capital_effect", "action_label",
                    "why_it_moves_goal", "missing_evidence")
_VALID_CONFIDENCE = {"High", "Moderate", "Low"}
_VALID_ACTION_KINDS = {"buy_now", "reentry_zone", "monitor_reentry", "red_gate",
                       "macro_alert", "watch_entry", "stale_critical", "synthesis",
                       "catalyst_imminent", "lean_in", "research_review",
                       "research_act_now", "decision_aging", "top_prospect", "sell_fast"}
_VALID_ACTION_STATES = {"ACT_NOW", "WATCH", "RESEARCH", "MONITOR"}
_VALID_GOAL_CHANNELS = {"upside", "downside_protection", "sizing_gap", "leverage",
                        "conviction", "opportunity_cost", "data_quality"}
_VALID_GOAL_IMPACTS = {"High", "Medium", "Low"}
_VALID_TIME_WINDOWS = {"today", "1-3 trading days", "1-2 weeks", "no timing edge"}
_VALID_CAPITAL_EFFECTS = {"start", "add", "trim", "sell", "hedge", "rotate",
                          "review", "no_capital_yet"}
# canonical catalyst-row field set (Contract C, OPTIONAL block — the near-term
# event lane read off the Catalyst Calendar). Validated only IF present, so a
# dark/unsourced lane (empty or absent) stays valid.
_CATALYST_REQUIRED = ("ticker", "label", "date", "days_out", "source")
# heartbeat entry (Contract C, OPTIONAL block — the layer run-status strip)
_HEARTBEAT_REQUIRED = ("layer", "status")
_VALID_HEARTBEAT_STATUS = {"ok", "stale", "down"}
_VALID_LANE_STATUS = {"has_data", "checked_clear", "not_checked", "stale", "failed"}
_VALID_FEEDBACK_STATUS = {"has_data", "checked_clear", "not_checked"}
# canonical lean-in-row field set (Contract C, OPTIONAL block ⑩ — the lean-in
# opportunity lane). Validated only IF present (forward-compatible). Only the
# ticker is required; the read fields may vary. Two HARD invariants are checked:
# `lean` (if present) is a known symmetric word, and `action` (if present) is
# "NONE" — the lane is a surface, never an order (no auto-buy, by contract).
_VALID_LEAN = {"lean_in", "build", "still_lagging", "cooling"}
_LEAN_ACTION = "NONE"


def _validate_pos(p: Any) -> list[str]:
    if not isinstance(p, dict):
        return ["must be a dict"]
    out: list[str] = [f"missing pos field: {k}" for k in _POS_REQUIRED if k not in p]
    t = p.get("t")
    if "t" in p and (not isinstance(t, str) or t.strip() == ""):
        out.append("t (ticker) must be a non-empty string")
    for k in ("cv", "cd", "nr"):
        if k in p and not isinstance(p.get(k), str):
            out.append(f"{k} must be a string")
    pct = p.get("pct")
    if "pct" in p and pct is not None and not isinstance(pct, (int, float)):
        out.append("pct must be a number or None")
    return out


def _validate_fresh_signal(s: Any) -> list[str]:
    if not isinstance(s, dict):
        return ["must be a dict"]
    out: list[str] = [f"missing field: {k}" for k in _FRESH_REQUIRED if k not in s]
    if "urgency" in s and s.get("urgency") not in _VALID_URGENCY:
        out.append(f"urgency must be one of {sorted(_VALID_URGENCY)}, got {s.get('urgency')!r}")
    tk = s.get("ticker")
    if "ticker" in s and (not isinstance(tk, str) or tk.strip() == ""):
        out.append("ticker must be a non-empty string")
    return out


def _validate_action(a: Any) -> list[str]:
    """One `actions` row (Contract C, optional block). ticker MAY be None (a
    market-wide action like a macro alert); gate MAY be None (no capital action
    implied). Confidence is the operator-facing read, not a tier letter."""
    if not isinstance(a, dict):
        return ["must be a dict"]
    out: list[str] = [f"missing field: {k}" for k in _ACTION_REQUIRED if k not in a]
    if "confidence" in a and a.get("confidence") not in _VALID_CONFIDENCE:
        out.append(f"confidence must be one of {sorted(_VALID_CONFIDENCE)}, "
                   f"got {a.get('confidence')!r}")
    if "kind" in a and a.get("kind") not in _VALID_ACTION_KINDS:
        out.append(f"kind must be a known action kind, got {a.get('kind')!r}")
    if "action_state" in a and a.get("action_state") not in _VALID_ACTION_STATES:
        out.append(f"action_state must be one of {sorted(_VALID_ACTION_STATES)}, "
                   f"got {a.get('action_state')!r}")
    channels = a.get("goal_channels")
    if "goal_channels" in a:
        if not isinstance(channels, list) or not all(isinstance(c, str) for c in channels):
            out.append("goal_channels must be a list of strings")
        else:
            bad = [c for c in channels if c not in _VALID_GOAL_CHANNELS]
            if bad:
                out.append(f"goal_channels has unknown value(s): {bad!r}")
    if "goal_impact" in a and a.get("goal_impact") not in _VALID_GOAL_IMPACTS:
        out.append(f"goal_impact must be one of {sorted(_VALID_GOAL_IMPACTS)}, "
                   f"got {a.get('goal_impact')!r}")
    if "goal_score" in a:
        score = a.get("goal_score")
        if not isinstance(score, int) or score < 0 or score > 100:
            out.append("goal_score must be an int from 0 to 100")
    if "time_window" in a and a.get("time_window") not in _VALID_TIME_WINDOWS:
        out.append(f"time_window must be one of {sorted(_VALID_TIME_WINDOWS)}, "
                   f"got {a.get('time_window')!r}")
    if "capital_effect" in a and a.get("capital_effect") not in _VALID_CAPITAL_EFFECTS:
        out.append(f"capital_effect must be one of {sorted(_VALID_CAPITAL_EFFECTS)}, "
                   f"got {a.get('capital_effect')!r}")
    for fld in ("action_label", "why_it_moves_goal"):
        if fld in a and (not isinstance(a.get(fld), str) or not a.get(fld).strip()):
            out.append(f"{fld} must be a non-empty string")
    if "missing_evidence" in a:
        me = a.get("missing_evidence")
        if not isinstance(me, list) or not all(isinstance(x, str) for x in me):
            out.append("missing_evidence must be a list of strings")
    if "rank" in a and not isinstance(a.get("rank"), int):
        out.append("rank must be an int")
    tk = a.get("ticker")
    if "ticker" in a and tk is not None and (not isinstance(tk, str) or tk.strip() == ""):
        out.append("ticker must be a non-empty string or None")
    g = a.get("gate")
    if "gate" in a and g is not None and not isinstance(g, dict):
        out.append("gate must be a dict or None")
    return out


def _validate_catalyst(c: Any) -> list[str]:
    """One `catalysts` row (Contract C, optional block — the near-term event lane
    read off the Catalyst Calendar). Shape: ticker/label/date/days_out/source.
    `date` is an ISO string (shape only — not parsed here); `days_out` is an int
    (days from the build's now to the event)."""
    if not isinstance(c, dict):
        return ["must be a dict"]
    out: list[str] = [f"missing field: {k}" for k in _CATALYST_REQUIRED if k not in c]
    for k in ("ticker", "label", "date", "source"):
        v = c.get(k)
        if k in c and (not isinstance(v, str) or v.strip() == ""):
            out.append(f"{k} must be a non-empty string")
    if "days_out" in c and not isinstance(c.get("days_out"), int):
        out.append("days_out must be an int")
    return out


def _validate_heartbeat_entry(h: Any) -> list[str]:
    """One `heartbeat` row (Contract C, optional block — the layer run-status
    strip). last_run/note are optional; status is the traffic-light."""
    if not isinstance(h, dict):
        return ["must be a dict"]
    out: list[str] = [f"missing field: {k}" for k in _HEARTBEAT_REQUIRED if k not in h]
    layer = h.get("layer")
    if "layer" in h and (not isinstance(layer, str) or layer.strip() == ""):
        out.append("layer must be a non-empty string")
    if "status" in h and h.get("status") not in _VALID_HEARTBEAT_STATUS:
        out.append(f"status must be one of {sorted(_VALID_HEARTBEAT_STATUS)}, "
                   f"got {h.get('status')!r}")
    return out


def _validate_lane_status_row(r: Any) -> list[str]:
    """One dark-lane-honesty row. Status is explicit so omitted lanes cannot be
    confused with checked-clear lanes."""
    if not isinstance(r, dict):
        return ["must be a dict"]
    out: list[str] = []
    for key in ("key", "label", "status", "detail", "checked_at"):
        if key not in r:
            out.append(f"missing field: {key}")
        elif not isinstance(r.get(key), str):
            out.append(f"{key} must be a string")
    if "status" in r and r.get("status") not in _VALID_LANE_STATUS:
        out.append(f"status must be one of {sorted(_VALID_LANE_STATUS)}, "
                   f"got {r.get('status')!r}")
    if "count" not in r:
        out.append("missing field: count")
    elif not isinstance(r.get("count"), int) or r.get("count") < 0:
        out.append("count must be a non-negative int")
    return out


def _validate_feedback_block(fb: Any) -> list[str]:
    if not isinstance(fb, dict):
        return [f"must be a dict, got {type(fb).__name__}"]
    out: list[str] = []
    for key in ("source_calls", "open_actions"):
        block = fb.get(key)
        if not isinstance(block, dict):
            out.append(f"{key} must be a dict")
            continue
        status = block.get("status")
        if status not in _VALID_FEEDBACK_STATUS:
            out.append(f"{key}.status must be one of {sorted(_VALID_FEEDBACK_STATUS)}, got {status!r}")
        line = block.get("line")
        if not isinstance(line, str) or not line.strip():
            out.append(f"{key}.line must be a non-empty string")
    recs = fb.get("recommendations")
    if not isinstance(recs, list) or not all(isinstance(r, str) for r in recs):
        out.append("recommendations must be a list of strings")
    return out


def _validate_radar_row(r: Any) -> list[str]:
    """One `radar` row (Contract C, optional block — the endorsed-but-not-owned
    watch lane). A dict carrying at least a non-empty `ticker`; the level fields
    (author/direction/entry/stop/target/window/date/quote) MAY be absent or None
    (a bare long call needn't name levels), so only `ticker` is enforced."""
    if not isinstance(r, dict):
        return ["must be a dict"]
    tk = r.get("ticker")
    if not isinstance(tk, str) or tk.strip() == "":
        return ["ticker must be a non-empty string"]
    return []

#----------------------------------------------------------------------
def _validate_lean_in_row(r: Any) -> list[str]:
    """One `lean_in` row (Contract C, optional block ⑩ — the opportunity lane,
    the mirror of risk surfacing). A dict with a non-empty `ticker`. The read
    fields are flexible, but two invariants are enforced WHEN present: `lean` is
    a known symmetric word, and `action` is "NONE" — the lane surfaces, it never
    emits an order (the no-auto-buy guard, enforced at the contract)."""
    if not isinstance(r, dict):
        return ["must be a dict"]
    out: list[str] = []
    tk = r.get("ticker")
    if not isinstance(tk, str) or tk.strip() == "":
        out.append("ticker must be a non-empty string")
    if "lean" in r and r.get("lean") not in _VALID_LEAN:
        out.append(f"lean must be one of {sorted(_VALID_LEAN)}, got {r.get('lean')!r}")
    if "action" in r and r.get("action") != _LEAN_ACTION:
        out.append(f"action must be {_LEAN_ACTION!r} (lean-in never auto-buys), "
                   f"got {r.get('action')!r}")
    if "caveats" in r and not isinstance(r.get("caveats"), list):
        out.append("caveats must be a list")
    return out


def validate_cockpit_feed(feed: Any) -> list[str]:
    """Return a list of problems with `feed` as a CockpitFeed (Contract C).

    Empty list == valid. Required top-level blocks (generated_at, staleness,
    hero, fresh_signals, holdings, rotation, macro; catalysts/questions/research
    optional), each holding's pos objects carry the full canonical per-name field
    set, fresh_signals carry ticker/urgency/what/why. Does NOT raise.
    """
    if not isinstance(feed, dict):
        return [f"feed must be a dict, got {type(feed).__name__}"]
    problems: list[str] = []

    ga = feed.get("generated_at", _MISSING)
    if ga is _MISSING:
        problems.append("missing field: generated_at")
    elif not isinstance(ga, str) or ga.strip() == "":
        problems.append("generated_at must be a non-empty string")

    for fld in _FEED_REQUIRED_DICT:
        v = feed.get(fld, _MISSING)
        if v is _MISSING:
            problems.append(f"missing field: {fld}")
        elif not isinstance(v, dict):
            problems.append(f"{fld} must be a dict, got {type(v).__name__}")

    for fld in _FEED_REQUIRED_LIST:
        v = feed.get(fld, _MISSING)
        if v is _MISSING:
            problems.append(f"missing field: {fld}")
        elif not isinstance(v, list):
            problems.append(f"{fld} must be a list, got {type(v).__name__}")

    for fld in _FEED_OPTIONAL_LIST:
        v = feed.get(fld, _MISSING)
        if v is not _MISSING and not isinstance(v, list):
            problems.append(f"{fld} must be a list, got {type(v).__name__}")

    research = feed.get("research", _MISSING)
    if research is not _MISSING and not isinstance(research, (dict, list)):
        problems.append(f"research must be a dict or list, got {type(research).__name__}")

    holdings = feed.get("holdings", _MISSING)
    if isinstance(holdings, list):
        for i, h in enumerate(holdings):
            if not isinstance(h, dict):
                problems.append(f"holdings[{i}] must be a dict")
                continue
            if not isinstance(h.get("cat"), str) or not h.get("cat"):
                problems.append(f"holdings[{i}] missing non-empty 'cat'")
            pos = h.get("pos", _MISSING)
            if pos is _MISSING:
                problems.append(f"holdings[{i}] missing 'pos'")
            elif not isinstance(pos, list):
                problems.append(f"holdings[{i}].pos must be a list, got {type(pos).__name__}")
            else:
                for j, p in enumerate(pos):
                    problems.extend(f"holdings[{i}].pos[{j}] {e}" for e in _validate_pos(p))

    fresh = feed.get("fresh_signals", _MISSING)
    if isinstance(fresh, list):
        for i, s in enumerate(fresh):
            problems.extend(f"fresh_signals[{i}] {e}" for e in _validate_fresh_signal(s))

    # OPTIONAL `actions` block (the Top-5 surface). Validated IF present so feeds
    # that predate it still pass; the assembler emits it for all fresh feeds.
    actions = feed.get("actions", _MISSING)
    if actions is not _MISSING:
        if not isinstance(actions, list):
            problems.append(f"actions must be a list, got {type(actions).__name__}")
        else:
            for i, a in enumerate(actions):
                problems.extend(f"actions[{i}] {e}" for e in _validate_action(a))

    # OPTIONAL `research_actions` block (the SEPARATE "From Research" surface —
    # ticker-specific Research-Queue items as candidate-actions, deduped against
    # the action + catalyst lanes). Rows reuse the action-row shape; validated IF
    # present so feeds that predate it stay valid (forward-compatible).
    research_actions = feed.get("research_actions", _MISSING)
    if research_actions is not _MISSING:
        if not isinstance(research_actions, list):
            problems.append(f"research_actions must be a list, got {type(research_actions).__name__}")
        else:
            for i, a in enumerate(research_actions):
                problems.extend(f"research_actions[{i}] {e}" for e in _validate_action(a))

    # OPTIONAL `catalysts` block (near-term event lane, read off the Catalyst
    # Calendar). The KEY is shape-checked as a list above (_FEED_OPTIONAL_LIST);
    # here we validate each ROW IF present. Empty/absent stays valid (a dark,
    # unsourced lane) — so "no catalysts" never looks falsely "checked".
    catalysts = feed.get("catalysts", _MISSING)
    if isinstance(catalysts, list):
        for i, c in enumerate(catalysts):
            problems.extend(f"catalysts[{i}] {e}" for e in _validate_catalyst(c))

    # OPTIONAL `heartbeat` (layer run-status strip) + `synthesis` (state-of-play).
    # Validated IF present so feeds that predate them still pass.
    heartbeat = feed.get("heartbeat", _MISSING)
    if heartbeat is not _MISSING:
        if not isinstance(heartbeat, list):
            problems.append(f"heartbeat must be a list, got {type(heartbeat).__name__}")
        else:
            for i, h in enumerate(heartbeat):
                problems.extend(f"heartbeat[{i}] {e}" for e in _validate_heartbeat_entry(h))

    synthesis = feed.get("synthesis", _MISSING)
    if synthesis is not _MISSING and not isinstance(synthesis, dict):
        problems.append(f"synthesis must be a dict, got {type(synthesis).__name__}")

    lane_status = feed.get("lane_status", _MISSING)
    if lane_status is not _MISSING:
        if not isinstance(lane_status, dict):
            problems.append(f"lane_status must be a dict, got {type(lane_status).__name__}")
        else:
            rows = lane_status.get("rows", _MISSING)
            if rows is _MISSING:
                problems.append("lane_status missing field: rows")
            elif not isinstance(rows, list):
                problems.append(f"lane_status.rows must be a list, got {type(rows).__name__}")
            else:
                for i, row in enumerate(rows):
                    problems.extend(f"lane_status.rows[{i}] {e}" for e in _validate_lane_status_row(row))
            counts = lane_status.get("counts", _MISSING)
            if counts is _MISSING:
                problems.append("lane_status missing field: counts")
            elif not isinstance(counts, dict):
                problems.append(f"lane_status.counts must be a dict, got {type(counts).__name__}")
            for flag in ("has_dark_lanes", "has_stale_or_failed"):
                if flag in lane_status and not isinstance(lane_status.get(flag), bool):
                    problems.append(f"lane_status.{flag} must be a bool")

    # OPTIONAL `bullish_flow` block (read-only UW opportunity WATCH lane, B1). A
    # dict {as_of,count,tickers,rows[]} or {}; validated IF present (forward-compat).
    bullish_flow = feed.get("bullish_flow", _MISSING)
    if bullish_flow is not _MISSING and not isinstance(bullish_flow, dict):
        problems.append(f"bullish_flow must be a dict, got {type(bullish_flow).__name__}")

    # OPTIONAL `prospects` block (Top Prospects lane — hot/movers/sell_fast/counts).
    # A dict or {}; validated IF present (forward-compat).
    prospects = feed.get("prospects", _MISSING)
    if prospects is not _MISSING and not isinstance(prospects, dict):
        problems.append(f"prospects must be a dict, got {type(prospects).__name__}")

    feedback = feed.get("feedback", _MISSING)
    if feedback is not _MISSING:
        problems.extend(f"feedback {e}" for e in _validate_feedback_block(feedback))

    # OPTIONAL `radar` block (endorsed, not owned). A list of dicts; absent OR
    # empty is valid (feeds that predate it, or a day with no qualifying call).
    radar = feed.get("radar", _MISSING)
    if radar is not _MISSING:
        if not isinstance(radar, list):
            problems.append(f"radar must be a list, got {type(radar).__name__}")
        else:
            for i, r in enumerate(radar):
                problems.extend(f"radar[{i}] {e}" for e in _validate_radar_row(r))

    # OPTIONAL `lean_in` block ⑩ (the opportunity lane — the mirror of risk
    # surfacing). A list of dicts; absent OR empty is valid (feeds that predate
    # it, or a quiet day with nothing to lean into — quiet-by-default, NOT an
    # "all clear"). Per-row invariants in _validate_lean_in_row.
    lean = feed.get("lean_in", _MISSING)
    if lean is not _MISSING:
        if not isinstance(lean, list):
            problems.append(f"lean_in must be a list, got {type(lean).__name__}")
        else:
            for i, r in enumerate(lean):
                problems.extend(f"lean_in[{i}] {e}" for e in _validate_lean_in_row(r))

    return problems


def is_valid_cockpit_feed(feed: Any) -> bool:
    return not validate_cockpit_feed(feed)


def assert_valid_cockpit_feed(feed: Any) -> None:
    problems = validate_cockpit_feed(feed)
    if problems:
        raise ValueError("invalid CockpitFeed: " + "; ".join(problems))
