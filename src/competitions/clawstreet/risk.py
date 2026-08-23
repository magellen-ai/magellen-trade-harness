"""Risk gates for trade decisions."""

from __future__ import annotations

from typing import Any, Optional

from .decision import Decision


class RiskGate:
    """Pre-order checks. Platform paper account sizing is left to the agent."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.require_reasoning = self.config.get("require_reasoning", True)
        self.min_reasoning_chars = int(self.config.get("min_reasoning_chars", 10))
        self.default_dry_run = self.config.get("default_dry_run", True)

    def check(self, decision: Decision) -> tuple[bool, Optional[str]]:
        is_valid, error = decision.validate()
        if not is_valid:
            return False, f"Decision validation failed: {error}"

        if self.require_reasoning and len(decision.reasoning.strip()) < self.min_reasoning_chars:
            return (
                False,
                f"Reasoning must be at least {self.min_reasoning_chars} characters",
            )

        return True, None

    def should_dry_run(self, force_live: bool = False) -> bool:
        if force_live:
            return False
        return bool(self.default_dry_run)
