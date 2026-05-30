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
