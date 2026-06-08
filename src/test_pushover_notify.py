import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pushover_notify


def test_load_config_accepts_existing_env_aliases():
    config = pushover_notify.load_config({
        "PUSHOVER_APP_TOKEN": "app-token",
        "PUSHOVER_USER_KEY": "user-key",
    })

    assert config.missing == []
    assert config.summary() == {
        "configured": True,
        "missing": [],
        "token_env": "PUSHOVER_APP_TOKEN",
        "user_env": "PUSHOVER_USER_KEY",
    }


def test_build_payload_redacts_secret_fields():
    config = pushover_notify.PushoverConfig(token="secret-token", user="secret-user")

    payload = pushover_notify.build_payload(
        title="Fundstrat alert",
        message="Action check",
        config=config,
        priority=1,
    )

    assert payload["token"] == "secret-token"
    assert payload["user"] == "secret-user"
    redacted = pushover_notify.redacted_payload(payload)
    assert redacted["token"] == "<redacted>"
    assert redacted["user"] == "<redacted>"


def test_send_message_dry_run_does_not_send():
    config = pushover_notify.PushoverConfig(token="secret-token", user="secret-user")

    report = pushover_notify.send_message(
        title="Fundstrat alert",
        message="Action check",
        config=config,
        dry_run=True,
    )

    assert report["dry_run"] is True
    assert report["sent"] is False
    assert report["payload"]["token"] == "<redacted>"


def test_emergency_priority_requires_retry_and_expire():
    config = pushover_notify.PushoverConfig(token="secret-token", user="secret-user")

    try:
        pushover_notify.build_payload(
            title="Emergency",
            message="Missing retry",
            config=config,
            priority=2,
        )
    except ValueError as exc:
        assert "retry and expire" in str(exc)
    else:
        raise AssertionError("expected ValueError")
