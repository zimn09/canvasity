"""Board object types and the deserialisation factory."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF

from ..config import DEFAULT_FILL, DEFAULT_STROKE, DEFAULT_TEXT
from .base import BoardItem
from .checklist_item import ChecklistItem
from .image_item import ImageItem, decode_image
from .project_item import ProjectItem
from .shape_item import ArrowItem, EllipseItem, LineItem, RectItem, ShapeItem
from .sticky_item import StickyItem
from .stroke_item import StrokeItem
from .text_item import TextItem

ITEM_TYPES: dict[str, type[BoardItem]] = {
    "rect": RectItem,
    "ellipse": EllipseItem,
    "line": LineItem,
    "arrow": ArrowItem,
    "sticky": StickyItem,
    "text": TextItem,
    "checklist": ChecklistItem,
    "project": ProjectItem,
    "stroke": StrokeItem,
    "image": ImageItem,
}


def item_from_dict(data: dict[str, Any]) -> BoardItem:
    """Rebuild an item from its serialised form."""
    kind = data.get("type")
    if kind not in ITEM_TYPES:
        raise ValueError(f"Unknown object type: {kind!r}")

    width = float(data.get("w", 120.0))
    height = float(data.get("h", 80.0))

    if kind == "rect":
        item: BoardItem = RectItem(
            width,
            height,
            data.get("fill", DEFAULT_FILL),
            data.get("stroke", DEFAULT_STROKE),
            float(data.get("stroke_width", 2.0)),
        )
    elif kind == "ellipse":
        item = EllipseItem(
            width,
            height,
            data.get("fill", DEFAULT_FILL),
            data.get("stroke", DEFAULT_STROKE),
            float(data.get("stroke_width", 2.0)),
        )
    elif kind in ("line", "arrow"):
        cls = ArrowItem if kind == "arrow" else LineItem
        item = cls(
            width,
            height,
            tuple(data.get("start", (0.0, 0.0))),
            tuple(data.get("end", (1.0, 1.0))),
            data.get("stroke", DEFAULT_STROKE),
            float(data.get("stroke_width", 2.0)),
        )
    elif kind == "sticky":
        item = StickyItem(
            width,
            height,
            data.get("text", ""),
            data.get("color", "#fde68a"),
            data.get("text_color", "#3f2d0a"),
            float(data.get("font_size", 15.0)),
        )
    elif kind == "text":
        item = TextItem(
            width,
            data.get("text", ""),
            data.get("text_color", DEFAULT_TEXT),
            data.get("font_family", "Inter"),
            float(data.get("font_size", 16.0)),
            bool(data.get("bold", False)),
            bool(data.get("italic", False)),
            bool(data.get("underline", False)),
            data.get("alignment", "left"),
        )
    elif kind == "checklist":
        item = ChecklistItem(
            width,
            data.get("title", "To-do"),
            data.get("tasks", []),
            data.get("fill", DEFAULT_FILL),
            data.get("text_color", DEFAULT_TEXT),
            float(data.get("font_size", 14.0)),
        )
    elif kind == "project":
        item = ProjectItem(
            width,
            data.get("title", "Project"),
            data.get("nodes", []),
            data.get("links", []),
            data.get("fill", DEFAULT_FILL),
            data.get("text_color", DEFAULT_TEXT),
            float(data.get("font_size", 14.0)),
        )
    elif kind == "stroke":
        points = [tuple(float(v) for v in p) for p in data.get("points", [])]
        item = StrokeItem(
            width,
            height,
            points,
            data.get("color", "#0f172a"),
            float(data.get("pen_width", 3.0)),
        )
    else:  # image
        image = decode_image(data.get("data", ""))
        from PySide6.QtGui import QPixmap

        item = ImageItem(QPixmap.fromImage(image), width, height)

    item.item_id = str(data.get("id") or item.item_id)
    item.group_id = data.get("group")
    item.setPos(QPointF(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
    item.setRotation(float(data.get("rot", 0.0)))
    item.setZValue(float(data.get("z", 0.0)))
    item.setOpacity(max(0.05, min(1.0, float(data.get("opacity", 1.0)))))
    return item


__all__ = [
    "BoardItem",
    "ShapeItem",
    "RectItem",
    "EllipseItem",
    "LineItem",
    "ArrowItem",
    "StickyItem",
    "TextItem",
    "ChecklistItem",
    "ProjectItem",
    "StrokeItem",
    "ImageItem",
    "ITEM_TYPES",
    "item_from_dict",
]
