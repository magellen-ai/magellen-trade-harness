# Agent credentials (this instance)

Local A-share paper via `paper-ashare`. Parallel experiments use distinct
`--account` names (one SQLite ledger each).

## Env

Launch injects from repo-root `.env` via config `env:`:

| Var | Purpose |
|-----|---------|
| `AIPROXY_API_KEY` | Pi model proxy |
| `HITHINK_FINANCE_API_KEY` | Tonghuashun / hithink-finance |
| `TAVILY_API_KEY` | Optional web search |

Optional override: `agent/secrets.env` (mode 600). Prefer keys in repo `.env`.

```bash
# from repo root
uv run harness instance sync-settings ashare-pi-test
uv run fuyao ping
uv run paper-ashare --account default accounts init --cash 1000000
```

Market skill is installed into this instance (not globally):

```yaml
skills_npx:
  - package: HiThink-Tech/Financial-API
    skill: hithink-finance
```

`harness instance sync-settings|sync-skills` (cwd = this instance) runs
`npx skills update -p -y` then
`npx skills add HiThink-Tech/Financial-API --skill hithink-finance --yes`.

## Launch

```bash
uv run harness instance sync-settings <name>
uv run harness instance sync-bin <name>
uv run harness instance launch <name>
# or inside instance after sync:
./bin/pi
./bin/paper-ashare status
./bin/fuyao quote 600519.SH
```

## Schedule

```bash
uv run harness schedule apply <name>
uv run harness schedule reload <name>
uv run harness schedule tick <name> --rule research-tick
```

Paper ledger: `./bin/paper-ashare fills` / `orders` / `portfolio`.  
Ledgers: `paper_ashare/<account>.sqlite` under this instance.
