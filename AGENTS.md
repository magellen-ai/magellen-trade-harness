# magellen-trade-harness

## What this repo is doing

- Harness runtime experiments (instances, skills, Claude Code / other agents).
- Competition adapters under `src/competitions/` (ClawStreet first).

## What works now

| CLI | Capability |
|-----|------------|
| `uv run clawstreet` | status / portfolio / order / fills / orders / audit / register / http-docs |
| `uv run harness` | skills list; instance init / launch / sync-skills / sync-settings |

- Trade secrets: `instances/<name>/agent/secrets.env` (preferred).
- Claude proxy/auth: repo `.env` + instance `cc-env` → `harness instance sync-settings`.
- Isolation: one ClawStreet agent per instance; instance ops in local `audit/`; platform history via `fills`/`orders`.
- Prefer CLI; raw HTTP via `clawstreet http-docs`.

## Package layout

- `src/competitions/clawstreet/` — trade client + CLI
- `src/runtime/` — instance scaffolding + `harness` CLI
- `skills/` — shared skill library
- `instances/` — gitignored workdirs

## Local overlays

If `AGENTS.local.md` exists, read it for machine paths and project-notes links.
