"""Conviction Engine · Layer 3 (Analyst) — feed assembler (the OUTPUT step).

Runs the Analyst reads over a CollectedSnapshot bundle and arranges their
outputs into ONE Contract-C CockpitFeed (the boundary Layer 4 consumes).
Deterministic: same inputs -> same feed. Used by the golden freeze (A5), the
golden-master test (A6), and the live runtime (A7).

A read never grades or fabricates; this step only ARRANGES read outputs into the
cockpit shape. The only transforms here are mechanical and named:
  • tier -> risk-class (ty)                         TIER_RISK
  • tier-band floor -> under-sized flag             TIER_FLOOR
  • ticker -> rotation-proxy sleeve                 NAME_SLEEVE
Catalysts / questions are cockpit-curated (not data-derived), so the assembler
emits them empty — they are layered in at Layer 4, not invented here.
"""
from __future__ import annotations

from types import SimpleNamespace

from analyst import (rotation_read, macro_read, staleness_read,
                     type_read, hero_needs_you_read, weight_read)
from analyst_judgment import (conviction_read, conviction_direction_read,
                              net_read, fresh_signal_read)
from analyst_config import theses_by_ticker

# ── name -> rotation-proxy sleeve (the leaderboard subject that stands in for a
#    single name's relative strength). v1 glue, tunable. A name with no proxy
#    falls to "_other" and simply carries no rotation label. ──
NAME_SLEEVE = {
    # AI / Semiconductors (SMH proxy) — incl. mega-cap AI + semis ETFs + photonics
    "SMH": "SMH", "MAGS": "SMH", "NVDA": "SMH", "MU": "SMH", "AVGO": "SMH",
    "ANET": "SMH", "IVES": "SMH", "GOOGL": "SMH", "MSFT": "SMH", "AMZN": "SMH",
    "ASML": "SMH", "NBIS": "SMH", "SOXX": "SMH", "FTXL": "SMH", "LITE": "SMH",
    "POET": "SMH",
    # Software (IGV proxy)
    "IGV": "IGV", "ORCL": "IGV", "RDDT": "IGV", "PLTR": "IGV", "CIBR": "IGV",
    # Quality core (GRNY proxy)
    "GRNY": "GRNY", "GRNJ": "GRNY", "COST": "GRNY", "RPG": "GRNY",
    # Financials (XLF proxy)
    "XLF": "XLF", "GS": "XLF", "JPM": "XLF", "SOFI": "XLF",
    # Nuclear (URA proxy)
    "LEU": "URA", "UUUU": "URA", "CCJ": "URA", "BWXT": "URA", "UURAF": "URA",
    # Critical minerals (REMX proxy)
    "MP": "REMX", "LYSDY": "REMX", "LIT": "REMX",
    # Crypto (IBIT proxy)
    "BMNR": "IBIT", "IBIT": "IBIT", "ETHA": "IBIT", "MSTR": "IBIT",
    "COIN": "IBIT", "HYPE": "IBIT",
    # Electrification (VOLT proxy)
    "VOLT": "VOLT", "GEV": "VOLT", "PWR": "VOLT", "STRL": "VOLT", "IESC": "VOLT",
    "BE": "VOLT", "NXT": "VOLT", "FIX": "VOLT", "DRIV": "VOLT", "PBW": "VOLT",
    # Gold / Hedge (GDX proxy)
    "GDX": "GDX", "SIL": "GDX", "WPM": "GDX", "NUE": "GDX",
}
# sleeve -> display category (cat) for the holdings groups
SLEEVE_CAT = {
    "SMH": "AI / Semiconductors", "IGV": "Software", "GRNY": "Quality core",
    "XLF": "Financials", "URA": "Nuclear", "REMX": "Critical minerals",
    "IBIT": "Crypto", "VOLT": "Electrification", "GDX": "Gold / Hedge",
    "_other": "Other holdings",
}
# tier -> cockpit risk-class (ty). A real transform, not a rename.
TIER_RISK = {"T1": "Core", "T2": "Core", "T3": "Tactical", "T4": "Probe"}
# tier -> position-size floor (% of book). Below floor on a high-confidence name
# trips the under-sizing lens inside ③ — the canonical "right but too small".
TIER_FLOOR = {"T1": 8.0, "T2": 4.0, "T3": 1.5, "T4": 0.0}

