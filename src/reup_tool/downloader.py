"""
downloader.py
-------------
Automates video downloading from Douyin / TikTok via the SnapWC web service.

Flow:
  1. Open https://snapwc.com/vi with a headless Chrome instance.
  2. Submit the user-provided video URL.
  3. Click the highest-quality download button.
  4. Wait for the embedded iframe to report "Tải xuống hoàn tất."
  5. Locate the downloaded .mp4 file in assets/original_video/ and return its path.

If the browser download does not produce a file, the module falls back to
extracting the direct .mp4 URL from the page source and downloading it via
requests with a streaming write.

Configuration is read from `config.downloader` (headless mode, user-agent).
"""

import re
import time
import logging
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from reup_tool.config import config

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[int, int, str], None]]


# ---------------------------------------------------------------------------
# Core download function
# ---------------------------------------------------------------------------

def download_douyin_video(
    url: str,
    output_dir: Optional[Path] = None,
    progress_callback: ProgressCallback = None,
) -> Tuple[str, str]:
    """
    Download a Douyin / TikTok video using Selenium-controlled Chrome via SnapWC.

    Args:
        url:               Full Douyin or TikTok share URL.
        output_dir:        Target directory for the downloaded file.
                           Defaults to config.paths.video_dir.
        progress_callback: Optional callable(current, total, detail) for
                           real-time progress reporting.

    Returns:
        Tuple of (absolute_file_path, filename).

    Raises:
        Exception: propagated with a descriptive message on failure.
    """

    def _notify(cur: int, tot: int, msg: str) -> None:
        if progress_callback:
            progress_callback(cur, tot, msg)

    output_dir = Path(output_dir) if output_dir else config.paths.video_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting Douyin/TikTok download via SnapWC")
    logger.info("URL: %s", url[:120])
    logger.info("Output directory: %s", output_dir)

    # --- Chrome options ---
    options = Options()
    if config.downloader.headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    if config.downloader.user_agent:
        options.add_argument(f"user-agent={config.downloader.user_agent}")

    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(output_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )

    driver = None
    original_tab = None

    try:
        _notify(1, 7, "Khởi tạo trình duyệt...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 90)
        original_tab = driver.current_window_handle

        # Step 1 – Open SnapWC
        _notify(1, 7, "Đang mở SnapWC...")
        driver.get("https://snapwc.com/vi")
        time.sleep(2)
        logger.info("SnapWC loaded")

        # Step 2 – Input URL
        _notify(2, 7, "Đang nhập URL...")
        field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
        field.clear()
        field.send_keys(url)
        time.sleep(1)

        # Step 3 – Submit
        _notify(3, 7, "Lấy liên kết tải xuống...")
        btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
        driver.execute_script("arguments[0].click();", btn)

        # Step 4 – Wait for result card
        _notify(4, 7, "Đang xử lý kết quả...")
        time.sleep(5)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.result-card, div.macos-result-card")))
        time.sleep(2)

        # Step 5 – Click highest-quality download button
        _notify(5, 7, "Click nút tải video...")
        dl_buttons = driver.find_elements(
            By.XPATH,
            "//button[.//i[contains(text(),'file_download')] and .//span[contains(text(),'Tải xuống')]]",
        )
        if not dl_buttons:
            raise RuntimeError("Download button not found on SnapWC result page.")

        last_btn = dl_buttons[-1]
        driver.execute_script("arguments[0].scrollIntoView(true);", last_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", last_btn)

        # Step 6 – Close any popup tabs
        _notify(6, 7, "Kiểm tra tab tải...")
        for tab in driver.window_handles:
            if tab != original_tab:
                driver.switch_to.window(tab)
                driver.close()
        driver.switch_to.window(original_tab)

        # Step 7 – Wait for iframe completion signal
        _notify(7, 7, "Đang tải video hoàn tất...")
        try:
            iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.iframe-download-frame")))
            driver.switch_to.frame(iframe)
            try:
                wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(),'Tải xuống hoàn tất')]")))
                logger.info("Download completion signal received from iframe.")
            except Exception:
                logger.warning("Completion signal not detected in iframe; waiting 10 s as fallback.")
                time.sleep(10)
            driver.switch_to.default_content()
        except Exception:
            logger.warning("iframe not found; waiting 10 s as fallback.")
            time.sleep(10)

        time.sleep(2)

        # Locate the newly downloaded mp4
        mp4_files = [f for f in output_dir.iterdir() if f.suffix == ".mp4"]
        if mp4_files:
            latest = max(mp4_files, key=lambda f: f.stat().st_ctime)
            driver.quit()
            size_mb = latest.stat().st_size / (1024 * 1024)
            logger.info("Downloaded: %s (%.2f MB)", latest.name, size_mb)
            _notify(7, 7, f"Đã tải: {latest.name[:24]}")
            return str(latest), latest.name

        # Fallback – extract direct mp4 URL from page HTML
        logger.info("No file found via browser download; attempting direct URL extraction.")
        html = driver.page_source
        mp4_urls = re.findall(r'https://[^\s"\']+\.mp4[^\s"\']*', html)
        if mp4_urls:
            headers = {
                "User-Agent": config.downloader.user_agent or "Mozilla/5.0",
                "Referer": "https://snapwc.com/vi",
            }
            resp = requests.get(mp4_urls[0], headers=headers, stream=True, timeout=120)
            resp.raise_for_status()
            filename = f"douyin_{int(time.time())}.mp4"
            video_path = output_dir / filename
            with open(video_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            driver.quit()
            logger.info("Downloaded via fallback URL: %s", filename)
            _notify(7, 7, f"Đã tải (fallback): {filename[:24]}")
            return str(video_path), filename

        raise RuntimeError("Could not locate a downloadable .mp4 file or URL on the page.")

    except Exception as exc:
        if driver:
            driver.quit()
        raise RuntimeError(f"download_douyin_video failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def process_all(url: Optional[str] = None, progress_callback: ProgressCallback = None) -> bool:
    """
    Pipeline entry point called by main.py.

    If a URL is supplied the video is downloaded into assets/original_video/.
    If no URL is supplied this step is skipped and True is returned so that
    the pipeline continues with videos already present in the directory.

    Args:
        url:               Douyin / TikTok share URL, or None to skip.
        progress_callback: Forwarded to download_douyin_video.

    Returns:
        True on success or skip, False on failure.
    """
    if not url:
        logger.info("No URL provided — skipping download step.")
        if progress_callback:
            progress_callback(1, 1, "Bỏ qua (dùng video có sẵn)")
        return True

    try:
        download_douyin_video(url, progress_callback=progress_callback)
        return True
    except Exception as exc:
        logger.error("Download failed: %s", exc)
        return False
