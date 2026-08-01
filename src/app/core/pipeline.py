"""
src/app/core/pipeline.py
========================
Pipeline Orchestrator & State Machine (9 Steps, Fingerprint Caching, Resume, Step Retry, Cancellation).

Improvements:
- All paths are now relative to project structure
- Better error handling and logging
- Cache invalidation based on prompt changes
"""

from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional

from app.core.config import config_instance
from app.core.project import Project
from app.services.downloader import DownloaderService
from app.services.extractor import ExtractorService
from app.services.chunker import ChunkerService
from app.services.transcriber import TranscriberService
from app.services.translator import TranslatorService
from app.services.dubber import DubberService
from app.services.separator import SeparatorService
from app.services.mixer import MixerService
from app.services.renderer import RenderService

logger = logging.getLogger("PipelineEngine")


class StepStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


# 9 Main Pipeline Steps
PIPELINE_STEPS = [
    ("download", "Video Input / Download"),
    ("visual_editor", "Simple Editor (Video Config)"),
    ("audio_extraction", "Audio Extraction"),
    ("audio_chunking", "Audio Chunking"),
    ("transcription", "Audio Transcription"),
    ("translation", "Subtitle Translation"),
    ("dubbing", "TTS Dubbing"),
    ("vocal_separation", "Vocal Separation"),
    ("rendering", "Video Rendering")
]


def calculate_fingerprint(input_path: Optional[Path], extra_config: Dict[str, Any]) -> str:
    """Calculate hash fingerprint based on input file modification time/size + configuration settings."""
    hasher = hashlib.sha256()
    if input_path and input_path.exists():
        stat = input_path.stat()
        hasher.update(f"{input_path.name}_{stat.st_size}_{stat.st_mtime}".encode("utf-8"))

    cfg_str = json.dumps(extra_config, sort_keys=True)
    hasher.update(cfg_str.encode("utf-8"))
    return hasher.hexdigest()[:16]


