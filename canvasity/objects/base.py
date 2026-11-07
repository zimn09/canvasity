"""Base class shared by every object that lives on the board."""

from __future__ import annotations

import math
import uuid
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsSceneMouseEvent

from ..config import MIN_ITEM_SIZE

HANDLE_PX = 9.0
ROTATE_OFFSET_PX = 27.0
HANDLE_MARGIN_PX = ROTATE_OFFSET_PX + HANDLE_PX + 14.0

CORNER_HANDLES = ("nw", "ne", "se", "sw")
EDGE_HANDLES = ("n", "e", "s", "w")


class BoardItem(QGraphicsObject):
    """An undo-aware, serialisable, selectable canvas object.

    Subclasses paint their content in :meth:`paint_content` and extend the
    serialised form with :meth:`_extra_dict`.
    """

    TYPE = "item"
    SUPPORTS_FILL = False
    SUPPORTS_STROKE = False
    SUPPORTS_TEXT = False
    RESIZE_AXES = "xy"  # "xy", "x" or "" (no resize)
    ROTATABLE = True

    def __init__(self) -> None:
        super().__init__()
        self.item_id: str = uuid.uuid4().hex
        self.group_id: str | None = None
        self._w = 120.0
        self._h = 80.0
        self._transform_mode: str | None = None
        self._active_handle: str | None = None
        self._margin = 60.0
        self._handle_scale = 1.0
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(self.rect().center())

    # ------------------------------------------------------------------ geometry
    def rect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._w, self._h)

    def content_rect(self) -> QRectF:
        """Rectangle used for fit-to-content and export bounds."""
        item = self.mapToScene(self.rect())
        return item.boundingRect()

    def set_size(self, width: float, height: float) -> None:
        min_width, min_height = self.min_size()
        width = max(min_width, float(width))
        height = max(min_height, float(height))
        if abs(width - self._w) < 1e-6 and abs(height - self._h) < 1e-6:
            return
        self.prepareGeometryChange()
        self._w = width
        self._h = height
        self.setTransformOriginPoint(self.rect().center())
        self.update()

    def min_size(self) -> tuple[float, float]:
        """Minimum supported size for this item, in local coordinates."""
        return (float(MIN_ITEM_SIZE), float(MIN_ITEM_SIZE))

    def boundingRect(self) -> QRectF:
        m = self._margin
        return self.rect().adjusted(-m, -m, m, m)

    def content_shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    def shape(self) -> QPainterPath:
        path = self.content_shape()
        if self._handles_visible():
            radius = (HANDLE_PX * 0.8) / self.view_scale()
            for name, point in self._handle_points().items():
                if name == "rotate":
                    path.addEllipse(point, radius * 1.2, radius * 1.2)
                else:
                    path.addRect(
                        QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2)
                    )
        return path

    # ------------------------------------------------------------------ view / scale
    def view_scale(self) -> float:
        scene = self.scene()
        if scene is not None and scene.views():
            return max(abs(scene.views()[0].transform().m11()), 0.001)
        return 1.0

    def refresh_handles(self) -> None:
        """Keep screen-constant handle sizes while the view zooms."""
        scale = self.view_scale()
        if abs(scale - self._handle_scale) < 1e-4:
            return
        self._handle_scale = scale
        margin = HANDLE_MARGIN_PX / scale
        if abs(margin - self._margin) > 0.5:
            self.prepareGeometryChange()
            self._margin = margin
        self.update()

    def handles_visible(self) -> bool:
        return self._handles_visible()

    def _handles_visible(self) -> bool:
        scene = self.scene()
        if scene is None or getattr(scene, "export_mode", False):
            return False
        if self.group_id is not None:
            return False
        if len(scene.selectedItems()) != 1 or not self.isSelected():
            return False
        return bool(self.RESIZE_AXES) or self.ROTATABLE

    def _accent(self) -> QColor:
        scene = self.scene()
        color = getattr(scene, "selection_color", "#2563eb") if scene else "#2563eb"
        return QColor(color)

    def _handle_points(self) -> dict[str, QPointF]:
        r = self.rect()
        w, h = r.width(), r.height()
        all_points = {
            "nw": QPointF(0.0, 0.0),
            "n": QPointF(w / 2.0, 0.0),
            "ne": QPointF(w, 0.0),
            "e": QPointF(w, h / 2.0),
            "se": QPointF(w, h),
            "s": QPointF(w / 2.0, h),
            "sw": QPointF(0.0, h),
            "w": QPointF(0.0, h / 2.0),
        }
        names: tuple[str, ...]
        if self.RESIZE_AXES == "xy":
            names = CORNER_HANDLES + EDGE_HANDLES
        elif self.RESIZE_AXES == "x":
            names = ("e", "w")
        else:
            names = ()
        points = {name: all_points[name] for name in names}
        if self.ROTATABLE:
            points["rotate"] = QPointF(w / 2.0, -ROTATE_OFFSET_PX / self.view_scale())
        return points

    def _handle_at(self, pos: QPointF) -> str | None:
        if not self._handles_visible():
            return None
        grab = (HANDLE_PX * 0.9) / self.view_scale()
        for name, point in self._handle_points().items():
            if (point - pos).manhattanLength() <= grab * 1.6:
                return name
        return None

    @staticmethod
    def _handle_cursor(name: str, rotation: float) -> Qt.CursorShape:
        if name == "rotate":
            return Qt.CursorShape.CrossCursor
        base = {
            "n": 90.0,
            "ne": 45.0,
            "e": 0.0,
            "se": -45.0,
            "s": -90.0,
            "sw": -135.0,
            "w": 180.0,
            "nw": 135.0,
        }[name]
        angle = (base + rotation) % 180.0
        if angle < 22.5 or angle >= 157.5:
            return Qt.CursorShape.SizeHorCursor
        if angle < 67.5:
            return Qt.CursorShape.SizeBDiagCursor
        if angle < 112.5:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.SizeFDiagCursor

    # ------------------------------------------------------------------ painting
    def paint_content(self, painter: QPainter) -> None:  # pragma: no cover - abstract
        pass

    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        painter.save()
        try:
            self.paint_content(painter)
        finally:
            painter.restore()
        self._paint_selection(painter)

    def _paint_selection(self, painter: QPainter) -> None:
        if not self.isSelected() or getattr(self.scene(), "export_mode", False):
            return
        if self.scene() is None:
            return
        scale = self.view_scale()
        accent = self._accent()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._handles_visible():
            pen = QPen(accent, 1.2 / scale, Qt.PenStyle.DashLine)
            pen.setDashPattern([4.0, 3.0])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect())
            painter.restore()
            return

        painter.setPen(QPen(accent, 1.15 / scale))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())

        size = HANDLE_PX / scale
        handle_brush = QBrush(QColor("#ffffff"))
        for name, point in self._handle_points().items():
            if name == "rotate":
                center = QPointF(self.rect().width() / 2.0, 0.0)
                painter.setPen(QPen(accent, 1.0 / scale))
                painter.drawLine(center, point)
                painter.setBrush(handle_brush)
                painter.setPen(QPen(accent, 1.4 / scale))
                radius = (HANDLE_PX * 0.62) / scale
                painter.drawEllipse(point, radius, radius)
            else:
                painter.setBrush(handle_brush)
                painter.setPen(QPen(accent, 1.2 / scale))
                painter.drawRect(
                    QRectF(
                        point.x() - size / 2.0,
                        point.y() - size / 2.0,
                        size,
                        size,
                    )
                )
        painter.restore()

    # ------------------------------------------------------------------ input
    def hoverMoveEvent(self, event: Any) -> None:
        handle = self._handle_at(event.pos())
        if handle:
            self.setCursor(QCursor(self._handle_cursor(handle, self.rotation())))
        elif self.isSelected() and self._handles_visible():
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: Any) -> None:
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._handle_at(event.pos())
            if handle:
                self._transform_mode = "rotate" if handle == "rotate" else "resize"
                self._active_handle = handle
                self._start_rect = self.rect()
                self._start_pos = self.pos()
                self._start_rotation = self.rotation()
                self._start_local = self.mapFromScene(event.scenePos())
                center = self.mapToScene(self.rect().center())
                self._start_angle = math.degrees(
                    math.atan2(
                        event.scenePos().y() - center.y(), event.scenePos().x() - center.x()
                    )
                )
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._transform_mode == "resize" and self._active_handle:
            self._apply_resize(event.scenePos())
            event.accept()
            return
        if self._transform_mode == "rotate":
            center = self.mapToScene(self.rect().center())
            angle = math.degrees(
                math.atan2(
                    event.scenePos().y() - center.y(), event.scenePos().x() - center.x()
                )
            )
            rotation = self._start_rotation + (angle - self._start_angle)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                rotation = round(rotation / 15.0) * 15.0
            self.setRotation(rotation % 360.0)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._transform_mode = None
        self._active_handle = None
        super().mouseReleaseEvent(event)

    def _apply_resize(self, scene_pos: QPointF) -> None:
        handle = self._active_handle
        if not handle:
            return
        local = self.mapFromScene(scene_pos)
        delta = local - self._start_local
        w0 = self._start_rect.width()
        h0 = self._start_rect.height()
        min_width, min_height = self.min_size()
        dx = 0.0
        dy = 0.0
        if self.RESIZE_AXES in ("xy", "x"):
            if "e" in handle:
                dx = max(delta.x(), min_width - w0)
            elif "w" in handle:
                dx = min(delta.x(), w0 - min_width)
        if self.RESIZE_AXES == "xy":
            if "s" in handle:
                dy = max(delta.y(), min_height - h0)
            elif "n" in handle:
                dy = min(delta.y(), h0 - min_height)

        new_w = w0 + dx if "e" in handle else w0 - dx if "w" in handle else w0
        new_h = h0 + dy if "s" in handle else h0 - dy if "n" in handle else h0
        new_w = max(min_width, new_w)
        new_h = max(min_height, new_h)

        # Keep the opposite edge/corner fixed in scene space, accounting for rotation.
        ax = 0.0 if "e" in handle else w0 if "w" in handle else w0 / 2.0
        ay = 0.0 if "s" in handle else h0 if "n" in handle else h0 / 2.0
        bx = 0.0 if "e" in handle else new_w if "w" in handle else new_w / 2.0
        by = 0.0 if "s" in handle else new_h if "n" in handle else new_h / 2.0
        c0 = QPointF(w0 / 2.0, h0 / 2.0)
        c1 = QPointF(new_w / 2.0, new_h / 2.0)
        rad = math.radians(self._start_rotation)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        vx = (ax - c0.x()) - (bx - c1.x())
        vy = (ay - c0.y()) - (by - c1.y())
        rot_x = vx * cos_a - vy * sin_a
        rot_y = vx * sin_a + vy * cos_a
        pos = QPointF(
            self._start_pos.x() + (c0.x() - c1.x()) + rot_x,
            self._start_pos.y() + (c0.y() - c1.y()) + rot_y,
        )
        self.set_size(new_w, new_h)
        self.setPos(pos)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene = self.scene()
            if (
                scene is not None
                and self._transform_mode is None
                and not getattr(scene, "applying_command", False)
            ):
                value = scene.snap_position(self, value)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    # ------------------------------------------------------------------ state
    def capture_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "pos": [self.pos().x(), self.pos().y()],
            "rot": self.rotation(),
            "size": [self._w, self._h],
            "z": self.zValue(),
            "opacity": self.opacity(),
            "group": self.group_id,
        }
        state.update(self._extra_state())
        return state

    def restore_state(self, state: dict[str, Any]) -> None:
        self.group_id = state.get("group")
        self.set_opacity_quiet(float(state.get("opacity", 1.0)))
        self.set_size(float(state["size"][0]), float(state["size"][1]))
        self.setRotation(float(state.get("rot", 0.0)))
        self.setPos(QPointF(float(state["pos"][0]), float(state["pos"][1])))
        self.setZValue(float(state.get("z", 0.0)))
        self._apply_extra_state(state)
        self.update()

    def set_opacity_quiet(self, value: float) -> None:
        self.setOpacity(max(0.05, min(1.0, value)))

    def _extra_state(self) -> dict[str, Any]:
        return {}

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        pass

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.item_id,
            "type": self.TYPE,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "w": self._w,
            "h": self._h,
            "rot": self.rotation(),
            "z": self.zValue(),
            "opacity": self.opacity(),
            "group": self.group_id,
        }
        data.update(self._extra_dict())
        return data

    def _extra_dict(self) -> dict[str, Any]:
        return {}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _color_to_hex(color: QColor) -> str:
        return color.name(QColor.NameFormat.HexArgb) if color.alpha() < 255 else color.name()

    def context_menu_actions(self) -> list[tuple[str, Any]]:
        return []
