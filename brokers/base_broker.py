from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class OrderSide:
    BUY = "buy"
    SELL = "sell"


class OrderSettlement:
    CI = "CI"
    H24 = "24hs"


class OrderStatus:
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Quote:
    instrument: str
    settlement: str
    bid: float
    ask: float
    last: float
    volume: float


@dataclass
class BookLevel:
    price: float
    quantity: float


@dataclass
class OrderBook:
    instrument: str
    settlement: str
    bids: list[BookLevel] = field(default_factory=list)
    asks: list[BookLevel] = field(default_factory=list)

    def get_bid_depth_ars(self, n_levels: int) -> float:
        return sum(level.price * level.quantity for level in self.bids[:n_levels])

    def get_ask_depth_ars(self, n_levels: int) -> float:
        return sum(level.price * level.quantity for level in self.asks[:n_levels])


@dataclass
class OrderResult:
    success: bool
    instrument: str
    order_id: str = ""
    side: str = ""
    settlement: str = ""
    executed_price: float = 0.0
    executed_quantity: float = 0.0
    status: str = OrderStatus.NEW
    error_message: str = ""
    raw_response: Optional[dict] = None


class BaseBroker(ABC):
    @abstractmethod
    def connect(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, instrument: str, settlement: str) -> Optional[Quote]:
        raise NotImplementedError

    @abstractmethod
    def get_order_book(self, instrument: str, settlement: str) -> Optional[OrderBook]:
        raise NotImplementedError

    @abstractmethod
    def send_order(
        self,
        instrument: str,
        side: str,
        settlement: str,
        quantity: float,
        price: float,
    ) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_account_balance(self) -> dict[str, float]:
        raise NotImplementedError

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        _ = order_id
        return None
