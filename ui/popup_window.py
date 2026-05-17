"""Translation popup window — PySide6, thread-safe via QObject controller."""

import logging
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from config import APP_NAME, ICON_FILE, C
from utils.language import LANGUAGES, get_source_lang, get_target_lang

log = logging.getLogger("popup_window")

_BADGE_COLORS = {"deepl": C["accent"], "google": C["green"], "yandex": C["yellow"]}


def _engine_display_name(engine: str) -> str:
    return {"deepl": "DeepL", "google": "Google Translate", "yandex": "Yandex Translate"}.get(engine, engine)


class _PopupWidget(QWidget):

    def __init__(self, original: str, translated: str, engine: str, target_lang: Optional[str]):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._translated  = translated
        self._engine      = engine
        self._target_lang = target_lang
        self._speaking    = False

        self.setWindowTitle(APP_NAME)
        self.resize(620, 520)
        self.setMinimumSize(440, 380)
        self.setStyleSheet(f"background: {C['bg']};")

        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self._build_ui(original, translated, engine, target_lang)

        self._autoclose = QTimer(self)
        self._autoclose.setSingleShot(True)
        self._autoclose.timeout.connect(self.close)
        self._autoclose.start(10_000)

    # ── Build ──

    def _build_ui(self, original, translated, engine, target_lang):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(f"background: {C['surface']}; border: none;")
        hdr_lo = QHBoxLayout(hdr)
        hdr_lo.setContentsMargins(16, 8, 16, 8)

        title = QLabel(APP_NAME)
        title.setFont(QFont("Segoe UI Semibold", 15))
        title.setStyleSheet(f"color: {C['text']}; background: transparent;")
        hdr_lo.addWidget(title)
        hdr_lo.addStretch()

        self._badge = QLabel()
        self._badge.setFont(QFont("Segoe UI Semibold", 10))
        hdr_lo.addWidget(self._badge)
        root.addWidget(hdr)

        # Content
        body = QWidget()
        body.setStyleSheet(f"background: {C['bg']};")
        body_lo = QVBoxLayout(body)
        body_lo.setContentsMargins(20, 16, 20, 8)
        body_lo.setSpacing(6)

        self._orig_label = QLabel()
        self._orig_label.setFont(QFont("Segoe UI Semibold", 10))
        self._orig_label.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        body_lo.addWidget(self._orig_label)

        self._orig_box = QTextEdit()
        self._orig_box.setFont(QFont("Segoe UI", 12))
        self._orig_box.setReadOnly(True)
        self._orig_box.setStyleSheet(
            f"QTextEdit {{ background: {C['card']}; color: {C['text']};"
            f" border: 1px solid {C['border']}; border-radius: 8px; padding: 6px; }}"
        )
        body_lo.addWidget(self._orig_box, 1)

        arrow = QLabel("  >")
        arrow.setFont(QFont("Segoe UI", 14))
        arrow.setStyleSheet(f"color: {C['accent']}; background: transparent;")
        body_lo.addWidget(arrow)

        self._trans_label = QLabel()
        self._trans_label.setFont(QFont("Segoe UI Semibold", 10))
        self._trans_label.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        body_lo.addWidget(self._trans_label)

        self._trans_box = QTextEdit()
        self._trans_box.setFont(QFont("Segoe UI", 12))
        self._trans_box.setReadOnly(True)
        self._trans_box.setStyleSheet(
            f"QTextEdit {{ background: {C['card']}; color: {C['green']};"
            f" border: 1px solid {C['border']}; border-radius: 8px; padding: 6px; }}"
        )
        body_lo.addWidget(self._trans_box, 1)

        root.addWidget(body, 1)

        # Footer
        footer = QFrame()
        footer.setFixedHeight(72)
        footer.setStyleSheet(f"background: {C['surface']}; border: none;")
        foot_lo = QHBoxLayout(footer)
        foot_lo.setContentsMargins(16, 12, 16, 12)

        self._usage_lbl = QLabel()
        self._usage_lbl.setFont(QFont("Segoe UI", 10))
        self._usage_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        foot_lo.addWidget(self._usage_lbl)
        foot_lo.addStretch()

        _btn = "border-radius: 8px; padding: 4px 14px; font-family: 'Segoe UI'; font-size: 12px;"

        self._speak_btn = QPushButton("  ▶  ")
        self._speak_btn.setFixedHeight(36)
        self._speak_btn.setStyleSheet(
            f"QPushButton {{ {_btn} background: {C['surface']}; color: {C['accent']};"
            f" border: 1px solid {C['border']}; }}"
            f"QPushButton:hover {{ background: {C['card_alt']}; }}"
        )
        self._speak_btn.clicked.connect(self._do_speak)
        foot_lo.addWidget(self._speak_btn)

        self._copy_btn = QPushButton("  Copy  ")
        self._copy_btn.setFixedHeight(36)
        self._copy_btn.setStyleSheet(
            f"QPushButton {{ {_btn} background: {C['accent']}; color: {C['bg']}; border: none; }}"
            f"QPushButton:hover {{ background: #7ba4e8; }}"
        )
        self._copy_btn.clicked.connect(self._do_copy)
        foot_lo.addWidget(self._copy_btn)

        close_btn = QPushButton("  Close  ")
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(
            f"QPushButton {{ {_btn} background: {C['card_alt']}; color: {C['text']}; border: none; }}"
            f"QPushButton:hover {{ background: {C['border']}; }}"
        )
        close_btn.clicked.connect(self.close)
        foot_lo.addWidget(close_btn)

        root.addWidget(footer)

        # Populate
        self._apply_content(original, translated, engine, target_lang)

    def _apply_content(self, original, translated, engine, target_lang):
        src_label = LANGUAGES.get(get_source_lang(), get_source_lang()).upper()
        tgt_code  = target_lang or get_target_lang()
        tgt_label = LANGUAGES.get(tgt_code, tgt_code).upper()

        self._orig_label.setText(f"ORIGINAL  ({src_label})")
        self._orig_box.setPlainText(original)
        self._trans_label.setText(f"TRANSLATION  ({tgt_label})")
        self._trans_box.setPlainText(translated)

        color = _BADGE_COLORS.get(engine, C["accent"])
        self._badge.setText(_engine_display_name(engine))
        self._badge.setStyleSheet(
            f"color: {C['bg']}; background: {color}; border-radius: 6px; padding: 2px 10px;"
        )
        self._refresh_usage(engine)

    def _refresh_usage(self, engine: str):
        from globals import usage_data
        if engine == "deepl" and usage_data["character_limit"] > 0:
            rem = usage_data["character_limit"] - usage_data["character_count"]
            pct = rem / usage_data["character_limit"] * 100
            txt = f"{rem:,} / {usage_data['character_limit']:,} chars left  ({pct:.1f}%)"
        elif engine == "deepl":
            txt = "DeepL usage data unavailable"
        else:
            txt = f"{_engine_display_name(engine)} - free, no limit"
        self._usage_lbl.setText(txt)

    # ── User interactions ──

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            self._reset_autoclose()

    def mousePressEvent(self, _e):
        self._reset_autoclose()

    def _reset_autoclose(self):
        self._autoclose.start(10_000)

    def _do_copy(self):
        self._reset_autoclose()
        from win32.clipboard import set_clipboard_text
        set_clipboard_text(self._translated)
        self._copy_btn.setText("  Copied!  ")
        QTimer.singleShot(1500, lambda: self._copy_btn.setText("  Copy  "))

    def _do_speak(self):
        self._reset_autoclose()
        from services.ai.tts import is_available, speak, stop
        if not is_available():
            return
        if self._speaking:
            stop()
            self._speaking = False
            self._speak_btn.setText("  ▶  ")
        else:
            self._speaking = True
            self._speak_btn.setText("  ■  ")
            lang = self._target_lang or get_target_lang()
            speak(self._translated, lang_code=lang)
            self._poll_tts()

    def _poll_tts(self):
        from services.ai.tts import _speak_lock
        if not _speak_lock.locked():
            self._speaking = False
            try:
                self._speak_btn.setText("  ▶  ")
            except RuntimeError:
                pass
        else:
            QTimer.singleShot(200, self._poll_tts)

    # ── Update in place ──

    def update_content(self, original: str, translated: str, engine: str, target_lang: Optional[str]):
        from services.ai.tts import stop
        stop()
        self._translated  = translated
        self._engine      = engine
        self._target_lang = target_lang
        self._speaking    = False
        self._speak_btn.setText("  ▶  ")
        self._copy_btn.setText("  Copy  ")
        self._apply_content(original, translated, engine, target_lang)
        self._reset_autoclose()


