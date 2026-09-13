"""Closed 2D outline → mesh. sharp = prism. soft = distance-field inflate."""

from __future__ import annotations

import math

import numpy as np

from Clay3D.scene3d import Mesh, merge
from Clay3D.tuning import DOODLE_SHARP_THICKNESS, DOODLE_SOFT_THICKNESS

# Working grid resolution along the outline's longer side. Enough for a
# smooth pillow without burying the renderer in triangles.
GRID_STEPS = 84
MAX_OUTLINE_POINTS = 160


def doodle_to_mesh(outline: list[tuple[float, float]], mode: str, scene) -> tuple[Mesh, np.ndarray]:
    """Build the solid for an outline, in canvas pixels.

    Returns the mesh (centred on its own origin) and the world position
    it should sit at, so it stays where it was drawn.
    """
    if mode not in ("soft", "sharp"):
        raise ValueError(f"unknown doodle mode: {mode}")
    ring = _prepare(outline)
    if ring is None:
        return None, None

    grid = _Grid(ring)
    if grid.mask is None:
        return None, None

    thickness = grid.span_pixels * DOODLE_SOFT_THICKNESS
    if mode == "soft":
        depth = grid.distance / max(grid.distance.max(), 1e-6)
        height = thickness * np.sqrt(np.clip(depth, 0.0, 1.0))
    else:
        height = np.full_like(
            grid.distance, grid.span_pixels * DOODLE_SHARP_THICKNESS
        )
    height = height * grid.inside  # zero outside, so the shell closes

    mesh = _shell(grid, height, scene, smooth=(mode == "soft"))
    if mode == "sharp":
        mesh = merge(mesh, _walls(grid, height, scene))

    low, high = mesh.bounds()
    centre = (low + high) / 2.0
    mesh.positions = (mesh.positions - centre).astype(np.float32)
    return mesh, centre


def _prepare(outline: list[tuple[float, float]]) -> np.ndarray | None:
    """Close the ring and thin it out to a manageable number of points."""
    points = np.asarray(outline, dtype=np.float64)
    if len(points) < 3:
        return None
    if np.allclose(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        return None
    if len(points) > MAX_OUTLINE_POINTS:
        keep = np.linspace(0, len(points) - 1, MAX_OUTLINE_POINTS).astype(int)
        points = points[keep]
    span = points.max(axis=0) - points.min(axis=0)
    if span.max() < 4.0:
        return None
    return points


class _Grid:
    """A sampling lattice over the outline's bounding box.

    `inside` marks lattice corners within the outline, `distance` holds
    how far each of those is from the outline, in canvas pixels.
    """

    def __init__(self, ring: np.ndarray):
        low = ring.min(axis=0)
        high = ring.max(axis=0)
        pad = max(high - low) * 0.04 + 2.0
        low -= pad
        high += pad
        self.span_pixels = float(max(high - low))

        steps_x = max(8, int(GRID_STEPS * (high[0] - low[0]) / self.span_pixels))
        steps_y = max(8, int(GRID_STEPS * (high[1] - low[1]) / self.span_pixels))
        self.xs = np.linspace(low[0], high[0], steps_x + 1)
        self.ys = np.linspace(low[1], high[1], steps_y + 1)
        self.grid_x, self.grid_y = np.meshgrid(self.xs, self.ys, indexing="ij")

        self.inside = _points_in_polygon(self.grid_x, self.grid_y, ring).astype(np.float64)
        self.mask = self.inside > 0.5
        if not self.mask.any():
            self.mask = None
            return
        self.distance = _distance_to_ring(self.grid_x, self.grid_y, ring) * self.inside
        # Cells whose four corners are all inside get triangles.
        self.cells = (
            self.mask[:-1, :-1] & self.mask[1:, :-1] & self.mask[1:, 1:] & self.mask[:-1, 1:]
        )


def _shell(grid: _Grid, height: np.ndarray, scene, smooth: bool) -> Mesh:
    """Front and back surfaces of the solid, built off the heightfield."""
    front_pos, front_nrm = _surface_grid(grid, height, scene, sign=1.0, smooth=smooth)
    back_pos, back_nrm = _surface_grid(grid, height, scene, sign=-1.0, smooth=smooth)
    uv = np.stack(
        [
            (grid.grid_x - grid.xs[0]) / max(grid.xs[-1] - grid.xs[0], 1e-6),
            (grid.grid_y - grid.ys[0]) / max(grid.ys[-1] - grid.ys[0], 1e-6),
        ],
        axis=-1,
    )
    front = _cells_to_soup(front_pos, front_nrm, uv, grid.cells, flip=False)
    back = _cells_to_soup(back_pos, back_nrm, uv, grid.cells, flip=True)
    return merge(front, back)


def _surface_grid(grid: _Grid, height: np.ndarray, scene, sign: float, smooth: bool):
    """World positions and normals for one face of the shell."""
    half_w, half_h = scene.canvas_extent()
    scale = scene.pixels_per_unit()
    world_x = grid.grid_x / scale - half_w
    world_y = half_h - grid.grid_y / scale
    world_z = sign * height / scale
    positions = np.stack([world_x, world_y, world_z], axis=-1)

    if not smooth:
        normals = np.zeros_like(positions)
        normals[..., 2] = sign
        return positions, normals

    # Slope of the pillow, so the shading curves instead of stepping.
    step_x = (grid.xs[1] - grid.xs[0]) / scale
    step_y = (grid.ys[1] - grid.ys[0]) / scale
    dz_dx = np.gradient(world_z, step_x, axis=0)
    dz_dy = -np.gradient(world_z, step_y, axis=1)
    # Both faces lean the same way across the pillow; only the z flips.
    normals = np.stack([-dz_dx, -dz_dy, np.ones_like(world_z)], axis=-1) * sign
    lengths = np.linalg.norm(normals, axis=-1, keepdims=True)
    return positions, normals / np.maximum(lengths, 1e-9)


def _cells_to_soup(
    position: np.ndarray, normal: np.ndarray, uv: np.ndarray, cells: np.ndarray, flip: bool
) -> Mesh:
    """Two triangles for every lattice cell that is fully inside."""
    a = (slice(0, -1), slice(0, -1))
    b = (slice(1, None), slice(0, -1))
    c = (slice(1, None), slice(1, None))
    d = (slice(0, -1), slice(1, None))
    order = [a, b, c, a, c, d]
    if flip:
        order = [a, c, b, a, d, c]
    keep = cells.reshape(-1)
    positions = np.stack([position[s].reshape(-1, 3)[keep] for s in order], axis=1)
    normals = np.stack([normal[s].reshape(-1, 3)[keep] for s in order], axis=1)
    uvs = np.stack([uv[s].reshape(-1, 2)[keep] for s in order], axis=1)
    return Mesh(
        positions.reshape(-1, 3).astype(np.float32),
        normals.reshape(-1, 3).astype(np.float32),
        uvs.reshape(-1, 2).astype(np.float32),
    )


def _walls(grid: _Grid, height: np.ndarray, scene) -> Mesh:
    """Vertical sides where a filled cell borders empty space."""
    half_w, half_h = scene.canvas_extent()
    scale = scene.pixels_per_unit()

    def world(ix: int, iy: int, z: float) -> np.ndarray:
        return np.array(
            [
                grid.xs[ix] / scale - half_w,
                half_h - grid.ys[iy] / scale,
                z,
            ]
        )

    cells = grid.cells
    thickness = float(height.max()) / scale
    quads = []
    padded = np.pad(cells, 1, constant_values=False)
    for dx, dy, corners in (
        (-1, 0, ((0, 0), (0, 1))),
        (1, 0, ((1, 1), (1, 0))),
        (0, -1, ((1, 0), (0, 0))),
        (0, 1, ((0, 1), (1, 1))),
    ):
        neighbour = padded[1 + dx : padded.shape[0] - 1 + dx, 1 + dy : padded.shape[1] - 1 + dy]
        edge = cells & ~neighbour
        for ix, iy in zip(*np.nonzero(edge)):
            (ax, ay), (bx, by) = corners
            p0 = world(ix + ax, iy + ay, -thickness)
            p1 = world(ix + bx, iy + by, -thickness)
            p2 = world(ix + bx, iy + by, thickness)
            p3 = world(ix + ax, iy + ay, thickness)
            quads.append((p0, p1, p2, p3))
    if not quads:
        return Mesh(
            np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32), np.zeros((0, 2), np.float32)
        )
    return _quad_soup(quads)


