"""Main window. Tabs, stage, panels."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPolygonF,
    QShortcut,
    QSurfaceFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Clay3D import brushes, icons, imagefx, selection, shapes2d
from Clay3D.canvas2d import Canvas
from Clay3D.io_files import load_image, load_scene, save_image, save_scene
from Clay3D.editing import EditingTools, TextBox
from Clay3D.panels import CONTEXT_PANELS, TABS
from Clay3D.scene3d import Scene
from Clay3D.stage import Stage
from Clay3D.theme import ACCENT, STYLESHEET
from Clay3D.widgets import rule

from Clay3D.tuning import CANVAS_DEFAULT_SIZE, UNDO_DEPTH

CANVAS_WIDTH, CANVAS_HEIGHT = CANVAS_DEFAULT_SIZE
PANEL_WIDTH = 312


@dataclass
class Undo:
    """One reversible step. Only the parts a step touched are captured."""

    pixels: np.ndarray | None = None
    size: tuple[int, int] | None = None
    objects: list | None = None
    selected: int = -1
    background: tuple = (255, 255, 255, 255)


class EditorWindow(QMainWindow, EditingTools):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Clay3D")
        self.resize(1420, 920)

        self.scene = Scene(canvas=Canvas(CANVAS_WIDTH, CANVAS_HEIGHT))
        self.tool = "marker"
        self.color = (0, 0, 0, 255)
        self.size = 12.0
        self.opacity = 1.0
        self.shape_style = "both"
        self.sticker_size = 120
        self.custom_sticker: np.ndarray | None = None
        self.magic = None               # selection.MagicCutout while magic select is open
        self.autofill_background = True  # "Lift an object out ... we'll automatically fill in the background"
        self.tube_profile = "cylinder"
        self.tube_taper = "uniform"
        self.selection: selection.Selection | None = None
        self.clipboard: np.ndarray | None = None
        self.text_box: TextBox | None = None
        self.live_shape: LiveShape | None = None
        self._live_drag = None
        self._live_start_box = (0.0, 0.0, 0.0, 0.0)
        self._stroke_points: list[tuple[float, float]] = []
        self._undo: list[Undo] = []
        self._redo: list[Undo] = []
        self._drag_mode: str | None = None
        self._drag_origin = (0.0, 0.0)
        self._drag_start = (np.zeros(2), np.ones(2), 0.0, (0, 0, 0, 0))
        self.cutout_error: str | None = None
        self.suppress_dialogs = False

        self._build()
        self.setAcceptDrops(True)
        self.apply_paint_settings()
        self.set_category("Brushes")
        QTimer.singleShot(0, lambda: self.scene.frame_canvas(self.stage.width(), self.stage.height()))

    @property
    def canvas(self) -> Canvas:
        return self.scene.canvas

    # ---- window construction -------------------------------------------

    def _build(self) -> None:
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet(STYLESHEET)
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(self._tab_strip())
        column.addWidget(rule())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.stage = Stage(self)
        body.addWidget(self.stage, 1)
        body.addWidget(self._right_panel())
        column.addLayout(body, 1)

        column.addWidget(rule())
        column.addWidget(self._bottom_bar())

        self.stack = QStackedWidget()
        self.stack.addWidget(page)
        self.menu_page = self._menu_page()
        self.stack.addWidget(self.menu_page)
        self.setCentralWidget(self.stack)
        self._install_shortcuts()

    def dragEnterEvent(self, event) -> None:
        if self.mime_has_image(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if self.mime_has_image(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if self.import_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def _tab_strip(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("tabStrip")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 2, 8, 0)
        row.setSpacing(2)

        menu = QToolButton()
        menu.setText("Menu")
        menu.setProperty("role", "action")
        menu.clicked.connect(self.show_menu)
        row.addWidget(menu)
        row.addSpacing(10)

        self.tab_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        for name, _ in TABS:
            button = QToolButton()
            button.setText(name)
            button.setIcon(icons.tab_icon(name))
            button.setIconSize(QSize(20, 20))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setProperty("role", "tab")
            button.clicked.connect(lambda checked=False, n=name: self.set_category(n))
            group.addButton(button)
            row.addWidget(button)
            self.tab_buttons[name] = button

        row.addStretch(1)
        # Select lives in the top bar in the original, not in the tabs.
        self.select_buttons: dict[str, QToolButton] = {}
        for tool, label, glyph in (
            ("select:box", "2D select", icons.select_icon("box", 18)),
            ("select:magic", "Magic select", icons.select_icon("magic", 18)),
            ("select:crop", "Crop", icons.select_icon("crop", 18)),
        ):
            button = self._action_button(
                label, label, lambda t=tool: self.choose_select_tool(t)
            )
            button.setIcon(glyph)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            row.addWidget(button)
            self.select_buttons[tool] = button
        self.undo_button = self._action_button("Undo", "Undo", self.undo)
        self.undo_button.setIcon(icons.history_icon("undo", 18))
        self.undo_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.redo_button = self._action_button("Redo", "Redo", self.redo)
        self.redo_button.setIcon(icons.history_icon("redo", 18))
        self.redo_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)
        return bar

    def _action_button(self, tooltip: str, text: str, handler) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setProperty("role", "action")
        # clicked(bool) must not eat the handler's arguments.
        button.clicked.connect(lambda checked=False, fn=handler: fn())
        return button

    def _right_panel(self) -> QWidget:
        holder = QWidget()
        holder.setObjectName("rightPanel")
        holder.setFixedWidth(PANEL_WIDTH)
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        self.panels: dict[str, QWidget] = {}
        self.panel_stack = QStackedWidget()
        self.panel_index: dict[str, int] = {}
        for name, factory in TABS + CONTEXT_PANELS:
            panel = factory(self)
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            scroller.setWidget(panel)
            scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.panels[name] = panel
            self.panel_index[name] = self.panel_stack.addWidget(scroller)
        box.addWidget(self.panel_stack)
        return holder

    def _bottom_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("bottomBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(8)

        row.addStretch(1)
        self.view_2d = QPushButton("2D view")
        self.view_2d.setCheckable(True)
        self.view_2d.setChecked(True)
        self.view_2d.clicked.connect(lambda checked=False: self.set_view("2d"))
        self.view_3d = QPushButton("3D view")
        self.view_3d.setCheckable(True)
        self.view_3d.clicked.connect(lambda checked=False: self.set_view("orbit"))
        row.addWidget(self.view_2d)
        row.addWidget(self.view_3d)
        self.perspective = QToolButton()
        self.perspective.setText("Show perspective")
        self.perspective.setToolTip(
            "Create in a 3D workspace that shows depth and relative size. "
            "(Recommended for 3D projects)."
        )
        self.perspective.setCheckable(True)
        self.perspective.setChecked(True)
        self.perspective.setProperty("role", "action")
        self.perspective.toggled.connect(self.set_perspective)
        row.addWidget(self.perspective)
        row.addStretch(1)

        zoom_out = self._action_button("Zoom out", "−", lambda: self.zoom_by(0.8))
        row.addWidget(zoom_out)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setFixedWidth(160)
        self.zoom_slider.setRange(10, 800)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self._zoom_slider_moved)
        self.zoom_slider.setToolTip("Adjust the zoom")
        row.addWidget(self.zoom_slider)
        row.addWidget(self._action_button("Zoom in", "+", lambda: self.zoom_by(1.25)))
        self.zoom_label = QLabel("100%")
        self.zoom_label.setProperty("role", "value")
        self.zoom_label.setFixedWidth(48)
        row.addWidget(self.zoom_label)
        row.addWidget(self._action_button("Reset view", "Reset view", self.fit_to_window))
        row.addWidget(
            self._action_button("Take screenshot", "Screenshot", self.take_screenshot)
        )
        return bar

    def _menu_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet(STYLESHEET)
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        sidebar = QWidget()
        sidebar.setObjectName("chrome")
        sidebar.setFixedWidth(300)
        column = QVBoxLayout(sidebar)
        column.setContentsMargins(18, 18, 18, 18)
        column.setSpacing(6)

        back = QToolButton()
        back.setText("←  Back")
        back.setProperty("role", "action")
        back.clicked.connect(self.hide_menu)
        column.addWidget(back)
        column.addSpacing(12)

        for label, handler in (
            ("New", self.new_document),
            ("Open image…", self.open_file),
            ("Save image", self.save_image_as),
            ("Save scene…", self.save_scene_as),
            ("Export 3D model…", self.export_model),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            column.addWidget(button)
        column.addStretch(1)

        about = QLabel("Clay3D\n\nPaint 3D-inspired editor for Linux.")
        about.setWordWrap(True)
        about.setProperty("role", "value")
        column.addWidget(about)

        outer.addWidget(sidebar)
        blurb = QLabel()
        blurb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(blurb, 1)
        return page

    def _install_shortcuts(self) -> None:
        for keys, handler in (
            (QKeySequence.StandardKey.Undo, self.undo),
            (QKeySequence.StandardKey.Redo, self.redo),
            (QKeySequence.StandardKey.New, self.new_document),
            (QKeySequence.StandardKey.Open, self.open_file),
            (QKeySequence.StandardKey.Save, self.save_image_as),
            (QKeySequence.StandardKey.Copy, self.copy_selection),
            (QKeySequence.StandardKey.Cut, self.cut_selection),
            (QKeySequence.StandardKey.Paste, self.paste_clipboard),
            (QKeySequence.StandardKey.SelectAll, self.select_all),
            (QKeySequence.StandardKey.Delete, self.delete_selection),
        ):
            shortcut = QShortcut(QKeySequence(keys), self, handler)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        for text, handler in (
            ("Ctrl+Y", self.redo),
            ("Ctrl+Shift+Z", self.redo),
            ("Ctrl+3", self.toggle_view),
            ("Ctrl+0", self.fit_to_window),
            ("Ctrl+D", self.clear_selection),
            ("Ctrl+Shift+X", self.crop_to_selection),
            ("[", lambda: self.set_size(max(1, self.size - 2))),
            ("]", lambda: self.set_size(min(400, self.size + 2))),
            ("Ctrl++", lambda: self.zoom_by(1.25)),
            ("Ctrl+-", lambda: self.zoom_by(0.8)),
            ("Esc", self.cancel_current),
        ):
            shortcut = QShortcut(QKeySequence(text), self, handler)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)

    def keyPressEvent(self, event) -> None:
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if ctrl and event.key() == Qt.Key.Key_Y:
            self.redo()
            event.accept()
            return
        if ctrl and event.key() == Qt.Key.Key_Z:
            if shift:
                self.redo()
            else:
                self.undo()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---- categories and settings ---------------------------------------

    def choose_select_tool(self, tool: str) -> None:
        """Pick a select tool from the top bar and show its options."""
        if not isinstance(tool, str) or not tool.startswith("select:"):
            return
        self.set_tool(tool)
        self.category = "Select"
        for key, button in self.tab_buttons.items():
            button.setChecked(False)
        for key, button in self.select_buttons.items():
            button.setChecked(key == tool)
        self.panel_stack.setCurrentIndex(self.panel_index["Select"])
        self.refresh_panels()

    def set_category(self, name: str) -> None:
        if name != "Select":
            self.clear_selection()
        self.category = name
        for key, button in self.tab_buttons.items():
            button.setChecked(key == name)
        self.panel_stack.setCurrentIndex(self.panel_index[name])
        if name != "Select":
            for button in self.select_buttons.values():
                button.setChecked(False)
        default = {
            "Brushes": "marker",
            "2D shapes": "shape:rectangle",
            "3D shapes": "shape3d:cube",
            "Stickers": "sticker:smile",
            "Text": "text",
            "Effects": "none",
            "Canvas": "canvas",
            "Select": "select:box",
        }.get(name, "none")
        if default != "none" and not self._tool_belongs_to(name):
            self.set_tool(default)
        self.refresh_panels()

    def _tool_belongs_to(self, category: str) -> bool:
        prefixes = {
            "Brushes": ("marker", "calligraphy", "oil", "watercolor", "pixel", "pencil",
                        "eraser", "crayon", "spray", "smudge", "fill", "eyedropper"),
            "2D shapes": ("shape:", "line:"),
            "3D shapes": ("shape3d:", "doodle_", "tube"),
            "Stickers": ("sticker:",),
            "Text": ("text",),
            "Select": ("select:",),
            "Canvas": ("canvas",),
        }.get(category, ())
        return any(self.tool == p or self.tool.startswith(p) for p in prefixes)

    def set_tool(self, tool: str) -> None:
        self.commit_text_box()
        self.commit_live_shape()
        entering_magic = tool in self.MAGIC_TOOLS and self.tool not in self.MAGIC_TOOLS
        if not tool.startswith("select:") or entering_magic or tool == "select:crop":
            # Leaving the selection tools puts a floating selection down,
            # rather than leaving it hovering with a hole underneath it.
            self.clear_selection()
        if tool not in self.MAGIC_TOOLS:
            self.cancel_magic_session()   # left before Done: nothing changes
        elif entering_magic:
            self.start_magic_session()
        self.tool = tool
        self.apply_paint_settings()
        self.refresh_panels()
        self.stage.update()

    def set_color(self, color) -> None:
        self.color = tuple(int(c) for c in color)
        self.apply_paint_settings()
        if self.live_shape is not None:
            self.live_shape.color = self.color
        obj = self.scene.selected()
        if obj is not None and self.category == "3D shapes":
            self.push_undo(objects=True)
            obj.color = self.color
        self.refresh_panels()
        self.stage.update()

    def set_size(self, size: float) -> None:
        self.size = max(1.0, float(size))
        self.apply_paint_settings()
        if self.live_shape is not None:
            self.live_shape.thickness = self.size
        self.refresh_panels()
        self.stage.update()

    def set_opacity(self, opacity: float) -> None:
        self.opacity = float(opacity)
        self.apply_paint_settings()

    def set_tolerance(self, tolerance: float) -> None:
        self.canvas.tolerance = float(tolerance)

    def apply_paint_settings(self) -> None:
        self.canvas.set_color(self.color)
        self.canvas.set_size(self.size)
        self.canvas.set_opacity(self.opacity)
        if self.tool in brushes.CATALOG:
            self.canvas.set_brush(self.tool)

    def set_object_material(self, smoothness: float | None = None, metallic: float | None = None) -> None:
        obj = self.scene.selected()
        if obj is None:
            return
        if smoothness is not None:
            obj.smoothness = smoothness
        if metallic is not None:
            obj.metallic = metallic
        self.stage.update()

    def set_text_style(self, **changes) -> None:
        if self.text_box is None:
            self.text_box = TextBox(0, 0)
        for key, value in changes.items():
            setattr(self.text_box, key, value)
        self.stage.update()

    def set_effect(self, name: str) -> None:
        self.scene.effect = name
        self.refresh_panels()
        self.stage.update()

    def set_light_rotation(self, degrees: float) -> None:
        self.scene.light_rotation = math.radians(degrees)
        self.stage.update()

    def refresh_panels(self) -> None:
        panel = self.panels.get(getattr(self, "category", "Brushes"))
        if panel is not None and hasattr(panel, "refresh"):
            panel.refresh()
        self.undo_button.setEnabled(bool(self._undo) or self.magic_stage() == "refine")
        self.redo_button.setEnabled(bool(self._redo) or self.magic_stage() == "refine")
        active = "select:magic" if self.tool in self.MAGIC_TOOLS else self.tool
        for tool, button in getattr(self, "select_buttons", {}).items():
            button.setChecked(active == tool)

    # ---- view ----------------------------------------------------------

    def set_view(self, mode: str) -> None:
        self.commit_text_box()
        self.commit_live_shape()
        self.scene.set_view(mode)
        self.view_2d.setChecked(mode == "2d")
        self.view_3d.setChecked(mode == "orbit")
        if mode == "2d":
            self.fit_to_window()
        else:
            self.scene.frame_scene()
        self.zoom_changed()
        self.stage.update()

    def toggle_view(self) -> None:
        self.set_view("orbit" if self.scene.camera.mode == "2d" else "2d")

    def fit_to_window(self) -> None:
        if self.scene.camera.mode == "2d":
            self.scene.frame_canvas(self.stage.width(), self.stage.height())
        else:
            self.scene.camera.reset()
        self.zoom_changed()
        self.stage.update()

    def zoom_by(self, factor: float) -> None:
        self.scene.camera.dolly(factor)
        self.zoom_changed()
        self.stage.update()

    def _zoom_slider_moved(self, percent: int) -> None:
        scale = self.stage.canvas_scale()
        if scale <= 0:
            return
        self.scene.camera.dolly((percent / 100.0) / scale)
        self.zoom_label.setText(f"{percent}%")
        self.stage.update()

    def zoom_changed(self) -> None:
        percent = int(round(self.stage.canvas_scale() * 100))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(10, min(800, percent)))
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{percent}%")

    def set_perspective(self, on: bool) -> None:
        """Toggle the 3D workspace between perspective and orthographic."""
        self.scene.camera.set_perspective(on)
        self.stage.update()

    def take_screenshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Take screenshot", "screenshot.png", "PNG (*.png)"
        )
        if path:
            self.stage.grab().save(path)

    def set_show_canvas(self, visible: bool) -> None:
        self.scene.show_canvas = visible
        self.stage.update()

    def set_transparent_canvas(self, transparent: bool) -> None:
        self.push_undo(canvas=True)
        rect = self.canvas.make_transparent() if transparent else self.canvas.make_opaque()
        self.stage.mark_canvas_dirty(rect)

    # ---- undo ----------------------------------------------------------

    def push_undo(self, canvas: bool = True, objects: bool = False) -> None:
        entry = Undo(selected=self.scene.selected_index, background=self.canvas.background)
        if canvas:
            entry.pixels = self.canvas.pixels.copy()
            entry.size = (self.canvas.width, self.canvas.height)
        if objects:
            entry.objects = [o.copy() for o in self.scene.objects]
        self._undo.append(entry)
        self._redo.clear()
        del self._undo[:-UNDO_DEPTH]
        self.refresh_panels()

    def _capture(self, like: Undo) -> Undo:
        entry = Undo(selected=self.scene.selected_index, background=self.canvas.background)
        if like.pixels is not None:
            entry.pixels = self.canvas.pixels.copy()
            entry.size = (self.canvas.width, self.canvas.height)
        if like.objects is not None:
            entry.objects = [o.copy() for o in self.scene.objects]
        return entry

    def _restore(self, entry: Undo) -> None:
        if entry.pixels is not None:
            self.canvas.width, self.canvas.height = entry.size
            self.canvas.pixels = entry.pixels.copy()
            self.canvas.background = entry.background
            self.stage.reload_canvas()
        if entry.objects is not None:
            self.scene.objects = entry.objects
        self.scene.selected_index = entry.selected
        self.selection = None
        self.refresh_panels()
        self.stage.update()

    def undo(self) -> None:
        if self.magic is not None:
            self.magic_undo()
            return
        if not self._undo:
            return
        entry = self._undo.pop()
        self._redo.append(self._capture(entry))
        self._restore(entry)

    def redo(self) -> None:
        if self.magic is not None:
            self.magic_redo()
            return
        if not self._redo:
            return
        entry = self._redo.pop()
        self._undo.append(self._capture(entry))
        self._restore(entry)

    # ---- what the stage asks --------------------------------------------

    def tool_wants_objects(self) -> bool:
        return self.tool.startswith(("shape3d:", "sticker:")) or self.tool == "select:object"

    def shows_gizmo(self) -> bool:
        return self.scene.selected() is not None and self.category == "3D shapes"

    def shows_brush_cursor(self) -> bool:
        return self.tool in brushes.CATALOG

    def brush_radius(self) -> float:
        return self.size / 2.0

    def before_gizmo_drag(self) -> None:
        self.push_undo(canvas=False, objects=True)

    def after_gizmo_drag(self) -> None:
        self.refresh_panels()

    def click_object(self, obj, uv, normal, mods) -> bool:
        """Handle a click aimed at a 3D object.

        Returns False when the tool has nothing to do with what was hit,
        so the stage can offer the same click to the canvas instead. A
        sticker works on either, which is the case this exists for.
        """
        if self.tool.startswith("shape3d:"):
            self.insert_primitive(self.tool.split(":", 1)[1])
            return True
        if self.tool.startswith("sticker:"):
            if obj is None or uv is None:
                return False
            self.apply_sticker_to_object(obj, uv)
            return True
        self.scene.select(obj)
        self.refresh_panels()
        return True

    def keyPressEvent(self, event) -> None:
        # Qt delivers keys to the widget, so the handler stays here and the
        # text tool's own logic stays with the other tools.
        if not self.type_into_text_box(event):
            super().keyPressEvent(event)

    # ---- files -----------------------------------------------------------

    def show_menu(self) -> None:
        self.stack.setCurrentIndex(1)

    def hide_menu(self) -> None:
        self.stack.setCurrentIndex(0)

    def new_document(self) -> None:
        self.push_undo(canvas=True, objects=True)
        self.scene.canvas = Canvas(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.scene.objects = []
        self.scene.selected_index = -1
        self.selection = None
        self.apply_paint_settings()
        self.stage.reload_canvas()
        self.hide_menu()
        self.set_view("2d")

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp);;Clay3D scene (*.clay3d)"
        )
        if not path:
            return
        self.push_undo(canvas=True, objects=True)
        if path.endswith(".clay3d"):
            self.scene = load_scene(path)
        else:
            self.scene.canvas = load_image(path)
        self.apply_paint_settings()
        self.stage.reload_canvas()
        self.hide_menu()
        self.fit_to_window()
        self.refresh_panels()

    def save_image_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save image", "artwork.png", "PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp)"
        )
        if path:
            self.clear_selection()
            save_image(self.canvas, path)
            self.hide_menu()

    def save_scene_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save scene", "artwork.clay3d", "Clay3D scene (*.clay3d)"
        )
        if path:
            self.clear_selection()
            save_scene(self.scene, path)
            self.hide_menu()

    def export_model(self) -> None:
        from Clay3D.io_files import save_model

        from Clay3D.io_files import MODEL_FORMATS

        path, _ = QFileDialog.getSaveFileName(
            self, "Export 3D model", "model.obj",
            ";;".join(caption for _, caption in MODEL_FORMATS),
        )
        if not path:
            return
        if not self.scene.objects:
            QMessageBox.information(self, "Nothing to export", "The scene has no 3D objects.")
            return
        save_model(self.scene, path)
        self.hide_menu()

    # ---- overlay ---------------------------------------------------------

    def paint_overlay(self, painter: QPainter, stage: Stage) -> None:
        self._draw_live_shape(painter, stage)
        self._draw_doodle_trail(painter, stage)
        self._draw_floating_selection(painter, stage)
        self._draw_text_box(painter, stage)

    def _draw_live_shape(self, painter: QPainter, stage: Stage) -> None:
        shape = self.live_shape
        if shape is None:
            return
        color = QColor(*shape.color[:3])
        painter.setPen(QPen(color, max(1.0, shape.thickness * stage.canvas_scale()),
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if shape.pixels is not None:
            x0, y0, x1, y1 = shape.box()
            top_left = stage.canvas_to_screen(x0, y0)
            bottom_right = stage.canvas_to_screen(x1, y1)
            if top_left is not None and bottom_right is not None:
                pixels = np.ascontiguousarray(shape.pixels)
                qimage = QImage(
                    pixels.data,
                    pixels.shape[1],
                    pixels.shape[0],
                    4 * pixels.shape[1],
                    QImage.Format.Format_RGBA8888,
                ).copy()
                painter.drawImage(QRectF(top_left, bottom_right), qimage)
        elif shape.points:
            path = shapes2d.line_path(shape.kind, shape.points + [shape.end])
            polygon = _to_screen(path, stage)
            if polygon is not None:
                painter.drawPolyline(polygon)
            painter.setPen(QPen(QColor(ACCENT), 1.2))
            painter.setBrush(QColor("#FFFFFF"))
            for point in shape.points:
                at = stage.canvas_to_screen(*point)
                if at is not None:
                    painter.drawEllipse(at, 4, 4)
        else:
            for part in shapes2d.contours(shape.kind, *shape.start, *shape.end):
                polygon = _to_screen(part, stage)
                if polygon is None:
                    continue
                if shape.style in ("both", "fill"):
                    painter.setBrush(QColor(*shape.color[:3], 140))
                else:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(polygon)
        if not shape.placed:
            return
        handles = self.live_item_handles()
        box = shape.box()
        corners = [
            stage.canvas_to_screen(box[0], box[1]),
            stage.canvas_to_screen(box[2], box[1]),
            stage.canvas_to_screen(box[2], box[3]),
            stage.canvas_to_screen(box[0], box[3]),
        ]
        if any(c is None for c in corners):
            return
        painter.setPen(QPen(QColor(ACCENT), 1.2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF(corners))
        painter.setPen(QPen(QColor("#C5C5C5"), 1.2))
        painter.setBrush(QColor("#FFFFFF"))
        for name, (hx, hy) in handles.items():
            at = stage.canvas_to_screen(hx, hy)
            if at is None:
                continue
            if name == "Stamp":
                painter.setBrush(QColor(ACCENT))
                painter.drawEllipse(at, 8, 8)
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawEllipse(at, 3.5, 3.5)
            elif name != "Rotate":
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawEllipse(at, 6, 6)

    def _draw_doodle_trail(self, painter: QPainter, stage: Stage) -> None:
        if not self.tool.startswith("doodle_") or len(self._stroke_points) < 2:
            return
        polygon = _to_screen(self._stroke_points, stage)
        if polygon is None:
            return
        painter.setPen(QPen(QColor(*self.color[:3]), 2.5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(polygon)

    def _draw_floating_selection(self, painter: QPainter, stage: Stage) -> None:
        if self.selection is None or self.selection.floating is None:
            return
        placed = self.selection.transformed()
        if placed is None:
            return
        pixels, (x, y) = placed
        top_left = stage.canvas_to_screen(x, y)
        bottom_right = stage.canvas_to_screen(x + pixels.shape[1], y + pixels.shape[0])
        if top_left is None or bottom_right is None:
            return
        image = QImage(
            np.ascontiguousarray(pixels).tobytes(),
            pixels.shape[1], pixels.shape[0], pixels.shape[1] * 4,
            QImage.Format.Format_RGBA8888,
        )
        painter.drawImage(QRectF(top_left, bottom_right), image)

    def _draw_text_box(self, painter: QPainter, stage: Stage) -> None:
        box = self.text_box
        if box is None:
            return
        at = stage.canvas_to_screen(box.x, box.y)
        if at is None:
            return
        scale = stage.canvas_scale()
        font = box.font()
        font.setPointSizeF(max(1.0, box.size * scale))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        lines = box.text.split("\n") or [""]
        width = max((metrics.horizontalAdvance(line) for line in lines), default=0)
        height = metrics.height() * len(lines)
        frame = QRectF(at.x() - 4, at.y() - 4, max(width, 40) + 8, height + 8)
        painter.setPen(QPen(QColor(ACCENT), 1.0, Qt.PenStyle.DashLine))
        painter.setBrush(QColor(255, 255, 255, 40))
        painter.drawRect(frame)
        painter.setPen(QColor(*self.color[:3]))
        for index, line in enumerate(lines):
            painter.drawText(
                QPointF(at.x(), at.y() + metrics.ascent() + index * metrics.height()), line
            )
        caret_x = at.x() + metrics.horizontalAdvance(lines[-1])
        caret_y = at.y() + (len(lines) - 1) * metrics.height()
        painter.setPen(QPen(QColor(*self.color[:3]), 1.5))
        painter.drawLine(
            QPointF(caret_x, caret_y), QPointF(caret_x, caret_y + metrics.height())
        )


def _to_screen(points, stage: Stage) -> QPolygonF | None:
    screen = [stage.canvas_to_screen(x, y) for x, y in points]
    if any(p is None for p in screen):
        return None
    return QPolygonF(screen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clay3D - 2D and 3D paint")
    parser.add_argument("--capture", help="Save a window grab to PATH and exit")
    parser.add_argument("--view", choices=["2d", "orbit"], help="Start in this view")
    parser.add_argument("--tab", help="Open this tab on start")
    parser.add_argument("--demo", action="store_true", help="Seed some artwork")
    args = parser.parse_args(argv)

    surface = QSurfaceFormat()
    surface.setVersion(3, 3)
    surface.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(surface)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Clay3D")
    app.setDesktopFileName("Clay3D")
    apply_light_palette(app)

    window = EditorWindow()
    if args.demo:
        seed_demo(window)
    window.show()
    if args.tab:
        window.set_category(args.tab)
    if args.view:
        window.set_view(args.view)

    if args.capture:
        def grab_and_quit() -> None:
            app.processEvents()
            window.grab().save(args.capture)
            app.quit()

        QTimer.singleShot(900, grab_and_quit)
    return app.exec()


def apply_light_palette(app: QApplication) -> None:
    """Pin the light Fluent look regardless of the desktop's own theme."""
    app.setStyle("Fusion")
    palette = QPalette()
    for role, colour in (
        (QPalette.ColorRole.Window, "#F3F2F1"),
        (QPalette.ColorRole.WindowText, "#201F1E"),
        (QPalette.ColorRole.Base, "#FFFFFF"),
        (QPalette.ColorRole.AlternateBase, "#F3F2F1"),
        (QPalette.ColorRole.Text, "#201F1E"),
        (QPalette.ColorRole.Button, "#FFFFFF"),
        (QPalette.ColorRole.ButtonText, "#201F1E"),
        (QPalette.ColorRole.ToolTipBase, "#FFFFFF"),
        (QPalette.ColorRole.ToolTipText, "#201F1E"),
        (QPalette.ColorRole.Highlight, "#0078D4"),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
    ):
        palette.setColor(role, QColor(colour))
    app.setPalette(palette)


