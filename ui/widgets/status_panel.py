from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StatusPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self._status = QLabel("Estado: stopped")
        self._capital = QLabel("Capital: disponible $0.00 | bloqueado $0.00 | PnL $0.00")
        self._last_op = QLabel("Ultima operacion: -")
        layout.addWidget(self._status)
        layout.addWidget(self._capital)
        layout.addWidget(self._last_op)

    def update_status(self, status: str) -> None:
        self._status.setText(f"Estado: {status}")

    def update_capital(self, available: float, blocked: float, pnl: float) -> None:
        self._capital.setText(
            f"Capital: disponible ${available:,.2f} | bloqueado ${blocked:,.2f} | PnL ${pnl:,.2f}"
        )

    def update_last_operation(self, instrument: str, net_profit: float, timestamp: str) -> None:
        self._last_op.setText(
            f"Ultima operacion: {instrument} | PnL ${net_profit:,.2f} | {timestamp}"
        )
