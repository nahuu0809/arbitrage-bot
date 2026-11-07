from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class ControlsBar(QWidget):
    start_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)

        self._start_btn = QPushButton("Iniciar")
        self._pause_btn = QPushButton("Pausar")
        self._stop_btn = QPushButton("Detener")

        layout.addWidget(self._start_btn)
        layout.addWidget(self._pause_btn)
        layout.addWidget(self._stop_btn)

        self._start_btn.clicked.connect(self.start_requested.emit)
        self._pause_btn.clicked.connect(self.pause_requested.emit)
        self._stop_btn.clicked.connect(self.stop_requested.emit)

        self.set_running_state(False)

    def set_running_state(self, running: bool) -> None:
        self._pause_btn.setEnabled(running)
        self._stop_btn.setEnabled(running)
        self._start_btn.setText("Reanudar" if running else "Iniciar")
