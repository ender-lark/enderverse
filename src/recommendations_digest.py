"""
recommendations_digest.py
=========================
v11.17 Active Recommendations Digest auto-refresh script.

Operationalizes the v11.17 framework patch: on every Fresh-Run / Where-do-I-stand /
Top-5 / What-changed / continuation-autopilot turn, fetch Active Trade Rationales DB,
group by freshness, detect duplicates, identify superseded/missing entries, and
surface a single consolidated digest.

Architecture:
- Pure-logic core (group_by_freshness, detect_duplicates, etc.) is testable without
  Notion API access. Tests in test_recommendations_digest.py.
- CLI wrapper at __main__ takes JSON input (export from Notion via MCP) and outputs
  digest as markdown.

CLI usage:
  python recommendations_digest.py --input rationales.json
  python recommendations_digest.py --input rationales.json --as-of 2026-05-14
  python recommendations_digest.py --input rationales.json --format json

Notion integration:
  Caller (Claude via MCP) fetches Active Trade Rationales DB rows, exports to JSON
  in the schema documented in EntrySchema below, and pipes to this script.

Author: Investing 2026 framework v11.17
Date: 2026-05-14
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

# Expected JSON entry schema (from Notion Active Trade Rationales DB):
# {
#   "page_id": "uuid",
#   "ticker_theme": "BMNR — T1 partial step-up (5%→7%)",
#   "ticker": "BMNR",                # parsed from ticker_theme
#   "rationale": "...",
#   "action": "BUY" | "SELL" | "HOLD",
#   "approx_size": 12000,
#   "reference_price": 21.91,
#   "target_price": 30.0,
#   "source": "Fundstrat-Lee" | "Meridian" | ...,
#   "lane": "Generational" | "Tactical Mode A" | ...,
#   "status": "Active" | "Executed" | "Expired" | "Cancelled" | "Renewed",
#   "recommended_date": "2026-05-14",
#   "valid_until": "2026-05-28",
#   "account_hint": "P-fid-Joint WROS",
# }

FRESHNESS_BANDS = {
    "FRESH": (0, 2),       # ≤2 days
    "MEDIUM": (3, 7),      # 3-7 days
    "OLDER": (8, 14),      # 8-14 days
    "STALE": (15, None),   # >14 days
}

CONFIDENCE_HINTS = {
    "HIGH": ["multi-source", "named anchor", "framework pre-commit", "forced",
             "P-AI-MOMENTUM-EXIT", "T1 trigger", "operator memory designates"],
    "MED-HIGH": ["single named source", "Tier B", "Lee Top 5", "Newton named"],
    "MED": ["operator-validated", "MED-HIGH", "Phase B"],
    "LOW": ["LOW", "MED ~55%", "speculative"],
}


@dataclass
class Rationale:
    """Single rationale entry parsed from Notion DB export."""
    page_id: str
    ticker: str
    ticker_theme: str
    rationale: str
    action: str
    approx_size: Optional[float]
    reference_price: Optional[float]
    target_price: Optional[float]
    source: Optional[str]
    lane: Optional[str]
    status: str
    recommended_date: Optional[date]
    valid_until: Optional[date]
    account_hint: Optional[str]

    # Computed fields
    days_old: int = 0
    freshness_band: str = "UNKNOWN"
    confidence_inferred: str = "UNKNOWN"
    flags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Rationale":
        """Parse a dict (from JSON export) into a Rationale."""
        def parse_date(s):
            if not s:
                return None
            if isinstance(s, date):
                return s
            try:
                return datetime.fromisoformat(s).date()
            except (ValueError, TypeError):
                return None

        ticker_theme = d.get("ticker_theme") or d.get("Ticker / Theme") or ""
        ticker = d.get("ticker") or _extract_ticker(ticker_theme)

        return cls(
            page_id=d.get("page_id") or d.get("id") or "",
            ticker=ticker,
            ticker_theme=ticker_theme,
            rationale=d.get("rationale") or d.get("Rationale") or "",
            action=d.get("action") or d.get("Action") or "",
            approx_size=d.get("approx_size") or d.get("Approx Size"),
            reference_price=d.get("reference_price") or d.get("Reference Price"),
            target_price=d.get("target_price") or d.get("Target Price"),
            source=d.get("source") or d.get("Source"),
            lane=d.get("lane") or d.get("Lane"),
            status=d.get("status") or d.get("Status") or "Active",
            recommended_date=parse_date(d.get("recommended_date") or d.get("Recommended Date")),
            valid_until=parse_date(d.get("valid_until") or d.get("Valid Until")),
            account_hint=d.get("account_hint") or d.get("Account Hint"),
        )


# ---------------------------------------------------------------------------
# Pure-logic core (testable without API access)
# ---------------------------------------------------------------------------

def _extract_ticker(ticker_theme: str) -> str:
    """Extract canonical ticker from a 'Ticker — Description' string.

    Examples:
      'BMNR — T1 partial step-up' → 'BMNR'
      'LEU Jan 2028 $300 LEAPS — nuclear' → 'LEU'
      'SMH May 22 $560/$520 put spread 7x' → 'SMH'
    """
    if not ticker_theme:
        return ""
    # Split on em-dash, hyphen, or whitespace; take first token
    for sep in ["—", " — ", " - "]:
        if sep in ticker_theme:
            head = ticker_theme.split(sep, 1)[0].strip()
            return head.split()[0] if head else ""
    return ticker_theme.split()[0] if ticker_theme.split() else ""


def compute_days_old(recommended_date: Optional[date], as_of: date) -> int:
    """Return age in days. Returns -1 if recommended_date is None (unparseable)."""
    if not recommended_date:
        return -1
    return (as_of - recommended_date).days


def assign_freshness_band(days_old: int) -> str:
    """Map age in days to FRESH / MEDIUM / OLDER / STALE / UNKNOWN."""
    if days_old < 0:
        return "UNKNOWN"
    for band, (lo, hi) in FRESHNESS_BANDS.items():
        if hi is None:
            if days_old >= lo:
                return band
        elif lo <= days_old <= hi:
            return band
    return "UNKNOWN"


def infer_confidence(rationale_text: str) -> str:
    """Infer confidence band from rationale text. Heuristic only."""
    if not rationale_text:
        return "UNKNOWN"
    text = rationale_text.upper()
    # Check direct confidence statements first
    if "HIGH ~9" in text or "HIGH ~8" in text or "HIGH (~9" in text or "HIGH (~8" in text:
        return "HIGH"
    if "MED-HIGH" in text or "MEDIUM-HIGH" in text:
        return "MED-HIGH"
    if "MED ~5" in text or "MEDIUM ~5" in text or "MED (~5" in text:
        return "MED"
    if "LOW ~" in text or "LOW (~" in text:
        return "LOW"
    # Fall back to keyword scan
    for band, hints in CONFIDENCE_HINTS.items():
        if any(h.upper() in text for h in hints):
            return band
    return "UNKNOWN"


def detect_duplicates(rationales: list[Rationale]) -> dict[str, list[Rationale]]:
    """Group Active rationales by ticker; return only tickers with >1 entry."""
    by_ticker = defaultdict(list)
    for r in rationales:
        if r.status != "Active":
            continue
        if r.ticker:
            by_ticker[r.ticker].append(r)
    return {t: rs for t, rs in by_ticker.items() if len(rs) > 1}


def detect_likely_superseded(
    duplicates: dict[str, list[Rationale]]
) -> list[tuple[Rationale, Rationale]]:
    """Within duplicate sets, flag older entries as likely-superseded by newer.

    Returns list of (older, newer) pairs.
    """
    pairs = []
    for ticker, rs in duplicates.items():
        # Sort by recommended_date desc (None → end)
        sorted_rs = sorted(
            rs,
            key=lambda r: r.recommended_date or date.min,
            reverse=True
        )
        newest = sorted_rs[0]
        for older in sorted_rs[1:]:
            if older.recommended_date and newest.recommended_date:
                if (newest.recommended_date - older.recommended_date).days >= 2:
                    pairs.append((older, newest))
    return pairs


def detect_untitled(rationales: list[Rationale]) -> list[Rationale]:
    """Flag entries with placeholder titles like 'New page' or empty ticker_theme."""
    return [r for r in rationales
            if not r.ticker_theme or
            r.ticker_theme.strip().lower() in ("new page", "untitled", "")]


def detect_expired_unmarked(
    rationales: list[Rationale],
    as_of: date,
    staleness_days: int = 14
) -> list[Rationale]:
    """Flag Active entries with valid_until past or recommended_date >staleness_days."""
    flagged = []
    for r in rationales:
        if r.status != "Active":
            continue
        if r.valid_until and r.valid_until < as_of:
            flagged.append(r)
            continue
        if r.recommended_date:
            age = (as_of - r.recommended_date).days
            if age > staleness_days:
                flagged.append(r)
    return flagged


def enrich_rationales(rationales: list[Rationale], as_of: date) -> list[Rationale]:
    """Apply all derived fields (days_old, freshness_band, confidence, flags) in place."""
    for r in rationales:
        r.days_old = compute_days_old(r.recommended_date, as_of)
        r.freshness_band = assign_freshness_band(r.days_old)
        r.confidence_inferred = infer_confidence(r.rationale)
        # Flag computation
        r.flags = []
        if not r.ticker_theme or r.ticker_theme.lower() in ("new page", "untitled"):
            r.flags.append("UNTITLED")
        if r.valid_until and r.valid_until < as_of and r.status == "Active":
            r.flags.append("VALID_UNTIL_EXPIRED")
        if r.days_old > 14 and r.status == "Active":
            r.flags.append("STALE_UNMARKED")
    return rationales


def group_by_freshness(rationales: list[Rationale]) -> dict[str, list[Rationale]]:
    """Group enriched rationales into FRESH/MEDIUM/OLDER/STALE/UNKNOWN buckets."""
    groups = {band: [] for band in list(FRESHNESS_BANDS.keys()) + ["UNKNOWN"]}
    for r in rationales:
        groups[r.freshness_band].append(r)
    return groups


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_markdown(
    rationales: list[Rationale],
    as_of: date,
    include_non_active: bool = False
) -> str:
    """Render the consolidated digest as markdown."""
    lines = []
    lines.append(f"# 📋 Active Recommendations Digest")
    lines.append(f"\n**As of: {as_of.isoformat()}**\n")
    lines.append(f"Total entries: {len(rationales)} "
                 f"(Active: {sum(1 for r in rationales if r.status == 'Active')})")

    active = [r for r in rationales if r.status == "Active"]
    groups = group_by_freshness(active)

    # Freshness summary line
    summary = " / ".join(
        f"{band}: {len(groups[band])}"
        for band in ["FRESH", "MEDIUM", "OLDER", "STALE", "UNKNOWN"]
    )
    lines.append(f"\nFreshness: {summary}\n")

    # Cleanup queue summary
    duplicates = detect_duplicates(active)
    superseded = detect_likely_superseded(duplicates)
    untitled = detect_untitled(active)
    expired = detect_expired_unmarked(active, as_of)
    lines.append(
        f"Cleanup queue: {len(duplicates)} duplicate-tickers, "
        f"{len(superseded)} likely-superseded, "
        f"{len(untitled)} untitled, "
        f"{len(expired)} stale-unmarked\n"
    )

    # FRESH section
    if groups["FRESH"]:
        lines.append("\n## 🟢 FRESH (≤2 days)\n")
        for r in sorted(groups["FRESH"], key=_sort_key):
            lines.append(_render_entry_short(r))

    # MEDIUM section
    if groups["MEDIUM"]:
        lines.append("\n## 🟡 MEDIUM (3-7 days)\n")
        for r in sorted(groups["MEDIUM"], key=_sort_key):
            lines.append(_render_entry_short(r))

    # OLDER section
    if groups["OLDER"]:
        lines.append("\n## 🟠 OLDER (8-14 days) — review needed\n")
        for r in sorted(groups["OLDER"], key=_sort_key):
            lines.append(_render_entry_short(r))

    # STALE section
    if groups["STALE"]:
        lines.append("\n## 🔴 STALE (>14 days) — auto-decay candidates\n")
        for r in sorted(groups["STALE"], key=_sort_key):
            lines.append(_render_entry_short(r))

    # Cleanup detail
    if duplicates:
        lines.append("\n## ⚠️ Duplicates detected\n")
        for ticker, rs in duplicates.items():
            lines.append(f"- **{ticker}**: {len(rs)} entries — "
                         f"{', '.join(r.recommended_date.isoformat() if r.recommended_date else '?' for r in rs)}")
    if superseded:
        lines.append("\n## ⚠️ Likely superseded\n")
        for older, newer in superseded:
            old_d = older.recommended_date.isoformat() if older.recommended_date else "?"
            new_d = newer.recommended_date.isoformat() if newer.recommended_date else "?"
            lines.append(f"- **{older.ticker}** {old_d} likely superseded by {new_d} entry")
    if untitled:
        lines.append("\n## ⚠️ Untitled entries\n")
        for r in untitled:
            lines.append(f"- {r.page_id} — needs retitling")

    return "\n".join(lines)


def _sort_key(r: Rationale):
    """Sort by confidence (HIGH first) then by approx_size desc."""
    conf_order = {"HIGH": 0, "MED-HIGH": 1, "MED": 2, "LOW": 3, "UNKNOWN": 4}
    return (
        conf_order.get(r.confidence_inferred, 4),
        -(r.approx_size or 0),
    )


def _render_entry_short(r: Rationale) -> str:
    size_str = f"${r.approx_size:,.0f}" if r.approx_size else "—"
    conf = r.confidence_inferred or "UNKNOWN"
    action = r.action or "?"
    date_str = r.recommended_date.isoformat() if r.recommended_date else "?"
    flags_str = f" [{', '.join(r.flags)}]" if r.flags else ""
    return (
        f"- **{r.ticker_theme}** · {date_str} · {conf} · {action} · {size_str}{flags_str}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="v11.17 Active Recommendations Digest renderer"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to JSON file with Active Trade Rationales DB export"
    )
    parser.add_argument(
        "--as-of",
        default=date.today().isoformat(),
        help="Date for freshness computation (default: today)"
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown"
    )
    args = parser.parse_args()

    with open(args.input) as f:
        raw = json.load(f)

    as_of = datetime.fromisoformat(args.as_of).date()

    rationales = [Rationale.from_dict(d) for d in raw]
    enrich_rationales(rationales, as_of)

    if args.format == "json":
        out = [asdict(r) for r in rationales]
        # Convert dates to strings for JSON
        for entry in out:
            for k in ("recommended_date", "valid_until"):
                if entry.get(k):
                    entry[k] = entry[k].isoformat() if isinstance(entry[k], date) else entry[k]
        print(json.dumps(out, indent=2, default=str))
    else:
        print(render_markdown(rationales, as_of))


if __name__ == "__main__":
    main()
