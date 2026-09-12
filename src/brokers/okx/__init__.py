"""OKX v5 broker — production-shaped service + thin CLI.

Import path for quant / scripts::

    from brokers.okx import OkxService, OrderRequest, stop_loss, oco_tp_sl

CLI::

    uv run okx status
    uv run okx order place --inst-id BTC-USDT --side buy --sz 0.001 --td-mode cash
    uv run okx algo sl --inst-id BTC-USDT --side sell --sz 0.001 --trigger-px 50000
"""

from .service import OkxService
from .types import (
    AlgoOrderRequest,
    AttachTpSl,
    OrderRequest,
    oco_tp_sl,
    stop_loss,
    take_profit,
)

__all__ = [
    "OkxService",
    "OrderRequest",
    "AlgoOrderRequest",
    "AttachTpSl",
    "stop_loss",
    "take_profit",
    "oco_tp_sl",
]
