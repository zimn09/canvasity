"""Board persistence: versioned JSON files written atomically."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import BOARD_FORMAT


class BoardIOError(Exception):
    """Raised when a board cannot be read or written."""


def save_board(path: str | Path, data: dict[str, Any]) -> Path:
    target = Path(path)
    payload = dict(data)
    payload["app"] = "Canvasity"
    payload["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = json.dumps(payload, indent=1, ensure_ascii=False)
    parent = target.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(parent), prefix=f".{target.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise BoardIOError(f"Could not save the board: {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise BoardIOError(f"Board data could not be serialised: {exc}") from exc
    return target


def load_board(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise BoardIOError(f"Could not open the board: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise BoardIOError("The board file is not valid UTF-8 text") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BoardIOError(f"The board file is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise BoardIOError("The board file is malformed")
    if data.get("format") != BOARD_FORMAT:
        raise BoardIOError("This file is not a Canvasity board")
    return data


def autosave_path_for(board_path: str | Path) -> Path:
    path = Path(board_path)
    return path.with_name(path.name + ".autosave")


def recovery_path(app_data: Path) -> Path:
    return app_data / "recovery.canvasity"


def file_mtime(path: str | Path) -> float:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def remove_quietly(path: str | Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass
