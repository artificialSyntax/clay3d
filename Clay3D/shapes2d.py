"""2D outlines in a unit box. ShapeType order. Curves = dense polylines."""

from __future__ import annotations

import math

# Name, label. Panel order; labels are Paint 3D's.
SHAPE_TYPES = (
    ("rectangle", "Square"),
    ("circle", "Circle"),
    ("diamond", "Diamond"),
    ("pentagon", "Pentagon"),
    ("hexagon", "Hexagon"),
    ("triangle", "Triangle"),
    ("right_triangle", "Right triangle"),
    ("arrow", "Arrow"),
    ("four_point_star", "Star: 4 points"),
    ("five_point_star", "Star: 5 points"),
    ("six_point_star", "Star: 6 points"),
    ("heart", "Heart"),
    ("lightning", "Lightning bolt"),
    ("round_rectangle", "Rounded Square"),
    ("check_mark", "Check mark"),
    ("capsule", "Capsule"),
    ("pointed_arrow", "Pointed arrow"),
    ("half_arc", "Arc"),
    ("multi_point_star", "Multipoint star"),
    ("speech_bubble", "Speech bubble"),
    ("thought_bubble", "Thought bubble"),
    ("cross", "Cross"),
    ("moon", "Moon"),
    ("banner", "Banner"),
)

# The original labels this control "Line type" and shows icons without
# names, so these captions are tooltips only.
LINE_TYPES = (
    ("straight", "Line"),
    ("curve", "Curve"),
    ("polygon", "Polygon"),
)

CURVE_STEPS = 64


def contours(kind: str, x0: float, y0: float, x1: float, y1: float) -> list[list[tuple[float, float]]]:
    """The shape's closed contours, fitted to the dragged rectangle.

    Most shapes are one ring. A few - the thought bubble's puffs - are
    genuinely several, so every caller gets a list either way.
    """
    if kind not in _UNIT_SHAPES:
        raise ValueError(f"unknown shape: {kind}")
    left, right = min(x0, x1), max(x0, x1)
    top, bottom = min(y0, y1), max(y0, y1)
    width = max(right - left, 1e-6)
    height = max(bottom - top, 1e-6)
    parts = _UNIT_SHAPES[kind]()
    if parts and isinstance(parts[0][0], (int, float)):
        parts = [parts]
    return [[(left + u * width, top + v * height) for u, v in part] for part in parts]


