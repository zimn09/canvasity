"""Project todo graph tool."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from ..config import DEFAULT_FILL
from ..objects import ProjectItem
from .base import BaseTool


def _readable_text_color(background: QColor) -> QColor:
    """Pick a dark or light text colour with reasonable contrast."""
    return QColor("#0f172a") if background.lightness() >= 140 else QColor("#f8fafc")


class ProjectTool(BaseTool):
    name = "project"
    cursor = Qt.CursorShape.PointingHandCursor
    hint = "Click to place a project todo graph · Drag ○ to connect todos"

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        pos = self.creation_pos(event)
        fill = QColor(self.scene.defaults["fill"])
        if not fill.isValid() or fill.alpha() == 0:
            fill = QColor(DEFAULT_FILL)
        item = ProjectItem(
            560.0,
            "Project",
            [],
            [],
            fill,
            _readable_text_color(fill),
            14.0,
        )
        item.setPos(pos)
        item.setZValue(self.scene.next_z())
        self.scene.add_items([item], "Add project")
        self.view.set_tool("select")
        item.begin_new_node_edit()
        return True
