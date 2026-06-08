#!/usr/bin/env python3
"""Send Investing OS notifications through Pushover without exposing secrets."""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"
TOKEN_ENV_NAMES = ("PUSHOVER_APP_TOKEN", "PUSHOVER_API_TOKEN", "PUSHOVER_TOKEN")
USER_ENV_NAMES = ("PUSHOVER_USER_KEY", "PUSHOVER_USER_TOKEN", "PUSHOVER_USER")
MAX_TITLE_CHARS = 250
MAX_MESSAGE_CHARS = 1024


@dataclass(frozen=True, repr=False)
class PushoverConfig:
    token: str
    user: str
    token_env: str = ""
    user_env: str = ""

    @property
    def missing(self) -> list[str]:
        missing: list[str] = []
        if not self.token:
            missing.append("token")
        if not self.user:
            missing.append("user")
        return missing

    def summary(self) -> dict[str, Any]:
        return {
            "configured": not self.missing,
            "missing": self.missing,
            "token_env": self.token_env,
            "user_env": self.user_env,
        }


def _first_env(env: Mapping[str, str], names: tuple[str, ...]) -> tuple[str, str]:
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return value, name
    return "", ""


def load_config(env: Mapping[str, str] | None = None) -> PushoverConfig:
    env = env or os.environ
    token, token_env = _first_env(env, TOKEN_ENV_NAMES)
    user, user_env = _first_env(env, USER_ENV_NAMES)
    return PushoverConfig(token=token, user=user, token_env=token_env, user_env=user_env)


def _truncate(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."


def build_payload(
    *,
    title: str,
    message: str,
    config: PushoverConfig | None = None,
    priority: int = 0,
    url: str = "",
    url_title: str = "",
    sound: str = "",
    retry: int | None = None,
    expire: int | None = None,
) -> dict[str, Any]:
    config = config or load_config()
    if config.missing:
        raise ValueError("Pushover config missing: " + ", ".join(config.missing))
    if priority not in {-2, -1, 0, 1, 2}:
        raise ValueError("Pushover priority must be one of -2, -1, 0, 1, 2")
    payload: dict[str, Any] = {
        "token": config.token,
        "user": config.user,
        "title": _truncate(title, MAX_TITLE_CHARS),
        "message": _truncate(message, MAX_MESSAGE_CHARS),
        "priority": str(priority),
    }
    if url:
        payload["url"] = _truncate(url, 512)
    if url_title:
        payload["url_title"] = _truncate(url_title, 100)
    if sound:
        payload["sound"] = _truncate(sound, 30)
    if priority == 2:
        if retry is None or expire is None:
            raise ValueError("Emergency priority requires retry and expire")
        payload["retry"] = str(retry)
        payload["expire"] = str(expire)
    return payload


def redacted_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    for key in ("token", "user"):
        if redacted.get(key):
            redacted[key] = "<redacted>"
    return redacted


def send_payload(
    payload: Mapping[str, Any],
    *,
    endpoint: str = PUSHOVER_ENDPOINT,
    timeout: float = 10.0,
) -> dict[str, Any]:
    data = urllib.parse.urlencode({key: str(value) for key, value in payload.items()}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return {
            "sent": 200 <= int(response.status) < 300,
            "status_code": int(response.status),
            "response": parsed,
        }


def send_message(
    *,
    title: str,
    message: str,
    priority: int = 0,
    url: str = "",
    url_title: str = "",
    sound: str = "",
    retry: int | None = None,
    expire: int | None = None,
    dry_run: bool = False,
    config: PushoverConfig | None = None,
) -> dict[str, Any]:
    config = config or load_config()
    payload = build_payload(
        title=title,
        message=message,
        config=config,
        priority=priority,
        url=url,
        url_title=url_title,
        sound=sound,
        retry=retry,
        expire=expire,
    )
    if dry_run:
        return {
            "sent": False,
            "dry_run": True,
            "configured": True,
            "payload": redacted_payload(payload),
        }
    result = send_payload(payload)
    result["dry_run"] = False
    return result


def _format_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"Pushover configured: {bool(report.get('configured', report.get('sent') or report.get('dry_run')))}",
        f"Dry run: {bool(report.get('dry_run'))}",
        f"Sent: {bool(report.get('sent'))}",
    ]
    if report.get("config"):
        config = report.get("config") or {}
        lines.append(f"Config env: token={config.get('token_env') or 'missing'} | user={config.get('user_env') or 'missing'}")
    if report.get("status_code"):
        lines.append(f"Status code: {report.get('status_code')}")
    if report.get("error"):
        lines.append(f"Error: {report.get('error')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a Pushover notification for Investing OS.")
    parser.add_argument("--title", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--priority", type=int, default=0)
    parser.add_argument("--url", default="")
    parser.add_argument("--url-title", default="")
    parser.add_argument("--sound", default="")
    parser.add_argument("--retry", type=int)
    parser.add_argument("--expire", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    config = load_config()
    if args.self_test:
        title = args.title or "Investing OS Pushover self-test"
        message = args.message or "Pushover is configured for Investing OS alerts."
    else:
        title = args.title
        message = args.message
    report: dict[str, Any]
    if config.missing:
        report = {
            "sent": False,
            "dry_run": args.dry_run,
            "configured": False,
            "config": config.summary(),
            "error": "Pushover config missing: " + ", ".join(config.missing),
        }
    elif not title or not message:
        report = {
            "sent": False,
            "dry_run": args.dry_run,
            "configured": True,
            "config": config.summary(),
            "error": "title and message are required unless --self-test supplies defaults",
        }
    else:
        try:
            report = send_message(
                title=title,
                message=message,
                priority=args.priority,
                url=args.url,
                url_title=args.url_title,
                sound=args.sound,
                retry=args.retry,
                expire=args.expire,
                dry_run=args.dry_run,
                config=config,
            )
            report["configured"] = True
            report["config"] = config.summary()
        except Exception as exc:
            report = {
                "sent": False,
                "dry_run": args.dry_run,
                "configured": True,
                "config": config.summary(),
                "error": str(exc),
            }
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_text(report))
    return 0 if (report.get("dry_run") or report.get("sent") or (args.self_test and report.get("configured"))) and not report.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
