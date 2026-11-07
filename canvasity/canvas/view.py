"""Infinite, zoomable canvas view with navigation and tool routing."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QKeyEvent, QPainter, QPen, QTransform, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

from ..config import (
    GRID_SIZE,
    GRID_VISIBLE_SCALE,
    IMAGE_EXTENSIONS,
    MAX_ZOOM,
    MIN_ZOOM,
    ZOOM_STEP,
)
from ..objects import ChecklistItem, ImageItem, StickyItem, TextItem
from ..theme import LIGHT, Palette
from ..tools import TOOL_CLASSES, BaseTool, create_tool
from .scene import BoardScene


class BoardView(QGraphicsView):
    zoom_changed = Signal(float)
    tool_changed = Signal(str)
    error_occurred = Signal(str)

    TOOL_KEYS = {
        Qt.Key.Key_V: "select",
        Qt.Key.Key_P: "pen",
        Qt.Key.Key_E: "eraser",
        Qt.Key.Key_S: "sticky",
        Qt.Key.Key_T: "text",
        Qt.Key.Key_C: "checklist",
        Qt.Key.Key_R: "rect",
        Qt.Key.Key_O: "ellipse",
        Qt.Key.Key_L: "line",
        Qt.Key.Key_A: "arrow",
        Qt.Key.Key_I: "image",
    }

    def __init__(self, scene: BoardScene, parent: Any = None) -> None:
        super().__init__(scene, parent)
        self.board_scene = scene
        self._palette: Palette = LIGHT
        self.show_grid = True
        self._panning = False
        self._space_held = False
        self._pan_last = QPointF()
        self._pan_drag_mode = QGraphicsView.DragMode.RubberBandDrag
        self._tool_name = "select"
        self._tool: BaseTool = create_tool("select", self)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scene().guides_changed.connect(self.viewport().update)
        self._apply_tool_cursor()

    # ------------------------------------------------------------------ theme / grid
    def set_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.board_scene.selection_color = palette.selection
        self.viewport().update()

    def set_grid_visible(self, visible: bool) -> None:
        self.show_grid = bool(visible)
        self.viewport().update()

    # ------------------------------------------------------------------ tools
    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def tool_hint(self) -> str:
        return self._tool.hint

    def set_tool(self, name: str) -> None:
        if name not in TOOL_CLASSES:
            return
        if name == self._tool_name:
            return
        self.board_scene.finish_editing()
        self._tool.deactivate()
        self._tool_name = name
        self._tool = create_tool(name, self)
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if name == "select"
            else QGraphicsView.DragMode.NoDrag
        )
        self._tool.activate()
        self._apply_tool_cursor()
        self.tool_changed.emit(name)

    def _apply_tool_cursor(self) -> None:
        if self._space_held or self._panning:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        cursor = self._tool.cursor
        if isinstance(cursor, QCursor):
            self.viewport().setCursor(cursor)
        else:
            self.viewport().setCursor(QCursor(cursor))

    # ------------------------------------------------------------------ navigation
    def current_zoom(self) -> float:
        return self.transform().m11()

    def zoom_at(self, factor: float, anchor: QPointF | None = None) -> None:
        old = self.current_zoom()
        if old <= 0:
            return
        new = min(max(old * factor, MIN_ZOOM), MAX_ZOOM)
        if abs(new - old) < 1e-9:
            return
        if anchor is None:
            anchor = QPointF(self.viewport().rect().center())
        scene_pos = self.mapToScene(anchor.toPoint())
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setTransform(QTransform().scale(new, new))
        mapped = self.mapFromScene(scene_pos)
        dx = mapped.x() - anchor.x()
        dy = mapped.y() - anchor.y()
        self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() + dx))
        self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() + dy))
        self._after_zoom()

    def zoom_in(self) -> None:
        self.zoom_at(ZOOM_STEP)

    def zoom_out(self) -> None:
        self.zoom_at(1.0 / ZOOM_STEP)

    def reset_zoom(self) -> None:
        self.zoom_at(1.0 / max(self.current_zoom(), 1e-6))

    def fit_to_content(self) -> None:
        rect = self.board_scene.content_rect(80.0)
        if rect.width() < 1.0 or rect.height() < 1.0:
            return
        viewport = self.viewport().rect()
        scale = min(
            viewport.width() / rect.width(),
            viewport.height() / rect.height(),
        ) * 0.94
        scale = min(max(scale, MIN_ZOOM), MAX_ZOOM)
        self.setTransform(QTransform().scale(scale, scale))
        self.centerOn(rect.center())
        self._after_zoom()

    def _after_zoom(self) -> None:
        self.board_scene.update_handle_scale()
        self.viewport().update()
        self.zoom_changed.emit(self.current_zoom())

    # ------------------------------------------------------------------ panning
    def _begin_pan(self, position: QPointF) -> None:
        self._panning = True
        self._pan_last = position
        self._pan_drag_mode = self.dragMode()
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def _end_pan(self) -> None:
        self._panning = False
        self.setDragMode(self._pan_drag_mode)
        self._apply_tool_cursor()

    def _pan_to(self, position: QPointF) -> None:
        delta = position - self._pan_last
        self._pan_last = position
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        hbar.setValue(int(hbar.value() - delta.x()))
        vbar.setValue(int(vbar.value() - delta.y()))

    # ------------------------------------------------------------------ events
    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = 1.0015**delta
        self.zoom_at(factor, event.position())
        event.accept()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            self._space_held and event.button() == Qt.MouseButton.LeftButton
        ):
            self._begin_pan(event.position())
            event.accept()
            return
        if self._tool.mouse_press(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if self._panning:
            self._pan_to(event.position())
            event.accept()
            return
        if self._tool.mouse_move(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if self._panning:
            self._end_pan()
            event.accept()
            return
        if self._tool.mouse_release(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if self._tool.name == "select":
            super().mouseDoubleClickEvent(event)
        else:
            event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.board_scene.is_editing():
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        if key == Qt.Key.Key_Space:
            if not self._space_held:
                self._space_held = True
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return

        delete_keys = (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
        if key in delete_keys:
            self.board_scene.delete_selected()
            event.accept()
            return

        if ctrl and key == Qt.Key.Key_C:
            self.board_scene.copy_selection()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_X:
            self.board_scene.cut_selected()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_V:
            self.board_scene.paste()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_D:
            self.board_scene.duplicate_selected()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_A:
            self.board_scene.select_all()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_Z:
            if shift:
                self.board_scene.undo_stack.redo()
            else:
                self.board_scene.undo_stack.undo()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_Y:
            self.board_scene.undo_stack.redo()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_G:
            if shift:
                self.board_scene.ungroup_selected()
            else:
                self.board_scene.group_selected()
            event.accept()
            return
        if ctrl and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_in()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_Minus:
            self.zoom_out()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_0:
            self.fit_to_content()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_1:
            self.reset_zoom()
            event.accept()
            return
        if ctrl:
            super().keyPressEvent(event)
            return

        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            step = 10.0 if shift else 1.0
            dx = -step if key == Qt.Key.Key_Left else step if key == Qt.Key.Key_Right else 0.0
            dy = -step if key == Qt.Key.Key_Up else step if key == Qt.Key.Key_Down else 0.0
            self.board_scene.nudge_selected(dx, dy)
            event.accept()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            selected = self.board_scene.selected_board_items()
            if len(selected) == 1 and isinstance(
                selected[0], (TextItem, StickyItem, ChecklistItem)
            ):
                selected[0].begin_edit()
                event.accept()
                return

        if key == Qt.Key.Key_Escape:
            if self._tool_name != "select":
                self.set_tool("select")
            else:
                self.board_scene.clearSelection()
            event.accept()
            return

        if key in self.TOOL_KEYS and not (mods & Qt.KeyboardModifier.AltModifier):
            self.set_tool(self.TOOL_KEYS[key])
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and self._space_held:
            self._space_held = False
            if not self._panning:
                self._apply_tool_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    # ------------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event: Any) -> None:
        if self._image_paths(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: Any) -> None:
        if self._image_paths(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: Any) -> None:
        paths = self._image_paths(event)
        if not paths:
            super().dropEvent(event)
            return
        position = self.mapToScene(event.position().toPoint())
        offset = 0.0
        for path in paths:
            self.insert_image(path, position + QPointF(offset, offset))
            offset += 28.0
        event.acceptProposedAction()

    @staticmethod
    def _image_paths(event: Any) -> list[str]:
        paths: list[str] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in IMAGE_EXTENSIONS:
                paths.append(local)
        return paths

    def insert_image(self, path: str, center: QPointF | None = None) -> ImageItem | None:
        try:
            item = ImageItem.from_file(path, float(self.board_scene.defaults["image_max"]))
        except (ValueError, OSError) as exc:
            self.error_occurred.emit(str(exc))
            return None
        if center is None:
            center = self.mapToScene(self.viewport().rect().center())
        item.setPos(center - QPointF(item.rect().width() / 2.0, item.rect().height() / 2.0))
        item.setZValue(self.board_scene.next_z())
        self.board_scene.add_items([item], "Insert image")
        return item

    # ------------------------------------------------------------------ painting
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(self._palette.canvas))
        if not self.show_grid:
            return
        scale = self.transform().m11()
        if scale < GRID_VISIBLE_SCALE or GRID_SIZE * scale < 7.0:
            return

        left = math.floor(rect.left() / GRID_SIZE) * GRID_SIZE
        top = math.floor(rect.top() / GRID_SIZE) * GRID_SIZE
        minor = []
        major = []
        x = left
        while x < rect.right():
            line = (x, rect.top(), x, rect.bottom())
            index = round(x / GRID_SIZE) % 5
            (major if index == 0 else minor).append(line)
            x += GRID_SIZE
        y = top
        while y < rect.bottom():
            line = (rect.left(), y, rect.right(), y)
            index = round(y / GRID_SIZE) % 5
            (major if index == 0 else minor).append(line)
            y += GRID_SIZE

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if minor:
            painter.setPen(QPen(QColor(self._palette.grid_minor), 0))
            from PySide6.QtCore import QLineF

            painter.drawLines([QLineF(*line) for line in minor])
        if major:
            from PySide6.QtCore import QLineF

            painter.setPen(QPen(QColor(self._palette.grid_major), 0))
            painter.drawLines([QLineF(*line) for line in major])

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        guides = self.board_scene.guide_lines()
        if not guides:
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        pen = QPen(QColor(self._palette.selection), 1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for axis, coordinate in guides:
            if axis == "v":
                painter.drawLine(
                    QPointF(coordinate, visible.top()),
                    QPointF(coordinate, visible.bottom()),
                )
            else:
                painter.drawLine(
                    QPointF(visible.left(), coordinate),
                    QPointF(visible.right(), coordinate),
                )
