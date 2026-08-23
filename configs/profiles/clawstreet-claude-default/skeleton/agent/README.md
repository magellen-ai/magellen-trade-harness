# Agent credentials (this instance)

Isolation unit = **one ClawStreet agent** (paper account), bound to this harness instance.

## Option A — register a new agent (human or AI)

```bash
uv run clawstreet register --instance <this-instance-name>
```

Then open `claim_url` from `agent/public.json`, claim in browser, verify:

```bash
./bin/clawstreet status
```

## Option B — paste an existing key

Create `agent/secrets.env` (mode 600):

```env
CLAWSTREET_API_KEY=...
CLAWSTREET_AGENT_ID=...
```

Never print the key. Never commit it (`instances/` is gitignored).

## History

Platform source of truth: `uv run clawstreet fills` / `orders`.  
Optional local audit: `audit/events.jsonl` (not a substitute for platform APIs).

## Operator notes (humans / harness experimenters — not for trading context)

```bash
# from repo root
uv run harness instance sync-settings <name>
uv run harness instance launch <name> --print
```

Do **not** put register/launch/cc-env into the trading context file (e.g. `CLAUDE.md`).

## Schedule (operator side)

Rules: `schedule/rules.d/base/` (strategy pack) + `local/` (agent edits).
Runner reads only `schedule/state/active.json` (created by `reload`).

```bash
uv run harness schedule apply <name> --pack default
uv run harness schedule status <name>
uv run harness schedule tick <name> [--dry-run]
```

Agent-facing verbs (`./bin/schedule check|reload|status`) come from `config.yaml expose`
via `harness instance sync-bin <name>`.
