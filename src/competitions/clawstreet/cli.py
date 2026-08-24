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

from .audit import AuditLog, compute_exposure
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
    """Merge repo defaults with instance ``config.yaml`` → ``trade`` (and flat aliases)."""
    path = Path(config_path) if config_path else repo_root() / "configs" / "default.yaml"
    defaults: dict[str, Any] = {
        "default_dry_run": True,
        "require_reasoning": True,
        "min_reasoning_chars": 10,
        "request_timeout_seconds": 20,
        "local_audit": True,
        "book_tag": None,
        "soft_limit_usd": None,
        "per_order_max_usd": None,
        "symbol_prefix": None,
    }
    loaded: dict[str, Any] = {}
    if path.exists():
        try:
            import yaml
        except ImportError:
            yaml = None  # type: ignore
        if yaml is not None:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            if isinstance(raw, dict):
                loaded = raw

    cfg = {**defaults, **{k: v for k, v in loaded.items() if k in defaults or k == "local_audit"}}

    inst = find_instance_root()
    if inst is not None:
        inst_cfg_path = inst / "config.yaml"
        if inst_cfg_path.exists():
            try:
                import yaml
            except ImportError:
                yaml = None  # type: ignore
            if yaml is not None:
                with open(inst_cfg_path, encoding="utf-8") as f:
                    inst_raw = yaml.safe_load(f) or {}
                if isinstance(inst_raw, dict):
                    trade = inst_raw.get("trade") or {}
                    if isinstance(trade, dict):
                        for key in (
                            "default_dry_run",
                            "book_tag",
                            "soft_limit_usd",
                            "per_order_max_usd",
                            "symbol_prefix",
                            "require_reasoning",
                            "min_reasoning_chars",
                            "local_audit",
                        ):
                            if key in trade and trade[key] is not None:
                                cfg[key] = trade[key]
                    # Flat aliases at instance top-level (legacy / override)
                    for key in (
                        "default_dry_run",
                        "soft_limit_usd",
                        "per_order_max_usd",
                        "book_tag",
                        "symbol_prefix",
                    ):
                        if key in inst_raw and inst_raw[key] is not None:
                            cfg[key] = inst_raw[key]
    return cfg


def _instance_name() -> Optional[str]:
    root = find_instance_root()
    return root.name if root is not None else None


def _quote_price(client: ClawStreetClient, symbol: str) -> Optional[float]:
    try:
        data = client.get_quotes([symbol])
    except Exception:  # noqa: BLE001 — soft-limit needs a price; fail open with warning upstream
        return None
    quotes = data.get("quotes") if isinstance(data, dict) else None
    if isinstance(quotes, list):
        for q in quotes:
            if isinstance(q, dict) and str(q.get("symbol", "")).upper() == symbol.upper():
                for key in ("price", "last", "last_price", "mid"):
                    if q.get(key) is not None:
                        try:
                            return float(q[key])
                        except (TypeError, ValueError):
                            continue
    if isinstance(quotes, dict):
        q = quotes.get(symbol) or quotes.get(symbol.upper())
        if isinstance(q, dict):
            for key in ("price", "last", "last_price", "mid"):
                if q.get(key) is not None:
                    try:
                        return float(q[key])
                    except (TypeError, ValueError):
                        continue
        elif q is not None:
            try:
                return float(q)
            except (TypeError, ValueError):
                pass
    # Some APIs return top-level symbol → price
    if isinstance(data, dict) and symbol in data:
        try:
            return float(data[symbol])
        except (TypeError, ValueError):
            pass
    return None


