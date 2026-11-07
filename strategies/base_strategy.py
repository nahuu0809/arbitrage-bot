from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Opportunity:
    instrument: str
    buy_price: float
    sell_price: float
    quantity: float
    expected_net_profit: float
    expected_gross_profit: float
    fees_total: float
    details: dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    def __init__(self, broker, state) -> None:
        self._broker = broker
        self._state = state

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def find_opportunity(self, instrument: str) -> Optional[Opportunity]:
        raise NotImplementedError

    @abstractmethod
    def scan_all(self) -> Optional[Opportunity]:
        raise NotImplementedError
