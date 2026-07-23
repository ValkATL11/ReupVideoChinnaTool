"""
Module downloader.py - Tải video Douyin/TikTok qua SnapWC
Sử dụng Selenium để tự động hóa trình duyệt (chạy ngầm)
"""

import os
import time
import requests
import re
from typing import Tuple, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service


def download_douyin_video(url: str, output_dir: str = None) -> Tuple[str, str]:
    """
    Tải video Douyin/TikTok bằng Selenium + Chrome qua SnapWC.
    Đợi text "Tải xuống hoàn tất." xuất hiện trong iframe thì coi như xong.
    """
    # Đường dẫn tuyệt đối
    if output_dir is None:
        output_dir = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\mp4"
    
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 60)
    print("🎬 TẢI VIDEO DOUYIN/TIKTOK (SNAPWC)")
    print("=" * 60)
    print(f"📌 URL: {url[:80]}...")
    print(f"📁 Thư mục tải: {output_dir}")
    print("=" * 60)
    print("🖥️ Chế độ chạy ngầm (không hiện trình duyệt)")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Cấu hình download tự động
    prefs = {
        "download.default_directory": output_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = None
    original_tab = None
    
    try:
        print("🚀 Đang khởi tạo trình duyệt...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 90)
        original_tab = driver.current_window_handle
        print("   ✅ Đã mở trình duyệt!")
        
        # BƯỚC 1: Mở SnapWC
        print("📄 [Bước 1/7] Đang mở SnapWC...")
        driver.get("https://snapwc.com/vi")
        time.sleep(2)
        print("   ✅ Đã tải trang")
        
        # BƯỚC 2: Nhập URL
        print("📝 [Bước 2/7] Đang nhập URL...")
        input_element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
        )
        input_element.clear()
        input_element.send_keys(url)
        time.sleep(1)
        print(f"   ✅ Đã nhập URL")
        
        # BƯỚC 3: Click nút "Lấy liên kết tải xuống"
        print("⬇️ [Bước 3/7] Đang click nút 'Lấy liên kết tải xuống'...")
        button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        driver.execute_script("arguments[0].click();", button)
        print("   ✅ Đã click")
        
        # BƯỚC 4: Đợi kết quả hiển thị
        print("⏳ [Bước 4/7] Đang đợi kết quả...")
        time.sleep(5)
        
        # Đợi kết quả hiển thị
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.result-card, div.macos-result-card"))
        )
        time.sleep(2)
        
        # Hiển thị danh sách chất lượng và dung lượng
        print("\n📊 DANH SÁCH CHẤT LƯỢNG:")
        print("-" * 40)
        
        # Tìm tất cả các item video
        video_items = driver.find_elements(By.CSS_SELECTOR, "div.result-panel div.q-item")
        
        for item in video_items:
            try:
                label_element = item.find_element(By.CSS_SELECTOR, "div.q-item__label")
                label_text = label_element.text.strip()
                
                size_element = item.find_element(By.CSS_SELECTOR, "div.q-item__label--caption")
                size_text = size_element.text.strip()
                
                print(f"   📹 {label_text}: {size_text}")
            except:
                continue
        
        print("-" * 40)
        
        # BƯỚC 5: Click nút Tải xuống (chọn 1080p hoặc UHD)
        print("\n📥 [Bước 5/7] Đang click nút Tải xuống...")
        
        # Tìm tất cả các nút có icon file_download và text "Tải xuống"
        download_buttons = driver.find_elements(By.XPATH, "//button[.//i[contains(text(), 'file_download')] and .//span[contains(text(), 'Tải xuống')]]")
        
        if download_buttons:
            # Lấy nút cuối cùng (thường là 1080p hoặc UHD)
            last_button = download_buttons[-1]
            
            # Tìm quality tương ứng
            selected_quality = "Không xác định"
            for item in video_items:
                try:
                    btn_in_item = item.find_element(By.CSS_SELECTOR, "button[rel='noreferrer noopener nofollow']")
                    if btn_in_item == last_button:
                        label = item.find_element(By.CSS_SELECTOR, "div.q-item__label").text.strip()
                        size = item.find_element(By.CSS_SELECTOR, "div.q-item__label--caption").text.strip()
                        selected_quality = f"{label} ({size})"
                        break
                except:
                    continue
            
            print(f"   ✅ Đang tải: {selected_quality}")
            
            # Scroll đến nút
            driver.execute_script("arguments[0].scrollIntoView(true);", last_button)
            time.sleep(1)
            
            # Click nút
            driver.execute_script("arguments[0].click();", last_button)
            print("   ✅ Đã click nút Tải xuống")
            
            # BƯỚC 6: Xử lý tab mới nếu có
            print("⏳ [Bước 6/7] Kiểm tra tab mới...")
            all_tabs = driver.window_handles
            if len(all_tabs) > 1:
                print(f"   🔄 Phát hiện tab mới, đang xử lý...")
                for tab in all_tabs:
                    if tab != original_tab:
                        driver.switch_to.window(tab)
                        time.sleep(1)
                        print(f"   📄 Tab mới URL: {driver.current_url[:60]}...")
                        driver.close()
                        break
                driver.switch_to.window(original_tab)
                print("   ✅ Đã quay lại tab cũ")
            
            # BƯỚC 7: Đợi text "Tải xuống hoàn tất." xuất hiện trong iframe
            print("⏳ [Bước 7/7] Đang đợi 'Tải xuống hoàn tất.' trong iframe...")
            
            # Đợi iframe xuất hiện
            try:
                # Đợi iframe load
                iframe = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.iframe-download-frame"))
                )
                print("   ✅ Đã tìm thấy iframe")
                
                # Chuyển vào iframe
                driver.switch_to.frame(iframe)
                print("   ✅ Đã chuyển vào iframe")
                
                # Đợi text "Tải xuống hoàn tất." trong iframe
                try:
                    complete_text = wait.until(
                        EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Tải xuống hoàn tất')]"))
                    )
                    print(f"   ✅ Đã xuất hiện: '{complete_text.text}'")
                except Exception as e:
                    print(f"   ⚠️ Không tìm thấy text trong iframe: {e}")
                    print("   ⏳ Đợi thêm 10 giây...")
                    time.sleep(10)
                
                # Chuyển ra khỏi iframe
                driver.switch_to.default_content()
                
            except Exception as e:
                print(f"   ⚠️ Không tìm thấy iframe: {e}")
                print("   ⏳ Đợi thêm 10 giây...")
                time.sleep(10)
            
            # Đợi thêm 2 giây để file ghi xong
            time.sleep(2)
            
            # Tìm file mới nhất trong thư mục downloads
            print("   🔍 Đang kiểm tra file đã tải...")
            files = [f for f in os.listdir(output_dir) if f.endswith('.mp4')]
            
            if files:
                # Lấy file mới nhất
                latest_file = max(files, key=lambda f: os.path.getctime(os.path.join(output_dir, f)))
                video_path = os.path.join(output_dir, latest_file)
                
                # Lấy dung lượng file
                file_size = os.path.getsize(video_path)
                size_mb = file_size / (1024 * 1024)
                
                print(f"   ✅ Đã tải xong: {latest_file}")
                print("=" * 60)
                print(f"✅ VIDEO ĐÃ TẢI THÀNH CÔNG!")
                print(f"📁 Đường dẫn: {video_path}")
                print(f"📄 Tên file: {latest_file}")
                print(f"📦 Dung lượng: {size_mb:.2f} MB")
                print("=" * 60)
                
                # Đóng trình duyệt
                print("\n🖥️ Đang đóng trình duyệt...")
                driver.quit()
                print("   ✅ Đã đóng trình duyệt")
                
                return video_path, latest_file
            else:
                # Nếu không tìm thấy file, thử tải bằng requests
                print("   🔍 Không tìm thấy file trong thư mục, thử lấy link từ HTML...")
                html = driver.page_source
                mp4_pattern = r'https://[^\s"\']+\.mp4[^\s"\']*'
                matches = re.findall(mp4_pattern, html)
                
                if matches:
                    download_link = matches[0]
                    print(f"   ✅ Tìm thấy link: {download_link[:80]}...")
                    
                    print("   📊 Đang kiểm tra dung lượng...")
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Referer': 'https://snapwc.com/vi'
                    }
                    response = requests.get(download_link, headers=headers, stream=True, timeout=120)
                    
                    if response.status_code == 200:
                        total_size = int(response.headers.get('content-length', 0))
                        size_mb = total_size / (1024 * 1024)
                        print(f"   📦 Dung lượng: {size_mb:.2f} MB")
                        
                        filename = f"douyin_{int(time.time())}.mp4"
                        video_path = os.path.join(output_dir, filename)
                        
                        print("   📥 Đang tải video...")
                        downloaded = 0
                        with open(video_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if total_size > 0:
                                        percent = (downloaded / total_size) * 100
                                        print(f"\r   Tiến độ: {percent:.1f}%", end='')
                        
                        print(f"\n   ✅ Đã tải xong!")
                        print("=" * 60)
                        print(f"✅ VIDEO ĐÃ TẢI THÀNH CÔNG!")
                        print(f"📁 Đường dẫn: {video_path}")
                        print(f"📄 Tên file: {filename}")
                        print(f"📦 Dung lượng: {downloaded / (1024*1024):.2f} MB")
                        print("=" * 60)
                        
                        # Đóng trình duyệt
                        print("\n🖥️ Đang đóng trình duyệt...")
                        driver.quit()
                        print("   ✅ Đã đóng trình duyệt")
                        
                        return video_path, filename
                else:
                    raise Exception("Không tìm thấy link tải video")
        else:
            raise Exception("Không tìm thấy nút Tải xuống")
        
    except Exception as e:
        if driver:
            print("\n⚠️ Có lỗi xảy ra, đang đóng trình duyệt...")
            driver.quit()
        raise Exception(f"Lỗi: {str(e)}")


def test_download():
    """Test tải video"""
    print("=" * 60)
    print("🧪 TEST TẢI VIDEO QUA SNAPWC")
    print("=" * 60)
    
    url = input("\n📌 Nhập link Douyin/TikTok: ").strip()
    
    if not url:
        print("❌ Link không được để trống!")
        return
    
    video_path, filename = download_douyin_video(url)
    print(f"\n✅ Đã tải: {video_path}")


def main():
    """CLI chính"""
    print("\n" + "=" * 60)
    print("🎬 CÔNG CỤ TẢI VIDEO DOUYIN/TIKTOK")
    print("=" * 60)
    
    url = input("\n📌 Nhập link Douyin/TikTok: ").strip()
    
    if not url:
        print("❌ Link không được để trống!")
        return
    
    try:
        video_path, filename = download_douyin_video(url)
        print(f"\n✅ Thành công! Video lưu tại: {video_path}")
        
    except Exception as e:
        print(f"\n❌ Lỗi: {str(e)}")


if __name__ == "__main__":
    # Nếu có tham số dòng lệnh hoặc muốn chạy test
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_download()
    else:
        main()