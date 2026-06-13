import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import disconfirmation_registry as dr


# --------------------------------------------------------------------------- fixtures

def _theses():
    """Mixed stance + coverage fixture: active/monitor x missing/draft/confirmed."""
    return [
        {"ticker": "AAA", "id": "thesis_aaa", "tier": "T2", "lane": "Speed", "stance": "ACTIVE"},
        {"ticker": "BBB", "id": "thesis_bbb", "tier": "T3", "lane": "BuyAndHold", "stance": "ACTIVE"},
        {"ticker": "CCC", "id": "thesis_ccc", "tier": "T2", "lane": "Speed", "stance": "ACTIVE"},
        {"ticker": "DDD", "id": "thesis_ddd", "tier": "T1", "lane": "Generational", "stance": "MONITOR"},
        {"ticker": "EEE", "id": "thesis_eee", "tier": "T3", "lane": "Speed", "stance": "MONITOR"},
    ]


def _registry():
    """AAA = draft, CCC = confirmed, DDD = draft (monitor). BBB/EEE have no entry."""
    return {
        "schema_version": 1,
        "last_updated": "2026-06-13",
        "entries": {
            "AAA": {
                "ticker": "AAA",
                "thesis_id": "thesis_aaa",
                "fastest_way_wrong": "AAA story breaks if demand stalls.",
                "invalidating_evidence": "Two down quarters of unit volume.",
                "flip_trigger": "Volume down two quarters in a row.",
                "last_reviewed": "2026-06-13",
                "status": dr.DRAFT_STATUS,
            },
            "CCC": {
                "ticker": "CCC",
                "thesis_id": "thesis_ccc",
                "fastest_way_wrong": "CCC margin compresses.",
                "invalidating_evidence": "Gross margin below 30% for a quarter.",
                "flip_trigger": "GM prints below 30%.",
                "last_reviewed": "2026-06-13",
                "status": "CONFIRMED",
            },
            "DDD": {
                "ticker": "DDD",
                "thesis_id": "thesis_ddd",
                "fastest_way_wrong": "DDD policy support lapses.",
                "invalidating_evidence": "Key contract cancelled.",
                "flip_trigger": "Contract non-renewal.",
                "last_reviewed": "2026-06-13",
                "status": dr.DRAFT_STATUS,
            },
        },
    }


# --------------------------------------------------------------------------- schema validation

def test_real_registry_validates_and_seeds_marquee_names():
    registry = dr.load_registry()  # raises if the shipped file is malformed
    entries = registry["entries"]
    assert entries, "registry should ship with seeded entries"
    # Marquee active names called out in the task brief.
    assert "NVDA" in entries
    assert "BMNR" in entries
    # Every shipped seed is a DRAFT starter (Claude does not assert kill-switches as fact).
    for ticker, entry in entries.items():
        assert not dr.is_confirmed(entry), f"{ticker} should ship as DRAFT, not CONFIRMED"


def test_validate_registry_accepts_fixture():
    dr.validate_registry(_registry())  # should not raise


@pytest.mark.parametrize("mutate, needle", [
    (lambda r: [], "must be a JSON object"),
    (lambda r: r.pop("entries"), "'entries'"),
    (lambda r: r["entries"].__setitem__("aaa", r["entries"]["AAA"]), "upper-case"),
    (lambda r: r["entries"]["AAA"].pop("flip_trigger"), "flip_trigger"),
    (lambda r: r["entries"]["AAA"].__setitem__("invalidating_evidence", "  "), "invalidating_evidence"),
    (lambda r: r["entries"]["AAA"].__setitem__("status", 5), "status"),
    (lambda r: r["entries"]["AAA"].__setitem__("ticker", "ZZZ"), "mismatched"),
])
def test_validate_registry_rejects_bad_schema(mutate, needle):
    bad = _registry()
    result = mutate(bad)
    if isinstance(result, list):  # the "root is not a dict" case
        bad = result
    with pytest.raises(dr.RegistryValidationError) as exc:
        dr.validate_registry(bad)
    assert needle in str(exc.value)


# --------------------------------------------------------------------------- lookups

def test_get_disconfirmation_is_case_insensitive_and_safe():
    reg = _registry()
    assert dr.get_disconfirmation("AAA", reg)["thesis_id"] == "thesis_aaa"
    assert dr.get_disconfirmation("aaa", reg)["thesis_id"] == "thesis_aaa"
    assert dr.get_disconfirmation("ZZZ", reg) is None
    assert dr.get_disconfirmation("", reg) is None


