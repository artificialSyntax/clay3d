"""Chrome colours + QSS."""

ACCENT = "#0078D4"
ACCENT_SOFT = "#E7F1FB"
ACCENT_EDGE = "#7FB9E8"
CHROME = "#FFFFFF"
PAGE = "#F3F2F1"
STAGE = "#DEE4EA"
INK = "#201F1E"
MUTED = "#605E5C"
LINE = "#E1DFDD"
HOVER = "#F3F2F1"

# The default swatches, arranged as two rows the way the original's
# colour section is.
PALETTE = (
    (0, 0, 0), (88, 88, 88), (153, 0, 0), (237, 28, 36), (255, 102, 0),
    (255, 220, 0), (0, 168, 51), (0, 140, 255), (40, 64, 220), (163, 0, 196),
    (255, 255, 255), (168, 168, 168), (166, 90, 48), (255, 105, 180), (255, 186, 0),
    (255, 236, 130), (140, 220, 0), (0, 200, 220), (80, 140, 255), (186, 120, 255),
)

STYLESHEET = f"""
QWidget#page {{
    background: {PAGE};
    color: {INK};
}}
QWidget#chrome, QWidget#rightPanel, QWidget#bottomBar, QWidget#tabStrip {{
    background: {CHROME};
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

QToolButton[role="tab"] {{
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 6px 12px 4px 12px;
    color: {INK};
    font-size: 12px;
}}
QToolButton[role="tab"]:hover {{
    background: {HOVER};
}}
QToolButton[role="tab"]:checked {{
    border-bottom: 3px solid {ACCENT};
    color: {ACCENT};
    font-weight: 600;
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
