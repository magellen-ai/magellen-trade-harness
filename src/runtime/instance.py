"""Harness instance scaffolding (framework only — concrete content lives in configs/)."""

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


_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

DEFAULT_PROFILE = "clawstreet-claude-default"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def skills_root() -> Path:
    return repo_root() / "skills"


def instances_root() -> Path:
    return repo_root() / "instances"


def harnesses_root() -> Path:
    return repo_root() / "configs" / "harnesses"


def profiles_root() -> Path:
    return repo_root() / "configs" / "profiles"


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
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and (child / "SKILL.md").exists()
    )


def list_harnesses() -> list[str]:
    root = harnesses_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "harness.yaml").is_file()
    )


def list_profiles() -> list[str]:
    root = profiles_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "profile.yaml").is_file()
    )


def load_harness(harness_id: str) -> dict[str, Any]:
    path = harnesses_root() / harness_id / "harness.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"harness not found: {path} (available: {list_harnesses()})"
        )
    data = load_yaml(path)
    data["_id"] = harness_id
    data["_dir"] = path.parent
    return data


def load_profile(profile_id: str) -> dict[str, Any]:
    root = profiles_root() / profile_id
    meta_path = root / "profile.yaml"
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"profile not found: {meta_path} (available: {list_profiles()})"
        )
    meta = load_yaml(meta_path)
    harness_id = meta.get("harness")
    if not harness_id:
        raise ValueError(f"profile {profile_id!r} missing harness: in profile.yaml")
    cfg_path = root / "config.yaml"
    cfg = load_yaml(cfg_path) if cfg_path.is_file() else {}
    return {
        "_id": profile_id,
        "_dir": root,
        "harness": str(harness_id),
        "meta": meta,
        "config": cfg,
        "skeleton": root / "skeleton",
    }


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def build_instance_config(
    name: str,
    profile_id: str,
    skills: Optional[list[str]] = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Merge harness ⊕ profile into an instance config dict.

    Returns (config, harness, profile).
    """
    profile = load_profile(profile_id)
    harness = load_harness(profile["harness"])

    cfg: dict[str, Any] = {}
    # Harness-derived fields inlined so the instance is self-contained.
    if harness.get("skill_dirs"):
        cfg["skill_dirs"] = list(harness["skill_dirs"])
    if harness.get("wrappers"):
        cfg["wrappers"] = list(harness["wrappers"])
    if harness.get("settings"):
        cfg["settings"] = dict(harness["settings"])
    if harness.get("launch"):
        cfg["launch"] = dict(harness["launch"])

    schedule: dict[str, Any] = {}
    if harness.get("schedule_actions"):
        schedule["actions"] = dict(harness["schedule_actions"])
    cfg["schedule"] = schedule

    cfg = _deep_merge(cfg, profile["config"])

    selected = skills if skills is not None else list(cfg.get("skills") or [])
    available = list_available_skills()
    unknown = [s for s in selected if s not in available]
    if unknown:
        raise FileNotFoundError(f"unknown skills {unknown}; available={available}")

    cfg["name"] = name
    cfg["profile"] = profile_id
    cfg["harness"] = profile["harness"]
    cfg["skills"] = selected
    return cfg, harness, profile


def _expand_placeholders(text: str, vars: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return vars.get(key, match.group(0))

    return _PLACEHOLDER.sub(repl, text)


def copy_skeleton(
    skeleton_dir: Path,
    instance_dir: Path,
    vars: dict[str, str],
    *,
    force: bool = False,
) -> list[Path]:
    """Copy profile skeleton into instance. Skip existing files unless force."""
    written: list[Path] = []
    if not skeleton_dir.is_dir():
        return written
    for src in sorted(skeleton_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(skeleton_dir)
        dest = instance_dir / rel
        if dest.exists() and not force:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = src.read_bytes()
        # Text substitution for common text suffixes.
        if src.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json", ".toml", ""} or src.name in {
            "CLAUDE.md",
            "AGENTS.md",
        }:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                dest.write_bytes(raw)
            else:
                dest.write_text(_expand_placeholders(text, vars), encoding="utf-8")
        else:
            dest.write_bytes(raw)
        written.append(dest)
    return written


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


def _write_verb_wrapper(
    instance_dir: Path, script_name: str, harness_group: str, verbs: list[str]
) -> Path:
    bin_dir = instance_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / script_name
    root = repo_root()
    verb_pattern = "|".join(verbs)
    usage = f"usage: {script_name} {{{verb_pattern}}}"
    content = f"""#!/usr/bin/env bash
# Generated by `harness instance sync-bin` from config.yaml `expose`; do not edit.
set -euo pipefail
ROOT="{root}"
INSTANCE="{instance_dir.resolve()}"
export HARNESS_INSTANCE="$INSTANCE"
CMD="${{1:-}}"
case "$CMD" in
  {verb_pattern})
    shift
    cd "$ROOT"
    exec uv run harness {harness_group} "$CMD" "$@"
    ;;
  *)
    echo "{usage}" >&2
    exit 2
    ;;
