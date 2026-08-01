"""
app/gui/components/prompt_generator_dialog.py
=============================================
SRT Translation Prompt Generator Dialog enforcing Core Rules 1 & 2.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QLineEdit, QMessageBox
)

from app.core.prompt_engine import PromptGenerator, prompt_library_instance
from app.gui.styles.theme import DARK_THEME_QSS


class PromptGeneratorDialog(QDialog):
    """Dialog allowing users to describe intent in natural language and generate a compliant SRT translation prompt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SRT Translation Prompt Generator - ReupTool V3")
        self.resize(700, 550)
        self.setStyleSheet(DARK_THEME_QSS)

        layout = QVBoxLayout(self)

        # Instructions
        lbl_info = QLabel(
            "Enter your translation style requirements in natural language below.\n"
            "The generator will automatically append mandatory Core Rules:\n"
            "• Core Rule 1: Max Vietnamese words = Duration × 3.5 (Under 0.8s -> max 2 words)\n"
            "• Core Rule 2: Elimination of filler words (thì, là, mà, rằng, ấy, vẫn, đang, đã, sẽ, được, bị, ...)"
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #a0a0b0; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(lbl_info)

        # User Request Input
        layout.addWidget(QLabel("Your Requirements (Natural Language):"))
        self.req_input = QLineEdit()
        self.req_input.setPlaceholderText("e.g. Dịch phim cổ trang Trung Quốc sang tiếng Việt tự nhiên, phù hợp giọng đọc TTS nữ.")
        layout.addWidget(self.req_input)

        # Generate Button
        btn_gen = QPushButton("⚡ Generate Prompt")
        btn_gen.setProperty("class", "PrimaryButton")
        btn_gen.clicked.connect(self.generate_prompt)
        layout.addWidget(btn_gen)

        # Output Preview Box
        layout.addWidget(QLabel("Generated System Prompt:"))
        self.prompt_preview = QTextEdit()
        layout.addWidget(self.prompt_preview)

        # Name Input for saving
        save_layout = QHBoxLayout()
        save_layout.addWidget(QLabel("Prompt Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("My Custom SRT Prompt")
        save_layout.addWidget(self.name_input)

        btn_save = QPushButton("Save to Prompt Library")
        btn_save.setProperty("class", "PrimaryButton")
        btn_save.clicked.connect(self.save_prompt)
        save_layout.addWidget(btn_save)

        layout.addLayout(save_layout)

        # Close
        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "SecondaryButton")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def generate_prompt(self):
        req = self.req_input.text().strip()
        generated = PromptGenerator.generate(req)
        self.prompt_preview.setPlainText(generated)

    def save_prompt(self):
        content = self.prompt_preview.toPlainText().strip()
        name = self.name_input.text().strip()

        if not content:
            QMessageBox.warning(self, "Warning", "Please generate a prompt first!")
            return
        if not name:
            QMessageBox.warning(self, "Warning", "Please enter a name for the prompt!")
            return

        prompt_library_instance.add_prompt(name=name, content=content, description="Generated via SRT Prompt Generator")
        QMessageBox.information(self, "Success", f"Prompt '{name}' saved successfully to Library!")
        self.accept()
