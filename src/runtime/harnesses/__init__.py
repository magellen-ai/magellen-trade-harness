"""Programmatic harness adapter registry.

Adapters are intentionally thin: the existing harness YAML remains the source
of launch/materialization details while this package provides a stable lookup
point for future runtime-specific behavior.
"""

from .base import HarnessAdapter, get_adapter

__all__ = ["HarnessAdapter", "get_adapter"]
