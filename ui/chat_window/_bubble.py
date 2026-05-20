"""Single chat message bubble — selectable text + copy button."""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget,
)

from config import C


class _Bubble(QWidget):
    """A single chat message bubble with selectable text and a copy button."""

    def __init__(self, role: str, text: str, role_label: str, role_color: str,
                 font_family: str, font_size: int):
        super().__init__()
        self._role      = role
        self._text      = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        is_user    = (role == "user")
        bubble_bg  = C["card"] if is_user else C["surface"]
        text_color = C["text"] if is_user else C["green"]
        pad_l, pad_r = (60, 10) if is_user else (10, 60)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(pad_l, 2, pad_r, 2)
        outer.setSpacing(2)

        # Role row
        role_row = QHBoxLayout()
        role_row.setSpacing(6)
        rl = QLabel("You" if is_user else role_label)
        rl.setFont(QFont("Segoe UI", 9))
        rl.setStyleSheet(f"color: {C['muted'] if is_user else role_color}; background: transparent;")
        role_row.addWidget(rl)

        copy_btn = QPushButton("[copy]")
        copy_btn.setFont(QFont("Segoe UI", 8))
        copy_btn.setFlat(True)
        copy_btn.setStyleSheet(
            f"QPushButton {{ color:{C['muted']}; background:transparent; border:none; }}"
            f"QPushButton:hover {{ color:{C['text']}; }}"
        )
        copy_btn.clicked.connect(self._copy)
        role_row.addWidget(copy_btn)
        role_row.addStretch()
        outer.addLayout(role_row)

        # Bubble
        bubble = QFrame()
        bubble.setStyleSheet(
            f"QFrame {{ background:{bubble_bg}; border:1px solid {C['border']};"
            f" border-radius:8px; }}"
            f"QTextEdit {{ background:{bubble_bg}; color:{text_color};"
            f" border:none; }}"
        )
        b_lo = QVBoxLayout(bubble)
        b_lo.setContentsMargins(0, 0, 0, 0)

        self._text_edit = QTextEdit()
        self._text_edit.setFont(QFont(font_family, font_size))
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlainText(text)
        self._text_edit.setFrameShape(QFrame.Shape.NoFrame)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._text_edit.document().contentsChanged.connect(self._adjust_height)
        b_lo.addWidget(self._text_edit)
        outer.addWidget(bubble)

        QTimer.singleShot(0, self._adjust_height)

    def _adjust_height(self):
        doc_h = int(self._text_edit.document().size().height()) + 12
        self._text_edit.setFixedHeight(max(doc_h, 36))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-measure after Qt has reflowed the document to the new viewport width
        QTimer.singleShot(0, self._adjust_height)

    def set_text(self, text: str):
        self._text = text
        self._text_edit.setPlainText(text)

    def update_font(self, family: str, size: int):
        self._text_edit.setFont(QFont(family, size))
        QTimer.singleShot(0, self._adjust_height)

    def _copy(self):
        from win32.clipboard import set_clipboard_text
        set_clipboard_text(self._text)

    def get_text(self) -> str:
        return self._text
