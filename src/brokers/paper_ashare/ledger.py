"""SQLite ledger: one file per named paper account."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT NOT NULL,
  cash REAL NOT NULL,
  initial_cash REAL NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS position_lots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  qty INTEGER NOT NULL,
  cost_price REAL NOT NULL,
  buy_date TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  order_type TEXT NOT NULL,
  qty INTEGER NOT NULL,
  limit_price REAL,
  filled_qty INTEGER NOT NULL DEFAULT 0,
  filled_price REAL,
  status TEXT NOT NULL,
  reasoning TEXT NOT NULL,
  reject_reason TEXT,
  fees_total REAL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  qty INTEGER NOT NULL,
  price REAL NOT NULL,
  commission REAL NOT NULL,
  stamp_duty REAL NOT NULL,
  transfer_fee REAL NOT NULL,
  fees_total REAL NOT NULL,
  ts TEXT NOT NULL,
  FOREIGN KEY(order_id) REFERENCES orders(id)
);

CREATE INDEX IF NOT EXISTS idx_lots_symbol ON position_lots(symbol);
CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_shanghai() -> date:
    # A-share session date: use Asia/Shanghai calendar day.
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except Exception:
        return date.today()


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def exists_account(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM account WHERE id = 1").fetchone()
            return row is not None

    def init_account(self, name: str, cash: float, force: bool = False) -> None:
        if cash <= 0:
            raise ValueError("cash must be positive")
        now = utc_now()
        with self.tx() as conn:
            row = conn.execute("SELECT 1 FROM account WHERE id = 1").fetchone()
            if row and not force:
                raise ValueError(f"account already initialized at {self.path} (use --force)")
            if row and force:
                conn.execute("DELETE FROM fills")
                conn.execute("DELETE FROM orders")
                conn.execute("DELETE FROM position_lots")
                conn.execute("DELETE FROM account")
            conn.execute(
                "INSERT INTO account (id, name, cash, initial_cash, created_at, updated_at) "
                "VALUES (1, ?, ?, ?, ?, ?)",
                (name, float(cash), float(cash), now, now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '1')"
            )

    def get_account(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
            if not row:
                raise ValueError(f"account not initialized: {self.path}")
            return dict(row)

    def set_cash(self, conn: sqlite3.Connection, cash: float) -> None:
        conn.execute(
            "UPDATE account SET cash = ?, updated_at = ? WHERE id = 1",
            (cash, utc_now()),
        )

    def list_lots(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM position_lots WHERE symbol = ? ORDER BY id",
                    (symbol,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM position_lots ORDER BY symbol, id"
                ).fetchall()
            return [dict(r) for r in rows]

    def insert_order(self, conn: sqlite3.Connection, order: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO orders (id, symbol, side, order_type, qty, limit_price, filled_qty, "
            "filled_price, status, reasoning, reject_reason, fees_total, created_at, updated_at) "
            "VALUES (:id, :symbol, :side, :order_type, :qty, :limit_price, :filled_qty, "
            ":filled_price, :status, :reasoning, :reject_reason, :fees_total, :created_at, :updated_at)",
            order,
        )

    def update_order(self, conn: sqlite3.Connection, order_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields = {**fields, "updated_at": utc_now()}
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        fields["id"] = order_id
        conn.execute(f"UPDATE orders SET {assignments} WHERE id = :id", fields)

    def insert_fill(self, conn: sqlite3.Connection, fill: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO fills (order_id, symbol, side, qty, price, commission, stamp_duty, "
            "transfer_fee, fees_total, ts) VALUES (:order_id, :symbol, :side, :qty, :price, "
            ":commission, :stamp_duty, :transfer_fee, :fees_total, :ts)",
            fill,
        )

    def insert_lot(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        qty: int,
        cost_price: float,
        buy_date: str,
    ) -> None:
        conn.execute(
            "INSERT INTO position_lots (symbol, qty, cost_price, buy_date, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (symbol, qty, cost_price, buy_date, utc_now()),
        )

    def consume_lots_fifo(
        self, conn: sqlite3.Connection, symbol: str, qty: int, today: date
    ) -> list[dict[str, Any]]:
        """Remove sellable lots FIFO. Raises ValueError if insufficient available."""
        rows = conn.execute(
            "SELECT * FROM position_lots WHERE symbol = ? ORDER BY id",
            (symbol,),
        ).fetchall()
        available = 0
        sellable: list[sqlite3.Row] = []
        for row in rows:
            buy_date = date.fromisoformat(row["buy_date"])
            if buy_date < today:
                available += int(row["qty"])
                sellable.append(row)
        if available < qty:
            raise ValueError(f"insufficient sellable qty for {symbol}: need {qty}, available {available}")

        remaining = qty
        consumed: list[dict[str, Any]] = []
        for row in sellable:
            if remaining <= 0:
                break
            lot_qty = int(row["qty"])
            take = min(lot_qty, remaining)
            consumed.append(
                {
                    "lot_id": row["id"],
                    "qty": take,
                    "cost_price": float(row["cost_price"]),
                    "buy_date": row["buy_date"],
                }
            )
            if take == lot_qty:
                conn.execute("DELETE FROM position_lots WHERE id = ?", (row["id"],))
            else:
                conn.execute(
                    "UPDATE position_lots SET qty = ? WHERE id = ?",
                    (lot_qty - take, row["id"]),
                )
            remaining -= take
        return consumed

    def list_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_fills(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fills ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
