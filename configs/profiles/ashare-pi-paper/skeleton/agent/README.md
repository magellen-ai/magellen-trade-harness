# Agent credentials (this instance)

This profile trades **local A-share paper** (`paper-ashare`), not ClawStreet.
Isolation unit for parallel experiments = **`--account <name>`** (one SQLite ledger each).

## Secrets / env

Pi launch injects from repo-root `.env` via `pi-env` (minimal process env):

| Var | Purpose |
|-----|---------|
| `AIPROXY_API_KEY` | Pi model proxy |
| `HITHINK_FINANCE_API_KEY` | Tonghuashun / hithink-finance |
| `TAVILY_API_KEY` | Optional web search |

Market skill is **not** vendored under repo `skills/`. Profile declares:

```yaml
skills_npx:
  - package: HiThink-Tech/Financial-API
    skill: hithink-finance
```

`harness instance sync-settings|sync-skills` (cwd = this instance) runs
`npx skills update -p -y` then
`npx skills add HiThink-Tech/Financial-API --skill hithink-finance --yes`
(**no `-g`**). Files land in instance `.agents/skills/` + `skills-lock.json`.

Optional override file: `agent/secrets.env` (mode 600). Prefer keys in repo `.env`.

```bash
# from repo root
uv run harness instance sync-settings ashare-pi-test
uv run fuyao ping
uv run paper-ashare --account default accounts init --cash 1000000
```

Never print keys. Never commit them.

## History / truth

- Paper ledger: `./bin/paper-ashare fills` / `orders` / `portfolio`
- Ledgers: `paper_ashare/<account>.sqlite` under this instance
- Optional local audit: `audit/events.jsonl` (not a substitute for the ledger)

## Operator notes (humans — not for trading context)

Pi is **instance-local** (`.pi/agent` via `PI_CODING_AGENT_DIR`).
**Do not run bare `pi`** — use `./bin/pi` or `harness instance launch`.

```bash
uv run harness instance sync-settings <name>
uv run harness instance sync-bin <name>
uv run harness instance launch <name> --print
uv run harness instance launch <name>
# or inside instance after sync:
./bin/pi
./bin/paper-ashare status
./bin/fuyao quote 600519.SH
```

Do **not** put launch / env maps into `AGENTS.md`.

## Schedule (operator side)

```bash
uv run harness schedule apply <name> --pack ashare-pi-demo
uv run harness schedule reload <name>
uv run harness schedule tick <name> --rule research-tick
```

Agent verbs: `./bin/schedule check|reload|status`.
