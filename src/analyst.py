"""Conviction Engine — Layer 3 Analyst: MECHANICAL reads (A2a + A2b).

The deterministic, Python-rule reads (tested by assert + boundaries).
A2a (config-consuming):
  ⑤ rotation_read       — classify each rotation card into a sleeve badge + note
  ⑥ macro_read          — the macro line + regime + fired alerts + implications
  ⑨ staleness_read      — the "sourced: …" stamp + per-source stale/baseline flags
A2b (the rest of the mechanical set):
  ④ type_read           — per held name: type · lock · why · break + untracked list
  ⑧ hero_needs_you_read — headline counts: hero vs needs_you (pure aggregator)
  ⑩ weight_read         — per subject: independent streams / voices / max trust
                          (echo-chamber guard that feeds the A3 judgment reads)

Boundary (Sources vs Analyst — RECORD): these are mechanical (fixed calcs /
config lookups / aggregation). The JUDGMENT reads (① conviction, ② conviction-
direction, ③ net-read, ⑦ fresh-signals) are A3. In particular ⑤ classifies a lag
but does NOT interpret it catch-up-vs-broken, and ④ states the configured type but
does NOT grade conviction — those are the A3 judgment reads.
"""
from __future__ import annotations

from datetime import date

from uw_price import classify_rotation
from analyst_config import ROTATION_BANDS, MACRO_ALERTS, is_stale, theses_by_ticker
from sources import DEFAULT_CADENCE


# =========================================================================== #
# ⑤ Rotation classification
# =========================================================================== #
def _rotation_note(label: str, rel_3m) -> str:
    if rel_3m is None:
        return "no data"
    return f"{label} {rel_3m:+.0%}/3M vs mkt"


def rotation_read(cards, bands: dict = ROTATION_BANDS) -> dict:
    """Classify each rotation card into a sleeve badge.

    Reuses the plug's `classify_rotation` + the config bands (single source of
    truth — the Analyst tunes the bands, the plug shares them). Non-rotation
    cards are ignored. Catch-up-vs-broken interpretation is NOT here (③ net-read).
    """
    sleeves = []
    for c in cards:
        if getattr(c, "kind", None) != "rotation":
            continue
        d = c.data or {}
        rel_1m, rel_3m = d.get("rel_1m"), d.get("rel_3m")
        label = classify_rotation(rel_1m, rel_3m, bands)
        sleeves.append({
            "subject": c.subject,
            "label": label,
            "rel_1m": rel_1m,
            "rel_3m": rel_3m,
            "abs_3m": d.get("abs_3m"),
            "rel_3m_vs_smh": d.get("rel_3m_vs_smh"),
            "note": _rotation_note(label, rel_3m),
        })

    by_label: dict = {}
    for s in sleeves:
        by_label.setdefault(s["label"], []).append(s["subject"])

    return {"sleeves": sleeves, "by_label": by_label}


# =========================================================================== #
# ⑥ Macro pulse
# =========================================================================== #
# Preferred display order for the macro line; present cards are appended in order.
MACRO_LINE_ORDER = ["10Y", "2s10s", "10s30s", "DXY", "VIX", "MOVE", "30Y", "2Y"]


def _macro_regime(by_subject: dict) -> dict:
    def val(s):
        c = by_subject.get(s)
        return (c.data or {}).get("value") if c else None

    def chg(s):
        c = by_subject.get(s)
        return (c.data or {}).get("chg_5d") if c else None

    # duration by 10Y 5d move (bp); vol by VIX/MOVE level; dollar by DXY 5d move (pt)
    duration = "flat"
    ten = chg("10Y")
    if ten is not None:
        duration = "rising" if ten > 2 else "falling" if ten < -2 else "flat"

    vix, move = val("VIX"), val("MOVE")
    vol = "elevated" if ((vix is not None and vix >= 20)
                         or (move is not None and move >= 110)) else "calm"

    dxy = chg("DXY")
    dollar = "neutral"
    if dxy is not None:
        dollar = "strong" if dxy > 1 else "weak" if dxy < -1 else "neutral"

    return {
        "duration": duration, "vol": vol, "dollar": dollar,
        "label": f"duration_{duration} · vol_{vol} · dollar_{dollar}",
    }


def _macro_alerts(by_subject: dict, alerts: dict) -> list:
    fired = []
    for key, spec in alerts.items():
        c = by_subject.get(spec["subject"])
        if not c:
            continue
        d = c.data or {}
        v, chg, v5 = d.get("value"), d.get("chg_5d"), d.get("value_5d_ago")
        kind = spec["kind"]
        hit = False
        if kind == "level_above" and v is not None:
            hit = v > spec["threshold"]
        elif kind in ("abs_change_above", "abs_change_pct_above",
                      "abs_change_bp_above") and chg is not None:
            hit = abs(chg) > spec["threshold"]
        elif kind == "sign_cross" and v is not None and v5 is not None:
            hit = (v >= 0) != (v5 >= 0)
        if hit:
            fired.append({"alert": key, "subject": spec["subject"],
                          "note": spec["note"], "detail": c.content})
    return fired


