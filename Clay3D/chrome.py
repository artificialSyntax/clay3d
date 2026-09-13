"""Window chrome: top bar, tools bar, menu page. Layout follows Paint 3D's.

Top bar:   Menu | tabs | Paste Undo History Redo | show-names toggle
Tools bar: Select Crop Magic select | 3D view  zoom-  slider  zoom+  NN%  ...
The side panel sits beside the tools bar; there is no bottom bar.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from Clay3D import icons
from Clay3D.theme import STYLESHEET

TOP_BUTTON_WIDTH = 68
TOP_BAR_HEIGHT = 48         # names hidden
TOOLS_BAR_HEIGHT = 48
ZOOM_SLIDER_WIDTH = 140
SIDE_PANEL_WIDTH = 264
COMPACT_PANEL_WIDTH = 84    # compact view
COMPACT_HEADER_HEIGHT = 84

TAB_ICONS = {
    "Brushes": "paintbrush",
    "2D shapes": "shapes",
    "3D shapes": "box",
    "Stickers": "sticker",
    "Text": "type",
    "Effects": "sparkles",
    "Canvas": "frame",
}

SELECT_TOOLS = (
    ("select:box", "Select", "square-dashed-mouse-pointer"),
    ("select:crop", "Crop", "crop"),
    ("select:magic", "Magic select", "wand-sparkles"),
)


# ---- top bar -------------------------------------------------------------


def top_bar(editor, tab_names) -> QWidget:
    bar = QWidget()
    bar.setObjectName("topBar")
    row = QHBoxLayout(bar)
    row.setContentsMargins(4, 0, 4, 0)
    row.setSpacing(0)

    editor.named_buttons = []

    menu = _top_button("Menu", "folder-open", "Menu")
    menu.clicked.connect(editor.show_menu)
    row.addWidget(menu)
    editor.named_buttons.append(menu)
    row.addSpacing(8)

    editor.tab_buttons = {}
    group = QButtonGroup(bar)
    for name in tab_names:
        button = _top_button(name, TAB_ICONS[name], name)
        button.setCheckable(True)
        button.setProperty("role", "tab")
        button.clicked.connect(lambda checked=False, n=name: editor.set_category(n))
        group.addButton(button)
        row.addWidget(button)
        editor.tab_buttons[name] = button
        editor.named_buttons.append(button)

    row.addStretch(1)

    paste = _top_button("Paste", "clipboard-paste", "Paste")
    paste.clicked.connect(lambda checked=False: editor.paste_clipboard())
    editor.undo_button = _top_button("Undo", "undo-2", "Undo")
    editor.undo_button.clicked.connect(lambda checked=False: editor.undo())
    editor.history_button = _top_button("History", "history", "History")
    editor.history_button.clicked.connect(lambda checked=False: editor.show_history())
    editor.redo_button = _top_button("Redo", "redo-2", "Redo")
    editor.redo_button.clicked.connect(lambda checked=False: editor.redo())
    for button in (paste, editor.undo_button, editor.history_button, editor.redo_button):
        row.addWidget(button)
        editor.named_buttons.append(button)

    editor.names_toggle = QToolButton()
    editor.names_toggle.setProperty("role", "action")
    editor.names_toggle.setCheckable(True)
    editor.names_toggle.setChecked(True)
    editor.names_toggle.setToolTip("Show or hide names in the menu")
    editor.names_toggle.setIconSize(QSize(16, 16))
    editor.names_toggle.toggled.connect(lambda on: show_button_names(editor, on))
    row.addWidget(editor.names_toggle)
    show_button_names(editor, True)
    return bar


def _top_button(text: str, icon_name: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tooltip)
    button.setIcon(icons.ui_icon(icon_name, 22, "#FFFFFF"))
    button.setIconSize(QSize(22, 22))
    button.setProperty("role", "topButton")
    button.setMinimumWidth(TOP_BUTTON_WIDTH)
    return button


def show_button_names(editor, on: bool) -> None:
    """The top bar's expand toggle: names under the icons, or icons only."""
    style = (
        Qt.ToolButtonStyle.ToolButtonTextUnderIcon if on else Qt.ToolButtonStyle.ToolButtonIconOnly
    )
    for button in editor.named_buttons:
        button.setToolButtonStyle(style)
        button.setMinimumHeight(TOP_BAR_HEIGHT + (22 if on else 0))
    editor.names_toggle.setIcon(icons.ui_icon("chevron-up" if on else "chevron-down", 16, "#FFFFFF"))


