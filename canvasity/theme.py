"""Light and dark theme palettes and the stylesheet that drives the chrome."""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    name: str
    window: str
    panel: str
    panel_alt: str
    canvas: str
    text: str
    muted: str
    border: str
    accent: str
    accent_text: str
    hover: str
    grid_minor: str
    grid_major: str
    selection: str
    danger: str
    shadow: str


LIGHT = Palette(
    name="light",
    window="#eef2f7",
    panel="#ffffff",
    panel_alt="#f8fafc",
    canvas="#ffffff",
    text="#0f172a",
    muted="#64748b",
    border="#e2e8f0",
    accent="#2563eb",
    accent_text="#ffffff",
    hover="#eff4ff",
    grid_minor="#e9eef5",
    grid_major="#d9e2ec",
    selection="#2563eb",
    danger="#dc2626",
    shadow="#94a3b8",
)

DARK = Palette(
    name="dark",
    window="#0b1220",
    panel="#111827",
    panel_alt="#0f172a",
    canvas="#1e293b",
    text="#e5e7eb",
    muted="#94a3b8",
    border="#2b3648",
    accent="#3b82f6",
    accent_text="#ffffff",
    hover="#1e293b",
    grid_minor="#263447",
    grid_major="#334155",
    selection="#60a5fa",
    danger="#f87171",
    shadow="#020617",
)

PALETTES = {LIGHT.name: LIGHT, DARK.name: DARK}

_QSS = Template(
    """
QWidget {
    color: $text;
    font-family: "Inter", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background: $window; }

QToolBar {
    background: $panel;
    border: none;
    spacing: 3px;
    padding: 5px;
}
QToolBar#TopToolBar { border-bottom: 1px solid $border; padding: 6px 8px; }
QToolBar#ToolPalette { border-right: 1px solid $border; padding: 7px 5px; }
QToolBar::separator { background: $border; width: 1px; height: 1px; margin: 4px 5px; }

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px;
}
QToolButton:hover { background: $hover; }
QToolButton:pressed { background: $border; }
QToolButton:checked { background: $accent; border-color: $accent; }
QToolButton#DangerToolButton:hover { background: rgba(220, 38, 38, 0.12); }
QToolButton::menu-indicator { image: none; }

QPushButton {
    background: $panel_alt;
    border: 1px solid $border;
    border-radius: 7px;
    padding: 6px 12px;
}
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted; background: transparent; }
QPushButton#PrimaryButton {
    background: $accent;
    color: $accent_text;
    border-color: $accent;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover { background: $accent; color: $accent_text; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $panel_alt;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px 7px;
    selection-background-color: $accent;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: $panel;
    border: 1px solid $border;
    selection-background-color: $accent;
    selection-color: $accent_text;
    outline: none;
}

QCheckBox { spacing: 7px; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid $border;
    border-radius: 4px;
    background: $panel_alt;
}
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }

QSlider::groove:horizontal { height: 4px; background: $border; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px; background: $accent;
}

QDockWidget { titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title {
    background: $panel;
    border-bottom: 1px solid $border;
    padding: 8px 12px;
    font-weight: 600;
}

QGroupBox {
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    background: $panel;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: $muted;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
}

QMenuBar { background: $panel; border-bottom: 1px solid $border; }
QMenuBar::item { padding: 5px 10px; background: transparent; border-radius: 5px; }
QMenuBar::item:selected { background: $hover; }
QMenu {
    background: $panel;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item { padding: 7px 26px 7px 12px; border-radius: 5px; }
QMenu::item:selected { background: $accent; color: $accent_text; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }

QStatusBar {
    background: $panel;
    border-top: 1px solid $border;
    color: $muted;
}
QStatusBar::item { border: none; }

QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    width: 10px; height: 10px;
    margin: 0;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: $border;
    border-radius: 5px;
    min-height: 30px; min-width: 30px;
}
QScrollBar::handle:hover { background: $muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QGraphicsView { border: none; background: $canvas; }

QScrollArea { background: $panel; border: none; }
QScrollArea > QWidget > QWidget { background: $panel; }
QWidget#PropertiesContent { background: $panel; }
QAbstractScrollArea::corner { background: $panel; }

QLabel#SectionHint { color: $muted; font-size: 11px; }
QLabel#ZoomLabel { color: $text; font-weight: 600; min-width: 44px; }
QLabel#BoardName { font-weight: 600; font-size: 14px; }

QToolTip {
    background: $panel;
    color: $text;
    border: 1px solid $border;
    border-radius: 5px;
    padding: 5px 8px;
}
"""
)


def stylesheet(palette: Palette) -> str:
    return _QSS.substitute(
        window=palette.window,
        panel=palette.panel,
        panel_alt=palette.panel_alt,
        canvas=palette.canvas,
        text=palette.text,
        muted=palette.muted,
        border=palette.border,
        accent=palette.accent,
        accent_text=palette.accent_text,
        hover=palette.hover,
    )


class ThemeManager(QObject):
    """Owns the active palette and applies it to the whole application."""

    changed = Signal(object)

    def __init__(self, app: QApplication, name: str = "light") -> None:
        super().__init__()
        self._app = app
        self._palette = PALETTES.get(name, LIGHT)

    @property
    def palette(self) -> Palette:
        return self._palette

    @property
    def name(self) -> str:
        return self._palette.name

    def apply(self, name: str) -> None:
        palette = PALETTES.get(name, LIGHT)
        self._palette = palette
        self._app.setStyleSheet(stylesheet(palette))
        self.changed.emit(palette)

    def toggle(self) -> str:
        self.apply("dark" if self.name == "light" else "light")
        return self.name
