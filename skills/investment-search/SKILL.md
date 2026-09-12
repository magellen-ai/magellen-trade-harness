---
name: investment-search
description: Use for focused market data or external evidence in trading and research tasks.
---

# Investment search

The scripts in `scripts/` are the entry points:

- `quote.py` and `bars.py` use yfinance for lightweight market data (`X:`
  symbols map to Yahoo crypto tickers).
- `search.py` performs an optional Tavily web search and exits non-zero when no
  key is configured.

Run them with `uv run --with yfinance python .agents/skills/investment-search/scripts/<script>.py`;
use the instance's linked path when available. Treat search snippets as leads,
verify important claims in the source, and keep memory notes to a few dated
facts with links. Never print API keys or dump raw HTML into memory.
