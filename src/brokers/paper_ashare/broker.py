"""Paper A-share broker: market orders, T+1 lots, fees, multi-account files."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from .fees import DEFAULT_FEES, FeeSchedule, calc_fees
from .ledger import Ledger, today_shanghai, utc_now
from .paths import ledger_path
from .quotes import CascadingQuoteFeed, QuoteFeed, normalize_symbol


LOT_SIZE = 100
DEFAULT_SLIPPAGE_BPS = 5.0  # 5 bp vs last for market fills


class PaperAshareBroker:
    def __init__(
        self,
        account: str = "default",
        quote_feed: Optional[QuoteFeed] = None,
        fees: FeeSchedule = DEFAULT_FEES,
        slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
        ledger: Optional[Ledger] = None,
    ):
        self.account_name = account
        self.ledger = ledger or Ledger(ledger_path(account))
        self.quotes = quote_feed or CascadingQuoteFeed()
        self.fees = fees
        self.slippage_bps = slippage_bps

    @staticmethod
    def list_account_files() -> list[str]:
        from .paths import ledger_dir

        return sorted(p.stem for p in ledger_dir().glob("*.sqlite"))

    def init_account(self, cash: float = 1_000_000.0, force: bool = False) -> dict[str, Any]:
        self.ledger.init_account(self.account_name, cash=cash, force=force)
        return self.status()

    def status(self) -> dict[str, Any]:
        acct = self.ledger.get_account()
        positions = self.portfolio()["positions"]
        market_value = sum(float(p.get("market_value") or 0) for p in positions)
        cash = float(acct["cash"])
        equity = cash + market_value
        initial = float(acct["initial_cash"])
        ret_pct = ((equity / initial) - 1.0) * 100.0 if initial else 0.0
        return {
            "account": acct["name"],
            "ledger": str(self.ledger.path),
            "cash": round(cash, 2),
            "market_value": round(market_value, 2),
            "equity": round(equity, 2),
            "initial_cash": initial,
            "total_return_pct": round(ret_pct, 4),
            "positions_count": len(positions),
        }

    def portfolio(self) -> dict[str, Any]:
        acct = self.ledger.get_account()
        lots = self.ledger.list_lots()
        today = today_shanghai()
        by_symbol: dict[str, dict[str, Any]] = {}
        for lot in lots:
            sym = lot["symbol"]
            bucket = by_symbol.setdefault(
                sym,
                {"symbol": sym, "qty": 0, "available": 0, "cost_value": 0.0},
            )
            qty = int(lot["qty"])
            bucket["qty"] += qty
            bucket["cost_value"] += qty * float(lot["cost_price"])
            buy_date = lot["buy_date"]
            from datetime import date

            if date.fromisoformat(buy_date) < today:
                bucket["available"] += qty

        positions: list[dict[str, Any]] = []
        for sym, bucket in sorted(by_symbol.items()):
            qty = int(bucket["qty"])
            avg_cost = bucket["cost_value"] / qty if qty else 0.0
            last = None
            market_value = None
            unrealized = None
            try:
                q = self.quotes.get_quote(sym)
                last = q.last
                market_value = last * qty
                unrealized = market_value - bucket["cost_value"]
            except Exception as e:
                bucket["quote_error"] = str(e)
            positions.append(
                {
                    "symbol": sym,
                    "qty": qty,
                    "available": int(bucket["available"]),
                    "avg_cost": round(avg_cost, 4),
                    "last": last,
                    "market_value": round(market_value, 2) if market_value is not None else None,
                    "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
                }
            )
        return {
            "cash": round(float(acct["cash"]), 2),
            "positions": positions,
        }

    def list_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.ledger.list_orders(limit=limit)

    def list_fills(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.ledger.list_fills(limit=limit)

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        reasoning: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Submit order. Business rejects return status=rejected (no exception)."""
        sym = normalize_symbol(symbol)
        side = side.lower().strip()
        order_type = order_type.lower().strip()
        order_id = str(uuid.uuid4())
        now = utc_now()
        base = {
            "id": order_id,
            "symbol": sym,
            "side": side,
            "order_type": order_type,
            "qty": int(qty),
            "limit_price": limit_price,
            "filled_qty": 0,
            "filled_price": None,
            "status": "pending",
            "reasoning": reasoning,
            "reject_reason": None,
            "fees_total": None,
            "created_at": now,
            "updated_at": now,
        }

        reject = self._precheck(sym, side, qty, order_type, limit_price, reasoning)
        if reject:
            base["status"] = "rejected"
            base["reject_reason"] = reject
            if not dry_run:
                with self.ledger.tx() as conn:
                    self.ledger.insert_order(conn, base)
            return {"success": False, "dry_run": dry_run, "order": base}

        if dry_run:
            try:
                preview = self._preview_fill(sym, side, int(qty), order_type, limit_price)
            except Exception as e:
                base["status"] = "rejected"
                base["reject_reason"] = str(e)
                return {"success": False, "dry_run": True, "order": base}
            base["status"] = "dry_run"
            base["filled_qty"] = int(qty)
            base["filled_price"] = preview["price"]
            base["fees_total"] = preview["fees"]["total"]
            return {
                "success": True,
                "dry_run": True,
                "order": base,
                "preview": preview,
                "message": "Dry-run: not written to ledger (pass --live)",
            }

        try:
            return self._execute(base, order_type, limit_price)
        except Exception as e:
            base["status"] = "rejected"
            base["reject_reason"] = str(e)
            with self.ledger.tx() as conn:
                self.ledger.insert_order(conn, base)
            return {"success": False, "dry_run": False, "order": base}

    def _precheck(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        limit_price: Optional[float],
        reasoning: str,
    ) -> Optional[str]:
        if side not in ("buy", "sell"):
            return f"side must be buy|sell, got {side!r} (short/cover not supported)"
        if order_type != "market":
            return "only market orders supported in MVP (limit later)"
        if limit_price is not None:
            return "limit_price not supported for market MVP"
        if qty <= 0:
            return "qty must be positive"
        if qty % LOT_SIZE != 0:
            return f"qty must be multiple of {LOT_SIZE}, got {qty}"
        if not reasoning or not reasoning.strip():
            return "reasoning required"
        if not self.ledger.exists_account():
            return f"account not initialized: {self.ledger.path}"
        # Soft limit-up check using prev_close when available (advisory; not a hard board).
        return None

    def _preview_fill(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        limit_price: Optional[float],
    ) -> dict[str, Any]:
        quote = self.quotes.get_quote(symbol)
        slip = self.slippage_bps / 10_000.0
        if side == "buy":
            price = quote.last * (1.0 + slip)
        else:
            price = quote.last * (1.0 - slip)
        # Optional: reject buys above +10% / sells below -10% vs prev (main board heuristic).
        if quote.prev_close and quote.prev_close > 0:
            up = quote.prev_close * 1.10
            down = quote.prev_close * 0.90
            if side == "buy" and quote.last >= up * 0.999:
                raise ValueError(f"likely limit-up ({quote.last} vs prev {quote.prev_close}); skip buy")
            if side == "sell" and quote.last <= down * 1.001:
                raise ValueError(f"likely limit-down ({quote.last} vs prev {quote.prev_close}); skip sell")
        price = round(price, 2)
        notional = price * qty
        fees = calc_fees(side, notional, self.fees)
        acct = self.ledger.get_account()
        cash = float(acct["cash"])
        if side == "buy":
            need = notional + fees["total"]
            if cash < need:
                raise ValueError(f"insufficient cash: need {need:.2f}, have {cash:.2f}")
        else:
            today = today_shanghai()
            # Check availability without mutating.
            available = 0
            from datetime import date

            for lot in self.ledger.list_lots(symbol):
                if date.fromisoformat(lot["buy_date"]) < today:
                    available += int(lot["qty"])
            if available < qty:
                raise ValueError(f"insufficient sellable qty: need {qty}, available {available}")
        return {
            "quote": {
                "last": quote.last,
                "prev_close": quote.prev_close,
                "source": quote.source,
                "asof_ms": quote.asof_ms,
            },
            "price": price,
            "notional": round(notional, 2),
            "fees": fees,
            "order_type": order_type,
            "limit_price": limit_price,
        }

    def _execute(
        self,
        base: dict[str, Any],
        order_type: str,
        limit_price: Optional[float],
    ) -> dict[str, Any]:
        sym = base["symbol"]
        side = base["side"]
        qty = int(base["qty"])
        preview = self._preview_fill(sym, side, qty, order_type, limit_price)
        price = float(preview["price"])
        fees = preview["fees"]
        today = today_shanghai().isoformat()
        now = utc_now()

        with self.ledger.tx() as conn:
            acct = dict(conn.execute("SELECT * FROM account WHERE id = 1").fetchone())
            cash = float(acct["cash"])
            if side == "buy":
                cash -= preview["notional"] + fees["total"]
                if cash < -1e-6:
                    raise ValueError("insufficient cash at commit")
                self.ledger.insert_lot(conn, sym, qty, price, today)
            else:
                self.ledger.consume_lots_fifo(conn, sym, qty, today_shanghai())
                cash += preview["notional"] - fees["total"]
            self.ledger.set_cash(conn, cash)

            order = {
                **base,
                "filled_qty": qty,
                "filled_price": price,
                "status": "filled",
                "fees_total": fees["total"],
                "updated_at": now,
            }
            self.ledger.insert_order(conn, order)
            self.ledger.insert_fill(
                conn,
                {
                    "order_id": order["id"],
                    "symbol": sym,
                    "side": side,
                    "qty": qty,
                    "price": price,
                    "commission": fees["commission"],
                    "stamp_duty": fees["stamp_duty"],
                    "transfer_fee": fees["transfer_fee"],
                    "fees_total": fees["total"],
                    "ts": now,
                },
            )

        return {
            "success": True,
            "dry_run": False,
            "order": order,
            "fill_preview": preview,
            "account": self.status(),
        }
