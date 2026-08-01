"""
src/app/services/downloader.py
===============================
Wrapper service around downloads.py supporting local file copy & URL downloading.
"""

import logging
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, Optional

from modules.downloader import DownloaderConfig, VideoDownloader
from app.core.project import Project

logger = logging.getLogger("DownloaderService")


class DownloaderService:
    """Service wrapper for video downloading and local input handling."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def process(
        self,
        project: Project,
        source_input: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """Process video input: local file copy or URL download."""
        project.ensure_directories()
        source_input = source_input.strip()

        candidate = Path(source_input)
        if candidate.exists() and candidate.is_file():
            logger.info("Processing local video file: %s", candidate)
            if progress_callback:
                progress_callback(1, 2, f"Copying local video: {candidate.name}")

            target_path = project.raw_video_path
            if candidate.resolve() != target_path.resolve():
                shutil.copy2(candidate, target_path)

            if progress_callback:
                progress_callback(2, 2, "Local video file ready!")

            return {
                "success": True,
                "file_path": str(target_path.resolve()),
                "filename": target_path.name,
                "project_id": project.project_id,
                "error": None
            }

        logger.info("Processing video URL download: %s", source_input[:100])
        config = DownloaderConfig(
            headless=self.headless,
            output_dir=project.video_dir
        )
        downloader = VideoDownloader(config=config, progress_callback=progress_callback)
        downloader.project_manager._project_id = project.project_id

        res = downloader.download(source_input)
        return res
