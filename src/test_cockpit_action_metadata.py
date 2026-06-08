from pathlib import Path


def test_jsx_action_cards_render_synthesis_change_and_capital_priority():
    text = Path(__file__).with_name("conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "synthesisChanges:a.synthesis_changes||\"\"" in text
    assert "capitalPriorityScore:(typeof a.capital_priority_score===\"number\"" in text
    assert "hidden decision metadata" in text
    assert "changes: ${a.synthesisChanges}" in text
    assert "priority: ${a.capitalPriorityScore}" in text
    assert "capitalEfficiency.priority_reason" in text
    assert "capitalEfficiency.do_nothing_risk" in text


def test_jsx_today_decisions_surface_action_validity_metadata():
    text = Path(__file__).with_name("conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "function TodayDecisionQueue" in text
    assert "function ActionCard(" in text
    assert "function TodayActionCard(" in text
    assert "function DecisionLaneBoard" in text
    assert "Needed evidence:" in text
    assert "Gather evidence" in text
    assert "Codex evidence request:" in text
    assert "request ready" in text
    assert "gatherCopied" not in text
    assert "function evidenceGatherPrompt" in text
    assert "function friendlyEvidencePart" in text
    assert "navigator.clipboard.writeText" in text
    assert "same-session price/tape still supports the setup" in text
    assert "where the money comes from" in text
    assert "Confidence basis:" in text
    assert "Confidence is based on:" in text
    assert "Why conviction:" in text
    assert "Latest evidence check" in text
    assert "evidenceNeededText" in text
    assert "confidenceBasis" in text
    assert "a.capitalPriorityScore" in text
    assert "a.freshnessJudgment" in text
    assert "assumptionRefresh.what_changed" in text
    assert "capitalEfficiency.priority_reason" in text
    assert "capitalEfficiency.do_nothing_risk" in text
    assert "disconfirmation.invalidates_if" in text
