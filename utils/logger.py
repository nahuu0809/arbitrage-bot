from __future__ import annotations

import logging
from datetime import datetime
from threading import Lock
from typing import Callable


class LogEmitter:
    _instance = None
    _lock = Lock()

    def __init__(self) -> None:
        self._callbacks: list[Callable[[str, str, str], None]] = []

    @classmethod
    def instance(cls) -> "LogEmitter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = LogEmitter()
            return cls._instance

    def register_callback(self, callback: Callable[[str, str, str], None]) -> None:
        self._callbacks.append(callback)

    def emit(self, level: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        for cb in list(self._callbacks):
            try:
                cb(ts, level, message)
            except Exception:
                pass


class UILogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        LogEmitter.instance().emit(record.levelname, msg)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    ui_handler = UILogHandler()
    ui_handler.setFormatter(formatter)
    logger.addHandler(ui_handler)

    logger.propagate = False
    return logger
