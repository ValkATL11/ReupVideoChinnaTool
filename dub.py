# edge_tts_lib.py
import os
import asyncio
import edge_tts
from pathlib import Path
import logging
from datetime import datetime

# ==================== CẤU HÌNH ====================
SUBTITLE_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\subtitle_text"
AUDIO_OUTPUT_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1\dubbing"

# Giọng đọc
VOICE_MALE = "vi-VN-NamMinhNeural"
VOICE_FEMALE = "vi-VN-HoaiMyNeural"
VOICE = VOICE_FEMALE

# Tốc độ đọc (1.0 = bình thường, 1.25 = nhanh hơn)
SPEED = 1.5

# Định dạng output
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
# =================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class EdgeTTSConverter:
    def __init__(self, voice=VOICE, speed=SPEED):
        self.voice = voice
        self.speed = speed
        self.output_dir = Path(AUDIO_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    async def text_to_speech(self, text, output_path):
        """Chuyển text thành audio bằng edge-tts"""
        try:
            # Tạo cấu hình
            rate = f"{int((self.speed - 1) * 100):+d}%"
            
            # Tạo communicate
            communicate = edge_tts.Communicate(text, self.voice, rate=rate)
            
            # Tạo audio
            await communicate.save(output_path)
            
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi TTS: {e}")
            return False
    
    async def process_text_file(self, text_path):
        """Xử lý một file text"""
        try:
            logger.info("=" * 60)
            logger.info(f"📄 Đang xử lý: {text_path.name}")
            
            # Đọc file text
            with open(text_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            
            if not lines:
                logger.warning(f"⚠️ File {text_path.name} trống, bỏ qua")
                return []
            
            logger.info(f"📊 Tìm thấy {len(lines)} dòng")
            
            # Tạo thư mục output
            base_name = text_path.stem.replace('_subtitle', '')
            video_dir = self.output_dir / base_name
            video_dir.mkdir(parents=True, exist_ok=True)
            
            downloaded_files = []
            
            # Xử lý từng dòng
            for i, line in enumerate(lines, 1):
                logger.info(f"\n📝 Dòng {i}/{len(lines)}: {line[:50]}...")
                
                # Tạo tên file
                filename = f"dong_{i:03d}.mp3"
                output_path = video_dir / filename
                
                # Chuyển text thành audio
                success = await self.text_to_speech(line, str(output_path))
                
                if success:
                    downloaded_files.append(str(output_path))
                    logger.info(f"✅ Đã tạo: {filename}")
                else:
                    logger.error(f"❌ Lỗi tạo audio dòng {i}")
            
            logger.info(f"\n✅ Hoàn thành! Đã tạo {len(downloaded_files)} file audio")
            return downloaded_files
            
        except Exception as e:
            logger.error(f"❌ Lỗi xử lý file {text_path}: {e}")
            return []
    
    async def process_all_files(self):
        """Xử lý tất cả file text trong thư mục"""
        text_files = list(Path(SUBTITLE_DIR).glob("*_subtitle.txt"))
        
        if not text_files:
            logger.warning(f"⚠️ Không tìm thấy file text nào trong {SUBTITLE_DIR}")
            return
        
        logger.info("=" * 60)
        logger.info(f"📁 Thư mục input: {SUBTITLE_DIR}")
        logger.info(f"📁 Thư mục output: {AUDIO_OUTPUT_DIR}")
        logger.info(f"🎤 Giọng đọc: {self.voice}")
        logger.info(f"⚡ Tốc độ: {self.speed}x")
        logger.info(f"📊 Tìm thấy {len(text_files)} file text")
        logger.info("=" * 60)
        
        success = 0
        failed = 0
        
        for i, text_file in enumerate(text_files, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"[{i}/{len(text_files)}] Xử lý: {text_file.name}")
            
            result = await self.process_text_file(text_file)
            
            if result:
                success += 1
            else:
                failed += 1
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 KẾT QUẢ:")
        logger.info(f"  ✅ Thành công: {success}/{len(text_files)}")
        logger.info(f"  ❌ Thất bại: {failed}/{len(text_files)}")
        logger.info(f"  📁 Thư mục output: {AUDIO_OUTPUT_DIR}")
        logger.info("=" * 60)

def main():
    # Tạo converter
    converter = EdgeTTSConverter()
    
    # Chạy
    asyncio.run(converter.process_all_files())

if __name__ == "__main__":
    main()