"""Local A-share paper broker CLI (multi named accounts)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .audit import AuditLog
from .broker import PaperAshareBroker
from .decision import Decision
from .paths import find_instance_root, ledger_dir, ledger_path, load_secrets_into_environ
from .quotes import CascadingQuoteFeed, FixedQuoteFeed, normalize_symbol
from .risk import RiskGate


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else repo_root() / "configs" / "default.yaml"
    defaults = {
        "default_dry_run": True,
        "require_reasoning": True,
        "min_reasoning_chars": 10,
        "local_audit": True,
        "paper_ashare_initial_cash": 1_000_000.0,
        "paper_ashare_slippage_bps": 5.0,
    }
    if not path.exists():
        return defaults
    try:
        import yaml
    except ImportError:
        return defaults
    with open(path, encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        return defaults
    return {**defaults, **loaded}


def make_broker(args: argparse.Namespace, config: dict[str, Any]) -> PaperAshareBroker:
    load_secrets_into_environ()
    feed = None
    fixed = getattr(args, "fixed_price", None)
    if fixed is not None:
        symbol = normalize_symbol(getattr(args, "symbol", "600519.SH"))
        feed = FixedQuoteFeed({symbol: float(fixed)})
    else:
        feed = CascadingQuoteFeed()
    return PaperAshareBroker(
        account=getattr(args, "account", "default"),
        quote_feed=feed,
        slippage_bps=float(config.get("paper_ashare_slippage_bps", 5.0)),
    )


def cmd_accounts_init(args: argparse.Namespace) -> None:
    config = load_config()
    cash = args.cash if args.cash is not None else float(config["paper_ashare_initial_cash"])
    broker = PaperAshareBroker(account=args.account)
    status = broker.init_account(cash=cash, force=args.force)
    print("ACCOUNT_INIT_OK")
    print(json.dumps(status, ensure_ascii=False, indent=2))


def cmd_accounts_list(_args: argparse.Namespace) -> None:
    root = ledger_dir()
    names = PaperAshareBroker.list_account_files()
    print(f"ledger_dir={root}")
    if not names:
        print("(no accounts — run: uv run paper-ashare accounts init)")
        return
    for name in names:
        path = ledger_path(name)
        try:
            st = PaperAshareBroker(account=name).status()
            print(
                f"{name}: equity={st['equity']} cash={st['cash']} "
                f"ret%={st['total_return_pct']} path={path}"
            )
        except Exception as e:
            print(f"{name}: ERROR {e} path={path}")


def cmd_status(args: argparse.Namespace) -> None:
    config = load_config()
    broker = make_broker(args, config)
    print(json.dumps(broker.status(), ensure_ascii=False, indent=2))


def cmd_portfolio(args: argparse.Namespace) -> None:
    config = load_config()
    broker = make_broker(args, config)
    port = broker.portfolio()
    print(f"Cash: ¥{port['cash']:.2f}")
    positions = port["positions"]
    if not positions:
        print("No positions")
        return
    print(f"Positions ({len(positions)}):")
    for pos in positions:
        print(
            f"  {pos['symbol']}: qty={pos['qty']} avail={pos['available']} "
            f"avg={pos['avg_cost']} last={pos.get('last')} mv={pos.get('market_value')} "
            f"upl={pos.get('unrealized_pnl')}"
        )


def cmd_order(args: argparse.Namespace) -> None:
    config = load_config()
    broker = make_broker(args, config)
    risk = RiskGate(config)
    audit = AuditLog(args.audit)

    decision = Decision.create(
        symbol=args.symbol,
        side=args.side,
        qty=int(args.qty),
        reasoning=args.reasoning,
        order_type=args.order_type,
    )
    passed, reason = risk.check(decision)
    if not passed:
        print(f"Risk gate REJECTED: {reason}", file=sys.stderr)
        if config.get("local_audit", True):
            audit.write_event(
                "order.rejected_local",
                decision.to_dict(),
                {"reason": reason},
                dry_run=True,
            )
        sys.exit(1)

    dry_run = risk.should_dry_run(force_live=args.live)
    if dry_run:
        print("Running in DRY-RUN mode (use --live to write paper ledger)")
    else:
        print("Placing LIVE paper order (local ledger)...")

    result = broker.place_order(
        symbol=decision.symbol,
        side=decision.side,
        qty=decision.qty,
        reasoning=decision.reasoning,
        order_type=decision.order_type,
        dry_run=dry_run,
    )
    if config.get("local_audit", True):
        if not result.get("success"):
            event = "order.rejected_broker"
        else:
            event = "order.dry_run" if dry_run else "order.submitted"
        audit.write_event(event, decision.to_dict(), result, dry_run)

    print("\nOrder Result:")
    print(f"  Decision ID: {decision.decision_id}")
    print(f"  Account: {args.account}")
    print(f"  Symbol: {decision.symbol}")
    print(f"  Side: {decision.side}")
    print(f"  Qty: {decision.qty}")
    print(f"  Dry Run: {dry_run}")
    order = result.get("order") or {}
    print(f"  Status: {order.get('status')}")
    if order.get("reject_reason"):
        print(f"  Reject: {order.get('reject_reason')}")
    if order.get("filled_price") is not None:
        print(f"  Fill px: {order.get('filled_price')} fees={order.get('fees_total')}")
    if result.get("preview"):
        print(f"  Quote source: {result['preview'].get('quote', {}).get('source')}")
    print("\nLedger truth: `uv run paper-ashare fills` / `orders` / `portfolio`.")
    if not result.get("success"):
        sys.exit(1)


def cmd_fills(args: argparse.Namespace) -> None:
    config = load_config()
    broker = make_broker(args, config)
    print(json.dumps(broker.list_fills(limit=args.limit), ensure_ascii=False, indent=2))


def cmd_orders(args: argparse.Namespace) -> None:
    config = load_config()
    broker = make_broker(args, config)
    print(json.dumps(broker.list_orders(limit=args.limit), ensure_ascii=False, indent=2))


def cmd_quote(args: argparse.Namespace) -> None:
    load_secrets_into_environ()
    feed = CascadingQuoteFeed()
    for raw in args.symbols:
        q = feed.get_quote(raw)
        print(
            f"{q.symbol}: last={q.last} prev={q.prev_close} "
            f"source={q.source} asof_ms={q.asof_ms}"
        )


def cmd_http_docs(_args: argparse.Namespace) -> None:
    doc = repo_root() / "docs" / "paper_ashare.md"
    if not doc.exists():
        print("docs/paper_ashare.md missing", file=sys.stderr)
        sys.exit(1)
    print(doc.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local A-share paper broker (SQLite, multi-account, dry-run default).",
    )
    parser.add_argument(
        "--account",
        default="default",
        help="Named paper account (one sqlite file per name)",
    )
    sub = parser.add_subparsers(dest="command")

    p_acc = sub.add_parser("accounts", help="Manage named paper accounts")
    acc_sub = p_acc.add_subparsers(dest="accounts_command")
    p_init = acc_sub.add_parser("init", help="Create/reset account ledger")
    p_init.add_argument("--cash", type=float, default=None)
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_accounts_init)
    acc_sub.add_parser("list", help="List accounts in ledger dir").set_defaults(
        func=cmd_accounts_list
    )

    sub.add_parser("status", help="Cash / equity / return").set_defaults(func=cmd_status)
    sub.add_parser("portfolio", help="Cash + positions").set_defaults(func=cmd_portfolio)

    p_order = sub.add_parser("order", help="Place order (dry-run default)")
    p_order.add_argument("symbol")
    p_order.add_argument("side", choices=["buy", "sell"])
    p_order.add_argument("qty", type=int)
    p_order.add_argument("reasoning")
    p_order.add_argument("--order-type", default="market")
    p_order.add_argument("--live", action="store_true")
    p_order.add_argument("--audit", help="Override local audit JSONL path")
    p_order.add_argument(
        "--fixed-price",
        type=float,
        help="Test only: force last price (skips network quotes)",
    )
    p_order.set_defaults(func=cmd_order)

    p_fills = sub.add_parser("fills", help="Ledger fills (source of truth)")
    p_fills.add_argument("--limit", type=int, default=10)
    p_fills.set_defaults(func=cmd_fills)

    p_orders = sub.add_parser("orders", help="Ledger orders")
    p_orders.add_argument("--limit", type=int, default=10)
    p_orders.set_defaults(func=cmd_orders)

    p_quote = sub.add_parser("quote", help="Last price via fuyao→eastmoney cascade")
    p_quote.add_argument("symbols", nargs="+")
    p_quote.set_defaults(func=cmd_quote)

    sub.add_parser("http-docs", help="Print docs/paper_ashare.md").set_defaults(
        func=cmd_http_docs
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "accounts" and not getattr(args, "accounts_command", None):
        parser.parse_args(["accounts", "--help"])
        sys.exit(1)
    if not args.command or not hasattr(args, "func"):
        # Show where ledgers would land for operators.
        inst = find_instance_root()
        print(f"ledger_dir={ledger_dir(inst)}")
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
