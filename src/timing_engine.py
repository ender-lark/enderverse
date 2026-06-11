"""Timing engine â€” "is the window actually open?" as a computed class.

Inputs (the six T-lanes from the engine design):
  T1 index/complex gates (``timing_gates.json`` â€” e.g. Newton's QQQ band),
  T2 name entry zones (FS daily levels), T3 rotation state (scoped),
  T4 same-session UW interpretation, T5 catalyst proximity, T6 event risk.

Output: one of OPEN-NOW / STAGE-ONLY / GATED / WAIT with **dated reasons**
and **flip conditions** ("what changes this class"), never a bare label.

Doctrine enforced here:
* **No manufactured urgency** â€” OPEN-NOW is impossible without a named
  positive trigger (tested as an invariant). Quiet days read WAIT.
* A red gate blocks full size (GATED); a broken-but-reclaimed gate caps at
  STAGE-ONLY with the stage fraction from tunables until the confirm rule is
  observed â€” exactly the Newton QQQ situation this engine was born from.
* UW ``contradicts`` forces WAIT (re-check) regardless of other triggers.
* Event risk (T6) never blocks alone; it annotates, and (tunable) downgrades
  OPEN-NOW one notch to STAGE-ONLY when live.
* SELL/TRIM legs: OPEN-NOW only on a scoped rotation trigger (sleeve TURNING
  DOWN / overexposed); otherwise STAGE-ONLY paired with the adds they fund.

Pure functions; gate file I/O isolated in :func:`load_gates`.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parent
GATES_PATH = SRC / "timing_gates.json"

TIMING_CLASSES = ("OPEN-NOW", "STAGE-ONLY", "GATED", "WAIT")

class GatesMissingError(Exception):
    pass

def _today(today: str | date | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(str(today), "%Y-%m-%d").date()

def load_gates(path: Path | str = GATES_PATH) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise GatesMissingError(
            f"{path.name} absent â€” index gates NOT loaded (honest absence)."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    gates = payload.get("gates")
    if not isinstance(gates, list):
        raise GatesMissingError(f"{path.name}: 'gates' list missing")
    return gates

def evaluate_gate(gate: dict[str, Any], price: float | None) -> dict[str, Any]:
    """Suggest a gate state from a live price (the 9:40 routine / in-session
    helper). Pure suggestion â€” writing the new state back is a separate act."""
    lo, hi = gate.get("level_low"), gate.get("level_high")
    state = gate.get("state")
    if price is None or lo is None or hi is None or gate.get("kind") != "support_band":
        return {"suggested_state": state, "changed": False, "why": "no evaluable levels/price"}
    if price < lo:
        suggested = "red"
        why = f"price {price} below band {lo}-{hi}"
    elif price > hi:
        suggested = "green" if state in ("red_but_tested", "green") else "red_but_tested"
        why = f"price {price} above band {lo}-{hi}" + (
            " â€” confirm rule satisfied this session" if suggested == "green" else " â€” reclaim, awaiting confirm"
        )
    else:
        suggested = "red_but_tested" if state in ("red", "red_but_tested") else state
        why = f"price {price} inside band {lo}-{hi}"
    return {"suggested_state": suggested, "changed": suggested != state, "why": why}

def _gate_applies(gate: dict[str, Any], sleeves: list[str]) -> bool:
    applies = gate.get("applies_to") or ["*"]
    if "*" in applies or any(a.startswith("*") for a in applies):
        return True
    return bool(set(a.lower() for a in applies) & set(s.lower() for s in sleeves))

def compute_timing(
    ticker: str,
    *,
    direction: str = "BUY",
    sleeves: list[str] | None = None,
    gates: list[dict[str, Any]] | None = None,
    entry_zone: dict[str, Any] | None = None,
    uw_state: dict[str, Any] | None = None,
    rotation: dict[str, Any] | None = None,
    catalyst: dict[str, Any] | None = None,
    event_risks: list[dict[str, Any]] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    today: str | date | None = None,
) -> dict[str, Any]:
    now = _today(today)
    sleeves = sleeves or []
    gates = gates or []
    uw = uw_state or {}
    timing_cfg = weights.get("timing", {})
    stage_fraction = float(timing_cfg.get("stage_only_fraction", 0.33))
    horizon = int(goal.get("act_now_horizon_days", 10))

    reasons: list[str] = []
    flips: list[str] = []
    triggers: list[str] = []
    deadline: str | None = None

    # ----- SELL/TRIM lane: scoped rotation triggers only --------------------
    if direction.upper() in ("SELL", "TRIM"):
        rot = rotation or {}
        state = str(rot.get("state") or "").upper()
        if "TURNING DOWN" in state or rot.get("overexposed"):
            why = "sleeve TURNING DOWN" if "TURNING DOWN" in state else "sleeve overexposed vs model band"
            return {
                "class": "OPEN-NOW",
                "named_trigger": f"funding trim â€” {why} ({now.isoformat()})",
                "deadline": now.isoformat(),
                "reasons": [f"{why} â€” scoped rotation trigger"],
                "flips": ["trigger clears if rotation state recovers / exposure returns to band"],
                "stage_fraction": None,
                "gate_red": False,
            }
        return {
            "class": "STAGE-ONLY",
            "named_trigger": None,
            "deadline": None,
            "reasons": ["funding leg â€” execute paired with the adds it funds (no standalone urgency)"],
            "flips": ["sleeve turns down or goes overexposed â†’ OPEN-NOW", "the funded add's window opens"],
            "stage_fraction": stage_fraction,
            "gate_red": False,
        }

    # ----- BUY lane ----------------------------------------------------------
    applicable = [g for g in gates if _gate_applies(g, sleeves)]
    hard_red = [g for g in applicable if g.get("state") == "red" and g.get("blocks_full_size")]
    tested = [g for g in applicable if g.get("state") == "red_but_tested" and g.get("blocks_full_size")]
    for g in applicable:
        if g.get("kind") == "context":
            reasons.append(f"context: {g.get('note')} ({g.get('stated')})")

    if uw.get("interpretation") == "contradicts":
        return {
            "class": "WAIT",
            "named_trigger": None,
            "deadline": None,
            "reasons": [f"same-session UW evidence CONTRADICTS ({uw.get('date') or now.isoformat()}) â€” re-check forced"]
            + reasons,
            "flips": ["contradicting evidence resolves on re-check"],
            "stage_fraction": None,
            "gate_red": bool(hard_red),
        }

    # positive triggers (each one named + dated)
    if entry_zone:
        lo, hi, price = entry_zone.get("zone_low"), entry_zone.get("zone_high"), entry_zone.get("price")
        if None not in (lo, hi, price) and lo <= price <= hi:
            triggers.append(
                f"price {price} inside {entry_zone.get('source','FS')} entry zone {lo}-{hi} ({entry_zone.get('date', now.isoformat())})"
            )
        elif None not in (lo, hi, price):
            flips.append(f"pullback into the {entry_zone.get('source','FS')} zone {lo}-{hi} (now {price})")
    if uw.get("interpretation") == "supports" and str(uw.get("date") or "") == now.isoformat():
        triggers.append(f"same-session UW evidence supports ({now.isoformat()})")
    if catalyst:
        try:
            cat_date = datetime.strptime(str(catalyst.get("date")), "%Y-%m-%d").date()
            days = (cat_date - now).days
            if 0 <= days <= horizon:
                triggers.append(f"catalyst {catalyst.get('name')} in {days}td ({cat_date.isoformat()})")
                deadline = cat_date.isoformat()
        except (TypeError, ValueError):
            pass

    if hard_red:
        g = hard_red[0]
        return {
            "class": "GATED",
            "named_trigger": None,
            "deadline": None,
            "reasons": [f"gate RED: {g.get('note')} ({g.get('stated')})"] + reasons,
            "flips": [g.get("confirm_rule", "gate reclaims")] + flips,
            "stage_fraction": None,
            "gate_red": True,
        }

    if tested:
        g = tested[0]
        return {
            "class": "STAGE-ONLY",
            "named_trigger": triggers[0] if triggers else None,
            "deadline": deadline or now.isoformat(),
            "reasons": [f"gate red-but-tested: {g.get('note')} ({g.get('stated')})"]
            + [f"trigger live: {t}" for t in triggers]
            + reasons,
            "flips": [g.get("confirm_rule", "gate confirms")] + flips,
            "stage_fraction": stage_fraction,
            "gate_red": False,
        }

    if triggers:
        cls = "OPEN-NOW"
        out_reasons = [f"trigger: {t}" for t in triggers] + reasons
        out_flips = flips + ["trigger expires end-of-window; re-derive then"]
        if event_risks and timing_cfg.get("event_risk_downgrade", True):
            ev = event_risks[0]
            return {
                "class": "STAGE-ONLY",
                "named_trigger": triggers[0],
                "deadline": deadline or now.isoformat(),
                "reasons": out_reasons + [f"event risk live: {ev.get('note') or ev.get('name')} â€” downgraded one notch"],
                "flips": out_flips + ["event passes / derisks â†’ OPEN-NOW"],
                "stage_fraction": stage_fraction,
                "gate_red": False,
            }
        return {
            "class": cls,
            "named_trigger": triggers[0],
            "deadline": deadline or now.isoformat(),
            "reasons": out_reasons,
            "flips": out_flips,
            "stage_fraction": None,
            "gate_red": False,
        }

    for ev in event_risks or []:
        reasons.append(f"event risk: {ev.get('note') or ev.get('name')} ({ev.get('date', now.isoformat())})")
    flips = flips + [
        "same-session UW proof interpreted 'supports'",
        f"a dated catalyst inside {horizon}td",
    ]
    return {
        "class": "WAIT",
        "named_trigger": None,
        "deadline": None,
        "reasons": reasons or ["no named positive trigger today â€” quiet is a valid state"],
        "flips": flips,
        "stage_fraction": None,
        "gate_red": False,
    }
