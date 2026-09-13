"""Sticker catalog. 32 presets + 8 textures. Glyphs drawn here."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

def _pen(color: QColor, width: float, round_cap: bool = False) -> QPen:
    """A pen with a real cap style - QPen's third argument is a PenStyle."""
    pen = QPen(color, width)
    if round_cap:
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


SKIN = QColor("#E8B48F")
DARK = QColor("#2B2B2B")
WHITE = QColor("#FFFFFF")

# key, label, group. Labels and order are the original's.
CATALOG = (
    ("star", "Star", "Stickers"),
    ("planet", "Planet", "Stickers"),
    ("sun", "Sun", "Stickers"),
    ("cloud", "Cloud", "Stickers"),
    ("spiral", "Spiral", "Stickers"),
    ("ninja_cat", "Ninja cat", "Stickers"),
    ("lollipop", "Lollipop", "Stickers"),
    ("rainbow", "Rainbow", "Stickers"),
    ("glasses", "Glasses", "Stickers"),
    ("sunglasses", "Sunglasses", "Stickers"),
    ("heart", "Heart", "Stickers"),
    ("mouth_kiss", "Kiss", "Stickers"),
    ("mouth_sad", "Sad", "Stickers"),
    ("mouth_happy", "Happy", "Stickers"),
    ("mouth_tongue", "Tongue", "Stickers"),
    ("moustache", "Moustache", "Stickers"),
    ("eye", "Eye", "Stickers"),
    ("eye_look_up", "Look up", "Stickers"),
    ("eye_worried", "Worried", "Stickers"),
    ("eyebrow", "Eyebrow", "Stickers"),
    ("ear_mouse", "Mouse ear", "Stickers"),
    ("ear_dog", "Dog ear", "Stickers"),
    ("ear_pig", "Pig ear", "Stickers"),
    ("ear", "Ear", "Stickers"),
    ("nose_mouse", "Mouse nose", "Stickers"),
    ("nose_dog", "Dog nose", "Stickers"),
    ("nose_pig", "Pig nose", "Stickers"),
    ("nose", "Nose", "Stickers"),
    ("eye_reptile", "Reptile eye", "Stickers"),
    ("eye_cat", "Cat eye", "Stickers"),
    ("eye_owl", "Owl eye", "Stickers"),
    ("eye_lash", "Eye lash", "Stickers"),
    ("bark", "Bark", "Textures"),
    ("concrete", "Concrete", "Textures"),
    ("fur", "Fur", "Textures"),
    ("gravel", "Gravel", "Textures"),
    ("hedge", "Hedge", "Textures"),
    ("marble", "Marble", "Textures"),
    ("sand", "Sand", "Textures"),
    ("wood", "Wood", "Textures"),
)

GROUPS = ("Stickers", "Textures")


def in_group(group: str) -> tuple[tuple[str, str], ...]:
    return tuple((key, label) for key, label, kind in CATALOG if kind == group)


def label_for(key: str) -> str:
    for candidate, label, _ in CATALOG:
        if candidate == key:
            return label
    return key


