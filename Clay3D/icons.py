"""QPainter icons. No image assets."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from Clay3D import shapes2d, stickers
from Clay3D.effects import EFFECTS

INK = QColor("#3B3A39")
SOFT = QColor("#8A8886")
ACCENT = QColor("#0078D4")


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pixmap, painter


def _finish(pixmap: QPixmap, painter: QPainter) -> QIcon:
    painter.end()
    return QIcon(pixmap)


def _pen(color: QColor, width: float, cap=Qt.PenCapStyle.RoundCap) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(cap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


# ---- brushes ------------------------------------------------------------


def brush_icon(name: str, size: int = 40) -> QIcon:
    pixmap, p = _canvas(size)
    s = size
    handle = QPointF(s * 0.72, s * 0.20)
    tip = QPointF(s * 0.30, s * 0.74)

    def shaft(width: float, color: QColor) -> None:
        p.setPen(_pen(color, width))
        p.drawLine(handle, QPointF(s * 0.40, s * 0.62))

    if name == "marker":
        shaft(s * 0.15, QColor("#605E5C"))
        p.setPen(_pen(ACCENT, s * 0.22))
        p.drawLine(QPointF(s * 0.42, s * 0.60), tip)
    elif name == "calligraphy":
        shaft(s * 0.13, QColor("#605E5C"))
        p.setPen(_pen(QColor("#2B2B2B"), s * 0.09, Qt.PenCapStyle.FlatCap))
        p.drawLine(QPointF(s * 0.44, s * 0.58), QPointF(s * 0.24, s * 0.80))
    elif name == "oil":
        shaft(s * 0.13, QColor("#A0522D"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#C8752F"))
        p.drawEllipse(QRectF(s * 0.16, s * 0.54, s * 0.34, s * 0.30))
        p.setPen(_pen(QColor("#8C5220"), s * 0.045))
        for i in range(3):
            offset = s * (0.60 + i * 0.075)
            p.drawLine(QPointF(s * 0.18, offset), QPointF(s * 0.48, offset - s * 0.05))
    elif name == "watercolor":
        shaft(s * 0.12, QColor("#605E5C"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(64, 150, 220, 150))
        p.drawEllipse(QRectF(s * 0.12, s * 0.50, s * 0.42, s * 0.36))
        p.setBrush(QColor(64, 150, 220, 90))
        p.drawEllipse(QRectF(s * 0.22, s * 0.58, s * 0.40, s * 0.32))
    elif name == "pixel":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        step = s * 0.16
        for cx, cy in ((3, 3), (4, 3), (4, 4), (5, 4), (2, 4), (3, 4)):
            p.drawRect(QRectF(cx * step - step, cy * step, step, step))
    elif name == "pencil":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E8B33C"))
        body = QPolygonF([
            QPointF(s * 0.74, s * 0.14), QPointF(s * 0.86, s * 0.26),
            QPointF(s * 0.40, s * 0.72), QPointF(s * 0.28, s * 0.60),
        ])
        p.drawPolygon(body)
        p.setBrush(QColor("#3B3A39"))
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.28, s * 0.60), QPointF(s * 0.40, s * 0.72),
            QPointF(s * 0.20, s * 0.80),
        ]))
    elif name == "eraser":
        p.setPen(_pen(SOFT, s * 0.05))
        p.setBrush(QColor("#F3C5CE"))
        p.save()
        p.translate(s * 0.5, s * 0.5)
        p.rotate(-35)
        p.drawRoundedRect(QRectF(-s * 0.30, -s * 0.18, s * 0.60, s * 0.36), s * 0.06, s * 0.06)
        p.restore()
    elif name == "crayon":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#7B2D8E"))
        p.save()
        p.translate(s * 0.5, s * 0.5)
        p.rotate(-40)
        p.drawRect(QRectF(-s * 0.12, -s * 0.30, s * 0.24, s * 0.46))
        p.drawPolygon(QPolygonF([
            QPointF(-s * 0.12, s * 0.16), QPointF(s * 0.12, s * 0.16), QPointF(0, s * 0.34),
        ]))
        p.restore()
    elif name == "spray":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#605E5C"))
        p.drawRoundedRect(QRectF(s * 0.34, s * 0.36, s * 0.26, s * 0.46), s * 0.05, s * 0.05)
        p.setBrush(QColor("#8A8886"))
        p.drawRect(QRectF(s * 0.40, s * 0.24, s * 0.14, s * 0.14))
        p.setBrush(ACCENT)
        for i, (dx, dy) in enumerate(((0.70, 0.20), (0.80, 0.30), (0.72, 0.36), (0.86, 0.18))):
            r = s * (0.035 if i % 2 else 0.05)
            p.drawEllipse(QPointF(s * dx, s * dy), r, r)
    elif name == "smudge":
        p.setPen(_pen(QColor("#605E5C"), s * 0.10))
        path = QPainterPath(QPointF(s * 0.18, s * 0.70))
        path.cubicTo(QPointF(s * 0.36, s * 0.30), QPointF(s * 0.64, s * 0.86), QPointF(s * 0.84, s * 0.38))
        p.drawPath(path)
        p.setPen(_pen(QColor(96, 94, 92, 90), s * 0.18))
        p.drawPath(path)
    elif name == "fill":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ACCENT)
        bucket = QPolygonF([
            QPointF(s * 0.22, s * 0.40), QPointF(s * 0.62, s * 0.40),
            QPointF(s * 0.54, s * 0.78), QPointF(s * 0.30, s * 0.78),
        ])
        p.drawPolygon(bucket)
        p.setPen(_pen(QColor("#605E5C"), s * 0.06))
        p.drawArc(QRectF(s * 0.26, s * 0.16, s * 0.32, s * 0.32), 0, 180 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2E7BD6"))
        p.drawEllipse(QPointF(s * 0.76, s * 0.66), s * 0.09, s * 0.12)
    elif name == "eyedropper":
        p.setPen(_pen(QColor("#605E5C"), s * 0.09))
        p.drawLine(QPointF(s * 0.70, s * 0.26), QPointF(s * 0.34, s * 0.62))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ACCENT)
        p.drawEllipse(QPointF(s * 0.74, s * 0.22), s * 0.12, s * 0.12)
        p.setBrush(INK)
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.32, s * 0.60), QPointF(s * 0.40, s * 0.68), QPointF(s * 0.22, s * 0.80),
        ]))
    else:
        p.setPen(_pen(INK, s * 0.10))
        p.drawLine(QPointF(s * 0.25, s * 0.72), QPointF(s * 0.75, s * 0.28))
    return _finish(pixmap, p)


# ---- 2D shapes and lines ------------------------------------------------


def shape_icon(kind: str, size: int = 40, filled: bool = True) -> QIcon:
    """Draw the outline the shape tool will actually produce."""
    pixmap, p = _canvas(size)
    inset = size * 0.16
    parts = shapes2d.contours(kind, inset, inset, size - inset, size - inset)
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for part in parts:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in part]))
        path.closeSubpath()
    p.setPen(_pen(ACCENT, max(1.2, size * 0.045)))
    p.setBrush(QColor(0, 120, 212, 45) if filled else Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    return _finish(pixmap, p)


def line_icon(kind: str, size: int = 40) -> QIcon:
    pixmap, p = _canvas(size)
    s = size
    p.setPen(_pen(ACCENT, max(1.4, s * 0.06)))
    if kind == "straight":
        p.drawLine(QPointF(s * 0.18, s * 0.78), QPointF(s * 0.82, s * 0.22))
    elif kind == "curve":
        path = QPainterPath(QPointF(s * 0.16, s * 0.74))
        path.cubicTo(QPointF(s * 0.36, s * 0.16), QPointF(s * 0.64, s * 0.86), QPointF(s * 0.84, s * 0.26))
        p.drawPath(path)
    else:
        p.drawPolyline(QPolygonF([
            QPointF(s * 0.16, s * 0.74), QPointF(s * 0.40, s * 0.26),
            QPointF(s * 0.64, s * 0.62), QPointF(s * 0.86, s * 0.30),
        ]))
    p.setBrush(QColor("#FFFFFF"))
    p.setPen(_pen(SOFT, max(1.0, s * 0.035)))
    for point in _handle_points(kind, s):
        p.drawEllipse(point, s * 0.065, s * 0.065)
    return _finish(pixmap, p)


def _handle_points(kind: str, s: float) -> list[QPointF]:
    if kind == "straight":
        return [QPointF(s * 0.18, s * 0.78), QPointF(s * 0.82, s * 0.22)]
    if kind == "curve":
        return [QPointF(s * 0.16, s * 0.74), QPointF(s * 0.84, s * 0.26)]
    return [QPointF(s * 0.16, s * 0.74), QPointF(s * 0.40, s * 0.26), QPointF(s * 0.86, s * 0.30)]


# ---- 3D shapes ----------------------------------------------------------


def shape3d_icon(kind: str, size: int = 44) -> QIcon:
    """A small isometric read of each primitive."""
    pixmap, p = _canvas(size)
    s = size
    p.translate(s / 2, s / 2)
    body = QColor("#B8C4D4")
    top = QColor("#DCE4EE")
    side = QColor("#95A3B6")
    p.setPen(_pen(QColor("#6B7889"), max(1.0, s * 0.03)))
    r = s * 0.30

    def iso(x: float, y: float, z: float) -> QPointF:
        # Screen y grows downward, so height subtracts rather than adds.
        return QPointF((x - z) * 0.87 * r, ((x + z) * 0.5 - y) * r)

    if kind == "cube":
        for face, colour in (
            ([(-1, 1, -1), (1, 1, -1), (1, 1, 1), (-1, 1, 1)], top),
            ([(-1, 1, 1), (1, 1, 1), (1, -1, 1), (-1, -1, 1)], body),
            ([(1, 1, 1), (1, 1, -1), (1, -1, -1), (1, -1, 1)], side),
        ):
            p.setBrush(colour)
            p.drawPolygon(QPolygonF([iso(*c) for c in face]))
    elif kind == "sphere":
        gradient = QLinearGradient(-r, -r, r, r)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, side)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(0, 0), r * 1.15, r * 1.15)
    elif kind in ("cylinder", "pipe", "capsule"):
        width, height = r * 1.05, r * 1.25
        p.setBrush(body)
        p.drawRect(QRectF(-width, -height * 0.6, width * 2, height * 1.2))
        p.setBrush(top)
        p.drawEllipse(QRectF(-width, -height * 0.85, width * 2, height * 0.5))
        if kind == "pipe":
            p.setBrush(side)
            p.drawEllipse(QRectF(-width * 0.45, -height * 0.72, width * 0.9, height * 0.24))
        if kind == "capsule":
            p.setBrush(body)
            p.drawEllipse(QRectF(-width, height * 0.35, width * 2, height * 0.5))
    elif kind in ("cone", "pyramid"):
        p.setBrush(body)
        apex = QPointF(0, -r * 1.2)
        p.drawPolygon(QPolygonF([apex, QPointF(-r * 1.1, r * 0.75), QPointF(r * 1.1, r * 0.75)]))
        if kind == "cone":
            p.setBrush(side)
            p.drawEllipse(QRectF(-r * 1.1, r * 0.5, r * 2.2, r * 0.55))
        else:
            p.setBrush(side)
            p.drawPolygon(QPolygonF([apex, QPointF(r * 1.1, r * 0.75), QPointF(r * 0.3, r * 1.05)]))
    elif kind in ("torus", "quarter_torus"):
        p.setBrush(body)
        outer = QRectF(-r * 1.2, -r * 0.75, r * 2.4, r * 1.5)
        if kind == "torus":
            p.drawEllipse(outer)
            p.setBrush(QColor(255, 255, 255, 0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(-r * 0.45, -r * 0.28, r * 0.9, r * 0.56))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(_pen(body, r * 0.55))
            p.drawArc(outer, 0, 100 * 16)
    elif kind == "hemisphere":
        p.setBrush(top)
        p.drawChord(QRectF(-r * 1.15, -r * 0.9, r * 2.3, r * 2.0), 0, 180 * 16)
        p.setBrush(side)
        p.drawEllipse(QRectF(-r * 1.15, r * 0.8, r * 2.3, r * 0.45))
    else:
        p.setBrush(body)
        p.drawRoundedRect(QRectF(-r, -r, r * 2, r * 2), r * 0.3, r * 0.3)
    return _finish(pixmap, p)


def doodle_icon(mode: str, size: int = 44) -> QIcon:
    """Soft edge reads as a puffed pillow, sharp edge as a flat slab."""
    pixmap, p = _canvas(size)
    s = size
    if mode == "soft":
        # A rounded blob with a highlight, so it looks inflated.
        blob = QPainterPath(QPointF(s * 0.18, s * 0.58))
        blob.cubicTo(QPointF(s * 0.14, s * 0.16), QPointF(s * 0.80, s * 0.12),
                     QPointF(s * 0.84, s * 0.52))
        blob.cubicTo(QPointF(s * 0.88, s * 0.88), QPointF(s * 0.24, s * 0.92),
                     QPointF(s * 0.18, s * 0.58))
        gradient = QLinearGradient(0, 0, 0, s)
        gradient.setColorAt(0.0, QColor(120, 190, 245))
        gradient.setColorAt(1.0, QColor(0, 96, 178))
        p.setBrush(QBrush(gradient))
        p.setPen(_pen(QColor("#0A5AA0"), max(1.2, s * 0.04)))
        p.drawPath(blob)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 130))
        p.drawEllipse(QRectF(s * 0.30, s * 0.24, s * 0.26, s * 0.16))
    else:
        # An extruded slab: a flat face plus a visible side wall.
        face = QPolygonF([
            QPointF(s * 0.20, s * 0.26), QPointF(s * 0.68, s * 0.18),
            QPointF(s * 0.80, s * 0.52), QPointF(s * 0.44, s * 0.66),
        ])
        p.setPen(_pen(QColor("#0A5AA0"), max(1.2, s * 0.04), Qt.PenCapStyle.SquareCap))
        p.setBrush(QColor(120, 190, 245))
        p.drawPolygon(face)
        p.setBrush(QColor(0, 96, 178))
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.20, s * 0.26), QPointF(s * 0.44, s * 0.66),
            QPointF(s * 0.44, s * 0.86), QPointF(s * 0.20, s * 0.46),
        ]))
        p.setBrush(QColor(20, 80, 150))
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.44, s * 0.66), QPointF(s * 0.80, s * 0.52),
            QPointF(s * 0.80, s * 0.72), QPointF(s * 0.44, s * 0.86),
        ]))
    return _finish(pixmap, p)


# ---- effects ------------------------------------------------------------


def effect_icon(name: str, size: int = 52) -> QIcon:
    """Run the filter's own maths over a test gradient: a real preview."""
    effect = EFFECTS.get(name, EFFECTS["none"])
    pixmap, p = _canvas(size)
    for y in range(size):
        for x in range(0, size, 2):
            base = _preview_colour(x / size, y / size)
            r, g, b = _grade(base, effect)
            p.setPen(QColor(r, g, b))
            p.drawLine(x, y, x + 1, y)
    p.setPen(_pen(QColor(0, 0, 0, 40), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(0.5, 0.5, size - 1, size - 1))
    return _finish(pixmap, p)


def image_filter_icon(name: str, size: int = 44) -> QIcon:
    """Run the real pixel filter over a thumbnail, so tiles differ truly."""
    import numpy as np

    from Clay3D import imagefx

    thumb = np.zeros((size, size, 4), dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            r, g, b = _preview_colour(x / size, y / size)
            thumb[y, x] = (int(r * 255), int(g * 255), int(b * 255), 255)
    filtered = imagefx.apply_filter(thumb, name)

    pixmap, p = _canvas(size)
    for y in range(size):
        for x in range(size):
            r, g, b = filtered[y, x, :3]
            p.setPen(QColor(int(r), int(g), int(b)))
            p.drawPoint(x, y)
    p.setPen(_pen(QColor(0, 0, 0, 40), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(0.5, 0.5, size - 1, size - 1))
    return _finish(pixmap, p)


def _preview_colour(u: float, v: float) -> tuple[float, float, float]:
    """A small scene with sky, ground and a warm subject to grade."""
    if v < 0.45:
        return (0.42 + 0.25 * v, 0.60 + 0.22 * v, 0.86)
    if (u - 0.5) ** 2 + (v - 0.72) ** 2 < 0.035:
        return (0.88, 0.42, 0.28)
    return (0.30 + 0.35 * u, 0.52 - 0.12 * v, 0.26)


def _grade(rgb: tuple[float, float, float], effect) -> tuple[int, int, int]:
    """The filter pass's band grade, on the CPU, for the tile previews."""
    if effect.strength <= 0.0:
        return tuple(int(min(max(v, 0.0), 1.0) * 255) for v in rgb)
    luma = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    shadows = 1.0 - _smoothstep(0.0, 0.5, luma)
    highlights = _smoothstep(0.5, 1.0, luma)
    midtones = 1.0 - shadows - highlights
    weights = (shadows, midtones, highlights)

    def band(values):
        return sum(w * v for w, v in zip(weights, values))

    filter_colour = _hue_to_rgb(effect.colour_filter_hue)
    density = band(effect.colour_filter_density)
    graded = [
        rgb[i] + (min(rgb[i] * filter_colour[i] * 2.0, 1.0) - rgb[i]) * density
        for i in range(3)
    ]
    gain = 2.0 ** band(effect.exposure)
    graded = [v * gain for v in graded]

    for amount in (band(effect.saturation), effect.saturation_global):
        grey = 0.299 * graded[0] + 0.587 * graded[1] + 0.114 * graded[2]
        graded = [grey + (v - grey) * amount for v in graded]

    mixed = [rgb[i] + (min(max(graded[i], 0.0), 1.0) - rgb[i]) * effect.strength for i in range(3)]
    return tuple(int(min(max(v, 0.0), 1.0) * 255) for v in mixed)


def _hue_to_rgb(hue: float) -> tuple[float, float, float]:
    """The shader's hue ramp, so previews and the stage agree."""
    out = []
    for shift in (1.0, 2.0 / 3.0, 1.0 / 3.0):
        p = abs(((hue + shift) % 1.0) * 6.0 - 3.0)
        out.append(min(max(p - 1.0, 0.0), 1.0))
    return tuple(out)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ---- stickers, selection, canvas, tabs ----------------------------------


def tube_icon(profile: str, size: int = 34) -> QIcon:
    """A short length of tube, drawn with the chosen cross-section."""
    from Clay3D import tube

    pixmap, p = _canvas(size)
    s = size
    section = tube._section(profile, sides_default=14)
    p.setPen(_pen(QColor("#0A5AA0"), max(1.0, s * 0.04)))
    for step, (offset, shade) in enumerate(((0.30, "#78BEF5"), (0.0, "#2E7BD6"))):
        p.setBrush(QColor(shade))
        radius = s * 0.26
        centre = QPointF(s * (0.36 + offset), s * (0.62 - offset * 0.9))
        p.drawPolygon(QPolygonF([
            QPointF(centre.x() + u * radius, centre.y() + v * radius) for u, v in section
        ]))
    return _finish(pixmap, p)


def sticker_icon(kind: str, size: int = 44) -> QIcon:
    """One sticker from the catalog, drawn at the requested size."""
    pixmap, p = _canvas(size)
    stickers.draw(p, kind, float(size))
    return _finish(pixmap, p)


def select_icon(kind: str, size: int = 40) -> QIcon:
    pixmap, p = _canvas(size)
    s = size
    dashed = _pen(INK, max(1.2, s * 0.045))
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "box":
        p.setPen(dashed)
        p.drawRect(QRectF(s * 0.16, s * 0.20, s * 0.68, s * 0.60))
    elif kind == "freeform":
        p.setPen(dashed)
        path = QPainterPath(QPointF(s * 0.22, s * 0.66))
        path.cubicTo(QPointF(s * 0.18, s * 0.20), QPointF(s * 0.82, s * 0.16), QPointF(s * 0.76, s * 0.60))
        path.cubicTo(QPointF(s * 0.72, s * 0.88), QPointF(s * 0.30, s * 0.88), QPointF(s * 0.22, s * 0.66))
        p.drawPath(path)
    elif kind == "crop":
        p.setPen(_pen(INK, max(1.4, s * 0.06)))
        p.drawLine(QPointF(s * 0.28, s * 0.10), QPointF(s * 0.28, s * 0.76))
        p.drawLine(QPointF(s * 0.24, s * 0.72), QPointF(s * 0.90, s * 0.72))
        p.drawLine(QPointF(s * 0.10, s * 0.28), QPointF(s * 0.72, s * 0.28))
        p.drawLine(QPointF(s * 0.72, s * 0.24), QPointF(s * 0.72, s * 0.90))
    else:
        p.setPen(_pen(ACCENT, max(1.4, s * 0.06)))
        p.drawLine(QPointF(s * 0.28, s * 0.78), QPointF(s * 0.62, s * 0.40))
        p.setBrush(ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.58, s * 0.34), QPointF(s * 0.80, s * 0.18), QPointF(s * 0.70, s * 0.44),
        ]))
        p.setPen(_pen(QColor("#FFB900"), max(1.1, s * 0.045)))
        for angle in (0, 90, 180, 270):
            radians = math.radians(angle)
            p.drawLine(
                QPointF(s * (0.74 + 0.10 * math.cos(radians)), s * (0.26 + 0.10 * math.sin(radians))),
                QPointF(s * (0.74 + 0.17 * math.cos(radians)), s * (0.26 + 0.17 * math.sin(radians))),
            )
    return _finish(pixmap, p)