ENDORSEMENT_KINDS = ("analyst_call", "what_to_own", "stance")


def _ns(items):
    return [SimpleNamespace(**it) for it in items]


def assemble_feed(bundle: dict, parabolic=None, generated_at=None) -> dict:
    """bundle = {as_of, snapshot:<CollectedSnapshot>, theses:[...with stance]}.
    Returns a Contract-C CockpitFeed (passes validate_cockpit_feed)."""
    as_of = bundle["as_of"]
    snap = bundle["snapshot"]
    theses = bundle["theses"]
    parabolic = set(parabolic or [])
    cards = _ns(snap["items"])
    by_tk = theses_by_ticker(theses)

    # ── sleeve-level mechanical reads ──
    rot = rotation_read(cards)
    rot_label = {s["subject"]: s["label"] for s in rot["sleeves"]}
    macro = macro_read(cards)
    stale = staleness_read(snap["staleness"], as_of)
    position_cards = [c for c in cards if getattr(c, "kind", None) == "position"]
    type_r = type_read(position_cards, theses)
    type_by_tk = {x["ticker"]: x for x in (type_r["tracked"] + type_r["untracked"])}

    # ── held names (dedup, first-seen order) ──
    held, seen = [], set()
    for c in position_cards:
        if c.subject and c.subject not in seen:
            held.append(c)
            seen.add(c.subject)

    # ── direction reads for held names + any name carrying endorsement cards
    #    (watchlist picks like FN feed the Actions strip) ──
    endorsement_subjects = {c.subject for c in cards
                            if getattr(c, "kind", None) in ENDORSEMENT_KINDS and c.subject}
    dir_reads = {tk: conviction_direction_read(tk, cards, as_of)
                 for tk in sorted(seen | endorsement_subjects)}

    fresh = fresh_signal_read(list(dir_reads.values()), theses)
    fresh_set = set(fresh["fresh_tickers"])
    wt = weight_read([c for c in cards
                      if getattr(c, "kind", None) in ENDORSEMENT_KINDS])

    # ── per-name pos rows, grouped by sleeve ──
    pos_by_sleeve: dict = {}
    for c in held:
        tk = c.subject
        th = by_tk.get(tk)
        conv = conviction_read(tk, th, cards)
        cd = dir_reads[tk]
        d = c.data or {}
        pct = d.get("pct")
        tier = (th or {}).get("tier")
        underweight = pct is not None and pct < TIER_FLOOR.get(tier, 0.0)
        nr = net_read(tk, th, conv,
                      rotation_label=rot_label.get(NAME_SLEEVE.get(tk)),
                      weighted=wt.get(tk), parabolic=(tk in parabolic),
                      underweight=underweight)
        t4 = type_by_tk.get(tk, {})
        pos = {
            "t": tk, "n": d.get("name", tk), "pct": pct, "st": "Owned",
            "cv": conv["cv"], "ty": TIER_RISK.get(tier, "Tactical"),
            "own": d.get("owner", ""), "lock": t4.get("lock", ""),
            "fresh": tk in fresh_set, "cd": cd["cd"], "cdNote": cd["cdNote"],
            "nr": nr["nr"], "dr": [[t4.get("why", "—")]], "be": t4.get("break", "—"),
        }
        pos_by_sleeve.setdefault(NAME_SLEEVE.get(tk, "_other"), []).append(pos)

    holdings = [{"cat": SLEEVE_CAT.get(s, "Other holdings"),
                 "rot": {"w": rot_label.get(s, "")}, "pos": ps}
                for s, ps in pos_by_sleeve.items()]

    hero = hero_needs_you_read(rot, macro, stale, type_r,
                               fresh_signals=fresh["fresh_signals"])

    return {
        "generated_at": generated_at or f"{as_of}T16:00:00",
        "staleness": stale,
        "hero": hero,
        "fresh_signals": fresh["fresh_signals"],
        "holdings": holdings,
        "rotation": rot["sleeves"],
        "macro": macro,
        "catalysts": [],
        "questions": [],
        "research": {},
    }
