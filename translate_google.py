# translate_simple.py
import os
import re
import time
import logging
import json
import requests
from pathlib import Path

# ==================== CẤU HÌNH ====================
TEXT_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\text"
TRANSLATED_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\translated"
ENABLE_TRANSLATION = True
# =================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class SRTTranslatorSimple:
    def __init__(self):
        # Dùng Google Translate API không chính thức qua requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logger.info("✅ Google Translate (via requests) initialized")
    
    def translate_text(self, text):
        """Dịch text bằng Google Translate qua requests"""
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": "zh-CN",
                "tl": "vi",
                "dt": "t",
                "q": text
            }
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Lấy text dịch từ response
                translated = ''.join([item[0] for item in data[0] if item[0]])
                return translated
            return None
        except Exception as e:
            logger.warning(f"⚠️ Lỗi dịch: {e}")
            return None
    
    def parse_srt(self, srt_content):
        lines = srt_content.strip().split('\n')
        segments = []
        current_segment = {}
        
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
    
    def translate_srt(self, srt_content, srt_path):
        try:
            logger.info(f"Đang dịch: {os.path.basename(srt_path)}")
            
            segments = self.parse_srt(srt_content)
            if not segments:
                return srt_content
            
            # Lấy tất cả text
            texts = [seg['text'] for seg in segments]
            
            # Dịch từng dòng
            translated_lines = []
            total = len(texts)
            
            for i, text in enumerate(texts, 1):
                if text.strip():
                    logger.info(f"   [{i}/{total}] Dịch: {text[:30]}...")
                    translated = self.translate_text(text)
                    translated_lines.append(translated if translated else text)
                else:
                    translated_lines.append(text)
                time.sleep(0.3)
            
            # Tạo SRT mới
            new_srt = []
            for i, seg in enumerate(segments):
                if i < len(translated_lines):
                    new_srt.append(str(seg['index']))
                    new_srt.append(seg['timestamp'])
                    new_srt.append(translated_lines[i].strip())
                    new_srt.append('')
            
            logger.info(f"✅ Dịch xong {len(segments)} dòng")
            return '\n'.join(new_srt)
            
        except Exception as e:
            logger.error(f"Lỗi: {e}")
            return srt_content

def process_srt_files():
    Path(TRANSLATED_DIR).mkdir(parents=True, exist_ok=True)
    srt_files = list(Path(TEXT_DIR).glob("*.srt"))
    
    if not srt_files:
        logger.warning(f"Không tìm thấy file SRT nào")
        return
    
    logger.info("=" * 60)
    logger.info(f"📁 Input: {TEXT_DIR}")
    logger.info(f"📁 Output: {TRANSLATED_DIR}")
    logger.info(f"📊 Tìm thấy {len(srt_files)} file")
    logger.info("🌐 Google Translate (via requests)")
    logger.info("=" * 60)
    
    translator = SRTTranslatorSimple()
    success = 0
    skipped = 0
    failed = 0
    
    for i, srt_file in enumerate(srt_files, 1):
        try:
            logger.info(f"\n[{i}/{len(srt_files)}] Xử lý: {srt_file.name}")
            
            with open(srt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            output_path = Path(TRANSLATED_DIR) / f"{srt_file.stem}_vi.srt"
            
            if output_path.exists():
                logger.info(f"⏭ File đã tồn tại, bỏ qua")
                skipped += 1
                continue
            
            translated = translator.translate_srt(content, srt_file)
            
            if translated and translated != content:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(translated)
                logger.info(f"✅ Đã dịch: {output_path.name}")
                success += 1
            else:
                logger.info(f"⏭ Không thay đổi")
                skipped += 1
            
            if i < len(srt_files):
                time.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Lỗi {srt_file.name}: {e}")
            failed += 1
    
    logger.info("\n" + "=" * 60)
    logger.info("📊 KẾT QUẢ:")
    logger.info(f"  ✅ Đã dịch: {success}/{len(srt_files)}")
    logger.info(f"  ⏭ Bỏ qua: {skipped}/{len(srt_files)}")
    logger.info(f"  ❌ Thất bại: {failed}/{len(srt_files)}")
    logger.info(f"  📁 Output: {TRANSLATED_DIR}")
    logger.info("=" * 60)

def main():
    if not ENABLE_TRANSLATION:
        logger.info("⏭ Dịch đã tắt")
        return
    process_srt_files()

if __name__ == "__main__":
    main()