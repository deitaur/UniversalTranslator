"""Voice-actions dialog — user picks how to process a Whisper transcript.

Thread model:
- A worker thread (Whisper pipeline) calls `ask_voice_actions(text)` and blocks.
- The controller, living on the Qt main thread, opens the dialog via signal.
- When the user clicks Apply/Cancel, the worker thread is unblocked with
  the chosen options (or None on cancel).
"""

import logging
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QTextEdit, QVBoxLayout,
)

from config import APP_NAME, ICON_FILE, C, config, save_config_full

log = logging.getLogger("voice_actions_dialog")

SHAPE_NONE     = "none"
SHAPE_SPELLING = "spelling"
SHAPE_DEEP     = "deep"
SHAPE_TASKS    = "tasks"

_SHAPE_OPTIONS = [
    (SHAPE_NONE,     "Без обработки  (вставить как есть)"),
    (SHAPE_SPELLING, "Исправить орфографию"),
    (SHAPE_DEEP,     "Глубокая редактура  (LLM)"),
    (SHAPE_TASKS,    "Оформить как список дел  (LLM)"),
]

_PREVIEW_LINES = 5
_PREVIEW_CHARS = 300


def _engine_short() -> str:
    import globals as g
    return {"deepl": "DeepL", "google": "Google", "yandex": "Yandex"}.get(
        g.current_engine, g.current_engine)


def _short_preview(text: str) -> str:
    lines = text.splitlines() or [text]
    if len(lines) > _PREVIEW_LINES:
        lines = lines[:_PREVIEW_LINES] + ["…"]
    out = "\n".join(lines)
    if len(out) > _PREVIEW_CHARS:
        out = out[:_PREVIEW_CHARS].rstrip() + " …"
    return out


