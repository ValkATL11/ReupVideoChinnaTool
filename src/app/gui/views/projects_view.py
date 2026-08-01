"""
app/gui/views/projects_view.py
===============================
Projects Management View.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QInputDialog, QMessageBox, QHeaderView
)

from app.core.project import ProjectManager
import subprocess
import sys


class ProjectsView(QWidget):
    """View for managing projects (New, Open, Recent, Rename, Duplicate, Delete, Open Folder)."""

    open_project_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_manager = ProjectManager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Top Bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("📁 All Projects"))

        top_bar.addStretch()

        btn_new = QPushButton("+ New Project")
        btn_new.setProperty("class", "PrimaryButton")
        btn_new.clicked.connect(self._create_new)
        top_bar.addWidget(btn_new)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "SecondaryButton")
        btn_refresh.clicked.connect(self.reload_projects)
        top_bar.addWidget(btn_refresh)

        layout.addLayout(top_bar)

        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Project ID", "Name", "Path", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.reload_projects()

    def reload_projects(self):
        projects = self.project_manager.list_projects()
        self.table.setRowCount(0)

        for proj in projects:
            row = self.table.rowCount()
            self.table.insertRow(row)

            pid = proj.get("project_id", "")
            self.table.setItem(row, 0, QTableWidgetItem(pid))
            self.table.setItem(row, 1, QTableWidgetItem(proj.get("name", pid)))
            self.table.setItem(row, 2, QTableWidgetItem(proj.get("path", "")))

            # Actions
            act_w = QWidget()
            hbox = QHBoxLayout(act_w)
            hbox.setContentsMargins(2, 2, 2, 2)

            btn_open = QPushButton("Open")
            btn_open.setProperty("class", "PrimaryButton")
            btn_open.clicked.connect(lambda _, p=pid: self.open_project_requested.emit(p))
            hbox.addWidget(btn_open)

            btn_folder = QPushButton("Folder")
            btn_folder.setProperty("class", "SecondaryButton")
            p_path = proj.get("path")
            btn_folder.clicked.connect(lambda _, p=p_path: self._open_folder(p))
            hbox.addWidget(btn_folder)

            btn_del = QPushButton("Delete")
            btn_del.setProperty("class", "SecondaryButton")
            btn_del.clicked.connect(lambda _, p=pid: self._delete_project(p))
            hbox.addWidget(btn_del)

            self.table.setCellWidget(row, 3, act_w)

    def _create_new(self):
        custom_id, ok = QInputDialog.getText(self, "New Project", "Enter Project ID (leave empty for auto):")
        if ok:
            try:
                proj = self.project_manager.create_project(custom_id=custom_id if custom_id.strip() else None)
                self.reload_projects()
                self.open_project_requested.emit(proj.project_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create project: {e}")

    def _open_folder(self, folder_path: str):
        if folder_path and Path(folder_path).exists():
            if sys.platform == "win32":
                subprocess.run(["explorer", str(Path(folder_path).resolve())])
            else:
                subprocess.run(["open", str(Path(folder_path).resolve())])

    def _delete_project(self, project_id: str):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete project '{project_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.project_manager.delete_project(project_id)
            self.reload_projects()
