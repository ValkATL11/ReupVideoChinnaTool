"""
app/gui/views/dashboard_view.py
================================
Main Dashboard View.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QLineEdit, QPushButton,
    QFileDialog, QListWidget, QListWidgetItem, QMessageBox
)

from app.core.project import ProjectManager, generate_project_id


class DashboardView(QWidget):
    """Main Dashboard View for Quick Input & Recent Projects Overview."""

    start_pipeline_requested = Signal(str, str)  # project_id, source_input

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_manager = ProjectManager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Welcome Card
        card_welcome = QFrame()
        card_welcome.setProperty("class", "CardFrame")
        v_wel = QVBoxLayout(card_welcome)

        lbl_head = QLabel("🚀 Start New Video Processing Task")
        lbl_head.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        v_wel.addWidget(lbl_head)

        lbl_desc = QLabel("Enter a Video URL (Douyin, TikTok, YouTube) or Browse a Local Video file to auto-create a Project.")
        lbl_desc.setStyleSheet("color: #a0a0b0;")
        v_wel.addWidget(lbl_desc)

        # Input Row
        hbox_in = QHBoxLayout()

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Paste Douyin/TikTok/YouTube URL or Local File Path (e.g. D:/my_video.mp4)...")
        hbox_in.addWidget(self.input_field)

        btn_browse = QPushButton("📁 Browse File...")
        btn_browse.setProperty("class", "SecondaryButton")
        btn_browse.clicked.connect(self._browse_file)
        hbox_in.addWidget(btn_browse)

        layout.addWidget(card_welcome)

        # Custom Project ID Row
        hbox_id = QHBoxLayout()
        hbox_id.addWidget(QLabel("Project ID:"))

        self.project_id_input = QLineEdit()
        self.project_id_input.setPlaceholderText("Auto Generate (PRJ-YYMMDD-XXXX) or Custom ID (e.g. Drama_001)...")
        hbox_id.addWidget(self.project_id_input)

        btn_gen_id = QPushButton("Generate ID")
        btn_gen_id.setProperty("class", "SecondaryButton")
        btn_gen_id.clicked.connect(lambda: self.project_id_input.setText(generate_project_id()))
        hbox_id.addWidget(btn_gen_id)

        v_wel.addLayout(hbox_in)
        v_wel.addLayout(hbox_id)

        # Action Buttons
        hbox_act = QHBoxLayout()
        btn_start = QPushButton("▶ Start Full Pipeline")
        btn_start.setProperty("class", "PrimaryButton")
        btn_start.setStyleSheet("font-size: 15px; padding: 10px 24px;")
        btn_start.clicked.connect(self._on_start_clicked)
        hbox_act.addWidget(btn_start)

        v_wel.addLayout(hbox_act)

        # Recent Projects Card
        card_recent = QFrame()
        card_recent.setProperty("class", "CardFrame")
        v_rec = QVBoxLayout(card_recent)

        v_rec.addWidget(QLabel("🕒 Recent Projects"))

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._on_recent_double_clicked)
        v_rec.addWidget(self.recent_list)

        layout.addWidget(card_recent)

        self.reload_recents()

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.webm);;All Files (*.*)"
        )
        if file_path:
            self.input_field.setText(file_path)

    def _on_start_clicked(self):
        src = self.input_field.text().strip()
        custom_id = self.project_id_input.text().strip()

        if not src:
            QMessageBox.warning(self, "Warning", "Please enter a Video URL or select a Local File!")
            return

        try:
            proj = self.project_manager.create_project(custom_id=custom_id if custom_id else None)
            self.start_pipeline_requested.emit(proj.project_id, src)
            self.reload_recents()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create project: {e}")

    def reload_recents(self):
        self.recent_list.clear()
        projects = self.project_manager.get_recent_projects()
        for p in projects:
            item = QListWidgetItem(f"🆔 {p.get('project_id')} | Name: {p.get('name')} | Created: {p.get('created_at')[:10]}")
            item.setData(Qt.ItemDataRole.UserRole, p.get("project_id"))
            self.recent_list.addItem(item)

    def _on_recent_double_clicked(self, item: QListWidgetItem):
        proj_id = item.data(Qt.ItemDataRole.UserRole)
        if proj_id:
            self.start_pipeline_requested.emit(proj_id, "")
