"""Tunable amounts: brushes, primitives, camera, lighting, controls."""

from __future__ import annotations

# ---- brushes ------------------------------------------------------------
# Per-brush flow.
BRUSH_FLOW = {
    "marker": 1.0,
    "calligraphy": 1.0,
    "oil": 0.55,
    "watercolor": 0.16,
    "pixel": 1.0,
    "pencil": 0.35,
    "crayon": 0.45,
    "spray": 0.10,
    "eraser": 1.0,
    "smudge": 0.55,
}
BRUSH_DAB_SPACING = {
    "marker": 0.15,
    "calligraphy": 0.15,
    "oil": 0.10,
    "watercolor": 0.08,
    "pixel": 0.5,
    "pencil": 0.07,
    "crayon": 0.09,
    "spray": 0.22,
    "eraser": 0.15,
    "smudge": 0.05,
}

# ---- 3D primitives ------------------------------------------------------
# Every primitive fills the unit cube; these are the proportions a shape
# needs beyond that rule.
CAPSULE_RADIUS = 0.3
TORUS_MAJOR_RADIUS = 0.34
TORUS_MINOR_RADIUS = 0.16
PIPE_INNER_RADIUS = 0.32

# ---- 3D doodle and tube -------------------------------------------------
# How far a doodle stands off the paper, as a fraction of its own size.
DOODLE_SOFT_THICKNESS = 0.22
DOODLE_SHARP_THICKNESS = 0.55 * DOODLE_SOFT_THICKNESS

# ---- camera -------------------------------------------------------------
CAMERA_FIELD_OF_VIEW = 38.0
CAMERA_START_DISTANCE = 8.0
CAMERA_START_PITCH = 0.28

# ---- lighting -----------------------------------------------------------
# Angle offset, colour, intensity, height.
LIGHT_RIG = (
    (0.6, (1.0, 0.98, 0.94), 0.62, 0.72),     # key
    (3.4, (0.88, 0.92, 1.0), 0.20, 0.15),     # fill
    (2.1, (1.0, 0.96, 0.90), 0.14, -0.35),    # rim, from below and behind
)
ENVIRONMENT_COLOR = (0.94, 0.96, 1.0)
ENVIRONMENT_INTENSITY = 0.42

# ---- controls -----------------------------------------------------------
BRUSH_SIZE_RANGE = (1, 120)
SHAPE_THICKNESS_RANGE = (1, 60)
TUBE_WEIGHT_RANGE = (2, 200)
STICKER_SIZE_RANGE = (16, 400)

# ---- documents ----------------------------------------------------------
CANVAS_DEFAULT_SIZE = (1152, 768)
UNDO_DEPTH = 24
