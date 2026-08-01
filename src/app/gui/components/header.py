"""
app/gui/components/header.py
=============================
App Header Bar Component.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from app.gui.components.key_manager_dialog import KeyManagerDialog
from app.gui.components.log_viewer_dialog import LogViewerDialog


class AppHeader(QFrame):
    """Top Header Bar of ReupTool V3."""

    open_key_manager = Signal()
    open_log_viewer = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setStyleSheet("background-color: #151518; border-bottom: 1px solid #282830;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        # Title
        lbl_title = QLabel("REUPTOOL V3")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078d4;")
        layout.addWidget(lbl_title)

        # Subtitle
        lbl_sub = QLabel("Professional Automated Video Dubbing & Processing")
        lbl_sub.setStyleSheet("font-size: 12px; color: #808090; margin-left: 8px;")
        layout.addWidget(lbl_sub)

        layout.addStretch()

        # Active Project Badge
        self.lbl_active_project = QLabel("Active Project: None")
        self.lbl_active_project.setStyleSheet("background-color: #24242e; border: 1px solid #383848; border-radius: 4px; padding: 4px 10px; font-weight: 600; color: #00a2ed;")
        layout.addWidget(self.lbl_active_project)

        # Quick Actions
        btn_keys = QPushButton("🔑 API Key Pool")
        btn_keys.setProperty("class", "SecondaryButton")
        btn_keys.clicked.connect(self._on_key_pool_clicked)
        layout.addWidget(btn_keys)

        btn_logs = QPushButton("📜 View Log")
        btn_logs.setProperty("class", "SecondaryButton")
        btn_logs.clicked.connect(self._on_logs_clicked)
        layout.addWidget(btn_logs)

    def set_active_project(self, project_id: str):
        self.lbl_active_project.setText(f"Active Project: {project_id}")

    def _on_key_pool_clicked(self):
        dlg = KeyManagerDialog(self)
        dlg.exec()

    def _on_logs_clicked(self):
        dlg = LogViewerDialog(self)
        dlg.exec()
