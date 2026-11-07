"""Selection tool - delegates to QGraphicsView's built-in interaction."""

from __future__ import annotations

from PySide6.QtCore import Qt

from .base import BaseTool


class SelectTool(BaseTool):
    name = "select"
    cursor = Qt.CursorShape.ArrowCursor
    hint = "Drag to select · Space+drag to pan · Wheel to zoom"
