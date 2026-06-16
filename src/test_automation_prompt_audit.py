from __future__ import annotations

from pathlib import Path

import automation_prompt_audit


def _write_hardened_repo(path: Path) -> None:
    (path / "src").mkdir(parents=True)
    (path / "src" / "cloud_routine_commit.py").write_text("receipt_normalized = True\n", encoding="utf-8")
    (path / "src" / "cloud_routine_receipts.py").write_text(
        "JSON_READ_ENCODINGS = ('utf-8', 'cp1252')\n"
        "def validate_receipt_file_encoding(path):\n"
        "    return []\n",
        encoding="utf-8",
    )


def _automation(path: Path, *, prompt: str, status: str = "ACTIVE", cwd: Path | None = None) -> None:
    path.mkdir(parents=True)
    cwds = f'cwds = ["{str(cwd).replace(chr(92), chr(92) + chr(92))}"]\n' if cwd else ""
    (path / "automation.toml").write_text(
        'version = 1\n'
        f'id = "{path.name}"\n'
        'kind = "cron"\n'
        'name = "Investing OS Test"\n'
        f'prompt = "{prompt}"\n'
        f'status = "{status}"\n'
        'rrule = "FREQ=DAILY"\n'
        f"{cwds}",
        encoding="utf-8",
    )


def test_audit_accepts_safe_helper_and_hardened_worktree(tmp_path):
    repo = tmp_path / "repo"
    _write_hardened_repo(repo)
    automations = tmp_path / "automations"
    _automation(
        automations / "investing-os-safe",
        prompt="Run Investing OS. Use python src/cloud_routine_commit.py --message x --format text.",
        cwd=repo,
    )

    report = automation_prompt_audit.audit_automations(automations)

    assert report["valid"] is True
    assert report["active_investing_os_automations"] == 1
    assert report["problems"] == []


def test_audit_rejects_active_prompt_without_safe_helper(tmp_path):
    repo = tmp_path / "repo"
    _write_hardened_repo(repo)
    automations = tmp_path / "automations"
    _automation(
        automations / "investing-os-unsafe",
        prompt="Run Investing OS and commit changes directly.",
        cwd=repo,
    )

    report = automation_prompt_audit.audit_automations(automations)

    assert report["valid"] is False
    assert "active prompt does not use src/cloud_routine_commit.py safe helper" in report["problems"][0]


def test_audit_rejects_unhardened_worktree(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "cloud_routine_commit.py").write_text("# old helper\n", encoding="utf-8")
    (repo / "src" / "cloud_routine_receipts.py").write_text("# old receipts\n", encoding="utf-8")
    automations = tmp_path / "automations"
    _automation(
        automations / "investing-os-old-worktree",
        prompt="Run Investing OS. Use python src/cloud_routine_commit.py --message x --format text.",
        cwd=repo,
    )

    report = automation_prompt_audit.audit_automations(automations)

    assert report["valid"] is False
    assert any("safe helper does not report receipt normalization" in problem for problem in report["problems"])
    assert any("receipt reader lacks legacy encoding fallback" in problem for problem in report["problems"])


def test_missing_automation_directory_is_non_blocking(tmp_path):
    report = automation_prompt_audit.audit_automations(tmp_path / "missing")

    assert report["valid"] is True
    assert report["checked"] is False
