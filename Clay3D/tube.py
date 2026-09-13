"""Tube brush: path swept to a solid. VolumeBrushType × TaperType."""

from __future__ import annotations

import math

import numpy as np

from Clay3D.scene3d import Mesh, merge

# Tube cross-sections.
PROFILES = (
    ("capsule", "Capsule"),
    ("cylinder", "Cylinder"),
    ("triangle", "Triangle"),
    ("diamond", "Diamond"),
    ("hexagon", "Hexagon"),
    ("star", "Star"),
)

# Tube tapers.
TAPERS = (
    ("uniform", "None"),
    ("big_to_small", "Big to small"),
    ("small_to_big", "Small to big"),
    ("small_to_big_to_small", "Small to big to small"),
    ("big_to_small_to_big", "Big to small to big"),
)

TAPER_HINTS = {
    "uniform": "No taper",
    "big_to_small": "Make the start of the tube larger than the end of the tube",
    "small_to_big": "Make the start of the tube smaller and the end of the tube larger",
    "small_to_big_to_small": (
        "Make the middle of the tube larger than the ends "
        "(great for drawing moustaches!)"
    ),
    "big_to_small_to_big": "Make the middle of the tube smaller than the ends",
}

MIN_POINTS = 4
SECTION_STEPS = 96


def taper_scale(taper: str, t: float) -> float:
    """How wide the tube is at position t along its length, 0..1."""
    if taper == "big_to_small":
        return 1.0 - 0.75 * t
    if taper == "small_to_big":
        return 0.25 + 0.75 * t
    if taper == "small_to_big_to_small":
        return 0.3 + 0.7 * math.sin(math.pi * t)
    if taper == "big_to_small_to_big":
        return 1.0 - 0.7 * math.sin(math.pi * t)
    return 1.0


def _section(profile: str, sides_default: int = 20) -> list[tuple[float, float]]:
    """The cross-section outline, as unit-radius points."""
    if profile in ("capsule", "cylinder"):
        sides = sides_default
        points = [
            (math.cos(2 * math.pi * i / sides), math.sin(2 * math.pi * i / sides))
            for i in range(sides)
        ]
        if profile == "capsule":
            # Flatten one axis so the section reads as a capsule end-on.
            points = [(x, y * 0.62) for x, y in points]
        return points
    if profile == "star":
        return [
            (
                (1.0 if i % 2 == 0 else 0.45) * math.cos(math.pi * i / 5),
                (1.0 if i % 2 == 0 else 0.45) * math.sin(math.pi * i / 5),
            )
            for i in range(10)
        ]
    sides = {"triangle": 3, "diamond": 4, "hexagon": 6}[profile]
    turn = math.pi / 2
    return [
        (math.cos(turn + 2 * math.pi * i / sides), math.sin(turn + 2 * math.pi * i / sides))
        for i in range(sides)
    ]


def tube_to_mesh(path: list[tuple[float, float]], profile: str, taper: str, weight: float, scene):
    """Sweep the cross-section along a canvas path, in world units.

    Returns the mesh centred on its own origin, plus where it belongs.
    """
    centreline = _resample(path)
    if centreline is None:
        return None, None

    half_w, half_h = scene.canvas_extent()
    scale = scene.pixels_per_unit()
    world = np.stack(
        [
            centreline[:, 0] / scale - half_w,
            half_h - centreline[:, 1] / scale,
            np.zeros(len(centreline)),
        ],
        axis=1,
    )
    radius = max(weight, 2.0) / 2.0 / scale
    section = _section(profile)

    rings = []
    for index, point in enumerate(world):
        t = index / max(len(world) - 1, 1)
        tangent = _tangent(world, index)
        normal, binormal = _frame(tangent)
        width = radius * taper_scale(taper, t)
        rings.append(
            np.array([point + normal * (u * width) + binormal * (v * width) for u, v in section])
        )

    mesh = merge(_skin(rings), _cap(rings[0], -1), _cap(rings[-1], 1))
    low, high = mesh.bounds()
    centre = (low + high) / 2.0
    mesh.positions = (mesh.positions - centre).astype(np.float32)
    return mesh, centre


