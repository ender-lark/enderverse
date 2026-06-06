import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import broker_pdf_extractor as bpe
import build_positions_cache as bpc
import position_reconciliation as pr


TEXT = "\n".join([
    "Account: SKB Fidelity Taxable",
    "Statement Date 06/05/2026",
    "Symbol Description Quantity Last Price Market Value",
    "NVDA NVIDIA CORP 12 170.00 $2,040.00",
    "GOOGL ALPHABET INC CLASS A 4 180.00 $720.00",
    "Cash Core $100.00",
])

DESCRIPTION_FIRST_TEXT = "\n".join([
    "Account: Parents Schwab IRA",
    "Positions as of 06/05/2026",
    "Description Symbol Quantity Price Market Value",
    "NVIDIA CORP NVDA 12 170.00 $2,040.00",
    "ALPHABET INC CLASS A GOOGL 4 180.00 $720.00",
    "NVIDIA CORP 12 170.00 $2,040.00",
])

ROBINHOOD_TEXT = "\n".join([
    "Individual investing",
    "Name Symbol Shares Price Average cost Total return Equity",
    "NVIDIA NVDA 36 $212.49 $120.20 $3,322.55 $7,649.64",
    "Fundstrat Granny Shots US S?GRNJ 400 $32.04 $27.00 $2,015.50 $12,816.00",
    "GE Vernova GEV 2 $968.99 $854.76 $228.47 $1,937.99",
])

SCHWAB_TEXT = "\n".join([
    "Symbol / Name Ratings  Reinvest % of Holdings",
    "MSFT",
    "MICROSOFT CORP 2 $450.24 +5.45%",
    "(5.45%) $900.48 +$46.50",
    "SMHVANECK SEMICONDUCTOR ETF 140 $598.93 -0.15%",
    "(-0.15%) $83,850.20 -$126.00",
])

FIDELITY_SEPARATED_TEXT = "\n".join([
    "Positions",
    "Overview As of May-31-20262:47 p.m. ET",
    "Symbol Currentvalue",
    "Today'sgain/loss%",
    "Today'sgain/loss $",
    "Totalgain/loss%",
    "Totalgain/loss $ Quantity Lastprice",
    "Lastpricechange",
    "Cost basistotal",
    "Joint WROS - TODX84632063",
    "$62,225.64 -0.23% -$140.81 +6.06% +$3,557.37 880.012M $70.71 -$0.16 $58,668.27W",
    "$52,785.00 -1.46% -$777.50 +14.62% +$6,733.18 250M $211.14 -$3.11 $46,051.82",
    "$370.00 +5.71% +$20.00 -55.61% -$463.36 5 $0.74 +$0.04 $833.36",
    "MAGSLISTED FD TR ROU?",
    "NVDANVIDIA CORPORAT?",
    "BMNR 30 CallAug-21-2026",
    "5/31/26, 2:47 PM Portfolio Positions",
    "https://digital.fidelity.com/ftgw/digital/portfolio/positions 1/1",
])


def test_parse_position_lines_extracts_ticker_quantity_and_market_value():
    rows = bpe.parse_position_lines(TEXT, account_name="SKB Fidelity Taxable")

    assert [row["symbol"] for row in rows] == ["NVDA", "GOOGL"]
    assert rows[0]["description"] == "NVIDIA CORP"
    assert rows[0]["quantity"] == 12.0
    assert rows[0]["market_value"] == 2040.0
    assert rows[0]["account_name"] == "SKB Fidelity Taxable"


def test_parse_position_lines_handles_description_before_symbol():
    rows = bpe.parse_position_lines(DESCRIPTION_FIRST_TEXT, account_name="Parents Schwab IRA")

    assert [row["symbol"] for row in rows] == ["NVDA", "GOOGL"]
    assert rows[0]["description"] == "NVIDIA CORP"
    assert rows[1]["description"] == "ALPHABET INC CLASS A"
    assert rows[0]["quantity"] == 12.0
    assert rows[0]["market_value"] == 2040.0
    assert rows[0]["account_name"] == "Parents Schwab IRA"


def test_parse_position_lines_does_not_treat_company_name_as_symbol():
    rows = bpe.parse_position_lines(ROBINHOOD_TEXT, account_name="RH Individual", broker="Robinhood")

    assert [row["symbol"] for row in rows] == ["NVDA", "GRNJ", "GEV"]
    assert rows[0]["description"] == "NVIDIA"
    assert rows[0]["quantity"] == 36.0
    assert rows[0]["market_value"] == 7649.64


def test_parse_position_lines_handles_schwab_wrapped_and_compact_rows():
    rows = bpe.parse_position_lines(SCHWAB_TEXT, account_name="Schwab Brokerage", broker="Schwab")

    assert [row["symbol"] for row in rows] == ["MSFT", "SMH"]
    assert rows[0]["description"] == "MICROSOFT CORP"
    assert rows[0]["quantity"] == 2.0
    assert rows[0]["market_value"] == 900.48
    assert rows[1]["description"] == "VANECK SEMICONDUCTOR ETF"
    assert rows[1]["quantity"] == 140.0
    assert rows[1]["market_value"] == 83850.2


