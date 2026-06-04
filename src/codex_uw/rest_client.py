#!/usr/bin/env python3
"""
uw_rest_client.py - small redaction-safe Unusual Whales REST client.

The client is deliberately generic. Higher-level code owns endpoint selection and
normalization; this module only handles auth, headers, URL construction, retries,
and safe errors. It never logs tokens.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .endpoints import UW_API_BASE, UW_CLIENT_API_ID, validate_endpoint_path


class UWConfigError(RuntimeError):
    pass


class UWRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class UWResponseSummary:
    endpoint: str
    status: int
    row_count: Optional[int]


def unwrap_uw_rows(payload: Any) -> list:
    """Return the common UW list payload without assuming a single wrapper."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "signals", "result"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return unwrap_uw_rows(val)
    return []


class UWRestClient:
    def __init__(
        self,
        token: Optional[str] = None,
        *,
        base_url: str = UW_API_BASE,
        timeout: float = 30.0,
        retries: int = 1,
        user_agent: str = "InvestingOS-Codex/1.0",
    ):
        token = token or os.environ.get("UW_API_KEY")
        if not token:
            raise UWConfigError("UW_API_KEY is not set")
        self._token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.headers = {
            "Authorization": f"Bearer {token}",
            "UW-CLIENT-API-ID": UW_CLIENT_API_ID,
            "Accept": "application/json",
            "User-Agent": user_agent,
        }

    def get_json(
        self,
        path_template: str,
        *,
        path_params: Optional[Mapping[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        validate_endpoint_path(path_template)
        path = self._format_path(path_template, path_params or {})
        url = self.base_url + path
        clean_params = self._clean_params(params or {})
        if clean_params:
            url += "?" + urlencode(clean_params, doseq=True)

        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                req = Request(url, headers=self.headers, method="GET")
                with urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    return json.loads(body) if body else {}
            except HTTPError as exc:
                last_error = exc
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise self._http_error(path_template, exc) from None
            except (URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise UWRequestError(f"UW request failed for {path_template}: {exc}") from None
            except json.JSONDecodeError as exc:
                raise UWRequestError(f"UW returned non-JSON for {path_template}: {exc}") from None
        raise UWRequestError(f"UW request failed for {path_template}: {last_error}")

    @staticmethod
    def _format_path(path_template: str, path_params: Mapping[str, Any]) -> str:
        safe = {k: str(v).upper() if k == "ticker" else str(v) for k, v in path_params.items()}
        try:
            return path_template.format(**safe)
        except KeyError as exc:
            raise UWRequestError(f"Missing UW path parameter {exc!s} for {path_template}") from None

    @staticmethod
    def _clean_params(params: Mapping[str, Any]) -> dict:
        out = {}
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple)) and not v:
                continue
            out[k] = v
        return out

    @staticmethod
    def _http_error(path_template: str, exc: HTTPError) -> UWRequestError:
        detail = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
            if raw:
                detail = raw[:300]
        except Exception:
            detail = ""
        msg = f"UW HTTP {exc.code} for {path_template}"
        if detail:
            msg += f": {detail}"
        return UWRequestError(msg)
