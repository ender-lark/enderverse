"""Fundstrat analyst lane metadata.

Fundstrat is useful as a source of truth, but its internal voices should not be
treated identically. This helper adds interpretation metadata while keeping all
Fundstrat rows in the single "fundstrat" independence group elsewhere.
"""
from __future__ import annotations

import re
from typing import Any


CRYPTO_TERMS = {
    "btc", "bitcoin", "eth", "ethereum", "crypto", "sol", "solana", "ibit",
    "ethe", "coin", "mstr", "bmnr", "hype",
}

PROMOTIONAL_TERMS = {
    "webinar", "podcast", "replay", "survey", "registration", "register",
    "event invite", "join us", "subscribe", "sponsored", "promotion",
}

MONTHLY_BASELINE_TERMS = {
    "monthly", "bible", "market update", "what to own", "top 5", "bottom 5",
    "consider list", "core list", "granny shots", "granny",
}

WEEKLY_REVIEW_TERMS = {
    "weekly review", "week in review", "weekly strategy", "weekly recap",
    "weekly update", "week ahead",
}

MACRO_TERMS = {
    "first word", "first to market", "macro", "fomc", "fed", "cpi", "ppi",
    "payroll", "jobs report", "rates", "yields", "10y", "inflation",
    "liquidity", "seasonality", "tariff", "oil", "geopolitical", "risk-on",
    "risk off", "risk-off", "volatility", "vix", "earnings season",
}

TECHNICAL_TERMS = {
    "breakout", "breakdown", "support", "resistance", "trend", "reversal",
    "bounce", "corrective", "pullback", "above", "below", "close", "holds",
    "hold", "target", "stop", "entry",
}

ACTION_CHANGE_TERMS = {
    "add", "accumulate", "avoid", "break above", "break below", "buy",
    "downgrade", "entry", "hedge", "invalidation", "near-term", "patience",
    "raise", "re-check", "recheck", "rebalance", "reduce", "resistance",
    "risk/reward", "rotate", "rotation", "sell", "size", "sizing", "stop",
    "support", "take profits", "target", "trim", "upgrade", "wait", "watch",
}

PROMOTING_DIRECTIONS = {"buy", "add", "accumulate", "sell", "trim", "reduce", "avoid"}
WATCH_DIRECTIONS = {"watch", "hold"}


def _blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).strip().lower()


def _has_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _has_price_level(text: str) -> bool:
    return bool(re.search(r"(?:\$|near\s+|toward\s+|above\s+|below\s+)?\b\d{2,5}(?:\.\d+)?\b", text))


def _has_specificity(text: str, *, entry: Any = None, stop: Any = None, target: Any = None, window: Any = None) -> bool:
    if entry is not None or stop is not None or target is not None or window:
        return True
    if _has_price_level(text) and any(term in text for term in TECHNICAL_TERMS):
        return True
    return any(term in text for term in {"entry", "stop", "target", "if ", "weekly close", "daily close"})


def _has_action_change(text: str, *, direction: Any = None, entry: Any = None, stop: Any = None,
                       target: Any = None, window: Any = None) -> bool:
    direction_l = str(direction or "").strip().lower()
    if direction_l in PROMOTING_DIRECTIONS:
        return True
    if entry is not None or stop is not None or target is not None or window:
        return True
    if _has_specificity(text, entry=entry, stop=stop, target=target, window=window):
        return True
    return _has_any(text, ACTION_CHANGE_TERMS)


