from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "settings.json")


@dataclass
class PPIConfig:
    username: str = "TU_USUARIO"
    password: str = "TU_PASSWORD"
    account_number: str = ""
    api_base_url: str = "https://api.portfoliopersonal.com"
    token_renewal_seconds_before_expiry: int = 300
    rate_limit_per_minute: int = 60


@dataclass
class TradingConfig:
    initial_capital: float = 100000.0
    polling_interval_seconds: int = 5
    max_capital_per_operation_percent: float = 25.0
    min_net_profit: float = 500.0
    order_book_positions_to_check: int = 3
    min_book_depth_ars: float = 10000.0
    validation_timeout_seconds: int = 5


@dataclass
class RiskConfig:
    enable_caucion_at_close: bool = False
    caucion_min_rate_percent: float = 20.0
    max_daily_loss_ars: float = 0.0
    max_daily_loss_percent: float = 10.0
    max_slippage_percent: float = 0.5
    max_position_por_ticker: float = 100.0
    max_loss_diario: float = 0.0
    stop_trading_flag: bool = False


@dataclass
class InstrumentsConfig:
    eligible_tickers: list[str] = field(default_factory=lambda: ["GGAL", "YPFD", "PAMP"])
    byma_local_tickers: list[str] = field(default_factory=lambda: ["GGAL", "YPFD", "PAMP"])


@dataclass
class TickRange:
    min: float
    max: float | None
    tick: float


@dataclass
class MarketMakingConfig:
    enabled: bool = False
    ticker: str = "GGAL"
    settlement: str = "CI"
    min_spread: float = 0.5
    order_size: float = 10.0
    max_position: float = 100.0
    cancel_threshold_ticks: int = 2


@dataclass
class ArbitrajeConfig:
    enabled: bool = True
    tasa_minima: float = 0.25


