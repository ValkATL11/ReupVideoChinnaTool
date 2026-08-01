"""
src/app/services/separator.py
===============================
Wrapper service around vocal_separator.py for vocal separation.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from pydub import AudioSegment
from app.core.project import Project

logger = logging.getLogger("SeparatorService")


class SeparatorService:
    """Service wrapper for vocal separation using phase cancellation techniques."""

    def __init__(self, mode: str = "mode_2", vocal_leak: float = 0.12):
        self.mode = mode
        self.vocal_leak = vocal_leak

    def process(self, project: Project) -> Optional[Path]:
        """Separate vocals from the project's audio file."""
        audio_path = project.raw_audio_path
        if not audio_path.exists():
            logger.error("Audio file does not exist: %s", audio_path)
            return None

        project.ensure_directories()
        output_path = project.nonvocal_audio_path

        try:
            audio = AudioSegment.from_file(audio_path)
            sr = audio.frame_rate
            channels = audio.channels

            if channels < 2:
                logger.error("Audio must be stereo for separation")
                return None

            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            max_val = float(1 << (8 * audio.sample_width - 1))
            samples /= max_val
            samples = samples.reshape((-1, channels)).T

            if self.mode == "mode_1":
                processed = self._process_voiceover_mode(samples)
            else:
                processed = self._process_music_sfx_mode(samples, self.vocal_leak)

            int16_samples = (processed * 32767).astype(np.int16)
            interleaved = int16_samples.T.flatten()

            output_audio = AudioSegment(
                data=interleaved.tobytes(),
                sample_width=2,
                frame_rate=sr,
                channels=2
            )
            output_audio.export(output_path, format="mp3")
            logger.info("Vocal separation completed: %s", output_path.name)
            return output_path

        except Exception as e:
            logger.error("Vocal separation failed: %s", e)
            return None

    def _process_voiceover_mode(self, stereo_audio: np.ndarray) -> np.ndarray:
        """Pure Phase Cancellation mode."""
        L, R = stereo_audio[0], stereo_audio[1]
        accompaniment_mono = (L - R) * 0.5
        out_L = accompaniment_mono
        out_R = -accompaniment_mono
        return np.ascontiguousarray(np.vstack((out_L, out_R)))

    def _process_music_sfx_mode(self, stereo_audio: np.ndarray, vocal_leak: float) -> np.ndarray:
        """Multi-band Mid-Side mode."""
        from scipy import signal
        L, R = stereo_audio[0], stereo_audio[1]
        sr = 44100

        mid = (L + R) * 0.5
        side = (L - R) * 0.5

        sos_bass = signal.butter(4, 150, btype='lowpass', fs=sr, output='sos')
        mid_bass = signal.sosfilt(sos_bass, mid)

        sos_treble = signal.butter(4, 5000, btype='highpass', fs=sr, output='sos')
        mid_treble = signal.sosfilt(sos_treble, mid)

        sos_vocal = signal.butter(4, [150, 5000], btype='bandpass', fs=sr, output='sos')
        mid_vocal_reduced = signal.sosfilt(sos_vocal, mid) * vocal_leak

        mid_reconstructed = mid_bass + mid_treble + mid_vocal_reduced
        out_L = mid_reconstructed + side
        out_R = mid_reconstructed - side
        return np.ascontiguousarray(np.vstack((out_L, out_R)))
