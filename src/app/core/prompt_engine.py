"""
src/app/core/prompt_engine.py
=============================
Prompt Library Persistence & SRT Prompt Generator enforcing Core Rule 1 & Core Rule 2.

This module is the single source of truth for Translation prompts used by
app/services/translator.py. It supports full CRUD (create/read/update/delete),
rename, duplicate, and "active prompt" management with the invariant that at
most one prompt is active at any time.
"""

from datetime import datetime
import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import config_instance

logger = logging.getLogger("PromptEngine")

PROMPTS_FILE_PATH = config_instance.config_dir / "prompts.json"

MANDATORY_FILLER_WORDS = [
    "thì", "là", "mà", "rằng", "ấy", "vẫn", "đang", "đã", "sẽ",
    "được", "bị", "các", "những", "mấy cái", "những cái", "việc", "sự"
]

KNOWN_PROMPT_PLACEHOLDERS = ["{text}", "{source_text}", "{segments}"]

BUILTIN_PROMPTS = [
    {
        "id": "builtin_srt_v1",
        "name": "Standard SRT Translation (Vietnamese TTS Optimized)",
        "description": "Built-in prompt enforcing duration caps & natural Vietnamese for TTS dubbing.",
        "is_builtin": True,
        "is_default": True,
        "active": True,
        "created_at": "2026-07-30T00:00:00",
        "updated_at": "2026-07-30T00:00:00",
        "content": (
            "Dịch đoạn văn bản SRT sau từ tiếng Trung sang tiếng Việt tự nhiên, phù hợp đọc TTS.\n\n"
            "QUY TẮC BẮT BUỘC:\n"
            "1. DURATION & SYLLABLE CAP (CORE RULE 1):\n"
            "   - Số từ tiếng Việt tối đa = Duration (giây) × 3.5.\n"
            "   - Subtitle ngắn hơn 0.8s: tối đa 2 từ.\n"
            "2. LOẠI BỎ FILLER WORDS KHÔNG CẦN THIẾT (CORE RULE 2):\n"
            "   - Tuyệt đối loại bỏ các từ dư thừa nếu không ảnh hưởng nghĩa: thì, là, mà, rằng, ấy, vẫn, đang, đã, sẽ, được, bị, các, những, mấy cái, những cái, việc, sự.\n"
            "   - Dùng từ ngắn gọn: 'nói' thay vì 'phát biểu', 'biết' thay vì 'nhận thức được', 'giúp' thay vì 'hỗ trợ'.\n"
            "3. GIỮ NGUYÊN ĐỊNH DẠNG SRT:\n"
            "   - Giữ nguyên số thứ tự subtitle, Start Time, End Time.\n"
            "   - Không gộp, không tách, không xóa, không thêm dòng subtitle."
        )
    }
]


class PromptValidationError(Exception):
    """Raised when prompt create/update/rename input fails validation."""
    pass


