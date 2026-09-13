"""Canvas rotate/flip/crop. Colour grading is effects.py."""

from __future__ import annotations

import numpy as np

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