def _used_exposure(audit: AuditLog, book_tag: Optional[str]) -> float:
    if not audit.enabled:
        return 0.0
    # Read chronologically (all entries) for exposure sum
    entries = audit.read_entries(limit=None, book_tag=None)
    # read_entries reverses; compute_exposure is order-independent for sums
    exp = compute_exposure(entries, book_tag=book_tag)
    return float(exp["live_used_usd"])


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
    book_tag = args.book_tag or config.get("book_tag")
    strategy = args.strategy
    instance = _instance_name()

    decision = Decision.create(
        symbol=args.symbol,
        side=args.side,
        qty=args.qty,
        reasoning=args.reasoning,
        order_type=args.order_type,
        strategy=strategy,
        book_tag=book_tag,
    )
    dry_run = risk_gate.should_dry_run(force_live=args.live)

    notional_usd: Optional[float] = None
    price = _quote_price(client, decision.symbol)
    if price is not None:
        notional_usd = abs(float(decision.qty) * price)
    elif args.live:
        print(
            "Warning: could not fetch quote for notional; soft-limit check uses size only if set",
            file=sys.stderr,
        )

    used = _used_exposure(audit, book_tag) if book_tag else _used_exposure(audit, None)

    passed, reason, warning = risk_gate.check(
        decision,
        dry_run=dry_run,
        notional_usd=notional_usd,
        used_notional_usd=used,
    )
    if warning:
        print(f"Risk gate WARNING: {warning}", file=sys.stderr)
    if not passed:
        print(f"Risk gate REJECTED: {reason}", file=sys.stderr)
        if config.get("local_audit", True):
            audit.write_event(
                "order.rejected_local",
                decision.to_dict(),
                {"reason": reason},
                dry_run=dry_run,
                instance=instance,
                book_tag=book_tag,
                strategy=strategy,
                notional_usd=notional_usd,
            )
        sys.exit(1)

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
            instance_prefix=instance,
        )
        if config.get("local_audit", True):
            event = "order.dry_run" if dry_run else "order.submitted"
            audit.write_event(
                event,
                decision.to_dict(),
                order_response,
                dry_run,
                instance=instance,
                book_tag=book_tag,
                strategy=strategy,
                notional_usd=notional_usd,
            )

        print("\nOrder Result:")
        print(f"  Decision ID: {decision.decision_id}")
        print(f"  Symbol: {decision.symbol}")
        print(f"  Side: {decision.side}")
        print(f"  Qty: {decision.qty}")
        if notional_usd is not None:
            print(f"  Notional (est): ${notional_usd:.2f}")
        if book_tag:
            print(f"  Book tag: {book_tag}")
        if strategy:
            print(f"  Strategy: {strategy}")
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
    tag = args.tag
    entries = audit.read_entries(limit=args.limit, book_tag=tag)
    if not entries:
        print(f"No local audit entries at {audit.path}" + (f" (tag={tag})" if tag else ""))
        print("Platform history: uv run clawstreet fills")
        return
    print(f"Local audit (not platform history) — {audit.path}\n")
    for entry in entries:
        tag_s = entry.get("book_tag") or "-"
        print(
            f"[{entry.get('ts')}] {entry.get('event')} "
            f"{entry.get('decision_id', '')[:8]} tag={tag_s}"
        )
        print(f"  {str(entry.get('side', '')).upper()} {entry.get('qty')} {entry.get('symbol')}")
        notional = entry.get("notional_usd")
        extra = f" notional=${notional:.2f}" if isinstance(notional, (int, float)) else ""
        print(
            f"  dry_run={entry.get('dry_run')} order_id={entry.get('order_id')}"
            f" strategy={entry.get('strategy') or '-'}{extra}"
        )
        if entry.get("reason"):
            print(f"  reason={entry.get('reason')}")
        print()


def cmd_exposure(args: argparse.Namespace) -> None:
    """Read-only: live book usage vs soft limit + today's dry-run intent."""
    config = load_config()
    audit = AuditLog(args.audit)
    book_tag = args.tag or config.get("book_tag")
    soft = config.get("soft_limit_usd")
    per_order = config.get("per_order_max_usd")
    instance = _instance_name()

    if not audit.enabled:
        print(
            "No instance audit path. Run inside an instance dir, set HARNESS_INSTANCE, "
            "or pass --audit PATH.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Full history (chronological order irrelevant for sum)
    all_entries = audit.read_entries(limit=None)
    exp = compute_exposure(all_entries, book_tag=book_tag)
    live_used = float(exp["live_used_usd"])
    remaining = None if soft is None else float(soft) - live_used

    out = {
        "instance": instance,
        "book_tag": book_tag,
        "soft_limit_usd": soft,
        "per_order_max_usd": per_order,
        "live_used_usd": live_used,
        "remaining_usd": remaining,
        "dry_run_intent_usd_today": exp["dry_run_intent_usd_today"],
        "live_order_count": exp["live_order_count"],
        "dry_run_order_count_today": exp["dry_run_order_count_today"],
        "skipped_missing_notional": exp["skipped_missing_notional"],
        "audit_path": str(audit.path) if audit.path else None,
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"Instance: {instance or '(none)'}")
    print(f"Book tag: {book_tag or '(none)'}")
    print(f"Live used (audit): ${live_used:.2f}")
    if soft is not None:
        print(f"Soft limit: ${float(soft):.2f}")
        print(f"Remaining: ${float(remaining or 0):.2f}")
    if per_order is not None:
        print(f"Per-order max: ${float(per_order):.2f}")
    print(f"Dry-run intent today: ${float(exp['dry_run_intent_usd_today']):.2f}")
    print(
        f"Counts: live_orders={exp['live_order_count']} "
        f"dry_run_today={exp['dry_run_order_count_today']} "
        f"skipped_no_notional={exp['skipped_missing_notional']}"
    )


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
    p_order.add_argument("--strategy", help="Local strategy label (audit only)")
    p_order.add_argument("--book-tag", help="Override config trade.book_tag")
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
    p_audit.add_argument("--tag", help="Filter by book_tag")
    p_audit.add_argument("--audit", help="Audit JSONL path")
    p_audit.set_defaults(func=cmd_audit)

    p_exp = sub.add_parser(
        "exposure",
        help="Local book soft-limit usage (from audit; not platform)",
    )
    p_exp.add_argument("--tag", help="Filter by book_tag (default: config trade.book_tag)")
    p_exp.add_argument("--audit", help="Audit JSONL path")
    p_exp.add_argument("--json", action="store_true", help="JSON output")
    p_exp.set_defaults(func=cmd_exposure)

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
