import json
import subprocess
import sys
from pathlib import Path

import federal_funding_intake as intake


def _sample_payload():
    return {
        "as_of": "2026-06-18",
        "rows": [
            {
                "date": "2026-06-18",
                "agency": "Department of War Office of Strategic Capital",
                "program": "critical minerals",
                "recipient": "Energy Fuels",
                "award_details": "$725M conditional loan commitment for rare-earth separation and metallization",
                "public_tickers": "UUUU, TSX: EFR",
                "priority": "High",
                "directness": "direct_public",
                "actionability": "review_now",
                "investing_angle": "Direct policy-backed public-company catalyst; confirm pullback/risk before acting.",
                "risks": ["conditional close", "capex execution", "possible dilution"],
                "next_trigger": "loan close terms, capex budget, offtake/customer evidence",
                "source_urls": ["https://www.war.gov/News/Releases/Release/Article/4520819/the-department-of-wars-office-of-strategic-capital-signs-725-million-conditiona/"],
            },
            {
                "date": "2026-06-17",
                "agency": "Commerce CHIPS R&D",
                "recipient": "SandboxAQ",
                "award_details": "$500M CHIPS R&D award for AI-driven semiconductor materials",
                "public_tickers": "NVDA, AMAT, LRCX, INTC, TSM",
                "priority": "Medium",
                "directness": "private_read_through",
                "actionability": "watch",
                "source_urls": ["https://www.nist.gov/news-events/news/2026/06/department-commerce-announces-definitive-agreement-sandboxaq-500-million"],
            },
        ],
    }


def test_normalize_federal_funding_payload_and_parse_money():
    cache = intake.normalize_funding_payload([_sample_payload()], generated_at="2026-06-18T16:15:00Z")

    assert cache["schema_version"] == 1
    assert cache["scan_status"] == "has_data"
    assert cache["summary"]["stored"] == 2
    assert cache["summary"]["direct_public"] == 1
    assert cache["rows"][0]["recipient"] == "Energy Fuels"
    assert cache["rows"][0]["award_value_usd"] == 725_000_000
    assert cache["rows"][0]["tickers"][0] == "UUUU"
    assert intake.validate_funding_cache(cache) == []


def test_direct_public_row_requires_ticker():
    cache = intake.normalize_funding_payload([
        {
            "rows": [
                {
                    "date": "2026-06-18",
                    "agency": "DOE",
                    "recipient": "Public Co",
                    "award_details": "$10M grant",
                    "directness": "direct_public",
                    "priority": "high",
                }
            ]
        }
    ])

    problems = intake.validate_funding_cache(cache)

    assert any("tickers" in problem for problem in problems)


def test_derives_signal_rows_and_monitor_research_without_urgency(tmp_path):
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps([
        {"ticker": "UUUU", "stance": "MONITOR"},
        {"ticker": "LDOS", "stance": "ACTIVE"},
    ]), encoding="utf-8")
    cache = intake.normalize_funding_payload([
        {
            "as_of": "2026-06-18",
            "rows": [
                _sample_payload()["rows"][0],
                {
                    "date": "2026-06-18",
                    "agency": "DHS Customs and Border Protection",
                    "recipient": "Leidos",
                    "award_details": "Potential $270M IDIQ for mobile screening systems",
                    "ticker": "LDOS",
                    "priority": "high",
                    "directness": "direct_public",
                    "actionability": "review_now",
                    "source_url": "https://www.govconwire.com/articles/leidos-cbp-medium-energy-mobile-systems",
                },
                {
                    "date": "2026-06-18",
                    "agency": "Defense Health Agency",
                    "recipient": "OptumHealth Care Solutions",
                    "award_details": "$25.3M bridge modification",
                    "ticker": "UNH",
                    "priority": "low",
                    "directness": "contract_backlog",
                    "actionability": "ignore",
                },
            ],
        }
    ])

    signals = intake.build_signal_rows(cache)
    research = intake.build_research_rows(cache, theses_path=theses)

    assert len(signals) == 2
    assert signals[0]["ticker"] == "UUUU"
    uuuu = next(row for row in research if row["ticker"] == "UUUU")
    ldos = next(row for row in research if row["ticker"] == "LDOS")
    assert "urgency" not in uuuu
    assert "MONITOR sleeve guardrail" in uuuu["notes"]
    assert ldos["urgency"] == "today"


def test_cli_writes_cache_signal_log_and_research_queue(tmp_path):
    payload = tmp_path / "funding.json"
    out = tmp_path / "federal_funding_moves.json"
    summary = tmp_path / "summary.json"
    signal = tmp_path / "signal_log.json"
    research = tmp_path / "research_queue.json"
    theses = tmp_path / "theses.json"
    payload.write_text(json.dumps(_sample_payload()), encoding="utf-8")
    theses.write_text(json.dumps([{"ticker": "UUUU", "stance": "MONITOR"}]), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "federal_funding_intake.py"),
            str(payload),
            "--out",
            str(out),
            "--summary",
            str(summary),
            "--signal-log-out",
            str(signal),
            "--research-out",
            str(research),
            "--theses",
            str(theses),
            "--merge-existing",
            "--generated-at",
            "2026-06-18T16:15:00Z",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["valid"] is True
    assert report["written"] is True
    assert report["signal_log"]["written"] is True
    assert report["research_queue"]["written"] is True
    cache = json.loads(out.read_text(encoding="utf-8"))
    signal_rows = json.loads(signal.read_text(encoding="utf-8"))
    research_rows = json.loads(research.read_text(encoding="utf-8"))
    assert cache["summary"]["top_signal"].startswith("Energy Fuels")
    assert signal_rows[0]["ticker"] == "UUUU"
    assert research_rows["pending"][0]["ticker"] == "UUUU"
    assert "urgency" not in research_rows["pending"][0]


def test_validate_cli_accepts_empty_checked_scan(tmp_path):
    out = tmp_path / "federal_funding_moves.json"
    out.write_text(json.dumps({
        "schema_version": 1,
        "source": "federal_funding_intake",
        "generated_at": "2026-06-18T21:30:00Z",
        "as_of": "2026-06-18",
        "scan_status": "checked_clear",
        "rows": [],
        "summary": {"stored": 0},
    }), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "federal_funding_intake.py"),
            "--validate",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["valid"] is True
