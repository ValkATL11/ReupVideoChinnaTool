"""
app/gui/components/prompt_card.py
==================================
Single prompt row/card used inside the Prompt Management view.
Displays name, active/inactive status, description, and exposes
Toggle / Edit / Duplicate / More (Rename, Duplicate, Delete) actions.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu, QCheckBox
)


class PromptCard(QFrame):
    """Visual card representing a single translation prompt."""

    toggle_requested = Signal(str)      # prompt_id
    edit_requested = Signal(str)        # prompt_id
    rename_requested = Signal(str)      # prompt_id
    duplicate_requested = Signal(str)   # prompt_id
    delete_requested = Signal(str)      # prompt_id

    def __init__(self, prompt: dict, parent=None):
        super().__init__(parent)
        self.prompt_id = prompt.get("id")
        self.setProperty("class", "CardFrame")
        self.setObjectName("PromptCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        # --- Top row: name + status badge ---
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        name_lbl = QLabel(prompt.get("name", "Untitled"))
        name_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #f0f0f8;")
        top_row.addWidget(name_lbl)

        is_active = bool(prompt.get("active"))
        status_lbl = QLabel("● Đang hoạt động" if is_active else "○ Không hoạt động")
        status_lbl.setStyleSheet(
            "color: #35d488; font-weight: 600; font-size: 12px;" if is_active
            else "color: #8a8a98; font-weight: 500; font-size: 12px;"
        )
        top_row.addWidget(status_lbl)

        if prompt.get("is_builtin"):
            builtin_lbl = QLabel("Hệ thống")
            builtin_lbl.setStyleSheet(
                "color: #a0a0b0; font-size: 11px; background-color: #2c2c34;"
                "border-radius: 4px; padding: 1px 6px;"
            )
            top_row.addWidget(builtin_lbl)

        top_row.addStretch()
        outer.addLayout(top_row)

        # --- Description ---
        desc = prompt.get("description", "").strip() or "Không có mô tả."
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #a0a0b0; font-size: 12px;")
        outer.addWidget(desc_lbl)

        # --- Bottom row: actions ---
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.toggle_chk = QCheckBox("Kích hoạt")
        self.toggle_chk.setChecked(is_active)
        self.toggle_chk.stateChanged.connect(lambda _: self.toggle_requested.emit(self.prompt_id))
        actions_row.addWidget(self.toggle_chk)

        actions_row.addStretch()

        btn_edit = QPushButton("Chỉnh sửa")
        btn_edit.setProperty("class", "SecondaryButton")
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.prompt_id))
        actions_row.addWidget(btn_edit)

        btn_dup = QPushButton("Nhân bản")
        btn_dup.setProperty("class", "SecondaryButton")
        btn_dup.clicked.connect(lambda: self.duplicate_requested.emit(self.prompt_id))
        actions_row.addWidget(btn_dup)

        btn_more = QPushButton("⋯")
        btn_more.setProperty("class", "SecondaryButton")
        btn_more.setFixedWidth(36)
        btn_more.clicked.connect(lambda: self._show_more_menu(btn_more, prompt))
        actions_row.addWidget(btn_more)

        outer.addLayout(actions_row)

    def _show_more_menu(self, anchor_btn: QPushButton, prompt: dict):
        menu = QMenu(self)
        act_edit = menu.addAction("Chỉnh sửa")
        act_rename = menu.addAction("Đổi tên")
        act_dup = menu.addAction("Nhân bản")
        menu.addSeparator()
        act_delete = menu.addAction("Xóa")

        if prompt.get("is_builtin"):
            act_rename.setEnabled(False)
            act_delete.setEnabled(False)

        chosen = menu.exec(anchor_btn.mapToGlobal(anchor_btn.rect().bottomLeft()))
        if chosen == act_edit:
            self.edit_requested.emit(self.prompt_id)
        elif chosen == act_rename:
            self.rename_requested.emit(self.prompt_id)
        elif chosen == act_dup:
            self.duplicate_requested.emit(self.prompt_id)
        elif chosen == act_delete:
            self.delete_requested.emit(self.prompt_id)
