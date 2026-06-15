#!/usr/bin/env python3
"""
reallocate_config.py — the assumptions / "dials" layer for the rebuilt reallocate.py.

WHY THIS FILE EXISTS (operator ask, 2026-06-02)
    "I'd like variables I can change easily ... change a variable to see how that
    assumption would change outcomes."
    So every structural assumption the reallocation depends on lives HERE, in one
    labeled place, as a named value you edit and re-run. The planner (reallocate.py,
    Chunk 2) IMPORTS these and hardcodes nothing.

WHAT COUNTS AS A "DIAL" (vs. a hardcode)
    Anything that, if you changed your mind about it, would change the recommended
    legs: the per-name target weights, the NVDA target, the SMH look-through
    approach, how much of each ETF wrapper to keep parked, the AI-sleeve flat %,
    the OPTIONAL concentration rail, the "too-parabolic-to-chase" gate, and the
    catalyst (earnings) gates.

GROUNDING — every default below traces to one of YOUR decisions, not a guess
    - The target table + dials      = your 2026-06-02 AI Reallocation Working Model.
    - "Rotation, AI ~flat ~60%" +
      "funded $-for-$"              = your pre-trade-gate finding (net-new AI REDs;
                                      only a funded wrapper->single rotation is AMBER).
    - Concentration rail DEFAULT=OFF= the "no random 38% cap" decision. Your standing
                                      concentration discipline is the tier caps +
                                      funded-factor-flat + ~60%-flat; the rail is an
                                      OPTIONAL extra ceiling you switch on and set
                                      yourself.
    - Run-up / chase gate           = your bifurcated-market read (don't chase the
                                      parabolic names; prefer constructive entries).

NOTHING HERE EXECUTES. Candidates only (P-NO-FILL-NO-FACT).

BUILD STATUS
    Chunk 1 (THIS FILE): the inputs layer (Dials / TargetWeightModel / ETF
        look-through) + the OPTIONAL concentration-rail validator + selftests.
    Chunk 2 (next): the rotation planner core that consumes these.
    Chunk 3: per-leg gate + catalyst sequence + premise-gate.
    Chunk 4: output + per-sub-sector metric + usability pass + ship.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ===========================================================================
# 1. THE DIALS  —  edit these, re-run, watch the plan change.
# ===========================================================================
# Each dial is a plain value with its current default + why. The planner reads
# these; it never hardcodes any of them.

SMH_APPROACH_A = "A"   # keep SMH ~8% base + singles on top (more look-through overlap)
SMH_APPROACH_B = "B"   # trim SMH to ~5%; the single names CARRY the semis exposure


@dataclass
class ConcentrationRail:
    """OPTIONAL aggregate concentration ceiling. OFF by default.

    There is NO hardcoded default ceiling (the "no random 38% cap" decision,
    2026-06-02). When you choose to switch it on, you set the numbers, and the
    planner blocks any rotation leg that would push the AI sleeve past them.
    All values are PERCENT OF BOOK. Leave a field None to not check it.
    """
    single_name_max_pct: Optional[float] = None        # e.g. 12.0 (also = T1 ceiling)
    total_single_name_max_pct: Optional[float] = None  # e.g. your modeled ~51-55
    etf_floor_pct: Optional[float] = None              # below this the wrapper IS the risk layer
    single_name_etf_multiple: Optional[float] = None   # name <= multiple x its look-through weight (e.g. 1.5)
    label: str = "off"

    @property
    def is_on(self) -> bool:
        return any(v is not None for v in (
            self.single_name_max_pct, self.total_single_name_max_pct,
            self.etf_floor_pct, self.single_name_etf_multiple))


RAIL_OFF = ConcentrationRail(label="off")   # the default — no aggregate cap

# A ready-to-use preset IF you ever want to switch the rail on at the levels we
# discussed. NOT applied by default — you'd pass this explicitly.
RAIL_PRESET_DISCUSSED = ConcentrationRail(
    single_name_max_pct=12.0,
    total_single_name_max_pct=55.0,   # your own modeled single-name sum, not an external 38
    etf_floor_pct=18.0,
    single_name_etf_multiple=1.5,
    label="discussed-preset",
)


@dataclass
class Dials:
    """The full assumptions set. Defaults = your 2026-06-02 Working Model.
    Change any field and re-run."""
    # -- the "go bigger" levers --
    nvda_target_pct: float = 12.0           # your decision: NVDA -> T1 12% (vs 10%)
    smh_approach: str = SMH_APPROACH_B      # your decision: B (singles carry semis)
    ai_sleeve_flat_pct: float = 60.0        # rotation holds total AI ~flat at ~60% of book

    # -- ETF reservoir keep-levels (% of book to KEEP parked; the rest is convertible) --
    # "ETFs are reservoirs; CONVERT->0 is a directional ceiling, not a forced sell."
    etf_keep_levels: dict = field(default_factory=lambda: {
        "SMH": 5.0,     # under Approach B
        "GRNY": 3.0,    # keep a residual of the Lee flagship (your decision)
        "MAGS": 0.0,    # directional convert-target (drawn down only as names are funded)
        "GRNJ": 0.0,    # protected by default; keep-level is not a sell target
        "IGV": 0.0,
        "IVES": 0.0,
        "SOXX": 0.0,
    })
    # Diversified wrappers that should not be used as automatic funding sources.
    # Override with an empty set only after an explicit thesis break, sizing cap, or
    # operator instruction.
    funding_protected_wrappers: set = field(default_factory=lambda: {"GRNJ"})

    # -- OPTIONAL aggregate concentration rail (default OFF) --
    concentration_rail: ConcentrationRail = field(default_factory=lambda: RAIL_OFF)

    # -- "too-parabolic-to-chase" gate --
    # A name whose trailing 1-month run-up exceeds this is NOT sized at market
    # (wait for a pullback or use defined-risk). Your bifurcated-market read.
    chase_block_1m_runup_pct: float = 35.0   # > +35% in 1M -> don't chase at market
    allow_defined_risk_on_parabolic: bool = True   # parabolic names may still be entered via defined-risk options

    # -- catalyst (earnings) gates: ticker -> ISO date; that name's add is held until on/after the date --
    catalyst_gates: dict = field(default_factory=lambda: {
        "AVGO": "2026-06-03",   # size AVGO only AFTER the print
    })
    # -- names gated by ANOTHER name's catalyst (correlated read) --
    # Your 6/2 sequence: "NVDA / TSM ... after the AVGO 6/3 print" \u2014 semis move together
    # through a bellwether print, so they wait for it too. Edit per your correlation read;
    # {} = each name gated only by its OWN catalyst.
    catalyst_correlated: dict = field(default_factory=lambda: {
        "AVGO": ["NVDA", "TSM"],
    })

    def describe(self) -> str:
        """Plain-language dump of the current dials (for the output header)."""
        rail = (f"ON [{self.concentration_rail.label}]"
                if self.concentration_rail.is_on else "OFF")
        keep = ", ".join(f"{k} {v:g}%" for k, v in self.etf_keep_levels.items() if v)
        protected = ", ".join(sorted(self.funding_protected_wrappers)) or "(none)"
        gates = ", ".join(f"{k}->{v}" for k, v in self.catalyst_gates.items())
        corr = ", ".join(f"{k}->{'/'.join(v)}" for k, v in self.catalyst_correlated.items())
        return (
            "Assumptions (dials):\n"
            f"  NVDA target            : {self.nvda_target_pct:g}%\n"
            f"  SMH approach           : {self.smh_approach}  "
            f"({'singles carry semis' if self.smh_approach == SMH_APPROACH_B else 'SMH base + singles on top'})\n"
            f"  AI sleeve held ~flat at: {self.ai_sleeve_flat_pct:g}% of book\n"
            f"  ETF reservoir keep     : {keep or '(none kept)'}\n"
            f"  Funding protected      : {protected}\n"
            f"  Concentration rail     : {rail}\n"
            f"  Chase block (1M run-up): > {self.chase_block_1m_runup_pct:g}% -> no market chase"
            f" (defined-risk {'allowed' if self.allow_defined_risk_on_parabolic else 'blocked'})\n"
            f"  Catalyst gates         : {gates or '(none)'}\n"
            f"  Catalyst-correlated    : {corr or '(none)'}"
        )


DEFAULT_DIALS = Dials()   # = your Working Model defaults, rail OFF


# ===========================================================================
# 2. THE TARGET-WEIGHT MODEL  —  your per-name conviction targets.
# ===========================================================================
# Right valuation lens per sub-sector (your decision: P/E is the wrong single
# metric here). The planner uses this only for labeling/context, never to
# auto-size — conviction + opportunity drive sizing.
SUBSECTOR_METRIC = {
    "compute":       "PEG / fwd P/E (NVDA ~19x fwd / PEG<0.3 = standout)",
    "memory":        "cyclical — low P/E is a peak-trap, watch the cycle (MU)",
    "optics":        "EV/Sales + segment growth (FN)",
    "networking":    "EV/Sales + AI-fabric share (ANET/AVGO)",
    "power_thermal": "backlog / book-to-bill (VRT)",
    "equipment":     "order-book / book-to-bill (ASML)",
    "foundry":       "order-book / utilization (TSM)",
    "hyperscaler":   "fwd P/E vs growth (GOOGL/MSFT/AMZN)",
    "software":      "rule-of-40 / EV/Sales",
}


@dataclass
class NameTarget:
    ticker: str
    target_pct: float          # % of book
    tier: str                  # T1..T4
    factor: str                # ai_complex / semiconductors / software / ...
    sub_sector: str            # key into SUBSECTOR_METRIC
    is_single_name: bool = True   # True = AI single name; False = AI-theme ETF wrapper
    note: str = ""


@dataclass
class TargetWeightModel:
    targets: list  # list[NameTarget]

    def as_map(self) -> dict:
        return {t.ticker: t.target_pct for t in self.targets}

    def single_names(self) -> list:
        return [t for t in self.targets if t.is_single_name]

    def etfs(self) -> list:
        return [t for t in self.targets if not t.is_single_name]

    def total_single_name_pct(self) -> float:
        return round(sum(t.target_pct for t in self.single_names()), 4)

    def total_etf_pct(self) -> float:
        return round(sum(t.target_pct for t in self.etfs()), 4)


def default_working_model() -> TargetWeightModel:
    """Your 2026-06-02 Working Model (Approach B). Edit here, or build your own
    TargetWeightModel and pass it in — the planner takes the model as input."""
    T = NameTarget
    return TargetWeightModel(targets=[
        T("NVDA",  12.0, "T1", "semiconductors", "compute",       True,  "compute moat; ~19x fwd / PEG<0.3 — the T1 promotion"),
        T("GOOGL",  8.0, "T1", "ai_complex",     "hyperscaler",   True,  "full-stack incl TPUs; capex-confirmed; constructive entry"),
        T("AVGO",   6.0, "T2", "semiconductors", "networking",    True,  "custom ASIC + networking; size AFTER 6/3 print"),
        T("MSFT",   5.0, "T2", "ai_complex",     "hyperscaler",   True,  "hyperscaler; cheap laggard"),
        T("AMZN",   4.0, "T2", "ai_complex",     "hyperscaler",   True,  "AWS; mild pullback"),
        T("TSM",    4.0, "T2", "semiconductors", "foundry",       True,  "foundry near-monopoly; extended"),
        T("MU",     3.0, "T3", "semiconductors", "memory",        True,  "HBM — HOLD FLAT, no add (parabolic, IVR ~100)"),
        T("ANET",   3.0, "T3", "ai_complex",     "networking",    True,  "AI networking fabric; constructive"),
        T("ASML",   2.0, "T3", "semiconductors", "equipment",     True,  "EUV monopoly; most irreplaceable, extended"),
        T("FN",     2.0, "T3", "ai_complex",     "optics",        True,  "optical interconnect; constructive on dips"),
        T("VRT",    2.0, "T3", "ai_complex",     "power_thermal", True,  "datacenter power/thermal; least chip-correlated"),
        T("SMH",    5.0, "T1", "semiconductors", "equipment",     False, "one diversified semis base (Approach B)"),
        T("GRNY",   3.0, "T3", "ai_complex",     "software",      False, "Lee flagship residual (reservoir)"),
    ])


# ===========================================================================
# 3. ETF LOOK-THROUGH  —  net out a wrapper's own holding of a name.
# ===========================================================================
# Holding SMH AND sizing NVDA double-counts NVDA (SMH is ~20% NVDA). The planner
# nets each wrapper's weight of a name out of the single-name sizing so effective
# exposure is honest. Weights are FRACTION-OF-ETF. v1 top-holdings (refine live).
ETF_LOOKTHROUGH = {
    "SMH":  {"NVDA": 0.20, "TSM": 0.11, "AVGO": 0.08, "AMD": 0.05, "MU": 0.04, "ASML": 0.04},
    "MAGS": {"NVDA": 0.14, "MSFT": 0.14, "AAPL": 0.13, "AMZN": 0.13, "GOOGL": 0.13, "META": 0.13, "AVGO": 0.10},
    "SOXX": {"NVDA": 0.09, "AVGO": 0.09, "TSM": 0.08, "AMD": 0.07, "MU": 0.05, "ASML": 0.04},
    "IGV":  {"MSFT": 0.09, "ORCL": 0.08, "CRM": 0.07},     # software — little overlap with the semis singles
    "IVES": {"NVDA": 0.05, "AVGO": 0.04, "MSFT": 0.04, "GOOGL": 0.03},  # Dan Ives AI — diversified
}


def lookthrough_implied_pct(ticker: str, etf_book_weights: dict) -> float:
    """Effective book % of `ticker` you already hold THROUGH the wrappers.
    etf_book_weights: {etf_ticker: that ETF's % of book}. Returns % of book.
    Example: SMH at 5% of book, SMH is 20% NVDA -> 1.0% NVDA via look-through."""
    implied = 0.0
    for etf, book_pct in etf_book_weights.items():
        frac = ETF_LOOKTHROUGH.get(etf, {}).get(ticker, 0.0)
        implied += book_pct * frac
    return round(implied, 4)


# ===========================================================================
# 4. OPTIONAL CONCENTRATION-RAIL VALIDATOR  —  enforced ONLY when you set a rail.
# ===========================================================================
def validate_concentration_rail(target_weights: dict,
                                model: TargetWeightModel,
                                rail: Optional[ConcentrationRail],
                                etf_book_weights: Optional[dict] = None) -> list:
    """Return a list of violation messages for the RESULTING target weights.

    EMPTY when the rail is off (rail is None, or RAIL_OFF, or all-None fields) —
    that is the default. When you set fields, each is checked (% of book):
      - single_name_max_pct        : no AI single name above this
      - total_single_name_max_pct  : sum of AI single names not above this
      - etf_floor_pct              : AI-theme ETF total not below this
      - single_name_etf_multiple   : name <= multiple x its look-through-implied
                                     weight (needs etf_book_weights; skipped if not given)

    target_weights : {ticker: resulting target % of book}
    """
    if rail is None or not rail.is_on:
        return []

    errs: list = []
    singles = {t.ticker for t in model.single_names()}
    etfs = {t.ticker for t in model.etfs()}

    if rail.single_name_max_pct is not None:
        for tk in sorted(singles):
            w = target_weights.get(tk, 0.0)
            if w > rail.single_name_max_pct + 1e-6:
                errs.append(f"{tk} {w:.1f}% exceeds single-name cap {rail.single_name_max_pct:.1f}%")

    if rail.total_single_name_max_pct is not None:
        total = sum(target_weights.get(tk, 0.0) for tk in singles)
        if total > rail.total_single_name_max_pct + 1e-6:
            errs.append(f"total AI single-name {total:.1f}% exceeds cap "
                        f"{rail.total_single_name_max_pct:.1f}%")

    if rail.etf_floor_pct is not None:
        etf_total = sum(target_weights.get(tk, 0.0) for tk in etfs)
        if etf_total < rail.etf_floor_pct - 1e-6:
            errs.append(f"AI-theme ETF {etf_total:.1f}% below floor "
                        f"{rail.etf_floor_pct:.1f}% (wrapper is the risk-control layer here)")

    if rail.single_name_etf_multiple is not None:
        if etf_book_weights:
            mult = rail.single_name_etf_multiple
            for tk in sorted(singles):
                implied = lookthrough_implied_pct(tk, etf_book_weights)
                if implied > 0 and target_weights.get(tk, 0.0) > mult * implied + 1e-6:
                    errs.append(f"{tk} {target_weights.get(tk, 0.0):.1f}% exceeds "
                                f"{mult:g}x its look-through weight ({implied:.1f}%)")
        # if etf_book_weights not supplied, this check is skipped (documented).

    return errs


# ===========================================================================
# SELFTEST
# ===========================================================================
def _selftest() -> None:
    fails = []

    def ok(cond, msg):
        if not cond:
            fails.append(msg)

    # 1. dials defaults match the Working Model decisions
    d = Dials()
    ok(d.nvda_target_pct == 12.0, "NVDA default should be 12%")
    ok(d.smh_approach == SMH_APPROACH_B, "SMH default should be Approach B")
    ok(abs(d.ai_sleeve_flat_pct - 60.0) < 1e-9, "AI sleeve flat default ~60%")
    ok(d.concentration_rail.label == "off" and not d.concentration_rail.is_on,
       "concentration rail OFF by default")
    ok(d.etf_keep_levels.get("SMH") == 5.0 and d.etf_keep_levels.get("GRNY") == 3.0,
       "ETF keep-levels default SMH 5 / GRNY 3")
    ok("GRNJ" in d.funding_protected_wrappers,
       "GRNJ default should be funding-protected unless explicitly overridden")
    ok(d.catalyst_gates.get("AVGO") == "2026-06-03", "AVGO catalyst gate default 6/3")

    # 2. the default Working Model is ~51-55% single-name (your deliberate bet)
    m = default_working_model()
    ts = m.total_single_name_pct()
    ok(50.0 <= ts <= 60.0, f"single-name target sum should be ~51-55%, got {ts}")
    ok(len(m.single_names()) == 11, "11 single names in the default model")
    ok({t.ticker for t in m.etfs()} == {"SMH", "GRNY"}, "ETFs in model = SMH, GRNY")

    # 3. rail OFF -> NO violations, even on a deliberately wild book
    wild = {t.ticker: 99.0 for t in m.single_names()}
    ok(validate_concentration_rail(wild, m, None) == [], "rail None -> no violations")
    ok(validate_concentration_rail(wild, m, RAIL_OFF) == [], "RAIL_OFF -> no violations")

    # 4. rail ON -> catches each violation type
    rail = ConcentrationRail(single_name_max_pct=12.0, total_single_name_max_pct=38.0,
                             etf_floor_pct=18.0, label="test")
    e_single = validate_concentration_rail({"NVDA": 15.0}, m, rail)
    ok(any("NVDA" in e and "single-name cap" in e for e in e_single),
       "single-name cap violation caught")
    e_total = validate_concentration_rail(m.as_map(), m, rail)  # model sums ~51 > 38
    ok(any("total AI single-name" in e for e in e_total), "total cap violation caught")
    e_floor = validate_concentration_rail({"SMH": 10.0, "GRNY": 3.0}, m, rail)
    ok(any("below floor" in e for e in e_floor), "ETF floor violation caught")

    # 5. the discussed preset uses YOUR ~55 number, not an external 38 — and the
    #    build surfaces a real tension: an 18% ETF floor fights Approach B.
    ok(RAIL_PRESET_DISCUSSED.total_single_name_max_pct == 55.0,
       "discussed preset total cap = 55 (own number, not external 38)")
    preset_errs = validate_concentration_rail(m.as_map(), m, RAIL_PRESET_DISCUSSED)
    ok(not any("total AI single-name" in e for e in preset_errs),
       "model single-name sum passes its own 55 cap")
    ok(any("below floor" in e for e in preset_errs),
       "FINDING: Approach-B model (AI-ETF ~8%) trips an 18% floor -> an ETF floor "
       "is inconsistent with convert-most-wrappers; another reason the rail is OFF by default")

    # 6. look-through table well-formed + the netting math
    for etf, hold in ETF_LOOKTHROUGH.items():
        ok(all(0.0 < w < 1.0 for w in hold.values()), f"{etf} weights are fractions")
    # SMH at 5% of book, 20% NVDA -> 1.0% NVDA via look-through
    implied = lookthrough_implied_pct("NVDA", {"SMH": 5.0})
    ok(abs(implied - 1.0) < 1e-9, f"NVDA look-through via SMH@5% should be 1.0%, got {implied}")

    # 7. 1.5x-ETF check only fires when book weights are supplied
    rail_mult = ConcentrationRail(single_name_etf_multiple=1.5, label="mult")
    ok(validate_concentration_rail({"NVDA": 50.0}, m, rail_mult) == [],
       "1.5x check skipped without etf_book_weights")
    e_mult = validate_concentration_rail({"NVDA": 50.0}, m, rail_mult, {"SMH": 5.0})
    ok(any("look-through weight" in e for e in e_mult),
       "1.5x check fires with etf_book_weights (NVDA 50% >> 1.5x*1.0%)")

    if fails:
        print("reallocate_config selftest: FAIL")
        for f in fails:
            print("  -", f)
        raise SystemExit(1)
    print(f"reallocate_config selftest: OK ({7} groups)  "
          f"[model single-name sum = {ts:g}% of book; rail default = OFF]")


if __name__ == "__main__":
    print(DEFAULT_DIALS.describe())
    print()
    _selftest()
