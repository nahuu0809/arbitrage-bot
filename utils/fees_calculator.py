"""
fees_calculator.py - Calcula comisiones, derechos BYMA e IVA para cada operación.

Estructura de costos (BYMA / PPI):
    - Comisión broker (PPI):  ~0.6% sobre el monto operado
    - Derechos de mercado:    ~0.01% sobre el monto operado
    - IVA sobre comisión:     21% sobre la comisión del broker

Aplica tanto para la pata de compra (CI) como para la de venta (24hs).
"""

from dataclasses import dataclass


# ──────────────────────────────────────────────
# Constantes de comisiones (ajustables si PPI las cambia)
# ──────────────────────────────────────────────
BROKER_COMMISSION_RATE = 0.006        # 0.6% comisión PPI
MARKET_RIGHTS_RATE = 0.0001           # 0.01% derechos BYMA
VAT_RATE = 0.21                       # 21% IVA sobre comisión del broker


@dataclass
class FeeBreakdown:
    """Desglose completo de comisiones para una operación."""
    amount: float                     # Monto base operado (precio * cantidad)

    broker_commission: float = 0.0    # Comisión del broker
    market_rights: float = 0.0        # Derechos de mercado BYMA
    vat_on_commission: float = 0.0    # IVA sobre comisión

    @property
    def total(self) -> float:
        """Suma total de todos los cargos."""
        return self.broker_commission + self.market_rights + self.vat_on_commission

    def __str__(self) -> str:
        return (
            f"Monto: ${self.amount:,.2f} | "
            f"Comisión: ${self.broker_commission:.2f} | "
            f"Derechos: ${self.market_rights:.2f} | "
            f"IVA: ${self.vat_on_commission:.2f} | "
            f"Total cargos: ${self.total:.2f}"
        )


@dataclass
class OperationFees:
    """Cargos totales de una operación completa (compra CI + venta 24hs)."""
    buy_fees: FeeBreakdown
    sell_fees: FeeBreakdown

    @property
    def total(self) -> float:
        return self.buy_fees.total + self.sell_fees.total

    def __str__(self) -> str:
        return (
            f"Compra CI  → {self.buy_fees}\n"
            f"Venta 24hs → {self.sell_fees}\n"
            f"TOTAL CARGOS: ${self.total:.2f}"
        )


# ──────────────────────────────────────────────
# Funciones de cálculo
# ──────────────────────────────────────────────

def calculate_fees_for_leg(amount: float) -> FeeBreakdown:
    """
    Calcula los cargos para una pata de la operación (compra o venta).

    Args:
        amount: Monto en ARS operado (precio * cantidad).

    Returns:
        FeeBreakdown con el desglose de costos.
    """
    broker_commission = amount * BROKER_COMMISSION_RATE
    market_rights = amount * MARKET_RIGHTS_RATE
    vat_on_commission = broker_commission * VAT_RATE

    return FeeBreakdown(
        amount=amount,
        broker_commission=broker_commission,
        market_rights=market_rights,
        vat_on_commission=vat_on_commission,
    )


def calculate_net_profit(
    buy_price: float,
    sell_price: float,
    quantity: float,
) -> tuple[float, float, OperationFees]:
    """
    Calcula la ganancia neta real de un arbitraje CI vs 24hs.

    Args:
        buy_price:  Precio de compra CI (por unidad).
        sell_price: Precio de venta 24hs (por unidad).
        quantity:   Cantidad de títulos.

    Returns:
        Tupla (ganancia_bruta, ganancia_neta, desglose_de_cargos).
    """
    buy_amount = buy_price * quantity
    sell_amount = sell_price * quantity

    gross_profit = (sell_price - buy_price) * quantity

    buy_fees = calculate_fees_for_leg(buy_amount)
    sell_fees = calculate_fees_for_leg(sell_amount)
    operation_fees = OperationFees(buy_fees=buy_fees, sell_fees=sell_fees)

    net_profit = gross_profit - operation_fees.total

    return gross_profit, net_profit, operation_fees


def calculate_max_quantity(
    available_capital: float,
    max_capital_percent: float,
    buy_price: float,
) -> float:
    """
    Calcula la cantidad máxima de títulos a comprar dado el capital disponible.

    Args:
        available_capital:   Capital líquido disponible en ARS.
        max_capital_percent: Porcentaje máximo del capital a usar (0-100).
        buy_price:           Precio de compra CI por título.

    Returns:
        Cantidad de títulos (como float para instrumentos fraccionados).
    """
    if buy_price <= 0:
        return 0.0

    capital_to_use = available_capital * (max_capital_percent / 100.0)

    # Reservamos un buffer del 0.7% para cubrir comisiones de la compra
    effective_capital = capital_to_use / (1 + BROKER_COMMISSION_RATE + MARKET_RIGHTS_RATE)
    quantity = effective_capital / buy_price

    return quantity
