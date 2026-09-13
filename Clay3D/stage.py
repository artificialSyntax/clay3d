"""GL stage + overlay chrome. Mouse → canvas pixels or object pick."""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from Clay3D import gizmo
from Clay3D.camera import project
from Clay3D.canvas2d import union
from Clay3D.renderer import SceneRenderer

# Manipulator and cutout chrome colours.
FRAME_LINE = QColor("#919191")
ANCHOR_FILL = QColor("#FCFCFC")
ANCHOR_EDGE = QColor("#C5C5C5")
BUTTON_FILL = QColor("#D8D8D8")
BUTTON_EDGE = QColor("#9E9E9E")
BUTTON_ICON = QColor("#5A5A5A")
BOX_LINE = QColor("#C5C5C5")
DIM_OUTSIDE = QColor(0, 0, 0, 153)      # the original dims to about 40%
STROKE_INNER = QColor("#FFFFFF")        # magic select add/remove stroke
STROKE_OUTER = QColor("#1E1E1E")
ANCHOR_SIZE = 9.0
BUTTON_RADIUS = 13.0
CURSOR_COLOR = QColor(32, 31, 30, 160)


class Stage(QOpenGLWidget):
    """The GL surface. All raw GL lives in the renderer it owns."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.renderer = SceneRenderer()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setMinimumSize(480, 360)

        self._pending_upload = None
        self._full_upload = True
        self._navigating = None
        self._last_mouse = QPoint()
        self._right_press: QPoint | None = None   # a right click that has not moved yet
        self._cursor_at: QPointF | None = None
        self._space_held = False
        self._gizmo_drag: gizmo.Drag | None = None
        self._painting = False
        self._resizing_canvas = False
        self.overlay = Overlay(self)

    @property
    def scene(self):
        return self.editor.scene

    # ---- GL -------------------------------------------------------------

    def initializeGL(self) -> None:
        self.renderer.initialize()
        self.renderer.sync_canvas(self.scene.canvas)
        self._full_upload = False
        # GL objects must be freed while their context is still current.
        self.context().aboutToBeDestroyed.connect(self._release_gl)

    def _release_gl(self) -> None:
        self.makeCurrent()
        self.renderer.release()
        self.doneCurrent()

    def paintGL(self) -> None:
        self._flush_canvas_uploads()
        ratio = self.devicePixelRatioF()
        self.renderer.render(
            self.scene,
            int(self.width() * ratio),
            int(self.height() * ratio),
            self.defaultFramebufferObject(),
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
        self._place_controls()

    def update(self) -> None:
        """Repaint the scene and the chrome drawn over it together."""
        super().update()
        self.overlay.update()

    def _flush_canvas_uploads(self) -> None:
        if self._full_upload:
            self.renderer.sync_canvas(self.scene.canvas)
            self._full_upload = False
        elif self._pending_upload is not None:
            self.renderer.sync_canvas(self.scene.canvas, self._pending_upload)
        self._pending_upload = None

    def mark_canvas_dirty(self, rect=None) -> None:
        """Queue a canvas region for upload before the next frame."""
        if rect is None:
            self._full_upload = True
        else:
            self._pending_upload = union(self._pending_upload, rect)
        self.update()

    def set_quality(self, name: str) -> None:
        self.makeCurrent()
        self.renderer.set_quality(name)
        self.doneCurrent()
        self.reload_canvas()

    def reload_canvas(self) -> None:
        self._full_upload = True
        self.update()

    # ---- coordinates ----------------------------------------------------

    def canvas_point(self, pos: QPointF) -> tuple[float, float] | None:
        """Where a screen position lands on the canvas, in canvas pixels."""
        origin, direction = self.scene.camera.ray(
            pos.x(), pos.y(), self.width(), self.height()
        )
        return self.scene.canvas_hit(origin, direction)

    def canvas_to_screen(self, x: float, y: float) -> QPointF | None:
        world = self.scene.canvas_to_world(x, y)
        matrix = self.scene.camera.view_projection(self.width(), self.height())
        point = project(world, matrix, self.width(), self.height())
        return None if point is None else QPointF(point[0], point[1])

    def canvas_scale(self) -> float:
        """Screen pixels per canvas pixel, for sizing overlay chrome."""
        a = self.canvas_to_screen(0, 0)
        b = self.canvas_to_screen(100, 0)
        if a is None or b is None:
            return 1.0
        return max(abs(b.x() - a.x()) / 100.0, 1e-4)

    def pin_canvas(self, top_left: QPointF, scale: float) -> None:
        """Move the 2D view so canvas (0, 0) sits at top_left at this zoom."""
        camera = self.scene.camera
        if camera.mode != "2d":
            return
        camera.zoom *= scale / self.canvas_scale()
        now = self.canvas_to_screen(0, 0)
        if now is None:
            return
        camera.pan_by(top_left.x() - now.x(), top_left.y() - now.y(), self.width(), self.height())

    def pick(self, pos: QPointF):
        origin, direction = self.scene.camera.ray(
            pos.x(), pos.y(), self.width(), self.height()
        )
        return self.scene.pick(origin, direction)

    # ---- mouse ----------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        pos = event.position()
        self._last_mouse = pos.toPoint()
        button = event.button()
        mods = event.modifiers()

        # The original's Controls help: left drag orbits; right, middle and
        # Alt+left all pan; the wheel zooms; double click resets the view.
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        if (
            button == Qt.MouseButton.MiddleButton
            or button == Qt.MouseButton.RightButton
            or self._space_held
            or (button == Qt.MouseButton.LeftButton and alt)
        ):
            self._navigating = "pan"
            if button == Qt.MouseButton.RightButton:
                self._right_press = pos.toPoint()
            return
        if button != Qt.MouseButton.LeftButton:
            return

        if self._start_gizmo(pos):
            return
        at = self.canvas_point(pos)
        if self.editor.shows_canvas_orbs() and at is not None:
            handle = self.editor.canvas_orb_at(*at)
            if handle is not None:
                self._resizing_canvas = True
                self.editor.begin_canvas_resize(handle)
                return
            if self.editor.tool in ("canvas", "none"):
                return
        if self.editor.tool_wants_objects():
            hit = self.pick(pos)
            obj, uv, normal = (hit[0], hit[2], hit[3]) if hit else (None, None, None)
            if self.editor.click_object(obj, uv, normal, mods):
                self.update()
                return
            # The tool passed on it, so let the canvas take the click.

        on_paper = at is not None and self.scene.canvas_contains(*at)
        # Magic select box handles sit on the paper's edge, half off it.
        box_open = self.editor.magic_stage() == "box" or self.editor.crop_box is not None
        if at is None or not (on_paper or box_open):
            # Empty stage: a left drag out here orbits, as the original does.
            if self.scene.camera.mode == "orbit":
                self._navigating = "orbit"
            return
        self._painting = True
        self.mark_canvas_dirty(self.editor.begin_canvas(at[0], at[1], mods))

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        self._cursor_at = pos

        if self._navigating is not None:
            self._navigate(pos)
            return
        if self._gizmo_drag is not None:
            uniform = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._gizmo_drag.update(pos.x(), pos.y(), self.width(), self.height(), uniform)
            self.update()
            return
        if self._resizing_canvas:
            self.editor.drag_canvas_resize(pos)
            return
        if self._painting:
            at = self.canvas_point(pos)
            if at is not None:
                self.mark_canvas_dirty(
                    self.editor.drag_canvas(at[0], at[1], event.modifiers())
                )
            return
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        pos = event.position()
        if self._navigating is not None:
            self._navigating = None
            # A right click that did not drag opens the menu; a drag pans.
            press, self._right_press = self._right_press, None
            if (
                event.button() == Qt.MouseButton.RightButton
                and press is not None
                and (pos.toPoint() - press).manhattanLength() <= 4
            ):
                self.editor.show_context_menu(self.mapToGlobal(pos.toPoint()))
            return
        if self._resizing_canvas:
            self._resizing_canvas = False
            self.editor.end_canvas_resize()
            self.update()
            return
        if self._gizmo_drag is not None:
            self._gizmo_drag = None
            self.editor.after_gizmo_drag()
            self.update()
            return
        if self._painting:
            self._painting = False
            at = self.canvas_point(pos)
            self.mark_canvas_dirty(
                self.editor.end_canvas(
                    at[0] if at else None, at[1] if at else None, event.modifiers()
                )
            )

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.editor.fit_to_window()

    def wheelEvent(self, event) -> None:
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            return
        self.scene.camera.dolly(1.12 ** steps)
        self.editor.zoom_changed()
        self.update()

    def dragEnterEvent(self, event) -> None:
        if self.editor.mime_has_image(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if self.editor.mime_has_image(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        at = self.canvas_point(event.position())
        x, y = at if at is not None else (24, 24)
        if self.editor.import_from_mime(event.mimeData(), x, y):
            event.acceptProposedAction()

    def _navigate(self, pos: QPointF) -> None:
        dx = pos.x() - self._last_mouse.x()
        dy = pos.y() - self._last_mouse.y()
        self._last_mouse = pos.toPoint()
        if self._navigating == "orbit":
            self.scene.camera.orbit(-dx * 0.008, dy * 0.008)
        else:
            self.scene.camera.pan_by(dx, dy, self.width(), self.height())
        self.update()

    def _start_gizmo(self, pos: QPointF) -> bool:
        obj = self.scene.selected()
        if obj is None or not self.editor.shows_gizmo():
            return False
        frame = gizmo.frame_for(obj, self.scene.camera, self.width(), self.height())
        if frame is None:
            return False
        handle = gizmo.hit_handle(frame, pos.x(), pos.y())
        if handle is None:
            return False
        self.editor.before_gizmo_drag()
        self._gizmo_drag = gizmo.Drag(
            obj, handle, frame, self.scene.camera, (pos.x(), pos.y())
        )
        return True

    # ---- keyboard -------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_held = True
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            return
        if self._view_key(event):
            return
        super().keyPressEvent(event)

    ARROWS = {
        Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
        Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1),
    }
    KEY_PAN_STEP = 40        # screen px per arrow press
    KEY_ORBIT_STEP = 0.08    # radians per arrow press

    def _view_key(self, event) -> bool:
        """The Controls card's keyboard mappings: Home, Page Up/Down, Alt/Ctrl + arrows."""
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key.Key_Home:
            self.editor.fit_to_window()
        elif key == Qt.Key.Key_PageUp:
            self.editor.zoom_by(1.25)
        elif key == Qt.Key.Key_PageDown:
            self.editor.zoom_by(0.8)
        elif key in self.ARROWS and mods & Qt.KeyboardModifier.AltModifier:
            dx, dy = self.ARROWS[key]
            # Arrow points where the view looks, so the paper moves the other way.
            self.scene.camera.pan_by(-dx * self.KEY_PAN_STEP, -dy * self.KEY_PAN_STEP,
                                     self.width(), self.height())
        elif (key in self.ARROWS and mods & Qt.KeyboardModifier.ControlModifier
              and self.scene.camera.mode == "orbit"):
            dx, dy = self.ARROWS[key]
            self.scene.camera.orbit(-dx * self.KEY_ORBIT_STEP, dy * self.KEY_ORBIT_STEP)
        else:
            return False
        self.update()
        return True

    def show_controls(self, visible: bool) -> None:
        from Clay3D.controls_help import ControlsCard

        if getattr(self, "controls_card", None) is None:
            self.controls_card = ControlsCard(self, lambda: self.show_controls(False))
        self.controls_card.setVisible(visible)
        self._place_controls()

    def _place_controls(self) -> None:
        card = getattr(self, "controls_card", None)
        if card is not None:
            card.move(18, self.height() - card.height() - 18)
            card.raise_()

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_held = False
            self.unsetCursor()
            return
        super().keyReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._cursor_at = None
        self.update()


