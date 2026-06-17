#!/usr/bin/env python3
"""Run the post-open UW evidence boundary in a commit-safe order.

The critical invariant is:

1. Capture bounded UW endpoint proof from the current action runbook.
2. Validate that the proof file is redacted summary data only.
3. Commit ``src/uw_endpoint_results.json`` before any feed/dashboard build.
4. Refresh the dashboard only after Git shows the proof file is clean.
5. Record a terminal receipt that says whether the boundary artifact committed.

This wrapper does not interpret neutral fetches as support. It only makes the
capture boundary honest and durable before the cockpit reads it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import cloud_routine_commit
import cloud_routine_receipts
from codex_uw.rest_client import UWConfigError, UWRestClient
from uw_action_runbook import build_uw_action_runbook
from uw_endpoint_result_capture import capture_endpoint_results
from uw_endpoint_result_proof import build_uw_endpoint_result_proof


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ROUTINE_ID = "investing-os-post-open-evidence-gate"
PROOF_PATH = SRC / "uw_endpoint_results.json"
FEED_PATH = SRC / "latest_cockpit_feed.json"

ALLOWED_TOP_KEYS = {
    "generated_at",
    "source",
    "runbook_line",
    "planned_checks",
    "rows",
    "counts",
    "honesty_rule",
}
ALLOWED_ROW_KEYS = {
    "mode",
    "endpoint",
    "ticker",
    "status",
    "checked_at",
    "summary",
    "source",
    "row_count",
}
SENSITIVE_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|secret|token|cookie|set-cookie|"
    r"private[_-]?key|raw[_-]?body|raw[_-]?response|response_body|html)",
    re.IGNORECASE,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def validate_redacted_endpoint_results(payload: Any) -> list[str]:
    """Return problems if the proof payload looks unsafe to commit."""
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["proof payload must be a JSON object"]
    extra_top = sorted(set(payload) - ALLOWED_TOP_KEYS)
    if extra_top:
        problems.append(f"unexpected top-level proof keys: {', '.join(extra_top)}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        problems.append("proof rows must be a list")
        rows = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"row {index} must be an object")
            continue
        extra_row = sorted(set(row) - ALLOWED_ROW_KEYS)
        if extra_row:
            problems.append(f"row {index} has unexpected keys: {', '.join(extra_row)}")
        summary = str(row.get("summary") or "")
        if len(summary) > 500:
            problems.append(f"row {index} summary is too long for redacted proof")
    compact = json.dumps(payload, sort_keys=True)
    if SENSITIVE_RE.search(compact):
        problems.append("proof payload contains sensitive/raw-response marker text")
    return problems


def _git_status_path(path: Path) -> str:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    proc = subprocess.run(
        ["git", "status", "--short", "--", rel],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def _path_is_committed_clean(path: Path) -> bool:
    return _git_status_path(path) == ""


def _load_runbook(feed_path: Path) -> dict[str, Any]:
    feed = _read_json(feed_path)
    if isinstance(feed, dict) and isinstance(feed.get("uw_action_runbook"), dict):
        return feed["uw_action_runbook"]
    if isinstance(feed, dict):
        return build_uw_action_runbook(feed)
    return {}


def _proof_counts(proof: dict[str, Any]) -> dict[str, int]:
    counts = proof.get("interpretation_counts") if isinstance(proof, dict) else {}
    return {
        "supports": int((counts or {}).get("supports") or 0),
        "contradicts": int((counts or {}).get("contradicts") or 0),
        "inconclusive": int((counts or {}).get("inconclusive") or 0),
        "missing": int((counts or {}).get("missing") or 0),
    }


def _summary_from_details(details: dict[str, Any]) -> str:
    counts = details.get("proof_interpretation_counts") or {}
    if details.get("boundary_artifact_committed"):
        boundary = "boundary_artifact_committed=true"
    elif details.get("no_fresh_boundary_data"):
        boundary = "no_fresh_boundary_data=true"
    else:
        boundary = "boundary_artifact_committed=false"
    return (
        f"UW proof {counts.get('supports', 0)} supports "
        f"{counts.get('contradicts', 0)} contradicts "
        f"{counts.get('inconclusive', 0)} inconclusive "
        f"{counts.get('missing', 0)} missing; {boundary}; "
        f"dashboard_refresh={details.get('dashboard_refresh_status', 'not_run')}"
    )


def _append_receipt(status: str, run_source: str, summary: str, details: dict[str, Any] | None = None) -> None:
    cloud_routine_receipts.append_receipt(
        routine_id=ROUTINE_ID,
        status=status,
        run_source=run_source,
        summary=summary,
        details=details,
    )


def _safe_commit(message: str, *, allowed_paths: list[str] | None = None, push: bool = False) -> dict[str, Any]:
    return cloud_routine_commit.cloud_routine_commit(
        message=message,
        allowed_paths=allowed_paths,
        cwd=ROOT,
        push=push,
    )


def run_post_open_uw_evidence(
    *,
    run_source: str,
    feed_path: Path = FEED_PATH,
    proof_path: Path = PROOF_PATH,
    timeout: float = 8.0,
    retries: int = 1,
    max_modes: int = 3,
    max_tickers_per_mode: int = 4,
    max_checks: int = 12,
    limit: int = 25,
    push: bool = False,
    refresh_dashboard: bool = True,
) -> dict[str, Any]:
    _append_receipt("started", run_source, "post-open evidence gate started")
    details: dict[str, Any] = {
        "boundary_artifact": str(proof_path.relative_to(ROOT)),
        "boundary_artifact_committed": False,
        "no_fresh_boundary_data": False,
        "feed_built_from_committed_proof": False,
        "dashboard_refresh_status": "not_run",
        "redaction_valid": False,
    }
    try:
        runbook = _load_runbook(feed_path)
        client = UWRestClient(timeout=timeout, retries=retries)
        capture = capture_endpoint_results(
            runbook,
            client,
            max_modes=max_modes,
            max_tickers_per_mode=max_tickers_per_mode,
            max_checks=max_checks,
            limit=limit,
        )
        redaction_problems = validate_redacted_endpoint_results(capture)
        details["redaction_problems"] = redaction_problems
        if redaction_problems:
            raise RuntimeError("UW endpoint proof failed redaction validation")
        details["redaction_valid"] = True
        _write_json(proof_path, capture)

        proof = build_uw_endpoint_result_proof(
            capture,
            runbook,
            generated_at=str(capture.get("generated_at") or ""),
            result_path=proof_path,
        )
        details.update({
            "proof_generated_at": capture.get("generated_at") or "",
            "proof_count": int(proof.get("count") or 0),
            "proof_line": proof.get("line") or "",
            "proof_newest_checked_at": proof.get("newest_checked_at") or "",
            "proof_interpretation_counts": _proof_counts(proof),
            "proof_blockers": proof.get("blockers") or [],
        })

        boundary_commit = _safe_commit(
            "Post-open UW endpoint proof boundary",
            allowed_paths=[str(proof_path.relative_to(ROOT)).replace("\\", "/")],
            push=False,
        )
        details["boundary_commit"] = {
            "valid": bool(boundary_commit.get("valid")),
            "committed": bool(boundary_commit.get("committed")),
            "commit": boundary_commit.get("commit") or "",
            "reason": boundary_commit.get("reason") or "",
            "selected_paths": boundary_commit.get("selected_paths") or [],
        }
        proof_clean = _path_is_committed_clean(proof_path)
        details["boundary_artifact_committed"] = bool(boundary_commit.get("committed")) and proof_clean
        details["no_fresh_boundary_data"] = (
            not details["boundary_artifact_committed"]
            and proof_clean
            and boundary_commit.get("reason") == "no allowed changed paths"
        )
        if not proof_clean:
            raise RuntimeError("UW proof file is still dirty after boundary commit; refusing dashboard refresh")
        if not details["boundary_artifact_committed"] and not details["no_fresh_boundary_data"]:
            raise RuntimeError(f"UW proof boundary commit failed: {boundary_commit.get('reason')}")

        if refresh_dashboard:
            proc = subprocess.run([sys.executable, "src/live_dashboard_refresh.py"], cwd=ROOT)
            details["dashboard_refresh_returncode"] = proc.returncode
            details["dashboard_refresh_status"] = "success" if proc.returncode == 0 else "failed"
            if proc.returncode != 0:
                raise RuntimeError(f"dashboard refresh failed with return code {proc.returncode}")
            feed_after = _read_json(feed_path)
            feed_proof = feed_after.get("uw_endpoint_proof") if isinstance(feed_after, dict) else {}
            details["feed_uw_proof_newest_checked_at"] = (feed_proof or {}).get("newest_checked_at") or ""
            details["feed_uw_proof_line"] = (feed_proof or {}).get("line") or ""
            details["feed_built_from_committed_proof"] = (
                bool(details.get("proof_newest_checked_at"))
                and details.get("proof_newest_checked_at") == details.get("feed_uw_proof_newest_checked_at")
                and _path_is_committed_clean(proof_path)
            )
            if not details["feed_built_from_committed_proof"]:
                raise RuntimeError("dashboard feed did not match the committed UW proof timestamp")

        summary = _summary_from_details(details)
        _append_receipt("success", run_source, summary, details)
        final_commit = _safe_commit("Post-open evidence gate scheduled run", push=push)
        details["final_commit"] = {
            "valid": bool(final_commit.get("valid")),
            "committed": bool(final_commit.get("committed")),
            "pushed": bool(final_commit.get("pushed")),
            "commit": final_commit.get("commit") or "",
            "reason": final_commit.get("reason") or "",
            "selected_paths": final_commit.get("selected_paths") or [],
        }
        return {"valid": True, "status": "success", "summary": summary, "details": details}
    except (UWConfigError, Exception) as exc:  # noqa: BLE001 - scheduled receipt must capture the honest failure.
        details["error"] = f"{type(exc).__name__}: {exc}"
        details["dashboard_refresh_status"] = details.get("dashboard_refresh_status") or "not_run"
        summary = _summary_from_details(details)
        _append_receipt("failed", run_source, summary, details)
        final_commit = _safe_commit(
            "Post-open evidence gate failed run",
            allowed_paths=[cloud_routine_commit.RECEIPT_PATH],
            push=push,
        )
        details["final_commit"] = {
            "valid": bool(final_commit.get("valid")),
            "committed": bool(final_commit.get("committed")),
            "pushed": bool(final_commit.get("pushed")),
            "commit": final_commit.get("commit") or "",
            "reason": final_commit.get("reason") or "",
            "selected_paths": final_commit.get("selected_paths") or [],
        }
        return {"valid": False, "status": "failed", "summary": summary, "details": details}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-source", choices=sorted(cloud_routine_receipts.VALID_RUN_SOURCES), default="manual")
    parser.add_argument("--feed", default=str(FEED_PATH))
    parser.add_argument("--out", default=str(PROOF_PATH))
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-modes", type=int, default=3)
    parser.add_argument("--max-tickers-per-mode", type=int, default=4)
    parser.add_argument("--max-checks", type=int, default=12)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--skip-dashboard-refresh", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    result = run_post_open_uw_evidence(
        run_source=args.run_source,
        feed_path=Path(args.feed),
        proof_path=Path(args.out),
        timeout=args.timeout,
        retries=args.retries,
        max_modes=args.max_modes,
        max_tickers_per_mode=args.max_tickers_per_mode,
        max_checks=args.max_checks,
        limit=args.limit,
        push=args.push,
        refresh_dashboard=not args.skip_dashboard_refresh,
    )
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(result["summary"])
        details = result.get("details") or {}
        print(f"boundary_artifact_committed={bool(details.get('boundary_artifact_committed'))}")
        print(f"no_fresh_boundary_data={bool(details.get('no_fresh_boundary_data'))}")
        if details.get("proof_newest_checked_at"):
            print(f"proof_newest_checked_at={details['proof_newest_checked_at']}")
        if details.get("feed_uw_proof_newest_checked_at"):
            print(f"feed_uw_proof_newest_checked_at={details['feed_uw_proof_newest_checked_at']}")
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
