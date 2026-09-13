"""Canvas rotate/flip/crop + pixel filters. Colour grading is effects.py."""

from __future__ import annotations

import numpy as np

# Canvas tab turns and flips.
TURNS = (
    ("rotate_right", "Rotate right 90°"),
    ("rotate_left", "Rotate left 90°"),
    ("flip_horizontal", "Flip horizontal"),
    ("flip_vertical", "Flip vertical"),
)

FILTERS = (
    ("sketch", "Sketch"),
    ("edge_detection", "Edge detection"),
    ("oil_texture", "Oil with texture"),
    ("wet_oil", "Wet oil"),
)


def turn(pixels: np.ndarray, direction: str) -> np.ndarray:
    if direction == "rotate_right":
        return np.rot90(pixels, k=-1).copy()
    if direction == "rotate_left":
        return np.rot90(pixels, k=1).copy()
    if direction == "flip_horizontal":
        return pixels[:, ::-1].copy()
    if direction == "flip_vertical":
        return pixels[::-1, :].copy()
    raise ValueError(f"unknown turn: {direction}")


def crop(pixels: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = rect
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(pixels.shape[1], int(x1)), min(pixels.shape[0], int(y1))
    if x1 <= x0 or y1 <= y0:
        return pixels.copy()
    return pixels[y0:y1, x0:x1].copy()


def apply_filter(pixels: np.ndarray, name: str) -> np.ndarray:
    if name not in _FILTERS:
        raise ValueError(f"unknown filter: {name}")
    rgb = pixels[:, :, :3].astype(np.float32)
    out = _FILTERS[name](rgb)
    result = pixels.copy()
    result[:, :, :3] = np.clip(out, 0, 255).astype(np.uint8)
    return result


# ---- the filters --------------------------------------------------------


def _edge_detection(rgb: np.ndarray) -> np.ndarray:
    magnitude = _sobel(_luma(rgb))
    edges = 255.0 - np.clip(magnitude * 2.2, 0, 255)
    return np.repeat(edges[:, :, None], 3, axis=2)


def _sketch(rgb: np.ndarray) -> np.ndarray:
    """Colour dodge of the image against its blurred inverse - pencil look."""
    grey = _luma(rgb)
    inverted = 255.0 - grey
    blurred = _box_blur(inverted, radius=6)
    dodged = grey * 255.0 / np.maximum(255.0 - blurred, 1.0)
    sketch = np.clip(dodged, 0, 255)
    return np.repeat(sketch[:, :, None], 3, axis=2)


def _oil_texture(rgb: np.ndarray) -> np.ndarray:
    """Flatten colour into patches, then emboss the canvas weave over it."""
    posterized = np.round(rgb / 26.0) * 26.0
    softened = np.stack([_box_blur(posterized[:, :, c], 2) for c in range(3)], axis=2)
    height, width = rgb.shape[:2]
    ys = np.arange(height)[:, None]
    xs = np.arange(width)[None, :]
    weave = (np.sin(xs * 0.7) + np.sin(ys * 0.7)) * 5.0
    return softened + weave[:, :, None]


def _wet_oil(rgb: np.ndarray) -> np.ndarray:
    """Smear colour along the local edge direction, like wet paint pulled."""
    grey = _luma(rgb)
    gx, gy = _gradients(grey)
    magnitude = np.maximum(np.hypot(gx, gy), 1e-3)
    shift_x = np.clip(np.round(-gy / magnitude * 4.0), -6, 6).astype(int)
    shift_y = np.clip(np.round(gx / magnitude * 4.0), -6, 6).astype(int)
    height, width = grey.shape
    ys = np.clip(np.arange(height)[:, None] + shift_y, 0, height - 1)
    xs = np.clip(np.arange(width)[None, :] + shift_x, 0, width - 1)
    smeared = rgb[ys, xs]
    blurred = np.stack([_box_blur(smeared[:, :, c], 1) for c in range(3)], axis=2)
    return 0.65 * blurred + 0.35 * rgb


_FILTERS = {
    "edge_detection": _edge_detection,
    "sketch": _sketch,
    "oil_texture": _oil_texture,
    "wet_oil": _wet_oil,
}


# ---- small image maths --------------------------------------------------


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _box_blur(plane: np.ndarray, radius: int) -> np.ndarray:
    """Box blur in constant time per pixel, via a summed-area table.

    `table[i, j]` holds the sum of everything above and left of (i, j),
    so any rectangle's total is four lookups no matter how big it is.
    """
    if radius < 1:
        return plane
    height, width = plane.shape
    size = 2 * radius + 1
    padded = np.pad(plane.astype(np.float64), radius, mode="edge")
    table = np.zeros((padded.shape[0] + 1, padded.shape[1] + 1), dtype=np.float64)
    table[1:, 1:] = padded.cumsum(axis=0).cumsum(axis=1)
    total = (
        table[size : size + height, size : size + width]
        - table[0:height, size : size + width]
        - table[size : size + height, 0:width]
        + table[0:height, 0:width]
    )
    return (total / (size * size)).astype(np.float32)


def _gradients(plane: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    padded = np.pad(plane, 1, mode="edge")
    gx = (
        padded[:-2, 2:] + 2 * padded[1:-1, 2:] + padded[2:, 2:]
        - padded[:-2, :-2] - 2 * padded[1:-1, :-2] - padded[2:, :-2]
    )
    gy = (
        padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:]
        - padded[:-2, :-2] - 2 * padded[:-2, 1:-1] - padded[:-2, 2:]
    )
    return gx, gy


def _sobel(plane: np.ndarray) -> np.ndarray:
    gx, gy = _gradients(plane)
    return np.hypot(gx, gy)
