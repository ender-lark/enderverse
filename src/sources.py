"""Conviction Engine — Layer 1: Sources (the plugs).

Contract A (Sources -> Collection): a uniform `SourceItem` fact-card.
Each external feed becomes one "plug" with the same shape:
    fetch  +  trust_weight  +  independence_group  +  provenance.

Design (per Build Plan P2):
  - SourceItem      : the standardized fact-card every plug emits.
  - BaseSource      : the plug template — an injectable fetcher + the dials.
  - SourceRegistry  : the wall of sockets — error-tolerant fetch_all() so one
                      bad plug can never sink the whole pull, plus an
                      independence_summary() for the Phase-2 echo-chamber guard.
  - make_price_source(): the first real plug — wraps the live rotation read.

Provenance plumbing is in from day one; the *smart* source weighting /
echo-chamber scoring is Phase 2 and rides on `independence_group`.

This module is pure-logic: fetchers are INJECTED, so every plug is testable
with canned data and no live credentials. Run `python sources.py --self-test`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Trust + independence dials (seeded for the v1 roster + the sources to come).
# trust_weight: 0..1 hard-data confidence.  independence_group: echo-chamber
# bucket — plugs in the same group collapse to ONE independent voice (Phase 2).
# ---------------------------------------------------------------------------
DEFAULT_TRUST: dict[str, float] = {
    "uw_price":        0.95,   # Unusual Whales market data — hard data
    "uw_macro":        0.95,   # Unusual Whales rates / dollar / vol
    "portfolio":       0.95,   # the canonical book itself
    "meridian":        0.75,   # Meridian critical-minerals research
    "fundstrat_bible": 0.70,   # monthly FS deck (Lee + Newton)
    "fundstrat_daily": 0.70,   # FS Inbox dailies (Newton / Lee); Farrell -> 0.65
    "reddit":          0.35,   # social (deferred plug; dial seeded)
}

DEFAULT_INDEPENDENCE: dict[str, str] = {
    "uw_price":        "market_data",
    "uw_macro":        "market_data",
    "portfolio":       "own",
    "meridian":        "thematic_research",
    "fundstrat_bible": "fundstrat",      # all Fundstrat plugs share ONE group
    "fundstrat_daily": "fundstrat",      #   (echo-chamber guard)
    "reddit":          "social",
}

# Fallbacks when a plug name isn't in the dials above.
FALLBACK_TRUST = 0.50
FALLBACK_INDEPENDENCE_PREFIX = ""   # unknown -> the plug's own name is its group

# Update cadence: how often a source refreshes. The Analyst's staleness read
# (Stage 3) maps cadence -> a freshness budget, so a STATIC source (e.g. Meridian,
# frozen Mar/Apr 2026 with no more updates coming) is labeled "baseline (date)"
# instead of false-alarming "stale" every day, while a daily feed flags quickly.
# Cadence is a SOURCE property, not a per-card field — Contract A is unchanged.
DEFAULT_CADENCE: dict[str, str] = {
    "uw_price":        "daily",
    "uw_macro":        "daily",
    "portfolio":       "on_refresh",   # updates when broker PDFs are uploaded
    "fundstrat_daily": "daily",
    "fundstrat_bible": "monthly",      # the monthly FS deck — a baseline snapshot
    "meridian":        "static",       # frozen; treat as a good base, not a live feed
    "reddit":          "daily",
}
FALLBACK_CADENCE = "daily"


def _now_iso() -> str:
    """UTC ISO-8601 timestamp (when a row was created, if a fetcher omits one)."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Contract A — the standardized fact-card.
# ---------------------------------------------------------------------------
@dataclass
class SourceItem:
    """One fact from one source, in the shape every downstream layer expects.

    Fields:
      source              plug name, e.g. "uw_price"
      kind                "rotation" | "macro" | "analyst_call" | "position" | "error"
      subject             what it's about, e.g. "SMH", "10Y", "XLF"
      content             human-readable one-liner, e.g. "LEADING +47%/3M vs mkt"
      timestamp           ISO-8601 string — the DATA's currency (drives staleness)
      trust_weight        0..1 confidence dial
      independence_group  echo-chamber bucket (Phase-2 weighting rides on this)
      data                structured payload (the numbers behind `content`)
    """
    source: str
    kind: str
    subject: str
    content: str
    timestamp: str
    trust_weight: float
    independence_group: str
    data: dict = field(default_factory=dict)

    def provenance(self) -> str:
        """One-line, end-to-end source label — the plumbing that lets every
        fact be traced back to where it came from."""
        return (
            f"{self.source} · {self.kind} · {self.subject} · {self.timestamp} · "
            f"trust={self.trust_weight:.2f} · grp={self.independence_group}"
        )


