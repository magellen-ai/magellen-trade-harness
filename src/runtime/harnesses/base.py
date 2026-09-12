"""Small adapter boundary shared by Agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HarnessAdapter:
    """Runtime identity and declarative harness configuration.

    Runtime-specific launch behavior remains in the harness config until an
    adapter needs to override it; this avoids a second configuration system.
    """

    id: str
    config: dict[str, Any]

    @property
    def context_file(self) -> str:
        return str(self.config.get("agent_context") or "AGENTS.md")

    def launch(self, instance_dir: Path) -> list[str]:
        del instance_dir
        launch = self.config.get("launch") or {}
        argv = launch.get("argv") if isinstance(launch, dict) else None
        if not isinstance(argv, list) or not argv:
            raise ValueError(f"harness {self.id!r} has no launch.argv")
        return [str(x) for x in argv]


def get_adapter(harness_id: str) -> HarnessAdapter:
    """Load one adapter from the existing harness declaration."""
    from ..instance import load_harness

    return HarnessAdapter(harness_id, load_harness(harness_id))
