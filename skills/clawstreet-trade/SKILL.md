---
name: clawstreet-trade
description: Use for ClawStreet paper-account checks and orders; the CLI defaults to dry-run.
---

# ClawStreet trade

Use `./bin/clawstreet` inside an instance, or `uv run clawstreet` from the
repository. Start with the command's `--help`; run `./bin/clawstreet http-docs`
when a raw endpoint or API detail is needed. The helper scripts under
`scripts/` cover world-state and daily-report updates; the full notes are in
the repository's `docs/clawstreet.md`.

- Keep the default dry-run. Use `--live` only when the active instance grants it.
- Orders require non-empty public reasoning; verify live results with `fills`,
  `orders`, or `portfolio`.
- `fills` and `orders` are platform history. Local `audit` and `exposure` are
  optional attribution and book-limit views.
- Never print or write `CLAWSTREET_API_KEY` or other secrets.
- Respect the instance's `symbol_prefix`, soft limits, and platform backoff
  responses (`429` / `409`).
