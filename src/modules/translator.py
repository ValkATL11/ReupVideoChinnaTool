#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Standalone Translator for SRT subtitles.
- Input:  transcriber_output/{PROJECT_ID}_transcribed/{PROJECT_ID}_refined.srt
- Output: translated/{PROJECT_ID}_refined_vi.srt
- Priority: Gemini API (if keys available) → Selenium (fallback)
- Chunk size: 120 lines per request (configurable)
- Tự động lấy Project ID từ tên file/path
"""

import os
import re
import sys
import time
import logging
from pathlib import Path
from typing import Optional, List, Callable, Dict

# --- Gemini API ---
from google import genai

# --- Selenium ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# ====== CẤU HÌNH ======
# Thư mục làm việc tương đối
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SRT_DIR = BASE_DIR / "transcriber_output"
DEFAULT_TRANSLATED_DIR = BASE_DIR / "translated"

# Đọc danh sách API key từ biến môi trường
_GEMINI_API_KEYS_ENV = os.environ.get("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in _GEMINI_API_KEYS_ENV.split(",") if k.strip()]

# Engine: ưu tiên API nếu có key, nếu không dùng Selenium
ENGINE = os.environ.get("TRANSLATOR_ENGINE", "gemini_api" if GEMINI_API_KEYS else "selenium").lower()

# ====== ĐỌC PROMPT TỪ FILE ======
PROMPT_FILE_PATH = BASE_DIR / "prompt" / "prompt.txt"

def load_prompt() -> str:
    if PROMPT_FILE_PATH.exists():
        try:
            with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception as e:
            logging.warning(f"Không thể đọc prompt file: {e}")
    # Fallback
    return (
        "Dịch đoạn văn bản sau từ tiếng Trung sang tiếng Việt, "
        "giữ nguyên số dòng và định dạng SRT (chỉ giữ lại phần nội dung, không thêm giải thích)."
    )

PROMPT_TEXT = load_prompt()

# Số dòng tối đa gửi mỗi lần
MAX_LINES_PER_CHUNK = int(os.environ.get("TRANSLATOR_MAX_LINES", "120"))

# Cấu hình Selenium
HEADLESS = os.environ.get("TRANSLATOR_HEADLESS", "true").lower() == "true"
USER_AGENT = os.environ.get("TRANSLATOR_USER_AGENT", None)

# ====== LOGGING ======
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ====== TIỆN ÍCH ======
def extract_project_id_from_path(file_path: Path) -> Optional[str]:
    """
    Trích xuất Project ID từ đường dẫn file.
    Format: transcriber_output/{PROJECT_ID}_transcribed/{PROJECT_ID}_refined.srt
    """
    # Lấy tên file không extension
    file_stem = file_path.stem  # VD: PRJ-260729-37TG_refined
    
    # Loại bỏ hậu tố _refined
    if file_stem.endswith("_refined"):
        project_id = file_stem[:-8]  # Loại bỏ "_refined"
    else:
        project_id = file_stem
    
    # Kiểm tra format PRJ-YYMMDD-XXXX
    pattern = r"^PRJ-[\dA-Z-]+$"
    if not re.match(pattern, project_id):
        logger.warning(f"⚠️ Project ID '{project_id}' không đúng format chuẩn.")
    
    return project_id


def get_output_path(input_path: Path, translated_dir: Path) -> Path:
    """
    Tạo đường dẫn output dựa trên input path.
    Input:  transcriber_output/{PROJECT_ID}_transcribed/{PROJECT_ID}_refined.srt
    Output: translated/{PROJECT_ID}_refined_vi.srt
    """
    # Trích xuất Project ID
    project_id = extract_project_id_from_path(input_path)
    if not project_id:
        # Fallback: lấy từ tên thư mục cha
        parent_name = input_path.parent.name  # VD: PRJ-260729-37TG_transcribed
        if parent_name.endswith("_transcribed"):
            project_id = parent_name[:-12]  # Loại bỏ "_transcribed"
        else:
            project_id = parent_name
    
    # Tạo tên file output
    output_filename = f"{project_id}_refined_vi.srt"
    output_path = translated_dir / output_filename
    
    return output_path


def read_text_file(file_path: Path) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Lỗi đọc file {file_path}: {e}")
        return ""


def write_text_file(file_path: Path, content: str) -> bool:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"Lỗi ghi file {file_path}: {e}")
        return False


def format_srt_content(content: str) -> str:
    """Chuẩn hóa định dạng SRT: mỗi block 3 dòng, cách nhau 1 dòng trống."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""
    blocks = []
    for i in range(0, len(lines), 3):
        block = "\n".join(lines[i:i+3])
        blocks.append(block)
    return "\n\n".join(blocks) + "\n"


