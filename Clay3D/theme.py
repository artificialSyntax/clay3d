"""Chrome colours + QSS."""

# Chrome palette.
ACCENT = "#0064B6"
ACCENT_SOFT = "#DCE9F5"
ACCENT_EDGE = "#7FB0DA"
CHROME = "#F0F2F3"          # side panel, tools bar
TOP_BAR = "#363941"
TOP_BAR_INK = "#FFFFFF"
TOP_BAR_DISABLED = "#B9BAC1"
PAGE = "#F0F2F3"
STAGE = "#DEE4EA"
INK = "#222255"
MUTED = "#5A5A7A"
LINE = "#E2E2E2"
HOVER = "#E2E7EC"
COMMIT = "#2A7A46"          # Done
CANCEL = "#B93430"          # Cancel

# The 18 permanent swatches, in the original's order: six across, three down.
PALETTE = (
    (255, 255, 255), (195, 195, 195), (88, 88, 88), (0, 0, 0), (136, 0, 27), (236, 28, 36),
    (255, 127, 39), (255, 202, 24), (253, 236, 166), (255, 242, 0), (196, 255, 14), (14, 209, 69),
    (140, 255, 251), (0, 168, 243), (63, 72, 204), (184, 61, 186), (255, 174, 200), (185, 122, 86),
)
PALETTE_COLUMNS = 6

# Material dropdown, as named in the original, with the look each gives.
MATERIALS = (
    ("Matte", 0.05, 0.0),
    ("Eggshell", 0.35, 0.0),
    ("Gloss", 0.85, 0.0),
    ("Polished metal", 0.90, 1.0),
    ("Satin metal", 0.55, 1.0),
    ("Dull metal", 0.25, 1.0),
)

STYLESHEET = f"""
QWidget#page {{
    background: {PAGE};
    color: {INK};
}}
QWidget#chrome, QWidget#rightPanel, QWidget#saveAsSidebar, QWidget#toolsBar, QWidget#menuPane {{
    background: {CHROME};
}}
QWidget#rightPanel {{
    border-left: 1px solid #BEBEBE;
}}
QWidget#topBar {{
    background: {TOP_BAR};
}}
QToolButton[role="topButton"], QToolButton[role="tab"] {{
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 4px 6px 2px 6px;
    color: {TOP_BAR_INK};
    font-size: 12px;
}}
QToolButton[role="topButton"]:hover, QToolButton[role="tab"]:hover {{
    border-bottom: 3px solid {ACCENT};
}}
QToolButton[role="topButton"]:disabled {{
    color: {TOP_BAR_DISABLED};
}}
QToolButton[role="tab"]:checked {{
    border-bottom: 3px solid {TOP_BAR_INK};
    font-weight: 600;
}}
QWidget#topBar QToolButton[role="action"] {{
    color: {TOP_BAR_INK};
}}
QWidget#topBar QToolButton[role="action"]:checked, QWidget#topBar QToolButton[role="action"]:hover {{
    background: transparent;
    border-color: transparent;
}}
QWidget#menuSidebar {{
    background: #E9ECED;
}}
QToolButton[role="menuItem"] {{
    background: transparent;
    border: none;
    padding: 12px 20px;
    color: {INK};
    font-size: 14px;
    text-align: left;
    min-width: 224px;
}}
QToolButton[role="menuItem"]:hover {{
    background: {ACCENT};
    color: #FFFFFF;
}}
QLabel[role="menuHeading"] {{
    font-size: 26px;
    font-weight: 300;
    padding-bottom: 12px;
}}
QFrame#controlsCard {{
    background: #FFFFFF;
    border: 1px solid #BEBEBE;
    border-radius: 4px;
}}
QToolButton[role="compactHeader"] {{
    background: {HOVER};
    border: none;
    border-bottom: 1px solid {LINE};
    color: {ACCENT};
    font-size: 11px;
    padding: 6px 2px;
}}
QToolButton[role="compactHeader"]:hover {{
    background: {ACCENT_SOFT};
}}
QToolButton[role="commit"] {{
    background: {COMMIT};
    border: none;
    border-radius: 2px;
}}
QToolButton[role="cancel"] {{
    background: {CANCEL};
    border: none;
    border-radius: 2px;
}}
QToolButton[role="commit"]:hover, QToolButton[role="cancel"]:hover {{
    border: 2px solid {INK};
}}
QPushButton[role="saveChoice"] {{
    text-align: left;
    padding: 12px 16px;
    min-width: 280px;
    max-width: 420px;
}}
/* A styled background does not reach child widgets on its own, so the
   panel bodies and the viewports they sit in are named and painted too. */
QWidget#panelBody {{
    background: {CHROME};
}}
QScrollArea > QWidget > QWidget {{
    background: {CHROME};
}}
QLabel {{
    color: {INK};
    background: transparent;
}}
QLabel[role="heading"] {{
    color: {ACCENT};
    font-size: 15px;
    font-weight: 600;
    padding: 2px 0 6px 0;
}}
QLabel[role="section"] {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
    padding-top: 6px;
}}
QLabel[role="value"] {{
    color: {MUTED};
    font-size: 11px;
}}

QToolButton[role="tile"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px;
}}
QToolButton[role="tile"]:hover {{
    background: {HOVER};
    border-color: {LINE};
}}
QToolButton[role="tile"]:checked {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT_EDGE};
}}

QToolButton[role="action"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 5px 8px;
    color: {INK};
}}
QToolButton[role="action"]:hover {{
    background: {HOVER};
    border-color: {LINE};
}}
QToolButton[role="action"]:checked {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT_EDGE};
}}
QToolButton[role="action"]:disabled {{
    color: #BEBBB8;
}}

QPushButton {{
    background: {CHROME};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: 2px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:checked {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton[role="primary"] {{
    background: {ACCENT};
    color: #FFFFFF;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{
    background: #106EBE;
}}

QSlider::groove:horizontal {{
    height: 3px;
    background: #C8C6C4;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {CHROME};
    border: 2px solid {ACCENT};
    width: 12px;
    height: 12px;
    margin: -6px 0;
    border-radius: 8px;
}}

QComboBox, QSpinBox, QLineEdit {{
    background: {CHROME};
    border: 1px solid #C8C6C4;
    border-radius: 2px;
    padding: 4px 6px;
    color: {INK};
}}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{
    border-color: {ACCENT};
}}
QCheckBox {{
    color: {INK};
    spacing: 7px;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #C8C6C4;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QFrame[role="rule"] {{
    color: {LINE};
    background: {LINE};
    max-height: 1px;
    border: none;
}}
"""
