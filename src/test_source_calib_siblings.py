"""
test_source_calib_siblings.py — v12.0 Go 8 source-calibration siblings.

Covers source_call_tracker.batch_classify (Inbox -> Log-ready entries),
source_call_tracker.scoring_lag_sweep (window-end-overdue unscored calls), and
the pretrade_gate convention pin (source calibration keys on the call-quality
ladder A/B/C/D, never the position tier T1-T4).
"""

# source_call_tracker FIRST: pretrade_gate does sys.path.insert(0, "/mnt/project"),
# which in a dual-checkout sandbox would otherwise shadow the repo source_call_tracker
# (the project snapshot predates batch_classify / scoring_lag_sweep).
import source_call_tracker as sct
import pretrade_gate as ptg


# ---------- batch_classify ----------

def test_batch_classify_structures_log_ready_entries():
    raw = [
        {"source": "Newton", "ticker": "nvda",
         "text": "Buy NVDA above $120, target $150, stop $110, over the next two weeks",
         "date": "2026-05-20"},
        {"source": "Lee",
         "text": "We continue to favor semiconductors into year-end"},
    ]
    out = sct.batch_classify(raw, now="2026-05-31")
    assert len(out) == 2
    a = out[0]
    assert a["source"] == "newton"            # lowercased
    assert a["ticker"] == "NVDA"              # uppercased
    assert a["tier"] in ("A", "B")            # named ticker + level + action
    assert a["outcome"] == "Pending"          # pre-registered, not yet scored
    assert a["falsification_condition"]       # populated
    assert a["window_end"]                    # populated
    # the soft "favor ... into year-end" call is unfalsifiable narrative -> D
    assert out[1]["tier"] == "D"


def test_batch_classify_window_end_anchored_to_call_date():
    raw = [{"source": "newton", "ticker": "MU",
            "text": "MU should work over the coming months", "date": "2026-05-01"}]
    out = sct.batch_classify(raw, now="2026-05-31")
    we = sct._parse_date(out[0]["window_end"])
    cd = sct._parse_date("2026-05-01")
    assert we is not None and we > cd          # window measured from the call date


def test_batch_classify_skips_empty_or_sourceless():
    raw = [{"source": "newton", "text": ""}, {"text": "no source here"}, "not-a-dict"]
    assert sct.batch_classify(raw, now="2026-05-31") == []


# ---------- scoring_lag_sweep ----------

def _calls():
    return [
        # overdue + unscored + scorable ladder -> DUE
        {"source": "newton", "ticker": "NVDA", "tier": "A", "outcome": None,
         "date": "2026-04-01", "window_end": "2026-04-15"},
        # already scored -> not due
        {"source": "lee", "ticker": "MU", "tier": "A", "outcome": "Win",
         "date": "2026-04-01", "window_end": "2026-04-15"},
        # backfill -> not due
        {"source": "newton", "ticker": "BMNR", "tier": "A", "outcome": None,
         "date": "2026-04-01", "window_end": "2026-04-15", "backfill": True},
        # Tier D (unfalsifiable) -> not due
        {"source": "meridian", "ticker": "LEU", "tier": "D", "outcome": None,
         "date": "2026-04-01", "window_end": "2026-04-15"},
        # window still open -> not due
        {"source": "farrell", "ticker": "HYPE", "tier": "B", "outcome": None,
         "date": "2026-05-20", "window_end": "2026-12-01"},
    ]


def test_scoring_lag_sweep_flags_only_overdue_unscored():
    sweep = sct.scoring_lag_sweep(_calls(), now="2026-05-31")
    assert sweep["count"] == 1
    assert {c["ticker"] for c in sweep["due"]} == {"NVDA"}
    assert sweep["by_source"] == {"newton": 1}
    assert sweep["oldest_overdue_days"] == 46    # 2026-04-15 -> 2026-05-31


def test_scoring_lag_surface_line_clean_vs_flagged():
    clean = sct.scoring_lag_sweep([], now="2026-05-31")
    assert "clean" in sct.scoring_lag_surface_line(clean)
    flagged = sct.scoring_lag_sweep(_calls(), now="2026-05-31")
    line = sct.scoring_lag_surface_line(flagged)
    assert "1 call" in line and "newton:1" in line


# ---------- pretrade_gate convention pin ----------

def test_source_calib_keys_on_ladder_not_position_tier():
    rates = {"newton": {"A": {"band": "CONSISTENT_MISS", "n": 20}}}
    # correct axis: the call-quality ladder
    flags_a = ptg._check_source_calibration("ADD", "newton", "A", rates)
    assert any(f.code == "SOURCE_CONSISTENT_MISS" and f.color == "RED" for f in flags_a)
    # wrong axis: the position tier has no key in source_rates -> silent no-op (the
    # exact bug the v12.0 pin prevents)
    assert ptg._check_source_calibration("ADD", "newton", "T1", rates) == []


def test_source_calib_below_breakeven_amber():
    rates = {"lee": {"B": {"band": "BELOW_BREAKEVEN", "n": 18}}}
    flags = ptg._check_source_calibration("ADD", "lee", "B", rates)
    assert any(f.color == "YELLOW" for f in flags)


def test_source_calib_dormant_under_n15():
    rates = {"newton": {"A": {"band": "CONSISTENT_MISS", "n": 9}}}
    assert ptg._check_source_calibration("ADD", "newton", "A", rates) == []


def test_evaluate_accepts_call_ladder_kwarg():
    res = ptg.evaluate("ADD", "NVDA", 1000.0, [], [], 1_000_000.0, call_ladder="A")
    assert res is not None and res.action == "ADD"
