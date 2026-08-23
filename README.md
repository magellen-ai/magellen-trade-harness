# magellen-trade-harness

Thin trade harness for paper-trading adapters (ClawStreet first).

This repo is the **execution / competition adapter layer only**:
auth → portfolio → order with public `reasoning` → local journal.
It is not a research engine and does not place live-money orders.

## Status

Week0: scaffold and ClawStreet paper-trade loop.

## Local setup

1. Clone this repo.
2. Create ignored local files (not in git):
   - `AGENTS.local.md` — machine-local paths and supplemental docs
   - secrets under `~/.config/magellen-trade-harness/` (never commit)
3. Prefer dry-run until an agent is claimed on ClawStreet.

## License

See repository license when added; default assumption for now is personal / experimental use.