# ---------------------------------------------------------------------------
# The plug template.
# ---------------------------------------------------------------------------
class BaseSource:
    """A uniform "plug": an injectable fetcher + the trust/independence dials.

    The fetcher is any callable returning an iterable of EITHER:
      - dict rows  {kind, subject, content?, timestamp?, data?}  (the plug
        stamps source / trust_weight / independence_group), OR
      - ready-made SourceItem objects (passed through untouched).

    Injecting the fetcher is what makes every plug testable with canned data
    and lets Claude-read prose and pure-Python REST calls flow through the
    SAME rails (the plug doesn't care where a row came from).
    """

    def __init__(
        self,
        name: str,
        fetcher: Callable[[], Iterable[Any]],
        trust_weight: float | None = None,
        independence_group: str | None = None,
        cadence: str | None = None,
    ) -> None:
        self.name = name
        self._fetcher = fetcher
        self.trust_weight = (
            trust_weight if trust_weight is not None
            else DEFAULT_TRUST.get(name, FALLBACK_TRUST)
        )
        self.independence_group = (
            independence_group if independence_group is not None
            else DEFAULT_INDEPENDENCE.get(name, FALLBACK_INDEPENDENCE_PREFIX + name)
        )
        self.cadence = (
            cadence if cadence is not None
            else DEFAULT_CADENCE.get(name, FALLBACK_CADENCE)
        )

    def _to_item(self, row: Any) -> SourceItem:
        """Stamp a raw dict row into a SourceItem (or pass a SourceItem through).

        A row MAY override ``trust_weight`` / ``independence_group`` per-card
        (used e.g. by fundstrat_daily so a single plug carries Newton/Lee at 0.70
        and Farrell at 0.65); otherwise the plug's dials apply."""
        if isinstance(row, SourceItem):
            return row
        if not isinstance(row, dict):
            raise TypeError(
                f"{self.name}: fetcher row must be a dict or SourceItem, "
                f"got {type(row).__name__}"
            )
        row_tw = row.get("trust_weight")
        return SourceItem(
            source=self.name,
            kind=row["kind"],
            subject=row["subject"],
            content=row.get("content", ""),
            timestamp=row.get("timestamp") or _now_iso(),
            trust_weight=self.trust_weight if row_tw is None else row_tw,
            independence_group=row.get("independence_group") or self.independence_group,
            data=row.get("data", {}) or {},
        )

    def fetch(self) -> list[SourceItem]:
        """Run the injected fetcher and shape its output into SourceItems.
        May raise — the registry wraps this so one bad plug can't sink the pull."""
        return [self._to_item(row) for row in self._fetcher()]


# ---------------------------------------------------------------------------
# The registry — the wall of sockets.
# ---------------------------------------------------------------------------
class SourceRegistry:
    """Holds the registered plugs and pulls them all, tolerantly.

    fetch_all() NEVER raises on a single plug's failure: a failing plug emits a
    single kind="error" SourceItem and the rest of the haul is still returned.
    """

    def __init__(self) -> None:
        self._sources: list[BaseSource] = []

    def register(self, source: BaseSource) -> "SourceRegistry":
        self._sources.append(source)
        return self

    @property
    def sources(self) -> list[BaseSource]:
        return list(self._sources)

    def fetch_all(self) -> list[SourceItem]:
        """Pull every plug. A bad plug -> one kind="error" item, pull survives."""
        items: list[SourceItem] = []
        for src in self._sources:
            try:
                items.extend(src.fetch())
            except Exception as exc:  # noqa: BLE001 — deliberate: isolate one plug
                items.append(
                    SourceItem(
                        source=src.name,
                        kind="error",
                        subject=src.name,
                        content=f"fetch failed: {type(exc).__name__}: {exc}",
                        timestamp=_now_iso(),
                        trust_weight=getattr(src, "trust_weight", 0.0),
                        independence_group=getattr(src, "independence_group", "error"),
                        data={"error_type": type(exc).__name__, "error": str(exc)},
                    )
                )
        return items

    def independence_summary(self) -> dict[str, list[str]]:
        """Map each independence_group -> sorted list of plug names in it.
        The echo-chamber view: e.g. {"fundstrat": ["fundstrat_bible",
        "fundstrat_daily"], "market_data": ["uw_macro", "uw_price"], ...}."""
        summary: dict[str, set[str]] = {}
        for src in self._sources:
            summary.setdefault(src.independence_group, set()).add(src.name)
        return {grp: sorted(names) for grp, names in summary.items()}


