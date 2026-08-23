"""Harness instance scaffolding (runtime workdirs are gitignored)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore


# Model / proxy routing defaults for isolated `--setting-sources project` sessions.
# Values may use $VAR / ${VAR}; resolved from repo `.env` + process env at sync time.
# Keep this public-safe; put personal proxy model aliases in instance config.yaml (gitignored).
DEFAULT_CC_ENV: dict[str, str] = {
    "ANTHROPIC_BASE_URL": "$ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL": "$ANTHROPIC_MODEL",
    "ENABLE_TOOL_SEARCH": "true",
}

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def skills_root() -> Path:
    return repo_root() / "skills"


def instances_root() -> Path:
    return repo_root() / "instances"


def load_repo_dotenv(*, override: bool = False) -> Path:
    """Load repo-root `.env` into os.environ (does not print values)."""
    path = repo_root() / ".env"
    if load_dotenv is None:
        raise RuntimeError("python-dotenv is required (uv sync installs it).")
    if path.exists():
        load_dotenv(path, override=override)
    return path


def expand_env_refs(value: str) -> tuple[str, list[str]]:
    """Expand $VAR / ${VAR}. Returns (expanded, missing_names)."""
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        if name not in os.environ or os.environ.get(name) == "":
            missing.append(name)
            return match.group(0)
        return os.environ[name]

    return _ENV_REF.sub(repl, value), missing


def default_instance_config(name: str, skills: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "runtime": "claude-code",
        "model": "claude",
        "skills": skills,
        "memory": {"kind": "files", "path": "memory"},
        "schedule": None,
        "competition": "clawstreet",
        "agent": {
            "secrets_env": "agent/secrets.env",
            "notes": "One ClawStreet agent per instance (separate paper account).",
        },
        "trade": {
            "cli": "bin/clawstreet",
            "default_dry_run": True,
        },
        # Written into .claude/settings.json → env after $VAR expansion from repo .env
        "cc-env": dict(DEFAULT_CC_ENV),
        "launch": {
            "setting_sources": "project,local",
            "notes": (
                "cc-env supports $VAR / ${VAR}; values come from repo .env + process env."
            ),
        },
    }


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required (uv sync installs it).")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required (uv sync installs it).")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def list_available_skills() -> list[str]:
    root = skills_root()
    if not root.exists():
        return []
    names = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            names.append(child.name)
    return names


def _link_skill(skill_name: str, dest_dir: Path) -> None:
    src = skills_root() / skill_name
    if not (src / "SKILL.md").exists():
        raise FileNotFoundError(f"skill not found in skills/: {skill_name}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / skill_name
    if dest.is_symlink() or dest.exists():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.symlink_to(src.resolve(), target_is_directory=True)


def _write_uv_wrapper(instance_dir: Path, script_name: str) -> Path:
    bin_dir = instance_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / script_name
    root = repo_root()
    content = f"""#!/usr/bin/env bash
set -euo pipefail
ROOT="{root}"
INSTANCE="{instance_dir.resolve()}"
export HARNESS_INSTANCE="$INSTANCE"
cd "$ROOT"
exec uv run {script_name} "$@"
"""
    wrapper.write_text(content, encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | 0o111)
    return wrapper


def build_claude_env(cfg: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Expand cc-env values ($VAR) using repo .env + process env.

    Returns (resolved_env, missing_var_names).
    """
    load_repo_dotenv(override=False)
    env: dict[str, str] = {}
    missing: list[str] = []
    raw = cfg.get("cc-env") or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if v is None:
                continue
            expanded, miss = expand_env_refs(str(v))
            missing.extend(miss)
            # Skip unresolved refs so we don't write literal "$FOO" into Claude settings.
            if miss:
                continue
            env[str(k)] = expanded
    # unique missing, stable order
    seen: set[str] = set()
    uniq_missing: list[str] = []
    for name in missing:
        if name not in seen:
            seen.add(name)
            uniq_missing.append(name)
    return env, uniq_missing


def write_claude_settings(instance_dir: Path, cfg: Optional[dict[str, Any]] = None) -> Path:
    """Write .claude/settings.json from config cc-env after $VAR expansion."""
    if cfg is None:
        cfg = load_yaml(instance_dir / "config.yaml")

    claude_dir = instance_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except json.JSONDecodeError:
            existing = {}

    env, _missing = build_claude_env(cfg)
    settings: dict[str, Any] = {
        **existing,
        "env": env,
        "permissions": existing.get("permissions")
        or {
            "allow": [
                "Bash(./bin/clawstreet *)",
                "Bash(bin/clawstreet *)",
                "Bash(./bin/harness *)",
                "Bash(bin/harness *)",
                "Bash(uv run clawstreet *)",
                "Bash(uv run harness *)",
            ]
        },
    }

    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(settings_path, 0o600)
    return settings_path


def _write_agent_readme(instance_dir: Path) -> None:
    readme = instance_dir / "agent" / "README.md"
    readme.write_text(
        """# Agent credentials (this instance)

Isolation unit = **one ClawStreet agent** (paper account), bound to this harness instance.

## Option A — register a new agent (human or AI)

```bash
uv run clawstreet register --instance <this-instance-name>
```

Then open `claim_url` from `agent/public.json`, claim in browser, verify:

```bash
./bin/clawstreet status
```

## Option B — paste an existing key

Create `agent/secrets.env` (mode 600):

```env
CLAWSTREET_API_KEY=...
CLAWSTREET_AGENT_ID=...
```

Never print the key. Never commit it (`instances/` is gitignored).

## History

Platform source of truth: `uv run clawstreet fills` / `orders`.  
Optional local audit: `audit/events.jsonl` (not a substitute for platform APIs).
""",
        encoding="utf-8",
    )


