---
name: investment-search
description: Gather external market/news evidence for paper trading. Quote/bars via yfinance; MACD scan; optional web search via Tavily. Use before deciding hold vs dry-run order on a research/scan tick.
---

# Investment search (L1 evidence)

Lightweight evidence gatherer for this harness. Prefer **scripts below** over ad-hoc scraping.
Do **not** treat search snippets as audited financial facts — cite them as leads and verify.

## Quote / overview (no API key)

```bash
uv run --with yfinance python .agents/skills/investment-search/scripts/quote.py AAPL
uv run --with yfinance python .agents/skills/investment-search/scripts/quote.py X:BTCUSD
```

`X:` crypto tickers map to Yahoo (e.g. `X:BTCUSD` → `BTC-USD`).

## Historical bars

```bash
uv run --with yfinance python .agents/skills/investment-search/scripts/bars.py X:BTCUSD --interval 1h --lookback 60d
```

JSON includes OHLCV plus `position_pct_in_range` for strategy position vote.

## MACD scan (schedule condition)

```bash
uv run --with yfinance python .agents/skills/investment-search/scripts/macd_scan.py X:BTCUSD X:ETHUSD X:SOLUSD
```

Exit **0** + candidate JSON when a *new* golden/death cross appears; exit **1** if none (condition skip).
State dedupe: `memory/.macd_state.json` (machine file, not injected).

## Web / news search (optional key)

```bash
uv run python .agents/skills/investment-search/scripts/search.py "BTC 24h news sentiment"
```

Without `TAVILY_API_KEY` the script exits non-zero — note that and continue.

## Strategy v0 resonance

1. MACD candidate (from scan condition) = technical vote  
2. `search.py` 24h news/sentiment = message vote  
3. `bars.py` position in range = position vote  
4. Need **≥2 votes** same direction before suggesting an open; else hold.

## Rules

- Never print API keys.
- Do not dump huge raw HTML into memory files — keep 3–8 bullet facts + sources.
- Quotes/bars are Yahoo-unofficial via yfinance; not HFT truth.
