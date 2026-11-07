"""
ppi_adapter.py - Adaptador alineado con la SDK oficial ppi-client.
"""

from __future__ import annotations

from typing import Optional

from ppi_client.models.disclaimer import Disclaimer
from ppi_client.models.order import Order
from ppi_client.models.order_budget import OrderBudget
from ppi_client.models.order_confirm import OrderConfirm
from ppi_client.ppi import PPI

from brokers.base_broker import (
    BaseBroker,
    BookLevel,
    OrderBook,
    OrderResult,
    OrderSide,
    OrderStatus,
    Quote,
)
from utils.config import get_config
from utils.logger import get_logger

logger = get_logger(__name__)

INSTRUMENT_TYPE = "ACCIONES"
QUANTITY_TYPE = "PAPELES"
OPERATION_TYPE_LIMIT = "PRECIO-LIMITE"
OPERATION_TERM = "HASTA-SU-EJECUCIÓN"

SETTLEMENT_MAP = {
    "CI": "INMEDIATA",
    "24hs": "A-24HS",
    "48hs": "A-48HS",
}

SIDE_MAP = {
    OrderSide.BUY: "Compra",
    OrderSide.SELL: "Venta",
    "buy": "Compra",
    "sell": "Venta",
}


class PPIAdapter(BaseBroker):
    def __init__(self):
        cfg = get_config()
        self._cfg = cfg.ppi
        self._is_sandbox = cfg.is_sandbox
        self._client = PPI(sandbox=self._is_sandbox)
        self._connected = False

    def _require_account(self) -> str:
        account = str(self._cfg.account_number or "").strip()
        if not account:
            try:
                accounts = self._client.account.get_accounts()
                if accounts:
                    account = str(accounts[0].get("accountNumber", "")).strip()
                    if account:
                        self._cfg.account_number = account
                        logger.info(f"account_number autodetectado desde API: {account}")
            except Exception as e:
                logger.error(f"No se pudo autodetectar account_number: {e}")
        if not account:
            raise ValueError(
                "Falta ppi.account_number en settings.json y no se pudo obtener desde get_accounts()."
            )
        return account

    def _sdk_settlement(self, settlement: str) -> str:
        return SETTLEMENT_MAP.get(settlement, "A-24HS")

    def _sdk_side(self, side: str) -> str:
        return SIDE_MAP.get(side, SIDE_MAP.get(str(side).lower(), "Compra"))

    def _status_to_internal(self, status: str) -> str:
        value = str(status or "").upper().replace("-", "_")
        mapping = {
            "NEW": OrderStatus.NEW,
            "PENDING_NEW": OrderStatus.NEW,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "PENDING_CANCEL": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return mapping.get(value, OrderStatus.NEW)

    def connect(self) -> bool:
        try:
            self._client.account.login_api(self._cfg.username, self._cfg.password)
            self._connected = True
            logger.info("Conexion con PPI establecida via SDK")
            return True
        except Exception as e:
            self._connected = False
            logger.error(f"No se pudo autenticar con PPI: {e}")
            return False

    def disconnect(self) -> None:
        self._connected = False
        logger.info("Desconexion local de PPI")

    def is_connected(self) -> bool:
        return self._connected

    def get_quote(self, instrument: str, settlement: str) -> Optional[Quote]:
        if not self._connected and not self.connect():
            return None

        sdk_settlement = self._sdk_settlement(settlement)
        try:
            current = self._client.marketdata.current(instrument, "Acciones", sdk_settlement)
            book = self._client.marketdata.book(instrument, "Acciones", sdk_settlement)
            bids = book.get("bids", []) or []
            offers = book.get("offers", []) or []

            bid = float((bids[0].get("price") if bids else current.get("price", 0)) or 0)
            ask = float((offers[0].get("price") if offers else current.get("price", 0)) or 0)
            last = float(current.get("price", 0) or 0)
            volume = float(current.get("volume", current.get("volumeAmount", 0)) or 0)

            return Quote(
                instrument=instrument,
                settlement=settlement,
                bid=bid,
                ask=ask,
                last=last,
                volume=volume,
            )
        except Exception as e:
            logger.error(f"Error obteniendo quote {instrument}/{settlement}: {e}")
            return None

    def get_order_book(self, instrument: str, settlement: str) -> Optional[OrderBook]:
        if not self._connected and not self.connect():
            return None
        sdk_settlement = self._sdk_settlement(settlement)

        try:
            data = self._client.marketdata.book(instrument, "Acciones", sdk_settlement)
            bids = [
                BookLevel(price=float(level.get("price", 0)), quantity=float(level.get("quantity", 0)))
                for level in data.get("bids", []) or []
            ]
            asks = [
                BookLevel(price=float(level.get("price", 0)), quantity=float(level.get("quantity", 0)))
                for level in data.get("offers", []) or []
            ]
            return OrderBook(instrument=instrument, settlement=settlement, bids=bids, asks=asks)
        except Exception as e:
            logger.error(f"Error obteniendo book {instrument}/{settlement}: {e}")
            return None

    def send_order(
        self,
        instrument: str,
        side: str,
        settlement: str,
        quantity: float,
        price: float,
    ) -> OrderResult:
        if not self._connected and not self.connect():
            return OrderResult(success=False, instrument=instrument, error_message="Sin autenticacion PPI")

        account = self._require_account()
        sdk_settlement = self._sdk_settlement(settlement)
        sdk_side = self._sdk_side(side)
        qty = max(1, int(round(float(quantity))))
        limit_price = float(price)

        try:
            budget = self._client.orders.budget(
                OrderBudget(
                    account,
                    qty,
                    limit_price,
                    instrument,
                    INSTRUMENT_TYPE,
                    QUANTITY_TYPE,
                    OPERATION_TYPE_LIMIT,
                    OPERATION_TERM,
                    None,
                    sdk_side,
                    sdk_settlement,
                )
            )

            disclaimers = []
            for d in budget.get("disclaimers", []) or []:
                disclaimers.append(Disclaimer(d.get("code"), True))

            confirmation = self._client.orders.confirm(
                OrderConfirm(
                    account,
                    qty,
                    limit_price,
                    instrument,
                    INSTRUMENT_TYPE,
                    QUANTITY_TYPE,
                    OPERATION_TYPE_LIMIT,
                    OPERATION_TERM,
                    None,
                    sdk_side,
                    sdk_settlement,
                    disclaimers,
                    None,
                )
            )

            order_id = str(confirmation.get("id", ""))
            status = self._status_to_internal(str(confirmation.get("status", OrderStatus.NEW)))
            exec_price = float(confirmation.get("price", limit_price) or limit_price)
            exec_qty = float(confirmation.get("quantity", qty) or qty)

            logger.info(
                f"Orden confirmada {instrument} {sdk_side} {sdk_settlement} id={order_id} status={status}"
            )
            return OrderResult(
                success=True,
                order_id=order_id,
                instrument=instrument,
                side=side,
                settlement=settlement,
                executed_price=exec_price,
                executed_quantity=exec_qty,
                status=status,
                raw_response=confirmation,
            )
        except Exception as e:
            logger.error(f"Error enviando orden {instrument}: {e}")
            return OrderResult(success=False, instrument=instrument, error_message=str(e))

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected and not self.connect():
            return False
        account = self._require_account()
        try:
            result = self._client.orders.cancel_order(Order(int(order_id), account, None))
            logger.info(f"Cancel order {order_id}: {result}")
            return True
        except Exception as e:
            logger.warning(f"No se pudo cancelar orden {order_id}: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        if not self._connected and not self.connect():
            return None
        account = self._require_account()
        try:
            detail = self._client.orders.get_order_detail(account, int(order_id), None)
            status = self._status_to_internal(str(detail.get("status", "")))
            qty = float(detail.get("quantity", 0) or 0)
            price = float(detail.get("price", 0) or 0)
            ticker = str(detail.get("ticker", ""))
            settlement = str(detail.get("settlement", ""))
            operation = str(detail.get("operation", ""))
            side = OrderSide.BUY if operation.lower().startswith("compra") else OrderSide.SELL

            return OrderResult(
                success=True,
                order_id=str(detail.get("id", order_id)),
                instrument=ticker,
                side=side,
                settlement=settlement,
                executed_price=price,
                executed_quantity=qty,
                status=status,
                raw_response=detail,
            )
        except Exception as e:
            logger.warning(f"No se pudo obtener estado de orden {order_id}: {e}")
            return None

    def get_account_balance(self) -> dict[str, float]:
        if not self._connected and not self.connect():
            return {}
        account = self._require_account()
        try:
            balances = self._client.account.get_available_balance(account)
            available_ars = 0.0
            for b in balances:
                name = str(b.get("name", "")).upper()
                symbol = str(b.get("symbol", b.get("simbol", ""))).upper()
                if "PESO" in name or symbol == "$":
                    available_ars += float(b.get("amount", 0) or 0)
            return {
                "available_ars": available_ars,
                "blocked_ars": 0.0,
                "total_ars": available_ars,
            }
        except Exception as e:
            logger.error(f"Error consultando balance: {e}")
            return {}
