"""
downloader.py - Video Downloader Module
========================================
A standalone module for downloading videos from Douyin / TikTok via SnapWC.
"""

import re
import time
import json
import logging
import secrets
import string
import base64
import urllib.parse
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple, Dict, Any

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class DownloaderConfig:
    """Configuration class for the downloader module."""
    
    def __init__(
        self,
        headless: bool = True,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        output_dir: Optional[Path] = None,
        snapwc_url: str = "https://snapwc.com/vi",
        wait_timeout: int = 90,
        download_timeout: int = 120,
        project_id_file: Optional[Path] = None
    ):
        self.headless = headless
        self.user_agent = user_agent
        self.output_dir = Path(output_dir) if output_dir else Path.cwd() / "original_videos"
        self.snapwc_url = snapwc_url
        self.wait_timeout = wait_timeout
        self.download_timeout = download_timeout
        self.project_id_file = project_id_file


# ---------------------------------------------------------------------------
# Project ID Manager
# ---------------------------------------------------------------------------

class ProjectIDManager:
    """Manages project IDs for consistent file naming."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path.cwd() / ".project_id"
        self._project_id: Optional[str] = None
    
    def generate(self) -> str:
        """Generate a new project ID."""
        date_str = datetime.now().strftime("%y%m%d")
        chars = string.ascii_uppercase + string.digits
        random_str = ''.join(secrets.choice(chars) for _ in range(4))
        return f"PRJ-{date_str}-{random_str}"
    
    def get(self) -> str:
        """Get or create a project ID."""
        if self._project_id:
            return self._project_id
        
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    self._project_id = f.read().strip()
                    return self._project_id
            except Exception:
                pass
        
        self._project_id = self.generate()
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'w') as f:
                f.write(self._project_id)
        except Exception:
            pass
        
        return self._project_id


# ---------------------------------------------------------------------------
# YouTube-DLP Downloader
# ---------------------------------------------------------------------------

class YTDLPDownloader:
    """Download videos using yt-dlp."""
    
    def __init__(self, output_dir: Path, project_id: str):
        self.output_dir = output_dir
        self.project_id = project_id
        self.logger = logging.getLogger(__name__)
    
    def _check_ytdlp_installed(self) -> bool:
        """Check if yt-dlp is installed."""
        try:
            subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            self.logger.warning("yt-dlp is not installed. Please install: pip install yt-dlp")
            return False
    
    def download(self, url: str) -> Optional[Path]:
        """
        Download video using yt-dlp.
        
        Returns:
            Path to downloaded file or None if failed.
        """
        if not self._check_ytdlp_installed():
            return None
        
        try:
            self.logger.info(f"Downloading with yt-dlp: {url[:100]}...")
            
            # Temporary filename
            temp_filename = f"{self.project_id}_temp.%(ext)s"
            temp_path = self.output_dir / temp_filename
            
            # yt-dlp command
            cmd = [
                "yt-dlp",
                "-o", str(temp_path),
                "--no-playlist",
                "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--no-warnings",
                "--quiet",
                url
            ]
            
            # Run yt-dlp
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.download_timeout if hasattr(self, 'config') else 300
            )
            
            if result.returncode != 0:
                self.logger.error(f"yt-dlp failed: {result.stderr}")
                return None
            
            # Find downloaded file
            downloaded_files = list(self.output_dir.glob(f"{self.project_id}_temp.*"))
            if not downloaded_files:
                self.logger.error("No file downloaded by yt-dlp")
                return None
            
            # Get the downloaded file
            temp_file = downloaded_files[0]
            
            # Rename to final format
            extension = temp_file.suffix
            final_name = f"{self.project_id}_Ovideo{extension}"
            final_path = self.output_dir / final_name
            
            # Remove existing file if any
            if final_path.exists():
                final_path.unlink()
            
            # Rename
            temp_file.rename(final_path)
            
            self.logger.info(f"Downloaded with yt-dlp: {final_name}")
            return final_path
            
        except subprocess.TimeoutExpired:
            self.logger.error("yt-dlp download timeout")
            return None
        except Exception as e:
            self.logger.error(f"yt-dlp download failed: {e}")
            return None


# ---------------------------------------------------------------------------
# Selenium Downloader (for Douyin/TikTok)
# ---------------------------------------------------------------------------

class SeleniumDownloader:
    """Download videos using Selenium (for Douyin/TikTok)."""
    
    def __init__(self, config: DownloaderConfig, project_id: str):
        self.config = config
        self.project_id = project_id
        self.logger = logging.getLogger(__name__)
    
    def _notify(self, current: int, total: int, message: str) -> None:
        """Send progress notification."""
        if hasattr(self, 'progress_callback') and self.progress_callback:
            self.progress_callback(current, total, message)
    
    def download(self, url: str) -> Optional[Path]:
        """Download Douyin/TikTok video using Selenium."""
        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("Downloading with Selenium (Douyin/TikTok)")
        
        # Chrome options
        options = Options()
        if self.config.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,720")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        if self.config.user_agent:
            options.add_argument(f"user-agent={self.config.user_agent}")
        
        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": str(output_dir.absolute()),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "profile.default_content_setting_values.automatic_downloads": 1,
            },
        )
        
        driver = None
        original_tab = None
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, self.config.wait_timeout)
            original_tab = driver.current_window_handle
            
            # Step 1 – Open SnapWC
            driver.get(self.config.snapwc_url)
            time.sleep(2)
            
            # Step 2 – Input URL
            field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
            field.clear()
            field.send_keys(url)
            time.sleep(1)
            
            # Step 3 – Submit
            btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
            driver.execute_script("arguments[0].click();", btn)
            
            # Step 4 – Wait for result card
            time.sleep(5)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.result-card, div.macos-result-card")))
            time.sleep(2)
            
            # Step 5 – Click download button
            dl_buttons = driver.find_elements(
                By.XPATH,
                "//button[.//i[contains(text(),'file_download')] and .//span[contains(text(),'Tải xuống')]]",
            )
            if not dl_buttons:
                dl_buttons = driver.find_elements(
                    By.XPATH,
                    "//button[.//span[contains(text(),'Tải xuống')]]",
                )
            
            if not dl_buttons:
                raise RuntimeError("Download button not found")
            
            last_btn = dl_buttons[-1]
            driver.execute_script("arguments[0].scrollIntoView(true);", last_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", last_btn)
            
            # Step 6 – Close popup tabs
            for tab in driver.window_handles:
                if tab != original_tab:
                    driver.switch_to.window(tab)
                    driver.close()
            driver.switch_to.window(original_tab)
            
            # Step 7 – Handle iframe
            try:
                iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.iframe-download-frame")))
                driver.switch_to.frame(iframe)
                time.sleep(2)
                
                try:
                    start_btn = driver.find_element(
                        By.XPATH, 
                        "//span[contains(text(), 'Bắt đầu tải xuống')]"
                    )
                    driver.execute_script("arguments[0].click();", start_btn)
                    self.logger.info("Clicked 'Bắt đầu tải xuống'")
                    time.sleep(2)
                except Exception:
                    pass
                
                try:
                    wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(text(), 'Tải xuống hoàn tất')]")
                    ))
                    self.logger.info("Download complete")
                    time.sleep(3)
                except Exception:
                    time.sleep(10)
                
                driver.switch_to.default_content()
                
            except Exception as e:
                self.logger.warning(f"Iframe handling failed: {e}")
                driver.switch_to.default_content()
            
            # Step 8 – Find downloaded file
            time.sleep(3)
            
            mp4_files = [f for f in output_dir.iterdir() if f.suffix == ".mp4"]
            if mp4_files:
                latest = max(mp4_files, key=lambda f: f.stat().st_ctime)
                
                # Rename to format: PRJ-YYMMDD-XXXX_Ovideo.mp4
                final_name = f"{self.project_id}_Ovideo.mp4"
                final_path = output_dir / final_name
                
                if latest.name != final_name:
                    if final_path.exists():
                        final_path.unlink()
                    latest.rename(final_path)
                else:
                    final_path = latest
                
                driver.quit()
                size_mb = final_path.stat().st_size / (1024 * 1024)
                self.logger.info("Downloaded: %s (%.2f MB)", final_name, size_mb)
                return final_path
            
            # Fallback: extract from page
            html = driver.page_source
            
            # Try from iframe payload
            try:
                iframe = driver.find_element(By.CSS_SELECTOR, "iframe.iframe-download-frame")
                src = iframe.get_attribute("src")
                if src and "payload=" in src:
                    payload = src.split("payload=")[1]
                    payload = urllib.parse.unquote(payload)
                    missing_padding = len(payload) % 4
                    if missing_padding:
                        payload += '=' * (4 - missing_padding)
                    payload = payload.replace('-', '+').replace('_', '/')
                    decoded = base64.b64decode(payload).decode('utf-8')
                    data = json.loads(decoded)
                    
                    video_url = None
                    if "item" in data and "url" in data["item"]:
                        video_url = data["item"]["url"]
                    elif "url" in data:
                        video_url = data["url"]
                    
                    if video_url:
                        headers = {
                            "User-Agent": self.config.user_agent or "Mozilla/5.0",
                            "Referer": self.config.snapwc_url,
                            "Accept": "video/mp4,video/webm,video/*,*/*",
                        }
                        resp = requests.get(video_url, headers=headers, stream=True, timeout=self.config.download_timeout)
                        resp.raise_for_status()
                        
                        filename = f"{self.project_id}_Ovideo.mp4"
                        video_path = output_dir / filename
                        
                        with open(video_path, "wb") as fh:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:
                                    fh.write(chunk)
                        
                        driver.quit()
                        return video_path
            except Exception:
                pass
            
            # Final fallback: regex
            mp4_urls = re.findall(r'https://[^\s"\']+\.mp4[^\s"\']*', html)
            mp4_urls = [u for u in mp4_urls if 'snapwc' not in u and 'google' not in u]
            
            if mp4_urls:
                headers = {
                    "User-Agent": self.config.user_agent or "Mozilla/5.0",
                    "Referer": self.config.snapwc_url,
                }
                resp = requests.get(mp4_urls[0], headers=headers, stream=True, timeout=self.config.download_timeout)
                resp.raise_for_status()
                
                filename = f"{self.project_id}_Ovideo.mp4"
                video_path = output_dir / filename
                
                with open(video_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
                
                driver.quit()
                return video_path
            
            raise RuntimeError("Could not locate downloadable file")
            
        except Exception as exc:
            if driver:
                driver.quit()
            self.logger.error(f"Selenium download failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Main Downloader
# ---------------------------------------------------------------------------

class VideoDownloader:
    """Main downloader class with auto-detection and fallback."""
    
    def __init__(
        self,
        config: Optional[DownloaderConfig] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ):
        self.config = config or DownloaderConfig()
        self.progress_callback = progress_callback
        self.logger = logging.getLogger(__name__)
        self.project_manager = ProjectIDManager(self.config.project_id_file)
        
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
    
    def _notify(self, current: int, total: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def _is_douyin_or_tiktok(self, url: str) -> bool:
        """Check if URL is from Douyin or TikTok."""
        patterns = [
            r'douyin\.com',
            r'tiktok\.com',
            r'vm\.tiktok',
            r'www\.douyin',
            r'iesdouyin\.com',
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns)
    
    def download(self, url: str) -> Dict[str, Any]:
        """
        Download video with auto-detection and fallback.
        
        - If Douyin/TikTok: Use Selenium (primary), fallback to yt-dlp
        - Other platforms: Use yt-dlp (primary), fallback to Selenium
        """
        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        project_id = self.project_manager.get()
        
        self.logger.info("=" * 60)
        self.logger.info("Starting video download")
        self.logger.info("URL: %s", url[:120])
        self.logger.info("Output directory: %s", output_dir)
        self.logger.info("Project ID: %s", project_id)
        self.logger.info("=" * 60)
        
        is_douyin = self._is_douyin_or_tiktok(url)
        self.logger.info(f"Platform: {'Douyin/TikTok' if is_douyin else 'Other'}")
        
        downloaded_path = None
        
        # Try primary method
        if is_douyin:
            # Primary: Selenium for Douyin/TikTok
            self._notify(1, 3, "Tải bằng Selenium (Douyin/TikTok)...")
            selenium_downloader = SeleniumDownloader(self.config, project_id)
            # Pass progress callback
            selenium_downloader.progress_callback = self.progress_callback
            downloaded_path = selenium_downloader.download(url)
            
            # Fallback: yt-dlp
            if not downloaded_path:
                self._notify(2, 3, "Selenium thất bại, thử yt-dlp...")
                ytdlp_downloader = YTDLPDownloader(output_dir, project_id)
                ytdlp_downloader.config = self.config  # Pass config for timeout
                downloaded_path = ytdlp_downloader.download(url)
        else:
            # Primary: yt-dlp for other platforms
            self._notify(1, 3, "Tải bằng yt-dlp...")
            ytdlp_downloader = YTDLPDownloader(output_dir, project_id)
            ytdlp_downloader.config = self.config
            downloaded_path = ytdlp_downloader.download(url)
            
            # Fallback: Selenium
            if not downloaded_path:
                self._notify(2, 3, "yt-dlp thất bại, thử Selenium...")
                selenium_downloader = SeleniumDownloader(self.config, project_id)
                selenium_downloader.progress_callback = self.progress_callback
                downloaded_path = selenium_downloader.download(url)
        
        # Check result
        if downloaded_path and downloaded_path.exists():
            self._notify(3, 3, "✅ Tải xuống thành công!")
            size_mb = downloaded_path.stat().st_size / (1024 * 1024)
            self.logger.info("=" * 60)
            self.logger.info("✅ DOWNLOAD SUCCESSFUL")
            self.logger.info(f"📁 File: {downloaded_path.name}")
            self.logger.info(f"📊 Size: {size_mb:.2f} MB")
            self.logger.info(f"📂 Path: {downloaded_path}")
            self.logger.info("=" * 60)
            
            return {
                "success": True,
                "file_path": str(downloaded_path.absolute()),
                "filename": downloaded_path.name,
                "project_id": project_id,
                "error": None
            }
        
        # Both methods failed
        self._notify(3, 3, "❌ Tải xuống thất bại")
        error_msg = "All download methods failed"
        self.logger.error("=" * 60)
        self.logger.error("❌ DOWNLOAD FAILED")
        self.logger.error(f"Error: {error_msg}")
        self.logger.error("=" * 60)
        
        return {
            "success": False,
            "file_path": None,
            "filename": None,
            "project_id": project_id,
            "error": error_msg
        }


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def download_video(
    url: str,
    output_dir: Optional[Path] = None,
    headless: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[str, Any]:
    """Convenience function to download a video."""
    config = DownloaderConfig(
        headless=headless,
        output_dir=output_dir
    )
    
    downloader = VideoDownloader(config, progress_callback)
    return downloader.download(url)


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for the downloader."""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description="Download videos using yt-dlp (primary) or Selenium (fallback)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download Douyin video (uses Selenium)
  python downloader.py "https://www.douyin.com/video/123"
  
  # Download YouTube video (uses yt-dlp)
  python downloader.py "https://www.youtube.com/watch?v=123"
  
  # Download with custom output directory
  python downloader.py "https://www.youtube.com/watch?v=123" -o ./my_videos
  
  # Show browser window (for Douyin)
  python downloader.py "https://www.douyin.com/video/123" --no-headless
        """
    )
    
    parser.add_argument("url", help="Video URL to download")
    parser.add_argument("-o", "--output", help="Output directory (default: ./original_videos)", default="./original_videos")
    parser.add_argument("--no-headless", action="store_true", help="Disable headless mode (show browser window)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    if not args.quiet:
        logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.WARNING)
    
    # Progress callback
    def progress_callback(current, total, message):
        if not args.quiet:
            print(f"[{current}/{total}] {message}")
    
    # Download
    result = download_video(
        url=args.url,
        output_dir=Path(args.output),
        headless=not args.no_headless,
        progress_callback=progress_callback
    )
    
    if result["success"]:
        print("\n" + "=" * 50)
        print("✅ DOWNLOAD SUCCESSFUL")
        print("=" * 50)
        print(f"📁 File: {result['filename']}")
        print(f"📂 Path: {result['file_path']}")
        print(f"🏷️  Project ID: {result['project_id']}")
        print("=" * 50)
        sys.exit(0)
    else:
        print("\n" + "=" * 50)
        print("❌ DOWNLOAD FAILED")
        print("=" * 50)
        print(f"Error: {result['error']}")
        print("=" * 50)
        sys.exit(1)


if __name__ == "__main__":
    main()