def draw(painter: QPainter, key: str, size: float) -> None:
    """Paint one sticker into a size x size box at the origin."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    handler = _HANDLERS.get(key)
    if handler is None:
        _fallback(painter, size)
        return
    handler(painter, size)


# ---- eyes ---------------------------------------------------------------


def _eye_base(p: QPainter, s: float, iris: QColor, pupil_width: float) -> None:
    white = QPainterPath()
    white.moveTo(QPointF(s * 0.08, s * 0.50))
    white.quadTo(QPointF(s * 0.50, s * 0.10), QPointF(s * 0.92, s * 0.50))
    white.quadTo(QPointF(s * 0.50, s * 0.90), QPointF(s * 0.08, s * 0.50))
    p.setPen(QPen(DARK, max(1.0, s * 0.035)))
    p.setBrush(WHITE)
    p.drawPath(white)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(iris)
    p.drawEllipse(QPointF(s * 0.50, s * 0.50), s * 0.19, s * 0.19)
    p.setBrush(DARK)
    p.drawEllipse(QPointF(s * 0.50, s * 0.50), s * 0.19 * pupil_width, s * 0.19)
    p.setBrush(WHITE)
    p.drawEllipse(QPointF(s * 0.44, s * 0.43), s * 0.045, s * 0.045)


def _eye(p, s):
    _eye_base(p, s, QColor("#5B8CC8"), 0.55)


def _eye_lash(p, s):
    _eye_base(p, s, QColor("#5B8CC8"), 0.55)
    p.setPen(_pen(DARK, max(1.2, s * 0.05), round_cap=True))
    for angle, length in ((205, 0.16), (225, 0.18), (247, 0.16)):
        radians = math.radians(angle)
        start = QPointF(s * (0.5 + 0.42 * math.cos(radians)), s * (0.5 + 0.30 * math.sin(radians)))
        p.drawLine(start, QPointF(start.x() - s * length * 0.7, start.y() - s * length * 0.7))


def _eye_look_up(p, s):
    _eye_base(p, s, QColor("#5B8CC8"), 0.55)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawRect(QRectF(s * 0.20, s * 0.52, s * 0.60, s * 0.30))
    p.setPen(QPen(DARK, max(1.0, s * 0.035)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(s * 0.08, s * 0.50))
    path.quadTo(QPointF(s * 0.50, s * 0.90), QPointF(s * 0.92, s * 0.50))
    p.drawPath(path)


def _eye_worried(p, s):
    _eye_base(p, s, QColor("#5B8CC8"), 0.55)
    p.setPen(_pen(DARK, max(1.3, s * 0.055), round_cap=True))
    p.drawLine(QPointF(s * 0.14, s * 0.14), QPointF(s * 0.60, s * 0.05))


def _eye_cat(p, s):
    _eye_base(p, s, QColor("#C8A82E"), 0.22)


def _eye_owl(p, s):
    p.setPen(QPen(DARK, max(1.0, s * 0.04)))
    p.setBrush(QColor("#F2C14E"))
    p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.44, s * 0.44)
    p.setBrush(WHITE)
    p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.30, s * 0.30)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(DARK)
    p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.17, s * 0.17)
    p.setBrush(WHITE)
    p.drawEllipse(QPointF(s * 0.44, s * 0.44), s * 0.05, s * 0.05)


def _eye_reptile(p, s):
    _eye_base(p, s, QColor("#7FB24B"), 0.16)


def _eyebrow(p, s):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#5A3B22"))
    brow = QPainterPath()
    brow.moveTo(QPointF(s * 0.08, s * 0.62))
    brow.quadTo(QPointF(s * 0.50, s * 0.24), QPointF(s * 0.92, s * 0.48))
    brow.quadTo(QPointF(s * 0.50, s * 0.42), QPointF(s * 0.08, s * 0.72))
    p.drawPath(brow)


# ---- noses and ears -----------------------------------------------------


def _nose(p, s):
    p.setPen(_pen(QColor("#B8845F"), max(1.2, s * 0.05), round_cap=True))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(s * 0.52, s * 0.12))
    path.quadTo(QPointF(s * 0.40, s * 0.55), QPointF(s * 0.34, s * 0.66))
    path.quadTo(QPointF(s * 0.50, s * 0.82), QPointF(s * 0.66, s * 0.66))
    p.drawPath(path)


def _nose_pig(p, s):
    p.setPen(QPen(QColor("#C9727F"), max(1.0, s * 0.04)))
    p.setBrush(QColor("#F0A5B0"))
    p.drawEllipse(QRectF(s * 0.12, s * 0.24, s * 0.76, s * 0.52))
    p.setBrush(QColor("#A85566"))
    for x in (0.36, 0.64):
        p.drawEllipse(QPointF(s * x, s * 0.50), s * 0.075, s * 0.12)


def _nose_dog(p, s):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(DARK)
    path = QPainterPath()
    path.moveTo(QPointF(s * 0.5, s * 0.82))
    path.quadTo(QPointF(s * 0.06, s * 0.60), QPointF(s * 0.20, s * 0.32))
    path.quadTo(QPointF(s * 0.50, s * 0.16), QPointF(s * 0.80, s * 0.32))
    path.quadTo(QPointF(s * 0.94, s * 0.60), QPointF(s * 0.5, s * 0.82))
    p.drawPath(path)
    p.setBrush(QColor(255, 255, 255, 70))
    p.drawEllipse(QPointF(s * 0.36, s * 0.38), s * 0.09, s * 0.06)


def _nose_mouse(p, s):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#E58FA0"))
    p.drawPolygon(QPolygonF([
        QPointF(s * 0.5, s * 0.74), QPointF(s * 0.18, s * 0.34), QPointF(s * 0.82, s * 0.34),
    ]))


def _ear(p, s):
    p.setPen(QPen(QColor("#B8845F"), max(1.1, s * 0.045)))
    p.setBrush(SKIN)
    outer = QPainterPath(QPointF(s * 0.66, s * 0.10))
    outer.quadTo(QPointF(s * 0.16, s * 0.18), QPointF(s * 0.26, s * 0.58))
    outer.quadTo(QPointF(s * 0.34, s * 0.92), QPointF(s * 0.66, s * 0.84))
    p.drawPath(outer)
    p.setBrush(Qt.BrushStyle.NoBrush)
    inner = QPainterPath(QPointF(s * 0.58, s * 0.28))
    inner.quadTo(QPointF(s * 0.36, s * 0.36), QPointF(s * 0.44, s * 0.64))
    p.drawPath(inner)


def _ear_pig(p, s):
    p.setPen(QPen(QColor("#C9727F"), max(1.0, s * 0.04)))
    p.setBrush(QColor("#F0A5B0"))
    p.drawPolygon(QPolygonF([
        QPointF(s * 0.16, s * 0.88), QPointF(s * 0.30, s * 0.12), QPointF(s * 0.86, s * 0.62),
    ]))


def _ear_dog(p, s):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#8A6240"))
    flop = QPainterPath(QPointF(s * 0.34, s * 0.06))
    flop.quadTo(QPointF(s * 0.92, s * 0.30), QPointF(s * 0.70, s * 0.92))
    flop.quadTo(QPointF(s * 0.34, s * 0.80), QPointF(s * 0.34, s * 0.06))
    p.drawPath(flop)


def _ear_mouse(p, s):
    p.setPen(QPen(QColor("#8A8A8A"), max(1.0, s * 0.04)))
    p.setBrush(QColor("#BFBFBF"))
    p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.44, s * 0.44)
    p.setBrush(QColor("#E9AEB8"))
    p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.26, s * 0.26)


# ---- mouths and accessories ---------------------------------------------


def _mouth_happy(p, s):
    p.setPen(QPen(DARK, max(1.0, s * 0.04)))
    p.setBrush(QColor("#B8354A"))
    smile = QPainterPath(QPointF(s * 0.08, s * 0.36))
    smile.quadTo(QPointF(s * 0.50, s * 0.92), QPointF(s * 0.92, s * 0.36))
    smile.quadTo(QPointF(s * 0.50, s * 0.48), QPointF(s * 0.08, s * 0.36))
    p.drawPath(smile)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawRect(QRectF(s * 0.18, s * 0.37, s * 0.64, s * 0.13))


def _mouth_sad(p, s):
    p.setPen(_pen(DARK, max(1.4, s * 0.06), round_cap=True))
    p.setBrush(Qt.BrushStyle.NoBrush)
    frown = QPainterPath(QPointF(s * 0.12, s * 0.70))
    frown.quadTo(QPointF(s * 0.50, s * 0.24), QPointF(s * 0.88, s * 0.70))
    p.drawPath(frown)


def _mouth_kiss(p, s):
    p.setPen(QPen(QColor("#8E1F33"), max(1.0, s * 0.035)))
    p.setBrush(QColor("#D62C4A"))
    lips = QPainterPath(QPointF(s * 0.10, s * 0.46))
    lips.quadTo(QPointF(s * 0.30, s * 0.16), QPointF(s * 0.50, s * 0.40))
    lips.quadTo(QPointF(s * 0.70, s * 0.16), QPointF(s * 0.90, s * 0.46))
    lips.quadTo(QPointF(s * 0.50, s * 0.94), QPointF(s * 0.10, s * 0.46))
    p.drawPath(lips)


def _mouth_tongue(p, s):
    _mouth_happy(p, s)
    p.setPen(QPen(QColor("#8E1F33"), max(1.0, s * 0.035)))
    p.setBrush(QColor("#E8637A"))
    p.drawEllipse(QRectF(s * 0.34, s * 0.56, s * 0.32, s * 0.38))


def _moustache(p, s):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#3E2A1A"))
    tash = QPainterPath(QPointF(s * 0.50, s * 0.40))
    tash.quadTo(QPointF(s * 0.24, s * 0.18), QPointF(s * 0.04, s * 0.44))
    tash.quadTo(QPointF(s * 0.20, s * 0.80), QPointF(s * 0.50, s * 0.56))
    tash.quadTo(QPointF(s * 0.80, s * 0.80), QPointF(s * 0.96, s * 0.44))
    tash.quadTo(QPointF(s * 0.76, s * 0.18), QPointF(s * 0.50, s * 0.40))
    p.drawPath(tash)


def _spectacles(p, s, lens: QColor, rim: QColor) -> None:
    p.setPen(QPen(rim, max(1.3, s * 0.055)))
    p.setBrush(lens)
    p.drawEllipse(QRectF(s * 0.04, s * 0.30, s * 0.36, s * 0.36))
    p.drawEllipse(QRectF(s * 0.60, s * 0.30, s * 0.36, s * 0.36))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(s * 0.40, s * 0.46), QPointF(s * 0.60, s * 0.46))


def _glasses(p, s):
    _spectacles(p, s, QColor(210, 235, 255, 120), QColor("#4A4A4A"))


def _sunglasses(p, s):
    _spectacles(p, s, QColor("#22303B"), QColor("#101820"))


# ---- objects ------------------------------------------------------------


def _heart(p, s):
    from Clay3D import shapes2d

    p.setPen(QPen(QColor("#8E1F33"), max(1.0, s * 0.04)))
    p.setBrush(QColor("#E8384F"))
    for part in shapes2d.contours("heart", s * 0.06, s * 0.06, s * 0.94, s * 0.94):
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in part]))


def _star(p, s):
    from Clay3D import shapes2d

    p.setPen(QPen(QColor("#B58500"), max(1.0, s * 0.04)))
    p.setBrush(QColor("#FFB900"))
    for part in shapes2d.contours("five_point_star", s * 0.04, s * 0.04, s * 0.96, s * 0.96):
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in part]))


def _sun(p, s):
    p.setPen(_pen(QColor("#E08A00"), max(1.2, s * 0.05), round_cap=True))
    for i in range(8):
        angle = math.pi * i / 4
        p.drawLine(
            QPointF(s * (0.5 + 0.34 * math.cos(angle)), s * (0.5 + 0.34 * math.sin(angle))),
            QPointF(s * (0.5 + 0.47 * math.cos(angle)), s * (0.5 + 0.47 * math.sin(angle))),
        )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FFC83D"))
    p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.28, s * 0.28)


def _cloud(p, s):
    p.setPen(QPen(QColor("#9AB4CC"), max(1.0, s * 0.04)))
    p.setBrush(WHITE)
    puff = QPainterPath()
    puff.addEllipse(QRectF(s * 0.04, s * 0.44, s * 0.42, s * 0.36))
    puff.addEllipse(QRectF(s * 0.26, s * 0.22, s * 0.44, s * 0.46))
    puff.addEllipse(QRectF(s * 0.54, s * 0.42, s * 0.42, s * 0.38))
    puff.addRect(QRectF(s * 0.14, s * 0.58, s * 0.72, s * 0.22))
    p.drawPath(puff.simplified())


def _rainbow(p, s):
    colours = ("#E8384F", "#F58220", "#FFC83D", "#4CAF50", "#2E7BD6", "#7B2D8E")
    width = s * 0.085
    for index, colour in enumerate(colours):
        p.setPen(_pen(QColor(colour), width))
        inset = s * 0.06 + index * width
        p.drawArc(QRectF(inset, inset, s - 2 * inset, s * 1.6 - 2 * inset), 0, 180 * 16)


def _planet(p, s):
    p.setPen(Qt.PenStyle.NoPen)
    body = QRadialGradient(s * 0.40, s * 0.38, s * 0.42)
    body.setColorAt(0.0, QColor("#F0B27A"))
    body.setColorAt(1.0, QColor("#B9722F"))
    p.setBrush(QBrush(body))
    p.drawEllipse(QPointF(s * 0.5, s * 0.48), s * 0.30, s * 0.30)
    p.setPen(QPen(QColor("#D9A066"), max(1.4, s * 0.06)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.save()
    p.translate(s * 0.5, s * 0.52)
    p.rotate(-20)
    p.drawEllipse(QRectF(-s * 0.47, -s * 0.13, s * 0.94, s * 0.26))
    p.restore()


def _spiral(p, s):
    p.setPen(_pen(QColor("#2E7BD6"), max(1.4, s * 0.06), round_cap=True))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    for step in range(140):
        t = step / 139.0
        angle = t * 5.6 * math.pi
        radius = s * 0.46 * (1.0 - t)
        point = QPointF(s * 0.5 + radius * math.cos(angle), s * 0.5 + radius * math.sin(angle))
        path.moveTo(point) if step == 0 else path.lineTo(point)
    p.drawPath(path)


def _lollipop(p, s):
    p.setPen(_pen(QColor("#BDB8B0"), max(1.2, s * 0.05), round_cap=True))
    p.drawLine(QPointF(s * 0.5, s * 0.62), QPointF(s * 0.5, s * 0.96))
    p.setPen(QPen(QColor("#8E1F33"), max(1.0, s * 0.035)))
    p.setBrush(QColor("#F04E6E"))
    p.drawEllipse(QPointF(s * 0.5, s * 0.36), s * 0.31, s * 0.31)
    p.setPen(_pen(WHITE, max(1.4, s * 0.06), round_cap=True))
    swirl = QPainterPath()
    for step in range(70):
        t = step / 69.0
        angle = t * 3.4 * math.pi
        radius = s * 0.28 * (1.0 - t)
        point = QPointF(s * 0.5 + radius * math.cos(angle), s * 0.36 + radius * math.sin(angle))
        swirl.moveTo(point) if step == 0 else swirl.lineTo(point)
    p.drawPath(swirl)


def _ninja_cat(p, s):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2B2B2B"))
    head = QPolygonF([
        QPointF(s * 0.16, s * 0.34), QPointF(s * 0.26, s * 0.08), QPointF(s * 0.40, s * 0.26),
        QPointF(s * 0.60, s * 0.26), QPointF(s * 0.74, s * 0.08), QPointF(s * 0.84, s * 0.34),
        QPointF(s * 0.84, s * 0.70), QPointF(s * 0.16, s * 0.70),
    ])
    p.drawPolygon(head)
    p.setBrush(QColor("#D64545"))
    p.drawRect(QRectF(s * 0.10, s * 0.40, s * 0.80, s * 0.16))
    p.setBrush(QColor("#F2C14E"))
    for x in (0.36, 0.64):
        p.drawEllipse(QPointF(s * x, s * 0.48), s * 0.065, s * 0.045)


# ---- textures -----------------------------------------------------------


def _texture(p, s, base: QColor, accent: QColor, kind: str) -> None:
    """Procedural stand-ins for the eight surface textures."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(base)
    p.drawRect(QRectF(0, 0, s, s))
    p.setPen(QPen(accent, max(1.0, s * 0.03)))
    p.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "stripes":
        for i in range(7):
            x = s * (0.06 + i * 0.14)
            path = QPainterPath(QPointF(x, 0))
            path.cubicTo(QPointF(x + s * 0.05, s * 0.33), QPointF(x - s * 0.05, s * 0.66),
                         QPointF(x, s))
            p.drawPath(path)
    elif kind == "grain":
        for i in range(5):
            y = s * (0.12 + i * 0.19)
            path = QPainterPath(QPointF(0, y))
            path.cubicTo(QPointF(s * 0.33, y - s * 0.06), QPointF(s * 0.66, y + s * 0.06),
                         QPointF(s, y))
            p.drawPath(path)
    elif kind == "speckle":
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        rng = _speckle_positions(kind)
        for x, y, r in rng:
            p.drawEllipse(QPointF(s * x, s * y), s * r, s * r)
    elif kind == "tufts":
        p.setPen(_pen(accent, max(1.0, s * 0.035), round_cap=True))
        for x, y, r in _speckle_positions(kind):
            p.drawLine(QPointF(s * x, s * y), QPointF(s * (x + r), s * (y - r * 2)))
    elif kind == "veins":
        for start, mid, end in (((0.0, 0.7), (0.4, 0.3), (1.0, 0.55)),
                                ((0.0, 0.25), (0.55, 0.6), (1.0, 0.2))):
            path = QPainterPath(QPointF(s * start[0], s * start[1]))
            path.quadTo(QPointF(s * mid[0], s * mid[1]), QPointF(s * end[0], s * end[1]))
            p.drawPath(path)
    else:  # flat wash with a soft mottle
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, r in _speckle_positions(kind):
            p.drawEllipse(QPointF(s * x, s * y), s * r * 1.6, s * r * 1.2)


