"""Pure schedule trigger parsing.

This module has no filesystem or process side effects.  Keeping interval and
cron semantics here lets the schedule runner concentrate on persistence and
execution, and makes trigger behavior easy to test in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


_INTERVAL_RE = re.compile(r"^(\d+)\s*(s|m|h|d)$")
_INTERVAL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_CRON_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def parse_interval(text: str) -> int:
    """Parse ``30s`` / ``5m`` / ``4h`` / ``1d`` as seconds."""

    match = _INTERVAL_RE.match(str(text).strip())
    if not match:
        raise ValueError(
            f"bad interval {text!r} (expected e.g. 30s / 5m / 4h / 1d)"
        )
    seconds = int(match.group(1)) * _INTERVAL_UNITS[match.group(2)]
    if seconds <= 0:
        raise ValueError(f"interval must be positive: {text!r}")
    return seconds


@dataclass(frozen=True)
class CronSpec:
    minute: frozenset[int]
    hour: frozenset[int]
    dom: frozenset[int]
    month: frozenset[int]
    dow: frozenset[int]
    dom_star: bool
    dow_star: bool


def _parse_cron_field(field: str, lo: int, hi: int) -> tuple[frozenset[int], bool]:
    """Parse numeric cron ``*``, lists, ranges and steps."""

    values: set[int] = set()
    is_star = field == "*"
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"bad step in {field!r}")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start < lo or end > hi or start > end:
            raise ValueError(f"value out of range [{lo},{hi}] in {field!r}")
        values.update(range(start, end + 1, step))
    return frozenset(values), is_star


def parse_cron(expr: str) -> CronSpec:
    """Parse a five-field numeric cron expression."""

    fields = str(expr).split()
    if len(fields) != 5:
        raise ValueError(
            f"bad cron {expr!r}: need 5 fields (minute hour dom month dow), numeric only"
        )
    parsed: list[frozenset[int]] = []
    stars: list[bool] = []
    for field, (lo, hi) in zip(fields, _CRON_BOUNDS):
        try:
            values, is_star = _parse_cron_field(field, lo, hi)
        except ValueError as exc:
            raise ValueError(f"bad cron {expr!r}: {exc}") from None
        parsed.append(values)
        stars.append(is_star)
    dow = frozenset(0 if value == 7 else value for value in parsed[4])
    return CronSpec(
        minute=parsed[0],
        hour=parsed[1],
        dom=parsed[2],
        month=parsed[3],
        dow=dow,
        dom_star=stars[2],
        dow_star=stars[4],
    )


def cron_matches(spec: CronSpec, dt: datetime) -> bool:
    """Return whether ``dt`` matches a parsed cron expression."""

    if dt.minute not in spec.minute or dt.hour not in spec.hour:
        return False
    if dt.month not in spec.month:
        return False
    dom_ok = dt.day in spec.dom
    dow_ok = ((dt.weekday() + 1) % 7) in spec.dow
    # Standard cron: if both dom and dow are restricted, either may match.
    if spec.dom_star and spec.dow_star:
        return True
    if spec.dom_star:
        return dow_ok
    if spec.dow_star:
        return dom_ok
    return dom_ok or dow_ok


__all__ = ["CronSpec", "cron_matches", "parse_cron", "parse_interval"]
