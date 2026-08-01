"""
app/editor/frame_extractor.py
==============================
Lightweight FFmpeg Frame Capture Engine with LRU Cache & Debouncing.
"""

import logging
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Dict, Optional

logger = logging.getLogger("FrameExtractor")


class FrameExtractor:
    """Extracts single video frames as image files without loading whole video into memory."""

    def __init__(self, cache_size: int = 20):
        self.cache_size = cache_size
        self.frame_cache: Dict[str, Path] = {}
        self.last_extract_time = 0.0
        self.debounce_sec = 0.15  # 150ms debounce threshold for timeline seeking

    def get_frame(self, video_path: Path, timestamp_sec: float, force: bool = False) -> Optional[Path]:
        """
        Extract frame at timestamp_sec (Fast Seeking).
        Returns Path to extracted temp image file.
        """
        if not video_path.exists():
            logger.error("Video path for frame capture does not exist: %s", video_path)
            return None

        # Check cache key
        cache_key = f"{video_path.name}_{int(timestamp_sec * 10)}"
        if not force and cache_key in self.frame_cache:
            cached_file = self.frame_cache[cache_key]
            if cached_file.exists():
                return cached_file

        # Apply debouncing throttling during rapid scrub
        now = time.time()
        if not force and (now - self.last_extract_time) < self.debounce_sec:
            # Skip rapid intermediate seeks
            return None

        self.last_extract_time = now

        # Output to temp file
        temp_dir = Path(tempfile.gettempdir()) / "reuptool_frames"
        temp_dir.mkdir(parents=True, exist_ok=True)
        out_image = temp_dir / f"frame_{cache_key}.jpg"

        # FFmpeg command using fast input seeking (-ss before -i)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", f"{timestamp_sec:.3f}",
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "3",  # High quality JPEG
            "-y",
            str(out_image)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if res.returncode == 0 and out_image.exists() and out_image.stat().st_size > 0:
                # Add to cache
                if len(self.frame_cache) >= self.cache_size:
                    # Evict oldest entry
                    oldest = next(iter(self.frame_cache))
                    del self.frame_cache[oldest]
                self.frame_cache[cache_key] = out_image
                return out_image
        except Exception as e:
            logger.error("Frame extraction error at %.2fs: %s", timestamp_sec, e)

        return None
