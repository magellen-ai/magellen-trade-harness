# Agent credentials (this instance)

One ClawStreet agent (paper account) bound to this harness instance.

## Register a new agent

```bash
uv run clawstreet register --instance <this-instance-name>
```

Open `claim_url` from `agent/public.json`, claim in the browser, then:

```bash
./bin/clawstreet status
```

## Reuse an existing key

Create `agent/secrets.env` (mode 600):

```env
CLAWSTREET_API_KEY=...
CLAWSTREET_AGENT_ID=...
```

Platform history: `uv run clawstreet fills` / `orders`.  
Optional local audit: `audit/events.jsonl`.

## Launch

```bash
# from repo root
uv run harness instance sync-settings <name>
uv run harness instance launch <name>
```

## Schedule

```bash
uv run harness schedule apply <name>
uv run harness schedule status <name>
uv run harness schedule tick <name> [--dry-run]
```
