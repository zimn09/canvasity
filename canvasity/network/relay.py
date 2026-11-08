"""Minimal live-board relay used by the collaborative canvas feature."""

from __future__ import annotations

import json
import socket
import socketserver
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..config import BOARD_FORMAT, BOARD_VERSION, COLLABORATION_PORT


class CollaborationServer(socketserver.ThreadingTCPServer):
    """A tiny newline-delimited JSON relay for one collaborative board."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, _CollaborationHandler)
        self._clients: set[_CollaborationHandler] = set()
        self._clients_lock = threading.Lock()
        self._boards: dict[int, dict[str, Any]] = {}
        self._next_client_id = 1
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self.serve_forever,
            name="canvasity-collab-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        thread = getattr(self, "_thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    def register_client(self, handler: _CollaborationHandler) -> None:
        with self._clients_lock:
            self._clients.add(handler)
            handler.client_id = self._next_client_id
            self._next_client_id += 1
            self._boards[handler.client_id] = handler.board

    def unregister_client(self, handler: _CollaborationHandler) -> None:
        with self._clients_lock:
            self._clients.discard(handler)
            self._boards.pop(handler.client_id, None)

    def _send(self, handler: _CollaborationHandler, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
        handler.request.sendall(payload)

    def handle_hello(
        self, handler: _CollaborationHandler, message: dict[str, Any]
    ) -> None:
        board = message.get("board")
        if isinstance(board, dict):
            handler.board = board
        with self._clients_lock:
            self._boards[handler.client_id] = handler.board
            others = [client for client in self._clients if client is not handler]
            if not others:
                # The first client acknowledges its own initial board snapshot.
                self._send(handler, {"type": "board", "board": self._boards[handler.client_id]})
            else:
                # A newly joined client adopts the current board state of the
                # clients already in the session. Existing clients already have
                # their own board and must not overwrite it with the joiner's
                # snapshot when they acknowledge the hello.
                for other in others:
                    self._send(handler, {"type": "board", "board": other.board})

    def broadcast_board(self, sender: _CollaborationHandler, board: dict[str, Any]) -> None:
        message = {"type": "board", "board": board}
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            if client is sender:
                continue
            try:
                self._send(client, message)
            except OSError:
                self.unregister_client(client)

    def broadcast_cursor(self, sender: _CollaborationHandler, message: dict[str, Any]) -> None:
        cursor = {
            "type": "cursor",
            "x": float(message.get("x") or 0.0),
            "y": float(message.get("y") or 0.0),
            "user": message.get("user") or {"id": "anonymous", "name": "Guest"},
        }
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            if client is sender:
                continue
            try:
                self._send(client, cursor)
            except OSError:
                self.unregister_client(client)


class _CollaborationHandler(socketserver.BaseRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.client_id: int = 0
        self.user: dict[str, Any] = {
            "id": "anonymous",
            "name": "Guest",
            "color": "#94a3b8",
        }
        self.board: dict[str, Any] = {
            "format": BOARD_FORMAT,
            "version": BOARD_VERSION,
            "items": [],
        }
        self.server.register_client(self)

    def handle(self) -> None:
        reader = self.request.makefile("rb")
        while True:
            line = reader.readline()
            if not line:
                break
            try:
                message = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            kind = message.get("type")
            if kind == "hello":
                self.server.handle_hello(self, message)
            elif kind == "board":
                board = message.get("board")
                if isinstance(board, dict):
                    self.board = board
                    self.server.broadcast_board(self, board)
            elif kind == "cursor":
                self.server.broadcast_cursor(self, message)

    def finish(self) -> None:
        self.server.unregister_client(self)
        try:
            self.request.close()
        except OSError:
            pass


def _json_line(message: dict[str, Any]) -> bytes:
    return json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"


class CollaborationClient(QObject):
    """Qt-facing client for the newline-delimited collaboration relay."""

    board_received = Signal(dict)
    cursor_received = Signal(dict)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._socket: socket.socket | None = None
        self._reader: Any = None
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._ready = threading.Event()
        self._host = "127.0.0.1"
        self._port = COLLABORATION_PORT
        self._user_id = "local"
        self._user_name = "You"
        self._user_color = "#38bdf8"
        self._board: dict[str, Any] = {
            "format": BOARD_FORMAT,
            "version": BOARD_VERSION,
            "items": [],
        }

    def start(
        self,
        host: str,
        port: int,
        user_id: str,
        user_name: str,
        color: str = "#38bdf8",
        board: dict[str, Any] | None = None,
    ) -> None:
        self._host = str(host)
        self._port = int(port)
        self._user_id = str(user_id)
        self._user_name = str(user_name)
        self._user_color = str(color)
        self._board = dict(board) if board is not None else {
            "format": BOARD_FORMAT,
            "version": BOARD_VERSION,
            "items": [],
        }
        self._stopping = False
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run, name="canvasity-collab-client", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(10.0):
            self.stop()
            raise ConnectionError(f"Collaboration client did not connect to {host}:{port}")

    def _run(self) -> None:
        try:
            self._socket = socket.create_connection((self._host, self._port), timeout=10.0)
            self._socket.settimeout(None)
            self._reader = self._socket.makefile("rb")
            self._send_raw(
                {
                    "type": "hello",
                    "user": {
                        "id": self._user_id,
                        "name": self._user_name,
                        "color": self._user_color,
                    },
                    "board": self._board,
                }
            )
            self._ready.set()
            while not self._stopping:
                line = self._reader.readline()
                if not line:
                    break
                try:
                    message = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                kind = message.get("type")
                if kind == "board":
                    self.board_received.emit(message.get("board") or self._board)
                elif kind == "cursor":
                    self.cursor_received.emit(message)
        except Exception as exc:  # pragma: no cover - exercised through error handling
            self.error_occurred.emit(f"Collaboration connection failed: {exc}")

    def _send_raw(self, message: dict[str, Any]) -> None:
        if self._socket is None:
            raise RuntimeError("Collaboration client is not connected")
        self._socket.sendall(_json_line(message))

    def send_hello(self) -> None:
        self._send_raw(
            {
                "type": "hello",
                "user": {
                    "id": self._user_id,
                    "name": self._user_name,
                    "color": self._user_color,
                },
                "board": self._board,
            }
        )

    def send_board(self, board: dict[str, Any]) -> None:
        self._board = board
        self._send_raw({"type": "board", "board": board})

    def send_cursor(self, x: float, y: float, user: dict[str, Any]) -> None:
        self._send_raw(
            {
                "type": "cursor",
                "x": float(x),
                "y": float(y),
                "user": user,
            }
        )

    def stop(self) -> None:
        self._stopping = True
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        socket = self._socket
        if socket is not None:
            try:
                socket.close()
            except OSError:
                pass
        self._socket = None
        self._reader = None
