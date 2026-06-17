import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_dossier_refresh as refresh
import decision_dossiers as dd
from tunables import load_conviction_weights


def _series(start, n=70, step=1):
    return [start + i * step for i in range(n)]


def _read(label, text, as_of=None, max_age_days=1):
    return {
        "label": label,
        "text": text,
        "as_of": as_of,
        "max_age_days": max_age_days,
        "source": "test",
    }


def _row(ticker, *, status="fresh"):
    return {
        "ticker": ticker,
        "status": status,
        "one_liner": f"{ticker} dossier.",
        "notion_url": None,
        "last_reviewed": "2026-06-16",
        "next_review_due": "2026-06-30",
        "synced_at": "2026-06-16",
        "reads": {
            "edge": _read("Edge/moat", "Durable edge.", "2026-06-16", 90),
            "price": _read("Good buy price?", "UNKNOWN - price not checked.", None, 1),
            "timing": _read("Good timing?", "UNKNOWN - timing not checked.", None, 1),
            "avoid": _read("What-not / avoid", "Durable avoid.", "2026-06-16", 90),
        },
    }


def _payload():
    return {
        "generated_at": "2026-06-16",
        "source": {"runtime_source": "repo mirror"},
        "dossiers": {
            "SMH": _row("SMH"),
            "AVGO": _row("AVGO"),
        },
    }


def test_refresh_updates_only_ticker_matched_price_and_timing_reads():
    payload, summary = refresh.refresh_payload(
        _payload(),
        uw_price_cache={
            "SMH": _series(100, step=2),
            "SPY": [100 for _ in range(70)],
        },
        opportunity_cache={
            "as_of": "2026-06-16",
            "signals": [
                {
                    "ticker": "SMH",
                    "signal_type": "sweep",
                    "direction": "bullish",
                    "strength": "strong",
                    "evidence": "ask-side call sweeps",
                    "detail": {"premium": 1_000_000},
                }
            ],
        },
        feed={
            "holdings": [
                {
                    "cat": "AI / Semiconductors",
                    "rot": {"w": "LEADING"},
                    "pos": [{"t": "SMH", "cd": "up"}],
                }
            ]
        },
        today="2026-06-16",
        as_of="2026-06-16",
        weights=load_conviction_weights(),
    )

    assert dd.validate_payload(payload) == []
    assert summary["updated_dossiers"] == 1
    rows = {row["ticker"]: row for row in summary["rows"]}
    assert rows["SMH"]["updated_reads"] == ["price", "timing"]
    assert rows["AVGO"]["updated_reads"] == []
    assert rows["AVGO"]["price_evidence"] is False
    assert rows["AVGO"]["timing_evidence"] is False

    smh = payload["dossiers"]["SMH"]
    assert smh["reads"]["price"]["as_of"] == "2026-06-16"
    assert smh["reads"]["price"]["source"] == "decision_dossier_refresh:uw_price_rotation"
    assert "not a valuation clearance" in smh["reads"]["price"]["text"]
    assert smh["reads"]["timing"]["as_of"] == "2026-06-16"
    assert smh["reads"]["timing"]["source"] == "decision_dossier_refresh:battery_evidence"
    assert "ticker-matched UW opportunity evidence" in smh["reads"]["timing"]["text"]

    avgo = payload["dossiers"]["AVGO"]
    assert avgo["reads"]["price"]["as_of"] is None
    assert avgo["reads"]["price"]["text"].startswith("UNKNOWN")
    assert avgo["reads"]["timing"]["as_of"] is None
    assert avgo["reads"]["timing"]["text"].startswith("UNKNOWN")