def _speckle_positions(seed: str):
    """A fixed scatter, so a texture tile looks the same every time."""
    import random

    rng = random.Random(seed)
    return [(rng.random(), rng.random(), 0.02 + rng.random() * 0.05) for _ in range(26)]


_TEXTURES = {
    "bark": (QColor("#7A5A3C"), QColor("#4E3722"), "stripes"),
    "concrete": (QColor("#B6B4B0"), QColor("#95938F"), "mottle"),
    "fur": (QColor("#C2996B"), QColor("#8E6A44"), "tufts"),
    "gravel": (QColor("#9A9793"), QColor("#6E6B67"), "speckle"),
    "hedge": (QColor("#4F7B3A"), QColor("#36592A"), "tufts"),
    "marble": (QColor("#EDEBE6"), QColor("#B9B5AC"), "veins"),
    "sand": (QColor("#DCC9A0"), QColor("#C2AC7E"), "speckle"),
    "wood": (QColor("#C08B4E"), QColor("#8A5E2E"), "grain"),
}


def _fallback(p: QPainter, s: float) -> None:
    p.setPen(QPen(QColor("#8A8886"), 1.0))
    p.setBrush(QColor("#F3F2F1"))
    p.drawRect(QRectF(s * 0.1, s * 0.1, s * 0.8, s * 0.8))


