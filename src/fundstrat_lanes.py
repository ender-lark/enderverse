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

TECHNICAL_TERMS = {
    "breakout", "breakdown", "support", "resistance", "trend", "reversal",
    "bounce", "corrective", "pullback", "above", "below", "close", "holds",
    "hold", "target", "stop", "entry",
}


def _blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).strip().lower()


def _has_price_level(text: str) -> bool:
    return bool(re.search(r"(?:\$|near\s+|toward\s+|above\s+|below\s+)?\b\d{2,5}(?:\.\d+)?\b", text))


def _has_specificity(text: str, *, entry: Any = None, stop: Any = None, target: Any = None, window: Any = None) -> bool:
    if entry is not None or stop is not None or target is not None or window:
        return True
    if _has_price_level(text) and any(term in text for term in TECHNICAL_TERMS):
        return True
    return any(term in text for term in {"entry", "stop", "target", "if ", "weekly close", "daily close"})


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
        }

    return {
        "fundstrat_lane": "general",
        "source_domain": "fundstrat_general",
        "author_role": "Fundstrat general research",
        "source_weight_note": "Fundstrat context; classify manually if it becomes action-relevant.",
        "confidence_policy": "Treat as context until lane, catalyst, and current validation are clear.",
        "trust_weight": 0.65,
    }
