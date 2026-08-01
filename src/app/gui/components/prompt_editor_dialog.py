"""
app/gui/components/prompt_editor_dialog.py
===========================================
Add / Edit / Rename dialog for Translation prompts.

Backed by app.core.prompt_engine.prompt_library_instance so the dialog is a
thin UI layer over the single source of truth used by the Translator.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QCheckBox, QMessageBox
)

from app.core.prompt_engine import (
    prompt_library_instance, PromptValidationError, extract_placeholders
)
from app.gui.styles.theme import DARK_THEME_QSS


class PromptEditorDialog(QDialog):
    """Dialog used for both creating a new prompt and editing an existing one.

    Modes:
      - Create: prompt_id is None.
      - Edit:   prompt_id is set; fields prefilled from the existing prompt.
      - Rename: prompt_id is set and focus_name_only=True -> only the name
                field is enabled, satisfying the "rename via edit dialog,
                focused on name" flow.
    """

    prompt_saved = Signal()
    prompt_deleted = Signal()

    def __init__(self, parent=None, prompt_id: str = None, focus_name_only: bool = False):
        super().__init__(parent)
        self.prompt_id = prompt_id
        self.is_edit_mode = prompt_id is not None
        self.focus_name_only = focus_name_only
        self._existing = prompt_library_instance.get_prompt(prompt_id) if prompt_id else None

        title = "Đổi tên prompt" if focus_name_only else ("Chỉnh sửa prompt" if self.is_edit_mode else "Thêm prompt mới")
        self.setWindowTitle(f"{title} - ReupTool V3")
        self.resize(640, 560 if not focus_name_only else 180)
        self.setStyleSheet(DARK_THEME_QSS)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Name ---
        layout.addWidget(QLabel("Tên prompt"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ví dụ: Prompt chuyên ngành")
        if self._existing:
            self.name_input.setText(self._existing.get("name", ""))
        layout.addWidget(self.name_input)

        if not focus_name_only:
            # --- Description ---
            layout.addWidget(QLabel("Mô tả"))
            self.desc_input = QLineEdit()
            self.desc_input.setPlaceholderText("Mô tả ngắn gọn mục đích sử dụng prompt này")
            if self._existing:
                self.desc_input.setText(self._existing.get("description", ""))
            layout.addWidget(self.desc_input)

            # --- Content ---
            content_header = QHBoxLayout()
            content_header.addWidget(QLabel("Nội dung prompt"))
            content_header.addStretch()
            self.char_count_lbl = QLabel("0 ký tự")
            self.char_count_lbl.setStyleSheet("color: #8a8a98; font-size: 11px;")
            content_header.addWidget(self.char_count_lbl)
            layout.addLayout(content_header)

            self.content_input = QPlainTextEdit()
            self.content_input.setPlaceholderText(
                "Nhập nội dung prompt dùng cho dịch thuật...\n\n"
                "Ví dụ: hướng dẫn văn phong, giới hạn độ dài, quy tắc định dạng SRT..."
            )
            self.content_input.setMinimumHeight(260)
            # Preserve exact text; QPlainTextEdit does not reformat/auto-correct.
            if self._existing:
                self.content_input.setPlainText(self._existing.get("content", ""))
            self.content_input.textChanged.connect(self._update_char_count)
            layout.addWidget(self.content_input)
            self._update_char_count()

            placeholders = extract_placeholders(self._existing.get("content", "")) if self._existing else []
            if placeholders:
                var_lbl = QLabel("Biến khả dụng: " + "  ".join(placeholders))
                var_lbl.setStyleSheet("color: #6fb8ff; font-size: 11px;")
                layout.addWidget(var_lbl)

            # --- Active toggle ---
            self.active_chk = QCheckBox("Kích hoạt (dùng prompt này cho Translation)")
            if self._existing:
                self.active_chk.setChecked(bool(self._existing.get("active")))
                if self._existing.get("is_builtin"):
                    pass  # builtin can still be activated, just not edited/deleted
            layout.addWidget(self.active_chk)

            if self._existing and self._existing.get("is_builtin"):
                lock_lbl = QLabel("Đây là prompt hệ thống (built-in) — không thể chỉnh sửa nội dung hoặc xóa.")
                lock_lbl.setWordWrap(True)
                lock_lbl.setStyleSheet("color: #e0a030; font-size: 11px;")
                layout.addWidget(lock_lbl)
                self.name_input.setEnabled(False)
                self.desc_input.setEnabled(False)
                self.content_input.setReadOnly(True)
        else:
            self.desc_input = None
            self.content_input = None
            self.active_chk = None

        # --- Buttons ---
        btn_row = QHBoxLayout()

        if self.is_edit_mode and not focus_name_only and self._existing and not self._existing.get("is_builtin"):
            btn_delete = QPushButton("Xóa")
            btn_delete.setProperty("class", "SecondaryButton")
            btn_delete.setStyleSheet("QPushButton { color: #ff6b6b; border-color: #6b2c2c; }")
            btn_delete.clicked.connect(self._handle_delete)
            btn_row.addWidget(btn_delete)

        btn_row.addStretch()

        btn_cancel = QPushButton("Hủy")
        btn_cancel.setProperty("class", "SecondaryButton")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        save_label = "Lưu tên" if focus_name_only else ("Lưu thay đổi" if self.is_edit_mode else "Tạo prompt")
        btn_save = QPushButton(save_label)
        btn_save.setProperty("class", "PrimaryButton")
        btn_save.clicked.connect(self._handle_save)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

        self.name_input.setFocus()
        self.name_input.selectAll()

    def _update_char_count(self):
        if self.content_input is not None:
            n = len(self.content_input.toPlainText())
            self.char_count_lbl.setText(f"{n:,} ký tự")

    def _handle_save(self):
        name = self.name_input.text().strip()

        try:
            if self.focus_name_only:
                prompt_library_instance.rename_prompt(self.prompt_id, name)
                self.prompt_saved.emit()
                self.accept()
                return

            description = self.desc_input.text().strip()
            content = self.content_input.toPlainText()
            want_active = self.active_chk.isChecked()

            if self.is_edit_mode:
                if self._existing and self._existing.get("is_builtin"):
                    # Built-in prompts: only the active toggle is editable.
                    if want_active and not self._existing.get("active"):
                        prompt_library_instance.activate_prompt(self.prompt_id)
                    self.prompt_saved.emit()
                    self.accept()
                    return

                prompt_library_instance.update_prompt(
                    self.prompt_id, name=name, content=content, description=description
                )
                currently_active = prompt_library_instance.get_prompt(self.prompt_id).get("active", False)
                if want_active and not currently_active:
                    prompt_library_instance.activate_prompt(self.prompt_id)
                elif not want_active and currently_active:
                    prompt_library_instance.toggle_active(self.prompt_id)
            else:
                prompt_library_instance.add_prompt(
                    name=name, content=content, description=description, active=want_active
                )

            self.prompt_saved.emit()
            self.accept()

        except PromptValidationError as e:
            QMessageBox.warning(self, "Không hợp lệ", str(e))
        except IOError as e:
            QMessageBox.critical(self, "Lỗi lưu trữ", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi không mong muốn: {e}")

    def _handle_delete(self):
        name = self._existing.get("name", "") if self._existing else ""
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Xóa prompt?")
        confirm.setText(
            f"Bạn có chắc muốn xóa prompt:\n\n\"{name}\"\n\nThao tác này không thể hoàn tác."
        )
        confirm.setIcon(QMessageBox.Icon.Warning)
        btn_yes = confirm.addButton("Xóa", QMessageBox.ButtonRole.DestructiveRole)
        confirm.addButton("Hủy", QMessageBox.ButtonRole.RejectRole)
        confirm.exec()

        if confirm.clickedButton() != btn_yes:
            return

        try:
            prompt_library_instance.delete_prompt(self.prompt_id)
            self.prompt_deleted.emit()
            self.accept()
        except PromptValidationError as e:
            QMessageBox.warning(self, "Không thể xóa", str(e))
        except IOError as e:
            QMessageBox.critical(self, "Lỗi lưu trữ", str(e))
