"""
src/app/services/mixer.py
==========================
Wrapper service around mix_audio.py for audio mixing.
"""

import logging
from pathlib import Path
from typing import Optional
import subprocess
import shutil

from app.core.project import Project

logger = logging.getLogger("MixerService")


class MixerService:
    """Service wrapper for mixing dubbed voice with background audio."""

    def __init__(self, voice_volume: float = 1.0, background_volume: float = 0.8, output_bitrate: str = "192k"):
        self.voice_volume = voice_volume
        self.background_volume = background_volume
        self.output_bitrate = output_bitrate

    def process(self, project: Project) -> Optional[Path]:
        """Mix the dubbed voice track with the non-vocal background track."""
        bg_path = project.nonvocal_audio_path
        voice_path = project.dubbed_master_path
        output_path = project.mixed_audio_path

        if not bg_path.exists():
            logger.error("Background audio not found: %s", bg_path)
            return None
        if not voice_path.exists():
            logger.error("Dubbed voice not found: %s", voice_path)
            return None

        project.ensure_directories()

        try:
            filter_complex = (
                f"[0:a]volume={self.background_volume}[bg]; "
                f"[1:a]volume={self.voice_volume}[voice]; "
                f"[bg][voice]amix=inputs=2:duration=longest:normalize=1"
            )

            cmd = [
                "ffmpeg", "-y",
                "-i", str(bg_path),
                "-i", str(voice_path),
                "-filter_complex", filter_complex,
                "-c:a", "libmp3lame",
                "-b:a", self.output_bitrate,
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("FFmpeg mixing failed: %s", result.stderr[-200:])
                return None

            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error("Output file not created or empty")
                return None

            logger.info("Audio mixing completed: %s", output_path.name)
            return output_path

        except Exception as e:
            logger.error("Audio mixing failed: %s", e)
            return None
