"""Camera matrices. 2d = ortho on paper; orbit = perspective."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from Clay3D.tuning import (
    CAMERA_FIELD_OF_VIEW,
    CAMERA_START_DISTANCE,
    CAMERA_START_PITCH,
)

# How tall the paper stands in the scene, in world units. The canvas has
# a fixed size in the world and its pixel density follows from its
# resolution - not the other way round. Tying world size to pixel count
# would make an inserted cube a tenth the relative size on a 4000px
# canvas that it is on a 400px one, which is not how the original behaves.
CANVAS_WORLD_HEIGHT = 6.4

MIN_ZOOM = 0.1
MAX_ZOOM = 8.0
MIN_DISTANCE = 1.5
MAX_DISTANCE = 40.0
MAX_PITCH = math.radians(88.0)


@dataclass
class Camera:
    mode: str = "2d"
    yaw: float = 0.0
    pitch: float = CAMERA_START_PITCH
    distance: float = CAMERA_START_DISTANCE
    target: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    zoom: float = 1.0
    pan: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    fov_degrees: float = CAMERA_FIELD_OF_VIEW
    near: float = 0.05
    far: float = 200.0
    # The original offers "Show perspective" and announces "Perspective
    # view on" / "Orthographic view on", so the orbit view does both.
    perspective: bool = True

    def copy(self) -> Camera:
        return Camera(
            mode=self.mode,
            yaw=self.yaw,
            pitch=self.pitch,
            distance=self.distance,
            target=self.target.copy(),
            zoom=self.zoom,
            pan=self.pan.copy(),
            fov_degrees=self.fov_degrees,
            perspective=self.perspective,
        )

    def reset(self) -> None:
        self.yaw = 0.0
        self.pitch = CAMERA_START_PITCH
        self.distance = CAMERA_START_DISTANCE
        self.target = np.zeros(3, dtype=np.float64)
        self.zoom = 1.0
        self.pan = np.zeros(2, dtype=np.float64)

    def orbit(self, dyaw: float, dpitch: float) -> None:
        self.yaw += dyaw
        self.pitch = max(-MAX_PITCH, min(MAX_PITCH, self.pitch + dpitch))

    def dolly(self, factor: float) -> None:
        if self.mode == "2d":
            self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        else:
            self.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, self.distance / factor))

    def eye(self) -> np.ndarray:
        if self.mode == "2d":
            return self.target + np.array([0.0, 0.0, self.distance])
        return self.target + self.distance * np.array(
            [
                math.cos(self.pitch) * math.sin(self.yaw),
                math.sin(self.pitch),
                math.cos(self.pitch) * math.cos(self.yaw),
            ]
        )

    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Right, up and forward unit vectors, in world space."""
        eye = self.eye()
        forward = _normalize(self.target - eye)
        world_up = np.array([0.0, 1.0, 0.0])
        if abs(float(np.dot(forward, world_up))) > 0.999:
            world_up = np.array([0.0, 0.0, 1.0])
        right = _normalize(np.cross(forward, world_up))
        up = np.cross(right, forward)
        return right, up, forward

    def view_matrix(self) -> np.ndarray:
        eye = self.eye()
        right, up, forward = self.basis()
        m = np.eye(4)
        m[0, :3] = right
        m[1, :3] = up
        m[2, :3] = -forward
        m[0, 3] = -float(np.dot(right, eye))
        m[1, 3] = -float(np.dot(up, eye))
        m[2, 3] = float(np.dot(forward, eye))
        return m

    def ortho_half_height(self) -> float:
        return (self.distance * 0.25) / self.zoom

    def set_perspective(self, on: bool) -> None:
        self.perspective = bool(on)

    def projection_matrix(self, width: int, height: int) -> np.ndarray:
        aspect = max(width, 1) / max(height, 1)
        if self.mode == "2d" or not self.perspective:
            half_h = self.ortho_half_height()
            half_w = half_h * aspect
            return _orthographic(-half_w, half_w, -half_h, half_h, self.near, self.far)
        f = 1.0 / math.tan(math.radians(self.fov_degrees) / 2.0)
        m = np.zeros((4, 4))
        m[0, 0] = f / aspect
        m[1, 1] = f
        m[2, 2] = (self.far + self.near) / (self.near - self.far)
        m[2, 3] = (2 * self.far * self.near) / (self.near - self.far)
        m[3, 2] = -1.0
        return m

    def view_projection(self, width: int, height: int) -> np.ndarray:
        return self.projection_matrix(width, height) @ self.view_matrix()

    def ray(self, sx: float, sy: float, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
        """A world-space ray through a screen pixel, as (origin, direction)."""
        ndc_x = (2.0 * sx / max(width, 1)) - 1.0
        ndc_y = 1.0 - (2.0 * sy / max(height, 1))
        right, up, forward = self.basis()
        aspect = max(width, 1) / max(height, 1)
        if self.mode == "2d" or not self.perspective:
            half_h = self.ortho_half_height()
            origin = (
                self.eye() + right * (ndc_x * half_h * aspect) + up * (ndc_y * half_h)
            )
            return origin, forward
        half_h = math.tan(math.radians(self.fov_degrees) / 2.0)
        direction = _normalize(
            forward + right * (ndc_x * half_h * aspect) + up * (ndc_y * half_h)
        )
        return self.eye(), direction

    def world_per_pixel(self, depth: float, width: int, height: int) -> float:
        """How far one screen pixel reaches in world units at some depth."""
        if self.mode == "2d" or not self.perspective:
            return (2.0 * self.ortho_half_height()) / max(height, 1)
        half_h = math.tan(math.radians(self.fov_degrees) / 2.0)
        return (2.0 * half_h * max(depth, 1e-3)) / max(height, 1)

    def pan_by(self, dx_pixels: float, dy_pixels: float, width: int, height: int) -> None:
        """Slide the view by a screen-space drag."""
        scale = self.world_per_pixel(self.distance, width, height)
        right, up, _ = self.basis()
        shift = right * (-dx_pixels * scale) + up * (dy_pixels * scale)
        self.target = self.target + shift


def _orthographic(
    left: float, right: float, bottom: float, top: float, near: float, far: float
) -> np.ndarray:
    m = np.eye(4)
    m[0, 0] = 2.0 / (right - left)
    m[1, 1] = 2.0 / (top - bottom)
    m[2, 2] = -2.0 / (far - near)
    m[0, 3] = -(right + left) / (right - left)
    m[1, 3] = -(top + bottom) / (top - bottom)
    m[2, 3] = -(far + near) / (far - near)
    return m


def _normalize(v: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(v))
    if length < 1e-12:
        return np.array([0.0, 0.0, -1.0])
    return v / length


def project(point: np.ndarray, view_projection: np.ndarray, width: int, height: int):
    """World point to screen pixels, or None if it is behind the camera."""
    clip = view_projection @ np.array([point[0], point[1], point[2], 1.0])
    if clip[3] <= 1e-6:
        return None
    ndc = clip[:3] / clip[3]
    return (
        (ndc[0] * 0.5 + 0.5) * width,
        (0.5 - ndc[1] * 0.5) * height,
        float(ndc[2]),
    )
