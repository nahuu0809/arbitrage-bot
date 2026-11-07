"""
ci_vs_24h.py - Estrategia de arbitraje entre plazos CI y 24hs.
"""

from __future__ import annotations

from typing import Optional

from brokers.base_broker import BaseBroker
from core.position_manager import PositionManager
from core.risk_manager import RiskManager
from core.state import BotState
from strategies.base_strategy import BaseStrategy, Opportunity
from utils.config import get_config
from utils.fees_calculator import OperationFees, calculate_max_quantity, calculate_net_profit
from utils.logger import get_logger

logger = get_logger(__name__)


class CIvs24hStrategy(BaseStrategy):
    def __init__(
        self,
        broker: BaseBroker,
        state: BotState,
        position_manager: PositionManager,
    ):
        super().__init__(broker, state)
        self._position_manager = position_manager
        self._risk = RiskManager(state)
        self._config = get_config()

    @property
    def name(self) -> str:
        return "CI vs 24hs Arbitrage"

    def _is_supported_instrument(self, instrument: str) -> bool:
        supported = {t.upper() for t in self._config.instruments.byma_local_tickers}
        return instrument.upper() in supported

    def find_opportunity(self, instrument: str) -> Optional[Opportunity]:
        if not self._config.arbitraje.enabled:
            return None
        if not self._is_supported_instrument(instrument):
            return None

        quote_ci = self._broker.get_quote(instrument, "CI")
        quote_24h = self._broker.get_quote(instrument, "24hs")
        if not quote_ci or not quote_24h:
            logger.debug(f"{instrument}: no se pudo obtener cotizacion")
            return None

        buy_price = float(quote_ci.ask)
        sell_price = float(quote_24h.bid)
        if buy_price <= 0 or sell_price <= 0:
            return None
        if sell_price <= buy_price:
            return None

        tna = ((sell_price / buy_price) - 1.0) * 365.0
        if tna < float(self._config.arbitraje.tasa_minima):
            logger.debug(
                f"{instrument}: TNA insuficiente {tna:.4f} < {self._config.arbitraje.tasa_minima:.4f}"
            )
            return None

        available_capital = self._state.available_cash
        quantity = calculate_max_quantity(
            available_capital,
            self._config.trading.max_capital_per_operation_percent,
            buy_price,
        )
        if quantity <= 0:
            return None

        current_position = self._position_manager.get_net_position(instrument)
        risk_ok, risk_reason = self._risk.approve_exposure(
            instrument=instrument,
            current_position=current_position,
            delta=quantity,
        )
        if not risk_ok:
            logger.warning(f"{instrument}: arbitraje bloqueado por riesgo: {risk_reason}")
            return None

        gross_profit, net_profit, fees = calculate_net_profit(buy_price, sell_price, quantity)
        if net_profit <= 0:
            return None
        if net_profit < float(self._config.trading.min_net_profit):
            return None

        if not self._validate_book_liquidity(instrument):
            return None

        logger.info(
            f"Oportunidad arbitraje {instrument} | CI={buy_price:.2f} | 24hs={sell_price:.2f} | "
            f"TNA={tna:.4f} | Qty={quantity:.2f} | Neta=${net_profit:,.2f}"
        )
        return Opportunity(
            instrument=instrument,
            buy_price=buy_price,
            sell_price=sell_price,
            quantity=quantity,
            expected_net_profit=net_profit,
            expected_gross_profit=gross_profit,
            fees_total=fees.total,
            details={
                "fees": fees,
                "tna": tna,
                "available_capital": available_capital,
            },
        )

    def _validate_book_liquidity(self, instrument: str) -> bool:
        n_levels = self._config.trading.order_book_positions_to_check
        min_depth = self._config.trading.min_book_depth_ars

        book_ci = self._broker.get_order_book(instrument, "CI")
        if not book_ci:
            return False
        if book_ci.get_ask_depth_ars(n_levels) < min_depth:
            return False

        book_24h = self._broker.get_order_book(instrument, "24hs")
        if not book_24h:
            return False
        if book_24h.get_bid_depth_ars(n_levels) < min_depth:
            return False

        return True

    def scan_all(self) -> Optional[Opportunity]:
        tickers = [t.upper() for t in self._config.instruments.byma_local_tickers]
        priority_tickers = self._position_manager.get_priority_instruments()
        ordered = priority_tickers + [t for t in tickers if t not in priority_tickers]

        best_opportunity: Optional[Opportunity] = None
        for ticker in ordered:
            try:
                opp = self.find_opportunity(ticker)
                if opp and (
                    best_opportunity is None
                    or opp.expected_net_profit > best_opportunity.expected_net_profit
                ):
                    best_opportunity = opp
            except Exception as e:
                logger.error(f"Error analizando {ticker}: {e}", exc_info=True)

        return best_opportunity

    def get_fees_for_opportunity(self, opportunity: Opportunity) -> OperationFees:
        return opportunity.details["fees"]
