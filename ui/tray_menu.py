"""System tray icon and menu — PySide6."""

import io
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from config import APP_NAME, CONFIG_DIR, STARTUP_LINK, config, save_config_full, ICON_FILE
import globals as g

_LANG_FLAGS = {
    "en": "🇬🇧", "ru": "🇷🇺", "de": "🇩🇪", "fr": "🇫🇷",
    "es": "🇪🇸", "zh": "🇨🇳", "ja": "🇯🇵", "ko": "🇰🇷",
    "pt": "🇵🇹", "it": "🇮🇹", "ar": "🇸🇦", "nl": "🇳🇱",
    "pl": "🇵🇱", "tr": "🇹🇷", "uk": "🇺🇦", "cs": "🇨🇿",
}


# ── PIL icon builders ─────────────────────────────────────────────────────────

def _font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()

def _tgt_label():
    from utils.language import get_target_lang
    return get_target_lang().upper()[:2]

def _build_base_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=12, fill=(24, 24, 37, 240))
    d.rounded_rectangle([3, 3, 61, 61], radius=11, outline=(88, 91, 112, 100), width=1)
    return img, d

def _draw_lang_badge(d, lang: str):
    d.rectangle([34, 42, 62, 62], fill=(24, 24, 37, 200))
    d.text((36, 44), lang, fill=(137, 180, 250), font=_font(13))

def build_tray_image_deepl(used, limit):
    img, d = _build_base_icon()
    d.text((12, 4), "T", fill=(137, 180, 250), font=_font(28))
    bx0, by0, bx1, by1 = 8, 44, 56, 54
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=4, fill=(49, 50, 68))
    frac = max(0, min(1, 1 - used / limit)) if limit > 0 else 1
    fx1 = bx0 + int((bx1 - bx0) * frac)
    if fx1 > bx0:
        color = (166, 227, 161) if frac > 0.25 else (249, 226, 175) if frac > 0.1 else (243, 139, 168)
        d.rounded_rectangle([bx0, by0, fx1, by1], radius=4, fill=color)
    _draw_lang_badge(d, _tgt_label())
    return img

def build_tray_image_google():
    img, d = _build_base_icon()
    d.text((16, 4), "G", fill=(66, 133, 244), font=_font(30))
    d.text((8, 44), _tgt_label(), fill=(137, 180, 250), font=_font(16))
    return img

def build_tray_image_yandex():
    img, d = _build_base_icon()
    d.text((16, 4), "Y", fill=(255, 204, 0), font=_font(30))
    d.text((8, 44), _tgt_label(), fill=(137, 180, 250), font=_font(16))
    return img


# ── PIL → Qt ──────────────────────────────────────────────────────────────────

def _pil_to_qicon(pil_img: Image.Image) -> QIcon:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return QIcon(QPixmap.fromImage(QImage.fromData(buf.getvalue())))


# ── State helpers ─────────────────────────────────────────────────────────────

def _engine_display_name():
    return {"deepl": "DeepL", "google": "Google Translate", "yandex": "Yandex Translate"}.get(
        g.current_engine, g.current_engine)

def _tray_title_suffix():
    from utils.language import get_target_lang
    tgt  = get_target_lang()
    flag = _LANG_FLAGS.get(tgt, "")
    return f"  {flag} →{tgt.upper()}" if flag else f"  →{tgt.upper()}"

def _compute_icon_and_tooltip():
    """Return (PIL Image, tooltip str) for current app state."""
    name   = _engine_display_name()
    suffix = _tray_title_suffix()
    if g.current_engine == "google":
        img = build_tray_image_google()
        tip = f"{APP_NAME}  [{name}]{suffix}"
    elif g.current_engine == "yandex":
        img = build_tray_image_yandex()
        tip = f"{APP_NAME}  [{name}]{suffix}"
    else:
        used  = g.usage_data["character_count"]
        limit = g.usage_data["character_limit"]
        img   = build_tray_image_deepl(used, limit)
        if limit > 0:
            rem = limit - used
            pct = rem / limit * 100
            tip = (f"{APP_NAME}  [{name}]{suffix}\n"
                   f"{rem:,} chars left ({pct:.1f}%)")
        else:
            tip = f"{APP_NAME}  [{name}]{suffix}"
    return img, tip


# ── Engine switching ──────────────────────────────────────────────────────────

def _set_engine(engine):
    g.current_engine = engine
    config["engine"] = engine
    save_config_full()
    if engine == "deepl":
        from services.translators.deepl import DeepLEngine
        count, limit = DeepLEngine().get_usage()
        g.usage_data["character_count"] = count
        g.usage_data["character_limit"] = limit
    update_tray_icon()
    rebuild_menu()


# ── Autostart / desktop shortcut (unchanged logic) ────────────────────────────

def is_autostart_enabled():
    return STARTUP_LINK.exists()

def _ensure_launcher_vbs():
    import sys
    launcher = CONFIG_DIR / "launch.vbs"
    main_py  = Path(__file__).parent.parent / "main.py"
    pythonw  = Path(sys.executable).parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        'WshShell.Run Chr(34) & "' + str(pythonw) + '" & Chr(34)'
        ' & " " & Chr(34) & "' + str(main_py) + '" & Chr(34), 0, False\n'
    )
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    launcher.write_text(vbs, encoding="utf-8")
    return launcher

