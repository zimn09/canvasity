"""Rectangle and ellipse creation tools."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt

from ..objects import EllipseItem, RectItem, ShapeItem
from .base import BaseTool


class ShapeTool(BaseTool):
    cursor = Qt.CursorShape.CrossCursor
    kind = "rect"
    label = "Rectangle"
    default_size = (180.0, 120.0)

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._item: ShapeItem | None = None
        self._start = None

    def _make_item(self, width: float, height: float) -> ShapeItem:
        defaults = self.scene.defaults
        cls = RectItem if self.kind == "rect" else EllipseItem
        return cls(
            width,
            height,
            defaults["fill"],
            defaults["stroke"],
            float(defaults["stroke_width"]),
        )

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        self._start = self.creation_pos(event)
        self._item = self._make_item(1.0, 1.0)
        self._item.setPos(self._start)
        self._item.setZValue(self.scene.next_z())
        self.scene.addItem(self._item)
        return True

    def mouse_move(self, event: Any) -> bool:
        if self._item is None or self._start is None:
            return False
        current = self.scene_pos(event)
        rect = QRectF(self._start, current).normalized()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            side = max(rect.width(), rect.height())
            rect = QRectF(rect.left(), rect.top(), side, side)
        self._item.setPos(rect.topLeft())
        self._item.set_size(max(rect.width(), 1.0), max(rect.height(), 1.0))
        return True

    def mouse_release(self, event: Any) -> bool:
        if self._item is None:
            return False
        item = self._item
        self._item = None
        self._start = None
        if item.rect().width() < 4.0 or item.rect().height() < 4.0:
            item.setPos(item.pos())
            item.set_size(*self.default_size)
        self.scene.commit_live_items([item], f"Draw {self.label.lower()}")
        self.view.set_tool("select")
        return True


class RectTool(ShapeTool):
    name = "rect"
    kind = "rect"
    label = "Rectangle"


class EllipseTool(ShapeTool):
    name = "ellipse"
    kind = "ellipse"
    label = "Ellipse"
