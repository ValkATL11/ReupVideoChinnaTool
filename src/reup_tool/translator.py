# src/reup_tool/translator.py
import os
import re
import time
import logging
from pathlib import Path
from typing import Optional, List, Callable
from google import genai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from reup_tool.config import config
from reup_tool.utils import read_text_file

logger = logging.getLogger(__name__)


class BaseTranslator:
    def translate_file(
        self,
        srt_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Optional[Path]:
        raise NotImplementedError("Subclasses must implement translate_file")

    def process_all(self, single_file: Optional[Path] = None, progress_callback: Optional[Callable[[int, int, str], None]] = None) -> bool:
        raise NotImplementedError("Subclasses must implement process_all")


class GeminiApiTranslator(BaseTranslator):
    def __init__(self):
        self.api_keys: List[str] = config.gemini_api_keys
        self.current_key_index = 0
        self.client = None
        self.key_error_counts = {key: 0 for key in self.api_keys}
        self.max_errors_per_key = 2
        self.available = bool(self.api_keys)
        self.total_tokens = 0
        self.model = "models/gemini-3.6-flash"

        if self.available:
            self._init_client()
        else:
            logger.warning("⚠️ No Gemini API keys available in environment")

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
            prompt_header = config.translator.prompt_text
            if prompt_header:
                prompt = f"{prompt_header}\n\nNội dung cần dịch:\n\n{text}"
            else:
                prompt = f"Translate Chinese to Vietnamese. Keep line count.\n\nChinese:\n{text}\n\nVietnamese:"

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
            if self.api_keys:
                current_key = self.api_keys[self.current_key_index]
                self.key_error_counts[current_key] += 1
                if self.key_error_counts[current_key] >= self.max_errors_per_key:
                    if self._switch_key():
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

    def translate_file(
        self,
        srt_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Optional[Path]:
        translated_dir = config.paths.translated_dir
        output_file = translated_dir / f"{srt_path.stem}_vi.srt"

        if output_file.exists() and output_file.stat().st_size > 0:
            if progress_callback:
                progress_callback(1, 1, f"Đã có sẵn: {output_file.name[:20]}")
            return output_file

        content = read_text_file(srt_path)

        segments = self.parse_srt(content)
        if not segments:
            return srt_path

        texts = [seg['text'] for seg in segments]
        full_text = '\n'.join(texts)

        if progress_callback:
            progress_callback(1, 2, f"Gửi API Gemini ({len(texts)} câu)...")

        translated_text = self.translate_text(full_text)
        if not translated_text:
            return None

        translated_lines = translated_text.strip().split('\n')
        if len(translated_lines) == len(segments):
            new_srt = []
            for i, seg in enumerate(segments):
                new_srt.append(str(seg['index']))
                new_srt.append(seg['timestamp'])
                new_srt.append(translated_lines[i].strip())
                new_srt.append('')
            final_content = '\n'.join(new_srt)
        else:
            final_content = content

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_content)

        if progress_callback:
            progress_callback(2, 2, f"Đã dịch API: {output_file.name[:20]}")

        return output_file

    def process_all(
        self,
        single_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        input_dir = config.paths.srt_dir
        # single_file là đường dẫn .mp4 (video gốc) — phải rút stem rồi tìm .srt,
        # KHÔNG dùng trực tiếp làm path SRT.
        if single_file:
            stem = Path(single_file).stem
            srt_files = list(input_dir.glob(f"{stem}.srt"))
            if not srt_files:
                srt_files = list(input_dir.glob(f"{stem}*.srt"))
        else:
            srt_files = list(input_dir.glob("*.srt"))

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

        return (success > 0)


class GeminiSeleniumTranslator(BaseTranslator):
    def __init__(self):
        self.headless = config.translator.headless
        self.user_agent = config.translator.user_agent
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
        translated_dir = config.paths.translated_dir
        output_file = translated_dir / f"{srt_path.stem}_vi.srt"

        if output_file.exists() and output_file.stat().st_size > 0:
            if progress_callback:
                progress_callback(1, 1, f"Đã có sẵn: {output_file.name[:20]}")
            return output_file

        if not self.driver:
            self._setup_driver()

        try:
            self.driver.get("https://gemini.google.com/app")
            time.sleep(5)

            original_content = read_text_file(srt_path)

            original_line_count = self._count_subtitle_lines(original_content)
            translated_content = ""
            translated_line_count = 0
            start_line = 1
            attempt = 1
            max_attempts = 20

            prompt_base = config.translator.prompt_text

            while translated_line_count < original_line_count and attempt <= max_attempts:
                if progress_callback:
                    progress_callback(translated_line_count, max(original_line_count, 1), f"Dịch dòng {start_line}/{original_line_count}")

                content_to_translate = self._get_content_from_line(original_content, start_line)
                if not content_to_translate:
                    break

                if attempt == 1:
                    full_text = f"{prompt_base}\n\n---\n\nNội dung cần dịch:\n\n{content_to_translate}"
                else:
                    full_text = f"Vui lòng tiếp tục dịch từ dòng {start_line} đến hết:\n\n{content_to_translate}\n\nChỉ trả về phần dịch từ dòng {start_line} đến hết, giữ đúng định dạng SRT."

                input_area = None
                try:
                    input_area = self.driver.find_element(By.CSS_SELECTOR, ".ql-editor, [contenteditable='true']")
                except Exception:
                    try:
                        input_area = self.driver.find_element(By.CSS_SELECTOR, "textarea")
                    except Exception:
                        pass

                if not input_area or not self._set_input_text_js(input_area, full_text):
                    break

                input_area.send_keys(Keys.ENTER)
                response_text = self._wait_for_gemini_complete(
                    timeout=300,
                    progress_callback=progress_callback,
                    start_line=start_line,
                    total_lines=original_line_count
                )

                if not response_text:
                    break

                if attempt == 1:
                    translated_content = response_text
                else:
                    blocks = self._extract_subtitle_blocks(response_text)
                    new_blocks = []
                    for block in blocks:
                        match = re.match(r'^(\d+)', block)
                        if match:
                            block_num = int(match.group(1))
                            if block_num >= start_line:
                                new_blocks.append(block)
                    if new_blocks:
                        translated_content = translated_content + '\n\n' + '\n\n'.join(new_blocks)
                    else:
                        translated_content = response_text

                translated_line_count = self._count_subtitle_lines(translated_content)
                if translated_line_count >= original_line_count:
                    break

                blocks = self._extract_subtitle_blocks(translated_content)
                if blocks:
                    last_block = blocks[-1]
                    match = re.match(r'^(\d+)', last_block)
                    if match:
                        start_line = int(match.group(1)) + 1
                    else:
                        start_line = translated_line_count + 1
                else:
                    start_line = translated_line_count + 1

                attempt += 1
                time.sleep(3)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(translated_content)

            if progress_callback:
                progress_callback(original_line_count, max(original_line_count, 1), f"Xong: {output_file.name[:20]}")
            return output_file

        except Exception as e:
            logger.error(f"❌ Lỗi Selenium translation: {e}")
            return None

    def process_all(
        self,
        single_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        input_dir = config.paths.srt_dir
        # single_file là đường dẫn .mp4 (video gốc) — phải rút stem rồi tìm .srt,
        # KHÔNG dùng trực tiếp làm path SRT.
        if single_file:
            stem = Path(single_file).stem
            srt_files = list(input_dir.glob(f"{stem}.srt"))
            if not srt_files:
                srt_files = list(input_dir.glob(f"{stem}*.srt"))
        else:
            srt_files = list(input_dir.glob("*.srt"))

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

        return (success > 0)


def get_translator() -> BaseTranslator:
    engine = config.translator.engine.lower()
    if engine == "gemini_api":
        return GeminiApiTranslator()
    else:
        return GeminiSeleniumTranslator()


def process_all(
    single_file: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> bool:
    translator = get_translator()
    return translator.process_all(single_file=single_file, progress_callback=progress_callback)
