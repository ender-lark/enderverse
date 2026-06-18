"""Invariant guards for the decision-led RENDER redesign of TODAY—DECIDE.

The render surface is NOT golden-covered, so these are the dedicated invariants the
redesign must never regress (RENDER-REDESIGN, 2026-06-18):

* the hero holds a real funded MOVE in trade-plan format, or an explicit honest
  starvation line — never a bare count/banner;
* no disposition / ask / tunable control ships that does not persist;
* the funding line is never silently dropped when ``funded_by`` is non-empty;
* a LOW/grey conviction stamp never headlines a six-figure move;
* a CONFLICTED card (landed F1) renders RESOLVE/RECHECK with NO one-tap ACT and is
  excluded from the hero + good-price tiers;
* the good-price tier is rail-free and labels ``impact`` a discount-priority score,
  never a buy signal; the sell-gate doctrine note rides meaningful positions;
* sizing transparency degrades honestly when F2 is absent (no fabricated dials) and
  becomes editable when ``sizing_tunables.json`` is present;
* the disposition spine read-back flips the honesty line off "none logged yet".
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import today_decide as td
import test_jsx_parity as P
import disposition_log as dl


def _html(payload: dict) -> str:
    return td.render_today_decide_html(payload)


def _verbs_for(html: str, cid: str) -> set[str]:
    return {
        m.group(1)
        for m in re.finditer(
            r'data-card="' + re.escape(cid) + r'"[^>]*data-verb="([^"]+)"', html
        )
    }


# ---------------------------------------------------------------------------
# Hero: a real move, or honest starvation — never a count/banner
# ---------------------------------------------------------------------------
def test_hero_leads_with_a_real_move_or_honest_starvation():
    html = _html(P._build_payload())
    assert "The move" in html  # the lead is a decision, not a "N ready cards" count
    # a real funded move leads (trade-plan header) OR the honest-starvation line shows
    assert ("funded move" in html and "trade plan" in html) or "No high-conviction" in html
    # the move surface is not a confident grid of zeros
    assert "0 ready cards" not in html and "N ready cards" not in html


# ---------------------------------------------------------------------------
# Every control persists (no build-without-wire)
# ---------------------------------------------------------------------------
def test_gated_move_reads_as_good_with_a_final_check_not_cryptic_stage():
    # the operator's fix: a good-but-gated move must read as a good thing to do with
    # one clearly-recommended final check — never the cryptic "STAGE".
    html = _html(P._build_payload())
    assert ">DO IT" in html                       # plain, positive primary label
    assert ">STAGE<" not in html                  # cryptic STAGE button retired
    low = html.lower()
    assert "final check" in low                   # the recommended check is spelled out
    assert ("looks like a good move" in low) or ("good to go" in low)


def test_no_disposition_or_ask_or_tunable_control_without_persistence():
    html = _html(P._build_payload())
    js = td._JS
    # disposition rail taps persist (localStorage) + automatic spine write + are wired
    assert "tdRail(this)" in html
    assert "localStorage.setItem(tdDispKey" in js
    assert "fetch('/td/disposition'" in js
    assert "fetch('/td/note'" in js               # notes write automatically too
    # per-card ask/notes persist + emit a chat-ready [CARD <id>] tag
    assert "localStorage.setItem(tdNotesKey" in js
    assert "[CARD " in js
    assert "tdAskSave(this)" in html and "tdAskCopy(this)" in html
    # sizing dials persist + live-recompute client-side
    assert "localStorage.setItem(tdTunKey" in js
    assert "function tdRecompute" in js
    # the page re-renders persisted state on load
    assert "function tdInit" in js


# ---------------------------------------------------------------------------
# Funding line never silently dropped
# ---------------------------------------------------------------------------
def test_funding_line_present_and_never_silently_dropped():
    html = _html(P._build_payload())
    # the hero header always renders a "Funded by" row for a move
    assert "Funded by" in html
    # empty funding is shown explicitly, never dropped
    assert td._render_funded_by({"funded_by": []}) == '<div class="td-v">Funding: not yet assigned</div>'
    legs = td._render_funded_by({"funded_by": [
        {"ticker": "IVES", "notional_usd": 67911.77},
        {"ticker": "GRNY", "notional_usd": 81562.86},
    ]})
    assert "IVES $67,912" in legs and "GRNY $81,563" in legs
    assert "dollar-for-dollar" in legs  # the legs sum, shown


# ---------------------------------------------------------------------------
# Loudness tracks conviction: a LOW stamp never headlines a six-figure move
# ---------------------------------------------------------------------------
def test_low_conviction_stamp_never_headlines_a_large_move():
    html = _html(P._build_payload())
    # isolate the loud headline line of the hero
    headline = html.split('class="td-hl"', 1)[1].split("</div>", 1)[0]
    assert "Conviction 1/5 LOW" not in headline  # conviction is NOT the headline
    assert "GOOGL" in headline                    # the sized move IS the headline
    # the conviction read still exists in the HTML (parity), just demoted off the headline
    assert "Conviction 1/5 LOW" in html


# ---------------------------------------------------------------------------
# F1 CONFLICTED preserved: RESOLVE/RECHECK, never ACT, excluded from tiers
# ---------------------------------------------------------------------------
def test_conflicted_card_resolve_no_act_and_excluded_from_tiers():
    payload = P._build_conflicted_payload()
    html = _html(payload)
    cid = next(
        c["card_id"] for c in payload["cards"] + payload["backlog"]
        if (c.get("conviction_display") or {}).get("band") == "CONFLICTED"
    )
    assert "#fb923c" in html                       # loud orange band
    assert "Conviction 3/5 CONFLICTED" in html     # literal posture line
    assert "Resolve signal before" in html         # resolve-direction face
    verbs = _verbs_for(html, cid)
    assert "ACT" not in verbs and (verbs & {"RECHECK", "CANDIDATE"})  # non-ACT rail
    # excluded from the good-price tier
    gpt = payload.get("good_price_tier") or {}
    gp = [r["ticker"] for r in (gpt.get("higher") or []) + (gpt.get("deep_visible") or []) + (gpt.get("deep_more") or [])]
    assert cid.split("-")[0] not in gp
    # excluded from the hero: no trade-plan header is attached to the conflicted card
    before = html.split(cid, 1)[0]
    assert "funded move" not in before[-1500:]


# ---------------------------------------------------------------------------
# Good-price tier: rail-free, impact is a look score (never a buy signal)
# ---------------------------------------------------------------------------
def _good_price_payload():
    return {"good_price_tier": {
        "freshness": "fresh", "packet_as_of": "2026-06-17",
        "higher": [{
            "ticker": "FN", "tier": "higher", "impact": 29, "pct_below_high": -21.5,
            "price": 588, "fifty_two_week_high": 748.89, "high_date": "2026-05-14",
            "exposure_usd": 8050, "exposure_pct": 0.42, "disconfirmation": "optical flow must beat the funded packet",
            "research_status": "", "source_tags": ["Fundstrat top-list"], "summary": "",
            "trusted": True, "monitor": False,
        }],
        "deep_visible": [{
            "ticker": "LEU", "tier": "deep", "impact": 63, "pct_below_high": -64.4,
            "price": 165, "fifty_two_week_high": 464.25, "high_date": "2025-10-16",
            "exposure_usd": 99621, "exposure_pct": 5.18, "disconfirmation": "uranium/HALEU flow + policy",
            "research_status": "", "source_tags": [], "summary": "", "trusted": False, "monitor": False,
            "sellgate_note": "already a meaningful position — hold/monitor; do not sell a live thesis into weakness",
        }],
        "deep_more": [], "deep_more_tickers": ["AVAV", "KTOS"], "screen_count": 107,
    }}


def test_good_price_tier_is_rail_free_and_impact_not_a_buy_signal():
    seg = td._render_good_price_tier(_good_price_payload())
    assert "td-rail" not in seg                 # never one tap from a buy
    assert "data-verb=" not in seg              # no disposition verbs in this tier
    assert "discount-priority" in seg           # impact labeled honestly
    assert "not a buy signal" in seg            # spelled out
    assert "do not sell a live thesis into weakness" in seg  # sell-gate doctrine
    assert "107-name discount screen" in seg    # the unconsumed screen is surfaced, not hidden
    # no shorthand: spelled-out labels, not "exp"
    assert "you own" in seg and "off 52w high" in seg and "per share" in seg


# ---------------------------------------------------------------------------
# Sizing transparency: honest degrade without F2, editable when present
# ---------------------------------------------------------------------------
def _sizing_card():
    return {
        "card_id": "X-ADD-2026-06-18", "ticker": "X",
        "sizing": {"source": "caps", "suggested_usd": 0.0, "heat": "cool", "cap_basis": "tier band"},
        "conviction_display": {"x5": 1},
    }


def test_sizing_transparency_degrades_honestly_without_f2():
    s = td._render_sizing_transparency(_sizing_card(), {})
    assert "are not present in this build" in s     # honest, F2 absent fallback
    assert 'oninput="tdDial' not in s               # NO fabricated dials
    assert "engine suggested size" in s             # the real current sizing is shown
    assert "no hidden caps" in s


def test_sizing_transparency_renders_editable_dials_when_present():
    s = td._render_sizing_transparency(
        _sizing_card(),
        {"base_size_usd": 10000, "conviction_size_slope": 5000, "per_name_soft_max_usd": 0},
    )
    assert 'oninput="tdDial(this)"' in s             # editable dials
    assert 'id="tdsize-X-ADD-2026-06-18"' in s       # live-recompute target
    assert 'data-formula' in s                       # client mirror of the formula
    assert "base size" in s and "conviction size slope" in s  # every tunable named, no shorthand


# ---------------------------------------------------------------------------
# Disposition spine read-back: honesty line flips off "none logged yet"
# ---------------------------------------------------------------------------
def _payload_with_dispositions(path):
    return td.build_today_decide_payload(
        feed=P._feed(), weights=P.W, goal=P.G, insights_payload=P._insights(),
        accounts=P._accounts(), gates=[P._gate()],
        congruence_result={"status": "ok", "rows": []}, today=P.TODAY,
        dispositions_path=path,
    )


def test_disposition_spine_readback_updates_honesty_line(tmp_path):
    pth = tmp_path / "dispositions.jsonl"
    before = _payload_with_dispositions(pth)
    assert before["honesty"]["dispositions"].startswith("none logged")
    assert "none logged yet" in td.render_today_decide_html(before)

    first = before["cards"][0]
    dl.append_disposition(P.TODAY, first["card_id"], first["ticker"], "PASS", reason="pilot", path=pth)

    after = _payload_with_dispositions(pth)
    assert not after["honesty"].get("dispositions", "").startswith("none logged")
    html = td.render_today_decide_html(after)
    assert "none logged yet" not in html
    assert "last disposition: PASS" in html
