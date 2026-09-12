"""Thin CLI over OkxService. Prefer importing OkxService from Python for quant code."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from .errors import OkxError
from .secrets import env_simulated_default, load_secrets_into_environ
from .service import OkxService
from .types import AlgoOrderRequest, AttachTpSl, OrderRequest


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _svc(args: argparse.Namespace, *, require_creds: bool = True) -> OkxService:
    load_secrets_into_environ(require_creds=require_creds)
    simulated = env_simulated_default()
    if getattr(args, "live_env", False):
        simulated = False
    if getattr(args, "demo", False):
        simulated = True
    return OkxService.from_env(
        simulated=simulated,
        default_dry_run=True,
        require_creds=require_creds,
    )


def _live_flag(args: argparse.Namespace) -> bool:
    """True when the call should stay dry-run (default). ``--live`` → False."""
    return not bool(getattr(args, "live", False))


def _svc_for_mutate(args: argparse.Namespace) -> OkxService:
    """Dry-run can build payloads without keys; ``--live`` requires Demo/live keys."""
    return _svc(args, require_creds=not _live_flag(args))


def cmd_status(args: argparse.Namespace) -> None:
    svc = _svc(args)
    _print_json(svc.status())


def cmd_balance(args: argparse.Namespace) -> None:
    svc = _svc(args)
    _print_json(svc.balance(ccy=args.ccy))


def cmd_positions(args: argparse.Namespace) -> None:
    svc = _svc(args)
    _print_json(svc.positions(inst_type=args.inst_type, inst_id=args.inst_id))


def cmd_ticker(args: argparse.Namespace) -> None:
    # Public; still load secrets for consistent env, but don't require.
    try:
        load_secrets_into_environ(require_creds=False)
    except Exception:
        pass
    svc = OkxService.from_env(require_creds=False, simulated=env_simulated_default())
    _print_json(svc.ticker(args.inst_id))


def cmd_order_place(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    attach = None
    if args.sl_trigger or args.tp_trigger:
        attach = AttachTpSl(
            tp_trigger_px=args.tp_trigger,
            tp_ord_px=args.tp_ord or ("-1" if args.tp_trigger else None),
            sl_trigger_px=args.sl_trigger,
            sl_ord_px=args.sl_ord or ("-1" if args.sl_trigger else None),
        )
    order = OrderRequest(
        inst_id=args.inst_id,
        side=args.side,
        sz=str(args.sz),
        td_mode=args.td_mode,
        ord_type=args.ord_type,
        px=str(args.px) if args.px is not None else None,
        cl_ord_id=args.cl_ord_id,
        tag=args.tag,
        reduce_only=args.reduce_only,
        pos_side=args.pos_side,
        tgt_ccy=args.tgt_ccy,
        attach_tp_sl=attach,
    )
    result = svc.place_order(order, dry_run=_live_flag(args))
    _print_json(result)
    if not result.get("success", True):
        sys.exit(2)


def cmd_order_cancel(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    result = svc.cancel_order(
        inst_id=args.inst_id,
        ord_id=args.ord_id,
        cl_ord_id=args.cl_ord_id,
        dry_run=_live_flag(args),
    )
    _print_json(result)


def cmd_order_amend(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    result = svc.amend_order(
        inst_id=args.inst_id,
        ord_id=args.ord_id,
        cl_ord_id=args.cl_ord_id,
        new_sz=str(args.new_sz) if args.new_sz is not None else None,
        new_px=str(args.new_px) if args.new_px is not None else None,
        dry_run=_live_flag(args),
    )
    _print_json(result)


def cmd_order_get(args: argparse.Namespace) -> None:
    svc = _svc(args)
    _print_json(
        svc.get_order(inst_id=args.inst_id, ord_id=args.ord_id, cl_ord_id=args.cl_ord_id)
    )


def cmd_orders(args: argparse.Namespace) -> None:
    svc = _svc(args)
    if args.history:
        rows = svc.list_orders_history(
            inst_type=args.inst_type or "SPOT",
            inst_id=args.inst_id,
            limit=args.limit,
        )
    else:
        rows = svc.list_orders_pending(
            inst_type=args.inst_type,
            inst_id=args.inst_id,
            limit=args.limit,
        )
    _print_json(rows)


def cmd_fills(args: argparse.Namespace) -> None:
    svc = _svc(args)
    _print_json(
        svc.list_fills(inst_type=args.inst_type, inst_id=args.inst_id, limit=args.limit)
    )


def cmd_algo_place(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    algo = AlgoOrderRequest(
        inst_id=args.inst_id,
        side=args.side,
        sz=str(args.sz),
        ord_type=args.ord_type,
        td_mode=args.td_mode,
        cl_ord_id=args.cl_ord_id,
        tag=args.tag,
        reduce_only=args.reduce_only,
        pos_side=args.pos_side,
        tp_trigger_px=args.tp_trigger,
        tp_ord_px=args.tp_ord,
        sl_trigger_px=args.sl_trigger,
        sl_ord_px=args.sl_ord,
        trigger_px=args.trigger_px,
        order_px=args.order_px,
        callback_ratio=args.callback_ratio,
        callback_spread=args.callback_spread,
        active_px=args.active_px,
        px_var=args.px_var,
        px_spread=args.px_spread,
        sz_limit=args.sz_limit,
        px_limit=args.px_limit,
        time_interval=args.time_interval,
    )
    result = svc.place_algo(algo, dry_run=_live_flag(args))
    _print_json(result)
    if not result.get("success", True):
        sys.exit(2)


def cmd_algo_sl(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    result = svc.place_stop_loss(
        inst_id=args.inst_id,
        side=args.side,
        sz=str(args.sz),
        trigger_px=str(args.trigger_px),
        td_mode=args.td_mode,
        ord_px=str(args.ord_px),
        reduce_only=False if args.no_reduce_only else True,
        pos_side=args.pos_side,
        dry_run=_live_flag(args),
    )
    _print_json(result)
    if not result.get("success", True):
        sys.exit(2)


def cmd_algo_tp(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    result = svc.place_take_profit(
        inst_id=args.inst_id,
        side=args.side,
        sz=str(args.sz),
        trigger_px=str(args.trigger_px),
        td_mode=args.td_mode,
        ord_px=str(args.ord_px),
        reduce_only=False if args.no_reduce_only else True,
        pos_side=args.pos_side,
        dry_run=_live_flag(args),
    )
    _print_json(result)
    if not result.get("success", True):
        sys.exit(2)


def cmd_algo_oco(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    result = svc.place_oco_tp_sl(
        inst_id=args.inst_id,
        side=args.side,
        sz=str(args.sz),
        tp_trigger_px=str(args.tp_trigger),
        sl_trigger_px=str(args.sl_trigger),
        td_mode=args.td_mode,
        tp_ord_px=str(args.tp_ord),
        sl_ord_px=str(args.sl_ord),
        reduce_only=False if args.no_reduce_only else True,
        pos_side=args.pos_side,
        dry_run=_live_flag(args),
    )
    _print_json(result)
    if not result.get("success", True):
        sys.exit(2)


def cmd_algo_cancel(args: argparse.Namespace) -> None:
    svc = _svc_for_mutate(args)
    result = svc.cancel_algo(
        inst_id=args.inst_id,
        algo_id=args.algo_id,
        dry_run=_live_flag(args),
    )
    _print_json(result)


def cmd_algos(args: argparse.Namespace) -> None:
    svc = _svc(args)
    if args.history:
        rows = svc.list_algos_history(
            ord_type=args.ord_type,
            inst_type=args.inst_type,
            inst_id=args.inst_id,
            limit=args.limit,
        )
    else:
        rows = svc.list_algos_pending(
            ord_type=args.ord_type,
            inst_type=args.inst_type,
            inst_id=args.inst_id,
            limit=args.limit,
        )
    _print_json(rows)


def cmd_http_docs(_args: argparse.Namespace) -> None:
    print(
        """OKX v5 (production-shaped service; default = demo via x-simulated-trading: 1)

