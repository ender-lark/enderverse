import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dossier_universe as du


def _feed(ticker):
    return {"today_decide": {"cards": [{"ticker": ticker, "decision_card": {"move": {"direction": "ADD"}}, "card_id": f"{ticker}-ADD"}]}}


def test_interest_universe_unions_sources_and_excludes_macro_cash():
    uni = du.interest_universe(
        feed=_feed("AAA"),
        open_opportunities={"opportunities": [{"ticker": "BBB", "kind": "lean_in"}],
                             "history": [{"ticker": "HHH", "kind": "lean_in"}]},
        source_calls=[{"ticker": "CCC", "date": "2026-06-16"},
                      {"ticker": "DDD", "date": "2025-01-01"},   # too old -> excluded
                      {"ticker": "SPX", "date": "2026-06-16"},    # macro -> excluded
                      {"ticker": "SPAXX", "date": "2026-06-16"}], # cash -> excluded
        top_prospects={"EEE": {"add_date": "2026-05-28"}, "_meta": "skip-scalar"},
        parabolic={"results": [{"ticker": "FFF"}]},
        source_call_candidates=[{"ticker": "GGG"}],
        today="2026-06-18",
        recent_call_days=45,
    )
    tickers = {r["ticker"] for r in uni}
    assert tickers == {"AAA", "BBB", "HHH", "CCC", "EEE", "FFF", "GGG"}
    assert "SPX" not in tickers and "SPAXX" not in tickers and "DDD" not in tickers
    # reasons are collected
    bbb = next(r for r in uni if r["ticker"] == "BBB")
    assert any("opportunity" in x or "lean-in" in x for x in bbb["reasons"])


def test_keeper_report_classifies_missing_stale_refresh_covered(tmp_path):
    # AAA fresh today (covered); BBB stale (old); CCC missing (no file);
    # DDD fresh but old enough to be within the refresh lead window.
    (tmp_path / "AAA.md").write_text("**CURRENT VERDICT (2026-06-18):** HOLD · conviction **high**\n", encoding="utf-8")
    (tmp_path / "BBB.md").write_text("**CURRENT VERDICT (2026-01-01):** HOLD · conviction **high**\n", encoding="utf-8")
    (tmp_path / "DDD.md").write_text("**CURRENT VERDICT (2026-05-09):** HOLD · conviction **high**\n", encoding="utf-8")  # 40d old
    universe = [{"ticker": t, "reasons": ["test"]} for t in ("AAA", "BBB", "CCC", "DDD")]
    rep = du.keeper_report(
        universe, dossier_dir=tmp_path, today="2026-06-18",
        max_verdict_age_days=45, refresh_lead_days=10,
    )
    klass = {r["ticker"]: r["klass"] for r in rep["rows"]}
    assert klass == {"AAA": "covered", "BBB": "stale", "CCC": "missing", "DDD": "refresh_soon"}
    assert rep["to_draft"] == ["CCC"]
    assert set(rep["to_refresh"]) == {"BBB", "DDD"}
    assert rep["status"] == "missing"  # any missing dominates
    assert rep["blocks"] is False and rep["alert_eligible"] is False
    assert "honesty_rule" in rep


def test_keeper_report_all_covered_is_clean(tmp_path):
    (tmp_path / "AAA.md").write_text("**CURRENT VERDICT (2026-06-18):** HOLD · conviction **high**\n", encoding="utf-8")
    rep = du.keeper_report([{"ticker": "AAA", "reasons": ["x"]}], dossier_dir=tmp_path, today="2026-06-18")
    assert rep["status"] == "covered"
    assert rep["to_draft"] == [] and rep["to_refresh"] == []
