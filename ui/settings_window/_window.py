"""SettingsWindow — main settings popup. Sections live in `_sections`,
shared widgets in `_widgets`. This file holds the window shell + slot callbacks.
"""

import datetime as _dt
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from config import APP_NAME, APP_VERSION, ICON_FILE, C, config, save_config_full
from win32.hotkeys import parse_hotkey_string

from ui.settings_window._sections import build_all_sections


class SettingsWindow(QWidget):

    _ai_load_sig = Signal(bool)

    def __init__(self, current_engine: str, update_tray_icon, rebuild_menu):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._current_engine = current_engine
        self._update_tray    = update_tray_icon
        self._rebuild_menu   = rebuild_menu

        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.resize(460, 580)
        self.setMinimumSize(380, 420)
        self.setStyleSheet(
            f"QWidget {{ background: {C['bg']}; color: {C['text']}; }}"
            f"QScrollArea {{ border: none; }}"
        )
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self._ai_load_sig.connect(self._on_ai_load_result)
        self._build()

    # ── Layout shell ──────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Mini header
        hdr = QFrame()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(f"background: {C['surface']}; border-bottom: 1px solid {C['border']};")
        hdr_lo = QHBoxLayout(hdr)
        hdr_lo.setContentsMargins(10, 0, 10, 0)
        title_lbl = QLabel("Settings")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        title_lbl.setStyleSheet(f"color: {C['text']}; background: transparent; border: none;")
        hdr_lo.addWidget(title_lbl)
        hdr_lo.addStretch()
        try:
            src = sys.argv[0] if getattr(sys, "frozen", False) else __file__
            ts = _dt.datetime.fromtimestamp(os.path.getmtime(src)).strftime("%d %b %Y")
        except Exception:
            ts = ""
        ver_lbl = QLabel(f"v{APP_VERSION}" + (f"  {ts}" if ts else ""))
        ver_lbl.setFont(QFont("Segoe UI", 8))
        ver_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent; border: none;")
        hdr_lo.addWidget(ver_lbl)
        root.addWidget(hdr)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setStyleSheet(f"background: {C['bg']};")
        inner_lo = QVBoxLayout(inner)
        inner_lo.setContentsMargins(0, 0, 0, 0)
        inner_lo.setSpacing(0)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setFont(QFont("Segoe UI Semibold", 10))
        self._save_btn.setFixedHeight(30)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background: {C['accent']}; color: {C['bg']}; border: none; }}"
            f"QPushButton:hover {{ background: #7ba4e8; }}"
        )
        self._save_btn.clicked.connect(self._save)
        root.addWidget(self._save_btn)

        build_all_sections(self, inner_lo)
        inner_lo.addStretch()

    # ── IP helpers (consumed by Mobile Bridge section + _refresh_qr) ──────────

    def _get_all_ips(self) -> list[str]:
        import socket
        ips = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith("127."):
                    ips.append(ip)
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            default_ip = s.getsockname()[0]
            s.close()
            if default_ip not in ips:
                ips.insert(0, default_ip)
        except Exception:
            pass
        return ips or ["127.0.0.1"]

    def _get_local_ip(self) -> str:
        return self._get_all_ips()[0]

    # ── Slot callbacks ────────────────────────────────────────────────────────

    def _copy_token(self, tok: str):
        from win32.clipboard import set_clipboard_text
        set_clipboard_text(tok)
        from ui.notifications import show_toast
        show_toast("Token copied", 1500)

    def _refresh_qr(self):
        try:
            import qrcode
            from PySide6.QtGui import QImage, QPixmap
        except ImportError:
            self._qr_lbl.setText("pip install qrcode[pil]")
            return

        from services.bridge.auth import get_or_create_token
        ip   = self._ip_combo.currentText() if hasattr(self, "_ip_combo") else self._get_local_ip()
        port = self._bridge_port.text().strip() or "8082"
        tok  = get_or_create_token()
        url  = f"ws://{ip}:{port}/?token={tok}"

        try:
            qr = qrcode.QRCode(box_size=3, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="white", back_color="#181825")
            img_rgb = img.convert("RGB")
            w, h = img_rgb.size
            data = img_rgb.tobytes("raw", "RGB")
            qimage = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimage).scaled(
                110, 110,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._qr_lbl.setPixmap(pix)
            self._qr_lbl.setToolTip(url)
        except Exception as e:
            self._qr_lbl.setText(f"QR error: {e}")

    def _on_engine(self, val: str):
        if val == "deepl" and not config.get("api_key"):
            self._deepl_key.setFocus()
        if val == "yandex" and not config.get("yandex_api_key"):
            self._yandex_key.setFocus()
        self._current_engine = val
        import globals as g
        g.current_engine = val
        config["engine"] = val
        save_config_full()
        if val == "deepl":
            try:
                from services.translators.deepl import DeepLEngine
                engine = DeepLEngine()
                count, limit = engine.get_usage()
                from globals import usage_data
                usage_data["character_count"] = count
                usage_data["character_limit"] = limit
            except Exception:
                pass
        self._update_tray()
        self._rebuild_menu()

    def _test_tts(self):
        from services.ai.tts import speak
        self._tts_test_btn.setText("…")
        self._tts_test_btn.setEnabled(False)
        config["tts_engine"] = self._tts_stored.get(self._tts_combo.currentText(), "gtts")
        speak("Проверка голоса", lang_code="ru")
        QTimer.singleShot(3000, lambda: (
            self._tts_test_btn.setText("▶ Test"),
            self._tts_test_btn.setEnabled(True),
        ))

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Папка для диктовок", self._dict_folder.text() or str(Path.home())
        )
        if folder:
            self._dict_folder.setText(folder)

    def _open_role_editor(self):
        from ui.role_editor import show_role_editor
        show_role_editor()

    def _on_load_ai(self):
        self._load_btn.setText("Loading…")
        self._load_btn.setEnabled(False)

        def _task():
            from services.ai.ollama import preload_model
            self._ai_load_sig.emit(preload_model())
        threading.Thread(target=_task, daemon=True).start()

    @Slot(bool)
    def _on_ai_load_result(self, success: bool):
        self._load_btn.setText("Loaded!" if success else "Error")
        self._load_btn.setEnabled(True)
        QTimer.singleShot(3000, lambda: self._load_btn.setText("Load into RAM"))

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        _n2c = self._name_to_code

        config["api_key"]          = self._deepl_key.text().strip()
        config["yandex_api_key"]   = self._yandex_key.text().strip()
        config["yandex_folder_id"] = self._yandex_folder.text().strip()

        config["ollama_model_chat"]   = self._ollama_chat_entry.text().strip()
        config["ollama_model_polish"] = self._ollama_polish_entry.text().strip()
        # invalidate the running-models cache so next call re-detects
        from services.ai import ollama as _ol
        _ol._ps_cache = []
        _ol._ps_cache_ts = 0.0

        config["negotiator_lang"] = self._neg_lang_combo.currentText()
        config["autostart"]       = self._autostart_cb.isChecked()
        config["clipboard_only"]  = self._clipboard_cb.isChecked()
        config["direct_type"]     = self._direct_cb.isChecked()
        config["tts_engine"]      = self._tts_stored.get(self._tts_combo.currentText(), "gtts")

        config["bridge_enabled"] = self._bridge_cb.isChecked()
        try:
            config["bridge_port"] = int(self._bridge_port.text().strip())
        except ValueError:
            pass

        config["dictation_folder"]   = self._dict_folder.text().strip()
        config["dictation_format"]   = self._fmt_stored.get(self._fmt_combo.currentText(), "md")
        config["dictation_obsidian"] = self._obsidian_cb.isChecked()
        config["dictation_tags"]     = self._tags_entry.text().strip()
        config["format_output"]      = self._format_cb.isChecked()

        src_name = self._src_combo.currentText()
        config["source_lang"] = _n2c.get(src_name, src_name)

        tgt_name = self._tgt_combo.currentText()
        _SAME = "(Same as source)"
        config["target_lang"] = "" if tgt_name == _SAME else _n2c.get(tgt_name, tgt_name)

        for name, entry in self._hotkey_entries.items():
            hk = entry.text().strip()
            if hk:
                try:
                    parse_hotkey_string(hk)
                    config[f"hotkey_{name}"] = hk
                except Exception:
                    pass

        save_config_full()
        self.close()

        def _post():
            from ui.tray_menu import set_autostart
            set_autostart(config["autostart"])
            self._update_tray()
            self._rebuild_menu()
        threading.Thread(target=_post, daemon=True).start()


# ── Public entry point ────────────────────────────────────────────────────────

def show_settings_window(current_engine: str, update_tray_icon, rebuild_menu):
    import logging
    log = logging.getLogger("settings")
    try:
        win = SettingsWindow(current_engine, update_tray_icon, rebuild_menu)
        win.show()
    except Exception as e:
        import traceback
        log.error("Settings window failed: %s\n%s", e, traceback.format_exc())