class PromptGenerator:
    """Generates SRT Translation Prompts incorporating user natural language instructions and core mandatory rules."""

    @staticmethod
    def generate(user_request: str) -> str:
        """Generate complete prompt based on user description + Core Rules."""
        user_request = user_request.strip() if user_request else "Dịch phim tự nhiên, ngắn gọn."

        prompt_text = (
            f"# ROLE & TASK\n"
            f"Bạn là chuyên gia dịch thuật phụ đề SRT và biên kịch lồng tiếng TTS tiếng Việt chuyên nghiệp.\n"
            f"Yêu cầu từ người dùng: {user_request}\n\n"
            f"# CORE RULE 1: DURATION & SYLLABLE CAP (BẮT BUỘC KHÔNG ĐƯỢC THAY ĐỔI)\n"
            f"- Tốc độ đọc tiếng Việt phải khớp nhịp audio gốc.\n"
            f"- Công thức giới hạn: Số từ tiếng Việt tối đa = Duration (giây) × 3.5.\n"
            f"  * Ví dụ: Subtitle 1.0 giây -> tối đa 3-4 từ.\n"
            f"  * Ví dụ: Subtitle 2.0 giây -> tối đa 7 từ.\n"
            f"- Subtitle dưới 0.8 giây: tối đa 2 từ.\n\n"
            f"# CORE RULE 2: LOẠI BỎ FILLER WORDS (BẮT BUỘC KHÔNG ĐƯỢC THAY ĐỔI)\n"
            f"- Loại bỏ tất cả các từ nối/từ đệm không cần thiết về mặt ngữ nghĩa:\n"
            f"  [{', '.join(MANDATORY_FILLER_WORDS)}]\n"
            f"- Ưu tiên từ đơn ngắn, dễ đọc TTS:\n"
            f"  * Dùng 'nói' thay vì 'phát biểu' / 'trò chuyện'.\n"
            f"  * Dùng 'biết' thay vì 'nhận thức được'.\n"
            f"  * Dùng 'giúp' thay vì 'hỗ trợ'.\n\n"
            f"# SRT PRESERVATION & FORMAT RULES\n"
            f"1. Giữ nguyên toàn bộ số thứ tự dòng subtitle.\n"
            f"2. Giữ nguyên Start Time và End Time (HH:MM:SS,mmm --> HH:MM:SS,mmm).\n"
            f"3. Không gộp, không tách, không xóa hay thêm bất kỳ block subtitle nào.\n"
            f"4. Chỉ thay đổi phần text phụ đề sang tiếng Việt.\n"
            f"5. Chỉ xuất ra nội dung file SRT hoàn chỉnh, không thêm giải thích hay markdown codeblock."
        )
        return prompt_text


def extract_placeholders(content: str) -> List[str]:
    """Return the list of known placeholders present in a prompt's content, in order of appearance."""
    if not content:
        return []
    found = []
    for ph in KNOWN_PROMPT_PLACEHOLDERS:
        if ph in content:
            found.append(ph)
    if found:
        return found
    return re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", content)


