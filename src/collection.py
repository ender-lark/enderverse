"""Conviction Engine — Layer 2 Collection: Contract B (`CollectedSnapshot`).

C1 (this step) defines the snapshot the Collection runner produces and the
Analyst consumes — one run's full haul plus run metadata. The runner that
actually builds it (registry -> fetch_all -> assemble + staleness + ok/failed) is
C2. The Analyst consumes a CollectedSnapshot and **never re-fetches**.

Per the P3 decision, the portfolio rides INSIDE `items` as `kind="position"`
cards (not a separate field) — the Analyst reconstructs the book via
`.positions()`. Staleness is the newest item-date per source (filled by the
runner), powering the cockpit's "sourced: FS 5/28 · rotation 5/29" stamp.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CollectedSnapshot:
    """Contract B — Collection -> Analyst.

    Fields:
      run_id            timestamp-based unique id for this run
      run_timestamp     ISO-8601, when the run happened
      items             the full haul: List[SourceItem] (rotation / macro /
                        analyst_call / position / model_trade / error cards)
      sources_ok        plug names that returned cleanly
      sources_failed    [{"name", "error"}] — from the kind="error" items
      staleness         {source_name: newest ISO date seen} (runner-computed)
      critical_missing  critical plug names that failed (Analyst degrades loudly)
    """
    run_id: str
    run_timestamp: str
    items: list = field(default_factory=list)            # List[SourceItem]
    sources_ok: list = field(default_factory=list)        # list[str]
    sources_failed: list = field(default_factory=list)    # list[{"name","error"}]
    staleness: dict = field(default_factory=dict)         # {source: ISO date}
    critical_missing: list = field(default_factory=list)  # list[str]

    def positions(self) -> list:
        """The held book — items with kind == 'position'. (P3: the Analyst
        reconstructs the portfolio by filtering these off the uniform rails.)"""
        return [it for it in self.items if getattr(it, "kind", None) == "position"]

    def errors(self) -> list:
        """The kind='error' items a failing plug emitted (mirrors sources_failed)."""
        return [it for it in self.items if getattr(it, "kind", None) == "error"]

    def items_of_kind(self, kind: str) -> list:
        return [it for it in self.items if getattr(it, "kind", None) == kind]


# ---------------------------------------------------------------------------
# C2 — the Collection runner.
# ---------------------------------------------------------------------------
CRITICAL_SOURCES = ("portfolio", "uw_price")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect(
    registry,
    critical=CRITICAL_SOURCES,
    run_id: str | None = None,
    run_timestamp: str | None = None,
) -> CollectedSnapshot:
    """Run a SourceRegistry into one CollectedSnapshot (Contract B).

    `registry.fetch_all()` is already error-tolerant (a failing plug -> one
    kind="error" item). This runner adds the run-level view on top:
      - sources_ok       = registered plugs that did NOT emit an error item
      - sources_failed   = [{name, error}] from the error items
      - staleness        = newest non-error item-date per source (the cockpit stamp;
                           ISO-8601 sorts chronologically, so max() is correct)
      - critical_missing = critical plugs that delivered NO data (failed, returned
                           empty, or absent) -> the Analyst degrades loudly.

    NOTE: a plug can be in BOTH sources_ok (ran cleanly) AND critical_missing
    (returned nothing) — that's the honest "ran fine but gave us no book" case.

    Pure assembly: fetchers are injected upstream, so no live creds and no
    re-fetch — the Analyst consumes the snapshot as-is.
    """
    items = registry.fetch_all()

    # registered plug names (deduped, order-preserved)
    registered, seen = [], set()
    for s in getattr(registry, "sources", []):
        if s.name not in seen:
            registered.append(s.name)
            seen.add(s.name)

    # failures: from the kind="error" items fetch_all emits
    sources_failed, failed_set = [], set()
    for it in items:
        if getattr(it, "kind", None) == "error":
            sources_failed.append({"name": it.source, "error": it.content})
            failed_set.add(it.source)

    sources_ok = [n for n in registered if n not in failed_set]

    # staleness: newest non-error timestamp per source
    staleness: dict = {}
    for it in items:
        if getattr(it, "kind", None) == "error":
            continue
        ts = getattr(it, "timestamp", None)
        if not ts:
            continue
        if it.source not in staleness or ts > staleness[it.source]:
            staleness[it.source] = ts

    delivered = set(staleness)   # sources that produced >=1 non-error item
    critical_missing = [c for c in critical if c not in delivered]

    rt = run_timestamp or _utc_now_iso()
    rid = run_id or ("run_" + rt.replace("-", "").replace(":", ""))
    return CollectedSnapshot(
        run_id=rid, run_timestamp=rt, items=items,
        sources_ok=sources_ok, sources_failed=sources_failed,
        staleness=staleness, critical_missing=critical_missing,
    )


# ---------------------------------------------------------------------------
# C4 — compact run-log (audit trail: "what did the engine see on day X").
# ---------------------------------------------------------------------------
def _run_log_summary(p: dict) -> str:
    failed = ", ".join(p["sources_failed"]) or "none"
    crit = ", ".join(p["critical_missing"]) or "none"
    return (f"{p['run_id']} · {p['item_count']} items · "
            f"{len(p['sources_ok'])} ok · {len(p['sources_failed'])} failed "
            f"({failed}) · critical missing: {crit}")


def run_log_payload(snapshot: CollectedSnapshot) -> dict:
    """Compact, audit-focused view of one run (timestamp · sources ok/failed ·
    staleness · item count). `sources_failed` is names-only here (the full errors
    live in the snapshot) to keep the log compact. Pure function — fully testable."""
    payload = {
        "run_id": snapshot.run_id,
        "run_timestamp": snapshot.run_timestamp,
        "item_count": len(snapshot.items),
        "sources_ok": list(snapshot.sources_ok),
        "sources_failed": [f.get("name") for f in snapshot.sources_failed],
        "critical_missing": list(snapshot.critical_missing),
        "staleness": dict(snapshot.staleness),
    }
    payload["summary"] = _run_log_summary(payload)
    return payload


def write_run_log(snapshot: CollectedSnapshot, writer) -> dict:
    """Write the compact run-log via an INJECTED `writer(payload)` callable
    (production: a Notion create/append; tests: a fake). The log is AUDIT, not
    critical — a writer failure is caught and reported, never raised, so a Notion
    hiccup can't sink the collection run.

    Returns {written: bool, payload: dict, result|error}.
    """
    payload = run_log_payload(snapshot)
    try:
        result = writer(payload)
        return {"written": True, "payload": payload, "result": result}
    except Exception as exc:  # noqa: BLE001 — audit log must not sink the run
        return {"written": False, "payload": payload,
                "error": f"{type(exc).__name__}: {exc}"}
