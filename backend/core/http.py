"""
Shared HTTP client for external providers
==========================================

* separate connect/read timeouts;
* retries with exponential backoff + jitter **only** for transient failures
  (timeouts, connection errors, HTTP 429, 500, 502, 503, 504);
* no retries for permanent client errors (400/401/403/404/422);
* every failure is mapped to a ``ProviderError`` with a stable ``kind`` and a
  sanitised message – URLs (which may contain keys) are never included.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from .logging_setup import get_logger

log = get_logger("http")

USER_AGENT = "TravelSafe/5.0 (educational travel-safety project)"
TRANSIENT_STATUS = {429, 500, 502, 503, 504}

# kind -> plain-language summary safe to show in the UI
KIND_MESSAGES = {
    "not_configured": "not configured",
    "unauthorized": "rejected the API key",
    "forbidden": "refused access for this key or plan",
    "rate_limited": "rate limit reached",
    "timeout": "did not respond in time",
    "unavailable": "temporarily unavailable",
    "network": "could not be reached",
    "bad_response": "returned data that could not be interpreted",
    "not_found": "has no data for this location",
    "no_data": "returned no data for this location",
    "disabled": "turned off in settings",
}


class ProviderError(Exception):
    def __init__(self, provider: str, kind: str, status: Optional[int] = None, detail: str = "") -> None:
        self.provider = provider
        self.kind = kind
        self.status = status
        self.detail = detail  # sanitised; safe for logs, not shown verbatim in the UI
        super().__init__(f"{provider}: {kind}" + (f" (HTTP {status})" if status else ""))

    @property
    def public_message(self) -> str:
        return f"{self.provider} {KIND_MESSAGES.get(self.kind, 'failed')}"


@dataclass
class HttpPolicy:
    connect_timeout: float = 4.0
    read_timeout: float = 8.0
    retries: int = 2
    backoff_base: float = 0.5
    backoff_cap: float = 4.0


def _provider_detail(resp: requests.Response) -> str:
    """Extract a short provider error message (no URLs, no keys)."""
    try:
        body = resp.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        for k in ("message", "reason", "detail", "error"):
            v = body.get(k)
            if isinstance(v, str):
                return v[:160]
    return ""


def _classify_status(status: int) -> str:
    if status == 401:
        return "unauthorized"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "unavailable"
    return "bad_response"


def get_json(provider: str, url: str, *, params: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None, policy: Optional[HttpPolicy] = None,
             sleep=None) -> Any:
    """GET a JSON document, retrying transient failures. Raises ProviderError."""
    policy = policy or HttpPolicy()
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.get(url, params=params, headers=hdrs,
                                timeout=(policy.connect_timeout, policy.read_timeout))
        except requests.exceptions.Timeout:
            err = ProviderError(provider, "timeout")
        except requests.exceptions.ConnectionError:
            err = ProviderError(provider, "network")
        except requests.exceptions.RequestException as exc:
            err = ProviderError(provider, "network", detail=type(exc).__name__)
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()
                except (ValueError, json.JSONDecodeError):
                    raise ProviderError(provider, "bad_response", 200, "invalid JSON") from None
            kind = _classify_status(resp.status_code)
            err = ProviderError(provider, kind, resp.status_code, _provider_detail(resp))
            if resp.status_code not in TRANSIENT_STATUS:
                log.warning("provider=%s permanent error kind=%s status=%s detail=%s",
                            provider, kind, resp.status_code, err.detail)
                raise err
        if attempt > policy.retries:
            log.warning("provider=%s failed after %d attempt(s): %s", provider, attempt, err)
            raise err
        delay = min(policy.backoff_cap, policy.backoff_base * 2 ** (attempt - 1)) * (0.5 + random.random() / 2)
        log.info("provider=%s transient failure (%s); retry %d in %.2fs", provider, err.kind, attempt, delay)
        (sleep or time.sleep)(delay)