def canvas_icon(kind: str, size: int = 40) -> QIcon:
    pixmap, p = _canvas(size)
    s = size
    frame = QRectF(s * 0.16, s * 0.22, s * 0.68, s * 0.56)
    if kind in ("rotate_right", "rotate_left"):
        # One glyph, mirrored, so the two directions read as opposites.
        if kind == "rotate_left":
            p.translate(s, 0)
            p.scale(-1, 1)
        p.setPen(_pen(ACCENT, max(1.6, s * 0.08), Qt.PenCapStyle.FlatCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60), 20 * 16, 290 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ACCENT)
        p.drawPolygon(QPolygonF([
            QPointF(s * x, s * y) for x, y in ((0.62, 0.20), (0.92, 0.26), (0.72, 0.46))
        ]))
    elif kind in ("flip_horizontal", "flip_vertical"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 120, 212, 120))
        p.setPen(_pen(ACCENT, 1.2))
        if kind == "flip_horizontal":
            p.drawPolygon(QPolygonF([
                QPointF(s * 0.10, s * 0.22), QPointF(s * 0.44, s * 0.34), QPointF(s * 0.44, s * 0.66),
                QPointF(s * 0.10, s * 0.78),
            ]))
            p.setBrush(QColor(0, 120, 212, 45))
            p.drawPolygon(QPolygonF([
                QPointF(s * 0.90, s * 0.22), QPointF(s * 0.56, s * 0.34), QPointF(s * 0.56, s * 0.66),
                QPointF(s * 0.90, s * 0.78),
            ]))
        else:
            p.drawPolygon(QPolygonF([
                QPointF(s * 0.22, s * 0.10), QPointF(s * 0.34, s * 0.44), QPointF(s * 0.66, s * 0.44),
                QPointF(s * 0.78, s * 0.10),
            ]))
            p.setBrush(QColor(0, 120, 212, 45))
            p.drawPolygon(QPolygonF([
                QPointF(s * 0.22, s * 0.90), QPointF(s * 0.34, s * 0.56), QPointF(s * 0.66, s * 0.56),
                QPointF(s * 0.78, s * 0.90),
            ]))
    elif kind == "transparent":
        step = s * 0.17
        for row in range(4):
            for col in range(4):
                shade = QColor("#FFFFFF") if (row + col) % 2 == 0 else QColor("#D8D8DC")
                p.fillRect(QRectF(s * 0.16 + col * step, s * 0.22 + row * step, step, step), shade)
        p.setPen(_pen(SOFT, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(frame)
    else:
        p.setPen(_pen(SOFT, max(1.2, s * 0.05)))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(frame)
        p.setPen(_pen(ACCENT, max(1.2, s * 0.05)))
        p.drawLine(QPointF(s * 0.16, s * 0.5), QPointF(s * 0.84, s * 0.5))
    return _finish(pixmap, p)


def history_icon(kind: str, size: int = 20) -> QIcon:
    """The undo and redo arrows in the top bar."""
    pixmap, p = _canvas(size)
    s = size
    p.setPen(_pen(INK, max(1.5, s * 0.09), Qt.PenCapStyle.FlatCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    box = QRectF(s * 0.16, s * 0.26, s * 0.68, s * 0.62)
    if kind == "undo":
        p.drawArc(box, 20 * 16, 150 * 16)
        head = [(0.16, 0.30), (0.16, 0.58), (0.40, 0.44)]
    else:
        p.drawArc(box, 10 * 16, 150 * 16)
        head = [(0.84, 0.30), (0.84, 0.58), (0.60, 0.44)]
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(INK)
    p.drawPolygon(QPolygonF([QPointF(s * x, s * y) for x, y in head]))
    return _finish(pixmap, p)


def tab_icon(name: str, size: int = 22) -> QIcon:
    """The small glyph above each tab label in the top strip."""
    if name == "Brushes":
        return brush_icon("marker", size)
    if name == "2D shapes":
        return shape_icon("pentagon", size, filled=False)
    if name == "3D shapes":
        return shape3d_icon("cube", size)
    if name == "Stickers":
        return sticker_icon("star", size)
    if name == "Effects":
        return effect_icon("popart", size)
    if name == "Canvas":
        return canvas_icon("transparent", size)
    if name == "Select":
        return select_icon("box", size)
    pixmap, p = _canvas(size)
    font = QFont()
    font.setPointSizeF(size * 0.62)
    font.setBold(True)
    p.setFont(font)
    p.setPen(INK)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "A")
    return _finish(pixmap, p)


def colour_wheel(size: int) -> QPixmap:
    """The hue ring used by the colour picker."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    gradient = QConicalGradient(size / 2, size / 2, 90)
    for i in range(13):
        gradient.setColorAt(i / 12.0, QColor.fromHsvF((1.0 - i / 12.0) % 1.0, 1.0, 1.0))
    p.setBrush(QBrush(gradient))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    p.end()
    return pixmap
