"""Rectangles, ellipses, lines and arrows."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF

from ..config import DEFAULT_FILL, DEFAULT_STROKE
from .base import BoardItem


def _qcolor(value: str | QColor) -> QColor:
    return QColor(value) if isinstance(value, str) else QColor(value)


class ShapeItem(BoardItem):
    SUPPORTS_FILL = True
    SUPPORTS_STROKE = True

    def __init__(
        self,
        width: float = 160.0,
        height: float = 100.0,
        fill: str | QColor = DEFAULT_FILL,
        stroke: str | QColor = DEFAULT_STROKE,
        stroke_width: float = 2.0,
    ) -> None:
        super().__init__()
        self.set_size(width, height)
        self._fill = _qcolor(fill)
        self._stroke = _qcolor(stroke)
        self._stroke_width = float(stroke_width)

    # ------------------------------------------------------------------ style access
    @property
    def fill(self) -> QColor:
        return self._fill

    def set_fill(self, color: QColor) -> None:
        self._fill = QColor(color)
        self.update()

    @property
    def stroke(self) -> QColor:
        return self._stroke

    def set_stroke(self, color: QColor) -> None:
        self._stroke = QColor(color)
        self.update()

    @property
    def stroke_width(self) -> float:
        return self._stroke_width

    def set_stroke_width(self, width: float) -> None:
        self._stroke_width = max(0.0, float(width))
        self.update()

    # ------------------------------------------------------------------ painting
    def _pen(self, color: QColor | None = None) -> QPen:
        pen = QPen(color or self._stroke, self._stroke_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _paint_brush(self, painter: QPainter) -> None:
        if self._fill.alpha() > 0:
            painter.setBrush(self._fill)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inset = self._stroke_width / 2.0
        r = self.rect().adjusted(inset, inset, -inset, -inset)
        if r.width() <= 0 or r.height() <= 0:
            return
        painter.setPen(self._pen())
        self._paint_brush(painter)

    # ------------------------------------------------------------------ state
    def _extra_state(self) -> dict[str, Any]:
        return {
            "fill": self._fill.name(QColor.NameFormat.HexArgb),
            "stroke": self._stroke.name(QColor.NameFormat.HexArgb),
            "stroke_width": self._stroke_width,
        }

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        if "fill" in state:
            self._fill = QColor(state["fill"])
        if "stroke" in state:
            self._stroke = QColor(state["stroke"])
        if "stroke_width" in state:
            self._stroke_width = float(state["stroke_width"])

    def _extra_dict(self) -> dict[str, Any]:
        return {
            "fill": self._fill.name(QColor.NameFormat.HexArgb),
            "stroke": self._stroke.name(QColor.NameFormat.HexArgb),
            "stroke_width": self._stroke_width,
        }


class RectItem(ShapeItem):
    TYPE = "rect"

    def paint_content(self, painter: QPainter) -> None:
        super().paint_content(painter)
        inset = self._stroke_width / 2.0
        r = self.rect().adjusted(inset, inset, -inset, -inset)
        if r.width() > 0 and r.height() > 0:
            painter.drawRect(r)


class EllipseItem(ShapeItem):
    TYPE = "ellipse"

    def paint_content(self, painter: QPainter) -> None:
        super().paint_content(painter)
        inset = self._stroke_width / 2.0
        r = self.rect().adjusted(inset, inset, -inset, -inset)
        if r.width() > 0 and r.height() > 0:
            painter.drawEllipse(r)


class LineItem(BoardItem):
    """A straight line or arrow defined by two normalised endpoints."""

    TYPE = "line"
    SUPPORTS_STROKE = True
    ARROW = False

    def __init__(
        self,
        width: float = 160.0,
        height: float = 100.0,
        start: tuple[float, float] = (0.0, 0.0),
        end: tuple[float, float] = (1.0, 1.0),
        stroke: str | QColor = DEFAULT_STROKE,
        stroke_width: float = 2.0,
    ) -> None:
        super().__init__()
        self.set_size(width, height)
        self._start = (float(start[0]), float(start[1]))
        self._end = (float(end[0]), float(end[1]))
        self._stroke = _qcolor(stroke)
        self._stroke_width = max(1.0, float(stroke_width))

    # ------------------------------------------------------------------ style
    @property
    def stroke(self) -> QColor:
        return self._stroke

    def set_stroke(self, color: QColor) -> None:
        self._stroke = QColor(color)
        self.update()

    @property
    def stroke_width(self) -> float:
        return self._stroke_width

    def set_stroke_width(self, width: float) -> None:
        self._stroke_width = max(1.0, float(width))
        self.update()

    def _points(self) -> tuple[QPointF, QPointF]:
        r = self.rect()
        p1 = QPointF(r.left() + self._start[0] * r.width(), r.top() + self._start[1] * r.height())
        p2 = QPointF(r.left() + self._end[0] * r.width(), r.top() + self._end[1] * r.height())
        return p1, p2

    def set_endpoints(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        self._start = (float(start[0]), float(start[1]))
        self._end = (float(end[0]), float(end[1]))
        self.update()

    def content_shape(self) -> QPainterPath:
        p1, p2 = self._points()
        line = QPainterPath(p1)
        line.lineTo(p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._stroke_width + 8.0, 14.0))
        return stroker.createStroke(line)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p1, p2 = self._points()
        pen = QPen(self._stroke, self._stroke_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(p1, p2)
        if self.ARROW:
            length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            if length > 2.0:
                head = min(max(12.0, self._stroke_width * 4.0), length * 0.45)
                angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
                spread = math.radians(26.0)
                a = QPointF(
                    p2.x() - head * math.cos(angle - spread),
                    p2.y() - head * math.sin(angle - spread),
                )
                b = QPointF(
                    p2.x() - head * math.cos(angle + spread),
                    p2.y() - head * math.sin(angle + spread),
                )
                painter.setBrush(self._stroke)
                painter.setPen(QPen(self._stroke, 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawPolygon(QPolygonF([p2, a, b]))

    # ------------------------------------------------------------------ state
    def _extra_state(self) -> dict[str, Any]:
        return {
            "start": list(self._start),
            "end": list(self._end),
            "stroke": self._stroke.name(QColor.NameFormat.HexArgb),
            "stroke_width": self._stroke_width,
        }

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        if "start" in state:
            self._start = tuple(float(v) for v in state["start"])  # type: ignore[assignment]
        if "end" in state:
            self._end = tuple(float(v) for v in state["end"])  # type: ignore[assignment]
        if "stroke" in state:
            self._stroke = QColor(state["stroke"])
        if "stroke_width" in state:
            self._stroke_width = float(state["stroke_width"])

    def _extra_dict(self) -> dict[str, Any]:
        return {
            "start": list(self._start),
            "end": list(self._end),
            "stroke": self._stroke.name(QColor.NameFormat.HexArgb),
            "stroke_width": self._stroke_width,
        }


class ArrowItem(LineItem):
    TYPE = "arrow"
    ARROW = True
