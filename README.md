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
uv run harness instance init demo --skills clawstreet-trade
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

```bash
uv run harness skills list
uv run harness instance init demo --skills clawstreet-trade
uv run harness instance sync-settings demo   # expand config cc-env $VAR via repo .env → .claude/settings.json
uv run harness instance launch demo --print
```

Instance `config.yaml` → `cc-env` supports `$VAR` / `${VAR}` (resolved from repo-root `.env` via dotenv, then process env). Example: `ANTHROPIC_BASE_URL: $ANTHROPIC_BASE_URL`. Copy `.env.example` → `.env` and fill keys (gitignored).

Isolation: **one ClawStreet agent per instance** (separate paper account). Instance dirs are gitignored.
