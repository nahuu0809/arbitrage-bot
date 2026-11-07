from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from brokers.base_broker import BaseBroker, OrderSide
from core.position_manager import PositionManager
from core.risk_manager import RiskManager
from core.state import BotState
from strategies.base_strategy import BaseStrategy, Opportunity
from utils.config import get_config
from utils.logger import get_logger
from utils.tick_size import adjust_price_to_tick, get_tick_size

logger = get_logger(__name__)


@dataclass
class ActiveOrder:
    side: str
    order_id: str
    price: float
    quantity: float


class MarketMakingStrategy(BaseStrategy):
    def __init__(
        self,
        broker: BaseBroker,
        state: BotState,
        position_manager: PositionManager,
        risk_manager: RiskManager,
    ):
        super().__init__(broker, state)
        self._config = get_config()
        self._position_manager = position_manager
        self._risk = risk_manager
        self._active_orders: dict[str, ActiveOrder] = {}

    @property
    def name(self) -> str:
        return "Intra-Ticker Market Making"

    def find_opportunity(self, instrument: str) -> Optional[Opportunity]:
        _ = instrument
        return None

    def scan_all(self) -> Optional[Opportunity]:
        mm_cfg = self._config.market_making
        if not mm_cfg.enabled:
            return None

        instrument = mm_cfg.ticker.upper()
        if instrument not in {t.upper() for t in self._config.instruments.byma_local_tickers}:
            logger.warning(f"MM deshabilitado para {instrument}: no esta en byma_local_tickers")
            return None

        settlement = mm_cfg.settlement
        quote = self._broker.get_quote(instrument, settlement)
        if not quote:
            return None

        best_bid = float(quote.bid)
        best_ask = float(quote.ask)
        if best_bid <= 0 or best_ask <= 0:
            return None

        spread = best_ask - best_bid
        if spread < float(mm_cfg.min_spread):
            return None

        net_pos = self._position_manager.get_net_position(instrument)
        max_pos = float(mm_cfg.max_position)
        qty = float(mm_cfg.order_size)

        buy_qty = max(0.0, min(qty, max_pos - net_pos))
        sell_qty = max(0.0, min(qty, max_pos + net_pos))

        buy_price = adjust_price_to_tick(best_bid, OrderSide.BUY)
        sell_price = adjust_price_to_tick(best_ask, OrderSide.SELL)

        self._sync_order(instrument, settlement, OrderSide.BUY, buy_price, buy_qty, max_pos)
        self._sync_order(instrument, settlement, OrderSide.SELL, sell_price, sell_qty, max_pos)
        return None

    def _sync_order(
        self,
        instrument: str,
        settlement: str,
        side: str,
        target_price: float,
        quantity: float,
        max_position: float,
    ) -> None:
        order = self._active_orders.get(side)
        if quantity <= 0:
            if order:
                if self._broker.cancel_order(order.order_id):
                    logger.info(f"Orden cancelada por inventario {side} {instrument} id={order.order_id}")
                self._active_orders.pop(side, None)
            return

        current_pos = self._position_manager.get_net_position(instrument)
        delta = quantity if side == OrderSide.BUY else -quantity
        risk_ok, risk_reason = self._risk.approve_exposure(
            instrument=instrument,
            current_position=current_pos,
            delta=delta,
            max_position_override=max_position,
        )
        if not risk_ok:
            logger.warning(f"MM bloqueado por riesgo {instrument} {side}: {risk_reason}")
            return

        if order:
            tick = get_tick_size(target_price)
            move_ticks = abs(target_price - order.price) / tick if tick > 0 else 0.0
            if move_ticks < float(self._config.market_making.cancel_threshold_ticks):
                return
            if self._broker.cancel_order(order.order_id):
                logger.info(
                    f"Cancel/replace {instrument} {side}: {order.price:.2f} -> {target_price:.2f}"
                )
            self._active_orders.pop(side, None)

        result = self._broker.send_order(
            instrument=instrument,
            side=side,
            settlement=settlement,
            quantity=quantity,
            price=target_price,
        )
        logger.info(
            f"Orden MM enviada {instrument} {settlement} {side} qty={quantity:.2f} limit=${target_price:.2f}"
        )
        if not result.success:
            logger.warning(f"Orden MM rechazada {instrument} {side}: {result.error_message}")
            return

        self._active_orders[side] = ActiveOrder(
            side=side,
            order_id=result.order_id,
            price=target_price,
            quantity=quantity,
        )
        filled_qty = float(result.executed_quantity or 0.0)
        if filled_qty > 0:
            self._position_manager.register_fill(
                instrument=instrument,
                side=side,
                quantity=filled_qty,
                price=float(result.executed_price),
                settlement=settlement,
            )
            logger.info(
                f"Fill MM {instrument} {side} qty={filled_qty:.2f} price=${float(result.executed_price):.2f}"
            )
