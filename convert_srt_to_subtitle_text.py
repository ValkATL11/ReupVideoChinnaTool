# convert_srt_to_subtitle_text.py
import os
import re
from pathlib import Path

# ==================== CẤU HÌNH ====================
# Thư mục chứa file SRT đã dịch
SRT_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\translated"

# Thư mục lưu file text đã chuyển đổi
OUTPUT_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\subtitle_text"
# =================================================

def extract_subtitle_text(srt_content):
    """
    Trích xuất phần hội thoại từ file SRT, mỗi câu một dòng,
    giữ nguyên thứ tự và nội dung
    """
    lines = srt_content.strip().split('\n')
    subtitle_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Bỏ qua dòng số thứ tự
        if line.isdigit():
            i += 1
            continue
        
        # Bỏ qua dòng timestamp
        if '-->' in line:
            i += 1
            continue
        
        # Nếu là dòng trống
        if line == '':
            i += 1
            continue
        
        # Nếu là text (hội thoại)
        if line and not line.isdigit() and '-->' not in line:
            # Loại bỏ các tiền tố không mong muốn
            line = re.sub(r'^Dòng\s*\d+:\s*', '', line)
            # Loại bỏ số thứ tự ở đầu dòng (nếu có)
            line = re.sub(r'^\d+\s+', '', line)
            
            # Thêm dòng text vào danh sách
            subtitle_lines.append(line)
        
        i += 1
    
    # Ghép các dòng lại với nhau, mỗi dòng là một câu
    return '\n'.join(subtitle_lines)

def process_all_srt_files():
    """Xử lý tất cả file SRT trong thư mục"""
    
    # Tạo thư mục output
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    
    # Lấy danh sách file SRT
    srt_files = list(Path(SRT_DIR).glob("*.srt"))
    
    if not srt_files:
        print(f"⚠️ Không tìm thấy file SRT nào trong: {SRT_DIR}")
        return
    
    print("=" * 60)
    print(f"📁 Thư mục input: {SRT_DIR}")
    print(f"📁 Thư mục output: {OUTPUT_DIR}")
    print(f"📊 Tìm thấy {len(srt_files)} file SRT")
    print("=" * 60)
    
    for srt_file in srt_files:
        try:
            print(f"\n📄 Đang xử lý: {srt_file.name}")
            
            # Đọc file SRT
            with open(srt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Trích xuất hội thoại
            text_content = extract_subtitle_text(content)
            
            # Lưu file text
            output_name = srt_file.stem.replace('_vi', '') + '_subtitle.txt'
            output_path = Path(OUTPUT_DIR) / output_name
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            # Hiển thị thông tin
            lines = text_content.split('\n')
            print(f"✅ Đã tạo: {output_path.name}")
            print(f"   📝 Số dòng: {len(lines)}")
            print(f"   📝 Ký tự: {len(text_content)}")
            
            # Hiển thị preview
            if lines:
                print(f"   📌 Preview: {lines[0][:50]}...")
            
        except Exception as e:
            print(f"❌ Lỗi xử lý {srt_file.name}: {e}")
    
    print("\n" + "=" * 60)
    print("✅ HOÀN THÀNH!")
    print(f"📁 File đã lưu tại: {OUTPUT_DIR}")

def main():
    process_all_srt_files()

if __name__ == "__main__":
    main()