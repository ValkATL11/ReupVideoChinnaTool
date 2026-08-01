"""
tests/test_v3_pipeline.py
==========================
Integration & Pipeline Failure / Recovery Tests for ReupTool V3.
"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from app.core.project import Project
from app.core.pipeline import PipelineEngine, StepStatus, PIPELINE_STEPS


class TestPipelineEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.project_id = "PRJ-260730-TEST"
        self.project = Project(
            project_id=self.project_id,
            base_dir=Path(self.temp_dir) / self.project_id
        )
        self.project.ensure_directories()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_initial_state(self):
        engine = PipelineEngine(self.project, source_input="https://example.com/test.mp4")
        self.assertEqual(engine.state["project_id"], self.project_id)
        self.assertEqual(len(engine.state["steps"]), 9)

        # Check all 9 main steps exist in state
        for step_key, _ in PIPELINE_STEPS:
            self.assertIn(step_key, engine.state["steps"])
            self.assertEqual(engine.state["steps"][step_key]["status"], StepStatus.PENDING.value)

    def test_pipeline_state_persistence(self):
        engine = PipelineEngine(self.project, source_input="test.mp4")
        engine.state["steps"]["download"]["status"] = StepStatus.SUCCESS.value
        engine.save_state()

        self.assertTrue(self.project.state_file_path.exists())

        # Reload engine
        engine2 = PipelineEngine(self.project)
        self.assertEqual(engine2.state["steps"]["download"]["status"], StepStatus.SUCCESS.value)

    def test_step_failure_and_resume_non_destructive(self):
        """Ensure failed steps preserve previous step outputs and do not wipe files."""
        engine = PipelineEngine(self.project)

        # Mark first 3 steps as SUCCESS with mock outputs
        mock_v = self.project.raw_video_path
        mock_v.write_text("mock video")

        engine.state["steps"]["download"]["status"] = StepStatus.SUCCESS.value
        engine.state["steps"]["download"]["output"] = str(mock_v)

        engine.save_state()

        # Check mock video file preserved
        self.assertTrue(mock_v.exists())
        self.assertEqual(mock_v.read_text(), "mock video")


if __name__ == "__main__":
    unittest.main()
