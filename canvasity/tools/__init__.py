"""Tool registry."""

from __future__ import annotations

from typing import Any

from .base import BaseTool
from .checklist import ChecklistTool
from .drawing import EraserTool, PenTool
from .image_tool import ImageTool
from .lines import ArrowTool, LineTool
from .notes import StickyTool, TextTool
from .select import SelectTool
from .shapes import EllipseTool, RectTool

TOOL_CLASSES: dict[str, type[BaseTool]] = {
    "select": SelectTool,
    "pen": PenTool,
    "eraser": EraserTool,
    "sticky": StickyTool,
    "text": TextTool,
    "checklist": ChecklistTool,
    "rect": RectTool,
    "ellipse": EllipseTool,
    "line": LineTool,
    "arrow": ArrowTool,
    "image": ImageTool,
}


def create_tool(name: str, view: Any) -> BaseTool:
    return TOOL_CLASSES.get(name, SelectTool)(view)


__all__ = ["BaseTool", "TOOL_CLASSES", "create_tool"]
