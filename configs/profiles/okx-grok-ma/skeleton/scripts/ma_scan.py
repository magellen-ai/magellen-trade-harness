#!/usr/bin/env python3
"""Dual-MA cross scanner for OKX demo schedule conditions.

Exit 0 + JSON on stdout when a *new* golden/death cross appears (deduped).
Exit 1 when no new signal (CONDITION_SKIP).
Exit 2 on hard errors.

State: memory/.ma_state.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _sma(closes: list[float], window: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    if window <= 0 or len(closes) < window:
        return out
    acc = sum(closes[:window])
    out[window - 1] = acc / window
    for i in range(window, len(closes)):
        acc += closes[i] - closes[i - window]
        out[i] = acc / window
    return out


def _latest_cross(
    fast: list[Optional[float]], slow: list[Optional[float]]
) -> tuple[Optional[str], Optional[int]]:
    pairs = [
        (i, fast[i], slow[i])
        for i in range(len(fast))
        if fast[i] is not None and slow[i] is not None
    ]
    for j in range(len(pairs) - 1, 0, -1):
        i0, f0, s0 = pairs[j]
        _i1, f1, s1 = pairs[j - 1]
        assert f0 is not None and s0 is not None and f1 is not None and s1 is not None
        if f1 <= s1 and f0 > s0:
            return "golden", i0
        if f1 >= s1 and f0 < s0:
            return "death", i0
    return None, None


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="OKX dual-MA cross condition")
    p.add_argument("--inst", default="BTC-USDT")
    p.add_argument("--bar", default="1H")
    p.add_argument("--fast", type=int, default=7)
    p.add_argument("--slow", type=int, default=25)
    p.add_argument(
        "--max-age",
        type=int,
        default=1,
        help="Only emit if cross age (bars from tip) ≤ this (default 1 = last/prev bar)",
    )
    p.add_argument(
        "--force-print",
        action="store_true",
        help="Always print status JSON and exit 0 (for research ticks; not a wake signal)",
    )
    p.add_argument(
        "--state",
        default="memory/.ma_state.json",
        help="Dedupe state path (instance-relative)",
    )
    args = p.parse_args(argv)

    if args.fast >= args.slow:
        print("fast must be < slow", file=sys.stderr)
        return 2

    try:
        from brokers.okx import OkxService
    except ImportError as e:
        print(f"import brokers.okx failed: {e}", file=sys.stderr)
        return 2

    try:
        svc = OkxService.from_env(require_creds=False)
        candles = svc.candles(args.inst, bar=args.bar, limit=max(args.slow + 10, 80))
    except Exception as e:  # noqa: BLE001
        print(f"okx candles failed: {e}", file=sys.stderr)
        return 2

    if candles and str(candles[-1].get("confirm")) == "0":
        candles = candles[:-1]
    if len(candles) < args.slow + 2:
        print("not enough candles", file=sys.stderr)
        return 2

    closes = [float(c["close"]) for c in candles]
    fast = _sma(closes, args.fast)
    slow = _sma(closes, args.slow)
    kind, idx = _latest_cross(fast, slow)
    tip = len(closes) - 1
    age = (tip - idx) if idx is not None else None
    bar_ts = candles[idx]["ts"] if idx is not None else candles[-1]["ts"]
    payload: dict[str, Any] = {
        "inst": args.inst,
        "bar": args.bar,
        "fast": args.fast,
        "slow": args.slow,
        "close": closes[-1],
        "ma_fast": fast[-1],
        "ma_slow": slow[-1],
        "cross": kind,
        "cross_age_bars": age,
        "cross_ts": bar_ts,
        "asof": datetime.now(timezone.utc).isoformat(),
    }

    if args.force_print:
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if kind is None or age is None or age > args.max_age:
        return 1

    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    prev: dict[str, Any] = {}
    if state_path.is_file():
        try:
            prev = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}

    sig_id = f"{args.inst}|{args.bar}|{kind}|{bar_ts}"
    if prev.get("last_signal_id") == sig_id:
        return 1

    state_path.write_text(
        json.dumps(
            {
                "last_signal_id": sig_id,
                "last": payload,
                "updated": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"candidates": [payload]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
