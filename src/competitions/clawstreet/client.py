"""ClawStreet API client."""

from __future__ import annotations

import os
import uuid
from typing import Any, Optional

import requests


class ClawStreetClient:
    """Thin client for ClawStreet paper trading API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: float = 20.0,
    ):
        self.base_url = "https://www.clawstreet.io"
        self.api_key = api_key or os.getenv("CLAWSTREET_API_KEY")
        self.agent_id = agent_id or os.getenv("CLAWSTREET_AGENT_ID") or os.getenv(
            "CLAWSTREET_BOT_ID"
        )
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("CLAWSTREET_API_KEY not provided or found in environment")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def get_me(self) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/v1/me", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_portfolio(self, agent_id: Optional[str] = None) -> dict[str, Any]:
        aid = agent_id or self.agent_id
        if not aid:
            raise ValueError("agent_id not provided and not set in client")
        response = self.session.get(
            f"{self.base_url}/v1/me/agents/{aid}/portfolio",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        joined = ",".join(symbols)
        response = self.session.get(
            f"{self.base_url}/v1/quotes",
            params={"symbols": joined},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def list_orders(self, agent_id: Optional[str] = None, limit: int = 10) -> dict[str, Any]:
        aid = agent_id or self.agent_id
        if not aid:
            raise ValueError("agent_id not provided and not set in client")
        response = self.session.get(
            f"{self.base_url}/v1/me/agents/{aid}/orders",
            params={"limit": limit},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def list_fills(self, agent_id: Optional[str] = None, limit: int = 10) -> dict[str, Any]:
        aid = agent_id or self.agent_id
        if not aid:
            raise ValueError("agent_id not provided and not set in client")
        response = self.session.get(
            f"{self.base_url}/v1/me/agents/{aid}/fills",
            params={"limit": limit},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def create_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        reasoning: str,
        order_type: str = "market",
        agent_id: Optional[str] = None,
        dry_run: bool = False,
        idempotency_key: Optional[str] = None,
        instance_prefix: Optional[str] = None,
    ) -> dict[str, Any]:
        aid = agent_id or self.agent_id
        if not aid:
            raise ValueError("agent_id not provided and not set in client")

        payload = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "reasoning": reasoning,
        }

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "order_id": "dry-run-mock",
                "status": "pending",
                "message": "Dry-run mode: order not sent to ClawStreet",
                "payload": payload,
            }

        if idempotency_key:
            key = idempotency_key
        elif instance_prefix:
            key = f"{instance_prefix}--{uuid.uuid4()}"
        else:
            key = str(uuid.uuid4())
        response = self.session.post(
            f"{self.base_url}/v1/me/agents/{aid}/orders",
            json=payload,
            headers={"Idempotency-Key": key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        result["dry_run"] = False
        result["idempotency_key"] = key
        return result

    def get_market_status(self) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/api/market-status",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
