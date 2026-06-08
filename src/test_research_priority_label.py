from pathlib import Path


JSX = Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx"


def test_from_research_uses_priority_badge_label_without_changing_action_contract():
    text = JSX.read_text(encoding="utf-8")

    assert 'confBadgeLabel:opts.confBadgeLabel||"conf"' in text
    assert 'const researchActions = (feed.research_actions||[]).map(a=>actionRow(a, { confBadgeLabel:"priority" }))' in text
    assert "todayPriority: todayPriorityRows(feed, actions, researchActions)" in text
    assert "researchActions," in text
    assert "priority: {a.confLabel}" not in text
    assert "conf: {a.confLabel}" not in text
    assert "{a.confBadgeLabel}: {a.confLabel}" in text
    assert "function ActionCard(" in text
    assert 'keyPrefix={`lane${section.key||"x"}`}' in text
    assert 'keyPrefix="rsch"' in text


def test_signal_log_is_separate_watch_only_dashboard_lane():
    text = JSX.read_text(encoding="utf-8")

    assert "function signalLogRow(" in text
    assert "signalLog: (feed.signal_log||[]).map(signalLogRow)" in text
    assert '<Section id="signal-log" title="Signal Log"' in text
    assert "watch-only items from the external signal log" in text
