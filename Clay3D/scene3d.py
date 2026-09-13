"""Scene graph: canvas + triangle meshes. Primitives from Shape3dType minus people/animals."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from Clay3D.camera import CANVAS_WORLD_HEIGHT, MAX_DISTANCE, MIN_DISTANCE, Camera
from Clay3D.tuning import (
    CAPSULE_RADIUS,
    PIPE_INNER_RADIUS,
    TORUS_MAJOR_RADIUS,
    TORUS_MINOR_RADIUS,
)

Color = tuple[int, int, int, int]

# Name, label. Order matches the 3D shapes panel in the original.
SHAPE3D_TYPES = (
    ("cube", "Cube"),
    ("sphere", "Sphere"),
    ("cylinder", "Cylinder"),
    ("capsule", "Capsule"),
    ("torus", "Torus"),
    ("cone", "Cone"),
    ("pipe", "Pipe"),
    ("hemisphere", "Hemisphere"),
    ("quarter_torus", "Quarter torus"),
    ("pyramid", "Pyramid"),
)

DEFAULT_COLOR: Color = (216, 212, 206, 255)


@dataclass
class Mesh:
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray

    @property
    def triangle_count(self) -> int:
        return len(self.positions) // 3

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if len(self.positions) == 0:
            return np.zeros(3), np.zeros(3)
        return self.positions.min(axis=0), self.positions.max(axis=0)

    def copy(self) -> Mesh:
        return Mesh(self.positions.copy(), self.normals.copy(), self.uvs.copy())

    def interleaved(self) -> np.ndarray:
        """Positions, normals and UVs packed for a single GL buffer."""
        return np.hstack([self.positions, self.normals, self.uvs]).astype(np.float32)

    def raycast(self, origin: np.ndarray, direction: np.ndarray):
        """Nearest hit in mesh space, as (distance, uv, normal), or None.

        Moller-Trumbore, run over every triangle at once.
        """
        tris = self.positions.reshape(-1, 3, 3).astype(np.float64)
        v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
        edge1 = v1 - v0
        edge2 = v2 - v0
        pvec = np.cross(direction, edge2)
        det = np.einsum("ij,ij->i", edge1, pvec)
        usable = np.abs(det) > 1e-12
        if not usable.any():
            return None
        inv_det = np.zeros_like(det)
        inv_det[usable] = 1.0 / det[usable]
        tvec = origin - v0
        u = np.einsum("ij,ij->i", tvec, pvec) * inv_det
        qvec = np.cross(tvec, edge1)
        v = (qvec @ direction) * inv_det
        t = np.einsum("ij,ij->i", edge2, qvec) * inv_det
        hit = usable & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1.0 + 1e-9) & (t > 1e-6)
        if not hit.any():
            return None
        indices = np.flatnonzero(hit)
        nearest = indices[np.argmin(t[indices])]
        bary = np.array([1.0 - u[nearest] - v[nearest], u[nearest], v[nearest]])
        corner_uvs = self.uvs[nearest * 3 : nearest * 3 + 3]
        corner_normals = self.normals[nearest * 3 : nearest * 3 + 3]
        return (
            float(t[nearest]),
            bary @ corner_uvs,
            _normalize(bary @ corner_normals),
        )


def merge(*meshes: Mesh) -> Mesh:
    return Mesh(
        np.vstack([m.positions for m in meshes]),
        np.vstack([m.normals for m in meshes]),
        np.vstack([m.uvs for m in meshes]),
    )


# ---- mesh construction --------------------------------------------------


def surface(sample, nu: int, nv: int) -> Mesh:
    """A parametric patch, triangulated over a (nu x nv) grid.

    `sample(u, v)` returns (position, normal) for u and v in 0..1. Both
    arrive as 2D arrays so the whole grid is evaluated in one go.
    """
    u = np.linspace(0.0, 1.0, nu + 1)
    v = np.linspace(0.0, 1.0, nv + 1)
    grid_u, grid_v = np.meshgrid(u, v, indexing="ij")
    position, normal = sample(grid_u, grid_v)
    uv = np.stack([grid_u, grid_v], axis=-1)
    return _grid_to_soup(position, normal, uv)


def _grid_to_soup(position: np.ndarray, normal: np.ndarray, uv: np.ndarray) -> Mesh:
    """Turn an (nu+1, nv+1) grid of corners into two triangles per cell."""
    a = (slice(0, -1), slice(0, -1))
    b = (slice(1, None), slice(0, -1))
    c = (slice(1, None), slice(1, None))
    d = (slice(0, -1), slice(1, None))
    corners = [a, b, c, a, c, d]
    positions = np.stack([position[s].reshape(-1, 3) for s in corners], axis=1)
    normals = np.stack([normal[s].reshape(-1, 3) for s in corners], axis=1)
    uvs = np.stack([uv[s].reshape(-1, 2) for s in corners], axis=1)
    return Mesh(
        positions.reshape(-1, 3).astype(np.float32),
        normals.reshape(-1, 3).astype(np.float32),
        uvs.reshape(-1, 2).astype(np.float32),
    )


def quad(p0, p1, p2, p3, uv_scale: float = 1.0) -> Mesh:
    """A flat four-sided face, with one normal shared by both triangles."""
    p0, p1, p2, p3 = (np.asarray(p, dtype=np.float64) for p in (p0, p1, p2, p3))
    normal = _normalize(np.cross(p1 - p0, p3 - p0))
    positions = np.array([p0, p1, p2, p0, p2, p3], dtype=np.float32)
    normals = np.tile(normal, (6, 1)).astype(np.float32)
    corner_uv = np.array([[0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1]], dtype=np.float32)
    return Mesh(positions, normals, corner_uv * uv_scale)


def _disc(radius: float, y: float, slices: int, facing: float, inner: float = 0.0) -> Mesh:
    """A flat cap, or an annulus when `inner` is non-zero."""

    def sample(u, v):
        theta = 2 * math.pi * u
        r = inner + (radius - inner) * v
        position = np.stack([r * np.cos(theta), np.full_like(u, y), r * np.sin(theta)], axis=-1)
        normal = np.zeros_like(position)
        normal[..., 1] = facing
        return position, normal

    mesh = surface(sample, slices, 1 if inner == 0.0 else 2)
    return mesh if facing > 0 else _flip(mesh)


def _flip(mesh: Mesh) -> Mesh:
    """Reverse winding so a surface faces the other way."""
    positions = mesh.positions.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
    normals = mesh.normals.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
    uvs = mesh.uvs.reshape(-1, 3, 2)[:, ::-1].reshape(-1, 2)
    return Mesh(positions, normals, uvs)


def _normalize(v: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(v))
    return v / length if length > 1e-12 else np.array([0.0, 1.0, 0.0])


# ---- the primitive catalog ----------------------------------------------

R = 0.5  # every primitive fits inside a unit cube centred on the origin


def cube_mesh() -> Mesh:
    s = R
    return merge(
        quad((-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)),
        quad((s, -s, -s), (-s, -s, -s), (-s, s, -s), (s, s, -s)),
        quad((s, -s, s), (s, -s, -s), (s, s, -s), (s, s, s)),
        quad((-s, -s, -s), (-s, -s, s), (-s, s, s), (-s, s, -s)),
        quad((-s, s, s), (s, s, s), (s, s, -s), (-s, s, -s)),
        quad((-s, -s, -s), (s, -s, -s), (s, -s, s), (-s, -s, s)),
    )


def sphere_mesh(slices: int = 48, stacks: int = 32) -> Mesh:
    def sample(u, v):
        theta = 2 * math.pi * u
        phi = math.pi * v
        normal = np.stack(
            [np.sin(phi) * np.cos(theta), np.cos(phi), np.sin(phi) * np.sin(theta)], axis=-1
        )
        return normal * R, normal

    return surface(sample, slices, stacks)


def cylinder_mesh(slices: int = 48) -> Mesh:
    def side(u, v):
        theta = 2 * math.pi * u
        normal = np.stack([np.cos(theta), np.zeros_like(u), np.sin(theta)], axis=-1)
        position = normal * R
        position[..., 1] = v * 2 * R - R
        return position, normal

    return merge(
        surface(side, slices, 1),
        _disc(R, R, slices, 1.0),
        _disc(R, -R, slices, -1.0),
    )


def capsule_mesh(slices: int = 48, stacks: int = 16) -> Mesh:
    radius = CAPSULE_RADIUS
    half = R - radius

    def side(u, v):
        theta = 2 * math.pi * u
        normal = np.stack([np.cos(theta), np.zeros_like(u), np.sin(theta)], axis=-1)
        position = normal * radius
        position[..., 1] = v * 2 * half - half
        return position, normal

    def dome(sign: float):
        def sample(u, v):
            theta = 2 * math.pi * u
            phi = (math.pi / 2) * v
            normal = np.stack(
                [np.cos(phi) * np.cos(theta), sign * np.sin(phi), np.cos(phi) * np.sin(theta)],
                axis=-1,
            )
            position = normal * radius
            position[..., 1] += sign * half
            return position, normal

        return sample

    top = surface(dome(1.0), slices, stacks)
    bottom = _flip(surface(dome(-1.0), slices, stacks))
    return merge(surface(side, slices, 1), top, bottom)


def torus_mesh(slices: int = 56, rings: int = 28, sweep: float = 1.0) -> Mesh:
    major = TORUS_MAJOR_RADIUS
    minor = TORUS_MINOR_RADIUS

    def sample(u, v):
        theta = 2 * math.pi * u * sweep
        phi = 2 * math.pi * v
        normal = np.stack(
            [np.cos(phi) * np.cos(theta), np.sin(phi), np.cos(phi) * np.sin(theta)], axis=-1
        )
        position = np.stack(
            [
                (major + minor * np.cos(phi)) * np.cos(theta),
                minor * np.sin(phi),
                (major + minor * np.cos(phi)) * np.sin(theta),
            ],
            axis=-1,
        )
        return position, normal

    return surface(sample, max(4, int(slices * sweep)), rings)


def quarter_torus_mesh() -> Mesh:
    body = torus_mesh(sweep=0.25)
    elbow = merge(body, _torus_end_cap(0.0, -1.0), _torus_end_cap(math.pi / 2, 1.0))
    return recentre(elbow)


def recentre(mesh: Mesh) -> Mesh:
    """Slide a mesh so its bounding box is centred on the origin."""
    low, high = mesh.bounds()
    mesh.positions = (mesh.positions - (low + high) / 2.0).astype(np.float32)
    return mesh


def _torus_end_cap(theta: float, facing: float) -> Mesh:
    """A flat disc closing one cut end of a swept torus."""
    major, minor = TORUS_MAJOR_RADIUS, TORUS_MINOR_RADIUS
    axis = np.array([math.cos(theta), 0.0, math.sin(theta)])
    tangent = np.array([-math.sin(theta), 0.0, math.cos(theta)]) * facing

    def sample(u, v):
        phi = 2 * math.pi * u
        r = minor * v
        centre = axis * major
        offset = axis[None, None, :] * (r * np.cos(phi))[..., None]
        offset = offset + np.array([0.0, 1.0, 0.0])[None, None, :] * (r * np.sin(phi))[..., None]
        position = centre[None, None, :] + offset
        normal = np.broadcast_to(tangent, position.shape).copy()
        return position, normal

    return surface(sample, 24, 2)


def cone_mesh(slices: int = 48) -> Mesh:
    slant = math.atan2(R, 2 * R)

    def side(u, v):
        theta = 2 * math.pi * u
        radius = R * (1.0 - v)
        position = np.stack(
            [radius * np.cos(theta), v * 2 * R - R, radius * np.sin(theta)], axis=-1
        )
        normal = np.stack(
            [
                np.cos(slant) * np.cos(theta),
                np.full_like(u, math.sin(slant)),
                np.cos(slant) * np.sin(theta),
            ],
            axis=-1,
        )
        return position, normal

    return merge(surface(side, slices, 1), _disc(R, -R, slices, -1.0))


def pipe_mesh(slices: int = 48) -> Mesh:
    inner = PIPE_INNER_RADIUS

    def wall(radius: float, outward: float):
        def sample(u, v):
            theta = 2 * math.pi * u
            normal = np.stack([np.cos(theta), np.zeros_like(u), np.sin(theta)], axis=-1)
            position = normal * radius
            position[..., 1] = v * 2 * R - R
            return position, normal * outward

        mesh = surface(sample, slices, 1)
        return mesh if outward > 0 else _flip(mesh)

    return merge(
        wall(R, 1.0),
        wall(inner, -1.0),
        _disc(R, R, slices, 1.0, inner=inner),
        _disc(R, -R, slices, -1.0, inner=inner),
    )


def hemisphere_mesh(slices: int = 48, stacks: int = 20) -> Mesh:
    flat_y = -R / 2  # a dome of radius R is R tall, so centre it on half that

    def sample(u, v):
        theta = 2 * math.pi * u
        phi = (math.pi / 2) * v
        normal = np.stack(
            [np.cos(phi) * np.cos(theta), np.sin(phi), np.cos(phi) * np.sin(theta)], axis=-1
        )
        position = normal * R
        position[..., 1] += flat_y
        return position, normal

    return merge(surface(sample, slices, stacks), _disc(R, flat_y, slices, -1.0))


def pyramid_mesh() -> Mesh:
    s = R
    apex = (0.0, s, 0.0)
    base = [(-s, -s, s), (s, -s, s), (s, -s, -s), (-s, -s, -s)]
    faces = [
        _triangle(base[i], base[(i + 1) % 4], apex) for i in range(4)
    ]
    return merge(quad(base[3], base[2], base[1], base[0]), *faces)


def _triangle(p0, p1, p2) -> Mesh:
    p0, p1, p2 = (np.asarray(p, dtype=np.float64) for p in (p0, p1, p2))
    normal = _normalize(np.cross(p1 - p0, p2 - p0))
    return Mesh(
        np.array([p0, p1, p2], dtype=np.float32),
        np.tile(normal, (3, 1)).astype(np.float32),
        np.array([[0, 0], [1, 0], [0.5, 1]], dtype=np.float32),
    )


BUILDERS = {
    "cube": cube_mesh,
    "sphere": sphere_mesh,
    "cylinder": cylinder_mesh,
    "capsule": capsule_mesh,
    "torus": torus_mesh,
    "cone": cone_mesh,
    "pipe": pipe_mesh,
    "hemisphere": hemisphere_mesh,
    "quarter_torus": quarter_torus_mesh,
    "pyramid": pyramid_mesh,
}


def build(kind: str) -> Mesh:
    if kind not in BUILDERS:
        raise ValueError(f"unknown 3D shape: {kind}")
    return BUILDERS[kind]()


# ---- objects ------------------------------------------------------------


@dataclass
class Transform:
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rotation: np.ndarray = field(default_factory=lambda: np.zeros(3))
    scale: np.ndarray = field(default_factory=lambda: np.ones(3))

    def copy(self) -> Transform:
        return Transform(self.position.copy(), self.rotation.copy(), self.scale.copy())

    def matrix(self) -> np.ndarray:
        m = np.eye(4)
        m[:3, :3] = rotation_matrix(*self.rotation) * self.scale
        m[:3, 3] = self.position
        return m

    def inverse_matrix(self) -> np.ndarray:
        """Undoes matrix(): scale back down, unrotate, then untranslate."""
        safe_scale = np.where(np.abs(self.scale) < 1e-9, 1e-9, self.scale)
        linear = rotation_matrix(*self.rotation).T / safe_scale[:, None]
        m = np.eye(4)
        m[:3, :3] = linear
        m[:3, 3] = -linear @ self.position
        return m

    def normal_matrix(self) -> np.ndarray:
        safe_scale = np.where(np.abs(self.scale) < 1e-9, 1e-9, self.scale)
        return rotation_matrix(*self.rotation) / safe_scale


def rotation_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=float)
    y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=float)
    z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=float)
    return z @ y @ x


@dataclass
class SceneObject:
    kind: str
    mesh: Mesh
    transform: Transform = field(default_factory=Transform)
    color: Color = DEFAULT_COLOR
    smoothness: float = 0.25
    metallic: float = 0.0
    texture: np.ndarray | None = None
    revision: int = 0

    def copy(self) -> SceneObject:
        return SceneObject(
            kind=self.kind,
            mesh=self.mesh.copy(),
            transform=self.transform.copy(),
            color=self.color,
            smoothness=self.smoothness,
            metallic=self.metallic,
            texture=None if self.texture is None else self.texture.copy(),
        )

    def move(self, dx: float, dy: float, dz: float) -> None:
        self.transform.position = self.transform.position + np.array([dx, dy, dz], dtype=float)

    def rotate(self, rx: float, ry: float, rz: float) -> None:
        self.transform.rotation = self.transform.rotation + np.array([rx, ry, rz], dtype=float)

    def scale_by(self, sx: float, sy: float, sz: float) -> None:
        self.transform.scale = self.transform.scale * np.array([sx, sy, sz], dtype=float)

    def world_centre(self) -> np.ndarray:
        low, high = self.mesh.bounds()
        centre = (low + high) / 2.0
        return (self.transform.matrix() @ np.append(centre, 1.0))[:3]

    def world_radius(self) -> float:
        low, high = self.mesh.bounds()
        extent = (high - low) / 2.0 * np.abs(self.transform.scale)
        return float(np.linalg.norm(extent))

    def ensure_texture(self, size: int = 512) -> np.ndarray:
        """The paint layer for this object, created blank on first use."""
        if self.texture is None:
            self.texture = np.zeros((size, size, 4), dtype=np.uint8)
        return self.texture

    def raycast(self, origin: np.ndarray, direction: np.ndarray):
        """World-space ray against this object, as (distance, uv, normal)."""
        inverse = self.transform.inverse_matrix()
        local_origin = (inverse @ np.append(origin, 1.0))[:3]
        local_direction = inverse[:3, :3] @ direction
        length = float(np.linalg.norm(local_direction))
        if length < 1e-12:
            return None
        hit = self.mesh.raycast(local_origin, local_direction / length)
        if hit is None:
            return None
        local_distance, uv, local_normal = hit
        world_normal = _normalize(self.transform.normal_matrix() @ local_normal)
        return local_distance / length, uv, world_normal


class Scene:
    """The canvas and the 3D objects, sharing one space and one camera."""

    def __init__(self, canvas=None) -> None:
        from Clay3D.canvas2d import Canvas

        self.canvas = canvas if canvas is not None else Canvas(1152, 768)
        self.objects: list[SceneObject] = []
        self.selected_index = -1
        self.camera = Camera()
        self.show_canvas = True
        self.show_grid = True
        self.effect = "none"
        self.light_rotation = 0.0
        self.canvas_revision = 0

    # -- canvas placement -------------------------------------------------

    def pixels_per_unit(self) -> float:
        """Canvas pixels per world unit, for this canvas's resolution.

        Derived, not fixed: the paper is always the same size in the
        scene, so a denser canvas simply has finer pixels.
        """
        return self.canvas.height / CANVAS_WORLD_HEIGHT

    def canvas_extent(self) -> tuple[float, float]:
        half_h = CANVAS_WORLD_HEIGHT / 2.0
        aspect = self.canvas.width / max(self.canvas.height, 1)
        return (half_h * aspect, half_h)

    def canvas_to_world(self, x: float, y: float) -> np.ndarray:
        half_w, half_h = self.canvas_extent()
        scale = self.pixels_per_unit()
        return np.array([x / scale - half_w, half_h - y / scale, 0.0])

    def world_to_canvas(self, point: np.ndarray) -> tuple[float, float]:
        half_w, half_h = self.canvas_extent()
        scale = self.pixels_per_unit()
        return ((float(point[0]) + half_w) * scale, (half_h - float(point[1])) * scale)

    def canvas_contains(self, x: float, y: float) -> bool:
        """Is this canvas coordinate actually on the paper?"""
        return 0 <= x < self.canvas.width and 0 <= y < self.canvas.height

    def canvas_hit(self, origin: np.ndarray, direction: np.ndarray):
        """Where a ray crosses the canvas plane, in canvas pixels.

        The plane is unbounded, so this can land outside the paper. That
        is wanted while dragging - a shape may be pulled past the edge -
        so callers that need a point *on* the paper check with
        `canvas_contains` first.
        """
        if abs(direction[2]) < 1e-9:
            return None
        t = -origin[2] / direction[2]
        if t <= 0:
            return None
        return self.world_to_canvas(origin + t * direction)

    # -- objects ----------------------------------------------------------

    def insert(self, kind: str, at: np.ndarray | None = None) -> SceneObject:
        obj = SceneObject(kind=kind, mesh=build(kind))
        obj.transform.position = (
            np.array([0.0, 0.0, 0.6]) if at is None else np.asarray(at, dtype=float)
        )
        self.objects.append(obj)
        self.selected_index = len(self.objects) - 1
        return obj

    def add(self, obj: SceneObject) -> SceneObject:
        self.objects.append(obj)
        self.selected_index = len(self.objects) - 1
        return obj

    def selected(self) -> SceneObject | None:
        if 0 <= self.selected_index < len(self.objects):
            return self.objects[self.selected_index]
        return None

    def select(self, obj: SceneObject | None) -> None:
        self.selected_index = -1 if obj is None else self.objects.index(obj)

    def remove_selected(self) -> None:
        if self.selected() is None:
            return
        del self.objects[self.selected_index]
        self.selected_index = min(self.selected_index, len(self.objects) - 1)

    def pick(self, origin: np.ndarray, direction: np.ndarray):
        """Nearest object along a ray, as (object, distance, uv, normal)."""
        best = None
        for obj in self.objects:
            hit = obj.raycast(origin, direction)
            if hit is None:
                continue
            if best is None or hit[0] < best[1]:
                best = (obj, hit[0], hit[1], hit[2])
        return best

    def set_view(self, mode: str) -> None:
        if mode not in ("2d", "orbit"):
            raise ValueError(f"unknown view: {mode}")
        self.camera.mode = mode
        if mode == "2d":
            self.camera.yaw = 0.0
            self.camera.pitch = 0.0

    @property
    def view_mode(self) -> str:
        return self.camera.mode

    def frame_scene(self) -> None:
        """Back the orbit camera off until canvas and objects both fit."""
        half_w, half_h = self.canvas_extent()
        reach = math.hypot(half_w, half_h) if self.show_canvas else 1.0
        for obj in self.objects:
            reach = max(reach, float(np.linalg.norm(obj.world_centre())) + obj.world_radius())
        fov = math.radians(self.camera.fov_degrees) / 2.0
        self.camera.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, reach / math.sin(fov) * 1.05))
        self.camera.target = np.zeros(3)

    MARGIN = 0.88  # leave a little stage visible around the paper

    def frame_canvas(self, width: int, height: int) -> None:
        """Set the 2D zoom so the whole canvas is comfortably in view."""
        if width <= 0 or height <= 0:
            return
        half_w, half_h = self.canvas_extent()
        aspect = width / height
        # The view must be at least this tall to show the whole canvas.
        needed = max(half_h, half_w / aspect) / self.MARGIN
        self.camera.target = np.zeros(3)
        self.camera.zoom = 1.0
        self.camera.zoom = self.camera.ortho_half_height() / needed
