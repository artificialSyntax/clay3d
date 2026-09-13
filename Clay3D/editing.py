"""Tool actions. Mixin on EditorWindow. begin/drag/end_canvas from Stage."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QPainter

from Clay3D import brushes, icons, imagefx, selection, shapes2d
from Clay3D.canvas2d import (
    anchor_offset,
    canvas_orb_positions,
    hit_canvas_orb,
    opposite_orb_anchor,
    size_from_orb_drag,
    union,
)
from Clay3D.doodle import doodle_to_mesh
from Clay3D.io_files import IMAGE_SUFFIXES, pixels_from_path
from Clay3D.scene3d import SceneObject

def handles_for_box(box, reach: float) -> dict[str, tuple[float, float]]:
    """The eight resize handles, plus the rotate grip above the box.

    Corners and edge midpoints both, which is what the original shows and
    what its own instruction describes: "Drag in the corners or sides of
    the blue box to show us what to focus on."
    """
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {
        "TopLeft": (x0, y0),
        "Top": (cx, y0),
        "TopRight": (x1, y0),
        "Right": (x1, cy),
        "BottomRight": (x1, y1),
        "Bottom": (cx, y1),
        "BottomLeft": (x0, y1),
        "Left": (x0, cy),
        "Rotate": (cx, y0 - reach * 2.2),
    }


STICKER_SOURCE_SIZE = 512   # px; stickers render this big and scale down on the canvas

# Drag modes that manipulate an existing selection rather than make one.
_SELECTION_DRAGS = (
    "move", "Rotate",
    "TopLeft", "Top", "TopRight", "Right",
    "BottomRight", "Bottom", "BottomLeft", "Left",
)


@dataclass
class TextBox:
    """A text box being typed into, before it is committed to pixels."""

    x: float
    y: float
    text: str = ""
    family: str = "Sans Serif"
    size: int = 48
    bold: bool = False
    italic: bool = False
    underline: bool = False
    align: str = "left"
    background: tuple | None = None   # Background fill colour, or None for none

    def font(self) -> QFont:
        font = QFont(self.family, self.size)
        font.setBold(self.bold)
        font.setItalic(self.italic)
        font.setUnderline(self.underline)
        return font


@dataclass
class LiveShape:
    """A 2D shape, line or sticker sitting on the paper until stamped."""

    kind: str
    start: tuple[float, float]
    end: tuple[float, float]
    points: list = field(default_factory=list)
    color: tuple = (0, 0, 0, 255)
    style: str = "both"
    thickness: float = 8.0
    opacity: float = 1.0
    pixels: object = None
    size: tuple[float, float] | None = None   # on-canvas size of pixels; start is the centre
    placed: bool = False
    source: str = "shape"

    def box(self) -> tuple[float, float, float, float]:
        if self.points:
            path = shapes2d.line_path(self.kind, self.points)
            xs, ys = [x for x, _ in path], [y for _, y in path]
            return (min(xs), min(ys), max(xs), max(ys))
        if self.pixels is not None:
            if self.size is not None:
                width, height = self.size
            else:
                height, width = self.pixels.shape[:2]
            cx, cy = self.start
            return (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
        x0, x1 = sorted((self.start[0], self.end[0]))
        y0, y1 = sorted((self.start[1], self.end[1]))
        return (x0, y0, x1, y1)

    def move(self, dx: float, dy: float) -> None:
        self.start = (self.start[0] + dx, self.start[1] + dy)
        self.end = (self.end[0] + dx, self.end[1] + dy)
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def contains(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.box()
        # A thin line still needs something to grab.
        pad = self.thickness / 2 + 6 if self.points else 0
        return x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad


class EditingTools:
    """Tool behaviour for `EditorWindow`. Not useful on its own."""

    # ---- canvas tools ----------------------------------------------------

    def begin_canvas(self, x: float, y: float, mods):
        tool = self.tool
        if tool == "eyedropper":
            self.set_color(self.canvas.pixel(int(x), int(y)))
            self.set_tool(self._before_eyedropper)
            return None
        if tool == "select:crop":
            return self._begin_crop_drag(x, y)
        if tool in brushes.CATALOG:
            self.push_undo()
            self.apply_paint_settings()
            return self.canvas.begin_stroke(x, y)
        if tool == "fill":
            self.push_undo()
            self.apply_paint_settings()
            return self.canvas.fill(int(x), int(y))
        if tool.startswith("shape:"):
            if self._begin_live_edit(x, y):
                return None
            self.live_shape = LiveShape(
                tool.split(":", 1)[1], (x, y), (x, y),
                color=self.color, style=self.shape_style,
                thickness=self.size, opacity=self.opacity, source="shape",
            )
            self._live_drag = "place"
            return None
        if tool.startswith("line:"):
            if self._begin_live_edit(x, y):
                return None
            kind = tool.split(":", 1)[1]
            self.live_shape = LiveShape(
                kind, (x, y), (x, y), points=shapes2d.line_points(kind, (x, y), (x, y)),
                color=self.color, style=self.shape_style,
                thickness=self.size, opacity=self.opacity, source="line",
            )
            self._live_drag = "place"
            return None
        if tool.startswith("doodle_") or tool == "tube":
            self._stroke_points = [(x, y)]
            return None
        if tool.startswith("sticker:"):
            return self.place_sticker(x, y, mods)
        if tool == "text":
            # Read the chosen style first: committing clears the box it lives on.
            style = self.text_box
            self.commit_text_box()
            self.text_box = TextBox(x, y)
            if style is not None:
                for key in ("family", "size", "bold", "italic", "underline", "align", "background"):
                    setattr(self.text_box, key, getattr(style, key))
            self.setFocus()
            return None
        if tool in self.MAGIC_TOOLS:
            return self._begin_magic(x, y)
        if tool.startswith("select:"):
            return self._begin_selection(tool.split(":", 1)[1], x, y)
        return None

    def drag_canvas(self, x: float, y: float, mods):
        tool = self.tool
        if tool in brushes.CATALOG:
            return self.canvas.extend_stroke(x, y)
        if self._editing_live_item():
            return self._drag_live_item(x, y)
        if tool.startswith("doodle_") or tool == "tube":
            self._stroke_points.append((x, y))
            self.stage.update()
            return None
        if tool in self.MAGIC_TOOLS:
            return self._drag_magic(x, y)
        if tool == "select:crop":
            return self._drag_crop(x, y)
        if tool.startswith("select:") and self._drag_mode is not None:
            return self._drag_selection(x, y)
        return None

    def end_canvas(self, x, y, mods):
        tool = self.tool
        if tool in brushes.CATALOG:
            return self.canvas.end_stroke()
        if self._editing_live_item():
            if self._live_drag == "place":
                self.live_shape.placed = True
            self._live_drag = None
            self.stage.update()
            return None
        if tool.startswith("doodle_"):
            return self._finish_doodle()
        if tool == "tube":
            return self._finish_tube()
        if tool in self.MAGIC_TOOLS:
            return self._end_magic()
        if tool == "select:crop":
            self._crop_drag = None
            return None
        if tool.startswith("select:") and self._drag_mode is not None:
            return self._end_selection(x, y)
        return None

    def cancel_current(self) -> None:
        """Escape: abandon whatever is in progress, text included."""
        if self.magic is not None:
            self.choose_select_tool("select:box")
        self.live_shape = None
        self._live_drag = None
        self._stroke_points = []
        self.text_box = None
        self.stage.update()

    # ---- shapes ---------------------------------------------------------

    def commit_live_shape(self):
        shape = self.live_shape
        self.live_shape = None
        self._live_drag = None
        if shape is None:
            return None
        x0, y0, x1, y1 = shape.box()
        too_small = shape.pixels is None and x1 - x0 < 2 and y1 - y0 < 2
        if too_small:
            return None
        self.push_undo()
        saved = (self.color, self.size, self.opacity, self.shape_style)
        self.color = shape.color
        self.size = shape.thickness
        self.opacity = shape.opacity
        self.shape_style = shape.style
        self.apply_paint_settings()
        rect = None
        if shape.pixels is not None:
            rect = self._blit_live_sticker(shape)
        elif shape.points:
            rect = self.canvas.stroke(shapes2d.line_path(shape.kind, shape.points))
        else:
            for part in shapes2d.contours(shape.kind, *shape.start, *shape.end):
                if shape.style in ("both", "fill"):
                    rect = union(rect, self.canvas.fill_polygon(part, shape.color))
                if shape.style in ("both", "outline"):
                    rect = union(rect, self.canvas.stroke(part + part[:1]))
        self.color, self.size, self.opacity, self.shape_style = saved
        self.apply_paint_settings()
        self.stage.mark_canvas_dirty(rect)
        self.refresh_panels()
        return rect

    def stamp_live_item(self):
        """Flatten the live 2D object onto the paper, as Stamp does."""
        return self.commit_live_shape()

    def _editing_live_item(self) -> bool:
        return (
            self.live_shape is not None
            and bool(self._live_drag)
            and self.tool.startswith(("shape:", "line:", "sticker:"))
        )

    def _blit_live_sticker(self, shape: LiveShape):
        from PIL import Image

        x0, y0, x1, y1 = shape.box()
        width, height = max(1, int(x1 - x0)), max(1, int(y1 - y0))
        image = Image.fromarray(shape.pixels, "RGBA").resize(
            (width, height), Image.Resampling.LANCZOS
        )
        pixels = np.array(image)
        if shape.opacity < 1.0:
            pixels[:, :, 3] = (pixels[:, :, 3] * shape.opacity).astype(np.uint8)
        return self.canvas.blit(pixels, int(x0), int(y0))

    def live_item_handles(self) -> dict[str, tuple[float, float]]:
        if self.live_shape is None or not self.live_shape.placed:
            return {}
        box = self.live_shape.box()
        if self.live_shape.source == "line":
            # A line is edited by its points, named as the original names them.
            handles = {f"Point {i + 1}": point for i, point in enumerate(self.live_shape.points)}
        else:
            handles = handles_for_box(box, self._handle_reach())
        x0, y0, x1, y1 = box
        handles["Stamp"] = ((x0 + x1) / 2.0, y1 + self._handle_reach() * 2.6)
        return handles

    def _live_handle_at(self, x: float, y: float) -> str | None:
        reach = self._handle_reach()
        for name, (hx, hy) in self.live_item_handles().items():
            if math.hypot(x - hx, y - hy) <= reach * 1.6:
                return name
        return None

    def _begin_live_edit(self, x: float, y: float) -> bool:
        shape = self.live_shape
        if shape is None or not shape.placed:
            return False
        handle = self._live_handle_at(x, y)
        if handle == "Stamp":
            self.commit_live_shape()
            return True
        if handle:
            self._live_drag = handle
            self._drag_origin = (x, y)
            self._live_start_box = shape.box()
            return True
        if shape.contains(x, y):
            self._live_drag = "move"
            self._drag_origin = (x, y)
            return True
        self.commit_live_shape()
        return False

    def _drag_live_item(self, x: float, y: float):
        shape = self.live_shape
        mode = self._live_drag
        if shape is None or mode is None:
            return None
        if mode == "place":
            shape.end = (x, y)
            if shape.source == "line":
                shape.points = shapes2d.line_points(shape.kind, shape.start, shape.end)
            if shape.pixels is not None:
                shape.start = (x, y)
                shape.end = (x, y)
        elif mode == "move":
            ox, oy = self._drag_origin
            shape.move(x - ox, y - oy)
            self._drag_origin = (x, y)
        elif mode.startswith("Point "):
            shape.points[int(mode.split()[1]) - 1] = (x, y)
        else:
            self._resize_live_item(mode, x, y)
        self.stage.update()
        return None

    def _resize_live_item(self, handle: str, x: float, y: float) -> None:
        x0, y0, x1, y1 = self._live_start_box
        if "Left" in handle:
            x0 = x
        if "Right" in handle:
            x1 = x
        if "Top" in handle:
            y0 = y
        if "Bottom" in handle:
            y1 = y
        self.live_shape.start = (x0, y0)
        self.live_shape.end = (x1, y1)
        if self.live_shape.pixels is not None:
            self.live_shape.start = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
            self.live_shape.end = self.live_shape.start
            width, height = max(8.0, abs(x1 - x0)), max(8.0, abs(y1 - y0))
            self.live_shape.size = (width, height)
            self.sticker_size = int(max(width, height))

    def place_sticker(self, x: float, y: float, mods) -> None:
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if self.live_shape is not None and self.live_shape.source == "sticker":
            if not ctrl and self._begin_live_edit(x, y):
                return None
            if self.live_shape is not None:
                self.commit_live_shape()
        # Keep a large source so the sticker stays sharp when enlarged.
        pixels = self._sticker_pixels(STICKER_SOURCE_SIZE)
        if pixels is None:
            return None
        height, width = pixels.shape[:2]
        fit = self.sticker_size / max(width, height)
        self.live_shape = LiveShape(
            self.tool.split(":", 1)[1],
            (x, y),
            (x, y),
            pixels=pixels,
            placed=True,
            source="sticker",
            color=self.color,
            opacity=self.opacity,
            size=(width * fit, height * fit),
        )
        self._live_drag = None
        self.stage.update()
        return None

    def insert_primitive(self, kind: str) -> None:
        self.push_undo(canvas=False, objects=True)
        obj = self.scene.insert(kind)
        obj.color = self.color
        self.refresh_panels()
        self.stage.update()

    def _finish_doodle(self):
        points = self._stroke_points
        self._stroke_points = []
        if len(points) < 6:
            return None
        mode = "soft" if self.tool == "doodle_soft" else "sharp"
        mesh, centre = doodle_to_mesh(points, mode, self.scene)
        if mesh is None:
            return None
        self.push_undo(canvas=False, objects=True)
        obj = SceneObject(kind=f"doodle-{mode}", mesh=mesh, color=self.color)
        obj.transform.position = centre
        self.scene.add(obj)
        self.set_view("orbit")
        self.refresh_panels()
        return None

    def _finish_tube(self):
        """Sweep the drawn path into a solid, as the Tube brush does."""
        from Clay3D import tube

        points = self._stroke_points
        self._stroke_points = []
        mesh, centre = tube.tube_to_mesh(
            points, self.tube_profile, self.tube_taper, self.size, self.scene
        )
        if mesh is None:
            return None
        self.push_undo(canvas=False, objects=True)
        obj = SceneObject(kind=f"tube-{self.tube_profile}", mesh=mesh, color=self.color)
        obj.transform.position = centre
        self.scene.add(obj)
        self.set_view("orbit")
        self.refresh_panels()
        return None

    # ---- stickers and text ----------------------------------------------

    def stamp_sticker_on_canvas(self, x: float, y: float):
        self.push_undo()
        pixels = self._sticker_pixels(self.sticker_size)
        if pixels is None:
            return None
        half = self.sticker_size // 2
        rect = self.canvas.blit(pixels, int(x) - half, int(y) - half)
        self.stage.mark_canvas_dirty(rect)
        return rect

    def _sticker_pixels(self, size: int):
        """The chosen sticker as RGBA, drawn or loaded from the user's image."""
        kind = self.tool.split(":", 1)[1]
        if kind.startswith("custom:"):
            index = int(kind.split(":", 1)[1])
            if not 0 <= index < len(self.custom_stickers):
                return None
            from PIL import Image

            image = Image.fromarray(self.custom_stickers[index], "RGBA")
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            return np.array(image)
        return _icon_to_array(icons.sticker_icon(kind, size), size)

    def apply_sticker_to_object(self, obj, uv) -> None:
        self.push_undo(canvas=False, objects=True)
        texture = obj.ensure_texture()
        size = max(24, int(texture.shape[0] * 0.22))
        pixels = self._sticker_pixels(size)
        if pixels is None:
            return
        cx = int(uv[0] * texture.shape[1]) - size // 2
        cy = int((1.0 - uv[1]) * texture.shape[0]) - size // 2
        _blend_into(texture, pixels, cx, cy)
        obj.revision += 1
        self.stage.update()

    def commit_text_box(self):
        box = self.text_box
        if box is None or not box.text:
            self.text_box = None
            return None
        self.push_undo()
        pixels, offset = _render_text(box, self.color)
        rect = self.canvas.blit(pixels, int(box.x) + offset[0], int(box.y) + offset[1])
        self.text_box = None
        self.stage.mark_canvas_dirty(rect)
        return rect

    def type_into_text_box(self, event) -> bool:
        """Feed a keystroke to the open text box. False if there isn't one.

        The original's own instruction: "Type to enter text, press
        Shift-Enter to commit text, or press the Escape key to discard."
        """
        if self.text_box is None:
            return False
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and shift:
            self.commit_text_box()
        elif key == Qt.Key.Key_Escape:
            self.text_box = None
            self.stage.update()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.text_box.text += "\n"
        elif key == Qt.Key.Key_Backspace:
            self.text_box.text = self.text_box.text[:-1]
        elif event.text() and event.text().isprintable():
            self.text_box.text += event.text()
        else:
            return False
        self.stage.update()
        return True

    # ---- selection -------------------------------------------------------

    CUTOUT_EDGE = (46, 197, 240, 255)

    MAGIC_TOOLS = ("select:magic", "select:magic_add", "select:magic_remove")

    # ---- magic select ------------------------------------------------------
    # Box stage: adjust the focus box, then Next. Refine stage: Add/Remove
    # strokes re-run the cut, then Done lifts it. Leaving the tool cancels.

    def start_magic_session(self) -> None:
        box = selection.default_magic_box(self.canvas.width, self.canvas.height)
        self.magic = selection.MagicCutout(self.canvas.pixels, box)
        self._magic_drag = None
        self._stroke_points = []

    def cancel_magic_session(self) -> None:
        self.magic = None
        self._magic_drag = None

    def magic_stage(self) -> str | None:
        """None, "box" or "refine"."""
        if self.magic is None:
            return None
        return "refine" if self.magic.segmented else "box"

    def magic_box_handles(self) -> dict[str, tuple[float, float]]:
        if self.magic_stage() != "box":
            return {}
        handles = handles_for_box(self.magic.box, self._handle_reach())
        handles.pop("Rotate")
        return handles

    def magic_next(self) -> None:
        """Next: cut out what the box focuses on."""
        if self.magic_stage() != "box":
            return
        self.cutout_error = None
        if not self.magic.segment():
            self.report_magic_select_failed()
            return
        self.set_tool("select:magic_add")
        self.stage.update()

    def finish_cutout(self) -> None:
        """Done: lift the cutout as a selection, fill behind it if asked."""
        if self.magic_stage() != "refine":
            return
        self.push_undo()
        cutout = self.magic.to_selection()
        self.magic = None
        hole = cutout.mask.copy()
        cutout.lift(self.canvas)
        if self.autofill_background:
            selection.autofill_background(self.canvas, hole)
        self.selection = cutout
        self.stage.reload_canvas()
        self.set_tool("select:box")
        self.refresh_panels()

    def report_magic_select_failed(self) -> None:
        self.cutout_error = "Magic select didn\u2019t work"
        if getattr(self, "suppress_dialogs", False):
            return
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self, "Magic select didn\u2019t work", "Sorry, we couldn\u2019t create your cutout."
        )

    def magic_undo(self) -> None:
        """Undo inside a session steps back through strokes, then to the box."""
        if self.magic_stage() == "refine" and not self.magic.undo():
            self.magic.back_to_box()
            self.set_tool("select:magic")
        self.refresh_panels()
        self.stage.update()

    def magic_redo(self) -> None:
        if self.magic_stage() == "refine":
            self.magic.redo()
        self.refresh_panels()
        self.stage.update()

    def _begin_magic(self, x: float, y: float):
        stage = self.magic_stage()
        if stage == "box":
            reach = self._handle_reach() * 1.4
            for name, (hx, hy) in self.magic_box_handles().items():
                if math.hypot(x - hx, y - hy) <= reach:
                    self._magic_drag = name
                    break
        elif stage == "refine":
            self._magic_drag = "stroke"
            self._stroke_points = [(x, y)]
        return None

    def _drag_magic(self, x: float, y: float):
        if self._magic_drag == "stroke":
            self._stroke_points.append((x, y))
        elif self._magic_drag is not None:
            self.magic.box = _drag_box_edge(
                self.magic.box, self._magic_drag, x, y, self.canvas.width, self.canvas.height
            )
        self.stage.update()
        return None

    def _end_magic(self):
        if self._magic_drag == "stroke" and self.magic is not None:
            self.magic.mark(self._stroke_points, adding=self.tool != "select:magic_remove")
            self._stroke_points = []
        self._magic_drag = None
        self.refresh_panels()
        self.stage.update()
        return None

    def cutout_overlay(self):
        """Cutout image for the refine stage: bright pixels, cyan rim.

        Returns (image, rect in canvas pixels) or None.
        """
        if self.magic_stage() != "refine":
            return None
        mask = self.magic.mask
        rows = np.flatnonzero(mask.any(axis=1))
        cols = np.flatnonzero(mask.any(axis=0))
        if len(rows) == 0:
            return None
        rect = (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)
        signature = id(self.magic.labels)
        if getattr(self, "_cutout_signature", None) == signature:
            return self._cutout_cache

        x0, y0, x1, y1 = rect
        mask = mask[y0:y1, x0:x1]
        pixels = self.canvas.pixels[y0:y1, x0:x1].copy()
        pixels[~mask] = (0, 0, 0, 0)
        interior = mask.copy()
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            interior &= np.roll(mask, shift, axis=axis)
        pixels[mask & ~interior] = self.CUTOUT_EDGE
        image = QImage(
            np.ascontiguousarray(pixels).tobytes(),
            pixels.shape[1], pixels.shape[0], pixels.shape[1] * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        self._cutout_signature = signature
        self._cutout_cache = (image, rect)
        return self._cutout_cache

    def selection_preview(self):
        """The rubber band while a selection box is being dragged out."""
        return getattr(self, "_select_preview", None)

    def selection_frame(self) -> tuple[float, float, float, float] | None:
        """The selection's box in canvas pixels, including any drag so far."""
        if self.selection is None or self.selection.is_empty():
            return None
        bounds = self.selection.bounds
        if bounds is None:
            return None
        return self.selection.frame() or bounds

    def selection_handles(self) -> dict[str, tuple[float, float]]:
        frame = self.selection_frame()
        if frame is None:
            return {}
        return handles_for_box(frame, self._handle_reach())

    def _handle_reach(self) -> float:
        """Handle size in canvas pixels, so it stays constant on screen."""
        return 9.0 / max(self.stage.canvas_scale(), 1e-4)

    def selection_handle_at(self, x: float, y: float) -> str | None:
        reach = self._handle_reach()
        for name, (hx, hy) in self.selection_handles().items():
            if math.hypot(x - hx, y - hy) <= reach * 1.4:
                return name
        return None

    def choose_image(self, title: str) -> np.ndarray | None:
        """Pick an image file; None if cancelled or unreadable (and say so)."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from Clay3D.io_files import IMAGE_FILTER, load_image

        path, _ = QFileDialog.getOpenFileName(self, title, "", IMAGE_FILTER)
        if not path:
            return None
        try:
            return load_image(path).pixels
        except (OSError, ValueError):
            if not getattr(self, "suppress_dialogs", False):
                QMessageBox.information(
                    self, "Can't read that file", "Clay3D can't read this file. It may be invalid, or in a format we don't currently support."
                )
            return None

    def add_custom_sticker(self) -> None:
        """Add sticker: the chosen image joins Custom stickers and is previewed."""
        pixels = self.choose_image("Choose your own sticker")
        if pixels is not None:
            self.use_custom_sticker(pixels)

    def use_custom_sticker(self, pixels: np.ndarray) -> None:
        self.custom_stickers.append(pixels)
        self.set_category("Stickers")
        self.set_tool(f"sticker:custom:{len(self.custom_stickers) - 1}")
        # Preview it on the paper at once, with handles, ready to stamp.
        self.place_sticker(self.canvas.width / 2, self.canvas.height / 2, Qt.KeyboardModifier.NoModifier)
        self.refresh_panels()

    def start_magic_select(self) -> None:
        self.choose_select_tool("select:magic")

    def start_crop(self) -> None:
        self.choose_select_tool("select:crop")

    # ---- crop tool ---------------------------------------------------------
    # A box over the paper with handles, an aspect ratio, then Done or Cancel.

    CROP_RATIOS = {"1:1": 1.0, "16:9": 16 / 9, "3:2": 3 / 2, "4:3": 4 / 3, "5:3": 5 / 3, "9:16": 9 / 16}

    def start_crop_session(self) -> None:
        self.crop_box = (0.0, 0.0, float(self.canvas.width), float(self.canvas.height))
        self.crop_ratio = "free"
        self._crop_drag = None

    def crop_handles(self) -> dict[str, tuple[float, float]]:
        if self.crop_box is None:
            return {}
        handles = handles_for_box(self.crop_box, self._handle_reach())
        handles.pop("Rotate")
        return handles

    def set_crop_ratio(self, key: str) -> None:
        """Reshape the crop box to a ratio, keeping its centre and width where it fits."""
        self.crop_ratio = key
        ratio = self.CROP_RATIOS.get(key)
        if self.crop_box is None or ratio is None:
            self.refresh_panels()
            return
        x0, y0, x1, y1 = self.crop_box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        width = min(x1 - x0, self.canvas.width)
        height = width / ratio
        if height > self.canvas.height:
            height = float(self.canvas.height)
            width = height * ratio
        x0 = min(max(0.0, cx - width / 2), self.canvas.width - width)
        y0 = min(max(0.0, cy - height / 2), self.canvas.height - height)
        self.crop_box = (x0, y0, x0 + width, y0 + height)
        self.refresh_panels()
        self.stage.update()

    def finish_crop(self) -> None:
        if self.crop_box is None:
            return
        box = tuple(int(round(v)) for v in self.crop_box)
        self.crop_box = None
        self.push_undo()
        self.canvas.pixels = imagefx.crop(self.canvas.pixels, box)
        self.canvas.height, self.canvas.width = self.canvas.pixels.shape[:2]
        self.stage.reload_canvas()
        self.choose_select_tool("select:box")
        self.fit_to_window()

    def cancel_crop(self) -> None:
        self.crop_box = None
        self.choose_select_tool("select:box")

    def _begin_crop_drag(self, x: float, y: float):
        self._crop_drag = None
        reach = self._handle_reach() * 1.4
        for name, (hx, hy) in self.crop_handles().items():
            if math.hypot(x - hx, y - hy) <= reach:
                self._crop_drag = name
                return None
        x0, y0, x1, y1 = self.crop_box or (0, 0, 0, 0)
        if x0 <= x <= x1 and y0 <= y <= y1:
            self._crop_drag = ("move", x, y, self.crop_box)
        return None

    def _drag_crop(self, x: float, y: float):
        drag = getattr(self, "_crop_drag", None)
        if drag is None or self.crop_box is None:
            return None
        if isinstance(drag, tuple):
            _, ox, oy, (x0, y0, x1, y1) = drag
            width, height = x1 - x0, y1 - y0
            nx0 = min(max(0.0, x0 + x - ox), self.canvas.width - width)
            ny0 = min(max(0.0, y0 + y - oy), self.canvas.height - height)
            self.crop_box = (nx0, ny0, nx0 + width, ny0 + height)
        else:
            self.crop_box = _drag_box_edge(
                self.crop_box, drag, x, y, self.canvas.width, self.canvas.height
            )
        self.refresh_panels()
        self.stage.update()
        return None

    # ---- selection commands --------------------------------------------------

    def turn_selection(self, direction: str) -> None:
        """Rotate and flip, applied to the floating selection."""
        if self.selection is None or self.selection.is_empty():
            return
        if self.selection.floating is None:
            self.push_undo()
            self.selection.lift(self.canvas)
            self.stage.reload_canvas()
        if direction == "rotate_left":
            self.selection.rotation -= math.pi / 2
        elif direction == "rotate_right":
            self.selection.rotation += math.pi / 2
        elif direction == "flip_horizontal":
            self.selection.scale = self.selection.scale * np.array([-1.0, 1.0])
        elif direction == "flip_vertical":
            self.selection.scale = self.selection.scale * np.array([1.0, -1.0])
        self.refresh_panels()
        self.stage.update()

    def make_sticker_from_selection(self) -> None:
        """Make sticker: the selection becomes a custom sticker to stamp."""
        if self.selection is None or self.selection.is_empty():
            return
        self.copy_selection()
        self.use_custom_sticker(self.clipboard)

    def _begin_selection(self, kind: str, x: float, y: float):
        if self.selection is not None and not self.selection.is_empty():
            handle = self.selection_handle_at(x, y)
            frame = self.selection_frame()
            inside = frame is not None and frame[0] <= x <= frame[2] and frame[1] <= y <= frame[3]
            if handle is not None or inside:
                if self.selection.floating is None:
                    self.push_undo()
                    self.selection.lift(self.canvas)
                    self.stage.reload_canvas()
                self._drag_mode = handle or "move"
                self._drag_origin = (x, y)
                frame = self.selection_frame() or self.selection.bounds
                self._drag_start = (
                    self.selection.offset.copy(),
                    self.selection.scale.copy(),
                    self.selection.rotation,
                    frame,
                )
                return None
            # Undo was pushed when the float started; stamping adds none.
            rect = self.selection.stamp(self.canvas)
            self.selection = None
            self.stage.mark_canvas_dirty(rect)
        self._drag_mode = kind
        self._drag_origin = (x, y)
        self._select_preview = None
        return None

    def _drag_selection(self, x: float, y: float):
        if self._drag_mode == "box":
            x0, y0 = self._drag_origin
            self._select_preview = (min(x0, x), min(y0, y), max(x0, x), max(y0, y))
            self.stage.update()
            return None
        if self.selection is None or self._drag_mode not in _SELECTION_DRAGS:
            self.stage.update()
            return None

        start_offset, start_scale, start_rotation, frame = self._drag_start
        origin_x, origin_y = self._drag_origin
        x0, y0, x1, y1 = frame
        if self._drag_mode == "move":
            self.selection.offset = start_offset + np.array(
                [x - origin_x, y - origin_y], dtype=float
            )
        elif self._drag_mode == "Rotate":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            was = math.atan2(origin_y - cy, origin_x - cx)
            now = math.atan2(y - cy, x - cx)
            self.selection.rotation = start_rotation + (now - was)
        else:
            mode = self._drag_mode
            nx0, ny0, nx1, ny1 = x0, y0, x1, y1
            if "Left" in mode:
                nx0 = x
            elif "Right" in mode:
                nx1 = x
            if "Top" in mode:
                ny0 = y
            elif "Bottom" in mode:
                ny1 = y
            orig_w = max(1.0, x1 - x0)
            orig_h = max(1.0, y1 - y0)
            new_w = max(1.0, abs(nx1 - nx0))
            new_h = max(1.0, abs(ny1 - ny0))
            self.selection.scale = start_scale * np.array([new_w / orig_w, new_h / orig_h])
            # Opposite corner stays put.
            self.selection.offset = start_offset + np.array(
                [min(nx0, nx1) - x0, min(ny0, ny1) - y0], dtype=float
            )
        self.stage.update()
        return None

    def _end_selection(self, x, y):
        mode = self._drag_mode
        self._drag_mode = None
        self._select_preview = None
        if mode in _SELECTION_DRAGS or x is None:
            self.stage.update()
            return None
        x0, y0 = self._drag_origin
        if mode == "box":
            self.selection = selection.box(self.canvas, x0, y0, x, y)
        if self.selection is not None and self.selection.is_empty():
            self.selection = None
        self.stage.update()
        self.refresh_panels()
        return None

    def select_all(self) -> None:
        self.clear_selection()
        self.selection = selection.box(self.canvas, 0, 0, self.canvas.width, self.canvas.height)
        self.stage.update()

    def clear_selection(self) -> None:
        self.stamp_floating()
        self.selection = None
        self.stage.update()

    def stamp_floating(self) -> None:
        """Collapse a floating selection into the paper; keep it selected."""
        if self.selection is not None and self.selection.floating is not None:
            rect = self.selection.stamp(self.canvas)
            self.stage.mark_canvas_dirty(rect)

    def invert_selection(self) -> None:
        if self.selection is None:
            self.select_all()
            return
        self.stamp_floating()
        self.selection = selection.Selection(~self.selection.mask)
        self.stage.update()

    def copy_selection(self) -> None:
        if self.selection is None or self.selection.is_empty():
            return
        placed = self.selection.transformed()
        if placed is not None:
            self.clipboard = placed[0].copy()
            self._set_system_clipboard_image(self.clipboard)
            return
        x0, y0, x1, y1 = self.selection.bounds
        patch = self.canvas.pixels[y0:y1, x0:x1].copy()
        patch[~self.selection.mask[y0:y1, x0:x1]] = (0, 0, 0, 0)
        self.clipboard = patch
        self._set_system_clipboard_image(patch)

    def cut_selection(self) -> None:
        self.copy_selection()
        self.delete_selection()

    def delete_selection(self) -> None:
        if self.selection is None:
            return
        if self.selection.floating is not None:
            # Float already has its undo entry from lift/paste.
            self.selection = None
            self.stage.update()
            return
        if self.selection.is_empty():
            return
        self.push_undo()
        self.canvas.pixels[self.selection.mask] = self.canvas.background
        rect = self.selection.bounds
        self.selection = None
        self.stage.mark_canvas_dirty(rect)

    def paste_clipboard(self) -> None:
        pixels = self.pixels_from_system_clipboard()
        if pixels is None:
            pixels = self.clipboard
        if pixels is None:
            return
        self.place_image(pixels)

    def mime_has_image(self, mime) -> bool:
        if mime is None:
            return False
        if mime.hasImage():
            data = mime.imageData()
            if data is not None and not getattr(data, "isNull", lambda: False)():
                return True
        return any(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
            for url in mime.urls()
        )

    def pixels_from_mime(self, mime) -> np.ndarray | None:
        if mime is None:
            return None
        if mime.hasImage():
            data = mime.imageData()
            image = data.toImage() if hasattr(data, "toImage") else data
            if image is not None and hasattr(image, "isNull") and not image.isNull():
                return _qimage_to_array(image)
        for url in mime.urls():
            pixels = pixels_from_path(url.toLocalFile())
            if pixels is not None:
                return pixels
        return None

    def pixels_from_system_clipboard(self) -> np.ndarray | None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is None:
            return None
        return self.pixels_from_mime(clipboard.mimeData())

    def import_from_mime(self, mime, x: float = 24, y: float = 24) -> bool:
        pixels = self.pixels_from_mime(mime)
        if pixels is None:
            return False
        self.place_image(pixels, x, y)
        return True

    def place_image(self, pixels: np.ndarray, x: float = 24, y: float = 24) -> None:
        pixels = _ensure_rgba(pixels)
        pixels = _fit_to_canvas(pixels, self.canvas.width, self.canvas.height)
        height, width = pixels.shape[:2]
        x = int(max(0, min(int(x), max(0, self.canvas.width - width))))
        y = int(max(0, min(int(y), max(0, self.canvas.height - height))))
        # Previous float collapses first, then undo snapshots that.
        self.clear_selection()
        self.push_undo()
        self.selection = selection.from_layer(self.canvas, pixels, x, y)
        self.set_tool("select:box")
        self.refresh_panels()
        self.stage.update()

    def _set_system_clipboard_image(self, pixels: np.ndarray) -> None:
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication

        pixels = np.ascontiguousarray(_ensure_rgba(pixels))
        height, width = pixels.shape[:2]
        image = QImage(pixels.data, width, height, 4 * width, QImage.Format.Format_RGBA8888).copy()
        QApplication.clipboard().setImage(image)

    def crop_to_selection(self) -> None:
        if self.selection is None or self.selection.is_empty():
            return
        # Box as shown, so a moved or scaled image crops to its whole frame.
        frame = self.selection_frame()
        self.stamp_floating()
        self.push_undo()
        self.canvas.pixels = imagefx.crop(self.canvas.pixels, frame)
        self.canvas.height, self.canvas.width = self.canvas.pixels.shape[:2]
        self.selection = None
        self.stage.reload_canvas()
        self.fit_to_window()

    # ---- canvas operations ------------------------------------------------

    def resize_canvas(
        self, width: int, height: int, anchor: str = "TopLeft", fit: bool = True,
        scale_image: bool = False,
    ) -> None:
        """New paper size. scale_image: "Resize image with canvas"."""
        self.clear_selection()
        self.push_undo()
        if scale_image:
            from PIL import Image

            image = Image.fromarray(self.canvas.pixels, "RGBA")
            image = image.resize((max(1, width), max(1, height)), Image.Resampling.LANCZOS)
            self.canvas.pixels = np.array(image)
            self.canvas.height, self.canvas.width = self.canvas.pixels.shape[:2]
        else:
            self.canvas.resize(width, height, anchor=anchor)
        self.stage.reload_canvas()
        if fit:
            self.fit_to_window()
        self.refresh_panels()

    def shows_canvas_orbs(self) -> bool:
        return self.category == "Canvas"

    def canvas_resize_handles(self) -> dict[str, tuple[float, float]]:
        return canvas_orb_positions(self.canvas.width, self.canvas.height)

    def canvas_orb_at(self, x: float, y: float) -> str | None:
        return hit_canvas_orb(
            x, y, self.canvas.width, self.canvas.height, self._handle_reach()
        )

    def begin_canvas_resize(self, handle: str) -> None:
        self.clear_selection()
        self.push_undo()
        lock = False
        panel = self.panels.get("Canvas")
        if panel is not None and hasattr(panel, "lock"):
            lock = panel.lock.isChecked()
        # Screen-space start. Paper world height is fixed, so canvas coords
        # under the pointer shift as the size changes; read the pointer
        # against the starting frame instead.
        self._canvas_resize = {
            "handle": handle,
            "width": self.canvas.width,
            "height": self.canvas.height,
            "pixels": self.canvas.pixels.copy(),
            "background": self.canvas.background,
            "lock": lock,
            "top_left": self.stage.canvas_to_screen(0, 0),
            "scale": self.stage.canvas_scale(),
        }

    def drag_canvas_resize(self, pointer: QPointF) -> None:
        state = getattr(self, "_canvas_resize", None)
        if state is None or state["top_left"] is None:
            return
        top_left, scale = state["top_left"], state["scale"]
        x = (pointer.x() - top_left.x()) / scale
        y = (pointer.y() - top_left.y()) / scale
        width, height = size_from_orb_drag(
            state["handle"], x, y, state["width"], state["height"], state["lock"]
        )
        anchor = opposite_orb_anchor(state["handle"])
        self.canvas.pixels = state["pixels"]
        self.canvas.width = state["width"]
        self.canvas.height = state["height"]
        self.canvas.background = state["background"]
        self.canvas.resize(width, height, anchor=anchor)
        # Old art stays put on screen; dragged edge lands under the pointer.
        dx, dy = anchor_offset(anchor, width - state["width"], height - state["height"])
        pinned = QPointF(top_left.x() - dx * scale, top_left.y() - dy * scale)
        self.stage.pin_canvas(pinned, scale)
        self.stage.reload_canvas()
        panel = self.panels.get("Canvas")
        if panel is not None:
            panel.refresh()

    def end_canvas_resize(self) -> None:
        self._canvas_resize = None
        self.refresh_panels()

    def turn_canvas(self, direction: str) -> None:
        self.push_undo()
        self.canvas.pixels = imagefx.turn(self.canvas.pixels, direction)
        self.canvas.height, self.canvas.width = self.canvas.pixels.shape[:2]
        self.stage.reload_canvas()
        self.fit_to_window()
        self.refresh_panels()


def _drag_box_edge(box, handle: str, x: float, y: float, width: int, height: int):
    """Box with the edges named by a handle moved to (x, y), kept on the paper."""
    x0, y0, x1, y1 = box
    x = min(max(x, 0.0), float(width))
    y = min(max(y, 0.0), float(height))
    smallest = 8.0
    if "Left" in handle:
        x0 = min(x, x1 - smallest)
    elif "Right" in handle:
        x1 = max(x, x0 + smallest)
    if "Top" in handle:
        y0 = min(y, y1 - smallest)
    elif "Bottom" in handle:
        y1 = max(y, y0 + smallest)
    return (x0, y0, x1, y1)


def _ensure_rgba(pixels: np.ndarray) -> np.ndarray:
    pixels = np.asarray(pixels)
    if pixels.ndim == 2:
        pixels = np.repeat(pixels[:, :, None], 3, axis=2)
    if pixels.shape[2] == 3:
        alpha = np.full(pixels.shape[:2] + (1,), 255, dtype=np.uint8)
        pixels = np.concatenate([pixels, alpha], axis=2)
    return np.ascontiguousarray(pixels, dtype=np.uint8)


def _fit_to_canvas(pixels: np.ndarray, canvas_w: int, canvas_h: int) -> np.ndarray:
    height, width = pixels.shape[:2]
    max_w = max(8, int(canvas_w * 0.92))
    max_h = max(8, int(canvas_h * 0.92))
    scale = min(1.0, max_w / width, max_h / height)
    if scale >= 1.0:
        return pixels
    from PIL import Image

    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return np.array(Image.fromarray(pixels).resize(size, Image.Resampling.LANCZOS))


def _icon_to_array(icon: QIcon, size: int) -> np.ndarray:
    pixmap = icon.pixmap(QSize(size, size))
    return _qimage_to_array(pixmap.toImage())


def _qimage_to_array(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = converted.width(), converted.height()
    buffer = np.frombuffer(converted.constBits(), dtype=np.uint8)
    return buffer.reshape(height, converted.bytesPerLine() // 4, 4)[:, :width].copy()


def _blend_into(target: np.ndarray, source: np.ndarray, x: int, y: int) -> None:
    """Alpha-composite `source` onto `target` at (x, y), clipped to fit."""
    h, w = source.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(target.shape[1], x + w), min(target.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    patch = source[y0 - y : y1 - y, x0 - x : x1 - x].astype(np.float32)
    alpha = patch[:, :, 3:4] / 255.0
    base = target[y0:y1, x0:x1].astype(np.float32)
    blended = patch * alpha + base * (1.0 - alpha)
    blended[:, :, 3] = np.maximum(base[:, :, 3], patch[:, :, 3])
    target[y0:y1, x0:x1] = np.clip(blended, 0, 255).astype(np.uint8)


def _render_text(box: TextBox, color) -> tuple[np.ndarray, tuple[int, int]]:
    """Rasterise a text box with Qt's font engine, ready to blit."""
    font = box.font()
    metrics = QFontMetrics(font)
    lines = box.text.split("\n")
    width = max((metrics.horizontalAdvance(line) for line in lines), default=1) + 8
    height = metrics.height() * len(lines) + 8
    image = QImage(max(1, width), max(1, height), QImage.Format.Format_RGBA8888)
    if box.background is not None:
        image.fill(QColor(*box.background[:3]))
    else:
        image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setFont(font)
    painter.setPen(QColor(*color[:3]))
    for index, line in enumerate(lines):
        x = 4
        if box.align == "center":
            x = (width - metrics.horizontalAdvance(line)) / 2
        elif box.align == "right":
            x = width - metrics.horizontalAdvance(line) - 4
        painter.drawText(QPointF(x, 4 + metrics.ascent() + index * metrics.height()), line)
    painter.end()
    return _qimage_to_array(image), (0, 0)
