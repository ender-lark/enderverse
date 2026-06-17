from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import loose_thread_sweep as lts


def test_cutoff_uses_latest_matching_receipt(tmp_path):
    receipts = tmp_path / "receipts.json"
    receipts.write_text(
        json.dumps({
            "schema_version": 1,
            "receipts": [
                {
                    "routine_id": "other",
                    "status": "success",
                    "run_source": "scheduled",
                    "recorded_at": "2026-06-17T01:00:00Z",
                },
                {
                    "routine_id": lts.ROUTINE_ID,
                    "status": "started",
                    "run_source": "scheduled",
                    "recorded_at": "2026-06-17T02:00:00Z",
                },
                {
                    "routine_id": lts.ROUTINE_ID,
                    "status": "success",
                    "run_source": "scheduled",
                    "recorded_at": "2026-06-17T02:05:00Z",
                },
            ],
        }),
        encoding="utf-8",
    )

    assert lts.cutoff_from_receipts(receipts) == datetime(2026, 6, 17, 2, 5, tzinfo=timezone.utc)


def test_cutoff_falls_back_to_bounded_lookback_for_first_run(tmp_path):
    receipts = tmp_path / "missing.json"
    now = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)

    assert lts.cutoff_from_receipts(receipts, now=now, default_lookback_hours=6) == now - timedelta(hours=6)


def test_route_heuristics_keep_capture_targets_separate():
    assert lts._route_for_text("fix automation prompt audit TODO") == lts.ROUTE_SYSTEM
    assert lts._route_for_text("Fundstrat analyst call follow-up") == lts.ROUTE_SOURCE_CALL
    assert lts._route_for_text("firm decision to keep ANET open") == lts.ROUTE_DECISION
    assert lts._route_for_text("research whether INTC catalyst is stale") == lts.ROUTE_RESEARCH


def test_collect_workboard_candidates_filters_to_recent_codex_rows(tmp_path):
    board = tmp_path / "WORKBOARD.md"
    board.write_text(
        "\n".join([
            "| id | agent | scope | files-or-state-owned | status | stamp |",
            "| --- | --- | --- | --- | --- | --- |",
            "| OLD | Codex | TODO old system task | `src/a.py` | CLAIMED | 2026-06-16 10:00 ET |",
            "| OTHER | Claude | TODO other agent item | `src/b.py` | CLAIMED | 2026-06-17 10:00 ET |",
            "| NEW | Codex | Follow-up: automate queue capture | `src/c.py` | CLAIMED | 2026-06-17 10:00 ET |",
        ]),
        encoding="utf-8",
    )

    candidates = lts.collect_workboard_candidates(board, datetime(2026, 6, 17, 0, 0, tzinfo=timezone.utc))

    assert len(candidates) == 1
    assert candidates[0].source_ref.endswith("WORKBOARD.md:5")
    assert candidates[0].route == lts.ROUTE_SYSTEM
    assert "NEW" in candidates[0].title


def test_collect_marker_candidates_routes_recent_task_notes(tmp_path):
    tasks = tmp_path / "docs" / "codex_tasks"
    tasks.mkdir(parents=True)
    note = tasks / "note.md"
    note.write_text("- TODO: Research whether MU trigger needs rewire\n", encoding="utf-8")

    candidates = lts.collect_marker_candidates([tasks], datetime(2020, 1, 1, tzinfo=timezone.utc))

    assert len(candidates) == 1
    assert candidates[0].route == lts.ROUTE_SYSTEM
    assert candidates[0].source_ref.endswith("note.md:1")
    assert "MU trigger" in candidates[0].title
