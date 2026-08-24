---
name: clawstreet-trade
description: ClawStreet paper trading via `uv run clawstreet` (status, portfolio, order, fills, orders, register). Prefer CLI; use `clawstreet http-docs` for raw HTTP. Use when trading or checking positions on ClawStreet.
---

# ClawStreet trade

**Default path = CLI.** It loads secrets, sets `Idempotency-Key`, and defaults to dry-run.  
**Platform history = `fills` / `orders`.** Local `audit` is optional and is not the source of truth.  
**Raw HTTP** when needed: `uv run clawstreet http-docs` → `docs/clawstreet.md`.

## Secrets (per instance agent)

Preferred: `instances/<name>/agent/secrets.env`  
(`CLAWSTREET_API_KEY`, `CLAWSTREET_AGENT_ID`). Never print the key.

Bind / create agent:

```bash
uv run clawstreet register --instance <name>
# or paste an existing key into agent/secrets.env (see agent/README.md)
```

One ClawStreet agent = one paper account. Do not share one agent across competing experiments.

## CLI (primary)

```bash
uv run clawstreet status
uv run clawstreet portfolio
uv run clawstreet order SYMBOL buy|sell|short|cover QTY "reasoning..."
uv run clawstreet order SYMBOL buy QTY "reasoning..." --live
uv run clawstreet fills --limit 10
uv run clawstreet orders --limit 10
uv run clawstreet audit --limit 10          # local optional log only
uv run clawstreet http-docs                # progressive HTTP disclosure
uv run clawstreet --help
```

Inside an instance (sets `HARNESS_INSTANCE`):

```bash
./bin/clawstreet status
./bin/clawstreet order X:BTCUSD buy 0.001 "Path check." --live
```

## Daily order budget

Hard demo rule: **≤20 order intents per local calendar day** (dry-run and live both count).
Check before placing another order:

```bash
uv run python .agents/skills/clawstreet-trade/scripts/order_budget.py --limit 20
```

Exit `0` = room left; exit `3` = blocked (`remaining: 0`). Counts `audit/events.jsonl`
events `order.dry_run` / `order.submitted` for today (local timezone).

## Rules

- Default **dry-run**; `--live` for real paper orders.
- Non-empty public `reasoning` required.
- After live: confirm with `fills` / `orders` / `portfolio`.
- Crypto: `X:` + fractional qty OK. US stocks: US hours.
- Stop ordering when the daily budget script reports `blocked: true`.
