#!/usr/bin/env python3
"""Per-thesis disconfirmation registry (sidecar).

For every thesis we track this registry answers three operator questions:

  * ``fastest_way_wrong``     - the single fastest way the thesis is wrong
  * ``invalidating_evidence`` - the specific, checkable evidence that proves it
  * ``flip_trigger``          - the condition that flips the call

It is a *sidecar*. It never edits ``theses.json`` and never surfaces cards on
its own. Card surfacing (``today_decide.py`` / ``directive_recs.py`` /
``cockpit_html_gen.py``) is owned elsewhere; this module only *provides* a
ready-to-wire payload via :func:`card_disconfirmation`, shaped to match the
``disconfirmation`` dict those renderers already consume
(``summary`` / ``invalidates_if`` / ``confirm_before_acting``), so later wiring
is a single line in the (separately owned) card builder.

Seed entries are deliberately ``status="DRAFT — operator to confirm"``: Claude
does not invent invalidation logic as fact. :func:`render_gaps_md` writes a
plain operator-readable list of every thesis that still has no confirmed
kill-switch (missing entirely, or DRAFT).

CLI::

    python disconfirmation_registry.py --check        # validate + summarize
    python disconfirmation_registry.py --gaps         # (re)write docs/disconfirmation_gaps.md
    python disconfirmation_registry.py --gaps --stdout
    python disconfirmation_registry.py --show NVDA
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Optional


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "disconfirmation_registry.json"
THESES_PATH = ROOT / "theses.json"
GAPS_PATH = ROOT.parent / "docs" / "disconfirmation_gaps.md"

DRAFT_STATUS = "DRAFT — operator to confirm"
CONFIRMED_PREFIX = "CONFIRMED"

REQUIRED_ENTRY_FIELDS = (
    "fastest_way_wrong",
    "invalidating_evidence",
    "flip_trigger",
    "last_reviewed",
    "status",
)


class RegistryValidationError(ValueError):
    """Raised when the disconfirmation registry fails schema validation."""


# --------------------------------------------------------------------------- I/O

def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the registry. Raises :class:`RegistryValidationError`."""
    data = _load_json(path or REGISTRY_PATH)
    validate_registry(data)
    return data


def load_theses(path: Path | None = None) -> list[dict[str, Any]]:
    """Load ``theses.json`` (read-only; this module never writes it)."""
    data = _load_json(path or THESES_PATH)
    if not isinstance(data, list):
        raise RegistryValidationError("theses.json must be a top-level list")
    return data


# -------------------------------------------------------------------- validation

def validate_registry(data: Any) -> None:
    """Validate registry structure; raise with a clear message on any violation."""
    if not isinstance(data, dict):
        raise RegistryValidationError("registry root must be a JSON object")
    entries = data.get("entries")
    if not isinstance(entries, dict):
        raise RegistryValidationError("registry must have an 'entries' object keyed by ticker")
    for ticker, entry in entries.items():
        if not isinstance(ticker, str) or not ticker.strip():
            raise RegistryValidationError(f"entry key {ticker!r} is not a non-empty ticker string")
        if ticker != ticker.strip().upper():
            raise RegistryValidationError(f"entry key {ticker!r} must be an upper-case ticker")
        if not isinstance(entry, dict):
            raise RegistryValidationError(f"entry {ticker!r} must be an object")
        for field in REQUIRED_ENTRY_FIELDS:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RegistryValidationError(
                    f"entry {ticker!r} field {field!r} must be a non-empty string"
                )
        declared = entry.get("ticker")
        if declared is not None and declared != ticker:
            raise RegistryValidationError(
                f"entry {ticker!r} has a mismatched 'ticker' field {declared!r}"
            )
        thesis_id = entry.get("thesis_id")
        if thesis_id is not None and (not isinstance(thesis_id, str) or not thesis_id.strip()):
            raise RegistryValidationError(f"entry {ticker!r} 'thesis_id' must be a non-empty string")


# ------------------------------------------------------------------------ lookups

def _registry(registry: dict[str, Any] | None) -> dict[str, Any]:
    return registry if registry is not None else load_registry()


def is_confirmed(entry: dict[str, Any] | None) -> bool:
    """An entry is a real kill-switch only once an operator confirms it.

    DRAFT (or any non-``CONFIRMED``) status is treated as not-yet-confirmed.
    """
    if not entry:
        return False
    status = str(entry.get("status", "")).strip().upper()
    return status.startswith(CONFIRMED_PREFIX)


def get_disconfirmation(
    ticker: str,
    registry: dict[str, Any] | None = None,
) -> Optional[dict[str, Any]]:
    """Return the raw disconfirmation entry for ``ticker``, or ``None`` if absent.

    This is the one-line lookup helper for later card wiring; see
    :func:`card_disconfirmation` for a render-ready payload.
    """
    if not ticker:
        return None
    entries = _registry(registry).get("entries", {})
    return entries.get(ticker.strip().upper())


