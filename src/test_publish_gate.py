"""Tests for publish_gate — the L5->L3 publish contract.

The centerpiece is the golden-fail: the actual 2026-06-01 feed is STRUCTURALLY
valid (Contract-C green) yet must FAIL the publish gate on both the canned stamp
and the mislabeled DXY. That is the proof the gate catches what Contract-C missed.
"""

import publish_gate as pg
from validators import validate_cockpit_feed


# ── fixtures ──────────────────────────────────────────────────────────────────
def _min_valid_feed(**overrides):
    """A minimal STRUCTURALLY-valid (Contract-C clean) feed; override pieces."""
    feed = {
        "generated_at": "2026-06-01T21:48:00+00:00",
        "staleness": {
            "stamp": "sourced: ...",
            "entries": [
                {"source": "portfolio", "date": "2026-06-01T21:48:47.195387+00:00", "age_days": 0, "stale": False, "flag": ""},
                {"source": "uw_price", "date": "2026-06-01T21:48:47.195591+00:00", "age_days": 0, "stale": False, "flag": ""},
                {"source": "uw_macro", "date": "2026-06-01T21:48:47.195689+00:00", "age_days": 0, "stale": False, "flag": ""},
                {"source": "fundstrat_daily", "date": "2026-05-29", "age_days": 3, "stale": True, "flag": "WARN"},
            ],
            "stale": ["fundstrat_daily"],
        },
        "hero": {"hero": {"count": 0, "names": [], "leading_sleeves": []},
                 "needs_you": {"count": 0, "items": []}},
        "fresh_signals": [],
        "holdings": [],
        "rotation": [],
        "macro": {
            "line": "10Y 4.45% \u00b7 2s10s +46bp \u00b7 10s30s +53bp \u00b7 DXY 99.4 (+0.1 5d) \u00b7 30Y 4.98% \u00b7 2Y 3.99%",
            "regime": {"duration": "flat", "vol": "calm", "dollar": "neutral",
                       "label": "duration_flat \u00b7 vol_calm \u00b7 dollar_neutral"},
            "alerts": [], "implications": [],
        },
        "catalysts": [],
        "questions": [],
        "research": {},
        "heartbeat": [],
        "synthesis": {},
    }
    feed.update(overrides)
    return feed


# the real 6/1 macro line (UUP's ~$27.76 printed under the DXY label)
_SIX_ONE_MACRO = {
    "line": "10Y 4.45% \u00b7 2s10s +46bp \u00b7 10s30s +53bp \u00b7 DXY 27.76 (+0.0 5d) \u00b7 30Y 4.98% \u00b7 2Y 3.99%",
    "regime": {"duration": "flat", "vol": "calm", "dollar": "neutral",
               "label": "duration_flat \u00b7 vol_calm \u00b7 dollar_neutral"},
    "alerts": [], "implications": [],
}


def _six_one_feed():
    """Reconstruct the 6/1 feed's contract-relevant fields: canned 10:10 stamp,
    real ~17:48 ET (21:48 UTC) live-source staleness, DXY=27.76."""
    return _min_valid_feed(
        generated_at="2026-06-01T10:10:00-04:00",
        macro=_SIX_ONE_MACRO,
    )


# ── sanity: the base fixture really is Contract-C clean ─────────────────────────
def test_base_fixture_is_contract_c_clean():
    assert validate_cockpit_feed(_min_valid_feed()) == []


def test_good_feed_passes_gate():
    feed = _min_valid_feed()
    assert pg.validate_publish_gate(feed) == []
    assert pg.is_valid_publish_gate(feed) is True


# ── the two 6/1 bugs, isolated ─────────────────────────────────────────────────
def test_canned_stamp_fails():
    feed = _min_valid_feed(generated_at="2026-06-01T10:10:00-04:00")  # 14:10 UTC vs 21:48
    problems = pg.validate_publish_gate(feed)
    assert any("stamp not from the clock" in p for p in problems), problems