# ---- tools bar -----------------------------------------------------------


def tools_bar(editor) -> QWidget:
    bar = QWidget()
    bar.setObjectName("toolsBar")
    bar.setFixedHeight(TOOLS_BAR_HEIGHT)
    row = QHBoxLayout(bar)
    row.setContentsMargins(8, 0, 4, 0)
    row.setSpacing(4)

    editor.select_buttons = {}
    for tool, label, icon_name in SELECT_TOOLS:
        button = QToolButton()
        button.setText(label)
        button.setToolTip(label)
        button.setIcon(icons.ui_icon(icon_name, 18))
        button.setIconSize(QSize(18, 18))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(True)
        button.setProperty("role", "action")
        button.clicked.connect(lambda checked=False, t=tool: editor.choose_select_tool(t))
        row.addWidget(button)
        editor.select_buttons[tool] = button

    row.addStretch(1)

    editor.view_3d = QToolButton()
    editor.view_3d.setText("3D view")
    editor.view_3d.setToolTip("3D view")
    editor.view_3d.setIcon(icons.ui_icon("rotate-3d", 18))
    editor.view_3d.setIconSize(QSize(18, 18))
    editor.view_3d.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    editor.view_3d.setCheckable(True)
    editor.view_3d.setProperty("role", "action")
    editor.view_3d.clicked.connect(lambda checked=False: editor.toggle_view())
    row.addWidget(editor.view_3d)
    row.addSpacing(8)

    row.addWidget(_icon_action("zoom-out", "Zoom out", lambda: editor.zoom_by(0.8)))
    editor.zoom_slider = QSlider(Qt.Orientation.Horizontal)
    editor.zoom_slider.setFixedWidth(ZOOM_SLIDER_WIDTH)
    editor.zoom_slider.setRange(10, 800)
    editor.zoom_slider.setValue(100)
    editor.zoom_slider.setToolTip("Adjust the zoom")
    editor.zoom_slider.valueChanged.connect(editor._zoom_slider_moved)
    row.addWidget(editor.zoom_slider)
    row.addWidget(_icon_action("zoom-in", "Zoom in", lambda: editor.zoom_by(1.25)))

    editor.zoom_box = QSpinBox()
    editor.zoom_box.setRange(10, 800)
    editor.zoom_box.setSuffix("%")
    editor.zoom_box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
    editor.zoom_box.setToolTip("Adjust the zoom")
    editor.zoom_box.setFixedWidth(64)
    editor.zoom_box.editingFinished.connect(lambda: editor.set_zoom_percent(editor.zoom_box.value()))
    row.addWidget(editor.zoom_box)

    more = _icon_action("ellipsis", "View more options", None)
    more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    more.setMenu(_view_options_menu(editor, more))
    row.addWidget(more)
    return bar


def _icon_action(icon_name: str, tooltip: str, handler) -> QToolButton:
    button = QToolButton()
    button.setIcon(icons.ui_icon(icon_name, 18))
    button.setIconSize(QSize(18, 18))
    button.setToolTip(tooltip)
    button.setProperty("role", "action")
    if handler is not None:
        button.clicked.connect(lambda checked=False: handler())
    return button


def _view_options_menu(editor, parent) -> QMenu:
    """View more options: the original's list, less mixed reality and help."""
    menu = QMenu(parent)
    menu.addAction("Undo", editor.undo)
    menu.addAction("Redo", editor.redo)
    menu.addSeparator()
    menu.addAction("Paste", editor.paste_clipboard)
    menu.addSeparator()
    menu.addAction("Canvas options", lambda: editor.set_category("Canvas"))
    menu.addSeparator()
    menu.addAction("Show interaction controls", lambda: editor.stage.show_controls(True))
    menu.addAction("Reset view", editor.fit_to_window)
    menu.addAction("Take screenshot", editor.take_screenshot)
    return menu


# ---- right-click menu ----------------------------------------------------


