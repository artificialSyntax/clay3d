"""Custom stickers kept between sessions, as PNGs in the app's data folder."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QStandardPaths

from Clay3D.document import write_atomically


def library_dir() -> Path:
    # CLAY3D_STICKER_DIR keeps tests away from the real folder.
    override = os.environ.get("CLAY3D_STICKER_DIR")
    if override:
        folder = Path(override)
    else:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        folder = Path(base or Path.home() / ".local/share/Clay3D") / "stickers"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_all() -> list[np.ndarray]:
    """Every kept sticker as RGBA pixels, oldest first. Unreadable files are skipped."""
    stickers = []
    for path in sorted(library_dir().glob("*.png"), key=lambda p: p.stat().st_mtime):
        try:
            with Image.open(path) as image:
                stickers.append(np.array(image.convert("RGBA")))
        except OSError:
            continue
    return stickers


def keep(pixels: np.ndarray) -> None:
    """Save a new custom sticker. A failed write only means it won't come back next time."""
    path = library_dir() / f"{uuid.uuid4().hex[:12]}.png"
    try:
        write_atomically(path, lambda temp: Image.fromarray(pixels, "RGBA").save(temp, "PNG"))
    except OSError:
        pass
