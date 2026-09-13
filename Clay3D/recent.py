"""Saved projects: files recently opened or saved, newest first, kept in QSettings."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSettings

from Clay3D import settings

LIMIT = 12
THUMB = 96


def _settings() -> QSettings:
    return settings._store()


def recent_files() -> list[str]:
    stored = _settings().value("recent_files", [])
    if isinstance(stored, str):
        stored = [stored]
    return [path for path in (stored or []) if Path(path).is_file()]


def remember(path: str | Path) -> None:
    path = str(Path(path).resolve())
    files = [p for p in recent_files() if p != path]
    _settings().setValue("recent_files", [path, *files][:LIMIT])


def forget_all() -> None:
    _settings().remove("recent_files")


def thumbnail(path: str) -> Image.Image | None:
    """A small RGBA preview: the image itself, or a project's canvas."""
    try:
        if path.lower().endswith(".clay3d"):
            with zipfile.ZipFile(path) as archive:
                image = Image.open(BytesIO(archive.read("canvas.png")))
        else:
            image = Image.open(path)
        image = image.convert("RGBA")
        image.thumbnail((THUMB, THUMB))
        return image
    except (OSError, KeyError, zipfile.BadZipFile, ValueError):
        return None
