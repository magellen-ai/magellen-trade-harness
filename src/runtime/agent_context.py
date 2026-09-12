"""Compose the small generated tool index in an instance context."""

from __future__ import annotations

import argparse
import re
from typing import Any, Callable, Optional

# Short defaults for contexts whose profile does not define its own rules.
COMMON_RULES_MD = """## Rules

- Keep secrets out of output and logs.
- Trading commands default to dry-run; use `--live` only when the profile allows it.
- Every order needs honest public reasoning.
"""

# Synthetic schedule agent surface (not a standalone uv script).
_SCHEDULE_HELPS: dict[str, str] = {
    "check": "Validate schedule/rules.d without activating",
    "reload": "Validate then atomically activate rules into state/active.json",
    "status": "Show active snapshot, drift, and per-rule state",
    "create": "Create an Agent-owned local interval wake rule",
    "list": "List Agent-owned local wake rules",
    "cancel": "Cancel an Agent-owned local wake rule",
}


def _as_enable_list(raw: Any) -> Optional[list[str]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(x) for x in raw]
    raise ValueError(f"bin.*.enable must be a string or list, got {type(raw)}")


def enable_matches(name: str, patterns: Optional[list[str]]) -> bool:
    """True if ``name`` is allowed. ``patterns`` None/empty = allow all.

    Each pattern is a regex matched with ``re.fullmatch``.
    Plain names like ``status`` still work (exact fullmatch).
    """
    if not patterns:
        return True
    for pat in patterns:
        try:
            if re.fullmatch(pat, name) is not None:
                return True
        except re.error as e:
            raise ValueError(f"invalid enable regex {pat!r}: {e}") from e
    return False


def resolve_enable(
    available: list[str], patterns: Optional[list[str]]
) -> list[str]:
    """Filter ``available`` command names by enable patterns (regex fullmatch)."""
    return [n for n in available if enable_matches(n, patterns)]


