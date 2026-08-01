"""
app/gui/workers/pipeline_worker.py
===================================
QThread Worker for Non-blocking Pipeline Execution & Async Tasks.
"""

import logging
from typing import Optional
from PySide6.QtCore import QThread, Signal

from app.core.pipeline import PipelineEngine
from app.core.project import Project

logger = logging.getLogger("PipelineWorker")


class PipelineWorker(QThread):
    """Background worker executing pipeline steps without freezing Qt Main UI Thread."""

    step_started = Signal(str, str)         # step_key, step_name
    progress_updated = Signal(str, int, int, str) # step_key, cur, total, message
    step_finished = Signal(str, str)        # step_key, message
    step_failed = Signal(str, str)          # step_key, error_message
    pipeline_completed = Signal(bool)       # success

    def __init__(self, project: Project, source_input: str = "", start_step_key: Optional[str] = None, force_rerun: bool = False):
        super().__init__()
        self.project = project
        self.source_input = source_input
        self.start_step_key = start_step_key
        self.force_rerun = force_rerun
        self.engine: Optional[PipelineEngine] = None

    def run(self) -> None:
        """QThread entry point."""
        logger.info("PipelineWorker started for project %s", self.project.project_id)

        self.engine = PipelineEngine(
            project=self.project,
            source_input=self.source_input,
            on_step_start=lambda k, n: self.step_started.emit(k, n),
            on_progress=lambda k, c, t, m: self.progress_updated.emit(k, c, t, m),
            on_step_finish=lambda k, m: self.step_finished.emit(k, m),
            on_step_fail=lambda k, e: self.step_failed.emit(k, e)
        )

        success = self.engine.run(start_step_key=self.start_step_key, force_rerun=self.force_rerun)
        self.pipeline_completed.emit(success)

    def cancel(self) -> None:
        """Cancel background pipeline execution."""
        if self.engine:
            self.engine.cancel()
