"""Query helpers for Fundstrat sector-allocation tactical stances.

The monthly Bible cache owns the raw compact state. This module provides a
stable query surface for tactical top/bottom sectors, named levels, and the
monthly checklist so dashboard/feed code does not reach into nested JSON
directly.
"""
from __future__ import annotations

from typing import Any


def sector_allocation(bible: dict[str, Any] | None) -> dict[str, Any]:
    bible = bible if isinstance(bible, dict) else {}
    sector = bible.get("sector_allocation")
    return sector if isinstance(sector, dict) else {}


def tactical_top3(bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = sector_allocation(bible).get("tactical_top3")
    return [row for row in rows or [] if isinstance(row, dict)]


def tactical_bottom3(bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = sector_allocation(bible).get("tactical_bottom3")
    return [row for row in rows or [] if isinstance(row, dict)]


def named_levels(bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = sector_allocation(bible).get("named_levels")
    return [row for row in rows or [] if isinstance(row, dict)]


def monthly_checklist(bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = sector_allocation(bible).get("monthly_checklist")
    return [row for row in rows or [] if isinstance(row, dict)]


def tactical_snapshot(bible: dict[str, Any] | None) -> dict[str, Any]:
    sector = sector_allocation(bible)
    return {
        "as_of": str(sector.get("as_of") or ""),
        "source": str(sector.get("source") or ""),
        "top3": tactical_top3(bible),
        "bottom3": tactical_bottom3(bible),
        "named_levels": named_levels(bible),
        "monthly_checklist": monthly_checklist(bible),
    }
