"""Low-level OKX v5 REST client (HMAC auth + simulated header)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from .errors import OkxAuthError, OkxError


DEFAULT_BASE_URL = "https://www.okx.com"


def utc_timestamp() -> str:
    """OKX expects ISO8601 with milliseconds, e.g. 2020-12-08T09:08:57.715Z."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(now.microsecond / 1000):03d}Z"


def sign(secret: str, timestamp: str, method: str, path_with_query: str, body: str) -> str:
    message = f"{timestamp}{method.upper()}{path_with_query}{body}"
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class OkxRestClient:
    """Thin transport. Prefer ``OkxService`` for trading semantics."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        *,
        simulated: bool = True,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = (
            api_key
            or os.getenv("OKX_API_KEY")
            or os.getenv("OKX_APIKEY")
            or os.getenv("OKX_KEY")
        )
        self.api_secret = (
            api_secret
            or os.getenv("OKX_API_SECRET")
            or os.getenv("OKX_SECRET_KEY")
            or os.getenv("OKX_API_SECRET_KEY")
            or os.getenv("OKX_SECRET")
        )
        self.passphrase = passphrase or os.getenv("OKX_PASSPHRASE") or os.getenv(
            "OKX_API_PASSPHRASE"
        )
        self.simulated = simulated
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        proxy = os.getenv("OKX_HTTP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        if proxy and not session:
            # Explicit OKX/HTTPS proxy; requests also honors env if set externally.
            self.session.proxies.update({"http": proxy, "https": proxy})

    @classmethod
    def from_env(
        cls,
        *,
        simulated: Optional[bool] = None,
        timeout: float = 20.0,
        require_creds: bool = True,
    ) -> "OkxRestClient":
        from .secrets import env_simulated_default, load_secrets_into_environ

        load_secrets_into_environ(require_creds=require_creds)
        flag = env_simulated_default() if simulated is None else simulated
        return cls(simulated=flag, timeout=timeout)

    def _assert_creds(self) -> None:
        if not self.api_key or not self.api_secret or not self.passphrase:
            raise OkxAuthError(
                "OKX credentials incomplete. Need OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE."
            )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any] | list[Any]] = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        if not path.startswith("/"):
            path = "/" + path

        query = ""
        if params:
            # Stable order for signing; drop None values.
            cleaned = {k: v for k, v in params.items() if v is not None}
            if cleaned:
                query = "?" + urlencode(cleaned, doseq=True)
        path_with_query = path + query

        body_str = ""
        if body is not None:
            body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.simulated:
            headers["x-simulated-trading"] = "1"

        if auth:
            self._assert_creds()
            ts = utc_timestamp()
            assert self.api_secret is not None
            headers.update(
                {
                    "OK-ACCESS-KEY": self.api_key or "",
                    "OK-ACCESS-SIGN": sign(self.api_secret, ts, method, path_with_query, body_str),
                    "OK-ACCESS-TIMESTAMP": ts,
                    "OK-ACCESS-PASSPHRASE": self.passphrase or "",
                }
            )

        url = f"{self.base_url}{path_with_query}"
        response = self.session.request(
            method.upper(),
            url,
            data=body_str if body is not None else None,
            headers=headers,
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError as e:
            raise OkxError(
                f"Non-JSON response HTTP {response.status_code}: {response.text[:200]}",
            ) from e

        if not isinstance(payload, dict):
            raise OkxError(f"Unexpected OKX payload type: {type(payload)}")

        # HTTP errors still often return OKX JSON; surface both.
        code = str(payload.get("code", ""))
        if response.status_code >= 400 and code in {"", "0"}:
            raise OkxError(
                f"HTTP {response.status_code}: {payload}",
                code=str(response.status_code),
                payload=payload,
            )
        if code not in {"0", ""}:
            raise OkxError(
                f"OKX error code={code} msg={payload.get('msg')!r}",
                code=code,
                payload=payload,
            )
        return payload

    def get(
        self,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        return self.request("GET", path, params=params, auth=auth)

    def post(
        self,
        path: str,
        *,
        body: Optional[dict[str, Any] | list[Any]] = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        return self.request("POST", path, body=body, auth=auth)