class Overlay(QWidget):
    """Transparent chrome drawn above the GL surface.

    A separate widget rather than QPainter calls inside paintGL: the two
    cannot share one paint device, and keeping them apart also matches
    how the original layers its manipulators over the 3D view.
    """

    def __init__(self, stage: "Stage"):
        super().__init__(stage)
        self.stage = stage
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(stage.rect())

    @property
    def scene(self):
        return self.stage.scene

    @property
    def editor(self):
        return self.stage.editor

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_overlay(painter)
        painter.end()

    def _draw_overlay(self, painter: QPainter) -> None:
        if self.scene.camera.mode == "2d":
            self._draw_canvas_border(painter)
        self._draw_canvas_orbs(painter)
        self.editor.paint_overlay(painter, self.stage)
        self._draw_selection(painter)
        self._draw_gizmo(painter)
        self._draw_brush_cursor(painter)

    def _draw_canvas_border(self, painter: QPainter) -> None:
        corners = [
            self.stage.canvas_to_screen(0, 0),
            self.stage.canvas_to_screen(self.scene.canvas.width, 0),
            self.stage.canvas_to_screen(self.scene.canvas.width, self.scene.canvas.height),
            self.stage.canvas_to_screen(0, self.scene.canvas.height),
        ]
        if any(c is None for c in corners):
            return
        painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF(corners))

    def _draw_canvas_orbs(self, painter: QPainter) -> None:
        if not self.editor.shows_canvas_orbs():
            return
        painter.setPen(QPen(ANCHOR_EDGE, 1.4))
        painter.setBrush(ANCHOR_FILL)
        for _, (hx, hy) in self.editor.canvas_resize_handles().items():
            at = self.stage.canvas_to_screen(hx, hy)
            if at is None:
                continue
            painter.drawEllipse(at, 7.0, 7.0)

    def _draw_selection(self, painter: QPainter) -> None:
        stage = self.editor.magic_stage()
        if stage == "box":
            self._draw_selection_box(painter, self.editor.magic.box, dim=True)
            return
        if self.editor.crop_box is not None:
            self._draw_selection_box(painter, self.editor.crop_box, dim=True)
            return
        if stage == "refine":
            self._dim_around_cutout(painter)
            self._draw_magic_stroke(painter)
            return
        band = self.editor.selection_preview()
        if band is not None:
            self._draw_selection_box(painter, band, dim=True)
            return

        selection = self.editor.selection
        if selection is None or selection.is_empty():
            return
        frame = self.editor.selection_frame()
        if frame is None:
            return
        x0, y0, x1, y1 = frame
        corners = [
            self.stage.canvas_to_screen(x0, y0),
            self.stage.canvas_to_screen(x1, y0),
            self.stage.canvas_to_screen(x1, y1),
            self.stage.canvas_to_screen(x0, y1),
        ]
        if any(c is None for c in corners):
            return
        polygon = QPolygonF(corners)
        self._draw_box_chrome(painter, polygon, self.editor.selection_handles(), y0)

    def _draw_selection_box(self, painter: QPainter, box, dim: bool) -> None:
        """The rubber band while a selection is being dragged out."""
        from Clay3D.editing import handles_for_box

        x0, y0, x1, y1 = box
        corners = [
            self.stage.canvas_to_screen(x0, y0), self.stage.canvas_to_screen(x1, y0),
            self.stage.canvas_to_screen(x1, y1), self.stage.canvas_to_screen(x0, y1),
        ]
        if any(c is None for c in corners):
            return
        polygon = QPolygonF(corners)
        magic_box = self.editor.magic_stage() == "box"
        cropping = self.editor.crop_box is not None
        if dim and (magic_box or cropping):
            whole = QPainterPath()
            whole.addRect(QRectF(self.rect()))
            keep = QPainterPath()
            keep.addPolygon(polygon)
            painter.fillPath(whole.subtracted(keep), DIM_OUTSIDE)
        if magic_box:
            handles = self.editor.magic_box_handles()
        elif cropping:
            handles = self.editor.crop_handles()
        else:
            handles = handles_for_box(box, self.editor._handle_reach())
        self._draw_box_chrome(painter, polygon, handles, y0)

    def _draw_box_chrome(self, painter: QPainter, polygon: QPolygonF, handles, top: float) -> None:
        painter.setPen(QPen(BOX_LINE, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(polygon)

        painter.setPen(QPen(ANCHOR_EDGE, 1.2))
        for name, (hx, hy) in handles.items():
            at = self.stage.canvas_to_screen(hx, hy)
            if at is None:
                continue
            if name == "Rotate":
                stem = self.stage.canvas_to_screen(hx, top)
                if stem is not None:
                    painter.setPen(QPen(BOX_LINE, 1.2))
                    painter.drawLine(at, stem)
                    painter.setPen(QPen(ANCHOR_EDGE, 1.2))
                painter.setBrush(ANCHOR_FILL)
                painter.drawEllipse(at, 5.5, 5.5)
            else:
                painter.setBrush(ANCHOR_FILL)
                painter.drawEllipse(at, 6.0, 6.0)

    def _dim_around_cutout(self, painter: QPainter) -> None:
        """Refine stage: whole view dimmed, cutout bright with a cyan rim."""
        whole = QPainterPath()
        whole.addRect(QRectF(self.rect()))
        painter.fillPath(whole, DIM_OUTSIDE)
        cutout = self.editor.cutout_overlay()
        if cutout is None:
            return
        image, (cx0, cy0, cx1, cy1) = cutout
        top_left = self.stage.canvas_to_screen(cx0, cy0)
        bottom_right = self.stage.canvas_to_screen(cx1, cy1)
        if top_left is not None and bottom_right is not None:
            painter.drawImage(QRectF(top_left, bottom_right), image)

    def _draw_magic_stroke(self, painter: QPainter) -> None:
        """Add/Remove stroke in progress: white line, dark outline."""
        points = [self.stage.canvas_to_screen(x, y) for x, y in self.editor._stroke_points]
        if len(points) < 2 or any(p is None for p in points):
            return
        line = QPolygonF(points)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for colour, width in ((STROKE_OUTER, 6.0), (STROKE_INNER, 3.0)):
            painter.setPen(QPen(colour, width, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPolyline(line)

    def _draw_gizmo(self, painter: QPainter) -> None:
        obj = self.scene.selected()
        if obj is None or not self.editor.shows_gizmo():
            return
        frame = gizmo.frame_for(obj, self.scene.camera, self.stage.width(), self.stage.height())
        if frame is None:
            return
        painter.setPen(QPen(FRAME_LINE, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(frame.left, frame.top, frame.width, frame.height))

        # Scale anchors are small squares in the original, not dots.
        half = ANCHOR_SIZE / 2
        painter.setPen(QPen(ANCHOR_EDGE, 1.2))
        painter.setBrush(ANCHOR_FILL)
        for name in gizmo.CORNERS + gizmo.EDGES:
            x, y = frame.anchor(name)
            painter.drawRect(QRectF(x - half, y - half, ANCHOR_SIZE, ANCHOR_SIZE))

        # Four round buttons on short stems: three rotations and a slide.
        for name in gizmo.BUTTONS:
            x, y = frame.anchor(name)
            painter.setPen(QPen(FRAME_LINE, 1.4))
            painter.drawLine(QPointF(x, y), QPointF(*_stem_root(frame, name)))
            painter.setPen(QPen(BUTTON_EDGE, 1.3))
            painter.setBrush(BUTTON_FILL)
            painter.drawEllipse(QPointF(x, y), BUTTON_RADIUS, BUTTON_RADIUS)
            _draw_button_icon(painter, name, x, y)

    def _draw_brush_cursor(self, painter: QPainter) -> None:
        if self.stage._cursor_at is None or not self.editor.shows_brush_cursor():
            return
        if self.stage.canvas_point(self.stage._cursor_at) is None:
            return
        radius = self.editor.brush_radius() * self.stage.canvas_scale()
        if radius < 2.0:
            return
        painter.setPen(QPen(CURSOR_COLOR, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.stage._cursor_at, radius, radius)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1.0))
        painter.drawEllipse(self.stage._cursor_at, radius + 1, radius + 1)


def _stem_root(frame, name: str) -> tuple[float, float]:
    """Where a manipulator button's stem meets the frame."""
    cx, cy = frame.centre
    return {
        "RotateZ": (cx, frame.top),
        "RotateX": (cx, frame.bottom),
        "RotateY": (frame.right, cy),
        "SlideZ": (frame.left, cy),
    }[name]


def _draw_button_icon(painter: QPainter, name: str, x: float, y: float) -> None:
    """Line art inside a manipulator button, following the original's."""
    painter.setPen(QPen(BUTTON_ICON, 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    r = BUTTON_RADIUS * 0.55
    if name == "SlideZ":
        # A tapered slab with a double-headed arrow through it.
        painter.drawPolygon(QPolygonF([
            QPointF(x - r * 0.9, y + r * 0.7), QPointF(x - r * 0.5, y - r * 0.7),
            QPointF(x + r * 0.5, y - r * 0.7), QPointF(x + r * 0.9, y + r * 0.7),
        ]))
        painter.drawLine(QPointF(x, y - r * 0.55), QPointF(x, y + r * 0.55))
        for tip, back in ((y - r * 0.75, y - r * 0.35), (y + r * 0.75, y + r * 0.35)):
            painter.drawLine(QPointF(x, tip), QPointF(x - r * 0.25, back))
            painter.drawLine(QPointF(x, tip), QPointF(x + r * 0.25, back))
        return

    start, sweep = {"RotateZ": (40, 280), "RotateY": (110, 250), "RotateX": (200, 250)}[name]
    painter.drawArc(QRectF(x - r, y - r, r * 2, r * 2), start * 16, sweep * 16)
    painter.setBrush(BUTTON_ICON)
    painter.setPen(Qt.PenStyle.NoPen)
    angle = math.radians(start + sweep)
    painter.drawEllipse(QPointF(x + r * math.cos(angle), y - r * math.sin(angle)), 1.8, 1.8)
