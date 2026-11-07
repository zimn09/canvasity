"""Headless tests for the canvas core, tools, storage and export."""

from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from canvasity.canvas.scene import BoardScene
from canvasity.canvas.view import BoardView
from canvasity.config import BOARD_FORMAT
from canvasity.export import export_pdf, export_png
from canvasity.objects import (
    ArrowItem,
    ChecklistItem,
    EllipseItem,
    ImageItem,
    LineItem,
    ProjectItem,
    RectItem,
    StickyItem,
    StrokeItem,
    TextItem,
    item_from_dict,
)
from canvasity.storage import BoardIOError, load_board, save_board

APP: QApplication | None = None


def app() -> QApplication:
    global APP
    if APP is None:
        APP = QApplication.instance() or QApplication([])
    return APP


def drag(view: BoardView, start: QPoint, end: QPoint, steps: int = 4) -> None:
    viewport = view.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    for index in range(1, steps + 1):
        point = QPoint(
            start.x() + (end.x() - start.x()) * index // steps,
            start.y() + (end.y() - start.y()) * index // steps,
        )
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(point),
            QPointF(viewport.mapToGlobal(point)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(viewport, event)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)


def click(view: BoardView, point: QPoint) -> None:
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)


def viewport_point(view: BoardView, scene_point: QPointF) -> QPoint:
    return view.mapFromScene(scene_point)


class CanvasTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app()

    def setUp(self) -> None:
        self.scene = BoardScene()
        self.view = BoardView(self.scene)
        self.view.resize(900, 600)
        self.view.show()
        app().processEvents()
        self.view.centerOn(0.0, 0.0)

    def tearDown(self) -> None:
        self.view.hide()
        self.scene.clear()
        self.view.deleteLater()
        app().processEvents()

    def add_rect(self, x: float = 0, y: float = 0) -> RectItem:
        item = RectItem(120, 80, "#ffffff", "#334155", 2)
        item.setPos(x, y)
        self.scene.add_items([item], "test")
        return item