def context_menu(editor) -> QMenu:
    """Right-click menu. With a 2D selection it carries the selection commands."""
    menu = QMenu(editor)
    menu.setStyleSheet(STYLESHEET)

    def item(icon_name: str, text: str, handler, enabled: bool = True) -> None:
        action = menu.addAction(icons.ui_icon(icon_name, 16), text, handler)
        action.setEnabled(enabled)

    item("undo-2", "Undo", editor.undo, editor.undo_button.isEnabled())
    item("redo-2", "Redo", editor.redo, editor.redo_button.isEnabled())
    menu.addSeparator()

    selected = editor.selection is not None and not editor.selection.is_empty()
    if not selected:
        item("frame", "Canvas options", lambda: editor.set_category("Canvas"))
        item("clipboard-paste", "Paste", editor.paste_clipboard)
        menu.addSeparator()
        item("mouse", "Show interaction controls", lambda: editor.stage.show_controls(True))
        item("rotate-ccw", "Reset view", editor.fit_to_window)
        item("image", "Take screenshot", editor.take_screenshot)
        return menu

    item("scissors", "Cut", editor.cut_selection)
    item("copy", "Copy", editor.copy_selection)
    item("clipboard-paste", "Paste", editor.paste_clipboard)
    item("trash-2", "Delete", editor.delete_selection)
    menu.addSeparator()
    item("crop", "Crop", editor.crop_to_selection)
    item("sticker", "Make sticker", editor.make_sticker_from_selection)
    item("wand-sparkles", "Magic select", editor.start_magic_select)
    menu.addSeparator()
    item("flip-horizontal-2", "Flip vertical", lambda: editor.turn_selection("flip_vertical"))
    item("flip-vertical-2", "Flip horizontal", lambda: editor.turn_selection("flip_horizontal"))
    item("rotate-ccw", "Rotate left", lambda: editor.turn_selection("rotate_left"))
    item("rotate-cw", "Rotate right", lambda: editor.turn_selection("rotate_right"))
    menu.addSeparator()
    item("square-dashed-mouse-pointer", "Select all", editor.select_all)
    return menu


# ---- history flyout ------------------------------------------------------


def history_flyout(editor) -> QMenu:
    """History: a slider over the undo stack, as the original's flyout."""
    menu = QMenu(editor)
    body = QWidget()
    column = QVBoxLayout(body)
    column.setContentsMargins(12, 12, 12, 12)
    label = QLabel("History")
    label.setProperty("role", "heading")
    column.addWidget(label)
    hint = QLabel("Slide to review your edits")
    hint.setProperty("role", "value")
    column.addWidget(hint)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setMinimumWidth(320)
    steps = len(editor._undo) + len(editor._redo)
    slider.setRange(0, steps)
    slider.setValue(len(editor._undo))
    slider.setEnabled(steps > 0)
    slider.setToolTip("Slide to review your edits")
    slider.valueChanged.connect(editor.scrub_history)
    column.addWidget(slider)

    record = QCheckBox("Start Recording")
    record.setToolTip(
        "Record your creative process in Clay3D. When you're done, export your history as a video."
    )
    record.setChecked(editor.recorder.recording)
    export = QPushButton("Export as video")
    export.setEnabled(editor.recorder.recording)
    record.toggled.connect(editor.set_recording)
    record.toggled.connect(export.setEnabled)
    export.clicked.connect(lambda checked=False: (menu.close(), editor.export_history_video()))
    buttons = QHBoxLayout()
    buttons.addWidget(record)
    buttons.addStretch(1)
    buttons.addWidget(export)
    column.addLayout(buttons)
    action = QWidgetAction(menu)
    action.setDefaultWidget(body)
    menu.addAction(action)
    menu.setStyleSheet(STYLESHEET)
    return menu


# ---- menu page -----------------------------------------------------------


