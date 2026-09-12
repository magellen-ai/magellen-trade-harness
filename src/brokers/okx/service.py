"""OKX trading service — reusable API for CLI, quant scripts, and agents.

This is intentionally richer than demo brokers (paper_ashare / clawstreet):
ordinary orders, amend/cancel, fills, positions, and algo legs (stop-loss,
take-profit, OCO, trigger, trailing, iceberg, TWAP).

Default environment is **demo** (``simulated=True`` / ``OKX_SIMULATED=1``).
Mutating calls still default to dry-run unless ``dry_run=False`` / CLI ``--live``.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from .client import OkxRestClient
from .secrets import env_simulated_default, load_secrets_into_environ
from .types import (
    AlgoOrderRequest,
    OrderRequest,
    Side,
    TdMode,
    oco_tp_sl,
    stop_loss,
    take_profit,
)


def _data_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _first(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    items = _data_list(payload)
    return items[0] if items else None


def _new_cl_ord_id(prefix: str = "mth") -> str:
    # OKX: up to 32 alphanumerics.
    raw = uuid.uuid4().hex
    return f"{prefix}{raw}"[:32]


class OkxService:
    def __init__(
        self,
        client: Optional[OkxRestClient] = None,
        *,
        default_dry_run: bool = True,
    ):
        self.client = client or OkxRestClient.from_env()
        self.default_dry_run = default_dry_run

    @classmethod
    def from_env(
        cls,
        *,
        simulated: Optional[bool] = None,
        default_dry_run: bool = True,
        timeout: float = 20.0,
        require_creds: bool = True,
    ) -> "OkxService":
        load_secrets_into_environ(require_creds=require_creds)
        flag = env_simulated_default() if simulated is None else simulated
        client = OkxRestClient.from_env(
            simulated=flag,
            timeout=timeout,
            require_creds=require_creds,
        )
        return cls(client, default_dry_run=default_dry_run)

    @property
    def simulated(self) -> bool:
        return self.client.simulated

    def _dry(self, dry_run: Optional[bool]) -> bool:
        return self.default_dry_run if dry_run is None else dry_run

    # --- account / positions -------------------------------------------------

    def account_config(self) -> dict[str, Any]:
        return self.client.get("/api/v5/account/config")

    def balance(self, ccy: Optional[str] = None) -> dict[str, Any]:
        params = {"ccy": ccy} if ccy else None
        return self.client.get("/api/v5/account/balance", params=params)

    def positions(
        self,
        *,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        payload = self.client.get(
            "/api/v5/account/positions",
            params={"instType": inst_type, "instId": inst_id},
        )
        return _data_list(payload)

    def status(self) -> dict[str, Any]:
        """Compact account snapshot for humans / agents."""
        cfg = _first(self.account_config()) or {}
        bal = _first(self.balance()) or {}
        details = bal.get("details") if isinstance(bal.get("details"), list) else []
        return {
            "simulated": self.simulated,
            "acct_lv": cfg.get("acctLv"),
            "pos_mode": cfg.get("posMode"),
            "total_eq": bal.get("totalEq"),
            "iso_eq": bal.get("isoEq"),
            "adj_eq": bal.get("adjEq"),
            "details": details,
            "raw_config": cfg,
        }

    # --- market (public) -----------------------------------------------------

    def ticker(self, inst_id: str) -> dict[str, Any]:
        payload = self.client.get(
            "/api/v5/market/ticker",
            params={"instId": inst_id},
            auth=False,
        )
        row = _first(payload)
        if row is None:
            raise ValueError(f"No ticker for {inst_id}")
        return row

    def candles(
        self,
        inst_id: str,
        *,
        bar: str = "15m",
        limit: int = 100,
        after: Optional[str] = None,
        before: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """GET /api/v5/market/candles — newest first from OKX; we return oldest→newest.

        Each row: ts, open, high, low, close, vol, vol_ccy, vol_ccy_quote, confirm.
        """
        payload = self.client.get(
            "/api/v5/market/candles",
            params={
                "instId": inst_id,
                "bar": bar,
                "limit": str(limit),
                "after": after,
                "before": before,
            },
            auth=False,
        )
        rows: list[dict[str, Any]] = []
        for item in payload.get("data") or []:
            if not isinstance(item, list) or len(item) < 5:
                continue
            rows.append(
                {
                    "ts": item[0],
                    "open": item[1],
                    "high": item[2],
                    "low": item[3],
                    "close": item[4],
                    "vol": item[5] if len(item) > 5 else None,
                    "vol_ccy": item[6] if len(item) > 6 else None,
                    "vol_ccy_quote": item[7] if len(item) > 7 else None,
                    "confirm": item[8] if len(item) > 8 else None,
                }
            )
        rows.reverse()  # chronological
        return rows

    def instruments(
        self,
        inst_type: str = "SPOT",
        *,
        inst_id: Optional[str] = None,
        uly: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        payload = self.client.get(
            "/api/v5/public/instruments",
            params={"instType": inst_type, "instId": inst_id, "uly": uly},
            auth=False,
        )
        return _data_list(payload)

    # --- ordinary orders -----------------------------------------------------

    def place_order(
        self,
        order: OrderRequest,
        *,
        dry_run: Optional[bool] = None,
        ensure_cl_ord_id: bool = True,
    ) -> dict[str, Any]:
        payload_body = order.to_payload()
        if ensure_cl_ord_id and not payload_body.get("clOrdId"):
            payload_body["clOrdId"] = _new_cl_ord_id()

        if self._dry(dry_run):
            return {
                "success": True,
                "dry_run": True,
                "simulated": self.simulated,
                "endpoint": "POST /api/v5/trade/order",
                "payload": payload_body,
                "message": "Dry-run: order not sent to OKX",
            }

        raw = self.client.post("/api/v5/trade/order", body=payload_body)
        row = _first(raw) or {}
        if str(row.get("sCode", "0")) not in {"0", ""}:
            return {
                "success": False,
                "dry_run": False,
                "simulated": self.simulated,
                "order": row,
                "raw": raw,
            }
        return {
            "success": True,
            "dry_run": False,
            "simulated": self.simulated,
            "ord_id": row.get("ordId"),
            "cl_ord_id": row.get("clOrdId") or payload_body.get("clOrdId"),
            "order": row,
            "raw": raw,
        }

    def cancel_order(
        self,
        *,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
        dry_run: Optional[bool] = None,
    ) -> dict[str, Any]:
        if not ord_id and not cl_ord_id:
            raise ValueError("cancel_order requires ord_id or cl_ord_id")
        body: dict[str, Any] = {"instId": inst_id}
        if ord_id:
            body["ordId"] = ord_id
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        if self._dry(dry_run):
            return {
                "success": True,
                "dry_run": True,
                "endpoint": "POST /api/v5/trade/cancel-order",
                "payload": body,
            }
        raw = self.client.post("/api/v5/trade/cancel-order", body=body)
        return {"success": True, "dry_run": False, "order": _first(raw), "raw": raw}

    def amend_order(
        self,
        *,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
        new_sz: Optional[str] = None,
        new_px: Optional[str] = None,
        dry_run: Optional[bool] = None,
    ) -> dict[str, Any]:
        if not ord_id and not cl_ord_id:
            raise ValueError("amend_order requires ord_id or cl_ord_id")
        if new_sz is None and new_px is None:
            raise ValueError("amend_order requires new_sz and/or new_px")
        body: dict[str, Any] = {"instId": inst_id}
        if ord_id:
            body["ordId"] = ord_id
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        if new_sz is not None:
            body["newSz"] = str(new_sz)
        if new_px is not None:
            body["newPx"] = str(new_px)
        if self._dry(dry_run):
            return {
                "success": True,
                "dry_run": True,
                "endpoint": "POST /api/v5/trade/amend-order",
                "payload": body,
            }
        raw = self.client.post("/api/v5/trade/amend-order", body=body)
        return {"success": True, "dry_run": False, "order": _first(raw), "raw": raw}

    def get_order(
        self,
        *,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if not ord_id and not cl_ord_id:
            raise ValueError("get_order requires ord_id or cl_ord_id")
        payload = self.client.get(
            "/api/v5/trade/order",
            params={"instId": inst_id, "ordId": ord_id, "clOrdId": cl_ord_id},
        )
        row = _first(payload)
        if row is None:
            raise ValueError("Order not found")
        return row

    def list_orders_pending(
        self,
        *,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        ord_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        payload = self.client.get(
            "/api/v5/trade/orders-pending",
            params={
                "instType": inst_type,
                "instId": inst_id,
                "ordType": ord_type,
                "limit": str(limit),
            },
        )
        return _data_list(payload)

    def list_orders_history(
        self,
        *,
        inst_type: str = "SPOT",
        inst_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        payload = self.client.get(
            "/api/v5/trade/orders-history",
            params={
                "instType": inst_type,
                "instId": inst_id,
                "state": state,
                "limit": str(limit),
            },
        )
        return _data_list(payload)

    def list_fills(
        self,
        *,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        payload = self.client.get(
            "/api/v5/trade/fills",
            params={
                "instType": inst_type,
                "instId": inst_id,
                "limit": str(limit),
            },
        )
        return _data_list(payload)

    # --- algo orders (TP/SL/OCO/trigger/…) -----------------------------------

    def place_algo(
        self,
        algo: AlgoOrderRequest,
        *,
        dry_run: Optional[bool] = None,
        ensure_cl_ord_id: bool = True,
    ) -> dict[str, Any]:
        body = algo.to_payload()
        if ensure_cl_ord_id and not body.get("clOrdId"):
            body["clOrdId"] = _new_cl_ord_id("algo")

        if self._dry(dry_run):
            return {
                "success": True,
                "dry_run": True,
                "simulated": self.simulated,
                "endpoint": "POST /api/v5/trade/order-algo",
                "payload": body,
                "message": "Dry-run: algo order not sent to OKX",
            }

        raw = self.client.post("/api/v5/trade/order-algo", body=body)
        row = _first(raw) or {}
        if str(row.get("sCode", "0")) not in {"0", ""}:
            return {
                "success": False,
                "dry_run": False,
                "simulated": self.simulated,
                "algo": row,
                "raw": raw,
            }
        return {
            "success": True,
            "dry_run": False,
            "simulated": self.simulated,
            "algo_id": row.get("algoId"),
            "cl_ord_id": row.get("clOrdId") or body.get("clOrdId"),
            "algo": row,
            "raw": raw,
        }

    def place_stop_loss(
        self,
        *,
        inst_id: str,
        side: Side,
        sz: str,
        trigger_px: str,
        td_mode: TdMode = "cash",
        ord_px: str = "-1",
        reduce_only: Optional[bool] = True,
        pos_side: Optional[str] = None,
        dry_run: Optional[bool] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.place_algo(
            stop_loss(
                inst_id=inst_id,
                side=side,
                sz=sz,
                trigger_px=trigger_px,
                td_mode=td_mode,
                ord_px=ord_px,
                reduce_only=reduce_only,
                pos_side=pos_side,  # type: ignore[arg-type]
                **kwargs,
            ),
            dry_run=dry_run,
        )

    def place_take_profit(
        self,
        *,
        inst_id: str,
        side: Side,
        sz: str,
        trigger_px: str,
        td_mode: TdMode = "cash",
        ord_px: str = "-1",
        reduce_only: Optional[bool] = True,
        pos_side: Optional[str] = None,
        dry_run: Optional[bool] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.place_algo(
            take_profit(
                inst_id=inst_id,
                side=side,
                sz=sz,
                trigger_px=trigger_px,
                td_mode=td_mode,
                ord_px=ord_px,
                reduce_only=reduce_only,
                pos_side=pos_side,  # type: ignore[arg-type]
                **kwargs,
            ),
            dry_run=dry_run,
        )

    def place_oco_tp_sl(
        self,
        *,
        inst_id: str,
        side: Side,
        sz: str,
        tp_trigger_px: str,
        sl_trigger_px: str,
        td_mode: TdMode = "cash",
        tp_ord_px: str = "-1",
        sl_ord_px: str = "-1",
        reduce_only: Optional[bool] = True,
        pos_side: Optional[str] = None,
        dry_run: Optional[bool] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.place_algo(
            oco_tp_sl(
                inst_id=inst_id,
                side=side,
                sz=sz,
                tp_trigger_px=tp_trigger_px,
                sl_trigger_px=sl_trigger_px,
                td_mode=td_mode,
                tp_ord_px=tp_ord_px,
                sl_ord_px=sl_ord_px,
                reduce_only=reduce_only,
                pos_side=pos_side,  # type: ignore[arg-type]
                **kwargs,
            ),
            dry_run=dry_run,
        )

    def cancel_algo(
        self,
        *,
        inst_id: str,
        algo_id: str,
        dry_run: Optional[bool] = None,
    ) -> dict[str, Any]:
        body = [{"instId": inst_id, "algoId": algo_id}]
        if self._dry(dry_run):
            return {
                "success": True,
                "dry_run": True,
                "endpoint": "POST /api/v5/trade/cancel-algos",
                "payload": body,
            }
        raw = self.client.post("/api/v5/trade/cancel-algos", body=body)
        return {"success": True, "dry_run": False, "algo": _first(raw), "raw": raw}

    def list_algos_pending(
        self,
        *,
        ord_type: str,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        payload = self.client.get(
            "/api/v5/trade/orders-algo-pending",
            params={
                "ordType": ord_type,
                "instType": inst_type,
                "instId": inst_id,
                "limit": str(limit),
            },
        )
        return _data_list(payload)

    def list_algos_history(
        self,
        *,
        ord_type: str,
        state: Optional[str] = None,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        payload = self.client.get(
            "/api/v5/trade/orders-algo-history",
            params={
                "ordType": ord_type,
                "state": state,
                "instType": inst_type,
                "instId": inst_id,
                "limit": str(limit),
            },
        )
        return _data_list(payload)