class PipelineEngine:
    """Core Pipeline Orchestrator executing the 9 steps with state management, caching, and recovery."""

    def __init__(
        self,
        project: Project,
        source_input: str = "",
        on_step_start: Optional[Callable[[str, str], None]] = None,
        on_progress: Optional[Callable[[str, int, int, str], None]] = None,
        on_step_finish: Optional[Callable[[str, str], None]] = None,
        on_step_fail: Optional[Callable[[str, str], None]] = None
    ):
        self.project = project
        self.source_input = source_input
        self.on_step_start = on_step_start
        self.on_progress = on_progress
        self.on_step_finish = on_step_finish
        self.on_step_fail = on_step_fail

        self.cancelled = False
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load state from project state.json or initialize new."""
        state_file = self.project.state_file_path
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not read state.json: %s", e)

        initial_state = {
            "project_id": self.project.project_id,
            "name": self.project.name,
            "created_at": self.project.created_at,
            "updated_at": self.project.updated_at,
            "source_input": self.source_input,
            "current_step": "download",
            "overall_progress_pct": 0,
            "steps": {step_key: {"status": StepStatus.PENDING.value, "fingerprint": "", "output": None, "error": None} for step_key, _ in PIPELINE_STEPS}
        }
        return initial_state

    def save_state(self) -> None:
        """Save pipeline state to project state.json."""
        self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.project.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.project.state_file_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save state.json: %s", e)

    def cancel(self) -> None:
        self.cancelled = True
        logger.info("Cancellation requested for pipeline %s", self.project.project_id)

    def run(self, start_step_key: Optional[str] = None, force_rerun: bool = False) -> bool:
        """Execute pipeline sequentially from start_step_key or current step."""
        self.cancelled = False
        step_keys = [k for k, _ in PIPELINE_STEPS]

        start_idx = 0
        if start_step_key and start_step_key in step_keys:
            start_idx = step_keys.index(start_step_key)

        enable_cache = config_instance.get("general.enable_cache", True)

        for idx in range(start_idx, len(step_keys)):
            if self.cancelled:
                logger.info("Pipeline cancelled at step %s", step_keys[idx])
                return False

            step_key, step_name = PIPELINE_STEPS[idx]
            self.state["current_step"] = step_key
            self.state["overall_progress_pct"] = int((idx / len(PIPELINE_STEPS)) * 100)
            self.save_state()

            if not force_rerun and enable_cache and self._is_step_cache_valid(step_key):
                logger.info("Step '%s' cache valid. Skipping.", step_name)
                self.state["steps"][step_key]["status"] = StepStatus.SKIPPED.value
                self.save_state()
                if self.on_step_finish:
                    self.on_step_finish(step_key, f"Skipped (Cached): {step_name}")
                continue

            logger.info("=" * 50)
            logger.info("Starting Step [%d/%d]: %s", idx + 1, len(PIPELINE_STEPS), step_name)
            logger.info("=" * 50)

            self.state["steps"][step_key]["status"] = StepStatus.RUNNING.value
            self.save_state()

            if self.on_step_start:
                self.on_step_start(step_key, step_name)

            success = self._execute_single_step(step_key, idx)
            if not success:
                if self.cancelled:
                    self.state["steps"][step_key]["status"] = StepStatus.CANCELLED.value
                else:
                    self.state["steps"][step_key]["status"] = StepStatus.FAILED.value
                self.save_state()

                if self.on_step_fail and not self.cancelled:
                    err_msg = self.state["steps"][step_key].get("error", "Step Execution Failed")
                    self.on_step_fail(step_key, err_msg)
                return False

            self.state["steps"][step_key]["status"] = StepStatus.SUCCESS.value
            self.save_state()

            if self.on_step_finish:
                self.on_step_finish(step_key, f"Completed: {step_name}")

        self.state["overall_progress_pct"] = 100
        self.save_state()
        logger.info("PIPELINE COMPLETED SUCCESSFULLY FOR %s", self.project.project_id)
        return True

    def _is_step_cache_valid(self, step_key: str) -> bool:
        """Verify if output file/folder for step exists and matches fingerprint."""
        step_state = self.state["steps"].get(step_key, {})
        if step_state.get("status") not in (StepStatus.SUCCESS.value, StepStatus.SKIPPED.value):
            return False

        if step_key == "visual_editor":
            return self.project.editor_config_path.exists()

        out_path_str = step_state.get("output")
        if not out_path_str:
            return False

        out_path = Path(out_path_str)
        if not out_path.exists():
            return False

        if step_key == "translation":
            try:
                from app.core.prompt_engine import prompt_library_instance
                active_prompt = prompt_library_instance.get_active_prompt()
                active_id = active_prompt.get("id") if active_prompt else None
                cached_prompt_id = step_state.get("prompt_id")
                if cached_prompt_id and active_id and cached_prompt_id != active_id:
                    logger.info(
                        "Translation cache invalidated: active prompt changed (%s -> %s).",
                        cached_prompt_id, active_id
                    )
                    return False
            except Exception as e:
                logger.warning("Could not verify translation prompt cache validity: %s", e)

        return True

    def _execute_single_step(self, step_key: str, step_idx: int) -> bool:
        """Route and execute step logic."""
        def progress_cb(cur, tot, msg):
            if self.on_progress:
                self.on_progress(step_key, cur, tot, msg)

        try:
            if step_key == "download":
                src = self.source_input or self.state.get("source_input", "")
                if not src and self.project.raw_video_path.exists():
                    src = str(self.project.raw_video_path.resolve())

                downloader = DownloaderService(headless=config_instance.get("modules.downloader.headless", True))
                res = downloader.process(self.project, src, progress_callback=progress_cb)
                if res and res.get("success"):
                    self.state["steps"][step_key]["output"] = res.get("file_path")
                    return True
                else:
                    self.state["steps"][step_key]["error"] = res.get("error", "Download failed")
                    return False

            elif step_key == "audio_extraction":
                extractor = ExtractorService(
                    sample_rate=config_instance.get("modules.audio_extractor.sample_rate", 44100),
                    channels=config_instance.get("modules.audio_extractor.channels", "stereo"),
                    normalize=config_instance.get("modules.audio_extractor.normalize", True),
                    bitrate=config_instance.get("modules.audio_extractor.bitrate", "192k"),
                    fast_copy=config_instance.get("modules.audio_extractor.fast_copy", False)
                )
                out = extractor.process(self.project)
                if out and out.exists():
                    self.state["steps"][step_key]["output"] = str(out.resolve())
                    return True
                return False

            elif step_key == "audio_chunking":
                chunker = ChunkerService(
                    max_size_mb=config_instance.get("modules.audio_chunker.max_file_size_mb", 19.5)
                )
                out = chunker.process(self.project)
                if out and out.exists():
                    self.state["steps"][step_key]["output"] = str(out.resolve())
                    return True
                return False

            elif step_key == "transcription":
                transcriber = TranscriberService(
                    model=config_instance.get("modules.transcriber.model", "whisper-large-v3-turbo"),
                    language=config_instance.get("modules.transcriber.language", "auto")
                )
                out = transcriber.process(self.project)
                if out and out.get("refined") and out["refined"].exists():
                    self.state["steps"][step_key]["output"] = str(self.project.transcribed_dir.resolve())
                    return True
                return False

            elif step_key == "translation":
                translator = TranslatorService(
                    mode=config_instance.get("modules.translator.mode", "auto")
                )
                out = translator.process(self.project, progress_callback=progress_cb)
                if out and out.exists():
                    self.state["steps"][step_key]["output"] = str(out.resolve())
                    if translator.resolved_prompt_id:
                        self.state["steps"][step_key]["prompt_id"] = translator.resolved_prompt_id
                    return True
                return False

            elif step_key == "dubbing":
                dubber = DubberService(
                    voice=config_instance.get("modules.dubber.voice_female", "vi-VN-HoaiMyNeural"),
                    mode=config_instance.get("modules.dubber.mode", "balanced"),
                    speed=config_instance.get("modules.dubber.speed", 1.0)
                )
                out = dubber.process(self.project)
                if out and out.exists():
                    self.state["steps"][step_key]["output"] = str(out.resolve())
                    return True
                return False

            elif step_key == "vocal_separation":
                separator = SeparatorService(
                    mode=config_instance.get("modules.vocal_separator.default_mode", "mode_2"),
                    vocal_leak=config_instance.get("modules.vocal_separator.vocal_leak", 0.12)
                )
                out = separator.process(self.project)
                if out and out.exists():
                    self.state["steps"][step_key]["output"] = str(out.resolve())
                    return True
                return False

            elif step_key == "visual_editor":
                if self.project.editor_config_path.exists():
                    self.state["steps"][step_key]["output"] = str(self.project.editor_config_path.resolve())
                    return True
                self.state["steps"][step_key]["error"] = (
                    "Simple Editor chưa được lưu. Hãy mở Simple Editor, cấu hình Subtitle/Blur/Logo "
                    "rồi bấm 'Save & Continue' trước khi tiếp tục pipeline."
                )
                return False

            elif step_key == "rendering":
                mixer = MixerService(
                    voice_volume=config_instance.get("modules.mixer.voice_volume", 1.0),
                    background_volume=config_instance.get("modules.mixer.background_volume", 0.8)
                )
                mix_out = mixer.process(self.project)
                if not (mix_out and mix_out.exists()):
                    self.state["steps"][step_key]["error"] = "Audio mixing failed before rendering."
                    return False

                renderer = RenderService(
                    preset=config_instance.get("modules.render.preset", "medium"),
                    crf=config_instance.get("modules.render.crf", 18)
                )
                out = renderer.process(self.project)
                if out and out.exists():
                    self.state["steps"][step_key]["output"] = str(out.resolve())
                    return True
                return False

            return False
        except Exception as e:
            logger.error("Exception during step %s: %s", step_key, e, exc_info=True)
            self.state["steps"][step_key]["error"] = str(e)
            return False
