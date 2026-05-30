"""Conviction Engine — Layer 3 Analyst: MECHANICAL reads (A2a).

The deterministic, Python-rule reads (tested by assert + boundaries). A2a covers
the three that consume the A1 config directly:
  ⑤ rotation_read   — classify each rotation card into a sleeve badge + note
  ⑥ macro_read      — the macro line + regime + fired alerts + implications
  ⑨ staleness_read  — the "sourced: …" stamp + per-source stale/baseline flags

Boundary (Sources vs Analyst — RECORD): these are mechanical (fixed calcs /
config lookups). The JUDGMENT reads (conviction, net-read, fresh-signals) are
A2b/A3. In particular, ⑤ classifies rotation but does NOT interpret a lag as
catch-up-vs-broken — that's the ③ net-read.
"""
from __future__ import annotations

from datetime import date

from uw_price import classify_rotation
from analyst_config import ROTATION_BANDS, MACRO_ALERTS, is_stale
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