class ToolTests(CanvasTestCase):
    def test_rectangle_tool_creates_item_and_returns_to_select(self) -> None:
        self.view.set_tool("rect")
        drag(self.view, QPoint(300, 250), QPoint(450, 350))
        items = self.scene.board_items()
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], RectItem)
        self.assertGreater(items[0].rect().width(), 100)
        self.assertEqual(self.view.tool_name, "select")
        self.scene.undo_stack.undo()
        self.assertEqual(len(self.scene.board_items()), 0)

    def test_ellipse_and_arrow_tools(self) -> None:
        self.view.set_tool("ellipse")
        drag(self.view, QPoint(250, 200), QPoint(360, 300))
        self.view.set_tool("arrow")
        drag(self.view, QPoint(400, 200), QPoint(520, 320))
        types = sorted(item.TYPE for item in self.scene.board_items())
        self.assertEqual(types, ["arrow", "ellipse"])

    def test_pen_tool_creates_stroke(self) -> None:
        self.view.set_tool("pen")
        start = QPoint(300, 250)
        QTest.mousePress(self.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        for step in range(1, 12):
            point = QPoint(300 + step * 8, 250 + (step % 3) * 5)
            event = QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(point),
                QPointF(self.view.viewport().mapToGlobal(point)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(self.view.viewport(), event)
        QTest.mouseRelease(
            self.view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(396, 260)
        )
        items = self.scene.board_items()
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], StrokeItem)
        self.assertEqual(self.view.tool_name, "pen")

    def test_eraser_removes_and_undo_restores(self) -> None:
        rect = self.add_rect()
        center = viewport_point(self.view, rect.mapToScene(rect.rect().center()))
        self.view.set_tool("eraser")
        click(self.view, center)
        self.assertEqual(len(self.scene.board_items()), 0)
        self.scene.undo_stack.undo()
        self.assertEqual(len(self.scene.board_items()), 1)

    def test_text_tool_creates_and_edits(self) -> None:
        self.view.set_tool("text")
        click(self.view, QPoint(300, 250))
        items = self.scene.board_items()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertIsInstance(item, TextItem)
        self.assertTrue(self.scene.is_editing())
        self.view.setFocus()
        QTest.keyClicks(self.view, "Hello board")
        QTest.keyClick(self.view, Qt.Key.Key_Escape)
        app().processEvents()
        self.assertEqual(item.text, "Hello board")
        self.assertGreater(item.rect().height(), 20)

    def test_sticky_tool_creates_note(self) -> None:
        self.view.set_tool("sticky")
        click(self.view, QPoint(320, 260))
        items = self.scene.board_items()
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], StickyItem)

    def test_checklist_tool_adds_toggles_and_removes_tasks(self) -> None:
        self.view.set_tool("checklist")
        click(self.view, QPoint(300, 250))
        items = self.scene.board_items()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertIsInstance(item, ChecklistItem)
        self.assertTrue(item.is_editing())
        self.assertTrue(self.scene.is_editing())

        self.view.setFocus()
        QTest.keyClicks(self.view, "Buy milk")
        QTest.keyClick(self.view, Qt.Key.Key_Escape)
        app().processEvents()
        self.assertEqual(item.total_count, 1)
        self.assertEqual(item.tasks[0]["text"], "Buy milk")
        self.assertEqual(item.done_count, 0)

        checkbox = viewport_point(
            self.view, item.mapToScene(item._checkbox_rect(0).center())
        )
        click(self.view, checkbox)
        app().processEvents()
        self.assertTrue(item.tasks[0]["done"])
        self.assertEqual(item.done_count, 1)
        self.scene.undo_stack.undo()
        self.assertFalse(item.tasks[0]["done"])

        add = viewport_point(self.view, item.mapToScene(item._add_rect().center()))
        click(self.view, add)
        app().processEvents()
        self.assertTrue(item.is_editing())
        self.view.setFocus()
        QTest.keyClicks(self.view, "Ship it")
        QTest.keyClick(self.view, Qt.Key.Key_Escape)
        app().processEvents()
        self.assertEqual(item.total_count, 2)
        self.assertEqual(item.tasks[1]["text"], "Ship it")

        delete = viewport_point(
            self.view, item.mapToScene(item._delete_rect(1).center())
        )
        click(self.view, delete)
        app().processEvents()
        self.assertEqual(item.total_count, 1)
        self.scene.undo_stack.undo()
        self.assertEqual(item.total_count, 2)

    def test_project_tool_builds_todo_graph(self) -> None:
        self.view.set_tool("project")
        click(self.view, QPoint(300, 250))
        items = self.scene.board_items()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertIsInstance(item, ProjectItem)
        self.assertTrue(item.is_editing())
        self.assertTrue(self.scene.is_editing())

        self.view.setFocus()
        app().processEvents()
        QTest.keyClicks(self.view, "Plan launch")
        QTest.keyClick(self.view, Qt.Key.Key_Escape)
        app().processEvents()
        self.assertEqual(item.total_count, 1)
        self.assertEqual(item.nodes[0]["text"], "Plan launch")
        self.view.fit_to_content()
        app().processEvents()

        add = viewport_point(self.view, item.mapToScene(item._add_rect().center()))
        click(self.view, add)
        app().processEvents()
        self.assertTrue(item.is_editing())
        self.view.setFocus()
        app().processEvents()
        QTest.keyClicks(self.view, "Ship it")
        QTest.keyClick(self.view, Qt.Key.Key_Escape)
        app().processEvents()
        self.assertEqual(item.total_count, 2)
        self.assertEqual(item.nodes[1]["text"], "Ship it")

        first, second = item.nodes
        start = viewport_point(
            self.view, item.mapToScene(item._connector_center(first))
        )
        end = viewport_point(
            self.view, item.mapToScene(item._node_rect(second).center())
        )
        drag(self.view, start, end)
        app().processEvents()
        self.assertEqual(item.links, [{"from": first["id"], "to": second["id"]}])
        self.scene.undo_stack.undo()
        self.assertEqual(item.links, [])
        self.scene.undo_stack.redo()
        self.assertEqual(item.links, [{"from": first["id"], "to": second["id"]}])

        checkbox = viewport_point(
            self.view, item.mapToScene(item._checkbox_rect(first).center())
        )
        click(self.view, checkbox)
        app().processEvents()
        self.assertTrue(item.nodes[0]["done"])
        self.assertEqual(item.done_count, 1)
        self.scene.undo_stack.undo()
        self.assertFalse(item.nodes[0]["done"])

        midpoint = viewport_point(
            self.view, item.mapToScene(item._link_midpoint(0))
        )
        QTest.mouseMove(self.view.viewport(), midpoint)
        app().processEvents()
        self.assertEqual(item._hover_link, 0)
        click(self.view, midpoint)
        app().processEvents()
        self.assertEqual(item.links, [])
        self.scene.undo_stack.undo()
        self.assertEqual(len(item.links), 1)

        delete = viewport_point(
            self.view, item.mapToScene(item._node_delete_rect(first).center())
        )
        click(self.view, delete)
        app().processEvents()
        self.assertEqual(item.total_count, 1)
        self.assertEqual(item.links, [])
        self.scene.undo_stack.undo()
        self.assertEqual(item.total_count, 2)
        self.assertEqual(len(item.links), 1)

    def test_project_title_and_todo_editing(self) -> None:
        item = ProjectItem(
            560,
            "Project",
            [{"id": "todo-1", "text": "Plan", "done": False, "x": 0, "y": 0}],
            [],
        )
        item.setPos(-280, -120)
        self.scene.add_items([item], "test")
        item.setSelected(True)
        app().processEvents()

        title = viewport_point(
            self.view, item.mapToScene(item._title_text_rect().center())
        )
        QTest.mouseDClick(self.view.viewport(), Qt.MouseButton.LeftButton, pos=title)
        app().processEvents()
        self.assertTrue(item.is_editing())
        self.view.setFocus()
        app().processEvents()
        QTest.keyClicks(self.view, "Launch plan")
        QTest.keyClick(self.view, Qt.Key.Key_Escape)
        app().processEvents()
        self.assertEqual(item.title, "Launch plan")
        self.scene.undo_stack.undo()
        self.assertEqual(item.title, "Project")

        todo = viewport_point(
            self.view, item.mapToScene(item._node_text_rect(item.nodes[0]).center())
        )
        QTest.mouseDClick(self.view.viewport(), Qt.MouseButton.LeftButton, pos=todo)
        app().processEvents()
        self.assertTrue(item.is_editing())
        self.view.setFocus()
        app().processEvents()
        QTest.keyClicks(self.view, "Write the plan")
        QTest.keyClick(self.view, Qt.Key.Key_Escape)
        app().processEvents()
        self.assertEqual(item.nodes[0]["text"], "Write the plan")
        self.scene.undo_stack.undo()
        self.assertEqual(item.nodes[0]["text"], "Plan")