def _macro_implications(regime: dict, alerts_fired: list) -> list:
    imp = []
    alert_subjects = {a["subject"] for a in alerts_fired}
    if regime["duration"] == "rising" or "10Y" in alert_subjects:
        imp.append("headwind: long-duration growth (NVDA/SMH/MAGS)")
    if regime["dollar"] == "weak":
        imp.append("tailwind: critical minerals (LEU/MP/UUUU)")
    if regime["dollar"] == "strong":
        imp.append("headwind: global exporters (NVDA China/AVGO) + minerals")
    if regime["vol"] == "elevated" or "MOVE" in alert_subjects:
        imp.append("upsize AI hedge (SMH puts)")
    if "2s10s" in alert_subjects:
        imp.append("curve signal: watch cyclicals/financials (XLF)")
    if "Real 10Y" in alert_subjects:
        imp.append("headwind: crypto (BMNR)")
    if imp:
        imp.append(
            "portfolio read: use macro as a sizing/timing gate, not a standalone trade; "
            "stage confirmed adds, avoid chasing, and re-check hedges if rates/vol keep moving"
        )
    else:
        imp.append(
            "portfolio read: no standalone macro action; keep rates/vol as a same-session "
            "check before adding beta, then collapse this lane if it does not change sizing, "
            "hedge, hold/add/trim, or research priority"
        )
    return imp


def macro_read(cards, alerts: dict = MACRO_ALERTS) -> dict:
    """Macro block: the one-line summary + regime + fired alerts + implications.

    Reuses each macro card's already-templated content for the line. Regime
    thresholds are coarse v1 defaults (tunable). Alerts evaluate the config
    MACRO_ALERTS against available cards; alerts for absent subjects don't fire.
    """
    by_subject = {c.subject: c for c in cards if getattr(c, "kind", None) == "macro"}

    ordered = [by_subject[s].content for s in MACRO_LINE_ORDER if s in by_subject]
    extras = [c.content for subj, c in by_subject.items() if subj not in MACRO_LINE_ORDER]
    line = " · ".join(ordered + extras)

    regime = _macro_regime(by_subject)
    alerts_fired = _macro_alerts(by_subject, alerts)
    implications = _macro_implications(regime, alerts_fired)

    return {"line": line, "regime": regime, "alerts": alerts_fired,
            "implications": implications}


# =========================================================================== #
# ⑨ Staleness stamp
# =========================================================================== #
def _parse_date(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def staleness_read(staleness: dict, as_of: str, cadence_map: dict | None = None) -> dict:
    """The "sourced: …" stamp + per-source flags.

    For each source: age = as_of − newest date; look up its cadence; a `static`
    source reads "(baseline)" and is NEVER stale; an over-budget source gets ⚠️.
    `cadence_map` defaults to the live source dial (injectable for tests).
    """
    cadence_map = cadence_map if cadence_map is not None else DEFAULT_CADENCE
    asof_d = _parse_date(as_of)

    entries, stale_flags = [], []
    for source, src_date in staleness.items():
        try:
            age = (asof_d - _parse_date(src_date)).days
        except (ValueError, TypeError):
            age = None
        cadence = cadence_map.get(source, "daily")
        stale = is_stale(age, cadence) if age is not None else False
        flag = "(baseline)" if cadence == "static" else ("⚠️" if stale else "")
        entries.append({"source": source, "date": src_date, "age_days": age,
                        "cadence": cadence, "stale": stale, "flag": flag})
        if stale:
            stale_flags.append(source)

    def _short(d):
        return d[5:10] if len(d) >= 10 else d   # MM-DD

    stamp = "sourced: " + " · ".join(
        f"{e['source']} {_short(e['date'])}" + (f" {e['flag']}" if e["flag"] else "")
        for e in entries
    )
    return {"stamp": stamp, "entries": entries, "stale": stale_flags}


# =========================================================================== #
# ④ Type / lock / why / break  (per held name)
# =========================================================================== #
# Field names are PROVISIONAL per the A2b spec. The cockpit (K1) consumes
# ty / lock / dr / be — reconcile at the cockpit stage (type->ty, why->dr,
# break->be). Kept descriptive here so the read is self-explaining.
NO_BREAK = "—"


def _why(thesis: dict) -> str:
    """Plain 'why we hold it': backing source + factor tags."""
    source = thesis.get("source") or "—"
    tags = thesis.get("factor_tags") or []
    tag_str = ", ".join(tags)
    return f"{source} · {tag_str}" if tag_str else source


def type_read(position_cards, theses) -> dict:
    """Per held name: type (tier · lane), lock (🔒 if Generational), why
    (source + factor tags), break (thesis-break condition or '—'); plus the
    untracked names (held but no thesis row → Tier-C default).

    Mechanical: pure lookup/assembly from theses.json + the position cards.
    Conviction GRADING (Strong/Promising/…) is the ① judgment read (A3); this
    read only states the configured type, it never grades. One entry per NAME —
    the portfolio plug emits a card per account, so same-ticker cards collapse.
    """
    by_ticker = theses_by_ticker(theses)

    tracked, untracked, seen = [], [], set()
    for c in position_cards:
        if getattr(c, "kind", None) != "position":
            continue
        ticker = c.subject
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)

        th = by_ticker.get(ticker)
        if th is None:
            untracked.append({
                "ticker": ticker,
                "type": "Tier-C (default)",
                "lock": "",
                "why": "no documented thesis",
                "break": NO_BREAK,
            })
            continue

        lane, tier = th.get("lane"), th.get("tier")
        type_str = " · ".join(x for x in (tier, lane) if x) or "—"
        tracked.append({
            "ticker": ticker,
            "type": type_str,
            "lock": "🔒" if lane == "Generational" else "",
            "why": _why(th),
            "break": th.get("break") or NO_BREAK,
        })

    return {
        "tracked": tracked,
        "untracked": untracked,
        "tracked_count": len(tracked),
        "untracked_count": len(untracked),
    }


