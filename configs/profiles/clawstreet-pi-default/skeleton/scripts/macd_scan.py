#!/usr/bin/env python3
"""MACD(12,26,9) scan — emit new golden/death crosses only (stateful dedupe).

Profile/instance strategy helper (copied into instance ``scripts/``).
Not part of the generic ``investment-search`` skill.

Exit 0 + JSON candidates on stdout when at least one *new* cross appears.
Exit 1 when no new signals (schedule condition_skip).
Exit 2 on usage / hard errors.

State file (machine, not injected): memory/.macd_state.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def to_yahoo(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.startswith("X:"):
        bare = s[2:]
        if bare.endswith("USD") and len(bare) > 3:
            return f"{bare[:-3]}-USD"
        return bare
    return s


def _ema(values: list[float], span: int) -> list[Optional[float]]:
    if not values:
        return []
    alpha = 2.0 / (span + 1)
    out: list[Optional[float]] = [None] * len(values)
    # Seed with SMA of first `span` points
    if len(values) < span:
        return out
    seed = sum(values[:span]) / span
    out[span - 1] = seed
    prev = seed
    for i in range(span, len(values)):
        prev = alpha * values[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def macd_series(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    dif: list[Optional[float]] = []
    for a, b in zip(ema_fast, ema_slow):
        if a is None or b is None:
            dif.append(None)
        else:
            dif.append(a - b)
    # DEA on DIF values (skip leading Nones by only feeding valid DIF)
    valid_idx = [i for i, v in enumerate(dif) if v is not None]
    valid_dif = [float(dif[i]) for i in valid_idx]  # type: ignore[arg-type]
    ema_dif = _ema(valid_dif, signal)
    dea: list[Optional[float]] = [None] * len(closes)
    hist: list[Optional[float]] = [None] * len(closes)
    for j, i in enumerate(valid_idx):
        if ema_dif[j] is None:
            continue
        dea[i] = ema_dif[j]
        hist[i] = float(dif[i]) - float(ema_dif[j])  # type: ignore[arg-type]
    return dif, dea, hist


def detect_cross(
    dif: list[Optional[float]], dea: list[Optional[float]]
) -> Optional[str]:
    """Return 'golden' | 'death' | None for the latest bar cross vs prior bar."""
    pairs = [
        (i, float(dif[i]), float(dea[i]))
        for i in range(len(dif))
        if dif[i] is not None and dea[i] is not None
    ]
    if len(pairs) < 2:
        return None
    _, d0, e0 = pairs[-2]
    _, d1, e1 = pairs[-1]
    if d0 <= e0 and d1 > e1:
        return "golden"
    if d0 >= e0 and d1 < e1:
        return "death"
    return None


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_closes(symbol: str, interval: str, lookback: str) -> tuple[list[float], float]:
    import yfinance as yf

    yahoo = to_yahoo(symbol)
    df = yf.Ticker(yahoo).history(period=lookback, interval=interval)
    if df is None or df.empty:
        raise RuntimeError(f"empty history for {symbol} ({yahoo})")
    closes = [float(x) for x in df["Close"].tolist()]
    return closes, closes[-1]


def find_state_path(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit)
    # Prefer instance memory/
    cwd = Path.cwd()
    candidate = cwd / "memory" / ".macd_state.json"
    if (cwd / "config.yaml").exists() and (cwd / "memory").is_dir():
        return candidate
    # HARNESS_INSTANCE
    import os

    env = os.environ.get("HARNESS_INSTANCE")
    if env:
        return Path(env) / "memory" / ".macd_state.json"
    return candidate


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="MACD cross scanner with state dedupe")
    parser.add_argument("symbols", nargs="+", help="Symbols e.g. X:BTCUSD X:ETHUSD")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--lookback", default="60d")
    parser.add_argument("--state", help="Override state JSON path")
    parser.add_argument(
        "--force-report",
        action="store_true",
        help="Report current cross even if state unchanged (debug)",
    )
    args = parser.parse_args(argv[1:])

    try:
        import yfinance  # noqa: F401
    except ImportError:
        print(
            "yfinance missing. Run: uv run --with yfinance python …/macd_scan.py …",
            file=sys.stderr,
        )
        return 2

    state_path = find_state_path(args.state)
    state = load_state(state_path)
    now = datetime.now(timezone.utc).isoformat()
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for symbol in args.symbols:
        try:
            closes, last = fetch_closes(symbol, args.interval, args.lookback)
            dif, dea, hist = macd_series(closes)
            cross = detect_cross(dif, dea)
            # Latest valid MACD values
            last_dif = next((dif[i] for i in range(len(dif) - 1, -1, -1) if dif[i] is not None), None)
            last_dea = next((dea[i] for i in range(len(dea) - 1, -1, -1) if dea[i] is not None), None)
            last_hist = next(
                (hist[i] for i in range(len(hist) - 1, -1, -1) if hist[i] is not None), None
            )
            prev = state.get(symbol) or {}
            prev_signal = prev.get("signal")
            is_new = cross is not None and (args.force_report or cross != prev_signal)
            # Always update last computed values; only change signal when cross fires
            new_entry = {
                "signal": cross if cross is not None else prev_signal,
                "last_cross": cross,
                "dif": last_dif,
                "dea": last_dea,
                "hist": last_hist,
                "close": last,
                "ts": now,
            }
            if is_new and cross is not None:
                candidates.append(
                    {
                        "symbol": symbol,
                        "direction": "buy" if cross == "golden" else "sell",
                        "cross": cross,
                        "dif": round(float(last_dif), 6) if last_dif is not None else None,
                        "dea": round(float(last_dea), 6) if last_dea is not None else None,
                        "hist": round(float(last_hist), 6) if last_hist is not None else None,
                        "close": last,
                        "prev_signal": prev_signal,
                    }
                )
                new_entry["signal"] = cross
                new_entry["reported_at"] = now
            state[symbol] = new_entry
        except Exception as e:  # noqa: BLE001
            errors.append({"symbol": symbol, "error": str(e)})

    save_state(state_path, state)

    payload = {
        "ok": True,
        "generated_at": now,
        "state_path": str(state_path),
        "candidates": candidates,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False))
    if candidates:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
