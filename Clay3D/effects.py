"""Effects tab filters. 22 swatches from ViewerFilter.Hex. Band amounts are ours."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

# Filter swatches, in panel order.
FILTER_HEXES = (
    ("filter1", "#c4e5e8"),
    ("filter2", "#e7d9ec"),
    ("filter3", "#94ae99"),
    ("filter4", "#73a1ec"),
    ("filter5", "#e3e6f2"),
    ("filter6", "#d0dad9"),
    ("filter7", "#eedde5"),
    ("filter8", "#c4e8e1"),
    ("filter9", "#e0beb4"),
    ("filter10", "#9999b2"),
    ("filter11", "#e9ddbc"),
    ("filter12", "#7b8a94"),
    ("filter13", "#7c8181"),
    ("filter14", "#8a7463"),
    ("filter15", "#daefd9"),
    ("filter16", "#e9b977"),
    ("filter17", "#190b1c"),
    ("filter18", "#1e0a69"),
    ("filter19", "#1e2424"),
    ("filter20", "#8e190f"),
    ("filter21", "#5b665d"),
    ("filter22", "#d9e1e5"),
)

Band = tuple[float, float, float]  # shadows, midtones, highlights


@dataclass(frozen=True)
class Effect:
    """One filter as a colour grade."""

    name: str
    label: str
    swatch: tuple[float, float, float] = (1.0, 1.0, 1.0)
    colour_filter_hue: float = 0.0          # ColorFilterHueGlobal, in turns
    colour_filter_density: Band = (0.0, 0.0, 0.0)
    exposure: Band = (0.0, 0.0, 0.0)
    saturation: Band = (1.0, 1.0, 1.0)
    saturation_global: float = 1.0
    vignette_weight: float = 0.0
    strength: float = 0.0


def _from_hex(name: str, hex_colour: str) -> Effect:
    """Turn a filter's swatch into band settings.

    The swatch is the light the filter puts the scene in, so its hue
    drives the colour filter, its saturation drives how densely that
    colour is applied, and its brightness drives exposure - pushed
    hardest in the shadows, where a change of light shows most.
    """
    value = hex_colour.lstrip("#")
    rgb = tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)
    brightness = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]

    # Punch the grade so pale swatches still read as a look,
    # and colourful ones actually saturate instead of washing the scene.
    density = min(1.0, 0.28 + saturation * 1.35)
    lift = (brightness - 0.55) * 0.85
    sat = 1.15 + saturation * 0.85
    return Effect(
        name=name,
        label=f"Filter {name.removeprefix('filter')}",
        swatch=rgb,
        colour_filter_hue=round(hue, 4),
        colour_filter_density=(
            round(density * 1.2, 4), round(density, 4), round(density * 0.75, 4)
        ),
        exposure=(round(lift * 1.25, 4), round(lift, 4), round(lift * 0.55, 4)),
        saturation=(
            round(sat * 0.95, 4),
            round(sat, 4),
            round(sat * 0.85, 4),
        ),
        saturation_global=round(1.05 + saturation * 0.45, 4),
        vignette_weight=round(max(0.0, 0.4 * (0.55 - brightness)), 4),
        strength=round(0.82 + 0.18 * saturation, 4),
    )


_ALL = (Effect("none", "None"),) + tuple(
    _from_hex(name, hex_colour) for name, hex_colour in FILTER_HEXES
)

EFFECTS: dict[str, Effect] = {effect.name: effect for effect in _ALL}
EFFECT_ORDER: tuple[str, ...] = tuple(effect.name for effect in _ALL)
