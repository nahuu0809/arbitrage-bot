from __future__ import annotations

from core.database import Database
from core.state import BotState
from utils.logger import get_logger

logger = get_logger(__name__)


class PositionManager:
    def __init__(self, state: BotState, db: Database):
        self._state = state
        self._db = db
        self._positions: list[dict] = []

    def load_positions_from_db(self) -> None:
        self._positions = self._db.get_open_positions()
        for pos in self._positions:
            settlement = str(pos.get("settlement", "")).upper()
            if settlement == "CI":
                self._state.update_ticker_position(
                    str(pos.get("instrument", "")),
                    float(pos.get("quantity", 0.0)),
                )

    def get_priority_instruments(self) -> list[str]:
        seen = set()
        ordered = []
        for pos in self._positions:
            instr = pos.get("instrument")
            if instr and instr not in seen:
                seen.add(instr)
                ordered.append(instr)
        return ordered

    def add_position(
        self,
        instrument: str,
        settlement: str,
        quantity: float,
        avg_price: float,
        operation_id: int,
    ) -> None:
        rec = {
            "instrument": instrument,
            "settlement": settlement,
            "quantity": quantity,
            "avg_price": avg_price,
            "operation_id": operation_id,
            "open": True,
        }
        self._positions.append(rec)
        self._db.add_position(**rec)
        if settlement.upper() == "CI":
            self._state.update_ticker_position(instrument, quantity)

    def get_net_position(self, instrument: str) -> float:
        return self._state.get_ticker_position(instrument)

    def can_increase_position(self, instrument: str, delta: float, max_position: float) -> bool:
        return abs(self.get_net_position(instrument) + delta) <= abs(max_position)

    def register_fill(
        self,
        instrument: str,
        side: str,
        quantity: float,
        price: float,
        settlement: str = "CI",
        pnl_impact: float = 0.0,
    ) -> None:
        side_lc = side.lower()
        signed_qty = float(quantity) if side_lc == "buy" else -float(quantity)
        if settlement.upper() == "CI":
            position = self._state.update_ticker_position(instrument, signed_qty)
            logger.info(f"Posicion actual {instrument}: {position:.2f}")
        ticker_pnl = self._state.add_ticker_pnl(instrument, float(pnl_impact))
        logger.info(
            f"PnL por ticker {instrument}: ${ticker_pnl:,.2f} | precio fill=${price:,.2f}"
        )