def find_refined_srt_files(directory: Path) -> List[Path]:
    """
    Tìm tất cả file *_refined.srt trong thư mục transcriber_output.
    Format: transcriber_output/{PROJECT_ID}_transcribed/{PROJECT_ID}_refined.srt
    """
    if not directory.exists():
        return []
    
    # Tìm tất cả file *_refined.srt trong các thư mục con
    srt_files = []
    for folder in directory.iterdir():
        if folder.is_dir() and folder.name.endswith("_transcribed"):
            # Tìm file refined.srt trong thư mục này
            for srt_file in folder.glob("*_refined.srt"):
                srt_files.append(srt_file)
    
    return srt_files


# ====== BASE TRANSLATOR ======
class BaseTranslator:
    def translate_file(
        self,
        srt_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Optional[Path]:
        raise NotImplementedError

    def process_all(
        self,
        single_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        pattern: str = "*.srt",
        recursive: bool = False
    ) -> bool:
        raise NotImplementedError


# ====== GEMINI API TRANSLATOR ======
class GeminiApiTranslator(BaseTranslator):
    def __init__(self, srt_dir: Path, translated_dir: Path):
        self.srt_dir = srt_dir
        self.translated_dir = translated_dir
        self.api_keys: List[str] = GEMINI_API_KEYS
        self.current_key_index = 0
        self.client = None
        self.key_error_counts = {key: 0 for key in self.api_keys}
        self.max_errors_per_key = 2
        self.available = bool(self.api_keys)
        self.total_tokens = 0
        self.model = "models/gemini-2.0-flash"

        if self.available:
            self._init_client()
        else:
            logger.warning("⚠️ Không có Gemini API keys.")

    def _init_client(self):
        if self.api_keys and self.available:
            api_key = self.api_keys[self.current_key_index]
            self.client = genai.Client(api_key=api_key)

    def _switch_key(self):
        for i, key in enumerate(self.api_keys):
            if self.key_error_counts.get(key, 0) < self.max_errors_per_key:
                if i != self.current_key_index:
                    self.current_key_index = i
                    self._init_client()
                    return True
        self.available = False
        return False

    def translate_text(self, text: str) -> Optional[str]:
        if not self.available or not self.client:
            return None

        try:
            prompt = f"{PROMPT_TEXT}\n\nNội dung cần dịch:\n\n{text}"
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )

            if response and response.text:
                translated = response.text.strip()
                translated = re.sub(r'^```\w*\n', '', translated)
                translated = re.sub(r'\n```$', '', translated)
                self.total_tokens += len(text) // 4 + len(translated) // 4
                return translated
            return None
        except Exception as e:
            logger.error(f"Lỗi gọi Gemini API: {e}")
            if self.api_keys:
                current_key = self.api_keys[self.current_key_index]
                self.key_error_counts[current_key] += 1
                if self.key_error_counts[current_key] >= self.max_errors_per_key:
                    if self._switch_key():
                        logger.info(f"Chuyển sang key khác: {self.current_key_index}")
                        return self.translate_text(text)
            return None

    def parse_srt(self, srt_content: str) -> List[dict]:
        lines = srt_content.strip().split('\n')
        segments = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.isdigit():
                current_segment = {'index': int(line)}
                i += 1
                if i < len(lines):
                    current_segment['timestamp'] = lines[i].strip()
                    i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip() != '':
                    text_lines.append(lines[i].strip())
                    i += 1
                current_segment['text'] = ' '.join(text_lines)
                segments.append(current_segment)
            else:
                i += 1
        return segments

    def segments_to_srt(self, segments: List[dict]) -> str:
        lines = []
        for seg in segments:
            lines.append(str(seg['index']))
            lines.append(seg['timestamp'])
            lines.append(seg['text'])
            lines.append('')
        return '\n'.join(lines).strip()

    def translate_file(
        self,
        srt_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Optional[Path]:
        # Tạo đường dẫn output
        output_path = get_output_path(srt_path, self.translated_dir)
        
        # Tạo thư mục output
        self.translated_dir.mkdir(parents=True, exist_ok=True)

        if output_path.exists() and output_path.stat().st_size > 0:
            if progress_callback:
                progress_callback(1, 1, f"Đã có sẵn: {output_path.name[:20]}")
            return output_path

        content = read_text_file(srt_path)
        if not content:
            return None

        segments = self.parse_srt(content)
        if not segments:
            logger.warning(f"Không parse được SRT: {srt_path}")
            return srt_path

        total = len(segments)
        translated_segments = []

        chunk_size = MAX_LINES_PER_CHUNK
        for start in range(0, total, chunk_size):
            end = min(start + chunk_size, total)
            chunk_segments = segments[start:end]
            chunk_text = '\n'.join(seg['text'] for seg in chunk_segments)

            if progress_callback:
                progress_callback(start, total, f"API dịch chunk {start//chunk_size +1}: dòng {start+1}-{end}")

            translated_text = self.translate_text(chunk_text)
            if not translated_text:
                logger.error(f"Dịch chunk {start//chunk_size +1} thất bại")
                return None

            translated_lines = translated_text.strip().split('\n')
            if len(translated_lines) == len(chunk_segments):
                for i, seg in enumerate(chunk_segments):
                    translated_segments.append({
                        'index': seg['index'],
                        'timestamp': seg['timestamp'],
                        'text': translated_lines[i].strip()
                    })
            else:
                logger.warning(f"Số dòng dịch không khớp ({len(translated_lines)} vs {len(chunk_segments)}) cho chunk {start//chunk_size +1}")
                for seg in chunk_segments:
                    translated_segments.append(seg.copy())

        final_content = self.segments_to_srt(translated_segments)
        final_content = format_srt_content(final_content)

        if not write_text_file(output_path, final_content):
            return None

        if progress_callback:
            progress_callback(total, total, f"Đã dịch API: {output_path.name[:20]}")
        return output_path

    def process_all(
        self,
        single_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        pattern: str = "*.srt",
        recursive: bool = False
    ) -> bool:
        if single_file:
            srt_files = [single_file] if single_file.exists() else []
            if not srt_files:
                # Tìm trong thư mục con
                srt_files = list(self.srt_dir.rglob(f"*{single_file.name}"))
        else:
            # Tìm tất cả file *_refined.srt trong các thư mục con
            srt_files = find_refined_srt_files(self.srt_dir)

        if not srt_files:
            if progress_callback:
                progress_callback(1, 1, "Không có file SRT")
            return False

        total_files = len(srt_files)
        success = 0
        for i, srt_file in enumerate(srt_files, 1):
            if progress_callback:
                progress_callback(i - 1, total_files, f"API Dịch {i}/{total_files}: {srt_file.name[:20]}")
            res = self.translate_file(srt_file, progress_callback=progress_callback)
            if res:
                success += 1

        return success > 0


# ====== GEMINI SELENIUM TRANSLATOR ======
class GeminiSeleniumTranslator(BaseTranslator):
    def __init__(self, srt_dir: Path, translated_dir: Path):
        self.srt_dir = srt_dir
        self.translated_dir = translated_dir
        self.headless = HEADLESS
        self.user_agent = USER_AGENT
        self.driver = None

    def _setup_driver(self):
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")

        if self.user_agent:
            chrome_options.add_argument(f"--user-agent={self.user_agent}")

        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        service = Service(ChromeDriverManager().install())
        service.log_path = os.devnull
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def _count_subtitle_lines(self, content: str) -> int:
        if not content:
            return 0
        pattern = r'^\d+\n\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}'
        return len(re.findall(pattern, content, re.MULTILINE))

    def _extract_subtitle_blocks(self, content: str) -> List[str]:
        if not content:
            return []
        pattern = r'(\d+\n\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}\n.*?)(?=\n\n\d+\n|\Z)'
        return re.findall(pattern, content, re.DOTALL)

    def _get_content_from_line(self, content: str, start_line: int) -> str:
        blocks = self._extract_subtitle_blocks(content)
        if start_line <= 1:
            return content
        if start_line > len(blocks):
            return ""
        return '\n\n'.join(blocks[start_line-1:])

    def _get_content_between_lines(self, content: str, start_line: int, end_line: int) -> str:
        blocks = self._extract_subtitle_blocks(content)
        total = len(blocks)
        if start_line < 1:
            start_line = 1
        if end_line > total:
            end_line = total
        if start_line > total or start_line > end_line:
            return ""
        return '\n\n'.join(blocks[start_line-1:end_line])

    def _set_input_text_js(self, input_area, text: str) -> bool:
        try:
            self.driver.execute_script("""
                const el = arguments[0];
                const text = arguments[1];
                el.focus();
                el.textContent = '';
                el.value = '';
                el.textContent = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                const range = document.createRange();
                const sel = window.getSelection();
                if (el.firstChild) {
                    range.setStartAfter(el.firstChild);
                    range.collapse(true);
                } else {
                    range.selectNodeContents(el);
                }
                sel.removeAllRanges();
                sel.addRange(range);
            """, input_area, text)
            content = self.driver.execute_script("return arguments[0].textContent || arguments[0].value || '';", input_area)
            return bool(content and len(content) > 10)
        except Exception:
            return False

    def _wait_for_gemini_complete(self, timeout=300, progress_callback=None, start_line=1, total_lines=1) -> str:
        time.sleep(5)
        start_time = time.time()
        last_content = ""
        stable_count = 0

        while time.time() - start_time < timeout:
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                response_divs = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    ".markdown.markdown-main-panel, .model-response-message-content, [class*='markdown-main-panel']"
                )

                if response_divs:
                    latest = response_divs[-1]
                    content = latest.text
                    loading = latest.find_elements(
                        By.CSS_SELECTOR,
                        ".loading, .typing, .skeleton, .animate-pulse, [aria-busy='true']"
                    )

                    if not loading and content and len(content) > 50:
                        if content == last_content:
                            stable_count += 1
                        else:
                            stable_count = 0
                            last_content = content

                        cur_lines = self._count_subtitle_lines(content)
                        if progress_callback:
                            progress_callback(min(start_line + cur_lines, total_lines), total_lines, f"Gemini trả lời: {cur_lines} dòng")

                        if stable_count >= 5:
                            return content
                    else:
                        if content and len(content) > len(last_content):
                            last_content = content
                        stable_count = 0
            except Exception:
                pass
            time.sleep(2)
        return last_content

    def translate_file(
        self,
        srt_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Optional[Path]:
        # Tạo đường dẫn output
        output_path = get_output_path(srt_path, self.translated_dir)
        
        # Tạo thư mục output
        self.translated_dir.mkdir(parents=True, exist_ok=True)

        if output_path.exists() and output_path.stat().st_size > 0:
            if progress_callback:
                progress_callback(1, 1, f"Đã có sẵn: {output_path.name[:20]}")
            return output_path

        if not self.driver:
            self._setup_driver()

        try:
            self.driver.get("https://gemini.google.com/app")
            time.sleep(5)

            original_content = read_text_file(srt_path)
            if not original_content:
                return None

            total_lines = self._count_subtitle_lines(original_content)
            if total_lines == 0:
                logger.warning(f"SRT không có dòng phụ đề: {srt_path}")
                return srt_path

            final_translated_blocks = []
            current_line = 1
            attempt = 0
            max_attempts = 999

            while current_line <= total_lines and attempt < max_attempts:
                attempt += 1
                end_line = min(current_line + MAX_LINES_PER_CHUNK - 1, total_lines)
                chunk_content = self._get_content_between_lines(original_content, current_line, end_line)
                if not chunk_content:
                    break

                if progress_callback:
                    progress_callback(current_line - 1, total_lines, f"Dịch dòng {current_line}-{end_line}")

                if attempt == 1:
                    full_text = f"{PROMPT_TEXT}\n\n---\n\nNội dung cần dịch:\n\n{chunk_content}"
                else:
                    full_text = f"Tiếp tục dịch từ dòng {current_line} đến {end_line}:\n\n{chunk_content}\n\nChỉ trả về phần dịch, giữ đúng định dạng SRT."

                input_area = None
                try:
                    input_area = self.driver.find_element(By.CSS_SELECTOR, ".ql-editor, [contenteditable='true']")
                except Exception:
                    try:
                        input_area = self.driver.find_element(By.CSS_SELECTOR, "textarea")
                    except Exception:
                        pass

                if not input_area or not self._set_input_text_js(input_area, full_text):
                    logger.error("Không thể nhập text vào Gemini")
                    break

                input_area.send_keys(Keys.ENTER)
                response_text = self._wait_for_gemini_complete(
                    timeout=300,
                    progress_callback=progress_callback,
                    start_line=current_line,
                    total_lines=total_lines
                )

                if not response_text:
                    logger.warning(f"Không nhận được phản hồi cho chunk {attempt}")
                    break

                blocks = self._extract_subtitle_blocks(response_text)
                if blocks:
                    valid_blocks = []
                    for block in blocks:
                        match = re.match(r'^(\d+)', block)
                        if match:
                            num = int(match.group(1))
                            if num >= current_line:
                                valid_blocks.append(block)
                    if valid_blocks:
                        final_translated_blocks.extend(valid_blocks)
                        last_block = valid_blocks[-1]
                        match = re.match(r'^(\d+)', last_block)
                        if match:
                            current_line = int(match.group(1)) + 1
                        else:
                            current_line += len(valid_blocks)
                    else:
                        logger.warning(f"Không tìm thấy block hợp lệ trong phản hồi (chunk {attempt})")
                        current_line = end_line + 1
                else:
                    logger.warning(f"Phản hồi không có block SRT (chunk {attempt})")
                    current_line = end_line + 1

                if current_line > total_lines:
                    break
                if current_line == end_line + 1:
                    pass
                else:
                    if current_line <= end_line:
                        current_line = end_line + 1

                time.sleep(3)

            final_content = '\n\n'.join(final_translated_blocks)
            final_content = format_srt_content(final_content)

            if not final_content:
                logger.error("Không có nội dung dịch nào")
                return None

            if not write_text_file(output_path, final_content):
                return None

            if progress_callback:
                progress_callback(total_lines, total_lines, f"Xong: {output_path.name[:20]}")
            return output_path

        except Exception as e:
            logger.error(f"❌ Lỗi Selenium translation: {e}")
            return None

    def process_all(
        self,
        single_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        pattern: str = "*.srt",
        recursive: bool = False
    ) -> bool:
        if single_file:
            srt_files = [single_file] if single_file.exists() else []
            if not srt_files:
                srt_files = list(self.srt_dir.rglob(f"*{single_file.name}"))
        else:
            srt_files = find_refined_srt_files(self.srt_dir)

        if not srt_files:
            if progress_callback:
                progress_callback(1, 1, "Không có file SRT nào")
            return False

        success = 0
        try:
            self._setup_driver()
            for i, srt_file in enumerate(srt_files, 1):
                res = self.translate_file(srt_file, progress_callback=progress_callback)
                if res:
                    success += 1
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None

        return success > 0


# ====== FACTORY ======
def get_translator(srt_dir: Path, translated_dir: Path) -> BaseTranslator:
    if ENGINE == "gemini_api":
        return GeminiApiTranslator(srt_dir, translated_dir)
    else:
        return GeminiSeleniumTranslator(srt_dir, translated_dir)


# ====== PUBLIC PROCESS FUNCTION ======
def process_all(
    single_file: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    srt_dir: Optional[Path] = None,
    translated_dir: Optional[Path] = None,
    pattern: str = "*.srt",
    recursive: bool = False
) -> bool:
    srt_dir = srt_dir or DEFAULT_SRT_DIR
    translated_dir = translated_dir or DEFAULT_TRANSLATED_DIR
    translator = get_translator(srt_dir, translated_dir)
    return translator.process_all(
        single_file=single_file,
        progress_callback=progress_callback,
        pattern=pattern,
        recursive=recursive
    )


# ====== MAIN ======
if __name__ == "__main__":
    DEFAULT_TRANSLATED_DIR.mkdir(parents=True, exist_ok=True)

    def console_progress(current, total, message):
        percent = (current / total * 100) if total > 0 else 0
        print(f"[{current}/{total}] ({percent:.1f}%) {message}")

    print("=== BẮT ĐẦU DỊCH PHỤ ĐỀ ===")
    print(f"Thư mục đầu vào: {DEFAULT_SRT_DIR}")
    print(f"Thư mục đầu ra:  {DEFAULT_TRANSLATED_DIR}")
    print(f"Engine: {ENGINE.upper()}")
    print(f"Số dòng mỗi lần dịch: {MAX_LINES_PER_CHUNK}")
    print("-" * 50)

    # Nếu có tham số dòng lệnh, dịch file cụ thể
    if len(sys.argv) > 1:
        file_spec = sys.argv[1]
        srt_file = Path(file_spec)
        if not srt_file.exists():
            # Tìm trong thư mục mặc định
            found = list(DEFAULT_SRT_DIR.rglob(f"*{file_spec}"))
            if found:
                srt_file = found[0]
            else:
                print(f"❌ Không tìm thấy file: {file_spec}")
                sys.exit(1)
        
        print(f"📄 Dịch file: {srt_file.name}")
        success = process_all(
            single_file=srt_file,
            srt_dir=DEFAULT_SRT_DIR,
            translated_dir=DEFAULT_TRANSLATED_DIR,
            progress_callback=console_progress
        )
    else:
        # Mặc định: tìm tất cả file *_refined.srt trong các thư mục con
        print("📂 Tìm và dịch tất cả file *_refined.srt...")
        srt_files = find_refined_srt_files(DEFAULT_SRT_DIR)
        
        if not srt_files:
            print("❌ Không tìm thấy file nào cần dịch.")
            sys.exit(1)

        print(f"📄 Tìm thấy {len(srt_files)} file:")
        for f in srt_files:
            print(f"   - {f.relative_to(DEFAULT_SRT_DIR)}")

        # Dịch từng file
        success_count = 0
        for idx, srt_file in enumerate(srt_files, 1):
            print(f"\n[{idx}/{len(srt_files)}] Đang dịch: {srt_file.name}")
            res = process_all(
                single_file=srt_file,
                srt_dir=DEFAULT_SRT_DIR,
                translated_dir=DEFAULT_TRANSLATED_DIR,
                progress_callback=console_progress
            )
            if res:
                success_count += 1
                # Kiểm tra file output đã được tạo
                output_path = get_output_path(srt_file, DEFAULT_TRANSLATED_DIR)
                if output_path.exists():
                    print(f"✅ Đã tạo: {output_path.relative_to(BASE_DIR)}")
                else:
                    print(f"⚠️ Không tìm thấy file output: {output_path.name}")

        success = success_count > 0

    if success:
        print(f"\n✅ Dịch hoàn tất! Kiểm tra thư mục: {DEFAULT_TRANSLATED_DIR}")
    else:
        print("\n❌ Không có file nào được dịch hoặc có lỗi xảy ra.")