def menu_page(editor) -> QWidget:
    page = QWidget()
    page.setObjectName("page")
    page.setStyleSheet(STYLESHEET)
    outer = QHBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    sidebar = QWidget()
    sidebar.setObjectName("menuSidebar")
    sidebar.setFixedWidth(SIDE_PANEL_WIDTH)
    column = QVBoxLayout(sidebar)
    column.setContentsMargins(0, 8, 0, 8)
    column.setSpacing(0)

    panes = QStackedWidget()
    save_as = _save_as_pane(editor)
    print_pane = _print_pane(editor)
    settings = _settings_pane(editor)
    editor.open_pane = OpenPane(editor)
    panes.addWidget(QWidget())
    panes.addWidget(save_as)
    panes.addWidget(settings)
    panes.addWidget(editor.open_pane)
    panes.addWidget(print_pane)

    column.addWidget(_menu_item("arrow-left", "Back", editor.hide_menu))
    column.addSpacing(8)
    for icon_name, label, handler in (
        ("file-plus", "New", editor.new_document),
        ("folder-open", "Open", lambda: editor.show_open_pane()),
        ("image-plus", "Insert", editor.insert_image),
        ("save", "Save", editor.save_document),
        ("save-all", "Save as", lambda: panes.setCurrentWidget(save_as)),
        ("printer", "Print", lambda: panes.setCurrentWidget(print_pane)),
        ("settings", "Settings", lambda: panes.setCurrentWidget(settings)),
    ):
        column.addWidget(_menu_item(icon_name, label, handler))
    column.addStretch(1)

    outer.addWidget(sidebar)
    outer.addWidget(panes, 1)
    editor.menu_panes = panes
    return page


class OpenPane(QWidget):
    """Menu > Open: Browse files, then Saved projects as thumbnails."""

    COLUMNS = 5

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setObjectName("menuPane")
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(48, 40, 48, 40)
        self.column.setSpacing(10)
        heading = QLabel("Open")
        heading.setProperty("role", "menuHeading")
        self.column.addWidget(heading)
        browse = QPushButton("Browse files")
        browse.setProperty("role", "primary")
        browse.setMaximumWidth(220)
        browse.clicked.connect(lambda checked=False: editor.open_file())
        self.column.addWidget(browse)
        self.recovered_caption = QLabel("Recovered projects")
        self.recovered_caption.setProperty("role", "section")
        self.column.addWidget(self.recovered_caption)
        self.recovered_holder = QWidget()
        self.column.addWidget(self.recovered_holder)
        caption = QLabel("Saved projects")
        caption.setProperty("role", "section")
        self.column.addWidget(caption)
        self.grid_holder = QWidget()
        self.column.addWidget(self.grid_holder)
        self.empty = QLabel("Files you open or save show up here.")
        self.empty.setProperty("role", "value")
        self.column.addWidget(self.empty)
        self.column.addStretch(1)

    def rebuild(self) -> None:
        from PySide6.QtWidgets import QGridLayout

        from Clay3D import recent

        from Clay3D.document import recovered_projects

        own = self.editor.recovery_path
        rescued = [str(p) for p in recovered_projects() if p != own]
        self.recovered_holder = self._replace_grid(
            self.recovered_holder, rescued, lambda p: self.editor.open_recovered(p), recovered=True
        )
        self.recovered_caption.setVisible(bool(rescued))
        self.recovered_holder.setVisible(bool(rescued))
        files = recent.recent_files()
        self.grid_holder = self._replace_grid(self.grid_holder, files, self.editor.open_path)
        self.empty.setVisible(not files)

    def _replace_grid(self, old: QWidget, paths, open_one, recovered: bool = False) -> QWidget:
        from PySide6.QtWidgets import QGridLayout

        index = self.column.indexOf(old)
        old.setParent(None)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        for i, path in enumerate(paths):
            grid.addWidget(self._file_button(path, open_one, recovered), i // self.COLUMNS, i % self.COLUMNS)
        grid.setColumnStretch(self.COLUMNS, 1)
        self.column.insertWidget(index, holder)
        return holder

    def _file_button(self, path: str, open_one, recovered: bool = False) -> QToolButton:
        from pathlib import Path

        from PySide6.QtGui import QIcon, QImage, QPixmap

        from Clay3D import recent

        button = QToolButton()
        button.setProperty("role", "tile")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setFixedSize(132, 140)
        name = self.editor.recovered_age(Path(path)) if recovered else Path(path).name
        button.setText(name if len(name) <= 18 else name[:15] + "...")
        button.setToolTip(path)
        preview = recent.thumbnail(path)
        if preview is not None:
            data = preview.tobytes()
            image = QImage(data, preview.width, preview.height, preview.width * 4,
                           QImage.Format.Format_RGBA8888).copy()
            button.setIcon(QIcon(QPixmap.fromImage(image)))
            button.setIconSize(QSize(recent.THUMB, recent.THUMB))
        button.clicked.connect(lambda checked=False, p=path: open_one(p))
        return button


def _menu_item(icon_name: str, label: str, handler) -> QToolButton:
    button = QToolButton()
    button.setText(label)
    button.setIcon(icons.ui_icon(icon_name, 20))
    button.setIconSize(QSize(20, 20))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setProperty("role", "menuItem")
    button.clicked.connect(lambda checked=False: handler())
    return button


def _pane(title: str) -> tuple[QWidget, QVBoxLayout]:
    pane = QWidget()
    pane.setObjectName("menuPane")
    column = QVBoxLayout(pane)
    column.setContentsMargins(48, 40, 48, 40)
    column.setSpacing(10)
    heading = QLabel(title)
    heading.setProperty("role", "menuHeading")
    column.addWidget(heading)
    return pane, column


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "value")
    return label


