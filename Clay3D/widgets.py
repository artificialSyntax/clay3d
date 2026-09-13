"""Dumb panel widgets: tiles, sliders, colour chips."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QIntValidator, QLinearGradient, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Clay3D import icons
from Clay3D.theme import ACCENT, INK, LINE, MATERIALS, PALETTE, PALETTE_COLUMNS


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
        self.chip.clicked.connect(self._edit_color)
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
        add.clicked.connect(self._add_color)
        box.addWidget(add)
        self._refresh()

    def _choose(self, rgb: tuple[int, int, int]) -> None:
        self._color = (*rgb, 255)
        self._refresh()
        self.picked.emit(self._color)

    def _edit_color(self) -> None:
        rgb = ColorPickerDialog.choose(self._color, ColorPickerDialog.EDIT_TITLE, self)
        if rgb is not None:
            self._choose(rgb)

    def _add_color(self) -> None:
        rgb = ColorPickerDialog.choose(self._color, ColorPickerDialog.ADD_TITLE, self)
        if rgb is not None:
            self._add_custom(rgb)

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


class SaturationValueSquare(QWidget):
    """298 x 260: saturation left to right, brightness top to bottom, over the hue."""

    changed = Signal()

    def __init__(self, picker: "ColorPickerDialog"):
        super().__init__()
        self.picker = picker
        self.setFixedSize(298, 260)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = QRectF(self.rect())
        painter.fillRect(rect, QColor.fromHsvF(self.picker.hue, 1.0, 1.0))
        whites = QLinearGradient(rect.topLeft(), rect.topRight())
        whites.setColorAt(0.0, QColor(255, 255, 255, 255))
        whites.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(rect, whites)
        blacks = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        blacks.setColorAt(0.0, QColor(0, 0, 0, 0))
        blacks.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, blacks)
        # The 29 px selection ring.
        at = QPointF(self.picker.saturation * self.width(), (1.0 - self.picker.value) * self.height())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#000000"), 2))
        painter.drawEllipse(at, 13.5, 13.5)
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.drawEllipse(at, 11.5, 11.5)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._pick(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._pick(event)

    def _pick(self, event: QMouseEvent) -> None:
        x = min(max(event.position().x() / self.width(), 0.0), 1.0)
        y = min(max(event.position().y() / self.height(), 0.0), 1.0)
        self.picker.set_hsv(saturation=x, value=1.0 - y)


class HueSlider(QWidget):
    """The rainbow strip under the square."""

    def __init__(self, picker: "ColorPickerDialog"):
        super().__init__()
        self.picker = picker
        self.setFixedSize(298, 32)
        self.setToolTip("Color")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(0, 8, self.width(), 16)
        rainbow = QLinearGradient(track.topLeft(), track.topRight())
        for step in range(7):
            rainbow.setColorAt(step / 6, QColor.fromHsvF(min(step / 6, 0.9999), 1.0, 1.0))
        painter.fillRect(track, rainbow)
        x = self.picker.hue * self.width()
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.setBrush(QColor.fromHsvF(self.picker.hue, 1.0, 1.0))
        painter.drawEllipse(QPointF(min(max(x, 9.0), self.width() - 9.0), 16.0), 9.0, 9.0)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._pick(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._pick(event)

    def _pick(self, event: QMouseEvent) -> None:
        hue = min(max(event.position().x() / self.width(), 0.0), 0.9999)
        self.picker.set_hsv(hue=hue)


class ColorPickerDialog(QDialog):
    """The original's colour dialog.

    Title ("Choose a new color" or "Edit color"), the saturation/brightness
    square with the hue strip under it, the chosen colour, Red, Green, Blue
    and Hex boxes, then OK and Cancel.
    """

    ADD_TITLE = "Choose a new color"
    EDIT_TITLE = "Edit color"

    def __init__(self, color: tuple[int, ...], title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(f"QDialog {{ background: white; color: {INK}; }}")
        self.hue, self.saturation, self.value, _ = QColor(*color[:3]).getHsvF()
        self.hue = max(self.hue, 0.0)   # greys report hue -1
        self._syncing = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 28, 24, 24)
        outer.setSpacing(0)
        header = QLabel(title)
        header.setStyleSheet("font-size: 15px;")
        outer.addWidget(header)
        outer.addSpacing(16)

        body = QHBoxLayout()
        body.setSpacing(0)
        left = QVBoxLayout()
        left.setSpacing(8)
        self.square = SaturationValueSquare(self)
        self.hue_slider = HueSlider(self)
        left.addWidget(self.square)
        left.addWidget(self.hue_slider)
        body.addLayout(left)

        right = QVBoxLayout()
        right.setContentsMargins(24, 0, 0, 0)
        right.setSpacing(0)
        self.preview = QLabel()
        self.preview.setFixedSize(89, 89)
        right.addWidget(self.preview)
        right.addSpacing(4)
        self.red = self._number_box(right, "Red")
        self.green = self._number_box(right, "Green")
        self.blue = self._number_box(right, "Blue")
        self.hex = self._text_box(right, "Hex")
        right.addStretch(1)
        body.addLayout(right)
        outer.addLayout(body)
        outer.addSpacing(24)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        ok = QPushButton("OK")
        ok.setProperty("role", "primary")
        ok.setFixedHeight(48)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(48)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        outer.addLayout(buttons)
        self.setFixedWidth(463)
        self._show_color()

    @classmethod
    def choose(cls, color: tuple[int, ...], title: str, parent=None) -> tuple[int, int, int] | None:
        """Open the dialog; the colour picked, or None on Cancel."""
        dialog = cls(color, title, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.rgb()

    def rgb(self) -> tuple[int, int, int]:
        color = QColor.fromHsvF(self.hue, self.saturation, self.value)
        return (color.red(), color.green(), color.blue())

    def set_hsv(self, hue=None, saturation=None, value=None) -> None:
        if hue is not None:
            self.hue = hue
        if saturation is not None:
            self.saturation = saturation
        if value is not None:
            self.value = value
        self._show_color()

    def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        hue, self.saturation, self.value, _ = QColor(*rgb).getHsvF()
        if hue >= 0:
            self.hue = hue
        self._show_color()

    # ---- boxes ------------------------------------------------------------

    def _caption(self, column: QVBoxLayout, text: str) -> None:
        caption = QLabel(text)
        caption.setContentsMargins(0, 2, 0, 5)
        column.addWidget(caption)

    def _number_box(self, column: QVBoxLayout, text: str) -> QLineEdit:
        self._caption(column, text)
        box = QLineEdit()
        box.setFixedSize(89, 28)
        box.setToolTip(text)
        box.setValidator(QIntValidator(0, 255, box))
        box.textEdited.connect(lambda _t: self._rgb_typed())
        column.addWidget(box)
        return box

    def _text_box(self, column: QVBoxLayout, text: str) -> QLineEdit:
        self._caption(column, text)
        box = QLineEdit()
        box.setFixedSize(89, 28)
        box.setToolTip(text)
        box.setMaxLength(7)
        box.textEdited.connect(self._hex_typed)
        column.addWidget(box)
        return box

    def _rgb_typed(self) -> None:
        values = [box.text() for box in (self.red, self.green, self.blue)]
        if all(v.isdigit() for v in values):
            self._from_typing(tuple(min(int(v), 255) for v in values))

    def _hex_typed(self, text: str) -> None:
        digits = text.lstrip("#")
        if len(digits) == 6 and all(c in "0123456789abcdefABCDEF" for c in digits):
            self._from_typing(tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4)))

    def _from_typing(self, rgb: tuple[int, int, int]) -> None:
        # Keep what is being typed where it is; update everything else.
        self._syncing = True
        self.set_rgb(rgb)
        self._syncing = False

    def _show_color(self) -> None:
        r, g, b = self.rgb()
        self.preview.setStyleSheet(f"background: rgb({r},{g},{b}); border: 2px solid rgba(0,0,0,40);")
        focused = self.focusWidget()
        for box, text in (
            (self.red, str(r)), (self.green, str(g)), (self.blue, str(b)), (self.hex, f"#{r:02X}{g:02X}{b:02X}"),
        ):
            if not (self._syncing and box is focused):
                box.setText(text)
        self.square.update()
        self.hue_slider.update()


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
