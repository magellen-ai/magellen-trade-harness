"""Trade decision schema for paper_ashare."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Decision:
    decision_id: str
    symbol: str
    side: str
    qty: int
    order_type: str
    reasoning: str
    created_at: str
    limit_price: Optional[float] = None

    @classmethod
    def create(
        cls,
        symbol: str,
        side: str,
        qty: int,
        reasoning: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> "Decision":
        return cls(
            decision_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            qty=int(qty),
            order_type=order_type,
            reasoning=reasoning,
            created_at=datetime.now(timezone.utc).isoformat(),
            limit_price=limit_price,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> tuple[bool, Optional[str]]:
        if not self.reasoning or not self.reasoning.strip():
            return False, "reasoning is required and cannot be empty"
        if self.side not in ("buy", "sell"):
            return False, f"side must be buy|sell, got '{self.side}'"
        if self.qty <= 0:
            return False, f"qty must be positive, got {self.qty}"
        if self.qty % 100 != 0:
            return False, f"qty must be multiple of 100, got {self.qty}"
        return True, None
