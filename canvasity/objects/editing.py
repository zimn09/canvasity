"""Shared inline text editor used by sticky notes and text boxes."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsTextItem


class InlineTextEditor(QGraphicsTextItem):
    """A QGraphicsTextItem that reports focus loss and Escape back to its owner."""

    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner

    def focusOutEvent(self, event: Any) -> None:
        super().focusOutEvent(event)
        self._owner.finish_edit()

    def keyPressEvent(self, event: Any) -> None:
        is_ctrl_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and bool(
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        )
        if event.key() == Qt.Key.Key_Escape or is_ctrl_enter:
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)
