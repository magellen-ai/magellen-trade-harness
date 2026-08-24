#!/usr/bin/env python3
"""Short quote / overview JSON via yfinance (no API key)."""

from __future__ import annotations

import json
import sys


def to_yahoo(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.startswith("X:"):
        # ClawStreet crypto: X:BTCUSD → BTC-USD
        bare = s[2:]
        if bare.endswith("USD") and len(bare) > 3:
            return f"{bare[:-3]}-USD"
        return bare
    return s


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] in ("-h", "--help"):
        print("Usage: quote.py SYMBOL", file=sys.stderr)
        print("  SYMBOL examples: AAPL  MSFT  X:BTCUSD", file=sys.stderr)
        return 2
    symbol = argv[1]
    yahoo = to_yahoo(symbol)
    try:
        import yfinance as yf
    except ImportError:
        print(
            "yfinance missing. Run: uv run --with yfinance python …/quote.py SYMBOL",
            file=sys.stderr,
        )
        return 1

    t = yf.Ticker(yahoo)
    info: dict = {}
    try:
        fi = t.fast_info
        if hasattr(fi, "items"):
            info = dict(fi)
        elif isinstance(fi, dict):
            info = fi
        else:
            info = {k: getattr(fi, k) for k in dir(fi) if not k.startswith("_")}
    except Exception as e:  # noqa: BLE001 — surface Yahoo quirks to agent
        print(json.dumps({"ok": False, "symbol": symbol, "yahoo": yahoo, "error": str(e)}))
        return 1

    last = info.get("last_price") or info.get("lastPrice") or info.get("regular_market_price")
    prev = info.get("previous_close") or info.get("previousClose")
    change_pct = None
    if last is not None and prev not in (None, 0):
        try:
            change_pct = round((float(last) - float(prev)) / float(prev) * 100.0, 4)
        except (TypeError, ValueError, ZeroDivisionError):
            change_pct = None

    # Optional slower fundamentals — best-effort, ignore failures
    fundamentals: dict = {}
    try:
        raw = t.info or {}
        for key in (
            "shortName",
            "sector",
            "industry",
            "marketCap",
            "trailingPE",
            "forwardPE",
            "priceToBook",
            "dividendYield",
            "currency",
        ):
            if key in raw and raw[key] is not None:
                fundamentals[key] = raw[key]
    except Exception:  # noqa: BLE001
        pass

    out = {
        "ok": True,
        "symbol": symbol,
        "yahoo": yahoo,
        "last": last,
        "previous_close": prev,
        "change_pct": change_pct,
        "currency": info.get("currency") or fundamentals.get("currency"),
        "fundamentals": fundamentals,
    }
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
