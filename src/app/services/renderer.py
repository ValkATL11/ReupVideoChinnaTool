"""
src/app/services/renderer.py
==============================
Wrapper service around render.py for video rendering.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional
import tempfile

from app.core.project import Project

logger = logging.getLogger("RenderService")

SUBTITLE_STYLE = (
    "FontName=Arial,"
    "FontSize=20,"
    "PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,"
    "BorderStyle=1,"
    "Outline=2,"
    "Shadow=1,"
    "Alignment=2"
)


def escape_ffmpeg_filter_path(file_path: Path) -> str:
    """Escape path for FFmpeg filter syntax."""
    abs_path = str(file_path.resolve())
    clean_path = abs_path.replace("\\", "/")
    clean_path = clean_path.replace(":", "\\:")
    clean_path = clean_path.replace("'", "\\'")
    return clean_path


def get_video_duration(video_path: Path) -> float:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def validate_output(output_path: Path) -> bool:
    """Validate that the output video is valid."""
    if not output_path.exists() or output_path.stat().st_size == 0:
        return False

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type",
        "-show_entries", "format=duration",
        "-of", "json",
        str(output_path)
    ]
    try:
        import json
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        streams = [s.get("codec_type") for s in data.get("streams", [])]
        duration = float(data.get("format", {}).get("duration", 0))
        return "video" in streams and "audio" in streams and duration > 0
    except Exception:
        return False


class RenderService:
    """Service wrapper for video rendering with subtitle burning."""

    def __init__(self, preset: str = "medium", crf: int = 18, resolution: str = "original"):
        self.preset = preset
        self.crf = crf
        self.resolution = resolution

    def process(self, project: Project) -> Optional[Path]:
        """Render the final video with burned-in subtitles and mixed audio."""
        video_path = project.raw_video_path
        subtitle_path = project.translated_srt_path
        audio_path = project.mixed_audio_path
        output_path = project.final_output_path

        if not video_path.exists():
            logger.error("Video file not found: %s", video_path)
            return None
        if not subtitle_path.exists():
            logger.error("Subtitle file not found: %s", subtitle_path)
            return None
        if not audio_path.exists():
            logger.error("Mixed audio not found: %s", audio_path)
            return None

        project.ensure_directories()

        try:
            orig_duration = get_video_duration(video_path)
            if orig_duration <= 0:
                logger.error("Invalid video duration")
                return None

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_srt = Path(temp_dir) / f"{project.project_id}_clean.srt"
                with open(subtitle_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()
                with open(temp_srt, "w", encoding="utf-8") as f:
                    f.write(content)

                escaped_srt = escape_ffmpeg_filter_path(temp_srt)

                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(audio_path),
                    "-vf", f"subtitles='{escaped_srt}':force_style='{SUBTITLE_STYLE}'",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264",
                    "-preset", self.preset,
                    "-crf", str(self.crf),
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-t", str(orig_duration),
                    str(output_path)
                ]

                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error("FFmpeg rendering failed: %s", result.stderr[-500:])
                    return None

                if validate_output(output_path):
                    logger.info("Rendering completed: %s", output_path.name)
                    return output_path
                else:
                    logger.error("Output validation failed")
                    if output_path.exists():
                        output_path.unlink()
                    return None

        except Exception as e:
            logger.error("Rendering failed: %s", e)
            return None
