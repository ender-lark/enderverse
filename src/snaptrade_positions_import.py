#!/usr/bin/env python3
"""Read-only SnapTrade account-position importer.

This module intentionally writes staged combined snapshots, not live
positions.json. Downstream cache writers already know how to validate and
promote combined broker-position JSON after an operator review.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SNAPTRADE_API_BASE = "https://api.snaptrade.com/api/v1"
DEFAULT_PROFILES_PATH = Path(__file__).with_name("snaptrade_profiles.local.json")
EXAMPLE_PROFILES_PATH = Path(__file__).with_name("snaptrade_profiles.example.json")
CLIENT_ID_ENV = "SNAPTRADE_CLIENT_ID"
CONSUMER_KEY_ENV = "SNAPTRADE_CONSUMER_KEY"
OPERATOR_TZ = ZoneInfo("America/New_York")
NON_TRADABLE_SYMBOL_PREFIXES = ("L0C",)
NON_TRADABLE_DESCRIPTION_TERMS = (
    "COLLATERAL DELV",
    "ESCROW",
    "RESTRICTED WTS",
)


class SnapTradeError(RuntimeError):
    """Raised when SnapTrade returns an unusable response."""


def user_env(name: str) -> str | None:
    """Read an env var from the current process or Windows user environment."""
    value = os.environ.get(name)
    if value:
        return value
    return windows_user_env(name)


def windows_user_env(name: str) -> str | None:
    """Read an env var directly from the Windows user environment."""
    if os.name != "nt":
        return None
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            raw, _ = winreg.QueryValueEx(key, name)
            return str(raw) if raw else None
    except OSError:
        return None


def api_credential_env(name: str) -> str | None:
    """Read SnapTrade API credentials, preferring refreshed Windows user env.

    Codex can inherit stale process-level credentials when the user updates
    Windows user environment variables during an active app session. For the
    API key pair, the registry is the durable source used by scheduled runs.
    """
    if name in {CLIENT_ID_ENV, CONSUMER_KEY_ENV}:
        value = windows_user_env(name)
        if value:
            return value
    return user_env(name)


def credential_status(names: list[str] | None = None) -> list[dict[str, Any]]:
    rows = []
    for name in names or [CLIENT_ID_ENV, CONSUMER_KEY_ENV]:
        value = user_env(name)
        rows.append({
            "name": name,
            "present": bool(value),
            "length": len(value or ""),
        })
    return rows


def compute_request_signature(resource_path: str,
                              consumer_key: str,
                              body: Any | None) -> str:
    """Return SnapTrade HMAC signature for a resource path.

    resource_path is the path after /api/v1, including the query string, for
    example /snapTrade/registerUser?clientId=...&timestamp=...
    """
    subpath, query = resource_path.split("?", 1)
    payload = {
        "content": None if body is None or body == {} else body,
        "path": f"/api/v1{subpath}",
        "query": query,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    digest = hmac.new(
        consumer_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _json_number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _nested(row: dict[str, Any], path: list[str]) -> Any:
    cur: Any = row
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _is_non_tradable_placeholder(ticker: str,
                                 description: str,
                                 market_value: float | None) -> bool:
    """Return true for SnapTrade custody placeholders, not live holdings."""
    if market_value not in (None, 0, 0.0):
        return False
    symbol = ticker.strip().upper()
    desc = description.strip().upper()
    if any(symbol.startswith(prefix) for prefix in NON_TRADABLE_SYMBOL_PREFIXES):
        return True
    return any(term in desc for term in NON_TRADABLE_DESCRIPTION_TERMS)


def _symbol_payload(position: dict[str, Any]) -> dict[str, Any]:
    symbol = position.get("symbol")
    if isinstance(symbol, dict):
        inner = symbol.get("symbol")
        if isinstance(inner, dict):
            return inner
        option_inner = symbol.get("option_symbol")
        if isinstance(option_inner, dict):
            return option_inner
    return {}


def _account_name(account: dict[str, Any], fallback: str) -> str:
    number = str(account.get("number") or "").strip()
    masked = f" {number}" if number else ""
    return str(account.get("name") or fallback).strip() + masked


def _broker_name(account: dict[str, Any], connection: dict[str, Any] | None = None) -> str:
    for source in (account, connection or {}):
        institution = source.get("institution_name")
        if institution:
            return str(institution).strip()
        brokerage = source.get("brokerage")
        if isinstance(brokerage, dict):
            name = brokerage.get("name") or brokerage.get("display_name")
            if name:
                return str(name).strip()
    return "SnapTrade"


def owner_for_account(profile: dict[str, Any], account: dict[str, Any]) -> str:
    """Resolve owner label using optional account-level override rules."""
    default_owner = str(profile.get("owner") or profile.get("profile") or profile.get("user_id") or "Unknown")
    account_id = str(account.get("id") or "").strip()
    account_name = str(account.get("name") or "").strip().lower()
    account_number = str(account.get("number") or "").strip().lower()
    for rule in profile.get("account_owner_overrides", []) or []:
        if not isinstance(rule, dict) or not rule.get("owner"):
            continue
        if rule.get("account_id") and str(rule["account_id"]).strip() == account_id:
            return str(rule["owner"]).strip()
        name_needle = str(rule.get("account_name_contains") or "").strip().lower()
        if name_needle and name_needle in account_name:
            return str(rule["owner"]).strip()
        number_needle = str(rule.get("account_number_contains") or "").strip().lower()
        if number_needle and number_needle in account_number:
            return str(rule["owner"]).strip()
    return default_owner


def normalize_equity_position(position: dict[str, Any],
                              *,
                              account_name: str,
                              owner: str) -> dict[str, Any] | None:
    symbol_info = _symbol_payload(position)
    ticker = str(
        symbol_info.get("raw_symbol")
        or symbol_info.get("symbol")
        or position.get("ticker")
        or ""
    ).strip().upper()
    if not ticker:
        return None
    units = _json_number(position.get("units") or position.get("quantity"))
    price = _json_number(position.get("price"))
    market_value = (
        _json_number(position.get("market_value"))
        or _json_number(position.get("current_value"))
        or _json_number(position.get("value"))
    )
    if market_value is None and units is not None and price is not None:
        market_value = units * price
    description = str(symbol_info.get("description") or position.get("description") or "").strip()
    if _is_non_tradable_placeholder(ticker, description, market_value):
        return None
    return {
        "symbol": ticker,
        "description": description,
        "quantity": units,
        "market_value": market_value,
        "account_name": account_name,
        "owner": owner,
        "asset_type": str(_nested(symbol_info, ["type", "description"]) or "").strip() or None,
        "average_purchase_price": _json_number(position.get("average_purchase_price")),
        "cash_equivalent": position.get("cash_equivalent"),
    }


def _option_market_value(
    *,
    broker: str,
    units: float | None,
    price: float | None,
    multiplier: int,
) -> float | None:
    """Normalize SnapTrade option value across broker price conventions.

    Fidelity/Schwab option rows observed through SnapTrade report option price
    per underlying share, so contract value is units * price * multiplier.
    Robinhood option rows observed through SnapTrade report contract-level
    value in the price field, so applying the multiplier again overstates value
    by 100x.
    """
    if units is None or price is None:
        return None
    if "robinhood" in str(broker or "").lower():
        return units * price
    return units * price * multiplier


def normalize_option_position(position: dict[str, Any],
                              *,
                              account_name: str,
                              owner: str,
                              broker: str = "") -> dict[str, Any] | None:
    option_info = _symbol_payload(position)
    underlying = option_info.get("underlying_symbol") if isinstance(option_info, dict) else None
    underlying_ticker = ""
    if isinstance(underlying, dict):
        underlying_ticker = str(underlying.get("raw_symbol") or underlying.get("symbol") or "").strip().upper()
    ticker = underlying_ticker or str(option_info.get("ticker") or "").strip().upper()
    if not ticker:
        return None
    units = _json_number(position.get("units"))
    price = _json_number(position.get("price"))
    multiplier = 10 if option_info.get("is_mini_option") else 100
    market_value = _json_number(position.get("market_value"))
    if market_value is None and units is not None and price is not None:
        market_value = _option_market_value(broker=broker, units=units, price=price, multiplier=multiplier)
    option_type = str(option_info.get("option_type") or "").strip().lower()
    strike = _json_number(option_info.get("strike_price"))
    expiry = option_info.get("expiration_date")
    label = " ".join(
        part for part in [
            str(strike).rstrip("0").rstrip(".") if strike is not None else "",
            option_type.title() if option_type else "Option",
            str(expiry or ""),
        ]
        if part
    )
    return {
        "symbol": ticker,
        "description": label,
        "quantity": units,
        "market_value": market_value,
        "account_name": account_name,
        "owner": owner,
        "asset_type": "option",
        "price": price,
        "option": {
            "occ_symbol": option_info.get("ticker"),
            "underlying": ticker,
            "expiry": expiry,
            "call_put": option_type or None,
            "strike": strike,
            "multiplier": multiplier,
            "price_convention": "contract" if "robinhood" in str(broker or "").lower() else "underlying_share",
        },
        "average_purchase_price": _json_number(position.get("average_purchase_price")),
    }


def balances_cash(balances: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in balances or []:
        currency = row.get("currency") if isinstance(row, dict) else {}
        if isinstance(currency, dict) and currency.get("code") not in (None, "USD"):
            continue
        cash = _json_number(row.get("cash") if isinstance(row, dict) else None)
        if cash is not None:
            total += cash
    return total


def build_combined_from_snaptrade(payload: dict[str, Any],
                                  *,
                                  as_of: str | None = None,
                                  generated_at: str | None = None) -> dict[str, Any]:
    """Convert staged SnapTrade raw data into broker-extractor combined JSON."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    as_of = as_of or datetime.now(OPERATOR_TZ).date().isoformat()
    files: list[dict[str, Any]] = []
    total_market_value = 0.0
    total_cash = 0.0
    warnings: list[str] = []

    for profile in payload.get("profiles", []) or []:
        profile_owner = str(profile.get("owner") or profile.get("profile") or "Unknown")
        for account in profile.get("accounts", []) or []:
            account_row = account.get("account") or {}
            owner = str(account.get("owner") or profile_owner)
            account_name = _account_name(account_row, "SnapTrade Account")
            broker = _broker_name(account_row, account.get("connection"))
            positions = []
            for position in account.get("positions", []) or []:
                normalized = normalize_equity_position(position, account_name=account_name, owner=owner)
                if normalized:
                    positions.append(normalized)
            for position in account.get("option_positions", []) or []:
                normalized = normalize_option_position(position, account_name=account_name, owner=owner, broker=broker)
                if normalized:
                    positions.append(normalized)

            market_value = sum(float(p.get("market_value") or 0.0) for p in positions)
            cash = balances_cash(account.get("balances", []) or [])
            total_market_value += market_value
            total_cash += cash
            if not positions:
                warnings.append(f"{owner}/{broker}/{account_name}: no positions returned")
            files.append({
                "source_file": f"snaptrade://{owner}/{broker}/{account_row.get('id') or account_name}",
                "broker": broker,
                "owner": owner,
                "account_name": account_name,
                "positions_scope": "account",
                "positions": positions,
                "cash": round(cash, 2),
                "validation": {
                    "passed": True,
                    "positions_found": len(positions),
                    "source": "snaptrade",
                },
            })

    return {
        "schema_version": "2.0",
        "extractor": "snaptrade_positions_import",
        "generated_at": generated_at,
        "files": files,
        "portfolio_summary": {
            "total_market_value": round(total_market_value, 2),
            "total_cash": round(total_cash, 2),
            "as_of": as_of,
        },
        "warnings": warnings,
    }


