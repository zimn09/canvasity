"""Project frames containing connectable to-do nodes."""

from __future__ import annotations

import math
import uuid
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from ..config import DEFAULT_FILL, DEFAULT_FONT, DEFAULT_TEXT
from .base import BoardItem
from .editing import InlineLineEditor

HEADER_HEIGHT = 68.0
FOOTER_HEIGHT = 42.0
CONTENT_PADDING = 20.0
NODE_WIDTH = 240.0
NODE_HEIGHT = 60.0
NODE_GAP_X = 36.0
NODE_GAP_Y = 26.0
NODE_COLUMNS = 2
DEFAULT_WIDTH = 560.0
MIN_WIDTH = 380.0
MIN_HEIGHT = 190.0
DEFAULT_TITLE = "Project"
DEFAULT_FONT_SIZE = 14.0
MAX_FONT_SIZE = 22.0
CHECKBOX_SIZE = 18.0
CONNECTOR_RADIUS = 5.5


class ProjectItem(BoardItem):
    """A project frame whose to-do nodes can be connected as a dependency graph.

    Drag a node body to arrange it, drag its right-edge circle onto another node
    to add a dependency arrow, and hover a link to reveal its remove button.
    The frame grows automatically as nodes are added or moved.
    """

    TYPE = "project"
    SUPPORTS_FILL = True
    SUPPORTS_TEXT = True
    RESIZE_AXES = ""
    ROTATABLE = True

    def __init__(
        self,
        width: float = DEFAULT_WIDTH,
        title: str = DEFAULT_TITLE,
        nodes: list[dict[str, Any]] | None = None,
        links: list[dict[str, Any]] | None = None,
        color: str | QColor = DEFAULT_FILL,
        text_color: str | QColor = DEFAULT_TEXT,
        font_size: float = DEFAULT_FONT_SIZE,
    ) -> None:
        super().__init__()
        self._default_width = max(MIN_WIDTH, float(width))
        self._title = str(title or DEFAULT_TITLE)
        self._nodes = self._sanitise_nodes(nodes or [])
        self._links = self._sanitise_links(links or [], self._nodes)
        self._color = QColor(color)
        self._text_color = QColor(text_color)
        self._font_size = max(8.0, min(MAX_FONT_SIZE, float(font_size)))

        self._editing_title = False
        self._editing_node_id: str | None = None
        self._editing_new = False
        self._draft_id: str | None = None
        self._draft_pos = QPointF()
        self._edit_before: dict[str, Any] | None = None
        self._interactive_press = False
        self._drag_node_id: str | None = None
        self._drag_offset = QPointF()
        self._connecting_from: str | None = None
        self._connection_pos = QPointF()
        self._connection_target: str | None = None
        self._hover_link: int | None = None

        self._editor = InlineLineEditor(self)
        self._editor.setZValue(10.0)
        self._editor.setVisible(False)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.document().setDocumentMargin(0.0)
        option = self._editor.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._editor.document().setDefaultTextOption(option)

        self._fit_size()

    # ------------------------------------------------------------------ data
    @staticmethod
    def _sanitise_nodes(nodes: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not isinstance(nodes, list):
            return result
        seen: set[str] = set()
        for raw in nodes:
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("id") or uuid.uuid4().hex)
            if node_id in seen:
                node_id = uuid.uuid4().hex
            seen.add(node_id)
            try:
                x = max(0.0, float(raw.get("x", 0.0)))
                y = max(0.0, float(raw.get("y", 0.0)))
            except (TypeError, ValueError):
                x = y = 0.0
            result.append(
                {
                    "id": node_id,
                    "text": str(raw.get("text", "")).strip(),
                    "done": bool(raw.get("done", False)),
                    "x": x,
                    "y": y,
                }
            )
        return result

    @staticmethod
    def _sanitise_links(
        links: Any, nodes: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if not isinstance(links, list):
            return result
        node_ids = {node["id"] for node in nodes}
        seen: set[tuple[str, str]] = set()
        for raw in links:
            if not isinstance(raw, dict):
                continue
            source = str(raw.get("from", ""))
            target = str(raw.get("to", ""))
            if source == target or source not in node_ids or target not in node_ids:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            result.append({"from": source, "to": target})
        return result

    @property
    def title(self) -> str:
        return self._title

    def set_title(self, title: str) -> None:
        self._title = str(title).strip() or DEFAULT_TITLE
        self.update()

    @property
    def nodes(self) -> list[dict[str, Any]]:
        return [dict(node) for node in self._nodes]

    @property
    def links(self) -> list[dict[str, str]]:
        return [dict(link) for link in self._links]

    @property
    def done_count(self) -> int:
        return sum(1 for node in self._nodes if node["done"])

    @property
    def total_count(self) -> int:
        return len(self._nodes)

    def add_node(
        self,
        text: str = "",
        done: bool = False,
        x: float | None = None,
        y: float | None = None,
    ) -> str:
        if x is None or y is None:
            slot = self._find_free_slot()
            x = slot.x() if x is None else x
            y = slot.y() if y is None else y
        node_id = uuid.uuid4().hex
        self._nodes.append(
            {
                "id": node_id,
                "text": str(text).strip(),
                "done": bool(done),
                "x": max(0.0, float(x)),
                "y": max(0.0, float(y)),
            }
        )
        self._fit_size()
        self.update()
        return node_id

    def remove_node(self, node_id: str) -> None:
        index = self._node_index_by_id(node_id)
        if index is None:
            return
        if self._editing_node_id == node_id:
            self._cancel_edit_ui()
        self._nodes.pop(index)
        self._links = [
            link
            for link in self._links
            if link["from"] != node_id and link["to"] != node_id
        ]
        self._hover_link = None
        self._fit_size()
        self.update()

    def set_node_text(self, node_id: str, text: str) -> None:
        node = self._node_by_id(node_id)
        if node is not None:
            node["text"] = str(text).strip()
            self.update()

    def set_node_done(self, node_id: str, done: bool) -> None:
        node = self._node_by_id(node_id)
        if node is not None:
            node["done"] = bool(done)
            self.update()

    def toggle_node(self, node_id: str) -> None:
        node = self._node_by_id(node_id)
        if node is not None:
            node["done"] = not node["done"]
            self.update()

    def add_link(self, source_id: str, target_id: str) -> bool:
        if source_id == target_id:
            return False
        if self._node_by_id(source_id) is None or self._node_by_id(target_id) is None:
            return False
        if any(
            link["from"] == source_id and link["to"] == target_id
            for link in self._links
        ):
            return False
        self._links.append({"from": source_id, "to": target_id})
        self.update()
        return True

    def remove_link(self, source_id: str, target_id: str) -> bool:
        for index, link in enumerate(self._links):
            if link["from"] == source_id and link["to"] == target_id:
                self.remove_link_at(index)
                return True
        return False

    def remove_link_at(self, index: int) -> None:
        if 0 <= index < len(self._links):
            del self._links[index]
            if self._hover_link == index:
                self._hover_link = None
            elif self._hover_link is not None and self._hover_link > index:
                self._hover_link -= 1
            self.update()

    # ------------------------------------------------------------------ appearance
    @property
    def fill(self) -> QColor:
        return QColor(self._color)

    def set_fill(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    @property
    def text_color(self) -> QColor:
        return QColor(self._text_color)

    def set_text_color(self, color: QColor) -> None:
        self._text_color = QColor(color)
        self._editor.setDefaultTextColor(self._text_color)
        self.update()

    @property
    def font_size(self) -> float:
        return self._font_size

    def set_font_size(self, size: float) -> None:
        self._font_size = max(8.0, min(MAX_FONT_SIZE, float(size)))
        self.update()

    # ------------------------------------------------------------------ geometry
    @staticmethod
    def _node_index(node_id: str, nodes: list[dict[str, Any]]) -> int | None:
        for index, node in enumerate(nodes):
            if node["id"] == node_id:
                return index
        return None

    def _node_index_by_id(self, node_id: str) -> int | None:
        return self._node_index(node_id, self._nodes)

    def _node_by_id(self, node_id: str) -> dict[str, Any] | None:
        index = self._node_index_by_id(node_id)
        return self._nodes[index] if index is not None else None

    def _node_rect(self, node: dict[str, Any]) -> QRectF:
        return QRectF(
            CONTENT_PADDING + float(node["x"]),
            HEADER_HEIGHT + float(node["y"]),
            NODE_WIDTH,
            NODE_HEIGHT,
        )

    def _checkbox_rect(self, node: dict[str, Any]) -> QRectF:
        rect = self._node_rect(node)
        return QRectF(
            rect.left() + 14.0,
            rect.center().y() - CHECKBOX_SIZE / 2.0,
            CHECKBOX_SIZE,
            CHECKBOX_SIZE,
        )

    def _node_text_rect(self, node: dict[str, Any]) -> QRectF:
        rect = self._node_rect(node)
        return QRectF(
            rect.left() + 42.0,
            rect.top() + 8.0,
            NODE_WIDTH - 42.0 - 30.0,
            NODE_HEIGHT - 16.0,
        )

    def _node_delete_rect(self, node: dict[str, Any]) -> QRectF:
        rect = self._node_rect(node)
        return QRectF(rect.right() - 24.0, rect.top() + 8.0, 14.0, 14.0)

    def _connector_center(self, node: dict[str, Any]) -> QPointF:
        rect = self._node_rect(node)
        return QPointF(rect.right(), rect.center().y())

    def _title_text_rect(self) -> QRectF:
        return QRectF(
            CONTENT_PADDING,
            12.0,
            max(80.0, self._w - CONTENT_PADDING * 2.0 - 126.0),
            24.0,
        )

    def _progress_text_rect(self) -> QRectF:
        return QRectF(self._w - CONTENT_PADDING - 116.0, 12.0, 116.0, 24.0)

    def _progress_bar_rect(self) -> QRectF:
        return QRectF(
            CONTENT_PADDING,
            48.0,
            max(40.0, self._w - CONTENT_PADDING * 2.0),
            4.0,
        )

    def _footer_top(self) -> float:
        return HEADER_HEIGHT + self._content_height(self._visible_nodes())

    def _add_rect(self) -> QRectF:
        return QRectF(
            CONTENT_PADDING,
            self._footer_top(),
            min(180.0, self._w - CONTENT_PADDING * 2.0),
            FOOTER_HEIGHT,
        )

    @staticmethod
    def _node_extent(nodes: list[dict[str, Any]]) -> tuple[float, float]:
        max_x = 0.0
        max_y = 0.0
        for node in nodes:
            max_x = max(max_x, float(node["x"]) + NODE_WIDTH)
            max_y = max(max_y, float(node["y"]) + NODE_HEIGHT)
        return max_x, max_y

    def _width_for_nodes(self, nodes: list[dict[str, Any]]) -> float:
        max_x, _ = self._node_extent(nodes)
        return max(self._default_width, max_x + CONTENT_PADDING * 2.0)

    def _content_height(self, nodes: list[dict[str, Any]]) -> float:
        _, max_y = self._node_extent(nodes)
        return max(NODE_HEIGHT, max_y) + CONTENT_PADDING

    def _height_for_nodes(self, nodes: list[dict[str, Any]]) -> float:
        return HEADER_HEIGHT + self._content_height(nodes) + FOOTER_HEIGHT

    def _visible_nodes(self) -> list[dict[str, Any]]:
        nodes = [dict(node) for node in self._nodes]
        if self._editing_new and self._draft_id is not None:
            nodes.append(
                {
                    "id": self._draft_id,
                    "text": "",
                    "done": False,
                    "x": self._draft_pos.x(),
                    "y": self._draft_pos.y(),
                }
            )
        return nodes

    def _state_nodes(self) -> list[dict[str, Any]]:
        nodes = [dict(node) for node in self._nodes]
        if self._editing_node_id is not None:
            for node in nodes:
                if node["id"] == self._editing_node_id:
                    node["text"] = self._editor_value()
                    break
        elif self._editing_new and self._draft_id is not None:
            text = self._editor_value()
            if text:
                nodes.append(
                    {
                        "id": self._draft_id,
                        "text": text,
                        "done": False,
                        "x": self._draft_pos.x(),
                        "y": self._draft_pos.y(),
                    }
                )
        return nodes

    def _state_links(self) -> list[dict[str, str]]:
        node_ids = {node["id"] for node in self._state_nodes()}
        return [
            dict(link)
            for link in self._links
            if link["from"] in node_ids and link["to"] in node_ids
        ]

    def _state_title(self) -> str:
        if self._editing_title:
            return self._editor_value() or DEFAULT_TITLE
        return self._title or DEFAULT_TITLE

    def _state_size(self) -> tuple[float, float]:
        nodes = self._state_nodes()
        return self._width_for_nodes(nodes), self._height_for_nodes(nodes)

    def _fit_size(self) -> None:
        nodes = self._visible_nodes()
        super().set_size(
            self._width_for_nodes(nodes),
            self._height_for_nodes(nodes),
        )

    def _grow_to_fit(self) -> None:
        nodes = self._visible_nodes()
        width = max(self._w, self._width_for_nodes(nodes))
        height = max(self._h, self._height_for_nodes(nodes))
        if abs(width - self._w) > 1e-6 or abs(height - self._h) > 1e-6:
            super().set_size(width, height)

    def set_size(self, width: float, height: float) -> None:
        super().set_size(
            max(MIN_WIDTH, float(width)),
            max(MIN_HEIGHT, float(height)),
        )

    def capture_state(self) -> dict[str, Any]:
        state = super().capture_state()
        state["size"] = list(self._state_size())
        return state

    def _find_free_slot(self) -> QPointF:
        existing = [
            QRectF(float(node["x"]), float(node["y"]), NODE_WIDTH, NODE_HEIGHT)
            for node in self._nodes
        ]
        for row in range(60):
            for column in range(NODE_COLUMNS):
                x = column * (NODE_WIDTH + NODE_GAP_X)
                y = row * (NODE_HEIGHT + NODE_GAP_Y)
                candidate = QRectF(x, y, NODE_WIDTH, NODE_HEIGHT)
                if not any(
                    candidate.adjusted(-8.0, -8.0, 8.0, 8.0).intersects(rect)
                    for rect in existing
                ):
                    return QPointF(x, y)
        _, max_y = self._node_extent(self._nodes)
        return QPointF(0.0, max_y + NODE_GAP_Y)

    # ------------------------------------------------------------------ link geometry
    def _link_geometry(
        self, source: dict[str, Any], target: dict[str, Any]
    ) -> tuple[QPainterPath, QPointF, QPointF]:
        source_rect = self._node_rect(source)
        target_rect = self._node_rect(target)
        source_center = source_rect.center()
        target_center = target_rect.center()
        dx = target_center.x() - source_center.x()
        dy = target_center.y() - source_center.y()

        if abs(dx) >= abs(dy):
            if dx >= 0.0:
                start = QPointF(source_rect.right(), source_center.y())
                end = QPointF(target_rect.left(), target_center.y())
            else:
                start = QPointF(source_rect.left(), source_center.y())
                end = QPointF(target_rect.right(), target_center.y())
            offset = max(36.0, abs(end.x() - start.x()) * 0.45)
            sign = 1.0 if end.x() >= start.x() else -1.0
            control1 = QPointF(start.x() + sign * offset, start.y())
            control2 = QPointF(end.x() - sign * offset, end.y())
        else:
            if dy >= 0.0:
                start = QPointF(source_center.x(), source_rect.bottom())
                end = QPointF(target_center.x(), target_rect.top())
            else:
                start = QPointF(source_center.x(), source_rect.top())
                end = QPointF(target_center.x(), target_rect.bottom())
            offset = max(28.0, abs(end.y() - start.y()) * 0.45)
            sign = 1.0 if end.y() >= start.y() else -1.0
            control1 = QPointF(start.x(), start.y() + sign * offset)
            control2 = QPointF(end.x(), end.y() - sign * offset)

        path = QPainterPath(start)
        path.cubicTo(control1, control2, end)
        return path, end, control2

    def _link_path_for(self, link: dict[str, str]) -> QPainterPath | None:
        source = self._node_by_id(link["from"])
        target = self._node_by_id(link["to"])
        if source is None or target is None:
            return None
        path, _, _ = self._link_geometry(source, target)
        return path

    def _link_at(self, pos: QPointF) -> int | None:
        for index, link in enumerate(self._links):
            path = self._link_path_for(link)
            if path is None:
                continue
            stroker = QPainterPathStroker()
            stroker.setWidth(max(8.0, 10.0 / self.view_scale()))
            if stroker.createStroke(path).contains(pos):
                return index
        return None

    def _link_midpoint(self, index: int) -> QPointF | None:
        if not 0 <= index < len(self._links):
            return None
        path = self._link_path_for(self._links[index])
        if path is None:
            return None
        return path.pointAtPercent(0.5)

    def _link_delete_rect(self, index: int) -> QRectF | None:
        midpoint = self._link_midpoint(index)
        if midpoint is None:
            return None
        return QRectF(midpoint.x() - 10.0, midpoint.y() - 10.0, 20.0, 20.0)

    # ------------------------------------------------------------------ hit testing
    def _node_at(self, pos: QPointF) -> dict[str, Any] | None:
        for node in reversed(self._nodes):
            if self._node_rect(node).contains(pos):
                return node
        return None

    def _connector_at(self, pos: QPointF) -> dict[str, Any] | None:
        radius = CONNECTOR_RADIUS + 6.0
        for node in reversed(self._nodes):
            center = self._connector_center(node)
            if (center - pos).manhattanLength() <= radius * 1.5:
                return node
        return None

    def _add_at(self, pos: QPointF) -> bool:
        return self._add_rect().contains(pos)

    def _title_at(self, pos: QPointF) -> bool:
        return 0.0 <= pos.y() < HEADER_HEIGHT

    # ------------------------------------------------------------------ painting
    def _title_font(self) -> QFont:
        font = QFont(DEFAULT_FONT, max(9, int(round(self._font_size + 3.0))))
        font.setBold(True)
        return font

    def _node_font(self, done: bool = False) -> QFont:
        font = QFont(DEFAULT_FONT, max(8, int(round(self._font_size))))
        font.setStrikeOut(done)
        return font

    def _small_font(self) -> QFont:
        return QFont(DEFAULT_FONT, max(7, int(round(self._font_size - 4.0))))

    def _muted(self, alpha: int = 150) -> QColor:
        color = QColor(self._text_color)
        color.setAlpha(alpha)
        return color

    def _node_fill(self) -> QColor:
        if self._color.lightness() >= 140:
            return QColor("#ffffff")
        return self._color.lighter(118)

    def _header_color(self) -> QColor:
        color = QColor(self._color)
        if color.lightness() >= 140:
            return color.darker(104)
        return color.lighter(108)

    def _paint_edit_highlight(self, painter: QPainter, rect: QRectF) -> None:
        accent = self._accent()
        accent.setAlpha(30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(rect.adjusted(-2.0, -1.0, 2.0, 1.0), 4.0, 4.0)

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()

        shadow = QRectF(rect).translated(3.0, 4.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 28))
        painter.drawRoundedRect(shadow, 11.0, 11.0)

        border = QColor(self._text_color)
        border.setAlpha(48)
        painter.setBrush(self._color)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 11.0, 11.0)

        painter.save()
        try:
            clip = QPainterPath()
            clip.addRoundedRect(rect.adjusted(1.0, 1.0, -1.0, -1.0), 10.0, 10.0)
            painter.setClipPath(clip)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._header_color())
            painter.drawRect(QRectF(0.0, 0.0, self._w, HEADER_HEIGHT))
            self._paint_header(painter)
            self._paint_empty_state(painter)
            self._paint_links(painter)
            self._paint_nodes(painter)
            self._paint_connection_preview(painter)
            self._paint_footer(painter)
        finally:
            painter.restore()

    def _paint_header(self, painter: QPainter) -> None:
        if self._editing_title:
            self._paint_edit_highlight(painter, self._title_text_rect())
        else:
            title_rect = self._title_text_rect()
            font = self._title_font()
            painter.setFont(font)
            painter.setPen(self._text_color)
            metrics = QFontMetrics(font)
            title = metrics.elidedText(
                self._state_title(),
                Qt.TextElideMode.ElideRight,
                int(title_rect.width()),
            )
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                title,
            )

        nodes = self._state_nodes()
        total = len(nodes)
        done = sum(1 for node in nodes if node["done"])
        progress = f"{done} of {total} done" if total else "No todos"
        painter.setFont(self._small_font())
        painter.setPen(self._muted(165))
        painter.drawText(
            self._progress_text_rect(),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            progress,
        )

        bar = self._progress_bar_rect()
        track = QColor(self._text_color)
        track.setAlpha(30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(bar, 2.0, 2.0)
        if total:
            fill_width = bar.width() * done / total
            if fill_width > 0.0:
                painter.setBrush(self._accent())
                painter.drawRoundedRect(
                    QRectF(bar.left(), bar.top(), fill_width, bar.height()), 2.0, 2.0
                )

    def _paint_empty_state(self, painter: QPainter) -> None:
        if self._nodes or self._editing_new:
            return
        rect = QRectF(
            CONTENT_PADDING,
            HEADER_HEIGHT,
            self._w - CONTENT_PADDING * 2.0,
            self._content_height([]),
        )
        painter.setFont(self._node_font())
        painter.setPen(self._muted(145))
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignCenter,
            "No todos yet",
        )

    def _paint_links(self, painter: QPainter) -> None:
        for index, link in enumerate(self._links):
            path = self._link_path_for(link)
            if path is None:
                continue
            hovered = self._hover_link == index
            color = self._accent() if hovered else self._muted(120)
            pen = QPen(color, 2.2 if hovered else 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            source = self._node_by_id(link["from"])
            target = self._node_by_id(link["to"])
            if source is not None and target is not None:
                _, end, control = self._link_geometry(source, target)
                self._paint_arrow(painter, end, control, color)
            if hovered:
                midpoint = self._link_midpoint(index)
                if midpoint is not None:
                    self._paint_link_remove(painter, midpoint)

    def _paint_arrow(
        self,
        painter: QPainter,
        end: QPointF,
        control: QPointF,
        color: QColor,
    ) -> None:
        dx = end.x() - control.x()
        dy = end.y() - control.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        size = 8.0
        base = QPointF(end.x() - ux * size, end.y() - uy * size)
        left = QPointF(base.x() + px * size * 0.55, base.y() + py * size * 0.55)
        right = QPointF(base.x() - px * size * 0.55, base.y() - py * size * 0.55)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([end, left, right]))

    def _paint_link_remove(self, painter: QPainter, midpoint: QPointF) -> None:
        rect = QRectF(midpoint.x() - 10.0, midpoint.y() - 10.0, 20.0, 20.0)
        painter.setPen(QPen(self._accent(), 1.2))
        painter.setBrush(self._node_fill())
        painter.drawEllipse(rect)
        pen = QPen(self._accent(), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        delta = 3.5
        painter.drawLine(
            QPointF(midpoint.x() - delta, midpoint.y() - delta),
            QPointF(midpoint.x() + delta, midpoint.y() + delta),
        )
        painter.drawLine(
            QPointF(midpoint.x() + delta, midpoint.y() - delta),
            QPointF(midpoint.x() - delta, midpoint.y() + delta),
        )

    def _paint_nodes(self, painter: QPainter) -> None:
        for node in self._visible_nodes():
            draft = self._editing_new and node["id"] == self._draft_id
            self._paint_node(painter, node, draft)

    def _paint_node(
        self, painter: QPainter, node: dict[str, Any], draft: bool
    ) -> None:
        rect = self._node_rect(node)
        done = bool(node["done"])
        border = QColor(self._text_color)
        border.setAlpha(48)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(self._node_fill())
        painter.drawRoundedRect(rect, 8.0, 8.0)

        if self._connection_target == node["id"]:
            painter.setPen(QPen(self._accent(), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 8.0, 8.0)

        box = self._checkbox_rect(node)
        if done:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._accent())
            painter.drawRoundedRect(box, 4.0, 4.0)
            check_pen = QPen(QColor("#ffffff"), 1.8)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(box.left() + 4.0, box.center().y()),
                        QPointF(box.left() + 7.5, box.bottom() - 4.5),
                        QPointF(box.right() - 3.5, box.top() + 4.5),
                    ]
                )
            )
        else:
            box_border = QColor(self._text_color)
            box_border.setAlpha(110)
            painter.setPen(QPen(box_border, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box, 4.0, 4.0)

        text_rect = self._node_text_rect(node)
        editing = self._editing_node_id == node["id"] or draft
        if editing:
            self._paint_edit_highlight(painter, text_rect)
            if draft and not self._editor_value():
                painter.setFont(self._node_font())
                painter.setPen(self._muted(120))
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    "New todo",
                )
        else:
            font = self._node_font(done)
            painter.setFont(font)
            painter.setPen(self._muted(135) if done else self._text_color)
            metrics = QFontMetrics(font)
            elided = metrics.elidedText(
                str(node["text"]),
                Qt.TextElideMode.ElideRight,
                int(text_rect.width()),
            )
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided,
            )

        if not draft:
            delete_rect = self._node_delete_rect(node)
            delete_color = QColor(self._text_color)
            delete_color.setAlpha(90)
            delete_pen = QPen(delete_color, 1.4)
            delete_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(delete_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            center = delete_rect.center()
            delta = 3.5
            painter.drawLine(
                QPointF(center.x() - delta, center.y() - delta),
                QPointF(center.x() + delta, center.y() + delta),
            )
            painter.drawLine(
                QPointF(center.x() + delta, center.y() - delta),
                QPointF(center.x() - delta, center.y() + delta),
            )

        connector = self._connector_center(node)
        has_outgoing = any(link["from"] == node["id"] for link in self._links)
        if has_outgoing or self._connecting_from == node["id"]:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._accent())
        else:
            painter.setPen(QPen(self._accent(), 1.4))
            painter.setBrush(self._node_fill())
        painter.drawEllipse(connector, CONNECTOR_RADIUS, CONNECTOR_RADIUS)

    def _paint_connection_preview(self, painter: QPainter) -> None:
        if self._connecting_from is None:
            return
        source = self._node_by_id(self._connecting_from)
        if source is None:
            return
        start = self._connector_center(source)
        end = self._connection_pos
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        if abs(dx) >= abs(dy):
            offset = max(30.0, abs(dx) * 0.4)
            sign = 1.0 if dx >= 0.0 else -1.0
            control1 = QPointF(start.x() + sign * offset, start.y())
            control2 = QPointF(end.x() - sign * offset, end.y())
        else:
            offset = max(24.0, abs(dy) * 0.4)
            sign = 1.0 if dy >= 0.0 else -1.0
            control1 = QPointF(start.x(), start.y() + sign * offset)
            control2 = QPointF(end.x(), end.y() - sign * offset)
        path = QPainterPath(start)
        path.cubicTo(control1, control2, end)
        pen = QPen(self._accent(), 1.8, Qt.PenStyle.DashLine)
        pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        self._paint_arrow(painter, end, control2, self._accent())

    def _paint_footer(self, painter: QPainter) -> None:
        footer_top = self._footer_top()
        separator = QColor(self._text_color)
        separator.setAlpha(28)
        painter.setPen(QPen(separator, 1.0))
        painter.drawLine(
            QPointF(CONTENT_PADDING, footer_top),
            QPointF(self._w - CONTENT_PADDING, footer_top),
        )

        accent = self._accent()
        plus_center = QPointF(
            CONTENT_PADDING + 9.0, footer_top + FOOTER_HEIGHT / 2.0
        )
        plus_pen = QPen(accent, 1.8)
        plus_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(plus_pen)
        painter.drawLine(
            QPointF(plus_center.x() - 4.5, plus_center.y()),
            QPointF(plus_center.x() + 4.5, plus_center.y()),
        )
        painter.drawLine(
            QPointF(plus_center.x(), plus_center.y() - 4.5),
            QPointF(plus_center.x(), plus_center.y() + 4.5),
        )
        painter.setFont(self._node_font())
        painter.setPen(accent)
        painter.drawText(
            QRectF(
                CONTENT_PADDING + 22.0,
                footer_top,
                self._w - CONTENT_PADDING * 2.0 - 22.0,
                FOOTER_HEIGHT,
            ),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Add todo",
        )

        if self._w >= 480.0:
            painter.setFont(self._small_font())
            painter.setPen(self._muted(135))
            painter.drawText(
                QRectF(
                    self._w - CONTENT_PADDING - 220.0,
                    footer_top,
                    220.0,
                    FOOTER_HEIGHT,
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "Drag ○ to connect",
            )

    # ------------------------------------------------------------------ editing
    def _is_editing(self) -> bool:
        return (
            self._editing_title
            or self._editing_new
            or self._editing_node_id is not None
        )

    def is_editing(self) -> bool:
        return self._is_editing()

    def _editor_value(self) -> str:
        return self._editor.toPlainText().strip()

    def _show_editor(self) -> None:
        self._editor.setVisible(True)
        self._editor.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        self._editor.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction
        )
        self._editor.setFocus(Qt.FocusReason.MouseFocusReason)

    def _select_all(self) -> None:
        cursor = self._editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self._editor.setTextCursor(cursor)

    def begin_edit(self) -> None:
        self.begin_title_edit()

    def begin_title_edit(self) -> None:
        if self._is_editing():
            self.finish_edit()
        self._edit_before = self.capture_state()
        self._editing_title = True
        self._editing_new = False
        self._editing_node_id = None
        rect = self._title_text_rect()
        self._editor.setFont(self._title_font())
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.setTextWidth(max(80.0, rect.width()))
        self._editor.setPlainText(self._title)
        self._editor.setPos(rect.topLeft())
        self._show_editor()
        self._select_all()
        self.update()

    def begin_node_edit(self, node_id: str) -> None:
        node = self._node_by_id(node_id)
        if node is None:
            return
        if self._is_editing():
            self.finish_edit()
        self._edit_before = self.capture_state()
        self._editing_title = False
        self._editing_new = False
        self._editing_node_id = node_id
        rect = self._node_text_rect(node)
        self._editor.setFont(self._node_font(False))
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.setTextWidth(max(40.0, rect.width()))
        self._editor.setPlainText(str(node["text"]))
        self._editor.setPos(rect.topLeft())
        self._show_editor()
        self._select_all()
        self.update()

    def begin_new_node_edit(self) -> None:
        if self._is_editing():
            self.finish_edit()
        self._edit_before = self.capture_state()
        self._editing_title = False
        self._editing_new = True
        self._editing_node_id = None
        self._draft_id = uuid.uuid4().hex
        while any(node["id"] == self._draft_id for node in self._nodes):
            self._draft_id = uuid.uuid4().hex
        self._draft_pos = self._find_free_slot()
        self._fit_size()
        draft = {
            "id": self._draft_id,
            "text": "",
            "done": False,
            "x": self._draft_pos.x(),
            "y": self._draft_pos.y(),
        }
        rect = self._node_text_rect(draft)
        self._editor.setFont(self._node_font(False))
        self._editor.setDefaultTextColor(self._text_color)
        self._editor.setTextWidth(max(40.0, rect.width()))
        self._editor.setPlainText("")
        self._editor.setPos(rect.topLeft())
        self._show_editor()
        self.update()

    def _cancel_edit_ui(self) -> None:
        self._editing_title = False
        self._editing_node_id = None
        self._editing_new = False
        self._draft_id = None
        self._edit_before = None
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._editor.setVisible(False)
        self._editor.clearFocus()
        self._fit_size()

    def finish_edit(self) -> None:
        if not self._is_editing():
            return
        title_edit = self._editing_title
        node_id = self._editing_node_id
        new_edit = self._editing_new
        text = self._editor_value()

        if title_edit:
            self._title = text or DEFAULT_TITLE
        elif node_id is not None:
            node = self._node_by_id(node_id)
            if node is not None:
                node["text"] = text
        elif new_edit and text and self._draft_id is not None:
            self._nodes.append(
                {
                    "id": self._draft_id,
                    "text": text,
                    "done": False,
                    "x": self._draft_pos.x(),
                    "y": self._draft_pos.y(),
                }
            )

        before = self._edit_before
        self._editing_title = False
        self._editing_node_id = None
        self._editing_new = False
        self._draft_id = None
        self._edit_before = None
        self._editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._editor.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._editor.setVisible(False)
        self._editor.clearFocus()
        self._fit_size()
        self.update()

        scene = self.scene()
        if scene is not None and before is not None:
            if title_edit:
                label = "Edit project title"
            elif new_edit:
                label = "Add project todo"
            else:
                label = "Edit project todo"
            scene.push_state([self], before, label)

    # ------------------------------------------------------------------ input
    def _select_self(self) -> None:
        if self.isSelected():
            return
        scene = self.scene()
        if scene is not None:
            scene.clearSelection()
        self.setSelected(True)

    def _clear_interaction(self) -> None:
        self._drag_node_id = None
        self._connecting_from = None
        self._connection_target = None
        self._interactive_press = False

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._handle_at(event.pos()):
            super().mousePressEvent(event)
            return
        if self._is_editing():
            self.finish_edit()

        pos = event.pos()
        connector = self._connector_at(pos)
        if connector is not None:
            self._select_self()
            self._interactive_press = True
            self._connecting_from = connector["id"]
            self._connection_pos = pos
            self._connection_target = None
            event.accept()
            return

        node = self._node_at(pos)
        if node is not None:
            self._select_self()
            self._interactive_press = True
            if self._checkbox_rect(node).adjusted(-4.0, -4.0, 4.0, 4.0).contains(pos):
                self.toggle_node(node["id"])
            elif self._node_delete_rect(node).adjusted(
                -3.0, -3.0, 3.0, 3.0
            ).contains(pos):
                self.remove_node(node["id"])
            else:
                self._drag_node_id = node["id"]
                self._drag_offset = pos - self._node_rect(node).topLeft()
            event.accept()
            return

        link_index = self._link_at(pos)
        if link_index is not None:
            delete_rect = self._link_delete_rect(link_index)
            if delete_rect is not None and delete_rect.contains(pos):
                self._select_self()
                self._interactive_press = True
                self.remove_link_at(link_index)
                event.accept()
                return

        if self._add_at(pos):
            self._select_self()
            self._interactive_press = True
            self.begin_new_node_edit()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag_node_id is not None:
            node = self._node_by_id(self._drag_node_id)
            if node is not None:
                pos = event.pos() - self._drag_offset
                node["x"] = max(0.0, pos.x() - CONTENT_PADDING)
                node["y"] = max(0.0, pos.y() - HEADER_HEIGHT)
                self._grow_to_fit()
                self.update()
            event.accept()
            return
        if self._connecting_from is not None:
            self._connection_pos = event.pos()
            target = self._node_at(event.pos())
            if target is not None and target["id"] == self._connecting_from:
                target = None
            self._connection_target = target["id"] if target is not None else None
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag_node_id is not None:
            self._drag_node_id = None
            self._interactive_press = False
            self._fit_size()
            self.update()
            event.accept()
            return
        if self._connecting_from is not None:
            source_id = self._connecting_from
            target_id = self._connection_target
            self._connecting_from = None
            self._connection_target = None
            self._interactive_press = False
            if target_id is not None:
                self.add_link(source_id, target_id)
            self.update()
            event.accept()
            return
        if self._interactive_press:
            self._interactive_press = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._handle_at(
            event.pos()
        ):
            if self._is_editing():
                self.finish_edit()
            pos = event.pos()
            if self._connector_at(pos) is not None:
                super().mouseDoubleClickEvent(event)
                return
            node = self._node_at(pos)
            if node is not None:
                if (
                    self._checkbox_rect(node)
                    .adjusted(-4.0, -4.0, 4.0, 4.0)
                    .contains(pos)
                    or self._node_delete_rect(node)
                    .adjusted(-3.0, -3.0, 3.0, 3.0)
                    .contains(pos)
                ):
                    super().mouseDoubleClickEvent(event)
                    return
                self._clear_interaction()
                self._select_self()
                self.begin_node_edit(node["id"])
                event.accept()
                return
            if self._title_at(pos):
                self._clear_interaction()
                self._select_self()
                self.begin_title_edit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def hoverMoveEvent(self, event: Any) -> None:
        super().hoverMoveEvent(event)
        if self._handle_at(event.pos()):
            return
        pos = event.pos()
        if self._connector_at(pos) is not None:
            self._set_hover_link(None)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        node = self._node_at(pos)
        if node is not None:
            self._set_hover_link(None)
            if (
                self._checkbox_rect(node).adjusted(-4.0, -4.0, 4.0, 4.0).contains(pos)
                or self._node_delete_rect(node)
                .adjusted(-3.0, -3.0, 3.0, 3.0)
                .contains(pos)
            ):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            return
        link_index = self._link_at(pos)
        if link_index is not None:
            self._set_hover_link(link_index)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        self._set_hover_link(None)
        if self._add_at(pos):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._title_at(pos):
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def hoverLeaveEvent(self, event: Any) -> None:
        self._set_hover_link(None)
        super().hoverLeaveEvent(event)

    def _set_hover_link(self, index: int | None) -> None:
        if self._hover_link == index:
            return
        self._hover_link = index
        self.update()

    # ------------------------------------------------------------------ state
    def _extra_state(self) -> dict[str, Any]:
        return {
            "title": self._state_title(),
            "nodes": self._state_nodes(),
            "links": self._state_links(),
            "fill": self._color.name(QColor.NameFormat.HexArgb),
            "text_color": self._text_color.name(QColor.NameFormat.HexArgb),
            "font_size": self._font_size,
        }

    def _apply_extra_state(self, state: dict[str, Any]) -> None:
        self._cancel_edit_ui()
        if "title" in state:
            self._title = str(state["title"]).strip() or DEFAULT_TITLE
        if "nodes" in state:
            self._nodes = self._sanitise_nodes(state["nodes"])
        if "links" in state:
            self._links = self._sanitise_links(state["links"], self._nodes)
        if "fill" in state:
            self._color = QColor(state["fill"])
        if "text_color" in state:
            self._text_color = QColor(state["text_color"])
        if "font_size" in state:
            self._font_size = max(
                8.0, min(MAX_FONT_SIZE, float(state["font_size"]))
            )
        self._hover_link = None
        self._fit_size()
        self.update()

    def _extra_dict(self) -> dict[str, Any]:
        return self._extra_state()
