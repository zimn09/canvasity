"""Sticky note object with inline editing."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from ..config import DEFAULT_FONT, DEFAULT_STICKY, STICKY_FONT_SIZE
from .base import BoardItem
from .editing import InlineTextEditor

PADDING = 14.0
STICKY_TEXT = "#3f2d0a"


class StickyItem(BoardItem):
    TYPE = "sticky"
    SUPPORTS_FILL = True
    SUPPORTS_TEXT = True

    def __init__(
        self,
        width: float = 220.0,
        height: float = 180.0,
        text: str = "",
        color: str | QColor = DEFAULT_STICKY,
        text_color: str | QColor = STICKY_TEXT,
        font_size: float = STICKY_FONT_SIZE,
    ) -> None:
        super().__init__()
        self._color = QColor(color)
        self._text_color = QColor(text_color)
        self._font_size = float(font_size)
        self._font_family = DEFAULT_FONT
        self._editing = False
        self._edit_before: dict[str, Any] | None = None

        self._editor = InlineTextEditor(self)
        self._editor.setPos(PADDING, PADDING)
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.setFont(self._make_font())
        self._editor.document().setDocumentMargin(0.0)
        self._editor.setPlainText(text)
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.set_size(width, height)
        self.setZValue(1.0)

    # ------------------------------------------------------------------ font
    def _make_font(self) -> QFont:
        font = QFont(self._font_family, int(self._font_size))
        return font

    def set_size(self, width: float, height: float) -> None:
        super().set_size(width, height)
        if hasattr(self, "_editor"):
            self._editor.setTextWidth(max(20.0, self._w - PADDING * 2.0))

    # ------------------------------------------------------------------ text api
    @property
    def text(self) -> str:
        return self._editor.toPlainText()

    def set_text(self, text: str) -> None:
        if text != self._editor.toPlainText():
            self._editor.setPlainText(text)
            self.update()

    @property
    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    @property
    def text_color(self) -> QColor:
        return self._text_color

    def set_text_color(self, color: QColor) -> None:
        self._text_color = QColor(color)
        self._editor.setDefaultTextColor(self._text_color)
        self.update()

    def set_font_size(self, size: float) -> None:
        self._font_size = max(6.0, float(size))
        self._editor.setFont(self._make_font())

    def set_font_family(self, family: str) -> None:
        self._font_family = family
        self._editor.setFont(self._make_font())

    # ------------------------------------------------------------------ painting
    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        shadow = QRectF(r).translated(2.5, 3.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 26))
        painter.drawRoundedRect(shadow, 7.0, 7.0)
        painter.setBrush(self._color)
        painter.setPen(QPen(self._color.darker(112), 1.0))
        painter.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 7.0, 7.0)
        if not self.text.strip() and not self._editing:
            painter.setPen(QPen(self._text_color.lighter(135), 1))
            font = QFont(self._font_family, int(self._font_size))
            font.setItalic(True)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(PADDING, PADDING, -PADDING, -PADDING),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                "Sticky note",
            )

    # ------------------------------------------------------------------ editing
    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.begin_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def begin_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self._edit_before = self.capture_state()
        self._editor.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self._editor.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._editor.setTextCursor(cursor)
        self.update()

    def finish_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        scene = self.scene()
        if scene is not None and self._edit_before is not None:
            scene.push_state([self], self._edit_before, "Edit text")
        self._edit_before = None
        self.update()

    # ------------------------------------------------------------------ state
    def _extra_state(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "color": self._color.name(QColor.NameFormat.HexArgb),
            "text_color": self._text_color.name(QColor.NameFormat.HexArgb),
            "font_size": self._font_size,
            "font_family": self._font_family,
        }

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        if "color" in state:
            self._color = QColor(state["color"])
        if "text_color" in state:
            self._text_color = QColor(state["text_color"])
            self._editor.setDefaultTextColor(self._text_color)
        if "font_size" in state:
            self._font_size = float(state["font_size"])
        if "font_family" in state:
            self._font_family = state["font_family"]
        if "text" in state:
            self._editor.setPlainText(state["text"])
        self._editor.setFont(self._make_font())

    def _extra_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "color": self._color.name(QColor.NameFormat.HexArgb),
            "text_color": self._text_color.name(QColor.NameFormat.HexArgb),
            "font_size": self._font_size,
            "font_family": self._font_family,
        }