def outline(kind: str, x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    """The shape's main contour. Convenience for callers wanting one ring."""
    return contours(kind, x0, y0, x1, y1)[0]


def _regular(sides: int, rotation: float = -math.pi / 2) -> list[tuple[float, float]]:
    """A regular polygon inscribed in the unit box."""
    return [
        (
            0.5 + 0.5 * math.cos(rotation + 2 * math.pi * i / sides),
            0.5 + 0.5 * math.sin(rotation + 2 * math.pi * i / sides),
        )
        for i in range(sides)
    ]


def _star(points: int, inner: float) -> list[tuple[float, float]]:
    result = []
    for i in range(points * 2):
        radius = 0.5 if i % 2 == 0 else 0.5 * inner
        angle = -math.pi / 2 + math.pi * i / points
        result.append((0.5 + radius * math.cos(angle), 0.5 + radius * math.sin(angle)))
    return result


def _arc(
    cx: float, cy: float, rx: float, ry: float, start: float, end: float, steps: int = CURVE_STEPS
) -> list[tuple[float, float]]:
    return [
        (cx + rx * math.cos(start + (end - start) * i / steps),
         cy + ry * math.sin(start + (end - start) * i / steps))
        for i in range(steps + 1)
    ]


def _rectangle():
    return [(0, 0), (1, 0), (1, 1), (0, 1)]


def _circle():
    return _arc(0.5, 0.5, 0.5, 0.5, 0.0, 2 * math.pi)[:-1]


def _diamond():
    return [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]


def _triangle():
    return [(0.5, 0), (1, 1), (0, 1)]


def _right_triangle():
    return [(0, 0), (1, 1), (0, 1)]


def _arrow():
    """A block arrow pointing right."""
    return [
        (0, 0.32), (0.58, 0.32), (0.58, 0.08), (1, 0.5),
        (0.58, 0.92), (0.58, 0.68), (0, 0.68),
    ]


def _pointed_arrow():
    """A slim arrowhead on a tail, pointing right."""
    return [
        (0, 0.38), (0.50, 0.38), (0.38, 0.06), (1, 0.5),
        (0.38, 0.94), (0.50, 0.62), (0, 0.62),
    ]


def _heart():
    raw = []
    for i in range(CURVE_STEPS):
        t = 2 * math.pi * i / CURVE_STEPS
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        raw.append((x, -y))
    return _fit_to_unit_box(raw)


def _lightning():
    return [
        (0.54, 0), (0.16, 0.55), (0.44, 0.55), (0.28, 1),
        (0.84, 0.40), (0.52, 0.40), (0.80, 0),
    ]


def _round_rectangle(radius: float = 0.18):
    r = radius
    corners = [
        (1 - r, r, -math.pi / 2, 0.0),
        (1 - r, 1 - r, 0.0, math.pi / 2),
        (r, 1 - r, math.pi / 2, math.pi),
        (r, r, math.pi, 1.5 * math.pi),
    ]
    points = []
    for cx, cy, start, end in corners:
        points.extend(_arc(cx, cy, r, r, start, end, steps=10))
    return points


def _check_mark():
    return [
        (0.08, 0.50), (0.22, 0.36), (0.40, 0.60), (0.78, 0.10),
        (0.94, 0.24), (0.40, 0.92),
    ]


def _capsule():
    r = 0.5
    return (
        _arc(1 - r, 0.5, r, 0.5, -math.pi / 2, math.pi / 2, steps=24)
        + _arc(r, 0.5, r, 0.5, math.pi / 2, 1.5 * math.pi, steps=24)
    )


def _half_arc(thickness: float = 0.34):
    """An open ring, half swept."""
    outer = _arc(0.5, 1.0, 0.5, 1.0, math.pi, 2 * math.pi, steps=40)
    inner = _arc(0.5, 1.0, 0.5 - thickness / 2, 1.0 - thickness, 2 * math.pi, math.pi, steps=40)
    return outer + inner


def _speech_bubble():
    body = _round_rectangle(0.16)
    scaled = [(x, 0.10 + y * 0.66) for x, y in body]
    tail = [(0.30, 0.76), (0.24, 1.0), (0.46, 0.76)]
    return _splice(scaled, tail, at=(0.30, 0.76))


def _thought_bubble():
    """A cloud with two trailing puffs, each its own contour."""
    body = [(x, 0.04 + y * 0.62) for x, y in _arc(0.5, 0.5, 0.5, 0.5, 0.0, 2 * math.pi)[:-1]]
    puffs = [
        _arc(cx, cy, r, r, 0.0, 2 * math.pi, steps=16)[:-1]
        for cx, cy, r in ((0.32, 0.80, 0.10), (0.20, 0.93, 0.062))
    ]
    return [body, *puffs]


def _cross(arm: float = 0.32):
    low, high = 0.5 - arm / 2, 0.5 + arm / 2
    return [
        (low, 0), (high, 0), (high, low), (1, low),
        (1, high), (high, high), (high, 1), (low, 1),
        (low, high), (0, high), (0, low), (low, low),
    ]


def _moon():
    """A crescent: two arcs meeting exactly at the horns."""
    outer = _arc(0.5, 0.5, 0.5, 0.5, math.pi / 2, 1.5 * math.pi, steps=40)
    inner = _arc(0.5, 0.5, 0.20, 0.5, 1.5 * math.pi, math.pi / 2, steps=40)
    return outer + inner[1:-1]


def _banner():
    return [
        (0, 0.12), (1, 0.12), (1, 0.88), (0.76, 0.68),
        (0.5, 0.88), (0.24, 0.68), (0, 0.88),
    ]


def _fit_to_unit_box(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Rescale a parametric curve so it exactly fills the unit box."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width = max(max(xs) - min(xs), 1e-9)
    height = max(max(ys) - min(ys), 1e-9)
    return [((x - min(xs)) / width, (y - min(ys)) / height) for x, y in points]


def _splice(ring, insert, at):
    """Drop a tail into a ring at the vertex nearest `at`."""
    index = min(range(len(ring)), key=lambda i: (ring[i][0] - at[0]) ** 2 + (ring[i][1] - at[1]) ** 2)
    return ring[: index + 1] + insert + ring[index + 1 :]


_UNIT_SHAPES = {
    "rectangle": _rectangle,
    "circle": _circle,
    "diamond": _diamond,
    "pentagon": lambda: _regular(5),
    "hexagon": lambda: _regular(6),
    "triangle": _triangle,
    "right_triangle": _right_triangle,
    "arrow": _arrow,
    "four_point_star": lambda: _star(4, 0.38),
    "five_point_star": lambda: _star(5, 0.42),
    "six_point_star": lambda: _star(6, 0.55),
    "heart": _heart,
    "lightning": _lightning,
    "round_rectangle": _round_rectangle,
    "check_mark": _check_mark,
    "capsule": _capsule,
    "pointed_arrow": _pointed_arrow,
    "half_arc": _half_arc,
    "multi_point_star": lambda: _star(12, 0.62),
    "speech_bubble": _speech_bubble,
    "thought_bubble": _thought_bubble,
    "cross": _cross,
    "moon": _moon,
    "banner": _banner,
}


def line_path(kind: str, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Turn the control points of a line tool into the path to stroke."""
    if len(points) < 2:
        return list(points)
    if kind == "straight":
        return [points[0], points[-1]]
    if kind == "polygon":
        return list(points)
    if kind == "curve":
        return _catmull_rom(points)
    raise ValueError(f"unknown line type: {kind}")


def _catmull_rom(points: list[tuple[float, float]], per_span: int = 16):
    """A smooth curve that actually passes through every control point."""
    if len(points) == 2:
        return list(points)
    padded = [points[0]] + list(points) + [points[-1]]
    curve = []
    for p0, p1, p2, p3 in zip(padded, padded[1:], padded[2:], padded[3:]):
        for i in range(per_span):
            t = i / per_span
            t2, t3 = t * t, t * t * t
            curve.append(
                (
                    0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                           + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                           + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                    0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                           + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                           + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
                )
            )
    curve.append(points[-1])
    return curve