def test_fidelity_disclosure_prose_is_not_a_position():
    text = "\n".join([
        "https://digital.fidelity.com/ftgw/digital/portfolio/positions",
        "Symbol Currentvalue Quantity Lastprice",
        "Adjusted due to previous wash sale disallowed loss within the 61 day period.",
        "cost basis information related to newly-purchased shares when a wash sale occurs.",
        "The price from the prior market day resets before the market opens.",
        "Portfolio Positions Currentvalue",
    ])

    rows = bpe.parse_position_lines(text, account_name="Fidelity", broker="Fidelity")

    assert rows == []


def test_fidelity_separated_value_and_symbol_blocks_pair_by_page():
    rows = bpe.parse_position_lines(
        FIDELITY_SEPARATED_TEXT,
        account_name="Fidelity",
        broker="Fidelity",
    )

    assert [row["symbol"] for row in rows] == ["MAGS", "NVDA", "BMNR"]
    assert rows[0]["quantity"] == 880.012
    assert rows[0]["market_value"] == 62225.64
    assert rows[0]["account_name"] == "Joint WROS - TODX84632063"
    assert rows[2]["asset_type"] == "option"
    assert rows[2]["option"]["expiry"] == "2026-08-21"
    assert rows[2]["option"]["call_put"] == "call"


def test_fidelity_separated_blocks_fail_closed_on_count_mismatch():
    text = FIDELITY_SEPARATED_TEXT.replace("NVDANVIDIA CORPORAT?\n", "")

    rows = bpe.parse_position_lines(text, account_name="Fidelity", broker="Fidelity")

    assert rows == []


def test_build_combined_from_text_file_matches_downstream_contracts(tmp_path):
    source = tmp_path / "skb_fidelity.txt"
    source.write_text(TEXT, encoding="utf-8")
    combined = bpe.build_combined([source], as_of="2026-06-05",
                                  generated_at="2026-06-05T14:00:00Z")

    assert bpe.validate_combined(combined) == []
    assert combined["files"][0]["validation"]["passed"] is True
    assert combined["portfolio_summary"]["total_market_value"] == 2760.0
    assert combined["portfolio_summary"]["total_cash"] == 100.0

    positions = bpc.build_positions(combined, [{"ticker": "NVDA"}, {"ticker": "GOOGL"}])
    accounts = pr.build_account_positions(combined, [{"ticker": "NVDA"}])

    assert positions["sleeve_value"] == 2860
    assert {p["ticker"] for p in positions["positions"]} == {"NVDA", "GOOGL"}
    assert accounts["account_positions"][0]["owner"] == "SKB"
    assert accounts["tracked_combined_positions"][0]["ticker"] == "NVDA"


def test_build_combined_from_description_first_text_file(tmp_path):
    source = tmp_path / "parents_schwab.txt"
    source.write_text(DESCRIPTION_FIRST_TEXT, encoding="utf-8")
    combined = bpe.build_combined([source], as_of="2026-06-05",
                                  generated_at="2026-06-05T14:00:00Z")

    assert bpe.validate_combined(combined) == []
    assert combined["files"][0]["validation"]["passed"] is True
    assert [p["symbol"] for p in combined["files"][0]["positions"]] == ["NVDA", "GOOGL"]
    assert combined["portfolio_summary"]["total_market_value"] == 2760.0


def test_extract_file_reads_selectable_pdf_text_when_available(tmp_path):
    pytest.importorskip("pypdf")
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")

    pdf = tmp_path / "parents_schwab.pdf"
    canvas = canvas_mod.Canvas(str(pdf))
    y = 760
    for line in DESCRIPTION_FIRST_TEXT.splitlines():
        canvas.drawString(72, y, line)
        y -= 16
    canvas.save()

    extracted = bpe.extract_file(pdf, as_of="2026-06-05")

    assert extracted["extraction_method"] == "pypdf_text"
    assert extracted["validation"]["passed"] is True
    assert [p["symbol"] for p in extracted["positions"]] == ["NVDA", "GOOGL"]


def test_failed_text_extraction_is_marked_not_passed(tmp_path):
    source = tmp_path / "image_only.txt"
    source.write_text("Portfolio screenshot with no selectable table rows", encoding="utf-8")

    combined = bpe.build_combined([source], as_of="2026-06-05")

    validation = combined["files"][0]["validation"]
    assert validation["passed"] is False
    assert validation["positions_found"] == 0
    assert "no confident" in validation["error"]
    assert combined["warnings"]
    assert bpe.validate_combined(combined) == []


def test_cli_writes_and_validates_combined_json(tmp_path):
    source = tmp_path / "skb_fidelity.txt"
    out = tmp_path / "combined.json"
    source.write_text(TEXT, encoding="utf-8")

    rc = bpe.main([str(source), "--out", str(out), "--as-of", "2026-06-05"])
    assert rc == 0
    assert out.exists()

    info = json.loads(out.read_text(encoding="utf-8"))
    assert info["files"][0]["positions"][0]["symbol"] == "NVDA"
    assert bpe.main(["--validate", str(out)]) == 0


def test_cli_self_test_passes():
    proc = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "broker_pdf_extractor.py"), "--self-test"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "self-test: PASS" in proc.stdout
