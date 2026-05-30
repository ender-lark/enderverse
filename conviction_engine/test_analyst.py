"""Unit tests for the Analyst mechanical reads (A2a: ⑤ ⑥ ⑨).

Run:  python -m pytest src/test_analyst.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from sources import SourceItem
from analyst import (
    rotation_read, macro_read, staleness_read,
    type_read, hero_needs_you_read, weight_read, NO_BREAK,
)


def _card(kind, subject, content, data=None, ts="2026-05-29",
          source="src", trust=0.9, grp="g"):
    return SourceItem(source, kind, subject, content, ts, trust, grp, data or {})


def _rot(subject, rel_1m, rel_3m, **extra):
    data = {"rel_1m": rel_1m, "rel_3m": rel_3m}
    data.update(extra)
    return _card("rotation", subject, f"{subject} rotation", data)


def _macro(subject, content, **data):
    return _card("macro", subject, content, data)


# =========================================================================== #
# ⑤ rotation_read
# =========================================================================== #
def test_rotation_classifies_and_groups():
    out = rotation_read([
        _rot("SMH", 0.06, 0.47),     # LEADING
        _rot("REMX", -0.01, -0.08),  # LAGGING
        _rot("XLF", 0.05, -0.10),    # lagged 3M, inflecting up 1M -> TURNING UP
    ])
    labels = {s["subject"]: s["label"] for s in out["sleeves"]}
    assert labels == {"SMH": "LEADING", "REMX": "LAGGING", "XLF": "TURNING UP"}
    assert out["by_label"]["LEADING"] == ["SMH"]
    assert out["by_label"]["LAGGING"] == ["REMX"]
    assert out["by_label"]["TURNING UP"] == ["XLF"]


def test_rotation_boundary_lead_at_0_05():
    # rel_3m exactly at the lead band (0.05) -> LEADING (inclusive)
    out = rotation_read([_rot("IGV", 0.0, 0.05)])
    assert out["sleeves"][0]["label"] == "LEADING"


def test_rotation_turning_down():
    # led 3M but rolling over last month -> TURNING DOWN
    out = rotation_read([_rot("MAGS", -0.05, 0.10)])
    assert out["sleeves"][0]["label"] == "TURNING DOWN"


def test_rotation_no_data():
    out = rotation_read([_rot("GRNJ", None, None)])
    s = out["sleeves"][0]
    assert s["label"] == "NO DATA"
    assert s["note"] == "no data"


def test_rotation_ignores_non_rotation_cards():
    out = rotation_read([_rot("SMH", 0.06, 0.47),
                         _macro("10Y", "10Y 4.45%", value=4.45)])
    assert [s["subject"] for s in out["sleeves"]] == ["SMH"]


def test_rotation_note_format():
    out = rotation_read([_rot("SMH", 0.06, 0.47)])
    assert out["sleeves"][0]["note"] == "LEADING +47%/3M vs mkt"


# =========================================================================== #
# ⑥ macro_read
# =========================================================================== #
def _macro_set():
    return [
        _macro("10Y", "10Y 4.76% (+5bp 5d)", value=4.76, value_5d_ago=4.71, chg_5d=5.0),
        _macro("2s10s", "2s10s +50bp", value=50, value_5d_ago=48, chg_5d=2),
        _macro("DXY", "DXY 98.5 (-1.3 5d)", value=98.5, value_5d_ago=99.8, chg_5d=-1.3),
        _macro("VIX", "VIX 17.2", value=17.2),
    ]


def test_macro_line_in_preferred_order():
    line = macro_read(_macro_set())["line"]
    assert "10Y 4.76%" in line and "VIX 17.2" in line
    assert line.index("10Y") < line.index("2s10s") < line.index("DXY") < line.index("VIX")


def test_macro_regime_rising_calm_weak():
    r = macro_read(_macro_set())["regime"]
    assert r["duration"] == "rising"   # 10Y +5bp
    assert r["vol"] == "calm"          # VIX 17.2
    assert r["dollar"] == "weak"       # DXY -1.3pt


def test_macro_regime_falling_elevated_strong():
    cards = [
        _macro("10Y", "10Y 4.20% (-6bp 5d)", value=4.20, chg_5d=-6.0),
        _macro("VIX", "VIX 26", value=26),
        _macro("DXY", "DXY 101 (+1.6 5d)", value=101, chg_5d=1.6),
    ]
    r = macro_read(cards)["regime"]
    assert r["duration"] == "falling"
    assert r["vol"] == "elevated"
    assert r["dollar"] == "strong"


def test_macro_alert_10y_boundary():
    not_fired = macro_read([_macro("10Y", "10Y 4.75%", value=4.75)])["alerts"]
    assert not any(a["alert"] == "10y_above" for a in not_fired)   # == threshold: no
    fired = macro_read([_macro("10Y", "10Y 4.76%", value=4.76)])["alerts"]
    assert any(a["alert"] == "10y_above" for a in fired)            # > threshold: yes


def test_macro_alert_vix_and_move():
    a = macro_read([_macro("VIX", "VIX 26", value=26),
                    _macro("MOVE", "MOVE 125", value=125)])["alerts"]
    keys = {x["alert"] for x in a}
    assert "vix_above" in keys and "move_above" in keys


def test_macro_alert_2s10s_sign_cross():
    crossed = macro_read([_macro("2s10s", "2s10s -5bp", value=-5, value_5d_ago=5)])["alerts"]
    assert any(a["alert"] == "2s10s_flip" for a in crossed)
    steady = macro_read([_macro("2s10s", "2s10s +50bp", value=50, value_5d_ago=48)])["alerts"]
    assert not any(a["alert"] == "2s10s_flip" for a in steady)


def test_macro_alert_dxy_5d_move():
    big = macro_read([_macro("DXY", "DXY (-2.5 5d)", value=97, chg_5d=-2.5)])["alerts"]
    assert any(a["alert"] == "dxy_5d_move" for a in big)
    small = macro_read([_macro("DXY", "DXY (-1.5 5d)", value=98, chg_5d=-1.5)])["alerts"]
    assert not any(a["alert"] == "dxy_5d_move" for a in small)


def test_macro_implications():
    imp = macro_read(_macro_set())["implications"]
    assert "headwind: long-duration growth (NVDA/SMH/MAGS)" in imp   # rising / 10Y alert
    assert "tailwind: critical minerals (LEU/MP/UUUU)" in imp        # dollar weak


# =========================================================================== #
# ⑨ staleness_read
# =========================================================================== #
REAL_CADENCE = {"uw_price": "daily", "fundstrat_bible": "monthly",
                "meridian": "static", "portfolio": "on_refresh"}


def test_staleness_basic_flags():
    staleness = {"uw_price": "2026-05-29", "fundstrat_bible": "2026-04-20",
                 "meridian": "2026-03-05", "portfolio": "2026-05-20"}
    out = staleness_read(staleness, as_of="2026-05-30", cadence_map=REAL_CADENCE)
    by = {e["source"]: e for e in out["entries"]}

    assert by["uw_price"]["stale"] is False and by["uw_price"]["flag"] == ""
    assert by["fundstrat_bible"]["stale"] is True and by["fundstrat_bible"]["flag"] == "⚠️"
    assert by["meridian"]["stale"] is False and by["meridian"]["flag"] == "(baseline)"
    assert by["portfolio"]["stale"] is True and by["portfolio"]["flag"] == "⚠️"
    assert out["stale"] == ["fundstrat_bible", "portfolio"]


def test_staleness_static_never_stale_however_old():
    out = staleness_read({"meridian": "2024-01-01"}, as_of="2026-05-30",
                         cadence_map=REAL_CADENCE)
    e = out["entries"][0]
    assert e["stale"] is False and e["flag"] == "(baseline)"


def test_staleness_daily_boundary():
    # age exactly == budget (2) -> not stale; age 3 -> stale
    at = staleness_read({"uw_price": "2026-05-29"}, as_of="2026-05-31",
                        cadence_map=REAL_CADENCE)
    assert at["entries"][0]["age_days"] == 2 and at["entries"][0]["stale"] is False
    over = staleness_read({"uw_price": "2026-05-29"}, as_of="2026-06-01",
                          cadence_map=REAL_CADENCE)
    assert over["entries"][0]["age_days"] == 3 and over["entries"][0]["stale"] is True


def test_staleness_stamp_format():
    out = staleness_read({"uw_price": "2026-05-29", "fundstrat_bible": "2026-04-20"},
                         as_of="2026-05-30", cadence_map=REAL_CADENCE)
    assert out["stamp"].startswith("sourced: ")
    assert "uw_price 05-29" in out["stamp"]
    assert "⚠️" in out["stamp"]            # fundstrat_bible is stale


def test_staleness_uses_live_cadence_dial_by_default():
    # no cadence_map passed -> uses sources.DEFAULT_CADENCE (meridian is static)
    out = staleness_read({"meridian": "2024-01-01"}, as_of="2026-05-30")
    assert out["entries"][0]["flag"] == "(baseline)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))


# =========================================================================== #
# ④ type_read
# =========================================================================== #
def _pos(ticker, pct=None):
    content = f"{ticker} {pct}% Owned" if pct is not None else f"{ticker} Owned"
    return _card("position", ticker, content, {"ticker": ticker, "pct": pct},
                 source="portfolio", trust=0.95, grp="own")


THESES = [
    {"ticker": "BMNR", "tier": "T1", "lane": "Generational",
     "source": "operator", "factor_tags": ["crypto", "eth"]},
    {"ticker": "SMH", "tier": "T1", "lane": "BuyAndHold",
     "source": "Lee", "factor_tags": ["ai", "semis"]},
    {"ticker": "LEU", "tier": "T2", "lane": "Speed",
     "source": "Meridian", "factor_tags": ["nuclear", "haleu"],
     "break": "HALEU contract canceled"},
]


def test_type_read_tracked_and_untracked():
    out = type_read([_pos("BMNR"), _pos("SMH"), _pos("AMZN")], THESES)
    assert {e["ticker"] for e in out["tracked"]} == {"BMNR", "SMH"}
    assert out["untracked"][0]["ticker"] == "AMZN"          # no thesis row
    assert out["untracked"][0]["type"] == "Tier-C (default)"
    assert out["tracked_count"] == 2 and out["untracked_count"] == 1


def test_type_read_lock_on_generational():
    out = type_read([_pos("BMNR"), _pos("SMH")], THESES)
    locks = {e["ticker"]: e["lock"] for e in out["tracked"]}
    assert locks["BMNR"] == "🔒"        # Generational -> locked
    assert locks["SMH"] == ""           # BuyAndHold  -> not locked


def test_type_read_type_why_break():
    out = type_read([_pos("BMNR"), _pos("LEU")], THESES)
    by = {e["ticker"]: e for e in out["tracked"]}
    assert by["BMNR"]["type"] == "T1 · Generational"
    assert by["BMNR"]["why"] == "operator · crypto, eth"     # source + factor tags
    assert by["BMNR"]["break"] == NO_BREAK                   # no break field -> —
    assert by["LEU"]["break"] == "HALEU contract canceled"   # surfaced when present


def test_type_read_dedupes_same_ticker_across_accounts():
    # portfolio emits one card per account; type_read is per NAME -> dedupe
    out = type_read([_pos("SMH"), _pos("SMH")], THESES)
    assert out["tracked_count"] == 1


def test_type_read_ignores_non_position_cards():
    out = type_read([_macro("10Y", "10Y 4.45%"), _pos("SMH")], THESES)
    assert out["tracked_count"] == 1 and out["untracked_count"] == 0


# =========================================================================== #
# ⑧ hero_needs_you_read
# =========================================================================== #
def test_hero_needs_you_counts():
    rotation = {"by_label": {"LEADING": ["SMH"]}}
    macro = {"alerts": [{"subject": "10Y", "note": "Newton resistance"}]}
    staleness = {"stale": ["portfolio", "fundstrat_bible"]}  # only portfolio critical
    type_reads = {"tracked": [
        {"ticker": "SMH", "break": NO_BREAK},
        {"ticker": "BMNR", "break": NO_BREAK},
        {"ticker": "LEU", "break": "HALEU contract canceled"},
    ]}
    out = hero_needs_you_read(rotation, macro, staleness, type_reads,
                              monitor_reentry=["MP"], red_gates=["NVDA add RED"])
    # stale-critical(portfolio) + macro(10Y) + monitor(MP) + red(NVDA) = 4
    assert out["needs_you"]["count"] == 4
    assert {i["reason"] for i in out["needs_you"]["items"]} == {
        "stale_critical", "macro_alert", "monitor_reentry", "red_gate"}
    # fundstrat_bible stale but NOT critical -> excluded
    details = {(i["reason"], i["detail"]) for i in out["needs_you"]["items"]}
    assert ("stale_critical", "fundstrat_bible") not in details


def test_hero_excludes_flagged_and_broken():
    rotation = {"by_label": {"LEADING": ["SMH"]}}
    type_reads = {"tracked": [
        {"ticker": "SMH", "break": NO_BREAK},
        {"ticker": "MP", "break": NO_BREAK},      # but flagged via monitor_reentry
        {"ticker": "LEU", "break": "broken"},     # broken thesis -> not hero
    ]}
    out = hero_needs_you_read(rotation, {"alerts": []}, {"stale": []}, type_reads,
                              monitor_reentry=["MP"])
    assert out["hero"]["names"] == ["SMH"]        # MP flagged, LEU broken
    assert out["hero"]["leading_sleeves"] == ["SMH"]


def test_hero_needs_you_empty_inputs():
    out = hero_needs_you_read({}, {}, {}, {})
    assert out["needs_you"]["count"] == 0
    assert out["hero"]["count"] == 0


# =========================================================================== #
# ⑩ weight_read
# =========================================================================== #
def test_weight_same_group_collapses_to_one_stream():
    # the two Fundstrat plugs on ONE name = 1 independent stream (echo-chamber guard)
    out = weight_read([
        _card("analyst_call", "XLF", "Lee: own financials",
              source="fundstrat_bible", trust=0.70, grp="fundstrat"),
        _card("analyst_call", "XLF", "Newton: XLF breakout",
              source="fundstrat_daily", trust=0.70, grp="fundstrat"),
    ])
    assert out["XLF"]["independent_streams"] == 1
    assert len(out["XLF"]["voices"]) == 1


def test_weight_different_groups_two_streams():
    out = weight_read([
        _card("analyst_call", "LEU", "Meridian: HALEU monopoly",
              source="meridian", trust=0.75, grp="thematic_research"),
        _card("analyst_call", "LEU", "Lee: nuclear OW",
              source="fundstrat_bible", trust=0.70, grp="fundstrat"),
    ])
    assert out["LEU"]["independent_streams"] == 2
    assert len(out["LEU"]["voices"]) == 2


def test_weight_keeps_highest_trust_voice_per_group():
    out = weight_read([
        _card("analyst_call", "NVDA", "low-trust take",
              source="fundstrat_daily", trust=0.65, grp="fundstrat"),
        _card("analyst_call", "NVDA", "high-trust take",
              source="fundstrat_bible", trust=0.72, grp="fundstrat"),
    ])
    assert out["NVDA"]["independent_streams"] == 1
    voice = out["NVDA"]["voices"][0]
    assert voice["trust"] == 0.72 and voice["content"] == "high-trust take"


def test_weight_max_trust():
    out = weight_read([
        _card("analyst_call", "SMH", "a", source="fundstrat_bible",
              trust=0.70, grp="fundstrat"),
        _card("position", "SMH", "SMH 9.9% Owned", source="portfolio",
              trust=0.95, grp="own"),
    ])
    assert out["SMH"]["max_trust"] == 0.95
    assert out["SMH"]["independent_streams"] == 2


def test_weight_skips_subjectless():
    out = weight_read([_card("stance", "", "macro stance: constructive",
                             source="fundstrat_bible", trust=0.70, grp="fundstrat")])
    assert out == {}
