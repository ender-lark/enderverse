from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cloud_routine_commit
import cloud_routine_receipts


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "codex@example.invalid")
    _git(repo, "config", "user.name", "Codex Test")
    (repo / "src").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "cloud_routine_receipts.json").write_text('{"receipts":[]}\n', encoding="utf-8")
    (repo / "src" / "fundstrat_intake_state.json").write_text("{}\n", encoding="utf-8")
    (repo / "docs" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_cloud_routine_commit_dry_run_reports_allowed_and_unrelated(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "cloud_routine_receipts.json").write_text('{"receipts":[{"status":"success"}]}\n', encoding="utf-8")
    (repo / "src" / "fundstrat_intake_state.json").write_text('{"dirty":true}\n', encoding="utf-8")

    report = cloud_routine_commit.cloud_routine_commit(
        message="cloud receipt",
        allowed_paths=["src/cloud_routine_receipts.json"],
        cwd=repo,
        dry_run=True,
    )

    assert report["committed"] is False
    assert report["selected_paths"] == ["src/cloud_routine_receipts.json"]
    assert report["unrelated_dirty_paths"] == ["src/fundstrat_intake_state.json"]


def test_cloud_routine_commit_commits_only_allowed_paths(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "cloud_routine_receipts.json").write_text('{"receipts":[{"status":"success"}]}\n', encoding="utf-8")
    (repo / "src" / "fundstrat_intake_state.json").write_text('{"dirty":true}\n', encoding="utf-8")

    report = cloud_routine_commit.cloud_routine_commit(
        message="cloud receipt",
        allowed_paths=["src/cloud_routine_receipts.json"],
        cwd=repo,
    )

    assert report["committed"] is True
    assert report["selected_paths"] == ["src/cloud_routine_receipts.json"]
    assert _git(repo, "show", "--name-only", "--format=", "HEAD") == "src/cloud_routine_receipts.json"
    status = _git(repo, "status", "--short")
    assert "src/fundstrat_intake_state.json" in status
    assert "src/cloud_routine_receipts.json" not in status


def test_cloud_routine_commit_normalizes_legacy_receipts_before_commit(tmp_path):
    repo = _repo(tmp_path)
    payload = {
        "schema_version": 1,
        "receipts": [
            {
                "routine_id": "investing-os-parabolic-cache",
                "status": "success",
                "run_source": "scheduled",
                "recorded_at": "2026-06-16T14:37:00Z",
                "summary": "PARABOLIC SETUP SCREENER \u2014 2026-06-16",
            }
        ],
    }
    (repo / "src" / "cloud_routine_receipts.json").write_bytes(
        json.dumps(payload, indent=2, ensure_ascii=False).encode("cp1252")
    )

    report = cloud_routine_commit.cloud_routine_commit(
        message="cloud receipt",
        allowed_paths=["src/cloud_routine_receipts.json"],
        cwd=repo,
    )

    assert report["committed"] is True
    assert report["receipt_normalized"] is True
    assert cloud_routine_receipts.validate_receipt_file_encoding(repo / "src" / "cloud_routine_receipts.json") == []
    assert _git(repo, "show", "--name-only", "--format=", "HEAD") == "src/cloud_routine_receipts.json"


def test_default_allowlist_includes_redacted_fundstrat_intake_bookkeeping():
    assert "src/fundstrat_inbox_entries.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/fundstrat_intake_state.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/fundstrat_intake_summary.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/fundstrat_transcript_index.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/fundstrat_daytime_alert_state.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/live_source_config.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/fundstrat_daily_calls.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/orphan_triage.json" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS
    assert "src/orphan_triage.md" in cloud_routine_commit.DEFAULT_ALLOWED_PATHS


def test_cloud_routine_commit_reports_push_failure_after_commit(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "cloud_routine_receipts.json").write_text('{"receipts":[{"status":"success"}]}\n', encoding="utf-8")

    report = cloud_routine_commit.cloud_routine_commit(
        message="cloud receipt",
        allowed_paths=["src/cloud_routine_receipts.json"],
        cwd=repo,
        push=True,
    )

    assert report["valid"] is False
    assert report["committed"] is True
    assert report["pushed"] is False
    assert report["git_step"] == "push"
    assert "push failed" in report["reason"]
    assert _git(repo, "show", "--name-only", "--format=", "HEAD") == "src/cloud_routine_receipts.json"


def test_cloud_routine_commit_reports_status_failure(tmp_path):
    not_repo = tmp_path / "not-repo"
    not_repo.mkdir()

    report = cloud_routine_commit.cloud_routine_commit(
        message="cloud receipt",
        allowed_paths=["src/cloud_routine_receipts.json"],
        cwd=not_repo,
    )

    assert report["valid"] is False
    assert report["committed"] is False
    assert report["git_step"] == "status"
    assert "git status failed" == report["reason"]
