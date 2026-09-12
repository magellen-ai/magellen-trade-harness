"""Configuration primitives and repository-wide validation.

The runtime deliberately keeps YAML as its user-facing format.  This module
owns the small amount of typed plumbing around it: safe mapping I/O, recursive
merging, model references, and validation of cross-file references.  Instance
scaffolding can therefore focus on materialising files instead of reimplementing
configuration rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - dependency is declared in pyproject.toml
    yaml = None  # type: ignore[assignment]

from .paths import RepositoryPaths


class ConfigError(ValueError):
    """Raised when a configuration document has an invalid shape."""


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping and provide a useful error for every bad shape."""

    if yaml is None:
        raise RuntimeError("PyYAML is required (uv sync installs it).")
    try:
        with Path(path).open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except UnicodeError as exc:
        raise ConfigError(f"invalid UTF-8 in {path}") from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        # Parser messages can echo a scalar from the document.  Keep config
        # diagnostics safe to print because environment values may be secrets.
        raise ConfigError(f"invalid YAML in {path}{location}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"config must be a mapping: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a UTF-8 YAML mapping, creating its parent directory."""

    if yaml is None:
        raise RuntimeError("PyYAML is required (uv sync installs it).")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge mappings recursively while replacing scalar/list values."""

    merged = dict(base)
    for key, value in overlay.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True)
class ModelRef:
    """A provider/model pair used by an agent runtime."""

    provider: str
    name: str

    @property
    def qualified(self) -> str:
        return f"{self.provider}/{self.name}"

    @classmethod
    def parse(cls, raw: Any) -> "ModelRef | None":
        if raw is None or str(raw).strip() == "":
            return None
        if isinstance(raw, dict):
            provider = str(raw.get("provider") or "").strip()
            name = str(raw.get("name") or raw.get("model") or "").strip()
        else:
            value = str(raw).strip()
            if "/" in value:
                provider, name = value.split("/", 1)
            else:
                provider, name = "", value
            provider, name = provider.strip(), name.strip()
        if not name or ("/" in name):
            raise ConfigError("invalid model reference (expected provider/name)")
        if not provider:
            raise ConfigError("model reference needs provider/name")
        return cls(provider, name)


@dataclass(frozen=True)
class ValidationIssue:
    """A repository validation diagnostic."""

    level: str
    source: str
    message: str

    def render(self) -> str:
        return f"{self.level.upper()} {self.source}: {self.message}"


def _issue(level: str, source: Path, message: str, root: Path) -> ValidationIssue:
    try:
        label = str(source.relative_to(root))
    except ValueError:
        label = str(source)
    return ValidationIssue(level, label, message)


def _files(root: Path, pattern: str) -> Iterable[Path]:
    directory = root / pattern
    if not directory.is_dir():
        return ()
    return (path for path in sorted(directory.iterdir()) if path.is_dir())


def _validate_harness(
    path: Path, root: Path, issues: list[ValidationIssue]
) -> None:
    try:
        data = load_yaml(path / "harness.yaml")
    except (OSError, ConfigError) as exc:
        issues.append(_issue("error", path / "harness.yaml", str(exc), root))
        return
    context = data.get("agent_context")
    if not isinstance(context, str) or not context.strip():
        issues.append(
            _issue("error", path / "harness.yaml", "agent_context is required", root)
        )
    launch = data.get("launch")
    if launch is not None:
        if not isinstance(launch, dict):
            issues.append(
                _issue("error", path / "harness.yaml", "launch must be a mapping", root)
            )
        elif not isinstance(launch.get("argv"), list) or not launch["argv"]:
            issues.append(
                _issue(
                    "error",
                    path / "harness.yaml",
                    "launch.argv must be a non-empty list",
                    root,
                )
            )
    for entry in data.get("materialize") or []:
        if not isinstance(entry, dict) or not entry.get("src") or not entry.get("dest"):
            issues.append(
                _issue(
                    "error",
                    path / "harness.yaml",
                    "materialize entries need src and dest",
                    root,
                )
            )
        elif not (path / str(entry["src"])).is_file():
            issues.append(
                _issue(
                    "error",
                    path / "harness.yaml",
                    f"materialize source not found: {entry['src']}",
                    root,
                )
            )


