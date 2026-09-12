"""Typed intents for OKX v5 trading (spot + derivatives + algo).

These are the reusable service-layer contracts. Quant programs should build
these objects (or call OkxService helpers) rather than hand-rolling REST bodies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional


TdMode = Literal["cash", "cross", "isolated"]
Side = Literal["buy", "sell"]
OrdType = Literal["market", "limit", "post_only", "fok", "ioc"]
AlgoOrdType = Literal[
    "conditional",
    "oco",
    "trigger",
    "move_order_stop",
    "iceberg",
    "twap",
]
PxType = Literal["last", "index", "mark"]
PosSide = Literal["long", "short", "net"]


def _omit_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _s(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


@dataclass(frozen=True)
class AttachTpSl:
    """Optional TP/SL attached to a regular place-order (attachAlgoOrds).

    Prefer AlgoOrderRequest for standalone stop / OCO. Use this when the
    exchange supports attaching protective legs to the entry fill.
    """

    tp_trigger_px: Optional[str] = None
    tp_ord_px: Optional[str] = None  # "-1" = market
    tp_trigger_px_type: PxType = "last"
    sl_trigger_px: Optional[str] = None
    sl_ord_px: Optional[str] = None  # "-1" = market
    sl_trigger_px_type: PxType = "last"

    def to_attach_algo_ord(self) -> dict[str, Any]:
        body = _omit_none(
            {
                "tpTriggerPx": _s(self.tp_trigger_px),
                "tpOrdPx": _s(self.tp_ord_px),
                "tpTriggerPxType": self.tp_trigger_px_type if self.tp_trigger_px else None,
                "slTriggerPx": _s(self.sl_trigger_px),
                "slOrdPx": _s(self.sl_ord_px),
                "slTriggerPxType": self.sl_trigger_px_type if self.sl_trigger_px else None,
            }
        )
        if not body:
            raise ValueError("AttachTpSl needs at least one of TP or SL fields")
        return body


@dataclass(frozen=True)
class OrderRequest:
    """POST /api/v5/trade/order"""

    inst_id: str
    side: Side
    sz: str
    td_mode: TdMode = "cash"
    ord_type: OrdType = "market"
    px: Optional[str] = None
    cl_ord_id: Optional[str] = None
    tag: Optional[str] = None
    tgt_ccy: Optional[Literal["base_ccy", "quote_ccy"]] = None
    reduce_only: Optional[bool] = None
    pos_side: Optional[PosSide] = None
    ban_amend: Optional[bool] = None
    attach_tp_sl: Optional[AttachTpSl] = None
    # Escape hatch for newer OKX fields without waiting on typed models.
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        if self.ord_type != "market" and self.px is None:
            raise ValueError(f"px required for ord_type={self.ord_type}")
        body = _omit_none(
            {
                "instId": self.inst_id,
                "tdMode": self.td_mode,
                "side": self.side,
                "ordType": self.ord_type,
                "sz": _s(self.sz),
                "px": _s(self.px),
                "clOrdId": self.cl_ord_id,
                "tag": self.tag,
                "tgtCcy": self.tgt_ccy,
                "reduceOnly": self.reduce_only,
                "posSide": self.pos_side,
                "banAmend": self.ban_amend,
            }
        )
        if self.attach_tp_sl is not None:
            body["attachAlgoOrds"] = [self.attach_tp_sl.to_attach_algo_ord()]
        if self.extra:
            body.update(self.extra)
        return body

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass(frozen=True)
class AlgoOrderRequest:
    """POST /api/v5/trade/order-algo

    Covers conditional / oco (TP+SL) / trigger / trailing / iceberg / twap.
    Pass only the fields needed for the chosen ``ord_type``.
    """

    inst_id: str
    side: Side
    sz: str
    ord_type: AlgoOrdType
    td_mode: TdMode = "cash"
    cl_ord_id: Optional[str] = None
    tag: Optional[str] = None
    tgt_ccy: Optional[Literal["base_ccy", "quote_ccy"]] = None
    reduce_only: Optional[bool] = None
    pos_side: Optional[PosSide] = None

    # conditional / oco — take profit
    tp_trigger_px: Optional[str] = None
    tp_ord_px: Optional[str] = None
    tp_trigger_px_type: Optional[PxType] = None

    # conditional / oco — stop loss
    sl_trigger_px: Optional[str] = None
    sl_ord_px: Optional[str] = None
    sl_trigger_px_type: Optional[PxType] = None

    # trigger
    trigger_px: Optional[str] = None
    order_px: Optional[str] = None
    trigger_px_type: Optional[PxType] = None

    # trailing (move_order_stop)
    callback_ratio: Optional[str] = None
    callback_spread: Optional[str] = None
    active_px: Optional[str] = None

    # iceberg / twap
    px_var: Optional[str] = None
    px_spread: Optional[str] = None
    sz_limit: Optional[str] = None
    px_limit: Optional[str] = None
    time_interval: Optional[str] = None

    extra: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.ord_type in {"conditional", "oco"}:
            has_tp = self.tp_trigger_px is not None
            has_sl = self.sl_trigger_px is not None
            if self.ord_type == "oco" and not (has_tp and has_sl):
                raise ValueError("oco requires both TP and SL trigger prices")
            if not has_tp and not has_sl and self.trigger_px is None:
                raise ValueError("conditional/oco needs TP, SL, and/or trigger fields")
            if has_tp and self.tp_ord_px is None:
                raise ValueError("tp_ord_px required when tp_trigger_px is set (use -1 for market)")
            if has_sl and self.sl_ord_px is None:
                raise ValueError("sl_ord_px required when sl_trigger_px is set (use -1 for market)")
        elif self.ord_type == "trigger":
            if self.trigger_px is None or self.order_px is None:
                raise ValueError("trigger requires trigger_px and order_px (-1 = market)")
        elif self.ord_type == "move_order_stop":
            if self.callback_ratio is None and self.callback_spread is None:
                raise ValueError("move_order_stop needs callback_ratio or callback_spread")
        elif self.ord_type in {"iceberg", "twap"}:
            if self.sz_limit is None or self.px_limit is None:
                raise ValueError(f"{self.ord_type} requires sz_limit and px_limit")
            if self.px_var is None and self.px_spread is None:
                raise ValueError(f"{self.ord_type} requires px_var or px_spread")
            if self.ord_type == "twap" and self.time_interval is None:
                raise ValueError("twap requires time_interval")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        body = _omit_none(
            {
                "instId": self.inst_id,
                "tdMode": self.td_mode,
                "side": self.side,
                "ordType": self.ord_type,
                "sz": _s(self.sz),
                "clOrdId": self.cl_ord_id,
                "tag": self.tag,
                "tgtCcy": self.tgt_ccy,
                "reduceOnly": self.reduce_only,
                "posSide": self.pos_side,
                "tpTriggerPx": _s(self.tp_trigger_px),
                "tpOrdPx": _s(self.tp_ord_px),
                "tpTriggerPxType": self.tp_trigger_px_type,
                "slTriggerPx": _s(self.sl_trigger_px),
                "slOrdPx": _s(self.sl_ord_px),
                "slTriggerPxType": self.sl_trigger_px_type,
                "triggerPx": _s(self.trigger_px),
                "orderPx": _s(self.order_px),
                "triggerPxType": self.trigger_px_type,
                "callbackRatio": _s(self.callback_ratio),
                "callbackSpread": _s(self.callback_spread),
                "activePx": _s(self.active_px),
                "pxVar": _s(self.px_var),
                "pxSpread": _s(self.px_spread),
                "szLimit": _s(self.sz_limit),
                "pxLimit": _s(self.px_limit),
                "timeInterval": _s(self.time_interval),
            }
        )
        if self.extra:
            body.update(self.extra)
        return body


def stop_loss(
    *,
    inst_id: str,
    side: Side,
    sz: str,
    trigger_px: str,
    td_mode: TdMode = "cash",
    ord_px: str = "-1",
    trigger_px_type: PxType = "last",
    reduce_only: Optional[bool] = True,
    pos_side: Optional[PosSide] = None,
    cl_ord_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> AlgoOrderRequest:
    """Convenience: one-way stop-loss (conditional)."""
    return AlgoOrderRequest(
        inst_id=inst_id,
        side=side,
        sz=str(sz),
        ord_type="conditional",
        td_mode=td_mode,
        sl_trigger_px=str(trigger_px),
        sl_ord_px=str(ord_px),
        sl_trigger_px_type=trigger_px_type,
        reduce_only=reduce_only,
        pos_side=pos_side,
        cl_ord_id=cl_ord_id,
        tag=tag,
    )


def take_profit(
    *,
    inst_id: str,
    side: Side,
    sz: str,
    trigger_px: str,
    td_mode: TdMode = "cash",
    ord_px: str = "-1",
    trigger_px_type: PxType = "last",
    reduce_only: Optional[bool] = True,
    pos_side: Optional[PosSide] = None,
    cl_ord_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> AlgoOrderRequest:
    """Convenience: one-way take-profit (conditional)."""
    return AlgoOrderRequest(
        inst_id=inst_id,
        side=side,
        sz=str(sz),
        ord_type="conditional",
        td_mode=td_mode,
        tp_trigger_px=str(trigger_px),
        tp_ord_px=str(ord_px),
        tp_trigger_px_type=trigger_px_type,
        reduce_only=reduce_only,
        pos_side=pos_side,
        cl_ord_id=cl_ord_id,
        tag=tag,
    )


def oco_tp_sl(
    *,
    inst_id: str,
    side: Side,
    sz: str,
    tp_trigger_px: str,
    sl_trigger_px: str,
    td_mode: TdMode = "cash",
    tp_ord_px: str = "-1",
    sl_ord_px: str = "-1",
    tp_trigger_px_type: PxType = "last",
    sl_trigger_px_type: PxType = "last",
    reduce_only: Optional[bool] = True,
    pos_side: Optional[PosSide] = None,
    cl_ord_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> AlgoOrderRequest:
    """Convenience: OCO take-profit + stop-loss."""
    return AlgoOrderRequest(
        inst_id=inst_id,
        side=side,
        sz=str(sz),
        ord_type="oco",
        td_mode=td_mode,
        tp_trigger_px=str(tp_trigger_px),
        tp_ord_px=str(tp_ord_px),
        tp_trigger_px_type=tp_trigger_px_type,
        sl_trigger_px=str(sl_trigger_px),
        sl_ord_px=str(sl_ord_px),
        sl_trigger_px_type=sl_trigger_px_type,
        reduce_only=reduce_only,
        pos_side=pos_side,
        cl_ord_id=cl_ord_id,
        tag=tag,
    )