def _resample(path: list[tuple[float, float]]) -> np.ndarray | None:
    """Even out the drawn points and drop the jitter between them."""
    points = np.asarray(path, dtype=np.float64)
    if len(points) < MIN_POINTS:
        return None
    steps = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))])
    if steps[-1] < 8.0:
        return None
    count = int(min(SECTION_STEPS, max(8, steps[-1] / 6)))
    wanted = np.linspace(0, steps[-1], count)
    smoothed = np.stack(
        [np.interp(wanted, steps, points[:, 0]), np.interp(wanted, steps, points[:, 1])], axis=1
    )
    return _smooth(smoothed)


def _smooth(points: np.ndarray, passes: int = 2) -> np.ndarray:
    for _ in range(passes):
        padded = np.vstack([points[:1], points, points[-1:]])
        points = (padded[:-2] + 2 * padded[1:-1] + padded[2:]) / 4.0
    return points


def _tangent(world: np.ndarray, index: int) -> np.ndarray:
    if index == 0:
        direction = world[1] - world[0]
    elif index == len(world) - 1:
        direction = world[-1] - world[-2]
    else:
        direction = world[index + 1] - world[index - 1]
    length = float(np.linalg.norm(direction))
    return direction / length if length > 1e-9 else np.array([1.0, 0.0, 0.0])


def _frame(tangent: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two axes across the tube, perpendicular to where it is heading."""
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(tangent, reference))) > 0.95:
        reference = np.array([0.0, 1.0, 0.0])
    normal = np.cross(tangent, reference)
    normal /= max(float(np.linalg.norm(normal)), 1e-9)
    binormal = np.cross(tangent, normal)
    binormal /= max(float(np.linalg.norm(binormal)), 1e-9)
    return normal, binormal


def _skin(rings: list[np.ndarray]) -> Mesh:
    """Join consecutive rings with two triangles per side."""
    positions, normals, uvs = [], [], []
    sides = len(rings[0])
    for index in range(len(rings) - 1):
        here, ahead = rings[index], rings[index + 1]
        centre_here = here.mean(axis=0)
        for side in range(sides):
            nxt = (side + 1) % sides
            quad = (here[side], here[nxt], ahead[nxt], ahead[side])
            outward = [_unit(corner - centre_here) for corner in (quad[0], quad[1])]
            outward += [_unit(quad[2] - ahead.mean(axis=0)), _unit(quad[3] - ahead.mean(axis=0))]
            for a, b, c in ((0, 1, 2), (0, 2, 3)):
                positions.extend([quad[a], quad[b], quad[c]])
                normals.extend([outward[a], outward[b], outward[c]])
                uvs.extend([(side / sides, index), (nxt / sides, index), (nxt / sides, index + 1)])
    return Mesh(
        np.array(positions, dtype=np.float32),
        np.array(normals, dtype=np.float32),
        np.array(uvs, dtype=np.float32),
    )


def _cap(ring: np.ndarray, facing: float) -> Mesh:
    """Close one end with a fan."""
    centre = ring.mean(axis=0)
    normal = _unit(np.cross(ring[1] - ring[0], ring[2] - ring[0])) * facing
    positions, normals, uvs = [], [], []
    for side in range(len(ring)):
        nxt = (side + 1) % len(ring)
        corners = (centre, ring[side], ring[nxt]) if facing > 0 else (centre, ring[nxt], ring[side])
        positions.extend(corners)
        normals.extend([normal, normal, normal])
        uvs.extend([(0.5, 0.5), (0.0, 0.0), (1.0, 0.0)])
    return Mesh(
        np.array(positions, dtype=np.float32),
        np.array(normals, dtype=np.float32),
        np.array(uvs, dtype=np.float32),
    )


def _unit(v: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(v))
    return v / length if length > 1e-9 else np.array([0.0, 0.0, 1.0])
