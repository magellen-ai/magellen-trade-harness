---
name: investment-search
description: Gather external market/news evidence for paper trading. Quote via yfinance; optional web search via Tavily. Use before deciding hold vs dry-run order on a research tick.
---

# Investment search (L1 evidence)

Lightweight evidence gatherer for this harness. Prefer **scripts below** over ad-hoc scraping.
Do **not** treat search snippets as audited financial facts — cite them as leads and verify.

## Quote / overview (no API key)

From the instance cwd (or repo root):

```bash
uv run --with yfinance python .agents/skills/investment-search/scripts/quote.py AAPL
uv run --with yfinance python .agents/skills/investment-search/scripts/quote.py X:BTCUSD
```

`X:` crypto tickers are mapped to Yahoo symbols (e.g. `X:BTCUSD` → `BTC-USD`).

Output is short JSON: last price, day change, crude fundamentals when Yahoo has them.

## Web / news search (optional key)

If `TAVILY_API_KEY` is set in the process env (repo `.env` → harness `env_from`, or export):

```bash
uv run python .agents/skills/investment-search/scripts/search.py "AAPL supplier concentration risk"
```

Without a key the script exits non-zero with a clear message — then either skip web search
or note “no Tavily key” in the journal and decide from quote + memory only.

## How to use on a research tick

1. Read watchlist / MEMORY for symbols and pending checks.
2. Run `quote.py` for each active symbol (cap to a few; do not spray).
3. Optionally `search.py` for one focused question per thesis.
4. Fold evidence into public `reasoning` (or an explicit hold note in `trade-journal.md`).

## Rules

- Never print API keys.
- Do not dump huge raw HTML into memory files — keep 3–8 bullet facts + sources.
- Quotes are Yahoo-unofficial via yfinance; not HFT truth.
- Search summaries are not SEC filings; escalate to EDGAR/edgartools later if needed.
