# convert_mp4_to_audio.py
import os
import time
import logging
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class ConvertioMP4ToAudio:
    def __init__(self, download_dir, headless=False):
        self.download_dir = download_dir
        self.headless = headless
        self.driver = None
        self.wait = None
        
    def setup_driver(self):
        """Khởi tạo Chrome driver với các tùy chọn"""
        chrome_options = Options()
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Thêm user-agent để tránh bị phát hiện headless
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Chế độ headless
        if self.headless:
            chrome_options.add_argument("--headless=new")
            # Cần thêm các option này cho headless
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Cấu hình thư mục tải xuống
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Thêm script để tránh bị phát hiện automation
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        self.wait = WebDriverWait(self.driver, 30)
        
    def open_website(self):
        """Mở trang web Convertio"""
        try:
            logger.info("Đang mở trang web Convertio...")
            self.driver.get("https://convertio.co/vn/")
            time.sleep(5)  # Tăng thời gian chờ cho headless
            return True
        except Exception as e:
            logger.error(f"Lỗi khi mở trang web: {e}")
            return False
    
    def upload_file(self, file_path):
        """Upload file MP4 lên"""
        try:
            logger.info(f"Đang upload file: {file_path}")
            
            # Tìm và click vào nút chọn file
            upload_label = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "label[for='pc-upload-add']"))
            )
            # Dùng JavaScript click để đảm bảo
            self.driver.execute_script("arguments[0].click();", upload_label)
            time.sleep(2)
            
            # Tìm input file và gửi file
            file_input = self.driver.find_element(By.ID, "pc-upload-add")
            file_input.send_keys(file_path)
            
            # Đợi upload hoàn tất
            time.sleep(8)  # Tăng thời gian chờ cho headless
            logger.info("Upload file thành công")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi upload file: {e}")
            return False
    
    def select_mp3_format(self):
        """Chọn định dạng MP3"""
        try:
            logger.info("Đang chọn định dạng MP3...")
            
            # Click vào dropdown chọn định dạng
            format_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-toggle='dropdown'].btn-caret"))
            )
            self.driver.execute_script("arguments[0].click();", format_btn)
            time.sleep(2)
            
            # Chọn tab Âm thanh
            try:
                audio_tab = self.driver.find_element(By.XPATH, "//li[contains(text(), 'Âm thanh')]")
                self.driver.execute_script("arguments[0].click();", audio_tab)
                time.sleep(1)
            except:
                pass
            
            # Chọn MP3
            mp3_option = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//li/span[text()='MP3']"))
            )
            self.driver.execute_script("arguments[0].click();", mp3_option)
            time.sleep(3)
            logger.info("Đã chọn định dạng MP3")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi chọn định dạng MP3: {e}")
            return False
    
    def configure_settings(self):
        """Cấu hình cài đặt MP3"""
        try:
            logger.info("Đang cấu hình cài đặt...")
            
            # Click vào nút Settings
            settings_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-settings"))
            )
            self.driver.execute_script("arguments[0].click();", settings_btn)
            time.sleep(2)
            
            # Chọn VBR quality 5 (120-150 kbps)
            try:
                # Click vào dropdown VBR
                vbr_dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "audio_qscale_mp3SelectBoxIt"))
                )
                self.driver.execute_script("arguments[0].click();", vbr_dropdown)
                time.sleep(1)
                
                # Chọn 120...150 kbps
                vbr_option = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//li[@data-id='5']"))
                )
                self.driver.execute_script("arguments[0].click();", vbr_option)
                time.sleep(1)
                logger.info("Đã chọn VBR: 120...150 kbps")
            except Exception as e:
                logger.warning(f"Không thể chọn VBR: {e}")
            
            # Click OK để đóng settings
            ok_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Ok')]"))
            )
            self.driver.execute_script("arguments[0].click();", ok_btn)
            time.sleep(2)
            logger.info("Đã lưu cài đặt")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi cấu hình: {e}")
            return False
    
    def start_conversion(self):
        """Bắt đầu chuyển đổi"""
        try:
            logger.info("Đang click nút Chuyển đổi...")
            
            # Thử nhiều cách để click
            methods = [
                # Cách 1: Tìm bằng class và text
                lambda: self.driver.find_element(By.XPATH, "//button[contains(@class, 'btn-primary') and contains(text(), 'Chuyển đổi')]"),
                # Cách 2: Tìm bằng div cha
                lambda: self.driver.find_element(By.CSS_SELECTOR, "div.convert-button button.btn.btn-xl.btn-primary"),
                # Cách 3: Tìm tất cả button và lọc
                lambda: next(btn for btn in self.driver.find_elements(By.TAG_NAME, "button") if "Chuyển đổi" in btn.text)
            ]
            
            for i, method in enumerate(methods, 1):
                try:
                    convert_btn = method()
                    # Scroll đến button
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", convert_btn)
                    time.sleep(1)
                    # Click bằng JavaScript để đảm bảo
                    self.driver.execute_script("arguments[0].click();", convert_btn)
                    logger.info(f"✓ Đã click nút Chuyển đổi thành công (Cách {i})")
                    return True
                except:
                    continue
            
            logger.error("Không thể click nút Chuyển đổi")
            return False
            
        except Exception as e:
            logger.error(f"Lỗi khi click nút Chuyển đổi: {e}")
            return False
    
    def wait_for_download_link(self, timeout=600):
        """Đợi link tải xuất xuất hiện"""
        try:
            logger.info("Đang đợi file chuyển đổi hoàn tất...")
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    # Tìm link tải về
                    download_link = self.driver.find_element(By.CSS_SELECTOR, "a.btn-blue[href*='.mp3']")
                    if download_link:
                        href = download_link.get_attribute("href")
                        logger.info(f"✓ Đã tìm thấy link tải về")
                        return href
                except:
                    pass
                
                # Hiển thị trạng thái đang xử lý
                try:
                    processing = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Đang xử lý') or contains(text(), 'Processing') or contains(text(), 'Converting')]")
                    logger.info("Đang chuyển đổi...")
                except:
                    pass
                
                time.sleep(5)
            
            logger.error("Timeout: Không tìm thấy link tải về")
            return None
            
        except Exception as e:
            logger.error(f"Lỗi khi đợi link tải: {e}")
            return None
    
    def download_file(self, url, filename):
        """Tải file về máy và kiểm tra"""
        try:
            logger.info(f"Đang tải file: {filename}")
            
            file_path = Path(self.download_dir) / filename
            
            # Kiểm tra file đã tồn tại
            if file_path.exists() and file_path.stat().st_size > 0:
                logger.info(f"✓ File đã tồn tại: {file_path}")
                return str(file_path)
            
            # Tải file bằng requests
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            logger.info(f"Kích thước file: {total_size/1024/1024:.2f} MB")
            
            # Tải file
            downloaded = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            if progress % 10 < 0.1:
                                logger.info(f"Tiến độ: {progress:.1f}%")
            
            # Kiểm tra file đã tải xong
            if file_path.exists() and file_path.stat().st_size > 0:
                logger.info(f"✓ Đã tải xong: {file_path}")
                logger.info(f"Kích thước: {file_path.stat().st_size/1024/1024:.2f} MB")
                return str(file_path)
            else:
                logger.error("File tải về bị lỗi")
                if file_path.exists():
                    file_path.unlink()
                return None
            
        except Exception as e:
            logger.error(f"Lỗi khi tải file: {e}")
            return None
    
    def process_file(self, mp4_path):
        """Xử lý chuyển đổi một file MP4"""
        try:
            # Tạo tên file output
            mp4_filename = os.path.basename(mp4_path)
            mp3_filename = os.path.splitext(mp4_filename)[0] + ".mp3"
            mp3_path = Path(self.download_dir) / mp3_filename
            
            # Kiểm tra file đã tồn tại
            if mp3_path.exists() and mp3_path.stat().st_size > 0:
                logger.info(f"✓ File {mp3_filename} đã tồn tại, bỏ qua")
                return str(mp3_path)
            
            # Mở website
            if not self.open_website():
                return None
            
            # Upload file
            if not self.upload_file(mp4_path):
                return None
            
            # Chọn MP3
            if not self.select_mp3_format():
                return None
            
            # Cấu hình settings
            if not self.configure_settings():
                return None
            
            # Click nút Chuyển đổi
            if not self.start_conversion():
                return None
            
            # Đợi link tải về
            download_url = self.wait_for_download_link()
            if not download_url:
                return None
            
            # Tải file
            return self.download_file(download_url, mp3_filename)
            
        except Exception as e:
            logger.error(f"Lỗi xử lý file: {e}")
            return None
    
    def close(self):
        """Đóng driver"""
        if self.driver:
            self.driver.quit()
            logger.info("Đã đóng trình duyệt")