esac
"""
    wrapper.write_text(content, encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | 0o111)
    return wrapper


def sync_instance_bin(name: str) -> list[Path]:
    """Regenerate instance bin/ wrappers from config.yaml wrappers + expose."""
    from . import schedule as schedule_mod

    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    cfg = load_yaml(instance_dir / "config.yaml")

    wrappers = list(cfg.get("wrappers") or ["clawstreet", "harness"])
    written = [_write_uv_wrapper(instance_dir, w) for w in wrappers]

    expose = cfg.get("expose") or {}
    if not isinstance(expose, dict):
        raise ValueError("config.yaml expose must be a mapping of tool -> verb list")

    schedule_wrapper = instance_dir / "bin" / "schedule"
    verbs = expose.get("schedule")
    if verbs:
        unknown = [v for v in verbs if v not in schedule_mod.AGENT_SAFE_VERBS]
        if unknown:
            raise ValueError(
                f"expose.schedule contains non-agent-safe verbs {unknown}; "
                f"allowed: {list(schedule_mod.AGENT_SAFE_VERBS)}"
            )
        written.append(
            _write_verb_wrapper(instance_dir, "schedule", "schedule", list(verbs))
        )
    elif schedule_wrapper.exists():
        schedule_wrapper.unlink()

    return written


def expand_env_map(cfg: dict[str, Any], key: str = "cc-env") -> tuple[dict[str, str], list[str]]:
    """Expand $VAR values from cfg[key]. Returns (resolved_env, missing_names)."""
    load_repo_dotenv(override=False)
    env: dict[str, str] = {}
    missing: list[str] = []
    raw = cfg.get(key) or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if v is None:
                continue
            expanded, miss = expand_env_refs(str(v))
            missing.extend(miss)
            if miss:
                continue
            env[str(k)] = expanded
    seen: set[str] = set()
    uniq: list[str] = []
    for name in missing:
        if name not in seen:
            seen.add(name)
            uniq.append(name)
    return env, uniq


# ---------------------------------------------------------------------------
# Settings / launch (paths and argv come from instance config, seeded by harness)
# ---------------------------------------------------------------------------


def sync_settings(instance_dir: Path, cfg: Optional[dict[str, Any]] = None) -> Path:
    """Write settings JSON from config settings.path + env_from (harness-agnostic)."""
    if cfg is None:
        cfg = load_yaml(instance_dir / "config.yaml")

    settings_meta = cfg.get("settings") or {}
    if not isinstance(settings_meta, dict) or not settings_meta.get("path"):
        raise ValueError(
            "config.yaml missing settings.path "
            "(seeded from harness at init; or add manually)"
        )
    rel = str(settings_meta["path"])
    settings_path = instance_dir / rel
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except json.JSONDecodeError:
            existing = {}

    env_from = str(settings_meta.get("env_from") or "cc-env")
    env, _missing = expand_env_map(cfg, env_from)
    out: dict[str, Any] = {**existing, "env": env}
    if "permissions" in existing:
        out["permissions"] = existing["permissions"]
    elif "permissions" in settings_meta:
        out["permissions"] = settings_meta["permissions"]

    settings_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(settings_path, 0o600)
    return settings_path


def sync_instance_settings(name: str) -> Path:
    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    return sync_settings(instance_dir, load_yaml(instance_dir / "config.yaml"))


def launch_command(name: str, cfg: Optional[dict[str, Any]] = None) -> list[str]:
    instance_dir = instances_root() / name
    if cfg is None:
        cfg_path = instance_dir / "config.yaml"
        if not cfg_path.exists():
            raise FileNotFoundError(f"instance config missing: {cfg_path}")
        cfg = load_yaml(cfg_path)
    launch = cfg.get("launch") or {}
    argv = launch.get("argv") if isinstance(launch, dict) else None
    if not argv or not isinstance(argv, list):
        raise ValueError(
            "config.yaml missing launch.argv "
            "(seeded from harness at init; or add manually)"
        )
    return [str(x) for x in argv]


def launch_instance(name: str, dry_print: bool = False) -> int:
    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    cfg = load_yaml(instance_dir / "config.yaml")
    launch = cfg.get("launch") or {}
    settings_path = None
    if isinstance(launch, dict) and launch.get("sync_settings_before", True):
        if cfg.get("settings"):
            settings_path = sync_settings(instance_dir, cfg)
    cmd = launch_command(name, cfg)
    if dry_print:
        print(f"cd {instance_dir}")
        print(f"export HARNESS_INSTANCE={instance_dir}")
        if settings_path:
            print(f"# synced settings → {settings_path}")
        print(" ".join(cmd))
        return 0
    print(f"Launching in {instance_dir}: {' '.join(cmd)}", file=sys.stderr)
    if settings_path:
        print(f"# synced settings → {settings_path}", file=sys.stderr)
    env = os.environ.copy()
    env["HARNESS_INSTANCE"] = str(instance_dir.resolve())
    return subprocess.call(cmd, cwd=str(instance_dir), env=env)


def sync_instance_skills(name: str) -> list[str]:
    instance_dir = instances_root() / name
    cfg = load_yaml(instance_dir / "config.yaml")
    selected = list(cfg.get("skills") or [])
    dirs = list(cfg.get("skill_dirs") or [".claude/skills"])
    for rel in dirs:
        dest = instance_dir / rel
        dest.mkdir(parents=True, exist_ok=True)
        for skill in selected:
            _link_skill(skill, dest)
    return selected


def init_instance(
    name: str,
    *,
    profile: str = DEFAULT_PROFILE,
    skills: Optional[list[str]] = None,
    force: bool = False,
) -> Path:
    if not name or "/" in name or name in (".", ".."):
        raise ValueError(f"invalid instance name: {name!r}")

    instance_dir = instances_root() / name
    if instance_dir.exists() and not force:
        raise FileExistsError(
            f"instance already exists: {instance_dir} (pass --force to recreate scaffolding)"
        )

    cfg, _harness, profile_data = build_instance_config(name, profile, skills=skills)
    selected = list(cfg["skills"])

    for sub in ("workdir", "audit", "logs", "memory", "agent"):
        (instance_dir / sub).mkdir(parents=True, exist_ok=True)

    cfg_path = instance_dir / "config.yaml"
    if not cfg_path.exists() or force:
        write_yaml(cfg_path, cfg)
    else:
        cfg = load_yaml(cfg_path)

    vars = {
        "name": name,
        "skills": ", ".join(selected) if selected else "(none)",
        "profile": profile,
        "harness": str(cfg.get("harness") or ""),
    }
    copy_skeleton(
        profile_data["skeleton"],
        instance_dir,
        vars,
        force=force,
    )

    sync_instance_skills(name)

    from . import schedule as schedule_mod

    schedule_mod.ensure_layout(instance_dir)
    pack = (cfg.get("schedule") or {}).get("pack") if isinstance(cfg.get("schedule"), dict) else None
    base_dir = schedule_mod.rules_dir(instance_dir, "base")
    if pack and not any(base_dir.iterdir()):
        schedule_mod.apply_pack(instance_dir, pack)

    sync_instance_bin(name)

    if cfg.get("settings"):
        sync_settings(instance_dir, cfg)

    return instance_dir
