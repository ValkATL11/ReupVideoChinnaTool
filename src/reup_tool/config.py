"""
config.py
---------
Central configuration loader for the ReupVideoChinnaTool project.

Responsibilities:
  - Load environment variables from the project-root .env file via python-dotenv.
  - Parse config/settings.json and expose typed configuration objects.
  - Auto-create all required asset directories on first import.
  - Validate mandatory API keys and raise an explicit error when missing.
  - After loading settings, overlay config/subtitle_style.json (written by the
    Subtitle Editor) so that the video merger always uses the user's chosen style.

All modules in src/reup_tool/ must import configuration exclusively through:
    from reup_tool.config import config
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project root resolution (two levels up from this file: src/reup_tool/ -> /)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env from project root before any environment variable is read
load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Color conversion helpers
# ---------------------------------------------------------------------------

def _hex_to_ass(hex_color: str, alpha: int = 0) -> str:
    """
    Convert an #RRGGBB hex string to ASS/SSA &HAABBGGRR& format.

    ASS stores colour channels in reverse (BGR) and the alpha byte is placed
    first (0 = fully opaque, 255 = fully transparent).

    Args:
        hex_color: A colour string like "#FFFF00" or "FFFF00".
        alpha:     0–255 where 0 is fully opaque (ASS convention).

    Returns:
        A valid ASS colour tag such as "&H0000FFFF&".
    """
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return "&H00FFFFFF&"          # fallback: white, fully opaque
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        alpha = max(0, min(255, alpha))
        return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}&"
    except ValueError:
        return "&H00FFFFFF&"


def _text_align_to_ass(alignment) -> int:
    """
    Convert a text-alignment keyword to its ASS numpad value.

    ASS numpad layout (bottom row = 1/2/3):
        7 8 9  ← top
        4 5 6  ← middle
        1 2 3  ← bottom

    We map the common subtitle positions:
        "left"   → 1 (bottom-left)
        "center" → 2 (bottom-center)   ← default
        "right"  → 3 (bottom-right)
    """
    mapping = {"left": 1, "center": 2, "right": 3}
    return mapping.get(str(alignment).lower().strip(), 2)


# ---------------------------------------------------------------------------
# Sub-configuration dataclasses
# ---------------------------------------------------------------------------

class PathsConfig:
    """
    Resolves all asset directory paths relative to PROJECT_ROOT.
    Directories are created automatically on first access if they do not exist.
    """

    def __init__(self, root: Path):
        self._root = root

    def _ensure(self, rel_path: str) -> Path:
        path = (self._root / rel_path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def video_dir(self) -> Path:
        """Input video directory: assets/original_video/"""
        return self._ensure("assets/original_video")

    @property
    def srt_dir(self) -> Path:
        """Raw SRT output from transcription: assets/original_srt/"""
        return self._ensure("assets/original_srt")

    @property
    def translated_dir(self) -> Path:
        """Vietnamese-translated SRT files: assets/translated_srt/"""
        return self._ensure("assets/translated_srt")

    @property
    def subtitle_text_dir(self) -> Path:
        """Plain-text subtitle lines for TTS: assets/subtitle_text/"""
        return self._ensure("assets/subtitle_text")

    @property
    def audio_dir(self) -> Path:
        """Extracted MP3 audio files: assets/original_audio/"""
        return self._ensure("assets/original_audio")

    @property
    def dubbing_dir(self) -> Path:
        """TTS-generated dubbing audio: assets/dubbing/"""
        return self._ensure("assets/dubbing")

    @property
    def output_dir(self) -> Path:
        """Final rendered video files: assets/output/"""
        return self._ensure("assets/output")

    @property
    def prompt_dir(self) -> Path:
        """Prompt text files: prompts/"""
        return self._ensure("prompts")


class DownloaderConfig:
    """Configuration for the Selenium-based video downloader."""

    def __init__(self, data: dict):
        self.headless: bool = data.get("headless", True)
        self.user_agent: str = data.get("user_agent", "")


class AudioConverterConfig:
    """Configuration for the Convertio MP4-to-MP3 converter."""

    def __init__(self, data: dict):
        self.headless: bool = data.get("headless", True)
        self.vbr_quality: int = int(data.get("vbr_quality", 5))


class TranscriberConfig:
    """Configuration for the Groq Whisper transcription module."""

    def __init__(self, data: dict):
        self.language: str = data.get("language", "auto")
        self.model: str = data.get("model", "whisper-large-v3-turbo")


class TranslatorConfig:
    """
    Configuration for the subtitle translation module.

    The prompt text is read lazily from the file pointed to by `prompt_file`.
    Supported engines: "gemini_api" | "gemini_selenium".
    """

    def __init__(self, data: dict, root: Path):
        self._root = root
        self.engine: str = data.get("engine", "gemini_selenium")
        self.headless: bool = data.get("headless", True)
        self.user_agent: str = data.get("user_agent", "")
        self.prompt_file: Path = (
            self._root / data.get("prompt_file", "prompts/translate_prompt.txt")
        ).resolve()

    @property
    def prompt_text(self) -> str:
        """Return the full prompt string from disk, or an empty string if the file is missing."""
        if self.prompt_file.exists():
            return self.prompt_file.read_text(encoding="utf-8")
        return ""


class DubberConfig:
    """Configuration for the Edge-TTS text-to-speech dubbing module."""

    def __init__(self, data: dict):
        self.voice_male: str = data.get("voice_male", "vi-VN-NamMinhNeural")
        self.voice_female: str = data.get("voice_female", "vi-VN-HoaiMyNeural")
        self._voice_mode: str = data.get("voice", "female")
        self.speed: float = float(data.get("speed", 1.3))
        self.output_format: str = data.get(
            "output_format", "audio-24khz-48kbitrate-mono-mp3"
        )

    @property
    def voice(self) -> str:
        """Return the active voice name based on the configured gender mode."""
        return self.voice_male if self._voice_mode == "male" else self.voice_female


class SubtitleStyle:
    """ASS/SSA subtitle styling parameters forwarded to FFmpeg."""

    def __init__(self, data: dict):
        self.font_name: str = data.get("font_name", "Cambria Bold")
        self.font_size: int = int(data.get("font_size", 28))
        self.primary_color: str = data.get("primary_color", "&H0005C8F7&")
        self.secondary_color: str = data.get("secondary_color", "&H00FFFFFF&")
        self.back_color: str = data.get("back_color", "&H80000000&")
        self.border_style: int = int(data.get("border_style", 3))
        self.shadow: int = int(data.get("shadow", 0))
        # Extended style fields — populated at runtime by _apply_subtitle_style
        self.outline_color: str = data.get("outline_color", "&H00000000&")
        self.outline_width: int = int(data.get("outline_width", 2))
        self.bold: int = -1 if data.get("bold", True) else 0    # ASS: -1=bold, 0=normal
        self.italic: int = -1 if data.get("italic", False) else 0
        self.underline: int = -1 if data.get("underline", False) else 0
        self.alignment: int = int(data.get("alignment", 2))      # ASS numpad (2=bottom-center)
        self.margin_v: int = int(data.get("margin_v", 20))
        self.margin_l: int = int(data.get("margin_l", 10))
        self.margin_r: int = int(data.get("margin_r", 10))
        self.pos_x_pct: float = float(data.get("pos_x_pct", 50.0))
        self.pos_y_pct: float = float(data.get("pos_y_pct", 85.0))


class VideoEncodeConfig:
    """FFmpeg video stream encoding parameters."""

    def __init__(self, data: dict):
        self.codec: str = data.get("codec", "libx264")
        self.pix_fmt: str = data.get("pix_fmt", "yuv420p")
        self.frame_rate: int = int(data.get("frame_rate", 25))
        self.gop_size: int = int(data.get("gop_size", 160))
        self.bitrate: str = data.get("bitrate", "4000k")
        self.profile: str = data.get("profile", "main")
        self.level: str = data.get("level", "3.1")
        self.preset: str = data.get("preset", "superfast")


class AudioEncodeConfig:
    """FFmpeg audio stream encoding parameters."""

    def __init__(self, data: dict):
        self.codec: str = data.get("codec", "libmp3lame")
        self.bitrate: str = data.get("bitrate", "128k")
        self.sample_rate: int = int(data.get("sample_rate", 44100))


class SuffixConfig:
    """File extension and suffix conventions used across all modules."""

    def __init__(self, data: dict):
        self.srt_suffix: str = data.get("srt_suffix", "_vi")
        self.video_ext: str = data.get("video_ext", ".mp4")
        self.srt_ext: str = data.get("srt_ext", ".srt")
        self.audio_ext: str = data.get("audio_ext", ".mp3")


class VideoMergerConfig:
    """Full configuration for the video/audio/subtitle merging module."""

    def __init__(self, data: dict):
        self.original_volume: float = float(data.get("original_volume", 0.3))
        self.new_volume: float = float(data.get("new_volume", 0.9))
        self.fade_in_ms: int = int(data.get("fade_in_ms", 30))
        self.fade_out_ms: int = int(data.get("fade_out_ms", 30))
        self.subtitle = SubtitleStyle(data.get("subtitle", {}))
        self.video = VideoEncodeConfig(data.get("video", {}))
        self.audio = AudioEncodeConfig(data.get("audio", {}))
        self.suffix = SuffixConfig(data.get("suffix", {}))


# ---------------------------------------------------------------------------
# Main Config singleton
# ---------------------------------------------------------------------------

class Config:
    """
    Singleton configuration object loaded once at module import time.

    Raises:
        FileNotFoundError: if config/settings.json is not found.
        EnvironmentError: if GROQ_API_KEY is absent from the environment.
    """

    def __init__(self):
        settings_path = PROJECT_ROOT / "config" / "settings.json"
        if not settings_path.exists():
            raise FileNotFoundError(
                f"settings.json not found at: {settings_path}\n"
                "Please create config/settings.json before running the application."
            )

        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # --- Path configuration ---
        self.paths = PathsConfig(PROJECT_ROOT)

        # --- Module configurations ---
        self.downloader = DownloaderConfig(data.get("downloader", {}))
        self.audio_converter = AudioConverterConfig(data.get("audio_converter", {}))
        self.transcriber = TranscriberConfig(data.get("transcriber", {}))
        self.translator = TranslatorConfig(data.get("translator", {}), PROJECT_ROOT)
        self.dubber = DubberConfig(data.get("dubber", {}))
        self.video_merger = VideoMergerConfig(data.get("video_merger", {}))

        # --- Overlay subtitle_style.json written by the Subtitle Editor ---
        # This is the fix for the preview↔export mismatch: the editor writes
        # config/subtitle_style.json and the merger now reads it here, converting
        # the editor's #RRGGBB colours and text-alignment keywords into ASS format.
        self._apply_subtitle_style_file()

        # --- Logging level ---
        self.log_level: str = data.get("logging", {}).get("level", "INFO")

        # --- API keys (environment-only, never stored in settings.json) ---
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()

        raw_gemini = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_api_key: str = raw_gemini
        self.gemini_api_keys: list[str] = (
            [k.strip() for k in raw_gemini.split(",") if k.strip()]
            if raw_gemini
            else []
        )

        # Validate mandatory keys at startup rather than silently failing later
        if not self.groq_api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set.\n"
                "Add it to your .env file:  GROQ_API_KEY=gsk_..."
            )

    # ------------------------------------------------------------------ #
    #  Subtitle style overlay                                              #
    # ------------------------------------------------------------------ #

    def _apply_subtitle_style_file(self) -> None:
        """
        Read config/subtitle_style.json (written by SubtitleEditor) and overlay
        its values on top of self.video_merger.subtitle.

        The style file uses the editor's native format:
          - colours as #RRGGBB hex strings
          - alignment as "left" | "center" | "right"
          - shadow/background as separate enable + parameter fields

        This method converts all of those to ASS/SSA format so that
        srt_to_ass() can use them directly without any further translation.

        If the file does not exist, or contains invalid JSON, the method
        returns silently and the settings.json defaults are preserved.
        """
        style_path = PROJECT_ROOT / "config" / "subtitle_style.json"
        if not style_path.exists():
            return

        try:
            style: dict = json.loads(style_path.read_text(encoding="utf-8"))
        except Exception:
            return  # Corrupt JSON — keep settings.json defaults

        sub = self.video_merger.subtitle

        # ── Font ──────────────────────────────────────────────────────────
        if "font_name" in style:
            sub.font_name = str(style["font_name"])
        if "font_size" in style:
            sub.font_size = max(8, int(float(style["font_size"])))

        # ── Text colour ───────────────────────────────────────────────────
        if "primary_color" in style:
            opacity = max(0, min(255, int(style.get("opacity", 255))))
            # ASS alpha: 0 = fully opaque, 255 = fully transparent (inverted)
            alpha = 255 - opacity
            sub.primary_color = _hex_to_ass(style["primary_color"], alpha)

        # ── Outline ───────────────────────────────────────────────────────
        if "outline_color" in style:
            sub.outline_color = _hex_to_ass(style["outline_color"])
        if "outline_width" in style:
            sub.outline_width = max(0, int(float(style["outline_width"])))

        # ── Shadow ────────────────────────────────────────────────────────
        # The editor stores shadow as enable + offset_x/y + colour.
        # ASS stores it as a single scalar "Shadow" distance and uses
        # BackColour for the drop-shadow colour.
        shadow_enable = bool(style.get("shadow_enable", False))
        if shadow_enable:
            sx = int(style.get("shadow_offset_x", 2))
            sy = int(style.get("shadow_offset_y", 2))
            # Use the larger of the two offsets as the ASS scalar distance
            sub.shadow = max(1, max(abs(sx), abs(sy)))
            if "shadow_color" in style:
                sub.back_color = _hex_to_ass(style["shadow_color"])
        else:
            sub.shadow = 0

        # ── Background box ────────────────────────────────────────────────
        # If a background is enabled it overrides border_style to 4 (opaque
        # box) and uses back_color with the configured opacity.
        # This takes priority over shadow's back_color assignment above.
        bg_enable = bool(style.get("background_enable", False))
        if bg_enable:
            bg_alpha = 255 - max(0, min(255, int(style.get("background_opacity", 128))))
            sub.back_color = _hex_to_ass(
                style.get("background_color", "#000000"), bg_alpha
            )
            sub.border_style = 4   # ASS: draw an opaque box behind the text

        # ── Bold / Italic / Underline ──────────────────────────────────────
        # ASS convention: -1 = on, 0 = off
        if "bold" in style:
            sub.bold = -1 if bool(style["bold"]) else 0
        if "italic" in style:
            sub.italic = -1 if bool(style["italic"]) else 0
        if "underline" in style:
            sub.underline = -1 if bool(style["underline"]) else 0

        # ── Alignment ─────────────────────────────────────────────────────
        if "alignment" in style:
            sub.alignment = _text_align_to_ass(style["alignment"])

        # ── Margins ───────────────────────────────────────────────────────
        if "margin_v" in style:
            sub.margin_v = max(0, int(float(style["margin_v"])))
        if "margin_h" in style:
            mh = max(0, int(float(style["margin_h"])))
            sub.margin_l = mh
            sub.margin_r = mh

        # ── Position (percentage, passed through unchanged) ───────────────
        if "pos_x_pct" in style:
            sub.pos_x_pct = float(style["pos_x_pct"])
        if "pos_y_pct" in style:
            sub.pos_y_pct = float(style["pos_y_pct"])


# Module-level singleton — imported by all other modules as `from reup_tool.config import config`
config = Config()
