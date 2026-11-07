"""Undo/redo commands for every board mutation."""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtGui import QUndoCommand

from ..objects.base import BoardItem


class AddItemsCommand(QUndoCommand):
    def __init__(self, scene: Any, items: Sequence[BoardItem], text: str = "Add objects") -> None:
        super().__init__(text)
        self._scene = scene
        self._items = list(items)

    def redo(self) -> None:
        for item in self._items:
            if item.scene() is not self._scene:
                self._scene.addItem(item)
        self._scene.select_items(self._items)

    def undo(self) -> None:
        for item in self._items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)


class RemoveItemsCommand(QUndoCommand):
    def __init__(
        self, scene: Any, items: Sequence[BoardItem], text: str = "Delete objects"
    ) -> None:
        super().__init__(text)
        self._scene = scene
        self._items = list(items)

    def redo(self) -> None:
        for item in self._items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._scene.clearSelection()
        self._scene.selection_info_changed.emit()

    def undo(self) -> None:
        for item in self._items:
            if item.scene() is not self._scene:
                self._scene.addItem(item)
        self._scene.select_items(self._items)


class StateCommand(QUndoCommand):
    """Restores before/after snapshots for one or more items."""

    MERGE_ID = 0x0CAB

    def __init__(
        self,
        scene: Any,
        items: Sequence[BoardItem],
        before: Sequence[dict[str, Any]],
        after: Sequence[dict[str, Any]],
        text: str = "Modify objects",
        mergeable: bool = False,
    ) -> None:
        super().__init__(text)
        self._scene = scene
        self._items = list(items)
        self._before = [dict(state) for state in before]
        self._after = [dict(state) for state in after]
        self._mergeable = mergeable

    def id(self) -> int:  # noqa: A003 - Qt API
        return self.MERGE_ID if self._mergeable else -1

    def redo(self) -> None:
        self._scene.apply_states(self._items, self._after)

    def undo(self) -> None:
        self._scene.apply_states(self._items, self._before)

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802 - Qt API
        if not isinstance(other, StateCommand):
            return False
        if not self._mergeable or other.text() != self.text():
            return False
        if [id(item) for item in self._items] != [id(item) for item in other._items]:
            return False
        self._after = other._after
        return True


class GroupCommand(QUndoCommand):
    def __init__(
        self,
        items: Sequence[BoardItem],
        before: Sequence[str | None],
        after: Sequence[str | None],
        text: str = "Group objects",
    ) -> None:
        super().__init__(text)
        self._items = list(items)
        self._before = list(before)
        self._after = list(after)

    def redo(self) -> None:
        for item, group_id in zip(self._items, self._after):
            item.group_id = group_id
            item.update()

    def undo(self) -> None:
        for item, group_id in zip(self._items, self._before):
            item.group_id = group_id
            item.update()
