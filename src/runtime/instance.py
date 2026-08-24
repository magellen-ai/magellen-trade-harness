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
_PLACEHOLDER = re.compile(r"\{\{([\w.]+)\}\}")
_SIMPLE_BRACE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

DEFAULT_PROFILE = "clawstreet-claude-default"

# Env keys kept when process_env_policy=minimal (harness isolation from host secrets).
_MINIMAL_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TERM",
        "TERMINFO",
        "COLORTERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "TMP",
        "TEMP",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "NODE_PATH",
        "NPM_CONFIG_PREFIX",
    }
)


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


def normalize_skills_npx(raw: Any) -> list[dict[str, Any]]:
    """Normalize profile ``skills_npx`` entries.

    Accepted forms::

        skills_npx:
          - package: HiThink-Tech/Financial-API
            skill: hithink-finance
          - HiThink-Tech/Financial-API@hithink-finance
    """
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("skills_npx must be a list")
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            if "@" not in item:
                raise ValueError(
                    f"skills_npx string must be package@skill, got {item!r}"
                )
            package, skill = item.split("@", 1)
            package, skill = package.strip(), skill.strip()
            if not package or not skill:
                raise ValueError(f"invalid skills_npx entry: {item!r}")
            out.append({"package": package, "skill": skill})
            continue
        if not isinstance(item, dict):
            raise ValueError(f"skills_npx entry must be str or mapping, got {type(item)}")
        package = str(item.get("package") or item.get("source") or "").strip()
        skill = str(item.get("skill") or "").strip()
        if not package or not skill:
            raise ValueError(
                "skills_npx entries need package (or source) and skill "
                f"(got {item!r})"
            )
        # Instance-scoped only — never install with npx -g.
        out.append({"package": package, "skill": skill})
    return out


def npx_skill_names(cfg: dict[str, Any]) -> list[str]:
    return [e["skill"] for e in normalize_skills_npx(cfg.get("skills_npx"))]


def skill_label_list(cfg: dict[str, Any]) -> list[str]:
    """Local skills/ names + npx skill names (for templates / listing)."""
    names = [str(s) for s in (cfg.get("skills") or [])]
    for name in npx_skill_names(cfg):
        if name not in names:
            names.append(name)
    return names