def set_autostart(enable):
    if enable:
        launcher = _ensure_launcher_vbs()
        vbs_lines = [
            'Set WshShell = CreateObject("WScript.Shell")',
            'Set shortcut = WshShell.CreateShortcut("' + str(STARTUP_LINK) + '")',
            'shortcut.TargetPath = "wscript.exe"',
            'shortcut.Arguments = """' + str(launcher) + '"""',
            'shortcut.WorkingDirectory = "' + str(CONFIG_DIR) + '"',
            'shortcut.Description = "' + APP_NAME + '"',
            'shortcut.Save',
        ]
        vbs_path = CONFIG_DIR / "_make_startup.vbs"
        vbs_path.write_text("\n".join(vbs_lines), encoding="utf-8")
        os.system('cscript //nologo "' + str(vbs_path) + '"')
        vbs_path.unlink(missing_ok=True)
    else:
        STARTUP_LINK.unlink(missing_ok=True)

def create_desktop_shortcut():
    desktop  = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    lnk_path = desktop / (APP_NAME + ".lnk")
    launcher = _ensure_launcher_vbs()
    if not ICON_FILE.exists():
        from ui.icon_generator import generate_app_icon
        generate_app_icon()
    vbs_lines = [
        'Set WshShell = CreateObject("WScript.Shell")',
        'Set shortcut = WshShell.CreateShortcut("' + str(lnk_path) + '")',
        'shortcut.TargetPath = "wscript.exe"',
        'shortcut.Arguments = """' + str(launcher) + '"""',
        'shortcut.WorkingDirectory = "' + str(CONFIG_DIR) + '"',
        'shortcut.IconLocation = "' + str(ICON_FILE) + '"',
        'shortcut.Description = "' + APP_NAME + ' - Ctrl+Alt+T / Ctrl+Alt+R"',
        'shortcut.Save',
    ]
    vbs_path = CONFIG_DIR / "_make_desktop_shortcut.vbs"
    vbs_path.write_text("\n".join(vbs_lines), encoding="utf-8")
    os.system('cscript //nologo "' + str(vbs_path) + '"')
    vbs_path.unlink(missing_ok=True)


# ── Qt menu builder ───────────────────────────────────────────────────────────

def _build_qt_menu(callbacks: dict) -> QMenu:
    menu = QMenu()

    a = QAction("Translate Clipboard", menu)
    a.triggered.connect(callbacks["translate_clipboard"])
    menu.addAction(a)
    menu.setDefaultAction(a)

    menu.addSeparator()

    engine_menu = QMenu("Engine", menu)
    ag = QActionGroup(engine_menu)
    ag.setExclusive(True)
    for ev, el in [("deepl", "DeepL"), ("google", "Google (free)"), ("yandex", "Yandex (free)")]:
        a = QAction(el, engine_menu)
        a.setCheckable(True)
        a.setChecked(g.current_engine == ev)
        a.triggered.connect(lambda checked=False, e=ev: _set_engine(e))
        engine_menu.addAction(a)
        ag.addAction(a)
    menu.addMenu(engine_menu)

    menu.addSeparator()

    a = QAction("Voice to Text  (Ctrl+Alt+W)", menu)
    a.triggered.connect(callbacks["whisper"])
    menu.addAction(a)

    try:
        from storage.roles import load_roles
        roles = load_roles()
        hotkey_hints = {"negotiator": "  (Ctrl+Alt+N)", "teacher": "  (Ctrl+Alt+E)"}
        for rid, role in roles.items():
            if role.get("show_in_tray", True):
                label = role.get("name", rid) + hotkey_hints.get(rid, "")
                a = QAction(label, menu)
                a.triggered.connect(lambda checked=False, r=rid: callbacks["role_chat"](r))
                menu.addAction(a)
    except Exception:
        pass

    menu.addSeparator()

    a = QAction("Settings", menu)
    a.triggered.connect(callbacks["settings"])
    menu.addAction(a)

    a = QAction("Quit", menu)
    a.triggered.connect(callbacks["quit"])
    menu.addAction(a)

    return menu


# ── Thread-safe tray controller ───────────────────────────────────────────────

class _TrayController(QObject):
    """Lives on the Qt main thread. Signals deliver updates safely from any thread."""
    _update_sig  = Signal(object, str)
    _rebuild_sig = Signal()

    def __init__(self, tray: QSystemTrayIcon, callbacks: dict):
        super().__init__()
        self._tray      = tray
        self._callbacks = callbacks
        self._update_sig.connect(self._apply_update)
        self._rebuild_sig.connect(self._apply_rebuild)

    @Slot(object, str)
    def _apply_update(self, pil_img, tooltip):
        self._tray.setIcon(_pil_to_qicon(pil_img))
        self._tray.setToolTip(tooltip)

    @Slot()
    def _apply_rebuild(self):
        self._tray.setContextMenu(_build_qt_menu(self._callbacks))

    def request_update(self):
        img, tip = _compute_icon_and_tooltip()
        self._update_sig.emit(img, tip)

    def request_rebuild(self):
        self._rebuild_sig.emit()


_controller: "_TrayController | None" = None


def update_tray_icon():
    """Thread-safe icon + tooltip refresh. Call from any thread."""
    if _controller:
        _controller.request_update()

def rebuild_menu():
    """Thread-safe menu rebuild. Call from any thread."""
    if _controller:
        _controller.request_rebuild()

def create_tray_icon(callbacks: dict):
    """Create the QSystemTrayIcon. Must be called after QApplication exists."""
    global _controller

    tray = QSystemTrayIcon()
    g.tray_icon = tray

    img, tip = _compute_icon_and_tooltip()
    tray.setIcon(_pil_to_qicon(img))
    tray.setToolTip(tip)
    tray.setContextMenu(_build_qt_menu(callbacks))

    def _on_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            callbacks["translate_clipboard"]()

    tray.activated.connect(_on_activated)
    tray.show()

    _controller = _TrayController(tray, callbacks)
