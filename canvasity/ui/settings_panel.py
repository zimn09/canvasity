"""Application settings tab for appearance, canvas defaults and collaboration."""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..canvas.scene import BoardScene
from ..canvas.view import BoardView
from ..config import COLLABORATION_PORT
from .properties_panel import ColorButton


class SettingsPanel(QWidget):
    def __init__(
        self,
        scene: BoardScene,
        view: BoardView,
        theme_name: str,
        on_theme_changed: Callable[[str], None],
        collaboration_port: int,
        on_collaboration_port_changed: Callable[[int], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.scene = scene
        self.view = view
        self._on_theme_changed = on_theme_changed
        self._on_collaboration_port_changed = on_collaboration_port_changed
        self._building = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("SettingsContent")
        self.layout = QVBoxLayout(content)
        self.layout.setContentsMargins(12, 10, 12, 14)
        self.layout.setSpacing(9)
        scroll.setWidget(content)

        self._build_appearance(theme_name)
        self._build_canvas()
        self._build_defaults()
        self._build_collaboration(collaboration_port)
        self.layout.addStretch(1)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _row(label: str, widget: QWidget) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        text = QLabel(label)
        text.setMinimumWidth(70)
        text.setObjectName("SectionHint")
        layout.addWidget(text)
        layout.addWidget(widget, 1)
        return holder

    def _new_group(self, title: str) -> tuple[QGroupBox, QVBoxLayout]:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(9, 4, 9, 9)
        layout.setSpacing(7)
        self.layout.addWidget(group)
        return group, layout

    # ------------------------------------------------------------------ sections
    def _build_appearance(self, theme_name: str) -> None:
        _group, layout = self._new_group("Appearance")

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        index = self.theme_combo.findData(theme_name)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_selected)
        layout.addWidget(self._row("Theme", self.theme_combo))

    def _build_canvas(self) -> None:
        _group, layout = self._new_group("Canvas")

        self.grid_check = QCheckBox("Show grid")
        self.grid_check.setChecked(self.view.show_grid)
        self.grid_check.toggled.connect(self.view.set_grid_visible)
        layout.addWidget(self.grid_check)

        self.snap_check = QCheckBox("Snap to grid")
        self.snap_check.setChecked(self.scene.grid_snap)
        self.snap_check.toggled.connect(
            lambda value: self.scene.set_snapping(grid=value)
        )
        layout.addWidget(self.snap_check)

        self.align_check = QCheckBox("Snap to objects")
        self.align_check.setChecked(self.scene.align_snap)
        self.align_check.toggled.connect(
            lambda value: self.scene.set_snapping(align=value)
        )
        layout.addWidget(self.align_check)

    def _build_defaults(self) -> None:
        _group, layout = self._new_group("New object defaults")

        self.pen_color_button = ColorButton(alpha=False)
        self.pen_color_button.set_color(QColor(self.scene.defaults["pen_color"]))
        self.pen_color_button.color_changed.connect(self._on_pen_color)
        layout.addWidget(self._row("Pen colour", self.pen_color_button))

        self.pen_width_spin = QSpinBox()
        self.pen_width_spin.setRange(1, 40)
        self.pen_width_spin.setValue(int(self.scene.defaults["pen_width"]))
        self.pen_width_spin.setSuffix(" px")
        self.pen_width_spin.valueChanged.connect(self._on_pen_width)
        layout.addWidget(self._row("Pen size", self.pen_width_spin))

        self.default_fill_button = ColorButton(alpha=False)
        self.default_fill_button.set_color(QColor(self.scene.defaults["fill"]))
        self.default_fill_button.color_changed.connect(self._on_default_fill)
        layout.addWidget(self._row("Fill", self.default_fill_button))

        self.default_stroke_button = ColorButton(alpha=False)
        self.default_stroke_button.set_color(QColor(self.scene.defaults["stroke"]))
        self.default_stroke_button.color_changed.connect(self._on_default_stroke)
        layout.addWidget(self._row("Stroke", self.default_stroke_button))

    def _build_collaboration(self, port: int) -> None:
        _group, layout = self._new_group("Collaboration")

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(port)
        self.port_spin.valueChanged.connect(self._on_port_changed)
        layout.addWidget(self._row("Port", self.port_spin))

        hint = QLabel(
            f"Default: {COLLABORATION_PORT}. Used when starting or joining a session."
        )
        hint.setWordWrap(True)
        hint.setObjectName("SectionHint")
        layout.addWidget(hint)

    # ------------------------------------------------------------------ handlers
    def _on_theme_selected(self, _index: int) -> None:
        if self._building:
            return
        name = self.theme_combo.currentData()
        if name:
            self._on_theme_changed(str(name))

    def _on_pen_color(self, color: QColor) -> None:
        if not self._building:
            self.scene.defaults["pen_color"] = color.name()

    def _on_pen_width(self, value: int) -> None:
        if not self._building:
            self.scene.defaults["pen_width"] = float(value)

    def _on_default_fill(self, color: QColor) -> None:
        if not self._building:
            self.scene.defaults["fill"] = color.name()

    def _on_default_stroke(self, color: QColor) -> None:
        if not self._building:
            self.scene.defaults["stroke"] = color.name()

    def _on_port_changed(self, value: int) -> None:
        if not self._building:
            self._on_collaboration_port_changed(value)

    # ------------------------------------------------------------------ sync
    def set_theme_name(self, name: str) -> None:
        index = self.theme_combo.findData(name)
        if index < 0:
            return
        self._building = True
        try:
            self.theme_combo.setCurrentIndex(index)
        finally:
            self._building = False

    def refresh_defaults(self) -> None:
        self._building = True
        try:
            self.pen_color_button.set_color(QColor(self.scene.defaults["pen_color"]))
            self.pen_width_spin.setValue(int(self.scene.defaults["pen_width"]))
            self.default_fill_button.set_color(QColor(self.scene.defaults["fill"]))
            self.default_stroke_button.set_color(QColor(self.scene.defaults["stroke"]))
        finally:
            self._building = False
