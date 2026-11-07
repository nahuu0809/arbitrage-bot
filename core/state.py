from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from threading import Lock


class BotStatus:
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class BotState:
    initial_capital: float

    def __post_init__(self) -> None:
        self.available_cash = float(self.initial_capital)
        self.blocked_cash = 0.0
        self.daily_profit = 0.0
        self.operations_count = 0
        self.status = BotStatus.STOPPED
        self.current_instrument: str | None = None
        self.last_trade_date = date.today().isoformat()
        self._max_drawdown = 0.0
        self._peak_equity = float(self.initial_capital)
        self._positions_by_ticker: dict[str, float] = {}
        self._pnl_by_ticker: dict[str, float] = {}
        self._lock = Lock()

    @property
    def total_capital(self) -> float:
        return self.available_cash + self.blocked_cash

    @property
    def max_drawdown(self) -> float:
        return self._max_drawdown

    def set_status(self, status: str) -> None:
        with self._lock:
            self.status = status

    def start_operation(self, instrument: str) -> None:
        with self._lock:
            self.current_instrument = instrument

    def end_operation(self) -> None:
        with self._lock:
            self.current_instrument = None

    def rollback_blocked_cash(self, amount: float) -> None:
        with self._lock:
            amount = max(0.0, float(amount))
            released = min(amount, self.blocked_cash)
            self.blocked_cash -= released
            self.available_cash += released

    def lock_cash(self, amount: float) -> None:
        with self._lock:
            if amount > self.available_cash:
                raise ValueError("Capital insuficiente para bloquear")
            self.available_cash -= amount
            self.blocked_cash += amount

    def settle_operation(self, blocked_amount: float, sale_amount: float) -> None:
        with self._lock:
            release = min(max(0.0, blocked_amount), self.blocked_cash)
            self.blocked_cash -= release
            self.available_cash += max(0.0, sale_amount)
            self.daily_profit += max(0.0, sale_amount) - release
            self.operations_count += 1
            self._update_drawdown()

    def _update_drawdown(self) -> None:
        equity = self.total_capital
        if equity > self._peak_equity:
            self._peak_equity = equity
        if self._peak_equity <= 0:
            self._max_drawdown = 0.0
            return
        dd = (self._peak_equity - equity) / self._peak_equity
        if dd > self._max_drawdown:
            self._max_drawdown = dd

    def get_ticker_position(self, instrument: str) -> float:
        with self._lock:
            return float(self._positions_by_ticker.get(instrument, 0.0))

    def update_ticker_position(self, instrument: str, delta: float) -> float:
        with self._lock:
            new_value = float(self._positions_by_ticker.get(instrument, 0.0)) + float(delta)
            self._positions_by_ticker[instrument] = new_value
            return new_value

    def get_ticker_pnl(self, instrument: str) -> float:
        with self._lock:
            return float(self._pnl_by_ticker.get(instrument, 0.0))

    def add_ticker_pnl(self, instrument: str, pnl: float) -> float:
        with self._lock:
            current = float(self._pnl_by_ticker.get(instrument, 0.0))
            updated = current + float(pnl)
            self._pnl_by_ticker[instrument] = updated
            return updated
