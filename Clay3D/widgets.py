"""Dumb panel widgets: tiles, sliders, colour chips."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Clay3D import icons
from Clay3D.theme import ACCENT, LINE, MATERIALS, PALETTE, PALETTE_COLUMNS


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "heading")
    return label


def section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setProperty("role", "section")
    return label


def rule() -> QFrame:
    line = QFrame()
    line.setProperty("role", "rule")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


class Tile(QToolButton):
    """One square tool button: an icon, a tooltip, and a checked state."""

    def __init__(self, key: str, label: str, icon: QIcon, size: int = 40, titled: bool = False):
        super().__init__()
        self.key = key
        self.setProperty("role", "tile")
        self.setIcon(icon)
        self.setIconSize(QSize(size, size))
        self.setToolTip(label)
        self.setCheckable(True)
        self.setAutoRaise(True)
        if titled:
            self.setText(label)
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            self.setFixedSize(size + 24, size + 30)
        else:
            self.setFixedSize(size + 14, size + 14)


class TileGrid(QWidget):
    """A grid of tiles where at most one is chosen at a time."""

    chosen = Signal(str)

    def __init__(self, entries, icon_for, columns: int = 5, size: int = 40,
                 exclusive: bool = True, titled: bool = False):
        super().__init__()
        self.tiles: dict[str, Tile] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(exclusive)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(2)
        for index, (key, label) in enumerate(entries):
            tile = Tile(key, label, icon_for(key), size, titled)
            tile.clicked.connect(lambda checked=False, k=key: self.chosen.emit(k))
            self._group.addButton(tile)
            grid.addWidget(tile, index // columns, index % columns)
            self.tiles[key] = tile
        grid.setColumnStretch(columns, 1)

    def select(self, key: str | None) -> None:
        for tile_key, tile in self.tiles.items():
            tile.setChecked(tile_key == key)

    def selected(self) -> str | None:
        for key, tile in self.tiles.items():
            if tile.isChecked():
                return key
        return None


class SliderRow(QWidget):
    """A labelled slider that shows its own value, like the option dials."""

    changed = Signal(float)

    def __init__(self, label: str, low: float, high: float, value: float, suffix: str = "", steps: int = 0):
        super().__init__()
        self.low = low
        self.high = high
        self.suffix = suffix
        self._scale = steps or 100

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 4, 0, 4)
        box.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.caption = QLabel(label)
        self.value_label = QLabel()
        self.value_label.setProperty("role", "value")
        top.addWidget(self.caption)
        top.addStretch(1)
        top.addWidget(self.value_label)
        box.addLayout(top)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self._scale)
        self.slider.setValue(self._to_slider(value))
        self.slider.valueChanged.connect(self._emit)
        box.addWidget(self.slider)
        self._show(value)

    def _to_slider(self, value: float) -> int:
        span = max(self.high - self.low, 1e-9)
        return int(round((value - self.low) / span * self._scale))

    def _from_slider(self, position: int) -> float:
        return self.low + (position / self._scale) * (self.high - self.low)

    def _emit(self, position: int) -> None:
        value = self._from_slider(position)
        self._show(value)
        self.changed.emit(value)

    def _show(self, value: float) -> None:
        text = f"{value:.0f}" if abs(value) >= 10 or float(value).is_integer() else f"{value:.2f}"
        self.value_label.setText(f"{text}{self.suffix}")

    def set_value(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_slider(value))
        self.slider.blockSignals(False)
        self._show(value)


class Swatch(QToolButton):
    def __init__(self, rgb: tuple[int, int, int], size: int = 20):
        super().__init__()
        self.rgb = rgb
        self.setFixedSize(size, size)
        self.setToolTip(f"rgb{rgb}")
        self.setStyleSheet(
            f"QToolButton {{ background: rgb{rgb}; border: 1px solid {LINE}; }}"
            f"QToolButton:hover {{ border: 2px solid {ACCENT}; }}"
        )


class ColorSection(QWidget):
    """Material and Color block, laid out as the original's 216 px column.

    Material dropdown; current colour beside the eyedropper; 6x3 palette;
    Add color.
    """

    picked = Signal(tuple)
    material_chosen = Signal(int)
    eyedropper = Signal()

    WIDTH = 216

    def __init__(self, color: tuple[int, int, int, int], materials: bool = False):
        super().__init__()
        self._color = color
        self.setFixedWidth(self.WIDTH)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)
        box.addWidget(section("Material and Color"))

        self.material = QComboBox()
        self.material.setFixedHeight(40)
        self.material.setToolTip("Choose a material")
        for name, _, _ in MATERIALS:
            self.material.addItem(name)
        self.material.setEnabled(materials)
        self.material.currentIndexChanged.connect(self.material_chosen.emit)
        box.addWidget(self.material)

        current = QHBoxLayout()
        current.setSpacing(0)
        self.chip = QToolButton()
        self.chip.setFixedSize(144, 48)
        self.chip.setToolTip("Edit color")
        self.chip.clicked.connect(self._open_dialog)
        current.addWidget(self.chip)
        self.pipette = QToolButton()
        self.pipette.setFixedSize(72, 48)
        self.pipette.setCheckable(True)
        self.pipette.setProperty("role", "tile")
        self.pipette.setToolTip("Eyedropper")
        self.pipette.setIcon(icons.ui_icon("pipette", 22))
        self.pipette.setIconSize(QSize(22, 22))
        self.pipette.clicked.connect(lambda checked=False: self.eyedropper.emit())
        current.addWidget(self.pipette)
        box.addLayout(current)

        grid = QGridLayout()
        grid.setSpacing(0)
        for index, rgb in enumerate(PALETTE):
            swatch = Swatch(rgb, 36)
            swatch.clicked.connect(lambda checked=False, c=rgb: self._choose(c))
            grid.addWidget(swatch, index // PALETTE_COLUMNS, index % PALETTE_COLUMNS)
        self._grid = grid
        box.addLayout(grid)

        add = QPushButton("Add color")
        add.setFixedHeight(36)
        add.clicked.connect(self._open_dialog)
        box.addWidget(add)
        self._refresh()

    def _choose(self, rgb: tuple[int, int, int]) -> None:
        self._color = (*rgb, 255)
        self._refresh()
        self.picked.emit(self._color)

    def _open_dialog(self) -> None:
        picker = ColorPickerPopup(self._color, self)
        picker.picked.connect(self._add_custom)
        picker.popup_at(self)

    def _add_custom(self, rgb: tuple[int, int, int]) -> None:
        swatch = Swatch(rgb, 36)
        swatch.clicked.connect(lambda checked=False, c=rgb: self._choose(c))
        slot = self._grid.count()
        self._grid.addWidget(swatch, slot // PALETTE_COLUMNS, slot % PALETTE_COLUMNS)
        self._choose(rgb)

    def set_color(self, color: tuple[int, int, int, int]) -> None:
        self._color = color
        self._refresh()

    def set_eyedropper(self, on: bool) -> None:
        self.pipette.setChecked(on)

    def set_material(self, index: int) -> None:
        self.material.blockSignals(True)
        self.material.setCurrentIndex(index)
        self.material.blockSignals(False)

    def _refresh(self) -> None:
        r, g, b = self._color[:3]
        self.chip.setStyleSheet(
            f"QToolButton {{ background: rgb({r},{g},{b}); border: 1px solid {LINE}; }}"
            f"QToolButton:hover {{ border: 2px solid {ACCENT}; }}"
        )
        self.chip.setToolTip(f"Edit color  #{r:02X}{g:02X}{b:02X}")


class ColorPickerPopup(QWidget):
    """HSV popup. Hue ring + sat/value sliders."""

    picked = Signal(tuple)

    def __init__(self, color: tuple[int, int, int, int], parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setStyleSheet(f"background: white; color: #201F1E; border: 1px solid {LINE};")
        qcolor = QColor(*color[:3])
        self._h, self._s, self._v, _ = qcolor.getHsvF()
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 10, 10, 10)
        self.wheel = QLabel()
        self.wheel.setPixmap(icons.colour_wheel(168))
        self.wheel.setFixedSize(168, 168)
        self.wheel.mousePressEvent = self._pick_hue
        column.addWidget(self.wheel, alignment=Qt.AlignmentFlag.AlignCenter)
        self.sat = SliderRow("Saturation", 0, 100, self._s * 100, "%")
        self.sat.changed.connect(lambda v: self._set(s=v / 100.0))
        column.addWidget(self.sat)
        self.val = SliderRow("Brightness", 0, 100, self._v * 100, "%")
        self.val.changed.connect(lambda v: self._set(v=v / 100.0))
        column.addWidget(self.val)
        self.preview = QLabel()
        self.preview.setFixedHeight(28)
        column.addWidget(self.preview)
        apply = QPushButton("Use this color")
        apply.clicked.connect(self._emit)
        column.addWidget(apply)
        self._paint_preview()

    def popup_at(self, widget: QWidget) -> None:
        self.adjustSize()
        self.move(widget.mapToGlobal(QPoint(0, widget.height())))
        self.show()

    def _pick_hue(self, event: QMouseEvent) -> None:
        import math

        centre = 84.0
        dx, dy = event.position().x() - centre, event.position().y() - centre
        if math.hypot(dx, dy) < 8:
            return
        angle = (math.degrees(math.atan2(-dy, dx)) + 360.0) % 360.0
        # Wheel is drawn from 90° (QConicalGradient), hue 0 at the top.
        self._set(h=((90.0 - angle) % 360.0) / 360.0)

    def _set(self, h=None, s=None, v=None) -> None:
        if h is not None:
            self._h = h
        if s is not None:
            self._s = s
        if v is not None:
            self._v = v
        self._paint_preview()

    def _paint_preview(self) -> None:
        color = QColor.fromHsvF(self._h, max(0.0, min(1.0, self._s)), max(0.0, min(1.0, self._v)))
        self.preview.setStyleSheet(f"background: {color.name()}; border: 1px solid {LINE};")

    def _emit(self) -> None:
        color = QColor.fromHsvF(self._h, max(0.0, min(1.0, self._s)), max(0.0, min(1.0, self._v)))
        self.picked.emit((color.red(), color.green(), color.blue()))
        self.close()


class PanelBody(QWidget):
    """A vertical stack with the panel's standard margins."""

    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("panelBody")
        self.box = QVBoxLayout(self)
        # 24 px gutters either side of a 216 px column.
        self.box.setContentsMargins(24, 12, 24, 12)
        self.box.setSpacing(6)
        self.box.addWidget(heading(title))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def add(self, widget: QWidget) -> QWidget:
        self.box.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self.box.addLayout(layout)

    def finish(self) -> None:
        self.box.addStretch(1)
