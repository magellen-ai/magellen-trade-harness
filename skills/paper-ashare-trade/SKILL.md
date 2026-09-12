---
name: paper-ashare-trade
description: Use for local A-share paper accounts and simulated orders; the CLI defaults to dry-run.
---

# Paper A-share trade

Use `./bin/paper-ashare` in an instance, or `uv run paper-ashare` from the
repository. Let `--help` provide command syntax; run
`./bin/paper-ashare http-docs` for ledger locations and simulator details (also
documented in the repository's `docs/paper_ashare.md`).

- Select an account with `--account`; `fills` and `orders` are the ledger truth.
- Keep dry-run unless the task explicitly authorizes `--live`.
- Orders need honest public reasoning, quantities in 100-share lots, and only
  `buy` / `sell` are supported. T+1 prevents selling same-day buys.
- Quotes use Fuyao when configured, then a public snapshot fallback.
- This is a simplified paper simulator, not a broker or live-trading gateway.