# ---------------------------------------------------------------------------
# First real plug — the price / rotation source.
# ---------------------------------------------------------------------------
def make_price_source(
    rotation_reader: Callable[[], Iterable[dict]],
    name: str = "uw_price",
) -> BaseSource:
    """Wrap a 'rotation reader' into a uniform plug.

    `rotation_reader()` returns raw rows, one per sleeve proxy:
        {proxy, rel_1m, rel_3m, abs_3m, rel_1m_vs_smh?, rel_3m_vs_smh?, label, timestamp?}
    where rel_* are fractions vs SPY (e.g. 0.47 == +47%) and `label` is the
    rotation classification ("LEADING" / "LAGGING" / "TURNING UP" / ...).

    The plug normalizes each into a kind="rotation" SourceItem with a templated
    one-liner like "LEADING +47%/3M vs mkt". (Only mechanical normalization here
    — the catch-up-vs-broken JUDGMENT is the Analyst's job, not the plug's.)
    """

    def fetcher() -> list[dict]:
        rows = list(rotation_reader())
        out: list[dict] = []
        for row in rows:
            label = row.get("label", "")
            rel_3m = row.get("rel_3m")
            if rel_3m is not None:
                content = f"{label} {rel_3m:+.0%}/3M vs mkt".strip()
            else:
                content = label
            out.append(
                {
                    "kind": "rotation",
                    "subject": row["proxy"],
                    "content": content,
                    "timestamp": row.get("timestamp") or _now_iso(),
                    "data": {
                        "rel_1m": row.get("rel_1m"),
                        "rel_3m": row.get("rel_3m"),
                        "abs_3m": row.get("abs_3m"),
                        "rel_1m_vs_smh": row.get("rel_1m_vs_smh"),
                        "rel_3m_vs_smh": row.get("rel_3m_vs_smh"),
                        "label": label,
                    },
                }
            )
        return out

    return BaseSource(name=name, fetcher=fetcher)


