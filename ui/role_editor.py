"""Role Editor window — PySide6. Create, edit, delete AI roles."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QTextEdit,
    QVBoxLayout, QWidget,
)

from config import APP_NAME, ICON_FILE, C


# ── Helpers (mirrors settings_window style) ───────────────────────────────────

def _label(text: str, bold: bool = False, color: str = None, size: int = 12) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", size, QFont.Weight.DemiBold if bold else QFont.Weight.Normal))
    lbl.setStyleSheet(f"color: {color or C['text']}; background: transparent; border: none;")
    return lbl


def _btn(text: str, bg: str, fg: str, hover: str = None, height: int = 32) -> QPushButton:
    b = QPushButton(text)
    b.setFont(QFont("Segoe UI Semibold", 11))
    b.setFixedHeight(height)
    h = hover or bg
    b.setStyleSheet(
        f"QPushButton {{ background: {bg}; color: {fg}; border: none;"
        f" border-radius: 6px; padding: 2px 10px; }}"
        f"QPushButton:hover {{ background: {h}; }}"
        f"QPushButton:disabled {{ background: {C['border']}; color: {C['muted']}; }}"
    )
    return b


# ── Main window ───────────────────────────────────────────────────────────────

class RoleEditorWindow(QWidget):

    def __init__(self):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"{APP_NAME} - Role Manager")
        self.resize(760, 580)
        self.setMinimumSize(650, 480)
        self.setStyleSheet(f"background: {C['bg']}; color: {C['text']};")
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))

        self._selected_id = None
        self._role_buttons: dict[str, QPushButton] = {}

        self._build()
        self._refresh_list()
        self._clear_editor()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(f"background: {C['surface']}; border: none;")
        hdr_lo = QHBoxLayout(hdr)
        hdr_lo.setContentsMargins(18, 0, 18, 0)
        hdr_lo.addWidget(_label("Role Manager", bold=True, size=17))
        root.addWidget(hdr)

        # Body: left list + right editor
        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(8)
        root.addLayout(body)

        # Left panel
        left = QFrame()
        left.setFixedWidth(200)
        left.setStyleSheet(
            f"QFrame {{ background: {C['card']}; border: 1px solid {C['border']};"
            f" border-radius: 10px; }}"
            f"QLabel {{ background: transparent; border: none; }}"
        )
        left_lo = QVBoxLayout(left)
        left_lo.setContentsMargins(8, 10, 8, 8)
        left_lo.setSpacing(4)
        left_lo.addWidget(_label("Roles", bold=True, size=12))

        # Scrollable role list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_lo = QVBoxLayout(self._list_container)
        self._list_lo.setContentsMargins(0, 0, 0, 0)
        self._list_lo.setSpacing(3)
        self._list_lo.addStretch()
        scroll.setWidget(self._list_container)
        left_lo.addWidget(scroll, 1)

        new_btn = _btn("+ New", C["accent"], C["bg"], "#7ba4e8", height=30)
        new_btn.clicked.connect(self._new_role)
        left_lo.addWidget(new_btn)
        body.addWidget(left)

        # Right panel
        right = QFrame()
        right.setStyleSheet(
            f"QFrame {{ background: {C['card']}; border: 1px solid {C['border']};"
            f" border-radius: 10px; }}"
            f"QLabel {{ background: transparent; border: none; }}"
            f"QLineEdit {{ background: {C['card_alt']}; color: {C['text']};"
            f" border: 1px solid {C['border']}; border-radius: 5px; padding: 3px 6px; }}"
        )
        right_lo = QVBoxLayout(right)
        right_lo.setContentsMargins(14, 12, 14, 12)
        right_lo.setSpacing(5)

        right_lo.addWidget(_label("Role Name:", color=C["subtext"], size=11))
        self._name_entry = QLineEdit()
        self._name_entry.setFont(QFont("Segoe UI", 12))
        right_lo.addWidget(self._name_entry)

        right_lo.addWidget(_label("System Prompt:", color=C["subtext"], size=11))
        self._prompt_text = QTextEdit()
        self._prompt_text.setFont(QFont("Consolas", 10))
        self._prompt_text.setStyleSheet(
            f"QTextEdit {{ background: {C['card_alt']}; color: {C['text']};"
            f" border: 1px solid {C['border']}; border-radius: 6px; padding: 4px; }}"
        )
        right_lo.addWidget(self._prompt_text, 1)

        # Materials folder row
        mat_row = QHBoxLayout()
        mat_row.addWidget(_label("Materials Folder:", color=C["subtext"], size=11))
        self._folder_lbl = QLabel("(none)")
        self._folder_lbl.setFont(QFont("Segoe UI", 10))
        self._folder_lbl.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        self._folder_lbl._path = ""
        mat_row.addWidget(self._folder_lbl, 1)
        open_btn = _btn("Open", C["card_alt"], C["text"], C["border"], height=26)
        open_btn.setFixedWidth(60)
        open_btn.clicked.connect(self._open_materials)
        mat_row.addWidget(open_btn)
        browse_btn = _btn("Browse", C["card_alt"], C["text"], C["border"], height=26)
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse_folder)
        mat_row.addWidget(browse_btn)
        right_lo.addLayout(mat_row)

        # Files label
        self._files_lbl = QLabel("No materials loaded")
        self._files_lbl.setFont(QFont("Segoe UI", 9))
        self._files_lbl.setStyleSheet(
            f"color: {C['muted']}; background: {C['card_alt']};"
            f" border: 1px solid {C['border']}; border-radius: 6px; padding: 4px 8px;"
        )
        self._files_lbl.setWordWrap(True)
        self._files_lbl.setFixedHeight(56)
        right_lo.addWidget(self._files_lbl)

        # Options row
        opt_row = QHBoxLayout()
        opt_row.addWidget(_label("Context tokens (num_ctx):", color=C["subtext"], size=10))
        self._ctx_entry = QLineEdit()
        self._ctx_entry.setFont(QFont("Consolas", 10))
        self._ctx_entry.setFixedWidth(80)
        self._ctx_entry.setStyleSheet(
            f"QLineEdit {{ background: {C['card_alt']}; color: {C['text']};"
            f" border: 1px solid {C['border']}; border-radius: 5px; padding: 2px 5px; }}"
        )
        opt_row.addWidget(self._ctx_entry)
        opt_row.addStretch()
        self._tray_cb = QCheckBox("Show in tray menu")
        self._tray_cb.setFont(QFont("Segoe UI", 10))
        self._tray_cb.setStyleSheet(f"QCheckBox {{ color: {C['text']}; background: transparent; }}")
        self._tray_cb.setChecked(True)
        opt_row.addWidget(self._tray_cb)
        right_lo.addLayout(opt_row)

        # Action buttons
        act_row = QHBoxLayout()
        save_btn = _btn("Save Role", C["accent"], C["bg"], "#7ba4e8", height=36)
        save_btn.setFont(QFont("Segoe UI Semibold", 12))
        save_btn.clicked.connect(self._save_role)
        act_row.addWidget(save_btn, 1)
        self._delete_btn = _btn("Delete", C["red"], C["bg"], "#e06080", height=36)
        self._delete_btn.setFont(QFont("Segoe UI Semibold", 12))
        self._delete_btn.setFixedWidth(90)
        self._delete_btn.clicked.connect(self._delete_role)
        act_row.addWidget(self._delete_btn)
        right_lo.addLayout(act_row)

        body.addWidget(right, 1)

    # ── Role list ─────────────────────────────────────────────────────────────

    def _refresh_list(self):
        from storage.roles import load_roles
        # Remove old buttons (keep the trailing stretch)
        while self._list_lo.count() > 1:
            item = self._list_lo.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._role_buttons.clear()

        roles = load_roles()
        for rid, rdata in roles.items():
            btn = QPushButton(rdata.get("name", rid))
            btn.setFont(QFont("Segoe UI", 11))
            btn.setFixedHeight(32)
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton {{ background: {C['card_alt']}; color: {C['text']};"
                f" border: none; border-radius: 6px; padding: 2px 8px; text-align: left; }}"
                f"QPushButton:hover {{ background: {C['border']}; }}"
                f"QPushButton:checked {{ background: {C['accent']}; color: {C['bg']}; }}"
            )
            btn.clicked.connect(lambda _, r=rid: self._load_role(r))
            self._list_lo.insertWidget(self._list_lo.count() - 1, btn)
            self._role_buttons[rid] = btn

        if self._selected_id and self._selected_id in self._role_buttons:
            self._role_buttons[self._selected_id].setChecked(True)

    def _highlight(self, active_id):
        for rid, btn in self._role_buttons.items():
            btn.setChecked(rid == active_id)

    # ── Editor ────────────────────────────────────────────────────────────────

    def _clear_editor(self):
        from config import config as cfg
        self._selected_id = None
        self._name_entry.clear()
        self._prompt_text.clear()
        self._folder_lbl.setText("(none)")
        self._folder_lbl._path = ""
        self._files_lbl.setText("No materials loaded")
        self._ctx_entry.setText(str(cfg.get("ollama_num_ctx", 4096)))
        self._tray_cb.setChecked(True)
        self._delete_btn.setEnabled(True)

    def _load_role(self, role_id: str):
        from storage.roles import load_roles, list_materials
        from config import config as cfg

        self._selected_id = role_id
        roles = load_roles()
        role  = roles.get(role_id, {})

        self._name_entry.setText(role.get("name", ""))
        self._prompt_text.setPlainText(role.get("system_prompt", ""))

        mat = role.get("materials_folder", "")
        self._folder_lbl.setText(os.path.basename(mat) if mat else "(default)")
        self._folder_lbl._path = mat

        materials = list_materials(role_id)
        if materials:
            names = [f.name for f in materials[:10]]
            txt = ", ".join(names)
            if len(materials) > 10:
                txt += f" +{len(materials) - 10} more"
            self._files_lbl.setText(txt)
        else:
            self._files_lbl.setText("No materials — add files to folder")

        self._ctx_entry.setText(str(cfg.get("ollama_num_ctx", 4096)))
        self._tray_cb.setChecked(role.get("show_in_tray", True))
        self._delete_btn.setEnabled(not role.get("builtin", False))
        self._highlight(role_id)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _new_role(self):
        self._clear_editor()
        self._highlight("")
        self._name_entry.setFocus()

    def _save_role(self):
        from storage.roles import create_role, update_role
        from config import config as cfg, save_config_full

        name   = self._name_entry.text().strip()
        prompt = self._prompt_text.toPlainText().strip()
        folder = self._folder_lbl._path
        in_tray = self._tray_cb.isChecked()
        if not name:
            return

        if self._selected_id:
            ok = update_role(self._selected_id, name=name, system_prompt=prompt,
                             materials_folder=folder, show_in_tray=in_tray)
            if not ok:
                self._selected_id = create_role(name, prompt,
                                                materials_folder=folder, show_in_tray=in_tray)
        else:
            self._selected_id = create_role(name, prompt,
                                            materials_folder=folder, show_in_tray=in_tray)

        ctx_val = self._ctx_entry.text().strip()
        if ctx_val:
            try:
                cfg["ollama_num_ctx"] = int(ctx_val)
                save_config_full()
            except ValueError:
                pass

        self._refresh_list()

    def _delete_role(self):
        from storage.roles import delete_role
        if not self._selected_id:
            return
        if delete_role(self._selected_id):
            self._selected_id = None
            self._clear_editor()
            self._refresh_list()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Materials Folder", self._folder_lbl._path or str(os.path.expanduser("~"))
        )
        if folder:
            self._folder_lbl.setText(os.path.basename(folder))
            self._folder_lbl._path = folder

    def _open_materials(self):
        if not self._selected_id:
            return
        from storage.roles import get_materials_folder
        folder = get_materials_folder(self._selected_id)
        if folder and folder.exists():
            os.startfile(str(folder))


# ── Public entry point ────────────────────────────────────────────────────────

def show_role_editor():
    win = RoleEditorWindow()
    win.show()
