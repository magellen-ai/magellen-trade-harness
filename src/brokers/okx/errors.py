"""OKX broker errors."""

from __future__ import annotations

from typing import Any, Optional


class OkxError(RuntimeError):
    """Transport or API-level failure."""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


class OkxAuthError(OkxError):
    """Missing or invalid credentials."""