def classify_fundstrat_publication(
    *,
    author: str = "",
    text: str = "",
    ticker: str = "",
    subject: str = "",
    direction: Any = None,
    entry: Any = None,
    stop: Any = None,
    target: Any = None,
    window: Any = None,
) -> dict[str, Any]:
    """Classify what kind of Fundstrat item this is and how useful it is.

    The classifier is intentionally conservative: a Fundstrat publication is
    only a daily-call input when it changes a portfolio decision, timing,
    sizing, hedge posture, risk gate, or research priority. Otherwise it stays
    as redacted audit context or monthly baseline context.
    """
    body = _blob(author, subject, text, ticker)
    author_l = _blob(author)
    direction_l = str(direction or "").strip().lower()
    specific = _has_specificity(body, entry=entry, stop=stop, target=target, window=window)
    action_changing = _has_action_change(
        body,
        direction=direction,
        entry=entry,
        stop=stop,
        target=target,
        window=window,
    )
    promotional = _has_any(body, PROMOTIONAL_TERMS)
    monthly = _has_any(body, MONTHLY_BASELINE_TERMS)
    weekly = _has_any(body, WEEKLY_REVIEW_TERMS)
    newton_author = "newton" in author_l or "mark newton" in body
    farrell_author = "farrell" in author_l or "sean farrell" in body
    lee_author = "lee" in author_l or "tom lee" in body
    crypto = farrell_author or _has_any(body, CRYPTO_TERMS)
    macro = lee_author or _has_any(body, MACRO_TERMS)
    technical = newton_author or (
        not lee_author
        and not farrell_author
        and not macro
        and not crypto
        and _has_any(body, TECHNICAL_TERMS)
    )
    has_named_ticker = bool(str(ticker or "").strip())

    if promotional and not action_changing:
        return {
            "publication_type": "promotion",
            "capture_policy": "suppress",
            "use_case": "none",
            "decision_usefulness": "low",
            "capture_reason": "Promotional, replay, or event content with no action-changing call.",
        }

    if monthly:
        return {
            "publication_type": "monthly_bible",
            "capture_policy": "monthly_baseline",
            "use_case": "allocation_baseline",
            "decision_usefulness": "medium",
            "capture_reason": "Monthly list or allocation context; use via Bible/prospect caches, not daily-call calibration.",
        }

    if weekly:
        if action_changing:
            return {
                "publication_type": "weekly_review",
                "capture_policy": "daily_call",
                "use_case": "risk_posture" if direction_l in WATCH_DIRECTIONS else "research_priority",
                "decision_usefulness": "medium",
                "capture_reason": "Weekly review changes risk posture, timing, sizing, or named-ticker research priority.",
            }
        return {
            "publication_type": "weekly_review",
            "capture_policy": "audit_only",
            "use_case": "context",
            "decision_usefulness": "low",
            "capture_reason": "Weekly recap/review without a portfolio action change.",
        }

    if technical:
        if specific or action_changing:
            return {
                "publication_type": "daily_technical",
                "capture_policy": "daily_call",
                "use_case": "technical_timing",
                "decision_usefulness": "high" if specific else "medium",
                "capture_reason": "Technical/timing item with levels, invalidation, or clear setup language.",
            }
        return {
            "publication_type": "daily_technical",
            "capture_policy": "audit_only",
            "use_case": "technical_context",
            "decision_usefulness": "low",
            "capture_reason": "Soft technical context without levels, timing, or setup change.",
        }

    if crypto:
        if action_changing or has_named_ticker:
            return {
                "publication_type": "crypto_strategy",
                "capture_policy": "daily_call" if action_changing else "audit_only",
                "use_case": "crypto_sleeve",
                "decision_usefulness": "medium" if action_changing else "low",
                "capture_reason": (
                    "Crypto or crypto-exposed equity context; act only inside the crypto sleeve/risk gate."
                ),
            }
        return {
            "publication_type": "crypto_strategy",
            "capture_policy": "audit_only",
            "use_case": "crypto_context",
            "decision_usefulness": "low",
            "capture_reason": "Crypto context without a posture change.",
        }

    if macro:
        if action_changing:
            return {
                "publication_type": "macro_update",
                "capture_policy": "daily_call",
                "use_case": "risk_posture",
                "decision_usefulness": "medium",
                "capture_reason": "Macro item changes risk posture, sizing, hedge, sector rotation, or a named-ticker gate.",
            }
        return {
            "publication_type": "macro_update",
            "capture_policy": "audit_only",
            "use_case": "macro_context",
            "decision_usefulness": "low",
            "capture_reason": "Macro backdrop only; keep as context unless it changes posture or a gate.",
        }

    if action_changing:
        return {
            "publication_type": "general_research",
            "capture_policy": "daily_call",
            "use_case": "research_priority",
            "decision_usefulness": "medium",
            "capture_reason": "General Fundstrat item contains a named action, timing, sizing, or risk cue.",
        }

    return {
        "publication_type": "general_context",
        "capture_policy": "audit_only",
        "use_case": "context",
        "decision_usefulness": "low",
        "capture_reason": "No ticker-level or portfolio-posture change detected.",
    }


def classify_fundstrat_lane(
    *,
    author: str = "",
    text: str = "",
    ticker: str = "",
    subject: str = "",
    entry: Any = None,
    stop: Any = None,
    target: Any = None,
    window: Any = None,
) -> dict[str, Any]:
    """Return lane/usefulness metadata for a Fundstrat-derived observation."""
    publication = classify_fundstrat_publication(
        author=author,
        text=text,
        ticker=ticker,
        subject=subject,
        entry=entry,
        stop=stop,
        target=target,
        window=window,
    )
    author_l = _blob(author)
    body = _blob(author, text, ticker, subject)
    ticker_l = str(ticker or subject or "").strip().lower()

    if "newton" in author_l or "mark newton" in body:
        specific = _has_specificity(body, entry=entry, stop=stop, target=target, window=window)
        trust_weight = 0.70 if specific else 0.58
        return {
            "fundstrat_lane": "technical",
            "source_domain": "technical_timing",
            "author_role": "Mark Newton technical/timing view",
            "source_weight_note": (
                "Technical/timing evidence with specific levels or timing; use for entry timing, not thesis by itself."
                if specific else
                "Technical/timing context only; lower weight until it gives specific levels, timing, or a clear setup."
            ),
            "confidence_policy": (
                "Use at normal Fundstrat weight only when the setup is specific/confident; otherwise treat as context."
            ),
            "trust_weight": trust_weight,
            **publication,
        }

    if "lee" in author_l or "tom lee" in body:
        return {
            "fundstrat_lane": "macro",
            "source_domain": "macro_strategy",
            "author_role": "Tom Lee macro/strategy view",
            "source_weight_note": (
                "Macro baseline from Fundstrat; useful for risk posture and capital timing, but confirm action with current tape and portfolio fit."
            ),
            "confidence_policy": "Use as the Fundstrat macro baseline; do not turn into a trade without current validation.",
            "trust_weight": 0.70,
            **publication,
        }

    if "farrell" in author_l or "sean farrell" in body or ticker_l in CRYPTO_TERMS or any(term in body for term in CRYPTO_TERMS):
        return {
            "fundstrat_lane": "crypto",
            "source_domain": "crypto_strategy",
            "author_role": "Fundstrat crypto analysis",
            "source_weight_note": (
                "Crypto-specific context; useful for crypto sleeve and crypto-exposed equities, not broad macro confirmation by itself."
            ),
            "confidence_policy": "Keep crypto analysis scoped to crypto/crypto-exposed positions and validate against live risk.",
            "trust_weight": 0.65,
            **publication,
        }

    return {
        "fundstrat_lane": "general",
        "source_domain": "fundstrat_general",
        "author_role": "Fundstrat general research",
        "source_weight_note": "Fundstrat context; classify manually if it becomes action-relevant.",
        "confidence_policy": "Treat as context until lane, catalyst, and current validation are clear.",
        "trust_weight": 0.65,
        **publication,
    }
