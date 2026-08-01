"""
app/editor/editor_config.py
============================
Percentage-based Coordinate System (0.0 - 100.0%) for Subtitles, Blur Regions & Logo Overlays.

v2: Supports MULTIPLE items per overlay type (subtitles / blur_regions / logos), each with
its own id so the GUI can Add / Edit / Delete individual items. Backward compatible with the
old single-item config format (auto-migrated on load).
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("EditorConfig")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


# Default field values for each overlay item type.
DEFAULT_SUBTITLE: Dict[str, Any] = {
    "id": None,
    "enabled": True,
    "text": "Phụ đề mẫu",
    "x_pct": 50.0,          # Center X position (%)
    "y_pct": 85.0,          # Center Y position (%)
    "font_size": 24,
    "font_color": "#FFFFFF",
    "bg_enabled": True,
    "bg_color": "#000000",
    "bg_opacity": 0.5,
    "bg_padding_x": 12.0,    # Horizontal background padding around text (px, at native video resolution)
    "bg_padding_y": 8.0,     # Vertical background padding around text (px, at native video resolution)
    "bg_corner_radius": 6.0, # Rounded-corner radius for the background (px). Preview only - see renderer.py.
    "start_time": 0.0,      # seconds
    "end_time": None,       # None = shown until end of video
}

DEFAULT_BLUR: Dict[str, Any] = {
    "id": None,
    "enabled": True,
    "x_pct": 10.0,           # Top-left X (%)
    "y_pct": 80.0,           # Top-left Y (%)
    "width_pct": 80.0,
    "height_pct": 12.0,
    "blur_strength": 10,
}

DEFAULT_LOGO: Dict[str, Any] = {
    "id": None,
    "enabled": True,
    "image_path": None,
    "x_pct": 5.0,             # Top-left X (%)
    "y_pct": 5.0,             # Top-left Y (%)
    "width_pct": 15.0,
    "height_pct": 10.0,
    "opacity": 0.8,
}


class EditorOverlayConfig:
    """Manages lists of relative-percentage overlay items (subtitles, blur regions, logos)
    so positioning stays consistent across 720p / 1080p / 4K renders."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.subtitles: List[Dict[str, Any]] = []
        self.blur_regions: List[Dict[str, Any]] = []
        self.logos: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # CRUD helpers - Subtitles
    # ------------------------------------------------------------------
    def add_subtitle(self, **overrides: Any) -> Dict[str, Any]:
        item = dict(DEFAULT_SUBTITLE)
        item.update(overrides)
        item["id"] = _new_id()
        self.subtitles.append(item)
        return item

    def get_subtitle(self, item_id: str) -> Optional[Dict[str, Any]]:
        return next((s for s in self.subtitles if s.get("id") == item_id), None)

    def update_subtitle(self, item_id: str, **changes: Any) -> bool:
        item = self.get_subtitle(item_id)
        if item is None:
            return False
        item.update(changes)
        return True

    def remove_subtitle(self, item_id: str) -> bool:
        before = len(self.subtitles)
        self.subtitles = [s for s in self.subtitles if s.get("id") != item_id]
        return len(self.subtitles) != before

    # ------------------------------------------------------------------
    # CRUD helpers - Blur Regions
    # ------------------------------------------------------------------
    def add_blur(self, **overrides: Any) -> Dict[str, Any]:
        item = dict(DEFAULT_BLUR)
        item.update(overrides)
        item["id"] = _new_id()
        self.blur_regions.append(item)
        return item

    def get_blur(self, item_id: str) -> Optional[Dict[str, Any]]:
        return next((b for b in self.blur_regions if b.get("id") == item_id), None)

    def update_blur(self, item_id: str, **changes: Any) -> bool:
        item = self.get_blur(item_id)
        if item is None:
            return False
        item.update(changes)
        return True

    def remove_blur(self, item_id: str) -> bool:
        before = len(self.blur_regions)
        self.blur_regions = [b for b in self.blur_regions if b.get("id") != item_id]
        return len(self.blur_regions) != before

    # ------------------------------------------------------------------
    # CRUD helpers - Logos
    # ------------------------------------------------------------------
    def add_logo(self, **overrides: Any) -> Dict[str, Any]:
        item = dict(DEFAULT_LOGO)
        item.update(overrides)
        item["id"] = _new_id()
        self.logos.append(item)
        return item

    def get_logo(self, item_id: str) -> Optional[Dict[str, Any]]:
        return next((l for l in self.logos if l.get("id") == item_id), None)

    def update_logo(self, item_id: str, **changes: Any) -> bool:
        item = self.get_logo(item_id)
        if item is None:
            return False
        item.update(changes)
        return True

    def remove_logo(self, item_id: str) -> bool:
        before = len(self.logos)
        self.logos = [l for l in self.logos if l.get("id") != item_id]
        return len(self.logos) != before

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "version": 2,
            "subtitles": self.subtitles,
            "blur_regions": self.blur_regions,
            "logos": self.logos,
        }

    def load_dict(self, data: Dict[str, Any]) -> None:
        if "subtitles" in data or "blur_regions" in data or "logos" in data:
            # Current (v2) multi-item format.
            self.subtitles = [dict(DEFAULT_SUBTITLE, **s) for s in data.get("subtitles", [])]
            self.blur_regions = [dict(DEFAULT_BLUR, **b) for b in data.get("blur_regions", [])]
            self.logos = [dict(DEFAULT_LOGO, **l) for l in data.get("logos", [])]
            for collection in (self.subtitles, self.blur_regions, self.logos):
                for item in collection:
                    if not item.get("id"):
                        item["id"] = _new_id()
            return

        # Legacy (v1) single-item format -> migrate into lists.
        self.subtitles = []
        self.blur_regions = []
        self.logos = []

        sub = data.get("subtitle")
        if sub:
            self.add_subtitle(
                enabled=sub.get("enabled", True),
                font_size=sub.get("font_size", 24),
                x_pct=sub.get("pos_x_pct", 50.0),
                y_pct=sub.get("pos_y_pct", 85.0),
            )

        blur = data.get("blur_region")
        if blur and blur.get("enabled"):
            self.add_blur(
                enabled=True,
                x_pct=blur.get("x_pct", 10.0),
                y_pct=blur.get("y_pct", 80.0),
                width_pct=blur.get("width_pct", 80.0),
                height_pct=blur.get("height_pct", 12.0),
                blur_strength=blur.get("blur_strength", 10),
            )

        logo = data.get("logo")
        if logo and logo.get("enabled") and logo.get("image_path"):
            self.add_logo(
                enabled=True,
                image_path=logo.get("image_path"),
                x_pct=logo.get("x_pct", 5.0),
                y_pct=logo.get("y_pct", 5.0),
                width_pct=logo.get("width_pct", 15.0),
                height_pct=logo.get("height_pct", 10.0),
                opacity=logo.get("opacity", 0.8),
            )
        logger.info("Migrated legacy v1 editor_config.json to v2 multi-item format.")

    def save(self, config_path: Path) -> bool:
        """Save configuration to editor_config.json."""
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info("Saved Visual Editor config to %s", config_path)
            return True
        except Exception as e:
            logger.error("Failed to save editor_config.json: %s", e)
            return False

    def load(self, config_path: Path) -> bool:
        """Load configuration from editor_config.json."""
        if not config_path.exists():
            return False
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.load_dict(data)
            logger.info("Loaded Visual Editor config from %s", config_path)
            return True
        except Exception as e:
            logger.error("Failed to load editor_config.json: %s", e)
            return False