def card_disconfirmation(
    ticker: str,
    registry: dict[str, Any] | None = None,
) -> Optional[dict[str, Any]]:
    """Render-ready sidecar payload for a decision card, or ``None`` if no entry.

    The known keys (``summary`` / ``invalidates_if`` / ``confirm_before_acting``)
    mirror the ``disconfirmation`` dict that ``cockpit_html_gen`` already consumes,
    so later wiring in the (separately owned) card builder is one line::

        dc = card_disconfirmation(ticker)
        if dc:
            action["disconfirmation"] = dc

    Extra keys (``flip_trigger`` / ``status`` / ``confirmed`` / ...) are ignored by
    today's renderer but available to richer consumers. A DRAFT entry carries an
    explicit confirm-before-acting note so an unconfirmed kill-switch never reads
    as fact on a card.
    """
    entry = get_disconfirmation(ticker, registry=registry)
    if entry is None:
        return None
    confirmed = is_confirmed(entry)
    confirm_before: list[str] = []
    if not confirmed:
        confirm_before.append(
            "Disconfirmation is DRAFT — operator must confirm before treating it as a kill-switch."
        )
    return {
        "summary": entry["fastest_way_wrong"],
        "invalidates_if": [entry["invalidating_evidence"]],
        "confirm_before_acting": confirm_before,
        "flip_trigger": entry["flip_trigger"],
        "status": entry["status"],
        "confirmed": confirmed,
        "ticker": entry.get("ticker", ticker.strip().upper()),
        "last_reviewed": entry["last_reviewed"],
    }


# ---------------------------------------------------------------------- coverage

def is_active(thesis: dict[str, Any]) -> bool:
    return str(thesis.get("stance", "")).strip().upper() == "ACTIVE"


def active_theses(theses: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in theses if is_active(t)]


def coverage_for(thesis: dict[str, Any], registry: dict[str, Any] | None = None) -> str:
    """Return ``"MISSING"``, ``"DRAFT"``, or ``"CONFIRMED"`` for one thesis."""
    entry = get_disconfirmation(str(thesis.get("ticker", "")), registry=registry)
    if entry is None:
        return "MISSING"
    return "CONFIRMED" if is_confirmed(entry) else "DRAFT"


