"""Conviction Engine · ⑩ LEAN-IN lane (Opportunity-Engine pivot, Chunk A).

The lean-in lane is the OPPORTUNITY mirror of risk surfacing: it proactively
surfaces names that look good (rising conviction + a working/turning tape) with
their evidence, an opportunity-cost read, the sizing ceiling, and what would
RAISE conviction — and it is SYMMETRIC (also prints `cooling` / `still_lagging`)
and NEVER auto-buys (every item action == "NONE").

These tests pin the load-bearing invariants:
  • additive + forward-compatible (a feed without the block still validates);
  • burned sleeves (stance MONITOR) are conviction-GATED out unless a high-conf
    re-entry has cleared;
  • symmetric — cooling / still_lagging fire on the negative reads;
  • no-auto-buy — action == "NONE", enforced at the contract validator too;
  • consistency with the Actions strip (an ⏳act name reads lean_in, a 👁watch
    name reads build).
Dials live in analyst_config (LEAN_IN_*); a couple are exercised here to prove
they're wired (adjustable, not hard-coded).
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from feed_assembler import assemble_feed
from validators import validate_cockpit_feed, _validate_lean_in_row, _VALID_LEAN
from analyst_judgment import lean_in_read, actions_read
from build_golden import build_snapshot_bundle

PARABOLIC = {"MU"}


# --------------------------------------------------------------------------- #
# tiny fixtures for the unit-level reads
# --------------------------------------------------------------------------- #
def _card(subject, *, kind="analyst_call", direction="overweight", group="fundstrat",
          trust=0.70, source="fundstrat_bible", date="2026-05-28"):
    return SimpleNamespace(source=source, kind=kind, subject=subject,
                           content=f"{subject} endorsement", timestamp=date,
                           trust_weight=trust, independence_group=group,
                           data={"direction": direction, "date": date})


def _thesis(ticker, *, tier="T2", lane="Tactical", stance="ACTIVE", tags=None,
            source="fundstrat"):
    return {"ticker": ticker, "tier": tier, "lane": lane, "stance": stance,
            "source": source, "factor_tags": list(tags or [])}


def _dr(ticker, cd="flat", *, event=None):
    events = [{"date": "2026-05-28", "event": event}] if event else []
    return {"ticker": ticker, "cd": cd, "cdNote": "n/a", "events": events}


def _lean_for(tk, items):
    return next((i for i in items if i["ticker"] == tk), None)


# --------------------------------------------------------------------------- #
# 1) integration over the golden snapshot
# --------------------------------------------------------------------------- #
def test_lean_in_present_and_contract_valid():
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    assert "lean_in" in feed and isinstance(feed["lean_in"], list)
    assert validate_cockpit_feed(feed) == []


def test_every_item_action_is_none():
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    assert feed["lean_in"], "expected at least one lean-in item in the golden snapshot"
    assert all(it["action"] == "NONE" for it in feed["lean_in"])


def test_all_leans_are_valid_words():
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    assert all(it["lean"] in _VALID_LEAN for it in feed["lean_in"])


def test_monitor_names_absent_without_reentry():
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    tickers = {it["ticker"] for it in feed["lean_in"]}
    for burned in ("BMNR", "LEU", "UUUU", "MP", "IBIT"):
        assert burned not in tickers, f"{burned} (MONITOR) must be gated out of lean_in"


def test_consistent_with_actions_strip():
    """An ⏳act name reads lean_in; a 👁watch name reads build — the lean-in lane
    must not contradict the Actions strip for the same name."""
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    actions = {a["ticker"]: a["kind"] for a in feed["actions"]}
    ita = _lean_for("ITA", feed["lean_in"])
    fn = _lean_for("FN", feed["lean_in"])
    assert actions.get("ITA") == "buy_now" and ita is not None and ita["lean"] == "lean_in"
    assert actions.get("FN") == "watch_entry" and fn is not None and fn["lean"] == "build"


# --------------------------------------------------------------------------- #
# 2) the symmetric reads (the unit logic)
# --------------------------------------------------------------------------- #
def test_lean_in_fires_on_working_tape_with_room():
    tk = "ZZZ"
    rot = {tk: {"subject": "IGV", "label": "TURNING UP", "rel_3m_vs_smh": -0.05}}
    out = lean_in_read([_dr(tk, "flat")], [_thesis(tk)], [_card(tk)], "2026-05-29",
                       rotation_by_name=rot, held=set())   # not owned -> room
    it = _lean_for(tk, out["lean_in"])
    assert it and it["lean"] == "lean_in" and it["action"] == "NONE"
    assert "SMH" in it["opportunity_cost"]


def test_act_trigger_overrides_to_lean_in_even_when_sized():
    """A confirmed entry trigger (⏳act) leans in even on an owned, fully-sized,
    no-rotation name — staying consistent with its buy_now action."""
    tk = "ZZZ"
    out = lean_in_read([_dr(tk, "up", event="breakout")], [_thesis(tk)], [_card(tk)],
                       "2026-05-29", held={tk}, underweight=set(), fresh_act={tk})
    it = _lean_for(tk, out["lean_in"])
    assert it and it["lean"] == "lean_in"


def test_watch_signal_reads_build_not_lean_in():
    tk = "ZZZ"
    out = lean_in_read([_dr(tk, "up", event="new_top5")], [_thesis(tk)], [_card(tk)],
                       "2026-05-29", held=set(), fresh_watch={tk})
    it = _lean_for(tk, out["lean_in"])
    assert it and it["lean"] == "build"


def test_cooling_is_symmetric_on_direction_down():
    tk = "ZZZ"
    out = lean_in_read([_dr(tk, "down")], [_thesis(tk)], [_card(tk)], "2026-05-29",
                       held={tk})
    it = _lean_for(tk, out["lean_in"])
    assert it and it["lean"] == "cooling" and it["action"] == "NONE"


def test_still_lagging_on_unturned_laggard():
    tk = "ZZZ"
    rot = {tk: {"subject": "XLF", "label": "LAGGING", "rel_3m_vs_smh": -0.30}}
    out = lean_in_read([_dr(tk, "flat")], [_thesis(tk)], [_card(tk)], "2026-05-29",
                       rotation_by_name=rot, held={tk})
    it = _lean_for(tk, out["lean_in"])
    assert it and it["lean"] == "still_lagging"


def test_sized_leading_core_is_quiet():
    """Owned, at/above floor, leading, flat, no fresh trigger -> no item
    (quiet-by-default; the lane is not noise on the core)."""
    tk = "ZZZ"
    rot = {tk: {"subject": "SMH", "label": "LEADING", "rel_3m_vs_smh": 0.0}}
    out = lean_in_read([_dr(tk, "flat")], [_thesis(tk)], [_card(tk)], "2026-05-29",
                       rotation_by_name=rot, held={tk}, underweight=set())
    assert _lean_for(tk, out["lean_in"]) is None


# --------------------------------------------------------------------------- #
# 3) the conviction-gated MONITOR reframe
# --------------------------------------------------------------------------- #
def test_monitor_gated_out_then_in_on_reentry():
    tk = "ZZZ"
    th = [_thesis(tk, stance="MONITOR")]
    rot = {tk: {"subject": "IBIT", "label": "TURNING UP", "rel_3m_vs_smh": 0.10}}
    base = dict(rotation_by_name=rot, held={tk})

    gated = lean_in_read([_dr(tk, "up", event="bottom_in")], th, [_card(tk)],
                         "2026-05-29", **base)
    assert _lean_for(tk, gated["lean_in"]) is None      # burned -> gated out

    cleared = lean_in_read([_dr(tk, "up", event="bottom_in")], th, [_card(tk)],
                           "2026-05-29", fresh_act={tk}, high_conf_reentry={tk}, **base)
    it = _lean_for(tk, cleared["lean_in"])
    assert it and it["stance_gate"] == "monitor"
    assert it["lean"] in ("lean_in", "build")
    assert any("burned sleeve" in c for c in it["caveats"])


# --------------------------------------------------------------------------- #
# 4) honesty caveats + adjustable dials
# --------------------------------------------------------------------------- #
def test_clustered_caveat_on_single_source():
    tk = "ZZZ"
    rot = {tk: {"subject": "IGV", "label": "TURNING UP", "rel_3m_vs_smh": -0.05}}
    out = lean_in_read([_dr(tk, "flat")], [_thesis(tk)], [_card(tk)], "2026-05-29",
                       rotation_by_name=rot, held=set())
    it = _lean_for(tk, out["lean_in"])
    assert it and any("clustered" in c for c in it["caveats"])


def test_require_cd_up_dial_is_wired():
    """Flipping the require_cd_up dial demands a fresh up-event before a tape-only
    lean_in — proving the threshold is adjustable, not hard-coded."""
    tk = "ZZZ"
    rot = {tk: {"subject": "IGV", "label": "TURNING UP", "rel_3m_vs_smh": -0.05}}
    loose = lean_in_read([_dr(tk, "flat")], [_thesis(tk)], [_card(tk)], "2026-05-29",
                         rotation_by_name=rot, held=set(), require_cd_up=False)
    strict = lean_in_read([_dr(tk, "flat")], [_thesis(tk)], [_card(tk)], "2026-05-29",
                          rotation_by_name=rot, held=set(), require_cd_up=True)
    assert _lean_for(tk, loose["lean_in"])["lean"] == "lean_in"
    # under the strict dial a flat (no up-event) tape no longer leans in
    strict_it = _lean_for(tk, strict["lean_in"])
    assert strict_it is None or strict_it["lean"] != "lean_in"


# --------------------------------------------------------------------------- #
# 5) the no-auto-buy contract + forward-compatibility
# --------------------------------------------------------------------------- #
def test_validator_rejects_nonzero_action():
    problems = _validate_lean_in_row({"ticker": "ZZZ", "lean": "lean_in", "action": "BUY"})
    assert any("action" in p for p in problems)


def test_validator_rejects_unknown_lean_word():
    problems = _validate_lean_in_row({"ticker": "ZZZ", "lean": "yolo"})
    assert any("lean" in p for p in problems)


def test_validator_accepts_minimal_row():
    assert _validate_lean_in_row({"ticker": "ZZZ"}) == []


def test_validator_requires_ticker():
    assert any("ticker" in p for p in _validate_lean_in_row({"lean": "lean_in"}))


def test_feed_without_lean_in_still_validates():
    """Forward-compatible: a feed that predates the block (no lean_in key) is
    still a valid CockpitFeed — additive, never required."""
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    del feed["lean_in"]
    assert validate_cockpit_feed(feed) == []


def test_feed_with_bad_lean_in_row_fails():
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    feed["lean_in"] = [{"ticker": "ZZZ", "action": "ADD"}]   # auto-buy not allowed
    assert validate_cockpit_feed(feed) != []


def test_caller_can_override_lean_in():
    """assemble_feed exposes the same additive override seam as radar."""
    override = [{"ticker": "ZZZ", "lean": "lean_in", "action": "NONE"}]
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC, lean_in=override)
    assert feed["lean_in"] == override


# --------------------------------------------------------------------------- #
# 6) promotion onto the Actions strip (front-and-center; deduped; lean_in-only)
# --------------------------------------------------------------------------- #
def _li(ticker, lean="lean_in", conviction="Promising", rotation="TURNING UP"):
    return {"ticker": ticker, "lean": lean, "conviction": conviction,
            "rotation": rotation, "headline": f"{ticker} looks good", "action": "NONE"}


def test_promotion_adds_new_lean_in_as_action():
    out = actions_read([], [], [_thesis("ZZZ")], lean_in_items=[_li("ZZZ")])
    row = next((a for a in out["actions"] if a["ticker"] == "ZZZ"), None)
    assert row and row["kind"] == "lean_in"
    assert row["confidence"] == "Moderate"            # Promising -> Moderate
    assert "no auto-buy" in row["your_move"].lower()
    assert row["gate"] is not None                    # sizing gate hook present


def test_promotion_dedupes_against_a_fresh_signal():
    """A name already on the strip as a buy_now is NOT duplicated by its lean-in."""
    fresh = [{"ticker": "ITA", "urgency": "act", "what": "breakout",
              "why": "broke out", "when": "2026-05-28", "detail": "x"}]
    out = actions_read(fresh, [], [_thesis("ITA")], lean_in_items=[_li("ITA")])
    ita_rows = [a for a in out["actions"] if a["ticker"] == "ITA"]
    assert len(ita_rows) == 1 and ita_rows[0]["kind"] == "buy_now"


def test_only_lean_in_is_promoted_not_build():
    out = actions_read([], [], [_thesis("ZZZ")], lean_in_items=[_li("ZZZ", lean="build")])
    assert not any(a["kind"] == "lean_in" for a in out["actions"])


def test_strong_lean_in_promotes_high_confidence():
    out = actions_read([], [], [_thesis("ZZZ")],
                       lean_in_items=[_li("ZZZ", conviction="Strong")])
    row = next(a for a in out["actions"] if a["ticker"] == "ZZZ")
    assert row["confidence"] == "High"


def test_golden_actions_unchanged_by_promotion():
    """In the golden snapshot the only lean_in (ITA) is already a buy_now, so
    promotion is a deliberate no-op — the act strip must be untouched."""
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    kinds = {a["ticker"]: a["kind"] for a in feed["actions"]}
    assert kinds == {"ITA": "buy_now", "FN": "watch_entry"}
    assert not any(a["kind"] == "lean_in" for a in feed["actions"])


def test_promoted_action_validates():
    out = actions_read([], [], [_thesis("ZZZ")], lean_in_items=[_li("ZZZ")])
    feed = assemble_feed(build_snapshot_bundle(), parabolic=PARABOLIC)
    feed["actions"] = out["actions"]
    assert validate_cockpit_feed(feed) == []           # lean_in is a valid action kind
