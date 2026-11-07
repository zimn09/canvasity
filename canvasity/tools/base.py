"""Tool interface and shared helpers."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, Qt

from ..config import GRID_SIZE


class BaseTool:
    name = "base"
    cursor = Qt.CursorShape.ArrowCursor
    hint = ""

    def __init__(self, view: Any) -> None:
        self.view = view
        self.scene = view.board_scene

    def scene_pos(self, event: Any) -> QPointF:
        return self.view.mapToScene(event.position().toPoint())

    def creation_pos(self, event: Any) -> QPointF:
        pos = self.scene_pos(event)
        if self.scene.grid_snap:
            return QPointF(
                round(pos.x() / GRID_SIZE) * GRID_SIZE,
                round(pos.y() / GRID_SIZE) * GRID_SIZE,
            )
        return pos

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def mouse_press(self, event: Any) -> bool:
        return False

    def mouse_move(self, event: Any) -> bool:
        return False

    def mouse_release(self, event: Any) -> bool:
        return False

    def mouse_double_click(self, event: Any) -> bool:
        return False

    def key_press(self, event: Any) -> bool:
        return False

    def _left_pressed(self, event: Any) -> bool:
        return event.button() == Qt.MouseButton.LeftButton