class PopupController(QObject):
    """Thread-safe controller. Lives on the Qt main thread."""
    _show_sig = Signal(str, str, str, str)   # original, translated, engine, target_lang

    def __init__(self):
        super().__init__()
        self._widget: Optional[_PopupWidget] = None
        self._show_sig.connect(self._do_show)

    def show_popup(self, original: str, translated: str, engine: str, target_lang: str):
        self._show_sig.emit(original, translated, engine, target_lang or "")

    @Slot(str, str, str, str)
    def _do_show(self, original: str, translated: str, engine: str, target_lang: str):
        tl = target_lang or None
        if self._widget is not None:
            try:
                self._widget.update_content(original, translated, engine, tl)
                self._widget.show()
                self._widget.activateWindow()
                self._widget.raise_()
                return
            except RuntimeError:
                self._widget = None

        self._widget = _PopupWidget(original, translated, engine, tl)
        self._widget.destroyed.connect(lambda: setattr(self, "_widget", None))
        self._widget.show()
        self._widget.activateWindow()


_controller: Optional[PopupController] = None


def setup_popup() -> PopupController:
    """Create the singleton. Must be called from the Qt main thread in main.py."""
    global _controller
    if _controller is None:
        _controller = PopupController()
    return _controller


def show_translation_popup(original: str, translated: str, current_engine: str, target_lang=None):
    if _controller is not None:
        _controller.show_popup(original, translated, current_engine, target_lang or "")
    else:
        log.warning("show_translation_popup called before setup_popup")
