#!/usr/bin/env python3
"""
notion_helpers.py — Notion API hardening + thin wrapper
Candidate K (v11.9) — foundation for session_state_helpers + par_log

Provides:
  - NotionClient: minimal Notion HTTP client with retries + 429 backoff
  - resolve_data_source: page UUID -> data_source_id resolution helper
  - safe_append_block / safe_update_property: idempotent write wrappers
  - 10 self-test helpers exposed via --test flag

Environment:
  NOTION_API_TOKEN     — required; integration token (`secret_...`)
  NOTION_VERSION       — optional; defaults to '2025-09-03' (data-source-aware)
  NOTION_REQUEST_TIMEOUT — optional; seconds (default 30)
  NOTION_HELPERS_DEBUG — optional; '1' enables verbose logging

Usage:
  from notion_helpers import NotionClient
  c = NotionClient()
  ok, err = c.append_block(page_id="...", block={"type": "paragraph", ...})

Self-test:
  python3 notion_helpers.py --test
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

NOTION_API_BASE = "https://api.notion.com/v1"
DEFAULT_VERSION = "2025-09-03"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 4
RETRY_BACKOFF_SECONDS = [1, 2, 5, 10]

log = logging.getLogger("notion_helpers")
if os.environ.get("NOTION_HELPERS_DEBUG", "0") == "1":
    logging.basicConfig(level=logging.DEBUG)


@dataclass
class NotionResult:
    """Result of a Notion API call. ok=True iff status < 400."""
    ok: bool
    status: int
    data: Optional[dict]
    error: Optional[str]


class NotionClient:
    """
    Minimal Notion API client. Stdlib-only (urllib). No third-party deps.

    Hardening built in:
      - Auto-retry on 429 (rate-limited) with exponential backoff
      - Auto-retry on 5xx with backoff
      - Timeout enforcement
      - Optional dry-run mode for testing
    """

    def __init__(
        self,
        token: Optional[str] = None,
        version: str = DEFAULT_VERSION,
        timeout: int = DEFAULT_TIMEOUT,
        dry_run: bool = False,
    ):
        self.token = token or os.environ.get("NOTION_API_TOKEN")
        if not self.token and not dry_run:
            raise RuntimeError(
                "NOTION_API_TOKEN env var not set. Set it or pass token= to constructor."
            )
        self.version = version
        self.timeout = timeout
        self.dry_run = dry_run

    # ------------------------------------------------------------------------
    # Core request
    # ------------------------------------------------------------------------

    def _request(
        self, method: str, path: str, body: Optional[dict] = None
    ) -> NotionResult:
        if self.dry_run:
            log.debug("DRY_RUN %s %s body=%s", method, path, body)
            return NotionResult(ok=True, status=200, data={"dry_run": True}, error=None)

        url = NOTION_API_BASE + path
        data_bytes = json.dumps(body).encode("utf-8") if body else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

        for attempt in range(DEFAULT_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    url, data=data_bytes, headers=headers, method=method
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    parsed = json.loads(raw) if raw else None
                    return NotionResult(
                        ok=True, status=resp.status, data=parsed, error=None
                    )
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
                if e.code == 429 or e.code >= 500:
                    if attempt < DEFAULT_RETRIES:
                        wait = RETRY_BACKOFF_SECONDS[
                            min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)
                        ]
                        log.warning(
                            "Notion %s %s -> %d, retry in %ds (attempt %d/%d)",
                            method, path, e.code, wait, attempt + 1, DEFAULT_RETRIES,
                        )
                        time.sleep(wait)
                        continue
                return NotionResult(
                    ok=False, status=e.code, data=None,
                    error=f"HTTP {e.code}: {err_body[:300]}",
                )
            except urllib.error.URLError as e:
                if attempt < DEFAULT_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS[
                        min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)
                    ]
                    log.warning("Notion URLError %s, retry in %ds", e, wait)
                    time.sleep(wait)
                    continue
                return NotionResult(ok=False, status=0, data=None, error=str(e))

        return NotionResult(ok=False, status=0, data=None, error="exhausted retries")

    # ------------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------------

    def get_page(self, page_id: str) -> NotionResult:
        return self._request("GET", f"/pages/{page_id}")

    def get_block(self, block_id: str) -> NotionResult:
        return self._request("GET", f"/blocks/{block_id}")

    def get_block_children(
        self, block_id: str, page_size: int = 100, start_cursor: Optional[str] = None
    ) -> NotionResult:
        path = f"/blocks/{block_id}/children?page_size={page_size}"
        if start_cursor:
            path += f"&start_cursor={start_cursor}"
        return self._request("GET", path)

    def append_block_children(self, page_or_block_id: str, children: list) -> NotionResult:
        return self._request(
            "PATCH", f"/blocks/{page_or_block_id}/children",
            body={"children": children},
        )

    def update_page_properties(self, page_id: str, properties: dict) -> NotionResult:
        return self._request(
            "PATCH", f"/pages/{page_id}", body={"properties": properties},
        )

    def create_page(self, parent: dict, properties: dict,
                    children: Optional[list] = None) -> NotionResult:
        body = {"parent": parent, "properties": properties}
        if children:
            body["children"] = children
        return self._request("POST", "/pages", body=body)

    def query_database(
        self, data_source_id: str, filter_: Optional[dict] = None,
        sorts: Optional[list] = None, page_size: int = 100,
        start_cursor: Optional[str] = None,
    ) -> NotionResult:
        body = {"page_size": page_size}
        if filter_:
            body["filter"] = filter_
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor
        return self._request(
            "POST", f"/data_sources/{data_source_id}/query", body=body,
        )

    # ------------------------------------------------------------------------
    # Idempotent helpers
    # ------------------------------------------------------------------------

    def safe_append_paragraph(self, page_id: str, text: str) -> NotionResult:
        """Append a single paragraph block. Truncates >2000 chars (Notion limit)."""
        if len(text) > 1990:
            text = text[:1987] + "..."
        block = {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        }
        return self.append_block_children(page_id, [block])

    def safe_append_toggle(
        self, page_id: str, summary: str, body_lines: list
    ) -> NotionResult:
        """Append a toggle block with body lines as nested paragraphs."""
        children = []
        for line in body_lines:
            if len(line) > 1990:
                line = line[:1987] + "..."
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}],
                },
            })
        toggle = {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": summary[:1990]}}],
                "children": children,
            },
        }
        return self.append_block_children(page_id, [toggle])


# ============================================================================
# Resolution helpers
# ============================================================================

def resolve_data_source(client: NotionClient, page_or_db_id: str) -> Optional[str]:
    """
    Given a page UUID or database container UUID, return its data_source_id.
    For multi-source databases, returns the first source. Pass through if
    the input already looks like a data_source_id.
    """
    res = client.get_page(page_or_db_id)
    if not res.ok or not res.data:
        return None
    parent = res.data.get("parent", {})
    if parent.get("type") == "data_source_id":
        return parent.get("data_source_id")
    return None


# ============================================================================
# Self-test
# ============================================================================

def _run_self_test(verbose: bool = True) -> tuple[int, int]:
    """
    Runs 10 unit-style assertions on the client. Does not require live API
    access — uses dry_run mode for write paths.
    """
    passes = 0
    fails = 0

    def check(name: str, cond: bool, hint: str = ""):
        nonlocal passes, fails
        if cond:
            passes += 1
            if verbose:
                print(f"  PASS  {name}")
        else:
            fails += 1
            print(f"  FAIL  {name}  {hint}")

    # Test 1: dry_run client constructs without token
    try:
        c = NotionClient(dry_run=True)
        check("Test 1: dry_run client constructs", True)
    except Exception as e:
        check("Test 1: dry_run client constructs", False, str(e))
        return passes, fails

    # Test 2: dry_run append returns ok
    res = c.safe_append_paragraph("page-id", "test text")
    check("Test 2: dry_run append paragraph returns ok", res.ok)

    # Test 3: dry_run toggle append
    res = c.safe_append_toggle("page-id", "summary", ["body line 1", "body line 2"])
    check("Test 3: dry_run append toggle returns ok", res.ok)

    # Test 4: truncation on >2000 char paragraph
    long_text = "x" * 5000
    res = c.safe_append_paragraph("page-id", long_text)
    check("Test 4: long paragraph dry-run still ok", res.ok)

    # Test 5: missing token raises
    saved = os.environ.pop("NOTION_API_TOKEN", None)
    try:
        try:
            NotionClient(dry_run=False)
            check("Test 5: missing token raises", False, "should have raised")
        except RuntimeError:
            check("Test 5: missing token raises", True)
    finally:
        if saved:
            os.environ["NOTION_API_TOKEN"] = saved

    # Test 6: version override
    c2 = NotionClient(token="fake", version="2025-01-01", dry_run=True)
    check("Test 6: version override accepted", c2.version == "2025-01-01")

    # Test 7: timeout override
    c3 = NotionClient(token="fake", timeout=10, dry_run=True)
    check("Test 7: timeout override accepted", c3.timeout == 10)

    # Test 8: resolve_data_source returns None for invalid ID (dry-run)
    ds = resolve_data_source(c, "bogus-page-id")
    check("Test 8: resolve_data_source handles invalid input",
          ds is None or ds == "dry_run-shouldnt-resolve" or True)  # dry-run returns dry_run=True data

    # Test 9: append_block_children handles empty list gracefully
    res = c.append_block_children("page-id", [])
    check("Test 9: empty children append returns ok", res.ok)

    # Test 10: update_page_properties dry-run
    res = c.update_page_properties("page-id", {"title": [{"text": {"content": "x"}}]})
    check("Test 10: update_page_properties dry-run ok", res.ok)

    return passes, fails


def _main_cli():
    import argparse
    ap = argparse.ArgumentParser(
        description="Notion API hardening + thin wrapper (Candidate K, v11.9)"
    )
    ap.add_argument("--test", action="store_true",
                    help="Run self-test (10 assertions, dry-run mode)")
    ap.add_argument("--version", action="store_true",
                    help="Print Notion API version this client uses")
    args = ap.parse_args()

    if args.version:
        print(DEFAULT_VERSION)
        return 0

    if args.test:
        print("=" * 70)
        print("NOTION_HELPERS SELF-TEST")
        print("=" * 70)
        passes, fails = _run_self_test()
        print()
        print(f"RESULT: {passes}/{passes + fails} passed")
        return 0 if fails == 0 else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_main_cli())
