"""Registered CLI capabilities exposed to Agent instances."""

from .cli import CliTool
from .registry import get_cli, list_clis, register_cli

__all__ = ["CliTool", "get_cli", "list_clis", "register_cli"]
