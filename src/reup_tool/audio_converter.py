# src/reup_tool/audio_converter.py
import os
import time
import logging
from pathlib import Path
from typing import Optional, Callable
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests

from reup_tool.config import config

logger = logging.getLogger(__name__)


class ConvertioMP4ToAudio:
    def __init__(self, download_dir: Path, headless: bool = True, vbr_quality: int = 5):
        self.download_dir = download_dir
        self.headless = headless
        self.vbr_quality = vbr_quality
        self.driver = None
        self.wait = None

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        user_agent = config.translator.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        chrome_options.add_argument(f"--user-agent={user_agent}")

        if self.headless:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

        prefs = {
            "download.default_directory": str(self.download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 30)

    def open_website(self):
        try:
            logger.info("Đang mở trang web Convertio...")
            self.driver.get("https://convertio.co/vn/")
            time.sleep(5)
            return True
        except Exception as e:
            logger.error(f"Lỗi khi mở trang web: {e}")
            return False

    def upload_file(self, file_path):
        try:
            logger.info(f"Đang upload file: {Path(file_path).name}")
            upload_label = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "label[for='pc-upload-add']"))
            )
            self.driver.execute_script("arguments[0].click();", upload_label)
            time.sleep(2)

            file_input = self.driver.find_element(By.ID, "pc-upload-add")
            file_input.send_keys(str(file_path))
            time.sleep(8)
            logger.info("✓ Upload file thành công")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi upload file: {e}")
            return False

    def select_mp3_format(self):
        try:
            logger.info("Đang chọn định dạng MP3...")
            format_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-toggle='dropdown'].btn-caret"))
            )
            self.driver.execute_script("arguments[0].click();", format_btn)
            time.sleep(2)

            try:
                audio_tab = self.driver.find_element(By.XPATH, "//li[contains(text(), 'Âm thanh')]")
                self.driver.execute_script("arguments[0].click();", audio_tab)
                time.sleep(1)
            except Exception:
                pass

            mp3_option = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//li/span[text()='MP3']"))
            )
            self.driver.execute_script("arguments[0].click();", mp3_option)
            time.sleep(3)
            logger.info("✓ Đã chọn định dạng MP3")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi chọn định dạng MP3: {e}")
            return False

    def configure_settings(self):
        try:
            logger.info("Đang cấu hình cài đặt...")
            settings_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-settings"))
            )
            self.driver.execute_script("arguments[0].click();", settings_btn)
            time.sleep(2)

            try:
                vbr_dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "audio_qscale_mp3SelectBoxIt"))
                )
                self.driver.execute_script("arguments[0].click();", vbr_dropdown)
                time.sleep(1)

                vbr_option = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//li[@data-id='{self.vbr_quality}']"))
                )
                self.driver.execute_script("arguments[0].click();", vbr_option)
                time.sleep(1)
                logger.info(f"✓ Đã chọn VBR quality: {self.vbr_quality}")
            except Exception as e:
                logger.warning(f"Không thể chọn VBR: {e}")

            ok_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Ok')]"))
            )
            self.driver.execute_script("arguments[0].click();", ok_btn)
            time.sleep(2)
            logger.info("✓ Đã lưu cài đặt")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi cấu hình: {e}")
            return False

    def start_conversion(self):
        try:
            logger.info("Đang click nút Chuyển đổi...")
            methods = [
                lambda: self.driver.find_element(By.XPATH, "//button[contains(@class, 'btn-primary') and contains(text(), 'Chuyển đổi')]"),
                lambda: self.driver.find_element(By.CSS_SELECTOR, "div.convert-button button.btn.btn-xl.btn-primary"),
                lambda: next(btn for btn in self.driver.find_elements(By.TAG_NAME, "button") if "Chuyển đổi" in btn.text)
            ]

            for i, method in enumerate(methods, 1):
                try:
                    convert_btn = method()
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", convert_btn)
                    time.sleep(1)
                    self.driver.execute_script("arguments[0].click();", convert_btn)
                    logger.info(f"✓ Đã click nút Chuyển đổi (Cách {i})")
                    return True
                except Exception:
                    continue

            logger.error("Không thể click nút Chuyển đổi")
            return False

        except Exception as e:
            logger.error(f"Lỗi khi click nút Chuyển đổi: {e}")
            return False

    def wait_for_download_link(self, timeout=600):
        try:
            logger.info("Đang đợi file chuyển đổi hoàn tất...")
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    download_link = self.driver.find_element(By.CSS_SELECTOR, "a.btn-blue[href*='.mp3']")
                    if download_link:
                        href = download_link.get_attribute("href")
                        logger.info("✓ Đã tìm thấy link tải về")
                        return href
                except Exception:
                    pass
                time.sleep(5)

            logger.error("Timeout: Không tìm thấy link tải về")
            return None
        except Exception as e:
            logger.error(f"Lỗi khi đợi link tải: {e}")
            return None

    def download_file(self, url, filename):
        try:
            logger.info(f"Đang tải file: {filename}")
            file_path = self.download_dir / filename

            if file_path.exists() and file_path.stat().st_size > 0:
                logger.info(f"✓ File đã tồn tại: {file_path}")
                return str(file_path)

            response = requests.get(url, stream=True)
            response.raise_for_status()

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if file_path.exists() and file_path.stat().st_size > 0:
                logger.info(f"✓ Đã tải xong: {file_path}")
                return str(file_path)
            else:
                return None
        except Exception as e:
            logger.error(f"Lỗi khi tải file: {e}")
            return None

    def process_file(self, mp4_path: Path):
        try:
            mp4_path = Path(mp4_path)
            mp3_filename = mp4_path.stem + ".mp3"
            mp3_path = self.download_dir / mp3_filename

            if mp3_path.exists() and mp3_path.stat().st_size > 0:
                logger.info(f"✓ File {mp3_filename} đã tồn tại, bỏ qua")
                return str(mp3_path)

            if not self.open_website():
                return None
            if not self.upload_file(str(mp4_path)):
                return None
            if not self.select_mp3_format():
                return None
            if not self.configure_settings():
                return None
            if not self.start_conversion():
                return None

            download_url = self.wait_for_download_link()
            if not download_url:
                return None

            return self.download_file(download_url, mp3_filename)

        except Exception as e:
            logger.error(f"Lỗi xử lý file: {e}")
            return None

    def close(self):
        if self.driver:
            self.driver.quit()
            logger.info("Đã đóng trình duyệt")


