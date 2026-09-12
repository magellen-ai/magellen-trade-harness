"""Load OKX credentials from instance / legacy secrets.env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


GLOBAL_SECRETS = Path.home() / ".config" / "magellen-trade-harness" / "secrets.env"

# Preferred names; aliases accepted for convenience.
_KEY_ALIASES = ("OKX_API_KEY", "OKX_APIKEY", "OKX_KEY")
_SECRET_ALIASES = ("OKX_API_SECRET", "OKX_SECRET_KEY", "OKX_API_SECRET_KEY", "OKX_SECRET")
_PASSPHRASE_ALIASES = ("OKX_PASSPHRASE", "OKX_API_PASSPHRASE")


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
            or (cur / "bin" / "okx").exists()
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


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        val = os.environ.get(name)
        if val:
            return val
    return None


def clean_secret_value(value: str) -> str:
    """Strip whitespace/quotes; tolerate ``KEY=="…"`` typos in .env files."""
    v = (value or "").strip()
    if v.startswith('="') and len(v) >= 2 and v.endswith('"'):
        v = v[2:-1]
    elif v.startswith("='") and len(v) >= 2 and v.endswith("'"):
        v = v[2:-1]
    elif len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
        v = v[1:-1]
    elif v.startswith("="):
        v = v[1:].strip().strip('"').strip("'")
    return v.strip()


def _load_repo_dotenv() -> None:
    """Best-effort: repo `.env` (never override existing env)."""
    try:
        root = Path(__file__).resolve().parents[3]
        env_path = root / ".env"
        if not env_path.exists():
            return
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            for key, value in parse_env_file(env_path).items():
                os.environ.setdefault(key, value)
    except Exception:
        pass


def _normalize_aliases() -> None:
    if not os.environ.get("OKX_API_KEY"):
        alt = _first_env(*_KEY_ALIASES)
        if alt:
            os.environ["OKX_API_KEY"] = alt
    if not os.environ.get("OKX_API_SECRET"):
        alt = _first_env(*_SECRET_ALIASES)
        if alt:
            os.environ["OKX_API_SECRET"] = alt
    if not os.environ.get("OKX_PASSPHRASE"):
        alt = _first_env(*_PASSPHRASE_ALIASES)
        if alt:
            os.environ["OKX_PASSPHRASE"] = alt
    for key in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"):
        if os.environ.get(key):
            os.environ[key] = clean_secret_value(os.environ[key])


def load_secrets_into_environ(*, require_creds: bool = True) -> tuple[dict[str, str], Path]:
    """Load secrets into os.environ (setdefault). Optionally require OKX keys.

    Order: process env → repo ``.env`` → instance/global ``secrets.env``.
    Accepts ``OKX_APIKEY`` as alias for ``OKX_API_KEY``.
    """
    _load_repo_dotenv()

    path = resolve_secrets_path()
    loaded: dict[str, str] = {}
    if path.exists():
        loaded = parse_env_file(path)
        for key, value in loaded.items():
            os.environ.setdefault(key, value)

    _normalize_aliases()

    if require_creds:
        missing = [
            name
            for name in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE")
            if not os.environ.get(name)
        ]
        if missing:
            raise ValueError(
                f"Missing {', '.join(missing)} (checked repo .env, {path}). "
                "Create a Demo Trading API key at OKX, then put "
                "OKX_API_KEY (or OKX_APIKEY) / OKX_API_SECRET / OKX_PASSPHRASE into "
                "repo .env, instances/<name>/agent/secrets.env, or "
                f"{GLOBAL_SECRETS}."
            )
    return loaded, path


def env_simulated_default() -> bool:
    """Default True (demo). Set OKX_SIMULATED=0 for live keys."""
    raw = (os.environ.get("OKX_SIMULATED") or "1").strip().lower()
    return raw not in {"0", "false", "no", "live", "prod", "production"}