def _write_instance_agents(instance_dir: Path, name: str, skills: list[str]) -> None:
    agents = instance_dir / "AGENTS.md"
    agents.write_text(
        f"""# instance: {name}

## Can do

- Prefer CLI: `./bin/clawstreet status|portfolio|order|fills|orders`
- Raw HTTP when needed: `uv run clawstreet http-docs`
- Secrets: `agent/secrets.env` (this instance's ClawStreet agent)
- Claude model/proxy: `config.yaml` → `cc-env` (`$VAR` from repo `.env`)
- Skills: {", ".join(skills) or "(none)"}

## Bind / create agent

See `agent/README.md`. Register:

```bash
uv run clawstreet register --instance {name}
```

## Launch

```bash
# ensure repo .env has ANTHROPIC_* then:
uv run harness instance sync-settings {name}
uv run harness instance launch {name}
```
""",
        encoding="utf-8",
    )
    (instance_dir / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")


def init_instance(
    name: str,
    skills: Optional[list[str]] = None,
    force: bool = False,
) -> Path:
    if not name or "/" in name or name in (".", ".."):
        raise ValueError(f"invalid instance name: {name!r}")

    available = list_available_skills()
    selected = skills if skills is not None else available
    unknown = [s for s in selected if s not in available]
    if unknown:
        raise FileNotFoundError(f"unknown skills {unknown}; available={available}")

    instance_dir = instances_root() / name
    if instance_dir.exists() and not force:
        raise FileExistsError(
            f"instance already exists: {instance_dir} (pass --force to recreate links/config)"
        )

    for sub in (
        "workdir",
        "audit",
        "logs",
        "memory",
        "agent",
        ".claude/skills",
        ".agents/skills",
    ):
        (instance_dir / sub).mkdir(parents=True, exist_ok=True)

    cfg_path = instance_dir / "config.yaml"
    if not cfg_path.exists() or force:
        write_yaml(cfg_path, default_instance_config(name, selected))

    cfg = load_yaml(cfg_path)
    if force:
        cfg["cc-env"] = dict(DEFAULT_CC_ENV)
        cfg.pop("cc-env-from-host", None)
        write_yaml(cfg_path, cfg)

    selected = list(cfg.get("skills") or selected)

    for skill in selected:
        _link_skill(skill, instance_dir / ".claude" / "skills")
        _link_skill(skill, instance_dir / ".agents" / "skills")

    _write_uv_wrapper(instance_dir, "clawstreet")
    _write_uv_wrapper(instance_dir, "harness")
    legacy = instance_dir / "bin" / "mth"
    if legacy.exists() or legacy.is_symlink():
        legacy.unlink()

    _write_agent_readme(instance_dir)
    _write_instance_agents(instance_dir, name, selected)

    old_journal = instance_dir / "journal"
    if old_journal.is_dir() and not any(old_journal.iterdir()):
        old_journal.rmdir()

    write_claude_settings(instance_dir, cfg)

    # Optional local overrides (permissions tweaks); project settings hold cc-env.
    local_settings = instance_dir / ".claude" / "settings.local.json"
    if not local_settings.exists() or force:
        local_settings.write_text(
            '{\n  "permissions": {\n'
            '    "allow": ["Bash(./bin/clawstreet *)", "Bash(bin/clawstreet *)",'
            ' "Bash(./bin/harness *)", "Bash(bin/harness *)",'
            ' "Bash(uv run clawstreet *)", "Bash(uv run harness *)"]\n'
            "  }\n}\n",
            encoding="utf-8",
        )

    return instance_dir


def sync_claude_settings(name: str) -> Path:
    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    cfg = load_yaml(instance_dir / "config.yaml")
    return write_claude_settings(instance_dir, cfg)


def launch_command(name: str) -> list[str]:
    instance_dir = instances_root() / name
    cfg_path = instance_dir / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"instance config missing: {cfg_path}")
    cfg = load_yaml(cfg_path)
    sources = (cfg.get("launch") or {}).get("setting_sources") or "project,local"
    return ["claude", "--setting-sources", sources]


def launch_instance(name: str, dry_print: bool = False) -> int:
    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    # Refresh settings so host ANTHROPIC_BASE_URL / API key are current.
    settings_path = sync_claude_settings(name)
    cmd = launch_command(name)
    if dry_print:
        print(f"cd {instance_dir}")
        print(f"export HARNESS_INSTANCE={instance_dir}")
        print(f"# synced Claude settings → {settings_path}")
        print(" ".join(cmd))
        return 0
    print(f"Launching in {instance_dir}: {' '.join(cmd)}", file=sys.stderr)
    print(f"# synced Claude settings → {settings_path}", file=sys.stderr)
    env = os.environ.copy()
    env["HARNESS_INSTANCE"] = str(instance_dir.resolve())
    return subprocess.call(cmd, cwd=str(instance_dir), env=env)


def sync_instance_skills(name: str) -> list[str]:
    instance_dir = instances_root() / name
    cfg = load_yaml(instance_dir / "config.yaml")
    selected = list(cfg.get("skills") or [])
    for skill in selected:
        _link_skill(skill, instance_dir / ".claude" / "skills")
        _link_skill(skill, instance_dir / ".agents" / "skills")
    return selected
