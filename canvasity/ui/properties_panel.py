"""Contextual properties panel for the current selection."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..canvas.scene import BoardScene
from ..objects import BoardItem, TextItem
from ..theme import LIGHT, Palette
from .icons import icon


class ColorButton(QToolButton):
    color_changed = Signal(QColor)

    def __init__(self, alpha: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("#ffffff")
        self._alpha = alpha
        self.setFixedSize(34, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose colour")
        self.clicked.connect(self._pick)
        self.set_color(self._color)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor, emit: bool = False) -> None:
        if color.isValid():
            self._color = QColor(color)
        c = self._color
        self.setStyleSheet(
            "QToolButton {"
            f"background: rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha() / 255:.3f});"
            "border: 1px solid rgba(120, 130, 145, 0.55);"
            "border-radius: 6px;"
            "}"
            "QToolButton:hover { border-color: rgba(70, 90, 120, 0.9); }"
        )
        if emit:
            self.color_changed.emit(self._color)

    def _pick(self) -> None:
        options = (
            QColorDialog.ColorDialogOption.ShowAlphaChannel
            if self._alpha
            else QColorDialog.ColorDialogOption(0)
        )
        chosen = QColorDialog.getColor(self._color, self, "Choose colour", options)
        if chosen.isValid():
            self.set_color(chosen, emit=True)


class PropertiesPanel(QWidget):
    def __init__(self, scene: BoardScene, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self._palette: Palette = LIGHT
        self._building = False
        self._icon_buttons: list[tuple[QToolButton, str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("PropertiesContent")
        self.layout = QVBoxLayout(content)
        self.layout.setContentsMargins(12, 10, 12, 14)
        self.layout.setSpacing(9)
        scroll.setWidget(content)

        self._build_header()
        self._build_appearance()
        self._build_text()
        self._build_arrange()
        self.layout.addStretch(1)

        scene.selection_info_changed.connect(self.sync_from_selection)
        self.sync_from_selection()

    # ------------------------------------------------------------------ helpers
    def _tool_button(
        self,
        icon_name: str,
        tooltip: str,
        slot: Callable[[], None],
        checkable: bool = False,
    ) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setIcon(icon(icon_name, self._palette))
        button.setIconSize(QSize(17, 17))
        button.setCheckable(checkable)
        button.clicked.connect(lambda _checked=False: slot())
        self._icon_buttons.append((button, icon_name))
        return button

    @staticmethod
    def _row(label: str, widget: QWidget) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        text = QLabel(label)
        text.setMinimumWidth(48)
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

    def _items_with(self, attr: str) -> list[BoardItem]:
        return [
            item
            for item in self.scene.selected_board_items()
            if getattr(item, attr, False)
        ]

    # ------------------------------------------------------------------ sections
    def _build_header(self) -> None:
        self.summary = QLabel("Nothing selected")
        self.summary.setWordWrap(True)
        self.layout.addWidget(self.summary)

        self.quick = QWidget()
        row = QHBoxLayout(self.quick)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.duplicate_btn = self._tool_button(
            "duplicate", "Duplicate (Ctrl+D)", self.scene.duplicate_selected
        )
        self.delete_btn = self._tool_button(
            "delete", "Delete (Del)", self.scene.delete_selected
        )
        row.addWidget(self.duplicate_btn)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        self.layout.addWidget(self.quick)

    def _build_appearance(self) -> None:
        self.appearance_group, layout = self._new_group("Appearance")

        self.fill_button = ColorButton(alpha=True)
        self.fill_button.color_changed.connect(self._on_fill)
        self.fill_row = self._row("Fill", self.fill_button)
        layout.addWidget(self.fill_row)

        self.stroke_button = ColorButton(alpha=False)
        self.stroke_button.color_changed.connect(self._on_stroke)
        self.stroke_row = self._row("Stroke", self.stroke_button)
        layout.addWidget(self.stroke_row)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 40)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(self._on_width)
        self.width_row = self._row("Width", self.width_spin)
        layout.addWidget(self.width_row)

        opacity_holder = QWidget()
        opacity_layout = QHBoxLayout(opacity_holder)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(8)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setMinimumWidth(38)
        self.opacity_label.setObjectName("SectionHint")
        opacity_layout.addWidget(self.opacity_slider, 1)
        opacity_layout.addWidget(self.opacity_label)
        self.opacity_row = self._row("Opacity", opacity_holder)
        layout.addWidget(self.opacity_row)

    def _build_text(self) -> None:
        self.text_group, layout = self._new_group("Text")

        self.text_color_button = ColorButton(alpha=False)
        self.text_color_button.color_changed.connect(self._on_text_color)
        self.text_color_row = self._row("Colour", self.text_color_button)
        layout.addWidget(self.text_color_row)

        self.font_spin = QSpinBox()
        self.font_spin.setRange(6, 120)
        self.font_spin.setSuffix(" pt")
        self.font_spin.valueChanged.connect(self._on_font_size)
        self.font_size_row = self._row("Size", self.font_spin)
        layout.addWidget(self.font_size_row)

        self.format_row = QWidget()
        format_layout = QHBoxLayout(self.format_row)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(3)
        self.bold_btn = self._tool_button("bold", "Bold", lambda: None, checkable=True)
        self.italic_btn = self._tool_button("italic", "Italic", lambda: None, checkable=True)
        self.underline_btn = self._tool_button(
            "underline", "Underline", lambda: None, checkable=True
        )
        self.bold_btn.toggled.connect(self._on_bold)
        self.italic_btn.toggled.connect(self._on_italic)
        self.underline_btn.toggled.connect(self._on_underline)
        for button in (self.bold_btn, self.italic_btn, self.underline_btn):
            format_layout.addWidget(button)
        format_layout.addStretch(1)
        layout.addWidget(self.format_row)

        self.align_row = QWidget()
        align_layout = QHBoxLayout(self.align_row)
        align_layout.setContentsMargins(0, 0, 0, 0)
        align_layout.setSpacing(3)
        self.align_group = QButtonGroup(self)
        self.align_group.setExclusive(True)
        specs = [
            ("align_left", "Align left", "left"),
            ("align_center", "Align centre", "center"),
            ("align_right", "Align right", "right"),
        ]
        for index, (name, tooltip, value) in enumerate(specs):
            button = self._tool_button(name, tooltip, lambda: None, checkable=True)
            button.setProperty("alignment_value", value)
            self.align_group.addButton(button, index)
            align_layout.addWidget(button)
        align_layout.addStretch(1)
        self.align_group.idClicked.connect(self._on_alignment)
        layout.addWidget(self.align_row)

    def _build_arrange(self) -> None:
        self.arrange_group, layout = self._new_group("Arrange")

        z_row = QWidget()
        z_layout = QHBoxLayout(z_row)
        z_layout.setContentsMargins(0, 0, 0, 0)
        z_layout.setSpacing(3)
        z_actions = [
            ("front", "Bring to front", "front"),
            ("forward", "Bring forward", "forward"),
            ("backward", "Send backward", "backward"),
            ("back", "Send to back", "back"),
        ]
        for icon_name, tooltip, mode in z_actions:
            button = self._tool_button(
                icon_name, tooltip, lambda m=mode: self.scene.reorder_selected(m)
            )
            z_layout.addWidget(button)
        z_layout.addStretch(1)
        layout.addWidget(z_row)

        align_holder = QWidget()
        align_grid = QHBoxLayout(align_holder)
        align_grid.setContentsMargins(0, 0, 0, 0)
        align_grid.setSpacing(3)
        align_actions = [
            ("align_left", "Align left", "left"),
            ("align_center", "Align horizontal centres", "hcenter"),
            ("align_right", "Align right", "right"),
            ("align_top", "Align top", "top"),
            ("align_middle", "Align vertical centres", "vcenter"),
            ("align_bottom", "Align bottom", "bottom"),
        ]
        self.align_object_buttons: list[QToolButton] = []
        for icon_name, tooltip, mode in align_actions:
            button = self._tool_button(
                icon_name, tooltip, lambda m=mode: self.scene.align_selected(m)
            )
            self.align_object_buttons.append(button)
            align_grid.addWidget(button)
        align_grid.addStretch(1)
        layout.addWidget(align_holder)

        group_row = QWidget()
        group_layout = QHBoxLayout(group_row)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(3)
        self.group_btn = self._tool_button(
            "group", "Group (Ctrl+G)", self.scene.group_selected
        )
        self.ungroup_btn = self._tool_button(
            "ungroup", "Ungroup (Ctrl+Shift+G)", self.scene.ungroup_selected
        )
        group_layout.addWidget(self.group_btn)
        group_layout.addWidget(self.ungroup_btn)
        group_layout.addStretch(1)
        layout.addWidget(group_row)

    # ------------------------------------------------------------------ sync
    def sync_from_selection(self) -> None:
        items = self.scene.selected_board_items()
        self._building = True
        try:
            count = len(items)
            if not items:
                self.summary.setText("Nothing selected \u2014 pick a tool or select an object.")
            elif count == 1:
                label = items[0].TYPE.capitalize()
                self.summary.setText(f"{label} selected")
            else:
                self.summary.setText(f"{count} objects selected")

            self.quick.setVisible(bool(items))

            fill_items = self._items_with("SUPPORTS_FILL")
            stroke_items = self._items_with("SUPPORTS_STROKE")
            width_items = [item for item in items if hasattr(item, "stroke_width")]
            text_items = [item for item in items if item.SUPPORTS_TEXT]

            self.fill_row.setVisible(bool(fill_items))
            self.stroke_row.setVisible(bool(stroke_items))
            self.width_row.setVisible(bool(width_items))
            self.opacity_row.setVisible(bool(items))
            if fill_items and hasattr(fill_items[0], "fill"):
                self.fill_button.set_color(fill_items[0].fill)
            if stroke_items and hasattr(stroke_items[0], "stroke"):
                self.stroke_button.set_color(stroke_items[0].stroke)
            if width_items:
                self.width_spin.setValue(int(round(float(width_items[0].stroke_width))))
            if items:
                self.opacity_slider.setValue(int(round(items[0].opacity() * 100)))
                self.opacity_label.setText(f"{self.opacity_slider.value()}%")
            self.appearance_group.setVisible(bool(items))

            self.text_group.setVisible(bool(text_items))
            if text_items:
                first = text_items[0]
                if hasattr(first, "text_color"):
                    self.text_color_button.set_color(first.text_color)
                if hasattr(first, "font_size"):
                    self.font_spin.setValue(int(round(first.font_size)))
                formatting = any(isinstance(item, TextItem) for item in text_items)
                self.format_row.setVisible(formatting)
                self.align_row.setVisible(formatting)
                if formatting:
                    text = next(item for item in text_items if isinstance(item, TextItem))
                    self.bold_btn.setChecked(text.bold)
                    self.italic_btn.setChecked(text.italic)
                    self.underline_btn.setChecked(text.underline)
                    button = next(
                        (
                            b
                            for b in self.align_group.buttons()
                            if b.property("alignment_value") == text.alignment_name
                        ),
                        None,
                    )
                    if button is not None:
                        button.setChecked(True)
                    else:
                        self.align_group.setExclusive(False)
                        for b in self.align_group.buttons():
                            b.setChecked(False)
                        self.align_group.setExclusive(True)

            self.arrange_group.setVisible(bool(items))
            for button in self.align_object_buttons:
                button.setEnabled(count >= 2)
            self.group_btn.setEnabled(count >= 2)
            self.ungroup_btn.setEnabled(any(item.group_id for item in items))
        finally:
            self._building = False

    # ------------------------------------------------------------------ handlers
    def _on_fill(self, color: QColor) -> None:
        if self._building:
            return
        items = self._items_with("SUPPORTS_FILL")
        if items:
            self.scene.apply_change(items, lambda item: item.set_fill(color), "Change fill")
        else:
            self.scene.defaults["fill"] = color.name()

    def _on_stroke(self, color: QColor) -> None:
        if self._building:
            return
        items = self._items_with("SUPPORTS_STROKE")
        if items:
            self.scene.apply_change(
                items, lambda item: item.set_stroke(color), "Change stroke"
            )
        else:
            self.scene.defaults["stroke"] = color.name()

    def _on_width(self, value: int) -> None:
        if self._building:
            return
        items = [item for item in self.scene.selected_board_items() if hasattr(item, "stroke_width")]
        self.scene.apply_change(
            items,
            lambda item: item.set_stroke_width(float(value)),
            "Change stroke width",
            mergeable=True,
        )

    def _on_opacity(self, value: int) -> None:
        self.opacity_label.setText(f"{value}%")
        if self._building:
            return
        items = self.scene.selected_board_items()
        self.scene.apply_change(
            items,
            lambda item: item.setOpacity(value / 100.0),
            "Change opacity",
            mergeable=True,
        )

    def _on_text_color(self, color: QColor) -> None:
        if self._building:
            return
        items = [item for item in self.scene.selected_board_items() if item.SUPPORTS_TEXT]
        self.scene.apply_change(
            items, lambda item: item.set_text_color(color), "Change text colour"
        )

    def _on_font_size(self, value: int) -> None:
        if self._building:
            return
        items = [item for item in self.scene.selected_board_items() if item.SUPPORTS_TEXT]
        self.scene.apply_change(
            items,
            lambda item: item.set_font_size(float(value)),
            "Change font size",
            mergeable=True,
        )

    def _text_items(self) -> list[TextItem]:
        return [
            item
            for item in self.scene.selected_board_items()
            if isinstance(item, TextItem)
        ]

    def _on_bold(self, checked: bool) -> None:
        if not self._building:
            items = self._text_items()
            self.scene.apply_change(
                items, lambda item: item.set_bold(checked), "Toggle bold"
            )

    def _on_italic(self, checked: bool) -> None:
        if not self._building:
            items = self._text_items()
            self.scene.apply_change(
                items, lambda item: item.set_italic(checked), "Toggle italic"
            )

    def _on_underline(self, checked: bool) -> None:
        if not self._building:
            items = self._text_items()
            self.scene.apply_change(
                items, lambda item: item.set_underline(checked), "Toggle underline"
            )

    def _on_alignment(self, index: int) -> None:
        if self._building:
            return
        button = self.align_group.button(index)
        name = button.property("alignment_value") if button else None
        if not name:
            return
        items = self._text_items()
        self.scene.apply_change(
            items, lambda item: item.set_alignment(str(name)), "Change alignment"
        )

    # ------------------------------------------------------------------ theme
    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        for button, name in self._icon_buttons:
            button.setIcon(icon(name, palette))
