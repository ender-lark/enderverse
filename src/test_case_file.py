import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import case_file as cf


def _write_md(directory, ticker, verdict_date, body="HOLD the line · conviction **high**"):
    path = directory / f"{ticker}.md"
    path.write_text(
        f"# {ticker} - Thesis of Record\n\n"
        f"**CURRENT VERDICT ({verdict_date}):** {body}\n\n## Why\n...\n",
        encoding="utf-8",
    )
    return path


def test_fresh_verdict_is_parsed_and_authoritative(tmp_path):
    _write_md(tmp_path, "AAA", "2026-06-18", body="**SIZE UP** now from the stub · conviction **medium-high**")
    out = cf.build_case_file(
        "AAA", "2026-06-18", dossier_dir=tmp_path, source_calls=[], signal_log=[], top_prospects={}
    )
    v = out["verdict"]
    assert v["status"] == "fresh"
    assert v["verdict_date"] == "2026-06-18"
    assert "SIZE UP" in v["verdict_line"]
    assert v["conviction"] == "medium-high"
    assert v["blocks"] is False and v["alert_eligible"] is False


def test_stale_verdict_self_degrades_to_unknown(tmp_path):
    _write_md(tmp_path, "AAA", "2026-01-01")
    v = cf.build_case_file(
        "AAA", "2026-06-18", dossier_dir=tmp_path, source_calls=[], signal_log=[], top_prospects={}
    )["verdict"]
    assert v["status"] == "stale"
    assert v["line"].startswith("UNKNOWN")
    assert "STALE" in v["line"]
    assert v["blocks"] is False  # a stale verdict cannot drive a decision


def test_missing_verdict_is_loud_not_quiet(tmp_path):
    v = cf.build_case_file(
        "ZZZ", "2026-06-18", dossier_dir=tmp_path, source_calls=[], signal_log=[], top_prospects={}
    )["verdict"]
    assert v["status"] == "missing"
    assert "NO THESIS-OF-RECORD" in v["line"]
    assert "do not size" in v["line"].lower()


def test_unparsed_verdict_file_is_flagged(tmp_path):
    (tmp_path / "AAA.md").write_text("# AAA\nNo verdict header here at all.\n", encoding="utf-8")
    v = cf.build_case_file(
        "AAA", "2026-06-18", dossier_dir=tmp_path, source_calls=[], signal_log=[], top_prospects={}
    )["verdict"]
    assert v["status"] == "unparsed"


def test_news_basket_is_separated_and_demoted(tmp_path):
    signal = [
        {"date": "2026-06-10", "ticker": "LEU", "signal": "LEU-specific note", "note": "x", "source": "u", "priority": "high"},
        {"date": "2026-06-12", "ticker": "ITA, BWXT, LEU, UUUU, GLD", "signal": "Iran macro", "note": "y", "source": "u2", "priority": "high"},
    ]
    news = cf.build_case_file(
        "LEU", "2026-06-18", dossier_dir=tmp_path, source_calls=[], signal_log=signal, top_prospects={}
    )["news"]
    events = news["events"]
    assert events[0]["name_specific"] is True
    assert events[0]["signal"] == "LEU-specific note"
    basket = [e for e in events if not e["name_specific"]][0]
    assert "basket" in basket["scope"]
    assert basket["ticker_count"] == 5
    assert news["name_specific_count"] == 1 and news["basket_count"] == 1


def test_macro_ticker_short_circuits_equity_path(tmp_path):
    out = cf.build_case_file(
        "SPX", "2026-06-18", dossier_dir=tmp_path, source_calls=[], signal_log=[], top_prospects={}
    )
    assert out["identity"]["kind"] == "macro"
    assert out["is_equity"] is False
    assert out["verdict"]["status"] == "skipped"
    assert out["earliest_record"]["status"] == "skipped"