Docs: https://www.okx.com/docs-v5/zh/

Auth headers: OK-ACCESS-KEY / SIGN / TIMESTAMP / PASSPHRASE
Demo: same base URL https://www.okx.com + header x-simulated-trading: 1
      (or SDK flag=1). Demo keys are created under Demo Trading.

Key endpoints used by OkxService:
  GET  /api/v5/account/balance
  GET  /api/v5/account/positions
  GET  /api/v5/account/config
  GET  /api/v5/market/ticker          (public)
  POST /api/v5/trade/order            limit/market/post_only/ioc/fok (+ optional attach TP/SL)
  POST /api/v5/trade/cancel-order
  POST /api/v5/trade/amend-order
  GET  /api/v5/trade/order
  GET  /api/v5/trade/orders-pending
  GET  /api/v5/trade/orders-history
  GET  /api/v5/trade/fills
  POST /api/v5/trade/order-algo       conditional / oco / trigger / trailing / iceberg / twap
  POST /api/v5/trade/cancel-algos
  GET  /api/v5/trade/orders-algo-pending
  GET  /api/v5/trade/orders-algo-history

Python (preferred for quant):
  from brokers.okx import OkxService, OrderRequest, stop_loss
  svc = OkxService.from_env()  # simulated by default
  svc.place_order(OrderRequest(...), dry_run=False)
  svc.place_stop_loss(inst_id="BTC-USDT", side="sell", sz="0.01", trigger_px="50000", dry_run=False)
