"""Freehand pen and eraser tools."""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPathItem

from ..objects import BoardItem, StrokeItem
from .base import BaseTool


class PenTool(BaseTool):
    name = "pen"
    cursor = Qt.CursorShape.CrossCursor
    hint = "Draw freehand strokes"

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        self.scene.finish_editing()
        self._points = [self.scene_pos(event)]
        pen = QPen(QColor(self.scene.defaults["pen_color"]))
        pen.setWidthF(float(self.scene.defaults["pen_width"]))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._preview = QGraphicsPathItem()
        self._preview.setPen(pen)
        self._preview.setZValue(self.scene.next_z() + 1.0)
        self.scene.addItem(self._preview)
        return True

    def _path(self) -> QPainterPath:
        path = QPainterPath()
        if not self._points:
            return path
        path.moveTo(self._points[0])
        for point in self._points[1:]:
            path.lineTo(point)
        if len(self._points) == 1:
            path.lineTo(self._points[0] + QPointF(0.01, 0.01))
        return path

    def mouse_move(self, event: Any) -> bool:
        if self._preview is None:
            return False
        pos = self.scene_pos(event)
        if not self._points or (pos - self._points[-1]).manhattanLength() > 0.6:
            self._points.append(pos)
            self._preview.setPath(self._path())
        return True

    def mouse_release(self, event: Any) -> bool:
        if self._preview is None:
            return False
        preview = self._preview
        self._preview = None
        self.scene.removeItem(preview)
        points = self._points
        self._points = []
        if not points:
            return True
        item = StrokeItem.from_scene_points(
            points,
            self.scene.defaults["pen_color"],
            float(self.scene.defaults["pen_width"]),
        )
        item.setZValue(self.scene.next_z())
        self.scene.add_items([item], "Draw stroke")
        return True


def _eraser_cursor() -> QCursor:
    size = 28
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(255, 255, 255, 230), 3.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(3, 3, size - 6, size - 6))
    painter.setPen(QPen(QColor(30, 41, 59, 230), 1.2))
    painter.drawEllipse(QRectF(3, 3, size - 6, size - 6))
    painter.end()
    return QCursor(pixmap, size // 2, size // 2)


class EraserTool(BaseTool):
    name = "eraser"
    hint = "Erase objects (drag over the canvas)"

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self.cursor = Qt.CursorShape.BlankCursor
        self._cursor = _eraser_cursor()
        self._active = False
        self._removed: list[BoardItem] = []

    def activate(self) -> None:
        self.view.viewport().setCursor(self._cursor)

    def deactivate(self) -> None:
        self.view.viewport().unsetCursor()

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        self.scene.finish_editing()
        self._active = True
        self._removed = []
        self._erase_at(self.scene_pos(event))
        return True

    def mouse_move(self, event: Any) -> bool:
        if not self._active:
            return False
        self._erase_at(self.scene_pos(event))
        return True

    def mouse_release(self, event: Any) -> bool:
        if not self._active:
            return False
        self._active = False
        if self._removed:
            from ..canvas.commands import RemoveItemsCommand

            self.scene.undo_stack.push(
                RemoveItemsCommand(self.scene, self._removed, "Erase objects")
            )
            self._removed = []
        return True

    def _erase_at(self, pos: QPointF) -> None:
        scale = max(self.scene.views()[0].transform().m11(), 0.05) if self.scene.views() else 1.0
        radius = 11.0 / scale
        area = QRectF(pos.x() - radius, pos.y() - radius, radius * 2.0, radius * 2.0)
        removed_ids = {id(item) for item in self._removed}
        to_remove: list[BoardItem] = []
        for candidate in self.scene.items(area):
            item = candidate
            while item is not None and not isinstance(item, BoardItem):
                item = item.parentItem()
            if item is None or id(item) in removed_ids:
                continue
            targets: Iterable[BoardItem] = [item]
            if item.group_id:
                targets = [
                    other
                    for other in self.scene.board_items()
                    if other.group_id == item.group_id
                ]
            for target in targets:
                if id(target) not in removed_ids:
                    removed_ids.add(id(target))
                    to_remove.append(target)
        for item in to_remove:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
                self._removed.append(item)
        if to_remove:
            self.scene.selection_info_changed.emit()
