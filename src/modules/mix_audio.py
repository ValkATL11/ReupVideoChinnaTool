#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Audio Mixer Module

Mixes two audio files (non-vocal background and dubbed voice) using FFmpeg.
Both tracks are played simultaneously from timestamp 0. The output duration
is the length of the longer track. Volume levels are configurable and
clipping is avoided via FFmpeg's amix normalization.

Input files:
    separated_audios/{PROJECT_ID}_Nvocal.mp3
    dubbing/{PROJECT_ID}/{PROJECT_ID}_0Full.mp3

Output file:
    mixed_audios/{PROJECT_ID}_Mixed.mp3
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Module-level logger
logger = logging.getLogger(__name__)


class AudioMixerError(Exception):
    """Base exception for audio mixer errors."""
    pass


class AudioMixer:
    """
    Mixes background audio (non-vocal) and dubbed voice into a single MP3.

    Attributes:
        voice_volume (float): Volume multiplier for the dubbing track (0.0 - 2.0).
        background_volume (float): Volume multiplier for the background track (0.0 - 2.0).
        ffmpeg_path (str): Path to the FFmpeg executable (auto-detected if None).
        output_bitrate (str): Bitrate for output MP3 (e.g., "192k").
    """

    def __init__(
        self,
        voice_volume: float = 1.0,
        background_volume: float = 0.8,
        ffmpeg_path: Optional[str] = None,
        output_bitrate: str = "192k",
    ):
        """
        Initialize the mixer with volume settings.

        Args:
            voice_volume: Volume gain for the dubbing track.
            background_volume: Volume gain for the background (music/SFX) track.
            ffmpeg_path: Explicit path to ffmpeg binary. If None, search PATH.
            output_bitrate: Bitrate for the output MP3 (e.g., "128k", "192k").
        """
        self.voice_volume = voice_volume
        self.background_volume = background_volume
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self.output_bitrate = output_bitrate

    def _check_ffmpeg(self) -> None:
        """Verify that FFmpeg is installed and accessible."""
        try:
            subprocess.run(
                [self.ffmpeg_path, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            raise AudioMixerError(
                f"FFmpeg not found or not executable: {self.ffmpeg_path}"
            ) from e

    def _validate_files(self, bg_path: Path, voice_path: Path) -> None:
        """Ensure both input files exist and are readable."""
        if not bg_path.is_file():
            raise FileNotFoundError(f"Background file not found: {bg_path}")
        if not voice_path.is_file():
            raise FileNotFoundError(f"Dubbing file not found: {voice_path}")

    def mix(self, project_id: str) -> Path:
        """
        Mix the two audio files for the given project ID.

        Args:
            project_id: Unique project identifier (e.g., "PRJ-260729-37TG").

        Returns:
            Path to the generated mixed audio file.

        Raises:
            AudioMixerError: If FFmpeg is missing, inputs are invalid,
                             or mixing fails.
            FileNotFoundError: If an input file does not exist.
        """
        # Build input paths
        bg_path = Path(f"separated_audios/{project_id}_Nvocal.mp3")
        voice_path = Path(f"dubbing/{project_id}/{project_id}_0Full.mp3")
        out_dir = Path("mixed_audios")
        out_path = out_dir / f"{project_id}_Mixed.mp3"

        logger.info("Starting mix for project: %s", project_id)
        logger.info("Background (non-vocal): %s", bg_path)
        logger.info("Dubbing (voice): %s", voice_path)
        logger.info("Output: %s", out_path)

        # Validate environment and inputs
        self._check_ffmpeg()
        self._validate_files(bg_path, voice_path)

        # Create output directory if needed
        out_dir.mkdir(exist_ok=True, parents=True)

        # Build FFmpeg command
        # We apply volume filters to each input, then mix with longest duration,
        # and finally normalize to avoid clipping.
        filter_complex = (
            f"[0:a]volume={self.background_volume}[bg]; "
            f"[1:a]volume={self.voice_volume}[voice]; "
            f"[bg][voice]amix=inputs=2:duration=longest:normalize=1"
        )

        cmd = [
            self.ffmpeg_path,
            "-i", str(bg_path),
            "-i", str(voice_path),
            "-filter_complex", filter_complex,
            "-c:a", "libmp3lame",
            "-b:a", self.output_bitrate,
            "-y",  # overwrite output
            str(out_path),
        ]

        logger.info("Running FFmpeg command: %s", " ".join(cmd))

        try:
            # Run FFmpeg, capturing stderr for debugging
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            raise AudioMixerError(f"Failed to execute FFmpeg: {e}") from e

        if result.returncode != 0:
            logger.error("FFmpeg returned error code %d", result.returncode)
            logger.error("FFmpeg stderr:\n%s", result.stderr)
            raise AudioMixerError(
                f"FFmpeg mixing failed (return code {result.returncode}). "
                "See logs for details."
            )

        # Verify output
        if not out_path.is_file():
            raise AudioMixerError(f"Output file not created: {out_path}")
        if out_path.stat().st_size == 0:
            raise AudioMixerError(f"Output file is empty: {out_path}")

        # Log success with file info
        file_size = out_path.stat().st_size
        logger.info("Mix completed successfully")
        logger.info("Output file: %s (size: %.2f MB)", out_path, file_size / (1024 * 1024))

        # Optionally, we could get duration via ffprobe, but not required.
        return out_path


# Optional: convenience function for direct usage without class instantiation
def mix_audio(
    project_id: str,
    voice_volume: float = 1.0,
    background_volume: float = 0.8,
    ffmpeg_path: Optional[str] = None,
) -> Path:
    """
    Convenience function to mix audio for a project.

    Args:
        project_id: Project identifier.
        voice_volume: Volume multiplier for voice track.
        background_volume: Volume multiplier for background track.
        ffmpeg_path: Optional path to ffmpeg.

    Returns:
        Path to the mixed output file.
    """
    mixer = AudioMixer(
        voice_volume=voice_volume,
        background_volume=background_volume,
        ffmpeg_path=ffmpeg_path,
    )
    return mixer.mix(project_id)


if __name__ == "__main__":
    # Example usage (standalone testing)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    try:
        # Replace with a valid project ID for testing
        project = "PRJ-260729-37TG"
        output = mix_audio(project)
        print(f"Mixed audio saved to: {output}")
    except Exception as e:
        logger.exception("Mix failed")
        sys.exit(1)