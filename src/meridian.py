"""Conviction Engine — the `meridian` plug (Stage 1, S6).

Meridian critical-minerals research (HALEU, Project Janus, rare earths, …) ->
uniform fact-cards carrying each item VERBATIM. Trust 0.75, group
thematic_research.

Two item kinds, kept mechanically distinct so the Analyst can't conflate them:
  - research thesis / named call -> kind="analyst_call"
  - a MODELED trade              -> kind="model_trade"  (+ is_model=True,
                                    model_tag="Meridian model", content prefixed
                                    "[Meridian model] …")

This honors the standing rule that Meridian *model* trades are NOT live signals:
they are tagged and given a different kind, so a downstream consumer never treats
a paper trade as an actionable buy. Note the separation of concerns —
`trust_weight` is source RELIABILITY (0.75 for all Meridian items); `is_model` is
ACTIONABILITY. The plug carries both facts; the Analyst decides what to do.

Boundary (Sources vs Analyst — RECORD): verbatim thesis text + named levels +
the model/research tag are mechanical -> plug. Whether a thesis fits the book,
how to size it, and how to treat a model trade are the Analyst's calls.

Pure-logic + injectable: pass a list of structured `items`; Collection's
Meridian-doc read parses them, tests use fakes.

Item shape (subject required):
    {subject, item_type: "thesis"|"call"|"model", direction, entry, stop,
     target, window, theme, quote, date}
"""
from __future__ import annotations

from datetime import datetime, timezone

from sources import BaseSource


MERIDIAN_MODEL_TAG = "Meridian model"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_levels(entry, stop, target, window) -> str:
    # NOTE: duplicated from fundstrat_daily — flagged on the Build Plan to extract
    # into a shared util in a later hygiene pass (kept local now to avoid churn).
    parts = []
    if entry is not None:
        parts.append(f"entry {entry}")
    if stop is not None:
        parts.append(f"stop {stop}")
    if target is not None:
        parts.append(f"tgt {target}")
    if window:
        parts.append(str(window))
    return ", ".join(parts)


def meridian_reader(items, as_of: str | None = None) -> list[dict]:
    """One card per Meridian item. Model trades get kind="model_trade",
    is_model=True, and a "[Meridian model] " content prefix."""
    rows: list[dict] = []
    for it in items or []:
        subject = it.get("subject") or it.get("ticker") or it.get("theme")
        if not subject:
            continue
        item_type = (it.get("item_type") or "thesis").lower()
        is_model = item_type == "model"
        direction = it.get("direction")
        quote = it.get("quote")
        theme = it.get("theme")
        entry, stop, target, window = (
            it.get("entry"), it.get("stop"), it.get("target"), it.get("window"))
        levels = _fmt_levels(entry, stop, target, window)

        if quote:
            base = quote
        else:
            head = "Meridian: " + (f"{direction} " if direction else "") + subject
            if theme:
                tail = f" — {theme}"
            elif levels:
                tail = f" ({levels})"
            else:
                tail = ""
            base = head + tail
        content = f"[{MERIDIAN_MODEL_TAG}] {base}" if is_model else base

        data = {
            "subject": subject, "item_type": item_type, "direction": direction,
            "theme": theme, "entry": entry, "stop": stop, "target": target,
            "window": window, "is_model": is_model, "verbatim": quote or base,
        }
        if is_model:
            data["model_tag"] = MERIDIAN_MODEL_TAG

        ts = it.get("date") or as_of or _utc_now_iso()
        rows.append({
            "kind": "model_trade" if is_model else "analyst_call",
            "subject": subject, "content": content, "timestamp": ts, "data": data,
        })

    return rows


def build_meridian_source(
    items, name: str = "meridian", **reader_kwargs
) -> BaseSource:
    """Wire the Meridian reader into the uniform `meridian` plug
    (trust 0.75, group thematic_research via the dials)."""
    def fetcher() -> list[dict]:
        return meridian_reader(items, **reader_kwargs)

    return BaseSource(name=name, fetcher=fetcher)
