# gemini_translator_fixed.py
import time
import re
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pyperclip

# ==================== CẤU HÌNH ====================
SUBTITLE_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\text"
OUTPUT_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\translated"

PROMPT = """Bạn là một biên dịch viên phụ đề chuyên nghiệp, có kinh nghiệm dịch phim, video ngắn và hội thoại đời thường.

Nhiệm vụ:
- Dịch toàn bộ file phụ đề sang tiếng Việt tự nhiên.
- Đọc toàn bộ nội dung trước khi dịch để hiểu bối cảnh.
- KHÔNG dịch từng câu độc lập.
- Luôn giữ ngữ nghĩa theo ngữ cảnh.

Quy tắc dịch:
1. Giữ nguyên số thứ tự, timestamp, khoảng trắng và định dạng SRT.
2. Chỉ dịch phần hội thoại.
3. Dịch theo NGHĨA, KHÔNG dịch từng từ.
4. Điều chỉnh câu cho tự nhiên như phụ đề phim Việt.
5. Nếu câu nói thiếu chủ ngữ hoặc bị cắt giữa các subtitle, dựa vào ngữ cảnh trước và sau để hoàn chỉnh.
6. Tên riêng giữ nguyên, nếu tiếng Trung thì dùng phiên âm.
7. Không dịch máy, chọn nghĩa phù hợp ngữ cảnh.
8. Nếu AI không chắc nghĩa, suy luận từ bối cảnh, không bịa.
9. Nếu bản gốc có lỗi ASR, tự sửa thành câu hợp lý nhất.
10. Nếu có thành ngữ, tiếng lóng, chuyển sang cách diễn đạt tự nhiên trong tiếng Việt.
11. Nếu người nói dùng kính ngữ, chuyển xưng hô phù hợp.
12. Nếu câu hài hước hoặc châm biếm, giữ đúng sắc thái.
13. Không dịch literal.
14. Không giải thích, không ghi chú, không thêm bình luận.
15. Chỉ trả về đúng định dạng SRT.

Định dạng bắt buộc:
1
00:00:00,000 --> 00:00:01,899
...

2
00:00:01,899 --> 00:00:02,439
...

Không dùng Markdown. Không dùng ```. Chỉ xuất file SRT hoàn chỉnh."""

# ================================================

def count_subtitle_lines(content):
    """Đếm số dòng subtitle trong file SRT"""
    if not content:
        return 0
    pattern = r'^\d+\n\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}'
    matches = re.findall(pattern, content, re.MULTILINE)
    return len(matches)

def extract_subtitle_blocks(content):
    """Tách nội dung thành các khối subtitle riêng biệt"""
    if not content:
        return []
    pattern = r'(\d+\n\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}\n.*?)(?=\n\n\d+\n|\Z)'
    blocks = re.findall(pattern, content, re.DOTALL)
    return blocks

def get_content_from_line(content, start_line):
    """Lấy nội dung từ dòng start_line trở đi"""
    blocks = extract_subtitle_blocks(content)
    if start_line <= 1:
        return content
    if start_line > len(blocks):
        return ""
    return '\n\n'.join(blocks[start_line-1:])

def wait_for_gemini_complete(driver, timeout=600):
    """
    Đợi Gemini trả lời HOÀN TOÀN (không còn loading, không còn animation)
    Trả về nội dung đầy đủ
    """
    print("⏳ Đợi Gemini trả lời hoàn toàn...")
    time.sleep(3)
    
    start_time = time.time()
    last_content = ""
    stable_count = 0  # Đếm số lần nội dung ổn định
    
    while time.time() - start_time < timeout:
        try:
            # Tìm div chứa response
            response_divs = driver.find_elements(
                By.CSS_SELECTOR, 
                ".markdown.markdown-main-panel, .model-response-message-content, [class*='markdown-main-panel']"
            )
            
            if response_divs:
                latest = response_divs[-1]
                
                # Kiểm tra có đang loading không
                loading = latest.find_elements(
                    By.CSS_SELECTOR, 
                    ".loading, .typing, .skeleton, .animate-pulse, [aria-busy='true']"
                )
                
                # Kiểm tra có đang streaming không
                streaming = latest.find_elements(
                    By.CSS_SELECTOR,
                    ".result-streaming, .streaming, .in-progress"
                )
                
                content = latest.text
                
                # Nếu không loading và không streaming
                if not loading and not streaming:
                    # Kiểm tra nội dung có thay đổi không
                    if content == last_content:
                        stable_count += 1
                    else:
                        stable_count = 0
                        last_content = content
                    
                    # Nếu ổn định trong 5 lần (10 giây) và có nội dung
                    if stable_count >= 5 and len(content) > 50:
                        line_count = count_subtitle_lines(content)
                        print(f"✅ Gemini đã trả lời xong! ({len(content)} ký tự, {line_count} dòng)")
                        return content
                else:
                    # Vẫn đang trả lời
                    if content and len(content) > len(last_content):
                        last_content = content
                        # Hiển thị tiến trình
                        if len(content) % 500 < 50:
                            print(f"⏳ Đang nhận... {len(content)} ký tự")
                    stable_count = 0
                    
        except Exception as e:
            pass
        
        time.sleep(2)
    
    print("⏰ Hết thời gian chờ, lấy nội dung hiện tại")
    return last_content

