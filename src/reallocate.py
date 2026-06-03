#!/usr/bin/env python3
"""
reallocate.py — target-weight ROTATION planner (REBUILT 2026-06-02).

WHAT THIS IS (the rebuild — not the old tier-band rebalancer)
    A faithful EXECUTOR of your conviction target-weight model. Given your
    per-name targets (reallocate_config.default_working_model) it produces the
    FUNDED ETF->single-name rotation that moves the book toward them — held
    ~flat in total AI, opportunity-gated, catalyst-sequenced. CANDIDATES only
    (P-NO-FILL-NO-FACT); tax-agnostic by request.

WHY IT WORKS THE WAY IT DOES (every rule traces to YOUR decisions)
    - Rotation, AI ~flat ~60%        : your pre-trade-gate finding — net-new AI REDs;
                                       only a funded $-for-$ wrapper->single rotation
                                       is AMBER. So every ADD is paired with a same-
                                       factor wrapper TRIM.
    - ETF look-through               : holding SMH AND sizing NVDA double-counts NVDA;
                                       we net the KEPT wrapper's NVDA out of the add.
    - Priority = conviction + entry  : ranked by tier + run-up tag (constructive first,
                                       parabolic last), NEVER by gap-to-target.
    - ETFs = reservoirs              : we only draw a wrapper down to fund a name that
                                       clears the bar; "convert->0" is a ceiling, not a
                                       forced sell.
    - Concentration rail = OFF       : your discipline is tier caps + funded-factor-flat
                                       + ~60%-flat; the aggregate rail is an optional dial
                                       you set (reallocate_config.ConcentrationRail).

    All the numbers live in reallocate_config.py — change a dial there, re-run, the
    plan changes. This module hardcodes none of them.

BUILD STATUS: Chunks 2-4 (planner core + ranking/gate/sequence/premise-gate +
    output/per-sub-sector metric). VERIFY-ONLY until committed + wired. The live
    `pretrade_gate.evaluate` wiring is a documented hook (the funded=AMBER /
    net-new=RED logic is implemented inline, mirroring the gate's factor finding).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from reallocate_config import (
    Dials, DEFAULT_DIALS, ConcentrationRail, RAIL_OFF,
    TargetWeightModel, NameTarget, default_working_model,
    SUBSECTOR_METRIC, ETF_LOOKTHROUGH, lookthrough_implied_pct,
    validate_concentration_rail, SMH_APPROACH_A, SMH_APPROACH_B,
)

# ===========================================================================
# CONSTANTS
# ===========================================================================
GATE_NOTIONAL_THRESHOLD = 25_000.0     # any leg >= this gets a gate verdict
MATERIALITY_PCT_DEFAULT = 0.5          # gaps smaller than this (% of book) aren't legged

ADD = "ADD"
TRIM = "TRIM"

# run-up entry tags (your bifurcated-market read)
TAG_CONSTRUCTIVE = "constructive"   # off-highs / pulled back -> size NOW
TAG_EXTENDED = "extended"           # rising but not parabolic -> ok, scale on dips
TAG_PARABOLIC = "parabolic"         # don't chase at market -> wait / defined-risk

_TAG_RANK = {TAG_CONSTRUCTIVE: 0, TAG_EXTENDED: 1, TAG_PARABOLIC: 2, "": 1}
_TIER_RANK = {"T1": 0, "T2": 1, "T3": 2, "T4": 3, "": 4}

# gate verdicts
GATE_GREEN = "GREEN"
GATE_AMBER = "AMBER"
GATE_RED = "RED"

# ETF roles — which wrappers are pure AI-factor (trimming them to fund AI singles
# is factor-FLAT) vs broad reservoirs (trimming them INCREASES net AI factor — a
# deliberate overweight, logged, not factor-flat).
AI_FACTOR_WRAPPERS = {"SMH", "MAGS", "IGV", "IVES", "SOXX", "FTXL", "SOXL"}
BROAD_RESERVOIRS = {"GRNY", "GRNJ"}


# ===========================================================================
# CONTRACTS
# ===========================================================================
@dataclass
class Leg:
    action: str                 # ADD / TRIM
    ticker: str
    current_pct: float
    target_pct: float
    effective_current_pct: float   # incl. look-through of KEPT wrappers (ADDs)
    delta_pct: float               # signed change in DIRECT holding
    notional_usd: float
    tier: str = ""
    factor: str = ""
    sub_sector: str = ""
    is_etf: bool = False
    funded_by: list = field(default_factory=list)   # ADD: [(etf, usd), ...]
    funds: list = field(default_factory=list)        # TRIM: [(name, usd), ...]
    gate: str = ""                 # GREEN/AMBER/RED, or "" when < threshold
    gate_reason: str = ""
    run_up_tag: str = ""
    entry_note: str = ""           # "size now" / "wait — parabolic" / "after 2026-06-03"
    sequence: str = "now"          # "now" / "after <date>" / "on pullback"
    rank: int = 0
    metric: str = ""               # per-sub-sector valuation lens
    rationale: str = ""
    caveats: list = field(default_factory=list)


@dataclass
class FundingSummary:
    pool_total_usd: float
    allocated_usd: float
    remaining_usd: float
    shortfall_usd: float
    sources: list = field(default_factory=list)   # [(etf, convertible_usd, drawn_usd)]


@dataclass
class TargetRow:
    ticker: str
    current_pct: float
    effective_current_pct: float
    target_pct: float
    gap_pct: float
    tier: str
    is_etf: bool
    run_up_tag: str = ""
    status: str = ""


@dataclass
class ReallocationResult:
    as_of: str
    total_book_value: float
    dials_describe: str
    legs: list = field(default_factory=list)
    sequence_now: list = field(default_factory=list)
    sequence_later: list = field(default_factory=list)   # [(ticker, reason)]
    funding: Optional[FundingSummary] = None
    target_vs_current: list = field(default_factory=list)
    rail_status: str = "off"
    rail_violations: list = field(default_factory=list)
    monitor_left_alone: list = field(default_factory=list)
    other_left_alone: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)


# ===========================================================================
# HELPERS
# ===========================================================================
def _pct(mv: float, total: float) -> float:
    return round(100.0 * mv / total, 4) if total else 0.0


def positions_from_feed(feed: dict, total_book_value: float) -> list:
    """Flatten a cockpit FEED ({holdings:[{cat,pos:[{t,pct}]}]}) into
    [{ticker, market_value}]. pct is % of book."""
    if not total_book_value:
        raise ValueError("total_book_value must be > 0")
    out = []
    for sleeve in feed.get("holdings", []):
        for p in sleeve.get("pos", []):
            pct = float(p.get("pct", 0.0))
            out.append({"ticker": p["t"], "market_value": pct / 100.0 * total_book_value})
    return out


def current_weights(positions: list, total: float) -> dict:
    return {p["ticker"]: _pct(p["market_value"], total) for p in positions}


def kept_wrapper_weights(dials: Dials) -> dict:
    """Post-rotation book % of each AI-factor wrapper we KEEP (for look-through)."""
    return {etf: dials.etf_keep_levels.get(etf, 0.0)
            for etf in AI_FACTOR_WRAPPERS if dials.etf_keep_levels.get(etf, 0.0) > 0}


def effective_current_pct(ticker: str, weights: dict, dials: Dials) -> float:
    """Direct holding + what you still hold THROUGH the wrappers you keep."""
    actual = weights.get(ticker, 0.0)
    implied = lookthrough_implied_pct(ticker, kept_wrapper_weights(dials))
    return round(actual + implied, 4)


# ===========================================================================
# FUNDING POOL  (one pool, spent once — Chunk 2)
# ===========================================================================
def build_funding_pool(weights: dict, total: float, dials: Dials,
                       model: TargetWeightModel) -> tuple:
    """Convertible ETF excess = current - keep_level, per AI-theme ETF.
    Returns (pool_usd, ordered_sources) with AI-factor wrappers drawn FIRST
    (factor-flat funding), broad reservoirs LAST (net-AI-increasing)."""
    model_etf_targets = {t.ticker: t.target_pct for t in model.etfs()}
    etf_tickers = (set(dials.etf_keep_levels) | set(model_etf_targets)
                   | AI_FACTOR_WRAPPERS | BROAD_RESERVOIRS)
    sources = []
    for etf in etf_tickers:
        cur = weights.get(etf, 0.0)
        if cur <= 0:
            continue
        keep = max(dials.etf_keep_levels.get(etf, 0.0), model_etf_targets.get(etf, 0.0))
        conv_pct = round(cur - keep, 4)
        if conv_pct > 1e-6:
            sources.append({
                "etf": etf, "cur_pct": cur, "keep_pct": keep,
                "conv_usd": round(conv_pct / 100.0 * total, 2),
                "broad": etf in BROAD_RESERVOIRS,
            })
    # AI-factor wrappers first (factor-flat), broad reservoirs last
    sources.sort(key=lambda s: (s["broad"], -s["conv_usd"]))
    pool = round(sum(s["conv_usd"] for s in sources), 2)
    return pool, sources


# ===========================================================================
# PLANNER CORE  (Chunk 2)
# ===========================================================================
def _add_candidates(weights: dict, total: float, dials: Dials,
                    model: TargetWeightModel, run_up: dict) -> list:
    """One ADD candidate per AI single name whose target is materially above its
    effective current. Tagged with run-up + gating, not yet funded."""
    out = []
    for t in model.single_names():
        eff = effective_current_pct(t.ticker, weights, dials)
        gap = round(t.target_pct - eff, 4)
        if gap < MATERIALITY_PCT_DEFAULT:
            continue  # at/above target (incl. look-through) -> no add (e.g. MU hold-flat)
        tag = _run_up_tag(t.ticker, run_up, dials)
        direct_cat = dials.catalyst_gates.get(t.ticker)
        corr_date, corr_src = _correlated_catalyst(t.ticker, dials)
        cand = {
            "t": t, "eff": eff, "gap_pct": gap,
            "gap_usd": round(gap / 100.0 * total, 2),
            "tag": tag,
            "chase_blocked": (tag == TAG_PARABOLIC),
            "catalyst": direct_cat or corr_date,
            "catalyst_correlated_to": None if direct_cat else corr_src,
        }
        out.append(cand)
    return out


def _run_up_tag(ticker: str, run_up: dict, dials: Dials) -> str:
    """Map a 1-month run-up % to a tag using the chase-block dial.
    run_up: {ticker: pct_1m}. Missing -> '' (unknown; treated as extended)."""
    if not run_up or ticker not in run_up:
        return ""
    r = run_up[ticker]
    if r > dials.chase_block_1m_runup_pct:
        return TAG_PARABOLIC
    if r > 10.0:
        return TAG_EXTENDED
    return TAG_CONSTRUCTIVE


def _correlated_catalyst(ticker: str, dials: Dials) -> tuple:
    """If `ticker` is in another (catalyst-gated) name's correlated list, return that
    name's catalyst date + the source ticker. Your 6/2 sequence: NVDA / TSM wait for the
    AVGO print (semis move together through a bellwether). (None, None) if not correlated."""
    for gated, corr_list in dials.catalyst_correlated.items():
        if ticker in corr_list and gated in dials.catalyst_gates:
            return dials.catalyst_gates[gated], gated
    return None, None


def _rank_key(cand) -> tuple:
    """Priority = conviction (tier) + entry quality (run-up tag) + catalyst-ready.
    NOT gap size (P-DIRECTIONAL-TARGETS: a gap is context, never the priority)."""
    t = cand["t"]
    catalyst_pending = 1 if cand["catalyst"] else 0
    return (_TIER_RANK.get(t.tier, 4), _TAG_RANK.get(cand["tag"], 1),
            catalyst_pending, -cand["gap_usd"])


def _allocate_pool(cands: list, pool: float, sources: list) -> tuple:
    """Spend ONE pool across ranked ADDs (best first), gap-capped, no double-spend.
    Mutates a copy of sources' remaining $; returns (funded_map, drawn_per_etf,
    remaining, shortfall). Chase-blocked names are funded too (they become
    'on pullback / defined-risk' legs) so the rotation stays whole."""
    remaining = pool
    src = [dict(s, rem=s["conv_usd"]) for s in sources]
    funded = {}        # ticker -> [(etf, usd)]
    drawn = {}         # etf -> usd
    shortfall = 0.0
    for c in cands:
        need = c["gap_usd"]
        got = 0.0
        legs = []
        for s in src:
            if need - got <= 1e-6 or remaining <= 1e-6:
                break
            take = min(s["rem"], need - got, remaining)
            if take <= 1e-6:
                continue
            s["rem"] = round(s["rem"] - take, 2)
            remaining = round(remaining - take, 2)
            got = round(got + take, 2)
            legs.append((s["etf"], round(take, 2)))
            drawn[s["etf"]] = round(drawn.get(s["etf"], 0.0) + take, 2)
        funded[c["t"].ticker] = legs
        c["funded_usd"] = got
        if got + 1e-6 < need:
            shortfall = round(shortfall + (need - got), 2)
    return funded, drawn, round(remaining, 2), round(shortfall, 2)


def _gate_for_add(funded_legs: list, notional: float) -> tuple:
    """Funded $-for-$ by AI-factor wrappers -> AMBER (net-factor-flat). Funded
    partly by a broad reservoir -> AMBER + caveat (increases net AI). < threshold
    -> no gate. (Mirrors pretrade_gate's factor finding; live gate is a hook.)"""
    if notional < GATE_NOTIONAL_THRESHOLD:
        return "", ""
    broad = [e for (e, _u) in funded_legs if e in BROAD_RESERVOIRS]
    if broad:
        return GATE_AMBER, (f"funded rotation, but partly from broad reservoir(s) "
                            f"{', '.join(broad)} -> increases net AI factor; deliberate overweight, log it")
    return GATE_AMBER, "funded $-for-$ by AI-factor wrapper trim -> net-factor-flat (override + log)"


def plan_reallocation(*, feed: Optional[dict] = None, positions: Optional[list] = None,
                      total_book_value: float,
                      model: Optional[TargetWeightModel] = None,
                      dials: Optional[Dials] = None,
                      run_up: Optional[dict] = None,
                      materiality_pct: float = MATERIALITY_PCT_DEFAULT,
                      as_of: str = "") -> ReallocationResult:
    """Core: current -> target funded rotation. Reads everything from `model` +
    `dials` (defaults = your Working Model). `run_up` = {ticker: 1M run-up %}
    for the chase gate (optional; degrades to no chase-gate if absent)."""
    model = model or default_working_model()
    dials = dials or DEFAULT_DIALS
    run_up = run_up or {}
    if positions is None:
        if feed is None:
            raise ValueError("provide positions=[...] or feed={...}")
        positions = positions_from_feed(feed, total_book_value)
    if not total_book_value:
        raise ValueError("total_book_value must be > 0")

    weights = current_weights(positions, total_book_value)
    res = ReallocationResult(as_of=as_of, total_book_value=total_book_value,
                             dials_describe=dials.describe())

    # 1. funding pool (one pool)
    pool, sources = build_funding_pool(weights, total_book_value, dials, model)

    # 2. ADD candidates + 3. rank by conviction+entry (not gap)
    cands = _add_candidates(weights, total_book_value, dials, model, run_up)
    cands.sort(key=_rank_key)

    # 4. spend the pool across ranked adds
    funded, drawn, remaining, shortfall = _allocate_pool(cands, pool, sources)

    # 5. build ADD legs
    rank = 0
    single_names = {t.ticker for t in model.single_names()}
    for c in cands:
        t = c["t"]
        funded_legs = funded.get(t.ticker, [])
        notional = round(sum(u for _e, u in funded_legs), 2)
        if notional <= 1e-6:
            # nothing funded (pool exhausted): record as unfunded shortfall note
            res.notes.append(f"{t.ticker}: gap {c['gap_pct']:.1f}% unfunded (pool exhausted)")
            continue
        rank += 1
        gate, greason = _gate_for_add(funded_legs, notional)
        if c["chase_blocked"]:
            entry, seq = "wait — parabolic; pullback or defined-risk only", "on pullback"
        elif c["catalyst"]:
            if c.get("catalyst_correlated_to"):
                entry = f"size AFTER the {c['catalyst_correlated_to']} {c['catalyst']} print (correlated semis read)"
            else:
                entry = f"size AFTER the {c['catalyst']} print"
            seq = f"after {c['catalyst']}"
        else:
            entry, seq = "size now (constructive/ok entry)", "now"
        leg = Leg(
            action=ADD, ticker=t.ticker, current_pct=weights.get(t.ticker, 0.0),
            target_pct=t.target_pct, effective_current_pct=c["eff"],
            delta_pct=round(notional / total_book_value * 100.0, 4), notional_usd=notional,
            tier=t.tier, factor=t.factor, sub_sector=t.sub_sector, is_etf=False,
            funded_by=funded_legs, gate=gate, gate_reason=greason,
            run_up_tag=c["tag"], entry_note=entry, sequence=seq, rank=rank,
            metric=SUBSECTOR_METRIC.get(t.sub_sector, ""),
            rationale=t.note,
        )
        if c["funded_usd"] + 1e-6 < c["gap_usd"]:
            leg.caveats.append(f"partially funded: ${notional:,.0f} of ${c['gap_usd']:,.0f} gap")
        leg.caveats.append("risk transformation, not a cut — same AI dollars, concentrated into the name")
        res.legs.append(leg)

    # 6. build TRIM legs (one per drawn-down ETF)
    for etf, usd in sorted(drawn.items(), key=lambda kv: -kv[1]):
        if usd <= 1e-6:
            continue
        cur = weights.get(etf, 0.0)
        delta = round(usd / total_book_value * 100.0, 4)
        funds_names = [(lg.ticker, [u for (e, u) in lg.funded_by if e == etf][0])
                       for lg in res.legs if any(e == etf for (e, _u) in lg.funded_by)]
        leg = Leg(
            action=TRIM, ticker=etf, current_pct=cur, target_pct=round(cur - delta, 4),
            effective_current_pct=cur, delta_pct=-delta, notional_usd=round(usd, 2),
            tier="", factor="", sub_sector="", is_etf=True,
            funds=funds_names, gate=GATE_GREEN if usd >= GATE_NOTIONAL_THRESHOLD else "",
            gate_reason="trim reduces concentration" if usd >= GATE_NOTIONAL_THRESHOLD else "",
            rank=0, rationale=("reservoir drawn to fund the names above"
                               if etf in BROAD_RESERVOIRS else "wrapper trimmed to fund same-factor singles"),
        )
        if etf in BROAD_RESERVOIRS:
            leg.caveats.append("broad reservoir — trimming this raises net AI exposure (deliberate)")
        res.legs.append(leg)

    # 7. funding summary
    res.funding = FundingSummary(
        pool_total_usd=pool, allocated_usd=round(pool - remaining, 2),
        remaining_usd=remaining, shortfall_usd=shortfall,
        sources=[(s["etf"], s["conv_usd"], drawn.get(s["etf"], 0.0)) for s in sources],
    )

    # 8. sequence split (now vs later)  — Chunk 3
    for lg in res.legs:
        if lg.action != ADD:
            continue
        if lg.sequence == "now":
            res.sequence_now.append(lg.ticker)
        else:
            res.sequence_later.append((lg.ticker, lg.entry_note))

    # 9. target-vs-current table (gaps as CONTEXT, never the trigger)
    for t in model.targets:
        eff = effective_current_pct(t.ticker, weights, dials) if t.is_single_name else weights.get(t.ticker, 0.0)
        gap = round(t.target_pct - eff, 4)
        tag = _run_up_tag(t.ticker, run_up, dials) if t.is_single_name else ""
        if gap < MATERIALITY_PCT_DEFAULT and gap > -MATERIALITY_PCT_DEFAULT:
            status = "at target"
        elif gap <= -MATERIALITY_PCT_DEFAULT:
            status = "above target (hold / trim source)" if not t.is_single_name else "above target — hold flat"
        elif tag == TAG_PARABOLIC:
            status = "below — but parabolic; wait / defined-risk"
        else:
            status = "below — opportunity to add (funded)"
        res.target_vs_current.append(TargetRow(
            ticker=t.ticker, current_pct=weights.get(t.ticker, 0.0),
            effective_current_pct=eff, target_pct=t.target_pct, gap_pct=gap,
            tier=t.tier, is_etf=(not t.is_single_name), run_up_tag=tag, status=status))

    # 10. optional concentration rail (default OFF -> [])
    target_map = {}
    for t in model.targets:
        if t.is_single_name:
            # resulting direct weight after the planned adds
            add = next((lg.notional_usd / total_book_value * 100.0
                        for lg in res.legs if lg.action == ADD and lg.ticker == t.ticker), 0.0)
            target_map[t.ticker] = round(weights.get(t.ticker, 0.0) + add, 4)
        else:
            target_map[t.ticker] = dials.etf_keep_levels.get(t.ticker, t.target_pct)
    res.rail_violations = validate_concentration_rail(
        target_map, model, dials.concentration_rail, kept_wrapper_weights(dials))
    res.rail_status = dials.concentration_rail.label if dials.concentration_rail.is_on else "off"

    # 11. left-alone (MONITOR + everything not in the AI universe) — premise-gate note
    ai_universe = (single_names | {t.ticker for t in model.etfs()}
                   | AI_FACTOR_WRAPPERS | BROAD_RESERVOIRS)
    leg_tickers = {lg.ticker for lg in res.legs}
    for p in positions:
        tk = p["ticker"]
        if tk in ai_universe or tk in leg_tickers:
            continue
        # not in the AI universe and not legged -> left alone. MONITOR sleeves
        # (crypto/nuclear/critical-min) land here automatically (never legged).
        res.other_left_alone.append(tk)

    # 12. warnings / premise-gate
    if not run_up:
        res.warnings.append("no run-up data supplied -> chase-gate inactive; verify entries live before acting")
    if shortfall > 1e-6:
        res.warnings.append(f"funding shortfall ${shortfall:,.0f}: not every target gap could be funded "
                            f"from the convertible pool (rotation stays AI-flat by design)")
    res.notes.append("PREMISE-GATE: each single-name add assumes a NAME-LEVEL edge (the model includes it); "
                     "if a name lacks a research/source tag, treat its add as research-only.")
    res.notes.append("Change any dial in reallocate_config.py (NVDA target, SMH approach, ETF keep-levels, "
                     "the rail, the chase gate) and re-run to see the plan change.")
    return res


# ===========================================================================
# OUTPUT  (Chunk 4 — mobile-first markdown)
# ===========================================================================
def _fmt_usd(x: float) -> str:
    return f"${x:,.0f}"


def _fmt_leg(lg: Leg) -> str:
    sign = "+" if lg.action == ADD else "-"
    gate = f" · gate {lg.gate}" if lg.gate else ""
    tag = f" · {lg.run_up_tag}" if lg.run_up_tag else ""
    head = (f"**{lg.action} {lg.ticker}** {lg.current_pct:.2f}% -> {lg.target_pct:.2f}% "
            f"({sign}{_fmt_usd(lg.notional_usd)}){tag}{gate}")
    return head


def format_reallocation(r: ReallocationResult) -> str:
    L = ["# Reallocation — CANDIDATES (funded AI rotation, tax-agnostic)",
         f"_as of {r.as_of or 'now'} · book {_fmt_usd(r.total_book_value)}_",
         "> Every line is a **CANDIDATE** — nothing here is executed (P-NO-FILL-NO-FACT). "
         "Total AI is held ~flat: each ADD is funded $-for-$ by a wrapper TRIM.",
         "",
         "```",
         r.dials_describe,
         "```"]

    if r.warnings:
        L.append("\n## \u26a0\ufe0f Data quality")
        L += [f"- {w}" for w in r.warnings]

    # ADD legs (ranked), each with its funding
    adds = [lg for lg in r.legs if lg.action == ADD]
    if adds:
        L.append(f"\n## Ranked adds ({len(adds)}) — by conviction + entry, not gap size")
        for lg in adds:
            L.append(f"{lg.rank}. {_fmt_leg(lg)}")
            if lg.funded_by:
                fund = ", ".join(f"{e} {_fmt_usd(u)}" for e, u in lg.funded_by)
                L.append(f"   \u21b3 funded by: {fund}")
            L.append(f"   \u21b3 {lg.entry_note}  ·  metric: {lg.metric}")
            if lg.gate_reason:
                L.append(f"   \u21b3 gate: {lg.gate_reason}")
            for c in lg.caveats:
                L.append(f"   \u26a0\ufe0f {c}")

    # TRIM legs
    trims = [lg for lg in r.legs if lg.action == TRIM]
    if trims:
        L.append("\n## Funding trims")
        for lg in trims:
            L.append(f"- {_fmt_leg(lg)} — {lg.rationale}")
            for c in lg.caveats:
                L.append(f"   \u26a0\ufe0f {c}")

    # sequence
    L.append("\n## Sequence")
    L.append(f"- **Now:** {', '.join(r.sequence_now) if r.sequence_now else '(none)'}")
    if r.sequence_later:
        for tk, reason in r.sequence_later:
            L.append(f"- **Later:** {tk} — {reason}")

    # funding summary
    if r.funding:
        f = r.funding
        L.append("\n## Funding (one pool, spent once)")
        L.append(f"pool {_fmt_usd(f.pool_total_usd)} · allocated {_fmt_usd(f.allocated_usd)} · "
                 f"remaining {_fmt_usd(f.remaining_usd)} · shortfall {_fmt_usd(f.shortfall_usd)}")

    # concentration rail
    if r.rail_status != "off":
        L.append(f"\n## Concentration rail: ON [{r.rail_status}]")
        if r.rail_violations:
            L += [f"- \u26d4 {v}" for v in r.rail_violations]
        else:
            L.append("- within limits")
    # (when off, we say nothing — that's the default)

    # target vs current (context only)
    movers = {lg.ticker for lg in r.legs}
    interesting = [row for row in r.target_vs_current
                   if row.ticker in movers or abs(row.gap_pct) >= 1.0]
    if interesting:
        L.append("\n## Target vs current (gaps = context, not triggers)")
        L.append("| Name | Tier | Now | Eff* | Target | Gap | Status |")
        L.append("|---|---|---:|---:|---:|---:|---|")
        for row in interesting:
            L.append(f"| {row.ticker} | {row.tier or ('ETF' if row.is_etf else '—')} | "
                     f"{row.current_pct:.1f}% | {row.effective_current_pct:.1f}% | "
                     f"{row.target_pct:.1f}% | {row.gap_pct:+.1f}% | {row.status} |")
        L.append("\n_*Eff = direct holding + look-through of the wrappers you keep._")

    if r.other_left_alone:
        L.append("\n## Left alone (not in the AI model — incl. MONITOR sleeves)")
        L.append("- " + ", ".join(sorted(r.other_left_alone)))

    if r.notes:
        L.append("\n## Notes")
        L += [f"- {n}" for n in r.notes]
    return "\n".join(L)


# ===========================================================================
# ENTRY POINT
# ===========================================================================
def reallocate(*, feed: Optional[dict] = None, positions: Optional[list] = None,
               total_book_value: float, model: Optional[TargetWeightModel] = None,
               dials: Optional[Dials] = None, run_up: Optional[dict] = None,
               as_of: str = "") -> tuple:
    """One call -> (ReallocationResult, markdown). Defaults = your Working Model."""
    res = plan_reallocation(feed=feed, positions=positions, total_book_value=total_book_value,
                            model=model, dials=dials, run_up=run_up, as_of=as_of)
    return res, format_reallocation(res)


# ===========================================================================
# REFINEMENT BACKLOG (v1 ships; refine live)
#   - GRNY/GRNJ broad-reservoir AI fraction is treated as fully net-AI-increasing;
#     a future pass could net only its ~IT-weight fraction as factor-flat.
#   - live pretrade_gate.evaluate wiring is a hook; the funded=AMBER / net-new=RED
#     logic is inline. Wire the real gate in integration.
#   - run-up tags come from a passed-in {ticker: 1M%} map (cockpit/UW supplies it);
#     a future pass could read the feed's rotation tags directly.
#   - correlated-name catalyst gating only gates the explicitly-named ticker; a
#     future pass could propagate AVGO's gate to correlated names automatically.
# ===========================================================================


if __name__ == "__main__":
    import argparse, json as _json, sys as _sys
    ap = argparse.ArgumentParser(description="Reallocate — funded AI target-weight rotation (CANDIDATES).")
    ap.add_argument("--feed"); ap.add_argument("--positions"); ap.add_argument("--book", type=float)
    ap.add_argument("--run-up", help="path to {ticker: 1M run-up %%} json")
    ap.add_argument("--as-of", default="")
    a = ap.parse_args()
    if a.book and (a.feed or a.positions):
        feed = _json.load(open(a.feed)) if a.feed else None
        pos = _json.load(open(a.positions)) if a.positions else None
        run_up = _json.load(open(a.run_up)) if a.run_up else None
        res, md = reallocate(feed=feed, positions=pos, total_book_value=a.book,
                             run_up=run_up, as_of=a.as_of)
        print(md)
    else:
        print("usage: python3 reallocate.py --positions pos.json --book 1921934 [--run-up runup.json]")
        print("run selftest: python3 test_reallocate_rebuild.py")
