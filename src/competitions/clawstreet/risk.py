"""Risk gates for trade decisions (reasoning + soft notional limits)."""

from __future__ import annotations

from typing import Any, Optional

from .decision import Decision


class RiskGate:
    """Pre-order checks. Soft notional limits are guardrails, not precise risk.

    Soft-limit breaches: **live** orders are rejected; **dry-run** only warns.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.require_reasoning = self.config.get("require_reasoning", True)
        self.min_reasoning_chars = int(self.config.get("min_reasoning_chars", 10))
        self.default_dry_run = self.config.get("default_dry_run", True)
        soft = self.config.get("soft_limit_usd")
        self.soft_limit_usd = float(soft) if soft is not None else None
        per = self.config.get("per_order_max_usd")
        self.per_order_max_usd = float(per) if per is not None else None
        prefix = self.config.get("symbol_prefix")
        self.symbol_prefix = str(prefix) if prefix else None

    def check(
        self,
        decision: Decision,
        *,
        dry_run: bool = True,
        notional_usd: Optional[float] = None,
        used_notional_usd: float = 0.0,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate decision + optional soft limits.

        Returns ``(ok, error, warning)``. ``error`` blocks the order;
        ``warning`` is informational (printed by CLI).
        """
        is_valid, error = decision.validate()
        if not is_valid:
            return False, f"Decision validation failed: {error}", None

        if self.require_reasoning and len(decision.reasoning.strip()) < self.min_reasoning_chars:
            return (
                False,
                f"Reasoning must be at least {self.min_reasoning_chars} characters",
                None,
            )

        if self.symbol_prefix and not decision.symbol.startswith(self.symbol_prefix):
            msg = (
                f"Symbol '{decision.symbol}' must start with '{self.symbol_prefix}' "
                f"for this instance book"
            )
            if dry_run:
                return True, None, msg
            return False, msg, None

        warning: Optional[str] = None
        if notional_usd is not None:
            notional = abs(float(notional_usd))
            if self.per_order_max_usd is not None and notional > self.per_order_max_usd:
                msg = (
                    f"Per-order notional ${notional:.2f} exceeds "
                    f"per_order_max_usd ${self.per_order_max_usd:.2f}"
                )
                if dry_run:
                    warning = msg
                else:
                    return False, msg, None

            if self.soft_limit_usd is not None:
                projected = float(used_notional_usd)
                side = decision.side.lower()
                if side in ("buy", "short"):
                    projected += notional
                elif side in ("sell", "cover"):
                    projected -= notional
                if projected > self.soft_limit_usd + 1e-6:
                    msg = (
                        f"Book exposure ${projected:.2f} would exceed "
                        f"soft_limit_usd ${self.soft_limit_usd:.2f} "
                        f"(used ${used_notional_usd:.2f} + order ${notional:.2f})"
                    )
                    if dry_run:
                        warning = msg if warning is None else f"{warning}; {msg}"
                    else:
                        return False, msg, warning

        return True, None, warning

    def should_dry_run(self, force_live: bool = False) -> bool:
        if force_live:
            return False
        return bool(self.default_dry_run)
