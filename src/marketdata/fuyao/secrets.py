"""Load Fuyao / HiThink API key from instance or global secrets.env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

GLOBAL_SECRETS = Path.home() / ".config" / "magellen-trade-harness" / "secrets.env"
# Prefer HITHINK_FINANCE_API_KEY (official env name); FUYAO_API_KEY is an alias.
API_KEY_ENVS = ("HITHINK_FINANCE_API_KEY", "FUYAO_API_KEY", "HITHINK_API_KEY")


def find_instance_root(start: Optional[Path] = None) -> Optional[Path]:
    env = os.environ.get("HARNESS_INSTANCE")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p

    cur = (start or Path.cwd()).resolve()
    for _ in range(6):
        if (cur / "config.yaml").exists() and (
            (cur / "agent").is_dir()
            or (cur / "bin" / "harness").exists()
            or (cur / "bin" / "clawstreet").exists()
        ):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


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
    inst = find_instance_root()
    if inst is not None:
        path = inst / "agent" / "secrets.env"
        if path.exists():
            return path
    if GLOBAL_SECRETS.exists():
        return GLOBAL_SECRETS
    if inst is not None:
        return inst / "agent" / "secrets.env"
    return GLOBAL_SECRETS


def _load_repo_dotenv() -> None:
    """Best-effort: repo-root `.env` without overriding existing env."""
    try:
        from pathlib import Path as _Path

        root = _Path(__file__).resolve().parents[3]
        env_path = root / ".env"
        if not env_path.exists():
            return
        try:
            from dotenv import load_dotenv
        except ImportError:
            return
        load_dotenv(env_path, override=False)
    except Exception:
        return


def load_secrets_into_environ() -> tuple[dict[str, str], Path]:
    _load_repo_dotenv()
    path = resolve_secrets_path()
    secrets: dict[str, str] = {}
    if path.exists():
        secrets = parse_env_file(path)
        for key, value in secrets.items():
            os.environ.setdefault(key, value)
    return secrets, path


def resolve_api_key() -> Optional[str]:
    load_secrets_into_environ()
    for name in API_KEY_ENVS:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None
