---
name: paper-ashare-trade
description: Local A-share paper broker via `uv run paper-ashare` (accounts, status, portfolio, order, fills, orders, quote). Multi named accounts in SQLite. Default dry-run; --live writes ledger. Use for A-share simulated trading experiments without a securities account.
---

# paper-ashare trade

**Default path = CLI.** Local ledger is the source of truth (`fills` / `orders`).  
Docs: `uv run paper-ashare http-docs` → `docs/paper_ashare.md`.

## Accounts (multi-agent)

One named account per experiment / agent:

```bash
uv run paper-ashare --account <name> accounts init --cash 1000000
uv run paper-ashare accounts list
```

Ledgers live under `instances/<instance>/paper_ashare/<name>.sqlite` when `HARNESS_INSTANCE` / cwd is an instance.

## CLI

```bash
uv run paper-ashare --account <name> status
uv run paper-ashare --account <name> portfolio
uv run paper-ashare --account <name> order SYMBOL buy|sell QTY "reasoning..."
uv run paper-ashare --account <name> order SYMBOL buy QTY "reasoning..." --live
uv run paper-ashare --account <name> fills --limit 10
uv run paper-ashare --account <name> orders --limit 10
uv run paper-ashare quote 600519.SH
```

## Rules

- Default **dry-run**; `--live` commits to SQLite.
- Non-empty `reasoning` required (≥10 chars by default).
- Qty must be a multiple of **100**. Only **buy/sell** market orders in MVP.
- T+1: cannot sell same-day buys.
- Quotes: Fuyao if `HITHINK_FINANCE_API_KEY` set, else Eastmoney public snapshot.
- After `--live`, confirm with `fills` / `portfolio`.
- This is **simplified paper** — not broker-official simulation.
