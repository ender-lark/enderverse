"""sell_gate.py -- Rail B sell-gate, as an OPERATOR-VISIBLE FLAG (not a hard block).

The operator authorized removing the sell-gate-as-blocker. So this module is a pure
function that returns a VERDICT a card carries and the render surfaces; it NEVER itself
emits a sell, and by default it never BLOCKs -- it FLAGs (a visible prompt). A BLOCK can
only fire when the operator turns the ``sell_gate_blocks`` dial on in
``src/sizing_tunables.json`` AND the doctrine condition (live thesis at/near a 52-week
low with no explicit thesis-break) actually holds.

Doctrine the FLAG mirrors (sell-gate & sizing doctrine, Rail A/B):
  - never sell a live thesis into weakness (the LEU/Janus failure mode);
  - load the thesis-of-record before any sell; near a 52-week low needs an explicit
    thesis-break justification.

Honesty: when the inputs needed to evaluate are absent (no thesis state, no 52-week range
read), the verdict is NOT_EVALUABLE with a visible not_checked stamp. The card stays
actionable. The gate never fabricates a PASS and never silently blocks on missing schema.
"""

from __future__ import annotations

from typing import Any

PASS = "PASS"
BLOCK = "BLOCK"
FLAG = "FLAG"
NOT_EVALUABLE = "NOT_EVALUABLE"

# Funding tiers where an exit is doctrine-permitted (no flag needed).
_PERMITTED_FUNDING_TIERS = {
    "redundant_wrapper",
    "winner_at_high",
    "tax_loss_harvest",
    "dead_thesis",
}


def evaluate_sell_gate(
    *,
    ticker: str,
    direction: str,
    thesis: dict[str, Any] | None,
    range_position: dict[str, Any] | None,
    next_catalyst: dict[str, Any] | None = None,
    funding_tier: str | None = None,
    thesis_break: str | None = None,
    blocks: bool = False,
) -> dict[str, Any]:
    """Return a Rail-B sell-gate verdict dict. ``direction`` in {TRIM, SELL}.

    ``blocks`` is the operator's ``sell_gate_blocks`` dial. When False (default), a
    doctrine hit yields FLAG (a visible prompt, card stays actionable). When True, the
    same hit yields BLOCK. Missing inputs always yield NOT_EVALUABLE regardless of the
    dial -- honesty, never a silent pass or a schema-driven block.

    Returned dict keys: verdict, evaluable(bool), thesis_state, alive, range_flag,
    catalyst_flag, requires_thesis_break, near_52wk_low, blocks, reasons[].
    """
    reasons: list[str] = []
    has_state = bool(thesis and thesis.get("state") not in (None, "", "UNKNOWN"))
    near_low = (range_position or {}).get("near_52wk_low", "not_checked")
    range_known = near_low in (True, False)
    has_break = bool(thesis_break and str(thesis_break).strip())

    # ---- activation gate: cannot evaluate without thesis state + a range read ----
    if not has_state or not range_known:
        missing = []
        if not has_state:
            missing.append("thesis state")
        if not range_known:
            missing.append("52wk range")
        return {
            "verdict": NOT_EVALUABLE,
            "evaluable": False,
            "thesis_state": (thesis or {}).get("state", "UNKNOWN"),
            "alive": None,
            "range_flag": None,
            "catalyst_flag": None,
            "requires_thesis_break": False,
            "near_52wk_low": near_low,
            "blocks": bool(blocks),
            "reasons": [
                f"sell-gate not evaluable -- missing {', '.join(missing)}; "
                "card left actionable, range/thesis not_checked"
            ],
        }

    state = str(thesis.get("state")).lower()
    alive = state not in ("impaired", "dead", "complete")

    range_flag = None
    if near_low is True:
        range_flag = "near 52-wk low -- selling into weakness"
        reasons.append(range_flag)

    catalyst_flag = None
    if next_catalyst and next_catalyst.get("live"):
        catalyst_flag = f"live catalyst {next_catalyst.get('label')} -> consider HOLD"
        reasons.append(catalyst_flag)

    # ---- doctrine-permitted exits -> PASS ----
    if (not alive) or (funding_tier in _PERMITTED_FUNDING_TIERS):
        return {
            "verdict": PASS,
            "evaluable": True,
            "thesis_state": state,
            "alive": alive,
            "range_flag": range_flag,
            "catalyst_flag": catalyst_flag,
            "requires_thesis_break": False,
            "near_52wk_low": near_low,
            "blocks": bool(blocks),
            "reasons": reasons
            or ["cleared: impaired/dead thesis or doctrine-permitted funding tier"],
        }

    # ---- doctrine hit: live thesis at/near low, no explicit break (LEU/Janus) ----
    if alive and near_low is True and not has_break:
        verdict = BLOCK if blocks else FLAG
        tail = (
            "blocked absent explicit thesis-break (sell_gate_blocks dial ON)"
            if blocks
            else "FLAGGED -- gentle prompt; needs an explicit thesis-break to sell "
            "(sell_gate_blocks dial OFF, so this never blocks)"
        )
        return {
            "verdict": verdict,
            "evaluable": True,
            "thesis_state": state,
            "alive": alive,
            "range_flag": range_flag,
            "catalyst_flag": catalyst_flag,
            "requires_thesis_break": True,
            "near_52wk_low": near_low,
            "blocks": bool(blocks),
            "reasons": reasons + [f"live thesis at/near 52-wk low -- {tail}"],
        }

    # ---- live thesis, not near low (or break supplied) -> FLAG (never auto-acts) ----
    return {
        "verdict": FLAG,
        "evaluable": True,
        "thesis_state": state,
        "alive": alive,
        "range_flag": range_flag,
        "catalyst_flag": catalyst_flag,
        "requires_thesis_break": not has_break,
        "near_52wk_low": near_low,
        "blocks": bool(blocks),
        "reasons": reasons
        + ["live thesis -- over-size is a PROMPT only; needs a reasoned thesis-break to sell"],
    }
