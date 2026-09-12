"""Harness instance scaffolding (framework only — concrete content lives in configs/)."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore

from . import config as config_mod
from .paths import RepositoryPaths


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
    return RepositoryPaths.discover().root


def skills_root() -> Path:
    return RepositoryPaths.discover().skills


def instances_root() -> Path:
    return RepositoryPaths.discover().instances


def harnesses_root() -> Path:
    return RepositoryPaths.discover().harnesses


def profiles_root() -> Path:
    return RepositoryPaths.discover().profiles


def providers_root() -> Path:
    """Root for reusable model-provider connection definitions."""
    return RepositoryPaths.discover().providers


def agents_root() -> Path:
    return RepositoryPaths.discover().agents


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
    return config_mod.load_yaml(path)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    config_mod.write_yaml(path, data)


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


def resolve_skill_specs(raw: Any) -> list[dict[str, Any]]:
    """Normalize unified skills entries from local path or npx source."""
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("skills must be a list")
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"source": "path", "path": item})
        elif isinstance(item, dict) and "path" in item:
            out.append({"source": "path", "path": str(item["path"])})
        elif isinstance(item, dict) and "npx" in item:
            npx = item["npx"]
            if isinstance(npx, str):
                if "@" not in npx:
                    raise ValueError("skills npx string must be package@skill")
                package, skill = npx.split("@", 1)
            else:
                if not isinstance(npx, dict):
                    raise ValueError("skills npx entry must be a string or mapping")
                package, skill = npx.get("package"), npx.get("skill")
            if not package or not skill:
                raise ValueError("skills npx entry needs package and skill")
            out.append({"source": "npx", "package": str(package), "skill": str(skill)})
        else:
            raise ValueError(f"invalid skill entry: {item!r}")
    return out


def resolve_tools(raw: Any) -> dict[str, dict[str, Any]]:
    """Resolve profile tool declarations through the CLI registry."""
    if not raw:
        return {}
    from .tools import get_cli
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, str):
            tool_id, entry = item, {}
        elif isinstance(item, dict) and item.get("cli"):
            tool_id, entry = str(item["cli"]), dict(item)
        else:
            raise ValueError(f"invalid tool entry: {item!r}")
        get_cli(tool_id)
        if tool_id in out:
            raise ValueError(f"duplicate tool declaration: {tool_id}")
        entry.pop("cli", None)
        out[tool_id] = entry
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
        Path(instance_dir) / ".grok" / "skills" / skill_name,
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
        p.name for p in root.iterdir() if p.is_dir() and (p / "config.yaml").is_file()
    )


def list_providers() -> list[str]:
    """List provider ids declared under ``configs/providers``."""
    root = providers_root()
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.yaml") if p.is_file())


def list_agents() -> list[str]:
    root = agents_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "agent.yaml").is_file()
    )


def load_agent(agent_id: str) -> dict[str, Any]:
    path = agents_root() / agent_id / "agent.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"agent not found: {path} (available: {list_agents()})"
        )
    data = load_yaml(path)
    data["_id"] = agent_id
    data["_dir"] = path.parent
    return data


def load_provider(provider_id: str) -> dict[str, Any]:
    """Load a provider connection definition without resolving its secret."""
    path = providers_root() / f"{provider_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"provider not found: {path} (available: {list_providers()})"
        )
    data = load_yaml(path)
    data["_id"] = provider_id
    data["_path"] = path
    return data


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
    cfg_path = root / "config.yaml"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"profile not found: {root} (available: {list_profiles()})")
    meta = load_yaml(cfg_path)
    harness_id = meta.get("harness")
    if not harness_id and meta.get("agent"):
        harness_id = load_agent(str(meta["agent"])).get("harness")
    if not harness_id:
        raise ValueError(f"profile {profile_id!r} missing harness: in profile.yaml")
    cfg = dict(meta)
    if not cfg.get("harness"):
        cfg["harness"] = harness_id
    return {
        "_id": profile_id,
        "_dir": root,
        "harness": str(harness_id),
        "meta": meta,
        "config": cfg,
        "skeleton": root / "skeleton",
    }


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    return config_mod.deep_merge(base, overlay)


def build_instance_config(
    name: str,
    profile_id: str,
    skills: Optional[list[str]] = None,
    agent_id: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Merge harness ⊕ profile into an instance config dict.

    Returns (config, harness, profile).
    """
    profile = load_profile(profile_id)
    if agent_id is None:
        agent_id = str(profile["meta"].get("agent") or "") or None
    harness = load_harness(profile["harness"])

    cfg: dict[str, Any] = {}
    # Harness-derived fields inlined so the instance is self-contained.
    if harness.get("skill_dirs"):
        cfg["skill_dirs"] = list(harness["skill_dirs"])
    if harness.get("process_env"):
        cfg["process_env"] = dict(harness["process_env"])
    if harness.get("process_env_policy"):
        cfg["process_env_policy"] = harness["process_env_policy"]
    if harness.get("materialize"):
        cfg["materialize"] = list(harness["materialize"])
    if harness.get("launch"):
        cfg["launch"] = dict(harness["launch"])
    if harness.get("agent_context"):
        cfg["agent_context"] = harness["agent_context"]

    schedule: dict[str, Any] = {}
    if harness.get("schedule_actions"):
        schedule["actions"] = dict(harness["schedule_actions"])
    cfg["schedule"] = schedule

    cfg = _deep_merge(cfg, profile["config"])

    if agent_id:
        agent = load_agent(agent_id)
        agent_profile = str(agent.get("profile") or "").strip()
        if agent_profile and agent_profile != profile_id:
            raise ValueError(
                f"agent {agent_id!r} belongs to profile {agent_profile!r}, "
                f"not {profile_id!r}"
            )
        model_cfg = agent.get("model")
        if model_cfg is not None:
            if (
                not isinstance(model_cfg, dict)
                or not model_cfg.get("provider")
                or not model_cfg.get("name")
            ):
                raise ValueError("agent model must contain provider and name")
            provider = str(model_cfg["provider"])
            provider_path = providers_root() / f"{provider}.yaml"
            if not provider_path.is_file():
                raise FileNotFoundError(
                    f"model provider not found: {provider} (available: {list_providers()})"
                )
            provider_data = load_yaml(provider_path)
            models = provider_data.get("models")
            model_name = str(model_cfg["name"])
            if isinstance(models, list) and model_name not in {str(item) for item in models}:
                raise ValueError(
                    f"model {model_name!r} is not declared by provider {provider!r}"
                )
        agent_harness = str(agent.get("harness") or profile["harness"])
        for key in ("env", "skills", "skills_npx", "bin", "tools", "trade", "schedule"):
            if key in agent:
                cfg[key] = (
                    _deep_merge(cfg.get(key, {}), agent[key])
                    if isinstance(agent[key], dict)
                    else agent[key]
                )
        if model_cfg is not None:
            # Keep the historical bare ``model`` key for harness templates and
            # expose the canonical provider-qualified reference separately.
            # Older instances and third-party harnesses read ``model`` directly.
            model_ref = config_mod.ModelRef(str(model_cfg["provider"]), model_name)
            cfg["model"] = model_name
            cfg["model_provider"] = model_ref.provider
            cfg["model_ref"] = model_ref.qualified
        cfg["harness"] = agent_harness
        cfg["agent"] = agent_id

    raw_skills = skills if skills is not None else list(cfg.get("skills") or [])
    specs = resolve_skill_specs(raw_skills)
    selected = [Path(s["path"]).name for s in specs if s["source"] == "path"]
    available = list_available_skills()
    unknown = [s for s in selected if s not in available]
    if unknown:
        raise FileNotFoundError(f"unknown skills {unknown}; available={available}")

    # Validate npx skill declarations (do not require them under repo skills/).
    cfg["skill_specs"] = specs

    if cfg.get("tools"):
        cfg["bin"] = resolve_tools(cfg["tools"])

    # Normalize bin (legacy wrappers/expose → bin) into the instance config.
    from . import agent_context as ac_mod

    cfg["bin"] = ac_mod.normalize_bin(cfg)
    cfg.pop("wrappers", None)
    cfg.pop("expose", None)

    cfg["name"] = name
    cfg["profile"] = profile_id
    cfg["harness"] = str(cfg.get("harness") or profile["harness"])
    cfg["skills"] = selected
    if not cfg.get("agent_context"):
        cfg["agent_context"] = "AGENTS.md"
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


