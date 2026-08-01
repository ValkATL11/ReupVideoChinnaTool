"""
app/gui/main_window.py
======================
Main Desktop Window of ReupTool V3 integrating Header, Sidebar, and 5 Views.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget

from app.gui.components.header import AppHeader
from app.gui.components.sidebar import AppSidebar
from app.gui.styles.theme import apply_theme
from app.gui.views.dashboard_view import DashboardView
from app.gui.views.projects_view import ProjectsView
from app.gui.views.pipeline_view import PipelineView
from app.gui.views.editor_view import VisualEditorView
from app.gui.views.prompt_manager_view import PromptManagerView
from app.gui.views.settings_view import SettingsView


class MainWindow(QMainWindow):
    """Main Application Window for ReupTool V3 Desktop."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReupTool V3 — Automated Video Dubbing & Processing Workstation")
        self.resize(1280, 800)

        # Central Widget & Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Header
        self.header = AppHeader(self)
        root_layout.addWidget(self.header)

        # Body Layout (Sidebar + Content Stack)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 2. Sidebar
        self.sidebar = AppSidebar(self)
        self.sidebar.page_changed.connect(self._on_nav_page_changed)
        body_layout.addWidget(self.sidebar)

        # 3. Stacked Views
        self.stack = QStackedWidget()

        # View 0: Dashboard
        self.view_dashboard = DashboardView(self)
        self.view_dashboard.start_pipeline_requested.connect(self._on_dashboard_start_pipeline)
        self.stack.addWidget(self.view_dashboard)

        # View 1: Projects
        self.view_projects = ProjectsView(self)
        self.view_projects.open_project_requested.connect(self._on_project_opened)
        self.stack.addWidget(self.view_projects)

        # View 2: Pipeline Engine
        self.view_pipeline = PipelineView(self)
        self.view_pipeline.open_simple_editor_requested.connect(self._on_open_simple_editor_requested)
        self.stack.addWidget(self.view_pipeline)

        # View 3: Visual Editor
        self.view_editor = VisualEditorView(self)
        self.view_editor.config_saved.connect(self._on_editor_config_saved)
        self.stack.addWidget(self.view_editor)

        # View 4: Prompt Management ("Prompt dịch")
        self.view_prompt_manager = PromptManagerView(self)
        self.stack.addWidget(self.view_prompt_manager)

        # View 5: Settings
        self.view_settings = SettingsView(self)
        self.stack.addWidget(self.view_settings)

        body_layout.addWidget(self.stack)
        root_layout.addLayout(body_layout)

    def _on_nav_page_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)

    def _on_dashboard_start_pipeline(self, project_id: str, source_input: str):
        self.header.set_active_project(project_id)
        self.view_pipeline.set_project(project_id, source_input)
        self.view_editor.set_project(project_id)
        # Navigate to Pipeline view
        self.sidebar.btn_group.button(2).setChecked(True)
        self.stack.setCurrentIndex(2)

    def _on_project_opened(self, project_id: str):
        self.header.set_active_project(project_id)
        self.view_pipeline.set_project(project_id, "")
        self.view_editor.set_project(project_id)
        # Navigate to Pipeline view
        self.sidebar.btn_group.button(2).setChecked(True)
        self.stack.setCurrentIndex(2)

    def _on_open_simple_editor_requested(self, project_id: str):
        """Pipeline halted at the Simple Editor gate (right after Download) -
        switch the user straight into the Simple Editor to configure it."""
        self.view_editor.set_project(project_id)
        self.sidebar.btn_group.button(3).setChecked(True)
        self.stack.setCurrentIndex(3)

    def _on_editor_config_saved(self, project_id: str):
        """Simple Editor's 'Save & Continue' just wrote editor_config.json -
        jump back to Pipeline and auto-resume into Audio Extraction / STT /
        Translation / TTS / ... / Render."""
        self.sidebar.btn_group.button(2).setChecked(True)
        self.stack.setCurrentIndex(2)
        self.view_pipeline.resume_after_editor(project_id)
