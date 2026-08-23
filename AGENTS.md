# magellen-trade-harness

## Purpose

Thin paper-trade harness. Map an already-reviewed decision into a competition / paper API, record a journal, and keep the research kernel elsewhere.

## Boundaries

- Do: ClawStreet adapter, decision schema, risk gates, journal, CLI.
- Do not: live-money trading, ML strategies, earnings parsers, multi-agent research loops, ranking-chasing indicator bots.
- Secrets never enter git, chat, or plaintext logs.

## Local supplements

If `AGENTS.local.md` exists in the repo root, **read it before coding**.
It holds machine-local paths and links to project notes that are intentionally not in this public repository.

Same rule for `CLAUDE.local.md` when present.

## Conventions

- Prefer a small Python package under `src/` when implementing the harness.
- Default order path is dry-run until explicitly disabled.
- Every order intent needs non-empty `reasoning`.
- After project-related work that changes status or decisions, update the local project `CONTEXT.md` pointed to by `AGENTS.local.md` when that file is available.
