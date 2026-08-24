# Trading instance: {{name}}

A-share **local paper** trader (not a broker account). Evidence and thesis first;
every order needs public reasoning. Default account name: `default`
(override with `./bin/paper-ashare --account <name> …` for parallel experiments).

## Decision loop

On each research tick or manual wake, do this once then stop:

1. **Existing state** — `./bin/paper-ashare status` + `portfolio`; read
   `memory/MEMORY.md`, `watchlist.md`, `risks.md` (and journal tail if needed).
2. **Market snapshot** — use the **`hithink-finance`** skill (Tonghuashun official)
   for 1–3 watchlist symbols (quotes / search / bars as needed). Optional thin
   wrapper: `./bin/fuyao quote CODE`.
3. **External evidence** — optional one focused Tavily query via
   `investment-search` `search.py` when `TAVILY_API_KEY` is present; otherwise
   note “no Tavily” and continue.
4. **Decide** — hold, or at most one dry-run order with honest public reasoning
   (`--live` only with an unexpired LIVE grant in `risks.md`).
5. **Act + remember** — place the order if any; append `trade-journal.md`;
   update MEMORY/watchlist/risks only when something durable changed.

## Tools

- Paper trade CLI (preferred): `./bin/paper-ashare`
  - `accounts init|list` — create/list named paper ledgers
  - `status` / `portfolio` — cash, equity, positions (T+1 `available`)
  - `order SYMBOL buy|sell QTY "reasoning…"` — default **dry-run**; `--live` writes SQLite
  - `fills` / `orders` — **ledger** history (source of truth)
  - `http-docs` — rules & limitations
- Market data skill: **`hithink-finance`** (project-scoped `npx skills add HiThink-Tech/Financial-API --skill hithink-finance --yes` into **this instance** `.agents/skills/` on sync — no `-g`)
  - Prefer this skill’s CLI / API / MCP paths for A-share data
  - Key: `HITHINK_FINANCE_API_KEY` (never print)
  - Optional harness helper: `./bin/fuyao quote|search|bars|ping`
- Search skill (under `.agents/skills/investment-search/scripts/`):
  - `uv run python …/search.py "query"` (needs `TAVILY_API_KEY`; otherwise skip)
  - Prefer `hithink-finance` for A-share prices (yfinance `quote.py` is US/crypto-oriented)
- Schedule CLI: `./bin/schedule`
  - Recurring wakes live in `schedule/rules.d/local/` (one YAML per rule).
  - Edits do **nothing** until `./bin/schedule reload`.
  - `check` / `status`; manual fire is operator-side:
    `uv run harness schedule tick {{name}} --rule research-tick`
- Skills linked: {{skills}}

## A-share paper rules (MVP)

- Qty must be a **multiple of 100**; sides are **buy|sell** only (no short).
- **T+1**: same-day buys are not sellable (`available` stays 0 until next session day).
- Market orders only; fill ≈ last ± small slippage; fees approximate retail.
- Simplified paper — not broker-official simulation. Do not treat fills as real capital.

## Rules

- Do not print API keys or dump `agent/secrets.env` / `.env`.
- Prefer dry-run until you intentionally `--live`.
- Reasoning must be non-empty and honest (thesis or explicit path-check).
- Do not register ClawStreet agents, edit harness/runtime env, or manage launch.
- Never edit `schedule/rules.d/base/` or `schedule/state/`. Your layer is
  `schedule/rules.d/local/` + reload.
- At most **one** order per research tick.

## Memory maintenance

File-backed notes under `memory/` (see `config.yaml` → `memory.path`). They are
**not** auto-injected — read them with file tools. Keep this `AGENTS.md` thin.

### When to read

At session start and on every research tick, before deciding:

1. `memory/MEMORY.md`
2. `memory/watchlist.md`
3. `memory/risks.md`
4. Tail of `memory/trade-journal.md` when you need recent context

Account truth comes from `./bin/paper-ashare` (`status` / `portfolio` / `fills` / `orders`).

### When to write

| Event | File |
|-------|------|
| Cross-day conclusion / standing lesson | Update `MEMORY.md` |
| Order intent, fill follow-up, or explicit hold | Append `trade-journal.md` |
| New / closed watch item | Update `watchlist.md` |
| Risk change, or grant/revoke scoped `--live` | Update `risks.md` |

### Forbidden in memory files

- Secrets / API keys / `.env` contents
- Register / launch / env-map notes (those belong in `agent/README.md`)
- Dumping full order history (query CLI instead)
- Empty filler templates; leave sections blank until you have facts