class SnapTradeClient:
    def __init__(self, client_id: str | None = None, consumer_key: str | None = None) -> None:
        self.client_id = client_id or api_credential_env(CLIENT_ID_ENV)
        self.consumer_key = consumer_key or api_credential_env(CONSUMER_KEY_ENV)
        if not self.client_id or not self.consumer_key:
            raise SnapTradeError("Missing SNAPTRADE_CLIENT_ID or SNAPTRADE_CONSUMER_KEY")

    def request(self,
                method: str,
                subpath: str,
                *,
                query: list[tuple[str, str]] | None = None,
                body: Any | None = None) -> Any:
        params = list(query or [])
        params.extend([
            ("clientId", self.client_id),
            ("timestamp", str(int(time.time()))),
        ])
        query_string = urllib.parse.urlencode(params)
        resource_path = f"{subpath}?{query_string}"
        signature = compute_request_signature(resource_path, self.consumer_key, body)
        data = None
        headers = {
            "Signature": signature,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            f"{SNAPTRADE_API_BASE}{resource_path}",
            data=data,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SnapTradeError(f"SnapTrade HTTP {exc.code}: {detail}") from exc
        if not raw:
            return None
        return json.loads(raw)

    def register_user(self, user_id: str) -> dict[str, Any]:
        return self.request("POST", "/snapTrade/registerUser", body={"userId": user_id})

    def login_url(self,
                  user_id: str,
                  user_secret: str,
                  *,
                  broker: str | None = None,
                  connection_type: str = "read",
                  custom_redirect: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"connectionType": connection_type}
        if broker:
            body["broker"] = broker
        if custom_redirect:
            body["customRedirect"] = custom_redirect
        return self.request(
            "POST",
            "/snapTrade/login",
            query=[("userId", user_id), ("userSecret", user_secret)],
            body=body,
        )

    def list_connections(self, user_id: str, user_secret: str) -> list[dict[str, Any]]:
        return self.request(
            "GET",
            "/authorizations",
            query=[("userId", user_id), ("userSecret", user_secret)],
        )

    def list_accounts(self, user_id: str, user_secret: str) -> list[dict[str, Any]]:
        return self.request(
            "GET",
            "/accounts",
            query=[("userId", user_id), ("userSecret", user_secret)],
        )

    def account_positions(self, account_id: str, user_id: str, user_secret: str) -> list[dict[str, Any]]:
        return self.request(
            "GET",
            f"/accounts/{urllib.parse.quote(account_id)}/positions",
            query=[("userId", user_id), ("userSecret", user_secret)],
        )

    def option_positions(self, account_id: str, user_id: str, user_secret: str) -> list[dict[str, Any]]:
        return self.request(
            "GET",
            f"/accounts/{urllib.parse.quote(account_id)}/options",
            query=[("userId", user_id), ("userSecret", user_secret)],
        )

    def account_balances(self, account_id: str, user_id: str, user_secret: str) -> list[dict[str, Any]]:
        return self.request(
            "GET",
            f"/accounts/{urllib.parse.quote(account_id)}/balances",
            query=[("userId", user_id), ("userSecret", user_secret)],
        )


def read_profiles(path: str | Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    profiles = doc.get("profiles") if isinstance(doc, dict) else doc
    if not isinstance(profiles, list):
        raise ValueError("profiles config must be a list or an object with profiles[]")
    return profiles


def resolve_profile_secret(profile: dict[str, Any]) -> str:
    value = profile.get("user_secret")
    if value:
        return str(value)
    env_name = str(profile.get("user_secret_env") or "").strip()
    if env_name:
        secret = user_env(env_name)
        if secret:
            return secret
    raise SnapTradeError(f"Missing user secret for profile {profile.get('profile')!r}")


def pull_profiles(client: SnapTradeClient,
                  profiles: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"profiles": []}
    for profile in profiles:
        user_id = str(profile.get("user_id") or "").strip()
        if not user_id:
            raise SnapTradeError(f"Profile {profile.get('profile')!r} is missing user_id")
        user_secret = resolve_profile_secret(profile)
        connections = client.list_connections(user_id, user_secret)
        accounts = client.list_accounts(user_id, user_secret)
        connection_by_id = {str(c.get("id")): c for c in connections if isinstance(c, dict)}
        account_rows = []
        for account in accounts:
            account_id = str(account.get("id") or "").strip()
            if not account_id:
                continue
            account_rows.append({
                "account": account,
                "owner": owner_for_account(profile, account),
                "connection": connection_by_id.get(str(account.get("brokerage_authorization")), {}),
                "positions": client.account_positions(account_id, user_id, user_secret),
                "option_positions": client.option_positions(account_id, user_id, user_secret),
                "balances": client.account_balances(account_id, user_id, user_secret),
            })
        out["profiles"].append({
            "profile": profile.get("profile") or user_id,
            "owner": profile.get("owner") or profile.get("profile") or user_id,
            "user_id": user_id,
            "accounts": account_rows,
        })
    return out


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SnapTrade broker-position importer.")
    parser.add_argument("--credential-status", action="store_true",
                        help="Report whether SnapTrade API credentials are available without printing secrets.")
    parser.add_argument("--register-user", help="Register a SnapTrade user id and print the env var command for its secret.")
    parser.add_argument("--secret-env", help="Env var name for a registered user's secret.")
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILES_PATH),
                        help="Path to profile config. Secrets should come from env vars.")
    parser.add_argument("--login-url", help="Profile name from --profiles to generate a read-only connection URL.")
    parser.add_argument("--broker", help="Optional broker slug for --login-url.")
    parser.add_argument("--pull", action="store_true", help="Pull profiles and write staged raw/combined JSON.")
    parser.add_argument("--raw-out", default="tmp/snaptrade_raw.json")
    parser.add_argument("--combined-out", default="tmp/snaptrade_combined.json")
    args = parser.parse_args()

    if args.credential_status:
        print(json.dumps({"credentials": credential_status()}, indent=2))
        return 0

    client = SnapTradeClient()

    if args.register_user:
        response = client.register_user(args.register_user)
        secret = response.get("userSecret")
        if not secret:
            raise SnapTradeError(f"Register response did not include userSecret: {response}")
        env_name = args.secret_env or f"SNAPTRADE_{args.register_user.upper().replace('-', '_')}_USER_SECRET"
        print(f"Registered userId: {response.get('userId')}")
        print(f"Store the user secret locally with:")
        print(f'setx {env_name} "{secret}"')
        print("Then add this profile to src/snaptrade_profiles.local.json.")
        return 0

    if args.login_url:
        profiles = read_profiles(args.profiles)
        selected = next((p for p in profiles if p.get("profile") == args.login_url), None)
        if not selected:
            raise SnapTradeError(f"Profile {args.login_url!r} not found in {args.profiles}")
        response = client.login_url(
            str(selected["user_id"]),
            resolve_profile_secret(selected),
            broker=args.broker,
            connection_type="read",
        )
        print(response.get("redirectURI") or json.dumps(response, indent=2))
        return 0

    if args.pull:
        profiles = read_profiles(args.profiles)
        raw = pull_profiles(client, profiles)
        combined = build_combined_from_snaptrade(raw)
        write_json(args.raw_out, raw)
        write_json(args.combined_out, combined)
        print(json.dumps({
            "raw_out": args.raw_out,
            "combined_out": args.combined_out,
            "profiles": len(raw["profiles"]),
            "accounts": sum(len(p.get("accounts", [])) for p in raw["profiles"]),
            "positions": sum(
                len(f.get("positions", []) or [])
                for f in combined.get("files", [])
            ),
            "total_market_value": combined["portfolio_summary"]["total_market_value"],
            "total_cash": combined["portfolio_summary"]["total_cash"],
            "warnings": combined.get("warnings", []),
        }, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SnapTradeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
