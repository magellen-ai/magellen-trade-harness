from __future__ import annotations

from .cli import CliTool

_REGISTRY: dict[str, type[CliTool]] = {}


def register_cli(cls: type[CliTool]) -> type[CliTool]:
    if not cls.id or not cls.executable:
        raise ValueError("CLI tool requires id and executable")
    if cls.id in _REGISTRY:
        raise ValueError(f"CLI already registered: {cls.id}")
    _REGISTRY[cls.id] = cls
    return cls


def _load_builtins() -> None:
    from . import builtins  # noqa: F401


def list_clis() -> list[str]:
    _load_builtins()
    return sorted(_REGISTRY)


def get_cli(tool_id: str) -> CliTool:
    _load_builtins()
    try:
        return _REGISTRY[tool_id]()
    except KeyError as exc:
        raise KeyError(f"unknown CLI tool {tool_id!r}; available: {list_clis()}") from exc
