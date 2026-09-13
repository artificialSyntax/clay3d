"""Effects tab filters: the original's names, swatches and order. Band amounts are ours."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

# key, label, swatch: the original's filters in its order. Default is the
# plain look; the last six are the Minecraft set, listed after the rest.
FILTERS = (
    ("default", "Default", "#d9e1e5"),
    ("lavender", "Lavender", "#e3e6f2"),
    ("candy", "Candy", "#eedde5"),
    ("taffy", "Taffy", "#e7d9ec"),
    ("spearmint", "Spearmint", "#daefd9"),
    ("sand", "Sand", "#e9ddbc"),
    ("tan", "Tan", "#e0beb4"),
    ("honey", "Honey", "#e9b977"),
    ("mist", "Mist", "#d0dad9"),
    ("aqua", "Aqua", "#c4e8e1"),
    ("sky", "Sky", "#c4e5e8"),
    ("canterbury", "Canterbury", "#9999b2"),
    ("spruce", "Spruce", "#94ae99"),
    ("stone", "Stone", "#7b8a94"),
    ("stratus", "Stratus", "#7c8181"),
    ("clay", "Clay", "#8a7463"),
    ("minecraft_day", "Day (Minecraft)", "#73a1ec"),
    ("minecraft_night", "Night (Minecraft)", "#190b1c"),
    ("minecraft_underwater", "Underwater (Minecraft)", "#1e0a69"),
    ("minecraft_cave", "Cave (Minecraft)", "#1e2424"),
    ("minecraft_nether", "Nether (Minecraft)", "#8e190f"),
    ("minecraft_end", "The End (Minecraft)", "#5b665d"),
)

DEFAULT_EFFECT = "default"

# Keys used by older Clay3D scenes, matched to the filter with the same swatch.
LEGACY_KEYS = {
    "none": "default", "filter1": "sky", "filter2": "taffy", "filter3": "spruce", "filter4": "minecraft_day",
    "filter5": "lavender", "filter6": "mist", "filter7": "candy", "filter8": "aqua", "filter9": "tan",
    "filter10": "canterbury", "filter11": "sand", "filter12": "stone", "filter13": "stratus", "filter14": "clay",
    "filter15": "spearmint", "filter16": "honey", "filter17": "minecraft_night", "filter18": "minecraft_underwater",
    "filter19": "minecraft_cave", "filter20": "minecraft_nether", "filter21": "minecraft_end", "filter22": "default",
}


def effect_key(name: str) -> str:
    """Today's key for a stored effect name, old scenes included."""
    return LEGACY_KEYS.get(name, name if name in EFFECTS else DEFAULT_EFFECT)


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


def _from_hex(name: str, label: str, hex_colour: str) -> Effect:
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
        label=label,
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


_ALL = (Effect("default", "Default", swatch=(217 / 255, 225 / 255, 229 / 255)),) + tuple(
    _from_hex(name, label, hex_colour) for name, label, hex_colour in FILTERS[1:]
)

EFFECTS: dict[str, Effect] = {effect.name: effect for effect in _ALL}
EFFECT_ORDER: tuple[str, ...] = tuple(effect.name for effect in _ALL)
