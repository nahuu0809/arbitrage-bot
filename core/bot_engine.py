"""
bot_engine.py - Motor principal del bot de trading.

Ejecuta el loop de anÃ¡lisis y ejecuciÃ³n en un QThread separado,
comunicÃ¡ndose con la UI mediante signals/slots (PySide6).

Loop principal:
  1. Verificar que el mercado estÃ© abierto
  2. Procesar liquidaciones pendientes del dÃ­a anterior
  3. Verificar lÃ­mites de riesgo
  4. Verificar que haya capital disponible
  5. Buscar oportunidades (scan_all)
  6. Si hay oportunidad â†’ ejecutar
  7. Verificar cauciÃ³n al cierre del dÃ­a
  8. Esperar interval y repetir
"""

import time
from datetime import date, datetime
from typing import Optional

from PySide6.QtCore import QThread, Signal

from brokers.base_broker import BaseBroker
from core.cash_flow_manager import CashFlowManager
from core.database import Database
from core.order_executor import OrderExecutor
from core.position_manager import PositionManager
from core.risk_manager import RiskManager
from core.state import BotState, BotStatus
from strategies.ci_vs_24h import CIvs24hStrategy
from strategies.market_making import MarketMakingStrategy
from utils.config import get_config
from utils.logger import get_logger
from utils.market_calendar import is_market_open, is_near_market_close, time_to_market_open

logger = get_logger(__name__)


