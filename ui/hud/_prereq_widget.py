"""ZBrush-style non-blocking prerequisite overlay — appears near cursor."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.hud._screen import _screen_w
from ui.hud._style import (
    _ZB_BG, _ZB_DIM, _ZB_ERR, _ZB_FONT, _ZB_OK, _ZB_SIZE, _ZB_TEXT,
)


class _PrereqWidget(QWidget):
    """
    Non-blocking prereq check overlay — appears near cursor.
    Rows: [dot] label  [status]  [action-btn?]
    """
    _W = 340

    def __init__(self, cx: int, cy: int, checks: dict, on_proceed, on_cancel):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._on_proceed = on_proceed
        self._on_cancel  = on_cancel
        self._checks     = checks
        self._pkg_missing = []
        for key, c in checks.items():
            if key == "packages" and c.get("missing_pip"):
                self._pkg_missing.extend(c["missing_pip"])

        self._build_ui()
        sw = _screen_w()
        x  = min(cx + 16, sw - self._W - 12)
        y  = cy + 20
        self.move(x, y)
        self.show()

    def _build_ui(self):
        self.setFixedWidth(self._W)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(3)

        _lf = QFont(_ZB_FONT, _ZB_SIZE)
        _bf = QFont(_ZB_FONT, _ZB_SIZE)
        _bf.setBold(True)

        # ── Header row ──
        hdr = QHBoxLayout()
        hdr.setSpacing(5)
        t = QLabel("Необходимые компоненты")
        t.setFont(_bf)
        t.setStyleSheet(f"color: {_ZB_TEXT};")
        hdr.addWidget(t)
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Check rows ──
        for key, c in self._checks.items():
            ok, optional = c["ok"], c.get("optional", False)
            if ok is True:
                dot, color = "●", _ZB_OK
            elif ok is False and optional:
                dot, color = "●", "#c8a040"
            elif ok is False:
                dot, color = "●", _ZB_ERR
            else:
                dot, color = "◦", _ZB_DIM

            row = QHBoxLayout()
            row.setSpacing(5)

            d = QLabel(dot)
            d.setFont(QFont(_ZB_FONT, 7))
            d.setFixedWidth(9)
            d.setStyleSheet(f"color: {color};")
            row.addWidget(d)

            lbl = QLabel(c["label"])
            lbl.setFont(_lf)
            lbl.setStyleSheet(f"color: {_ZB_TEXT};")
            lbl.setFixedWidth(130)
            row.addWidget(lbl)

            detail = QLabel(c["detail"][:45])
            detail.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
            detail.setStyleSheet(f"color: {color if ok is not True else _ZB_DIM};")
            row.addWidget(detail, 1)

            root.addLayout(row)

        # ── Divider ──
        div = QLabel()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #505050;")
        root.addWidget(div)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.addStretch()

        _bs = (f"QPushButton {{ background:#505050; color:{_ZB_TEXT}; border:none;"
               f" padding:2px 8px; font-size:8pt; }}"
               f"QPushButton:hover {{ background:#686868; }}")

        cancel = QPushButton("Отмена")
        cancel.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        cancel.setStyleSheet(_bs)
        cancel.clicked.connect(self._cancel)
        btn_row.addWidget(cancel)

        if self._pkg_missing:
            install = QPushButton("Скачать и установить")
            install.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
            install.setStyleSheet(_bs.replace(_ZB_TEXT, "#c8a040"))
            install.clicked.connect(self._install)
            btn_row.addWidget(install)

        ready = all(c["ok"] is not False for c in self._checks.values()
                    if not c.get("optional"))
        proceed_lbl = "Продолжить" if ready else "Всё равно продолжить"
        proceed_col = _ZB_OK if ready else "#c8a040"
        proceed = QPushButton(proceed_lbl)
        proceed.setFont(QFont(_ZB_FONT, _ZB_SIZE - 1))
        proceed.setStyleSheet(_bs.replace(_ZB_TEXT, proceed_col))
        proceed.clicked.connect(self._proceed)
        btn_row.addWidget(proceed)

        root.addLayout(btn_row)
        self.adjustSize()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 2, 2)
        p.fillPath(path, QColor(_ZB_BG))

    def _proceed(self):
        self.close()
        if self._on_proceed:
            self._on_proceed()

    def _cancel(self):
        self.close()
        if self._on_cancel:
            self._on_cancel()

    def _install(self):
        import subprocess
        try:
            subprocess.Popen(
                ["cmd", "/k", "pip", "install"] + self._pkg_missing,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            from ui.notifications import show_toast
            show_toast(f"Error: {e}")

    def mousePressEvent(self, _e):
        pass   # don't close on click — user needs to read it

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._cancel()
