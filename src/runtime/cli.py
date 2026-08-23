"""Runtime CLI: instance init/launch/sync-skills/sync-settings + skills list."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from . import instance as instance_mod


def cmd_instance_init(args: argparse.Namespace) -> None:
    skills = args.skills.split(",") if args.skills else None
    if skills is not None:
        skills = [s.strip() for s in skills if s.strip()]
    try:
        path = instance_mod.init_instance(args.name, skills=skills, force=args.force)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"INSTANCE_OK {path}")
    print(f"skills={instance_mod.load_yaml(path / 'config.yaml').get('skills')}")
    print("Bind agent: uv run clawstreet register --instance", args.name)
    print("Or paste key into", path / "agent" / "secrets.env")
    print("Claude settings: uv run harness instance sync-settings", args.name)
    print("Then: uv run harness instance launch", args.name, "--print")


def cmd_instance_launch(args: argparse.Namespace) -> None:
    try:
        code = instance_mod.launch_instance(args.name, dry_print=args.print_only)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


def cmd_instance_sync_skills(args: argparse.Namespace) -> None:
    try:
        selected = instance_mod.sync_instance_skills(args.name)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"SYNC_OK skills={selected}")


def cmd_instance_sync_settings(args: argparse.Namespace) -> None:
    try:
        path = instance_mod.sync_claude_settings(args.name)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    cfg = instance_mod.load_yaml(instance_mod.instances_root() / args.name / "config.yaml")
    env, missing = instance_mod.build_claude_env(cfg)
    present = sorted(env.keys())
    print(f"SETTINGS_OK {path}")
    print(f"dotenv={instance_mod.repo_root() / '.env'}")
    print(f"env_keys={present}")
    if missing:
        print(f"unresolved=$refs missing in .env/process: {missing}")


def cmd_skills_list(_args: argparse.Namespace) -> None:
    print("\n".join(instance_mod.list_available_skills()) or "(no skills/ entries)")


def register_commands(sub: argparse._SubParsersAction) -> None:
    p_skills = sub.add_parser("skills", help="Skill library helpers")
    skills_sub = p_skills.add_subparsers(dest="skills_command")
    p_skills_list = skills_sub.add_parser("list", help="List skills/ library")
    p_skills_list.set_defaults(func=cmd_skills_list)

    p_inst = sub.add_parser("instance", help="Harness instance management")
    inst_sub = p_inst.add_subparsers(dest="instance_command")

    p_init = inst_sub.add_parser("init", help="Create gitignored instance workdir")
    p_init.add_argument("name")
    p_init.add_argument(
        "--skills",
        help="Comma-separated skill names from skills/; default=all available",
    )
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_instance_init)

    p_launch = inst_sub.add_parser("launch", help="Open Claude Code in instance dir")
    p_launch.add_argument("name")
    p_launch.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print command only",
    )
    p_launch.set_defaults(func=cmd_instance_launch)

    p_sync = inst_sub.add_parser("sync-skills", help="Re-link skills from config.yaml")
    p_sync.add_argument("name")
    p_sync.set_defaults(func=cmd_instance_sync_skills)

    p_sync_settings = inst_sub.add_parser(
        "sync-settings",
        help="Rewrite .claude/settings.json from cc-env + host ANTHROPIC_* env",
    )
    p_sync_settings.add_argument("name")
    p_sync_settings.set_defaults(func=cmd_instance_sync_settings)


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
