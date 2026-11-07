"""Application-wide constants and defaults."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths

APP_NAME = "Canvasity"
APP_ORG = "Canvasity"
APP_VERSION = "0.4.0"

BOARD_EXTENSION = ".canvasity"
BOARD_FORMAT = "canvasity"
BOARD_VERSION = 1

GRID_SIZE = 20.0
MAJOR_GRID = 5  # every 5th line is drawn darker
MIN_ZOOM = 0.05
MAX_ZOOM = 32.0
ZOOM_STEP = 1.25
GRID_VISIBLE_SCALE = 0.35  # hide the grid when zoomed further out than this
SCENE_LIMIT = 50_000.0
NUDGE_STEP = 1.0
NUDGE_STEP_LARGE = 10.0

MIN_ITEM_SIZE = 8.0
SNAP_THRESHOLD_PX = 7.0
AUTOSAVE_INTERVAL_MS = 30_000

COLLABORATION_HOST = "0.0.0.0"
COLLABORATION_PORT = 8765
COLLABORATION_LOCAL_HOST = "127.0.0.1"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}

DEFAULT_FILL = "#ffffff"
DEFAULT_STROKE = "#334155"
DEFAULT_TEXT = "#0f172a"
DEFAULT_STICKY = "#fde68a"
DEFAULT_PEN = "#0f172a"
DEFAULT_FONT = "Inter"
DEFAULT_FONT_SIZE = 16

STICKY_FONT_SIZE = 15


def app_data_dir() -> Path:
    """Return (and create) the per-user application data directory."""
    raw = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    path = Path(raw) if raw else Path.home() / ".canvasity"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_board_name() -> str:
    return "Untitled"