_HANDLERS = {
    "eye": _eye,
    "eye_lash": _eye_lash,
    "eye_look_up": _eye_look_up,
    "eye_worried": _eye_worried,
    "eye_cat": _eye_cat,
    "eye_owl": _eye_owl,
    "eye_reptile": _eye_reptile,
    "eyebrow": _eyebrow,
    "nose": _nose,
    "nose_pig": _nose_pig,
    "nose_dog": _nose_dog,
    "nose_mouse": _nose_mouse,
    "ear": _ear,
    "ear_pig": _ear_pig,
    "ear_dog": _ear_dog,
    "ear_mouse": _ear_mouse,
    "mouth_happy": _mouth_happy,
    "mouth_sad": _mouth_sad,
    "mouth_kiss": _mouth_kiss,
    "mouth_tongue": _mouth_tongue,
    "moustache": _moustache,
    "glasses": _glasses,
    "sunglasses": _sunglasses,
    "heart": _heart,
    "star": _star,
    "sun": _sun,
    "cloud": _cloud,
    "rainbow": _rainbow,
    "planet": _planet,
    "spiral": _spiral,
    "lollipop": _lollipop,
    "ninja_cat": _ninja_cat,
}
_HANDLERS.update(
    {key: (lambda p, s, spec=spec: _texture(p, s, *spec)) for key, spec in _TEXTURES.items()}
)
