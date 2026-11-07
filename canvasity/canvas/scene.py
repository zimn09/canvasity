"""The board scene: selection, snapping, undo history and (de)serialisation."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QTransform, QUndoStack
from PySide6.QtWidgets import QApplication, QGraphicsScene

from ..config import (
    BOARD_FORMAT,
    BOARD_VERSION,
    GRID_SIZE,
    SCENE_LIMIT,
    SNAP_THRESHOLD_PX,
)
from ..objects import BoardItem, item_from_dict
from .commands import (
    AddItemsCommand,
    GroupCommand,
    RemoveItemsCommand,
    StateCommand,
)


class BoardScene(QGraphicsScene):
    selection_info_changed = Signal()
    guides_changed = Signal()

    CLIPBOARD_TAG = "canvasity-clipboard"

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setSceneRect(-SCENE_LIMIT, -SCENE_LIMIT, SCENE_LIMIT * 2, SCENE_LIMIT * 2)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)

        self.undo_stack = QUndoStack(self)
        self.selection_color = "#2563eb"
        self.export_mode = False
        self.applying_command = False
        self.grid_snap = False
        self.align_snap = True
        self._guides: list[tuple[str, float]] = []
        self._interaction_before: dict[str, tuple[BoardItem, dict[str, Any]]] | None = None
        self._group_guard = False
        self._snap_disabled = False
        self._clipboard_json: str | None = None

        self.defaults: dict[str, Any] = {
            "fill": "#ffffff",
            "stroke": "#334155",
            "stroke_width": 2.0,
            "text_color": "#0f172a",
            "font_family": "Inter",
            "font_size": 16.0,
            "sticky_color": "#fde68a",
            "pen_color": "#0f172a",
            "pen_width": 3.0,
            "image_max": 640.0,
        }

        self.selectionChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------ selection
    def _on_selection_changed(self) -> None:
        if not self._group_guard:
            self._expand_groups()
        for item in self.items():
            if isinstance(item, BoardItem):
                item.update()
        self.selection_info_changed.emit()

    def _expand_groups(self) -> None:
        selected = [item for item in self.selectedItems() if isinstance(item, BoardItem)]
        group_ids = {item.group_id for item in selected if item.group_id}
        if not group_ids:
            return
        self._group_guard = True
        try:
            for item in self.items():
                if (
                    isinstance(item, BoardItem)
                    and item.group_id in group_ids
                    and not item.isSelected()
                ):
                    item.setSelected(True)
        finally:
            self._group_guard = False

    def select_items(self, items: Iterable[BoardItem], clear: bool = True) -> None:
        if clear:
            self.clearSelection()
        for item in items:
            if item.scene() is self:
                item.setSelected(True)
        self.selection_info_changed.emit()

    def select_all(self) -> None:
        self.select_items([item for item in self.items() if isinstance(item, BoardItem)])

    def board_items(self) -> list[BoardItem]:
        return [item for item in self.items() if isinstance(item, BoardItem)]

    def selected_board_items(self) -> list[BoardItem]:
        items = [item for item in self.selectedItems() if isinstance(item, BoardItem)]
        return sorted(items, key=lambda item: item.zValue())

    def next_z(self) -> float:
        items = self.board_items()
        return max((item.zValue() for item in items), default=0.0) + 1.0

    # ------------------------------------------------------------------ adding / removing
    def add_items(self, items: Sequence[BoardItem], text: str = "Add objects") -> None:
        if not items:
            return
        self.undo_stack.push(AddItemsCommand(self, items, text))

    def commit_live_items(self, items: Sequence[BoardItem], text: str = "Draw object") -> None:
        """Finish live-created items that are already in the scene."""
        for item in items:
            if item.scene() is self:
                self.removeItem(item)
        self.add_items(items, text)

    def delete_selected(self) -> None:
        self.finish_editing()
        items = self.selected_board_items()
        if not items:
            return
        self.undo_stack.push(RemoveItemsCommand(self, items, "Delete objects"))

    def cut_selected(self) -> None:
        if not self.selected_board_items():
            return
        self.copy_selection()
        self.delete_selected()

    # ------------------------------------------------------------------ clipboard
    def copy_selection(self) -> None:
        self.finish_editing()
        items = self.selected_board_items()
        if not items:
            return
        payload = {
            "app": self.CLIPBOARD_TAG,
            "version": 1,
            "items": [item.to_dict() for item in items],
        }
        text = json.dumps(payload)
        self._clipboard_json = text
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _clipboard_payload(self) -> list[dict[str, Any]] | None:
        clipboard = QApplication.clipboard()
        raw = clipboard.text() if clipboard is not None else ""
        candidates = [raw, self._clipboard_json or ""]
        for text in candidates:
            if not text:
                continue
            try:
                payload = json.loads(text)
            except (TypeError, ValueError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("app") == self.CLIPBOARD_TAG
                and isinstance(payload.get("items"), list)
            ):
                return [item for item in payload["items"] if isinstance(item, dict)]
        return None

    def _clone_dicts(
        self, dictionaries: Sequence[dict[str, Any]], dx: float, dy: float
    ) -> list[BoardItem]:
        group_map: dict[str, str] = {}
        clones: list[BoardItem] = []
        for data in dictionaries:
            data = dict(data)
            data["id"] = uuid.uuid4().hex
            old_group = data.get("group")
            if old_group:
                if old_group not in group_map:
                    group_map[old_group] = uuid.uuid4().hex
                data["group"] = group_map[old_group]
            data["x"] = float(data.get("x", 0.0)) + dx
            data["y"] = float(data.get("y", 0.0)) + dy
            clones.append(item_from_dict(data))
        return clones

    def paste(self) -> None:
        payload = self._clipboard_payload()
        if not payload:
            return
        try:
            with self.no_snap():
                clones = self._clone_dicts(payload, 24.0, 24.0)
        except (ValueError, KeyError, TypeError):
            return
        if not clones:
            return
        self.add_items(clones, "Paste objects")

    def duplicate_selected(self) -> None:
        items = self.selected_board_items()
        if not items:
            return
        try:
            with self.no_snap():
                clones = self._clone_dicts([item.to_dict() for item in items], 24.0, 24.0)
        except (ValueError, KeyError, TypeError):
            return
        self.add_items(clones, "Duplicate objects")

    # ------------------------------------------------------------------ grouping
    def group_selected(self) -> None:
        items = self.selected_board_items()
        if len(items) < 2:
            return
        before = [item.group_id for item in items]
        group_id = uuid.uuid4().hex
        after = [group_id for _ in items]
        self.undo_stack.push(GroupCommand(items, before, after, "Group objects"))
        self.selection_info_changed.emit()
        for item in items:
            item.update()

    def ungroup_selected(self) -> None:
        items = [item for item in self.selected_board_items() if item.group_id]
        if not items:
            return
        before = [item.group_id for item in items]
        after: list[str | None] = [None for _ in items]
        self.undo_stack.push(GroupCommand(items, before, after, "Ungroup objects"))
        self.selection_info_changed.emit()
        for item in items:
            item.update()

    # ------------------------------------------------------------------ z-order
    def reorder_selected(self, mode: str) -> None:
        items = self.board_items()
        if not items:
            return
        items.sort(key=lambda item: item.zValue())
        selected = [item for item in items if item.isSelected()]
        if not selected:
            return
        selected_ids = {id(item) for item in selected}
        order = list(items)
        if mode == "front":
            order = [item for item in order if id(item) not in selected_ids] + selected
        elif mode == "back":
            order = selected + [item for item in order if id(item) not in selected_ids]
        elif mode == "forward":
            for item in reversed(selected):
                index = order.index(item)
                if index + 1 < len(order) and id(order[index + 1]) not in selected_ids:
                    order[index], order[index + 1] = order[index + 1], order[index]
        elif mode == "backward":
            for item in selected:
                index = order.index(item)
                if index > 0 and id(order[index - 1]) not in selected_ids:
                    order[index], order[index - 1] = order[index - 1], order[index]
        before = [item.capture_state() for item in order]
        for index, item in enumerate(order):
            item.setZValue(float(index + 1))
        after = [item.capture_state() for item in order]
        if before != after:
            self.undo_stack.push(StateCommand(self, order, before, after, "Reorder objects"))

    def align_selected(self, mode: str) -> None:
        items = self.selected_board_items()
        if len(items) < 2:
            return
        rects = [item.mapToScene(item.rect()).boundingRect() for item in items]
        left = min(r.left() for r in rects)
        right = max(r.right() for r in rects)
        top = min(r.top() for r in rects)
        bottom = max(r.bottom() for r in rects)
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0

        def move(item: BoardItem) -> None:
            rect = item.mapToScene(item.rect()).boundingRect()
            dx = dy = 0.0
            if mode == "left":
                dx = left - rect.left()
            elif mode == "hcenter":
                dx = center_x - (rect.left() + rect.right()) / 2.0
            elif mode == "right":
                dx = right - rect.right()
            elif mode == "top":
                dy = top - rect.top()
            elif mode == "vcenter":
                dy = center_y - (rect.top() + rect.bottom()) / 2.0
            elif mode == "bottom":
                dy = bottom - rect.bottom()
            item.setPos(item.pos() + QPointF(dx, dy))

        self.apply_change(items, move, "Align objects")

    # ------------------------------------------------------------------ state helpers
    @contextmanager
    def no_snap(self) -> Iterator[None]:
        previous = self._snap_disabled
        self._snap_disabled = True
        try:
            yield
        finally:
            self._snap_disabled = previous

    def apply_change(
        self,
        items: Sequence[BoardItem],
        setter: Callable[[BoardItem], None],
        text: str = "Modify objects",
        mergeable: bool = False,
    ) -> None:
        if not items:
            return
        before = [item.capture_state() for item in items]
        for item in items:
            setter(item)
        after = [item.capture_state() for item in items]
        if before != after:
            self.undo_stack.push(
                StateCommand(self, items, before, after, text, mergeable=mergeable)
            )
            self.selection_info_changed.emit()

    def push_state(
        self,
        items: Sequence[BoardItem],
        before: dict[str, Any] | Sequence[dict[str, Any]],
        text: str = "Modify objects",
    ) -> None:
        if not items:
            return
        before_list = (
            [before] if isinstance(before, dict) else [dict(state) for state in before]
        )
        after = [item.capture_state() for item in items]
        if before_list != after:
            self.undo_stack.push(StateCommand(self, items, before_list, after, text))
            self.selection_info_changed.emit()

    def apply_states(
        self, items: Sequence[BoardItem], states: Sequence[dict[str, Any]]
    ) -> None:
        previous = self.applying_command
        self.applying_command = True
        try:
            for item, state in zip(items, states):
                if item.scene() is self:
                    item.restore_state(state)
        finally:
            self.applying_command = previous
        self.selection_info_changed.emit()

    def nudge_selected(self, dx: float, dy: float) -> None:
        items = self.selected_board_items()
        if not items:
            return
        with self.no_snap():
            self.apply_change(
                items,
                lambda item: item.setPos(item.pos() + QPointF(dx, dy)),
                "Nudge objects",
                mergeable=True,
            )

    # ------------------------------------------------------------------ snapping
    def _item_rect_in_scene(self, item: BoardItem) -> QRectF:
        return item.mapToScene(item.rect()).boundingRect()

    def snap_position(self, item: BoardItem, pos: QPointF) -> QPointF:
        if (
            self._snap_disabled
            or self.export_mode
            or self.applying_command
            or not (self.grid_snap or self.align_snap)
            or len(self.selectedItems()) > 1
        ):
            return pos

        delta = pos - item.pos()
        moving = self._item_rect_in_scene(item).translated(delta)
        scale = max(item.view_scale(), 0.05)
        threshold = SNAP_THRESHOLD_PX / scale

        dx = 0.0
        dy = 0.0
        if self.grid_snap:
            dx = round(moving.left() / GRID_SIZE) * GRID_SIZE - moving.left()
            dy = round(moving.top() / GRID_SIZE) * GRID_SIZE - moving.top()

        guide_v: float | None = None
        guide_h: float | None = None
        if self.align_snap:
            best_x: float | None = None
            best_y: float | None = None
            for other in self.items():
                if other is item or not isinstance(other, BoardItem):
                    continue
                if other.isSelected() or not other.isVisible():
                    continue
                other_rect = self._item_rect_in_scene(other)
                x_targets = (
                    other_rect.left(),
                    other_rect.center().x(),
                    other_rect.right(),
                )
                y_targets = (
                    other_rect.top(),
                    other_rect.center().y(),
                    other_rect.bottom(),
                )
                for source in (moving.left(), moving.center().x(), moving.right()):
                    for target in x_targets:
                        diff = target - source
                        if abs(diff) <= threshold and (
                            best_x is None or abs(diff) < abs(best_x)
                        ):
                            best_x = diff
                            guide_v = target
                for source in (moving.top(), moving.center().y(), moving.bottom()):
                    for target in y_targets:
                        diff = target - source
                        if abs(diff) <= threshold and (
                            best_y is None or abs(diff) < abs(best_y)
                        ):
                            best_y = diff
                            guide_h = target
            if best_x is not None:
                dx = best_x
            if best_y is not None:
                dy = best_y

        guides: list[tuple[str, float]] = []
        if guide_v is not None:
            guides.append(("v", guide_v))
        if guide_h is not None:
            guides.append(("h", guide_h))
        if guides != self._guides:
            self._guides = guides
            self.guides_changed.emit()
        return QPointF(pos.x() + dx, pos.y() + dy)

    def clear_guides(self) -> None:
        if self._guides:
            self._guides = []
            self.guides_changed.emit()

    def guide_lines(self) -> list[tuple[str, float]]:
        return list(self._guides)

    def set_snapping(self, grid: bool | None = None, align: bool | None = None) -> None:
        if grid is not None:
            self.grid_snap = grid
        if align is not None:
            self.align_snap = align

    # ------------------------------------------------------------------ interaction undo
    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._interaction_before = {}
            for item in self.selectedItems():
                if isinstance(item, BoardItem):
                    self._interaction_before[item.item_id] = (item, item.capture_state())
            target = self._top_item_at(event.scenePos())
            if (
                target is not None
                and target.item_id not in self._interaction_before
            ):
                self._interaction_before[target.item_id] = (target, target.capture_state())
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._interaction_before is not None:
            for item in self.selectedItems():
                if isinstance(item, BoardItem) and item.item_id not in self._interaction_before:
                    self._interaction_before[item.item_id] = (item, item.capture_state())

    def mouseReleaseEvent(self, event: Any) -> None:
        super().mouseReleaseEvent(event)
        self.clear_guides()
        pending = self._interaction_before
        self._interaction_before = None
        if not pending:
            return
        changed: list[BoardItem] = []
        before: list[dict[str, Any]] = []
        after: list[dict[str, Any]] = []
        for item, state in pending.values():
            if item.scene() is not self:
                continue
            current = item.capture_state()
            if current != state:
                changed.append(item)
                before.append(state)
                after.append(current)
        if changed:
            text = "Modify objects"
            self.undo_stack.push(StateCommand(self, changed, before, after, text))

    def _top_item_at(self, pos: QPointF) -> BoardItem | None:
        item = self.itemAt(pos, QTransform())
        while item is not None:
            if isinstance(item, BoardItem):
                return item
            item = item.parentItem()
        return None

    # ------------------------------------------------------------------ editing
    def is_editing(self) -> bool:
        focus = self.focusItem()
        if focus is None:
            return False
        return focus.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction

    def finish_editing(self) -> bool:
        focus = self.focusItem()
        if focus is None:
            return False
        from PySide6.QtWidgets import QGraphicsTextItem

        if isinstance(focus, QGraphicsTextItem):
            focus.clearFocus()
            self.setFocusItem(None)
            return True
        return False

    # ------------------------------------------------------------------ zoom / export
    def update_handle_scale(self) -> None:
        for item in self.items():
            if isinstance(item, BoardItem):
                item.refresh_handles()

    def set_export_mode(self, enabled: bool) -> None:
        self.export_mode = enabled
        for item in self.board_items():
            item.update()

    def content_rect(self, margin: float = 40.0) -> QRectF:
        items = self.board_items()
        if not items:
            return QRectF(-600.0, -400.0, 1200.0, 800.0)
        rect = QRectF()
        for item in items:
            bounds = item.content_rect()
            rect = bounds if rect.isNull() else rect.united(bounds)
        if rect.width() < 1.0 or rect.height() < 1.0:
            rect = QRectF(rect.left(), rect.top(), max(rect.width(), 100.0), max(rect.height(), 100.0))
        return rect.adjusted(-margin, -margin, margin, margin)

    # ------------------------------------------------------------------ serialisation
    def to_board_dict(self) -> dict[str, Any]:
        items = sorted(self.board_items(), key=lambda item: item.zValue())
        return {
            "format": BOARD_FORMAT,
            "version": BOARD_VERSION,
            "items": [item.to_dict() for item in items],
        }

    def load_board_dict(self, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ValueError("Board file does not contain a JSON object")
        if data.get("format") != BOARD_FORMAT:
            raise ValueError("This file is not a Canvasity board")
        version = data.get("version", 0)
        if not isinstance(version, int) or version > BOARD_VERSION:
            raise ValueError(
                f"Board format version {version!r} is newer than this application supports"
            )
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("Board item list is malformed")
        items: list[BoardItem] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ValueError("Board contains a malformed object")
            items.append(item_from_dict(raw))

        self.finish_editing()
        self.clear()
        self.undo_stack.clear()
        self.applying_command = True
        try:
            for item in items:
                self.addItem(item)
        finally:
            self.applying_command = False
        self.clearSelection()
        self.clear_guides()
        self.selection_info_changed.emit()

    def new_board(self) -> None:
        self.finish_editing()
        self.clear()
        self.undo_stack.clear()
        self.clearSelection()
        self.clear_guides()
        self.selection_info_changed.emit()