def _write_restricted_wrapper(
    instance_dir: Path,
    script_name: str,
    verbs: list[str],
    exec_argv: list[str],
) -> Path:
    """Write bin/<script_name> that only allows listed first-arg verbs."""
    bin_dir = instance_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / script_name
    root = repo_root()
    if not verbs:
        raise ValueError(f"bin.{script_name}: enable matched no commands")
    invalid = [verb for verb in verbs if not re.fullmatch(r"[A-Za-z0-9_-]+", verb)]
    if invalid:
        raise ValueError(f"bin.{script_name}: command names must be shell-safe: {invalid}")
    verb_pattern = "|".join(verbs)
    usage = f"usage: {script_name} {{{verb_pattern}}}"
    exec_line = " ".join(shlex.quote(x) for x in exec_argv)
    content = f"""#!/usr/bin/env bash
# Generated by `harness instance sync-bin` from config.yaml `bin`; do not edit.
set -euo pipefail
ROOT={shlex.quote(str(root))}
INSTANCE={shlex.quote(str(instance_dir.resolve()))}
export HARNESS_INSTANCE="$INSTANCE"
CMD="${{1:-}}"
case "$CMD" in
  {verb_pattern})
    shift
    cd "$ROOT"
    exec {exec_line} "$CMD" "$@"
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


def compose_agent_context(
    instance_dir: Path,
    cfg: Optional[dict[str, Any]] = None,
) -> Path:
    """Rewrite agent context from the profile body and compact generated index."""
    from . import agent_context as ac_mod

    instance_dir = Path(instance_dir).resolve()
    if cfg is None:
        cfg = load_yaml(instance_dir / "config.yaml")

    agent_context = str(cfg.get("agent_context") or "AGENTS.md")
    profile_id = str(cfg.get("profile") or "")
    if not profile_id:
        raise ValueError("config.yaml missing profile (needed to load skeleton)")

    skeleton_src = profiles_root() / profile_id / "skeleton" / agent_context
    if not skeleton_src.is_file():
        raise FileNotFoundError(
            f"profile skeleton missing {skeleton_src} "
            f"(harness agent_context={agent_context!r})"
        )

    vars = {
        "name": str(cfg.get("name") or instance_dir.name),
        "skills": ", ".join(skill_label_list(cfg)) or "(none)",
        "profile": profile_id,
        "harness": str(cfg.get("harness") or ""),
    }
    body = _expand_placeholders(skeleton_src.read_text(encoding="utf-8"), vars)
    body = ac_mod.strip_generated_sections(body)
    appendix = ac_mod.render_tools_markdown(cfg)
    # Profile instructions are authoritative.  Add generic trade defaults
    # only when a trading profile has no boundary section of its own.
    has_boundary = re.search(r"^##\s+.*(?:Rules|规则|边界|安全).*$", body, re.MULTILINE)
    trade_tools = {"clawstreet", "paper-ashare", "okx"}
    can_trade = False
    for name, entry in ac_mod.normalize_bin(cfg).items():
        via = str(entry.get("via") or name)
        if via not in trade_tools:
            continue
        helps = ac_mod.tool_command_helps(via)
        enabled = ac_mod.resolve_enable(list(helps), entry.get("enable"))
        if "order" in enabled:
            can_trade = True
            break
    if not has_boundary and can_trade:
        appendix = appendix.rstrip() + "\n\n" + ac_mod.COMMON_RULES_MD
    dest = instance_dir / agent_context
    dest.write_text(body.rstrip() + "\n\n" + appendix, encoding="utf-8")
    return dest


def sync_instance_bin(name: str) -> list[Path]:
    """Regenerate instance wrappers and refresh the compact agent context."""
    from . import agent_context as ac_mod
    from . import schedule as schedule_mod

    instance_dir = instances_root() / name
    if not instance_dir.is_dir():
        raise FileNotFoundError(f"instance not found: {instance_dir}")
    cfg = load_yaml(instance_dir / "config.yaml")
    bins = ac_mod.normalize_bin(cfg)
    # Persist normalized bin when migrating old configs.
    if cfg.get("bin") != bins or "wrappers" in cfg or "expose" in cfg:
        cfg["bin"] = bins
        cfg.pop("wrappers", None)
        cfg.pop("expose", None)
        write_yaml(instance_dir / "config.yaml", cfg)

    written: list[Path] = []
    managed_names = set(bins.keys())

    for script_name, entry in bins.items():
        via = str(entry.get("via") or script_name)
        enable = entry.get("enable")

        if via == "schedule":
            available = list(schedule_mod.AGENT_SAFE_VERBS)
            verbs = ac_mod.resolve_enable(available, enable)
            unknown = [v for v in verbs if v not in schedule_mod.AGENT_SAFE_VERBS]
            if unknown:
                raise ValueError(
                    f"bin.schedule enable resolved to non-agent-safe verbs {unknown}; "
                    f"allowed: {list(schedule_mod.AGENT_SAFE_VERBS)}"
                )
            written.append(
                _write_restricted_wrapper(
                    instance_dir,
                    script_name,
                    verbs,
                    ["uv", "run", "harness", "schedule"],
                )
            )
            continue

        helps = ac_mod.tool_command_helps(via)
        available = list(helps.keys()) if helps else []
        if enable is not None and available:
            verbs = ac_mod.resolve_enable(available, enable)
            written.append(
                _write_restricted_wrapper(
                    instance_dir,
                    script_name,
                    verbs,
                    ["uv", "run", via],
                )
            )
        else:
            # Full passthrough when enable omitted or commands unknown.
            written.append(_write_uv_wrapper(instance_dir, script_name))
            # If script_name != via, rewrite wrapper to call via.
            if script_name != via:
                written[-1] = _write_uv_wrapper_for(instance_dir, script_name, via)

    # Drop stale agent-facing wrappers we no longer manage (never leave bin/harness).
    bin_dir = instance_dir / "bin"
    if bin_dir.is_dir():
        for path in bin_dir.iterdir():
            if not path.is_file():
                continue
            if path.name in managed_names:
                continue
            if path.name in {"pi", "grok", "grok-exec"}:
                continue  # harness materialize
            if path.name == "harness" or path.name in {
                "clawstreet",
                "paper-ashare",
                "fuyao",
                "schedule",
            }:
                path.unlink()

    written.append(compose_agent_context(instance_dir, cfg))
    return written


def _write_uv_wrapper(instance_dir: Path, script_name: str) -> Path:
    return _write_uv_wrapper_for(instance_dir, script_name, script_name)


def _write_uv_wrapper_for(
    instance_dir: Path, script_name: str, uv_script: str
) -> Path:
    bin_dir = instance_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / script_name
    root = repo_root()
    content = f"""#!/usr/bin/env bash
