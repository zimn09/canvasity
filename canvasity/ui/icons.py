"""Vector icon factory - icons are rendered from inline SVG and tinted to the theme."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..theme import LIGHT, Palette

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

PATHS: dict[str, str] = {
    "select": '<path d="M5 3.5 18.5 12l-6.2 1.2L9.6 19 5 3.5Z"/>',
    "pen": (
        '<path d="m4 20 3.7-.8L20 6.9a1.85 1.85 0 0 0-2.6-2.6L4.9 16.5 4 20Z"/>'
        '<path d="m15.7 5.7 2.6 2.6"/>'
    ),
    "eraser": (
        '<path d="m7.2 17.2-3.4-3.4 8.6-8.6a2 2 0 0 1 2.8 0l2.2 2.2a2 2 0 0 1 0 2.8L13 15"/>'
        '<path d="M7.2 17.2H18"/><path d="m10.6 9.6 4 4"/>'
    ),
    "sticky": '<path d="M5 4h14v10l-5 5H5V4Z"/><path d="M19 14h-5v5"/>',
    "text": '<path d="M5 6V4h14v2"/><path d="M12 4v16"/><path d="M9 20h6"/>',
    "checklist": (
        '<rect x="4.5" y="3.5" width="15" height="17" rx="2"/>'
        '<path d="m7.5 9 1.6 1.6L12 7.8"/><path d="M14.5 9.5h2.5"/>'
        '<path d="m7.5 15 1.6 1.6L12 13.8"/><path d="M14.5 15.5h2.5"/>'
    ),
    "rect": '<rect x="4" y="5" width="16" height="14" rx="1.5"/>',
    "ellipse": '<ellipse cx="12" cy="12" rx="8" ry="7"/>',
    "line": (
        '<path d="M4.5 19.5 19.5 4.5"/>'
        '<circle cx="4.5" cy="19.5" r="1.3"/><circle cx="19.5" cy="4.5" r="1.3"/>'
    ),
    "arrow": '<path d="M4 20 20 4"/><path d="M13 4h7v7"/>',
    "image": (
        '<rect x="3.5" y="5" width="17" height="14" rx="2"/>'
        '<circle cx="9" cy="10" r="1.6"/>'
        '<path d="m4.5 17.5 5-5 4 4 2.5-2.5 3.5 3.5"/>'
    ),
    "new": (
        '<path d="M7 3h7l4 4v14H7V3Z"/><path d="M14 3v5h5"/>'
        '<path d="M12 12v6"/><path d="M9 15h6"/>'
    ),
    "open": '<path d="M3 7h6l2 2h10v10H3V7Z"/><path d="M3 7V5h6l2 2"/>',
    "save": (
        '<path d="M5 3h12l3 3v15H5V3Z"/><path d="M8 3v6h8V3"/>'
        '<rect x="8" y="13" width="9" height="7"/>'
    ),
    "export": (
        '<path d="M12 3v11"/><path d="m8 10 4 4 4-4"/>'
        '<path d="M5 16v5h14v-5"/>'
    ),
    "undo": '<path d="M9 7 4 12l5 5"/><path d="M4 12h9a6 6 0 0 1 6 6v1"/>',
    "redo": '<path d="m15 7 5 5-5 5"/><path d="M20 12h-9a6 6 0 0 0-6 6v1"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4.2"/>'
        '<path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4'
        'M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/>'
    ),
    "moon": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z"/>',
    "grid": (
        '<rect x="4" y="4" width="16" height="16" rx="1"/>'
        '<path d="M4 9.3h16M4 14.7h16M9.3 4v16M14.7 4v16"/>'
    ),
    "zoom_in": (
        '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 4.5 4.5"/>'
        '<path d="M10.5 7.5v6M7.5 10.5h6"/>'
    ),
    "zoom_out": (
        '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 4.5 4.5"/>'
        '<path d="M7.5 10.5h6"/>'
    ),
    "fit": (
        '<path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5"/>'
        '<rect x="8.5" y="8.5" width="7" height="7" rx="1"/>'
    ),
    "delete": (
        '<path d="M4 7h16"/><path d="M9 7V4h6v3"/>'
        '<path d="M6 7l1 14h10l1-14"/><path d="M10 11v6M14 11v6"/>'
    ),
    "duplicate": (
        '<rect x="8" y="8" width="12" height="12" rx="1.5"/>'
        '<path d="M16 8V4H4v12h4"/>'
    ),
    "front": (
        '<rect x="4" y="4" width="11" height="11" rx="1.5"/>'
        '<rect x="9" y="9" width="11" height="11" rx="1.5" fill="{color}" opacity="0.15"/>'
    ),
    "back": (
        '<rect x="9" y="9" width="11" height="11" rx="1.5"/>'
        '<rect x="4" y="4" width="11" height="11" rx="1.5" fill="{color}" opacity="0.15"/>'
    ),
    "forward": '<path d="M12 20V4"/><path d="m6 10 6-6 6 6"/>',
    "backward": '<path d="M12 4v16"/><path d="m6 14 6 6 6-6"/>',
    "group": (
        '<rect x="3.5" y="3.5" width="7" height="7" rx="1"/>'
        '<rect x="13.5" y="3.5" width="7" height="7" rx="1"/>'
        '<rect x="3.5" y="13.5" width="7" height="7" rx="1"/>'
        '<rect x="13.5" y="13.5" width="7" height="7" rx="1"/>'
    ),
    "ungroup": (
        '<rect x="3" y="3" width="9" height="9" rx="1"/>'
        '<path d="M15 15h6v6h-6z" stroke-dasharray="2 2"/>'
    ),
    "bold": '<path d="M7 4h6a4 4 0 0 1 0 8H7V4Z"/><path d="M7 12h7a4 4 0 0 1 0 8H7v-8Z"/>',
    "italic": '<path d="M10 4h8M6 20h8M15 4 9 20"/>',
    "underline": '<path d="M7 4v6a5 5 0 0 0 10 0V4"/><path d="M5 20h14"/>',
    "align_left": '<path d="M4 6h16M4 12h10M4 18h14"/>',
    "align_center": '<path d="M4 6h16M7 12h10M5 18h14"/>',
    "align_right": '<path d="M4 6h16M10 12h10M6 18h14"/>',
    "align_top": '<path d="M4 4h16M6 8v10M12 8v14M18 8v8"/>',
    "align_middle": '<path d="M4 12h16M8 4v10M16 4v16"/>',
    "align_bottom": '<path d="M4 20h16M6 6v10M12 2v14M18 8v8"/>',
}


@lru_cache(maxsize=256)
def _render(name: str, color: str, size: int) -> QPixmap:
    body = PATHS.get(name, PATHS["rect"]).replace("{color}", color)
    svg = _TEMPLATE.format(color=color, body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def icon(name: str, palette: Palette = LIGHT, size: int = 20) -> QIcon:
    result = QIcon()
    tint = palette.text
    on_tint = palette.accent_text
    disabled = palette.muted
    normal = _render(name, tint, size)
    checked = _render(name, on_tint, size)
    muted = _render(name, disabled, size)
    for mode in (
        QIcon.Mode.Normal,
        QIcon.Mode.Active,
        QIcon.Mode.Selected,
    ):
        result.addPixmap(normal, mode, QIcon.State.Off)
        result.addPixmap(checked, mode, QIcon.State.On)
    result.addPixmap(muted, QIcon.Mode.Disabled, QIcon.State.Off)
    return result


def app_icon() -> QIcon:
    path = Path(__file__).resolve().parent.parent / "assets" / "icons" / "logo.svg"
    if path.exists():
        return QIcon(str(path))
    return icon("sticky")
