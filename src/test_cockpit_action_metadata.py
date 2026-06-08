from pathlib import Path


def test_jsx_action_cards_render_synthesis_change_and_capital_priority():
    text = Path(__file__).with_name("conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "synthesisChanges:a.synthesis_changes||\"\"" in text
    assert "capitalPriorityScore:(typeof a.capital_priority_score===\"number\"" in text
    assert "changes: {a.synthesisChanges}" in text
    assert "priority: {a.capitalPriorityScore}" in text
