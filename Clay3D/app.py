"""Main window. Tabs, stage, panels."""

from __future__ import annotations

import argparse
import math
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
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
    QFileDialog,
    QGridLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Clay3D import brushes, chrome, icons, recent, selection, settings, shapes2d, stickers
from Clay3D.canvas2d import Canvas
from Clay3D.io_files import IMAGE_FILTER, load_image, load_scene
from Clay3D.document import DocumentActions, recovered_projects, recovery_dir
from Clay3D.editing import EditingTools, TextBox
from Clay3D.panels import CONTEXT_PANELS, TABS
from Clay3D.recording import HistoryRecorder, ffmpeg_available
from Clay3D.scene3d import Scene
from Clay3D.stage import Stage
from Clay3D.theme import ACCENT, STYLESHEET

from Clay3D.tuning import CANVAS_DEFAULT_SIZE, UNDO_DEPTH

CANVAS_WIDTH, CANVAS_HEIGHT = CANVAS_DEFAULT_SIZE


@dataclass
class Undo:
    """One reversible step. Only the parts a step touched are captured.

    pixels starts as a full canvas copy. Once the next step is pushed, a
    background thread shrinks it to the rectangle that step changed
    (rect is then set), which is all an undo needs to put back.
    """

    pixels: np.ndarray | None = None
    size: tuple[int, int] | None = None
    objects: list | None = None
    selected: int = -1
    background: tuple = (255, 255, 255, 255)
    rect: tuple[int, int, int, int] | None = None
    trimming: Future | None = None


UNDO_TRIMMER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clay3d-undo")


def _trim_undo(entry: Undo, after: np.ndarray) -> None:
    """Keep only the part of entry.pixels that differs from the state after it."""
    import cv2

    difference = cv2.absdiff(entry.pixels, after)
    changed = difference[:, :, 0]
    for channel in range(1, 4):
        changed = cv2.bitwise_or(changed, difference[:, :, channel])
    x, y, width, height = cv2.boundingRect(changed)
    entry.pixels = entry.pixels[y:y + height, x:x + width].copy()
    entry.rect = (x, y, x + width, y + height)


