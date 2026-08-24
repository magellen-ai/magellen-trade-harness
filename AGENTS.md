# magellen-trade-harness

## How to use this file

**`AGENTS.md` is the agent-facing README** for this repo: durable facts and conventions every coding agent should follow. Prefer writing shared “remember this” rules here (not only in chat).

- **Shared / for anyone cloning the repo** → this file.
- **Machine-only paths, personal habits, Obsidian links** → `AGENTS.local.md` (gitignored). Read it when present.
- **Human-oriented longer docs** → `README.md` (setup narrative is fine to duplicate briefly here if agents need it).

## What this repo is doing

- Harness **runtime** experiments (instances, skills, Claude Code / Pi / other agents).
- Competition adapters under `src/competitions/` (ClawStreet first).
- Local brokers under `src/brokers/` (A-share paper first). Market data under `src/marketdata/` (Fuyao/HiThink).

## What works now

| CLI | Capability |
|-----|------------|
| `uv run clawstreet` | status / portfolio / order / fills / orders / audit / register / http-docs |
| `uv run paper-ashare` | accounts init\|list; status / portfolio / order / fills / orders / quote (local A-share paper; multi `--account`) |
| `uv run fuyao` | ping / quote / search / bars / calendar / http-docs (Tonghuashun HiThink data; read-only) |
| `uv run harness` | skills/profiles/harnesses list; instance init(--profile)/launch/sync-*; schedule check/reload/status/apply/tick/packs |

A-share Pi paper profile: `ashare-pi-paper` (local skills: paper-ashare-trade + investment-search; **npx project** skill: `HiThink-Tech/Financial-API` → `hithink-finance` into the **instance** `.agents/skills/`; schedule pack `ashare-pi-demo` with `context_files` @path inject). Init: `uv run harness instance init <name> --profile ashare-pi-paper`. Sync / launch runs `npx skills update -p -y` + `npx skills add … --yes` with cwd=instance (**never `-g`**).

- Prefer **`uv run`** (not raw `python -m` / `PYTHONPATH`).
- Trade secrets: `instances/<name>/agent/secrets.env` (preferred). Legacy: `~/.config/magellen-trade-harness/secrets.env`.
- Fuyao key env: `HITHINK_FINANCE_API_KEY` (alias `FUYAO_API_KEY`) in the same secrets file.
- Runtime auth/files: repo `.env` + instance `env_from` map → `harness instance sync-settings` (materialize) / launch injects **process_env**.
- Isolation: one ClawStreet agent per instance (may reuse the same agent key across instances over time, but not concurrently). For A-share paper, use distinct `--account` names (one sqlite ledger each under `instances/<name>/paper_ashare/`).
- Instance ops log: local `audit/`. ClawStreet account truth: platform `fills` / `orders`. paper_ashare truth: local ledger `fills` / `orders`.
- Prefer CLI for trading; raw HTTP via `clawstreet http-docs` / `fuyao http-docs` / `paper-ashare http-docs` when needed.

## Profiles & harnesses (instance scaffolding)

Concrete agent content is **not** in Python. Init reads config directories:

| Layer | Path | Role |
|-------|------|------|
| **Harness** (thin) | `configs/harnesses/<id>/` | Tool binding: `harness.yaml` + **template files**. Declares `env_from`, `process_env`, `materialize` (`src`→`dest`), `launch.argv`, default `schedule_actions`. Framework does not know Claude/Pi JSON shapes. |
| **Profile** (many) | `configs/profiles/<id>/` | Experiment: `profile.yaml` → `harness: …`; `config.yaml` (skills/env map/expose); `skeleton/` (`CLAUDE.md` or `AGENTS.md`, …) |

Same harness can back many profiles.  
`uv run harness instance init <name> --profile <id>` merges harness⊕profile into the instance (self-contained `config.yaml` + skeleton copy; existing files skipped).

