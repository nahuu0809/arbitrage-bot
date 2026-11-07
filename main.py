"""
main.py - Punto de entrada del Bot de Trading Argentina.

Inicializa la aplicaciÃ³n Qt y abre la ventana principal.
"""

import sys
import os

# Asegurar que el directorio raÃ­z del proyecto estÃ© en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.main_window import MainWindow
from utils.config import get_config, CONFIG_PATH
from utils.logger import get_logger

logger = get_logger("main")


def main() -> int:
    """Entry point principal."""

    # â”€â”€ Verificar que existe settings.json â”€â”€
    if not os.path.exists(CONFIG_PATH):
        print(f"ERROR: No se encontrÃ³ settings.json en {CONFIG_PATH}")
        print("CopiÃ¡ el archivo de ejemplo y configurÃ¡ tus credenciales.")
        return 1

    # â”€â”€ Validar configuraciÃ³n bÃ¡sica â”€â”€
    try:
        config = get_config()
        logger.info(f"ConfiguraciÃ³n cargada | Modo: {config.mode.upper()}")

        if config.ppi.username == "TU_USUARIO":
            logger.warning(
                "âš ï¸  Las credenciales de PPI no estÃ¡n configuradas. "
                "EditÃ¡ settings.json en la raiz del proyecto antes de iniciar."
            )
        if not str(config.ppi.account_number).strip():
            logger.warning(
                "âš ï¸  Falta ppi.account_number en settings.json. "
                "Es obligatorio para enviar/cancelar/consultar ordenes."
            )
    except Exception as e:
        print(f"ERROR al cargar configuraciÃ³n: {e}")
        return 1

    # â”€â”€ Inicializar Qt â”€â”€
    app = QApplication(sys.argv)
    app.setApplicationName("Bot de Trading Argentina")
    app.setOrganizationName("Personal")

    # High DPI scaling (Qt6 lo maneja automÃ¡ticamente)
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # â”€â”€ Abrir ventana principal â”€â”€
    window = MainWindow()
    window.show()

    logger.info("AplicaciÃ³n iniciada correctamente")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