class EditorWindow(QMainWindow, EditingTools, DocumentActions):
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
        self.custom_stickers: list[np.ndarray] = []   # Add sticker / Make sticker, in order
        self.magic = None               # selection.MagicCutout while magic select is open
        self.autofill_background = True  # "Lift an object out ... we'll automatically fill in the background"
        self.material_index = 0         # theme.MATERIALS, "Matte"
        self.crop_box = None            # (x0, y0, x1, y1) while the crop tool is open
        self.crop_ratio = "free"
        self._before_eyedropper = "marker"
        self.tube_profile = "cylinder"
        self.tube_taper = "uniform"
        self.selection: selection.Selection | None = None
        self.clipboard: np.ndarray | None = None
        self.text_box: TextBox | None = None
        self.live_shape: LiveShape | None = None
        self._live_drag = None
        self._live_start_box = (0.0, 0.0, 0.0, 0.0)
        self._stroke_points: list[tuple[float, float]] = []
        self.recorder = HistoryRecorder()
        self._undo: list[Undo] = []
        self._redo: list[Undo] = []
        self._drag_mode: str | None = None
        self._drag_origin = (0.0, 0.0)
        self._drag_start = (np.zeros(2), np.ones(2), 0.0, (0, 0, 0, 0))
        self.cutout_error: str | None = None
        self.suppress_dialogs = False

        self._build()
        self.init_document()
        self.apply_saved_settings()
        if recovered_projects():
            # Work left behind by a session that didn't close cleanly: show it.
            QTimer.singleShot(0, self.show_recovered_on_launch)
        self.setAcceptDrops(True)
        self.apply_paint_settings()
        self.set_category("Brushes")
        QTimer.singleShot(0, self.fit_to_window)

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

        column.addWidget(chrome.top_bar(self, [name for name, _ in TABS]))

        # Paint 3D's grid: tools bar over the stage, side panel beside both.
        body = QGridLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.stage = Stage(self)
        body.addWidget(chrome.tools_bar(self), 0, 0)
        body.addWidget(self.stage, 1, 0)
        body.addWidget(self._right_panel(), 0, 1, 2, 1)
        body.setRowStretch(1, 1)
        body.setColumnStretch(0, 1)
        column.addLayout(body, 1)

        self.stack = QStackedWidget()
        self.stack.addWidget(page)
        self.menu_page = chrome.menu_page(self)
        self.stack.addWidget(self.menu_page)
        from Clay3D.saveas import SaveAsImagePage

        self.save_as_page = SaveAsImagePage(self)
        self.stack.addWidget(self.save_as_page)
        self.setCentralWidget(self.stack)
        self._install_shortcuts()

    def closeEvent(self, event) -> None:
        self.handle_close(event)

    def dragEnterEvent(self, event) -> None:
        if self.mime_has_image(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if self.mime_has_image(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if self.import_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def _right_panel(self) -> QWidget:
        holder = QWidget()
        holder.setObjectName("rightPanel")
        holder.setFixedWidth(chrome.SIDE_PANEL_WIDTH)
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
        # Compact view: a narrow strip naming the tab; click it to open the panel.
        self.compact_header = QToolButton()
        self.compact_header.setProperty("role", "compactHeader")
        self.compact_header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.compact_header.setIconSize(QSize(24, 24))
        self.compact_header.setFixedHeight(chrome.COMPACT_HEADER_HEIGHT)
        self.compact_header.setToolTip("Sidebar")
        self.compact_header.clicked.connect(lambda checked=False: self.toggle_compact_panel())
        self.compact_header.hide()
        box.addWidget(self.compact_header)
        box.addWidget(self.panel_stack, 1)
        self.compact_filler = QWidget()     # holds the strip at the top while collapsed
        self.compact_filler.hide()
        box.addWidget(self.compact_filler, 1)
        self.right_panel = holder
        return holder

    def _install_shortcuts(self) -> None:
        for keys, handler in (
            (QKeySequence.StandardKey.Undo, self.undo),
            (QKeySequence.StandardKey.New, self.new_document),
            (QKeySequence.StandardKey.Open, self.open_file),
            (QKeySequence.StandardKey.Save, self.save_document),
            (QKeySequence.StandardKey.Copy, self.copy_selection),
            (QKeySequence.StandardKey.Cut, self.cut_selection),
            (QKeySequence.StandardKey.Paste, self.paste_clipboard),
            (QKeySequence.StandardKey.SelectAll, self.select_all),
            (QKeySequence.StandardKey.Delete, self.delete_selection),
        ):
            shortcut = QShortcut(QKeySequence(keys), self, handler)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        # Redo is spelled out rather than StandardKey.Redo: that already means
        # Ctrl+Shift+Z here (and Ctrl+Y elsewhere), and a key bound twice is
        # ambiguous to Qt, which then runs neither.
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

    # ---- categories and settings ---------------------------------------

    def choose_select_tool(self, tool: str) -> None:
        """Pick a select tool from the top bar and show its options."""
        if not isinstance(tool, str) or not tool.startswith("select:"):
            return
        if tool == "select:crop" and self.selection_on_canvas():
            # Crop with something selected crops to it at once, placing it.
            self.crop_to_selection()
            tool = "select:box"
        self.set_tool(tool)
        self.category = "Select"
        for key, button in self.tab_buttons.items():
            button.setChecked(False)
        for key, button in self.select_buttons.items():
            button.setChecked(key == tool)
        self.panel_stack.setCurrentIndex(self.panel_index["Select"])
        self.refresh_panels()

    def selection_on_canvas(self) -> bool:
        """A selection whose box overlaps the paper, so there is something to crop to."""
        frame = self.selection_frame()
        if frame is None:
            return False
        x0, y0, x1, y1 = frame
        return x1 > 0 and y1 > 0 and x0 < self.canvas.width and y0 < self.canvas.height

    def set_compact_view(self, on: bool) -> None:
        """Settings > Use compact view: sidebar narrows to a strip until opened."""
        self.compact_view = on
        settings.save("compact_view", on)
        self.compact_header.setVisible(on)
        self._show_panel(not on)

    def toggle_compact_panel(self) -> None:
        self._show_panel(not self.panel_stack.isVisible())

    def _show_panel(self, open_: bool) -> None:
        self.panel_stack.setVisible(open_)
        self.compact_filler.setVisible(not open_)
        width = chrome.SIDE_PANEL_WIDTH if open_ else chrome.COMPACT_PANEL_WIDTH
        self.right_panel.setFixedWidth(width)
        self._label_compact_header()

    def _label_compact_header(self) -> None:
        name = getattr(self, "category", "Brushes")
        icon_name = chrome.TAB_ICONS.get(name, "square-dashed-mouse-pointer")
        self.compact_header.setIcon(icons.ui_icon(icon_name, 24))
        self.compact_header.setText(name)

    def set_display_quality(self, level: str) -> None:
        settings.save("display_quality", level)
        self.stage.set_quality(level)
        self.stage.update()

    def apply_saved_settings(self) -> None:
        self.compact_switch.setChecked(settings.load("compact_view"))
        self.set_compact_view(settings.load("compact_view"))
        self.perspective_switch.setChecked(settings.load("show_perspective"))
        level = settings.load("display_quality")
        self.quality_choice.setCurrentIndex(self.quality_choice.findData(level))
        self.stage.renderer.set_quality(level)

    def set_category(self, name: str) -> None:
        if name != "Select":
            self.clear_selection()
        self.category = name
        if getattr(self, "compact_view", False):
            self._label_compact_header()
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
            "Stickers": f"sticker:{stickers.CATALOG[0][0]}",
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
                        "eraser", "crayon", "spray", "fill", "eyedropper"),
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
        if tool == "select:crop" and self.tool != "select:crop":
            self.start_crop_session()
        elif tool != "select:crop":
            self.crop_box = None
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

    def set_material(self, index: int) -> None:
        """Material dropdown: a named look, applied to the selected 3D object."""
        from Clay3D.theme import MATERIALS

        self.material_index = index
        _, smoothness, metallic = MATERIALS[index]
        self.set_object_material(smoothness=smoothness, metallic=metallic)

    def toggle_eyedropper(self) -> None:
        """Eyedropper button: pick one colour, then go back to the tool in hand."""
        if self.tool == "eyedropper":
            self.set_tool(self._before_eyedropper)
            return
        self._before_eyedropper = self.tool
        self.set_tool("eyedropper")

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
        self.history_button.setEnabled(bool(self._undo or self._redo))
        active = "select:magic" if self.tool in self.MAGIC_TOOLS else self.tool
        for tool, button in getattr(self, "select_buttons", {}).items():
            button.setChecked(active == tool)

    # ---- view ----------------------------------------------------------

    def set_view(self, mode: str) -> None:
        self.commit_text_box()
        self.commit_live_shape()
        self.scene.set_view(mode)
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
        self.zoom_changed()
        self.stage.update()

    def set_zoom_percent(self, percent: int) -> None:
        self._zoom_slider_moved(percent)

    def zoom_changed(self) -> None:
        percent = int(round(self.stage.canvas_scale() * 100))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(10, min(800, percent)))
        self.zoom_slider.blockSignals(False)
        self.zoom_box.blockSignals(True)
        self.zoom_box.setValue(max(10, min(800, percent)))
        self.zoom_box.blockSignals(False)

    def set_perspective(self, on: bool) -> None:
        """Toggle the 3D workspace between perspective and orthographic."""
        settings.save("show_perspective", on)
        self.scene.camera.set_perspective(on)
        self.stage.update()

    def take_screenshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Take screenshot", "screenshot.png", "PNG (*.png)"
        )
        if path and not self.stage.grab().save(path):
            self.report_save_failure(OSError(f"Could not write {path}"))

    def set_show_canvas(self, visible: bool) -> None:
        self.scene.show_canvas = visible
        self.stage.update()

    def set_transparent_canvas(self, transparent: bool) -> None:
        self.push_undo(canvas=True)
        rect = self.canvas.make_transparent() if transparent else self.canvas.make_opaque()
        self.stage.mark_canvas_dirty(rect)

    # ---- undo ----------------------------------------------------------

    def set_recording(self, on: bool) -> None:
        if on:
            self.recorder.start()
            self.recorder.capture(self.canvas.pixels)
        else:
            self.recorder.stop()

    def export_history_video(self) -> None:
        """Export as video: the recorded edits as a time-lapse."""
        if ffmpeg_available():
            default, filters = "history.mp4", "MP4 video (*.mp4);;Animated GIF (*.gif)"
        else:
            default, filters = "history.gif", "Animated GIF (*.gif)"
        path, _ = QFileDialog.getSaveFileName(self, "Export as video", default, filters)
        if not path:
            return
        if not path.lower().endswith((".mp4", ".gif")):
            path += ".mp4" if ffmpeg_available() else ".gif"
        try:
            self.recorder.export(path, self.canvas.pixels)
        except (OSError, ValueError) as error:
            QMessageBox.information(self, "Sorry, that didn't work.", str(error))

    def push_undo(self, canvas: bool = True, objects: bool = False) -> None:
        # Each edit is a frame of the time-lapse, taken as the edit begins.
        self.recorder.capture(self.canvas.pixels)
        entry = Undo(selected=self.scene.selected_index, background=self.canvas.background)
        if canvas:
            entry.pixels = self.canvas.pixels.copy()
            entry.size = (self.canvas.width, self.canvas.height)
            self._trim_previous_undo(entry)
        if objects:
            entry.objects = [o.copy() for o in self.scene.objects]
        self._undo.append(entry)
        self._redo.clear()
        self.mark_unsaved()
        del self._undo[:-UNDO_DEPTH]
        self.refresh_panels()

    def _trim_previous_undo(self, entry: Undo) -> None:
        """The step before this one is finished: shrink its snapshot in the background."""
        if not self._undo:
            return
        previous = self._undo[-1]
        if previous.pixels is None or previous.rect is not None or previous.trimming is not None:
            return
        if previous.size != entry.size:
            return  # a resize in between; the full copy is the only thing that restores it
        previous.trimming = UNDO_TRIMMER.submit(_trim_undo, previous, entry.pixels)

    def _capture(self, like: Undo) -> Undo:
        entry = Undo(selected=self.scene.selected_index, background=self.canvas.background)
        if like.pixels is not None:
            entry.pixels = self.canvas.pixels.copy()
            entry.size = (self.canvas.width, self.canvas.height)
        if like.objects is not None:
            entry.objects = [o.copy() for o in self.scene.objects]
        return entry

    def _restore(self, entry: Undo) -> None:
        if entry.trimming is not None:
            entry.trimming.result()
        if entry.pixels is not None and entry.rect is not None:
            # A trimmed step: the canvas already matches everything outside rect.
            x0, y0, x1, y1 = entry.rect
            self.canvas.pixels[y0:y1, x0:x1] = entry.pixels
            self.canvas.background = entry.background
            if x1 > x0 and y1 > y0:
                self.stage.mark_canvas_dirty(entry.rect)
        elif entry.pixels is not None:
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

    def show_context_menu(self, global_pos) -> None:
        chrome.context_menu(self).exec(global_pos)

    def show_history(self) -> None:
        flyout = chrome.history_flyout(self)
        button = self.history_button
        flyout.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def scrub_history(self, position: int) -> None:
        """History slider: step undo or redo until the stack sits at position."""
        while len(self._undo) > position and self._undo:
            self.undo()
        while len(self._undo) < position and self._redo:
            self.redo()

    def undo(self) -> None:
        if self.magic is not None:
            self.magic_undo()
            return
        if not self._undo:
            return
        entry = self._undo.pop()
        self._redo.append(self._capture(entry))
        self._restore(entry)
        self.mark_unsaved()

    def redo(self) -> None:
        if self.magic is not None:
            self.magic_redo()
            return
        if not self._redo:
            return
        entry = self._redo.pop()
        self._undo.append(self._capture(entry))
        self._restore(entry)
        self.mark_unsaved()

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

    def open_save_as(self) -> None:
        """Menu > Save as > Image: the export preview page."""
        self.clear_selection()
        self.commit_live_shape()
        self.commit_text_box()
        self.save_as_page.open_for()
        self.stack.setCurrentWidget(self.save_as_page)

    def close_save_as(self) -> None:
        self.stack.setCurrentIndex(0)

    def hide_menu(self) -> None:
        self.stack.setCurrentIndex(0)

    def new_document(self) -> None:
        if not self.confirm_leaving_document():
            return
        self.push_undo(canvas=True, objects=True)
        self.scene.canvas = Canvas(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.scene.objects = []
        self.scene.selected_index = -1
        self.selection = None
        self.apply_paint_settings()
        self.stage.reload_canvas()
        self.hide_menu()
        self.set_view("2d")
        self.mark_saved(None)

    def show_recovered_on_launch(self) -> None:
        self.show_menu()
        self.show_open_pane()

    def show_open_pane(self) -> None:
        self.open_pane.rebuild()
        self.menu_panes.setCurrentWidget(self.open_pane)

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", "", f"{IMAGE_FILTER};;Clay3D scene (*.clay3d)"
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if self.confirm_leaving_document():
            self.load_document(path)

    def load_document(self, path: str) -> bool:
        """Replace the document with a file. False (and a message) if it can't be read."""
        try:
            if path.lower().endswith(".clay3d"):
                scene = load_scene(path)
            else:
                canvas = load_image(path)
        except (OSError, ValueError, KeyError):
            QMessageBox.information(
                self, "Can't read that file", "It may be invalid, or in a format we don’t support."
            )
            return False
        self.push_undo(canvas=True, objects=True)
        if path.lower().endswith(".clay3d"):
            self.scene = scene
        else:
            self.scene.canvas = canvas
        self.apply_paint_settings()
        self.stage.reload_canvas()
        self.hide_menu()
        self.fit_to_window()
        self.refresh_panels()
        if Path(path).parent != recovery_dir():
            recent.remember(path)
            self.mark_saved(path)
        return True

    def print_canvas(self) -> None:
        """Menu > Print > 2D print: the picture, fitted to the page."""
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        self.clear_selection()
        self.render_to_printer(printer)

    def render_to_printer(self, printer) -> None:
        pixels = np.ascontiguousarray(self.canvas.pixels)
        height, width = pixels.shape[:2]
        image = QImage(pixels.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888)
        painter = QPainter(printer)
        page = painter.viewport()
        scale = min(page.width() / width, page.height() / height)
        target = QRectF(
            page.x() + (page.width() - width * scale) / 2,
            page.y() + (page.height() - height * scale) / 2,
            width * scale, height * scale,
        )
        painter.drawImage(target, image)
        painter.end()

    def insert_image(self) -> None:
        """Menu > Insert: an image placed on the canvas as a selection."""
        pixels = self.choose_image("Insert")
        if pixels is None:
            return
        self.hide_menu()
        self.choose_select_tool("select:box")
        self.place_image(pixels)

    def save_scene_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as Clay3D project", f"{Path(self.document_name()).stem}.clay3d", "Clay3D project (*.clay3d)"
        )
        if path:
            if not path.lower().endswith(".clay3d"):
                path += ".clay3d"
            self.write_document(path)

    def export_model(self) -> None:
        from Clay3D.io_files import save_model

        from Clay3D.io_files import MODEL_FORMATS

        if not self.scene.objects:
            # The original's words for the same empty case under 3D print.
            QMessageBox.information(self, "Can't save an empty project", "Try adding a shape or two!")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as copy", "model.obj",
            ";;".join(caption for _, caption in MODEL_FORMATS),
        )
        if not path:
            return
        if self.write_file(path, lambda temp: save_model(self.scene, temp)):
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
            polygon = _to_screen(shapes2d.line_path(shape.kind, shape.points), stage)
            if polygon is not None:
                painter.drawPolyline(polygon)
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
        if not shape.points:
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
        """Draw the float through the painter's transform, from a cached preview.

        Resampling the full image every frame made dragging a large paste
        crawl; the exact pixels are only produced when it is stamped.
        """
        selection = self.selection
        if selection is None or selection.floating is None:
            return
        frame = selection.frame()
        centre = stage.canvas_to_screen((frame[0] + frame[2]) / 2, (frame[1] + frame[3]) / 2)
        if centre is None:
            return
        height, width = selection.floating.shape[:2]
        scale_x = stage.canvas_scale() * selection.scale[0]
        scale_y = stage.canvas_scale() * selection.scale[1]
        image = self._float_preview(selection.floating, max(abs(scale_x), abs(scale_y)))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(centre)
        painter.rotate(math.degrees(selection.rotation))
        painter.scale(scale_x, scale_y)
        painter.drawImage(QRectF(-width / 2, -height / 2, width, height), image)
        painter.restore()

    def _float_preview(self, floating: np.ndarray, screen_scale: float) -> QImage:
        """The float as a QImage, halved until it is no bigger than it shows."""
        cache = getattr(self, "_float_cache", None)
        if cache is None or cache["array"] is not floating:
            height, width = floating.shape[:2]
            full = QImage(
                np.ascontiguousarray(floating).tobytes(), width, height, width * 4,
                QImage.Format.Format_RGBA8888,
            ).copy()
            cache = {"array": floating, "levels": {1: full}}
            self._float_cache = cache
        level = 1
        while level * 2 * screen_scale <= 1.0 and level < 64:
            level *= 2
        if level not in cache["levels"]:
            full = cache["levels"][1]
            cache["levels"][level] = full.scaled(
                max(1, full.width() // level), max(1, full.height() // level),
                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
        return cache["levels"][level]

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
        if box.background is not None:
            painter.setBrush(QColor(*box.background[:3]))
        else:
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


def use_host_file_dialogs() -> None:
    """Open and save through the desktop's own file chooser.

    Qt's xdg-desktop-portal theme hands file dialogs to the portal, which
    shows the host's chooser (KDE, GNOME, ...). Where no portal answers, Qt
    falls back to its built-in dialog. A theme the user set is left alone.
    Must run before QApplication exists.
    """
    if sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORMTHEME"):
        os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"


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

    use_host_file_dialogs()
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
