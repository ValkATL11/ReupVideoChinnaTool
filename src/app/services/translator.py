"""
src/app/services/translator.py
================================
Wrapper service around translator.py with Gemini Key Pool & Prompt Engine integration.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from modules.translator import GeminiApiTranslator, GeminiSeleniumTranslator, get_output_path
from app.core.key_manager import key_manager_instance
from app.core.prompt_engine import prompt_library_instance
from app.core.project import Project

logger = logging.getLogger("TranslatorService")


class TranslatorService:
    """Service wrapper for SRT translation."""

    def __init__(self, mode: str = "auto", prompt_id: Optional[str] = None):
        self.mode = mode
        self.prompt_id = prompt_id
        self.resolved_prompt_id: Optional[str] = None

    def process(
        self,
        project: Project,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Optional[Path]:
        """Translate project refined SRT file to Vietnamese SRT file."""
        input_srt = project.refined_srt_path
        if not input_srt.exists():
            logger.error("Refined SRT file does not exist: %s", input_srt)
            return None

        project.ensure_directories()
        translated_dir = project.translated_dir

        prompt_item = prompt_library_instance.get_prompt(self.prompt_id) if self.prompt_id else prompt_library_instance.get_active_prompt()
        if prompt_item is None:
            prompt_item = prompt_library_instance.get_active_prompt()
        prompt_text = prompt_item.get("content", "") if prompt_item else ""
        self.resolved_prompt_id = prompt_item.get("id") if prompt_item else None

        import modules.translator as translator_module
        if prompt_text:
            translator_module.PROMPT_TEXT = prompt_text

        gemini_key = key_manager_instance.gemini.get_active_key()
        active_mode = self.mode.lower()

        if active_mode == "auto":
            engine = "gemini_api" if gemini_key else "selenium"
        elif active_mode == "gemini_api":
            engine = "gemini_api"
        else:
            engine = "selenium"

        if engine == "gemini_api" and not gemini_key:
            logger.warning("No Gemini API Key available. Falling back to Selenium mode.")
            engine = "selenium"

        if engine == "gemini_api":
            logger.info("Using Gemini API Translator with key pool...")
            translator_module.GEMINI_API_KEYS = [k["key"] for k in key_manager_instance.gemini.keys if k.get("enabled", True)]
            trans_inst = GeminiApiTranslator(srt_dir=project.transcribed_dir, translated_dir=translated_dir)
            out_path = trans_inst.translate_file(input_srt, progress_callback=progress_callback)
            return out_path
        else:
            logger.info("Using Selenium Gemini Translator...")
            trans_inst = GeminiSeleniumTranslator(srt_dir=project.transcribed_dir, translated_dir=translated_dir)
            out_path = trans_inst.translate_file(input_srt, progress_callback=progress_callback)
            return out_path
