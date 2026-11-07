# Arbitrage Bot

Bot de trading de escritorio en Python (PySide6) para el mercado argentino. Detecta oportunidades de arbitraje entre plazos de liquidación y opera a través de la API de PPI, con controles de riesgo y modo sandbox.

> **Aviso:** proyecto personal de aprendizaje, no es asesoramiento financiero. Por defecto trabaja en modo `sandbox`. Probalo ahí y con dinero que puedas perder antes de usar una cuenta real.

## Qué incluye

- **Estrategias** (`strategies/`): arbitraje **CI vs 24 hs** (compra contado inmediato, vende a 24 hs si la tasa supera un mínimo) y **market making** sobre un ticker.
- **Motor del bot** (`core/bot_engine.py`) con un estado compartido (`core/state.py`) que consume la interfaz.
- **Riesgo** (`core/risk_manager.py`): pérdida máxima diaria, posición máxima por ticker y interruptor de parada (`stop_trading_flag`).
- **Posiciones, caja y ejecución** (`core/position_manager.py`, `cash_flow_manager.py`, `order_executor.py`).
- **Broker** (`brokers/`): interfaz base y adaptador para PPI con renovación de token y límite de pedidos por minuto.
- **Utilidades** (`utils/`): comisiones y costos, tamaño de tick, calendario de mercado y configuración.
- **Persistencia** en SQLite (`core/database.py`).
- **Interfaz** (`ui/`): ventana principal con panel de estado, posiciones, controles y visor de logs, con tema oscuro (`styles.qss`).

## Requisitos

- Python 3.10 o superior.
- Una cuenta de PPI con acceso a la API (sandbox o producción).

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # en Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración

Copiá el ejemplo y completá tus datos:

```bash
cp settings.example.json settings.json
```

`settings.json` guarda tus credenciales, por eso está en `.gitignore`. Nunca lo subas.

| Sección | Qué controla |
| --- | --- |
| `mode` | `sandbox` o `production` |
| `ppi` | Usuario, clave, número de cuenta y URL de la API |
| `trading` | Capital inicial, ganancia neta mínima, pérdida diaria máxima, slippage, profundidad mínima del libro |
| `instruments` | Tickers locales y elegibles |
| `risk` | Caución al cierre, posición máxima por ticker, pérdida diaria, parada de emergencia |
| `arbitraje` / `market_making` | Parámetros de cada estrategia |

## Ejecutar

```bash
python main.py
```

Para probar la conexión con el sandbox sin abrir la interfaz: `python scripts/smoke_sandbox.py`.

## Estructura

```
main.py              punto de entrada (Qt)
brokers/             interfaz base y adaptador de PPI
core/                motor, estado, riesgo, posiciones, caja, ejecución, base de datos
strategies/          CI vs 24hs, market making
ui/                  ventana principal y widgets
utils/               configuración, comisiones, ticks, calendario, logger
scripts/             prueba de humo contra el sandbox
```

## Estado

Es el origen de la lógica que después se reescribió en C# como `terminal-f` (terminal WPF en C#). No tiene suite de tests.

## Créditos

- [ppi-client](https://pypi.org/project/ppi-client/): SDK oficial de Portfolio Personal Inversiones. El adaptador `brokers/ppi_adapter.py` está alineado con su interfaz. El SDK no está incluido.
- [PySide6 / Qt for Python](https://pyside.org) (LGPL) y [requests](https://requests.readthedocs.io).
- Los ejemplos de la documentación de la API de PPI se usaron como referencia y no se incluyen.

## Licencia

Código bajo [licencia MIT](LICENSE). © 2026 Nahuel Emiliano Diaz.
