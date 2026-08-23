"""Optional local audit log (not a substitute for platform orders/fills)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from .secrets import find_instance_root


class AuditLog:
    """Append-only local copy of intents. Prefer GET fills/orders for history."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            inst = find_instance_root()
            if inst is None:
                self.path = None
                return
            path = str(inst / "audit" / "events.jsonl")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def write_event(
        self,
        event: str,
        decision: dict[str, Any],
        order_response: dict[str, Any],
        dry_run: bool,
        competition: str = "clawstreet",
    ) -> None:
        if not self.enabled or self.path is None:
            return

        order = order_response.get("order") if isinstance(order_response, dict) else None
        order_id = None
        if isinstance(order, dict):
            order_id = order.get("id")
        if order_id is None and isinstance(order_response, dict):
            order_id = order_response.get("order_id")

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "competition": competition,
            "decision_id": decision.get("decision_id"),
            "symbol": decision.get("symbol"),
            "side": decision.get("side"),
            "qty": decision.get("qty"),
            "reasoning": decision.get("reasoning"),
            "dry_run": dry_run,
            "order_id": order_id,
            "idempotency_key": order_response.get("idempotency_key")
            if isinstance(order_response, dict)
            else None,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_entries(self, limit: Optional[int] = None) -> List[dict[str, Any]]:
        if not self.enabled or self.path is None or not self.path.exists():
            return []
        entries: List[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        entries.reverse()
        if limit is not None:
            entries = entries[:limit]
        return entries
