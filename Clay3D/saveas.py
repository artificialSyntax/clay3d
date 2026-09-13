"""Save as > Image: a preview of the export beside its options, as the original's.

Sidebar: file type, Pixels/Percent, Transparency, width and height with a
lock, Dimensions and File size, then Save and Cancel.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Clay3D import icons, recent
from Clay3D.chrome import SIDE_PANEL_WIDTH
from Clay3D.io_files import EXPORT_TYPES, encode_image, export_pixels
from Clay3D.theme import STYLESHEET
from Clay3D.widgets import heading, rule

CHECKER = 12   # px, transparency checkerboard in the preview


class PreviewArea(QWidget):
    """The export, scaled to fit, over a checkerboard where it is transparent."""

    def __init__(self):
        super().__init__()
        self.image: QImage | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def show_pixels(self, pixels: np.ndarray) -> None:
        height, width = pixels.shape[:2]
        self.image = QImage(
            np.ascontiguousarray(pixels).tobytes(), width, height, width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#DEE4EA"))
        if self.image is None:
            return
        margin = 40
        scale = min(
            (self.width() - 2 * margin) / self.image.width(),
            (self.height() - 2 * margin) / self.image.height(),
            1.0,
        )
        width, height = self.image.width() * scale, self.image.height() * scale
        target = QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)
        painter.save()
        painter.setClipRect(target)
        for row in range(int(height // CHECKER) + 1):
            for col in range(int(width // CHECKER) + 1):
                shade = QColor("#FFFFFF") if (row + col) % 2 == 0 else QColor("#D8D8DC")
                painter.fillRect(
                    QRectF(target.x() + col * CHECKER, target.y() + row * CHECKER, CHECKER, CHECKER),
                    shade,
                )
        painter.restore()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(target, self.image)


class SaveAsImagePage(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setObjectName("page")
        self.setStyleSheet(STYLESHEET)
        self._syncing = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self._refresh_preview)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.preview = PreviewArea()
        row.addWidget(self.preview, 1)
        row.addWidget(self._sidebar())

    def _sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("saveAsSidebar")
        side.setFixedWidth(SIDE_PANEL_WIDTH)
        box = QVBoxLayout(side)
        box.setContentsMargins(24, 12, 24, 12)
        box.setSpacing(8)
        box.addWidget(heading("Preview"))

        self.file_type = QComboBox()
        self.file_type.setToolTip("Choose a file type")
        for name, _, _ in EXPORT_TYPES:
            self.file_type.addItem(f"{name} (image)", name)
        self.file_type.currentIndexChanged.connect(self._type_changed)
        box.addWidget(self.file_type)

        self.units = QComboBox()
        self.units.addItems(["Pixels", "Percent"])
        self.units.currentTextChanged.connect(lambda _t: self.reset_size())
        box.addWidget(self.units)

        self.transparency = QCheckBox("Transparency")
        self.transparency.toggled.connect(lambda _on: self._schedule())
        box.addWidget(self.transparency)

        grid = QGridLayout()
        grid.addWidget(QLabel("Width"), 0, 0)
        grid.addWidget(QLabel("Height"), 0, 2)
        self.width_box = QSpinBox()
        self.height_box = QSpinBox()
        for spin in (self.width_box, self.height_box):
            spin.setRange(1, 20000)
        self.lock = QToolButton()
        self.lock.setProperty("role", "tile")
        self.lock.setCheckable(True)
        self.lock.setChecked(True)
        self.lock.setIcon(icons.ui_icon("lock", 16))
        self.lock.setToolTip("Lock aspect ratio")
        grid.addWidget(self.width_box, 1, 0)
        grid.addWidget(self.lock, 1, 1)
        grid.addWidget(self.height_box, 1, 2)
        box.addLayout(grid)
        self.width_box.valueChanged.connect(lambda v: self._follow(v, self.width_box))
        self.height_box.valueChanged.connect(lambda v: self._follow(v, self.height_box))
        box.addWidget(rule())

        self.dimensions = QLabel()
        self.file_size = QLabel()
        for label, value in (("Dimensions", self.dimensions), ("File size", self.file_size)):
            caption = QLabel(label)
            caption.setProperty("role", "section")
            box.addWidget(caption)
            value.setProperty("role", "value")
            box.addWidget(value)
        box.addStretch(1)

        save = QPushButton("Save")
        save.setProperty("role", "primary")
        save.clicked.connect(self.save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.editor.close_save_as)
        box.addWidget(save)
        box.addWidget(cancel)
        return side

    # ---- state ----------------------------------------------------------------

    def open_for(self) -> None:
        """Called each time the page is shown: start from the canvas as it is."""
        canvas = self.editor.canvas
        self.transparency.blockSignals(True)
        self.transparency.setChecked(canvas.background[3] == 0)
        self.transparency.blockSignals(False)
        self.reset_size()
        self._type_changed()

    def reset_size(self) -> None:
        canvas = self.editor.canvas
        self._syncing = True
        if self.units.currentText() == "Percent":
            self.width_box.setValue(100)
            self.height_box.setValue(100)
        else:
            self.width_box.setValue(canvas.width)
            self.height_box.setValue(canvas.height)
        self._syncing = False
        self._schedule()

    def output_size(self) -> tuple[int, int]:
        canvas = self.editor.canvas
        if self.units.currentText() == "Percent":
            return (
                max(1, round(canvas.width * self.width_box.value() / 100)),
                max(1, round(canvas.height * self.height_box.value() / 100)),
            )
        return self.width_box.value(), self.height_box.value()

    def type_name(self) -> str:
        return self.file_type.currentData()

    def output_pixels(self) -> np.ndarray:
        width, height = self.output_size()
        transparent = self.transparency.isChecked() and self.transparency.isEnabled()
        return export_pixels(self.editor.canvas.pixels, width, height, transparent)

    def _type_changed(self, _index: int = 0) -> None:
        keeps_alpha = dict((name, alpha) for name, _, alpha in EXPORT_TYPES)[self.type_name()]
        self.transparency.setEnabled(keeps_alpha)
        self._schedule()

    def _follow(self, value: int, source) -> None:
        if self._syncing:
            return
        if self.lock.isChecked():
            self._syncing = True
            other = self.height_box if source is self.width_box else self.width_box
            if self.units.currentText() == "Percent":
                other.setValue(value)
            else:
                canvas = self.editor.canvas
                ratio = canvas.width / max(canvas.height, 1)
                other.setValue(max(1, round(value / ratio if source is self.width_box else value * ratio)))
            self._syncing = False
        self._schedule()

    def _schedule(self) -> None:
        # Re-encoding for File size is not free; wait for typing to settle.
        self._refresh_timer.start()

    def _refresh_preview(self) -> None:
        pixels = self.output_pixels()
        self.preview.show_pixels(pixels)
        height, width = pixels.shape[:2]
        self.dimensions.setText(f"{width} x {height} px")
        size_kb = max(1, round(len(encode_image(pixels, self.type_name())) / 1024))
        self.file_size.setText(f"{size_kb} kb")

    # ---- actions ---------------------------------------------------------------

    def save(self) -> None:
        name = self.type_name()
        suffix = dict((n, s) for n, s, _ in EXPORT_TYPES)[name]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as", f"artwork{suffix}", f"{name} (*{suffix} *{suffix.upper()})"
        )
        if not path:
            return
        if not path.lower().endswith(suffix) and not (name == "JPEG" and path.lower().endswith(".jpeg")):
            path += suffix
        self.write(path)
        self.editor.close_save_as()

    def write(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(encode_image(self.output_pixels(), self.type_name()))
        recent.remember(path)
