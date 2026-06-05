import json
import subprocess
import sys
from pathlib import Path

from analyst_judgment import actions_read
from event_risk import (
    event_risk_actions_read,
    normalize_event_risks,
    validate_event_risks,
)
from validators import validate_cockpit_feed


THESES = [
    {"ticker": "NVDA", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
]


def test_normalize_event_risks_accepts_supplied_aliases_and_sorts_by_severity():
    rows = normalize_event_risks(
        {
            "events": [
                {
                    "headline": "Oil shock risk from Middle East escalation",
                    "priority": "HIGH",
                    "asset_classes": "oil; energy; semis",
                    "symbols": "XLE, NVDA",
                    "source": "Manual scan",
                    "watch_for": "Brent gap higher",
                },
                {"event": "Low urgency logistics note", "severity": "low", "source": "Manual scan"},
            ]
        },
        default_date="2026-06-05",
    )

    assert [row["severity"] for row in rows] == ["high", "low"]
    assert rows[0]["title"] == "Oil shock risk from Middle East escalation"
    assert rows[0]["date"] == "2026-06-05"
    assert rows[0]["channels"] == ["oil", "energy", "semis"]
    assert rows[0]["tickers"] == ["XLE", "NVDA"]
    assert validate_event_risks(rows) == []


def test_high_event_risk_promotes_review_action_not_trade_order():
    event_rows = normalize_event_risks([
        {
            "title": "Iran conflict drives oil-volatility shock",
            "severity": "critical",
            "channels": ["oil", "rates", "vol"],
            "source": "Daily event scan",
            "summary": "Crude spike can change exposure and new-buy timing.",
        }
    ])

    promoted = event_risk_actions_read(event_rows)
    actions = actions_read([], [], THESES, event_risk_actions=promoted)["actions"]

    assert actions[0]["kind"] == "event_risk"
    assert actions[0]["action_state"] == "ACT_NOW"
    assert actions[0]["capital_effect"] == "review"
    assert actions[0]["ticker"] is None
    assert actions[0]["gate"] is None
    assert "hedges" in actions[0]["your_move"]
    assert validate_cockpit_feed({
        "generated_at": "2026-06-05T14:00:00+00:00",
        "staleness": {},
        "lane_status": {"rows": [], "counts": {}, "has_dark_lanes": False, "has_stale_or_failed": False},
        "hero": {},
        "actions": actions,
        "fresh_signals": [],
        "holdings": [],
        "rotation": [],
        "macro": {},
        "event_risk": event_rows,
    }) == []


def test_medium_event_risk_stays_context_only():
    rows = normalize_event_risks([
        {"title": "Weekly policy watch", "severity": "medium", "source": "Daily event scan"}
    ])

    assert event_risk_actions_read(rows) == []


def test_event_risk_intake_writes_normalized_cache_and_summary(tmp_path):
    src = tmp_path / "event_scan.json"
    out = tmp_path / "event_risks.json"
    summary = tmp_path / "summary.json"
    src.write_text(json.dumps({
        "risks": [
            {"headline": "Oil shock risk", "priority": "high", "source": "Manual scan"}
        ]
    }), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "event_risk_intake.py"),
            str(src),
            "--out",
            str(out),
            "--summary",
            str(summary),
            "--date",
            "2026-06-05",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    status = json.loads(summary.read_text(encoding="utf-8"))
    assert payload[0]["title"] == "Oil shock risk"
    assert payload[0]["date"] == "2026-06-05"
    assert status["written"] is True
    assert status["promoted"] == 1