def test_refresh_does_not_turn_absent_opportunity_row_into_checked_no_signal():
    payload, summary = refresh.refresh_payload(
        {"generated_at": "2026-06-16", "dossiers": {"AVGO": _row("AVGO")}},
        uw_price_cache={"SMH": _series(100, step=2), "SPY": [100 for _ in range(70)]},
        opportunity_cache={
            "as_of": "2026-06-16",
            "signals": [
                {
                    "ticker": "SMH",
                    "signal_type": "sweep",
                    "direction": "bullish",
                    "strength": "strong",
                    "evidence": "other ticker",
                }
            ],
        },
        today="2026-06-16",
        as_of="2026-06-16",
        weights=load_conviction_weights(),
    )

    row = summary["rows"][0]
    assert row["ticker"] == "AVGO"
    assert row["updated_reads"] == []
    assert row["timing_evidence"] is False
    assert "source" not in payload
    assert payload["dossiers"]["AVGO"]["reads"]["timing"]["as_of"] is None
    assert payload["dossiers"]["AVGO"]["reads"]["timing"]["text"].startswith("UNKNOWN")


def test_old_dynamic_refresh_stays_stale_under_card_dossier_guard():
    payload, summary = refresh.refresh_payload(
        {"generated_at": "2026-06-16", "dossiers": {"SMH": _row("SMH")}},
        uw_price_cache={
            "SMH": _series(100, step=2),
            "SPY": [100 for _ in range(70)],
        },
        opportunity_cache={
            "as_of": "2026-06-12",
            "signals": [
                {
                    "ticker": "SMH",
                    "signal_type": "sweep",
                    "direction": "bullish",
                    "strength": "strong",
                    "evidence": "ask-side call sweeps",
                }
            ],
        },
        today="2026-06-16",
        as_of="2026-06-12",
        weights=load_conviction_weights(),
    )

    assert summary["updated_dossiers"] == 1
    assert payload["dossiers"]["SMH"]["status"] == "stale"
    card = dd.card_dossier("SMH", dossiers=payload["dossiers"], today="2026-06-16")
    assert card["status"] == "stale"
    assert card["reads"]["price"]["freshness"]["status"] == "stale"
    assert card["reads"]["price"]["text"].startswith("UNKNOWN")
    assert card["reads"]["timing"]["freshness"]["status"] == "stale"
    assert card["reads"]["timing"]["text"].startswith("UNKNOWN")


def test_pending_sync_rows_are_not_refreshed():
    payload = {
        "generated_at": "2026-06-16",
        "dossiers": {"SMH": _row("SMH", status="pending_sync")},
    }

    out, summary = refresh.refresh_payload(
        payload,
        uw_price_cache={"SMH": _series(100, step=2), "SPY": [100 for _ in range(70)]},
        opportunity_cache={"as_of": "2026-06-16", "signals": []},
        today="2026-06-16",
        as_of="2026-06-16",
        weights=load_conviction_weights(),
    )

    assert summary["rows"] == [{"ticker": "SMH", "updated_reads": [], "skipped": "pending_sync"}]
    assert out["dossiers"]["SMH"]["reads"]["price"]["text"].startswith("UNKNOWN")


def test_cli_dry_run_does_not_write(tmp_path):
    dossier_path = tmp_path / "decision_dossiers.json"
    dossier_path.write_text(json.dumps(_payload()), encoding="utf-8")
    price_path = tmp_path / "uw_closes.json"
    price_path.write_text(json.dumps({"SMH": _series(100, step=2), "SPY": [100 for _ in range(70)]}), encoding="utf-8")
    opp_path = tmp_path / "uw_opportunity_signals.json"
    opp_path.write_text(json.dumps({"as_of": "2026-06-16", "signals": []}), encoding="utf-8")
    before = dossier_path.read_text(encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "decision_dossier_refresh.py"),
            "--in",
            str(dossier_path),
            "--out",
            str(dossier_path),
            "--uw-prices",
            str(price_path),
            "--uw-opportunity",
            str(opp_path),
            "--today",
            "2026-06-16",
            "--as-of",
            "2026-06-16",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["written"] is False
    assert dossier_path.read_text(encoding="utf-8") == before
