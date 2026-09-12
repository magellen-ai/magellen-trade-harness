#!/usr/bin/env python3
"""OKX demo: dual moving-average crossover (mainstream spot CTA-lite).

One-shot cycle (not a daemon):
  1) pull candles  2) MA_fast / MA_slow  3) gold/death cross on last closed bar
  4) small market order on demo + optional OCO TP/SL

Usage::

    uv run python scripts/okx_ma_cross_demo.py
    uv run python scripts/okx_ma_cross_demo.py --live
    uv run python scripts/okx_ma_cross_demo.py --inst BTC-USDT --bar 15m --fast 7 --slow 25 --quote-sz 20 --live
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Allow `uv run python scripts/...` without install edge-cases.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from brokers.okx import OkxService, OrderRequest  # noqa: E402


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


def _cross_signal(
    fast: list[Optional[float]],
    slow: list[Optional[float]],
    *,
    max_age_bars: int = 0,
) -> tuple[str, Optional[int]]:
    """Return (buy|sell|hold, age_bars).

    ``max_age_bars=0`` → only a cross on the latest closed bar.
    ``max_age_bars=N`` → also act if the most recent cross is ≤ N bars ago.
    """
    pairs = [
        (i, fast[i], slow[i])
        for i in range(len(fast))
        if fast[i] is not None and slow[i] is not None
    ]
    if len(pairs) < 2:
        return "hold", None

    last_i = pairs[-1][0]
    # search newest cross first
    for j in range(len(pairs) - 1, 0, -1):
        i0, f0, s0 = pairs[j]
        _i1, f1, s1 = pairs[j - 1]
        assert f0 is not None and s0 is not None and f1 is not None and s1 is not None
        age = last_i - i0
        if f1 <= s1 and f0 > s0:
            sig = "buy"
        elif f1 >= s1 and f0 < s0:
            sig = "sell"
        else:
            continue
        if age <= max_age_bars:
            return sig, age
        # older than allowed — stop (newest cross already too old)
        return "hold", age
    return "hold", None


def _avail(svc: OkxService, ccy: str) -> float:
    payload = svc.balance(ccy=ccy)
    details = ((payload.get("data") or [{}])[0].get("details") or [])
    for row in details:
        if isinstance(row, dict) and row.get("ccy") == ccy:
            for key in ("availBal", "cashBal", "eq"):
                if row.get(key) not in (None, ""):
                    return float(row[key])
    return 0.0


def run(args: argparse.Namespace) -> dict[str, Any]:
    svc = OkxService.from_env(default_dry_run=not args.live)
    if not svc.simulated and args.live:
        raise SystemExit("Refusing --live on non-simulated OKX env. Set OKX_SIMULATED=1.")

    candles = svc.candles(args.inst, bar=args.bar, limit=max(args.slow + 5, 80))
    # Drop unconfirmed last candle if present (confirm == "0").
    if candles and str(candles[-1].get("confirm")) == "0":
        candles = candles[:-1]
    closes = [float(c["close"]) for c in candles]
    fast = _sma(closes, args.fast)
    slow = _sma(closes, args.slow)
    signal, cross_age = _cross_signal(fast, slow, max_age_bars=args.max_cross_age)

    last = candles[-1]
    last_close = float(last["close"])
    last_ts = datetime.fromtimestamp(int(last["ts"]) / 1000, tz=timezone.utc).isoformat()
    f_now = fast[-1]
    s_now = slow[-1]

    usdt = _avail(svc, "USDT")
    base = args.inst.split("-")[0]
    base_bal = _avail(svc, base)
    ticker = svc.ticker(args.inst)
    last_px = float(ticker.get("last") or last_close)

    report: dict[str, Any] = {
        "strategy": "dual_ma_cross",
        "inst": args.inst,
        "bar": args.bar,
        "fast": args.fast,
        "slow": args.slow,
        "max_cross_age": args.max_cross_age,
        "cross_age_bars": cross_age,
        "simulated": svc.simulated,
        "live": bool(args.live),
        "bar_ts": last_ts,
        "close": last_close,
        "ma_fast": round(f_now, 4) if f_now is not None else None,
        "ma_slow": round(s_now, 4) if s_now is not None else None,
        "signal": signal,
        "balances": {base: base_bal, "USDT": usdt},
        "ticker_last": last_px,
        "actions": [],
    }

    if signal == "hold":
        report["message"] = "No crossover on last closed bar — no order."
        return report

    if signal == "buy":
        quote_sz = min(float(args.quote_sz), usdt * 0.95)
        if quote_sz < 5:
            report["message"] = f"Skip buy: USDT avail {usdt} too low for quote_sz={args.quote_sz}"
            return report
        order = OrderRequest(
            inst_id=args.inst,
            side="buy",
            sz=f"{quote_sz:.4f}",
            td_mode="cash",
            ord_type="market",
            tgt_ccy="quote_ccy",
            tag="macross",
        )
        placed = svc.place_order(order, dry_run=not args.live)
        report["actions"].append({"type": "market_buy", "result": placed})

        if args.live and placed.get("success") and args.sl_pct > 0:
            # Approximate base size from fill notional; fallback quote/last.
            base_sz = quote_sz / last_px
            fills = svc.list_fills(inst_id=args.inst, limit=5)
            for fill in fills:
                if fill.get("ordId") == placed.get("ord_id"):
                    base_sz = float(fill.get("fillSz") or base_sz)
                    break
            sl_px = last_px * (1 - args.sl_pct / 100.0)
            tp_px = last_px * (1 + args.tp_pct / 100.0)
            # Round sz to instrument-ish precision for BTC spot.
            sz_str = f"{base_sz:.8f}".rstrip("0").rstrip(".")
            oco = svc.place_oco_tp_sl(
                inst_id=args.inst,
                side="sell",
                sz=sz_str,
                tp_trigger_px=f"{tp_px:.2f}",
                sl_trigger_px=f"{sl_px:.2f}",
                td_mode="cash",
                reduce_only=None,
                dry_run=False,
            )
            report["actions"].append(
                {
                    "type": "oco_tp_sl",
                    "tp": round(tp_px, 2),
                    "sl": round(sl_px, 2),
                    "sz": sz_str,
                    "result": oco,
                }
            )
        report["message"] = "Buy signal executed."
        return report

    # sell
    sell_sz = min(float(args.base_sz), base_bal * 0.95)
    if sell_sz <= 0:
        report["message"] = f"Skip sell: {base} avail {base_bal}"
        return report
    # BTC lot: keep 8 decimals
    sz_str = f"{sell_sz:.8f}".rstrip("0").rstrip(".")
    order = OrderRequest(
        inst_id=args.inst,
        side="sell",
        sz=sz_str,
        td_mode="cash",
        ord_type="market",
        tgt_ccy="base_ccy",
        tag="macross",
    )
    placed = svc.place_order(order, dry_run=not args.live)
    report["actions"].append({"type": "market_sell", "result": placed})
    report["message"] = "Sell signal executed."
    return report


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="OKX demo dual-MA crossover (one shot)")
    p.add_argument("--inst", default="BTC-USDT")
    p.add_argument("--bar", default="15m", help="OKX bar size, e.g. 5m/15m/1H")
    p.add_argument("--fast", type=int, default=7)
    p.add_argument("--slow", type=int, default=25)
    p.add_argument("--quote-sz", type=float, default=20.0, help="USDT notional on buy")
    p.add_argument("--base-sz", type=float, default=0.0002, help="Base size on sell")
    p.add_argument("--tp-pct", type=float, default=1.5, help="Take-profit %% after buy")
    p.add_argument("--sl-pct", type=float, default=1.0, help="Stop-loss %% after buy")
    p.add_argument(
        "--max-cross-age",
        type=int,
        default=0,
        help="Act if newest MA cross is ≤ N bars ago (0 = only last bar)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Send orders to OKX (still demo if OKX_SIMULATED=1)",
    )
    args = p.parse_args(argv)
    if args.fast >= args.slow:
        raise SystemExit("--fast must be < --slow")
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
