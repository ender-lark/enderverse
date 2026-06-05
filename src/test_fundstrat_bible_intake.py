import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_bible_intake import (
    build_deck_from_paths,
    merge_decks,
    parse_bible_text,
    update_top_prospects_from_bible,
    validate_bible_deck,
    write_outputs,
)


TEXT = "\n".join([
    "Fundstrat Monthly Strategy 2026-06",
    "Macro Stance: Risk-on, buy dips into mid-year.",
    "What to Own: Technology, Industrials, Financials",
    "Core List: ANET - AI networking; VRT",
    "Top 5: NVDA - secular AI leader; GOOGL; GS",
    "Bottom 5: XYZ; ABC - funding source",
])


def test_parse_bible_text_keeps_only_useful_sections():
    deck = parse_bible_text(TEXT, source_file="monthly.txt")

    assert deck["deck_date"] == "2026-06"
    assert deck["macro_stance"] == "Risk-on, buy dips into mid-year."
    assert deck["what_to_own"] == ["Technology", "Industrials", "Financials"]
    assert "core_list" not in deck
    assert "consider" not in deck
    assert deck["top5"] == [{"ticker": "NVDA", "note": "secular AI leader"}, "GOOGL", "GS"]
    assert deck["bottom5"] == ["XYZ", {"ticker": "ABC", "note": "funding source"}]
    assert "Fundstrat Monthly Strategy" not in json.dumps(deck)
    assert validate_bible_deck(deck) == []


def test_chart_like_notes_are_not_stored():
    deck = parse_bible_text("\n".join([
        "Fundstrat Monthly 2026-06",
        "Top 5: NVDA - chart source: Fundstrat 1 2 3 4 5; GOOGL - AI search",
    ]))

    assert deck["top5"] == ["NVDA", {"ticker": "GOOGL", "note": "AI search"}]


def test_build_deck_from_text_file_and_write_outputs(tmp_path):
    src = tmp_path / "monthly.txt"
    out = tmp_path / "fundstrat_bible.json"
    summary_path = tmp_path / "fundstrat_bible_intake_summary.json"
    src.write_text(TEXT, encoding="utf-8")

    deck, summary = build_deck_from_paths([src], as_of="2026-06")
    written = write_outputs(deck, summary, out=out, summary_path=summary_path)
    saved = json.loads(out.read_text(encoding="utf-8"))
    saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert written["fundstrat_bible"] == str(out)
    assert saved["top5"][0]["ticker"] == "NVDA"
    assert saved_summary["valid"] is True
    assert saved_summary["top5"] == 3
    assert saved_summary["consider"] == 0


def test_core_list_summary_statistics_is_ignored_for_now():
    deck = parse_bible_text("\n".join([
        "Fundstrat Monthly 2026-05-28",
        "Core List: Summary Statistics",
        "● 1 AMD Advanced Micro Devices Inc Information Technology Semiconductors & Semiconductors $808,028 43.3% 121.5% 38.4x 17 1 120% 178% Y",
        "2 CAT Caterpillar Inc Industrials Machinery $419,106 5.0% 49.0% 30.3x 16 5 103% 141% Y",
        "Top 5: AMD; GOOGL",
    ]))

    assert "core_list" not in deck
    assert deck["top5"] == ["AMD", "GOOGL"]


def test_large_cap_top_bottom_idea_page_handles_pdf_text_order():
    deck = parse_bible_text("\n".join([
        "Macro Research",
        "5/28/2026 For Exclusive Use of Fundstrat Direct Members Only",
        "May 2026: Top 5 and Bottom 5 Large-cap Core Ideas",
        "Deere & Co. ($DE)",
        "Texas Pacific Land Corp. ($TPL)",
        "Robinhood Markets Inc. ($HOOD)",
        "Packaging Corp. of America ($PKG)",
        "Echostar Corp. ($SATS)",
        "Bottom 5 Large-cap ideas",
        "Advanced Micro Devices ($AMD)",
        "Arista Networks ($ANET)",
        "Alphabet Inc. ($GOOGL)",
        "Quanta Services Inc. ($PWR)",
        "Goldman Sachs Group Inc. ($GS)",
        "Top 5 Large-cap ideas",
    ]))

    assert deck["bottom5"] == ["DE", "TPL", "HOOD", "PKG", "SATS"]
    assert deck["top5"] == ["AMD", "ANET", "GOOGL", "PWR", "GS"]


def test_json_deck_passthrough_and_merge_existing(tmp_path):
    json_path = tmp_path / "deck.json"
    json_path.write_text(json.dumps({
        "deck_date": "2026-06",
        "what_to_own": ["Technology"],
        "top5": ["NVDA"],
    }), encoding="utf-8")
    existing = {"deck_date": "2026-05", "top5": ["GOOGL"], "bottom5": ["XYZ"]}

    deck, summary = build_deck_from_paths([json_path], merge_existing=existing)

    assert deck["deck_date"] == "2026-06"
    assert deck["top5"] == ["GOOGL", "NVDA"]
    assert deck["bottom5"] == ["XYZ"]
    assert summary["valid"] is True


def test_update_top_prospects_from_monthly_bible(tmp_path):
    cache_path = tmp_path / "top_prospects.json"
    deck = {
        "deck_date": "2026-06",
        "top5": [{"ticker": "NVDA", "note": "secular AI leader"}],
        "consider": ["ANET"],
        "bottom5": ["XYZ"],
    }

    summary = update_top_prospects_from_bible(
        deck,
        cache_path,
        generated_at="2026-06-05T14:00:00Z",
    )
    cache = json.loads(cache_path.read_text(encoding="utf-8"))

    assert summary["updated"] is True
    assert summary["picks"] == 3
    assert cache["NVDA"]["events"][0]["source"] == "FS-Monthly"
    assert cache["NVDA"]["events"][0]["direction"] == "long"
    assert cache["ANET"]["events"][0]["category"] == "consider_list"
    assert cache["ANET"]["events"][0]["direction"] == "long"
    assert cache["ANET"]["conviction_score"] == 4
    assert cache["ANET"]["urgency_score"] == 0
    assert cache["XYZ"]["events"][0]["direction"] == "avoid"
    assert "Fundstrat Monthly Strategy" not in json.dumps(cache)


def test_invalid_empty_upload_fails_validation():
    deck = parse_bible_text("Fundstrat monthly charts only, no useful section headings.")
    assert "no stance" in validate_bible_deck(deck)[0]


def test_merge_decks_dedupes_lists():
    merged = merge_decks(
        {"deck_date": "2026-05", "top5": ["NVDA"], "consider": ["ANET"], "what_to_own": ["Technology"]},
        {"deck_date": "2026-06", "top5": ["NVDA", "GOOGL"], "consider": ["ANET", "VRT"], "what_to_own": ["Technology", "Financials"]},
    )

    assert merged["deck_date"] == "2026-06"
    assert merged["top5"] == ["NVDA", "GOOGL"]
    assert merged["consider"] == ["ANET", "VRT"]
    assert merged["what_to_own"] == ["Technology", "Financials"]


def test_cli_self_test_passes():
    proc = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "fundstrat_bible_intake.py"), "--self-test"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "self-test: PASS" in proc.stdout
