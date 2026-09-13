"""Right-hand panels. One class per tab. refresh() follows selection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from Clay3D import brushes, icons, imagefx, selection, shapes2d, stickers, tube
from Clay3D.effects import EFFECT_ORDER, EFFECTS
from Clay3D.scene3d import SHAPE3D_TYPES
from Clay3D.tuning import (
    BRUSH_SIZE_RANGE,
    SHAPE_THICKNESS_RANGE,
    STICKER_SIZE_RANGE,
    TUBE_WEIGHT_RANGE,
)
from Clay3D.widgets import ColorSection, PanelBody, SliderRow, TileGrid, rule, section

DOODLES = (("doodle_soft", "Soft edge"), ("doodle_sharp", "Sharp edge"))


class BrushesPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Brushes")
        self.editor = editor
        entries = [(name, brushes.get(name).label) for name in brushes.PANEL_ORDER]
        entries.append(("fill", "Fill"))
        entries.append(("eyedropper", "Eyedropper"))
        self.tiles = TileGrid(entries, icons.brush_icon, columns=5)
        self.tiles.chosen.connect(editor.set_tool)
        self.add(self.tiles)
        self.add(rule())
        self.thickness = SliderRow("Thickness", *BRUSH_SIZE_RANGE, editor.size, " px")
        self.thickness.changed.connect(editor.set_size)
        self.add(self.thickness)
        self.opacity = SliderRow("Opacity", 0, 100, editor.opacity * 100, "%")
        self.opacity.changed.connect(lambda v: editor.set_opacity(v / 100.0))
        self.add(self.opacity)
        self.tolerance = SliderRow("Fill tolerance", 0, 100, editor.canvas.tolerance * 100, "%")
        self.tolerance.changed.connect(lambda v: editor.set_tolerance(v / 100.0))
        self.add(self.tolerance)
        self.add(rule())
        self.colors = ColorSection(editor.color)
        self.colors.picked.connect(editor.set_color)
        self.add(self.colors)
        self.finish()

    def refresh(self) -> None:
        self.tiles.select(self.editor.tool)
        self.thickness.set_value(self.editor.size)
        self.opacity.set_value(self.editor.opacity * 100)
        self.colors.set_color(self.editor.color)
        self.tolerance.setVisible(self.editor.tool == "fill")


class ShapesPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("2D shapes")
        self.editor = editor
        self.shapes = TileGrid(
            shapes2d.SHAPE_TYPES, lambda k: icons.shape_icon(k), columns=6, size=34
        )
        self.shapes.chosen.connect(lambda k: editor.set_tool(f"shape:{k}"))
        self.add(self.shapes)
        self.add(section("Lines and curves"))
        self.lines = TileGrid(shapes2d.LINE_TYPES, icons.line_icon, columns=6, size=34)
        self.lines.chosen.connect(lambda k: editor.set_tool(f"line:{k}"))
        self.add(self.lines)
        self.add(rule())

        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Style"))
        self.style = QComboBox()
        self.style.addItems(["Outline and fill", "Outline only", "Fill only"])
        self.style.currentIndexChanged.connect(self._style_changed)
        style_row.addWidget(self.style, 1)
        self.add_layout(style_row)

        self.thickness = SliderRow("Thickness", *SHAPE_THICKNESS_RANGE, editor.size, " px")
        self.thickness.changed.connect(editor.set_size)
        self.add(self.thickness)
        self.opacity = SliderRow("Opacity", 0, 100, editor.opacity * 100, "%")
        self.opacity.changed.connect(lambda v: editor.set_opacity(v / 100.0))
        self.add(self.opacity)
        self.add(rule())
        self.colors = ColorSection(editor.color)
        self.colors.picked.connect(editor.set_color)
        self.add(self.colors)
        stamp = QPushButton("Stamp")
        stamp.setProperty("role", "primary")
        stamp.setToolTip("Flatten the shape onto the canvas")
        stamp.clicked.connect(editor.stamp_live_item)
        self.add(stamp)
        self.finish()

    def _style_changed(self, index: int) -> None:
        self.editor.shape_style = ("both", "outline", "fill")[index]

    def refresh(self) -> None:
        tool = self.editor.tool
        self.shapes.select(tool.split(":", 1)[1] if tool.startswith("shape:") else None)
        self.lines.select(tool.split(":", 1)[1] if tool.startswith("line:") else None)
        self.thickness.set_value(self.editor.size)
        self.colors.set_color(self.editor.color)


class Shapes3DPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("3D shapes")
        self.editor = editor
        self.shapes = TileGrid(SHAPE3D_TYPES, icons.shape3d_icon, columns=5, size=40)
        self.shapes.chosen.connect(lambda k: editor.set_tool(f"shape3d:{k}"))
        self.add(self.shapes)
        self.add(section("3D doodle"))
        self.doodles = TileGrid(
            DOODLES, lambda k: icons.doodle_icon(k.split("_")[1]), columns=5, size=40
        )
        self.doodles.chosen.connect(editor.set_tool)
        self.add(self.doodles)

        self.add(section("Tube brush"))
        self.profiles = TileGrid(
            tube.PROFILES, icons.tube_icon, columns=6, size=34
        )
        self.profiles.chosen.connect(self._choose_profile)
        self.add(self.profiles)
        taper_row = QHBoxLayout()
        taper_row.addWidget(QLabel("Taper"))
        self.taper = QComboBox()
        for key, label in tube.TAPERS:
            self.taper.addItem(label, key)
            self.taper.setItemData(
                self.taper.count() - 1, tube.TAPER_HINTS[key], Qt.ItemDataRole.ToolTipRole
            )
        self.taper.currentIndexChanged.connect(self._choose_taper)
        taper_row.addWidget(self.taper, 1)
        self.add_layout(taper_row)
        self.weight = SliderRow("Weight", *TUBE_WEIGHT_RANGE, editor.size, " px")
        self.weight.changed.connect(editor.set_size)
        self.add(self.weight)
        self.add(rule())

        self.selected_label = QLabel("Nothing selected")
        self.selected_label.setProperty("role", "value")
        self.add(self.selected_label)
        self.smoothness = SliderRow("Smoothness", 0, 100, 25, "%")
        self.smoothness.changed.connect(
            lambda v: editor.set_object_material(smoothness=v / 100.0)
        )
        self.add(self.smoothness)
        self.metallic = SliderRow("Metallic", 0, 100, 0, "%")
        self.metallic.changed.connect(lambda v: editor.set_object_material(metallic=v / 100.0))
        self.add(self.metallic)
        self.add(rule())
        self.colors = ColorSection(editor.color)
        self.colors.picked.connect(editor.set_color)
        self.add(self.colors)
        self.finish()

    def _choose_profile(self, key: str) -> None:
        self.editor.tube_profile = key
        self.editor.set_tool("tube")

    def _choose_taper(self, index: int) -> None:
        self.editor.tube_taper = self.taper.itemData(index)

    def refresh(self) -> None:
        tool = self.editor.tool
        self.shapes.select(tool.split(":", 1)[1] if tool.startswith("shape3d:") else None)
        self.doodles.select(tool if tool.startswith("doodle_") else None)
        self.profiles.select(self.editor.tube_profile if tool == "tube" else None)
        self.weight.setVisible(tool == "tube")
        self.taper.setEnabled(tool == "tube")
        obj = self.editor.scene.selected()
        self.selected_label.setText(
            f"Selected: {obj.kind.replace('_', ' ')}" if obj else "Nothing selected"
        )
        self.smoothness.setEnabled(obj is not None)
        self.metallic.setEnabled(obj is not None)
        if obj is not None:
            self.smoothness.set_value(obj.smoothness * 100)
            self.metallic.set_value(obj.metallic * 100)


class StickersPanel(PanelBody):
    """Stickers and Textures, the two groups the original ships."""

    def __init__(self, editor):
        super().__init__("Stickers")
        self.editor = editor
        self.grids: dict[str, TileGrid] = {}
        for group in stickers.GROUPS:
            self.add(section(group))
            grid = TileGrid(stickers.in_group(group), icons.sticker_icon, columns=4, size=44)
            grid.chosen.connect(lambda k: editor.set_tool(f"sticker:{k}"))
            self.add(grid)
            self.grids[group] = grid

        custom = QPushButton("Add sticker")
        custom.clicked.connect(editor.add_custom_sticker)
        self.add(custom)
        self.add(rule())

        self.size = SliderRow("Size", *STICKER_SIZE_RANGE, 120, " px")
        self.size.changed.connect(lambda v: setattr(editor, "sticker_size", int(v)))
        self.add(self.size)
        stamp = QPushButton("Stamp")
        stamp.setProperty("role", "primary")
        stamp.setToolTip("Flatten the sticker onto the canvas")
        stamp.clicked.connect(editor.stamp_live_item)
        self.add(stamp)
        hint = QLabel(
            "Click the canvas to place a sticker, then drag it. Stamp commits it. "
            "Click a 3D object to wrap it onto that surface. Hold Ctrl to place another."
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "value")
        self.add(hint)
        self.finish()

    def refresh(self) -> None:
        tool = self.editor.tool
        chosen = tool.split(":", 1)[1] if tool.startswith("sticker:") else None
        for grid in self.grids.values():
            grid.select(chosen if chosen in grid.tiles else None)


class TextPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Text")
        self.editor = editor
        add = QPushButton("Add a text box")
        add.setProperty("role", "primary")
        add.clicked.connect(lambda: editor.set_tool("text"))
        self.add(add)
        self.add(rule())

        self.font = QFontComboBox()
        self.font.setCurrentFont(self.font.currentFont())
        self.font.currentFontChanged.connect(lambda f: editor.set_text_style(family=f.family()))
        self.add(self.font)

        row = QHBoxLayout()
        self.point_size = QSpinBox()
        self.point_size.setRange(6, 400)
        self.point_size.setValue(48)
        self.point_size.valueChanged.connect(lambda v: editor.set_text_style(size=v))
        row.addWidget(self.point_size)
        for key, label in (("bold", "B"), ("italic", "I"), ("underline", "U")):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("role", "action")
            button.toggled.connect(lambda on, k=key: editor.set_text_style(**{k: on}))
            row.addWidget(button)
        row.addStretch(1)
        self.add_layout(row)

        align_row = QHBoxLayout()
        align_row.addWidget(QLabel("Align"))
        self.align = QComboBox()
        self.align.addItems(["Left", "Centre", "Right"])
        self.align.currentTextChanged.connect(
            lambda t: editor.set_text_style(align=t.lower().replace("centre", "center"))
        )
        align_row.addWidget(self.align, 1)
        self.add_layout(align_row)

        hint = QLabel("Click the canvas to place a text box, then type. Press Esc to commit.")
        hint.setWordWrap(True)
        hint.setProperty("role", "value")
        self.add(hint)
        self.add(rule())
        self.colors = ColorSection(editor.color)
        self.colors.picked.connect(editor.set_color)
        self.add(self.colors)
        self.finish()

    def refresh(self) -> None:
        self.colors.set_color(self.editor.color)


class EffectsPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Effects")
        self.editor = editor
        # The original shows unlabelled swatches; the names stay as tooltips.
        entries = [(name, EFFECTS[name].label) for name in EFFECT_ORDER]
        self.tiles = TileGrid(entries, icons.effect_icon, columns=4, size=54)
        self.tiles.chosen.connect(editor.set_effect)
        self.add(self.tiles)
        self.add(rule())
        self.light = SliderRow("Lighting rotation", 0, 360, 0, "°")
        self.light.changed.connect(editor.set_light_rotation)
        self.add(self.light)
        hint = QLabel("Effects grade the whole stage - canvas and 3D objects together.")
        hint.setWordWrap(True)
        hint.setProperty("role", "value")
        self.add(hint)
        self.finish()

    def refresh(self) -> None:
        self.tiles.select(self.editor.scene.effect)


class CanvasPanel(PanelBody):
    def __init__(self, editor):
        super().__init__("Canvas options")
        self.editor = editor
        self.show_canvas = QCheckBox("Show canvas")
        self.show_canvas.setChecked(True)
        self.show_canvas.toggled.connect(editor.set_show_canvas)
        self.add(self.show_canvas)
        self.transparent = QCheckBox("Transparent canvas")
        self.transparent.toggled.connect(editor.set_transparent_canvas)
        self.add(self.transparent)
        self.add(rule())

        self.add(section("Resize canvas"))
        grid = QGridLayout()
        grid.addWidget(QLabel("Width"), 0, 0)
        self.width = QSpinBox()
        self.width.setRange(1, 10000)
        self.width.setValue(editor.canvas.width)
        grid.addWidget(self.width, 0, 1)
        grid.addWidget(QLabel("Height"), 1, 0)
        self.height = QSpinBox()
        self.height.setRange(1, 10000)
        self.height.setValue(editor.canvas.height)
        grid.addWidget(self.height, 1, 1)
        self.units = QComboBox()
        self.units.addItems(["Pixels", "Percent"])
        grid.addWidget(self.units, 0, 2)
        self.add_layout(grid)
        self.lock = QCheckBox("Lock aspect ratio")
        self.lock.setChecked(True)
        self.add(self.lock)
        self.width.valueChanged.connect(lambda v: self._follow_aspect(v, self.width))
        self.height.valueChanged.connect(lambda v: self._follow_aspect(v, self.height))
        apply_resize = QPushButton("Resize")
        apply_resize.clicked.connect(self._apply_resize)
        self.add(apply_resize)
        self.add(rule())

        self.add(section("Rotate and flip"))
        self.turns = TileGrid(imagefx.TURNS, icons.canvas_icon, columns=4, size=34, exclusive=False)
        self.turns.chosen.connect(editor.turn_canvas)
        self.add(self.turns)
        self.add(rule())

        self.add(section("Filters"))
        self.filters = TileGrid(
            imagefx.FILTERS, lambda k: icons.image_filter_icon(k, 40),
            columns=4, size=40, exclusive=False,
        )
        self.filters.chosen.connect(editor.apply_image_filter)
        self.add(self.filters)
        self.finish()
        self._syncing = False

    def _follow_aspect(self, value: int, source) -> None:
        if not self.lock.isChecked() or self._syncing or self.units.currentText() == "Percent":
            return
        self._syncing = True
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
        self.editor.resize_canvas(width, height)

    def refresh(self) -> None:
        self.turns.select(None)
        self.filters.select(None)
        self.show_canvas.blockSignals(True)
        self.show_canvas.setChecked(self.editor.scene.show_canvas)
        self.show_canvas.blockSignals(False)
        if self.units.currentText() == "Pixels":
            self._syncing = True
            self.width.setValue(self.editor.canvas.width)
            self.height.setValue(self.editor.canvas.height)
            self._syncing = False


class SelectPanel(PanelBody):
    """2D selection options, or the magic select steps while that tool is open."""

    ADD_HINT = "Missing something? Mark any unselected areas to add them to your cutout."
    REMOVE_HINT = "Too much selected? Mark unwanted areas to remove them from your cutout."

    def __init__(self, editor):
        super().__init__("2D selection")
        self.editor = editor
        self.title = self.box.itemAt(0).widget()
        self.plain = self._plain_options(editor)
        self.box_step = self._box_step(editor)
        self.refine_step = self._refine_step(editor)
        for part in (self.plain, self.box_step, self.refine_step):
            self.add(part)
        self.finish()

    def _plain_options(self, editor) -> QWidget:
        part, layout = _column()
        entries = list(selection.SELECT_TYPES) + [("crop", "Crop")]
        self.tiles = TileGrid(entries, icons.select_icon, columns=4, size=38)
        self.tiles.chosen.connect(lambda k: editor.choose_select_tool(f"select:{k}"))
        layout.addWidget(self.tiles)
        layout.addWidget(rule())
        layout.addWidget(section("With the selection"))
        grid = QGridLayout()
        actions = (
            ("Cut", editor.cut_selection),
            ("Copy", editor.copy_selection),
            ("Paste", editor.paste_clipboard),
            ("Delete", editor.delete_selection),
            ("Invert", editor.invert_selection),
            ("Select all", editor.select_all),
            ("Deselect", editor.clear_selection),
            ("Crop to selection", editor.crop_to_selection),
        )
        for index, (label, handler) in enumerate(actions):
            button = QPushButton(label)
            button.clicked.connect(handler)
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)
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
        for tool, text in (("select:magic_add", "Add"), ("select:magic_remove", "Remove")):
            button = QToolButton()
            button.setText(text)
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
        layout.addWidget(rule())

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

    def refresh(self) -> None:
        tool = self.editor.tool
        stage = self.editor.magic_stage()
        self.title.setText("2D selection" if stage is None else "Magic select")
        self.plain.setVisible(stage is None)
        self.box_step.setVisible(stage == "box")
        self.refine_step.setVisible(stage == "refine")
        self.tiles.select(tool.split(":", 1)[1] if tool.startswith("select:") else None)
        for key, button in self.refine_buttons.items():
            button.setChecked(tool == key)
        removing = tool == "select:magic_remove"
        self.refine_hint.setText(self.REMOVE_HINT if removing else self.ADD_HINT)


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
