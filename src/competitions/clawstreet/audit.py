"""Optional local audit log (not a substitute for platform orders/fills)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from .secrets import find_instance_root


# Live events that contribute to book notional exposure.
_EXPOSURE_EVENTS = frozenset({"order.submitted"})
# Dry-run intents counted separately for the day.
_DRY_RUN_EVENTS = frozenset({"order.dry_run"})


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
        *,
        instance: Optional[str] = None,
        book_tag: Optional[str] = None,
        strategy: Optional[str] = None,
        notional_usd: Optional[float] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        if not self.enabled or self.path is None:
            return

        order = order_response.get("order") if isinstance(order_response, dict) else None
        order_id = None
        if isinstance(order, dict):
            order_id = order.get("id")
        if order_id is None and isinstance(order_response, dict):
            order_id = order_response.get("order_id")

        if instance is None:
            root = find_instance_root()
            instance = root.name if root is not None else None

        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "competition": competition,
            "instance": instance,
            "book_tag": book_tag or decision.get("book_tag"),
            "strategy": strategy or decision.get("strategy"),
            "decision_id": decision.get("decision_id"),
            "symbol": decision.get("symbol"),
            "side": decision.get("side"),
            "qty": decision.get("qty"),
            "notional_usd": notional_usd,
            "reasoning": decision.get("reasoning"),
            "signals": decision.get("signals"),
            "invalidation": decision.get("invalidation"),
            "size_hint": decision.get("size_hint"),
            "dry_run": dry_run,
            "order_id": order_id,
            "idempotency_key": order_response.get("idempotency_key")
            if isinstance(order_response, dict)
            else None,
        }
        if isinstance(order_response, dict) and order_response.get("reason"):
            entry["reason"] = order_response.get("reason")
        if extra:
            entry.update(extra)

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_entries(
        self,
        limit: Optional[int] = None,
        *,
        book_tag: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        if not self.enabled or self.path is None or not self.path.exists():
            return []
        entries: List[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        if book_tag is not None:
            entries = [e for e in entries if e.get("book_tag") == book_tag]
        entries.reverse()
        if limit is not None:
            entries = entries[:limit]
        return entries


def _signed_notional(side: Optional[str], notional: float) -> float:
    """Buy/short add exposure; sell/cover reduce."""
    s = (side or "").lower()
    if s in ("buy", "short"):
        return notional
    if s in ("sell", "cover"):
        return -notional
    return 0.0


def _entry_notional(entry: dict[str, Any]) -> Optional[float]:
    raw = entry.get("notional_usd")
    if raw is None:
        return None
    try:
        return abs(float(raw))
    except (TypeError, ValueError):
        return None


def _ts_date(ts: Optional[str]) -> Optional[date]:
    if not ts:
        return None
    try:
        # Accept trailing Z
        cleaned = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        return None


def compute_exposure(
    entries: List[dict[str, Any]],
    *,
    book_tag: Optional[str] = None,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Aggregate book exposure from audit entries (tolerant of legacy rows).

    Live used notional = sum of signed notionals on ``order.submitted``.
    Dry-run day intent = sum of abs notionals on today's ``order.dry_run``.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()

    live_used = 0.0
    live_count = 0
    dry_day = 0.0
    dry_day_count = 0
    skipped_no_notional = 0

    for entry in entries:
        if book_tag is not None and entry.get("book_tag") != book_tag:
            continue
        event = entry.get("event")
        notional = _entry_notional(entry)
        if event in _EXPOSURE_EVENTS and not entry.get("dry_run", False):
            if notional is None:
                skipped_no_notional += 1
                continue
            live_used += _signed_notional(entry.get("side"), notional)
            live_count += 1
        elif event in _DRY_RUN_EVENTS:
            entry_day = _ts_date(entry.get("ts"))
            if entry_day != today:
                continue
            if notional is None:
                skipped_no_notional += 1
                continue
            dry_day += notional
            dry_day_count += 1

    return {
        "book_tag": book_tag,
        "live_used_usd": round(live_used, 4),
        "live_order_count": live_count,
        "dry_run_intent_usd_today": round(dry_day, 4),
        "dry_run_order_count_today": dry_day_count,
        "skipped_missing_notional": skipped_no_notional,
    }
