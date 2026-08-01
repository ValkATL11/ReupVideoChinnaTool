"""
src/app/services/extractor.py
==============================
Wrapper service around audio_extractor.py for audio extraction from video.
"""

import logging
from pathlib import Path
from typing import Optional

from modules.audio_extractor import FFmpegExtractor
from app.core.project import Project

logger = logging.getLogger("ExtractorService")


class ExtractorService:
    """Service wrapper for audio extraction from video."""

    def __init__(
        self,
        sample_rate: int = 44100,
        channels: str = "stereo",
        normalize: bool = True,
        bitrate: str = "192k",
        fast_copy: bool = False
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.normalize = normalize
        self.bitrate = bitrate
        self.fast_copy = fast_copy

    def process(self, project: Project) -> Optional[Path]:
        """Extract audio from the project's raw video file."""
        video_path = project.raw_video_path
        if not video_path.exists():
            logger.error("Raw video file does not exist: %s", video_path)
            return None

        project.ensure_directories()

        extractor = FFmpegExtractor(
            output_dir=project.audio_dir,
            sample_rate=self.sample_rate,
            channels=self.channels,
            normalize=self.normalize,
            bitrate=self.bitrate,
            fast_copy=self.fast_copy
        )
        extractor.project_manager._project_id = project.project_id

        output_path = extractor.extract(video_path)
        return output_path
