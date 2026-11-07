from __future__ import annotations

from core.state import BotState
from utils.config import get_config
from utils.logger import get_logger

logger = get_logger(__name__)


class RiskManager:
    def __init__(self, state: BotState):
        self._state = state
        self._cfg = get_config().risk
        self._stop_trading_flag = bool(self._cfg.stop_trading_flag)

    def set_stop_trading_flag(self, value: bool, reason: str = "") -> None:
        self._stop_trading_flag = bool(value)
        self._cfg.stop_trading_flag = self._stop_trading_flag
        if self._stop_trading_flag:
            logger.error(f"Trading bloqueado por riesgo: {reason or 'stop_trading_flag activo'}")
        else:
            logger.info("Trading reanudado por riesgo")

    def check_daily_limit(self) -> bool:
        limit_ars = abs(float(getattr(self._cfg, "max_loss_diario", 0.0)))
        if limit_ars <= 0:
            limit_ars = abs(float(getattr(self._cfg, "max_daily_loss_ars", 0.0)))
        if limit_ars <= 0:
            pct = abs(float(getattr(self._cfg, "max_daily_loss_percent", 0.0)))
            if pct > 0:
                limit_ars = self._state.initial_capital * (pct / 100.0)

        exceeded = self._state.daily_profit <= -limit_ars if limit_ars > 0 else False
        if exceeded:
            self.set_stop_trading_flag(
                True,
                f"max_loss_diario alcanzado ({self._state.daily_profit:,.2f} <= -{limit_ars:,.2f})",
            )
        return exceeded

    def is_safe_to_trade(self) -> tuple[bool, str]:
        self._stop_trading_flag = bool(self._stop_trading_flag or self._cfg.stop_trading_flag)
        if self._state.status == "error":
            return False, "Bot en estado de error"
        if self._stop_trading_flag:
            return False, "Trading bloqueado por riesgo"
        if self.check_daily_limit():
            return False, "Limite de perdida diaria alcanzado"
        return True, "OK"

    def validate_slippage(self, expected_price: float, executed_price: float) -> tuple[bool, float]:
        if expected_price <= 0:
            return False, 100.0
        slippage_pct = abs((executed_price - expected_price) / expected_price) * 100.0
        return slippage_pct <= float(self._cfg.max_slippage_percent), slippage_pct

    def validate_position_limit(
        self,
        instrument: str,
        new_abs_position: float,
        max_position_override: float | None = None,
    ) -> tuple[bool, str]:
        max_pos = (
            abs(float(max_position_override))
            if max_position_override is not None
            else abs(float(getattr(self._cfg, "max_position_por_ticker", 0.0)))
        )
        if max_pos <= 0:
            return True, "OK"
        if abs(float(new_abs_position)) > max_pos:
            return False, (
                f"Limite por ticker excedido {instrument}: "
                f"{new_abs_position:.2f} > {max_pos:.2f}"
            )
        return True, "OK"

    def approve_exposure(
        self,
        instrument: str,
        current_position: float,
        delta: float,
        max_position_override: float | None = None,
    ) -> tuple[bool, str]:
        safe, reason = self.is_safe_to_trade()
        if not safe:
            return False, reason
        return self.validate_position_limit(
            instrument=instrument,
            new_abs_position=current_position + delta,
            max_position_override=max_position_override,
        )