def test_is_confirmed_only_for_confirmed_status():
    assert dr.is_confirmed({"status": "CONFIRMED"}) is True
    assert dr.is_confirmed({"status": "confirmed 2026-06-13 by operator"}) is True
    assert dr.is_confirmed({"status": dr.DRAFT_STATUS}) is False
    assert dr.is_confirmed({}) is False
    assert dr.is_confirmed(None) is False


def test_coverage_for_classifies_each_state():
    reg = _registry()
    by_ticker = {t["ticker"]: t for t in _theses()}
    assert dr.coverage_for(by_ticker["AAA"], reg) == "DRAFT"
    assert dr.coverage_for(by_ticker["BBB"], reg) == "MISSING"
    assert dr.coverage_for(by_ticker["CCC"], reg) == "CONFIRMED"
    assert dr.coverage_for(by_ticker["DDD"], reg) == "DRAFT"


# --------------------------------------------------------------------------- missing helper

def test_missing_disconfirmation_reports_draft_and_missing_but_not_confirmed():
    reg = _registry()
    missing = {t["ticker"] for t in dr.missing_disconfirmation(_theses(), reg)}
    assert "AAA" in missing      # active + DRAFT  -> gap
    assert "BBB" in missing      # active + MISSING -> gap
    assert "CCC" not in missing  # active + CONFIRMED -> NOT a gap
    assert "DDD" not in missing  # DDD is MONITOR (helper is active-only)
    assert "EEE" not in missing  # EEE is MONITOR


def test_missing_disconfirmation_on_real_data_flags_draft_nvda():
    # NVDA ships ACTIVE + DRAFT, so it must surface as a gap on real data.
    theses = dr.load_theses()
    missing = {t["ticker"] for t in dr.missing_disconfirmation(theses)}
    assert "NVDA" in missing
    assert missing, "no active thesis has a confirmed kill-switch yet, so this can't be empty"


# --------------------------------------------------------------------------- gaps report

def test_render_gaps_md_lists_draft_and_missing():
    md = dr.render_gaps_md(_theses(), _registry(), write=False)
    assert "cannot currently be proven wrong" in md
    assert "Coverage: 1/5 theses have a confirmed kill-switch" in md
    # DRAFT entries are surfaced in full as gaps...
    assert "AAA story breaks if demand stalls." in md
    assert "DDD policy support lapses." in md
    # ...missing active names are called out...
    assert "BBB" in md
    # ...and the confirmed one is not reported as a gap (only in the table).
    assert "CCC margin compresses." not in md
    assert "| CCC | T2 | Speed | ACTIVE | CONFIRMED |" in md


def test_render_gaps_md_writes_file(tmp_path):
    out = tmp_path / "disconfirmation_gaps.md"
    md = dr.render_gaps_md(_theses(), _registry(), out_path=out, write=True)
    assert out.exists()
    assert out.read_text(encoding="utf-8") == md
    assert md.startswith("# Disconfirmation Gaps")


def test_render_gaps_md_handles_all_confirmed():
    reg = _registry()
    reg["entries"]["AAA"]["status"] = "CONFIRMED"
    theses = [t for t in _theses() if t["ticker"] in {"AAA", "CCC"}]
    md = dr.render_gaps_md(theses, reg, write=False)
    assert "Coverage: 2/2 theses have a confirmed kill-switch" in md
    assert "(none — every thesis has at least a draft entry)" in md


# --------------------------------------------------------------------------- card-wiring helper

def test_card_disconfirmation_matches_renderer_contract():
    reg = _registry()
    card = dr.card_disconfirmation("AAA", reg)
    # Keys the cockpit_html_gen disconfirmation block already consumes:
    assert set(["summary", "invalidates_if", "confirm_before_acting"]).issubset(card)
    assert card["summary"] == reg["entries"]["AAA"]["fastest_way_wrong"]
    assert card["invalidates_if"] == [reg["entries"]["AAA"]["invalidating_evidence"]]
    # DRAFT -> not confirmed, and a confirm-before-acting note is present.
    assert card["confirmed"] is False
    assert card["confirm_before_acting"]
    assert "DRAFT" in card["confirm_before_acting"][0]


def test_card_disconfirmation_confirmed_has_no_draft_note():
    card = dr.card_disconfirmation("CCC", _registry())
    assert card["confirmed"] is True
    assert card["confirm_before_acting"] == []


def test_card_disconfirmation_missing_returns_none():
    assert dr.card_disconfirmation("ZZZ", _registry()) is None


def test_real_card_disconfirmation_is_one_line_ready():
    # End-to-end against shipped data: NVDA seed yields a render-ready payload.
    card = dr.card_disconfirmation("nvda")
    assert card is not None
    assert card["summary"]
    assert card["invalidates_if"] and card["invalidates_if"][0]
    assert card["confirmed"] is False
