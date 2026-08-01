"""
app/gui/components/log_viewer_dialog.py
========================================
Detailed Log Viewer Dialog.
"""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QComboBox
)

from app.gui.styles.theme import DARK_THEME_QSS


class LogViewerDialog(QDialog):
    """Dialog allowing users to inspect detailed technical log files by module or step."""

    def __init__(self, parent=None, log_file_path: str = "app.log"):
        super().__init__(parent)
        self.setWindowTitle("Detailed Technical Log Viewer - ReupTool V3")
        self.resize(750, 500)
        self.setStyleSheet(DARK_THEME_QSS)

        self.log_file_path = Path(log_file_path)

        layout = QVBoxLayout(self)

        # Top Bar
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Select Module / Filter:"))

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Events", "INFO", "WARNING", "ERROR", "FFmpeg", "Groq API", "Gemini API"])
        self.filter_combo.currentTextChanged.connect(self.reload_logs)
        top_layout.addWidget(self.filter_combo)

        top_layout.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "SecondaryButton")
        btn_refresh.clicked.connect(self.reload_logs)
        top_layout.addWidget(btn_refresh)

        layout.addLayout(top_layout)

        # Log Text Box
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        # Bottom Action Bar
        bottom_layout = QHBoxLayout()

        btn_copy = QPushButton("Copy Logs")
        btn_copy.setProperty("class", "SecondaryButton")
        btn_copy.clicked.connect(self.copy_to_clipboard)
        bottom_layout.addWidget(btn_copy)

        btn_clear = QPushButton("Clear Display")
        btn_clear.setProperty("class", "SecondaryButton")
        btn_clear.clicked.connect(self.log_text.clear)
        bottom_layout.addWidget(btn_clear)

        bottom_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "PrimaryButton")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

        self.reload_logs()

    def reload_logs(self):
        """Read log file and display filtered content."""
        if not self.log_file_path.exists():
            self.log_text.setPlainText(f"Log file '{self.log_file_path}' does not exist yet.")
            return

        filter_text = self.filter_combo.currentText()
        try:
            with open(self.log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            if filter_text != "All Events":
                lines = [line for line in lines if filter_text.lower() in line.lower()]

            self.log_text.setPlainText("".join(lines[-1000:]))  # Display last 1000 lines
            self.log_text.moveCursor(self.log_text.textCursor().MoveOperation.End)
        except Exception as e:
            self.log_text.setPlainText(f"Error reading log file: {e}")

    def copy_to_clipboard(self):
        self.log_text.selectAll()
        self.log_text.copy()