def test_empty_decisions_lane_when_no_log(tmp_path):
    out = cf.build_case_file(
        "AAA",
        "2026-06-18",
        dossier_dir=tmp_path,
        source_calls=[],
        signal_log=[],
        top_prospects={},
        dispositions_path=tmp_path / "dispositions.jsonl",  # absent
        open_opportunities={"history": []},
    )
    dec = out["decisions"]
    assert dec["status"] == "empty"
    assert "C6" in dec["line"] or "no decision log yet" in dec["line"].lower()


def test_decisions_lane_reads_dispositions(tmp_path):
    dp = tmp_path / "dispositions.jsonl"
    import disposition_log as dl

    dl.append_disposition("2026-06-10", "AAA-ADD-2026-06-10", "AAA", "ACT", path=dp)
    dec = cf.build_case_file(
        "AAA",
        "2026-06-18",
        dossier_dir=tmp_path,
        source_calls=[],
        signal_log=[],
        top_prospects={},
        dispositions_path=dp,
        open_opportunities={"history": []},
    )["decisions"]
    assert dec["status"] == "ok"
    assert dec["events"][0]["verb"] == "ACT"


def test_earliest_record_is_honest_without_top_prospects(tmp_path):
    source_calls = [
        {"ticker": "LEU", "date": "2026-06-05", "verbatim_quote": "q", "source": "newton"},
        {"ticker": "LEU", "date": "2026-06-10", "verbatim_quote": "q2", "source": "lee"},
        {"ticker": "XOP", "date": "2026-06-03", "verbatim_quote": "q3", "source": "newton"},
    ]
    er = cf.build_case_file(
        "LEU", "2026-06-18", dossier_dir=tmp_path, source_calls=source_calls, signal_log=[], top_prospects={}
    )["earliest_record"]
    assert er["records"][0]["source"] == "fundstrat_call_cache"
    assert er["records"][0]["date"] == "2026-06-05"
    assert er["cache_floor"] == "2026-06-03"
    assert "cache begins" in er["line"].lower()
    assert "added on" not in er["line"].lower()  # never a bare synthesized first-seen


def test_earliest_record_surfaces_top_prospects_add_date(tmp_path):
    top_prospects = {"AAA": {"add_date": "2026-05-28", "add_price": 100.0}}
    source_calls = [{"ticker": "AAA", "date": "2026-06-05", "verbatim_quote": "q", "source": "x"}]
    er = cf.build_case_file(
        "AAA", "2026-06-18", dossier_dir=tmp_path, source_calls=source_calls, signal_log=[], top_prospects=top_prospects
    )["earliest_record"]
    sources = {r["source"] for r in er["records"]}
    assert "top_prospects" in sources
    assert er["records"][0]["date"] == "2026-05-28"  # earliest wins


def test_fundstrat_calls_lane_filters_and_sorts(tmp_path):
    source_calls = [
        {"ticker": "AAA", "date": "2026-06-05", "verbatim_quote": "older", "source": "x", "tier": "B", "outcome": "Pending"},
        {"ticker": "AAA", "date": "2026-06-12", "verbatim_quote": "newer", "source": "y", "tier": "A", "outcome": "Pending"},
        {"ticker": "BBB", "date": "2026-06-12", "verbatim_quote": "other", "source": "z"},
    ]
    fs = cf.build_case_file(
        "AAA", "2026-06-18", dossier_dir=tmp_path, source_calls=source_calls, signal_log=[], top_prospects={}
    )["fundstrat_calls"]
    assert fs["count"] == 2
    assert fs["events"][0]["date"] == "2026-06-12"  # newest first
    assert fs["events"][0]["text"] == "newer"


def test_cli_emits_valid_json_with_all_lanes(capsys):
    rc = cf.main(["LEU", "--today", "2026-06-18", "--format", "json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    for lane in ("identity", "verdict", "earliest_record", "fundstrat_calls", "news", "decisions"):
        assert lane in out
