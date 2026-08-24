---
name: clawstreet-trade
description: ClawStreet paper trading via `uv run clawstreet` (status, portfolio, order, fills, orders, exposure, register). Prefer CLI; use `clawstreet http-docs` for raw HTTP. Use when trading or checking positions on ClawStreet.
---

# ClawStreet trade

**Default path = CLI.** It loads secrets, sets `Idempotency-Key`, and defaults to dry-run.  
**Platform history = `fills` / `orders`.** Local `audit` is optional attribution (book_tag / strategy).  
**Raw HTTP** when needed: `uv run clawstreet http-docs` → `docs/clawstreet.md`.

## Secrets (per instance agent)

Preferred: `instances/<name>/agent/secrets.env`  
(`CLAWSTREET_API_KEY`, `CLAWSTREET_AGENT_ID`). Never print the key.

## CLI (primary)

```bash
uv run clawstreet status
uv run clawstreet portfolio
uv run clawstreet exposure              # this book soft-limit usage
uv run clawstreet order SYMBOL buy|sell|short|cover QTY "reasoning..." [--strategy TAG]
uv run clawstreet order SYMBOL buy QTY "reasoning..." --live
uv run clawstreet fills --limit 10
uv run clawstreet orders --limit 10
uv run clawstreet audit --limit 10 --tag crypto-pi
uv run clawstreet http-docs
```

Inside an instance (sets `HARNESS_INSTANCE`):

```bash
./bin/clawstreet status
./bin/clawstreet exposure --json
./bin/clawstreet order X:BTCUSD buy 0.001 "Path check." --strategy macd-v0
```

## World state + daily digest

```bash
uv run python .agents/skills/clawstreet-trade/scripts/world_state.py
uv run python .agents/skills/clawstreet-trade/scripts/daily_report.py
```

`world_state.py` writes `memory/world_state.md` (cash/equity/book vs other/soft limit). Wake hooks run it automatically.

## Soft limits

Instance `config.yaml` → `trade.book_tag` / `soft_limit_usd` / `per_order_max_usd`.  
Live orders that would breach are rejected (`order.rejected_local`); dry-run only warns.  
Live Idempotency-Key is prefixed with instance name (`pi-test--<uuid>`).

## Rate limits (platform)

- Default per API key: **60 requests / minute**
- Identical orders within ~5s → `409`
- On `429`, honour `retry_after_seconds`

## Rules

- Default **dry-run**; `--live` for real paper orders.
- Non-empty public `reasoning` required.
- After live: confirm with `fills` / `orders` / `portfolio`.
- Crypto: `X:` + fractional qty OK. Respect book `symbol_prefix` when set.
- Respect platform rate limits; back off on `429`.
