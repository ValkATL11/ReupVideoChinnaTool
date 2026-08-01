"""
src/app/services/dubber.py
===========================
Wrapper service around dubber.py for TTS dubbing.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from modules.dubber import run_smart_dubber, UserMode
from app.core.project import Project

logger = logging.getLogger("DubberService")


class DubberService:
    """Service wrapper for Smart Dubber Pro."""

    def __init__(self, voice: str = "vi-VN-HoaiMyNeural", mode: str = "balanced", speed: float = 1.0, output_format: str = "mp3"):
        self.voice = voice
        self.mode_str = mode
        self.speed = speed
        self.output_format = output_format

        mode_map = {
            "time_first": UserMode.TIME_FIRST,
            "quality_first": UserMode.QUALITY_FIRST,
            "balanced": UserMode.BALANCED
        }
        self.user_mode = mode_map.get(mode.lower(), UserMode.BALANCED)

    def process(self, project: Project) -> Optional[Path]:
        """Synthesize TTS audio from translated SRT file."""
        srt_file = project.translated_srt_path
        if not srt_file.exists():
            logger.error("Translated SRT file does not exist: %s", srt_file)
            return None

        project.ensure_directories()
        base_dubout_dir = project.dubbing_dir.parent

        import modules.dubber as dubber_module
        dubber_module.VOICE_DEFAULT = self.voice

        res = asyncio.run(run_smart_dubber(
            srt_file=srt_file,
            base_dubout_dir=base_dubout_dir,
            mode=self.user_mode,
            output_format=self.output_format
        ))
        return res
