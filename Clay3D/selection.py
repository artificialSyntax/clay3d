"""Mask selections. lift = cut to buffer; stamp = put back."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

Rect = tuple[int, int, int, int]

class Selection:
    """A masked region of the canvas, optionally lifted off it."""

    def __init__(self, mask: np.ndarray):
        self.mask = mask
        self.floating: np.ndarray | None = None
        self.origin = (0, 0)
        self.offset = np.zeros(2)
        self.rotation = 0.0
        self.scale = np.ones(2)

    @property
    def bounds(self) -> Rect | None:
        rows = np.flatnonzero(self.mask.any(axis=1))
        cols = np.flatnonzero(self.mask.any(axis=0))
        if len(rows) == 0 or len(cols) == 0:
            return None
        return (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)

    def is_empty(self) -> bool:
        return not self.mask.any()

    # -- lift and stamp ---------------------------------------------------

    def lift(self, canvas) -> Rect | None:
        """Cut the selected pixels out of the canvas into a floating buffer."""
        rect = self.bounds
        if rect is None or self.floating is not None:
            return rect
        x0, y0, x1, y1 = rect
        patch = canvas.pixels[y0:y1, x0:x1].copy()
        local_mask = self.mask[y0:y1, x0:x1]
        patch[~local_mask] = (0, 0, 0, 0)
        self.floating = patch
        self.origin = (x0, y0)
        canvas.pixels[y0:y1, x0:x1][local_mask] = canvas.background
        return rect

    def frame(self) -> Rect | None:
        """Where transformed() will land, worked out without resampling anything.

        Cheap enough to call every frame while a float is dragged; the pixels
        themselves are only produced when they are stamped or copied.
        """
        if self.floating is None:
            return None
        height, width = self.floating.shape[:2]
        scaled_w = max(1, int(round(width * abs(self.scale[0]))))
        scaled_h = max(1, int(round(height * abs(self.scale[1]))))
        if abs(self.rotation) > 1e-6:
            rotated_w, rotated_h = rotated_size(scaled_w, scaled_h, -math.degrees(self.rotation))
        else:
            rotated_w, rotated_h = scaled_w, scaled_h
        x = int(round(self.origin[0] + self.offset[0] - (rotated_w - scaled_w) // 2))
        y = int(round(self.origin[1] + self.offset[1] - (rotated_h - scaled_h) // 2))
        return (x, y, x + rotated_w, y + rotated_h)

    def transformed(self) -> tuple[np.ndarray, tuple[int, int]] | None:
        """The floating buffer with its move, scale and rotation applied."""
        if self.floating is None:
            return None
        image = Image.fromarray(self.floating, "RGBA")
        width = max(1, int(round(image.width * abs(self.scale[0]))))
        height = max(1, int(round(image.height * abs(self.scale[1]))))
        if (width, height) != image.size:
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        if self.scale[0] < 0:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if self.scale[1] < 0:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        before = image.size
        if abs(self.rotation) > 1e-6:
            image = image.rotate(
                -math.degrees(self.rotation), resample=Image.Resampling.BICUBIC, expand=True
            )
        grown_x = (image.width - before[0]) // 2
        grown_y = (image.height - before[1]) // 2
        position = (
            int(round(self.origin[0] + self.offset[0] - grown_x)),
            int(round(self.origin[1] + self.offset[1] - grown_y)),
        )
        return np.array(image), position

    def stamp(self, canvas) -> Rect | None:
        """Put the floating buffer back down and stop floating."""
        placed = self.transformed()
        if placed is None:
            return None
        pixels, (x, y) = placed
        rect = canvas.blit(pixels, x, y)
        self.mask = _mask_from_blit(canvas, pixels, x, y)
        self.floating = None
        self.offset = np.zeros(2)
        self.rotation = 0.0
        self.scale = np.ones(2)
        self.origin = (x, y)
        return rect

    def drop(self) -> None:
        """Abandon a float without stamping it (used when undoing)."""
        self.floating = None


def rotated_size(width: int, height: int, degrees: float) -> tuple[int, int]:
    """Size of Image.rotate(degrees, expand=True) on a width x height image.

    Mirrors Pillow's own arithmetic, corner rounding included, so a frame
    computed here matches the pixels transformed() produces exactly.
    """
    angle = degrees % 360.0
    if angle in (0.0, 180.0):
        return width, height
    if angle in (90.0, 270.0):
        return height, width
    radians = -math.radians(angle)
    a, b = round(math.cos(radians), 15), round(math.sin(radians), 15)
    d, e = round(-math.sin(radians), 15), round(math.cos(radians), 15)
    cx, cy = width / 2, height / 2
    c = a * -cx + b * -cy + cx
    f = d * -cx + e * -cy + cy
    xs = [a * x + b * y + c for x, y in ((0, 0), (width, 0), (width, height), (0, height))]
    ys = [d * x + e * y + f for x, y in ((0, 0), (width, 0), (width, height), (0, height))]
    return (math.ceil(max(xs)) - math.floor(min(xs)), math.ceil(max(ys)) - math.floor(min(ys)))


def _mask_from_blit(canvas, pixels: np.ndarray, x: int, y: int) -> np.ndarray:
    mask = np.zeros((canvas.height, canvas.width), dtype=bool)
    h, w = pixels.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.width, x + w), min(canvas.height, y + h)
    if x1 <= x0 or y1 <= y0:
        return mask
    mask[y0:y1, x0:x1] = pixels[y0 - y : y1 - y, x0 - x : x1 - x, 3] > 8
    return mask


# ---- building selections ------------------------------------------------


def from_layer(canvas, pixels: np.ndarray, x: float, y: float) -> Selection:
    """A floating patch that has not been cut out of the paper."""
    pixels = np.ascontiguousarray(pixels)
    height, width = pixels.shape[:2]
    ox, oy = int(round(x)), int(round(y))
    mask = np.zeros((canvas.height, canvas.width), dtype=bool)
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(canvas.width, ox + width), min(canvas.height, oy + height)
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = pixels[y0 - oy : y1 - oy, x0 - ox : x1 - ox, 3] > 8
    sel = Selection(mask)
    sel.floating = pixels
    sel.origin = (ox, oy)
    return sel


def box(canvas, x0: float, y0: float, x1: float, y1: float) -> Selection:
    mask = np.zeros((canvas.height, canvas.width), dtype=bool)
    left, right = sorted((int(x0), int(x1)))
    top, bottom = sorted((int(y0), int(y1)))
    left, top = max(0, left), max(0, top)
    right, bottom = min(canvas.width, right), min(canvas.height, bottom)
    if right > left and bottom > top:
        mask[top:bottom, left:right] = True
    return Selection(mask)


# ---- magic select -------------------------------------------------------
# Graph cut (GrabCut) seeded by the focus box, refined by Add/Remove
# strokes that re-run the cut. Work happens on a downsampled copy.

WORK_SIDE = 512
STROKE_WIDTH = 3          # work pixels
FIRST_PASSES = 4
REFINE_PASSES = 2
FLOOD_TOLERANCE = 10     # per channel, neighbour to neighbour
SPECK_SHARE = 0.005       # components under this share of the cutout are dropped
FILL_SIDE = 512


def default_magic_box(width: int, height: int) -> tuple[float, float, float, float]:
    """Box the tool opens with: the picture, inset 5%."""
    dx, dy = width * 0.05, height * 0.05
    return (dx, dy, width - dx, height - dy)


class MagicCutout:
    """One magic select session on a picture."""

    def __init__(self, pixels: np.ndarray, box):
        import cv2

        height, width = pixels.shape[:2]
        self.size = (width, height)
        self.box = box
        self.k = min(1.0, WORK_SIDE / max(width, height))
        work_size = (max(1, round(width * self.k)), max(1, round(height * self.k)))
        rgb = np.ascontiguousarray(pixels[:, :, 2::-1])
        if self.k < 1.0:
            rgb = cv2.resize(rgb, work_size, interpolation=cv2.INTER_AREA)
        self.work = np.ascontiguousarray(rgb)
        self.labels: np.ndarray | None = None
        self._models = None
        self._mask: np.ndarray | None = None
        self._undo: list[np.ndarray] = []
        self._redo: list[np.ndarray] = []

    # -- state ----------------------------------------------------------------

    @property
    def segmented(self) -> bool:
        return self.labels is not None

    @property
    def mask(self) -> np.ndarray:
        """Cutout at canvas resolution."""
        if self._mask is None:
            self._mask = self._full_mask()
        return self._mask

    # -- running the cut ------------------------------------------------------

    def segment(self) -> bool:
        """First cut from the box. False when nothing is found."""
        import cv2

        labels = np.full(self.work.shape[:2], cv2.GC_BGD, np.uint8)
        x0, y0, x1, y1 = self._work_box()
        labels[y0:y1, x0:x1] = cv2.GC_PR_FGD
        if not (labels == cv2.GC_BGD).any():
            # Box covers the picture: its rim is the only background there is.
            rim = max(3, int(0.03 * max(labels.shape)))
            labels[:rim, :] = labels[-rim:, :] = cv2.GC_PR_BGD
            labels[:, :rim] = labels[:, -rim:] = cv2.GC_PR_BGD
        self._models = (np.zeros((1, 65)), np.zeros((1, 65)))
        if not self._cut(labels, FIRST_PASSES):
            return False
        self._undo.clear()
        self._redo.clear()
        return True

    def mark(self, points, adding: bool) -> bool:
        """Add/Remove stroke in canvas pixels.

        The stroke is pinned, the similar-coloured region it touches becomes
        a hint for the same side, then the cut re-runs.
        """
        import cv2

        if self.labels is None or not points:
            return False
        stroke = np.zeros(self.labels.shape, np.uint8)
        line = np.array([[x * self.k, y * self.k] for x, y in points], np.int32)
        if len(line) == 1:
            cv2.circle(stroke, tuple(int(v) for v in line[0]), STROKE_WIDTH, 1, -1)
        else:
            cv2.polylines(stroke, [line], False, 1, STROKE_WIDTH)
        stroke = stroke.astype(bool)

        labels = self.labels.copy()
        grown = self._region_touched(stroke, adding)
        labels[grown] = cv2.GC_PR_FGD if adding else cv2.GC_PR_BGD
        labels[stroke] = cv2.GC_FGD if adding else cv2.GC_BGD
        before = self.labels
        if not self._cut(labels, REFINE_PASSES):
            return False
        self._undo.append(before)
        self._redo.clear()
        return True

    def _region_touched(self, stroke: np.ndarray, adding: bool) -> np.ndarray:
        """Flood from the stroke through similar colour, on the side it changes."""
        import cv2

        # Flood may only enter what the stroke is changing.
        changing = ~_foreground(self.labels) if adding else _foreground(self.labels)
        barrier = np.pad((~changing).astype(np.uint8), 1, constant_values=1)
        tolerance = (FLOOD_TOLERANCE,) * 3
        flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
        ys, xs = np.nonzero(stroke)
        for x, y in zip(xs[::2], ys[::2]):
            if barrier[y + 1, x + 1]:
                continue
            cv2.floodFill(self.work, barrier, (int(x), int(y)), 0, tolerance, tolerance, flags)
        return barrier[1:-1, 1:-1] == 255

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.labels)
        self._set_labels(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.labels)
        self._set_labels(self._redo.pop())
        return True

    def back_to_box(self) -> None:
        """Forget the cut; the box stays."""
        self._set_labels(None)
        self._undo.clear()
        self._redo.clear()

    def to_selection(self) -> Selection:
        return Selection(self.mask.copy())

    # -- internals ------------------------------------------------------------

    def _cut(self, labels: np.ndarray, passes: int) -> bool:
        import cv2

        # Copies: a failed cut must leave the colour models untouched.
        bgd, fgd = (model.copy() for model in self._models)
        cv2.setRNGSeed(0)   # k-means inside GrabCut; same picture, same cut
        try:
            cv2.grabCut(self.work, labels, None, bgd, fgd, passes, cv2.GC_INIT_WITH_MASK)
        except cv2.error:
            return False
        found = _foreground(labels)
        if found.sum() < max(4, 0.001 * found.size):
            return False
        self._models = (bgd, fgd)
        self._set_labels(labels)
        return True

    def _set_labels(self, labels: np.ndarray | None) -> None:
        self.labels = labels
        self._mask = None

    def _work_box(self) -> tuple[int, int, int, int]:
        work_h, work_w = self.work.shape[:2]
        x0, y0, x1, y1 = self.box
        left, right = sorted((x0 * self.k, x1 * self.k))
        top, bottom = sorted((y0 * self.k, y1 * self.k))
        return (
            max(0, int(round(left))), max(0, int(round(top))),
            min(work_w, int(round(right))), min(work_h, int(round(bottom))),
        )

    def _full_mask(self) -> np.ndarray:
        import cv2

        width, height = self.size
        found = _drop_specks(_foreground(self.labels)).astype(np.uint8) * 255
        if self.k < 1.0:
            found = cv2.resize(found, (width, height), interpolation=cv2.INTER_LINEAR)
        return found > 127


def _foreground(labels: np.ndarray) -> np.ndarray:
    return (labels == 1) | (labels == 3)   # GC_FGD, GC_PR_FGD


def _drop_specks(found: np.ndarray) -> np.ndarray:
    import cv2

    count, parts, stats, _ = cv2.connectedComponentsWithStats(found.astype(np.uint8), connectivity=8)
    if count <= 2:
        return found
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = np.flatnonzero(areas >= SPECK_SHARE * areas.sum()) + 1
    return np.isin(parts, keep)


def autofill_background(canvas, mask: np.ndarray) -> Rect | None:
    """Fill the hole a cutout leaves from its surroundings. Downsampled inpaint."""
    import cv2

    if not mask.any():
        return None
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    pad = max(8, int(0.15 * max(rows[-1] - rows[0], cols[-1] - cols[0])))
    y0, y1 = max(0, rows[0] - pad), min(canvas.height, rows[-1] + 1 + pad)
    x0, x1 = max(0, cols[0] - pad), min(canvas.width, cols[-1] + 1 + pad)

    patch = canvas.pixels[y0:y1, x0:x1]
    # Grow the hole a little so the subject's antialiased rim goes too.
    hole = cv2.dilate(mask[y0:y1, x0:x1].astype(np.uint8), np.ones((5, 5), np.uint8))
    height, width = hole.shape
    k = min(1.0, FILL_SIDE / max(height, width))
    small_size = (max(1, round(width * k)), max(1, round(height * k)))
    small = cv2.resize(patch, small_size, interpolation=cv2.INTER_AREA)
    small_hole = cv2.resize(hole, small_size, interpolation=cv2.INTER_NEAREST)
    # Shrinking blends subject colour into the hole's rim; fill that rim too.
    small_hole = cv2.dilate(small_hole, np.ones((3, 3), np.uint8))
    radius = max(3, int(round(6 * k)))
    colour = cv2.inpaint(np.ascontiguousarray(small[:, :, :3]), small_hole, radius, cv2.INPAINT_NS)
    alpha = cv2.inpaint(np.ascontiguousarray(small[:, :, 3]), small_hole, radius, cv2.INPAINT_NS)
    filled = np.dstack([colour, alpha])
    filled = cv2.resize(filled, (width, height), interpolation=cv2.INTER_LINEAR)
    region = hole.astype(bool)
    patch[region] = filled[region]
    return (int(x0), int(y0), int(x1), int(y1))