def missing_disconfirmation(
    theses: Iterable[dict[str, Any]],
    registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Active theses with no operator-confirmed disconfirmation (missing OR draft)."""
    reg = _registry(registry)
    return [t for t in active_theses(theses) if coverage_for(t, reg) != "CONFIRMED"]


# ------------------------------------------------------------------------ report

def _thesis_label(thesis: dict[str, Any]) -> str:
    return (
        f"{thesis.get('ticker', '?')} "
        f"({thesis.get('tier', '?')} · {thesis.get('lane', '?')} · {thesis.get('stance', '?')})"
    )


def _sort_key(thesis: dict[str, Any]) -> tuple[str, str]:
    return (str(thesis.get("tier", "")), str(thesis.get("ticker", "")))


def render_gaps_md(
    theses: Iterable[dict[str, Any]] | None = None,
    registry: dict[str, Any] | None = None,
    out_path: Path | str | None = GAPS_PATH,
    write: bool = True,
    as_of: str | None = None,
) -> str:
    """Render (and by default write) the operator-readable disconfirmation gaps list.

    The report reads as a plain "these theses can't currently be proven wrong"
    list: a MISSING section (no entry at all, active names called out first), a
    DRAFT section (seeded starters awaiting operator confirmation, shown in full),
    and a full coverage table. Returns the markdown string.
    """
    reg = _registry(registry)
    rows = list(theses) if theses is not None else load_theses()
    as_of = as_of or str(reg.get("last_updated") or "(date not set)")

    buckets: dict[str, list[dict[str, Any]]] = {"MISSING": [], "DRAFT": [], "CONFIRMED": []}
    for thesis in rows:
        buckets[coverage_for(thesis, reg)].append(thesis)
    for bucket in buckets.values():
        bucket.sort(key=_sort_key)

    n_total = len(rows)
    n_conf = len(buckets["CONFIRMED"])
    n_draft = len(buckets["DRAFT"])
    n_missing = len(buckets["MISSING"])

    out: list[str] = []
    out.append("# Disconfirmation Gaps")
    out.append("")
    out.append(
        "Theses that **cannot currently be proven wrong** — they lack an "
        "operator-confirmed kill-switch."
    )
    out.append("")
    out.append(f"As of: {as_of}")
    out.append(
        "Source: `src/disconfirmation_registry.json` (sidecar, owned by Claude Code / CC-C). "
        "Regenerate with `python src/disconfirmation_registry.py --gaps`."
    )
    out.append("")
    out.append(
        "A thesis is only treated as falsifiable once its disconfirmation entry is "
        "reviewed and marked `CONFIRMED`. `DRAFT — operator to confirm` entries are "
        "Claude-seeded starters: reasoned, specific, and checkable, but **not yet "
        "operator-confirmed fact**."
    )
    out.append("")
    out.append(
        f"**Coverage: {n_conf}/{n_total} theses have a confirmed kill-switch** — "
        f"{n_missing} missing, {n_draft} draft, {n_conf} confirmed."
    )
    out.append("")

    # --- MISSING -----------------------------------------------------------
    out.append("## No kill-switch at all (MISSING)")
    out.append("")
    if buckets["MISSING"]:
        out.append(
            "No disconfirmation entry exists — there is currently no written way to "
            "prove these wrong."
        )
        out.append("")
        active_missing = [t for t in buckets["MISSING"] if is_active(t)]
        other_missing = [t for t in buckets["MISSING"] if not is_active(t)]
        out.append("**Active (urgent — being acted on with no kill-switch):**")
        out.extend(
            [f"- {_thesis_label(t)}" for t in active_missing] or ["- (none)"]
        )
        out.append("")
        out.append("**Monitor / other:**")
        out.extend(
            [f"- {_thesis_label(t)}" for t in other_missing] or ["- (none)"]
        )
    else:
        out.append("(none — every thesis has at least a draft entry)")
    out.append("")

    # --- DRAFT -------------------------------------------------------------
    out.append("## DRAFT — operator to confirm")
    out.append("")
    if buckets["DRAFT"]:
        out.append(
            "Starter reasoning exists but is unconfirmed. Review, then edit and set "
            "`status: CONFIRMED` in the registry to make it a live kill-switch."
        )
        out.append("")
        for thesis in buckets["DRAFT"]:
            entry = get_disconfirmation(str(thesis.get("ticker", "")), reg) or {}
            out.append(f"### {_thesis_label(thesis)}")
            out.append(f"- **Fastest way wrong:** {entry.get('fastest_way_wrong', '')}")
            out.append(f"- **Invalidating evidence:** {entry.get('invalidating_evidence', '')}")
            out.append(f"- **Flip trigger:** {entry.get('flip_trigger', '')}")
            out.append(
                f"- Last reviewed: {entry.get('last_reviewed', '')} · "
                f"status: {entry.get('status', '')}"
            )
            out.append("")
    else:
        out.append("(none)")
        out.append("")

    # --- CONFIRMED ---------------------------------------------------------
    out.append("## Confirmed kill-switches")
    out.append("")
    if buckets["CONFIRMED"]:
        out.extend(f"- {_thesis_label(t)}" for t in buckets["CONFIRMED"])
    else:
        out.append("(none yet — operator has not confirmed any disconfirmation)")
    out.append("")

    # --- TABLE -------------------------------------------------------------
    out.append("## Full coverage table")
    out.append("")
    out.append("| Ticker | Tier | Lane | Stance | Disconfirmation |")
    out.append("|---|---|---|---|---|")
    for thesis in sorted(rows, key=_sort_key):
        out.append(
            f"| {thesis.get('ticker', '?')} | {thesis.get('tier', '?')} | "
            f"{thesis.get('lane', '?')} | {thesis.get('stance', '?')} | "
            f"{coverage_for(thesis, reg)} |"
        )
    out.append("")
    out.append(
        "_Generated by `src/disconfirmation_registry.py` (`--gaps`). "
        "Sidecar only; does not surface cards._"
    )

    md = "\n".join(out) + "\n"
    if write and out_path is not None:
        Path(out_path).write_text(md, encoding="utf-8")
    return md


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-thesis disconfirmation registry (sidecar)."
    )
    parser.add_argument("--check", action="store_true",
                        help="validate the registry and print a coverage summary")
    parser.add_argument("--gaps", action="store_true",
                        help="(re)write docs/disconfirmation_gaps.md")
    parser.add_argument("--stdout", action="store_true",
                        help="with --gaps, print the report instead of writing the file")
    parser.add_argument("--show", metavar="TICKER",
                        help="print the registry entry for one ticker")
    args = parser.parse_args(argv)

    registry = load_registry()  # validates or raises

    if args.show:
        entry = get_disconfirmation(args.show, registry)
        if entry is None:
            print(f"no entry for {args.show.strip().upper()}")
        else:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
        return 0

    if args.check and not args.gaps:
        theses = load_theses()
        missing = missing_disconfirmation(theses, registry)
        print(
            f"registry OK: {len(registry.get('entries', {}))} entries; "
            f"{len(missing)} of {len(active_theses(theses))} active theses "
            f"without a confirmed kill-switch"
        )
        return 0

    # default action (and --gaps): regenerate the gaps report
    theses = load_theses()
    md = render_gaps_md(theses, registry, write=not args.stdout)
    if args.stdout:
        print(md, end="")
    else:
        print(
            f"wrote {GAPS_PATH} ({len(theses)} theses; "
            f"{len(missing_disconfirmation(theses, registry))} active gaps)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
