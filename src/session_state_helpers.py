#!/usr/bin/env python3
"""
session_state_helpers.py — week-aware Session State writes
Candidate K (v11.9) — Notion Session State decomposition

Replaces the single ~22K-char Session State page with a parent-index + per-week
sub-page architecture. Writes go to the current ISO-week sub-page; the parent
holds an index linking to all weeks.

Architecture:
  ⚡ Session State (parent — operator's existing page UUID 343c5031-...)
    ├── 📋 Session State 2026-W18  (May 4-10)
    ├── 📋 Session State 2026-W19  (May 11-17)
    ├── 📋 Session State 2026-W20  (May 18-24)
    └── 📋 Session State 2026-W{NN} (auto-created on first write of new week)

Usage from automation scripts:
    from session_state_helpers import SessionStateWriter
    sw = SessionStateWriter()
    ok, err = sw.append_note(
        "Two-Lens Run on NBIS — Tier A confirmed post-Q1",
        ticker="NBIS", tag="two-lens-run"
    )

Falls back to legacy single-page write if SS_DECOMPOSITION_ENABLED=0 (operator
override for testing / rollback).
"""

import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from notion_helpers import NotionClient

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Operator's Session State parent page UUID
SESSION_STATE_PARENT_UUID = os.environ.get(
    "SESSION_STATE_PARENT_UUID",
    "343c5031-4bb6-81a1-9035-e4ffbf93ccdc",
)

# Feature flag — set to 0 to fall back to legacy single-page writes
DECOMPOSITION_ENABLED = os.environ.get("SS_DECOMPOSITION_ENABLED", "1") == "1"

_log = logging.getLogger("session_state_helpers")


# -----------------------------------------------------------------------------
# ISO-week utilities
# -----------------------------------------------------------------------------

def current_week_id(today: Optional[date] = None) -> str:
    """Return current week as 'YYYY-Wnn' (ISO 8601 week numbering)."""
    today = today or date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def week_page_title(week_id: str) -> str:
    """Format the standardized sub-page title."""
    return f"📋 Session State {week_id}"


def week_date_range(week_id: str) -> Tuple[date, date]:
    """Convert 'YYYY-Wnn' back to (Monday, Sunday) date range."""
    year_str, week_str = week_id.split("-W")
    year = int(year_str)
    week = int(week_str)
    monday = date.fromisocalendar(year, week, 1)
    sunday = date.fromisocalendar(year, week, 7)
    return monday, sunday


# -----------------------------------------------------------------------------
# SessionStateWriter
# -----------------------------------------------------------------------------

