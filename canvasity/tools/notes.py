"""Sticky note tool."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, Qt

from ..objects import StickyItem, TextItem
from ..objects.sticky_item import STICKY_TEXT
from .base import BaseTool


class StickyTool(BaseTool):
    name = "sticky"
    cursor = Qt.CursorShape.PointingHandCursor
    hint = "Click to place a sticky note"

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        pos = self.creation_pos(event)
        item = StickyItem(
            220.0,
            180.0,
            "",
            self.scene.defaults["sticky_color"],
            STICKY_TEXT,
            15.0,
        )
        item.setPos(pos)
        item.setZValue(self.scene.next_z())
        self.scene.add_items([item], "Add sticky note")
        self.view.set_tool("select")
        item.begin_edit()
        return True


class TextTool(BaseTool):
    name = "text"
    cursor = Qt.CursorShape.IBeamCursor
    hint = "Click to place a text box"

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        pos = self.creation_pos(event)
        item = TextItem(
            280.0,
            "",
            self.scene.defaults["text_color"],
            self.scene.defaults["font_family"],
            float(self.scene.defaults["font_size"]),
        )
        item.setPos(QPointF(pos.x(), pos.y()))
        item.setZValue(self.scene.next_z())
        self.scene.add_items([item], "Add text box")
        self.view.set_tool("select")
        item.begin_edit()
        return True