**Runtime sync:** `harness instance sync-settings` / `sync-runtime` only renders `materialize` templates. Launch/tick merge `env_from` + `process_env` into the subprocess environment (`process_env_policy: inherit|minimal`). Pi harness uses `minimal` + `PI_CODING_AGENT_DIR` + CLI `--no-*` flags so it does **not** use `~/.pi` / `~/.agents`; start via `./bin/pi` or `harness instance launch`, never bare `pi`.

## Schedule (instance automation)

Rule engine per instance: a rule = trigger (interval/cron) × optional condition (script gate) × action (`script` builtin, or named actions from config). Design invariants:

- **Source vs active**: rules live in `instances/<name>/schedule/rules.d/`; editing them does nothing until `harness schedule reload` validates and atomically compiles into `schedule/state/active.json` — the only file the tick runner reads. Broken edits never reach the runner.
- **base vs local**: `base/` is owned by strategy packs (`configs/schedules/<pack>/`, in git; `harness schedule apply --pack X` overwrites the whole dir). `local/` is agent/operator-owned and never touched by apply. Same rule `id` in local shadows base entirely (no field merge).
- **State is sacred**: `schedule/state/` (active, cursor, journal) survives pack swaps — experiments keep their history.
- **Agent surface**: instance `bin/schedule` wrapper forwards only `expose.schedule` verbs from `config.yaml` (default check/reload/status; apply/tick stay operator-side). Regenerate wrappers with `harness instance sync-bin`.
- **Actions are bindings, not builtins**: only `script` is built into the engine. Other kinds (e.g. `wake-main`) resolve via `config.yaml → schedule.actions` (argv/shell templates + optional before hooks). Swap the template to adapt another harness; rules stay the same.
- **Optional `action.context_files`**: instance-relative paths become harness `@path` injects at fire time (`context_files_mode: argv` for Pi CLI args, `prompt_prefix` for Claude-style in-prompt `@path`). Empty/omit = thin context (agent must read files).
- **Runner**: `harness schedule tick <name>` from cron/systemd; flock prevents overlap; named-action logs to `logs/schedule/`, events to `schedule/state/journal.jsonl`. Cron exprs are numeric 5-field, local machine time.

## Context control (critical)

This repo exists to **compare harness / context / tools** and how they change agent behavior. Do not casually dump ops noise into agent context.

| File | Audience | Contents |
|------|----------|----------|
| Profile `skeleton/CLAUDE.md` (Claude) or `AGENTS.md` (other) | Seeded into instance at init | Trading role/tools/rules — edit per profile, not in framework code |
| `instances/<name>/CLAUDE.md` or `AGENTS.md` | Live trading agent context | Copied from profile; instance may hand-edit afterward |
| `instances/<name>/agent/README.md` | Humans / harness experimenters | Bind secrets, register, launch |
| Repo `AGENTS.md` (this file) | Coding agents working on the harness | Layout, CLIs, conventions |
| `AGENTS.local.md` | This machine only | Paths, vault links, personal habits |

Do not put register/launch/env maps into the trading context file. Framework code has no `if claude` / `if pi` branches for scaffolding.

## Package layout

- `src/competitions/clawstreet/` — competition trade client + CLI
- `src/brokers/paper_ashare/` — local A-share paper ledger + CLI
- `src/marketdata/fuyao/` — Tonghuashun HiThink (fuyao) read-only market data + CLI
- `src/runtime/` — instance scaffolding + `harness` CLI
- `skills/` — shared skill library (profile selects; init links into harness `skill_dirs`)
- `configs/harnesses/` — thin tool bindings + materialize templates; `configs/profiles/` — experiment packs
- `configs/schedules/` — schedule strategy packs
- `instances/` — gitignored workdirs (never commit secrets or settings with keys)

## Secrets & safety

- Never print, commit, or log API keys.
- ClawStreet keys only go to `www.clawstreet.io`.
- Default order path is dry-run; `--live` is explicit paper trading only.
- Every order needs non-empty public `reasoning`.
- Do not register/claim ClawStreet agents unless the owner explicitly asks.

## After project work

If `AGENTS.local.md` points at project notes, update that `CONTEXT.md` when status or decisions change.
