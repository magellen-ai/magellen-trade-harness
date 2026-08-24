"""Instance schedule engine (harness-agnostic).

Design (see repo AGENTS.md "Schedule"):

- Source rules live in ``instances/<name>/schedule/rules.d/{base,local}/*.yaml``
  (one rule per file; ``local`` shadows ``base`` by rule id). Editing source
  files does nothing until ``harness schedule reload`` validates and compiles
  them into ``schedule/state/active.json`` — the only file the runner reads.
- ``base/`` is owned by strategy packs (``harness schedule apply <pack>``
  overwrites the whole dir); ``local/`` is owned by the agent/operator and is
  never touched by apply.
- ``schedule/state/`` (active snapshot, cursor, journal, lock) is runtime
  state: never overwritten by apply/reload beyond atomic activation.

Actions: the engine has one builtin (``script``). Any other ``action.kind``
is a **named action** looked up in ``config.yaml → schedule.actions`` (argv /
shell templates + optional before hooks). The engine never hardcodes a
specific coding-agent CLI — Claude / Codex / others bind via config.

Rule schema (v1)::

    id: research-tick            # optional; defaults to file stem
    enabled: true                # optional; default true
    concurrency: skip            # optional; only "skip" supported in v1
    trigger:
      kind: interval             # interval | cron
      every: 4h                  #   interval: 30s / 5m / 4h / 1d
      # expr: "0 9 * * 1-5"      #   cron: 5 numeric fields, local time
    condition:                   # optional gate, evaluated at fire time
      kind: script               # v1: script only (exit 0 = fire)
      run: "scripts/check.sh"    # shell command, cwd = instance dir
      timeout: 120               # optional, seconds
    action:
      kind: script               # builtin OR any name in schedule.actions
      run: "..."                 #   script: shell command
      # kind: wake-main          #   named: requires schedule.actions.wake-main
      # prompt / prompt_file:    #   if template uses {prompt}
      timeout: 3600              # optional, seconds
      # max_turns: "30"          # optional extras → {max_turns} etc.
      # context_files:           # optional; instance-relative paths → @path inject
      #   - memory/MEMORY.md

Named-action harness binding (``schedule.actions.<kind>``) may set
``context_files_mode``:

- ``argv`` (default): insert ``@path`` tokens after ``-p`` / ``--print`` in argv
  (Pi-style CLI file args).
- ``prompt_prefix``: prepend ``@path`` lines to ``{prompt}`` (Claude-style).

Shell templates always use ``prompt_prefix`` when ``context_files`` is set.
Missing files at fire time are skipped (logged); reload only warns.

Placeholders in named-action templates: ``{prompt}`` ``{instance}``
``{timeout}`` ``{max_turns}`` ``{condition_output}`` (and any other string
field on the rule action / action defaults). Inside ``prompt`` text itself,
``{condition_output}`` is substituted before the prompt is passed into
templates (nested placeholders are not re-expanded).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import instance as instance_mod

SCHEMA_VERSION = 1
TRIGGER_KINDS = ("interval", "cron")
CONDITION_KINDS = ("script",)
CONCURRENCY_MODES = ("skip",)

DEFAULT_CONDITION_TIMEOUT = 120
DEFAULT_NAMED_ACTION_TIMEOUT = 3600
DEFAULT_SCRIPT_TIMEOUT = 600
CONDITION_OUTPUT_LIMIT = 8000  # chars of condition stdout injected into prompts
CRON_LOOKBACK_CAP_MIN = 7 * 24 * 60  # max minutes scanned for missed cron fires
CONTEXT_FILES_MODES = ("argv", "prompt_prefix")
PRINT_FLAGS = ("-p", "--print")

# Verbs the generated instance-facing ``bin/schedule`` wrapper may forward.
AGENT_SAFE_VERBS = ("check", "reload", "status")

_INTERVAL_RE = re.compile(r"^(\d+)\s*(s|m|h|d)$")
_INTERVAL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def resolve_instance_dir(name: Optional[str]) -> Path:
    """Instance dir from explicit name, else $HARNESS_INSTANCE."""
    if name:
        path = instance_mod.instances_root() / name
    else:
        env = os.environ.get("HARNESS_INSTANCE", "")
        if not env:
            raise ValueError("no instance: pass a name or set HARNESS_INSTANCE")
        path = Path(env)
    if not path.is_dir():
        raise FileNotFoundError(f"instance not found: {path}")
    return path.resolve()


def schedule_dir(instance_dir: Path) -> Path:
    return instance_dir / "schedule"


def rules_dir(instance_dir: Path, layer: str) -> Path:
    return schedule_dir(instance_dir) / "rules.d" / layer


def state_dir(instance_dir: Path) -> Path:
    return schedule_dir(instance_dir) / "state"


def active_path(instance_dir: Path) -> Path:
    return state_dir(instance_dir) / "active.json"


def cursor_path(instance_dir: Path) -> Path:
    return state_dir(instance_dir) / "cursor.json"


def journal_path(instance_dir: Path) -> Path:
    return state_dir(instance_dir) / "journal.jsonl"


def ensure_layout(instance_dir: Path) -> None:
    for layer in ("base", "local"):
        rules_dir(instance_dir, layer).mkdir(parents=True, exist_ok=True)
    state_dir(instance_dir).mkdir(parents=True, exist_ok=True)


def journal(instance_dir: Path, event: str, **detail: Any) -> None:
    ensure_layout(instance_dir)
    entry = {"ts": _now().isoformat(timespec="seconds"), "event": event, **detail}
    with open(journal_path(instance_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _now() -> datetime:
    return datetime.now().astimezone()


# ---------------------------------------------------------------------------
# Interval / cron parsing
# ---------------------------------------------------------------------------


def parse_interval(text: str) -> int:
    """'30s' / '5m' / '4h' / '1d' → seconds."""
    m = _INTERVAL_RE.match(str(text).strip())
    if not m:
        raise ValueError(f"bad interval {text!r} (expected e.g. 30s / 5m / 4h / 1d)")
    seconds = int(m.group(1)) * _INTERVAL_UNITS[m.group(2)]
    if seconds <= 0:
        raise ValueError(f"interval must be positive: {text!r}")
    return seconds


@dataclass
class CronSpec:
    minute: frozenset[int]
    hour: frozenset[int]
    dom: frozenset[int]
    month: frozenset[int]
    dow: frozenset[int]
    dom_star: bool
    dow_star: bool


_CRON_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]  # dow 7 == sunday == 0


def _parse_cron_field(field: str, lo: int, hi: int) -> tuple[frozenset[int], bool]:
    """Supports * , - / with numeric values. Returns (values, is_star)."""
    values: set[int] = set()
    is_star = field == "*"
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"bad step in {field!r}")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start < lo or end > hi or start > end:
            raise ValueError(f"value out of range [{lo},{hi}] in {field!r}")
        values.update(range(start, end + 1, step))
    return frozenset(values), is_star


def parse_cron(expr: str) -> CronSpec:
    fields = str(expr).split()
    if len(fields) != 5:
        raise ValueError(
            f"bad cron {expr!r}: need 5 fields (minute hour dom month dow), numeric only"
        )
    parsed = []
    stars = []
    for field, (lo, hi) in zip(fields, _CRON_BOUNDS):
        try:
            values, is_star = _parse_cron_field(field, lo, hi)
        except ValueError as e:
            raise ValueError(f"bad cron {expr!r}: {e}") from None
        parsed.append(values)
        stars.append(is_star)
    dow = frozenset(0 if v == 7 else v for v in parsed[4])
    return CronSpec(
        minute=parsed[0],
        hour=parsed[1],
        dom=parsed[2],
        month=parsed[3],
        dow=dow,
        dom_star=stars[2],
        dow_star=stars[4],
    )


def cron_matches(spec: CronSpec, dt: datetime) -> bool:
    if dt.minute not in spec.minute or dt.hour not in spec.hour:
        return False
    if dt.month not in spec.month:
        return False
    dom_ok = dt.day in spec.dom
    dow_ok = ((dt.weekday() + 1) % 7) in spec.dow  # python Mon=0 → cron Sun=0
    # Standard cron: if both dom and dow are restricted, either may match.
    if spec.dom_star and spec.dow_star:
        return True
    if spec.dom_star:
        return dow_ok
    if spec.dow_star:
        return dom_ok
    return dom_ok or dow_ok


# ---------------------------------------------------------------------------
# Validation / compilation
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    level: str  # "error" | "warning"
    source: str  # e.g. "local/foo.yaml"
    rule_id: str
    message: str

    def render(self) -> str:
        return f"{self.level.upper()} {self.source} [{self.rule_id}]: {self.message}"


def _err(src: str, rid: str, msg: str) -> Issue:
    return Issue("error", src, rid, msg)


def _warn(src: str, rid: str, msg: str) -> Issue:
    return Issue("warning", src, rid, msg)


def _check_keys(
    raw: dict, allowed: set[str], src: str, rid: str, where: str, issues: list[Issue]
) -> None:
    for key in raw:
        if key not in allowed:
            issues.append(_err(src, rid, f"unknown key {key!r} in {where}"))


def _compile_trigger(raw: Any, src: str, rid: str, issues: list[Issue]) -> Optional[dict]:
    if not isinstance(raw, dict):
        issues.append(_err(src, rid, "trigger must be a mapping"))
        return None
    kind = raw.get("kind")
    if kind not in TRIGGER_KINDS:
        issues.append(_err(src, rid, f"trigger.kind must be one of {'|'.join(TRIGGER_KINDS)}"))
        return None
    if kind == "interval":
        _check_keys(raw, {"kind", "every"}, src, rid, "trigger", issues)
        try:
            seconds = parse_interval(raw.get("every", ""))
        except ValueError as e:
            issues.append(_err(src, rid, f"trigger.every: {e}"))
            return None
        return {"kind": "interval", "every": str(raw["every"]), "seconds": seconds}
    _check_keys(raw, {"kind", "expr"}, src, rid, "trigger", issues)
    expr = raw.get("expr", "")
    try:
        parse_cron(expr)
    except ValueError as e:
        issues.append(_err(src, rid, f"trigger.expr: {e}"))
        return None
    return {"kind": "cron", "expr": str(expr)}


def _compile_condition(raw: Any, src: str, rid: str, issues: list[Issue]) -> Optional[dict]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        issues.append(_err(src, rid, "condition must be a mapping"))
        return None
    kind = raw.get("kind")
    if kind not in CONDITION_KINDS:
        issues.append(
            _err(src, rid, f"condition.kind must be one of {'|'.join(CONDITION_KINDS)} (v1)")
        )
        return None
    _check_keys(raw, {"kind", "run", "timeout"}, src, rid, "condition", issues)
    run = raw.get("run")
    if not run or not isinstance(run, str):
        issues.append(_err(src, rid, "condition.run must be a non-empty shell command"))
        return None
    timeout = raw.get("timeout", DEFAULT_CONDITION_TIMEOUT)
    if not isinstance(timeout, int) or timeout <= 0:
        issues.append(_err(src, rid, "condition.timeout must be a positive integer (seconds)"))
        return None
    return {"kind": "script", "run": run, "timeout": timeout}


def _configured_actions(instance_dir: Path) -> dict[str, Any]:
    cfg_path = instance_dir / "config.yaml"
    if not cfg_path.is_file():
        return {}
    cfg = instance_mod.load_yaml(cfg_path)
    sched = cfg.get("schedule") or {}
    if not isinstance(sched, dict):
        return {}
    actions = sched.get("actions") or {}
    return actions if isinstance(actions, dict) else {}


def _template_placeholders(action_def: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def scan(value: Any) -> None:
        if isinstance(value, str):
            found.update(_PLACEHOLDER_RE.findall(value))
        elif isinstance(value, list):
            for item in value:
                scan(item)
        elif isinstance(value, dict):
            for item in value.values():
                scan(item)

    scan(action_def.get("argv"))
    scan(action_def.get("shell"))
    for hook in action_def.get("before") or []:
        scan(hook)
    return found


def _resolve_prompt(
    raw: dict[str, Any],
    src: str,
    rid: str,
    rule_file: Path,
    instance_dir: Path,
    issues: list[Issue],
    *,
    required: bool,
) -> tuple[Optional[str], Optional[str]]:
    prompt = raw.get("prompt")
    prompt_file = raw.get("prompt_file")
    if prompt and prompt_file:
        issues.append(_err(src, rid, "use only one of action.prompt / prompt_file"))
        return None, None
    if not prompt and not prompt_file:
        if required:
            issues.append(
                _err(src, rid, "action needs prompt or prompt_file (template uses {prompt})")
            )
            return None, None
        return None, None
    if prompt_file:
        candidate = (rule_file.parent / str(prompt_file)).resolve()
        sched_root = schedule_dir(instance_dir).resolve()
        pack_root = rule_file.parent.resolve()
        if not (
            str(candidate).startswith(str(sched_root) + os.sep)
            or str(candidate).startswith(str(pack_root) + os.sep)
        ):
            issues.append(
                _err(src, rid, f"prompt_file must stay within schedule/: {prompt_file}")
            )
            return None, None
        if not candidate.is_file():
            issues.append(_err(src, rid, f"prompt_file not found: {prompt_file}"))
            return None, None
        prompt = candidate.read_text(encoding="utf-8")
        if not isinstance(prompt, str) or not prompt.strip():
            issues.append(_err(src, rid, "prompt_file is empty"))
            return None, None
        return prompt, str(prompt_file)
    if not isinstance(prompt, str) or not prompt.strip():
        issues.append(_err(src, rid, "action.prompt must be non-empty"))
        return None, None
    return prompt, None


def _validate_action_def(action_def: Any, src: str, rid: str, issues: list[Issue]) -> bool:
    if not isinstance(action_def, dict):
        issues.append(_err(src, rid, "schedule.actions entry must be a mapping"))
        return False
    has_argv = "argv" in action_def
    has_shell = "shell" in action_def
    if has_argv == has_shell:
        issues.append(
            _err(src, rid, "named action needs exactly one of argv (list) or shell (string)")
        )
        return False
    if has_argv:
        argv = action_def["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            issues.append(_err(src, rid, "action argv must be a non-empty list of strings"))
            return False
    else:
        if not isinstance(action_def["shell"], str) or not action_def["shell"].strip():
            issues.append(_err(src, rid, "action shell must be a non-empty string"))
            return False
    before = action_def.get("before") or []
    if before and not isinstance(before, list):
        issues.append(_err(src, rid, "action before must be a list of hooks"))
        return False
    for i, hook in enumerate(before):
        if not isinstance(hook, dict):
            issues.append(_err(src, rid, f"before[{i}] must be a mapping"))
            return False
        if ("argv" in hook) == ("shell" in hook):
            issues.append(_err(src, rid, f"before[{i}] needs exactly one of argv / shell"))
            return False
    cwd = action_def.get("cwd", "instance")
    if cwd not in ("instance", "repo"):
        issues.append(_err(src, rid, "action cwd must be 'instance' or 'repo'"))
        return False
    mode = action_def.get("context_files_mode", "argv")
    if mode not in CONTEXT_FILES_MODES:
        issues.append(
            _err(
                src,
                rid,
                f"context_files_mode must be one of {CONTEXT_FILES_MODES}; got {mode!r}",
            )
        )
        return False
    return True


def _compile_context_files(
    raw: dict[str, Any],
    src: str,
    rid: str,
    instance_dir: Path,
    issues: list[Issue],
) -> Optional[list[str]]:
    """Validate and normalize action.context_files (instance-relative paths)."""
    if "context_files" not in raw:
        return None
    value = raw["context_files"]
    if not isinstance(value, list):
        issues.append(_err(src, rid, "action.context_files must be a list of paths"))
        return None
    root = instance_dir.resolve()
    out: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            issues.append(_err(src, rid, f"action.context_files[{i}] must be a non-empty string"))
            return None
        rel = item.strip().replace("\\", "/")
        if rel.startswith("/") or re.match(r"^[A-Za-z]:/", rel):
            issues.append(_err(src, rid, f"action.context_files[{i}] must be relative: {item}"))
            return None
        parts = Path(rel).parts
        if ".." in parts:
            issues.append(_err(src, rid, f"action.context_files[{i}] must not contain '..': {item}"))
            return None
        if not parts or parts[0] == "":
            issues.append(_err(src, rid, f"action.context_files[{i}] is empty"))
            return None
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            issues.append(
                _err(src, rid, f"action.context_files[{i}] escapes instance dir: {item}")
            )
            return None
        if rel in seen:
            continue
        seen.add(rel)
        if not candidate.is_file():
            issues.append(
                _warn(src, rid, f"context_files not found yet (ok if created later): {rel}")
            )
        out.append(rel)
    return out


def _resolve_context_ats(
    instance_dir: Path, paths: list[str]
) -> tuple[list[str], list[str]]:
    """Return (@path tokens for existing files, skipped relative paths)."""
    root = instance_dir.resolve()
    ats: list[str] = []
    skipped: list[str] = []
    for rel in paths:
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            skipped.append(rel)
            continue
        if not candidate.is_file():
            skipped.append(rel)
            continue
        ats.append("@" + rel.replace("\\", "/"))
    return ats, skipped


def _inject_context_ats_argv(argv: list[str], ats: list[str]) -> list[str]:
    """Insert @path tokens after the first -p/--print flag (and its value if present).

    Patterns handled:
      [..., "-p", "{prompt}", ...]  → [..., "-p", @a, @b, "{prompt}", ...]
      [..., "-p", ...] with no following value yet — inserts after -p
    If no print flag, append ats before the last arg when that looks like the
    prompt, else append at end.
    """
    if not ats:
        return argv
    for i, token in enumerate(argv):
        if token in PRINT_FLAGS:
            # Prefer inserting after the flag's value (usual: -p "{prompt}").
            if i + 1 < len(argv):
                insert_at = i + 1
                return argv[:insert_at] + ats + argv[insert_at:]
            return argv + ats
    return argv + ats


def _apply_context_files(
    *,
    prompt: str,
    argv: Optional[list[str]],
    action_def: dict[str, Any],
    instance_dir: Path,
    paths: list[str],
    log_lines: list[str],
) -> tuple[str, Optional[list[str]]]:
    """Apply context_files via @path according to harness mode. Mutates delivery only."""
    if not paths:
        return prompt, argv
    ats, skipped = _resolve_context_ats(instance_dir, paths)
    if skipped:
        log_lines.append(f"# context_files skipped (missing): {skipped}")
    if not ats:
        log_lines.append("# context_files: (none present)")
        return prompt, argv

    mode = action_def.get("context_files_mode", "argv")
    if "shell" in action_def and "argv" not in action_def:
        mode = "prompt_prefix"
    if mode not in CONTEXT_FILES_MODES:
        mode = "argv"

    log_lines.append(f"# context_files: {ats} mode={mode}")
    if mode == "prompt_prefix" or argv is None:
        prefix = "\n".join(ats) + "\n\n"
        return prefix + prompt, argv
    return prompt, _inject_context_ats_argv(argv, ats)


def _compile_action(
    raw: Any,
    src: str,
    rid: str,
    rule_file: Path,
    instance_dir: Path,
    issues: list[Issue],
    configured_actions: Optional[dict[str, Any]] = None,
) -> Optional[dict]:
    if not isinstance(raw, dict):
        issues.append(_err(src, rid, "action must be a mapping"))
        return None
    kind = raw.get("kind")
    if not kind or not isinstance(kind, str):
        issues.append(_err(src, rid, "action.kind is required"))
        return None

    if kind == "script":
        _check_keys(raw, {"kind", "run", "timeout"}, src, rid, "action", issues)
        run = raw.get("run")
        if not run or not isinstance(run, str):
            issues.append(_err(src, rid, "action.run must be a non-empty shell command"))
            return None
        timeout = raw.get("timeout", DEFAULT_SCRIPT_TIMEOUT)
        if not isinstance(timeout, int) or timeout <= 0:
            issues.append(_err(src, rid, "action.timeout must be a positive integer (seconds)"))
            return None
        return {"kind": "script", "run": run, "timeout": timeout}

    # Named action — bound via config.schedule.actions[kind]
    actions = (
        configured_actions
        if configured_actions is not None
        else _configured_actions(instance_dir)
    )
    if kind not in actions:
        known = sorted(actions.keys())
        issues.append(
            _err(
                src,
                rid,
                f"unknown action.kind {kind!r}; builtin=script; "
                f"configured={known or '(none — add schedule.actions in config.yaml)'}",
            )
        )
        return None
    action_def = actions[kind]
    if not _validate_action_def(action_def, src, rid, issues):
        return None

    placeholders = _template_placeholders(action_def)
    needs_prompt = "prompt" in placeholders
    reserved = {"kind", "prompt", "prompt_file", "timeout", "run", "context_files"}
    # Allow arbitrary string/int extras for placeholders (e.g. max_turns).
    for key, value in raw.items():
        if key in reserved:
            continue
        if not isinstance(value, (str, int, bool)):
            issues.append(
                _err(src, rid, f"action.{key} must be a scalar (for template placeholders)")
            )
            return None

    prompt, prompt_file = _resolve_prompt(
        raw, src, rid, rule_file, instance_dir, issues, required=needs_prompt
    )
    if needs_prompt and prompt is None:
        return None

    context_files = _compile_context_files(raw, src, rid, instance_dir, issues)
    if "context_files" in raw and context_files is None:
        return None

    timeout = raw.get("timeout", DEFAULT_NAMED_ACTION_TIMEOUT)
    if not isinstance(timeout, int) or timeout <= 0:
        issues.append(_err(src, rid, "action.timeout must be a positive integer (seconds)"))
        return None

    defaults = action_def.get("defaults") or {}
    if defaults and not isinstance(defaults, dict):
        issues.append(_err(src, rid, "schedule.actions[].defaults must be a mapping"))
        return None

    params: dict[str, str] = {}
    for key, value in {**defaults, **{k: v for k, v in raw.items() if k not in reserved}}.items():
        params[str(key)] = str(value)

    out: dict[str, Any] = {
        "kind": kind,
        "timeout": timeout,
        "params": params,
    }
    if prompt is not None:
        out["prompt"] = prompt
    if prompt_file:
        out["prompt_file"] = prompt_file
    if context_files:
        out["context_files"] = context_files
    return out


_TOP_KEYS = {"id", "enabled", "concurrency", "trigger", "condition", "action"}


def _compile_rule(
    rule_file: Path,
    layer: str,
    instance_dir: Path,
    issues: list[Issue],
    configured_actions: Optional[dict[str, Any]] = None,
) -> Optional[dict]:
    src = f"{layer}/{rule_file.name}"
    try:
        raw = instance_mod.load_yaml(rule_file)
    except Exception as e:
        issues.append(_err(src, rule_file.stem, f"cannot parse: {e}"))
        return None

    rid = str(raw.get("id") or rule_file.stem)
    _check_keys(raw, _TOP_KEYS, src, rid, "rule", issues)

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        issues.append(_err(src, rid, "enabled must be true/false"))
        return None
    concurrency = raw.get("concurrency", "skip")
    if concurrency not in CONCURRENCY_MODES:
        issues.append(
            _err(src, rid, f"concurrency must be one of {'|'.join(CONCURRENCY_MODES)} (v1)")
        )
        return None
    if "trigger" not in raw or "action" not in raw:
        issues.append(_err(src, rid, "rule needs both trigger and action"))
        return None

    trigger = _compile_trigger(raw["trigger"], src, rid, issues)
    condition = _compile_condition(raw.get("condition"), src, rid, issues)
    action = _compile_action(
        raw["action"],
        src,
        rid,
        rule_file,
        instance_dir,
        issues,
        configured_actions=configured_actions,
    )
    if trigger is None or action is None:
        return None
    if raw.get("condition") is not None and condition is None:
        return None

    return {
        "id": rid,
        "layer": layer,
        "source": src,
        "enabled": enabled,
        "concurrency": concurrency,
        "trigger": trigger,
        "condition": condition,
        "action": action,
    }


def _layer_rule_files(layer_dir: Path) -> list[Path]:
    if not layer_dir.is_dir():
        return []
    return sorted(
        p for p in layer_dir.iterdir() if p.is_file() and p.suffix in (".yaml", ".yml")
    )


def check_rules(
    instance_dir: Path, base_dir_override: Optional[Path] = None
) -> tuple[list[dict], list[Issue]]:
    """Validate + compile the merged rule set (local shadows base by id).

    Returns (compiled_rules, issues); rules are usable iff no error issues.
    """
    issues: list[Issue] = []
    base_dir = base_dir_override or rules_dir(instance_dir, "base")
    local_dir = rules_dir(instance_dir, "local")
    configured_actions = _configured_actions(instance_dir)

    layers: dict[str, dict[str, dict]] = {"base": {}, "local": {}}
    for layer, layer_dir in (("base", base_dir), ("local", local_dir)):
        for rule_file in _layer_rule_files(layer_dir):
            rule = _compile_rule(
                rule_file, layer, instance_dir, issues, configured_actions=configured_actions
            )
            if rule is None:
                continue
            if rule["id"] in layers[layer]:
                issues.append(
                    _err(rule["source"], rule["id"], f"duplicate id in {layer}/ layer")
                )
                continue
            layers[layer][rule["id"]] = rule

    merged = dict(layers["base"])
    for rid, rule in layers["local"].items():
        if rid not in merged:
            issues.append(
                _warn(rule["source"], rid, "local rule does not shadow any base rule (new rule)")
            )
        merged[rid] = rule

    rules = sorted(merged.values(), key=lambda r: r["id"])
    if rules and all(not r["enabled"] for r in rules):
        issues.append(_warn("-", "-", "all rules are disabled"))
    return rules, issues


def source_hash(instance_dir: Path) -> str:
    """Hash of everything under schedule/ except state/ (drift detection)."""
    root = schedule_dir(instance_dir)
    h = hashlib.sha256()
    if root.is_dir():
        skip = state_dir(instance_dir).resolve()
        for path in sorted(root.rglob("*")):
            resolved = path.resolve()
            if resolved == skip or str(resolved).startswith(str(skip) + os.sep):
                continue
            if path.is_file():
                h.update(str(path.relative_to(root)).encode())
                h.update(b"\0")
                h.update(path.read_bytes())
                h.update(b"\0")
    return h.hexdigest()[:16]


def load_active(instance_dir: Path) -> Optional[dict]:
    path = active_path(instance_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def reload_schedule(instance_dir: Path) -> tuple[Optional[dict], list[Issue]]:
    """check → compile → atomically activate. Keeps old active on errors."""
    ensure_layout(instance_dir)
    rules, issues = check_rules(instance_dir)
    if any(i.level == "error" for i in issues):
        journal(
            instance_dir,
            "reload_failed",
            errors=[i.render() for i in issues if i.level == "error"],
        )
        return None, issues

    snapshot = {
        "schema": SCHEMA_VERSION,
        "activated_at": _now().isoformat(timespec="seconds"),
        "source_hash": source_hash(instance_dir),
        "rules": rules,
    }
    target = active_path(instance_dir)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".active.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    journal(
        instance_dir,
        "activated",
        rules=len(rules),
        enabled=sum(1 for r in rules if r["enabled"]),
        source_hash=snapshot["source_hash"],
    )
    return snapshot, issues


# ---------------------------------------------------------------------------
# Strategy packs
# ---------------------------------------------------------------------------


def packs_root() -> Path:
    return instance_mod.repo_root() / "configs" / "schedules"


def list_packs() -> list[str]:
    root = packs_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def apply_pack(instance_dir: Path, pack: str) -> tuple[Optional[dict], list[Issue]]:
    """Validate pack (merged with current local/) then overwrite base/ + reload.

    Nothing changes on validation failure.
    """
    pack_dir = packs_root() / pack
    if not pack_dir.is_dir():
        raise FileNotFoundError(f"pack not found: {pack_dir} (available: {list_packs()})")
    ensure_layout(instance_dir)

    _, issues = check_rules(instance_dir, base_dir_override=pack_dir)
    if any(i.level == "error" for i in issues):
        return None, issues

    base = rules_dir(instance_dir, "base")
    if base.exists():
        shutil.rmtree(base)
    shutil.copytree(pack_dir, base)
    journal(instance_dir, "apply_pack", pack=pack)

    snapshot, reload_issues = reload_schedule(instance_dir)
    assert snapshot is not None, "pack validated but reload failed"
    return snapshot, issues + reload_issues


# ---------------------------------------------------------------------------
# Runner (tick)
# ---------------------------------------------------------------------------


def _load_cursor(instance_dir: Path) -> dict[str, Any]:
    path = cursor_path(instance_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _save_cursor(instance_dir: Path, cursor: dict[str, Any]) -> None:
    path = cursor_path(instance_dir)
    path.write_text(json.dumps(cursor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _is_due(rule: dict, cursor_entry: dict[str, Any], now: datetime) -> bool:
    trigger = rule["trigger"]
    last_fired = _parse_ts(cursor_entry.get("last_fired"))
    if trigger["kind"] == "interval":
        if last_fired is None:
            return True  # first tick after activation fires immediately
        return (now - last_fired).total_seconds() >= trigger["seconds"]

    spec = parse_cron(trigger["expr"])
    last_checked = _parse_ts(cursor_entry.get("last_checked"))
    if last_checked is None:
        return cron_matches(spec, now)
    # Catch fires missed between ticks, capped to avoid unbounded scans.
    start = max(last_checked, now - timedelta(minutes=CRON_LOOKBACK_CAP_MIN))
    cursor_min = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end_min = now.replace(second=0, microsecond=0)
    while cursor_min <= end_min:
        if cron_matches(spec, cursor_min):
            return True
        cursor_min += timedelta(minutes=1)
    return False


def _run_shell(
    command: str,
    instance_dir: Path,
    timeout: int,
    *,
    cwd: Optional[Path] = None,
) -> tuple[int, str]:
    env = instance_mod.instance_process_env(instance_dir)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd or instance_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"


def _expand_placeholders(text: str, vars: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in vars:
            raise KeyError(key)
        return vars[key]

    return _PLACEHOLDER_RE.sub(repl, text)


def _run_argv(
    argv: list[str],
    cwd: Path,
    instance_dir: Path,
    timeout: int,
    log_file: Optional[Path] = None,
) -> int:
    env = instance_mod.instance_process_env(instance_dir)
    try:
        if log_file is None:
            proc = subprocess.run(
                argv, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout
            )
            return proc.returncode
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(f"# argv: {argv!r}\n")
            log.flush()
            proc = subprocess.run(
                argv,
                cwd=str(cwd),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            log.write(f"\n# exit={proc.returncode}\n")
            return proc.returncode
    except subprocess.TimeoutExpired:
        if log_file is not None:
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(f"\n# timeout after {timeout}s\n")
        return 124
    except FileNotFoundError:
        if log_file is not None:
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(f"\n# executable not found: {argv[0]!r}\n")
        return 127


def run_configured_action(
    instance_dir: Path,
    action: dict[str, Any],
    *,
    condition_output: str,
    log_file: Path,
    configured_actions: Optional[dict[str, Any]] = None,
) -> int:
    """Execute a named action from config.schedule.actions (harness-agnostic)."""
    actions = (
        configured_actions
        if configured_actions is not None
        else _configured_actions(instance_dir)
    )
    action_def = actions[action["kind"]]
    prompt = action.get("prompt") or ""
    if prompt:
        # Nested placeholders inside {prompt} are not re-expanded by templates.
        prompt = prompt.replace("{condition_output}", condition_output)

    context_paths = list(action.get("context_files") or [])
    context_log: list[str] = []
    argv_template: Optional[list[str]] = (
        list(action_def["argv"]) if "argv" in action_def else None
    )
    prompt, argv_template = _apply_context_files(
        prompt=prompt,
        argv=argv_template,
        action_def=action_def,
        instance_dir=instance_dir,
        paths=context_paths,
        log_lines=context_log,
    )

    vars: dict[str, str] = {
        "instance": instance_dir.name,
        "timeout": str(action["timeout"]),
        "condition_output": condition_output,
        "prompt": prompt,
        **(action.get("params") or {}),
    }

    cwd_mode = action_def.get("cwd", "instance")
    cwd = instance_dir if cwd_mode == "instance" else instance_mod.repo_root()
    timeout = action["timeout"]

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as log:
        log.write(f"# named-action {action['kind']} {_now().isoformat(timespec='seconds')}\n")
        for line in context_log:
            log.write(line + "\n")

    try:
        for i, hook in enumerate(action_def.get("before") or []):
            hook_cwd_mode = hook.get("cwd", "repo")
            hook_cwd = (
                instance_dir if hook_cwd_mode == "instance" else instance_mod.repo_root()
            )
            if "argv" in hook:
                argv = [_expand_placeholders(x, vars) for x in hook["argv"]]
                code = _run_argv(argv, hook_cwd, instance_dir, min(timeout, 120), log_file)
            else:
                shell = _expand_placeholders(hook["shell"], vars)
                code, output = _run_shell(
                    shell, instance_dir, min(timeout, 120), cwd=hook_cwd
                )
                with open(log_file, "a", encoding="utf-8") as log:
                    log.write(f"# before[{i}] shell exit={code}\n")
                    if output:
                        log.write(output)
            if code != 0:
                with open(log_file, "a", encoding="utf-8") as log:
                    log.write(f"# before[{i}] failed exit={code}\n")
                return code

        if argv_template is not None:
            argv = [_expand_placeholders(x, vars) for x in argv_template]
            return _run_argv(argv, cwd, instance_dir, timeout, log_file)
        shell = _expand_placeholders(action_def["shell"], vars)
        code, output = _run_shell(shell, instance_dir, timeout, cwd=cwd)
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(f"# shell: {shell!r}\n")
            log.write(output)
            log.write(f"\n# exit={code}\n")
        return code
    except KeyError as e:
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(f"\n# missing placeholder {{{e.args[0]}}}\n")
        return 2


def tick(
    instance_dir: Path,
    dry_run: bool = False,
    only_rule: Optional[str] = None,
) -> list[str]:
    """Evaluate the active snapshot once. Returns human-readable report lines.

    ``only_rule`` forces that rule to fire regardless of its trigger (for
    manual testing); other rules are skipped entirely.
    """
    ensure_layout(instance_dir)
    lines: list[str] = []

    lock_file = open(state_dir(instance_dir) / ".lock", "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lines.append("TICK_SKIP another tick is running (lock held)")
        journal(instance_dir, "tick_skipped", reason="lock_held")
        return lines

    try:
        active = load_active(instance_dir)
        if active is None:
            lines.append("TICK_NOOP no active schedule (run: harness schedule reload)")
            return lines
        # Drift is reported by `harness schedule status`, not on every tick.

        now = _now()
        cursor = _load_cursor(instance_dir)
        configured_actions = _configured_actions(instance_dir)
        fired = 0

        for rule in active.get("rules", []):
            rid = rule["id"]
            if only_rule is not None and rid != only_rule:
                continue
            if not rule["enabled"] and only_rule is None:
                continue
            entry = cursor.setdefault(rid, {})
            due = True if only_rule == rid else _is_due(rule, entry, now)
            entry["last_checked"] = now.isoformat(timespec="seconds")
            if not due:
                continue

            if dry_run:
                lines.append(f"WOULD_FIRE {rid} ({rule['trigger']['kind']})")
                continue

            condition_output = ""
            cond = rule.get("condition")
            if cond is not None:
                code, output = _run_shell(cond["run"], instance_dir, cond["timeout"])
                if code != 0:
                    lines.append(f"CONDITION_SKIP {rid} exit={code}")
                    journal(instance_dir, "condition_skip", rule=rid, exit=code)
                    continue
                condition_output = output.strip()[:CONDITION_OUTPUT_LIMIT]

            action = rule["action"]
            ts_tag = now.strftime("%Y%m%dT%H%M%S")
            if action["kind"] == "script":
                code, output = _run_shell(action["run"], instance_dir, action["timeout"])
                detail = {"output_tail": output.strip()[-500:]}
            else:
                log_file = instance_dir / "logs" / "schedule" / f"{rid}.{ts_tag}.log"
                code = run_configured_action(
                    instance_dir,
                    action,
                    condition_output=condition_output,
                    log_file=log_file,
                    configured_actions=configured_actions,
                )
                detail = {"log": str(log_file.relative_to(instance_dir))}

            entry["last_fired"] = now.isoformat(timespec="seconds")
            fired += 1
            status = "FIRED" if code == 0 else f"FIRED_ERR exit={code}"
            lines.append(f"{status} {rid} action={action['kind']} {detail}")
            journal(
                instance_dir,
                "fired" if code == 0 else "fire_error",
                rule=rid,
                action=action["kind"],
                exit=code,
                **detail,
            )

        if not dry_run:
            _save_cursor(instance_dir, cursor)
        if fired == 0 and not any(line.startswith("WOULD_FIRE") for line in lines):
            lines.append("TICK_OK nothing due")
        else:
            lines.append(f"TICK_OK fired={fired}" if not dry_run else "TICK_OK (dry-run)")
        return lines
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def status_report(instance_dir: Path) -> list[str]:
    ensure_layout(instance_dir)
    lines: list[str] = []
    active = load_active(instance_dir)
    current_hash = source_hash(instance_dir)

    if active is None:
        lines.append("ACTIVE none (run: harness schedule reload)")
    else:
        rules = active.get("rules", [])
        enabled = sum(1 for r in rules if r["enabled"])
        lines.append(
            f"ACTIVE rules={len(rules)} enabled={enabled} "
            f"activated_at={active.get('activated_at')} hash={active.get('source_hash')}"
        )
        drift = active.get("source_hash") != current_hash
        lines.append(f"DRIFT {'yes — edited but not reloaded' if drift else 'no'}")

    _, issues = check_rules(instance_dir)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    lines.append(f"SOURCE errors={len(errors)} warnings={len(warnings)}")
    for issue in errors + warnings:
        lines.append("  " + issue.render())

    if active is not None:
        cursor = _load_cursor(instance_dir)
        for rule in active.get("rules", []):
            trig = rule["trigger"]
            trig_s = f"interval:{trig['every']}" if trig["kind"] == "interval" else f"cron:{trig['expr']}"
            entry = cursor.get(rule["id"], {})
            lines.append(
                f"RULE {rule['id']} layer={rule['layer']} trigger={trig_s} "
                f"enabled={str(rule['enabled']).lower()} "
                f"condition={'yes' if rule.get('condition') else 'no'} "
                f"last_fired={entry.get('last_fired') or 'never'}"
            )
    return lines
