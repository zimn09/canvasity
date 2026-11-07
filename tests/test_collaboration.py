"""Headless tests for the live collaboration relay and client."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from canvasity.config import BOARD_FORMAT, BOARD_VERSION
from canvasity.network import CollaborationClient, CollaborationServer


APP: QApplication | None = None


def app() -> QApplication:
    global APP
    if APP is None:
        APP = QApplication.instance() or QApplication([])
    return APP


class CollaborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app()

    def setUp(self) -> None:
        self.server = CollaborationServer(("127.0.0.1", 0))
        self.server.start()
        self.client_a = CollaborationClient()
        self.client_b = CollaborationClient()

    def tearDown(self) -> None:
        self.client_b.stop()
        self.client_a.stop()
        self.server.stop()

    def test_client_hello_and_cursor_round_trip(self) -> None:
        board_a = {
            "format": BOARD_FORMAT,
            "version": BOARD_VERSION,
            "items": [],
        }
        board_b = {
            "format": BOARD_FORMAT,
            "version": BOARD_VERSION,
            "items": [],
        }

        board_spy = QSignalSpy(self.client_b.board_received)
        cursor_spy = QSignalSpy(self.client_b.cursor_received)
        self.client_a.start(
            "127.0.0.1",
            self.server.port,
            "client-a",
            "Alice",
            "#38bdf8",
            board_a,
        )
        self.client_b.start(
            "127.0.0.1",
            self.server.port,
            "client-b",
            "Bob",
            "#f59e0b",
            board_b,
        )

        board_deadline_passed = False
        for _ in range(50):
            QTest.qWait(100)
            if board_spy.count() > 0:
                board_deadline_passed = True
                break
        self.assertTrue(board_deadline_passed, "Client B did not receive Client A's board")

        self.client_a.send_cursor(12.0, 34.0, {"id": "client-a", "name": "Alice", "color": "#38bdf8"})
        cursor_deadline_passed = False
        for _ in range(50):
            QTest.qWait(100)
            if cursor_spy.count() > 0:
                cursor_deadline_passed = True
                break
        self.assertTrue(cursor_deadline_passed, "Client B did not receive Client A's cursor")

        cursor = cursor_spy.at(0)[0]
        self.assertEqual(float(cursor["x"]), 12.0)
        self.assertEqual(float(cursor["y"]), 34.0)
        self.assertEqual(str(cursor["user"]["id"]), "client-a")
