"""Interactive to-do checklist cards."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from ..config import DEFAULT_FILL, DEFAULT_FONT, DEFAULT_TEXT
from .base import BoardItem
from .editing import InlineLineEditor

PADDING = 14.0
TITLE_TOP = 11.0
TITLE_HEIGHT = 24.0
PROGRESS_TOP = 39.0
PROGRESS_HEIGHT = 4.0
ROW_TOP = 54.0
ROW_HEIGHT = 34.0
FOOTER_HEIGHT = 38.0
BOTTOM_PADDING = 8.0
MIN_WIDTH = 220.0
CHECKBOX_SIZE = 18.0
TEXT_OFFSET = 30.0
DELETE_WIDTH = 24.0
DEFAULT_TITLE = "To-do"
DEFAULT_FONT_SIZE = 14.0
MAX_FONT_SIZE = 22.0


class ChecklistItem(BoardItem):
    """A small, interactive to-do card that lives on the board.

    Click a checkbox to complete a task, click the footer to add a task, click
    the row's × to remove it, and double-click text to edit it. Task changes
    made through the canvas are captured by the scene's normal interaction
    undo, while inline edits push their own state command.
    """

    TYPE = "checklist"
    SUPPORTS_FILL = True
    SUPPORTS_TEXT = True
    RESIZE_AXES = "x"

    def __init__(
        self,
        width: float = 320.0,
        title: str = DEFAULT_TITLE,
        tasks: list[dict[str, Any]] | None = None,
        color: str | QColor = DEFAULT_FILL,
        text_color: str | QColor = DEFAULT_TEXT,
        font_size: float = DEFAULT_FONT_SIZE,
    ) -> None:
        super().__init__()
        self._title = str(title or DEFAULT_TITLE)
        self._tasks = self._sanitise_tasks(tasks or [])
        self._color = QColor(color)
        self._text_color = QColor(text_color)
        self._font_size = max(8.0, min(MAX_FONT_SIZE, float(font_size)))

        self._editing_title = False
        self._editing_new = False
        self._editing_index: int | None = None
        self._edit_before: dict[str, Any] | None = None
        self._interactive_press = False

        self._editor = InlineLineEditor(self)
        self._editor.setZValue(10.0)
        self._editor.setVisible(False)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.document().setDocumentMargin(0.0)
        option = self._editor.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._editor.document().setDefaultTextOption(option)

        self.set_size(width, 0.0)

    # ------------------------------------------------------------------ data
    @staticmethod
    def _sanitise_tasks(tasks: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not isinstance(tasks, list):
            return result
        for raw in tasks:
            if isinstance(raw, dict):
                text = str(raw.get("text", "")).strip()
                done = bool(raw.get("done", False))
            elif isinstance(raw, str):
                text = raw.strip()
                done = False
            else:
                continue
            result.append({"text": text, "done": done})
        return result

    @property
    def title(self) -> str:
        return self._title

    def set_title(self, title: str) -> None:
        self._title = str(title).strip() or DEFAULT_TITLE
        self.update()

    @property
    def tasks(self) -> list[dict[str, Any]]:
        return [dict(task) for task in self._tasks]

    @property
    def done_count(self) -> int:
        return sum(1 for task in self._tasks if task["done"])

    @property
    def total_count(self) -> int:
        return len(self._tasks)

    def add_task(self, text: str = "", done: bool = False) -> int:
        self._tasks.append({"text": str(text).strip(), "done": bool(done)})
        self._fit_height()
        self.update()
        return len(self._tasks) - 1

    def remove_task(self, index: int) -> None:
        if not 0 <= index < len(self._tasks):
            return
        if self._editing_index == index:
            self._cancel_edit_ui()
        elif self._editing_index is not None and self._editing_index > index:
            self._editing_index -= 1
        del self._tasks[index]
        self._fit_height()
        self.update()

    def set_task_text(self, index: int, text: str) -> None:
        if 0 <= index < len(self._tasks):
            self._tasks[index]["text"] = str(text).strip()
            self.update()

    def set_task_done(self, index: int, done: bool) -> None:
        if 0 <= index < len(self._tasks):
            self._tasks[index]["done"] = bool(done)
            self.update()

    def toggle_task(self, index: int) -> None:
        if 0 <= index < len(self._tasks):
            self._tasks[index]["done"] = not self._tasks[index]["done"]
            self.update()

    # ------------------------------------------------------------------ appearance
    @property
    def fill(self) -> QColor:
        return QColor(self._color)

    def set_fill(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    @property
    def text_color(self) -> QColor:
        return QColor(self._text_color)

    def set_text_color(self, color: QColor) -> None:
        self._text_color = QColor(color)
        self._editor.setDefaultTextColor(self._text_color)
        self.update()

    @property
    def font_size(self) -> float:
        return self._font_size

    def set_font_size(self, size: float) -> None:
        self._font_size = max(8.0, min(MAX_FONT_SIZE, float(size)))
        self.update()

    # ------------------------------------------------------------------ geometry
    def _row_top(self, index: int) -> float:
        return ROW_TOP + index * ROW_HEIGHT

    def _visible_row_count(self) -> int:
        return len(self._tasks) + (1 if self._editing_new else 0)

    @staticmethod
    def _height_for_rows(rows: int) -> float:
        return ROW_TOP + max(1, rows) * ROW_HEIGHT + FOOTER_HEIGHT + BOTTOM_PADDING

    def _computed_height(self) -> float:
        return self._height_for_rows(self._visible_row_count())

    def _state_tasks(self) -> list[dict[str, Any]]:
        tasks = [{"text": task["text"], "done": task["done"]} for task in self._tasks]
        if self._editing_new:
            text = self._editor_value()
            if text:
                tasks.append({"text": text, "done": False})
        elif self._editing_index is not None and 0 <= self._editing_index < len(tasks):
            tasks[self._editing_index]["text"] = self._editor_value()
        return tasks

    def _state_title(self) -> str:
        if self._editing_title:
            return self._editor_value() or DEFAULT_TITLE
        return self._title or DEFAULT_TITLE

    def _state_height(self) -> float:
        return self._height_for_rows(len(self._state_tasks()))

    def set_size(self, width: float, height: float) -> None:
        width = max(MIN_WIDTH, float(width))
        super().set_size(width, self._computed_height())

    def _fit_height(self) -> None:
        super().set_size(self._w, self._computed_height())

    def capture_state(self) -> dict[str, Any]:
        # Keep the state stable while a new task row is being edited: an empty
        # draft row must not create an undo step of its own.
        state = super().capture_state()
        state["size"] = [self._w, self._state_height()]
        return state

    # ------------------------------------------------------------------ layout helpers
    def _title_text_rect(self) -> QRectF:
        return QRectF(PADDING, TITLE_TOP, max(40.0, self._w - PADDING * 2 - 96.0), TITLE_HEIGHT)

    def _progress_text_rect(self) -> QRectF:
        return QRectF(self._w - PADDING - 90.0, TITLE_TOP, 90.0, TITLE_HEIGHT)

    def _progress_bar_rect(self) -> QRectF:
        return QRectF(PADDING, PROGRESS_TOP, max(20.0, self._w - PADDING * 2), PROGRESS_HEIGHT)

    def _checkbox_rect(self, index: int) -> QRectF:
        top = self._row_top(index) + (ROW_HEIGHT - CHECKBOX_SIZE) / 2.0
        return QRectF(PADDING, top, CHECKBOX_SIZE, CHECKBOX_SIZE)

    def _delete_rect(self, index: int) -> QRectF:
        size = 18.0
        top = self._row_top(index) + (ROW_HEIGHT - size) / 2.0
        return QRectF(self._w - PADDING - size, top, size, size)

    def _task_text_rect(self, index: int) -> QRectF:
        left = PADDING + TEXT_OFFSET
        return QRectF(
            left,
            self._row_top(index) + 6.0,
            max(20.0, self._w - left - DELETE_WIDTH - PADDING),
            ROW_HEIGHT - 12.0,
        )

    def _footer_top(self) -> float:
        return ROW_TOP + max(1, self._visible_row_count()) * ROW_HEIGHT

    def _add_rect(self) -> QRectF:
        return QRectF(PADDING, self._footer_top(), self._w - PADDING * 2, FOOTER_HEIGHT)

    def _task_text_at(self, pos: QPointF) -> int | None:
        for index in range(self._visible_row_count()):
            if self._task_text_rect(index).contains(pos):
                return index
        return None

    def _checkbox_at(self, pos: QPointF) -> int | None:
        for index in range(len(self._tasks)):
            if self._checkbox_rect(index).adjusted(-4, -4, 4, 4).contains(pos):
                return index
        return None

    def _delete_at(self, pos: QPointF) -> int | None:
        for index in range(len(self._tasks)):
            if self._delete_rect(index).adjusted(-4, -4, 4, 4).contains(pos):
                return index
        return None

    def _add_at(self, pos: QPointF) -> bool:
        return self._add_rect().contains(pos)

    def _title_at(self, pos: QPointF) -> bool:
        return 0.0 <= pos.y() < ROW_TOP and PADDING - 4 <= pos.x() <= self._w - PADDING + 4

    # ------------------------------------------------------------------ painting
    def _title_font(self) -> QFont:
        font = QFont(DEFAULT_FONT, max(9, int(round(self._font_size + 2.0))))
        font.setBold(True)
        return font

    def _task_font(self, done: bool = False) -> QFont:
        font = QFont(DEFAULT_FONT, max(8, int(round(self._font_size))))
        font.setStrikeOut(done)
        return font

    def _progress_font(self) -> QFont:
        return QFont(DEFAULT_FONT, max(7, int(round(self._font_size - 4.0))))

    def _muted(self, alpha: int = 150) -> QColor:
        color = QColor(self._text_color)
        color.setAlpha(alpha)
        return color

    def _paint_edit_highlight(self, painter: QPainter, rect: QRectF) -> None:
        accent = self._accent()
        accent.setAlpha(30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(rect.adjusted(-2.0, -1.0, 2.0, 1.0), 4.0, 4.0)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()

        shadow = QRectF(rect).translated(2.5, 3.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 24))
        painter.drawRoundedRect(shadow, 9.0, 9.0)

        border = QColor(self._text_color)
        border.setAlpha(45)
        painter.setBrush(self._color)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 9.0, 9.0)

        painter.save()
        try:
            clip = QPainterPath()
            clip.addRoundedRect(rect.adjusted(1.0, 1.0, -1.0, -1.0), 8.0, 8.0)
            painter.setClipPath(clip)
            self._paint_header(painter)
            self._paint_tasks(painter)
            self._paint_footer(painter)
        finally:
            painter.restore()

    def _paint_header(self, painter: QPainter) -> None:
        if self._editing_title:
            self._paint_edit_highlight(painter, self._title_text_rect())
        else:
            title = self._state_title()
            painter.setFont(self._title_font())
            painter.setPen(self._text_color)
            metrics = QFontMetrics(self._title_font())
            title_rect = self._title_text_rect()
            elided = metrics.elidedText(
                title, Qt.TextElideMode.ElideRight, int(title_rect.width())
            )
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided,
            )

        tasks = self._state_tasks()
        total = len(tasks)
        done = sum(1 for task in tasks if task["done"])
        progress = f"{done} of {total} done" if total else "No tasks"
        painter.setFont(self._progress_font())
        painter.setPen(self._muted(160))
        painter.drawText(
            self._progress_text_rect(),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            progress,
        )

        bar = self._progress_bar_rect()
        track = QColor(self._text_color)
        track.setAlpha(30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(bar, 2.0, 2.0)
        if total:
            fill_width = bar.width() * done / total
            if fill_width > 0.0:
                painter.setBrush(self._accent())
                painter.drawRoundedRect(
                    QRectF(bar.left(), bar.top(), fill_width, bar.height()), 2.0, 2.0
                )

    def _paint_tasks(self, painter: QPainter) -> None:
        if not self._tasks and not self._editing_new:
            painter.setFont(self._task_font())
            painter.setPen(self._muted(140))
            painter.drawText(
                self._task_text_rect(0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "No tasks yet",
            )
            return

        for index, task in enumerate(self._tasks):
            done = bool(task["done"])
            box = self._checkbox_rect(index)
            if done:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._accent())
                painter.drawRoundedRect(box, 4.0, 4.0)
                check_pen = QPen(QColor("#ffffff"), 1.8)
                check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(check_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                points = QPolygonF(
                    [
                        QPointF(box.left() + 4.0, box.center().y()),
                        QPointF(box.left() + 7.5, box.bottom() - 4.5),
                        QPointF(box.right() - 3.5, box.top() + 4.5),
                    ]
                )
                painter.drawPolyline(points)
            else:
                box_border = QColor(self._text_color)
                box_border.setAlpha(110)
                painter.setPen(QPen(box_border, 1.2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(box, 4.0, 4.0)

            text_rect = self._task_text_rect(index)
            if self._editing_index == index:
                self._paint_edit_highlight(painter, text_rect)
            else:
                font = self._task_font(done)
                painter.setFont(font)
                painter.setPen(self._muted(135) if done else self._text_color)
                metrics = QFontMetrics(font)
                elided = metrics.elidedText(
                    str(task["text"]),
                    Qt.TextElideMode.ElideRight,
                    int(text_rect.width()),
                )
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    elided,
                )

            delete_rect = self._delete_rect(index)
            delete_color = QColor(self._text_color)
            delete_color.setAlpha(90)
            delete_pen = QPen(delete_color, 1.4)
            delete_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(delete_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            center = delete_rect.center()
            delta = 4.0
            painter.drawLine(
                QPointF(center.x() - delta, center.y() - delta),
                QPointF(center.x() + delta, center.y() + delta),
            )
            painter.drawLine(
                QPointF(center.x() + delta, center.y() - delta),
                QPointF(center.x() - delta, center.y() + delta),
            )

        if self._editing_new:
            index = len(self._tasks)
            box = self._checkbox_rect(index)
            box_border = QColor(self._text_color)
            box_border.setAlpha(110)
            painter.setPen(QPen(box_border, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box, 4.0, 4.0)
            self._paint_edit_highlight(painter, self._task_text_rect(index))

    def _paint_footer(self, painter: QPainter) -> None:
        footer_top = self._footer_top()
        separator = QColor(self._text_color)
        separator.setAlpha(28)
        painter.setPen(QPen(separator, 1.0))
        painter.drawLine(
            QPointF(PADDING, footer_top), QPointF(self._w - PADDING, footer_top)
        )

        accent = self._accent()
        plus_center = QPointF(PADDING + 9.0, footer_top + FOOTER_HEIGHT / 2.0)
        plus_pen = QPen(accent, 1.8)
        plus_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(plus_pen)
        painter.drawLine(
            QPointF(plus_center.x() - 4.5, plus_center.y()),
            QPointF(plus_center.x() + 4.5, plus_center.y()),
        )
        painter.drawLine(
            QPointF(plus_center.x(), plus_center.y() - 4.5),
            QPointF(plus_center.x(), plus_center.y() + 4.5),
        )
        painter.setFont(self._task_font())
        painter.setPen(accent)
        painter.drawText(
            QRectF(PADDING + 22.0, footer_top, self._w - PADDING * 2 - 22.0, FOOTER_HEIGHT),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Add task",
        )

    # ------------------------------------------------------------------ editing
    def _is_editing(self) -> bool:
        return self._editing_title or self._editing_new or self._editing_index is not None

    def is_editing(self) -> bool:
        return self._is_editing()

    def _editor_value(self) -> str:
        return self._editor.toPlainText().strip()

    def _show_editor(self) -> None:
        self._editor.setVisible(True)
        self._editor.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self._editor.setFocus(Qt.FocusReason.MouseFocusReason)

    def _select_all(self) -> None:
        cursor = self._editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self._editor.setTextCursor(cursor)

    def begin_edit(self) -> None:
        self.begin_title_edit()

    def begin_title_edit(self) -> None:
        if self._is_editing():
            self.finish_edit()
        self._edit_before = self.capture_state()
        self._editing_title = True
        self._editing_new = False
        self._editing_index = None
        rect = self._title_text_rect()
        self._editor.setFont(self._title_font())
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.setTextWidth(max(40.0, rect.width()))
        self._editor.setPlainText(self._title)
        self._editor.setPos(rect.topLeft())
        self._show_editor()
        self._select_all()
        self.update()

    def begin_task_edit(self, index: int) -> None:
        if not 0 <= index < len(self._tasks):
            return
        if self._is_editing():
            self.finish_edit()
        self._edit_before = self.capture_state()
        self._editing_title = False
        self._editing_new = False
        self._editing_index = index
        rect = self._task_text_rect(index)
        self._editor.setFont(self._task_font(False))
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.setTextWidth(max(20.0, rect.width()))
        self._editor.setPlainText(self._tasks[index]["text"])
        self._editor.setPos(rect.topLeft())
        self._show_editor()
        self._select_all()
        self.update()

    def begin_new_task_edit(self) -> None:
        if self._is_editing():
            self.finish_edit()
        self._edit_before = self.capture_state()
        self._editing_title = False
        self._editing_new = True
        self._editing_index = None
        self._fit_height()
        rect = self._task_text_rect(len(self._tasks))
        self._editor.setFont(self._task_font(False))
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.setTextWidth(max(20.0, rect.width()))
        self._editor.setPlainText("")
        self._editor.setPos(rect.topLeft())
        self._show_editor()
        self.update()

    def _cancel_edit_ui(self) -> None:
        self._editing_title = False
        self._editing_new = False
        self._editing_index = None
        self._edit_before = None
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._editor.setVisible(False)
        self._editor.clearFocus()

    def finish_edit(self) -> None:
        if not self._is_editing():
            return
        title_edit = self._editing_title
        new_edit = self._editing_new
        index = self._editing_index
        text = self._editor_value()

        if title_edit:
            self._title = text or DEFAULT_TITLE
        elif new_edit:
            if text:
                self._tasks.append({"text": text, "done": False})
        elif index is not None and 0 <= index < len(self._tasks):
            self._tasks[index]["text"] = text

        before = self._edit_before
        self._editing_title = False
        self._editing_new = False
        self._editing_index = None
        self._edit_before = None
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._editor.setVisible(False)
        self._editor.clearFocus()
        self._fit_height()
        self.update()

        scene = self.scene()
        if scene is not None and before is not None:
            if title_edit:
                label = "Edit checklist title"
            elif new_edit:
                label = "Add checklist task"
            else:
                label = "Edit checklist task"
            scene.push_state([self], before, label)

    # ------------------------------------------------------------------ input
    def _select_self(self) -> None:
        if self.isSelected():
            return
        scene = self.scene()
        if scene is not None:
            scene.clearSelection()
        self.setSelected(True)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._handle_at(event.pos()):
            super().mousePressEvent(event)
            return
        if self._is_editing():
            self.finish_edit()

        pos = event.pos()
        checkbox = self._checkbox_at(pos)
        delete = self._delete_at(pos)
        add = self._add_at(pos)
        if checkbox is None and delete is None and not add:
            super().mousePressEvent(event)
            return

        self._select_self()
        self._interactive_press = True
        if checkbox is not None:
            self.toggle_task(checkbox)
        elif delete is not None:
            self.remove_task(delete)
        else:
            self.begin_new_task_edit()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._interactive_press:
            self._interactive_press = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._handle_at(event.pos()):
            if self._is_editing():
                self.finish_edit()
            index = self._task_text_at(event.pos())
            if index is not None and index < len(self._tasks):
                self._select_self()
                self.begin_task_edit(index)
                event.accept()
                return
            if self._title_at(event.pos()):
                self._select_self()
                self.begin_title_edit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def hoverMoveEvent(self, event: Any) -> None:
        super().hoverMoveEvent(event)
        if self._handle_at(event.pos()):
            return
        pos = event.pos()
        if (
            self._checkbox_at(pos) is not None
            or self._delete_at(pos) is not None
            or self._add_at(pos)
        ):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._task_text_at(pos) is not None or self._title_at(pos):
            self.setCursor(Qt.CursorShape.IBeamCursor)

    # ------------------------------------------------------------------ state
    def _extra_state(self) -> dict[str, Any]:
        return {
            "title": self._state_title(),
            "tasks": self._state_tasks(),
            "fill": self._color.name(QColor.NameFormat.HexArgb),
            "text_color": self._text_color.name(QColor.NameFormat.HexArgb),
            "font_size": self._font_size,
        }

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        self._cancel_edit_ui()
        if "title" in state:
            self._title = str(state["title"]).strip() or DEFAULT_TITLE
        if "tasks" in state:
            self._tasks = self._sanitise_tasks(state["tasks"])
        if "fill" in state:
            self._color = QColor(state["fill"])
        if "text_color" in state:
            self._text_color = QColor(state["text_color"])
        if "font_size" in state:
            self._font_size = max(
                8.0, min(MAX_FONT_SIZE, float(state["font_size"]))
            )
        self._fit_height()
        self.update()

    def _extra_dict(self) -> dict[str, Any]:
        return self._extra_state()