def process_all(
    single_file: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> bool:
    video_dir = config.paths.video_dir
    audio_dir = config.paths.audio_dir

    if single_file:
        mp4_files = [Path(single_file)]
    else:
        mp4_files = list(video_dir.glob("*.mp4"))

    if not mp4_files:
        logger.warning(f"⚠️ Không tìm thấy file MP4 nào trong: {video_dir}")
        if progress_callback:
            progress_callback(1, 1, "Không có file MP4 nào")
        return False

    total_files = len(mp4_files)
    converter = ConvertioMP4ToAudio(
        audio_dir,
        headless=config.audio_converter.headless,
        vbr_quality=config.audio_converter.vbr_quality
    )

    try:
        converter.setup_driver()
        success = 0

        for i, mp4_file in enumerate(mp4_files, 1):
            if progress_callback:
                progress_callback(i - 1, total_files, f"Xử lý {i}/{total_files}: {mp4_file.name[:20]}")

            mp3_path = audio_dir / (mp4_file.stem + ".mp3")
            if mp3_path.exists() and mp3_path.stat().st_size > 0:
                logger.info(f"⏭ File {mp3_path.name} đã tồn tại, bỏ qua")
                success += 1
                if progress_callback:
                    progress_callback(i, total_files, f"Đã có sẵn: {mp3_path.name[:20]}")
                continue

            result = converter.process_file(mp4_file)
            if result:
                success += 1
                if progress_callback:
                    progress_callback(i, total_files, f"Thành công: {Path(result).name[:20]}")
            else:
                if progress_callback:
                    progress_callback(i, total_files, f"Thất bại: {mp4_file.name[:20]}")

        return (success > 0)
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        return False
    finally:
        converter.close()