def _run_npx_skills(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    cmd = ["npx", "--yes", "skills", *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def ensure_npx_skills(instance_dir: Path, entries: list[dict[str, Any]]) -> list[str]:
    """Install/refresh declared npx skills **inside the instance** (no ``-g``).

    Project-scope ``npx skills add`` writes into the instance's hidden
    ``.agents/skills/`` (plus ``skills-lock.json``). Never touches user-global
    skill dirs.
    """
    if not entries:
        return []

    instance_dir = Path(instance_dir)
    instance_dir.mkdir(parents=True, exist_ok=True)

    upd = _run_npx_skills(["update", "-p", "-y"], cwd=instance_dir)
    if upd.returncode != 0:
        sys.stderr.write(
            f"npx skills update -p warning (exit {upd.returncode}): "
            f"{(upd.stderr or upd.stdout or '').strip()[:500]}\n"
        )

    installed: list[str] = []
    for entry in entries:
        package = entry["package"]
        skill = entry["skill"]
        # No -g: project install → instance/.agents/skills/<skill>
        args = ["add", package, "--skill", skill, "--yes"]
        proc = _run_npx_skills(args, cwd=instance_dir)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(
                f"npx skills add {package} --skill {skill} (cwd={instance_dir}) failed "
                f"(exit {proc.returncode}): {detail[:800]}"
            )
        dest = instance_dir / ".agents" / "skills" / skill
        if not (dest / "SKILL.md").is_file():
            raise FileNotFoundError(
                f"npx reported success but {dest}/SKILL.md missing "
                f"(expected project install under instance .agents/skills/)"
            )
        installed.append(skill)
    return installed


def resolve_instance_npx_skill_path(instance_dir: Path, skill_name: str) -> Path:
    """Locate an npx skill already installed under the instance."""
    candidates = [
        Path(instance_dir) / ".agents" / "skills" / skill_name,
        Path(instance_dir) / ".pi" / "skills" / skill_name,
        Path(instance_dir) / ".claude" / "skills" / skill_name,
    ]
    for path in candidates:
        if (path / "SKILL.md").is_file():
            return path.resolve()
    raise FileNotFoundError(
        f"npx skill {skill_name!r} not found under {instance_dir}/.agents/skills. "
        "Run sync-skills / sync-settings (project-scoped npx, no -g)."
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
    if harness.get("env_from"):
        cfg["env_from"] = harness["env_from"]
    if harness.get("process_env"):
        cfg["process_env"] = dict(harness["process_env"])
    if harness.get("process_env_policy"):
        cfg["process_env_policy"] = harness["process_env_policy"]
    if harness.get("materialize"):
        cfg["materialize"] = list(harness["materialize"])
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

    # Validate npx skill declarations (do not require them under repo skills/).
    cfg["skills_npx"] = normalize_skills_npx(cfg.get("skills_npx"))

    cfg["name"] = name
    cfg["profile"] = profile_id
    cfg["harness"] = profile["harness"]
    cfg["skills"] = selected
    return cfg, harness, profile


def _expand_placeholders(text: str, vars: dict[str, str]) -> str:
    """Expand ``{{name}}`` / ``{{env.KEY}}``. Unknown ``env.*`` raises; others stay literal."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key.startswith("env."):
            env_key = key[4:]
            if env_key not in vars:
                raise KeyError(env_key)
            return vars[env_key]
        if key in vars:
            return vars[key]
        return match.group(0)

    return _PLACEHOLDER.sub(repl, text)


def _expand_simple_braces(text: str, vars: dict[str, str]) -> str:
    """Expand ``{name}`` for process_env values (unknown keys stay literal)."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return vars[key] if key in vars else match.group(0)

    return _SIMPLE_BRACE.sub(repl, text)


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


def _link_skill_from(src: Path, dest_dir: Path, skill_name: str) -> None:
    if not (src / "SKILL.md").exists():
        raise FileNotFoundError(f"skill missing SKILL.md: {src}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / skill_name
    if dest.is_symlink() or dest.exists():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.symlink_to(src.resolve(), target_is_directory=True)


def _link_skill(skill_name: str, dest_dir: Path) -> None:
    src = skills_root() / skill_name
    if not (src / "SKILL.md").exists():
        raise FileNotFoundError(f"skill not found in skills/: {skill_name}")
    _link_skill_from(src, dest_dir, skill_name)


def _ensure_npx_skill_in_dir(
    instance_dir: Path, skill_name: str, dest_dir: Path
) -> None:
    """Make sure skill_name is visible under dest_dir (already installed by npx)."""
    src = resolve_instance_npx_skill_path(instance_dir, skill_name)
    dest = dest_dir / skill_name
    # npx already wrote into .agents/skills — same path, nothing to do.
    if dest.resolve() == src.resolve():
        return
    _link_skill_from(src, dest_dir, skill_name)


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
# Runtime materialize + process env (harness-agnostic)
# ---------------------------------------------------------------------------


def _template_vars(
    instance_dir: Path, cfg: dict[str, Any], resolved_env: dict[str, str]
) -> dict[str, str]:
    name = str(cfg.get("name") or instance_dir.name)
    return {
        **resolved_env,
        "name": name,
        "instance": name,
        "instance_dir": str(instance_dir.resolve()),
        "profile": str(cfg.get("profile") or ""),
        "harness": str(cfg.get("harness") or ""),
        "skills": ", ".join(skill_label_list(cfg)) or "(none)",
        "repo_root": str(repo_root()),
        # Raw JSON object for templates like ``"env": {{env_json}}`` (not a string).
        "env_json": json.dumps(resolved_env, ensure_ascii=False, indent=2),
    }


def resolve_env_from(
    cfg: dict[str, Any],
) -> tuple[str, dict[str, str], list[str]]:
    """Return (env_from_key, resolved_map, missing_names)."""
    key = str(cfg.get("env_from") or "cc-env")
    env, missing = expand_env_map(cfg, key)
    return key, env, missing


def instance_process_env(
    instance_dir: Path, cfg: Optional[dict[str, Any]] = None
) -> dict[str, str]:
    """Env for launch / schedule subprocesses (secrets + harness process_env)."""
    if cfg is None:
        cfg = load_yaml(instance_dir / "config.yaml")
    instance_dir = instance_dir.resolve()
    _, resolved, _missing = resolve_env_from(cfg)
    vars = _template_vars(instance_dir, cfg, resolved)
    policy = str(cfg.get("process_env_policy") or "inherit")
    if policy == "minimal":
        env = {k: os.environ[k] for k in _MINIMAL_ENV_KEYS if k in os.environ}
    elif policy == "inherit":
        env = os.environ.copy()
    else:
        raise ValueError(
            f"unknown process_env_policy {policy!r} (expected inherit|minimal)"
        )
    env.update(resolved)
    raw_pe = cfg.get("process_env") or {}
    if isinstance(raw_pe, dict):
        for k, v in raw_pe.items():
            if v is None:
                continue
            env[str(k)] = _expand_simple_braces(
                _expand_placeholders(str(v), vars), vars
            )
    env["HARNESS_INSTANCE"] = str(instance_dir)
    return env


def sync_runtime(
    instance_dir: Path, cfg: Optional[dict[str, Any]] = None
) -> list[Path]:
    """Render harness ``materialize`` templates into the instance (no harness-specific JSON)."""
    if cfg is None:
        cfg = load_yaml(instance_dir / "config.yaml")
    instance_dir = instance_dir.resolve()
    harness_id = cfg.get("harness")
    if not harness_id:
        raise ValueError("config.yaml missing harness id")
    harness_dir = harnesses_root() / str(harness_id)
    if not harness_dir.is_dir():
        raise FileNotFoundError(f"harness dir not found: {harness_dir}")

    _, resolved, missing = resolve_env_from(cfg)
    vars = _template_vars(instance_dir, cfg, resolved)
    entries = cfg.get("materialize") or []
    if not isinstance(entries, list):
        raise ValueError("config.yaml materialize must be a list")

    written: list[Path] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"materialize[{i}] must be a mapping")
        src_rel = entry.get("src")
        dest_rel = entry.get("dest")
        if not src_rel or not dest_rel:
            raise ValueError(f"materialize[{i}] needs src and dest")
        src = harness_dir / str(src_rel)
        if not src.is_file():
            raise FileNotFoundError(f"materialize src not found: {src}")
        dest = instance_dir / str(dest_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = _expand_placeholders(src.read_text(encoding="utf-8"), vars)
        except KeyError as e:
            hint = ""
            if missing:
                hint = f"; also unresolved $refs: {missing}"
            raise ValueError(
                f"materialize {src_rel}: missing env key {e.args[0]!r} "
                f"(add it to config {cfg.get('env_from') or 'env'} / repo .env){hint}"
            ) from None
        dest.write_text(text, encoding="utf-8")
        mode = entry.get("mode", 0o600)
        if isinstance(mode, str):
            mode = int(mode, 0)
        os.chmod(dest, int(mode))
        written.append(dest)
    return written


def sync_settings(instance_dir: Path, cfg: Optional[dict[str, Any]] = None) -> list[Path]:
    """Alias for :func:`sync_runtime` (CLI / schedule hooks keep the old name)."""
    return sync_runtime(instance_dir, cfg)


def sync_instance_settings(name: str) -> list[Path]:
    """Materialize templates and refresh skills (including ``skills_npx`` via npx)."""
    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    # Keep instance skill_dirs current whenever settings are synced.
    sync_instance_skills(name)
    return sync_runtime(instance_dir, load_yaml(instance_dir / "config.yaml"))


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


def _launch_sync_before(launch: dict[str, Any]) -> bool:
    if "sync_before" in launch:
        return bool(launch.get("sync_before"))
    # Backward-compatible key from older instance configs.
    return bool(launch.get("sync_settings_before", True))


def launch_instance(
    name: str,
    dry_print: bool = False,
    extra_argv: Optional[list[str]] = None,
) -> int:
    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    cfg = load_yaml(instance_dir / "config.yaml")
    launch = cfg.get("launch") or {}
    written: list[Path] = []
    if isinstance(launch, dict) and _launch_sync_before(launch):
        # Refresh local + skills_npx (npx update/add) before materialize/launch.
        sync_instance_skills(name)
        if cfg.get("materialize"):
            written = sync_runtime(instance_dir, cfg)
    cmd = launch_command(name, cfg)
    if extra_argv:
        cmd = cmd + [str(x) for x in extra_argv]
    env = instance_process_env(instance_dir, cfg)
    if dry_print:
        print(f"cd {instance_dir}")
        for key in sorted(
            k
            for k in env
            if k == "HARNESS_INSTANCE"
            or k.startswith("PI_")
            or k in (cfg.get("process_env") or {})
        ):
            print(f"export {key}={env[key]}")
        if written:
            print(f"# materialized → {[str(p) for p in written]}")
        print(" ".join(cmd))
        return 0
    print(f"Launching in {instance_dir}: {' '.join(cmd)}", file=sys.stderr)
    if written:
        print(f"# materialized → {[str(p) for p in written]}", file=sys.stderr)
    return subprocess.call(cmd, cwd=str(instance_dir), env=env)


def sync_instance_skills(name: str) -> list[str]:
    """Link repo ``skills/`` + install ``skills_npx`` into this instance only (no npx -g)."""
    instance_dir = instances_root() / name
    cfg = load_yaml(instance_dir / "config.yaml")
    selected = list(cfg.get("skills") or [])
    npx_entries = normalize_skills_npx(cfg.get("skills_npx"))
    if npx_entries:
        ensure_npx_skills(instance_dir, npx_entries)
    dirs = list(cfg.get("skill_dirs") or [".claude/skills"])
    for rel in dirs:
        dest = instance_dir / rel
        dest.mkdir(parents=True, exist_ok=True)
        for skill in selected:
            _link_skill(skill, dest)
        for entry in npx_entries:
            _ensure_npx_skill_in_dir(instance_dir, entry["skill"], dest)
    return skill_label_list(cfg)


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
        "skills": ", ".join(skill_label_list(cfg)) or "(none)",
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

    if cfg.get("materialize"):
        sync_runtime(instance_dir, cfg)

    return instance_dir
