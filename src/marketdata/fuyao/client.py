"""Thin HTTP client for https://fuyao.aicubes.cn (Tonghuashun financial data)."""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

from .secrets import resolve_api_key


class FuyaoError(RuntimeError):
    """API or auth failure."""


class FuyaoClient:
    """Read-only A-share market data via REST + X-api-key."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://fuyao.aicubes.cn",
        timeout: float = 20.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or resolve_api_key() or os.getenv("HITHINK_FINANCE_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError(
                "Missing API key. Set HITHINK_FINANCE_API_KEY (or FUYAO_API_KEY) in "
                "instances/<name>/agent/secrets.env or the environment. "
                "Create a key at https://fuyao.aicubes.cn/admin/"
            )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-api-key": self.api_key,
                "Accept": "application/json",
            }
        )

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise FuyaoError(f"Unexpected response type: {type(payload)}")
        code = payload.get("code")
        if code not in (0, None, "0"):
            raise FuyaoError(
                f"Fuyao error code={code} message={payload.get('message')!r} "
                f"request_id={payload.get('request_id')}"
            )
        return payload

    def snapshot(self, thscodes: list[str]) -> dict[str, Any]:
        if not thscodes:
            raise ValueError("thscodes required")
        joined = ",".join(normalize_thscode(c) for c in thscodes)
        return self._get("/api/a-share/prices/snapshot", {"thscodes": joined})

    def historical(
        self,
        thscode: str,
        start_ms: int,
        end_ms: int,
        interval: str = "1d",
        adjust: str = "forward",
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._get(
            "/api/a-share/prices/historical",
            {
                "thscode": normalize_thscode(thscode),
                "interval": interval,
                "start": start_ms,
                "end": end_ms,
                "adjust": adjust,
                "offset": offset,
            },
        )

    def search_tickers(self, q: str, limit: int = 10) -> dict[str, Any]:
        return self._get(
            "/api/meta/tickers/search",
            {"q": q, "limit": limit},
        )

    def calendar(self) -> dict[str, Any]:
        return self._get("/api/a-share/calendar")


def normalize_thscode(code: str) -> str:
    """Accept 600519 / 600519.SH / sh600519 → 600519.SH."""
    raw = code.strip().upper().replace(" ", "")
    if not raw:
        raise ValueError("empty symbol")
    if "." in raw:
        return raw
    if raw.startswith(("SH", "SZ", "BJ")) and len(raw) > 2 and raw[2:].isdigit():
        return f"{raw[2:]}.{raw[:2]}"
    if raw.isdigit() and len(raw) == 6:
        if raw.startswith(("5", "6", "9")):
            return f"{raw}.SH"
        return f"{raw}.SZ"
    return raw
