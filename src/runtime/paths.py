"""Repository and instance paths.

Keeping path discovery in one module makes the runtime services independent of
the current working directory and gives tests a small, deterministic boundary.
The public helpers intentionally return :class:`~pathlib.Path` objects so
callers can still compose paths without another abstraction layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def repository_root() -> Path:
    """Return the checkout root containing ``pyproject.toml``."""

    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RepositoryPaths:
    """Stable locations used by the runtime configuration repository."""

    root: Path

    @classmethod
    def discover(cls) -> "RepositoryPaths":
        return cls(repository_root())

    @property
    def skills(self) -> Path:
        return self.root / "skills"

    @property
    def instances(self) -> Path:
        return self.root / "instances"

    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def harnesses(self) -> Path:
        return self.configs / "harnesses"

    @property
    def profiles(self) -> Path:
        return self.configs / "profiles"

    @property
    def agents(self) -> Path:
        return self.configs / "agents"

    @property
    def providers(self) -> Path:
        return self.configs / "providers"

    def instance(self, name: str) -> Path:
        return self.instances / name

    def harness(self, name: str) -> Path:
        return self.harnesses / name

    def profile(self, name: str) -> Path:
        return self.profiles / name

    def agent(self, name: str) -> Path:
        return self.agents / name

    def provider(self, name: str) -> Path:
        return self.providers / f"{name}.yaml"
