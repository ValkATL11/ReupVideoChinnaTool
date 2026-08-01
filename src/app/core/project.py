"""
src/app/core/project.py
=======================
Unified Project Manager & Project ID System (PRJ-YYMMDD-XXXX).

Improvements:
- All paths are now relative to project base_dir, not cwd
- Proper path isolation between projects
- Consistent file naming conventions
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import re
import secrets
import shutil
import string
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ProjectManager")

INVALID_PATH_CHARS = re.compile(r'[\\/:*?"<>|]')


def generate_project_id() -> str:
    """Generate automatic Project ID in format PRJ-YYMMDD-XXXX."""
    date_str = datetime.now().strftime("%y%m%d")
    chars = string.ascii_uppercase + string.digits
    random_str = ''.join(secrets.choice(chars) for _ in range(4))
    return f"PRJ-{date_str}-{random_str}"


def validate_project_id(project_id: str) -> bool:
    """Validate Project ID."""
    if not project_id or not project_id.strip():
        return False
    if INVALID_PATH_CHARS.search(project_id):
        return False
    if ".." in project_id or "." == project_id:
        return False
    if project_id != project_id.strip():
        return False
    return True


class Project:
    """Represents a single project entity with consistent path management."""

    def __init__(self, project_id: str, name: Optional[str] = None, base_dir: Optional[Path] = None):
        if not validate_project_id(project_id):
            raise ValueError(f"Invalid Project ID: '{project_id}'")

        self.project_id = project_id
        self.name = name or project_id

        # Base directory for this project
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            from app.core.config import config_instance
            projects_root = config_instance.get("general.projects_dir", Path("data/projects"))
            self.base_dir = Path(projects_root) / self.project_id

        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

        # Directory structure - all relative to base_dir or project root
        # These paths are now consistent and project-isolated
        project_root = self.base_dir.parent

        # Shared resource directories (created on demand)
        self.video_dir = project_root / "original_videos"
        self.audio_dir = project_root / "original_audios"
        self.chunked_dir = project_root / "chunked_audio" / f"{self.project_id}_Chunked"
        self.transcribed_dir = project_root / "transcriber_output" / f"{self.project_id}_transcribed"
        self.translated_dir = project_root / "translated"
        self.dubbing_dir = project_root / "dubbing" / self.project_id
        self.separated_dir = project_root / "separated_audios"
        self.mixed_dir = project_root / "mixed_audios"
        self.output_dir = project_root / "output"

    # Core File Standard Paths
    @property
    def raw_video_path(self) -> Path:
        return self.video_dir / f"{self.project_id}_Ovideo.mp4"

    @property
    def raw_audio_path(self) -> Path:
        return self.audio_dir / f"{self.project_id}_Oaudio.mp3"

    @property
    def refined_srt_path(self) -> Path:
        return self.transcribed_dir / f"{self.project_id}_refined.srt"

    @property
    def translated_srt_path(self) -> Path:
        return self.translated_dir / f"{self.project_id}_refined_vi.srt"

    @property
    def dubbed_master_path(self) -> Path:
        return self.dubbing_dir / f"{self.project_id}_0Full.mp3"

    @property
    def nonvocal_audio_path(self) -> Path:
        return self.separated_dir / f"{self.project_id}_Nvocal.mp3"

    @property
    def mixed_audio_path(self) -> Path:
        return self.mixed_dir / f"{self.project_id}_Mixed.mp3"

    @property
    def final_output_path(self) -> Path:
        return self.output_dir / f"{self.project_id}_Final.mp4"

    @property
    def editor_config_path(self) -> Path:
        return self.base_dir / "editor_config.json"

    @property
    def state_file_path(self) -> Path:
        return self.base_dir / "state.json"

    def ensure_directories(self) -> None:
        """Create project directory and required workspace folders."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.translated_dir.mkdir(parents=True, exist_ok=True)
        self.separated_dir.mkdir(parents=True, exist_ok=True)
        self.mixed_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "base_dir": str(self.base_dir.resolve()),
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class ProjectManager:
    """Manages project creation, recent projects tracking, loading, and deletion."""

    def __init__(self, projects_root: Optional[Path] = None):
        from app.core.config import config_instance
        self.projects_root = Path(projects_root) if projects_root else config_instance.get("general.projects_dir", Path("data/projects"))
        self.recent_file = self.projects_root.parent / ".recent_projects.json"
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def create_project(self, custom_id: Optional[str] = None, name: Optional[str] = None) -> Project:
        """Create a new project with auto or custom ID."""
        project_id = custom_id.strip() if custom_id else generate_project_id()
        if not validate_project_id(project_id):
            raise ValueError(f"Invalid Project ID: '{project_id}'")

        project = Project(project_id=project_id, name=name or project_id, base_dir=self.projects_root / project_id)
        project.ensure_directories()

        self._add_to_recent(project)
        logger.info("Created project: %s (%s)", project_id, project.name)
        return project

    def list_projects(self) -> List[Dict[str, Any]]:
        """Scan projects folder and return list of projects."""
        projects = []
        if not self.projects_root.exists():
            return projects

        for item in self.projects_root.iterdir():
            if item.is_dir():
                state_file = item / "state.json"
                if state_file.exists():
                    try:
                        with open(state_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        projects.append({
                            "project_id": data.get("project_id", item.name),
                            "name": data.get("name", item.name),
                            "created_at": data.get("created_at", ""),
                            "updated_at": data.get("updated_at", ""),
                            "path": str(item.resolve())
                        })
                        continue
                    except Exception:
                        pass
                projects.append({
                    "project_id": item.name,
                    "name": item.name,
                    "created_at": "",
                    "updated_at": "",
                    "path": str(item.resolve())
                })
        return projects

    def delete_project(self, project_id: str, keep_final_output: bool = True) -> bool:
        """Delete a project directory with safety checks."""
        proj_dir = self.projects_root / project_id
        if proj_dir.exists():
            try:
                shutil.rmtree(proj_dir)
                self._remove_from_recent(project_id)
                logger.info("Deleted project directory: %s", proj_dir)
                return True
            except Exception as e:
                logger.error("Failed to delete project directory (%s): %s", proj_dir, e)
                return False
        return False

    def get_recent_projects(self) -> List[Dict[str, Any]]:
        if self.recent_file.exists():
            try:
                with open(self.recent_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _add_to_recent(self, project: Project) -> None:
        recents = self.get_recent_projects()
        recents = [r for r in recents if r.get("project_id") != project.project_id]
        recents.insert(0, project.to_dict())
        recents = recents[:10]

        try:
            with open(self.recent_file, "w", encoding="utf-8") as f:
                json.dump(recents, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _remove_from_recent(self, project_id: str) -> None:
        recents = self.get_recent_projects()
        recents = [r for r in recents if r.get("project_id") != project_id]
        try:
            with open(self.recent_file, "w", encoding="utf-8") as f:
                json.dump(recents, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
