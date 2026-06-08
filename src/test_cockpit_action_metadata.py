from pathlib import Path


def test_jsx_action_cards_render_synthesis_change_and_capital_priority():
    text = Path(__file__).with_name("conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "synthesisChanges:a.synthesis_changes||\"\"" in text
    assert "capitalPriorityScore:(typeof a.capital_priority_score===\"number\"" in text
    assert "changes: {a.synthesisChanges}" in text
    assert "priority: {a.capitalPriorityScore}" in text
    assert "capitalEfficiency.priority_reason" in text
    assert "capitalEfficiency.do_nothing_risk" in text


def test_jsx_market_open_packet_surfaces_action_validity_metadata():
    text = Path(__file__).with_name("conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "r.capital_priority_score" in text
    assert "r.freshness_label" in text
    assert "r.key_assumptions" in text
    assert "r.capital_priority_reason" in text
    assert "r.do_nothing_risk" in text
    assert "r.invalidates" in text
