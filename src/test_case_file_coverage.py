import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import case_file_coverage as cfc


def _feed_with_action_ticker(ticker):
    return {
        "today_decide": {
            "cards": [
                {
                    "ticker": ticker,
                    "decision_card": {"move": {"direction": "ADD"}},
                    "card_id": f"{ticker}-ADD",
                }
            ]
        }
    }


def _write_md(directory, ticker, verdict_date):
    (directory / f"{ticker}.md").write_text(
        f"**CURRENT VERDICT ({verdict_date}):** HOLD the line · conviction **high**\n",
        encoding="utf-8",
    )


def test_missing_md_is_flagged_non_blocking(tmp_path):
    out = cfc.build_case_file_coverage(_feed_with_action_ticker("AAA"), dossier_dir=tmp_path, today="2026-06-18")
    assert out["missing_count"] == 1
    assert out["status"] == "missing"
    assert out["blocks"] is False and out["alert_eligible"] is False
    assert "honesty_rule" in out


def test_fresh_md_is_covered(tmp_path):
    _write_md(tmp_path, "AAA", "2026-06-18")
    out = cfc.build_case_file_coverage(_feed_with_action_ticker("AAA"), dossier_dir=tmp_path, today="2026-06-18")
    assert out["covered_count"] == 1
    assert out["status"] == "covered"


def test_stale_md_is_flagged_needs_review(tmp_path):
    _write_md(tmp_path, "AAA", "2026-01-01")
    out = cfc.build_case_file_coverage(_feed_with_action_ticker("AAA"), dossier_dir=tmp_path, today="2026-06-18")
    assert out["stale_count"] == 1
    assert out["status"] == "needs_review"


def test_unparsed_md_is_flagged(tmp_path):
    (tmp_path / "AAA.md").write_text("# AAA\nno verdict header here\n", encoding="utf-8")
    out = cfc.build_case_file_coverage(_feed_with_action_ticker("AAA"), dossier_dir=tmp_path, today="2026-06-18")
    assert out["unparsed_count"] == 1
    assert out["status"] == "needs_review"


def test_no_targets_is_clean(tmp_path):
    out = cfc.build_case_file_coverage({"today_decide": {"cards": []}}, dossier_dir=tmp_path, today="2026-06-18")
    assert out["total_count"] == 0
    assert out["status"] == "covered"
