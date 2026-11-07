from __future__ import annotations

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class PositionsTable(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Instrumento", "Plazo", "Cantidad", "Precio Promedio"])
        layout.addWidget(self._table)

    def set_positions(self, positions: list[dict]) -> None:
        self._table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self._table.setItem(row, 0, QTableWidgetItem(str(pos.get("instrument", ""))))
            self._table.setItem(row, 1, QTableWidgetItem(str(pos.get("settlement", ""))))
            self._table.setItem(row, 2, QTableWidgetItem(str(pos.get("quantity", ""))))
            self._table.setItem(row, 3, QTableWidgetItem(str(pos.get("avg_price", ""))))
