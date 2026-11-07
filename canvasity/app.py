"""Application bootstrap."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import APP_NAME, APP_ORG, APP_VERSION
from .ui.main_window import CanvasityWindow

logger = logging.getLogger(__name__)


def _install_exception_hook() -> None:
    """Log unexpected errors instead of letting them crash a Qt callback."""
    showing = False

    def handle(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        nonlocal showing
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        if showing:
            return
        showing = True
        try:
            QMessageBox.critical(
                None,
                APP_NAME,
                f"An unexpected error occurred:\n\n{exc}\n\n"
                "The board is still open; save your work to a new file if needed.",
            )
        finally:
            showing = False

    sys.excepthook = handle


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arguments = list(argv if argv is not None else sys.argv)
    app = QApplication(arguments)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    _install_exception_hook()

    window = CanvasityWindow()
    window.show()

    board: Path | None = None
    for candidate in arguments[1:]:
        path = Path(candidate)
        if path.is_file():
            board = path
            break

    if board is not None:
        window.open_path(board, confirm_save=False)
    else:
        QTimer.singleShot(0, window.maybe_restore_session)
    return app.exec()
