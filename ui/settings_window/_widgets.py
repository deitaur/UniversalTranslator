"""Style constants + reusable widgets (collapsible Section + tiny form helpers)
shared across the Settings window sections.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from config import C


# ── Fonts ─────────────────────────────────────────────────────────────────────

_F_LABEL  = QFont("Segoe UI", 9)
_F_INPUT  = QFont("Consolas", 9)
_F_HDR    = QFont("Segoe UI Semibold", 9)
_F_MONO   = QFont("Consolas", 8)


# ── Stylesheets ───────────────────────────────────────────────────────────────

_SS_INPUT = (
    f"QLineEdit {{ background: {C['card_alt']}; color: {C['text']};"
    f" border: 1px solid {C['border']}; border-radius: 3px;"
    f" padding: 1px 5px; min-height: 20px; }}"
)
_SS_COMBO = (
    f"QComboBox {{ background: {C['card_alt']}; color: {C['text']};"
    f" border: 1px solid {C['border']}; border-radius: 3px;"
    f" padding: 1px 5px; min-height: 20px; }}"
    f"QComboBox::drop-down {{ border: none; }}"
    f"QComboBox QAbstractItemView {{ background: {C['card']}; color: {C['text']}; }}"
)
_SS_CHECK = (
    f"QCheckBox {{ color: {C['text']}; background: transparent; font-size: 9px; }}"
)
_SS_RADIO = (
    f"QRadioButton {{ color: {C['text']}; background: transparent; font-size: 9px; }}"
)


# ── Collapsible Section ───────────────────────────────────────────────────────

class _Section(QWidget):
    """ZBrush-style collapsible section with ▸/▾ header button."""

    def __init__(self, title: str, parent=None, expanded: bool = False):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header button
        self._btn = QPushButton()
        self._btn.setCheckable(True)
        self._btn.setChecked(expanded)
        self._btn.setFixedHeight(22)
        self._btn.setFont(_F_HDR)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(
            f"QPushButton {{ background: {C['surface']}; color: {C['text']};"
            f" border: none; border-top: 1px solid {C['border']};"
            f" text-align: left; padding-left: 8px; }}"
            f"QPushButton:hover {{ background: {C['card']}; }}"
        )
        self._set_title(title, expanded)
        self._btn.toggled.connect(self._toggle)
        outer.addWidget(self._btn)

        # Body
        self._body = QWidget()
        self._body.setStyleSheet(
            f"background: {C['bg']};"
            f"QLabel {{ background: transparent; border: none; color: {C['text']}; }}"
        )
        self._body_lo = QVBoxLayout(self._body)
        self._body_lo.setContentsMargins(10, 4, 8, 6)
        self._body_lo.setSpacing(3)
        self._body.setVisible(expanded)
        outer.addWidget(self._body)

        self._title = title

    def _set_title(self, title: str, expanded: bool):
        arrow = "▾" if expanded else "▸"
        self._btn.setText(f"  {arrow}  {title}")

    def _toggle(self, checked: bool):
        self._body.setVisible(checked)
        self._set_title(self._title, checked)

    def add(self, widget: QWidget):
        self._body_lo.addWidget(widget)

    def add_layout(self, lo):
        self._body_lo.addLayout(lo)

    def add_spacing(self, n: int = 4):
        self._body_lo.addSpacing(n)


# ── Tiny form helpers ─────────────────────────────────────────────────────────

def _lbl(text: str, color: str = None, bold: bool = False) -> QLabel:
    w = QLabel(text)
    f = QFont("Segoe UI Semibold" if bold else "Segoe UI", 9)
    w.setFont(f)
    w.setStyleSheet(f"color: {color or C['subtext']}; background: transparent; border: none;")
    return w


def _input(text: str = "", placeholder: str = "", mono: bool = False, pw: bool = False) -> QLineEdit:
    w = QLineEdit(text)
    w.setFont(_F_INPUT if mono else _F_LABEL)
    if placeholder:
        w.setPlaceholderText(placeholder)
    if pw:
        w.setEchoMode(QLineEdit.EchoMode.Password)
    w.setStyleSheet(_SS_INPUT)
    w.setFixedHeight(22)
    return w


def _combo(items: list[str], current: str = "") -> QComboBox:
    w = QComboBox()
    w.setFont(_F_LABEL)
    w.addItems(items)
    if current:
        w.setCurrentText(current)
    w.setStyleSheet(_SS_COMBO)
    w.setFixedHeight(22)
    return w


def _btn(text: str, bg: str = None, fg: str = None, height: int = 22) -> QPushButton:
    b = QPushButton(text)
    b.setFont(_F_LABEL)
    b.setFixedHeight(height)
    _bg = bg or C["card_alt"]
    _fg = fg or C["text"]
    b.setStyleSheet(
        f"QPushButton {{ background: {_bg}; color: {_fg}; border: 1px solid {C['border']};"
        f" border-radius: 3px; padding: 0 8px; }}"
        f"QPushButton:hover {{ background: {C['surface']}; }}"
        f"QPushButton:disabled {{ color: {C['muted']}; }}"
    )
    return b


def _row(*widgets, stretch: bool = True) -> QHBoxLayout:
    lo = QHBoxLayout()
    lo.setContentsMargins(0, 0, 0, 0)
    lo.setSpacing(4)
    for w in widgets:
        if isinstance(w, int):
            lo.addSpacing(w)
        elif isinstance(w, QWidget):
            lo.addWidget(w)
        else:
            lo.addLayout(w)
    if stretch:
        lo.addStretch()
    return lo
