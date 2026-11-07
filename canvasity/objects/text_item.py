"""Free-standing text boxes with inline editing."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor, QTextOption
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from ..config import DEFAULT_FONT, DEFAULT_FONT_SIZE, DEFAULT_TEXT
from .base import BoardItem
from .editing import InlineTextEditor

PADDING = 6.0
ALIGNMENTS = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
    "justify": Qt.AlignmentFlag.AlignJustify,
}


class TextItem(BoardItem):
    TYPE = "text"
    SUPPORTS_TEXT = True
    RESIZE_AXES = "x"

    def __init__(
        self,
        width: float = 280.0,
        text: str = "",
        color: str | QColor = DEFAULT_TEXT,
        font_family: str = DEFAULT_FONT,
        font_size: float = DEFAULT_FONT_SIZE,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        alignment: str = "left",
    ) -> None:
        super().__init__()
        self._font_family = font_family
        self._font_size = float(font_size)
        self._bold = bool(bold)
        self._italic = bool(italic)
        self._underline = bool(underline)
        self._alignment = alignment if alignment in ALIGNMENTS else "left"
        self._text_color = QColor(color)
        self._editing = False
        self._edit_before: dict[str, Any] | None = None
        self._fitting = False

        self._editor = InlineTextEditor(self)
        self._editor.setPos(PADDING, PADDING)
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.document().setDocumentMargin(0.0)
        self._editor.setPlainText(text)
        self._apply_font()
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._editor.document().contentsChanged.connect(self._content_changed)

        self.set_size(width, 40.0)
        self._fit_height()

    # ------------------------------------------------------------------ font helpers
    def _make_font(self) -> QFont:
        font = QFont(self._font_family, int(self._font_size))
        font.setBold(self._bold)
        font.setItalic(self._italic)
        font.setUnderline(self._underline)
        return font

    def _apply_font(self) -> None:
        self._editor.setFont(self._make_font())
        option = self._editor.document().defaultTextOption()
        option.setAlignment(ALIGNMENTS[self._alignment])
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._editor.document().setDefaultTextOption(option)
        self._editor.setTextWidth(max(20.0, self._w - PADDING * 2.0))
        self._editor.setDefaultTextColor(self._text_color)

    @property
    def text(self) -> str:
        return self._editor.toPlainText()

    def set_text(self, text: str) -> None:
        if text != self._editor.toPlainText():
            self._editor.setPlainText(text)
            self._fit_height()
            self.update()

    @property
    def text_color(self) -> QColor:
        return self._text_color

    def set_text_color(self, color: QColor) -> None:
        self._text_color = QColor(color)
        self._editor.setDefaultTextColor(self._text_color)
        self.update()

    @property
    def font_size(self) -> float:
        return self._font_size

    def set_font_size(self, size: float) -> None:
        self._font_size = max(6.0, float(size))
        self._apply_font()
        self._fit_height()

    @property
    def font_family(self) -> str:
        return self._font_family

    def set_font_family(self, family: str) -> None:
        self._font_family = family
        self._apply_font()
        self._fit_height()

    @property
    def bold(self) -> bool:
        return self._bold

    def set_bold(self, value: bool) -> None:
        self._bold = bool(value)
        self._apply_font()
        self._fit_height()

    @property
    def italic(self) -> bool:
        return self._italic

    def set_italic(self, value: bool) -> None:
        self._italic = bool(value)
        self._apply_font()
        self._fit_height()

    @property
    def underline(self) -> bool:
        return self._underline

    def set_underline(self, value: bool) -> None:
        self._underline = bool(value)
        self._apply_font()
        self._fit_height()

    @property
    def alignment_name(self) -> str:
        return self._alignment

    def set_alignment(self, name: str) -> None:
        if name not in ALIGNMENTS:
            return
        self._alignment = name
        self._apply_font()
        self._fit_height()

    # ------------------------------------------------------------------ geometry
    def set_size(self, width: float, height: float) -> None:
        if getattr(self, "_fitting", False):
            super().set_size(width, height)
            return
        super().set_size(width, height)
        if hasattr(self, "_editor"):
            self._editor.setTextWidth(max(20.0, self._w - PADDING * 2.0))
            self._fit_height()

    def _fit_height(self) -> None:
        if self._fitting or not hasattr(self, "_editor"):
            return
        doc_height = self._editor.document().size().height()
        new_height = max(30.0, doc_height + PADDING * 2.0)
        if abs(new_height - self._h) > 0.5:
            self._fitting = True
            try:
                super().set_size(self._w, new_height)
            finally:
                self._fitting = False
            self.update()

    def _content_changed(self) -> None:
        if self._editing:
            self._fit_height()
        self.update()

    # ------------------------------------------------------------------ painting
    def paint_content(self, painter: QPainter) -> None:
        if not self.text.strip() and not self._editing:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(self._text_color.lighter(145), 1))
            font = QFont(self._font_family, int(self._font_size))
            font.setItalic(True)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(PADDING, PADDING, -PADDING, -PADDING),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                "Text",
            )
            painter.restore()

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
        self._fit_height()
        scene = self.scene()
        if scene is not None and self._edit_before is not None:
            scene.push_state([self], self._edit_before, "Edit text")
        self._edit_before = None
        self.update()

    # ------------------------------------------------------------------ state
    def _extra_state(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "text_color": self._text_color.name(QColor.NameFormat.HexArgb),
            "font_family": self._font_family,
            "font_size": self._font_size,
            "bold": self._bold,
            "italic": self._italic,
            "underline": self._underline,
            "alignment": self._alignment,
        }

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        if "text_color" in state:
            self._text_color = QColor(state["text_color"])
        if "font_family" in state:
            self._font_family = state["font_family"]
        if "font_size" in state:
            self._font_size = float(state["font_size"])
        if "bold" in state:
            self._bold = bool(state["bold"])
        if "italic" in state:
            self._italic = bool(state["italic"])
        if "underline" in state:
            self._underline = bool(state["underline"])
        if "alignment" in state:
            self._alignment = state["alignment"]
        if "text" in state and state["text"] != self.text:
            self._editor.setPlainText(state["text"])
        self._apply_font()
        self._fit_height()

    def _extra_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "text_color": self._text_color.name(QColor.NameFormat.HexArgb),
            "font_family": self._font_family,
            "font_size": self._font_size,
            "bold": self._bold,
            "italic": self._italic,
            "underline": self._underline,
            "alignment": self._alignment,
        }