def test_dxy_implausible_fails():
    feed = _min_valid_feed(macro=_SIX_ONE_MACRO)
    problems = pg.validate_publish_gate(feed)
    assert any("DXY implausible" in p for p in problems), problems


def test_honest_usd_uup_label_passes():
    """Repair A (2026-06-01): the engine now emits the dollar slot as
    "USD (UUP) 27.76" (UUP ~$28, inside its 20-40 band) instead of "DXY 27.76",
    so the going-forward feed PASSES the gate where the 6/1 feed failed."""
    honest = {**_min_valid_feed()["macro"],
              "line": "10Y 4.45% \u00b7 USD (UUP) 27.76 (+0.1 5d) \u00b7 30Y 4.98% \u00b7 2Y 3.99%"}
    feed = _min_valid_feed(macro=honest)
    assert pg.validate_publish_gate(feed) == []


def test_usd_uup_out_of_band_fails():
    """A ~99 under the "USD (UUP)" label = a DXY-magnitude value re-mislabeled
    onto the proxy slot — still caught by the 20-40 band."""
    bad = {**_min_valid_feed()["macro"],
           "line": "10Y 4.45% \u00b7 USD (UUP) 99 (+0.1 5d) \u00b7 30Y 4.98% \u00b7 2Y 3.99%"}
    feed = _min_valid_feed(macro=bad)
    problems = pg.validate_publish_gate(feed)
    assert any("USD (UUP) implausible" in p for p in problems), problems


# ── GOLDEN-FAIL: the real 6/1 feed is Contract-C clean but fails the gate ───────
def test_six_one_feed_is_contract_c_clean_but_fails_gate():
    feed = _six_one_feed()
    # Contract-C sees nothing wrong — this is why the bugs shipped.
    assert validate_cockpit_feed(feed) == []
    # The publish gate catches BOTH.
    problems = pg.validate_publish_gate(feed)
    assert any("stamp not from the clock" in p for p in problems), problems
    assert any("DXY implausible" in p for p in problems), problems
    assert pg.is_valid_publish_gate(feed) is False


def test_assert_raises_on_six_one_feed():
    try:
        pg.assert_valid_publish_gate(_six_one_feed())
        raised = False
    except ValueError as e:
        raised = True
        assert "do NOT publish" in str(e)
    assert raised


# ── edge cases ──────────────────────────────────────────────────────────────
def test_absent_optional_level_ok():
    # VIX is absent from the line (it drops gracefully) -> no VIX flag.
    feed = _min_valid_feed()
    assert "VIX" not in feed["macro"]["line"]
    assert pg.validate_publish_gate(feed) == []


def test_missing_datetime_staleness_cannot_verify():
    feed = _min_valid_feed(staleness={
        "stamp": "sourced: ...",
        "entries": [{"source": "fundstrat_daily", "date": "2026-05-29", "age_days": 3, "flag": "WARN"}],
        "stale": [],
    })
    problems = pg.validate_publish_gate(feed)
    assert any("cannot verify stamp" in p for p in problems), problems


def test_yield_out_of_band_fails():
    bad = {**_min_valid_feed()["macro"],
           "line": "10Y 45.0% \u00b7 DXY 99.4 (+0.1 5d) \u00b7 30Y 4.98% \u00b7 2Y 3.99%"}
    feed = _min_valid_feed(macro=bad)
    problems = pg.validate_publish_gate(feed)
    assert any("10Y implausible" in p for p in problems), problems


def test_non_dict_feed():
    assert pg.validate_publish_gate("not a feed")
    assert pg.is_valid_publish_gate(None) is False


def test_stamp_within_tolerance_passes():
    # 90 min apart < 2h tolerance -> OK (a slow build is fine).
    feed = _min_valid_feed(generated_at="2026-06-01T20:18:00+00:00")  # 21:48 - 90m
    assert not any("stamp" in p for p in pg.validate_publish_gate(feed))
