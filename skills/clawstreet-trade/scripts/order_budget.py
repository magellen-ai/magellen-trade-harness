#!/usr/bin/env python3
"""Count today's local order intents from audit/events.jsonl (daily budget helper)."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ORDER_EVENTS = {"order.dry_run", "order.submitted", "order.rejected"}


def _local_zone():
    try:
        return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")
    except Exception:  # noqa: BLE001
        return timezone.utc


def _parse_ts(raw: str) -> date | None:
    if not raw:
        return None
    try:
        # accept ...Z or +08:00; budget day = local calendar date
        ts = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_local_zone()).date()
    except ValueError:
        return None


def main(argv: list[str]) -> int:
    limit = 20
    audit = Path("audit/events.jsonl")
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
            continue
        if args[i] == "--audit" and i + 1 < len(args):
            audit = Path(args[i + 1])
            i += 2
            continue
        if args[i] in ("-h", "--help"):
            print(
                "Usage: order_budget.py [--limit 20] [--audit audit/events.jsonl]",
                file=sys.stderr,
            )
            return 2
        print(f"unknown arg: {args[i]}", file=sys.stderr)
        return 2

    today = date.today()
    count = 0
    dry = 0
    live = 0
    if audit.is_file():
        for line in audit.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = row.get("event") or row.get("type")
            if ev not in ORDER_EVENTS:
                continue
            d = _parse_ts(str(row.get("ts") or row.get("timestamp") or ""))
            if d != today:
                continue
            count += 1
            if row.get("dry_run", True) or ev == "order.dry_run":
                dry += 1
            else:
                live += 1

    remaining = max(0, limit - count)
    out = {
        "ok": True,
        "date": today.isoformat(),
        "limit": limit,
        "used": count,
        "dry_run": dry,
        "live": live,
        "remaining": remaining,
        "blocked": remaining <= 0,
        "audit": str(audit),
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0 if remaining > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
