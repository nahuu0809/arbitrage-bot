from __future__ import annotations

from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget


class LogViewer(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        layout.addWidget(self._text)

    def append_log(self, time_str: str, level: str, message: str) -> None:
        self._text.append(f"[{time_str}] [{level}] {message}")
