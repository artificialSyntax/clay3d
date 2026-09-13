"""Screen-space 3D frame + hit tests. No Qt, no GL."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from Clay3D.camera import project

HANDLE_RADIUS = 7.0
ROTATE_OFFSET = 30.0
FRAME_PADDING = 14.0

# Corner and edge anchors.
CORNERS = ("TopLeft", "TopRight", "BottomRight", "BottomLeft")
EDGES = ("Top", "Right", "Bottom", "Left")

# The four round buttons the original hangs off the frame, with the
# captions it ships for them. Top rotates in plane, right spins about Y,
# bottom flips about X, and left slides the object through the scene.
BUTTONS = ("RotateZ", "RotateY", "RotateX", "SlideZ")
BUTTON_HINTS = {
    "RotateZ": "Rotate on the z-axis",
    "RotateY": "Spin on the y-axis",
    "RotateX": "Flip on the x-axis",
    "SlideZ": "Slide forward and backwards on the z-axis",
}
ROTATORS = ("RotateZ", "RotateY", "RotateX")


@dataclass
class Frame:
    """Where every handle sits on screen for the current selection."""

    left: float
    top: float
    right: float
    bottom: float
    centre_depth: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def anchor(self, name: str) -> tuple[float, float]:
        cx, cy = self.centre
        positions = {
            "TopLeft": (self.left, self.top),
            "TopRight": (self.right, self.top),
            "BottomRight": (self.right, self.bottom),
            "BottomLeft": (self.left, self.bottom),
            "Top": (cx, self.top),
            "Right": (self.right, cy),
            "Bottom": (cx, self.bottom),
            "Left": (self.left, cy),
            "RotateZ": (cx, self.top - ROTATE_OFFSET),
            "RotateY": (self.right + ROTATE_OFFSET, cy),
            "RotateX": (cx, self.bottom + ROTATE_OFFSET),
            "SlideZ": (self.left - ROTATE_OFFSET, cy),
        }
        return positions[name]

    def handles(self) -> list[tuple[str, tuple[float, float]]]:
        return [(name, self.anchor(name)) for name in CORNERS + EDGES + BUTTONS]

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


def frame_for(obj, camera, width: int, height: int) -> Frame | None:
    """Fit a screen-space box around an object's projected corners."""
    low, high = obj.mesh.bounds()
    corners = np.array(
        [[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
    )
    model = obj.transform.matrix()
    world = (model @ np.hstack([corners, np.ones((8, 1))]).T).T[:, :3]
    view_projection = camera.view_projection(width, height)
    points = [project(p, view_projection, width, height) for p in world]
    visible = [p for p in points if p is not None]
    if len(visible) < 4:
        return None
    xs = [p[0] for p in visible]
    ys = [p[1] for p in visible]
    centre = project(obj.world_centre(), view_projection, width, height)
    depth = float(np.linalg.norm(obj.world_centre() - camera.eye()))
    return Frame(
        left=min(xs) - FRAME_PADDING,
        top=min(ys) - FRAME_PADDING,
        right=max(xs) + FRAME_PADDING,
        bottom=max(ys) + FRAME_PADDING,
        centre_depth=depth if centre is not None else depth,
    )


def hit_handle(frame: Frame, x: float, y: float) -> str | None:
    """Which handle, if any, is under the cursor."""
    for name, (hx, hy) in frame.handles():
        if math.hypot(x - hx, y - hy) <= HANDLE_RADIUS + 4.0:
            return name
    if frame.contains(x, y):
        return "Move"
    return None


class Drag:
    """One manipulation in progress, from mouse-down to mouse-up."""

    def __init__(self, obj, handle: str, frame: Frame, camera, start: tuple[float, float]):
        self.obj = obj
        self.handle = handle
        self.frame = frame
        self.camera = camera
        self.start = start
        self.start_position = obj.transform.position.copy()
        self.start_rotation = obj.transform.rotation.copy()
        self.start_scale = obj.transform.scale.copy()
        self.start_angle = _angle_from_centre(frame, start)

    def update(self, x: float, y: float, width: int, height: int, uniform: bool = False) -> None:
        if self.handle == "Move":
            self._move(x, y, width, height)
        elif self.handle == "SlideZ":
            self._slide(y, width, height)
        elif self.handle in ROTATORS:
            self._rotate(x, y)
        else:
            self._scale(x, y, uniform)

    def _slide(self, y: float, width: int, height: int) -> None:
        """Push the object toward or away from the camera."""
        scale = self.camera.world_per_pixel(self.frame.centre_depth, width, height)
        _, _, forward = self.camera.basis()
        self.obj.transform.position = self.start_position + forward * (
            (self.start[1] - y) * scale
        )

    def _move(self, x: float, y: float, width: int, height: int) -> None:
        scale = self.camera.world_per_pixel(self.frame.centre_depth, width, height)
        right, up, _ = self.camera.basis()
        dx = (x - self.start[0]) * scale
        dy = (y - self.start[1]) * scale
        self.obj.transform.position = self.start_position + right * dx - up * dy

    def _rotate(self, x: float, y: float) -> None:
        delta = _angle_from_centre(self.frame, (x, y)) - self.start_angle
        axis = {"RotateX": 0, "RotateY": 1, "RotateZ": 2}[self.handle]
        rotation = self.start_rotation.copy()
        rotation[axis] += delta
        self.obj.transform.rotation = rotation

    def _scale(self, x: float, y: float, uniform: bool) -> None:
        cx, cy = self.frame.centre
        start_dx = max(abs(self.start[0] - cx), 1e-3)
        start_dy = max(abs(self.start[1] - cy), 1e-3)
        factor_x = abs(x - cx) / start_dx
        factor_y = abs(y - cy) / start_dy

        if self.handle in CORNERS or uniform:
            factor = max(0.05, (factor_x + factor_y) / 2)
            factors = np.array([factor, factor, factor])
        elif self.handle in ("Left", "Right"):
            factors = np.array([max(0.05, factor_x), 1.0, 1.0])
        else:
            factors = np.array([1.0, max(0.05, factor_y), 1.0])
        self.obj.transform.scale = self.start_scale * factors


def _angle_from_centre(frame: Frame, point: tuple[float, float]) -> float:
    cx, cy = frame.centre
    return math.atan2(point[1] - cy, point[0] - cx)