class BotEngine(QThread):
    """
    QThread que ejecuta el loop de trading.

    Signals emitidos hacia la UI:
      - status_changed(str):         Nuevo estado del bot
      - capital_updated(float, float, float): (disponible, bloqueado, p&l_dia)
      - operation_executed(dict):    Datos de una operaciÃ³n completada
      - error_occurred(str):         Mensaje de error crÃ­tico
      - market_closed():             El mercado cerrÃ³ o no estÃ¡ abierto
    """

    # â”€â”€ Signals para comunicaciÃ³n con la UI â”€â”€
    status_changed = Signal(str)
    capital_updated = Signal(float, float, float)   # disponible, bloqueado, pnl_dia
    operation_executed = Signal(dict)
    error_occurred = Signal(str)
    market_closed = Signal()
    log_message = Signal(str, str, str)             # time, level, message

    def __init__(
        self,
        broker: BaseBroker,
        db: Database,
        state: BotState,
    ):
        super().__init__()
        self._broker = broker
        self._db = db
        self._state = state
        self._config = get_config()

        # Componentes del core
        self._risk_manager = RiskManager(state)
        self._cash_flow = CashFlowManager(state, db)
        self._position_manager = PositionManager(state, db)
        self._order_executor = OrderExecutor(
            broker=broker,
            state=state,
            risk_manager=self._risk_manager,
            cash_flow_manager=self._cash_flow,
            position_manager=self._position_manager,
            db=db,
        )

        # Estrategias activas
        self._strategy = CIvs24hStrategy(broker, state, self._position_manager)
        self._mm_strategy: MarketMakingStrategy | None = None
        if self._config.market_making.enabled:
            self._mm_strategy = MarketMakingStrategy(
                broker=broker,
                state=state,
                position_manager=self._position_manager,
                risk_manager=self._risk_manager,
            )

        # Control interno
        self._running = False
        self._pause_requested = False
        self._last_daily_init_date: Optional[date] = None
        self._snapshot_counter = 0  # Para guardar snapshot cada N ciclos

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Ciclo de vida del QThread
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def run(self) -> None:
        """Entry point del QThread. Ejecuta el loop principal."""
        logger.info("ðŸ¤– Bot engine iniciado")
        self._running = True
        self._state.set_status(BotStatus.RUNNING)
        self.status_changed.emit(BotStatus.RUNNING)

        try:
            self._connect_broker()
            self._restore_state()
            self._main_loop()
        except Exception as e:
            logger.critical(f"Error crÃ­tico en bot engine: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self._state.set_status(BotStatus.ERROR)
            self.status_changed.emit(BotStatus.ERROR)
        finally:
            self._cleanup()

    def stop(self) -> None:
        """Solicita la detenciÃ³n del bot. Thread-safe."""
        logger.info("Deteniendo bot engine...")
        self._running = False
        self._state.set_status(BotStatus.STOPPED)
        self.status_changed.emit(BotStatus.STOPPED)

    def pause(self) -> None:
        """Pausa temporalmente el bot (no ejecuta Ã³rdenes pero sigue el loop)."""
        self._pause_requested = True
        self._state.set_status(BotStatus.PAUSED)
        self.status_changed.emit(BotStatus.PAUSED)
        logger.info("Bot en pausa")

    def resume(self) -> None:
        """Reanuda el bot desde pausa."""
        self._pause_requested = False
        self._state.set_status(BotStatus.RUNNING)
        self.status_changed.emit(BotStatus.RUNNING)
        logger.info("Bot reanudado")

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Loop principal
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _main_loop(self) -> None:
        """Loop principal de trading."""
        polling_interval = self._config.trading.polling_interval_seconds

        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Error en tick del loop: {e}", exc_info=True)
                # No detener el bot por errores no crÃ­ticos, solo loggear

            # Actualizar UI con estado de capital
            self.capital_updated.emit(
                self._state.available_cash,
                self._state.blocked_cash,
                self._state.daily_profit,
            )

            # Snapshot de DB cada 60 ciclos (~5 min con interval=5s)
            self._snapshot_counter += 1
            if self._snapshot_counter >= 60:
                self._save_state_snapshot()
                self._snapshot_counter = 0

            time.sleep(polling_interval)

    def _tick(self) -> None:
        """Un ciclo de anÃ¡lisis y (potencial) ejecuciÃ³n."""

        # â”€â”€ Verificar si el mercado estÃ¡ abierto â”€â”€
        if not is_market_open():
            delta = time_to_market_open()
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes = remainder // 60
            logger.debug(f"Mercado cerrado. PrÃ³xima apertura en {hours}h {minutes}m")
            self.market_closed.emit()
            return

        # â”€â”€ InicializaciÃ³n diaria (una vez por dÃ­a) â”€â”€
        today = date.today()
        if self._last_daily_init_date != today:
            self._daily_init(today)

        # â”€â”€ Pausa solicitada â”€â”€
        if self._pause_requested:
            return

        # â”€â”€ Verificar lÃ­mite de pÃ©rdida diaria â”€â”€
        if self._risk_manager.check_daily_limit():
            logger.warning("LÃ­mite de pÃ©rdida diaria alcanzado. Deteniendo bot.")
            self.stop()
            return

        # â”€â”€ Verificar capital disponible â”€â”€
        can_operate, reason = self._cash_flow.can_operate_today()
        if not can_operate:
            logger.debug(f"No se puede operar: {reason}")
            # Verificar cauciÃ³n al cierre si corresponde
            if is_near_market_close():
                self._evaluate_caucion()
            return

        # â”€â”€ Verificar si es seguro tradear â”€â”€
        safe, reason = self._risk_manager.is_safe_to_trade()
        if not safe:
            logger.debug(f"No es seguro operar: {reason}")
            return

        # â”€â”€ Buscar oportunidades â”€â”€
        if self._mm_strategy is not None:
            self._mm_strategy.scan_all()

        if not self._config.arbitraje.enabled:
            if is_near_market_close():
                self._evaluate_caucion()
            return

        opportunity = self._strategy.scan_all()

        if opportunity is None:
            # Sin oportunidades: evaluar cauciÃ³n si estamos cerca del cierre
            if is_near_market_close():
                self._evaluate_caucion()
            return

        # â”€â”€ Ejecutar arbitraje â”€â”€
        fees = self._strategy.get_fees_for_opportunity(opportunity)
        result = self._order_executor.execute_arbitrage(
            instrument=opportunity.instrument,
            ci_price=opportunity.buy_price,
            h24_price=opportunity.sell_price,
            quantity=opportunity.quantity,
            expected_net_profit=opportunity.expected_net_profit,
            fees=fees,
        )

        if result.success:
            logger.info(f"âœ… OperaciÃ³n completada: {result.instrument} | Ganancia: ${result.net_profit:,.2f}")
            self.operation_executed.emit({
                "instrument": result.instrument,
                "net_profit": result.net_profit,
                "gross_profit": result.gross_profit,
                "buy_price": result.buy_order.executed_price,
                "sell_price": result.sell_order.executed_price,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        else:
            logger.error(f"âŒ OperaciÃ³n fallida: {result.error_message}")
            if result.rolled_back:
                logger.info("Rollback exitoso: sin pÃ©rdida de capital")

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # InicializaciÃ³n diaria
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _daily_init(self, today: date) -> None:
        """Tareas de inicio de dÃ­a hÃ¡bil."""
        logger.info(f"ðŸ“… Inicio del dÃ­a de trading: {today.strftime('%d/%m/%Y')}")
        self._last_daily_init_date = today

        # Procesar liquidaciones pendientes del dÃ­a anterior
        settled = self._cash_flow.process_due_settlements()
        if settled > 0:
            logger.info(f"Liquidaciones procesadas: {settled}")

        # Guardar estado inicial del dÃ­a en DB
        self._db.upsert_daily_state(
            trade_date=today.isoformat(),
            initial_capital=self._state.initial_capital,
            current_capital=self._state.total_capital,
            daily_profit=self._state.daily_profit,
            operations_count=self._state.operations_count,
            max_drawdown=0.0,
            status="active",
        )

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # CauciÃ³n colocadora al cierre
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _evaluate_caucion(self) -> None:
        """Evalua si corresponde registrar una caucion colocadora al cierre."""
        risk_config = self._config.risk
        if not risk_config.enable_caucion_at_close:
            return

        available = self._state.available_cash
        if available <= 0:
            return

        min_amount = max(1000.0, float(self._config.trading.min_book_depth_ars))
        if available < min_amount:
            logger.info(
                f"Caucion omitida: capital insuficiente (${available:,.2f} < ${min_amount:,.2f})"
            )
            return

        annual_rate = float(risk_config.caucion_min_rate_percent) / 100.0
        expected_daily_interest = available * annual_rate / 365.0
        logger.info(
            f"Evaluando caucion al cierre | Capital: ${available:,.2f} | "
            f"Tasa minima: {risk_config.caucion_min_rate_percent}% | "
            f"Interes diario estimado: ${expected_daily_interest:,.2f}"
        )
        self._db.insert_operation(
            instrument="CAUCION",
            ci_price=0.0,
            h24_price=0.0,
            quantity=0.0,
            buy_amount=available,
            sell_amount=available + expected_daily_interest,
            gross_profit=expected_daily_interest,
            total_fees=0.0,
            net_profit=expected_daily_interest,
            status="caucion_evaluated",
            notes=(
                f"Evaluacion automatica cierre; tasa_min={risk_config.caucion_min_rate_percent}%"
            ),
        )


    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Helpers
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _connect_broker(self) -> None:
        """Conecta con el broker. Lanza excepciÃ³n si falla."""
        logger.info(f"Conectando con broker (modo: {self._config.mode})...")

        if not self._broker.connect():
            raise ConnectionError("No se pudo conectar con el broker PPI")

        logger.info("âœ… ConexiÃ³n con broker establecida")

    def _restore_state(self) -> None:
        """Restaura el estado desde DB si hay datos del dÃ­a actual."""
        today = date.today().isoformat()
        daily_state = self._db.get_daily_state(today)

        if daily_state:
            logger.info("Estado del dÃ­a anterior encontrado. Restaurando...")
            # Restaurar posiciones abiertas
            self._position_manager.load_positions_from_db()

            logger.info(
                f"Estado restaurado | "
                f"Capital: ${daily_state['current_capital']:,.2f} | "
                f"P&L: ${daily_state['daily_profit']:,.2f}"
            )
        else:
            logger.info("Primer inicio del dÃ­a. Estado limpio.")

    def _save_state_snapshot(self) -> None:
        """Guarda un snapshot del estado actual en DB."""
        try:
            self._db.upsert_daily_state(
                trade_date=date.today().isoformat(),
                initial_capital=self._state.initial_capital,
                current_capital=self._state.total_capital,
                daily_profit=self._state.daily_profit,
                operations_count=self._state.operations_count,
                max_drawdown=abs(self._state.max_drawdown),
                status=self._state.status,
            )
        except Exception as e:
            logger.error(f"Error guardando snapshot: {e}")

    def _cleanup(self) -> None:
        """Limpieza al detener el bot."""
        logger.info("Realizando limpieza al detener el bot...")

        # Guardar estado final
        self._save_state_snapshot()

        # Desconectar broker
        try:
            self._broker.disconnect()
        except Exception as e:
            logger.error(f"Error al desconectar broker: {e}")

        self._running = False
        logger.info("ðŸ›‘ Bot engine detenido")
