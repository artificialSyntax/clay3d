"""Show interaction controls: the Controls card, bottom-left of the workspace.

Tabs per input; each lists Orbit, Pan, Zoom and Reset with the original's
wording, trimmed to what Clay3D does with that input.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Clay3D import icons

CARD_SIZE = (396, 194)

MAPPINGS = {
    "Mouse": (
        ("orbit", "Orbit", "Press and hold Left Mouse button and drag to orbit around your model."),
        ("hand", "Pan", "Press and hold Right Mouse button and drag to pan across your model."),
        ("zoom-in", "Zoom", "Scroll your wheel up or down to zoom in or out."),
        ("rotate-ccw", "Reset", "Double click to reset your view."),
    ),
    "Keyboard": (
        ("orbit", "Orbit", "Hold the Ctrl key and press the arrow keys to orbit around your model."),
        ("hand", "Pan", "Hold the Alt key and press the arrow keys to pan across your model."),
        ("zoom-in", "Zoom", "Press the Page Up key to zoom in or the Page Down key to zoom out."),
        ("rotate-ccw", "Reset", "Press the Home key to reset your view."),
    ),
}
TAB_ICONS = {"Mouse": "mouse", "Keyboard": "keyboard"}


class ControlsCard(QFrame):
    def __init__(self, parent, on_close):
        super().__init__(parent)
        self.setObjectName("controlsCard")
        self.setFixedSize(*CARD_SIZE)
        column = QVBoxLayout(self)
        column.setContentsMargins(14, 10, 10, 10)
        column.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("Controls")
        title.setProperty("role", "heading")
        top.addWidget(title)
        top.addStretch(1)
        self.tabs = QButtonGroup(self)
        pages = QStackedWidget()
        for index, name in enumerate(MAPPINGS):
            tab = QToolButton()
            tab.setProperty("role", "tile")
            tab.setCheckable(True)
            tab.setChecked(index == 0)
            tab.setIcon(icons.ui_icon(TAB_ICONS[name], 18))
            tab.setToolTip(name)
            tab.clicked.connect(lambda checked=False, i=index: pages.setCurrentIndex(i))
            self.tabs.addButton(tab)
            top.addWidget(tab)
            pages.addWidget(self._page(name))
        close = QToolButton()
        close.setProperty("role", "tile")
        close.setIcon(icons.ui_icon("x", 16))
        close.setToolTip("Close controls")
        close.clicked.connect(lambda checked=False: on_close())
        top.addWidget(close)
        column.addLayout(top)
        column.addWidget(pages, 1)

    def _page(self, name: str) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        for index, (icon_name, label, detail) in enumerate(MAPPINGS[name]):
            cell = QWidget()
            cell.setToolTip(detail)
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 0, 0, 0)
            glyph = QLabel()
            glyph.setPixmap(icons.ui_pixmap(icon_name, 22))
            glyph.setFixedSize(QSize(26, 26))
            row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
            text = QLabel(f"<b>{label}</b><br>{detail}")
            text.setWordWrap(True)
            text.setProperty("role", "value")
            row.addWidget(text, 1)
            grid.addWidget(cell, index // 2, index % 2)
        return page
