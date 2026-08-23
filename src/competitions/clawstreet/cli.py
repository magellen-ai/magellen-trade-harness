"""ClawStreet competition CLI.

Primary path for agents: this CLI (secrets, Idempotency-Key, dry-run).
Platform history: use `fills` / `orders` (HTTP wrappers). Optional local `audit`.
Raw HTTP: see docs/clawstreet.md (progressive disclosure).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .audit import AuditLog
from .client import ClawStreetClient
from .decision import Decision
from .register import register_agent
from .risk import RiskGate
from .secrets import find_instance_root, load_secrets_into_environ


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_secrets() -> None:
    try:
        load_secrets_into_environ()
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else repo_root() / "configs" / "default.yaml"
    defaults = {
        "default_dry_run": True,
        "require_reasoning": True,
        "min_reasoning_chars": 10,
        "request_timeout_seconds": 20,
        "local_audit": True,
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


def _agent_view(me_data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(me_data.get("agent"), dict):
        return me_data["agent"]
    return me_data


def cmd_status(_args: argparse.Namespace) -> None:
    load_secrets()
    config = load_config()
    client = ClawStreetClient(timeout=float(config.get("request_timeout_seconds", 20)))
    try:
        me_data = client.get_me()
        agent = _agent_view(me_data)
        portfolio = client.get_portfolio()
        market = client.get_market_status()
        print(f"Agent ID: {agent.get('id') or client.agent_id}")
        print(f"Name: {agent.get('name', 'N/A')}")
        print(f"Ticker: {agent.get('ticker', 'N/A')}")
        print(f"Claimed: {agent.get('claimed')}")
        if "is_active" in agent and agent.get("is_active") is not None:
            print(f"Active: {agent.get('is_active')}")
        print(f"Portfolio cash: ${float(portfolio.get('cash') or 0):.2f}")
        print(f"Portfolio equity: ${float(portfolio.get('equity') or 0):.2f}")
        print(f"Total return %: {portfolio.get('total_return_pct')}")
        print("\nMarket Status:")
        print(f"  US equities isOpen: {market.get('isOpen')}")
        print(f"  nextOpen: {market.get('nextOpen')}")
        if market.get("btc") is not None:
            print("  btc quote present: yes (crypto trades 24/7)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_portfolio(_args: argparse.Namespace) -> None:
    load_secrets()
    config = load_config()
    client = ClawStreetClient(timeout=float(config.get("request_timeout_seconds", 20)))
    try:
        portfolio = client.get_portfolio()
        print(f"Cash: ${float(portfolio.get('cash') or 0):.2f}")
        print(f"Equity: ${float(portfolio.get('equity') or 0):.2f}")
        print(f"Total return %: {portfolio.get('total_return_pct')}")
        positions = portfolio.get("positions") or []
        if positions:
            print(f"\nPositions ({len(positions)}):")
            for pos in positions:
                print(
                    f"  {pos.get('symbol')}: qty={pos.get('qty')} "
                    f"avg={pos.get('avg_cost') or pos.get('avg_price')}"
                )
        else:
            print("\nNo positions")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_order(args: argparse.Namespace) -> None:
    load_secrets()
    config = load_config()
    client = ClawStreetClient(timeout=float(config.get("request_timeout_seconds", 20)))
    risk_gate = RiskGate(config)
    audit = AuditLog(args.audit)

    decision = Decision.create(
        symbol=args.symbol,
        side=args.side,
        qty=args.qty,
        reasoning=args.reasoning,
        order_type=args.order_type,
    )
    passed, reason = risk_gate.check(decision)
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

    dry_run = risk_gate.should_dry_run(force_live=args.live)
    if dry_run:
        print("Running in DRY-RUN mode (use --live to place real paper order)")
    else:
        print("Placing LIVE paper order...")

    try:
        order_response = client.create_order(
            symbol=decision.symbol,
            side=decision.side,
            qty=decision.qty,
            reasoning=decision.reasoning,
            order_type=decision.order_type,
            dry_run=dry_run,
        )
        if config.get("local_audit", True):
            event = "order.dry_run" if dry_run else "order.submitted"
            audit.write_event(event, decision.to_dict(), order_response, dry_run)

        print("\nOrder Result:")
        print(f"  Decision ID: {decision.decision_id}")
        print(f"  Symbol: {decision.symbol}")
        print(f"  Side: {decision.side}")
        print(f"  Qty: {decision.qty}")
        print(f"  Dry Run: {dry_run}")
        if not dry_run:
            order = order_response.get("order") or {}
            print(f"  Order ID: {order.get('id') or order_response.get('order_id')}")
            print(f"  Status: {order.get('status') or order_response.get('status')}")
            print(f"  Idempotency-Key: {order_response.get('idempotency_key')}")
        print("\nHistory source of truth: `uv run clawstreet fills` / `orders` (platform).")
        if config.get("local_audit", True) and audit.enabled:
            print(f"Local audit (optional): {audit.path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_audit(args: argparse.Namespace) -> None:
    audit = AuditLog(args.audit)
    if not audit.enabled:
        print(
            "No instance audit path. Run inside an instance dir, set HARNESS_INSTANCE, "
            "or pass --audit PATH. For real history use: uv run clawstreet fills",
            file=sys.stderr,
        )
        sys.exit(1)
    entries = audit.read_entries(limit=args.limit)
    if not entries:
        print(f"No local audit entries at {audit.path}")
        print("Platform history: uv run clawstreet fills")
        return
    print(f"Local audit (not platform history) — {audit.path}\n")
    for entry in entries:
        print(f"[{entry.get('ts')}] {entry.get('event')} {entry.get('decision_id', '')[:8]}")
        print(f"  {str(entry.get('side', '')).upper()} {entry.get('qty')} {entry.get('symbol')}")
        print(f"  dry_run={entry.get('dry_run')} order_id={entry.get('order_id')}")
        print()


def cmd_fills(args: argparse.Namespace) -> None:
    load_secrets()
    config = load_config()
    client = ClawStreetClient(timeout=float(config.get("request_timeout_seconds", 20)))
    try:
        print(json.dumps(client.list_fills(limit=args.limit), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_orders(args: argparse.Namespace) -> None:
    load_secrets()
    config = load_config()
    client = ClawStreetClient(timeout=float(config.get("request_timeout_seconds", 20)))
    try:
        print(json.dumps(client.list_orders(limit=args.limit), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_register(args: argparse.Namespace) -> None:
    instance_root = None
    if args.instance:
        instance_root = repo_root() / "instances" / args.instance
        if not instance_root.is_dir():
            print(f"Error: instance not found: {instance_root}", file=sys.stderr)
            sys.exit(1)
    else:
        instance_root = find_instance_root()

    try:
        public = register_agent(
            instance_root=instance_root,
            name=args.name,
            ticker=args.ticker,
            force=args.force,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("REGISTER_OK")
    print(json.dumps(public, ensure_ascii=False, indent=2))
    if public.get("claim_url"):
        print("\nClaim the agent in the browser before trading, then verify with status.")


def cmd_http_docs(_args: argparse.Namespace) -> None:
    doc = repo_root() / "docs" / "clawstreet.md"
    if not doc.exists():
        print("docs/clawstreet.md missing", file=sys.stderr)
        sys.exit(1)
    print(doc.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ClawStreet paper-trade CLI (secrets + Idempotency-Key + dry-run). "
        "For raw HTTP see: uv run clawstreet http-docs",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Me + portfolio snapshot").set_defaults(func=cmd_status)
    sub.add_parser("portfolio", help="Portfolio").set_defaults(func=cmd_portfolio)

    p_order = sub.add_parser("order", help="Place order (dry-run default)")
    p_order.add_argument("symbol")
    p_order.add_argument("side", choices=["buy", "sell", "short", "cover"])
    p_order.add_argument("qty", type=float)
    p_order.add_argument("reasoning")
    p_order.add_argument("--order-type", default="market")
    p_order.add_argument("--live", action="store_true")
    p_order.add_argument("--audit", help="Override local audit JSONL path")
    p_order.set_defaults(func=cmd_order)

    p_fills = sub.add_parser("fills", help="Platform fills (source of truth)")
    p_fills.add_argument("--limit", type=int, default=10)
    p_fills.set_defaults(func=cmd_fills)

    p_orders = sub.add_parser("orders", help="Platform orders list")
    p_orders.add_argument("--limit", type=int, default=10)
    p_orders.set_defaults(func=cmd_orders)

    p_audit = sub.add_parser(
        "audit",
        help="Local optional audit log (not platform history)",
    )
    p_audit.add_argument("--limit", type=int, default=10)
    p_audit.add_argument("--audit", help="Audit JSONL path")
    p_audit.set_defaults(func=cmd_audit)

    p_reg = sub.add_parser(
        "register",
        help="Register a new ClawStreet agent; write key to instance agent/ or global store",
    )
    p_reg.add_argument("--instance", help="Instance name under instances/")
    p_reg.add_argument("--name", help="Agent display name")
    p_reg.add_argument("--ticker", help="Agent ticker")
    p_reg.add_argument("--force", action="store_true")
    p_reg.set_defaults(func=cmd_register)

    sub.add_parser(
        "http-docs",
        help="Print raw HTTP docs (progressive disclosure for agents)",
    ).set_defaults(func=cmd_http_docs)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command or not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