def main():
    # Đường dẫn thư mục
    mp4_dir = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\mp4"
    audio_dir = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\audio"
    
    # Tạo thư mục output
    Path(audio_dir).mkdir(parents=True, exist_ok=True)
    
    # Lấy danh sách file MP4
    mp4_files = list(Path(mp4_dir).glob("*.mp4"))
    
    if not mp4_files:
        logger.warning("Không tìm thấy file MP4 nào")
        return
    
    logger.info(f"Tìm thấy {len(mp4_files)} file MP4")
    logger.info(f"Thư mục output: {audio_dir}")
    logger.info("=" * 50)
    
    # Chọn chế độ: True = headless, False = có hiển thị
    HEADLESS_MODE = True  # Đổi thành True nếu muốn chạy headless
    
    converter = ConvertioMP4ToAudio(audio_dir, headless=HEADLESS_MODE)
    
    try:
        converter.setup_driver()
        
        success = 0
        failed = 0
        
        for i, mp4_file in enumerate(mp4_files, 1):
            logger.info(f"\n[{i}/{len(mp4_files)}] Xử lý: {mp4_file.name}")
            
            result = converter.process_file(str(mp4_file))
            
            if result:
                logger.info(f"✓ Thành công: {result}")
                success += 1
            else:
                logger.error(f"✗ Thất bại: {mp4_file.name}")
                failed += 1
            
            if i < len(mp4_files):
                logger.info("Đợi 5 giây trước khi xử lý file tiếp theo...")
                time.sleep(5)
        
        # Tổng kết
        logger.info("=" * 50)
        logger.info(f"✓ HOÀN THÀNH! Thành công: {success}/{len(mp4_files)}, Thất bại: {failed}/{len(mp4_files)}")
        
    except Exception as e:
        logger.error(f"Lỗi: {e}")
    
    finally:
        converter.close()

if __name__ == "__main__":
    main()