def _quad_soup(quads: list[tuple]) -> Mesh:
    corners = np.array(quads, dtype=np.float64)
    p0, p1, p2, p3 = corners[:, 0], corners[:, 1], corners[:, 2], corners[:, 3]
    normals = np.cross(p1 - p0, p3 - p0)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    positions = np.stack([p0, p1, p2, p0, p2, p3], axis=1).reshape(-1, 3)
    repeated = np.repeat(normals, 6, axis=0)
    uv = np.tile(
        np.array([[0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1]], dtype=np.float32), (len(quads), 1)
    )
    return Mesh(positions.astype(np.float32), repeated.astype(np.float32), uv)


# ---- polygon maths ------------------------------------------------------


def _points_in_polygon(grid_x: np.ndarray, grid_y: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Even-odd test for a whole lattice at once."""
    inside = np.zeros(grid_x.shape, dtype=bool)
    for (ax, ay), (bx, by) in zip(ring, np.roll(ring, -1, axis=0)):
        if ay == by:
            continue
        crosses = (grid_y >= min(ay, by)) & (grid_y < max(ay, by))
        t = (grid_y - ay) / (by - ay)
        inside ^= crosses & (grid_x >= ax + t * (bx - ax))
    return inside


def _distance_to_ring(grid_x: np.ndarray, grid_y: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Shortest distance from every lattice point to the outline itself."""
    points = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1)
    starts = ring
    ends = np.roll(ring, -1, axis=0)
    segments = ends - starts
    lengths = np.maximum(np.einsum("ij,ij->i", segments, segments), 1e-12)
    best = np.full(len(points), np.inf)
    # One segment at a time keeps peak memory to one grid-sized array.
    for start, segment, length in zip(starts, segments, lengths):
        offset = points - start
        t = np.clip((offset @ segment) / length, 0.0, 1.0)
        closest = start + t[:, None] * segment
        np.minimum(best, np.linalg.norm(points - closest, axis=1), out=best)
    return best.reshape(grid_x.shape)
