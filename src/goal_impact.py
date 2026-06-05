"""Goal-impact metadata for cockpit action rows.

The early-retirement goal is operational in v1: surface asymmetric upside,
avoidable downside, sizing gaps, leverage/timing opportunities, and stale
decision risk. This module is pure and deterministic; it only annotates action
rows the engine already produced.
"""
from __future__ import annotations

from copy import deepcopy

GOAL_CHANNELS = {
    "upside",
    "downside_protection",
    "sizing_gap",
    "leverage",
    "conviction",
    "opportunity_cost",
    "data_quality",
}
GOAL_IMPACTS = {"High", "Medium", "Low"}
TIME_WINDOWS = {"today", "1-3 trading days", "1-2 weeks", "no timing edge"}
CAPITAL_EFFECTS = {
    "start",
    "add",
    "trim",
    "sell",
    "hedge",
    "rotate",
    "review",
    "no_capital_yet",
}

_KIND_DEFAULTS = {
    "red_gate": {
        "goal_channels": ["downside_protection", "data_quality"],
        "goal_impact": "High",
        "goal_score": 88,
        "time_window": "today",
        "capital_effect": "review",
        "action_label": "CLEAR GATE",
        "why_it_moves_goal": "A hard gate can block or invalidate a capital action.",
    },
    "sell_fast": {
        "goal_channels": ["downside_protection", "opportunity_cost"],
        "goal_impact": "High",
        "goal_score": 86,
        "time_window": "today",
        "capital_effect": "trim",
        "action_label": "TRIM/SELL REVIEW",
        "why_it_moves_goal": "A sell-fast warning on a tracked name can prevent avoidable drawdown.",
    },
    "buy_now": {
        "goal_channels": ["upside", "conviction", "opportunity_cost"],
        "goal_impact": "High",
        "goal_score": 84,
        "time_window": "today",
        "capital_effect": "add",
        "action_label": "BUY/ADD",
        "why_it_moves_goal": "A buy trigger with rising conviction can improve compounding if sized in time.",
    },
    "top_prospect": {
        "goal_channels": ["upside", "conviction", "opportunity_cost"],
        "goal_impact": "High",
        "goal_score": 82,
        "time_window": "1-3 trading days",
        "capital_effect": "start",
        "action_label": "START/VALIDATE",
        "why_it_moves_goal": "An ACT_NOW prospect may be an asymmetric opportunity before the window closes.",
        "missing_evidence": ["confirm thesis", "size through gate"],
    },
    "research_act_now": {
        "goal_channels": ["conviction", "upside", "opportunity_cost"],
        "goal_impact": "High",
        "goal_score": 74,
        "time_window": "1-3 trading days",
        "capital_effect": "review",
        "action_label": "RESEARCH ACT NOW",
        "why_it_moves_goal": "Time-sensitive research can unlock or reject a capital move before the setup decays.",
        "missing_evidence": ["decision-grade thesis", "position sizing decision"],
    },
    "reentry_zone": {
        "goal_channels": ["upside", "conviction", "opportunity_cost"],
        "goal_impact": "High",
        "goal_score": 80,
        "time_window": "today",
        "capital_effect": "add",
        "action_label": "RE-ENTER",
        "why_it_moves_goal": "A re-entry trigger can restore exposure after a setup returns.",
    },
    "decision_aging": {
        "goal_channels": ["opportunity_cost", "upside"],
        "goal_impact": "High",
        "goal_score": 78,
        "time_window": "today",
        "capital_effect": "review",
        "action_label": "DECIDE",
        "why_it_moves_goal": "An unresolved opportunity can keep running while capital stays undeployed.",
    },
    "catalyst_imminent": {
        "goal_channels": ["conviction", "downside_protection", "upside"],
        "goal_impact": "Medium",
        "goal_score": 68,
        "time_window": "1-3 trading days",
        "capital_effect": "review",
        "action_label": "REVIEW",
        "why_it_moves_goal": "A near-term catalyst can change upside, downside, or sizing posture.",
    },
    "lean_in": {
        "goal_channels": ["sizing_gap", "upside", "opportunity_cost"],
        "goal_impact": "High",
        "goal_score": 76,
        "time_window": "1-2 weeks",
        "capital_effect": "add",
        "action_label": "ADD/ROTATE",
        "why_it_moves_goal": "A conviction-backed sizing gap can make a right call too small.",
    },
    "conviction_gap": {
        "goal_channels": ["sizing_gap", "conviction", "opportunity_cost"],
        "goal_impact": "High",
        "goal_score": 79,
        "time_window": "1-3 trading days",
        "capital_effect": "review",
        "action_label": "SIZE GAP",
        "why_it_moves_goal": "A high-conviction target gap can make the right thesis too small to matter unless disposition is explicit.",
        "missing_evidence": ["live opportunity", "funding leg", "pre-trade gate"],
    },
    "monitor_reentry": {
        "goal_channels": ["conviction", "upside"],
        "goal_impact": "Medium",
        "goal_score": 58,
        "time_window": "1-2 weeks",
        "capital_effect": "no_capital_yet",
        "action_label": "WATCH",
        "why_it_moves_goal": "A MONITOR sleeve needs a genuine re-entry trigger before capital moves.",
        "missing_evidence": ["confirm re-entry trigger"],
    },
    "macro_alert": {
        "goal_channels": ["downside_protection", "data_quality"],
        "goal_impact": "Medium",
        "goal_score": 56,
        "time_window": "today",
        "capital_effect": "review",
        "action_label": "CHECK MACRO",
        "why_it_moves_goal": "Macro conditions can change whether a capital action is worth taking.",
    },
    "watch_entry": {
        "goal_channels": ["upside", "conviction"],
        "goal_impact": "Medium",
        "goal_score": 52,
        "time_window": "1-2 weeks",
        "capital_effect": "no_capital_yet",
        "action_label": "WATCH",
        "why_it_moves_goal": "The setup is relevant, but the entry trigger has not fired.",
        "missing_evidence": ["entry trigger"],
    },
    "research_review": {
        "goal_channels": ["conviction", "upside"],
        "goal_impact": "Medium",
        "goal_score": 48,
        "time_window": "1-2 weeks",
        "capital_effect": "no_capital_yet",
        "action_label": "RESEARCH NOW",
        "why_it_moves_goal": "Research may raise conviction enough to justify a capital move.",
        "missing_evidence": ["decision-grade thesis"],
    },
    "synthesis": {
        "goal_channels": ["conviction", "opportunity_cost"],
        "goal_impact": "Medium",
        "goal_score": 54,
        "time_window": "1-3 trading days",
        "capital_effect": "review",
        "action_label": "REVIEW",
        "why_it_moves_goal": "Synthesis identified a decision candidate that needs operator review.",
    },
    "stale_critical": {
        "goal_channels": ["data_quality", "downside_protection"],
        "goal_impact": "Low",
        "goal_score": 32,
        "time_window": "today",
        "capital_effect": "no_capital_yet",
        "action_label": "REFRESH DATA",
        "why_it_moves_goal": "Stale critical data lowers confidence until refreshed.",
    },
}


def _confidence_bump(confidence: str) -> int:
    return {"High": 6, "Moderate": 0, "Low": -8}.get(confidence, 0)


def _impact_from_score(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def annotate_action(row: dict) -> dict:
    """Return a copy of one action row with goal-impact fields."""
    out = deepcopy(row)
    meta = dict(_KIND_DEFAULTS.get(out.get("kind"), _KIND_DEFAULTS["watch_entry"]))

    score = int(meta["goal_score"]) + _confidence_bump(out.get("confidence"))
    if out.get("age_days") is not None:
        score += 8
    score = max(0, min(100, score))

    meta["goal_score"] = score
    meta["goal_impact"] = _impact_from_score(score)

    if out.get("days_to_catalyst") is not None:
        days = out.get("days_to_catalyst")
        meta["time_window"] = "today" if days == 0 else "1-3 trading days" if days <= 3 else "1-2 weeks"

    for key, value in meta.items():
        out.setdefault(key, value)
    out["goal_channels"] = [c for c in out.get("goal_channels", []) if c in GOAL_CHANNELS]
    out.setdefault("missing_evidence", [])
    return out


def annotate_actions(rows: list[dict] | None) -> list[dict]:
    return [annotate_action(r) for r in (rows or [])]