class SessionStateWriter:
    """Week-aware Session State writer. Auto-creates the current-week sub-page
    on first write of each ISO week. Subsequent writes append to that sub-page.

    State caching: caches discovered week-sub-page UUIDs in memory for the
    process lifetime to avoid re-querying. Use refresh_cache() if sub-pages
    are created/deleted externally during a long-running process.
    """

    def __init__(self, client: Optional[NotionClient] = None):
        self.client = client or NotionClient()
        self._week_cache: dict = {}  # week_id -> page_uuid

    # ----- Sub-page discovery + creation -----

    def find_week_subpage(self, week_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Find the sub-page UUID for a given ISO week. Returns (success,
        page_uuid_or_None, error). page_uuid is None if no such sub-page yet."""
        if week_id in self._week_cache:
            return True, self._week_cache[week_id], None

        # Fetch children of the parent page
        target_title = week_page_title(week_id)
        cursor: Optional[str] = None
        pages_checked = 0

        while pages_checked < 20:  # safety: max 20 pages of children
            ok, data, err = self.client.get_block_children(
                block_id=SESSION_STATE_PARENT_UUID, start_cursor=cursor,
            )
            if not ok:
                return False, None, f"failed to list parent children: {err}"
            assert data is not None
            for block in data.get("results", []):
                if block.get("type") == "child_page":
                    title = block.get("child_page", {}).get("title", "")
                    if title == target_title:
                        page_uuid = block["id"]
                        self._week_cache[week_id] = page_uuid
                        return True, page_uuid, None
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            pages_checked += 1

        # Not found
        return True, None, None

    def create_week_subpage(self, week_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Create the sub-page for a given ISO week under the parent. Returns
        (success, new_page_uuid, error)."""
        monday, sunday = week_date_range(week_id)
        title = week_page_title(week_id)

        # Title property + scaffolding content
        properties = {
            "title": [
                {"type": "text", "text": {"content": title}},
            ],
        }
        scaffold = [
            {
                "object": "block", "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {
                        "content": f"Week of {monday.isoformat()} → {sunday.isoformat()}"
                    }}]
                },
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {
                        "content": "Session activity for this week. Append-only; "
                                   "do not edit prior entries without preserving timestamps."
                    }}]
                },
            },
            {
                "object": "block", "type": "divider",
                "divider": {},
            },
        ]

        ok, data, err = self.client.create_page(
            parent={"page_id": SESSION_STATE_PARENT_UUID},
            properties=properties,
            children=scaffold,
        )
        if not ok:
            return False, None, f"failed to create sub-page: {err}"
        assert data is not None
        page_uuid = data["id"]
        self._week_cache[week_id] = page_uuid
        _log.info(f"Created Session State sub-page for {week_id}: {page_uuid}")
        return True, page_uuid, None

    def ensure_current_week_subpage(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Find or create the current week's sub-page. Returns (success, uuid, error)."""
        week_id = current_week_id()
        ok, uuid, err = self.find_week_subpage(week_id)
        if not ok:
            return False, None, err
        if uuid is None:
            return self.create_week_subpage(week_id)
        return True, uuid, None

    # ----- Append operations -----

    def append_note(
        self, content: str, ticker: Optional[str] = None,
        tag: Optional[str] = None, timestamp: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Append a timestamped note to the current week's sub-page.

        Returns (success, error_message_or_None). On success, returns (True, None).
        On failure, returns (False, error_description).

        Format of appended block:
            [HH:MM ET] [ticker:TICKER] [tag] — content
        """
        if not DECOMPOSITION_ENABLED:
            # Legacy mode: write directly to parent page
            return self._legacy_append(content, ticker, tag, timestamp)

        ts = timestamp or datetime.now(timezone.utc).astimezone()
        ts_str = ts.strftime("%H:%M %Z")
        prefix_parts = [f"[{ts_str}]"]
        if ticker:
            prefix_parts.append(f"[{ticker}]")
        if tag:
            prefix_parts.append(f"[{tag}]")
        prefix = " ".join(prefix_parts)
        full_text = f"{prefix} — {content}"

        # Notion paragraph blocks have 2000 char limit per rich_text element;
        # for very long notes, split into multiple paragraphs
        chunks = [full_text[i:i+1800] for i in range(0, len(full_text), 1800)]
        blocks = []
        for chunk in chunks:
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                },
            })

        ok, uuid, err = self.ensure_current_week_subpage()
        if not ok or uuid is None:
            return False, f"could not get current week sub-page: {err}"

        ok2, _, err2 = self.client.append_block_children(block_id=uuid, children=blocks)
        if not ok2:
            return False, f"append failed: {err2}"
        return True, None

    def _legacy_append(
        self, content: str, ticker: Optional[str], tag: Optional[str],
        timestamp: Optional[datetime],
    ) -> Tuple[bool, Optional[str]]:
        """Legacy mode: write directly to parent page (the pre-decomposition path).
        Used when SS_DECOMPOSITION_ENABLED=0."""
        ts = timestamp or datetime.now(timezone.utc).astimezone()
        ts_str = ts.strftime("%H:%M %Z")
        prefix_parts = [f"[{ts_str}]"]
        if ticker:
            prefix_parts.append(f"[{ticker}]")
        if tag:
            prefix_parts.append(f"[{tag}]")
        prefix = " ".join(prefix_parts)
        full_text = f"{prefix} — {content}"

        block = {
            "object": "block", "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": full_text[:1800]}}]
            },
        }
        ok, _, err = self.client.append_block_children(
            block_id=SESSION_STATE_PARENT_UUID, children=[block]
        )
        if not ok:
            return False, f"legacy append failed: {err}"
        return True, None

    # ----- Maintenance -----

    def refresh_cache(self) -> None:
        """Clear the in-memory week→UUID cache. Use if sub-pages were created or
        deleted externally during a long-running process."""
        self._week_cache.clear()

    def list_all_week_subpages(self) -> Tuple[bool, list, Optional[str]]:
        """List all week sub-pages discovered under the parent. Returns (success,
        list-of-(week_id, page_uuid)-tuples, error). Useful for index rebuilds."""
        results = []
        cursor: Optional[str] = None
        pages_checked = 0

        while pages_checked < 20:
            ok, data, err = self.client.get_block_children(
                block_id=SESSION_STATE_PARENT_UUID, start_cursor=cursor,
            )
            if not ok:
                return False, results, err
            assert data is not None
            for block in data.get("results", []):
                if block.get("type") == "child_page":
                    title = block.get("child_page", {}).get("title", "")
                    if title.startswith("📋 Session State "):
                        week_id = title.replace("📋 Session State ", "").strip()
                        results.append((week_id, block["id"]))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            pages_checked += 1

        return True, results, None


# -----------------------------------------------------------------------------
# Diagnostics
# -----------------------------------------------------------------------------

def main():
    """CLI diagnostic — show current week, find or report sub-page status."""
    print("=" * 70)
    print("session_state_helpers.py — diagnostic")
    print("=" * 70)
    week_id = current_week_id()
    monday, sunday = week_date_range(week_id)
    print(f"Current ISO week: {week_id}")
    print(f"Week range: {monday.isoformat()} → {sunday.isoformat()}")
    print(f"Expected sub-page title: '{week_page_title(week_id)}'")
    print(f"Decomposition enabled: {DECOMPOSITION_ENABLED}")
    print(f"Parent UUID: {SESSION_STATE_PARENT_UUID}")
    print()
    if not os.environ.get("NOTION_API_TOKEN"):
        print("(NOTION_API_TOKEN not set — skipping live discovery)")
        return
    writer = SessionStateWriter()
    ok, all_weeks, err = writer.list_all_week_subpages()
    if not ok:
        print(f"FAILED to list sub-pages: {err}")
        return
    print(f"Discovered {len(all_weeks)} week sub-page(s):")
    for w, uuid in sorted(all_weeks):
        print(f"  {w}: {uuid}")


if __name__ == "__main__":
    main()