def normalize_bin(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return normalized ``bin`` map. Legacy ``wrappers`` + ``expose`` → ``bin``."""
    raw = cfg.get("bin")
    if isinstance(raw, dict) and raw:
        out: dict[str, dict[str, Any]] = {}
        for key, value in raw.items():
            name = str(key)
            if (
                name in {".", ".."}
                or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None
            ):
                raise ValueError(
                    f"bin name {name!r} must contain only letters, digits, ., _ or -"
                )
            if value is None:
                entry: dict[str, Any] = {}
            elif isinstance(value, dict):
                entry = dict(value)
            else:
                raise ValueError(f"bin.{name} must be a mapping or null")
            entry["enable"] = _as_enable_list(entry.get("enable"))
            out[name] = entry
        return out

    # Legacy one-release mapping.
    out = {}
    for w in cfg.get("wrappers") or []:
        name = str(w)
        if name == "harness":
            continue
        if (
            name in {".", ".."}
            or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None
        ):
            raise ValueError(
                f"wrapper name {name!r} must contain only letters, digits, ., _ or -"
            )
        out[name] = {"enable": None}
    expose = cfg.get("expose") or {}
    if isinstance(expose, dict) and expose.get("schedule"):
        out["schedule"] = {
            "via": "schedule",
            "enable": _as_enable_list(expose.get("schedule")),
        }
    return out


def bin_keys(cfg: dict[str, Any]) -> list[str]:
    return list(normalize_bin(cfg).keys())


def _load_parser(tool: str) -> Optional[argparse.ArgumentParser]:
    loaders: dict[str, Callable[[], argparse.ArgumentParser]] = {
        "clawstreet": lambda: __import__(
            "competitions.clawstreet.cli", fromlist=["build_parser"]
        ).build_parser(),
        "paper-ashare": lambda: __import__(
            "brokers.paper_ashare.cli", fromlist=["build_parser"]
        ).build_parser(),
        "fuyao": lambda: __import__(
            "marketdata.fuyao.cli", fromlist=["build_parser"]
        ).build_parser(),
    }
    loader = loaders.get(tool)
    if loader is None:
        return None
    return loader()


def _subcommand_helps(parser: argparse.ArgumentParser) -> dict[str, str]:
    """Map top-level subcommand name → short help (+ positionals if any)."""
    out: dict[str, str] = {}
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        help_by_name: dict[str, str] = {}
        for ca in action._choices_actions:
            # argparse stores the subcommand name on the choice action.
            label = getattr(ca, "dest", None) or getattr(ca, "metavar", None)
            if label and ca.help:
                help_by_name[str(label)] = str(ca.help)
        # choices keys are authoritative names
        for name, sub in action.choices.items():
            text = help_by_name.get(name) or (sub.description or "") or ""
            positionals: list[str] = []
            for a in sub._actions:
                if a.option_strings:
                    continue
                if a.dest in ("help",) or a.dest is None:
                    continue
                # Skip nested subparsers dest
                if isinstance(a, argparse._SubParsersAction):
                    nested = "|".join(sorted(a.choices.keys()))
                    if nested:
                        positionals.append(f"{{{nested}}}")
                    continue
                meta = a.metavar or a.dest
                if meta and str(meta) not in ("command",):
                    positionals.append(str(meta))
            if positionals:
                extra = " ".join(positionals)
                text = f"{text} — `{extra}`".strip(" —") if text else f"`{extra}`"
            out[str(name)] = text.strip()
    return out


def tool_command_helps(tool: str) -> dict[str, str]:
    """All top-level commands for a bin tool name."""
    if tool == "schedule" or tool.startswith("schedule"):
        return dict(_SCHEDULE_HELPS)
    try:
        from .tools import get_cli
        registered = get_cli(tool).command_helps()
        if registered:
            return registered
    except (KeyError, ImportError):
        pass
    parser = _load_parser(tool)
    if parser is None:
        return {}
    return _subcommand_helps(parser)


def render_tools_markdown(cfg: dict[str, Any]) -> str:
    """Build a compact ``## Tools`` index from ``bin:``.

    The command metadata is still used to restrict wrappers, but descriptions
    belong in the skill or CLI help.  Repeating them in every instance wastes
    context and makes the generated section compete with task-specific rules.
    """
    bins = normalize_bin(cfg)
    if not bins:
        return "## Tools\n\n_(no bin tools configured)_\n"

    lines = ["## Tools", ""]
    for name, entry in bins.items():
        via = str(entry.get("via") or name)
        enable = entry.get("enable")
        helps = tool_command_helps(via if via != "schedule" else "schedule")
        if not helps and via == name:
            helps = tool_command_helps(name)
        enabled = resolve_enable(list(helps), enable) if helps else []
        label = f"`./bin/{name}`" + (f" ({via})" if via != name else "")
        if not helps:
            detail = "passthrough"
        elif enable is None:
            detail = "all commands"
        elif enabled:
            detail = "commands: " + ", ".join(f"`{cmd}`" for cmd in enabled)
        else:
            detail = "no enabled commands"
        lines.append(f"- {label} — {detail}")

    skills = cfg.get("skills") or []
    npx = cfg.get("skills_npx") or []
    if skills or npx:
        label_parts = [str(s) for s in skills]
        if isinstance(npx, list):
            for item in npx:
                if isinstance(item, dict) and item.get("skill"):
                    label_parts.append(str(item["skill"]))
        lines.append(f"- Skills linked: {', '.join(label_parts) or '(none)'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_generated_appendix(cfg: dict[str, Any]) -> str:
    return render_tools_markdown(cfg).rstrip() + "\n\n" + COMMON_RULES_MD


def strip_generated_sections(body: str) -> str:
    """Remove a trailing generated Tools/Rules block if re-composing mid-file."""
    # Prefer cutting at the last top-level ## Tools that precedes ## Rules.
    marker = "\n## Tools\n"
    idx = body.rfind(marker)
    if idx == -1:
        if body.startswith("## Tools\n"):
            return ""
        return body.rstrip()
    return body[:idx].rstrip()