class ManipulationTests(CanvasTestCase):
    def test_move_item_with_mouse_and_undo(self) -> None:
        rect = self.add_rect(0, 0)
        self.scene.clearSelection()
        self.view.set_tool("select")
        center = viewport_point(self.view, rect.mapToScene(rect.rect().center()))
        drag(self.view, center, center + QPoint(60, 40))
        moved = rect.pos()
        self.assertNotEqual(moved, QPointF(0, 0))
        self.scene.undo_stack.undo()
        self.assertAlmostEqual(rect.pos().x(), 0.0, places=3)
        self.assertAlmostEqual(rect.pos().y(), 0.0, places=3)

    def test_project_node_drag_and_undo(self) -> None:
        item = ProjectItem(
            560,
            "Project",
            [{"id": "todo-1", "text": "Plan", "done": False, "x": 0, "y": 0}],
            [],
        )
        item.setPos(-280, -120)
        self.scene.add_items([item], "test")
        item.setSelected(True)
        app().processEvents()
        center = viewport_point(
            self.view, item.mapToScene(item._node_rect(item.nodes[0]).center())
        )
        drag(self.view, center, center + QPoint(60, 40))
        app().processEvents()
        moved = item.nodes[0]
        self.assertGreater(moved["x"], 0.0)
        self.assertGreater(moved["y"], 0.0)
        self.scene.undo_stack.undo()
        restored = item.nodes[0]
        self.assertAlmostEqual(restored["x"], 0.0, places=3)
        self.assertAlmostEqual(restored["y"], 0.0, places=3)

    def test_project_resize_handle_and_undo(self) -> None:
        item = ProjectItem(
            560,
            "Project",
            [{"id": "todo-1", "text": "Plan", "done": False, "x": 0, "y": 0}],
            [],
        )
        item.setPos(-280, -120)
        self.scene.add_items([item], "test")
        item.setSelected(True)
        app().processEvents()
        start_size = (item.rect().width(), item.rect().height())
        handle = item.mapToScene(QPointF(start_size[0], start_size[1]))
        start = viewport_point(self.view, handle)
        drag(self.view, start, start + QPoint(80, 40))
        app().processEvents()
        self.assertGreater(item.rect().width(), start_size[0] + 20)
        self.assertGreater(item.rect().height(), start_size[1] + 10)
        self.scene.undo_stack.undo()
        self.assertAlmostEqual(item.rect().width(), start_size[0], places=2)
        self.assertAlmostEqual(item.rect().height(), start_size[1], places=2)

    def test_resize_handle_and_undo(self) -> None:
        rect = self.add_rect(0, 0)
        rect.setSelected(True)
        app().processEvents()
        start_size = (rect.rect().width(), rect.rect().height())
        handle = rect.mapToScene(QPointF(start_size[0], start_size[1]))
        start = viewport_point(self.view, handle)
        drag(self.view, start, start + QPoint(50, 30))
        self.assertGreater(rect.rect().width(), start_size[0] + 20)
        self.assertGreater(rect.rect().height(), start_size[1] + 10)
        self.scene.undo_stack.undo()
        self.assertAlmostEqual(rect.rect().width(), start_size[0], places=2)
        self.assertAlmostEqual(rect.rect().height(), start_size[1], places=2)

    def test_rotate_handle_and_undo(self) -> None:
        rect = self.add_rect(0, 0)
        rect.setSelected(True)
        app().processEvents()
        scale = self.view.current_zoom()
        handle = rect.mapToScene(QPointF(60.0, -27.0 / scale))
        start = viewport_point(self.view, handle)
        center = viewport_point(self.view, rect.mapToScene(rect.rect().center()))
        drag(self.view, start, center + QPoint(120, 0))
        self.assertGreater(abs(rect.rotation()), 10.0)
        self.scene.undo_stack.undo()
        self.assertAlmostEqual(rect.rotation(), 0.0, places=2)

    def test_group_moves_together(self) -> None:
        first = self.add_rect(0, 0)
        second = self.add_rect(300, 0)
        self.scene.select_items([first, second])
        self.scene.group_selected()
        self.assertIsNotNone(first.group_id)
        self.assertEqual(first.group_id, second.group_id)
        before = second.pos()
        self.scene.clearSelection()
        center = viewport_point(self.view, first.mapToScene(first.rect().center()))
        drag(self.view, center, center + QPoint(40, 0))
        self.assertNotEqual(second.pos(), before)
        self.scene.undo_stack.undo()
        self.assertAlmostEqual(second.pos().x(), before.x(), places=3)

    def test_clipboard_copy_paste(self) -> None:
        rect = self.add_rect(0, 0)
        self.scene.clearSelection()
        rect.setSelected(True)
        self.scene.copy_selection()
        self.scene.paste()
        self.assertEqual(len(self.scene.board_items()), 2)
        pasted = [item for item in self.scene.board_items() if item is not rect][0]
        self.assertNotEqual(pasted.pos(), rect.pos())
        self.scene.undo_stack.undo()
        self.assertEqual(len(self.scene.board_items()), 1)

    def test_duplicate_and_delete(self) -> None:
        self.add_rect()
        self.scene.duplicate_selected()
        self.assertEqual(len(self.scene.board_items()), 2)
        self.scene.delete_selected()
        self.assertEqual(len(self.scene.board_items()), 1)
        self.scene.undo_stack.undo()
        self.assertEqual(len(self.scene.board_items()), 2)

    def test_snapping_to_other_object(self) -> None:
        first = self.add_rect(0, 0)
        second = self.add_rect(300, 20)
        self.scene.clearSelection()
        second.setSelected(True)
        self.scene.set_snapping(grid=False, align=True)
        snapped = self.scene.snap_position(second, QPointF(122, 20))
        self.assertAlmostEqual(snapped.x(), 120.0, places=3)
        self.assertTrue(self.scene.guide_lines())
        self.scene.clear_guides()
        self.assertFalse(self.scene.guide_lines())

    def test_z_order_operations(self) -> None:
        first = self.add_rect(0, 0)
        second = self.add_rect(20, 20)
        first.setZValue(1.0)
        second.setZValue(2.0)
        self.scene.clearSelection()
        first.setSelected(True)
        self.scene.reorder_selected("front")
        self.assertGreater(first.zValue(), second.zValue())
        self.scene.undo_stack.undo()
        self.assertLess(first.zValue(), second.zValue())

    def test_nudge_merges_undo_steps(self) -> None:
        rect = self.add_rect(0, 0)
        self.scene.clearSelection()
        rect.setSelected(True)
        self.scene.nudge_selected(1, 0)
        self.scene.nudge_selected(1, 0)
        self.assertAlmostEqual(rect.pos().x(), 2.0, places=3)
        self.scene.undo_stack.undo()
        self.assertAlmostEqual(rect.pos().x(), 0.0, places=3)


