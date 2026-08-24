#!/usr/bin/env python3
"""One-page daily digest: schedule journal + audit + exposure (T5)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _ensure_import() -> None:
    try:
        import competitions.clawstreet  # noqa: F401
        return
    except ImportError:
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "src"
        if (candidate / "competitions" / "clawstreet").is_dir():
            sys.path.insert(0, str(candidate))
            return


def _parse_day(ts: str) -> Optional[date]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Daily always-on digest")
    parser.add_argument("--day", help="UTC date YYYY-MM-DD (default today)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])

    _ensure_import()
    from competitions.clawstreet.audit import AuditLog, compute_exposure
    from competitions.clawstreet.cli import load_config
    from competitions.clawstreet.secrets import find_instance_root

    inst = find_instance_root()
    if inst is None:
        print("Error: no instance root", file=sys.stderr)
        return 1

    day = date.fromisoformat(args.day) if args.day else datetime.now(timezone.utc).date()
    config = load_config()
    book_tag = config.get("book_tag")

    audit = AuditLog(str(inst / "audit" / "events.jsonl"))
    entries = audit.read_entries(limit=None) if audit.enabled else []
    day_audit = [e for e in entries if _parse_day(str(e.get("ts") or "")) == day]
    events = Counter(str(e.get("event")) for e in day_audit)

    exp = compute_exposure(entries, book_tag=book_tag)

    sched_path = inst / "schedule" / "state" / "journal.jsonl"
    sched_events: Counter[str] = Counter()
    sched_rules: Counter[str] = Counter()
    if sched_path.exists():
        for line in sched_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _parse_day(str(row.get("ts") or "")) != day:
                continue
            sched_events[str(row.get("event") or row.get("kind") or "?")] += 1
            if row.get("rule"):
                sched_rules[str(row["rule"])] += 1

    journal_path = inst / "memory" / "trade-journal.md"
    journal_lines = 0
    if journal_path.exists():
        text = journal_path.read_text(encoding="utf-8")
        # crude: count day headers
        journal_lines = text.count(str(day)) + text.count(day.isoformat())

    summary: dict[str, Any] = {
        "day": day.isoformat(),
        "instance": inst.name,
        "book_tag": book_tag,
        "schedule_events": dict(sched_events),
        "schedule_rules": dict(sched_rules),
        "audit_events": dict(events),
        "audit_entries_today": len(day_audit),
        "exposure": exp,
        "soft_limit_usd": config.get("soft_limit_usd"),
        "trade_journal_day_mentions": journal_lines,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(f"# Daily digest — {inst.name} — {day.isoformat()} (UTC)")
    print()
    print(f"Book tag: {book_tag}")
    print(f"Soft limit: {config.get('soft_limit_usd')}")
    print(f"Live used: ${float(exp['live_used_usd']):.2f}")
    print(f"Dry-run intent today: ${float(exp['dry_run_intent_usd_today']):.2f}")
    print()
    print("Schedule events:", dict(sched_events) or "(none)")
    print("Schedule by rule:", dict(sched_rules) or "(none)")
    print("Audit events:", dict(events) or "(none)")
    print(f"Audit entries today: {len(day_audit)}")
    print(f"Trade-journal day mentions: {journal_lines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
