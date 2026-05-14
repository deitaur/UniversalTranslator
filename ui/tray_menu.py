"""
System tray icon and menu
"""

import os
import pystray
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import APP_NAME, CONFIG_DIR, STARTUP_DIR, STARTUP_LINK, C, config, save_config_full, ICON_FILE
import globals as g

def _font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()

def _build_base_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=12, fill=(24, 24, 37, 240))
    d.rounded_rectangle([3, 3, 61, 61], radius=11, outline=(88, 91, 112, 100), width=1)
    return img, d

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
    return img

def build_tray_image_google():
    img, d = _build_base_icon()
    d.text((16, 4), "G", fill=(66, 133, 244), font=_font(30))
    d.text((14, 44), "free", fill=(108, 112, 134), font=_font(11))
    return img

def build_tray_image_yandex():
    img, d = _build_base_icon()
    d.text((16, 4), "Y", fill=(255, 204, 0), font=_font(30))
    d.text((14, 44), "free", fill=(108, 112, 134), font=_font(11))
    return img

def _engine_display_name():
    return {"deepl": "DeepL", "google": "Google Translate", "yandex": "Yandex Translate"}.get(g.current_engine, g.current_engine)

def update_tray_icon():
    if g.tray_icon is None:
        return
    name = _engine_display_name()
    if g.current_engine == "google":
        g.tray_icon.icon = build_tray_image_google()
        g.tray_icon.title = APP_NAME + "  [" + name + "]"
    elif g.current_engine == "yandex":
        g.tray_icon.icon = build_tray_image_yandex()
        g.tray_icon.title = APP_NAME + "  [" + name + "]"
    else:
        used = g.usage_data["character_count"]
        limit = g.usage_data["character_limit"]
        g.tray_icon.icon = build_tray_image_deepl(used, limit)
        if limit > 0:
            rem = limit - used
            pct = rem / limit * 100
            g.tray_icon.title = APP_NAME + "  [" + name + "]\n" + format(rem, ",") + " chars left (" + format(pct, ".1f") + "%)"
        else:
            g.tray_icon.title = APP_NAME + "  [" + name + "]"

def is_autostart_enabled():
    return STARTUP_LINK.exists()

def set_autostart(enable):
    if enable:
        vbs_lines = [
            'Set WshShell = CreateObject("WScript.Shell")',
            'Set shortcut = WshShell.CreateShortcut("' + str(STARTUP_LINK) + '")',
            'shortcut.TargetPath = "wscript.exe"',
            'shortcut.Arguments = """' + str(CONFIG_DIR / "launch.vbs") + '"""',
            'shortcut.WorkingDirectory = "' + str(CONFIG_DIR) + '"',
            'shortcut.Description = "' + APP_NAME + '"',
            'shortcut.Save',
        ]
        vbs = "\n".join(vbs_lines)
        vbs_path = CONFIG_DIR / "_make_startup.vbs"
        vbs_path.write_text(vbs, encoding="utf-8")
        os.system('cscript //nologo "' + str(vbs_path) + '"')
        vbs_path.unlink(missing_ok=True)
    else:
        STARTUP_LINK.unlink(missing_ok=True)

def _set_engine(engine):
    g.current_engine = engine
    config["engine"] = engine
    save_config_full()
    if engine == "deepl":
        from services.translators.deepl import DeepLEngine
        deepl = DeepLEngine()
        count, limit = deepl.get_usage()
        g.usage_data["character_count"] = count
        g.usage_data["character_limit"] = limit
    update_tray_icon()

def _ck_deepl(item):
    return g.current_engine == "deepl"

def _ck_google(item):
    return g.current_engine == "google"

def _ck_yandex(item):
    return g.current_engine == "yandex"

def _build_menu(on_translate_clipboard, on_settings, on_whisper, on_role_chat, on_quit):
    def menu_generator():
        yield pystray.MenuItem("Translate Clipboard", lambda icon, item: on_translate_clipboard(), default=True)
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Engine", pystray.Menu(
            pystray.MenuItem("DeepL", lambda icon, item: _set_engine("deepl"), checked=_ck_deepl),
            pystray.MenuItem("Google (free)", lambda icon, item: _set_engine("google"), checked=_ck_google),
            pystray.MenuItem("Yandex (free)", lambda icon, item: _set_engine("yandex"), checked=_ck_yandex),
        ))
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Voice to Text  (Ctrl+Alt+W)", lambda icon, item: on_whisper())
        
        from storage.roles import load_roles
        roles = load_roles()
        
        # Keep track of hotkeys for built-in roles just for display purposes in tray
        hotkey_hints = {
            "negotiator": "  (Ctrl+Alt+N)",
            "teacher": "  (Ctrl+Alt+E)"
        }
        
        def make_callback(role_id):
            return lambda icon, item: on_role_chat(role_id)
        
        for rid, role in roles.items():
            if role.get("show_in_tray", True):
                name = role.get("name", rid)
                hint = hotkey_hints.get(rid, "")
                yield pystray.MenuItem(name + hint, make_callback(rid))
                
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Settings", lambda icon, item: on_settings())
        yield pystray.MenuItem("Quit", lambda icon, item: on_quit())

    return pystray.Menu(menu_generator)

def create_desktop_shortcut():
    desktop = Path(os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"))
    lnk_path = desktop / (APP_NAME + ".lnk")
    launcher = CONFIG_DIR / "launch.vbs"
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
    vbs = "\n".join(vbs_lines)
    vbs_path = CONFIG_DIR / "_make_desktop_shortcut.vbs"
    vbs_path.write_text(vbs, encoding="utf-8")
    os.system('cscript //nologo "' + str(vbs_path) + '"')
    vbs_path.unlink(missing_ok=True)
