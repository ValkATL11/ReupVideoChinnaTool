"""
src/app/core/key_manager.py
===========================
Central API Key Pool Manager (Groq & Gemini) with Auto Rotation, Cooldown,
and Health Tracking.

Security Improvements:
- API keys are loaded from environment variables (GROQ_API_KEYS, GEMINI_API_KEYS)
- Keys can be added/removed via config or environment
- Keys are masked when displayed
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional
from app.core.config import config_instance

logger = logging.getLogger("ApiKeyManager")


def mask_key(key: str) -> str:
    """Mask key string for safe UI display and logging."""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


class ApiKeyPool:
    """Pool of API keys for a specific provider (Groq / Gemini)."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.keys: List[Dict[str, Any]] = []
        self.current_index = 0
        self._load_from_env()
        self.reload()

    def _load_from_env(self) -> None:
        """Load API keys from environment variables."""
        env_key = f"{self.provider_name.upper()}_API_KEYS"
        env_value = os.environ.get(env_key, "")
        if env_value:
            env_keys = [k.strip() for k in env_value.split(",") if k.strip()]
            for i, key_str in enumerate(env_keys, 1):
                self.keys.append({
                    "id": f"{self.provider_name}_{i}",
                    "key": key_str,
                    "enabled": True,
                    "error_count": 0,
                    "cooldown_until": 0
                })
            if self.keys:
                logger.info("Loaded %d %s key(s) from environment variables", len(self.keys), self.provider_name)

    def reload(self) -> None:
        """Reload key list from Central Config."""
        raw_keys = config_instance.get(f"api_keys.{self.provider_name}", [])
        # Preserve env-loaded keys
        env_keys = [k for k in self.keys if k.get("from_env")]

        config_keys = []
        for item in raw_keys:
            if isinstance(item, dict):
                config_keys.append({
                    "id": item.get("id", f"{self.provider_name}_{len(config_keys)+1}"),
                    "key": item.get("key", "").strip(),
                    "enabled": item.get("enabled", True),
                    "error_count": item.get("error_count", 0),
                    "cooldown_until": item.get("cooldown_until", 0),
                    "from_env": False
                })
            elif isinstance(item, str) and item.strip():
                config_keys.append({
                    "id": f"{self.provider_name}_{len(config_keys)+1}",
                    "key": item.strip(),
                    "enabled": True,
                    "error_count": 0,
                    "cooldown_until": 0,
                    "from_env": False
                })

        # Merge: env keys take precedence, then config keys
        env_ids = {k["id"] for k in env_keys}
        self.keys = env_keys + [k for k in config_keys if k["id"] not in env_ids]
        self.current_index = 0

    def sync_to_config(self) -> None:
        """Save current pool back to Central Config (excluding env keys)."""
        config_keys = [k for k in self.keys if not k.get("from_env")]
        config_instance.set(f"api_keys.{self.provider_name}", config_keys)

    def add_key(self, key_str: str) -> bool:
        """Add new API key to pool."""
        key_str = key_str.strip()
        if not key_str:
            return False
        if any(k["key"] == key_str for k in self.keys):
            logger.warning("Key already exists in %s pool", self.provider_name)
            return False

        key_obj = {
            "id": f"{self.provider_name}_{len(self.keys)+1}",
            "key": key_str,
            "enabled": True,
            "error_count": 0,
            "cooldown_until": 0,
            "from_env": False
        }
        self.keys.append(key_obj)
        self.sync_to_config()
        logger.info("Added new key #%s to %s pool: %s", len(self.keys), self.provider_name, mask_key(key_str))
        return True

    def remove_key(self, key_id: str) -> bool:
        """Remove key by ID or index."""
        original_len = len(self.keys)
        self.keys = [k for k in self.keys if k["id"] != key_id and k["key"] != key_id]
        if len(self.keys) < original_len:
            self.sync_to_config()
            logger.info("Removed key %s from %s pool", key_id, self.provider_name)
            return True
        return False

    def toggle_key(self, key_id: str, enabled: bool) -> bool:
        """Enable or disable specific key."""
        for k in self.keys:
            if k["id"] == key_id or k["key"] == key_id:
                k["enabled"] = enabled
                self.sync_to_config()
                logger.info("Key %s %s in %s pool", mask_key(k['key']), 'enabled' if enabled else 'disabled', self.provider_name)
                return True
        return False

    def get_active_key(self) -> Optional[str]:
        """Get currently active valid key with rotation support."""
        if not self.keys:
            return None

        now = time.time()
        start_idx = self.current_index

        for i in range(len(self.keys)):
            idx = (start_idx + i) % len(self.keys)
            k = self.keys[idx]
            if k.get("enabled", True) and k.get("cooldown_until", 0) <= now:
                self.current_index = idx
                logger.debug("Using %s key #%d (%s)", self.provider_name, idx + 1, mask_key(k["key"]))
                return k["key"]

        logger.warning("No active valid key available in %s pool!", self.provider_name)
        return None

    def mark_error(self, key_str: str, cooldown_sec: int = 300) -> Optional[str]:
        """Mark error for key, set cooldown, and return next active key."""
        now = time.time()
        for k in self.keys:
            if k["key"] == key_str:
                k["error_count"] = k.get("error_count", 0) + 1
                k["cooldown_until"] = now + cooldown_sec
                logger.warning(
                    "Key %s in %s pool marked error (count: %d). Cooldown for %ds.",
                    mask_key(key_str), self.provider_name, k["error_count"], cooldown_sec
                )
                break
        self.sync_to_config()

        self.current_index = (self.current_index + 1) % max(1, len(self.keys))
        return self.get_active_key()


class ApiKeyManager:
    """Central API Key Manager for all providers."""

    def __init__(self):
        self.groq = ApiKeyPool("groq")
        self.gemini = ApiKeyPool("gemini")

    def reload_all(self) -> None:
        self.groq.reload()
        self.gemini.reload()


# Global singleton instance
key_manager_instance = ApiKeyManager()
