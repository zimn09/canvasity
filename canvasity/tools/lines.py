"""Straight line and arrow tools."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt

from ..objects import ArrowItem, LineItem
from .base import BaseTool


class LineTool(BaseTool):
    name = "line"
    cursor = Qt.CursorShape.CrossCursor
    arrow = False
    label = "Line"

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._item: LineItem | None = None
        self._start: QPointF | None = None
        self._active = False

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        defaults = self.scene.defaults
        cls = ArrowItem if self.arrow else LineItem
        self._start = self.creation_pos(event)
        self._item = cls(
            1.0,
            1.0,
            (0.0, 0.0),
            (1.0, 1.0),
            defaults["stroke"],
            float(defaults["stroke_width"]),
        )
        self._item.setPos(self._start)
        self._item.setZValue(self.scene.next_z())
        self.scene.addItem(self._item)
        self._active = True
        return True

    def mouse_move(self, event: Any) -> bool:
        if not self._active or self._item is None or self._start is None:
            return False
        current = self.scene_pos(event)
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            dx = current.x() - self._start.x()
            dy = current.y() - self._start.y()
            current = (
                QPointF(current.x(), self._start.y())
                if abs(dx) >= abs(dy)
                else QPointF(self._start.x(), current.y())
            )
        rect = QRectF(self._start, current).normalized()
        width = max(rect.width(), 1.0)
        height = max(rect.height(), 1.0)
        self._item.setPos(rect.topLeft())
        self._item.set_size(width, height)
        start = (
            (self._start.x() - rect.left()) / width,
            (self._start.y() - rect.top()) / height,
        )
        end = (
            (current.x() - rect.left()) / width,
            (current.y() - rect.top()) / height,
        )
        self._item.set_endpoints(start, end)
        return True

    def mouse_release(self, event: Any) -> bool:
        if self._item is None:
            return False
        item = self._item
        self._item = None
        self._active = False
        if item.rect().width() < 5.0 and item.rect().height() < 5.0:
            item.set_size(180.0, 1.0)
            item.set_endpoints((0.0, 0.5), (1.0, 0.5))
        self.scene.commit_live_items([item], f"Draw {self.label.lower()}")
        self.view.set_tool("select")
        return True


class ArrowTool(LineTool):
    name = "arrow"
    arrow = True
    label = "Arrow"
