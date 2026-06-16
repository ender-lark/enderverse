#!/usr/bin/env python3
"""Repo-owned verification command for the Investing OS codebase.

Run from the repository root:

    python src/verify_standard.py

The standard suite runs the full repo-owned Python test tree and then runs a few
standalone self-tests that are intentionally executable outside pytest.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = ROOT / "tmp"


@dataclass(frozen=True)
class Check:
    name: str
    command: list[str]
    why: str


def _python() -> str:
    return sys.executable or "python"


def _npx() -> str | None:
    # On Windows, prefer npx.cmd so script execution policy does not block npx.
    if os.name == "nt":
        return shutil.which("npx.cmd") or shutil.which("npx")
    return shutil.which("npx")


def standard_checks() -> list[Check]:
    py = _python()
    return [
        Check(
            name="pytest-src",
            command=[py, "-m", "pytest", "src", "-q"],
            why="broad src suite, including rebuilt reallocation planner tests",
        ),
        Check(
            name="rebuilt-reallocate-direct-check",
            command=[py, "src/test_reallocate_rebuild.py"],
            why="covers the current target-weight rotation planner API",
        ),
        Check(
            name="cockpit-injector-selftest",
            command=[py, "src/render_cockpit.py", "--selftest"],
            why="proves the canonical JSX feed injector still round-trips",
        ),
        Check(
            name="broker-pdf-extractor-selftest",
            command=[py, "src/broker_pdf_extractor.py", "--self-test"],
            why="keeps broker position intake's standalone contract executable",
        ),
        Check(
            name="cloud-routine-receipts-utf8",
            command=[
                py,
                "src/cloud_routine_receipts.py",
                "--out",
                "src/cloud_routine_receipts.json",
                "--validate",
                "--require-utf8",
                "--format",
                "text",
            ],
            why="catches legacy-encoded receipt stores before dashboard builds break",
        ),
    ]


def js_check() -> Check:
    npx = _npx()
    if not npx:
        raise RuntimeError("npx is not available; install Node.js or omit --include-js")
    outfile = TMP_DIR / "verify-cockpit.js"
    return Check(
        name="cockpit-jsx-bundle",
        command=[
            npx,
            "esbuild",
            "src/conviction_cockpit_v5.jsx",
            "--bundle",
            "--external:react",
            "--format=esm",
            f"--outfile={outfile}",
            "--loader:.jsx=jsx",
        ],
        why="optional syntax/bundle check for dashboard JSX edits",
    )


def run_check(check: Check) -> int:
    print(f"\n== {check.name} ==", flush=True)
    print(check.why, flush=True)
    print("+ " + " ".join(check.command), flush=True)
    proc = subprocess.run(check.command, cwd=ROOT)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-js",
        action="store_true",
        help="also run the optional esbuild check for conviction_cockpit_v5.jsx",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list checks without running them",
    )
    args = parser.parse_args(argv)

    checks = standard_checks()
    if args.include_js:
        TMP_DIR.mkdir(exist_ok=True)
        checks.append(js_check())

    if args.list:
        for check in checks:
            print(f"{check.name}: {' '.join(check.command)}")
        return 0

    failures: list[str] = []
    try:
        for check in checks:
            if run_check(check) != 0:
                failures.append(check.name)
    finally:
        js_out = TMP_DIR / "verify-cockpit.js"
        if js_out.exists():
            js_out.unlink()

    if failures:
        print("\nVerification failed:")
        for name in failures:
            print(f"- {name}")
        return 1

    print("\nVerification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
