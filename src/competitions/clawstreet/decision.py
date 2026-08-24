"""Decision schema for trade intents."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Decision:
    """Trade decision with reasoning and metadata.

    Platform order payload only uses symbol/side/qty/order_type/reasoning.
    Extra strategy fields stay in local audit / journal.
    """

    decision_id: str
    symbol: str
    side: str
    qty: float
    order_type: str
    reasoning: str
    thesis_source: str
    memo_path: Optional[str]
    created_at: str
    strategy: Optional[str] = None
    signals: Optional[dict[str, Any]] = None
    invalidation: Optional[str] = None
    size_hint: Optional[float] = None
    book_tag: Optional[str] = None

    @classmethod
    def create(
        cls,
        symbol: str,
        side: str,
        qty: float,
        reasoning: str,
        order_type: str = "market",
        thesis_source: str = "manual",
        memo_path: Optional[str] = None,
        strategy: Optional[str] = None,
        signals: Optional[dict[str, Any]] = None,
        invalidation: Optional[str] = None,
        size_hint: Optional[float] = None,
        book_tag: Optional[str] = None,
    ) -> "Decision":
        return cls(
            decision_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            reasoning=reasoning,
            thesis_source=thesis_source,
            memo_path=memo_path,
            created_at=datetime.now(timezone.utc).isoformat(),
            strategy=strategy,
            signals=signals,
            invalidation=invalidation,
            size_hint=size_hint,
            book_tag=book_tag,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> tuple[bool, Optional[str]]:
        if not self.reasoning or not self.reasoning.strip():
            return False, "reasoning is required and cannot be empty"

        if self.side not in ("buy", "sell", "short", "cover"):
            return False, f"side must be buy|sell|short|cover, got '{self.side}'"

        if self.qty <= 0:
            return False, f"qty must be positive, got {self.qty}"

        return True, None