set -euo pipefail
ROOT={shlex.quote(str(root))}
INSTANCE={shlex.quote(str(instance_dir.resolve()))}
export HARNESS_INSTANCE="$INSTANCE"
cd "$ROOT"
exec uv run {shlex.quote(uv_script)} "$@"
"""
    wrapper.write_text(content, encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | 0o111)
    return wrapper


def expand_env_map(cfg: dict[str, Any], key: str = "env") -> tuple[dict[str, str], list[str]]:
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


def _env_block_key(cfg: dict[str, Any]) -> str:
    """Pick which config key holds the launch secret map.

    Prefer unified ``env``. Legacy instances may still use ``env_from`` +
    ``pi-env`` / ``cc-env`` until re-inited or hand-edited.
    """
    raw = cfg.get("env")
    if isinstance(raw, dict) and raw:
        return "env"
    legacy_from = cfg.get("env_from")
    if legacy_from and isinstance(cfg.get(str(legacy_from)), dict):
        return str(legacy_from)
    for legacy in ("pi-env", "cc-env"):
        block = cfg.get(legacy)
        if isinstance(block, dict) and block:
            return legacy
    return "env"


# ---------------------------------------------------------------------------
# Runtime materialize + process env (harness-agnostic)
# ---------------------------------------------------------------------------


def _parse_model(cfg: dict[str, Any]) -> tuple[str, str]:
    """Split the canonical model reference, with legacy-key compatibility."""
    raw = str(cfg.get("model_ref") or cfg.get("model") or "").strip()
    if not raw:
        return "", ""
    if "/" in raw:
        provider, model_id = raw.split("/", 1)
        return provider.strip(), model_id.strip()
    return str(cfg.get("model_provider") or "").strip(), raw


def _template_vars(
    instance_dir: Path, cfg: dict[str, Any], resolved_env: dict[str, str]
) -> dict[str, str]:
    name = str(cfg.get("name") or instance_dir.name)
    provider, model_id = _parse_model(cfg)
    return {
        **resolved_env,
        "name": name,
        "instance": name,
        "instance_dir": str(instance_dir.resolve()),
        "profile": str(cfg.get("profile") or ""),
        "harness": str(cfg.get("harness") or ""),
        "model": str(cfg.get("model") or ""),
        "default_provider": provider,
        "default_model": model_id,
        "skills": ", ".join(skill_label_list(cfg)) or "(none)",
        "repo_root": str(repo_root()),
        # Raw JSON object for templates like ``"env": {{env_json}}`` (not a string).
        "env_json": json.dumps(resolved_env, ensure_ascii=False, indent=2),
    }


def resolve_env_from(
    cfg: dict[str, Any],
) -> tuple[str, dict[str, str], list[str]]:
    """Return (env_key, resolved_map, missing_names)."""
    key = _env_block_key(cfg)
    env, missing = expand_env_map(cfg, key)
    return key, env, missing


def _runtime_path(current: str) -> str:
    """Prepend user tool dirs so cron/systemd can find ``uv`` and real ``pi``.

    Cron often has ``PATH=/usr/bin:/bin``. ``minimal`` copies that through, so
    wake hooks fail with 127. Do **not** prepend instance ``bin/``: ``bin/pi``
    wraps ``harness instance launch``, which execs ``pi`` again and would
    recurse. Instance wrappers stay ``./bin/…`` in agent prompts.
    """
    extras: list[str] = []
    home = Path.home()
    for rel in ((".local", "bin"), (".npm-global", "bin"), ("bin",)):
        candidate = home.joinpath(*rel)
        if candidate.is_dir():
            extras.append(str(candidate))
    seen: set[str] = set()
    ordered: list[str] = []
    for part in extras + [p for p in current.split(os.pathsep) if p]:
        if part in seen:
            continue
        seen.add(part)
        ordered.append(part)
    return os.pathsep.join(ordered)


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
    env["PATH"] = _runtime_path(env.get("PATH", os.defpath))
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
                f"(add it to config env / repo .env){hint}"
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
    specs = resolve_skill_specs(cfg.get("skill_specs")) if cfg.get("skill_specs") else []
    npx_entries = [s for s in specs if s["source"] == "npx"]
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
    agent: Optional[str] = None,
) -> Path:
    if not agent:
        raise ValueError("instance init requires --agent")
    agent_cfg = load_agent(agent)
    profile = str(agent_cfg.get("profile") or profile)
    if not name or "/" in name or name in (".", ".."):
        raise ValueError(f"invalid instance name: {name!r}")

    instance_dir = instances_root() / name
    if instance_dir.exists() and not force:
        raise FileExistsError(
            f"instance already exists: {instance_dir} (pass --force to recreate scaffolding)"
        )

    cfg, _harness, profile_data = build_instance_config(
        name, profile, skills=skills, agent_id=agent
    )
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
    base_dir = schedule_mod.rules_dir(instance_dir, "base")
    # Seed base/ from this profile's schedule/ when empty.
    if profile and (profiles_root() / profile / "schedule").is_dir():
        if not any(base_dir.iterdir()):
            schedule_mod.apply_pack(instance_dir, profile)

    sync_instance_bin(name)

    if cfg.get("materialize"):
        sync_runtime(instance_dir, cfg)

    return instance_dir
