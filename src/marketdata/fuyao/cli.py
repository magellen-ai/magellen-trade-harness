"""Fuyao / HiThink Finance CLI (quotes, search, bars, calendar)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .client import FuyaoClient, normalize_thscode
from .secrets import load_secrets_into_environ, resolve_api_key


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _client(timeout: float = 20.0) -> FuyaoClient:
    load_secrets_into_environ()
    return FuyaoClient(timeout=timeout)


def cmd_quote(args: argparse.Namespace) -> None:
    client = _client()
    codes = [normalize_thscode(s) for s in args.symbols]
    payload = client.snapshot(codes)
    data = payload.get("data") or {}
    items = data.get("item") or []
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"timestamp_ms={data.get('timestamp')} total={data.get('total')}")
    for item in items:
        print(
            f"{item.get('thscode')}: last={item.get('last_price')} "
            f"chg%={item.get('price_change_ratio_pct')} "
            f"open={item.get('open_price')} high={item.get('high_price')} "
            f"low={item.get('low_price')} prev={item.get('prev_price')} "
            f"vol={item.get('volume')}"
        )
    if not items:
        print("No snapshot rows returned", file=sys.stderr)
        sys.exit(1)


def cmd_search(args: argparse.Namespace) -> None:
    client = _client()
    payload = client.search_tickers(args.query, limit=args.limit)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    data = payload.get("data") or {}
    items = data.get("item") or data.get("items") or []
    if isinstance(data, list):
        items = data
    for item in items:
        if isinstance(item, dict):
            print(
                f"{item.get('thscode') or item.get('ticker')}: "
                f"{item.get('name') or item.get('security_name') or ''}"
            )
        else:
            print(item)
    if not items:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_bars(args: argparse.Namespace) -> None:
    client = _client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(args.days, 1))
    payload = client.historical(
        thscode=args.symbol,
        start_ms=int(start.timestamp() * 1000),
        end_ms=int(end.timestamp() * 1000),
        interval="1d",
        adjust=args.adjust,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    data = payload.get("data") or {}
    items = data.get("item") or []
    print(f"{normalize_thscode(args.symbol)} bars={len(items)} adjust={args.adjust}")
    for bar in items[-min(10, len(items)) :]:
        ts = bar.get("date_ms")
        day = (
            datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
            if isinstance(ts, (int, float))
            else ts
        )
        print(
            f"  {day}: o={bar.get('open_price')} h={bar.get('high_price')} "
            f"l={bar.get('low_price')} c={bar.get('close_price')} v={bar.get('volume')}"
        )


def cmd_calendar(_args: argparse.Namespace) -> None:
    client = _client()
    payload = client.calendar()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_http_docs(_args: argparse.Namespace) -> None:
    doc = repo_root() / "docs" / "fuyao.md"
    if not doc.exists():
        print("docs/fuyao.md missing", file=sys.stderr)
        sys.exit(1)
    print(doc.read_text(encoding="utf-8"))


def cmd_ping(_args: argparse.Namespace) -> None:
    key = resolve_api_key()
    if not key:
        print(
            "NO_KEY: set HITHINK_FINANCE_API_KEY in agent/secrets.env "
            "(https://fuyao.aicubes.cn/admin/)",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"KEY_PRESENT len={len(key)}")
    client = _client()
    payload = client.snapshot(["600519.SH"])
    items = ((payload.get("data") or {}).get("item")) or []
    if not items:
        print("PING_FAIL: empty snapshot", file=sys.stderr)
        sys.exit(1)
    print(f"PING_OK {items[0].get('thscode')} last={items[0].get('last_price')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tonghuashun HiThink Finance (fuyao) market data CLI. Read-only.",
    )
    sub = parser.add_subparsers(dest="command")

    p_quote = sub.add_parser("quote", help="A-share price snapshot")
    p_quote.add_argument("symbols", nargs="+", help="600519 / 600519.SH / …")
    p_quote.add_argument("--json", action="store_true")
    p_quote.set_defaults(func=cmd_quote)

    p_search = sub.add_parser("search", help="Ticker search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_bars = sub.add_parser("bars", help="Daily bars (last N calendar days window)")
    p_bars.add_argument("symbol")
    p_bars.add_argument("--days", type=int, default=30)
    p_bars.add_argument(
        "--adjust",
        choices=["none", "forward", "backward"],
        default="forward",
    )
    p_bars.add_argument("--json", action="store_true")
    p_bars.set_defaults(func=cmd_bars)

    sub.add_parser("calendar", help="A-share trading calendar").set_defaults(
        func=cmd_calendar
    )
    sub.add_parser("ping", help="Check API key + one snapshot").set_defaults(
        func=cmd_ping
    )
    sub.add_parser("http-docs", help="Print docs/fuyao.md").set_defaults(
        func=cmd_http_docs
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command or not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