class PromptLibrary:
    """Manages persistent library of Translation prompts (CRUD + single-active-prompt invariant)."""

    def __init__(self, storage_file: Optional[Path] = None):
        self.storage_file = storage_file or PROMPTS_FILE_PATH
        self.prompts: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self.load()

    def load(self) -> None:
        """Load prompts from disk. Falls back to builtin defaults on missing/corrupt storage."""
        with self._lock:
            if not self.storage_file.exists():
                self.prompts = [dict(p) for p in BUILTIN_PROMPTS]
                self.save()
                return

            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                data = json.loads(raw) if raw.strip() else []
                if not isinstance(data, list):
                    raise ValueError("prompts.json root must be a list")
                self.prompts = data
                self._migrate_and_repair()
            except Exception as e:
                logger.error("Failed to load prompt library (%s), falling back to defaults: %s", self.storage_file, e)
                self.prompts = [dict(p) for p in BUILTIN_PROMPTS]
                self.save()

    def save(self) -> bool:
        """Persist prompts to disk. Returns False (and logs) on failure instead of raising."""
        with self._lock:
            try:
                self.storage_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self.storage_file.with_suffix(".json.tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self.prompts, f, ensure_ascii=False, indent=2)
                tmp_path.replace(self.storage_file)
                return True
            except PermissionError as e:
                logger.error("Permission denied while saving prompt library: %s", e)
                return False
            except Exception as e:
                logger.error("Failed to save prompt library: %s", e)
                return False

    def _migrate_and_repair(self) -> None:
        """Ensure every prompt has the fields this module relies on."""
        changed = False

        if not self.prompts:
            self.prompts = [dict(p) for p in BUILTIN_PROMPTS]
            changed = True

        now = datetime.now().isoformat()
        for p in self.prompts:
            if "id" not in p or not p["id"]:
                p["id"] = f"usr_{uuid.uuid4().hex[:12]}"
                changed = True
            p.setdefault("name", "Untitled Prompt")
            p.setdefault("description", "")
            p.setdefault("content", "")
            p.setdefault("is_builtin", False)
            p.setdefault("created_at", now)
            p.setdefault("updated_at", now)
            if "active" not in p:
                p["active"] = bool(p.get("is_default", False))
                changed = True

        active_prompts = [p for p in self.prompts if p.get("active")]
        if len(active_prompts) == 0:
            fallback = next((p for p in self.prompts if p.get("is_default")), None)
            fallback = fallback or next((p for p in self.prompts if p.get("is_builtin")), None)
            fallback = fallback or self.prompts[0]
            fallback["active"] = True
            changed = True
        elif len(active_prompts) > 1:
            active_prompts.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
            for p in active_prompts[1:]:
                p["active"] = False
            changed = True

        for p in self.prompts:
            new_default = p.get("active", False)
            if p.get("is_default") != new_default:
                p["is_default"] = new_default
                changed = True

        if changed:
            self.save()

    def list_prompts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.prompts)

    def get_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        if not prompt_id:
            return None
        with self._lock:
            for p in self.prompts:
                if p["id"] == prompt_id:
                    return p
        return None

    def get_active_prompt(self) -> Optional[Dict[str, Any]]:
        """Return the single currently-active prompt."""
        with self._lock:
            for p in self.prompts:
                if p.get("active"):
                    return p
            self._migrate_and_repair()
            for p in self.prompts:
                if p.get("active"):
                    return p
            return self.prompts[0] if self.prompts else (dict(BUILTIN_PROMPTS[0]))

    def get_default_prompt(self) -> Dict[str, Any]:
        """Legacy alias kept for backward compatibility."""
        return self.get_active_prompt() or (self.prompts[0] if self.prompts else BUILTIN_PROMPTS[0])

    def _validate_name(self, name: str, exclude_id: Optional[str] = None) -> str:
        clean = (name or "").strip()
        if not clean:
            raise PromptValidationError("Tên prompt không được để trống.")
        with self._lock:
            for p in self.prompts:
                if p["id"] == exclude_id:
                    continue
                if p.get("name", "").strip().lower() == clean.lower():
                    raise PromptValidationError(f"Đã tồn tại prompt với tên '{clean}'.")
        return clean

    def _validate_content(self, content: str) -> str:
        if not content or not content.strip():
            raise PromptValidationError("Nội dung prompt không được để trống.")
        return content

    def add_prompt(self, name: str, content: str, description: str = "", active: bool = False) -> Dict[str, Any]:
        with self._lock:
            clean_name = self._validate_name(name)
            clean_content = self._validate_content(content)

            now = datetime.now().isoformat()
            new_prompt = {
                "id": f"usr_{uuid.uuid4().hex[:12]}",
                "name": clean_name,
                "description": (description or "").strip(),
                "content": clean_content,
                "is_builtin": False,
                "is_default": False,
                "active": False,
                "created_at": now,
                "updated_at": now
            }
            self.prompts.append(new_prompt)

            if active:
                self.activate_prompt(new_prompt["id"], _save=False)

            if not self.save():
                raise IOError("Không thể lưu prompt vào bộ nhớ.")
            return new_prompt

    def update_prompt(self, prompt_id: str, name: Optional[str] = None, content: Optional[str] = None,
                      description: Optional[str] = None) -> bool:
        with self._lock:
            p = self.get_prompt(prompt_id)
            if p is None:
                raise PromptValidationError("Prompt không tồn tại.")
            if p.get("is_builtin"):
                raise PromptValidationError("Không thể chỉnh sửa prompt hệ thống (built-in).")

            if name is not None:
                p["name"] = self._validate_name(name, exclude_id=prompt_id)
            if content is not None:
                p["content"] = self._validate_content(content)
            if description is not None:
                p["description"] = description.strip()

            p["updated_at"] = datetime.now().isoformat()
            if not self.save():
                raise IOError("Không thể lưu thay đổi prompt.")
            return True

    def rename_prompt(self, prompt_id: str, new_name: str) -> bool:
        with self._lock:
            p = self.get_prompt(prompt_id)
            if p is None:
                raise PromptValidationError("Prompt không tồn tại.")
            if p.get("is_builtin"):
                raise PromptValidationError("Không thể đổi tên prompt hệ thống (built-in).")
            p["name"] = self._validate_name(new_name, exclude_id=prompt_id)
            p["updated_at"] = datetime.now().isoformat()
            if not self.save():
                raise IOError("Không thể lưu tên prompt mới.")
            return True

    def duplicate_prompt(self, prompt_id: str) -> Dict[str, Any]:
        with self._lock:
            src = self.get_prompt(prompt_id)
            if src is None:
                raise PromptValidationError("Prompt không tồn tại.")

            base_name = src["name"]
            new_name = f"{base_name} (Copy)"
            counter = 2
            existing_names = {p["name"].strip().lower() for p in self.prompts}
            while new_name.strip().lower() in existing_names:
                new_name = f"{base_name} (Copy {counter})"
                counter += 1

            now = datetime.now().isoformat()
            new_prompt = {
                "id": f"usr_{uuid.uuid4().hex[:12]}",
                "name": new_name,
                "description": src.get("description", ""),
                "content": src.get("content", ""),
                "is_builtin": False,
                "is_default": False,
                "active": False,
                "created_at": now,
                "updated_at": now
            }
            self.prompts.append(new_prompt)
            if not self.save():
                raise IOError("Không thể lưu prompt nhân bản.")
            return new_prompt

    def delete_prompt(self, prompt_id: str) -> bool:
        with self._lock:
            p = self.get_prompt(prompt_id)
            if p is None:
                raise PromptValidationError("Prompt không tồn tại.")
            if p.get("is_builtin"):
                raise PromptValidationError("Không thể xóa prompt hệ thống (built-in).")
            if len(self.prompts) <= 1:
                raise PromptValidationError("Không thể xóa prompt cuối cùng. Hệ thống yêu cầu ít nhất một prompt.")

            was_active = p.get("active", False)
            self.prompts.remove(p)

            if was_active and self.prompts:
                fallback = next((x for x in self.prompts if x.get("is_builtin")), self.prompts[0])
                fallback["active"] = True
                fallback["is_default"] = True
                fallback["updated_at"] = datetime.now().isoformat()

            if not self.save():
                raise IOError("Không thể lưu sau khi xóa prompt.")
            return True

    def activate_prompt(self, prompt_id: str, _save: bool = True) -> bool:
        """Mark exactly one prompt active; all others become inactive."""
        with self._lock:
            target = self.get_prompt(prompt_id)
            if target is None:
                raise PromptValidationError("Prompt không tồn tại hoặc đã bị xóa.")

            now = datetime.now().isoformat()
            for p in self.prompts:
                should_be_active = (p["id"] == prompt_id)
                if p.get("active", False) != should_be_active:
                    p["active"] = should_be_active
                    p["updated_at"] = now
                p["is_default"] = should_be_active

            if _save:
                if not self.save():
                    raise IOError("Không thể lưu trạng thái kích hoạt prompt.")
            return True

    def toggle_active(self, prompt_id: str) -> bool:
        """Toggle a prompt's active state."""
        with self._lock:
            p = self.get_prompt(prompt_id)
            if p is None:
                raise PromptValidationError("Prompt không tồn tại.")

            if not p.get("active"):
                return self.activate_prompt(prompt_id)

            fallback = next((x for x in self.prompts if x["id"] != prompt_id and x.get("is_builtin")), None)
            fallback = fallback or next((x for x in self.prompts if x["id"] != prompt_id), None)
            if fallback is None:
                return True
            return self.activate_prompt(fallback["id"])


# Global singleton instance
prompt_library_instance = PromptLibrary()
