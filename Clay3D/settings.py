"""Menu > Settings values that last between launches (QSettings)."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings

QUALITY_LEVELS = ("Normal", "High", "Ultra")
DEFAULTS = {"compact_view": False, "show_perspective": True, "display_quality": "High"}


def _store() -> QSettings:
    # CLAY3D_SETTINGS_FILE points at a throwaway ini, so tests never touch the real one.
    path = os.environ.get("CLAY3D_SETTINGS_FILE")
    if path:
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings("Clay3D", "Clay3D")


def load(key: str):
    default = DEFAULTS[key]
    value = _store().value(key, default)
    if isinstance(default, bool):
        # QSettings hands booleans back as the strings "true"/"false".
        return value in (True, "true", "1", 1)
    return value if value in QUALITY_LEVELS or key != "display_quality" else default


def save(key: str, value) -> None:
    _store().setValue(key, value)