class _Dialog(QDialog):
    def __init__(self, raw_text: str, initial_shape: str, initial_translate: bool):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self._raw_text = raw_text
        self._result: Optional[dict] = None
        self._expanded = False

        self.setWindowTitle(f"{APP_NAME} — обработка диктовки")
        self.setMinimumWidth(520)
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))
        self.setStyleSheet(f"background: {C['bg']}; color: {C['text']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        # ── Preview ──
        n_chars = len(raw_text)
        n_lines = raw_text.count("\n") + 1
        hdr = QLabel(f"Распознано:  {n_chars} симв.,  {n_lines} стр.")
        hdr.setFont(QFont("Segoe UI Semibold", 9))
        hdr.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        root.addWidget(hdr)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFont(QFont("Segoe UI", 11))
        self._preview.setStyleSheet(
            f"QTextEdit {{ background: {C['card']}; color: {C['text']};"
            f" border: 1px solid {C['border']}; border-radius: 6px; padding: 8px; }}"
        )
        self._preview.setFixedHeight(118)
        self._preview.setPlainText(_short_preview(raw_text))
        root.addWidget(self._preview)

        self._expand_btn = QPushButton("Показать весь текст ▾")
        self._expand_btn.setFlat(True)
        self._expand_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {C['accent']};"
            f" border: none; padding: 0; text-align: left; }}"
            f"QPushButton:hover {{ color: #7ba4e8; }}"
        )
        self._expand_btn.clicked.connect(self._expand)
        truncated = (n_lines > _PREVIEW_LINES) or (n_chars > _PREVIEW_CHARS)
        if truncated:
            root.addWidget(self._expand_btn)
        else:
            self._expand_btn.hide()

        # ── Shape radios ──
        root.addSpacing(6)
        shape_lbl = QLabel("Обработка:")
        shape_lbl.setFont(QFont("Segoe UI Semibold", 10))
        shape_lbl.setStyleSheet(f"color: {C['text']}; background: transparent;")
        root.addWidget(shape_lbl)

        self._shape_group = QButtonGroup(self)
        any_checked = False
        for value, label in _SHAPE_OPTIONS:
            rb = QRadioButton(label)
            rb.setFont(QFont("Segoe UI", 11))
            rb.setStyleSheet(f"QRadioButton {{ color: {C['text']}; padding: 2px 0; }}")
            rb.setProperty("shape_value", value)
            if value == initial_shape:
                rb.setChecked(True)
                any_checked = True
            self._shape_group.addButton(rb)
            root.addWidget(rb)
        if not any_checked:
            self._shape_group.buttons()[0].setChecked(True)

        # ── Translate checkbox ──
        root.addSpacing(8)
        self._translate_cb = QCheckBox(f"Перевести  ({_engine_short()})")
        self._translate_cb.setFont(QFont("Segoe UI", 11))
        self._translate_cb.setStyleSheet(f"QCheckBox {{ color: {C['text']}; }}")
        self._translate_cb.setChecked(initial_translate)
        root.addWidget(self._translate_cb)

        # ── Remember ──
        root.addSpacing(4)
        self._remember_cb = QCheckBox("Запомнить выбор  (не показывать диалог в след. раз)")
        self._remember_cb.setFont(QFont("Segoe UI", 9))
        self._remember_cb.setStyleSheet(f"QCheckBox {{ color: {C['muted']}; }}")
        root.addWidget(self._remember_cb)

        root.addStretch()

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel = QPushButton("Отмена")
        cancel.setFixedHeight(34)
        cancel.setMinimumWidth(96)
        cancel.setStyleSheet(
            f"QPushButton {{ background: {C['card_alt']}; color: {C['text']};"
            f" border: none; border-radius: 6px; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: {C['border']}; }}"
        )
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        apply_btn = QPushButton("Применить  ⏎")
        apply_btn.setFixedHeight(34)
        apply_btn.setMinimumWidth(140)
        apply_btn.setDefault(True)
        apply_btn.setStyleSheet(
            f"QPushButton {{ background: {C['accent']}; color: {C['bg']};"
            f" border: none; border-radius: 6px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #7ba4e8; }}"
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        root.addLayout(btn_row)

    def _expand(self):
        if self._expanded:
            return
        self._expanded = True
        self._preview.setPlainText(self._raw_text)
        self._preview.setFixedHeight(260)
        self._expand_btn.hide()
        self.adjustSize()

    def _on_apply(self):
        shape = SHAPE_NONE
        for b in self._shape_group.buttons():
            if b.isChecked():
                shape = b.property("shape_value")
                break
        self._result = {
            "shape":     shape,
            "translate": self._translate_cb.isChecked(),
            "remember":  self._remember_cb.isChecked(),
        }
        self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.reject()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_apply()
        else:
            super().keyPressEvent(e)

    def get_result(self) -> Optional[dict]:
        return self._result


# ── Thread-safe controller ────────────────────────────────────────────────────

class _Controller(QObject):
    """Lives on the Qt main thread. Worker threads call `ask()`."""
    _show_sig = Signal(str, object)   # raw_text, on_result callable

    def __init__(self):
        super().__init__()
        self._show_sig.connect(self._do_show)

    def ask(self, raw_text: str, on_result: Callable[[Optional[dict]], None]):
        self._show_sig.emit(raw_text, on_result)

    @Slot(str, object)
    def _do_show(self, raw_text: str, on_result):
        initial_shape = config.get("voice_action_shape", SHAPE_NONE)
        initial_translate = bool(config.get("voice_action_translate", False))
        dlg = _Dialog(raw_text, initial_shape, initial_translate)
        try:
            dlg.exec()
            result = dlg.get_result()
        finally:
            dlg.deleteLater()
        try:
            on_result(result)
        except Exception as e:
            log.error("on_result callback failed: %s", e, exc_info=True)


_controller: Optional[_Controller] = None


def setup_voice_actions_dialog() -> _Controller:
    """Create the singleton controller. Call once from the Qt main thread."""
    global _controller
    if _controller is None:
        _controller = _Controller()
    return _controller


def ask_voice_actions(raw_text: str) -> Optional[dict]:
    """Block calling thread until the user picks options.

    Returns dict {shape, translate, remember} or None on cancel.
    Must be called from a non-Qt thread (the worker thread)."""
    if _controller is None:
        # Auto-init as a safety net if someone forgot to call setup.
        setup_voice_actions_dialog()

    holder = {"value": None}
    done = threading.Event()

    def _on_result(result):
        holder["value"] = result
        done.set()

    _controller.ask(raw_text, _on_result)
    done.wait()
    result = holder["value"]

    if result and result.get("remember"):
        config["voice_action_shape"]     = result["shape"]
        config["voice_action_translate"] = result["translate"]
        config["voice_show_dialog"]      = False
        try:
            save_config_full()
        except Exception as e:
            log.warning("save_config_full failed: %s", e)

    return result
