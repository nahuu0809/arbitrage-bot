from __future__ import annotations

from datetime import date, timedelta

from core.state import BotState
from utils.logger import get_logger

logger = get_logger(__name__)


class CashFlowManager:
    def __init__(self, state: BotState, db):
        self._state = state
        self._db = db

    def can_operate_today(self) -> tuple[bool, str]:
        if self._state.available_cash <= 0:
            return False, "Sin capital disponible"
        return True, "OK"

    def process_due_settlements(self) -> int:
        due = self._db.get_due_settlements(date.today().isoformat())
        processed = 0
        for item in due:
            blocked_amount = float(item.get("blocked_amount", 0.0))
            sale_amount = float(item.get("sale_amount", 0.0))
            self._state.settle_operation(blocked_amount, sale_amount)
            self._db.mark_settlement_processed(int(item["id"]))
            processed += 1
        if processed > 0:
            logger.info(f"Liquidaciones 24hs acreditadas: {processed}")
        return processed

    def on_buy_ci_executed(self, instrument: str, buy_amount: float) -> None:
        _ = instrument
        self._state.lock_cash(buy_amount)

    def on_sell_24h_executed(
        self,
        instrument: str,
        blocked_amount: float,
        sale_amount: float,
        operation_id: int,
    ) -> None:
        due_date = self._next_business_day(date.today()).isoformat()
        self._db.add_pending_settlement(
            instrument=instrument,
            blocked_amount=blocked_amount,
            sale_amount=sale_amount,
            operation_id=operation_id,
            due_date=due_date,
        )
        logger.info(
            f"Settlement pendiente registrado {instrument} op={operation_id} due={due_date}"
        )

    def _next_business_day(self, current: date) -> date:
        d = current + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d
