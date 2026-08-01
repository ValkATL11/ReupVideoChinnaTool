"""
src/app/services/transcriber.py
================================
Wrapper service around transcriber.py with API Key Pool rotation.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.transcriber import TranscriberAPI
from app.core.key_manager import key_manager_instance
from app.core.project import Project

logger = logging.getLogger("TranscriberService")


class TranscriberService:
    """Service wrapper for Groq Whisper transcription with API key pool rotation."""

    def __init__(self, model: str = "whisper-large-v3-turbo", language: str = "auto"):
        self.model = model
        self.language = language

    def process(self, project: Project) -> Optional[Dict[str, Path]]:
        """Run 2-pass transcription on chunked folder of project."""
        chunked_folder = project.chunked_dir
        if not chunked_folder.exists():
            logger.error("Chunked folder does not exist: %s", chunked_folder)
            return None

        groq_key = key_manager_instance.groq.get_active_key()
        if not groq_key:
            logger.error("No active Groq API key available! Please add/enable Groq API keys in Settings.")
            raise RuntimeError("No active Groq API key available in Key Manager.")

        output_dir = Path("data/transcriber_output")
        output_dir.mkdir(parents=True, exist_ok=True)

        max_key_attempts = max(1, len(key_manager_instance.groq.keys))
        for attempt in range(max_key_attempts):
            try:
                runner = TranscriberAPI(api_key=groq_key, model=self.model)
                result = runner.process_folder(chunked_folder, language=self.language)
                if not result:
                    raise RuntimeError(f"Transcription failed with key {groq_key[:6]}...")

                out_files = runner.export_outputs(result, output_dir)
                return out_files
            except Exception as e:
                logger.warning("Groq API error on attempt %d: %s", attempt + 1, e)
                groq_key = key_manager_instance.groq.mark_error(groq_key)
                if not groq_key:
                    break

        raise RuntimeError("All Groq API keys failed or rate-limited.")
