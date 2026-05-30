"""Unit tests for the Analyst mechanical reads (A2a: ⑤ ⑥ ⑨).

Run:  python -m pytest src/test_analyst.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from sources import SourceItem
from analyst import rotation_read, macro_read, staleness_read


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