# =========================================================================== #
# ⑧ Hero / needs-you  (the headline aggregator)
# =========================================================================== #
CRITICAL_SOURCES = ("portfolio", "uw_price")


def hero_needs_you_read(rotation, macro, staleness, type_reads,
                        fresh_signals=None, monitor_reentry=None,
                        red_gates=None, catalyst_imminent=None,
                        critical_sources=CRITICAL_SOURCES) -> dict:
    """Aggregate the mechanical reads into the cockpit headline.

    needs_you = stale CRITICAL sources + firing macro alerts + MONITOR re-entry
    candidates + any RED gate + near-term catalysts on held names (+ act-now
    fresh signals once A3 supplies them).
    hero      = the clean, tracked, intact-thesis names not flagged elsewhere
    (plus the LEADING sleeves as positive context).

    Pure aggregator — every input is another read's output. fresh_signals /
    monitor_reentry / red_gates / catalyst_imminent default empty so A2b can call
    with just the four mechanical reads, and the caller can enrich without
    changing the signature. catalyst_imminent items are pre-formed needs_you
    dicts (reason "catalyst_imminent") from analyst_judgment.catalyst_needs_you.
    """
    fresh_signals = fresh_signals or []
    monitor_reentry = monitor_reentry or []
    red_gates = red_gates or []
    catalyst_imminent = catalyst_imminent or []

    items = []
    for src in (staleness.get("stale") or []):
        if src in critical_sources:
            items.append({"reason": "stale_critical", "detail": src})
    for a in (macro.get("alerts") or []):
        items.append({"reason": "macro_alert",
                      "detail": a.get("subject"), "note": a.get("note")})
    for t in monitor_reentry:
        items.append({"reason": "monitor_reentry", "detail": t})
    for g in red_gates:
        items.append({"reason": "red_gate", "detail": g})
    for s in fresh_signals:
        if isinstance(s, dict) and s.get("urgency") == "act":
            items.append({"reason": "fresh_act",
                          "detail": s.get("ticker") or s.get("subject")})
    for c in catalyst_imminent:
        items.append(c)

    flagged = {i["detail"] for i in items}
    hero_names = [
        e["ticker"] for e in (type_reads.get("tracked") or [])
        if e.get("break") in (NO_BREAK, "", None) and e["ticker"] not in flagged
    ]
    leading_sleeves = (rotation.get("by_label") or {}).get("LEADING", [])

    return {
        "hero": {"count": len(hero_names), "names": hero_names,
                 "leading_sleeves": leading_sleeves},
        "needs_you": {"count": len(items), "items": items},
    }


# =========================================================================== #
# ⑩ Trust + independence weighting  (echo-chamber guard; feeds A3 ①–③)
# =========================================================================== #
def weight_read(cards) -> dict:
    """Per subject, collapse same-independence-group cards to ONE voice.

    independent_streams = count of DISTINCT independence_group (the two Fundstrat
    plugs on one name = 1 stream, not 2 — the echo-chamber guard). voices = the
    highest-trust card kept per group. max_trust = best trust across the subject.
    Feeds the ①–③ judgment reads in A3 (A3 passes the endorsement cards per name).
    Subject-less cards are skipped.
    """
    by_subject: dict = {}
    for c in cards:
        subject = getattr(c, "subject", None)
        if not subject:
            continue
        by_subject.setdefault(subject, []).append(c)

    out: dict = {}
    for subject, subj_cards in by_subject.items():
        best_per_group: dict = {}
        for c in subj_cards:
            grp = getattr(c, "independence_group", None)
            trust = getattr(c, "trust_weight", 0.0) or 0.0
            cur = best_per_group.get(grp)
            if cur is None or trust > (getattr(cur, "trust_weight", 0.0) or 0.0):
                best_per_group[grp] = c

        voices = [{
            "group": grp,
            "source": getattr(c, "source", None),
            "trust": getattr(c, "trust_weight", None),
            "content": getattr(c, "content", None),
        } for grp, c in best_per_group.items()]

        max_trust = max((getattr(c, "trust_weight", 0.0) or 0.0)
                        for c in subj_cards)

        out[subject] = {
            "independent_streams": len(best_per_group),
            "voices": voices,
            "max_trust": max_trust,
        }
    return out