"""
    )


def _add_live(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--live",
        action="store_true",
        help="Actually send to OKX (default is dry-run). Still uses demo keys unless --live-env.",
    )


def _add_inst_side_sz(p: argparse.ArgumentParser) -> None:
    p.add_argument("--inst-id", required=True, help="e.g. BTC-USDT or BTC-USDT-SWAP")
    p.add_argument("--side", required=True, choices=["buy", "sell"])
    p.add_argument("--sz", required=True, help="Size (string-compatible)")
    p.add_argument(
        "--td-mode",
        default="cash",
        choices=["cash", "cross", "isolated"],
        help="cash=spot; cross/isolated=margin/derivatives",
    )
    p.add_argument("--pos-side", choices=["long", "short", "net"], default=None)
    p.add_argument("--cl-ord-id", default=None)
    p.add_argument("--tag", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="okx",
        description="OKX v5 broker CLI (thin). Service layer: brokers.okx.OkxService",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Force simulated trading header (default unless OKX_SIMULATED=0)",
    )
    parser.add_argument(
        "--live-env",
        action="store_true",
        help="Use live trading env (no x-simulated-trading). Dangerous; needs live API keys.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="Account config + equity snapshot")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("balance", help="Account balance")
    p.add_argument("--ccy", default=None)
    p.set_defaults(func=cmd_balance)

    p = sub.add_parser("positions", help="Open positions")
    p.add_argument("--inst-type", default=None, help="SPOT / MARGIN / SWAP / FUTURES / OPTION")
    p.add_argument("--inst-id", default=None)
    p.set_defaults(func=cmd_positions)

    p = sub.add_parser("ticker", help="Public ticker")
    p.add_argument("inst_id")
    p.set_defaults(func=cmd_ticker)

    # order group
    order = sub.add_parser("order", help="Ordinary orders")
    order_sub = order.add_subparsers(dest="order_cmd", required=True)

    p = order_sub.add_parser("place", help="Place limit/market/… order")
    _add_inst_side_sz(p)
    p.add_argument(
        "--ord-type",
        default="market",
        choices=["market", "limit", "post_only", "fok", "ioc"],
    )
    p.add_argument("--px", default=None)
    p.add_argument("--tgt-ccy", choices=["base_ccy", "quote_ccy"], default=None)
    p.add_argument("--reduce-only", action="store_true", default=None)
    p.add_argument("--tp-trigger", default=None, help="Attach take-profit trigger (attachAlgoOrds)")
    p.add_argument("--tp-ord", default=None, help="Attach TP order px (-1=market)")
    p.add_argument("--sl-trigger", default=None, help="Attach stop-loss trigger")
    p.add_argument("--sl-ord", default=None, help="Attach SL order px (-1=market)")
    _add_live(p)
    p.set_defaults(func=cmd_order_place)

    p = order_sub.add_parser("cancel", help="Cancel order")
    p.add_argument("--inst-id", required=True)
    p.add_argument("--ord-id", default=None)
    p.add_argument("--cl-ord-id", default=None)
    _add_live(p)
    p.set_defaults(func=cmd_order_cancel)

    p = order_sub.add_parser("amend", help="Amend size/price")
    p.add_argument("--inst-id", required=True)
    p.add_argument("--ord-id", default=None)
    p.add_argument("--cl-ord-id", default=None)
    p.add_argument("--new-sz", default=None)
    p.add_argument("--new-px", default=None)
    _add_live(p)
    p.set_defaults(func=cmd_order_amend)

    p = order_sub.add_parser("get", help="Get order")
    p.add_argument("--inst-id", required=True)
    p.add_argument("--ord-id", default=None)
    p.add_argument("--cl-ord-id", default=None)
    p.set_defaults(func=cmd_order_get)

    p = sub.add_parser("orders", help="List pending (default) or history orders")
    p.add_argument("--inst-type", default=None)
    p.add_argument("--inst-id", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--history", action="store_true")
    p.set_defaults(func=cmd_orders)

    p = sub.add_parser("fills", help="List fills")
    p.add_argument("--inst-type", default=None)
    p.add_argument("--inst-id", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_fills)

    # algo group
    algo = sub.add_parser("algo", help="Algo orders (TP/SL/OCO/trigger/…)")
    algo_sub = algo.add_subparsers(dest="algo_cmd", required=True)

    p = algo_sub.add_parser("place", help="Generic place algo")
    _add_inst_side_sz(p)
    p.add_argument(
        "--ord-type",
        required=True,
        choices=["conditional", "oco", "trigger", "move_order_stop", "iceberg", "twap"],
    )
    p.add_argument("--reduce-only", action="store_true", default=None)
    p.add_argument("--tp-trigger", default=None)
    p.add_argument("--tp-ord", default=None)
    p.add_argument("--sl-trigger", default=None)
    p.add_argument("--sl-ord", default=None)
    p.add_argument("--trigger-px", default=None)
    p.add_argument("--order-px", default=None)
    p.add_argument("--callback-ratio", default=None)
    p.add_argument("--callback-spread", default=None)
    p.add_argument("--active-px", default=None)
    p.add_argument("--px-var", default=None)
    p.add_argument("--px-spread", default=None)
    p.add_argument("--sz-limit", default=None)
    p.add_argument("--px-limit", default=None)
    p.add_argument("--time-interval", default=None)
    _add_live(p)
    p.set_defaults(func=cmd_algo_place)

    p = algo_sub.add_parser("sl", help="Place stop-loss (conditional)")
    _add_inst_side_sz(p)
    p.add_argument("--trigger-px", required=True)
    p.add_argument("--ord-px", default="-1", help="-1 = market")
    p.add_argument("--no-reduce-only", action="store_true")
    _add_live(p)
    p.set_defaults(func=cmd_algo_sl)

    p = algo_sub.add_parser("tp", help="Place take-profit (conditional)")
    _add_inst_side_sz(p)
    p.add_argument("--trigger-px", required=True)
    p.add_argument("--ord-px", default="-1")
    p.add_argument("--no-reduce-only", action="store_true")
    _add_live(p)
    p.set_defaults(func=cmd_algo_tp)

    p = algo_sub.add_parser("oco", help="Place OCO TP+SL")
    _add_inst_side_sz(p)
    p.add_argument("--tp-trigger", required=True)
    p.add_argument("--sl-trigger", required=True)
    p.add_argument("--tp-ord", default="-1")
    p.add_argument("--sl-ord", default="-1")
    p.add_argument("--no-reduce-only", action="store_true")
    _add_live(p)
    p.set_defaults(func=cmd_algo_oco)

    p = algo_sub.add_parser("cancel", help="Cancel algo order")
    p.add_argument("--inst-id", required=True)
    p.add_argument("--algo-id", required=True)
    _add_live(p)
    p.set_defaults(func=cmd_algo_cancel)

    p = sub.add_parser("algos", help="List pending/history algo orders")
    p.add_argument(
        "--ord-type",
        required=True,
        choices=["conditional", "oco", "trigger", "move_order_stop", "iceberg", "twap"],
    )
    p.add_argument("--inst-type", default=None)
    p.add_argument("--inst-id", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--history", action="store_true")
    p.set_defaults(func=cmd_algos)

    p = sub.add_parser("http-docs", help="Print endpoint map")
    p.set_defaults(func=cmd_http_docs)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (OkxError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
