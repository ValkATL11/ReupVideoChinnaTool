# src/reup_tool/dubber.py
import os
import asyncio
import edge_tts
from pathlib import Path
import logging
from typing import Optional, List, Callable

from reup_tool.config import config

logger = logging.getLogger(__name__)


class EdgeTTSConverter:
    def __init__(self, voice: Optional[str] = None, speed: Optional[float] = None):
        self.voice = voice or config.dubber.voice
        self.speed = speed if speed is not None else config.dubber.speed
        self.output_dir = config.paths.dubbing_dir

    async def text_to_speech(self, text: str, output_path: str) -> bool:
        try:
            rate = f"{int((self.speed - 1) * 100):+d}%"
            communicate = edge_tts.Communicate(text, self.voice, rate=rate)
            await communicate.save(output_path)
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi TTS: {e}")
            return False

    async def process_text_file(
        self,
        text_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[str]:
        try:
            with open(text_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

            if not lines:
                return []

            base_name = text_path.stem.replace('_subtitle', '')
            video_dir = self.output_dir / base_name
            video_dir.mkdir(parents=True, exist_ok=True)

            downloaded_files = []
            total_lines = len(lines)

            for i, line in enumerate(lines, 1):
                filename = f"dong_{i:03d}.mp3"
                output_path = video_dir / filename

                if progress_callback:
                    progress_callback(i, total_lines, f"TTS {base_name[:12]}: Dòng {i}/{total_lines}")

                if output_path.exists() and output_path.stat().st_size > 1024:
                    downloaded_files.append(str(output_path))
                    continue

                success = await self.text_to_speech(line, str(output_path))
                if success:
                    downloaded_files.append(str(output_path))

            return downloaded_files

        except Exception as e:
            logger.error(f"❌ Lỗi xử lý file {text_path}: {e}")
            return []

    async def process_all_files_async(
        self,
        single_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        input_dir = config.paths.subtitle_text_dir

        if single_file:
            stem = Path(single_file).stem.replace('_subtitle', '')
            text_files = list(input_dir.glob(f"{stem}*_subtitle.txt"))
        else:
            text_files = list(input_dir.glob("*_subtitle.txt"))

        if not text_files:
            if progress_callback:
                progress_callback(1, 1, "Không có file text")
            return False

        success = 0
        for text_file in text_files:
            result = await self.process_text_file(text_file, progress_callback=progress_callback)
            if result:
                success += 1

        return (success > 0)


def process_all(
    single_file: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> bool:
    converter = EdgeTTSConverter()
    return asyncio.run(converter.process_all_files_async(single_file=single_file, progress_callback=progress_callback))
