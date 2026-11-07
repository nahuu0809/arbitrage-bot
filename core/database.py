from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any


class Database:
    def __init__(self, db_path: str = "bot_data.sqlite3") -> None:
        self._path = Path(db_path)
        self._lock = Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_state (
                  trade_date TEXT PRIMARY KEY,
                  payload TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  created_at TEXT NOT NULL,
                  payload TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  instrument TEXT NOT NULL,
                  settlement TEXT NOT NULL,
                  quantity REAL NOT NULL,
                  avg_price REAL NOT NULL,
                  operation_id INTEGER NOT NULL,
                  open INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_settlements (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  instrument TEXT NOT NULL,
                  blocked_amount REAL NOT NULL,
                  sale_amount REAL NOT NULL,
                  operation_id INTEGER NOT NULL,
                  due_date TEXT NOT NULL,
                  processed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.commit()

    def _to_payload(self, kwargs: dict[str, Any]) -> str:
        import json

        return json.dumps(kwargs, ensure_ascii=False)

    def _from_payload(self, payload: str) -> dict[str, Any]:
        import json

        return json.loads(payload)

    def upsert_daily_state(self, **kwargs) -> None:
        trade_date = kwargs["trade_date"]
        payload = self._to_payload(kwargs)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO daily_state(trade_date, payload)
                VALUES(?, ?)
                ON CONFLICT(trade_date) DO UPDATE SET payload=excluded.payload
                """,
                (trade_date, payload),
            )
            self._conn.commit()

    def get_daily_state(self, trade_date: str):
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM daily_state WHERE trade_date = ?",
                (trade_date,),
            ).fetchone()
        if not row:
            return None
        return self._from_payload(row["payload"])

    def insert_operation(self, **kwargs) -> int:
        created_at = datetime.now().isoformat()
        payload = self._to_payload(kwargs)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO operations(created_at, payload) VALUES(?, ?)",
                (created_at, payload),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_open_positions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT instrument, settlement, quantity, avg_price, operation_id, open
                FROM positions
                WHERE open = 1
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def add_position(self, **kwargs) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO positions(instrument, settlement, quantity, avg_price, operation_id, open)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    kwargs.get("instrument", ""),
                    kwargs.get("settlement", ""),
                    float(kwargs.get("quantity", 0.0)),
                    float(kwargs.get("avg_price", 0.0)),
                    int(kwargs.get("operation_id", 0)),
                    1 if kwargs.get("open", True) else 0,
                ),
            )
            self._conn.commit()

    def add_pending_settlement(
        self,
        instrument: str,
        blocked_amount: float,
        sale_amount: float,
        operation_id: int,
        due_date: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO pending_settlements(instrument, blocked_amount, sale_amount, operation_id, due_date, processed)
                VALUES(?, ?, ?, ?, ?, 0)
                """,
                (instrument, float(blocked_amount), float(sale_amount), int(operation_id), due_date),
            )
            self._conn.commit()

    def get_due_settlements(self, upto_date: str | None = None) -> list[dict]:
        cutoff = upto_date or date.today().isoformat()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, instrument, blocked_amount, sale_amount, operation_id, due_date
                FROM pending_settlements
                WHERE processed = 0 AND due_date <= ?
                ORDER BY due_date ASC, id ASC
                """,
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_settlement_processed(self, settlement_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE pending_settlements SET processed = 1 WHERE id = ?",
                (int(settlement_id),),
            )
            self._conn.commit()
