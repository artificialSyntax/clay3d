"""Right-hand panels. One class per tab. refresh() follows selection."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Clay3D import brushes, icons, shapes2d, stickers, tube
from Clay3D.effects import EFFECT_ORDER, EFFECTS
from Clay3D.scene3d import SHAPE3D_TYPES
from Clay3D.tuning import (
    BRUSH_SIZE_RANGE,
    SHAPE_THICKNESS_RANGE,
    TUBE_WEIGHT_RANGE,
)
from Clay3D.widgets import ColorSection, PanelBody, SliderRow, TileGrid, rule, section

# 3D doodle row, as the original orders it.
DOODLES = (("doodle_sharp", "Sharp edge"), ("doodle_soft", "Soft edge"), ("tube", "Tube brush"))

# 3D objects grid order.
SHAPE3D_ORDER = (
    "cube", "sphere", "hemisphere", "cone", "pyramid",
    "cylinder", "pipe", "capsule", "quarter_torus", "torus",
)

TILE = 28           # icon size; a tile is TILE + 14 wide, five fit in 216 px


def icon_row(entries, handler, size: int = 20) -> QHBoxLayout:
    """A row of icon buttons: (icon, tooltip, callback)."""
    row = QHBoxLayout()
    row.setSpacing(2)
    for icon_name, tooltip, callback in entries:
        button = QToolButton()
        button.setProperty("role", "tile")
        button.setIcon(icons.ui_icon(icon_name, size))
        button.setIconSize(QSize(size, size))
        button.setFixedSize(size + 22, size + 22)
        button.setToolTip(tooltip)
        button.clicked.connect(lambda checked=False, fn=callback: handler(fn))
        row.addWidget(button)
    row.addStretch(1)
    return row


def text_and_icon(icon_name: str, text: str, callback) -> QToolButton:
    button = QToolButton()
    button.setProperty("role", "action")
    button.setText(text)
    button.setIcon(icons.ui_icon(icon_name, 18))
    button.setIconSize(QSize(18, 18))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.clicked.connect(lambda checked=False: callback())
    return button


def labelled_combo(label: str, items) -> tuple[QWidget, QComboBox]:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 4, 0, 4)
    column.setSpacing(4)
    column.addWidget(QLabel(label))
    combo = QComboBox()
    combo.addItems(list(items))
    column.addWidget(combo)
    return holder, combo


def colour_block(editor, materials: bool = False) -> ColorSection:
    block = ColorSection(editor.color, materials=materials)
    block.picked.connect(editor.set_color)
    block.eyedropper.connect(editor.toggle_eyedropper)
    block.material_chosen.connect(editor.set_material)
    return block


class BrushesPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Brushes")
        self.editor = editor
        entries = [(name, brushes.get(name).label) for name in brushes.PANEL_ORDER]
        entries.append(("fill", "Fill"))
        self.tiles = TileGrid(entries, icons.brush_tool_icon, columns=5, size=TILE)
        self.tiles.chosen.connect(editor.set_tool)
        self.add(self.tiles)
        self.add(rule())
        self.thickness = SliderRow("Thickness", *BRUSH_SIZE_RANGE, editor.size, " px")
        self.thickness.changed.connect(editor.set_size)
        self.add(self.thickness)
        self.tolerance = SliderRow("Tolerance", 0, 100, editor.canvas.tolerance * 100, "%")
        self.tolerance.changed.connect(lambda v: editor.set_tolerance(v / 100.0))
        self.add(self.tolerance)
        self.opacity = SliderRow("Opacity", 0, 100, editor.opacity * 100, "%")
        self.opacity.changed.connect(lambda v: editor.set_opacity(v / 100.0))
        self.add(self.opacity)
        self.add(rule())
        self.colors = colour_block(editor)
        self.add(self.colors)
        self.finish()

    def refresh(self) -> None:
        tool = self.editor.tool
        self.tiles.select(tool)
        filling = tool == "fill"
        # Fill has Tolerance and Opacity; the brushes have Thickness and Opacity.
        self.thickness.setVisible(not filling)
        self.tolerance.setVisible(filling)
        self.thickness.set_value(self.editor.size)
        self.opacity.set_value(self.editor.opacity * 100)
        self.colors.set_color(self.editor.color)
        self.colors.set_eyedropper(tool == "eyedropper")


class ShapesPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("2D shapes")
        self.editor = editor
        self.shapes = TileGrid(
            shapes2d.SHAPE_TYPES, lambda k: icons.shape_icon(k), columns=5, size=TILE
        )
        self.shapes.chosen.connect(lambda k: editor.set_tool(f"shape:{k}"))
        self.add(self.shapes)
        self.add(section("Line and curve"))
        self.lines = TileGrid(shapes2d.LINE_TYPES, icons.line_icon, columns=5, size=TILE)
        self.lines.chosen.connect(lambda k: editor.set_tool(f"line:{k}"))
        self.add(self.lines)
        self.add(rule())

        holder, self.line_type = labelled_combo("Line type", ("Solid", "None"))
        self.line_type.currentIndexChanged.connect(self._style_changed)
        self.add(holder)
        self.thickness = SliderRow("Thickness", *SHAPE_THICKNESS_RANGE, editor.size, " px")
        self.thickness.changed.connect(editor.set_size)
        self.add(self.thickness)
        self.opacity = SliderRow("Opacity", 0, 100, editor.opacity * 100, "%")
        self.opacity.changed.connect(lambda v: editor.set_opacity(v / 100.0))
        self.add(self.opacity)
        holder, self.fill = labelled_combo("Fill", ("Solid", "None"))
        self.fill.currentIndexChanged.connect(self._style_changed)
        self.add(holder)
        self.add(rule())
        self.colors = colour_block(editor)
        self.add(self.colors)
        self.finish()

    def _style_changed(self, _index: int) -> None:
        outline = self.line_type.currentIndex() == 0
        filled = self.fill.currentIndex() == 0
        if outline and filled:
            self.editor.shape_style = "both"
        elif filled:
            self.editor.shape_style = "fill"
        else:
            # Line and fill both None would draw nothing; keep the line.
            self.editor.shape_style = "outline"

    def refresh(self) -> None:
        tool = self.editor.tool
        self.shapes.select(tool.split(":", 1)[1] if tool.startswith("shape:") else None)
        self.lines.select(tool.split(":", 1)[1] if tool.startswith("line:") else None)
        self.thickness.set_value(self.editor.size)
        self.colors.set_color(self.editor.color)
        self.colors.set_eyedropper(tool == "eyedropper")


class Shapes3DPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("3D shapes")
        self.editor = editor
        labels = dict(SHAPE3D_TYPES)
        self.add(section("3D objects"))
        self.shapes = TileGrid(
            [(key, labels[key]) for key in SHAPE3D_ORDER], icons.shape3d_icon, columns=5, size=TILE
        )
        self.shapes.chosen.connect(lambda k: editor.set_tool(f"shape3d:{k}"))
        self.add(self.shapes)

        self.add(section("3D doodle"))
        self.doodles = TileGrid(DOODLES, icons.doodle_tool_icon, columns=5, size=TILE)
        self.doodles.chosen.connect(editor.set_tool)
        self.add(self.doodles)

        self.tube_options = QWidget()
        tube_box = QVBoxLayout(self.tube_options)
        tube_box.setContentsMargins(0, 0, 0, 0)
        tube_box.addWidget(QLabel("Shape of tube"))
        self.profiles = TileGrid(tube.PROFILES, icons.tube_icon, columns=6, size=20)
        self.profiles.chosen.connect(lambda k: setattr(editor, "tube_profile", k))
        tube_box.addWidget(self.profiles)
        holder, self.taper = labelled_combo("Taper", [label for _, label in tube.TAPERS])
        for index, (key, _) in enumerate(tube.TAPERS):
            self.taper.setItemData(index, tube.TAPER_HINTS[key], Qt.ItemDataRole.ToolTipRole)
        self.taper.currentIndexChanged.connect(
            lambda i: setattr(editor, "tube_taper", tube.TAPERS[i][0])
        )
        tube_box.addWidget(holder)
        self.weight = SliderRow("Thickness", *TUBE_WEIGHT_RANGE, editor.size, " px")
        self.weight.changed.connect(editor.set_size)
        tube_box.addWidget(self.weight)
        self.add(self.tube_options)
        self.add(rule())

        self.colors = colour_block(editor, materials=True)
        self.add(self.colors)
        self.finish()

    def refresh(self) -> None:
        tool = self.editor.tool
        self.shapes.select(tool.split(":", 1)[1] if tool.startswith("shape3d:") else None)
        self.doodles.select(tool if tool.startswith("doodle_") or tool == "tube" else None)
        self.profiles.select(self.editor.tube_profile)
        self.tube_options.setVisible(tool == "tube")
        self.colors.set_color(self.editor.color)
        self.colors.set_eyedropper(tool == "eyedropper")
        self.colors.set_material(self.editor.material_index)


class StickersPanel(PanelBody):
    """Stickers, Textures and Custom stickers, switched by the row at the top."""

    PIVOTS = (
        ("Stickers", "sticker", "Stickers"),
        ("Textures", "image", "Textures"),
        ("Custom", "image-plus", "Custom stickers"),
    )

    def __init__(self, editor):
        super().__init__("Stickers")
        self.editor = editor

        pivot_row = QHBoxLayout()
        pivot_row.setSpacing(2)
        self.pivot_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        for key, icon_name, tooltip in self.PIVOTS:
            button = QToolButton()
            button.setProperty("role", "tile")
            button.setCheckable(True)
            button.setIcon(icons.ui_icon(icon_name, 22))
            button.setIconSize(QSize(22, 22))
            button.setFixedSize(60, 40)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda checked=False, k=key: self._show_pivot(k))
            group.addButton(button)
            pivot_row.addWidget(button)
            self.pivot_buttons[key] = button
        pivot_row.addStretch(1)
        self.add_layout(pivot_row)

        self.pages: dict[str, QWidget] = {}
        for group_name in stickers.GROUPS:
            grid = TileGrid(stickers.in_group(group_name), icons.sticker_icon, columns=4, size=36)
            grid.chosen.connect(lambda k: editor.set_tool(f"sticker:{k}"))
            self.pages[group_name] = grid
            self.add(grid)
        custom_page = QWidget()
        self.custom_box = QVBoxLayout(custom_page)
        self.custom_box.setContentsMargins(0, 0, 0, 0)
        add = QPushButton("Add sticker")
        add.setToolTip("Choose your own sticker")
        add.clicked.connect(editor.add_custom_sticker)
        self.custom_box.addWidget(add)
        self.custom_grid: TileGrid | None = None
        self.pages["Custom"] = custom_page
        self.add(custom_page)
        self.add(rule())

        self.opacity = SliderRow("Sticker opacity", 0, 100, editor.opacity * 100, "%")
        self.opacity.changed.connect(lambda v: editor.set_opacity(v / 100.0))
        self.add(self.opacity)
        self.finish()
        self._show_pivot("Stickers")

    def _show_pivot(self, key: str) -> None:
        for name, page in self.pages.items():
            page.setVisible(name == key)
        self.pivot_buttons[key].setChecked(True)

    def _rebuild_custom_grid(self) -> None:
        """One tile per sticker the user has added, newest last."""
        count = len(self.editor.custom_stickers)
        if self.custom_grid is not None and len(self.custom_grid.tiles) == count:
            return
        if self.custom_grid is not None:
            self.custom_grid.setParent(None)
        entries = [(f"custom:{i}", "Custom sticker") for i in range(count)]
        stickers_by_key = {f"custom:{i}": p for i, p in enumerate(self.editor.custom_stickers)}
        self.custom_grid = TileGrid(
            entries, lambda k: icons.pixels_icon(stickers_by_key[k], 36), columns=4, size=36
        )
        self.custom_grid.chosen.connect(lambda k: self.editor.set_tool(f"sticker:{k}"))
        self.custom_box.insertWidget(0, self.custom_grid)

    def refresh(self) -> None:
        tool = self.editor.tool
        chosen = tool.split(":", 1)[1] if tool.startswith("sticker:") else None
        self._rebuild_custom_grid()
        if chosen is not None and chosen.startswith("custom:"):
            self._show_pivot("Custom")
        for grid in [*self.pages.values(), self.custom_grid]:
            if isinstance(grid, TileGrid):
                grid.select(chosen if chosen in grid.tiles else None)
        self.opacity.set_value(self.editor.opacity * 100)


class TextPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Text")
        self.editor = editor
        self.tools = TileGrid([("text", "2D text")], icons.text_tool_icon, columns=5, size=TILE)
        self.tools.chosen.connect(editor.set_tool)
        self.add(self.tools)
        self.add(rule())

        self.font = QFontComboBox()
        self.font.setToolTip("Choose a font")
        self.font.currentFontChanged.connect(lambda f: editor.set_text_style(family=f.family()))
        self.add(self.font)

        row = QHBoxLayout()
        row.setSpacing(2)
        self.point_size = QSpinBox()
        self.point_size.setRange(6, 400)
        self.point_size.setValue(48)
        self.point_size.setToolTip("Change text size")
        self.point_size.valueChanged.connect(lambda v: editor.set_text_style(size=v))
        row.addWidget(self.point_size)
        for key, icon_name, tooltip in (
            ("bold", "bold", "Bold your text"),
            ("italic", "italic", "Italicize your text"),
            ("underline", "underline", "Underline your text"),
        ):
            button = QToolButton()
            button.setProperty("role", "tile")
            button.setCheckable(True)
            button.setIcon(icons.ui_icon(icon_name, 18))
            button.setToolTip(tooltip)
            button.toggled.connect(lambda on, k=key: editor.set_text_style(**{k: on}))
            row.addWidget(button)
        row.addStretch(1)
        self.add_layout(row)

        align_row = QHBoxLayout()
        align_row.setSpacing(2)
        align_group = QButtonGroup(self)
        for key, icon_name, tip in (
            ("left", "align-left", "Left align text"),
            ("center", "align-center", "Center your text"),
            ("right", "align-right", "Right align text"),
        ):
            button = QToolButton()
            button.setProperty("role", "tile")
            button.setCheckable(True)
            button.setChecked(key == "left")
            button.setIcon(icons.ui_icon(icon_name, 18))
            button.setToolTip(tip)
            button.clicked.connect(lambda checked=False, k=key: editor.set_text_style(align=k))
            align_group.addButton(button)
            align_row.addWidget(button)
        align_row.addStretch(1)
        self.add_layout(align_row)

        fill_row = QHBoxLayout()
        self.background_fill = QToolButton()
        self.background_fill.setProperty("role", "action")
        self.background_fill.setCheckable(True)
        self.background_fill.setText("Background fill")
        self.background_fill.setIcon(icons.ui_icon("paint-bucket", 18))
        self.background_fill.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.background_fill.setToolTip("Add a background color to your text box")
        self.background_fill.toggled.connect(lambda _on: self._background_changed())
        fill_row.addWidget(self.background_fill)
        self.background_chip = QToolButton()
        self.background_chip.setFixedSize(40, 28)
        self.background_chip.setToolTip("Choose a fill color")
        self.background_chip.clicked.connect(self._choose_background)
        fill_row.addWidget(self.background_chip)
        fill_row.addStretch(1)
        self.add_layout(fill_row)
        self._background = (255, 255, 255)
        self._paint_background_chip()

        self.add(rule())
        self.colors = colour_block(editor)
        self.add(self.colors)
        self.finish()

    def _choose_background(self) -> None:
        from Clay3D.widgets import ColorPickerDialog

        rgb = ColorPickerDialog.choose(self._background, ColorPickerDialog.EDIT_TITLE, self)
        if rgb is not None:
            self._background_picked(rgb)

    def _background_picked(self, rgb) -> None:
        self._background = tuple(rgb)
        self._paint_background_chip()
        self.background_fill.setChecked(True)
        self._background_changed()

    def _paint_background_chip(self) -> None:
        r, g, b = self._background
        self.background_chip.setStyleSheet(
            f"QToolButton {{ background: rgb({r},{g},{b}); border: 1px solid #BEBEBE; }}"
        )

    def _background_changed(self) -> None:
        on = self.background_fill.isChecked()
        self.editor.set_text_style(background=(*self._background, 255) if on else None)

    def refresh(self) -> None:
        self.tools.select(self.editor.tool)
        self.colors.set_color(self.editor.color)
        self.colors.set_eyedropper(self.editor.tool == "eyedropper")


class EffectsPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Effects")
        self.editor = editor
        self.add(section("Filter"))
        # Unlabelled swatches; names stay as tooltips.
        entries = [(name, EFFECTS[name].label) for name in EFFECT_ORDER]
        self.tiles = TileGrid(entries, icons.effect_icon, columns=4, size=40)
        self.tiles.chosen.connect(editor.set_effect)
        self.add(self.tiles)
        self.add(rule())
        self.light = SliderRow("Light wheel", 0, 360, 0, "°")
        self.light.changed.connect(editor.set_light_rotation)
        self.add(self.light)
        self.finish()

    def refresh(self) -> None:
        self.tiles.select(self.editor.scene.effect)


class CanvasPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Canvas")
        self.editor = editor
        self._syncing = False
        self.show_canvas = QCheckBox("Show canvas")
        self.show_canvas.setChecked(True)
        self.show_canvas.toggled.connect(editor.set_show_canvas)
        self.add(self.show_canvas)
        self.transparent = QCheckBox("Transparent canvas")
        self.transparent.toggled.connect(editor.set_transparent_canvas)
        self.add(self.transparent)
        self.add(rule())

        self.add(section("Resize canvas"))
        self.scale_image = QCheckBox("Resize image with canvas")
        self.scale_image.setChecked(True)
        self.add(self.scale_image)
        self.units = QComboBox()
        self.units.addItems(["Pixels", "Percent"])
        self.units.currentTextChanged.connect(lambda _t: self.refresh())
        self.add(self.units)

        grid = QGridLayout()
        grid.addWidget(QLabel("Width"), 0, 0)
        grid.addWidget(QLabel("Height"), 0, 2)
        self.width = QSpinBox()
        self.width.setRange(1, 10000)
        self.height = QSpinBox()
        self.height.setRange(1, 10000)
        grid.addWidget(self.width, 1, 0)
        self.lock = QToolButton()
        self.lock.setProperty("role", "tile")
        self.lock.setCheckable(True)
        self.lock.setChecked(True)
        self.lock.setIcon(icons.ui_icon("lock", 16))
        self.lock.setToolTip("Lock aspect ratio")
        grid.addWidget(self.lock, 1, 1)
        grid.addWidget(self.height, 1, 2)
        self.add_layout(grid)
        self.width.valueChanged.connect(lambda v: self._follow_aspect(v, self.width))
        self.height.valueChanged.connect(lambda v: self._follow_aspect(v, self.height))
        self.width.editingFinished.connect(self._apply_resize)
        self.height.editingFinished.connect(self._apply_resize)
        self.add(rule())

        self.add(section("Rotate and flip"))
        self.add_layout(icon_row((
            ("rotate-ccw", "Rotate left", "rotate_left"),
            ("rotate-cw", "Rotate right", "rotate_right"),
            ("flip-horizontal-2", "Flip vertical", "flip_vertical"),
            ("flip-vertical-2", "Flip horizontal", "flip_horizontal"),
        ), editor.turn_canvas))
        self.finish()
        self.refresh()

    def _follow_aspect(self, value: int, source) -> None:
        if not self.lock.isChecked() or self._syncing:
            return
        self._syncing = True
        if self.units.currentText() == "Percent":
            (self.height if source is self.width else self.width).setValue(value)
        else:
            ratio = self.editor.canvas.width / max(self.editor.canvas.height, 1)
            if source is self.width:
                self.height.setValue(max(1, int(round(value / ratio))))
            else:
                self.width.setValue(max(1, int(round(value * ratio))))
        self._syncing = False

    def _apply_resize(self) -> None:
        if self.units.currentText() == "Percent":
            width = max(1, int(self.editor.canvas.width * self.width.value() / 100))
            height = max(1, int(self.editor.canvas.height * self.height.value() / 100))
        else:
            width, height = self.width.value(), self.height.value()
        if (width, height) == (self.editor.canvas.width, self.editor.canvas.height):
            return
        self.editor.resize_canvas(width, height, scale_image=self.scale_image.isChecked())

    def refresh(self) -> None:
        self.show_canvas.blockSignals(True)
        self.show_canvas.setChecked(self.editor.scene.show_canvas)
        self.show_canvas.blockSignals(False)
        self._syncing = True
        if self.units.currentText() == "Pixels":
            self.width.setValue(self.editor.canvas.width)
            self.height.setValue(self.editor.canvas.height)
        else:
            self.width.setValue(100)
            self.height.setValue(100)
        self._syncing = False


class SelectPanel(PanelBody):
    """Select options; the magic select steps or crop options while those run."""

    ADD_HINT = "Missing something? Mark any unselected areas to add them to your cutout."
    REMOVE_HINT = "Too much selected? Mark unwanted areas to remove them from your cutout."
    CROP_RATIOS = (
        ("16:9", "16:9"), ("5:3", "5:3"), ("3:2", "3:2"), ("4:3", "4:3"),
        ("1:1", "1:1"), ("9:16", "9:16"), ("free", "Custom"),
    )

    def __init__(self, editor):
        super().__init__("Select")
        self.editor = editor
        self.title = self.box.itemAt(0).widget()
        self.plain = self._plain_options(editor)
        self.box_step = self._box_step(editor)
        self.refine_step = self._refine_step(editor)
        self.crop_step = self._crop_step(editor)
        for part in (self.plain, self.box_step, self.refine_step, self.crop_step):
            self.add(part)
        self.finish()

    def _plain_options(self, editor) -> QWidget:
        part, layout = _column()
        self.size_readout = QLabel()
        self.size_readout.setProperty("role", "value")
        self.size_readout.setToolTip("Selection size")
        layout.addWidget(self.size_readout)

        layout.addWidget(section("Select"))
        select_all = QPushButton("Select all")
        select_all.clicked.connect(editor.select_all)
        layout.addWidget(select_all)

        layout.addWidget(section("Edit"))
        layout.addLayout(icon_row((
            ("scissors", "Cut", editor.cut_selection),
            ("copy", "Copy", editor.copy_selection),
            ("clipboard-paste", "Paste", editor.paste_clipboard),
            ("trash-2", "Delete", editor.delete_selection),
        ), lambda fn: fn()))

        layout.addWidget(section("Rotate and flip"))
        layout.addLayout(icon_row((
            ("rotate-ccw", "Rotate left", lambda: editor.turn_selection("rotate_left")),
            ("rotate-cw", "Rotate right", lambda: editor.turn_selection("rotate_right")),
            ("flip-vertical-2", "Flip horizontal", lambda: editor.turn_selection("flip_horizontal")),
            ("flip-horizontal-2", "Flip vertical", lambda: editor.turn_selection("flip_vertical")),
        ), lambda fn: fn()))
        layout.addWidget(rule())

        layout.addWidget(text_and_icon("crop", "Crop", editor.crop_to_selection))
        layout.addWidget(text_and_icon("sticker", "Make sticker", editor.make_sticker_from_selection))
        layout.addWidget(text_and_icon("wand-sparkles", "Magic select", editor.start_magic_select))
        return part

    def _box_step(self, editor) -> QWidget:
        part, layout = _column()
        hint = QLabel("Drag in the corners or sides of the blue box to show us what to focus on.")
        hint.setWordWrap(True)
        hint.setProperty("role", "value")
        layout.addWidget(hint)
        next_button = QPushButton("Next")
        next_button.setProperty("role", "primary")
        next_button.clicked.connect(editor.magic_next)
        layout.addWidget(next_button)
        return part

    def _refine_step(self, editor) -> QWidget:
        part, layout = _column()
        label = QLabel("Refine your cutout")
        label.setProperty("role", "section")
        layout.addWidget(label)

        row = QHBoxLayout()
        self.refine_buttons: dict[str, QToolButton] = {}
        for tool, text, icon_name in (
            ("select:magic_add", "Add", "plus"), ("select:magic_remove", "Remove", "minus"),
        ):
            button = QToolButton()
            button.setText(text)
            button.setIcon(icons.ui_icon(icon_name, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setProperty("role", "action")
            button.clicked.connect(lambda checked=False, t=tool: editor.set_tool(t))
            row.addWidget(button)
            self.refine_buttons[tool] = button
        row.addStretch(1)
        layout.addLayout(row)

        self.refine_hint = QLabel(self.ADD_HINT)
        self.refine_hint.setWordWrap(True)
        self.refine_hint.setProperty("role", "value")
        layout.addWidget(self.refine_hint)

        self.autofill = QCheckBox("Autofill background")
        self.autofill.setToolTip("Autofill background after cutout")
        self.autofill.setChecked(editor.autofill_background)
        self.autofill.toggled.connect(lambda on: setattr(editor, "autofill_background", on))
        layout.addWidget(self.autofill)

        self.done_button = QPushButton("Done")
        self.done_button.setProperty("role", "primary")
        self.done_button.clicked.connect(editor.finish_cutout)
        layout.addWidget(self.done_button)
        return part

    def _crop_step(self, editor) -> QWidget:
        part, layout = _column()
        self.crop_ratio = QComboBox()
        for key, label in self.CROP_RATIOS:
            self.crop_ratio.addItem(label, key)
        self.crop_ratio.currentIndexChanged.connect(
            lambda i: editor.set_crop_ratio(self.crop_ratio.itemData(i))
        )
        layout.addWidget(self.crop_ratio)
        grid = QGridLayout()
        grid.addWidget(QLabel("Width"), 0, 0)
        grid.addWidget(QLabel("Height"), 0, 1)
        self.crop_width = QLabel()
        self.crop_height = QLabel()
        for column, readout in enumerate((self.crop_width, self.crop_height)):
            readout.setProperty("role", "value")
            grid.addWidget(readout, 1, column)
        layout.addLayout(grid)
        buttons = QHBoxLayout()
        done = QToolButton()
        done.setProperty("role", "commit")
        done.setIcon(icons.ui_icon("check", 22, "#FFFFFF"))
        done.setToolTip("Done")
        done.clicked.connect(lambda checked=False: editor.finish_crop())
        cancel = QToolButton()
        cancel.setProperty("role", "cancel")
        cancel.setIcon(icons.ui_icon("x", 22, "#FFFFFF"))
        cancel.setToolTip("Cancel")
        cancel.clicked.connect(lambda checked=False: editor.cancel_crop())
        for button in (done, cancel):
            button.setFixedSize(104, 40)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        return part

    def refresh(self) -> None:
        tool = self.editor.tool
        stage = self.editor.magic_stage()
        cropping = self.editor.crop_box is not None
        if cropping:
            self.title.setText("Crop")
        else:
            self.title.setText("Select" if stage is None else "Magic select")
        self.plain.setVisible(stage is None and not cropping)
        self.box_step.setVisible(stage == "box")
        self.refine_step.setVisible(stage == "refine")
        self.crop_step.setVisible(cropping)
        for key, button in self.refine_buttons.items():
            button.setChecked(tool == key)
        removing = tool == "select:magic_remove"
        self.refine_hint.setText(self.REMOVE_HINT if removing else self.ADD_HINT)
        frame = self.editor.selection_frame()
        if frame is None:
            self.size_readout.setText("")
        else:
            width, height = int(frame[2] - frame[0]), int(frame[3] - frame[1])
            self.size_readout.setText(f"W: {width} px    H: {height} px")
        if cropping:
            self.crop_ratio.blockSignals(True)
            self.crop_ratio.setCurrentIndex(self.crop_ratio.findData(self.editor.crop_ratio))
            self.crop_ratio.blockSignals(False)
            x0, y0, x1, y1 = self.editor.crop_box
            self.crop_width.setText(f"{int(round(x1 - x0))} px")
            self.crop_height.setText(f"{int(round(y1 - y0))} px")


def _column() -> tuple[QWidget, QVBoxLayout]:
    part = QWidget()
    layout = QVBoxLayout(part)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    return part, layout


# The original's seven tool tabs. Its eighth is the 3D library, which
# needs the Remix 3D service and is gone, so it is not here.
TABS = (
    ("Brushes", BrushesPanel),
    ("2D shapes", ShapesPanel),
    ("3D shapes", Shapes3DPanel),
    ("Stickers", StickersPanel),
    ("Text", TextPanel),
    ("Effects", EffectsPanel),
    ("Canvas", CanvasPanel),
)

# Select is not a tab in the original: its tools sit in the top bar and
# their options appear in the right panel while one is active.
CONTEXT_PANELS = (("Select", SelectPanel),)