print("🚀 Mở Chrome...")

# Khởi tạo Chrome
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
)

wait = WebDriverWait(driver, 60)

# Tạo thư mục output
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

try:
    # 1. Mở Gemini
    print("🌐 Truy cập https://gemini.google.com/app...")
    driver.get("https://gemini.google.com/app")
    time.sleep(5)
    
    # 2. Lấy danh sách file SRT
    srt_files = list(Path(SUBTITLE_DIR).glob("*.srt"))
    if not srt_files:
        print("❌ Không tìm thấy file SRT nào!")
        driver.quit()
        exit()
    
    print(f"📂 Tìm thấy {len(srt_files)} file SRT\n")
    
    for idx, srt_file in enumerate(srt_files, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(srt_files)}] 📄 {srt_file.name}")
        
        # Đọc file SRT gốc
        with open(srt_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        original_line_count = count_subtitle_lines(original_content)
        print(f"📊 Số dòng gốc: {original_line_count}")
        
        translated_content = ""
        translated_line_count = 0
        start_line = 1
        attempt = 1
        max_attempts = 20
        
        while translated_line_count < original_line_count and attempt <= max_attempts:
            print(f"\n📝 Lần {attempt} - Dịch từ dòng {start_line}")
            
            content_to_translate = get_content_from_line(original_content, start_line)
            if not content_to_translate:
                break
            
            # Tạo prompt
            if attempt == 1:
                full_text = f"{PROMPT}\n\n---\n\nNội dung cần dịch:\n\n{content_to_translate}"
            else:
                full_text = f"""Vui lòng tiếp tục dịch từ dòng {start_line} đến hết:

{content_to_translate}

Chỉ trả về phần dịch từ dòng {start_line} đến hết, giữ đúng định dạng SRT."""
            
            # Tìm input
            print("📝 Đang nhập prompt...")
            try:
                input_area = None
                try:
                    input_area = driver.find_element(By.CSS_SELECTOR, ".ql-editor, [contenteditable='true']")
                except:
                    pass
                
                if not input_area:
                    try:
                        input_area = driver.find_element(By.CSS_SELECTOR, "textarea")
                    except:
                        pass
                
                if not input_area:
                    print("⚠️ Không tìm thấy input area")
                    break
                
                input_area.click()
                time.sleep(0.5)
                input_area.clear()
                time.sleep(0.3)
                
            except Exception as e:
                print(f"⚠️ Lỗi tìm input: {e}")
                break
            
            # Copy-paste
            pyperclip.copy(full_text)
            time.sleep(0.3)
            input_area.send_keys(Keys.CONTROL + 'v')
            print(f"✅ Đã paste {len(full_text)} ký tự")
            time.sleep(1)
            
            # Gửi (Enter)
            input_area.send_keys(Keys.ENTER)
            print("📤 Đã gửi yêu cầu!")
            
            # Đợi Gemini trả lời HOÀN TOÀN
            response_text = wait_for_gemini_complete(driver, timeout=600)
            
            if not response_text:
                print("❌ Không nhận được response")
                break
            
            # Nếu lần đầu, gán toàn bộ
            if attempt == 1:
                translated_content = response_text
            else:
                # Lấy phần mới từ response (không lấy cả đống trùng lặp)
                # Tìm block bắt đầu từ start_line
                blocks = extract_subtitle_blocks(response_text)
                new_blocks = []
                
                for block in blocks:
                    match = re.match(r'^(\d+)', block)
                    if match:
                        block_num = int(match.group(1))
                        if block_num >= start_line:
                            new_blocks.append(block)
                
                if new_blocks:
                    new_content = '\n\n'.join(new_blocks)
                    translated_content = translated_content + '\n\n' + new_content
                else:
                    # Fallback: lấy toàn bộ response (có thể trùng lặp nhưng đỡ mất)
                    translated_content = response_text
            
            # Đếm số dòng
            translated_line_count = count_subtitle_lines(translated_content)
            print(f"📊 Đã dịch: {translated_line_count}/{original_line_count} dòng")
            
            if translated_line_count >= original_line_count:
                print("✅ Đã dịch đủ!")
                break
            
            # Tính dòng tiếp theo
            blocks = extract_subtitle_blocks(translated_content)
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
        
        # Lưu file
        output_file = Path(OUTPUT_DIR) / f"{srt_file.stem}_vi.srt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(translated_content)
        
        final_count = count_subtitle_lines(translated_content)
        print(f"\n✅ Đã lưu: {output_file.name} ({final_count}/{original_line_count} dòng)")
        
        # Reset trang
        driver.get("https://gemini.google.com/app")
        time.sleep(3)
    
    print(f"\n{'='*60}")
    print(f"✅ XONG! Đã xử lý {len(srt_files)} file")
    print(f"📁 Output: {OUTPUT_DIR}")
    print(f"{'='*60}")

except Exception as e:
    print(f"❌ Lỗi: {e}")
    import traceback
    traceback.print_exc()

finally:
    print("\n🔚 Đóng trình duyệt...")
    time.sleep(3)
    driver.quit()