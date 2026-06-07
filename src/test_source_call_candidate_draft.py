import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import source_call_candidate_draft as draft


def _feed():
    return {
        "feedback": {
            "source_calls": {
                "observations": [
                    {
                        "source": "Fundstrat Gmail full-body read",
                        "author": "Newton",
                        "ticker": "XOP",
                        "direction": "avoid",
                        "date": "2026-06-03",
                        "quote": "Bounce only; resistance near 175.72 should repel price toward 162.",
                    },
                    {
                        "author": "Newton",
                        "ticker": "TNX",
                        "date": "2026-06-03",
                        "quote": "Corrective bounce toward 4.55 should precede a turn lower.",
                    },
                ]
            }
        }
    }


def test_observations_from_feed_returns_classifiable_rows():
    rows = draft.observations_from_feed(_feed())

    assert rows == [
        {
            "source": "Newton",
            "ticker": "XOP",
            "text": "Bounce only; resistance near 175.72 should repel price toward 162.",
            "date": "2026-06-03",
        },
        {
            "source": "Newton",
            "ticker": "TNX",
            "text": "Corrective bounce toward 4.55 should precede a turn lower.",
            "date": "2026-06-03",
        },
    ]


def test_draft_candidates_from_feed_classifies_pending_rows():
    rows, summary = draft.draft_candidates_from_feed(_feed(), classified_at="2026-06-05")

    assert summary["observations"] == 2
    assert summary["drafted"] == 2
    assert summary["stored"] == 2
    assert summary["tickers"] == ["TNX", "XOP"]
    assert rows[0]["source"] == "newton"
    assert rows[0]["ticker"] == "XOP"
    assert rows[0]["outcome"] == "Pending"
    assert rows[0]["window_end"] >= "2026-06-03"


def test_observations_from_feed_falls_back_to_fundstrat_radar_rows():
    feed = {
        "feedback": {"source_calls": {"observations": []}},
        "radar": [
            {
                "author": "Newton",
                "ticker": "QQQ",
                "date": "2026-06-05",
                "direction": "support",
                "quote": "QQQ support must hold before leaning into growth.",
            },
            {
                "author": "Newton",
                "ticker": "QQQ",
                "date": "2026-06-05",
                "quote": "QQQ support must hold before leaning into growth.",
            },
            {
                "author": "Tom Lee",
                "ticker": "RSP",
                "date": "2026-06-05",
                "quote": "Broadening would support a constructive risk backdrop.",
            },
        ],
    }

    rows = draft.observations_from_feed(feed)

    assert rows == [
        {
            "source": "Newton",
            "ticker": "QQQ",
            "text": "QQQ support must hold before leaning into growth.",
            "date": "2026-06-05",
        },
        {
            "source": "Tom Lee",
            "ticker": "RSP",
            "text": "Broadening would support a constructive risk backdrop.",
            "date": "2026-06-05",
        },
    ]


def test_source_call_candidate_draft_cli_dry_run(tmp_path):
    feed = tmp_path / "feed.json"
    out = tmp_path / "source_call_candidates.json"
    feed.write_text(json.dumps(_feed()), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "source_call_candidate_draft.py"),
            "--feed",
            str(feed),
            "--out",
            str(out),
            "--classified-at",
            "2026-06-05",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["drafted"] == 2
    assert payload["written"] is False
    assert not out.exists()