def seed_demo(window: EditorWindow) -> None:
    """Paint something so screenshots and manual checks have content."""
    canvas = window.canvas
    canvas.set_brush("marker")
    canvas.set_color((0, 120, 212, 255))
    canvas.set_size(24)
    canvas.stroke([(160, 180), (520, 180), (520, 430), (160, 430), (160, 180)])
    canvas.set_color((16, 124, 16, 255))
    canvas.fill(320, 300)
    canvas.set_brush("oil")
    canvas.set_color((196, 80, 40, 255))
    canvas.set_size(54)
    canvas.stroke([(640, 220), (780, 360), (920, 200), (1040, 420)])
    canvas.set_brush("pencil")
    canvas.set_color((40, 40, 40, 255))
    canvas.set_size(18)
    canvas.stroke([(200, 600), (420, 560), (640, 640), (960, 580)])
    canvas.set_brush("watercolor")
    canvas.set_color((136, 23, 152, 255))
    canvas.set_size(70)
    canvas.stroke([(260, 700), (560, 730), (860, 690)])
    canvas.set_color((0, 0, 0, 255))
    canvas.set_size(12)
    window.apply_paint_settings()

    for index, kind in enumerate(("cube", "sphere", "cone", "torus")):
        obj = window.scene.insert(kind)
        obj.transform.position = np.array([-2.4 + index * 1.6, -0.6, 0.9])
        obj.color = [(232, 17, 35, 255), (0, 120, 212, 255), (255, 185, 0, 255),
                     (136, 23, 152, 255)][index]
    window.scene.selected_index = 1
    window.stage.reload_canvas()


if __name__ == "__main__":
    raise SystemExit(main())
