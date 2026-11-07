"""Image insertion tool (file picker) - drag & drop lives in the view."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from ..config import IMAGE_EXTENSIONS
from .base import BaseTool


class ImageTool(BaseTool):
    name = "image"
    cursor = Qt.CursorShape.PointingHandCursor
    hint = "Click to insert an image"

    def mouse_press(self, event: Any) -> bool:
        if not self._left_pressed(event):
            return False
        pos = self.scene_pos(event)
        patterns = " ".join(f"*{ext}" for ext in sorted(IMAGE_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Insert image",
            "",
            f"Images ({patterns});;All files (*)",
        )
        if path:
            self.view.insert_image(path, pos)
        self.view.set_tool("select")
        return True
