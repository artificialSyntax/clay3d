"""Brush stamps. One code path; numbers differ per name."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from Clay3D.tuning import BRUSH_DAB_SPACING, BRUSH_FLOW


GRAIN_SIZE = 256


@dataclass(frozen=True)
class Brush:
    """How one brush lays paint down.

    shape       footprint: round, nib (angled flat), square, or bristle
    flow        alpha deposited by a single stamp, 0..1
    spacing     distance between stamps, as a fraction of the radius
    softness    edge feather, as a fraction of the radius
    grain       how strongly the paper texture eats into the stamp, 0..1
    scatter     random stamp displacement, in radii (spray can)
    density     fraction of the footprint that gets any paint (spray can)
    build_up    True: overlapping stamps darken. False: a stroke is flat.
    erases      paint back to the canvas background instead of the color
    smudges     drag existing pixels instead of depositing color
    """

    name: str
    label: str
    shape: str = "round"
    flow: float = 1.0
    spacing: float = 0.15  # both are set from tuning.py at build time
    softness: float = 0.12
    grain: float = 0.0
    scatter: float = 0.0
    density: float = 1.0
    build_up: bool = False
    erases: bool = False
    smudges: bool = False


CATALOG: dict[str, Brush] = {
    "marker": Brush("marker", "Marker", softness=0.10),
    "calligraphy": Brush("calligraphy", "Calligraphy pen", shape="nib", softness=0.06),
    "oil": Brush(
        "oil",
        "Oil brush",
        shape="bristle",
        flow=0.55,
        spacing=0.10,
        softness=0.22,
        grain=0.55,
        build_up=True,
    ),
    "watercolor": Brush(
        "watercolor",
        "Watercolor",
        flow=0.16,
        spacing=0.08,
        softness=0.55,
        grain=0.25,
        build_up=True,
    ),
    "pixel": Brush("pixel", "Pixel pen", shape="square", spacing=0.5, softness=0.0),
    "pencil": Brush(
        "pencil",
        "Pencil",
        flow=0.35,
        spacing=0.07,
        softness=0.30,
        grain=0.85,
        build_up=True,
    ),
    "crayon": Brush(
        "crayon",
        "Crayon",
        flow=0.45,
        spacing=0.09,
        softness=0.20,
        grain=0.95,
        build_up=True,
    ),
    "spray": Brush(
        "spray",
        "Spray can",
        flow=0.10,
        spacing=0.22,
        softness=0.85,
        scatter=0.55,
        density=0.30,
        build_up=True,
    ),
    "eraser": Brush("eraser", "Eraser", shape="square", softness=0.05, erases=True),
    "smudge": Brush("smudge", "Smudger", flow=0.55, spacing=0.05, smudges=True),
}

# The Brushes panel, in the original's order. Fill is a click tool rather
# than a stamp brush, so the app appends it to the panel itself.
#
# Smudger stays in CATALOG but not the panel; Paint 3D's panel has no smudge.
PANEL_ORDER = (
    "marker",
    "calligraphy",
    "oil",
    "watercolor",
    "pixel",
    "pencil",
    "eraser",
    "crayon",
    "spray",
)


def _apply_tuning() -> None:
    """Take flow and spacing from tuning.py, where the guesses live."""
    import dataclasses

    for name, brush in list(CATALOG.items()):
        CATALOG[name] = dataclasses.replace(
            brush,
            flow=BRUSH_FLOW.get(name, brush.flow),
            spacing=BRUSH_DAB_SPACING.get(name, brush.spacing),
        )


_apply_tuning()


def get(name: str) -> Brush:
    if name not in CATALOG:
        raise ValueError(f"unknown brush: {name}")
    return CATALOG[name]


# Paper grain: mean 0.514, standard deviation 0.181, correlation
# half-width 2 px. Octave weights fitted to that spectrum.
GRAIN_MEAN = 0.514
GRAIN_DEVIATION = 0.181
GRAIN_OCTAVES = ((0, 0.30), (1, 0.70))


def _build_grain() -> np.ndarray:
    """A tileable paper texture, sampled in canvas space.

    Painting in canvas space (not stamp space) is what makes pencil and
    crayon look like they are catching on the tooth of the paper: the
    texture stays put while the brush moves over it.
    """
    rng = np.random.default_rng(0x3D9A17)
    noise = rng.random((GRAIN_SIZE, GRAIN_SIZE), dtype=np.float32)
    grain = np.zeros_like(noise)
    for radius, weight in GRAIN_OCTAVES:
        grain += weight * (noise if radius == 0 else _wrap_blur(noise, radius))
    grain = (grain - grain.mean()) / max(grain.std(), 1e-6)
    grain = grain * GRAIN_DEVIATION + GRAIN_MEAN
    return np.clip(grain, 0.0, 1.0).astype(np.float32)


def _wrap_blur(field: np.ndarray, radius: int) -> np.ndarray:
    out = np.zeros_like(field)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out += np.roll(np.roll(field, dy, axis=0), dx, axis=1)
    return out / ((2 * radius + 1) ** 2)


GRAIN = _build_grain()


def grain_patch(x0: int, y0: int, width: int, height: int) -> np.ndarray:
    """The paper texture under a rectangle of canvas, tiled forever."""
    ys = np.arange(y0, y0 + height) % GRAIN_SIZE
    xs = np.arange(x0, x0 + width) % GRAIN_SIZE
    return GRAIN[np.ix_(ys, xs)]


_kernel_cache: dict[tuple, np.ndarray] = {}
HEADING_STEPS = 32


def stamp(brush: Brush, radius: float, heading: float) -> np.ndarray:
    """One stamp's alpha footprint, as a square float32 array.

    Cached per (brush, radius, heading bucket) because a stroke lays down
    hundreds of stamps and almost all of them are identical.
    """
    radius = max(0.5, float(radius))
    quantized_radius = round(radius * 4) / 4
    bucket = 0
    if brush.shape in ("nib", "bristle"):
        bucket = int(round(heading / (2 * math.pi) * HEADING_STEPS)) % HEADING_STEPS
    key = (brush.name, quantized_radius, bucket)
    cached = _kernel_cache.get(key)
    if cached is None:
        angle = 2 * math.pi * bucket / HEADING_STEPS
        cached = _make_stamp(brush, quantized_radius, angle)
        _kernel_cache[key] = cached
    return cached


def _make_stamp(brush: Brush, radius: float, heading: float) -> np.ndarray:
    reach = radius * (1.0 + brush.scatter)
    half = max(1, int(math.ceil(reach)) + 1)
    size = 2 * half + 1
    coords = np.arange(size, dtype=np.float32) - half
    dy = coords[:, None]
    dx = coords[None, :]

    if brush.shape == "square":
        distance = np.maximum(np.abs(dx), np.abs(dy)) / radius
    elif brush.shape == "nib":
        # A flat nib: narrow across the stroke, wide along it, held at a
        # fixed angle to the page the way a real calligraphy pen is.
        angle = heading + math.pi / 4
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        along = (dx * cos_a + dy * sin_a) / radius
        across = (-dx * sin_a + dy * cos_a) / max(radius * 0.22, 0.35)
        distance = np.sqrt(along * along + across * across)
    else:
        distance = np.sqrt(dx * dx + dy * dy) / radius

    softness = max(brush.softness, 1.0 / max(radius, 1.0))
    alpha = np.clip((1.0 - distance) / softness, 0.0, 1.0).astype(np.float32)

    if brush.shape == "bristle":
        alpha *= _bristle_mask(size, half, heading)
    if brush.scatter > 0.0:
        alpha *= _scatter_mask(brush, size, radius)
    return alpha


def _bristle_mask(size: int, half: int, heading: float) -> np.ndarray:
    """Streaks running along the stroke."""
    coords = np.arange(size, dtype=np.float32) - half
    dy = coords[:, None]
    dx = coords[None, :]
    across = -dx * math.sin(heading) + dy * math.cos(heading)
    streaks = 0.55 + 0.45 * np.cos(across * 2.1)
    return streaks.astype(np.float32)


def _scatter_mask(brush: Brush, size: int, radius: float) -> np.ndarray:
    """Speckle for the spray can, fixed per stamp size so it stays cheap."""
    rng = np.random.default_rng(int(radius * 97) ^ 0x5A17)
    return (rng.random((size, size)) < brush.density).astype(np.float32)
