# magellen-trade-harness

Harness runtime + competition adapters. Two CLIs:

| Command | Role |
|---------|------|
| `uv run clawstreet …` | ClawStreet trading (primary for agents) |
| `uv run harness …` | Instance / skills runtime |

## Setup

```bash
uv sync
cp .env.example .env   # fill ANTHROPIC_* for Claude Code proxy (optional until launch)
uv run harness profiles list
uv run harness instance init demo --profile clawstreet-claude-default
uv run clawstreet register --instance demo   # or paste key into instances/demo/agent/secrets.env
uv run clawstreet status                     # set HARNESS_INSTANCE or use ./bin/clawstreet inside instance
```

Secrets live in **`instances/<name>/agent/secrets.env`** (gitignored). Legacy fallback: `~/.config/magellen-trade-harness/secrets.env`.

## clawstreet (CLI first, HTTP when needed)

```bash
uv run clawstreet status|portfolio|order|fills|orders|audit|register|http-docs
```

- CLI handles secret load, `Idempotency-Key`, default dry-run.
- **History source of truth:** `fills` / `orders` (platform).
- **Raw HTTP:** `uv run clawstreet http-docs` → `docs/clawstreet.md`.

## harness

Scaffolding is config-driven (not hardcoded in Python):

- `configs/harnesses/<id>/` — thin tool binding (`launch.argv`, `skill_dirs`, default wake action)
- `configs/profiles/<id>/` — experiment pack (`CLAUDE.md` / models / skills); many profiles may share one harness

```bash
uv run harness skills list
uv run harness profiles list
uv run harness harnesses list
uv run harness instance init demo --profile clawstreet-claude-default
uv run harness instance sync-settings demo   # expand env_from $VAR → settings.path
uv run harness instance launch demo --print  # runs config launch.argv
```

Instance `config.yaml` is self-contained after init (`profile`/`harness` ids recorded). `cc-env` supports `$VAR` / `${VAR}` from repo-root `.env`.

Isolation: **one ClawStreet agent per instance** (separate paper account). Instance dirs are gitignored.

## schedule (instance automation)

Per-instance rule engine: rule = trigger (interval/cron) × optional script condition × action. Builtin action is only `script`; other kinds (e.g. `wake-main`) resolve via `config.yaml → schedule.actions` (argv/shell templates — swap to bind another harness). Sources in `schedule/rules.d/` (`base/` = pack, `local/` = agent edits, same id shadows); edits take effect only after `reload` → `schedule/state/active.json`.

```bash
uv run harness schedule check|reload|status <name>     # agent-safe (also ./bin/schedule inside instance)
uv run harness schedule apply <name> --pack default    # overwrite base/ from a pack, then reload
uv run harness schedule tick <name> [--dry-run]        # runner; put this in cron/systemd
uv run harness schedule packs
```

Design notes in `AGENTS.md` ("Schedule"). Rule schema is documented at the top of `src/runtime/schedule.py`.
