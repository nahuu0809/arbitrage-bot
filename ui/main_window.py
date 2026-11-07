"""
main_window.py - Ventana principal de la aplicación.

Integra todos los widgets y conecta el BotEngine con la UI.
Gestiona el ciclo de vida del QThread de trading.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget,
)

from brokers.ppi_adapter import PPIAdapter
from core.bot_engine import BotEngine
from core.database import Database
from core.state import BotState
from ui.widgets.controls import ControlsBar
from ui.widgets.log_viewer import LogViewer
from ui.widgets.positions_table import PositionsTable
from ui.widgets.status_panel import StatusPanel
from utils.config import get_config
from utils.logger import LogEmitter, get_logger

logger = get_logger(__name__)

# Ruta a los estilos QSS
STYLES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "styles.qss")


class MainWindow(QMainWindow):
    """Ventana principal del bot de trading."""

    def __init__(self):
        super().__init__()
        self._config = get_config()
        self._engine: BotEngine | None = None

        self._setup_ui()
        self._setup_log_emitter()
        self._load_styles()

        logger.info(f"🤖 Bot de Trading Argentina iniciado | Modo: {self._config.mode.upper()}")

    # ──────────────────────────────────────────
    # Construcción de UI
    # ──────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("Bot de Trading Argentina")
        self.setMinimumSize(800, 600)
        self.resize(1000, 720)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Panel de estado (arriba) ──
        self._status_panel = StatusPanel()
        main_layout.addWidget(self._status_panel)

        # ── Contenido central (logs + posiciones) ──
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setContentsMargins(12, 12, 12, 12)

        self._log_viewer = LogViewer()
        self._positions_table = PositionsTable()

        splitter.addWidget(self._log_viewer)
        splitter.addWidget(self._positions_table)
        splitter.setSizes([400, 200])

        main_layout.addWidget(splitter, stretch=1)

        # ── Barra de controles (abajo) ──
        self._controls = ControlsBar()
        self._controls.start_requested.connect(self._on_start)
        self._controls.pause_requested.connect(self._on_pause)
        self._controls.stop_requested.connect(self._on_stop)
        main_layout.addWidget(self._controls)

        # ── Modo sandbox en título si corresponde ──
        if self._config.is_sandbox:
            self.setWindowTitle("Bot de Trading Argentina [SANDBOX]")

    def _setup_log_emitter(self) -> None:
        """Conecta el sistema de logging con el LogViewer."""
        LogEmitter.instance().register_callback(self._on_log_message)

    def _load_styles(self) -> None:
        """Carga el archivo de estilos QSS."""
        if os.path.exists(STYLES_PATH):
            with open(STYLES_PATH, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # ──────────────────────────────────────────
    # Control del bot
    # ──────────────────────────────────────────

    def _on_start(self) -> None:
        """Inicializa y arranca el BotEngine en un QThread."""
        if self._engine and self._engine.isRunning():
            # Reanudar si está pausado
            self._engine.resume()
            return

        logger.info("Iniciando bot engine...")

        try:
            # Crear componentes
            db = Database()
            state = BotState(initial_capital=self._config.trading.initial_capital)
            broker = PPIAdapter()

            # Crear y conectar el engine
            self._engine = BotEngine(broker=broker, db=db, state=state)

            # Conectar signals del engine → slots de la UI
            self._engine.status_changed.connect(self._on_status_changed)
            self._engine.capital_updated.connect(self._on_capital_updated)
            self._engine.operation_executed.connect(self._on_operation_executed)
            self._engine.error_occurred.connect(self._on_error)
            self._engine.market_closed.connect(self._on_market_closed)
            self._engine.finished.connect(self._on_engine_finished)

            self._engine.start()

        except Exception as e:
            logger.error(f"Error iniciando bot: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo iniciar el bot:\n{e}")
            self._controls.set_running_state(False)

    def _on_pause(self) -> None:
        if self._engine:
            self._engine.pause()

    def _on_stop(self) -> None:
        if self._engine:
            logger.info("Deteniendo bot...")
            self._engine.stop()

    # ──────────────────────────────────────────
    # Slots del BotEngine
    # ──────────────────────────────────────────

    def _on_status_changed(self, status: str) -> None:
        self._status_panel.update_status(status)
        running = status in ("running", "paused")
        self._controls.set_running_state(running)

    def _on_capital_updated(self, available: float, blocked: float, pnl: float) -> None:
        self._status_panel.update_capital(available, blocked, pnl)

    def _on_operation_executed(self, data: dict) -> None:
        """Callback cuando se completa una operación."""
        self._status_panel.update_last_operation(
            instrument=data["instrument"],
            net_profit=data["net_profit"],
            timestamp=data["timestamp"],
        )
        logger.info(
            f"✅ Operación completada: {data['instrument']} | "
            f"Compra CI: ${data['buy_price']:,.2f} | "
            f"Venta 24hs: ${data['sell_price']:,.2f} | "
            f"Ganancia neta: ${data['net_profit']:,.2f}"
        )

    def _on_error(self, message: str) -> None:
        logger.error(f"Error crítico del bot: {message}")
        QMessageBox.critical(self, "Error Crítico", message)

    def _on_market_closed(self) -> None:
        pass  # El log ya se imprime desde el engine; no hace falta UI extra

    def _on_engine_finished(self) -> None:
        """El QThread terminó su ejecución."""
        logger.info("Engine detenido correctamente")
        self._controls.set_running_state(False)
        self._status_panel.update_status("stopped")

    # ──────────────────────────────────────────
    # Logging hacia la UI
    # ──────────────────────────────────────────

    def _on_log_message(self, time_str: str, level: str, message: str) -> None:
        """Recibe logs del LogEmitter y los envía al LogViewer."""
        self._log_viewer.append_log(time_str, level, message)

    # ──────────────────────────────────────────
    # Cierre de la ventana
    # ──────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Detiene el bot antes de cerrar la aplicación."""
        if self._engine and self._engine.isRunning():
            reply = QMessageBox.question(
                self,
                "Cerrar bot",
                "El bot está activo. ¿Detenerse y cerrar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

            self._engine.stop()
            self._engine.wait(5000)  # Esperar máximo 5 segundos

        event.accept()