class ViewTests(CanvasTestCase):
    def test_zoom_clamps_and_anchors(self) -> None:
        self.view.zoom_at(4.0, QPointF(100, 100))
        self.assertGreater(self.view.current_zoom(), 1.0)
        self.view.zoom_at(1e6)
        self.assertLessEqual(self.view.current_zoom(), 32.0)
        self.view.zoom_at(1e-6)
        self.assertGreaterEqual(self.view.current_zoom(), 0.05)
        self.view.reset_zoom()
        self.assertAlmostEqual(self.view.current_zoom(), 1.0, places=5)

    def test_fit_to_content(self) -> None:
        self.add_rect(0, 0)
        self.add_rect(2000, 1200)
        self.view.fit_to_content()
        self.assertGreater(self.view.current_zoom(), 0.0)
        self.assertLess(self.view.current_zoom(), 1.0)

    def test_guide_signal_does_not_crash(self) -> None:
        self.add_rect(0, 0)
        self.scene.clear_guides()
        self.scene.guides_changed.emit()
        app().processEvents()


class SerializationTests(CanvasTestCase):
    def _populate(self) -> None:
        rect = RectItem(140, 90, "#dbeafe", "#2563eb", 3)
        rect.setPos(10, 20)
        rect.setRotation(15)
        rect.group_id = "g1"
        self.scene.add_items([rect])
        text = TextItem(280, "Hello", "#111827", font_size=22, bold=True, alignment="center")
        text.setPos(-100, 30)
        self.scene.add_items([text])
        sticky = StickyItem(200, 160, "Note", "#fde68a")
        sticky.setPos(400, 40)
        self.scene.add_items([sticky])
        stroke = StrokeItem.from_scene_points(
            [QPointF(0, 0), QPointF(20, 10), QPointF(40, 0)], "#0f172a", 4
        )
        stroke.setPos(0, 300)
        self.scene.add_items([stroke])
        line = LineItem(100, 60, (0, 1), (1, 0), "#334155", 2)
        line.setPos(200, 300)
        self.scene.add_items([line])
        arrow = ArrowItem(100, 60, (0, 0), (1, 1), "#334155", 2)
        arrow.setPos(400, 300)
        self.scene.add_items([arrow])
        pixmap = QPixmap(40, 30)
        pixmap.fill(QColor("#10b981"))
        image = ImageItem(pixmap, 40, 30)
        image.setPos(600, 300)
        self.scene.add_items([image])
        checklist = ChecklistItem(
            320,
            "Launch",
            [
                {"text": "Write copy", "done": True},
                {"text": "Publish", "done": False},
            ],
        )
        checklist.setPos(800, 300)
        self.scene.add_items([checklist])
        project = ProjectItem(
            560,
            "Roadmap",
            [
                {"id": "p1", "text": "Plan", "done": True, "x": 0, "y": 0},
                {"id": "p2", "text": "Build", "done": False, "x": 276, "y": 0},
            ],
            [{"from": "p1", "to": "p2"}],
        )
        project.setPos(100, 500)
        self.scene.add_items([project])

    def test_round_trip_all_types(self) -> None:
        self._populate()
        data = self.scene.to_board_dict()
        self.assertEqual(data["format"], BOARD_FORMAT)
        self.assertEqual(len(data["items"]), 9)
        self.scene.new_board()
        self.assertEqual(len(self.scene.board_items()), 0)
        self.scene.load_board_dict(data)
        self.assertEqual(len(self.scene.board_items()), 9)
        types = sorted(item.TYPE for item in self.scene.board_items())
        self.assertEqual(
            sorted(types),
            sorted(
                [
                    "arrow",
                    "checklist",
                    "image",
                    "line",
                    "project",
                    "rect",
                    "sticky",
                    "stroke",
                    "text",
                ]
            ),
        )

    def test_checklist_round_trip(self) -> None:
        item = ChecklistItem(
            280,
            "Errands",
            [
                {"text": "Milk", "done": True},
                {"text": "Bread", "done": False},
            ],
            "#ffffff",
            "#0f172a",
            15,
        )
        clone = item_from_dict(item.to_dict())
        self.assertIsInstance(clone, ChecklistItem)
        self.assertEqual(clone.title, "Errands")
        self.assertEqual(clone.total_count, 2)
        self.assertEqual(clone.done_count, 1)
        self.assertEqual(clone.tasks[0]["text"], "Milk")
        self.assertTrue(clone.tasks[0]["done"])

    def test_project_round_trip(self) -> None:
        item = ProjectItem(
            560,
            "Roadmap",
            [
                {"id": "p1", "text": "Plan", "done": True, "x": 0, "y": 0},
                {"id": "p2", "text": "Build", "done": False, "x": 276, "y": 0},
            ],
            [{"from": "p1", "to": "p2"}],
            "#f8fafc",
            "#0f172a",
            15,
        )
        clone = item_from_dict(item.to_dict())
        self.assertIsInstance(clone, ProjectItem)
        self.assertEqual(clone.title, "Roadmap")
        self.assertEqual(clone.total_count, 2)
        self.assertEqual(clone.done_count, 1)
        self.assertEqual(clone.nodes[0]["text"], "Plan")
        self.assertEqual(clone.links, [{"from": "p1", "to": "p2"}])
        self.assertEqual(clone.font_size, 15)

    def test_item_dict_round_trip(self) -> None:
        rect = RectItem(90, 60, "#ff0000", "#00ff00", 4)
        rect.setPos(12, 34)
        rect.setRotation(30)
        clone = item_from_dict(rect.to_dict())
        self.assertEqual(clone.TYPE, "rect")
        self.assertAlmostEqual(clone.pos().x(), 12)
        self.assertAlmostEqual(clone.rotation(), 30)
        self.assertEqual(clone.fill.name(), "#ff0000")

    def test_rejects_invalid_data(self) -> None:
        with self.assertRaises(ValueError):
            self.scene.load_board_dict({"format": "other", "version": 1, "items": []})
        with self.assertRaises(ValueError):
            self.scene.load_board_dict(
                {"format": BOARD_FORMAT, "version": 999, "items": []}
            )
        with self.assertRaises(ValueError):
            self.scene.load_board_dict(
                {"format": BOARD_FORMAT, "version": 1, "items": [{"type": "nope"}]}
            )


class StorageExportTests(CanvasTestCase):
    def test_save_load_and_corruption(self) -> None:
        rect = RectItem(100, 50)
        rect.setPos(5, 6)
        self.scene.add_items([rect])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.canvasity"
            save_board(path, self.scene.to_board_dict())
            self.assertTrue(path.exists())
            data = load_board(path)
            self.assertEqual(len(data["items"]), 1)
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(BoardIOError):
                load_board(path)

    def test_export_png_and_pdf(self) -> None:
        self.add_rect(0, 0)
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "board.png"
            pdf = Path(directory) / "board.pdf"
            export_png(self.scene, png, 1.0)
            export_pdf(self.scene, pdf)
            self.assertGreater(png.stat().st_size, 100)
            self.assertGreater(pdf.stat().st_size, 100)

    def test_image_embedded_in_json(self) -> None:
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor("#123456"))
        item = ImageItem(pixmap, 20, 20)
        data = item.to_dict()
        self.assertIn("data", data)
        base64.b64decode(data["data"])


if __name__ == "__main__":
    unittest.main()
