# translate_gemini.py
import os
import re
import time
import logging
from pathlib import Path
from google import genai

# ==================== CẤU HÌNH ====================
GEMINI_API_KEYS = [
    "",
    "",
]

TEXT_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\text"
TRANSLATED_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\translated"

# Dùng gemini-3.6-flash (mới nhất, rẻ, nhanh)
GEMINI_MODEL = "models/gemini-3.6-flash"

ENABLE_TRANSLATION = True
# =================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class SRTTranslatorGemini:
    def __init__(self):
        self.api_keys = GEMINI_API_KEYS
        self.current_key_index = 0
        self.client = None
        self.key_error_counts = {key: 0 for key in self.api_keys}
        self.max_errors_per_key = 2
        self.available = True
        self.total_tokens = 0  # Đếm token để biết tiêu thụ
        
        self._init_client()
        logger.info(f"✅ Gemini 3.6 Flash initialized with {len(self.api_keys)} keys")
    
    def _init_client(self):
        if self.api_keys and self.available:
            api_key = self.api_keys[self.current_key_index]
            self.client = genai.Client(api_key=api_key)
            logger.info(f"🔑 Key: {api_key[:10]}...{api_key[-4:]}")
    
    def _switch_key(self):
        for i, key in enumerate(self.api_keys):
            if self.key_error_counts.get(key, 0) < self.max_errors_per_key:
                if i != self.current_key_index:
                    self.current_key_index = i
                    self._init_client()
                    return True
        self.available = False
        logger.warning("⚠️ All Gemini keys exhausted")
        return False
    
    def translate_text(self, text):
        """Dịch text bằng Gemini 3.6 Flash - tối ưu token"""
        if not self.available or not self.client:
            return None
        
        try:
            # Prompt ngắn gọn để tiết kiệm token
            prompt = f"""Translate Chinese to Vietnamese. Keep line count.

Chinese:
{text}

Vietnamese:"""
            
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            
            if response and response.text:
                translated = response.text.strip()
                translated = re.sub(r'^```\w*\n', '', translated)
                translated = re.sub(r'\n```$', '', translated)
                
                # Ước tính token (1 token ~ 4 ký tự)
                self.total_tokens += len(text) // 4 + len(translated) // 4
                
                return translated
            return None
            
        except Exception as e:
            error_msg = str(e)
            current_key = self.api_keys[self.current_key_index]
            self.key_error_counts[current_key] += 1
            logger.warning(f"⚠️ Error ({self.key_error_counts[current_key]}/{self.max_errors_per_key})")
            
            if self.key_error_counts[current_key] >= self.max_errors_per_key:
                if self._switch_key():
                    return self.translate_text(text)
            
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
            
            texts = [seg['text'] for seg in segments]
            
            # GỘP TẤT CẢ vào 1 lần gọi để tiết kiệm API
            full_text = '\n'.join(texts)
            logger.info(f"📤 {len(texts)} dòng, {len(full_text)} ký tự")
            
            translated_text = self.translate_text(full_text)
            
            if not translated_text:
                logger.error("❌ Translation failed")
                return srt_content
            
            translated_lines = translated_text.strip().split('\n')
            
            if len(translated_lines) == len(segments):
                new_srt = []
                for i, seg in enumerate(segments):
                    new_srt.append(str(seg['index']))
                    new_srt.append(seg['timestamp'])
                    new_srt.append(translated_lines[i].strip())
                    new_srt.append('')
                logger.info(f"✅ Dịch xong {len(segments)} dòng")
                return '\n'.join(new_srt)
            else:
                logger.warning(f"Số dòng không khớp: {len(translated_lines)} vs {len(segments)}")
                # Fallback: dịch từng dòng
                return self._translate_segments(segments)
            
        except Exception as e:
            logger.error(f"Lỗi: {e}")
            return srt_content
    
    def _translate_segments(self, segments):
        """Dịch từng segment (tốn nhiều token hơn)"""
        translated_lines = []
        for seg in segments:
            text = seg['text']
            if text.strip():
                translated = self.translate_text(text)
                translated_lines.append(translated if translated else text)
            else:
                translated_lines.append(text)
            time.sleep(0.5)
        
        new_srt = []
        for i, seg in enumerate(segments):
            if i < len(translated_lines):
                new_srt.append(str(seg['index']))
                new_srt.append(seg['timestamp'])
                new_srt.append(translated_lines[i].strip())
                new_srt.append('')
        return '\n'.join(new_srt)

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
    logger.info(f"🤖 Gemini 3.6 Flash ({len(GEMINI_API_KEYS)} keys)")
    logger.info("=" * 60)
    
    translator = SRTTranslatorGemini()
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
    logger.info(f"  📊 Token ước tính: {translator.total_tokens}")
    logger.info("=" * 60)

def main():
    if not ENABLE_TRANSLATION:
        logger.info("⏭ Dịch đã tắt")
        return
    process_srt_files()

if __name__ == "__main__":
    main()