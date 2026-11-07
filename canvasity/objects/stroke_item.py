"""Freehand pen strokes."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen

from .base import BoardItem


class StrokeItem(BoardItem):
    TYPE = "stroke"
    SUPPORTS_STROKE = True

    def __init__(
        self,
        width: float = 100.0,
        height: float = 100.0,
        points: list[tuple[float, float]] | None = None,
        color: str | QColor = "#0f172a",
        pen_width: float = 3.0,
    ) -> None:
        super().__init__()
        self._points = list(points or [(0.0, 0.0), (1.0, 1.0)])
        self._color = QColor(color)
        self._pen_width = max(0.5, float(pen_width))
        self._cached_path: QPainterPath | None = None
        self._cached_key: tuple[float, float] | None = None
        self.set_size(width, height)

    @classmethod
    def from_scene_points(
        cls,
        points: list[QPointF],
        color: str | QColor,
        pen_width: float,
    ) -> "StrokeItem":
        if not points:
            points = [QPointF(0.0, 0.0), QPointF(0.0, 0.0)]
        xs = [p.x() for p in points]
        ys = [p.y() for p in points]
        left, top = min(xs), min(ys)
        width = max(max(xs) - left, 1.0)
        height = max(max(ys) - top, 1.0)
        normalized = [((p.x() - left) / width, (p.y() - top) / height) for p in points]
        item = cls(width=width, height=height, points=normalized, color=color, pen_width=pen_width)
        item.setPos(left, top)
        return item

    # ------------------------------------------------------------------ style
    @property
    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    @property
    def pen_width(self) -> float:
        return self._pen_width

    def set_pen_width(self, width: float) -> None:
        self._pen_width = max(0.5, float(width))
        self.update()

    # Aliases so the properties panel can treat strokes uniformly with shapes.
    @property
    def stroke(self) -> QColor:
        return self._color

    def set_stroke(self, color: QColor) -> None:
        self.set_color(color)

    @property
    def stroke_width(self) -> float:
        return self._pen_width

    def set_stroke_width(self, width: float) -> None:
        self.set_pen_width(width)

    # ------------------------------------------------------------------ path
    def set_size(self, width: float, height: float) -> None:
        super().set_size(width, height)
        self._cached_path = None

    def _path(self) -> QPainterPath:
        key = (self._w, self._h)
        if self._cached_path is not None and self._cached_key == key:
            return self._cached_path
        pts = [QPointF(x * self._w, y * self._h) for x, y in self._points]
        path = QPainterPath()
        if len(pts) == 1:
            path.moveTo(pts[0])
            path.lineTo(pts[0] + QPointF(0.01, 0.0))
        else:
            path.moveTo(pts[0])
            if len(pts) == 2:
                path.lineTo(pts[1])
            else:
                for i in range(1, len(pts) - 1):
                    mid = QPointF(
                        (pts[i].x() + pts[i + 1].x()) / 2.0,
                        (pts[i].y() + pts[i + 1].y()) / 2.0,
                    )
                    path.quadTo(pts[i], mid)
                path.lineTo(pts[-1])
        self._cached_path = path
        self._cached_key = key
        return path

    def content_shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._pen_width + 10.0, 14.0))
        return stroker.createStroke(self._path())

    def content_rect(self) -> QRectF:
        rect = super().content_rect()
        return rect.adjusted(-self._pen_width, -self._pen_width, self._pen_width, self._pen_width)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self._color, self._pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path())

    # ------------------------------------------------------------------ state
    def _extra_state(self) -> dict[str, Any]:
        return {
            "points": [list(p) for p in self._points],
            "color": self._color.name(QColor.NameFormat.HexArgb),
            "pen_width": self._pen_width,
        }

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        if "points" in state:
            self._points = [tuple(float(v) for v in p) for p in state["points"]]
            self._cached_path = None
        if "color" in state:
            self._color = QColor(state["color"])
        if "pen_width" in state:
            self._pen_width = float(state["pen_width"])

    def _extra_dict(self) -> dict[str, Any]:
        return {
            "points": [list(p) for p in self._points],
            "color": self._color.name(QColor.NameFormat.HexArgb),
            "pen_width": self._pen_width,
        }
