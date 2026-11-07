"""Main application window: toolbars, menus, panels and document lifecycle."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QToolButton,
    QWidget,
)

from ..canvas.scene import BoardScene
from ..canvas.view import BoardView
from ..config import (
    APP_NAME,
    APP_ORG,
    APP_VERSION,
    AUTOSAVE_INTERVAL_MS,
    BOARD_EXTENSION,
    DEFAULT_STROKE,
    default_board_name,
    app_data_dir,
)
from ..export import ExportError, export_pdf, export_png
from ..objects import LineItem, ShapeItem, StrokeItem, TextItem
from ..storage import (
    BoardIOError,
    autosave_path_for,
    file_mtime,
    load_board,
    recovery_path,
    remove_quietly,
    save_board,
)
from ..theme import Palette, ThemeManager
from .icons import app_icon, icon
from .properties_panel import PropertiesPanel

logger = logging.getLogger(__name__)

TOOL_SPECS = [
    ("select", "select", "Select", "V"),
    ("pen", "pen", "Pen", "P"),
    ("eraser", "eraser", "Eraser", "E"),
    ("sticky", "sticky", "Sticky note", "S"),
    ("text", "text", "Text", "T"),
    ("checklist", "checklist", "To-do checklist", "C"),
    ("rect", "rect", "Rectangle", "R"),
    ("ellipse", "ellipse", "Ellipse", "O"),
    ("line", "line", "Line", "L"),
    ("arrow", "arrow", "Arrow", "A"),
    ("image", "image", "Insert image", "I"),
]


class CanvasityWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = QSettings(APP_ORG, APP_NAME)
        application = QApplication.instance()
        if application is None:
            raise RuntimeError("CanvasityWindow requires a QApplication")
        self.theme = ThemeManager(application, str(self.settings.value("theme", "light")))

        self._path: Path | None = None
        self._name = default_board_name()
        self._meta_dirty = False
        self._recovery_checked = False
        self._action_icons: dict[QAction, str] = {}
        self._button_icons: list[tuple[QToolButton, str]] = []

        self.scene = BoardScene(self)
        self.view = BoardView(self.scene, self)
        self.setCentralWidget(self.view)
        self.resize(1440, 900)
        self.setMinimumSize(960, 640)
        self.setWindowIcon(app_icon())

        self.panel = PropertiesPanel(self.scene, self.view, self)
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_dock()
        self._build_status_bar()
        self._connect_signals()
        self._restore_geometry()

        self.theme.changed.connect(self._apply_theme)
        self.theme.apply(self.theme.name)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        self._update_title()
        self._update_status()
        self._update_editing_state()

    # ------------------------------------------------------------------ helpers
    @property
    def dirty(self) -> bool:
        return self._meta_dirty or not self.scene.undo_stack.isClean()

    def _make_action(
        self,
        text: str,
        icon_name: str | None = None,
        shortcut: str | list[str] | None = None,
        slot: Callable[[], None] | None = None,
        checkable: bool = False,
        tooltip: str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icon(icon_name, self.theme.palette))
            self._action_icons[action] = icon_name
        if shortcut:
            if isinstance(shortcut, list):
                action.setShortcuts([QKeySequence(value) for value in shortcut])
            else:
                action.setShortcut(QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        if slot is not None:
            action.triggered.connect(lambda _checked=False: slot())
        if tooltip:
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
        return action

    def _build_actions(self) -> None:
        self.new_action = self._make_action(
            "New board", "new", "Ctrl+N", self.new_board, tooltip="New board (Ctrl+N)"
        )
        self.open_action = self._make_action(
            "Open board…", "open", "Ctrl+O", self.open_board, tooltip="Open board (Ctrl+O)"
        )
        self.save_action = self._make_action(
            "Save", "save", "Ctrl+S", self.save_board, tooltip="Save (Ctrl+S)"
        )
        self.save_as_action = self._make_action(
            "Save as…",
            "save",
            "Ctrl+Shift+S",
            self.save_board_as,
            tooltip="Save as (Ctrl+Shift+S)",
        )
        self.rename_action = self._make_action(
            "Rename board…", None, "F2", self.rename_board, tooltip="Rename board (F2)"
        )
        self.export_png_action = self._make_action(
            "Export as PNG…", "image", None, self.export_to_png
        )
        self.export_pdf_action = self._make_action(
            "Export as PDF…", "export", None, self.export_to_pdf
        )
        self.quit_action = self._make_action("Exit", None, "Ctrl+Q", self.close)

        stack = self.scene.undo_stack
        self.undo_action = stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.setIcon(icon("undo", self.theme.palette))
        self._action_icons[self.undo_action] = "undo"
        self.redo_action = stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcuts(
            [QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")]
        )
        self.redo_action.setIcon(icon("redo", self.theme.palette))
        self._action_icons[self.redo_action] = "redo"

        self.cut_action = self._make_action(
            "Cut", None, "Ctrl+X", self.scene.cut_selected, tooltip="Cut (Ctrl+X)"
        )
        self.copy_action = self._make_action(
            "Copy", None, "Ctrl+C", self.scene.copy_selection, tooltip="Copy (Ctrl+C)"
        )
        self.paste_action = self._make_action(
            "Paste", None, "Ctrl+V", self.scene.paste, tooltip="Paste (Ctrl+V)"
        )
        self.duplicate_action = self._make_action(
            "Duplicate",
            "duplicate",
            "Ctrl+D",
            self.scene.duplicate_selected,
            tooltip="Duplicate (Ctrl+D)",
        )
        self.delete_action = self._make_action(
            "Delete",
            "delete",
            "Delete",
            self.scene.delete_selected,
            tooltip="Delete (Del)",
        )
        self.select_all_action = self._make_action(
            "Select all", None, "Ctrl+A", self.scene.select_all
        )
        self.group_action = self._make_action(
            "Group", "group", "Ctrl+G", self.scene.group_selected, tooltip="Group (Ctrl+G)"
        )
        self.ungroup_action = self._make_action(
            "Ungroup",
            "ungroup",
            "Ctrl+Shift+G",
            self.scene.ungroup_selected,
            tooltip="Ungroup (Ctrl+Shift+G)",
        )

        self.zoom_in_action = self._make_action(
            "Zoom in", "zoom_in", ["Ctrl+=", "Ctrl++"], self.view.zoom_in
        )
        self.zoom_out_action = self._make_action(
            "Zoom out", "zoom_out", "Ctrl+-", self.view.zoom_out
        )
        self.zoom_reset_action = self._make_action(
            "Actual size", None, "Ctrl+1", self.view.reset_zoom
        )
        self.fit_action = self._make_action(
            "Fit to screen", "fit", "Ctrl+0", self.view.fit_to_content
        )
        self.grid_action = self._make_action(
            "Show grid", "grid", None, self._toggle_grid, checkable=True
        )
        self.grid_action.setChecked(self.view.show_grid)
        self.theme_action = self._make_action(
            "Toggle dark mode", "moon", "Ctrl+Shift+T", self.toggle_theme
        )
        self.about_action = self._make_action("About Canvasity", None, None, self._about)

        self._editing_actions = [
            self.cut_action,
            self.copy_action,
            self.paste_action,
            self.duplicate_action,
            self.delete_action,
            self.select_all_action,
            self.group_action,
            self.ungroup_action,
        ]
        # Canvas shortcuts should only fire while the canvas has focus, so they
        # never steal Delete/Ctrl+Z/etc. from widgets in the properties panel.
        view_actions = [
            self.undo_action,
            self.redo_action,
            *self._editing_actions,
            self.zoom_in_action,
            self.zoom_out_action,
            self.zoom_reset_action,
            self.fit_action,
        ]
        for action in view_actions:
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.view.addAction(action)

    def _build_menus(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addAction(self.rename_action)
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("Export")
        export_menu.addAction(self.export_png_action)
        export_menu.addAction(self.export_pdf_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = menu.addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.duplicate_action)
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.select_all_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.group_action)
        edit_menu.addAction(self.ungroup_action)

        view_menu = menu.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.zoom_reset_action)
        view_menu.addAction(self.fit_action)
        view_menu.addSeparator()
        view_menu.addAction(self.grid_action)
        view_menu.addAction(self.theme_action)

        help_menu = menu.addMenu("&Help")
        help_menu.addAction(self.about_action)

    def _build_toolbars(self) -> None:
        palette = self.theme.palette
        top = QToolBar("Main", self)
        top.setObjectName("TopToolBar")
        top.setMovable(False)
        top.setFloatable(False)
        top.setIconSize(QSize(19, 19))
        top.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, top)

        for action in (
            self.new_action,
            self.open_action,
            self.save_action,
        ):
            top.addAction(action)
        top.addSeparator()
        top.addAction(self.undo_action)
        top.addAction(self.redo_action)
        top.addSeparator()

        export_button = QToolButton(top)
        export_button.setIcon(icon("export", palette))
        export_button.setToolTip("Export board")
        export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_button.setAutoRaise(True)
        export_menu = export_button.menu()
        if export_menu is None:
            from PySide6.QtWidgets import QMenu

            export_menu = QMenu(export_button)
            export_button.setMenu(export_menu)
        export_menu.addAction(self.export_png_action)
        export_menu.addAction(self.export_pdf_action)
        top.addWidget(export_button)
        self._button_icons.append((export_button, "export"))

        spacer_left = QWidget(top)
        spacer_left.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top.addWidget(spacer_left)

        self.board_label = QLabel(self._name, top)
        self.board_label.setObjectName("BoardName")
        self.board_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.board_label.setMinimumWidth(220)
        top.addWidget(self.board_label)

        spacer_right = QWidget(top)
        spacer_right.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top.addWidget(spacer_right)

        self.theme_button = QToolButton(top)
        self.theme_button.setAutoRaise(True)
        self.theme_button.setIcon(icon("moon", palette))
        self.theme_button.setToolTip("Toggle dark mode (Ctrl+Shift+T)")
        self.theme_button.clicked.connect(self.toggle_theme)
        top.addWidget(self.theme_button)
        self._button_icons.append((self.theme_button, "moon"))

        tool_bar = QToolBar("Tools", self)
        tool_bar.setObjectName("ToolPalette")
        tool_bar.setOrientation(Qt.Orientation.Vertical)
        tool_bar.setMovable(False)
        tool_bar.setFloatable(False)
        tool_bar.setIconSize(QSize(22, 22))
        tool_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tool_bar)

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        for index, (name, icon_name, label, key) in enumerate(TOOL_SPECS):
            action = QAction(icon(icon_name, palette), f"{label} ({key})", self)
            action.setCheckable(True)
            action.setToolTip(f"{label} ({key})")
            action.triggered.connect(
                lambda _checked=False, tool=name: self.view.set_tool(tool)
            )
            self.tool_group.addAction(action)
            self.tool_actions[name] = action
            self._action_icons[action] = icon_name
            tool_bar.addAction(action)
            if name in ("eraser", "checklist", "arrow"):
                tool_bar.addSeparator()
        self.tool_actions["select"].setChecked(True)

    def _build_dock(self) -> None:
        self.dock = QDockWidget("Properties", self)
        self.dock.setObjectName("PropertiesDock")
        self.dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.dock.setWidget(self.panel)
        self.dock.setMinimumWidth(280)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        view_menu = next(
            (
                action.menu()
                for action in self.menuBar().actions()
                if action.text() == "&View"
            ),
            None,
        )
        if view_menu is not None:
            view_menu.addSeparator()
            view_menu.addAction(self.dock.toggleViewAction())

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.selection_label = QLabel("No selection", bar)
        bar.addWidget(self.selection_label)
        self.hint_label = QLabel(self.view.tool_hint, bar)
        self.hint_label.setObjectName("SectionHint")
        bar.addWidget(self.hint_label, 1)

        palette = self.theme.palette
        self.zoom_out_button = QToolButton(bar)
        self.zoom_out_button.setAutoRaise(True)
        self.zoom_out_button.setIcon(icon("zoom_out", palette))
        self.zoom_out_button.setToolTip("Zoom out (Ctrl+-)")
        self.zoom_out_button.clicked.connect(self.view.zoom_out)
        bar.addPermanentWidget(self.zoom_out_button)
        self._button_icons.append((self.zoom_out_button, "zoom_out"))

        self.zoom_label = QLabel("100%", bar)
        self.zoom_label.setObjectName("ZoomLabel")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar.addPermanentWidget(self.zoom_label)

        self.zoom_in_button = QToolButton(bar)
        self.zoom_in_button.setAutoRaise(True)
        self.zoom_in_button.setIcon(icon("zoom_in", palette))
        self.zoom_in_button.setToolTip("Zoom in (Ctrl+=)")
        self.zoom_in_button.clicked.connect(self.view.zoom_in)
        bar.addPermanentWidget(self.zoom_in_button)
        self._button_icons.append((self.zoom_in_button, "zoom_in"))

        self.fit_button = QToolButton(bar)
        self.fit_button.setAutoRaise(True)
        self.fit_button.setIcon(icon("fit", palette))
        self.fit_button.setToolTip("Fit to screen (Ctrl+0)")
        self.fit_button.clicked.connect(self.view.fit_to_content)
        bar.addPermanentWidget(self.fit_button)
        self._button_icons.append((self.fit_button, "fit"))

    # ------------------------------------------------------------------ signals / theme
    def _connect_signals(self) -> None:
        self.view.zoom_changed.connect(self._update_zoom)
        self.view.tool_changed.connect(self._on_tool_changed)
        self.view.error_occurred.connect(self._show_warning)
        self.scene.selection_info_changed.connect(self._update_status)
        self.scene.selectionChanged.connect(self._update_status)
        self.scene.focusItemChanged.connect(self._update_editing_state)
        self.scene.undo_stack.cleanChanged.connect(self._update_title)
        self.scene.undo_stack.canUndoChanged.connect(self._sync_undo_actions)
        self.scene.undo_stack.canRedoChanged.connect(self._sync_undo_actions)
        self.scene.undo_stack.indexChanged.connect(self._on_history_changed)
        self.panel.grid_check.toggled.connect(self.grid_action.setChecked)
        self.grid_action.toggled.connect(self.panel.grid_check.setChecked)

    def _on_history_changed(self, _index: int) -> None:
        self.panel.sync_from_selection()
        self._update_status()

    def _apply_theme(self, palette: Palette) -> None:
        previous = getattr(self, "_current_palette", None)
        if previous is not None and previous.name != palette.name:
            self._adapt_item_colors(previous, palette)
        self._current_palette = palette
        self.view.set_theme(palette)
        self.panel.apply_theme(palette)
        for action, name in list(self._action_icons.items()):
            action.setIcon(icon(name, palette))
        for button, name in self._button_icons:
            button.setIcon(icon(name, palette))
        self.theme_button.setIcon(
            icon("sun" if palette.name == "dark" else "moon", palette)
        )
        self.theme_action.setIcon(
            icon("sun" if palette.name == "dark" else "moon", palette)
        )
        self._button_icons = [
            (button, name)
            for button, name in self._button_icons
            if button is not self.theme_button
        ]
        self._button_icons.append(
            (self.theme_button, "sun" if palette.name == "dark" else "moon")
        )
        self.scene.defaults["text_color"] = palette.text
        self.scene.defaults["stroke"] = palette.text
        self.scene.defaults["pen_color"] = palette.text
        self.panel.refresh_defaults()
        self.scene.update_handle_scale()
        self.view.viewport().update()

    def toggle_theme(self) -> None:
        name = self.theme.toggle()
        self.settings.setValue("theme", name)

    def _adapt_item_colors(self, previous: Palette, current: Palette) -> None:
        """Keep default-coloured content readable when the board changes theme."""
        old_text = QColor(previous.text)
        new_text = QColor(current.text)
        old_default_stroke = QColor(DEFAULT_STROKE)
        for item in self.scene.board_items():
            if isinstance(item, TextItem):
                if item.text_color == old_text:
                    item.set_text_color(new_text)
            elif isinstance(item, StrokeItem):
                if item.color == old_text:
                    item.set_color(new_text)
            elif isinstance(item, (ShapeItem, LineItem)):
                if item.stroke == old_text or item.stroke == old_default_stroke:
                    item.set_stroke(new_text)

    def _on_tool_changed(self, name: str) -> None:
        action = self.tool_actions.get(name)
        if action is not None:
            action.setChecked(True)
        self.hint_label.setText(self.view.tool_hint)

    def _toggle_grid(self) -> None:
        self.view.set_grid_visible(self.grid_action.isChecked())

    # ------------------------------------------------------------------ status
    def _update_zoom(self, scale: float) -> None:
        percent = scale * 100.0
        if percent < 10.0:
            self.zoom_label.setText(f"{percent:.1f}%")
        else:
            self.zoom_label.setText(f"{percent:.0f}%")

    def _update_status(self) -> None:
        items = self.scene.selected_board_items()
        if not items:
            self.selection_label.setText("No selection")
        elif len(items) == 1:
            self.selection_label.setText(f"1 {items[0].TYPE} selected")
        else:
            self.selection_label.setText(f"{len(items)} objects selected")

    def _sync_undo_actions(self, *_args: Any) -> None:
        editing = self.scene.is_editing()
        stack = self.scene.undo_stack
        self.undo_action.setEnabled(not editing and stack.canUndo())
        self.redo_action.setEnabled(not editing and stack.canRedo())

    def _update_editing_state(self, *_args: Any) -> None:
        editing = self.scene.is_editing()
        for action in self._editing_actions:
            action.setEnabled(not editing)
        self._sync_undo_actions()

    # ------------------------------------------------------------------ document
    def _update_title(self) -> None:
        marker = " •" if self.dirty else ""
        self.setWindowTitle(f"{self._name}{marker} \u2014 {APP_NAME}")
        if hasattr(self, "board_label"):
            self.board_label.setText(f"{self._name}{marker}")
            self.board_label.setToolTip(
                str(self._path) if self._path else "Not saved yet"
            )

    def _maybe_save(self) -> bool:
        if not self.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Save changes to \u201c{self._name}\u201d before continuing?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            return self.save_board()
        if choice == QMessageBox.StandardButton.Discard:
            return True
        return False

    def new_board(self) -> None:
        if not self._maybe_save():
            return
        self.scene.new_board()
        self._path = None
        self._name = default_board_name()
        self._meta_dirty = False
        remove_quietly(recovery_path(app_data_dir()))
        self.view.set_tool("select")
        self.view.centerOn(0.0, 0.0)
        self.view.reset_zoom()
        self._update_title()
        self._update_status()
        self.statusBar().showMessage("New board created", 3000)

    def open_board(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open board",
            str(self._path.parent) if self._path else str(Path.home()),
            f"Canvasity boards (*{BOARD_EXTENSION});;All files (*)",
        )
        if path:
            self.open_path(path, confirm_save=False)

    def open_path(self, path: str | Path, confirm_save: bool = True) -> None:
        if confirm_save and not self._maybe_save():
            return
        source = Path(path)
        if not source.exists():
            self._show_error(f"Board not found: {source}")
            return
        try:
            data = load_board(source)
        except BoardIOError as exc:
            self._show_error(str(exc))
            return

        autosave = autosave_path_for(source)
        recovered = False
        if autosave.exists() and file_mtime(autosave) > file_mtime(source):
            choice = QMessageBox.question(
                self,
                "Unsaved changes found",
                "An autosave newer than the board file was found.\n"
                "Recover the autosaved version?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                try:
                    data = load_board(autosave)
                    recovered = True
                except BoardIOError as exc:
                    self._show_warning(f"Autosave could not be read: {exc}")
            remove_quietly(autosave)

        try:
            self.scene.load_board_dict(data)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._path = source
        self._name = str(data.get("name") or source.stem)
        self._meta_dirty = recovered
        self.scene.undo_stack.setClean()
        self.view.set_tool("select")
        self.view.fit_to_content()
        self._update_title()
        self._update_status()
        self.statusBar().showMessage(
            f"Opened {source.name}" + (" (recovered autosave)" if recovered else ""),
            4000,
        )

    def save_board(self) -> bool:
        if self._path is None:
            return self.save_board_as()
        return self._save_to(self._path)

    def save_board_as(self) -> bool:
        default_dir = self._path.parent if self._path else Path.home()
        suggested = default_dir / f"{self._safe_name()}{BOARD_EXTENSION}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save board as",
            str(suggested),
            f"Canvasity boards (*{BOARD_EXTENSION})",
        )
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != BOARD_EXTENSION:
            target = target.with_suffix(BOARD_EXTENSION)
        if self._path is None:
            self._name = target.stem
        return self._save_to(target)

    def _save_to(self, target: Path) -> bool:
        data = self.scene.to_board_dict()
        data["name"] = self._name
        try:
            save_board(target, data)
        except BoardIOError as exc:
            self._show_error(str(exc))
            return False
        self._path = target
        self.scene.undo_stack.setClean()
        self._meta_dirty = False
        remove_quietly(autosave_path_for(target))
        remove_quietly(recovery_path(app_data_dir()))
        self._update_title()
        self.statusBar().showMessage(f"Saved {target.name}", 3000)
        return True

    def rename_board(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Rename board", "Board name:", text=self._name
        )
        if not ok:
            return
        name = name.strip()
        if not name or name == self._name:
            return
        self._name = name
        self._meta_dirty = True
        self._update_title()
        self.statusBar().showMessage("Board renamed", 2500)

    # ------------------------------------------------------------------ autosave
    def _autosave(self) -> None:
        if not self.dirty:
            return
        data = self.scene.to_board_dict()
        data["name"] = self._name
        target = (
            autosave_path_for(self._path)
            if self._path is not None
            else recovery_path(app_data_dir())
        )
        try:
            save_board(target, data)
        except BoardIOError as exc:
            logger.warning("Autosave failed: %s", exc)

    def maybe_restore_session(self) -> None:
        if self._recovery_checked:
            return
        self._recovery_checked = True
        path = recovery_path(app_data_dir())
        if not path.exists():
            return
        try:
            data = load_board(path)
        except BoardIOError:
            remove_quietly(path)
            return
        if not data.get("items"):
            remove_quietly(path)
            return
        choice = QMessageBox.question(
            self,
            "Restore session",
            "An unsaved board from your last session was found.\nRestore it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice != QMessageBox.StandardButton.Yes:
            remove_quietly(path)
            return
        try:
            self.scene.load_board_dict(data)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._path = None
        self._name = str(data.get("name") or "Recovered board")
        self._meta_dirty = True
        self.scene.undo_stack.setClean()
        self.view.fit_to_content()
        remove_quietly(path)
        self._update_title()
        self.statusBar().showMessage("Recovered unsaved board", 4000)

    # ------------------------------------------------------------------ export
    def _default_export_path(self, suffix: str) -> Path:
        base = self._path.parent if self._path else Path.home()
        return base / f"{self._safe_name()}{suffix}"

    def _safe_name(self) -> str:
        value = re.sub(r'[\\/:*?"<>|]+', "-", self._name).strip(" .")
        return value or "board"

    def export_to_png(self) -> None:
        suggested = self._default_export_path(".png")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as PNG", str(suggested), "PNG image (*.png)"
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".png":
            target = target.with_suffix(".png")
        try:
            export_png(self.scene, target, scale=2.0)
        except ExportError as exc:
            self._show_error(str(exc))
            return
        self.statusBar().showMessage(f"Exported {target.name}", 4000)

    def export_to_pdf(self) -> None:
        suggested = self._default_export_path(".pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as PDF", str(suggested), "PDF document (*.pdf)"
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        try:
            export_pdf(self.scene, target)
        except ExportError as exc:
            self._show_error(str(exc))
            return
        self.statusBar().showMessage(f"Exported {target.name}", 4000)

    # ------------------------------------------------------------------ misc
    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, APP_NAME, message)

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)

    def _about(self) -> None:
        import PySide6

        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} {APP_VERSION}</h3>"
            "<p>A local, infinite-canvas whiteboard built with PySide6.</p>"
            f"<p>Qt/PySide6 {PySide6.__version__} \u00b7 Python 3</p>"
            "<p>No accounts, no cloud, no telemetry.</p>",
        )

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: Any) -> None:
        if not self._maybe_save():
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("theme", self.theme.name)
        remove_quietly(recovery_path(app_data_dir()))
        event.accept()
