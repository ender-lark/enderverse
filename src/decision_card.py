"""The decision-card contract â€” Mandate v1.2 Â§3.1, additive to V2 action rows.

Five fields, none optional. A field the engine cannot derive is **stamped
UNKNOWN** (an explicit ``{"unknown": true, "note": ...}`` structure) â€” never
silently omitted. Cards attach to existing V2 action rows under the
``decision_card`` key, which downstream V2 validators tolerate (additive,
validate-if-present).

Field shapes (when known):

* ``move``       â€” ``{ticker, direction, lane, band}``; direction in
  :data:`DIRECTIONS`; ``band`` is a human-readable size band ("$56,609 staged",
  "0% -> 8% of book").
* ``conviction`` â€” ``{read, points, groups, raises}``; ``read`` in
  :data:`CONVICTION_READS`; ``groups`` maps independence-group name -> points;
  ``raises`` lists what evidence would raise the read.
* ``window``     â€” ``{class, deadline, reasons, flips}``; ``class`` in
  :data:`WINDOW_CLASSES`; ``reasons``/``flips`` are plain-English, dated.
* ``evidence``   â€” ``{links}``; each link ``{label, ref}`` reaching exact
  support within the tap budget.
* ``impact``     â€” ``{band, base, material, basis}``; ``base`` in
  ``{"book", "sleeve"}`` (lane-aware materiality) or UNKNOWN.
"""

from __future__ import annotations

from typing import Any

UNKNOWN = "UNKNOWN"
CARD_FIELDS = ("move", "conviction", "window", "evidence", "impact")
DIRECTIONS = {"BUY", "SELL", "TRIM", "HEDGE", "REVIEW", "RE-CHECK", UNKNOWN}
CONVICTION_READS = {"HIGH", "MODERATE", "LOW", "CONFLICTED", UNKNOWN}
WINDOW_CLASSES = {"OPEN-NOW", "STAGE-ONLY", "GATED", "WAIT", UNKNOWN}
IMPACT_BASES = {"book", "sleeve", UNKNOWN}

_UNKNOWN_NOTES = {
    "move": "move not derivable from current evidence",
    "conviction": "conviction inputs not wired or insufficient",
    "window": "no dated timing evidence available",
    "evidence": "no traceable evidence links available",
    "impact": "impact band not computable at proposed size",
}

def unknown_field(name: str) -> dict[str, Any]:
    """The explicit UNKNOWN stamp for a missing card field."""
    return {"unknown": True, "note": _UNKNOWN_NOTES.get(name, "not derivable")}

def is_unknown(field: Any) -> bool:
    return isinstance(field, dict) and field.get("unknown") is True

def stamp_unknown(card: dict[str, Any] | None) -> dict[str, Any]:
    """Return a card with all five fields present (missing ones stamped)."""
    card = dict(card or {})
    for name in CARD_FIELDS:
        if name not in card or card[name] in (None, {}, ""):
            card[name] = unknown_field(name)
    return card

def _problem(problems: list[str], text: str) -> None:
    problems.append(text)

def validate_decision_card(card: Any) -> list[str]:
    """Return a list of problems (empty list = valid).

    UNKNOWN-stamped fields are valid â€” the contract forbids *silent* omission,
    not honest ignorance.
    """
    problems: list[str] = []
    if not isinstance(card, dict):
        return ["decision_card must be an object"]
    for name in CARD_FIELDS:
        if name not in card:
            _problem(problems, f"missing field '{name}' (stamp UNKNOWN, never omit)")
    if problems:
        return problems

    move = card["move"]
    if not is_unknown(move):
        if not isinstance(move, dict):
            _problem(problems, "move must be an object or UNKNOWN-stamped")
        else:
            direction = move.get("direction")
            if direction not in DIRECTIONS:
                _problem(problems, f"move.direction '{direction}' not in {sorted(DIRECTIONS)}")
            ticker = move.get("ticker")
            if ticker is not None and not isinstance(ticker, str):
                _problem(problems, "move.ticker must be a string or null")
            if not str(move.get("band") or "").strip():
                _problem(problems, "move.band required (size lane / $ band) or stamp UNKNOWN")

    conviction = card["conviction"]
    if not is_unknown(conviction):
        if not isinstance(conviction, dict):
            _problem(problems, "conviction must be an object or UNKNOWN-stamped")
        else:
            read = conviction.get("read")
            if read not in CONVICTION_READS:
                _problem(problems, f"conviction.read '{read}' not in {sorted(CONVICTION_READS)}")
            points = conviction.get("points")
            if points is not None and (isinstance(points, bool) or not isinstance(points, (int, float))):
                _problem(problems, "conviction.points must be numeric or null")
            raises = conviction.get("raises")
            if raises is not None and not isinstance(raises, list):
                _problem(problems, "conviction.raises must be a list")

    window = card["window"]
    if not is_unknown(window):
        if not isinstance(window, dict):
            _problem(problems, "window must be an object or UNKNOWN-stamped")
        else:
            cls = window.get("class")
            if cls not in WINDOW_CLASSES:
                _problem(problems, f"window.class '{cls}' not in {sorted(WINDOW_CLASSES)}")
            reasons = window.get("reasons")
            if not isinstance(reasons, list) or not reasons:
                _problem(problems, "window.reasons must be a non-empty list (no urgency without a named reason)")
            flips = window.get("flips")
            if flips is not None and not isinstance(flips, list):
                _problem(problems, "window.flips must be a list")

    evidence = card["evidence"]
    if not is_unknown(evidence):
        if not isinstance(evidence, dict):
            _problem(problems, "evidence must be an object or UNKNOWN-stamped")
        else:
            links = evidence.get("links")
            if not isinstance(links, list) or not links:
                _problem(problems, "evidence.links must be a non-empty list (or stamp UNKNOWN)")
            else:
                for i, link in enumerate(links):
                    if not isinstance(link, dict) or not str(link.get("label") or "").strip():
                        _problem(problems, f"evidence.links[{i}] needs a 'label'")

    impact = card["impact"]
    if not is_unknown(impact):
        if not isinstance(impact, dict):
            _problem(problems, "impact must be an object or UNKNOWN-stamped")
        else:
            base = impact.get("base")
            if base not in IMPACT_BASES:
                _problem(problems, f"impact.base '{base}' not in {sorted(IMPACT_BASES)} (lane-aware materiality)")
            material = impact.get("material")
            if material is not None and not isinstance(material, bool):
                _problem(problems, "impact.material must be true/false/null")
            if not str(impact.get("band") or "").strip():
                _problem(problems, "impact.band required or stamp UNKNOWN")

    return problems

def attach(action_row: dict[str, Any], card: dict[str, Any] | None) -> dict[str, Any]:
    """Stamp, validate, and attach a card to a V2 action row (additive)."""
    if not isinstance(action_row, dict):
        raise TypeError("action_row must be a dict")
    stamped = stamp_unknown(card)
    problems = validate_decision_card(stamped)
    if problems:
        raise ValueError("invalid decision_card: " + "; ".join(problems))
    action_row["decision_card"] = stamped
    return action_row