def _validate_profile(
    path: Path,
    root: Path,
    harness_ids: set[str],
    agent_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    config_path = path / "config.yaml"
    try:
        data = load_yaml(config_path)
    except (OSError, ConfigError) as exc:
        issues.append(_issue("error", config_path, str(exc), root))
        return
    try:
        from .agent_context import normalize_bin

        normalize_bin(data)
    except ValueError as exc:
        issues.append(_issue("error", config_path, str(exc), root))
    harness = data.get("harness")
    if harness and str(harness) not in harness_ids:
        issues.append(_issue("error", config_path, f"unknown harness: {harness}", root))
    agent = data.get("agent")
    if agent and str(agent) not in agent_ids:
        issues.append(_issue("error", config_path, f"unknown agent: {agent}", root))
    elif agent:
        agent_path = root / "configs" / "agents" / str(agent) / "agent.yaml"
        try:
            agent_data = load_yaml(agent_path)
        except (OSError, ConfigError) as exc:
            issues.append(_issue("error", agent_path, str(exc), root))
        else:
            declared_profile = agent_data.get("profile")
            if declared_profile and str(declared_profile) != path.name:
                issues.append(
                    _issue(
                        "error",
                        config_path,
                        f"agent {agent!r} belongs to profile {declared_profile!r}",
                        root,
                    )
                )
            agent_harness = agent_data.get("harness")
            if harness and agent_harness and str(agent_harness) != str(harness):
                issues.append(
                    _issue(
                        "error",
                        config_path,
                        f"agent {agent!r} uses harness {agent_harness!r}, not {harness!r}",
                        root,
                    )
                )
    tools = data.get("tools") or []
    if not isinstance(tools, list):
        issues.append(_issue("error", config_path, "tools must be a list", root))
    else:
        from .tools import get_cli

        seen_tools: set[str] = set()
        for entry in tools:
            tool_id = (
                entry
                if isinstance(entry, str)
                else entry.get("cli")
                if isinstance(entry, dict)
                else None
            )
            if not tool_id:
                issues.append(
                    _issue("error", config_path, f"invalid tool entry: {entry!r}", root)
                )
                continue
            tool_id = str(tool_id)
            if tool_id in seen_tools:
                issues.append(
                    _issue("error", config_path, f"duplicate tool declaration: {tool_id}", root)
                )
                continue
            seen_tools.add(tool_id)
            try:
                get_cli(tool_id)
            except KeyError as exc:
                issues.append(_issue("error", config_path, str(exc), root))
    skills = data.get("skills") or []
    if not isinstance(skills, list):
        issues.append(_issue("error", config_path, "skills must be a list", root))
    else:
        for entry in skills:
            if isinstance(entry, str):
                skill_path = root / entry
                if not (skill_path / "SKILL.md").is_file():
                    issues.append(_issue("error", config_path, f"skill not found: {entry}", root))
            elif isinstance(entry, dict) and "npx" in entry:
                npx = entry["npx"]
                if isinstance(npx, str):
                    valid = "@" in npx and all(part.strip() for part in npx.split("@", 1))
                else:
                    valid = (
                        isinstance(npx, dict)
                        and bool(str(npx.get("package") or "").strip())
                        and bool(str(npx.get("skill") or "").strip())
                    )
                if not valid:
                    issues.append(
                        _issue(
                            "error",
                            config_path,
                            f"invalid npx skill entry: {entry!r}",
                            root,
                        )
                    )
            elif isinstance(entry, dict) and "path" in entry:
                skill_path = root / str(entry["path"])
                if not (skill_path / "SKILL.md").is_file():
                    issues.append(
                        _issue(
                            "error",
                            config_path,
                            f"skill not found: {entry['path']}",
                            root,
                        )
                    )
            else:
                issues.append(
                    _issue(
                        "error", config_path, f"invalid skill entry: {entry!r}", root
                    )
                )


def _validate_agent(
    path: Path,
    root: Path,
    profile_ids: set[str],
    harness_ids: set[str],
    provider_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    config_path = path / "agent.yaml"
    try:
        data = load_yaml(config_path)
    except (OSError, ConfigError) as exc:
        issues.append(_issue("error", config_path, str(exc), root))
        return
    for key, known in (("profile", profile_ids), ("harness", harness_ids)):
        value = data.get(key)
        if value and str(value) not in known:
            issues.append(_issue("error", config_path, f"unknown {key}: {value}", root))
    model = data.get("model")
    if "bin" in data:
        try:
            from .agent_context import normalize_bin

            normalize_bin(data)
        except ValueError as exc:
            issues.append(_issue("error", config_path, str(exc), root))
    if model is None:
        return
    if not isinstance(model, dict) or not model.get("provider") or not model.get("name"):
        issues.append(_issue("error", config_path, "model needs provider and name", root))
        return
    provider = str(model["provider"])
    if provider not in provider_ids:
        issues.append(_issue("error", config_path, f"unknown model provider: {provider}", root))
    else:
        provider_path = root / "configs" / "providers" / f"{provider}.yaml"
        try:
            provider_data = load_yaml(provider_path)
        except (OSError, ConfigError) as exc:
            issues.append(_issue("error", provider_path, str(exc), root))
        else:
            models = provider_data.get("models")
            if isinstance(models, list) and str(model["name"]) not in {
                str(item) for item in models
            }:
                issues.append(
                    _issue(
                        "error",
                        config_path,
                        f"model {model['name']!r} is not declared by provider {provider!r}",
                        root,
                    )
                )


def validate_repository(root: Path | None = None) -> list[ValidationIssue]:
    """Validate all declarative resources and their cross-file references."""

    paths = RepositoryPaths(root or RepositoryPaths.discover().root)
    issues: list[ValidationIssue] = []
    harnesses = {
        path.name
        for path in _files(paths.configs, "harnesses")
        if (path / "harness.yaml").is_file()
    }
    profiles = {
        path.name
        for path in _files(paths.configs, "profiles")
        if (path / "config.yaml").is_file()
    }
    agents = {
        path.name
        for path in _files(paths.configs, "agents")
        if (path / "agent.yaml").is_file()
    }
    providers = (
        {path.stem for path in paths.providers.glob("*.yaml")}
        if paths.providers.is_dir()
        else set()
    )

    for path in _files(paths.configs, "harnesses"):
        if (path / "harness.yaml").is_file():
            _validate_harness(path, paths.root, issues)
    for path in _files(paths.configs, "profiles"):
        if (path / "config.yaml").is_file():
            _validate_profile(path, paths.root, harnesses, agents, issues)
    for path in _files(paths.configs, "agents"):
        if (path / "agent.yaml").is_file():
            _validate_agent(path, paths.root, profiles, harnesses, providers, issues)
    provider_files = (
        sorted(paths.providers.glob("*.yaml")) if paths.providers.is_dir() else ()
    )
    for path in provider_files:
        try:
            data = load_yaml(path)
        except (OSError, ConfigError) as exc:
            issues.append(_issue("error", path, str(exc), paths.root))
            continue
        if not isinstance(data.get("models"), list):
            issues.append(_issue("error", path, "models must be a list", paths.root))
    return issues
