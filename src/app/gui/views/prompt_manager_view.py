"""
app/gui/views/prompt_manager_view.py
=====================================
"Quản lý Prompt dịch" — Translation Prompt Management screen.

Lets the user view, add, edit, rename, duplicate, delete, and activate
Translation prompts. Backed entirely by app.core.prompt_engine.prompt_library_instance,
which is also what app/services/translator.py reads from — so changes made
here take effect on the next Translation run with no restart required.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QMessageBox
)

from app.core.prompt_engine import prompt_library_instance, PromptValidationError
from app.gui.components.prompt_card import PromptCard
from app.gui.components.prompt_editor_dialog import PromptEditorDialog


class PromptManagerView(QWidget):
    """Full-page view for managing Translation prompts."""

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # --- Header ---
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("Quản lý Prompt dịch")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #ffffff;")
        title_box.addWidget(title_lbl)

        subtitle_lbl = QLabel("Tạo, chỉnh sửa và quản lý các prompt dùng cho dịch thuật.")
        subtitle_lbl.setStyleSheet("color: #a0a0b0; font-size: 12px;")
        title_box.addWidget(subtitle_lbl)

        header_row.addLayout(title_box)
        header_row.addStretch()

        btn_add = QPushButton("+ Thêm prompt mới")
        btn_add.setProperty("class", "PrimaryButton")
        btn_add.clicked.connect(self._handle_add)
        header_row.addWidget(btn_add)

        root.addLayout(header_row)

        # --- Scrollable prompt list ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll)

        self.reload_prompts()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def reload_prompts(self):
        """Rebuild the card list from the current prompt library state."""
        # Clear existing cards (keep the trailing stretch item).
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        prompts = prompt_library_instance.list_prompts()
        for prompt in prompts:
            card = PromptCard(prompt)
            card.toggle_requested.connect(self._handle_toggle)
            card.edit_requested.connect(self._handle_edit)
            card.rename_requested.connect(self._handle_rename)
            card.duplicate_requested.connect(self._handle_duplicate)
            card.delete_requested.connect(self._handle_delete)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _handle_add(self):
        dlg = PromptEditorDialog(self)
        dlg.prompt_saved.connect(self.reload_prompts)
        dlg.exec()

    def _handle_edit(self, prompt_id: str):
        dlg = PromptEditorDialog(self, prompt_id=prompt_id)
        dlg.prompt_saved.connect(self.reload_prompts)
        dlg.prompt_deleted.connect(self.reload_prompts)
        dlg.exec()

    def _handle_rename(self, prompt_id: str):
        dlg = PromptEditorDialog(self, prompt_id=prompt_id, focus_name_only=True)
        dlg.prompt_saved.connect(self.reload_prompts)
        dlg.exec()

    def _handle_duplicate(self, prompt_id: str):
        try:
            prompt_library_instance.duplicate_prompt(prompt_id)
            self.reload_prompts()
        except PromptValidationError as e:
            QMessageBox.warning(self, "Không thể nhân bản", str(e))
        except IOError as e:
            QMessageBox.critical(self, "Lỗi lưu trữ", str(e))

    def _handle_toggle(self, prompt_id: str):
        try:
            prompt_library_instance.toggle_active(prompt_id)
            self.reload_prompts()
        except PromptValidationError as e:
            QMessageBox.warning(self, "Không thể kích hoạt", str(e))
            self.reload_prompts()  # revert checkbox visual state
        except IOError as e:
            QMessageBox.critical(self, "Lỗi lưu trữ", str(e))
            self.reload_prompts()

    def _handle_delete(self, prompt_id: str):
        prompt = prompt_library_instance.get_prompt(prompt_id)
        if prompt is None:
            return

        confirm = QMessageBox(self)
        confirm.setWindowTitle("Xóa prompt?")
        confirm.setText(
            f"Bạn có chắc muốn xóa prompt:\n\n\"{prompt.get('name', '')}\"\n\n"
            "Thao tác này không thể hoàn tác."
        )
        confirm.setIcon(QMessageBox.Icon.Warning)
        btn_yes = confirm.addButton("Xóa", QMessageBox.ButtonRole.DestructiveRole)
        confirm.addButton("Hủy", QMessageBox.ButtonRole.RejectRole)
        confirm.exec()

        if confirm.clickedButton() != btn_yes:
            return

        try:
            prompt_library_instance.delete_prompt(prompt_id)
            self.reload_prompts()
        except PromptValidationError as e:
            QMessageBox.warning(self, "Không thể xóa", str(e))
        except IOError as e:
            QMessageBox.critical(self, "Lỗi lưu trữ", str(e))
