"""
order_executor.py - Ejecucion atomica de pares de ordenes con reconciliacion de fills.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from brokers.base_broker import BaseBroker, OrderResult, OrderSide, OrderSettlement, OrderStatus
from core.cash_flow_manager import CashFlowManager
from core.database import Database
from core.position_manager import PositionManager
from core.risk_manager import RiskManager
from core.state import BotState
from utils.config import get_config
from utils.fees_calculator import OperationFees
from utils.logger import get_logger
from utils.tick_size import adjust_price_to_tick

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    instrument: str
    buy_order: Optional[OrderResult] = None
    sell_order: Optional[OrderResult] = None
    net_profit: Optional[float] = None
    gross_profit: Optional[float] = None
    fees: Optional[OperationFees] = None
    error_message: str = ""
    rolled_back: bool = False


class OrderExecutor:
    def __init__(
        self,
        broker: BaseBroker,
        state: BotState,
        risk_manager: RiskManager,
        cash_flow_manager: CashFlowManager,
        position_manager: PositionManager,
        db: Database,
    ):
        self._broker = broker
        self._state = state
        self._risk = risk_manager
        self._cash_flow = cash_flow_manager
        self._position_manager = position_manager
        self._db = db
        self._config = get_config().trading
        self._validation_timeout = max(1, int(self._config.validation_timeout_seconds))

    def execute_arbitrage(
        self,
        instrument: str,
        ci_price: float,
        h24_price: float,
        quantity: float,
        expected_net_profit: float,
        fees: OperationFees,
    ) -> ExecutionResult:
        buy_limit = self._prepare_limit_price(ci_price, OrderSide.BUY, instrument, OrderSettlement.CI)
        sell_limit = self._prepare_limit_price(h24_price, OrderSide.SELL, instrument, OrderSettlement.H24)

        logger.info(
            f"Iniciando arbitraje {instrument} | "
            f"Compra CI: ${buy_limit:,.2f} | Venta 24hs: ${sell_limit:,.2f} | "
            f"Qty: {quantity:.2f} | Ganancia esperada: ${expected_net_profit:,.2f}"
        )

        self._state.start_operation(instrument)
        buy_amount = buy_limit * quantity
        try:
            return self._execute_with_reconciliation(
                instrument=instrument,
                buy_price=buy_limit,
                sell_price=sell_limit,
                quantity=quantity,
                buy_amount=buy_amount,
                fees=fees,
            )
        finally:
            self._state.end_operation()

    def _prepare_limit_price(self, price: float, side: str, instrument: str, settlement: str) -> float:
        adjusted = adjust_price_to_tick(price, side)
        if abs(adjusted - float(price)) > 1e-9:
            logger.info(
                f"Ajuste tick {instrument} {settlement} {side}: {price:.6f} -> {adjusted:.6f}"
            )
        return max(adjusted, 0.01)

    def _wait_order_final_state(self, sent_order: OrderResult, fallback_instrument: str) -> OrderResult:
        order = sent_order
        current_status = str(order.status or "").lower()
        if current_status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            return order

        deadline = time.time() + self._validation_timeout
        while time.time() < deadline:
            status = self._broker.get_order_status(order.order_id)
            if status is not None:
                if not status.instrument:
                    status.instrument = fallback_instrument
                order = status
                current_status = str(order.status or "").lower()
                if current_status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                    break
            time.sleep(0.5)

        return order

    def _execute_with_reconciliation(
        self,
        instrument: str,
        buy_price: float,
        sell_price: float,
        quantity: float,
        buy_amount: float,
        fees: OperationFees,
    ) -> ExecutionResult:
        try:
            self._cash_flow.on_buy_ci_executed(instrument, buy_amount)
        except ValueError as e:
            logger.error(f"No se pudo bloquear el capital: {e}")
            return ExecutionResult(success=False, instrument=instrument, error_message=str(e))

        buy_sent = self._broker.send_order(
            instrument=instrument,
            side=OrderSide.BUY,
            settlement=OrderSettlement.CI,
            quantity=quantity,
            price=buy_price,
        )
        logger.info(f"Orden BUY enviada {instrument} CI qty={quantity:.2f} @ ${buy_price:,.2f}")
        if not buy_sent.success:
            self._state.rollback_blocked_cash(buy_amount)
            return ExecutionResult(
                success=False,
                instrument=instrument,
                buy_order=buy_sent,
                error_message=f"Compra CI fallo: {buy_sent.error_message}",
            )

        buy_final = self._wait_order_final_state(buy_sent, instrument)
        buy_qty = float(buy_final.executed_quantity or 0.0)
        if buy_qty <= 0:
            self._broker.cancel_order(buy_final.order_id)
            self._state.rollback_blocked_cash(buy_amount)
            return ExecutionResult(
                success=False,
                instrument=instrument,
                buy_order=buy_final,
                error_message="Compra CI sin fills confirmados",
            )

        buy_exec_price = float(buy_final.executed_price or buy_price)
        buy_slippage_ok, buy_slippage = self._risk.validate_slippage(buy_price, buy_exec_price)
        if not buy_slippage_ok:
            logger.warning(f"Slippage excesivo en compra ({buy_slippage:.3f}%).")

        self._position_manager.register_fill(
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=buy_qty,
            price=buy_exec_price,
            settlement=OrderSettlement.CI,
        )

        sell_sent = self._broker.send_order(
            instrument=instrument,
            side=OrderSide.SELL,
            settlement=OrderSettlement.H24,
            quantity=buy_qty,
            price=sell_price,
        )
        logger.info(f"Orden SELL enviada {instrument} 24hs qty={buy_qty:.2f} @ ${sell_price:,.2f}")
        if not sell_sent.success:
            return self._handle_sell_failure(instrument, buy_final, buy_qty, buy_exec_price, buy_amount)

        sell_final = self._wait_order_final_state(sell_sent, instrument)
        sell_qty = float(sell_final.executed_quantity or 0.0)
        sell_exec_price = float(sell_final.executed_price or sell_price)

        if sell_qty <= 0:
            return self._handle_sell_failure(instrument, buy_final, buy_qty, buy_exec_price, buy_amount)

        sell_slippage_ok, sell_slippage = self._risk.validate_slippage(sell_price, sell_exec_price)
        if not sell_slippage_ok:
            logger.warning(f"Slippage excesivo en venta ({sell_slippage:.3f}%).")

        if sell_qty < buy_qty:
            logger.warning(
                f"Fill parcial en 24hs {instrument}: vendido {sell_qty:.2f} de {buy_qty:.2f}. Intentando cobertura."
            )
            hedge_qty = buy_qty - sell_qty
            hedge_price = self._prepare_limit_price(buy_exec_price * 0.998, OrderSide.SELL, instrument, OrderSettlement.CI)
            hedge = self._broker.send_order(
                instrument=instrument,
                side=OrderSide.SELL,
                settlement=OrderSettlement.CI,
                quantity=hedge_qty,
                price=hedge_price,
            )
            if hedge.success and float(hedge.executed_quantity or 0.0) > 0:
                self._position_manager.register_fill(
                    instrument=instrument,
                    side=OrderSide.SELL,
                    quantity=float(hedge.executed_quantity),
                    price=float(hedge.executed_price or hedge_price),
                    settlement=OrderSettlement.CI,
                )
                logger.error(f"Cobertura CI aplicada para {instrument} qty={hedge_qty:.2f}")
            else:
                self._risk.set_stop_trading_flag(True, f"Exposicion parcial no cubierta en {instrument}")

        actual_buy_amount = buy_exec_price * buy_qty
        actual_sell_amount = sell_exec_price * sell_qty
        gross_profit = actual_sell_amount - actual_buy_amount
        net_profit = gross_profit - fees.total

        op_id = self._db.insert_operation(
            instrument=instrument,
            ci_price=buy_exec_price,
            h24_price=sell_exec_price,
            quantity=min(buy_qty, sell_qty),
            buy_amount=actual_buy_amount,
            sell_amount=actual_sell_amount,
            gross_profit=gross_profit,
            total_fees=fees.total,
            net_profit=net_profit,
            status="completed" if sell_qty >= buy_qty else "partial",
        )

        self._cash_flow.on_sell_24h_executed(
            instrument=instrument,
            blocked_amount=actual_buy_amount,
            sale_amount=actual_sell_amount,
            operation_id=op_id,
        )
        self._position_manager.register_fill(
            instrument=instrument,
            side=OrderSide.SELL,
            quantity=sell_qty,
            price=sell_exec_price,
            settlement=OrderSettlement.H24,
            pnl_impact=net_profit,
        )
        logger.info(
            f"Arbitraje finalizado {instrument} | qty_buy={buy_qty:.2f} qty_sell={sell_qty:.2f} "
            f"| neta=${net_profit:,.2f}"
        )

        return ExecutionResult(
            success=sell_qty > 0,
            instrument=instrument,
            buy_order=buy_final,
            sell_order=sell_final,
            net_profit=net_profit,
            gross_profit=gross_profit,
            fees=fees,
            rolled_back=sell_qty < buy_qty,
            error_message="" if sell_qty >= buy_qty else "Venta parcial; se intento cobertura",
        )

    def _handle_sell_failure(
        self,
        instrument: str,
        buy_order: OrderResult,
        buy_qty: float,
        buy_exec_price: float,
        buy_amount: float,
    ) -> ExecutionResult:
        logger.error(f"Fallo pierna 24hs en {instrument}. Intentando proteger exposicion.")
        if self._broker.cancel_order(buy_order.order_id):
            self._state.rollback_blocked_cash(buy_amount)
            return ExecutionResult(
                success=False,
                instrument=instrument,
                buy_order=buy_order,
                rolled_back=True,
                error_message="Fallo venta 24hs; compra cancelada",
            )

        hedge_price = self._prepare_limit_price(buy_exec_price * 0.998, OrderSide.SELL, instrument, OrderSettlement.CI)
        hedge = self._broker.send_order(
            instrument=instrument,
            side=OrderSide.SELL,
            settlement=OrderSettlement.CI,
            quantity=buy_qty,
            price=hedge_price,
        )

        if hedge.success and float(hedge.executed_quantity or 0.0) > 0:
            sell_amt = float(hedge.executed_price or hedge_price) * float(hedge.executed_quantity)
            pnl = sell_amt - buy_amount
            self._state.rollback_blocked_cash(buy_amount)
            self._position_manager.register_fill(
                instrument=instrument,
                side=OrderSide.SELL,
                quantity=float(hedge.executed_quantity),
                price=float(hedge.executed_price or hedge_price),
                settlement=OrderSettlement.CI,
                pnl_impact=pnl,
            )
            self._db.insert_operation(
                instrument=instrument,
                ci_price=buy_exec_price,
                h24_price=0.0,
                quantity=float(hedge.executed_quantity),
                buy_amount=buy_amount,
                sell_amount=sell_amt,
                gross_profit=pnl,
                total_fees=0.0,
                net_profit=pnl,
                status="hedged",
                notes="Fallo venta 24hs; cierre emergencia CI",
            )
            return ExecutionResult(
                success=False,
                instrument=instrument,
                buy_order=buy_order,
                sell_order=hedge,
                rolled_back=True,
                error_message="Fallo venta 24hs; cobertura CI ejecutada",
            )

        self._risk.set_stop_trading_flag(True, f"Exposicion abierta no cubierta en {instrument}")
        op_id = self._db.insert_operation(
            instrument=instrument,
            ci_price=buy_exec_price,
            h24_price=0.0,
            quantity=buy_qty,
            buy_amount=buy_amount,
            sell_amount=0.0,
            gross_profit=0.0,
            total_fees=0.0,
            net_profit=0.0,
            status="partial",
            notes="Fallo venta 24hs; sin cobertura",
        )
        self._position_manager.add_position(
            instrument=instrument,
            settlement="CI",
            quantity=buy_qty,
            avg_price=buy_exec_price,
            operation_id=op_id,
        )
        return ExecutionResult(
            success=False,
            instrument=instrument,
            buy_order=buy_order,
            rolled_back=False,
            error_message="Fallo venta 24hs; posicion abierta",
        )
