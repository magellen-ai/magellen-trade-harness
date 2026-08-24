"""Runtime CLI: instance init/launch/sync-*, skills list, schedule engine."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from . import instance as instance_mod
from . import schedule as schedule_mod


def _die(exc: BaseException) -> None:
    print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)


def cmd_instance_init(args: argparse.Namespace) -> None:
    skills = args.skills.split(",") if args.skills else None
    if skills is not None:
        skills = [s.strip() for s in skills if s.strip()]
    try:
        path = instance_mod.init_instance(
            args.name,
            profile=args.profile,
            skills=skills,
            force=args.force,
        )
    except (OSError, ValueError, RuntimeError, FileNotFoundError, FileExistsError) as e:
        _die(e)
    cfg = instance_mod.load_yaml(path / "config.yaml")
    print(f"INSTANCE_OK {path}")
    print(f"profile={cfg.get('profile')} harness={cfg.get('harness')}")
    print(f"skills={cfg.get('skills')}")
    from . import agent_context as ac_mod

    bins = ac_mod.bin_keys(cfg)
    if "clawstreet" in bins:
        print("Bind agent: uv run clawstreet register --instance", args.name)
        print("Or paste key into", path / "agent" / "secrets.env")
    elif "paper-ashare" in bins:
        print(
            "Paper account: uv run paper-ashare --account default accounts init "
            f"(cwd or HARNESS_INSTANCE={path})"
        )
        print("Keys (HITHINK/TAVILY/AIPROXY) come from repo .env via config env; optional agent/secrets.env")
    else:
        print("Optional secrets:", path / "agent" / "secrets.env")
    print("Settings: uv run harness instance sync-settings", args.name)
    print("Then: uv run harness instance launch --show-cmd", args.name)


def cmd_instance_launch(args: argparse.Namespace) -> None:
    extra = list(getattr(args, "argv", None) or [])
    if extra and extra[0] == "--":
        extra = extra[1:]
    try:
        code = instance_mod.launch_instance(
            args.name, dry_print=args.print_only, extra_argv=extra or None
        )
    except Exception as e:
        _die(e)
    sys.exit(code)


def cmd_instance_sync_skills(args: argparse.Namespace) -> None:
    try:
        selected = instance_mod.sync_instance_skills(args.name)
    except Exception as e:
        _die(e)
    cfg = instance_mod.load_yaml(instance_mod.instances_root() / args.name / "config.yaml")
    npx = instance_mod.normalize_skills_npx(cfg.get("skills_npx"))
    print(f"SYNC_OK skills={selected}")
    if npx:
        print(
            "skills_npx="
            + ", ".join(f"{e['package']}@{e['skill']}" for e in npx)
        )


def cmd_instance_sync_settings(args: argparse.Namespace) -> None:
    try:
        written = instance_mod.sync_instance_settings(args.name)
    except Exception as e:
        _die(e)
    cfg = instance_mod.load_yaml(instance_mod.instances_root() / args.name / "config.yaml")
    _key, env, missing = instance_mod.resolve_env_from(cfg)
    print(f"RUNTIME_OK files={[str(p) for p in written]}")
    print(f"dotenv={instance_mod.repo_root() / '.env'}")
    print(f"env_key={_key} env_keys={sorted(env.keys())}")
    npx = instance_mod.normalize_skills_npx(cfg.get("skills_npx"))
    if npx:
        print(
            "skills_npx="
            + ", ".join(f"{e['package']}@{e['skill']}" for e in npx)
        )
    if missing:
        print(f"unresolved=$refs missing in .env/process: {missing}")


def cmd_instance_sync_bin(args: argparse.Namespace) -> None:
    try:
        written = instance_mod.sync_instance_bin(args.name)
    except Exception as e:
        _die(e)
    print(f"BIN_OK wrappers={[p.name for p in written]}")


def cmd_skills_list(_args: argparse.Namespace) -> None:
    local = instance_mod.list_available_skills()
    print("local skills/:")
    print("\n".join(f"  {s}" for s in local) or "  (none)")
    print("npx skills (declare via profile skills_npx; installed under ~/.agents/skills):")
    print("  e.g. package=HiThink-Tech/Financial-API skill=hithink-finance")


def cmd_profiles_list(_args: argparse.Namespace) -> None:
    print("\n".join(instance_mod.list_profiles()) or "(no configs/profiles/)")


def cmd_harnesses_list(_args: argparse.Namespace) -> None:
    print("\n".join(instance_mod.list_harnesses()) or "(no configs/harnesses/)")


# --- schedule -------------------------------------------------------------


def _schedule_instance(args: argparse.Namespace):
    try:
        return schedule_mod.resolve_instance_dir(getattr(args, "name", None))
    except Exception as e:
        _die(e)


def cmd_schedule_check(args: argparse.Namespace) -> None:
    instance_dir = _schedule_instance(args)
    schedule_mod.ensure_layout(instance_dir)
    rules, issues = schedule_mod.check_rules(instance_dir)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    if errors:
        print(f"CHECK_FAIL errors={len(errors)} warnings={len(warnings)}")
    else:
        base = sum(1 for r in rules if r["layer"] == "base")
        print(
            f"CHECK_OK rules={len(rules)} (base={base} local={len(rules) - base}) "
            f"warnings={len(warnings)}"
        )
    for issue in errors + warnings:
        print("  " + issue.render())
    if errors:
        sys.exit(1)


def cmd_schedule_reload(args: argparse.Namespace) -> None:
    instance_dir = _schedule_instance(args)
    snapshot, issues = schedule_mod.reload_schedule(instance_dir)
    for issue in issues:
        print("  " + issue.render())
    if snapshot is None:
        print("RELOAD_FAIL active snapshot unchanged; fix errors above and rerun")
        sys.exit(1)
    enabled = sum(1 for r in snapshot["rules"] if r["enabled"])
    print(
        f"RELOAD_OK rules={len(snapshot['rules'])} enabled={enabled} "
        f"hash={snapshot['source_hash']}"
    )


def cmd_schedule_status(args: argparse.Namespace) -> None:
    instance_dir = _schedule_instance(args)
    for line in schedule_mod.status_report(instance_dir):
        print(line)


def cmd_schedule_apply(args: argparse.Namespace) -> None:
    instance_dir = _schedule_instance(args)
    pack = getattr(args, "pack", None) or None
    try:
        label, _pack_dir = schedule_mod.resolve_schedule_dir(instance_dir, pack)
        snapshot, issues = schedule_mod.apply_pack(instance_dir, pack)
    except Exception as e:
        _die(e)
    for issue in issues:
        print("  " + issue.render())
    if not snapshot:
        print(f"APPLY_FAIL pack={label} rejected; base/ and active unchanged")
        sys.exit(1)
    print(f"APPLY_OK pack={label} rules={len(snapshot['rules'])} hash={snapshot['source_hash']}")


def cmd_schedule_tick(args: argparse.Namespace) -> None:
    instance_dir = _schedule_instance(args)
    try:
        lines = schedule_mod.tick(instance_dir, dry_run=args.dry_run, only_rule=args.rule)
    except Exception as e:
        _die(e)
    for line in lines:
        print(line)


def cmd_schedule_packs(_args: argparse.Namespace) -> None:
    packs = schedule_mod.list_packs()
    if not packs:
        print("(no configs/profiles/*/schedule/)")
        return
    for name in packs:
        print(name)


def register_commands(sub: argparse._SubParsersAction) -> None:
    p_skills = sub.add_parser("skills", help="Skill library helpers")
    skills_sub = p_skills.add_subparsers(dest="skills_command")
    p_skills_list = skills_sub.add_parser("list", help="List skills/ library")
    p_skills_list.set_defaults(func=cmd_skills_list)

    p_inst = sub.add_parser("instance", help="Harness instance management")
    inst_sub = p_inst.add_subparsers(dest="instance_command")

    p_init = inst_sub.add_parser("init", help="Create gitignored instance workdir from a profile")
    p_init.add_argument("name")
    p_init.add_argument(
        "--profile",
        default=instance_mod.DEFAULT_PROFILE,
        help=f"configs/profiles/<id> (default: {instance_mod.DEFAULT_PROFILE})",
    )
    p_init.add_argument(
        "--skills",
        help="Comma-separated skill names; default = profile config.yaml skills",
    )
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_instance_init)

    p_launch = inst_sub.add_parser("launch", help="Run launch.argv from instance config")
    p_launch.add_argument("name")
    p_launch.add_argument(
        "--show-cmd",
        dest="print_only",
        action="store_true",
        help="Print cwd/env/command only (do not execute)",
    )
    p_launch.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help=argparse.SUPPRESS,  # legacy alias; prefer --show-cmd (avoids clash with pi -p/--print)
    )
    p_launch.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="Extra args for the agent; put them after -- (e.g. launch NAME -- -p 'hi')",
    )
    p_launch.set_defaults(func=cmd_instance_launch)

    p_sync = inst_sub.add_parser("sync-skills", help="Re-link skills into config skill_dirs")
    p_sync.add_argument("name")
    p_sync.set_defaults(func=cmd_instance_sync_skills)

    p_sync_settings = inst_sub.add_parser(
        "sync-settings",
        help="Materialize harness templates + resolve config env (process_env applied at launch/tick)",
    )
    p_sync_settings.add_argument("name")
    p_sync_settings.set_defaults(func=cmd_instance_sync_settings)

    p_sync_bin = inst_sub.add_parser(
        "sync-bin",
        help="Regenerate instance bin/ from config bin: + refresh agent context (Tools/Rules)",
    )
    p_sync_bin.add_argument("name")
    p_sync_bin.set_defaults(func=cmd_instance_sync_bin)

    p_profiles = sub.add_parser("profiles", help="Experiment profiles under configs/profiles/")
    profiles_sub = p_profiles.add_subparsers(dest="profiles_command")
    p_profiles_list = profiles_sub.add_parser("list", help="List available profiles")
    p_profiles_list.set_defaults(func=cmd_profiles_list)

    p_harnesses = sub.add_parser("harnesses", help="Tool bindings under configs/harnesses/")
    harnesses_sub = p_harnesses.add_subparsers(dest="harnesses_command")
    p_harnesses_list = harnesses_sub.add_parser("list", help="List available harnesses")
    p_harnesses_list.set_defaults(func=cmd_harnesses_list)

    p_sched = sub.add_parser("schedule", help="Instance schedule engine")
    sched_sub = p_sched.add_subparsers(dest="schedule_command")

    def _sched_parser(verb: str, help_text: str):
        p = sched_sub.add_parser(verb, help=help_text)
        p.add_argument(
            "name",
            nargs="?",
            help="Instance name (default: derive from $HARNESS_INSTANCE)",
        )
        return p

    _sched_parser("check", "Validate schedule/rules.d without activating").set_defaults(
        func=cmd_schedule_check
    )
    _sched_parser(
        "reload", "Validate then atomically activate rules into state/active.json"
    ).set_defaults(func=cmd_schedule_reload)
    _sched_parser("status", "Show active snapshot, drift, and per-rule state").set_defaults(
        func=cmd_schedule_status
    )

    p_apply = _sched_parser(
        "apply",
        "Overwrite rules.d/base/ from the instance profile's schedule/, then reload",
    )
    p_apply.add_argument(
        "--pack",
        help="Profile id whose schedule/ to apply (default: instance config.yaml profile)",
    )
    p_apply.set_defaults(func=cmd_schedule_apply)

    p_tick = _sched_parser("tick", "Evaluate active schedule once (cron/systemd entrypoint)")
    p_tick.add_argument("--dry-run", action="store_true", help="Report due rules, run nothing")
    p_tick.add_argument("--rule", help="Force-fire one rule id regardless of trigger")
    p_tick.set_defaults(func=cmd_schedule_tick)

    p_packs = sched_sub.add_parser(
        "packs",
        help="List profiles that ship configs/profiles/<id>/schedule/",
    )
    p_packs.set_defaults(func=cmd_schedule_packs)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Harness runtime CLI")
    sub = parser.add_subparsers(dest="command")
    register_commands(sub)
    args = parser.parse_args(argv)
    if not args.command or not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
