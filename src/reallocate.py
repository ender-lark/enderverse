#!/usr/bin/env python3
"""
reallocate.py — framework-aware whole-book reallocation (in-session callable)

WHAT THIS IS
    The in-session sibling of the Conviction Cockpit: a DECISION tool, not a
    routine. Looks at the whole book and proposes a TARGET reallocation —
    which names to size up, which to trim, and how to fund it — as a set of
    CANDIDATE legs (P-NO-FILL-NO-FACT). Tax-agnostic by request.

NOT A NAIVE REBALANCER (the whole point — CI v12.2 §7-D)
    Two moves a dumb rebalancer makes are FORBIDDEN here and are made
    structurally impossible by the contracts below:
      1. Never trim the high-conviction AI/semis CORE below conviction, and
         never flag it "overweight -> trim". Only ABOVE_CEILING names are
         trim-eligible, so in-band / below core is never touched.
      2. Never ADD to MONITOR-stance sleeves (crypto/ETH, nuclear/uranium,
         critical-minerals) to close a gap. MONITOR names never appear as a
         leg (calibrate() suppresses them; the validator rejects any leg that
         is MONITOR-classed).
    Source-gated rotation AMONG high-conviction sleeves IS allowed (the
    SMH/MAGS -> XLF/GS/GOOGL move): each leg carries its own source tag
    (FUNDING-SEQUENCE-REQUIRED). That is planner logic (Chunk 2).

ARCHITECTURE (reuses tested engines — NOT a from-scratch sizer)
    diagnosis  : conviction_sizing_calibrator.calibrate(positions, theses, total)
                 -> per-name floor/ceiling/gap classification + MONITOR
                    suppression + source discount + Deepwork flag.
    sleeves    : portfolio_factor_exposure.analyze(...) (Chunk 2, rotation rule)
    gate       : pretrade_gate.evaluate(...) on any leg >= $25K (Chunk 3)
    input      : the cockpit FEED (holdings/`pct`/sleeve `cat`) + theses, OR
                 positions[{ticker, market_value}] directly.

BUILD STATUS
    Chunk 1 (THIS FILE so far): contracts (Leg / ReallocationResult),
        sleeve classifier, FEED adapter, schema validator.
    Chunk 2 (later): planner core — trim<->add pairing, funding, rotation rule.
    Chunk 3 (later): pretrade_gate wiring + output assembly (table + moves).
    Chunk 4 (later): integrate the callable + ship.

The schema validator (validate_reallocation) is the Contract-test at this
seam: a downstream planner CANNOT silently emit a leg that breaks the
framework — the bad shape is rejected here.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional

# Single source of truth for the size bands + untiered default — imported, not
# re-declared, so Reallocate can never drift from the calibrator.
#   T1 Generational 8-12% · T2 High-conv 4-7% · T3 Tactical 1.5-3% · T4 Spec 0-1%
from conviction_sizing_calibrator import TIER_BANDS, UNTIERED_DEFAULT, calibrate

# ===========================================================================
# CONSTANTS
# ===========================================================================

GATE_NOTIONAL_THRESHOLD = 25_000.0     # any leg >= this -> pretrade_gate (Chunk 3)
RECONCILE_TOL_PCT = 0.5                 # Sum(target%)+cash% must be within this of 100
CEILING_TOL_PCT = 0.05                  # rounding slack on ceiling-cap checks

# Sleeve classification — factor-tag buckets (lowercase). CORE takes precedence
# over thematic when a name carries both (e.g., VOLT = nuclear + ai_complex
# -> CORE because of ai_complex). v1 heuristic; operator-overridable. See the
# REFINEMENT BACKLOG note at the bottom.
CORE_FACTORS = {"ai_complex", "semiconductors", "software"}
OTHER_HC_FACTORS = {"financials", "cyclicals", "energy", "oil_services"}
THEMATIC_FACTORS = {
    "crypto", "eth", "nuclear", "uranium", "critical_minerals",
    "rare_earth", "gold",
}

# Sleeve classes
CLS_CORE = "CORE"                          # high-conviction AI/semis — under-sizing lens
CLS_OTHER_HC = "OTHER_HIGH_CONVICTION"     # e.g. financials (XLF/GS) — rotation target
CLS_MONITOR = "MONITOR"                     # below floor on purpose — NEVER add/trim
CLS_TAIL = "TAIL_SPEC"                      # T4 / sub-scale — trim-for-funding eligible
CLS_UNDOCUMENTED = "UNDOCUMENTED"           # no thesis/tier — excluded from legs, nudge

LEG_CLASSES = {CLS_CORE, CLS_OTHER_HC, CLS_MONITOR, CLS_TAIL, CLS_UNDOCUMENTED}

# Classes a leg may legitimately carry (MONITOR + UNDOCUMENTED are never legged)
LEGGABLE_CLASSES = {CLS_CORE, CLS_OTHER_HC, CLS_TAIL}

ADD = "ADD"
TRIM = "TRIM"

SOURCE_TAG_PREFILLED = "PREFILLED"                       # from thesis.source
SOURCE_TAG_REQUIRED = "REQUIRED"                         # operator must supply
SOURCE_TAG_ROTATION = "ROTATION_RATIONALE_REQUIRED"      # cross-sleeve rotation

# What SIZED a leg's target (the authority for its target_pct). TIER_BAND is the
# default v1 behavior (size toward the tier floor/ceiling). EXPLICIT_TARGET means
# the operator handed in a per-name target_weights map and THAT weight is binding
# — it overrides the tier band (e.g. promote NVDA to 10% past its T2 ceiling, or
# trim/exit a CORE name the operator has consciously de-convicted). The validator
# relaxes the tier-ceiling checks for EXPLICIT_TARGET legs but keeps every safety
# invariant, and additionally pins each explicit leg to the operator's map value.
SIZING_TIER_BAND = "TIER_BAND"
SIZING_EXPLICIT_TARGET = "EXPLICIT_TARGET"

# A funded rotation is "net-factor-neutral" on a factor when the $ added to that
# factor is matched (or exceeded) by the $ trimmed from it — so net exposure does
# not rise. Below this tolerance (in pp of book) the plan's net delta for a factor
# reads as flat-or-down, which is how an in-isolation pretrade_gate
# INCREMENTAL_FACTOR_CONCENTRATION RED on a single add leg should be re-read
# (AMBER / override-and-log) when the add is funded by a same-factor trim.
NET_FACTOR_FLAT_TOL_PCT = 0.5      # <= 0.5pp of book net == "did not raise factor"

# ETF look-through table (v1, approximate, OPERATOR-OVERRIDABLE via the
# `etf_lookthrough` arg). Holding an ETF AND sizing its constituents as singles
# double-counts that factor. Weights are the ETF's approximate constituent % (the
# SMH row encodes the Notion model's "SMH ~= 13% NVDA + AVGO/TSM/AMD/MU"). Used
# only to WARN + show the look-through-adjusted true single-name exposure; it does
# NOT silently resize anything (P-NO-FILL-NO-FACT).
ETF_LOOKTHROUGH = {
    "SMH": {
        "factor": "semiconductors",
        "constituents": {"NVDA": 0.13, "TSM": 0.10, "AVGO": 0.09,
                         "AMD": 0.05, "MU": 0.04},
    },
}


# ===========================================================================
# HELPERS
# ===========================================================================

def norm_tier(tier_raw: Optional[str]) -> str:
    """'T1 Generational' / 't1' / 'T1' -> 'T1'. Empty/unknown -> '' (untiered)."""
    if not tier_raw:
        return ""
    tok = str(tier_raw).strip().upper().split()[0]
    return tok if tok in TIER_BANDS else ""


def tier_band(tier: str) -> tuple[float, float]:
    """Return (floor_pct, ceiling_pct) as PERCENT (e.g. (8.0, 12.0)) for a tier.

    Untiered -> the UNTIERED_DEFAULT band. Bands come from the calibrator as
    fractions; we return percent for human-facing leg fields.
    """
    t = tier if tier in TIER_BANDS else UNTIERED_DEFAULT
    lo, hi = TIER_BANDS[t]
    return round(lo * 100.0, 4), round(hi * 100.0, 4)


def _factors_of(thesis: Optional[dict]) -> set[str]:
    if not thesis:
        return set()
    return {str(f).strip().lower() for f in (thesis.get("factor_tags") or []) if f}


# ===========================================================================
# SLEEVE CLASSIFIER
# ===========================================================================

def classify_holding(thesis: Optional[dict]) -> str:
    """Classify one holding into a sleeve class from its thesis.

    Order matters (safety first):
      1. MONITOR stance      -> CLS_MONITOR   (never add/trim)
      2. no thesis / untiered -> CLS_UNDOCUMENTED (excluded from legs; nudge —
         do NOT let it default to T3 and generate a spurious trim of a big
         undocumented core name like MSFT/AVGO).
      3. T4                  -> CLS_TAIL
      4. CORE factor present -> CLS_CORE      (ai_complex/semis/software)
      5. OTHER_HC factor     -> CLS_OTHER_HIGH_CONVICTION
      6. otherwise (tiered, factor-bearing) -> CLS_OTHER_HIGH_CONVICTION
    """
    if not thesis:
        return CLS_UNDOCUMENTED
    stance = (thesis.get("stance") or "").strip().upper()
    if stance == "MONITOR":
        return CLS_MONITOR
    tier = norm_tier(thesis.get("tier"))
    if tier == "":
        return CLS_UNDOCUMENTED
    if tier == "T4":
        return CLS_TAIL
    factors = _factors_of(thesis)
    if factors & CORE_FACTORS:
        return CLS_CORE
    if factors & OTHER_HC_FACTORS:
        return CLS_OTHER_HC
    # Tiered name carrying only thematic factors but NOT MONITOR-stance is
    # unusual; treat as other-high-conviction (operator can re-stance it).
    return CLS_OTHER_HC


@dataclass
class HoldingClass:
    """Per-name classification row (the classifier's output)."""
    ticker: str
    sleeve: str                  # FEED `cat` label (display grouping)
    sleeve_class: str            # one of LEG_CLASSES
    tier: str                    # normalized T1-T4 ('' if untiered)
    current_pct: float           # % of book
    floor_pct: float
    ceiling_pct: float
    source: Optional[str] = None
    factors: list[str] = field(default_factory=list)
    leggable: bool = False       # may this name appear as a trim/add leg?
    note: Optional[str] = None


def classify_book(
    positions: list[dict],
    theses: list[dict],
) -> list[HoldingClass]:
    """Join positions (carrying `_pct` + `_sleeve` from the FEED, or just
    ticker) with theses and classify each name.

    `positions` rows use: ticker, optional `_pct` (else 0), optional `_sleeve`.
    """
    by_ticker_th = {(t.get("ticker") or "").upper(): t for t in theses}
    out: list[HoldingClass] = []
    for p in positions:
        tk = (p.get("ticker") or "").upper().strip()
        if not tk:
            continue
        th = by_ticker_th.get(tk)
        cls = classify_holding(th)
        tier = norm_tier(th.get("tier")) if th else ""
        floor_pct, ceiling_pct = tier_band(tier)
        leggable = cls in LEGGABLE_CLASSES
        note = None
        if cls == CLS_UNDOCUMENTED:
            note = "no thesis / untiered — excluded from reallocation; add a tier line"
        elif cls == CLS_MONITOR:
            note = "MONITOR stance — intentionally below floor; never add/trim here"
        out.append(HoldingClass(
            ticker=tk,
            sleeve=p.get("_sleeve") or (th.get("lane") if th else None) or "Unclassified",
            sleeve_class=cls,
            tier=tier,
            current_pct=float(p.get("_pct") or 0.0),
            floor_pct=floor_pct,
            ceiling_pct=ceiling_pct,
            source=(th.get("source") if th else None),
            factors=sorted(_factors_of(th)),
            leggable=leggable,
            note=note,
        ))
    return out


# ===========================================================================
# FEED ADAPTER  (cockpit FEED -> engine inputs; single source of truth for %)
# ===========================================================================

def positions_from_feed(feed: dict, total_book_value: float) -> list[dict]:
    """Flatten the cockpit FEED `holdings` (sleeve-grouped) into positions.

    Each FEED position carries `t` (ticker), `pct` (% of book), `own`, `ty`;
    each group carries `cat` (sleeve label). We convert pct -> market_value
    using `total_book_value` so the calibrator's % == the FEED's % exactly
    (ONE denominator — the systems-engineer seam guard).
    """
    if total_book_value <= 0:
        raise ValueError("total_book_value must be > 0")
    rows: list[dict] = []
    for group in feed.get("holdings", []) or []:
        sleeve = group.get("cat")
        for p in group.get("pos", []) or []:
            tk = (p.get("t") or p.get("ticker") or "").upper().strip()
            if not tk:
                continue
            pct = float(p.get("pct") or 0.0)
            rows.append({
                "ticker": tk,
                "market_value": pct / 100.0 * total_book_value,
                "_pct": pct,
                "_sleeve": sleeve,
                "_owner": p.get("own"),
                "_ty": p.get("ty"),
            })
    return rows


def cash_pct_from_positions(positions: list[dict]) -> float:
    """Cash % = 100 - sum(holding %), floored at 0."""
    invested = sum(float(p.get("_pct") or 0.0) for p in positions)
    return max(0.0, round(100.0 - invested, 4))


# ===========================================================================
# CONTRACTS  (Leg + ReallocationResult)  — the shapes that flow downstream
# ===========================================================================

def _empty_gate(ticker: str, action: str, notional: float) -> dict:
    """A leg gate slot, mirroring the FEED `actions[].gate` shape. `result`
    is None until the live session fires pretrade_gate (Chunk 3)."""
    needs = notional >= GATE_NOTIONAL_THRESHOLD
    return {
        "needs_gate": needs,
        "ticker": ticker,
        "default_action": action,
        "preview": ("\U0001f7e1 size \u2192 gate" if needs else "no gate (< $25K)"),
        "result": None,            # filled live: GREEN/AMBER/RED + flags
    }


@dataclass
class Leg:
    """One CANDIDATE reallocation move. Never an executed trade."""
    leg_id: str
    action: str                  # ADD | TRIM
    ticker: str
    sleeve: str
    sleeve_class: str            # must be in LEGGABLE_CLASSES
    tier: str
    current_pct: float
    target_pct: float
    delta_pct: float             # target - current (signed)
    notional_usd: float          # abs $ of the move
    floor_pct: float
    ceiling_pct: float
    source_tag: Optional[str] = None
    source_tag_status: str = SOURCE_TAG_REQUIRED
    funds_leg_id: Optional[str] = None      # TRIM: the ADD it funds
    funded_by_leg_id: Optional[str] = None  # ADD: the TRIM funding it
    rotation: bool = False                  # part of a cross-sleeve rotation pair
    optional: bool = False                  # trims are optional/funding-gated
    deepwork: bool = False                  # T1 ADD -> always Deepwork
    rank: int = 0
    rationale: str = ""
    caveats: list[str] = field(default_factory=list)
    # --- target-weight mode (explicit per-name targets) ---
    binding: str = SIZING_TIER_BAND          # TIER_BAND (default) | EXPLICIT_TARGET
    factor_tags: list[str] = field(default_factory=list)
    net_factor_neutral: bool = False         # add funded by a same-factor trim
    net_factor_label: Optional[str] = None   # the shared factor, e.g. "ai_complex"
    stage_after: Optional[str] = None        # sequencing: gate-event to stage after
    gate: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.gate:
            self.gate = _empty_gate(self.ticker, self.action, self.notional_usd)


@dataclass
class TargetRow:
    """Target-vs-current for EVERY holding (moved or not). Drives the table +
    the reconciliation invariant (sum of target% + cash% ~= 100)."""
    ticker: str
    sleeve: str
    sleeve_class: str
    tier: str
    current_pct: float
    target_pct: float
    classification: str = ""     # CRITICALLY_BELOW/BELOW_FLOOR/IN_BAND/ABOVE_CEILING


@dataclass
class FundingSummary:
    trims_total_usd: float = 0.0
    adds_total_usd: float = 0.0
    cash_used_usd: float = 0.0           # cash DRAWN to help fund adds (>= 0)
    cash_freed_usd: float = 0.0          # surplus trims PARKED to cash (>= 0)
    shortfall_usd: float = 0.0
    unfunded_adds: list[str] = field(default_factory=list)


@dataclass
class ReallocationResult:
    as_of: str
    total_book_value: float
    cash_pct: float
    mode: dict                                   # {names, funding, scope, aggressiveness}
    legs: list[Leg] = field(default_factory=list)
    sub_threshold_legs: list[Leg] = field(default_factory=list)
    target_vs_current: list[TargetRow] = field(default_factory=list)
    funding: FundingSummary = field(default_factory=FundingSummary)
    monitor_left_alone: list[str] = field(default_factory=list)
    undocumented_excluded: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # --- target-weight mode artifacts (empty in tier-band mode) ---
    explicit_targets: dict = field(default_factory=dict)   # ticker -> target % (operator map)
    net_factor_delta: dict = field(default_factory=dict)   # factor -> signed $ net delta
    lookthrough: list[dict] = field(default_factory=list)  # ETF overlap findings
    # banners — always true; surfaced so the output can never be mistaken for
    # an execution-ready plan
    tax_agnostic: bool = True
    all_legs_are_candidates: bool = True

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# ===========================================================================
# SCHEMA VALIDATOR  (Contract-test at the seam — encodes the guardrails)
# ===========================================================================

_LEG_REQUIRED = (
    "leg_id", "action", "ticker", "sleeve", "sleeve_class", "tier",
    "current_pct", "target_pct", "delta_pct", "notional_usd",
    "floor_pct", "ceiling_pct", "source_tag_status", "gate",
)


def _validate_leg(leg: dict, idx: int) -> list[str]:
    e: list[str] = []
    tag = f"legs[{idx}]"
    for k in _LEG_REQUIRED:
        if k not in leg:
            e.append(f"{tag}: missing required field '{k}'")
    if e:
        return e  # can't reason further without the basics

    action = leg["action"]
    if action not in (ADD, TRIM):
        e.append(f"{tag}: action must be ADD|TRIM, got {action!r}")

    # MONITOR / UNDOCUMENTED may NEVER be a leg (safety guardrail)
    if leg["sleeve_class"] not in LEGGABLE_CLASSES:
        e.append(
            f"{tag}: sleeve_class {leg['sleeve_class']!r} is not leggable — "
            f"MONITOR/UNDOCUMENTED names must never appear as a leg"
        )

    if leg["notional_usd"] < 0:
        e.append(f"{tag}: notional_usd must be >= 0")

    cur, tgt = leg["current_pct"], leg["target_pct"]
    delta = leg["delta_pct"]
    if abs((tgt - cur) - delta) > 1e-6:
        e.append(f"{tag}: delta_pct {delta} != target-current {tgt - cur}")

    # Binding = what authorized this target. EXPLICIT_TARGET legs are driven by an
    # operator-supplied target_weights map and may legitimately sit outside the
    # tier band (NVDA promoted past its old ceiling; a CORE name consciously
    # de-convicted below its floor). For those we KEEP directionality + the >=0
    # bound + map-equality (checked in validate_reallocation), but skip the
    # tier-ceiling caps. TIER_BAND legs keep the full conservative-sizing rules.
    binding = leg.get("binding", SIZING_TIER_BAND)
    explicit = binding == SIZING_EXPLICIT_TARGET
    if binding not in (SIZING_TIER_BAND, SIZING_EXPLICIT_TARGET):
        e.append(f"{tag}: invalid binding {binding!r}")

    ceil = leg["ceiling_pct"]
    if action == ADD:
        if tgt <= cur:
            e.append(f"{tag}: ADD must increase weight (target>current)")
        if explicit:
            if tgt > 100.0 + CEILING_TOL_PCT:
                e.append(f"{tag}: ADD explicit target {tgt}% exceeds 100%")
        elif tgt > ceil + CEILING_TOL_PCT:
            e.append(f"{tag}: ADD target {tgt}% exceeds tier ceiling {ceil}%")
    elif action == TRIM:
        if tgt >= cur:
            e.append(f"{tag}: TRIM must decrease weight (target<current)")
        if explicit:
            # explicit trim/exit: only bound is target >= 0 (the operator's map is
            # the authority; below-floor de-conviction is a deliberate, caveated move)
            if tgt < -CEILING_TOL_PCT:
                e.append(f"{tag}: TRIM explicit target {tgt}% must be >= 0")
        else:
            # conservative-trim rule: never trim a name BELOW its ceiling
            if tgt < ceil - CEILING_TOL_PCT:
                e.append(
                    f"{tag}: TRIM target {tgt}% is below tier ceiling {ceil}% — "
                    f"trims fund from over-ceiling excess only, never below ceiling"
                )
            if cur <= ceil + CEILING_TOL_PCT:
                e.append(
                    f"{tag}: TRIM on {leg['ticker']} which is not above its ceiling "
                    f"({cur}% <= {ceil}%) — only ABOVE_CEILING names are trim-eligible"
                )

    # gate flag must match the $25K threshold exactly
    gate = leg["gate"] or {}
    if gate.get("needs_gate") != (leg["notional_usd"] >= GATE_NOTIONAL_THRESHOLD):
        e.append(f"{tag}: gate.needs_gate disagrees with the $25K threshold")

    # source tag must never be silently absent (FUNDING-SEQUENCE-REQUIRED)
    status = leg["source_tag_status"]
    if status not in (SOURCE_TAG_PREFILLED, SOURCE_TAG_REQUIRED, SOURCE_TAG_ROTATION):
        e.append(f"{tag}: invalid source_tag_status {status!r}")
    if status == SOURCE_TAG_PREFILLED and not leg.get("source_tag"):
        e.append(f"{tag}: source_tag_status PREFILLED but source_tag is empty")
    return e


def validate_reallocation(result: Any) -> list[str]:
    """Return a list of contract violations ([] == valid). Mirrors
    validators.validate_cockpit_feed's error-list style.

    Accepts a ReallocationResult or its as_dict() form.
    """
    if isinstance(result, ReallocationResult):
        result = result.as_dict()
    if not isinstance(result, dict):
        return ["reallocation result is not a dict"]

    e: list[str] = []

    # banners — must be present and true
    if result.get("tax_agnostic") is not True:
        e.append("tax_agnostic banner must be True")
    if result.get("all_legs_are_candidates") is not True:
        e.append("all_legs_are_candidates banner must be True")

    legs = result.get("legs", []) or []
    sub_legs = result.get("sub_threshold_legs", []) or []
    all_legs = list(legs) + list(sub_legs)
    for i, leg in enumerate(all_legs):
        e.extend(_validate_leg(leg, i))

    # reconciliation: sum(target%) over EVERY holding + cash% ~= 100
    rows = result.get("target_vs_current", [])
    if rows:
        tgt_sum = sum(float(r.get("target_pct") or 0.0) for r in rows)
        cash = float(result.get("cash_pct") or 0.0)
        total = tgt_sum + cash
        if abs(total - 100.0) > RECONCILE_TOL_PCT:
            e.append(
                f"reconciliation: sum(target%)={tgt_sum:.2f} + cash%={cash:.2f} "
                f"= {total:.2f}, not ~100 (tol {RECONCILE_TOL_PCT})"
            )
        # MONITOR / undocumented rows must hold target == current (untouched)
        legged = {l.get("ticker") for l in all_legs}
        for r in rows:
            if r.get("sleeve_class") in (CLS_MONITOR, CLS_UNDOCUMENTED):
                if r.get("ticker") in legged:
                    e.append(f"{r.get('ticker')}: {r.get('sleeve_class')} name appears in legs")
                if abs(float(r.get("target_pct") or 0) - float(r.get("current_pct") or 0)) > CEILING_TOL_PCT:
                    e.append(
                        f"{r.get('ticker')}: {r.get('sleeve_class')} target moved "
                        f"from current — must be left untouched"
                    )

    # explicit-target contract (target-weight mode): every EXPLICIT_TARGET leg
    # must move its name to EXACTLY the operator's mapped weight, and must have a
    # map entry at all. This is what makes "the planner can never invent a CORE
    # trim" checkable at the seam: an explicit leg is provably traceable to the
    # operator's target_weights, never to planner discretion.
    explicit_targets = result.get("explicit_targets") or {}
    if explicit_targets:
        emap = {str(k).upper(): float(v) for k, v in explicit_targets.items()}
        for leg in all_legs:
            if leg.get("binding") != SIZING_EXPLICIT_TARGET:
                continue
            tk = (leg.get("ticker") or "").upper()
            if tk not in emap:
                e.append(
                    f"{tk}: EXPLICIT_TARGET leg has no entry in explicit_targets "
                    f"map — explicit legs must trace to the operator's targets")
            elif abs(float(leg.get("target_pct") or 0.0) - emap[tk]) > CEILING_TOL_PCT:
                e.append(
                    f"{tk}: EXPLICIT_TARGET leg target {leg.get('target_pct')}% != "
                    f"operator map {emap[tk]}% — explicit legs hit the exact target")

    # funding coherence: sources used (trims + cash_used) == uses (funded adds +
    # cash_freed). shortfall is UNMET add demand, reported separately — never a
    # source. cash_freed defaults to 0, so tier-band mode is unchanged.
    f = result.get("funding") or {}
    adds = float(f.get("adds_total_usd") or 0.0)
    trims = float(f.get("trims_total_usd") or 0.0)
    cash_used = float(f.get("cash_used_usd") or 0.0)
    cash_freed = float(f.get("cash_freed_usd") or 0.0)
    shortfall = float(f.get("shortfall_usd") or 0.0)
    if adds or trims or cash_used or cash_freed or shortfall:
        bal = (trims + cash_used) - (adds + cash_freed)
        tol = max(50.0, 0.005 * float(result.get("total_book_value") or 0.0))
        if abs(bal) > tol:
            e.append(
                f"funding: sources trims({trims:.0f})+cash_used({cash_used:.0f}) != "
                f"uses adds({adds:.0f})+cash_freed({cash_freed:.0f}) "
                f"[bal {bal:.0f}, tol {tol:.0f}]"
            )
        if shortfall < 0:
            e.append(f"funding: shortfall_usd must be >= 0, got {shortfall:.0f}")
        if cash_used < 0:
            e.append(f"funding: cash_used_usd must be >= 0, got {cash_used:.0f}")
        if cash_freed < 0:
            e.append(f"funding: cash_freed_usd must be >= 0, got {cash_freed:.0f}")
    return e


def is_valid_reallocation(result: Any) -> bool:
    return not validate_reallocation(result)


def assert_valid_reallocation(result: Any) -> None:
    errs = validate_reallocation(result)
    if errs:
        raise ValueError("invalid reallocation result:\n  - " + "\n  - ".join(errs))


# ===========================================================================
# PLANNER CORE  (Chunk 2)  — ConvictionReport -> ranked, paired CANDIDATE legs
# ===========================================================================

DEFAULT_MODE = {
    "names": "resize_only",        # v1: re-weight current holdings only
    "funding": "cash_neutral",     # adds funded by trims
    "scope": "aggregate",          # owner-aggregate (per-account = GAP-F)
    "aggressiveness": "material_only",
}

# ADD priority: CORE under-sizing is the documented failure mode -> rank first.
_CLASS_PRIORITY = {CLS_CORE: 3, CLS_OTHER_HC: 2, CLS_TAIL: 1}
_CLASSIF_PRIORITY = {"CRITICALLY_BELOW": 2, "BELOW_FLOOR": 1}
_MACRO_BUMP = {"HIGH": 0.5, "NORMAL": 0.0, "LOW": -0.5}


def _normalize_positions(positions: list[dict], book: float) -> list[dict]:
    """Ensure each position carries BOTH market_value (for calibrate) and _pct
    (for the classifier), derived from whichever is present."""
    out = []
    for p in positions:
        q = dict(p)
        mv, pct = q.get("market_value"), q.get("_pct")
        if (pct in (None, 0)) and mv:
            q["_pct"] = float(mv) / book * 100.0
        if (mv in (None, 0)) and pct:
            q["market_value"] = float(pct) / 100.0 * book
        out.append(q)
    return out


def _classes_by_ticker(positions: list[dict], theses: list[dict]) -> dict:
    return {h.ticker: h for h in classify_book(positions, theses)}


def _classif_by_ticker(report) -> dict:
    d = {}
    for bucket in (report.critically_below, report.below_floor, report.in_band,
                   report.above_ceiling, report.monitor_suppressed):
        for g in bucket:
            d[g.ticker] = g.classification
    return d


def _is_no_thesis(gap) -> bool:
    return "no_thesis_row" in getattr(gap, "flags", [])


def _build_add_candidates(report, cbt: dict, book: float) -> list[dict]:
    """ADD candidates = below-floor / critically-below, documented, non-MONITOR.
    (MONITOR is already isolated in report.monitor_suppressed; we additionally
    drop calibrate's no_thesis_row names — the undocumented guard.)"""
    out = []
    for gap in list(report.critically_below) + list(report.below_floor):
        if _is_no_thesis(gap):
            continue
        hc = cbt.get(gap.ticker)
        scls = hc.sleeve_class if hc else CLS_OTHER_HC
        if scls not in LEGGABLE_CLASSES:
            continue
        cur = gap.current_pct * 100.0
        floor = gap.floor_pct * 100.0
        ceil = gap.ceiling_pct * 100.0
        disc = gap.source_discount or 1.0
        # size toward floor, scaled by the source hit-rate discount (dormant at
        # n<15 -> disc=1.0 today); never above ceiling.
        target = min(cur + disc * (floor - cur), ceil)
        delta = round(target - cur, 4)
        notional = round(gap.discounted_gap_value, 2)
        if delta <= 0 or notional <= 0:
            continue
        out.append({
            "ticker": gap.ticker, "sleeve": (hc.sleeve if hc else "Unclassified"),
            "sleeve_class": scls, "tier": gap.tier, "current_pct": round(cur, 4),
            "target_pct": round(target, 4), "delta_pct": delta, "notional": notional,
            "floor_pct": round(floor, 4), "ceiling_pct": round(ceil, 4),
            "source": gap.source_at_entry, "classification": gap.classification,
            "macro_urgency": gap.macro_urgency, "deepwork": gap.tier == "T1",
        })
    return out


def _build_trim_candidates(report, cbt: dict, book: float) -> list[dict]:
    """TRIM/funding candidates = above-ceiling, documented, non-MONITOR. Only
    the excess ABOVE ceiling is fundable (never trim below ceiling)."""
    out = []
    for gap in report.above_ceiling:
        if _is_no_thesis(gap):
            continue
        hc = cbt.get(gap.ticker)
        scls = hc.sleeve_class if hc else CLS_CORE
        if scls not in LEGGABLE_CLASSES:
            continue
        cur = gap.current_pct * 100.0
        ceil = gap.ceiling_pct * 100.0
        excess_pct = max(0.0, cur - ceil)
        excess_usd = excess_pct / 100.0 * book
        if excess_usd <= 0:
            continue
        out.append({
            "ticker": gap.ticker, "sleeve": (hc.sleeve if hc else "Unclassified"),
            "sleeve_class": scls, "tier": gap.tier, "current_pct": round(cur, 4),
            "ceiling_pct": round(ceil, 4), "floor_pct": round(gap.floor_pct * 100, 4),
            "excess_pct": round(excess_pct, 4), "excess_usd": round(excess_usd, 2),
            "remaining_usd": round(excess_usd, 2), "source": gap.source_at_entry,
        })
    out.sort(key=lambda c: -c["excess_usd"])   # draw from most-over-ceiling first
    return out


def _add_sort_key(c: dict):
    return (
        _CLASS_PRIORITY.get(c["sleeve_class"], 0)
        + _MACRO_BUMP.get(c.get("macro_urgency", "NORMAL"), 0.0),
        _CLASSIF_PRIORITY.get(c["classification"], 0),
        c["notional"],
    )


def _add_rationale(ac: dict, rotation: bool, primary: Optional[dict]) -> str:
    base = (f"{ac['ticker']} is {ac['classification'].replace('_', ' ').lower()} its "
            f"{ac['tier']} band ({ac['floor_pct']:.1f}-{ac['ceiling_pct']:.1f}%); "
            f"size toward floor (+{ac['delta_pct']:.2f}pp).")
    if rotation and primary:
        base += (f" Funded by rotating out of over-ceiling {primary['ticker']} "
                 f"({primary['sleeve']}) -> CROSS-SLEEVE: confirm the rotation "
                 f"rationale and tag this leg's source.")
    return base


def _trim_rationale(tc: dict, ac: dict, draw: float) -> str:
    return (f"{tc['ticker']} is {tc['excess_pct']:.1f}pp over its {tc['tier']} "
            f"ceiling ({tc['ceiling_pct']:.1f}%); trim ${draw:,.0f} to fund "
            f"{ac['ticker']} (stays above ceiling). OPTIONAL — don't trim a "
            f"winner for tidiness.")


def plan_reallocation(*, positions: Optional[list[dict]] = None,
                      feed: Optional[dict] = None, theses: list[dict],
                      total_book_value: float, mode: Optional[dict] = None,
                      macro: Optional[dict] = None,
                      source_rates: Optional[dict] = None,
                      materiality_pct: float = 1.0,
                      materiality_usd: float = GATE_NOTIONAL_THRESHOLD,
                      expected_cash_pct: Optional[float] = None,
                      target_weights: Optional[dict] = None,
                      sequence_events: Optional[dict] = None,
                      etf_lookthrough: Optional[dict] = None,
                      cash_reserve_pct: float = 0.0,
                      as_of: str = "") -> ReallocationResult:
    """Build a framework-aware reallocation as CANDIDATE legs. Reuses
    calibrate() for the floor/ceiling diagnosis + MONITOR suppression; this
    function adds the trim<->add pairing, funding, and rotation rule.

    Two modes:
      * TIER-BAND (default): size below-band names toward their tier floor,
        funded by above-ceiling excess. Unchanged v1 behavior.
      * TARGET-WEIGHT (when `target_weights` {ticker: % of book} is given): plan
        the funded trim<->add legs to move current weights to those EXACT
        targets. The explicit map drives the plan; the tier band is only used for
        the floor/ceiling diagnosis (display + below-conviction caveats).

    Provide `feed` (cockpit FEED) OR `positions` [{ticker, market_value|_pct}].
    """
    if feed is not None and positions is None:
        positions = positions_from_feed(feed, total_book_value)
    if positions is None:
        raise ValueError("provide positions or feed")
    if total_book_value <= 0:
        raise ValueError("total_book_value must be > 0")
    book = float(total_book_value)
    mode = {**DEFAULT_MODE, **(mode or {})}
    positions = _normalize_positions(positions, book)

    if target_weights:
        return plan_target_reallocation(
            positions=positions, theses=theses, total_book_value=book,
            target_weights=target_weights, mode=mode, macro=macro,
            source_rates=source_rates, materiality_pct=materiality_pct,
            materiality_usd=materiality_usd, expected_cash_pct=expected_cash_pct,
            sequence_events=sequence_events, etf_lookthrough=etf_lookthrough,
            cash_reserve_pct=cash_reserve_pct, as_of=as_of)

    report = calibrate(positions, theses, book, macro, source_rates)
    cbt = _classes_by_ticker(positions, theses)
    classif = _classif_by_ticker(report)

    add_cands = _build_add_candidates(report, cbt, book)
    trim_cands = _build_trim_candidates(report, cbt, book)
    add_cands.sort(key=_add_sort_key, reverse=True)
    trim_capacity = sum(t["remaining_usd"] for t in trim_cands)

    legs: list[Leg] = []
    unfunded: list[dict] = []
    funded_add_usd = 0.0
    trimmed_usd = 0.0
    cash_used = 0.0                         # cash-neutral + cash-fixed -> 0 (v1)
    seq = 1

    for ac in add_cands:
        need = ac["notional"]
        if need > trim_capacity + 1e-6:     # cash-neutral: can't fund -> defer
            unfunded.append({"ticker": ac["ticker"], "needed_usd": round(need, 2),
                             "sleeve": ac["sleeve"], "tier": ac["tier"]})
            continue
        add_id = f"A{seq}"; seq += 1
        # draw from trims, largest-excess first
        funders: list[list] = []
        remaining = need
        for tc in trim_cands:
            if remaining <= 1e-6:
                break
            draw = min(tc["remaining_usd"], remaining)
            if draw <= 1e-9:
                continue
            tc["remaining_usd"] -= draw
            remaining -= draw
            funders.append([tc, draw])
        trim_capacity -= need
        funded_add_usd += need
        funders.sort(key=lambda x: -x[1])
        primary = funders[0][0] if funders else None
        rotation = bool(primary and primary["sleeve_class"] != ac["sleeve_class"])

        trim_legs: list[Leg] = []
        for tc, draw in funders:
            trim_id = f"T{seq}"; seq += 1
            draw_pct = round(draw / book * 100.0, 4)
            tgt = round(tc["current_pct"] - draw_pct, 4)
            if tgt < tc["ceiling_pct"] - CEILING_TOL_PCT:   # never below ceiling
                tgt = tc["ceiling_pct"]
            trimmed_usd += draw
            trim_legs.append(Leg(
                leg_id=trim_id, action=TRIM, ticker=tc["ticker"], sleeve=tc["sleeve"],
                sleeve_class=tc["sleeve_class"], tier=tc["tier"],
                current_pct=tc["current_pct"], target_pct=tgt,
                delta_pct=round(tgt - tc["current_pct"], 4), notional_usd=round(draw, 2),
                floor_pct=tc["floor_pct"], ceiling_pct=tc["ceiling_pct"],
                source_tag=tc["source"],
                source_tag_status=(SOURCE_TAG_PREFILLED if tc["source"] else SOURCE_TAG_REQUIRED),
                funds_leg_id=add_id, rotation=(tc["sleeve_class"] != ac["sleeve_class"]), optional=True,
                caveats=["Over-ceiling winner — trim is OPTIONAL, sized only to fund this add."],
                rationale=_trim_rationale(tc, ac, draw),
            ))

        add_status = SOURCE_TAG_ROTATION if rotation else (
            SOURCE_TAG_PREFILLED if ac["source"] else SOURCE_TAG_REQUIRED)
        legs.append(Leg(
            leg_id=add_id, action=ADD, ticker=ac["ticker"], sleeve=ac["sleeve"],
            sleeve_class=ac["sleeve_class"], tier=ac["tier"],
            current_pct=ac["current_pct"], target_pct=ac["target_pct"],
            delta_pct=ac["delta_pct"], notional_usd=round(need, 2),
            floor_pct=ac["floor_pct"], ceiling_pct=ac["ceiling_pct"],
            source_tag=ac["source"], source_tag_status=add_status,
            funded_by_leg_id=(trim_legs[0].leg_id if trim_legs else None),
            rotation=rotation, deepwork=ac["deepwork"],
            rationale=_add_rationale(ac, rotation, primary),
        ))
        legs.extend(trim_legs)

    # ---- materiality split (surface small legs separately, never hide) ----
    def _material(l: Leg) -> bool:
        return l.notional_usd >= materiality_usd or abs(l.delta_pct) >= materiality_pct

    if mode["aggressiveness"] == "material_only":
        main_legs = [l for l in legs if _material(l)]
        sub_legs = [l for l in legs if not _material(l)]
    else:
        main_legs, sub_legs = list(legs), []
    for i, l in enumerate(main_legs, 1):
        l.rank = i
    for i, l in enumerate(sub_legs, 1):
        l.rank = i

    # ---- target-vs-current for EVERY holding (overlay net leg deltas) ----
    delta_by_ticker: dict = {}
    for l in legs:
        delta_by_ticker[l.ticker] = delta_by_ticker.get(l.ticker, 0.0) + l.delta_pct
    rows = [
        TargetRow(
            ticker=hc.ticker, sleeve=hc.sleeve, sleeve_class=hc.sleeve_class,
            tier=hc.tier, current_pct=round(hc.current_pct, 4),
            target_pct=round(hc.current_pct + delta_by_ticker.get(hc.ticker, 0.0), 4),
            classification=classif.get(hc.ticker, ""),
        )
        for hc in cbt.values()
    ]

    funding = FundingSummary(
        trims_total_usd=round(trimmed_usd, 2), adds_total_usd=round(funded_add_usd, 2),
        cash_used_usd=round(cash_used, 2),
        shortfall_usd=round(sum(u["needed_usd"] for u in unfunded), 2),
        unfunded_adds=[u["ticker"] for u in unfunded],
    )
    monitor_left = [g.ticker for g in report.monitor_suppressed]
    undoc = [g.ticker for g in report.no_thesis if "monitor_suppressed" not in g.flags]

    over_ceiling_hc = [r for r in rows if r.classification == "ABOVE_CEILING"
                       and r.sleeve_class in (CLS_CORE, CLS_OTHER_HC)]
    has_material_trim = any(l.action == TRIM for l in main_legs)
    notes: list[str] = []
    if not main_legs and not sub_legs and not unfunded and not over_ceiling_hc:
        notes.append("No reallocation indicated — every documented, non-MONITOR name is within its tier band.")
    if not main_legs and sub_legs:
        notes.append(f"No move clears the materiality cut (>={materiality_pct:g}pp or "
                     f">=${materiality_usd:,.0f}) — {len(sub_legs)} minor move(s) under sub-threshold.")
    if over_ceiling_hc and not has_material_trim:
        over = ", ".join(f"{r.ticker} (~{r.current_pct:.1f}% vs {tier_band(r.tier)[1]:.0f}% ceiling)"
                         for r in over_ceiling_hc)
        notes.append("Over-ceiling capacity exists but no material add needs it — trims NOT "
                     f"recommended (winners; only trim to fund a real add): {over}.")
    if unfunded:
        notes.append("Cash-neutral shortfall — highest-priority adds funded first; the rest "
                     "are unfunded candidates (no capital invented).")

    cash_pct = cash_pct_from_positions(positions)
    coverage = round(sum(float(p.get("_pct") or 0.0) for p in positions), 2)
    warnings: list[str] = []
    if coverage < 95.0:
        warnings.append(
            f"FEED covers only {coverage:.1f}% of the book by weight ({100 - coverage:.1f}% "
            f"reads as cash/untracked). If the FEED rolls a long tail into 'Other holdings', "
            f"weights are incomplete — verify against the Latest Portfolio before acting.")
    if expected_cash_pct is not None and abs(cash_pct - expected_cash_pct) > 1.0:
        warnings.append(
            f"FEED-implied cash {cash_pct:.2f}% differs from stated {expected_cash_pct:.2f}% "
            f"— the FEED may be missing holdings; verify before acting.")

    return ReallocationResult(
        as_of=as_of, total_book_value=book, cash_pct=cash_pct,
        mode=mode, legs=main_legs, sub_threshold_legs=sub_legs, target_vs_current=rows,
        funding=funding, monitor_left_alone=monitor_left, undocumented_excluded=undoc,
        notes=notes, warnings=warnings,
    )


def summary_line(r: ReallocationResult) -> str:
    return (f"REALLOCATE (tax-agnostic · CANDIDATES): {len(r.legs)} material leg(s), "
            f"{len(r.sub_threshold_legs)} sub-threshold, "
            f"{len(r.funding.unfunded_adds)} unfunded; MONITOR untouched: "
            f"{', '.join(r.monitor_left_alone) or 'none'}.")


# ===========================================================================
# TARGET-WEIGHT PLANNER  — explicit per-name targets -> funded trim<->add legs
#
# The operator hands in `target_weights` {ticker: % of book}; we plan the funded
# legs that move CURRENT weights to those EXACT targets. The tier band is NOT the
# target here (it's only the floor/ceiling diagnosis for display + de-conviction
# caveats). Safety invariants are identical to tier-band mode and are enforced by
# the same validate_reallocation: MONITOR/UNDOCUMENTED never legged, each leg
# carries its own source tag, cross-sleeve adds are ROTATION_RATIONALE_REQUIRED,
# >=$25K -> gate, T1 ADD -> deepwork. Two target-mode specifics:
#   * EXPLICIT_TARGET binding lets a leg sit outside its tier band (NVDA 10% past
#     T2 ceiling; a CORE name trimmed below floor) — but ONLY to the operator's
#     exact mapped weight (the validator pins it), so no trim is ever planner-
#     invented. Below-floor CORE trims carry a visible de-conviction caveat.
#   * Funded-rotation pairing prefers a SAME-FACTOR trim to fund each add (the
#     true net-flat rotation), labels those pairs NET-FACTOR-NEUTRAL, and reports
#     a plan-level net factor delta so an in-isolation gate concentration RED can
#     be re-read as AMBER/override for a net-flat rotation.
# ===========================================================================

def _target_diff_record(tk: str, hc, target_pct: float, book: float,
                        classif: dict, sequence_events: dict) -> dict:
    # round current/target FIRST, then derive delta from the rounded fields, so
    # (target_pct - current_pct) == delta_pct holds to float-epsilon (the
    # validator's delta check is exact to 1e-6).
    cur = round(hc.current_pct, 4)
    tgt = round(target_pct, 4)
    delta = round(tgt - cur, 4)
    return {
        "ticker": tk, "sleeve": hc.sleeve, "sleeve_class": hc.sleeve_class,
        "tier": hc.tier, "current_pct": cur,
        "target_pct": tgt, "delta_pct": delta,
        "notional": round(abs(delta) / 100.0 * book, 2),
        "floor_pct": hc.floor_pct, "ceiling_pct": hc.ceiling_pct,
        "source": hc.source, "factors": list(hc.factors),
        "classification": classif.get(tk, ""), "deepwork": hc.tier == "T1",
        "stage_after": sequence_events.get(tk), "is_exit": abs(target_pct) < 1e-9,
        "remaining_usd": round(abs(delta) / 100.0 * book, 2), "_funded": [],
    }


def _add_caveats(ac: dict) -> list[str]:
    cav = []
    if ac["target_pct"] > ac["ceiling_pct"] + CEILING_TOL_PCT:
        cav.append(
            f"Explicit target {ac['target_pct']:.1f}% is ABOVE the {ac['tier'] or 'T3'} "
            f"ceiling {ac['ceiling_pct']:.1f}% — a conscious tier promotion; confirm "
            f"the over-band single-name concentration is intended.")
    return cav


def _trim_caveats(tc: dict) -> list[str]:
    cav = []
    if tc["is_exit"]:
        cav.append("Full EXIT to 0% — confirm this de-conviction is intended.")
    elif tc["target_pct"] < tc["floor_pct"] - CEILING_TOL_PCT and \
            tc["sleeve_class"] == CLS_CORE:
        cav.append(
            f"Explicit target {tc['target_pct']:.1f}% is BELOW the {tc['tier'] or 'T3'} "
            f"conviction floor {tc['floor_pct']:.1f}% on a CORE name — confirm this is "
            f"an intentional de-conviction, not a sizing slip.")
    return cav


def plan_target_reallocation(*, positions: list[dict], theses: list[dict],
                             total_book_value: float, target_weights: dict,
                             mode: Optional[dict] = None, macro: Optional[dict] = None,
                             source_rates: Optional[dict] = None,
                             materiality_pct: float = 1.0,
                             materiality_usd: float = GATE_NOTIONAL_THRESHOLD,
                             expected_cash_pct: Optional[float] = None,
                             sequence_events: Optional[dict] = None,
                             etf_lookthrough: Optional[dict] = None,
                             cash_reserve_pct: float = 0.0,
                             as_of: str = "") -> ReallocationResult:
    """Plan funded trim<->add legs to move current weights to an EXPLICIT
    per-name target_weights map. See the section header for the contract."""
    book = float(total_book_value)
    if book <= 0:
        raise ValueError("total_book_value must be > 0")
    # force names/funding to target mode (these keys win over any incoming mode,
    # which plan_reallocation has already merged with DEFAULT_MODE)
    mode = {**DEFAULT_MODE, **(mode or {}),
            "names": "target_weight", "funding": "funded_rotation"}
    tmap = {str(k).upper().strip(): float(v)
            for k, v in (target_weights or {}).items() if str(k).strip()}
    sequence_events = {str(k).upper(): v for k, v in (sequence_events or {}).items()}
    positions = _normalize_positions(positions, book)

    # Every targeted ticker must be classifiable even if not currently held
    # (e.g. TSM 0% -> 4%): add a zero-weight row so classify_book/calibrate see it.
    held = {(p.get("ticker") or "").upper() for p in positions}
    pos_aug = list(positions) + [
        {"ticker": tk, "market_value": 0.0, "_pct": 0.0}
        for tk in tmap if tk not in held]

    report = calibrate(pos_aug, theses, book, macro, source_rates)
    cbt = _classes_by_ticker(pos_aug, theses)
    classif = _classif_by_ticker(report)

    # ---- per-ticker diffs (MONITOR/UNDOCUMENTED are never legged, only warned) -
    monitor_in_map: list[str] = []
    undoc_in_map: list[str] = []
    add_cands: list[dict] = []
    trim_cands: list[dict] = []
    for tk, target_pct in tmap.items():
        hc = cbt.get(tk)
        if hc is None or hc.sleeve_class == CLS_UNDOCUMENTED:
            undoc_in_map.append(tk)
            continue
        if hc.sleeve_class == CLS_MONITOR:
            monitor_in_map.append(tk)
            continue
        rec = _target_diff_record(tk, hc, target_pct, book, classif, sequence_events)
        if abs(rec["delta_pct"]) < 1e-9 or rec["notional"] < 1e-6:
            continue  # already at target
        (add_cands if rec["delta_pct"] > 0 else trim_cands).append(rec)

    # ---- funded-rotation pairing (same-factor trims first) -------------------
    # Trims are FIXED by the explicit targets (they happen regardless); pairing is
    # attribution + the net-factor-neutral label. Adds draw from the trim pool,
    # preferring a same-factor trim, then any trim, then available cash.
    add_cands.sort(key=lambda c: (_CLASS_PRIORITY.get(c["sleeve_class"], 0),
                                   c["notional"]), reverse=True)
    trims_total = round(sum(t["notional"] for t in trim_cands), 2)
    cash_pct_now = cash_pct_from_positions(positions)
    available_cash = max(0.0, (cash_pct_now - cash_reserve_pct) / 100.0 * book)

    cash_used = 0.0
    funded_add_usd = 0.0
    unfunded: list[dict] = []
    trim_id = {t["ticker"]: f"T{i+1}" for i, t in enumerate(trim_cands)}
    add_id = {a["ticker"]: f"A{i+1}" for i, a in enumerate(add_cands)}

    for ac in add_cands:
        need = ac["notional"]
        fa = set(ac["factors"])
        pool = sorted(trim_cands, key=lambda t: (
            0 if (set(t["factors"]) & fa) else 1, -t["remaining_usd"]))
        funders: list[list] = []
        remaining = need
        for tc in pool:
            if remaining <= 1e-6:
                break
            draw = min(tc["remaining_usd"], remaining)
            if draw <= 1e-9:
                continue
            tc["remaining_usd"] -= draw
            remaining -= draw
            funders.append([tc, round(draw, 2)])
        cash_draw = 0.0
        if remaining > 1e-6 and available_cash > 1e-6:
            cash_draw = min(available_cash, remaining)
            available_cash -= cash_draw
            remaining -= cash_draw
        if remaining > 1e-6:
            # cannot fully fund this EXACT target — roll back, defer (never hit an
            # explicit target partially), surface as unfunded.
            for tc, draw in funders:
                tc["remaining_usd"] += draw
            available_cash += cash_draw
            unfunded.append({"ticker": ac["ticker"], "needed_usd": round(need, 2),
                             "sleeve": ac["sleeve"], "tier": ac["tier"]})
            continue
        cash_used += cash_draw
        funded_add_usd += need
        ac["_cash_draw"] = round(cash_draw, 2)
        ac["_funders"] = funders
        for tc, draw in funders:
            tc["_funded"].append([ac["ticker"], draw])

    # ---- build trim legs (one per name, to its exact target) -----------------
    legs: list[Leg] = []
    for tc in trim_cands:
        primary_add = max(tc["_funded"], key=lambda x: x[1])[0] if tc["_funded"] else None
        funded_names = ", ".join(a for a, _ in tc["_funded"]) or "cash (parked surplus)"
        rationale = (
            f"{tc['ticker']} {tc['current_pct']:.2f}% -> {tc['target_pct']:.2f}% "
            f"({'EXIT' if tc['is_exit'] else 'trim'}, explicit target); "
            f"funds {funded_names}.")
        legs.append(Leg(
            leg_id=trim_id[tc["ticker"]], action=TRIM, ticker=tc["ticker"],
            sleeve=tc["sleeve"], sleeve_class=tc["sleeve_class"], tier=tc["tier"],
            current_pct=tc["current_pct"], target_pct=tc["target_pct"],
            delta_pct=tc["delta_pct"], notional_usd=tc["notional"],
            floor_pct=tc["floor_pct"], ceiling_pct=tc["ceiling_pct"],
            source_tag=tc["source"],
            source_tag_status=(SOURCE_TAG_PREFILLED if tc["source"] else SOURCE_TAG_REQUIRED),
            funds_leg_id=(add_id.get(primary_add) if primary_add else None),
            rotation=False, optional=False, binding=SIZING_EXPLICIT_TARGET,
            factor_tags=tc["factors"], stage_after=tc["stage_after"],
            rationale=rationale, caveats=_trim_caveats(tc)))

    # ---- build add legs (to exact target) ------------------------------------
    for ac in add_cands:
        if "_funders" not in ac:
            continue  # unfunded
        funders = ac["_funders"]
        primary = max(funders, key=lambda x: x[1])[0] if funders else None
        rotation = bool(primary and primary["sleeve_class"] != ac["sleeve_class"])
        shared = (set(primary["factors"]) & set(ac["factors"])) if primary else set()
        neutral = bool(shared)
        label = sorted(shared)[0] if shared else None
        status = SOURCE_TAG_ROTATION if rotation else (
            SOURCE_TAG_PREFILLED if ac["source"] else SOURCE_TAG_REQUIRED)
        src_names = ", ".join(f"{t['ticker']} ${d:,.0f}" for t, d in funders)
        if ac["_cash_draw"] > 0:
            src_names = (src_names + ", " if src_names else "") + f"cash ${ac['_cash_draw']:,.0f}"
        rationale = (
            f"{ac['ticker']} {ac['current_pct']:.2f}% -> {ac['target_pct']:.2f}% "
            f"(+{ac['delta_pct']:.2f}pp, explicit target); funded by {src_names}.")
        if neutral:
            rationale += (f" NET-FACTOR-NEUTRAL on {label}: funding trim shares this "
                          f"factor, so the rotation does not raise net {label} exposure.")
        elif rotation:
            rationale += (f" CROSS-SLEEVE rotation ({primary['sleeve']} -> {ac['sleeve']}) "
                          f"— confirm the rotation rationale and tag this leg's source.")
        legs.append(Leg(
            leg_id=add_id[ac["ticker"]], action=ADD, ticker=ac["ticker"],
            sleeve=ac["sleeve"], sleeve_class=ac["sleeve_class"], tier=ac["tier"],
            current_pct=ac["current_pct"], target_pct=ac["target_pct"],
            delta_pct=ac["delta_pct"], notional_usd=ac["notional"],
            floor_pct=ac["floor_pct"], ceiling_pct=ac["ceiling_pct"],
            source_tag=ac["source"], source_tag_status=status,
            funded_by_leg_id=(trim_id.get(primary["ticker"]) if primary else None),
            rotation=rotation, deepwork=ac["deepwork"], binding=SIZING_EXPLICIT_TARGET,
            factor_tags=ac["factors"], net_factor_neutral=neutral,
            net_factor_label=label, stage_after=ac["stage_after"],
            rationale=rationale, caveats=_add_caveats(ac)))

    # ---- net factor delta across the whole plan ------------------------------
    net_factor_delta: dict = {}
    for l in legs:
        signed = l.notional_usd if l.action == ADD else -l.notional_usd
        for f in l.factor_tags:
            net_factor_delta[f] = round(net_factor_delta.get(f, 0.0) + signed, 2)

    # ---- materiality split + rank --------------------------------------------
    def _material(l: Leg) -> bool:
        return l.notional_usd >= materiality_usd or abs(l.delta_pct) >= materiality_pct
    if mode["aggressiveness"] == "material_only":
        main_legs = [l for l in legs if _material(l)]
        sub_legs = [l for l in legs if not _material(l)]
    else:
        main_legs, sub_legs = list(legs), []
    for i, l in enumerate(main_legs, 1):
        l.rank = i
    for i, l in enumerate(sub_legs, 1):
        l.rank = i

    # ---- target-vs-current for EVERY holding (overlay net leg deltas) --------
    delta_by_ticker: dict = {}
    for l in legs:
        delta_by_ticker[l.ticker] = delta_by_ticker.get(l.ticker, 0.0) + l.delta_pct
    rows = [
        TargetRow(
            ticker=hc.ticker, sleeve=hc.sleeve, sleeve_class=hc.sleeve_class,
            tier=hc.tier, current_pct=round(hc.current_pct, 4),
            target_pct=round(hc.current_pct + delta_by_ticker.get(hc.ticker, 0.0), 4),
            classification=classif.get(hc.ticker, ""))
        for hc in cbt.values()]

    # ---- ETF look-through (warn on ETF + single double-count) ----------------
    lt_table = etf_lookthrough or ETF_LOOKTHROUGH
    final_pct = {r.ticker: r.target_pct for r in rows}
    lookthrough: list[dict] = []
    lt_warnings: list[str] = []
    for etf, info in lt_table.items():
        etf_pct = final_pct.get(etf.upper())
        if etf_pct is None or etf_pct <= 1e-9:
            continue
        overlaps = []
        for name, w in (info.get("constituents") or {}).items():
            sp = final_pct.get(name.upper())
            if sp and sp > 1e-9:
                via = round(etf_pct * w, 4)
                overlaps.append({"ticker": name.upper(), "single_pct": round(sp, 4),
                                 "via_etf_pct": via, "true_pct": round(sp + via, 4)})
        if overlaps:
            lookthrough.append({"etf": etf.upper(), "etf_pct": round(etf_pct, 4),
                                "factor": info.get("factor"), "overlaps": overlaps})
            names = ", ".join(f"{o['ticker']} (single {o['single_pct']:.1f}% + "
                              f"{o['via_etf_pct']:.2f}% via {etf.upper()} = "
                              f"true ~{o['true_pct']:.1f}%)" for o in overlaps)
            lt_warnings.append(
                f"ETF look-through: {etf.upper()} held at {etf_pct:.1f}% double-counts "
                f"{info.get('factor')} that is ALSO sized as singles — {names}. "
                f"Approach A = keep {etf.upper()} base + singles on top (true exposure "
                f"is the higher number); Approach B = shrink {etf.upper()} and let the "
                f"singles carry the factor (cleaner attribution).")

    # ---- funding summary (conservation holds by construction) ----------------
    cash_freed = round(trims_total + cash_used - funded_add_usd, 2)
    funding = FundingSummary(
        trims_total_usd=trims_total, adds_total_usd=round(funded_add_usd, 2),
        cash_used_usd=round(cash_used, 2), cash_freed_usd=max(0.0, cash_freed),
        shortfall_usd=round(sum(u["needed_usd"] for u in unfunded), 2),
        unfunded_adds=[u["ticker"] for u in unfunded])

    # new cash% from the flow: old cash + trims - funded adds (as pp of book)
    new_cash_pct = round(cash_pct_now + (trims_total - funded_add_usd) / book * 100.0, 4)

    monitor_left = sorted(set([g.ticker for g in report.monitor_suppressed]) | set(monitor_in_map))
    undoc = sorted(set([g.ticker for g in report.no_thesis
                        if "monitor_suppressed" not in g.flags]) | set(undoc_in_map))

    # ---- notes + warnings ----------------------------------------------------
    notes: list[str] = []
    if not main_legs and not sub_legs:
        notes.append("No moves indicated — current weights already match the target map "
                     "(MONITOR/undocumented names excluded).")
    neutral_legs = [l for l in main_legs if l.net_factor_neutral]
    if neutral_legs:
        nf = ", ".join(sorted({l.net_factor_label for l in neutral_legs if l.net_factor_label}))
        notes.append(
            f"Funded rotation: {len(neutral_legs)} add(s) are NET-FACTOR-NEUTRAL ({nf}) — "
            f"funded by same-factor trims, so net exposure does not rise. A pretrade_gate "
            f"INCREMENTAL_FACTOR_CONCENTRATION RED scored on a single add IN ISOLATION "
            f"should be read as AMBER (override + log) where the plan's net factor delta is "
            f"flat-or-down (see net_factor_delta).")
    if cash_freed > materiality_usd:
        notes.append(f"Net de-risking: trims exceed funded adds by ${cash_freed:,.0f} — "
                     f"surplus parks to cash (cash {cash_pct_now:.1f}% -> {new_cash_pct:.1f}%).")
    if unfunded:
        notes.append("Some explicit targets are unfunded (trims + available cash "
                     "insufficient) — listed names stay at current; raise cash or trim "
                     "more to reach every target.")
    seq_legs = [l for l in main_legs if l.stage_after]
    if seq_legs:
        ev = ", ".join(sorted({l.stage_after for l in seq_legs}))
        notes.append(f"Sequencing: {len(seq_legs)} correlated leg(s) tagged to STAGE AFTER "
                     f"[{ev}] — the rest are 'now'.")
    if monitor_in_map:
        notes.append(f"target_weights listed MONITOR name(s) {', '.join(sorted(monitor_in_map))}"
                     f" — left UNTOUCHED (MONITOR is never traded to fund a gap).")
    if undoc_in_map:
        notes.append(f"target_weights listed name(s) with no thesis/tier "
                     f"({', '.join(sorted(undoc_in_map))}) — excluded; add a thesis line "
                     f"to size them.")

    warnings: list[str] = list(lt_warnings)
    coverage = round(sum(float(p.get("_pct") or 0.0) for p in positions), 2)
    if coverage < 95.0:
        warnings.append(
            f"FEED covers only {coverage:.1f}% of the book by weight ({100 - coverage:.1f}% "
            f"reads as cash/untracked) — verify against the Latest Portfolio before acting.")
    if expected_cash_pct is not None and abs(cash_pct_now - expected_cash_pct) > 1.0:
        warnings.append(
            f"FEED-implied cash {cash_pct_now:.2f}% differs from stated "
            f"{expected_cash_pct:.2f}% — the FEED may be missing holdings; verify.")

    return ReallocationResult(
        as_of=as_of, total_book_value=book, cash_pct=new_cash_pct, mode=mode,
        legs=main_legs, sub_threshold_legs=sub_legs, target_vs_current=rows,
        funding=funding, monitor_left_alone=monitor_left, undocumented_excluded=undoc,
        notes=notes, warnings=warnings, explicit_targets={k: round(v, 4) for k, v in tmap.items()},
        net_factor_delta=net_factor_delta, lookthrough=lookthrough)


def net_factor_is_flat_or_down(result: ReallocationResult, factor: str) -> bool:
    """True when the plan's net $ delta for `factor` does not raise exposure
    (<= NET_FACTOR_FLAT_TOL_PCT of book). This is the test for re-reading an
    in-isolation gate INCREMENTAL_FACTOR_CONCENTRATION RED as AMBER/override."""
    tol = NET_FACTOR_FLAT_TOL_PCT / 100.0 * float(result.total_book_value or 0.0)
    return float(result.net_factor_delta.get(factor, 0.0)) <= tol


# ===========================================================================
# GATE WIRING  (Chunk 3)  — fire the REAL pretrade_gate LIVE, in-session
# ===========================================================================

def run_gate_on_legs(result: ReallocationResult, *, positions: list[dict],
                     theses: list[dict], total_book_value: float,
                     macro: Optional[dict] = None,
                     source_rates: Optional[dict] = None,
                     market_state: Optional[dict] = None,
                     include_sub_threshold: bool = False) -> ReallocationResult:
    """LIVE step: fire the real pretrade_gate on every leg with needs_gate
    (>= $25K). Results attach to leg.gate['result'] HERE, in-session — the plan
    is never *built* with baked gate results (they depend on live macro/source/
    factor state, per CI v12.2 §6). Returns the same result, mutated.
    """
    import pretrade_gate  # lazy: the core planner must not hard-depend on it
    book = float(total_book_value)
    positions = _normalize_positions(positions, book)
    pool = list(result.legs) + (list(result.sub_threshold_legs) if include_sub_threshold else [])
    for leg in pool:
        if not leg.gate.get("needs_gate"):
            continue
        gr = pretrade_gate.evaluate(
            leg.action, leg.ticker, leg.notional_usd, positions, theses, book,
            macro_pulse=macro, source_rates=source_rates, market_state=market_state,
        )
        leg.gate["result"] = {
            "overall": gr.overall,
            "deepwork_required": gr.deepwork_required,
            "requires_log": gr.requires_log,
            "summary": gr.summary,
            "flags": [{"color": f.color, "code": f.code, "message": f.message}
                      for f in gr.flags],
        }
    annotate_net_factor_overrides(result, include_sub_threshold=include_sub_threshold)
    return result


def annotate_net_factor_overrides(result: ReallocationResult, *,
                                  include_sub_threshold: bool = False) -> ReallocationResult:
    """Re-read pretrade_gate's per-leg INCREMENTAL_FACTOR_CONCENTRATION RED in the
    context of the WHOLE funded plan.

    The gate scores each leg IN ISOLATION: at ~60% ai_complex it REDs any AI add
    on its own. But a funded wrapper->single rotation (the AI add paired with a
    same-factor trim) does NOT raise net factor exposure. So when the plan's net
    delta for that factor is flat-or-down, we attach an explicit 'read_as: AMBER
    (override + log)' note to the leg's gate result. We do NOT mutate the gate's
    own `overall` — the gate's isolated verdict stays honest; this is the
    portfolio-level reconciliation the operator reads alongside it."""
    import re
    pool = list(result.legs) + (list(result.sub_threshold_legs)
                                if include_sub_threshold else [])
    for leg in pool:
        res = leg.gate.get("result")
        if not res:
            continue
        for fl in res.get("flags", []):
            if fl.get("code") != "INCREMENTAL_FACTOR_CONCENTRATION" or fl.get("color") != "RED":
                continue
            # which factor did the gate RED on? it is single-quoted in the message
            # ("Post-trade 'ai_complex' = 65.0% ..."). Fall back to the leg's tags.
            m = re.search(r"'([^']+)'", fl.get("message", ""))
            cand = [m.group(1).lower()] if m else list(leg.factor_tags)
            flat = [f for f in cand
                    if f in leg.factor_tags and net_factor_is_flat_or_down(result, f)]
            if not flat:
                continue   # the REDed factor really IS net-up — leave the RED standing
            deltas = {f: round(result.net_factor_delta.get(f, 0.0), 0) for f in flat}
            res.setdefault("overrides", []).append({
                "flag": "INCREMENTAL_FACTOR_CONCENTRATION",
                "gate_color": "RED",
                "read_as": "AMBER",
                "factor": flat[0],
                "reason": (
                    f"Gate scored this add IN ISOLATION. The plan's net delta for the "
                    f"flagged factor is flat-or-down ({deltas}) — this add is a funded "
                    f"net-factor-neutral rotation, so net exposure does not rise. Read as "
                    f"AMBER: override + log, don't block."),
            })
    return result


# ===========================================================================
# OUTPUT RENDERER  (Chunk 3)  — the human-readable deliverable (mobile-first MD)
# ===========================================================================

def _fmt_leg_line(l: Leg) -> str:
    label = "ADD " if l.action == ADD else "TRIM"
    sign = "+" if l.delta_pct >= 0 else ""
    g = l.gate.get("result")
    if l.gate.get("needs_gate"):
        gate_txt = f" · gate: {g['overall']}" if g else " · gate: RUN-LIVE (>=$25K)"
    else:
        gate_txt = ""
    tags = []
    if l.net_factor_neutral:
        tags.append(f"NET-FACTOR-NEUTRAL ({l.net_factor_label})")
    if l.rotation:
        tags.append("rotation")
    if l.optional:
        tags.append("optional")
    if l.deepwork:
        tags.append("DEEPWORK")
    if l.stage_after:
        tags.append(f"stage after {l.stage_after}")
    tagtxt = (" · " + " · ".join(tags)) if tags else ""
    src = f"{l.source_tag or '—'}/{l.source_tag_status}"
    return (f"**{label} {l.ticker}** {l.current_pct:.2f}% -> {l.target_pct:.2f}% "
            f"({sign}${l.notional_usd:,.0f}){tagtxt}{gate_txt} · src {src}")


def format_reallocation(r: ReallocationResult) -> str:
    """Render a ReallocationResult as mobile-first markdown."""
    L = ["# Reallocation — CANDIDATES (tax-agnostic)",
         f"_as of {r.as_of or 'now'} · book ${r.total_book_value:,.0f} · cash {r.cash_pct:.2f}%_",
         "> \u26a0\ufe0f Every line is a **CANDIDATE** — nothing here is executed "
         "(P-NO-FILL-NO-FACT). Multi-leg: each leg carries its **own** source tag; "
         "a cross-sleeve rotation needs your rationale."]

    if r.warnings:
        L.append("\n## \u26a0\ufe0f Data quality")
        for w in r.warnings:
            L.append(f"- {w}")

    if r.legs:
        L.append(f"\n## Ranked moves ({len(r.legs)} material)")
        for l in r.legs:
            L.append(f"{l.rank}. {_fmt_leg_line(l)}")
            if l.action == ADD and l.funded_by_leg_id:
                L.append(f"   \u21b3 funded by leg {l.funded_by_leg_id}")
            if l.action == TRIM and l.funds_leg_id:
                L.append(f"   \u21b3 funds leg {l.funds_leg_id}")
            L.append(f"   \u21b3 {l.rationale}")
            for c in l.caveats:
                L.append(f"   \u26a0\ufe0f {c}")
            for ov in (l.gate.get("result") or {}).get("overrides", []):
                L.append(f"   \U0001f504 gate {ov['gate_color']} read as **{ov['read_as']}**: "
                         f"{ov['reason']}")
    else:
        L.append("\n## Ranked moves\n_No material moves today._")

    if r.sub_threshold_legs:
        L.append(f"\n## Minor moves (below materiality cut · {len(r.sub_threshold_legs)})")
        for l in r.sub_threshold_legs:
            L.append(f"- {_fmt_leg_line(l)}")

    if r.funding.unfunded_adds:
        L.append(f"\n## Unfunded (shortfall: ${r.funding.shortfall_usd:,.0f})")
        L.append("- " + ", ".join(r.funding.unfunded_adds))

    f = r.funding
    L.append("\n## Funding")
    L.append(f"trims ${f.trims_total_usd:,.0f} → adds ${f.adds_total_usd:,.0f} "
             f"(cash used ${f.cash_used_usd:,.0f} · cash freed ${f.cash_freed_usd:,.0f}) · "
             f"shortfall ${f.shortfall_usd:,.0f}")

    # --- target-weight mode extras: net factor delta + ETF look-through -------
    if r.net_factor_delta:
        L.append("\n## Net factor delta (whole plan)")
        L.append("_Adds minus trims per factor — the funded-rotation lens the per-leg gate lacks._")
        L.append("| Factor | Net Δ$ | Reading |")
        L.append("|---|---:|---|")
        for fac, d in sorted(r.net_factor_delta.items(), key=lambda kv: kv[1]):
            flat = net_factor_is_flat_or_down(r, fac)
            read = "flat/down — gate concentration RED reads as AMBER" if flat else "net ADD"
            L.append(f"| {fac} | {d:+,.0f} | {read} |")

    if r.lookthrough:
        L.append("\n## ⚠️ ETF look-through (double-count check)")
        for lt in r.lookthrough:
            L.append(f"- **{lt['etf']}** held {lt['etf_pct']:.1f}% ({lt['factor']}) overlaps "
                     f"singles you also size:")
            for o in lt["overlaps"]:
                L.append(f"   ↳ {o['ticker']}: single {o['single_pct']:.1f}% + "
                         f"{o['via_etf_pct']:.2f}% via {lt['etf']} = **true ~{o['true_pct']:.1f}%**")

    movers = {l.ticker for l in r.legs} | {l.ticker for l in r.sub_threshold_legs}
    interesting = [row for row in r.target_vs_current
                   if row.ticker in movers
                   or row.classification in ("ABOVE_CEILING", "BELOW_FLOOR", "CRITICALLY_BELOW")]
    in_band_n = len(r.target_vs_current) - len(interesting)
    if interesting:
        L.append("\n## Target vs current")
        L.append("| Ticker | Class | Tier | Now | -> Target | State |")
        L.append("|---|---|---|---:|---:|---|")
        for row in sorted(interesting, key=lambda x: -abs(x.target_pct - x.current_pct)):
            chg = "" if abs(row.target_pct - row.current_pct) < 1e-6 else " *"
            L.append(f"| {row.ticker} | {row.sleeve_class} | {row.tier or '—'} | "
                     f"{row.current_pct:.2f}% | {row.target_pct:.2f}%{chg} | {row.classification or '—'} |")
        if in_band_n:
            L.append(f"\n_+{in_band_n} other holding(s) in-band, unchanged._")

    la = []
    if r.monitor_left_alone:
        la.append(f"**MONITOR (intentional — never auto-added):** {', '.join(r.monitor_left_alone)}")
    if r.undocumented_excluded:
        la.append(f"**Undocumented (need a thesis line to be in scope):** {', '.join(r.undocumented_excluded)}")
    if la:
        L.append("\n## Left alone")
        L.extend(la)

    if r.notes:
        L.append("\n## Notes")
        for n in r.notes:
            L.append(f"- {n}")
    return "\n".join(L)


def reallocate(*, feed: Optional[dict] = None, positions: Optional[list[dict]] = None,
               theses: list[dict], total_book_value: float,
               run_gate: bool = False, macro: Optional[dict] = None,
               source_rates: Optional[dict] = None, market_state: Optional[dict] = None,
               mode: Optional[dict] = None, materiality_pct: float = 1.0,
               materiality_usd: float = GATE_NOTIONAL_THRESHOLD,
               expected_cash_pct: Optional[float] = None,
               target_weights: Optional[dict] = None,
               sequence_events: Optional[dict] = None,
               etf_lookthrough: Optional[dict] = None,
               cash_reserve_pct: float = 0.0,
               as_of: str = "") -> tuple[ReallocationResult, str]:
    """One-call in-session entry point: plan -> (optionally) fire the LIVE gate
    -> render. Returns (ReallocationResult, markdown). Set run_gate=True with
    live macro/source_rates to populate gate verdicts on >=$25K legs.

    Pass `target_weights` {ticker: % of book} to drive TARGET-WEIGHT mode (exact
    funded legs to those weights); omit it for the default TIER-BAND behavior."""
    result = plan_reallocation(
        feed=feed, positions=positions, theses=theses, total_book_value=total_book_value,
        mode=mode, macro=macro, source_rates=source_rates, materiality_pct=materiality_pct,
        materiality_usd=materiality_usd, expected_cash_pct=expected_cash_pct,
        target_weights=target_weights, sequence_events=sequence_events,
        etf_lookthrough=etf_lookthrough, cash_reserve_pct=cash_reserve_pct, as_of=as_of)
    if run_gate:
        pos = positions if positions is not None else (
            positions_from_feed(feed, total_book_value) if feed is not None else None)
        if pos is not None:
            run_gate_on_legs(result, positions=pos, theses=theses,
                             total_book_value=total_book_value, macro=macro,
                             source_rates=source_rates, market_state=market_state)
    # self-validate at the seam: a caller must never silently receive an
    # invalid plan (Four-Lens systems-engineer finding).
    _errs = validate_reallocation(result)
    if _errs:
        result.warnings = ([f"\u26d4 CONTRACT VIOLATION (do not act): {e}" for e in _errs]
                           + list(result.warnings))
    return result, format_reallocation(result)


# ===========================================================================
# REFINEMENT BACKLOG (v1.0 ships; refine live)
#   - classify_holding factor priority is a heuristic; a name with a CORE
#     factor + a thematic factor (e.g. VOLT) lands CORE. Operator override
#     hook is a future add.
#   - UNDOCUMENTED names are excluded from legs (safe). A future pass could
#     fall back to the FEED `ty`/`cat` to tier big undocumented core names
#     rather than just nudging.
#   - cash model is fixed/cash-neutral for v1 (book ~0.65% cash). A
#     "deploy $X" mode is a documented future option.
#   - materiality split is per-leg; a future pass could be pair-aware so a
#     funded add and its trims never land in different lists.
#   - ADD sizes to floor x source-discount; an "AI under-sizing aggressive"
#     mode (size toward midpoint/ceiling for CORE) is a documented option.
# ===========================================================================


if __name__ == "__main__":
    import argparse
    import json as _json
    import sys as _sys

    ap = argparse.ArgumentParser(
        description="Reallocate — framework-aware whole-book reallocation "
                    "(CANDIDATES, tax-agnostic).")
    ap.add_argument("--feed", help="path to a cockpit FEED json")
    ap.add_argument("--theses", help="path to theses.json")
    ap.add_argument("--book", type=float, help="total book value, e.g. 1875000")
    ap.add_argument("--as-of", default="")
    ap.add_argument("--expected-cash", type=float, default=None,
                    help="stated cash %% for a consistency check")
    ap.add_argument("--materiality-pct", type=float, default=1.0)
    ap.add_argument("--target-weights", help="path to a {ticker: %%-of-book} json — "
                    "drives TARGET-WEIGHT mode (exact funded legs); omit for tier-band")
    ap.add_argument("--sequence-events", help="path to a {ticker: 'event'} json — "
                    "tag correlated legs to 'stage after [event]'")
    a = ap.parse_args()

    if a.feed and a.theses and a.book:
        feed = _json.load(open(a.feed))
        theses = _json.load(open(a.theses))
        tw = _json.load(open(a.target_weights)) if a.target_weights else None
        seq = _json.load(open(a.sequence_events)) if a.sequence_events else None
        result, md = reallocate(feed=feed, theses=theses, total_book_value=a.book,
                                as_of=a.as_of, expected_cash_pct=a.expected_cash,
                                materiality_pct=a.materiality_pct,
                                target_weights=tw, sequence_events=seq)
        print(md)
        errs = validate_reallocation(result)
        print("\n[validate] " + ("OK" if not errs else "; ".join(errs)), file=_sys.stderr)
    else:
        demo = ReallocationResult(
            as_of="2026-06-01", total_book_value=1_875_000, cash_pct=0.65, mode=DEFAULT_MODE)
        print("smoke — validate empty result:", validate_reallocation(demo) or "OK")
        print("usage: python3 reallocate.py --feed FEED.json --theses theses.json --book 1875000")
