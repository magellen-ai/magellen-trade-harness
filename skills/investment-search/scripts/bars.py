#!/usr/bin/env python3
"""Historical OHLCV bars via yfinance → JSON (reuses quote.py symbol mapping)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def to_yahoo(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.startswith("X:"):
        bare = s[2:]
        if bare.endswith("USD") and len(bare) > 3:
            return f"{bare[:-3]}-USD"
        return bare
    return s


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Fetch OHLCV bars as JSON")
    parser.add_argument("symbol", help="e.g. X:BTCUSD or AAPL")
    parser.add_argument("--interval", default="1h", help="yfinance interval (default 1h)")
    parser.add_argument("--lookback", default="60d", help="yfinance period (default 60d)")
    parser.add_argument("--limit", type=int, default=0, help="Keep last N bars (0=all)")
    args = parser.parse_args(argv[1:])

    symbol = args.symbol
    yahoo = to_yahoo(symbol)
    try:
        import yfinance as yf
    except ImportError:
        print(
            "yfinance missing. Run: uv run --with yfinance python …/bars.py SYMBOL",
            file=sys.stderr,
        )
        return 1

    try:
        df = yf.Ticker(yahoo).history(period=args.lookback, interval=args.interval)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "symbol": symbol, "yahoo": yahoo, "error": str(e)}))
        return 1

    if df is None or df.empty:
        print(
            json.dumps(
                {
                    "ok": False,
                    "symbol": symbol,
                    "yahoo": yahoo,
                    "error": "empty history",
                }
            )
        )
        return 1

    if args.limit and args.limit > 0:
        df = df.tail(args.limit)

    bars = []
    for idx, row in df.iterrows():
        bars.append(
            {
                "ts": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]) if "Volume" in row else None,
            }
        )

    closes = [b["close"] for b in bars]
    recent_high = max(closes) if closes else None
    recent_low = min(closes) if closes else None
    last = closes[-1] if closes else None
    position_pct = None
    if last is not None and recent_high is not None and recent_low is not None:
        span = recent_high - recent_low
        if span > 0:
            position_pct = round((last - recent_low) / span * 100.0, 2)

    out = {
        "ok": True,
        "symbol": symbol,
        "yahoo": yahoo,
        "interval": args.interval,
        "lookback": args.lookback,
        "count": len(bars),
        "last_close": last,
        "range_high": recent_high,
        "range_low": recent_low,
        "position_pct_in_range": position_pct,
        "bars": bars,
    }
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