@dataclass
class AppConfig:
    mode: str = "sandbox"
    ppi: PPIConfig = field(default_factory=PPIConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    instruments: InstrumentsConfig = field(default_factory=InstrumentsConfig)
    market_making: MarketMakingConfig = field(default_factory=MarketMakingConfig)
    arbitraje: ArbitrajeConfig = field(default_factory=ArbitrajeConfig)
    tick_table: list[TickRange] = field(
        default_factory=lambda: [
            TickRange(min=0.0, max=10.0, tick=0.01),
            TickRange(min=10.0, max=100.0, tick=0.05),
            TickRange(min=100.0, max=1000.0, tick=0.10),
            TickRange(min=1000.0, max=None, tick=0.50),
        ]
    )

    @property
    def is_sandbox(self) -> bool:
        return self.mode.lower() == "sandbox"


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _safe_optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    cfg = AppConfig()

    if not os.path.exists(CONFIG_PATH):
        return cfg

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cfg.mode = str(data.get("mode", cfg.mode))

    ppi = data.get("ppi", {})
    cfg.ppi = PPIConfig(
        username=str(ppi.get("username", cfg.ppi.username)),
        password=str(ppi.get("password", cfg.ppi.password)),
        account_number=str(ppi.get("account_number", cfg.ppi.account_number)),
        api_base_url=str(ppi.get("api_base_url", cfg.ppi.api_base_url)),
        token_renewal_seconds_before_expiry=_safe_int(
            ppi.get(
                "token_renewal_seconds_before_expiry",
                cfg.ppi.token_renewal_seconds_before_expiry,
            ),
            cfg.ppi.token_renewal_seconds_before_expiry,
        ),
        rate_limit_per_minute=_safe_int(
            ppi.get("rate_limit_per_minute", cfg.ppi.rate_limit_per_minute),
            cfg.ppi.rate_limit_per_minute,
        ),
    )

    trading = data.get("trading", {})
    cfg.trading = TradingConfig(
        initial_capital=_safe_float(
            trading.get("initial_capital", cfg.trading.initial_capital),
            cfg.trading.initial_capital,
        ),
        polling_interval_seconds=_safe_int(
            trading.get("polling_interval_seconds", cfg.trading.polling_interval_seconds),
            cfg.trading.polling_interval_seconds,
        ),
        max_capital_per_operation_percent=_safe_float(
            trading.get(
                "max_capital_per_operation_percent",
                cfg.trading.max_capital_per_operation_percent,
            ),
            cfg.trading.max_capital_per_operation_percent,
        ),
        min_net_profit=_safe_float(
            trading.get("min_net_profit", cfg.trading.min_net_profit),
            cfg.trading.min_net_profit,
        ),
        order_book_positions_to_check=_safe_int(
            trading.get(
                "order_book_positions_to_check",
                cfg.trading.order_book_positions_to_check,
            ),
            cfg.trading.order_book_positions_to_check,
        ),
        min_book_depth_ars=_safe_float(
            trading.get("min_book_depth_ars", cfg.trading.min_book_depth_ars),
            cfg.trading.min_book_depth_ars,
        ),
        validation_timeout_seconds=_safe_int(
            trading.get(
                "validation_timeout_seconds",
                cfg.trading.validation_timeout_seconds,
            ),
            cfg.trading.validation_timeout_seconds,
        ),
    )

    risk = data.get("risk", {})
    cfg.risk = RiskConfig(
        enable_caucion_at_close=_safe_bool(
            risk.get("enable_caucion_at_close", cfg.risk.enable_caucion_at_close),
            cfg.risk.enable_caucion_at_close,
        ),
        caucion_min_rate_percent=_safe_float(
            risk.get("caucion_min_rate_percent", cfg.risk.caucion_min_rate_percent),
            cfg.risk.caucion_min_rate_percent,
        ),
        max_daily_loss_ars=_safe_float(
            risk.get("max_daily_loss_ars", cfg.risk.max_daily_loss_ars),
            cfg.risk.max_daily_loss_ars,
        ),
        max_daily_loss_percent=_safe_float(
            risk.get(
                "max_daily_loss_percent",
                trading.get("max_daily_loss_percent", cfg.risk.max_daily_loss_percent),
            ),
            cfg.risk.max_daily_loss_percent,
        ),
        max_slippage_percent=_safe_float(
            risk.get(
                "max_slippage_percent",
                trading.get("max_slippage_percent", cfg.risk.max_slippage_percent),
            ),
            cfg.risk.max_slippage_percent,
        ),
        max_position_por_ticker=_safe_float(
            risk.get("max_position_por_ticker", cfg.risk.max_position_por_ticker),
            cfg.risk.max_position_por_ticker,
        ),
        max_loss_diario=_safe_float(
            risk.get("max_loss_diario", cfg.risk.max_loss_diario),
            cfg.risk.max_loss_diario,
        ),
        stop_trading_flag=_safe_bool(
            risk.get("stop_trading_flag", cfg.risk.stop_trading_flag),
            cfg.risk.stop_trading_flag,
        ),
    )

    instruments = data.get("instruments", {})
    eligible = instruments.get("eligible_tickers", cfg.instruments.eligible_tickers)
    if not isinstance(eligible, list):
        eligible = cfg.instruments.eligible_tickers
    byma = instruments.get("byma_local_tickers", cfg.instruments.byma_local_tickers)
    if not isinstance(byma, list):
        byma = cfg.instruments.byma_local_tickers
    cfg.instruments = InstrumentsConfig(
        eligible_tickers=[str(t).upper() for t in eligible],
        byma_local_tickers=[str(t).upper() for t in byma],
    )

    mm = data.get("market_making", {})
    cfg.market_making = MarketMakingConfig(
        enabled=_safe_bool(mm.get("enabled", cfg.market_making.enabled), cfg.market_making.enabled),
        ticker=str(mm.get("ticker", cfg.market_making.ticker)).upper(),
        settlement=str(mm.get("settlement", cfg.market_making.settlement)),
        min_spread=_safe_float(mm.get("min_spread", cfg.market_making.min_spread), cfg.market_making.min_spread),
        order_size=_safe_float(mm.get("order_size", cfg.market_making.order_size), cfg.market_making.order_size),
        max_position=_safe_float(mm.get("max_position", cfg.market_making.max_position), cfg.market_making.max_position),
        cancel_threshold_ticks=_safe_int(
            mm.get("cancel_threshold_ticks", cfg.market_making.cancel_threshold_ticks),
            cfg.market_making.cancel_threshold_ticks,
        ),
    )

    arb = data.get("arbitraje", {})
    cfg.arbitraje = ArbitrajeConfig(
        enabled=_safe_bool(arb.get("enabled", cfg.arbitraje.enabled), cfg.arbitraje.enabled),
        tasa_minima=_safe_float(arb.get("tasa_minima", cfg.arbitraje.tasa_minima), cfg.arbitraje.tasa_minima),
    )

    raw_tick_table = data.get("tick_table", [])
    if isinstance(raw_tick_table, list) and raw_tick_table:
        parsed_ticks: list[TickRange] = []
        for row in raw_tick_table:
            if not isinstance(row, dict):
                continue
            min_v = _safe_float(row.get("min", 0.0), 0.0)
            max_v = _safe_optional_float(row.get("max"))
            tick_v = _safe_float(row.get("tick", 0.0), 0.0)
            if tick_v > 0:
                parsed_ticks.append(TickRange(min=min_v, max=max_v, tick=tick_v))
        if parsed_ticks:
            cfg.tick_table = parsed_ticks

    return cfg
