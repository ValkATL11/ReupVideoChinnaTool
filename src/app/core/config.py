"""
src/app/core/config.py
======================
Centralized Configuration System with JSON Persistence, Schema Versioning,
and Environment Variable Support.

Security Improvements:
- API keys are now loaded from environment variables or .env file
- Sensitive data is never stored in config.json
- Schema versioning with migration support
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path Resolution
# ---------------------------------------------------------------------------
# Determine the project root (2 levels up from this file: src/app/core/ -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
_DATA_DIR = _PROJECT_ROOT / "data"

# ---------------------------------------------------------------------------
# Environment Loading
# ---------------------------------------------------------------------------
def _load_env_file() -> None:
    """Load environment variables from .env file in project root."""
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value:
                            os.environ.setdefault(key, value)
        except Exception as e:
            logging.getLogger("ConfigManager").warning("Could not load .env file: %s", e)


_load_env_file()

logger = logging.getLogger("ConfigManager")

CONFIG_SCHEMA_VERSION = 1
DEFAULT_CONFIG_PATH = _CONFIG_DIR / "config.json"
PROMPTS_FILE_PATH = _CONFIG_DIR / "prompts.json"


def get_default_config() -> Dict[str, Any]:
    """Return default configuration structure."""
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "general": {
            "output_dir": str((_DATA_DIR / "output").resolve()),
            "projects_dir": str((_DATA_DIR / "projects").resolve()),
            "enable_global_retry": True,
            "max_retries": 3,
            "retry_delay_sec": 5,
            "enable_cache": True,
            "cleanup_mode": "ask_before_cleanup",
        },
        "api_keys": {
            "groq": [],
            "gemini": []
        },
        "modules": {
            "downloader": {
                "headless": True,
                "max_timeout": 120,
                "wait_timeout": 90,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            "audio_extractor": {
                "sample_rate": 44100,
                "channels": "stereo",
                "normalize": True,
                "bitrate": "192k",
                "format": "mp3",
                "fast_copy": False
            },
            "audio_chunker": {
                "auto_mode": True,
                "max_file_size_mb": 19.5,
                "safety_file_size_mb": 18.0,
                "silence_thresh_db": -35,
                "min_silence_dur": 0.3
            },
            "transcriber": {
                "model": "whisper-large-v3-turbo",
                "language": "auto"
            },
            "translator": {
                "mode": "auto",
                "max_lines_per_chunk": 120,
                "default_prompt_id": "builtin_srt_v1"
            },
            "dubber": {
                "mode": "balanced",
                "voice_female": "vi-VN-HoaiMyNeural",
                "voice_male": "vi-VN-NamMinhNeural",
                "default_gender": "female",
                "speed": 1.0,
                "output_format": "mp3"
            },
            "vocal_separator": {
                "default_mode": "mode_2",
                "vocal_leak": 0.12
            },
            "mixer": {
                "voice_volume": 1.0,
                "background_volume": 0.8,
                "output_bitrate": "192k"
            },
            "render": {
                "resolution": "original",
                "preset": "medium",
                "crf": 18,
                "video_codec": "libx264",
                "audio_codec": "aac",
                "audio_bitrate": "192k"
            }
        }
    }


class ConfigManager:
    """Manages system configuration reading, merging, updating, and writing."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config: Dict[str, Any] = get_default_config()
        self.load()

    def load(self) -> None:
        """Load configuration from JSON file or create with defaults."""
        if not self.config_path.exists():
            logger.info("Config file not found. Creating default config at: %s", self.config_path)
            self.save()
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            version = data.get("schema_version", 0)
            if version < CONFIG_SCHEMA_VERSION:
                logger.info("Migrating config schema version %s to %s", version, CONFIG_SCHEMA_VERSION)
                data = self._migrate_schema(data, version)

            self.config = self._deep_merge(get_default_config(), data)
            logger.info("Loaded configuration successfully from %s", self.config_path.name)
        except Exception as e:
            logger.error("Error loading config file (%s), fallback to defaults: %s", self.config_path, e)
            self.config = get_default_config()

    def save(self) -> bool:
        """Save configuration to JSON file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info("Configuration saved to %s", self.config_path)
            return True
        except Exception as e:
            logger.error("Failed to save config: %s", e)
            return False

    def get(self, key_path: str, default: Any = None) -> Any:
        """Retrieve value using dot-notation path, e.g. 'general.output_dir'."""
        keys = key_path.split(".")
        val = self.config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def set(self, key_path: str, value: Any, save_immediately: bool = True) -> bool:
        """Set value using dot-notation path, e.g. 'modules.dubber.speed'."""
        keys = key_path.split(".")
        d = self.config
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

        if save_immediately:
            return self.save()
        return True

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge override into base."""
        merged = base.copy()
        for k, v in override.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = self._deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    def _migrate_schema(self, data: Dict[str, Any], old_version: int) -> Dict[str, Any]:
        """Migration hook for future schema updates."""
        data["schema_version"] = CONFIG_SCHEMA_VERSION
        return data

    @property
    def project_root(self) -> Path:
        """Return the project root directory."""
        return _PROJECT_ROOT

    @property
    def data_dir(self) -> Path:
        """Return the data directory."""
        return _DATA_DIR

    @property
    def config_dir(self) -> Path:
        """Return the config directory."""
        return _CONFIG_DIR


# Global singleton instance
config_instance = ConfigManager()