# ---------------------------------------------------------------------------
# Self-test (run: python sources.py --self-test).
# ---------------------------------------------------------------------------
def _self_test() -> int:
    checks = 0

    # 1. SourceItem construction + provenance.
    it = SourceItem("uw_price", "rotation", "SMH", "LEADING +47%/3M vs mkt",
                    "2026-05-29", 0.95, "market_data", {"rel_3m": 0.47})
    assert it.subject == "SMH" and it.data["rel_3m"] == 0.47
    prov = it.provenance()
    assert "uw_price" in prov and "SMH" in prov and "trust=0.95" in prov
    checks += 1

    # 2. BaseSource stamps source/trust/group onto raw dict rows.
    src = BaseSource("uw_macro", lambda: [
        {"kind": "macro", "subject": "10Y", "content": "10Y 4.45% (-3bp 5d)",
         "timestamp": "2026-05-29", "data": {"value": 4.45, "chg_5d": -0.03}},
    ])
    rows = src.fetch()
    assert len(rows) == 1
    r = rows[0]
    assert r.source == "uw_macro" and r.trust_weight == 0.95
    assert r.independence_group == "market_data" and r.kind == "macro"
    checks += 1

    # 3. Default trust/group lookup from the dials.
    p = BaseSource("uw_price", lambda: [])
    assert p.trust_weight == 0.95 and p.independence_group == "market_data"
    fb = BaseSource("fundstrat_bible", lambda: [])
    assert fb.trust_weight == 0.70 and fb.independence_group == "fundstrat"
    checks += 1

    # 4. Explicit overrides beat the defaults (e.g. Farrell daily at 0.65).
    farrell = BaseSource("fundstrat_daily", lambda: [], trust_weight=0.65)
    assert farrell.trust_weight == 0.65 and farrell.independence_group == "fundstrat"
    checks += 1

    # 5. Unknown source name -> fallback trust + its own name as its group.
    unk = BaseSource("mystery_feed", lambda: [])
    assert unk.trust_weight == FALLBACK_TRUST and unk.independence_group == "mystery_feed"
    checks += 1

    # 6. A fetcher may return ready-made SourceItems (passed through untouched).
    pre = SourceItem("portfolio", "position", "SMH", "SMH 9.90% Owned",
                     "2026-05-27", 0.95, "own", {"pct": 9.9})
    pass_src = BaseSource("portfolio", lambda: [pre])
    out = pass_src.fetch()
    assert out[0] is pre
    checks += 1

    # 7. Registry gathers from multiple good plugs.
    reg = SourceRegistry()
    reg.register(BaseSource("uw_macro", lambda: [
        {"kind": "macro", "subject": "VIX", "content": "VIX 17.2"}]))
    reg.register(BaseSource("meridian", lambda: [
        {"kind": "analyst_call", "subject": "LEU",
         "content": "HALEU enrichment monopoly"}]))
    haul = reg.fetch_all()
    assert len(haul) == 2
    assert {h.source for h in haul} == {"uw_macro", "meridian"}
    checks += 1

    # 8. Error-tolerance: one plug raises -> exactly one kind="error" item,
    #    the good plug's items still come back.
    def boom():
        raise RuntimeError("connector down")
    reg2 = SourceRegistry()
    reg2.register(BaseSource("uw_price", boom))
    reg2.register(BaseSource("uw_macro", lambda: [
        {"kind": "macro", "subject": "10Y", "content": "10Y 4.45%"}]))
    haul2 = reg2.fetch_all()
    errs = [h for h in haul2 if h.kind == "error"]
    goods = [h for h in haul2 if h.kind != "error"]
    assert len(errs) == 1 and errs[0].source == "uw_price"
    assert "connector down" in errs[0].content
    assert len(goods) == 1 and goods[0].subject == "10Y"
    checks += 1

    # 9. independence_summary groups the two Fundstrat plugs into one group.
    reg3 = SourceRegistry()
    for n in ("uw_price", "fundstrat_bible", "fundstrat_daily"):
        reg3.register(BaseSource(n, lambda: []))
    summ = reg3.independence_summary()
    assert summ["fundstrat"] == ["fundstrat_bible", "fundstrat_daily"]
    assert summ["market_data"] == ["uw_price"]
    checks += 1

    # 10. make_price_source: fake rotation reader -> well-formed rotation items.
    def fake_rotation():
        return [
            {"proxy": "SMH", "rel_1m": 0.06, "rel_3m": 0.47, "abs_3m": 0.52,
             "label": "LEADING", "timestamp": "2026-05-29"},
            {"proxy": "REMX", "rel_1m": -0.01, "rel_3m": -0.08, "abs_3m": 0.03,
             "label": "LAGGING", "timestamp": "2026-05-29"},
        ]
    price = make_price_source(fake_rotation)
    pitems = price.fetch()
    assert price.trust_weight == 0.95 and price.independence_group == "market_data"
    assert len(pitems) == 2
    smh = next(i for i in pitems if i.subject == "SMH")
    assert smh.kind == "rotation" and smh.content == "LEADING +47%/3M vs mkt"
    assert smh.data["rel_3m"] == 0.47 and smh.data["label"] == "LEADING"
    checks += 1

    # 11. A row may override trust_weight per-card; default applies otherwise.
    ov = BaseSource("fundstrat_daily", lambda: [
        {"kind": "analyst_call", "subject": "HYPE", "content": "accumulate",
         "trust_weight": 0.65}])
    card = ov.fetch()[0]
    assert card.trust_weight == 0.65 and card.independence_group == "fundstrat"
    card2 = BaseSource("fundstrat_daily", lambda: [
        {"kind": "analyst_call", "subject": "NVDA", "content": "buy"}]).fetch()[0]
    assert card2.trust_weight == 0.70
    checks += 1

    # 12. Source cadence: seeded by name (meridian static / bible monthly /
    #     uw daily / portfolio on_refresh); unknown -> daily; override wins.
    assert BaseSource("meridian", lambda: []).cadence == "static"
    assert BaseSource("fundstrat_bible", lambda: []).cadence == "monthly"
    assert BaseSource("uw_price", lambda: []).cadence == "daily"
    assert BaseSource("portfolio", lambda: []).cadence == "on_refresh"
    assert BaseSource("mystery_feed", lambda: []).cadence == "daily"
    assert BaseSource("x", lambda: [], cadence="weekly").cadence == "weekly"
    checks += 1

    print(f"sources.py self-test: {checks}/{checks} checks PASS")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    print(__doc__)