def _save_as_pane(editor) -> QWidget:
    pane, column = _pane("Save as")
    for label, hint, handler in (
        ("Image", "PNG, JPEG, BMP, GIF or TIFF, with a preview", editor.open_save_as),
        ("3D model", "OBJ, PLY, STL or glTF", editor.export_model),
        ("Clay3D project", "Canvas and 3D objects, editable later", editor.save_scene_as),
    ):
        button = QPushButton(f"{label}\n{hint}")
        button.setProperty("role", "saveChoice")
        button.clicked.connect(lambda checked=False, fn=handler: fn())
        column.addWidget(button)
    column.addStretch(1)
    return pane


def _print_pane(editor) -> QWidget:
    pane, column = _pane("Print")
    column.addWidget(_hint("Choose a printer and print your work."))
    button = QPushButton("2D print")
    button.setProperty("role", "primary")
    button.setMaximumWidth(220)
    button.clicked.connect(lambda checked=False: editor.print_canvas())
    column.addWidget(button)
    column.addStretch(1)
    return pane


def _settings_pane(editor) -> QWidget:
    """Settings, in the original's order: compact view, perspective, display quality."""
    pane, column = _pane("Settings")

    editor.compact_switch = QCheckBox("Use compact view")
    editor.compact_switch.setToolTip("Reduce the size of the sidebar to make more room in your workspace.")
    editor.compact_switch.toggled.connect(editor.set_compact_view)
    column.addWidget(editor.compact_switch)
    column.addWidget(_hint("Reduce the size of the sidebar to make more room in your workspace."))

    editor.perspective_switch = QCheckBox("Show perspective")
    editor.perspective_switch.setToolTip(
        "Create in a 3D workspace that shows depth and relative size. "
        "(Recommended for 3D projects)."
    )
    editor.perspective_switch.setChecked(editor.scene.camera.perspective)
    editor.perspective_switch.toggled.connect(editor.set_perspective)
    column.addWidget(editor.perspective_switch)
    column.addWidget(_hint(
        "Create in a 3D workspace that shows depth and relative size. (Recommended for 3D projects)."
    ))

    column.addWidget(QLabel("Adjust display quality"))
    column.addWidget(_hint("Choose how Clay3D renders to improve your experience on this device."))
    editor.quality_choice = QComboBox()
    for level in ("Normal", "High", "Ultra"):
        editor.quality_choice.addItem(f"{level} (recommended)" if level == "High" else level, level)
    editor.quality_choice.setMaximumWidth(250)
    editor.quality_choice.currentIndexChanged.connect(
        lambda i: editor.set_display_quality(editor.quality_choice.itemData(i))
    )
    column.addWidget(editor.quality_choice)

    line = QFrame()
    line.setProperty("role", "rule")
    line.setFrameShape(QFrame.Shape.HLine)
    column.addWidget(line)
    about = QLabel("About\n\nClay3D. Paint 3D-inspired editor for Linux.")
    about.setWordWrap(True)
    about.setProperty("role", "value")
    column.addWidget(about)
    column.addStretch(1)
    return pane
