"""Resolve ClawStreet secrets for the current harness instance / legacy global path."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


GLOBAL_SECRETS = Path.home() / ".config" / "magellen-trade-harness" / "secrets.env"


def find_instance_root(start: Optional[Path] = None) -> Optional[Path]:
    """Resolve harness instance root (HARNESS_INSTANCE first, then cwd walk)."""
    env = os.environ.get("HARNESS_INSTANCE")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p

    cur = (start or Path.cwd()).resolve()
    for _ in range(6):
        if (cur / "config.yaml").exists() and (
            (cur / "agent").is_dir()
            or (cur / "bin" / "clawstreet").exists()
            or (cur / "bin" / "harness").exists()
        ):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def agent_dir(instance_root: Path) -> Path:
    return instance_root / "agent"


def instance_secrets_path(instance_root: Path) -> Path:
    return agent_dir(instance_root) / "secrets.env"


def parse_env_file(path: Path) -> dict[str, str]:
    secrets: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip()
    return secrets


def resolve_secrets_path() -> Path:
    """Prefer instance agent/secrets.env, then legacy global store."""
    inst = find_instance_root()
    if inst is not None:
        path = instance_secrets_path(inst)
        if path.exists():
            return path
    if GLOBAL_SECRETS.exists():
        return GLOBAL_SECRETS
    if inst is not None:
        # Point at the expected path even if missing (caller errors with hint).
        return instance_secrets_path(inst)
    return GLOBAL_SECRETS


def load_secrets_into_environ() -> tuple[dict[str, str], Path]:
    path = resolve_secrets_path()
    if not path.exists():
        raise FileNotFoundError(
            f"secrets not found at {path}. "
            "Put CLAWSTREET_API_KEY and CLAWSTREET_AGENT_ID in "
            "instances/<name>/agent/secrets.env (preferred) or "
            f"{GLOBAL_SECRETS}. Or run: uv run clawstreet register --instance <name>"
        )
    secrets = parse_env_file(path)
    for key, value in secrets.items():
        os.environ[key] = value
    if not os.environ.get("CLAWSTREET_API_KEY"):
        raise ValueError(f"CLAWSTREET_API_KEY missing in {path}")
    if not os.environ.get("CLAWSTREET_AGENT_ID") and os.environ.get("CLAWSTREET_BOT_ID"):
        os.environ["CLAWSTREET_AGENT_ID"] = os.environ["CLAWSTREET_BOT_ID"]
    return secrets, path
