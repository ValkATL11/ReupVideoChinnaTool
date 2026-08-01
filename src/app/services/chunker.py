"""
src/app/services/chunker.py
============================
Wrapper service around audio_chunker.py for smart audio chunking.
"""

import logging
from pathlib import Path
from typing import Optional

from modules.audio_chunker import SmartAudioChunker
from app.core.project import Project

logger = logging.getLogger("ChunkerService")


class ChunkerService:
    """Service wrapper for smart audio chunking."""

    def __init__(self, max_size_mb: float = 19.5):
        self.max_size_mb = max_size_mb

    def process(self, project: Project) -> Optional[Path]:
        """Chunk the project's audio file if needed."""
        audio_path = project.raw_audio_path
        if not audio_path.exists():
            logger.error("Audio file does not exist: %s", audio_path)
            return None

        chunker = SmartAudioChunker(project_id=project.project_id)
        output_dir = chunker.process(audio_path)
        return output_dir
