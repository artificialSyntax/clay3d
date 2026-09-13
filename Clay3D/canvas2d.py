"""RGBA uint8 canvas. Ops return dirty rects. Stroke coverage is per-brush."""

from __future__ import annotations

import math

import numpy as np

from Clay3D import brushes

Color = tuple[int, int, int, int]
Rect = tuple[int, int, int, int]


def union(a: Rect | None, b: Rect | None) -> Rect | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


class Canvas:
    def __init__(self, width: int, height: int, background: Color = (255, 255, 255, 255)):
        self.width = int(width)
        self.height = int(height)
        self.background: Color = background
        self.pixels = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        self.pixels[:, :] = background

        self._color: Color = (0, 0, 0, 255)
        self._size = 12
        self._opacity = 1.0
        self._brush = brushes.get("marker")
        self.tolerance = 0.12

        self._coverage: np.ndarray | None = None
        self._base: np.ndarray | None = None
        self._stroke_rect: Rect | None = None
        self._last_point: tuple[float, float] | None = None
        self._residue = 0.0

    # ---- settings -------------------------------------------------------

    def set_color(self, color: Color) -> None:
        r, g, b, a = color
        self._color = (int(r), int(g), int(b), int(a))

    def set_size(self, size: float) -> None:
        self._size = max(1.0, float(size))

    def set_opacity(self, opacity: float) -> None:
        self._opacity = min(1.0, max(0.0, float(opacity)))

    def set_brush(self, name: str) -> None:
        self._brush = brushes.get(name)

    @property
    def brush_name(self) -> str:
        return self._brush.name

    @property
    def radius(self) -> float:
        return max(0.5, self._size / 2.0)

    def pixel(self, x: int, y: int) -> Color:
        r, g, b, a = self.pixels[int(y), int(x)]
        return (int(r), int(g), int(b), int(a))

    def resize(self, width: int, height: int, anchor: str = "TopLeft") -> None:
        """Grow or crop the paper, keeping the art anchored to one corner."""
        width, height = max(1, int(width)), max(1, int(height))
        grown = np.zeros((height, width, 4), dtype=np.uint8)
        grown[:, :] = self.background
        copy_w = min(width, self.width)
        copy_h = min(height, self.height)
        dx, dy = anchor_offset(anchor, width - self.width, height - self.height)
        sx, sy = max(0, -dx), max(0, -dy)
        tx, ty = max(0, dx), max(0, dy)
        grown[ty : ty + copy_h, tx : tx + copy_w] = self.pixels[
            sy : sy + copy_h, sx : sx + copy_w
        ]
        self.pixels = grown
        self.width, self.height = width, height

    # ---- strokes --------------------------------------------------------

    def begin_stroke(self, x: float, y: float) -> Rect | None:
        self._coverage = np.zeros((self.height, self.width), dtype=np.float32)
        self._base = self.pixels.copy()
        self._stroke_rect = None
        self._last_point = (float(x), float(y))
        self._residue = 0.0
        return self._lay_down([(float(x), float(y))], heading=0.0)

    def extend_stroke(self, x: float, y: float) -> Rect | None:
        if self._coverage is None or self._last_point is None:
            return self.begin_stroke(x, y)
        x0, y0 = self._last_point
        x1, y1 = float(x), float(y)
        heading = math.atan2(y1 - y0, x1 - x0)
        points = self._space_samples(x0, y0, x1, y1)
        self._last_point = (x1, y1)
        if not points:
            return None
        return self._lay_down(points, heading)

    def end_stroke(self) -> Rect | None:
        rect = self._stroke_rect
        self._coverage = None
        self._base = None
        self._stroke_rect = None
        self._last_point = None
        return rect

    def stroke(self, points: list[tuple[float, float]]) -> Rect | None:
        """Draw a whole polyline as one stroke. Used by shapes and tests."""
        if not points:
            return None
        rect = self.begin_stroke(*points[0])
        for x, y in points[1:]:
            rect = union(rect, self.extend_stroke(x, y))
        self.end_stroke()
        return rect

    def _space_samples(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> list[tuple[float, float]]:
        """Stamp positions along a segment, evenly spaced for this brush.

        Leftover distance carries into the next segment so spacing stays
        even across a whole stroke instead of resetting at every event.
        """
        step = max(0.7, self.radius * self._brush.spacing * 2.0)
        distance = math.hypot(x1 - x0, y1 - y0)
        if distance < 1e-6:
            return []
        points = []
        travelled = step - self._residue
        while travelled <= distance:
            t = travelled / distance
            points.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
            travelled += step
        self._residue = (self._residue + distance) % step
        return points

    def _lay_down(self, points: list[tuple[float, float]], heading: float) -> Rect | None:
        kernel = brushes.stamp(self._brush, self.radius, heading)
        half = kernel.shape[0] // 2
        rect = None
        for x, y in points:
            rect = union(rect, self._accumulate(kernel, half, x, y))
        if rect is None:
            return None
        self._composite(rect)
        self._stroke_rect = union(self._stroke_rect, rect)
        return rect

    def _accumulate(self, kernel: np.ndarray, half: int, x: float, y: float) -> Rect | None:
        cx, cy = int(round(x)), int(round(y))
        x0, y0 = cx - half, cy - half
        x1, y1 = x0 + kernel.shape[1], y0 + kernel.shape[0]
        clip = _clip(x0, y0, x1, y1, self.width, self.height)
        if clip is None:
            return None
        cx0, cy0, cx1, cy1 = clip
        patch = kernel[cy0 - y0 : cy1 - y0, cx0 - x0 : cx1 - x0] * self._brush.flow
        if self._brush.grain > 0.0:
            paper = brushes.grain_patch(cx0, cy0, cx1 - cx0, cy1 - cy0)
            patch = patch * (1.0 - self._brush.grain * (1.0 - paper))
        target = self._coverage[cy0:cy1, cx0:cx1]
        if self._brush.build_up:
            np.clip(target + patch, 0.0, 1.0, out=target)
        else:
            np.maximum(target, patch, out=target)
        return (cx0, cy0, cx1, cy1)

    def _composite(self, rect: Rect) -> None:
        """Blend the stroke's coverage over the pre-stroke pixels."""
        x0, y0, x1, y1 = rect
        coverage = self._coverage[y0:y1, x0:x1, None]
        base = self._base[y0:y1, x0:x1].astype(np.float32)
        if self._brush.erases:
            # Erasing goes back to the paper, whether that is white or clear.
            source = np.array(self.background, dtype=np.float32)
            alpha = coverage * self._opacity
        else:
            source = np.array(self._color, dtype=np.float32)
            alpha = coverage * self._opacity * (self._color[3] / 255.0)
        blended = source * alpha + base * (1.0 - alpha)
        self.pixels[y0:y1, x0:x1] = np.clip(blended, 0, 255).astype(np.uint8)

    # ---- click tools ----------------------------------------------------

    def fill(self, x: int, y: int) -> Rect | None:
        """Flood fill from a seed, within the current tolerance.

        Scanline span filling: each pass swallows a whole horizontal run,
        so cost tracks the number of spans rather than the pixel count.
        """
        x, y = int(x), int(y)
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        import cv2

        matches = self._similar_to(self.pixels[y, x])
        if not matches[y, x]:
            return None
        # Connected run of matching pixels around the seed, 4-neighbour, done in C.
        region = matches.astype(np.uint8)
        _, _, _, (rx, ry, rw, rh) = cv2.floodFill(region, None, (x, y), 2, 0, 0, 4)
        rect = (rx, ry, rx + rw, ry + rh)
        mask = region[ry:ry + rh, rx:rx + rw] == 2
        _paint_masked(self.pixels, mask, rect, self._color, self._opacity)
        return rect

    def _similar_to(self, target: np.ndarray) -> np.ndarray:
        """Pixels whose summed RGBA distance from target is within tolerance."""
        import cv2

        limit = self.tolerance * 255.0 * 4.0
        difference = cv2.absdiff(self.pixels, tuple(float(v) for v in target))
        # Sum the four channel differences in 16 bits: 4 x 255 overflows 8.
        channels = cv2.split(difference)
        total = cv2.add(channels[0], channels[1], dtype=cv2.CV_16U)
        total = cv2.add(total, channels[2], dtype=cv2.CV_16U)
        total = cv2.add(total, channels[3], dtype=cv2.CV_16U)
        return total <= limit

    def replace_color(self, target: Color, replacement: Color) -> Rect:
        """Recolor every matching pixel at once, ignoring connectivity."""
        matches = self._similar_to(np.array(target, dtype=np.uint8))
        self.pixels[matches] = replacement
        return (0, 0, self.width, self.height)

    def fill_polygon(self, points: list[tuple[float, float]], color: Color) -> Rect | None:
        region = _polygon_mask(points, self.width, self.height)
        if region is None:
            return None
        mask, rect = region
        _paint_masked(self.pixels, mask, rect, color, self._opacity)
        return rect

    def blit(self, rgba: np.ndarray, x: int, y: int) -> Rect | None:
        """Alpha-composite an RGBA image onto the canvas (text, stickers)."""
        h, w = rgba.shape[:2]
        clip = _clip(int(x), int(y), int(x) + w, int(y) + h, self.width, self.height)
        if clip is None:
            return None
        x0, y0, x1, y1 = clip
        source = rgba[y0 - int(y) : y1 - int(y), x0 - int(x) : x1 - int(x)].astype(np.float32)
        alpha = source[:, :, 3:4] / 255.0
        base = self.pixels[y0:y1, x0:x1].astype(np.float32)
        blended = source * alpha + base * (1.0 - alpha)
        blended[:, :, 3] = np.maximum(base[:, :, 3], source[:, :, 3])
        self.pixels[y0:y1, x0:x1] = np.clip(blended, 0, 255).astype(np.uint8)
        return (x0, y0, x1, y1)

    def make_transparent(self) -> Rect:
        opaque_white = np.all(self.pixels[:, :, :3] > 250, axis=2)
        self.pixels[opaque_white] = (0, 0, 0, 0)
        self.background = (0, 0, 0, 0)
        return (0, 0, self.width, self.height)

    def make_opaque(self) -> Rect:
        empty = self.pixels[:, :, 3] < 250
        self.pixels[empty] = (255, 255, 255, 255)
        self.background = (255, 255, 255, 255)
        return (0, 0, self.width, self.height)


# Eight orbs on the paper, as Paint 3D draws them in the Canvas tab.
CANVAS_ORBS = (
    "TopLeft", "Top", "TopRight",
    "Left", "Right",
    "BottomLeft", "Bottom", "BottomRight",
)

_OPPOSITE_ORB = {
    "TopLeft": "BottomRight",
    "Top": "Bottom",
    "TopRight": "BottomLeft",
    "Left": "Right",
    "Right": "Left",
    "BottomLeft": "TopRight",
    "Bottom": "Top",
    "BottomRight": "TopLeft",
}


def canvas_orb_positions(width: float, height: float) -> dict[str, tuple[float, float]]:
    w, h = float(width), float(height)
    return {
        "TopLeft": (0.0, 0.0),
        "Top": (w / 2.0, 0.0),
        "TopRight": (w, 0.0),
        "Left": (0.0, h / 2.0),
        "Right": (w, h / 2.0),
        "BottomLeft": (0.0, h),
        "Bottom": (w / 2.0, h),
        "BottomRight": (w, h),
    }


def opposite_orb_anchor(handle: str) -> str:
    return _OPPOSITE_ORB[handle]


def size_from_orb_drag(
    handle: str,
    x: float,
    y: float,
    old_w: int,
    old_h: int,
    lock: bool = False,
) -> tuple[int, int]:
    """New paper size while dragging a canvas orb at canvas pixel (x, y)."""
    ratio = old_w / max(old_h, 1)
    if handle in ("Right", "TopRight", "BottomRight"):
        width = max(1, int(round(x)))
    elif handle in ("Left", "TopLeft", "BottomLeft"):
        width = max(1, int(round(old_w - x)))
    else:
        width = old_w
    if handle in ("Bottom", "BottomLeft", "BottomRight"):
        height = max(1, int(round(y)))
    elif handle in ("Top", "TopLeft", "TopRight"):
        height = max(1, int(round(old_h - y)))
    else:
        height = old_h
    if lock:
        if handle in ("Left", "Right"):
            height = max(1, int(round(width / ratio)))
        elif handle in ("Top", "Bottom"):
            width = max(1, int(round(height * ratio)))
        else:
            scale_w = width / max(old_w, 1)
            scale_h = height / max(old_h, 1)
            scale = scale_h if abs(scale_h - 1) > abs(scale_w - 1) else scale_w
            width = max(1, int(round(old_w * scale)))
            height = max(1, int(round(old_h * scale)))
    return width, height


def hit_canvas_orb(
    x: float,
    y: float,
    width: float,
    height: float,
    reach: float,
) -> str | None:
    best = None
    best_d = reach * 1.4
    for name, (hx, hy) in canvas_orb_positions(width, height).items():
        distance = math.hypot(x - hx, y - hy)
        if distance <= best_d:
            best, best_d = name, distance
    return best


# ---- geometry helpers ---------------------------------------------------


def anchor_offset(anchor: str, dw: int, dh: int) -> tuple[int, int]:
    horizontal = {"Left": 0, "Center": dw // 2, "Right": dw}
    vertical = {"Top": 0, "Center": dh // 2, "Bottom": dh}
    if anchor in ("TopLeft", "Top", "Left"):
        return (0, 0)
    if anchor == "Center":
        return (dw // 2, dh // 2)
    if anchor == "TopRight":
        return (dw, 0)
    if anchor == "BottomLeft":
        return (0, dh)
    if anchor == "BottomRight":
        return (dw, dh)
    return (horizontal.get(anchor, 0), vertical.get(anchor, 0))


def _clip(x0: int, y0: int, x1: int, y1: int, width: int, height: int) -> Rect | None:
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _paint_masked(pixels: np.ndarray, mask: np.ndarray, rect: Rect, color: Color, opacity: float) -> None:
    """Lay a flat colour over the masked pixels inside a rectangle.

    The opaque case is by far the common one and skips the float maths
    entirely, which matters because a fill can cover the whole canvas.
    """
    x0, y0, x1, y1 = rect
    patch = pixels[y0:y1, x0:x1]
    alpha = (color[3] / 255.0) * opacity
    where = mask[:, :, None]
    if alpha >= 0.999:
        np.copyto(patch, np.array(color, dtype=np.uint8), where=where)
        return
    source = np.array(color, dtype=np.float32)
    blended = np.clip(source * alpha + patch.astype(np.float32) * (1.0 - alpha), 0, 255).astype(np.uint8)
    np.copyto(patch, blended, where=where)


def _polygon_mask(
    points: list[tuple[float, float]], width: int, height: int
) -> tuple[np.ndarray, Rect] | None:
    """Even-odd polygon rasterization, limited to the shape's bounding box."""
    if len(points) < 3:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    rect = _clip(
        int(math.floor(min(xs))), int(math.floor(min(ys))),
        int(math.ceil(max(xs))) + 1, int(math.ceil(max(ys))) + 1,
        width, height,
    )
    if rect is None:
        return None
    x0, y0, x1, y1 = rect
    column = np.arange(x0, x1, dtype=np.float32) + 0.5
    row = np.arange(y0, y1, dtype=np.float32) + 0.5
    inside = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if ay == by:
            continue
        crosses = ((row >= min(ay, by)) & (row < max(ay, by)))[:, None]
        t = (row - ay) / (by - ay)
        crossing_x = (ax + t * (bx - ax))[:, None]
        inside ^= crosses & (column[None, :] >= crossing_x)
    if not inside.any():
        return None
    return inside, rect
