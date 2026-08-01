"""
app/gui/views/pipeline_view.py
================================
Pipeline Engine Status & Controls View (9 Main Steps).
"""

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QGroupBox
)

from app.core.pipeline import PIPELINE_STEPS, StepStatus
from app.core.project import Project, ProjectManager
from app.gui.workers.pipeline_worker import PipelineWorker
from app.gui.components.log_viewer_dialog import LogViewerDialog


class PipelineView(QWidget):
    """Pipeline Engine View displaying real-time 9-step status, progress & controls."""

    # Emitted when the pipeline halts at the "visual_editor" gate (Simple Editor
    # not saved yet), so MainWindow can automatically switch to the Simple Editor.
    open_simple_editor_requested = Signal(str)  # project_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_manager = ProjectManager()
        self.active_project: Optional[Project] = None
        self.worker: Optional[PipelineWorker] = None
        self.source_input = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header Info Card
        card_info = QFrame()
        card_info.setProperty("class", "CardFrame")
        v_info = QVBoxLayout(card_info)

        self.lbl_proj_title = QLabel("Pipeline Engine - No Project Selected")
        self.lbl_proj_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        v_info.addWidget(self.lbl_proj_title)

        self.lbl_status = QLabel("Status: Idle")
        self.lbl_status.setStyleSheet("color: #00a2ed; font-weight: 600;")
        v_info.addWidget(self.lbl_status)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        v_info.addWidget(self.progress_bar)

        # Controls Row
        hbox_ctrl = QHBoxLayout()

        self.btn_run = QPushButton("▶ Run Full Pipeline")
        self.btn_run.setProperty("class", "PrimaryButton")
        self.btn_run.clicked.connect(self._run_pipeline)
        hbox_ctrl.addWidget(self.btn_run)

        self.btn_resume = QPushButton("⏯ Resume Pipeline")
        self.btn_resume.setProperty("class", "SecondaryButton")
        self.btn_resume.clicked.connect(self._resume_pipeline)
        hbox_ctrl.addWidget(self.btn_resume)

        self.btn_stop = QPushButton("⏹ Stop / Cancel")
        self.btn_stop.setProperty("class", "SecondaryButton")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_pipeline)
        hbox_ctrl.addWidget(self.btn_stop)

        btn_logs = QPushButton("📜 View Log")
        btn_logs.setProperty("class", "SecondaryButton")
        btn_logs.clicked.connect(self._open_logs)
        hbox_ctrl.addWidget(btn_logs)

        v_info.addLayout(hbox_ctrl)
        layout.addWidget(card_info)

        # 9 Steps Status List Card
        card_steps = QFrame()
        card_steps.setProperty("class", "CardFrame")
        v_steps = QVBoxLayout(card_steps)

        v_steps.addWidget(QLabel("📋 9 Pipeline Steps Lifecycle"))

        self.step_list = QListWidget()
        v_steps.addWidget(self.step_list)

        layout.addWidget(card_steps)

        self._init_step_list()

    def set_project(self, project_id: str, source_input: str = ""):
        """Set currently active project for pipeline view."""
        self.active_project = Project(project_id)
        self.source_input = source_input
        self.lbl_proj_title.setText(f"Pipeline Engine — Project: {project_id}")
        self.reload_step_statuses()

    def _init_step_list(self):
        self.step_list.clear()
        for idx, (step_key, step_name) in enumerate(PIPELINE_STEPS, 1):
            item = QListWidgetItem(f"○ Step {idx}: {step_name} [PENDING]")
            item.setData(Qt.ItemDataRole.UserRole, step_key)
            self.step_list.addItem(item)

    def reload_step_statuses(self):
        if not self.active_project:
            return

        state_file = self.active_project.state_file_path
        if not state_file.exists():
            self._init_step_list()
            return

        state = self.active_project.to_dict()
        import json
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

        steps_data = state.get("steps", {})
        self.progress_bar.setValue(state.get("overall_progress_pct", 0))

        self.step_list.clear()
        for idx, (step_key, step_name) in enumerate(PIPELINE_STEPS, 1):
            s_data = steps_data.get(step_key, {})
            st = s_data.get("status", StepStatus.PENDING.value)

            icon = "○"
            if st in (StepStatus.SUCCESS.value, StepStatus.SKIPPED.value):
                icon = "✓"
            elif st == StepStatus.RUNNING.value:
                icon = "⟳"
            elif st == StepStatus.FAILED.value:
                icon = "❌"

            item = QListWidgetItem(f"{icon} Step {idx}: {step_name} [{st}]")
            item.setData(Qt.ItemDataRole.UserRole, step_key)
            self.step_list.addItem(item)

    def _run_pipeline(self):
        if not self.active_project:
            QMessageBox.warning(self, "Warning", "Please select or create a project first!")
            return
        self._start_worker(start_step_key=None, force_rerun=True)

    def _resume_pipeline(self):
        if not self.active_project:
            QMessageBox.warning(self, "Warning", "Please select or create a project first!")
            return
        self._start_worker(start_step_key=None, force_rerun=False)

    def resume_after_editor(self, project_id: str):
        """Called by MainWindow once Simple Editor's 'Save & Continue' has written
        editor_config.json. Resumes the pipeline (cache-aware) so it proceeds
        straight into Audio Extraction -> STT -> Translation -> TTS -> ... -> Render."""
        if not self.active_project or self.active_project.project_id != project_id:
            self.active_project = Project(project_id)
        self.reload_step_statuses()
        self._resume_pipeline()

    def _start_worker(self, start_step_key: Optional[str] = None, force_rerun: bool = False):
        self.btn_run.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_status.setText("Status: Running Pipeline...")

        self.worker = PipelineWorker(
            project=self.active_project,
            source_input=self.source_input,
            start_step_key=start_step_key,
            force_rerun=force_rerun
        )
        self.worker.step_started.connect(self._on_step_started)
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.step_finished.connect(self._on_step_finished)
        self.worker.step_failed.connect(self._on_step_failed)
        self.worker.pipeline_completed.connect(self._on_pipeline_completed)
        self.worker.start()

    def _stop_pipeline(self):
        if self.worker:
            self.worker.cancel()
            self.lbl_status.setText("Status: Stopping...")

    def _on_step_started(self, step_key: str, step_name: str):
        self.lbl_status.setText(f"Status: Running {step_name}...")
        self.reload_step_statuses()

    def _on_progress_updated(self, step_key: str, cur: int, tot: int, msg: str):
        self.lbl_status.setText(f"[{cur}/{tot}] {msg}")

    def _on_step_finished(self, step_key: str, msg: str):
        self.reload_step_statuses()

    def _on_step_failed(self, step_key: str, err: str):
        self.reload_step_statuses()
        self.btn_run.setEnabled(True)
        self.btn_resume.setEnabled(True)
        self.btn_stop.setEnabled(False)

        if step_key == "visual_editor" and self.active_project:
            self.lbl_status.setText("Status: Waiting for Simple Editor...")
            QMessageBox.information(
                self, "Simple Editor Required",
                "Hãy cấu hình Subtitle / Blur / Logo trong Simple Editor rồi bấm "
                "'Save & Continue' để pipeline tự động tiếp tục."
            )
            self.open_simple_editor_requested.emit(self.active_project.project_id)
            return

        QMessageBox.critical(self, "Step Failed", f"Step '{step_key}' failed:\n\n{err}")

    def _on_pipeline_completed(self, success: bool):
        self.btn_run.setEnabled(True)
        self.btn_resume.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if success:
            self.lbl_status.setText("Status: Completed Successfully! 🎉")
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "Success", "Full Pipeline finished successfully!")
        else:
            self.lbl_status.setText("Status: Pipeline Stopped or Failed.")

    def _open_logs(self):
        dlg = LogViewerDialog(self)
        dlg.exec()
