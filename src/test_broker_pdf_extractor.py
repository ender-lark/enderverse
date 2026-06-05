import json
import os
import subprocess
import sys

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


def test_parse_position_lines_extracts_ticker_quantity_and_market_value():
    rows = bpe.parse_position_lines(TEXT, account_name="SKB Fidelity Taxable")

    assert [row["symbol"] for row in rows] == ["NVDA", "GOOGL"]
    assert rows[0]["description"] == "NVIDIA CORP"
    assert rows[0]["quantity"] == 12.0
    assert rows[0]["market_value"] == 2040.0
    assert rows[0]["account_name"] == "SKB Fidelity Taxable"


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
