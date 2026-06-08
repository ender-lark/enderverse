import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_daytime_alert import (
    build_alert_report,
    build_push_message,
    classify_call,
    update_state_for_alerts,
)


def test_fluff_fundstrat_update_stays_quiet():
    row = {
        "author": "Fundstrat",
        "ticker": "SPY",
        "direction": "watch",
        "quote": "Join us for a replay webinar with general market observations.",
        "date": "2026-06-08",
        "subject": "Webinar replay",
    }

    classified = classify_call(row, now="2026-06-08T11:00:00-04:00")

    assert classified["qualifies"] is False
    assert classified["reason"] == "fluff_or_low_value"


def test_time_sensitive_defensive_call_qualifies():
    row = {
        "author": "Newton",
        "ticker": "XOP",
        "direction": "avoid",
        "quote": "Break below support near 175 today would keep downside risk active.",
        "date": "2026-06-08",
        "subject": "Daily Technical Strategy",
    }

    report = build_alert_report(
        [row],
        feed={"positions": [{"ticker": "XOP"}]},
        now="2026-06-08T11:00:00-04:00",
    )

    assert report["status"] == "notify"
    assert report["alerts"][0]["ticker"] == "XOP"
    assert report["alerts"][0]["posture"] == "trim/hedge/re-check"


def test_context_only_call_does_not_alert():
    row = {
        "author": "Tom Lee",
        "ticker": "QQQ",
        "direction": "watch",
        "quote": "Long-term AI thesis remains constructive but no immediate action changes.",
        "date": "2026-06-08",
        "subject": "Macro note",
    }

    report = build_alert_report([row], now="2026-06-08T11:00:00-04:00")

    assert report["status"] == "quiet"
    assert report["suppressed"][0]["reason"] == "does_not_change_action_posture"


def test_duplicate_alert_suppression_uses_state():
    row = {
        "author": "Newton",
        "ticker": "TNX",
        "direction": "avoid",
        "quote": "Break above resistance in 10-year yield today would raise risk.",
        "date": "2026-06-08",
        "subject": "Daily Technical Strategy",
    }
    first = build_alert_report([row], now="2026-06-08T11:00:00-04:00")
    state = update_state_for_alerts({}, first)

    second = build_alert_report([row], state=state, now="2026-06-08T12:00:00-04:00")

    assert first["status"] == "notify"
    assert second["status"] == "quiet"
    assert second["counts"]["duplicates"] == 1


def test_push_message_is_action_oriented_and_no_execution():
    row = {
        "author": "Sean Farrell",
        "ticker": "BTC",
        "direction": "trim",
        "quote": "Break below support today would keep crypto downside risk active.",
        "date": "2026-06-08",
        "subject": "Crypto Strategy",
    }
    report = build_alert_report([row], now="2026-06-08T11:00:00-04:00")

    title, message = build_push_message(report)

    assert "Fundstrat intraday" in title
    assert "BTC" in message
    assert "Open the cockpit before acting" in message
