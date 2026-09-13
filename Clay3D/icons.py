"""Icons. UI glyphs are Lucide SVGs (ui_icons/, ISC); previews are drawn."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtSvg import QSvgRenderer

from Clay3D import shapes2d, stickers
from Clay3D.effects import EFFECTS

INK = QColor("#222255")
SOFT = QColor("#8A8886")
ACCENT = QColor("#0064B6")


UI_ICON_DIR = Path(__file__).with_name("ui_icons")


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    return (UI_ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")


def ui_icon(name: str, size: int = 20, color: QColor | str = INK) -> QIcon:
    """A Lucide glyph from ui_icons/, stroked in one colour."""
    return QIcon(ui_pixmap(name, size, color))


def ui_pixmap(name: str, size: int = 20, color: QColor | str = INK) -> QPixmap:
    colour = QColor(color).name()
    svg = _svg_source(name).replace("currentColor", colour)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    # Render at 2x so the icon stays crisp on HiDPI screens.
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size * 2, size * 2))
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return pixmap


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


# ---- tool tiles ------------------------------------------------------------

# Brush tiles use standard Lucide glyphs; the drawn previews below stay for
# things that are pictures of their result (shapes, stickers, 3D objects).
BRUSH_GLYPHS = {
    "marker": "highlighter",
    "calligraphy": "pen-tool",
    "oil": "paintbrush",
    "watercolor": "droplet",
    "pixel": "grid-3x3",
    "pencil": "pencil",
    "eraser": "eraser",
    "crayon": "pen-line",
    "spray": "spray-can",
    "fill": "paint-bucket",
    "eyedropper": "pipette",
}


def brush_tool_icon(name: str, size: int = 28) -> QIcon:
    return ui_icon(BRUSH_GLYPHS[name], size)


def doodle_tool_icon(key: str, size: int = 28) -> QIcon:
    if key == "tube":
        return tube_icon("capsule", size)
    return doodle_icon(key.split("_", 1)[1], size)


def text_tool_icon(key: str, size: int = 28) -> QIcon:
    return ui_icon("type", size)


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
    else:
        points = [(point.x(), point.y()) for point in _handle_points(kind, s)]
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in shapes2d.line_path(kind, points)]))
    p.setBrush(QColor("#FFFFFF"))
    p.setPen(_pen(SOFT, max(1.0, s * 0.035)))
    for point in _handle_points(kind, s):
        p.drawEllipse(point, s * 0.065, s * 0.065)
    return _finish(pixmap, p)


def _handle_points(kind: str, s: float) -> list[QPointF]:
    """One handle per point: an S that bends once more with each extra point."""
    if kind == "straight":
        return [QPointF(s * 0.18, s * 0.78), QPointF(s * 0.82, s * 0.22)]
    count = shapes2d.LINE_POINT_COUNTS[kind]
    points = []
    for i in range(count):
        t = i / (count - 1)
        wave = 0.20 * (1 if i % 2 else -1) if 0 < i < count - 1 else 0.0
        points.append(QPointF(s * (0.16 + 0.68 * t), s * (0.74 - 0.48 * t + wave)))
    return points


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
    effect = EFFECTS.get(name, EFFECTS["default"])
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


# ---- stickers and tubes -------------------------------------------------


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


def pixels_icon(pixels, size: int = 44) -> QIcon:
    """An RGBA array as a square icon, aspect kept."""
    from PySide6.QtGui import QImage

    height, width = pixels.shape[:2]
    image = QImage(pixels.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888)
    scaled = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    pixmap, p = _canvas(size)
    p.drawImage(QPointF((size - scaled.width()) / 2, (size - scaled.height()) / 2), scaled)
    return _finish(pixmap, p)


def sticker_icon(kind: str, size: int = 44) -> QIcon:
    """One sticker from the catalog, drawn at the requested size."""
    pixmap, p = _canvas(size)
    stickers.draw(p, kind, float(size))
    return _finish(pixmap, p)
