"""Instance + ledger path resolution for paper_ashare."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

GLOBAL_SECRETS = Path.home() / ".config" / "magellen-trade-harness" / "secrets.env"
GLOBAL_LEDGER_DIR = Path.home() / ".config" / "magellen-trade-harness" / "paper_ashare"


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


def ledger_dir(instance_root: Optional[Path] = None) -> Path:
    inst = instance_root if instance_root is not None else find_instance_root()
    if inst is not None:
        path = inst / "paper_ashare"
    else:
        path = GLOBAL_LEDGER_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def ledger_path(account: str = "default", instance_root: Optional[Path] = None) -> Path:
    safe = account.strip().replace("/", "_").replace("..", "_") or "default"
    return ledger_dir(instance_root) / f"{safe}.sqlite"


def parse_env_file(path: Path) -> dict[str, str]:
    secrets: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip()
    return secrets


def load_secrets_into_environ() -> None:
    """Best-effort: repo `.env` then instance/global secrets (never override)."""
    try:
        root = Path(__file__).resolve().parents[3]
        env_path = root / ".env"
        if env_path.exists():
            try:
                from dotenv import load_dotenv

                load_dotenv(env_path, override=False)
            except ImportError:
                pass
    except Exception:
        pass

    inst = find_instance_root()
    candidates: list[Path] = []
    if inst is not None:
        candidates.append(inst / "agent" / "secrets.env")
    candidates.append(GLOBAL_SECRETS)
    for path in candidates:
        if path.exists():
            for key, value in parse_env_file(path).items():
                os.environ.setdefault(key, value)
            return
