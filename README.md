# magellen-trade-harness

Harness runtime + competition / paper adapters. CLIs:

| Command | Role |
|---------|------|
| `uv run clawstreet …` | ClawStreet US/crypto paper trading |
| `uv run paper-ashare …` | Local A-share paper accounts (multi `--account`) |
| `uv run okx …` | OKX v5 (demo by default; service layer for quant) |
| `uv run fuyao …` | Tonghuashun HiThink market data (read-only) |
| `uv run harness …` | Instance / skills runtime |

## Setup

```bash
uv sync
cp .env.example .env   # fill ANTHROPIC_* for Claude Code proxy (optional until launch)
uv run harness profiles list
uv run harness config check            # 校验 harness/profile/agent/provider 引用
uv run harness instance init demo --agent clawstreet-claude-default
uv run clawstreet register --instance demo   # or paste key into instances/demo/agent/secrets.env
uv run clawstreet status                     # set HARNESS_INSTANCE or use ./bin/clawstreet inside instance

# A-share local paper on Pi (fuyao + paper-ashare + Tavily)
uv run harness instance init ashare-pi-test --agent ashare-pi-paper
uv run harness schedule apply ashare-pi-test   # seeds/refreshes from profile schedule/
# keys: HITHINK_FINANCE_API_KEY / TAVILY_API_KEY / AIPROXY_API_KEY in repo .env

# A-share fundamental research on Grok Build (fuyao + yichen-unified-search; no trading)
uv run harness instance init ashare-fundamental --agent ashare-grok-fundamental
# Grok membership: host ~/.grok (grok login). Workspace does not pin a model.
# keys: HITHINK_FINANCE_API_KEY in repo .env

# OKX demo dual-MA on Grok Build + grok-4.5
uv run harness instance init okx-grok-demo --agent okx-grok-ma
uv run harness schedule apply okx-grok-demo
# enable local rules, reload, cron tick; keys: OKX_* + OKX_HTTP_PROXY in .env
```

Secrets live in **`instances/<name>/agent/secrets.env`** (gitignored). Legacy fallback: `~/.config/magellen-trade-harness/secrets.env`.

## clawstreet (CLI first, HTTP when needed)

```bash
uv run clawstreet status|portfolio|order|fills|orders|audit|register|http-docs
```

- CLI handles secret load, `Idempotency-Key`, default dry-run.
- **History source of truth:** `fills` / `orders` (platform).
- **Raw HTTP:** `uv run clawstreet http-docs` → `docs/clawstreet.md`.

## paper-ashare (local A-share paper)

```bash
uv run paper-ashare --account demo accounts init --cash 1000000
uv run paper-ashare --account demo status|portfolio|order|fills|orders
uv run paper-ashare quote 600519.SH
```

- Default dry-run; `--live` writes SQLite under `instances/<name>/paper_ashare/` (or `~/.config/.../paper_ashare/`).
- Docs: `uv run paper-ashare http-docs` → `docs/paper_ashare.md`.

## fuyao (HiThink / Tonghuashun data)

```bash
# put HITHINK_FINANCE_API_KEY in instances/<name>/agent/secrets.env
uv run fuyao ping|quote|search|bars|calendar|http-docs
```

Key: https://fuyao.aicubes.cn/admin/ · Docs: `docs/fuyao.md`.

## harness

Scaffolding is config-driven (not hardcoded in Python):

- `configs/harnesses/<id>/` — thin tool binding + **materialize templates** (`process_env`, `launch.argv`)
- `configs/profiles/<id>/` — experiment pack (`CLAUDE.md` / `AGENTS.md` / skills / **`schedule/`**); many profiles may share one harness

```bash
uv run harness skills list
uv run harness profiles list
uv run harness harnesses list
uv run harness tools list              # 可供 profile 绑定的 CLI 能力
uv run harness instance init demo --agent clawstreet-claude-default
uv run harness instance init demo-pi --agent clawstreet-pi-default
uv run harness instance sync-settings demo   # render materialize templates
uv run harness instance launch --show-cmd demo
uv run harness instance launch demo          # interactive / runs launch.argv
```

Instance `config.yaml` is self-contained after init. `env:` maps support `$VAR` / `${VAR}` from repo-root `.env`. Pi instances use `process_env_policy: minimal` + `PI_CODING_AGENT_DIR` (no `~/.pi`); start with `./bin/pi` or `harness instance launch`, not bare `pi`. Grok Build instances reuse host `~/.grok` for membership auth and the default model; start with `./bin/grok` or `harness instance launch`.

Isolation: **one ClawStreet agent per instance** (separate paper account). Instance dirs are gitignored.

## schedule (instance automation)

Per-instance rule engine: rule = trigger (interval/cron) × optional script condition × action. Builtin action is only `script`; other kinds (e.g. `wake-main`) resolve via `config.yaml → schedule.actions` (argv/shell templates — swap to bind another harness). Sources in `schedule/rules.d/` (`base/` = profile schedule, `local/` = agent edits, same id shadows); edits take effect only after `reload` → `schedule/state/active.json`.

```bash
uv run harness schedule check|reload|status <name>     # agent-safe (also ./bin/schedule inside instance)
uv run harness schedule apply <name>                   # overwrite base/ from instance profile's schedule/
uv run harness schedule apply <name> --pack <profile>  # optional: another profile's schedule/
uv run harness schedule tick <name> [--dry-run] [--rule ID]  # runner; put tick in cron/systemd
uv run harness schedule packs   # profiles that ship schedule/
uv run harness schedule create <name> <rule-id> --every 1h --prompt '复盘当前研究'
uv run harness schedule list <name>
uv run harness schedule cancel <name> <rule-id>
```

Crypto always-on lives under `configs/profiles/clawstreet-pi-default/schedule/` (scan / research / risk). Enable via local shadows. Prefer manual `tick --rule …` for most tests.

Design notes in `AGENTS.md` ("Schedule"). Rule schema is documented at the top of `src/runtime/schedule.py`.
