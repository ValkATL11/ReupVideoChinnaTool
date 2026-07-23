# audio_to_text.py
import os
import time
import logging
import json
from pathlib import Path
from groq import Groq

# ==================== CẤU HÌNH ====================
# PASTE API KEY CỦA BẠN VÀO ĐÂY
GROQ_API_KEY = ""  # ← Paste key vào đây

# CẤU HÌNH NGÔN NGỮ
# "auto" - tự động phát hiện ngôn ngữ
# "zh" - tiếng Trung
# "vi" - tiếng Việt
# "en" - tiếng Anh
LANGUAGE = "auto"  # Để auto để tự động phát hiện ngôn ngữ gốc
# =================================================

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class AudioToTextConverter:
    def __init__(self, api_key):
        """
        Khởi tạo converter với Groq API key
        
        Args:
            api_key: Groq API key
        """
        self.api_key = api_key
        self.client = Groq(api_key=api_key)
        self.model = "whisper-large-v3-turbo"
        
    def transcribe_audio(self, audio_path, language="auto", response_format="verbose_json"):
        """
        Chuyển đổi audio thành text với timestamp
        
        Args:
            audio_path: Đường dẫn file audio
            language: Ngôn ngữ (auto, zh, vi, en, ...)
            response_format: Định dạng trả về (verbose_json để có timestamp)
        
        Returns:
            Dictionary chứa kết quả transcription với timestamp
        """
        try:
            logger.info(f"Đang chuyển đổi: {os.path.basename(audio_path)}")
            
            # Đọc file audio
            with open(audio_path, "rb") as file:
                # Upload file lên Groq
                # Nếu language = "auto" thì không truyền tham số language
                if language == "auto":
                    transcription = self.client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), file.read()),
                        model=self.model,
                        response_format=response_format,
                        timestamp_granularities=["segment"]
                    )
                else:
                    transcription = self.client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), file.read()),
                        model=self.model,
                        language=language,
                        response_format=response_format,
                        timestamp_granularities=["segment"]
                    )
            
            # Xử lý response - Groq trả về object hoặc dict tùy thuộc vào response_format
            if response_format == "verbose_json":
                # Nếu là object, chuyển thành dict
                if hasattr(transcription, 'model_dump'):
                    data = transcription.model_dump()
                elif hasattr(transcription, '__dict__'):
                    data = transcription.__dict__
                else:
                    data = transcription
                
                # Nếu data là dict
                if isinstance(data, dict):
                    result = {
                        "text": data.get("text", ""),
                        "language": data.get("language", language),
                        "duration": data.get("duration", 0),
                        "segments": []
                    }
                    
                    # Lấy segments với timestamp
                    segments = data.get("segments", [])
                    for segment in segments:
                        result["segments"].append({
                            "start": segment.get("start", 0) if isinstance(segment, dict) else segment.start,
                            "end": segment.get("end", 0) if isinstance(segment, dict) else segment.end,
                            "text": segment.get("text", "") if isinstance(segment, dict) else segment.text,
                            "tokens": segment.get("tokens", []) if isinstance(segment, dict) else getattr(segment, 'tokens', [])
                        })
                else:
                    # Nếu là object
                    result = {
                        "text": getattr(transcription, 'text', ''),
                        "language": getattr(transcription, 'language', language),
                        "duration": getattr(transcription, 'duration', 0),
                        "segments": []
                    }
                    
                    segments = getattr(transcription, 'segments', [])
                    for segment in segments:
                        result["segments"].append({
                            "start": getattr(segment, 'start', 0),
                            "end": getattr(segment, 'end', 0),
                            "text": getattr(segment, 'text', ''),
                            "tokens": getattr(segment, 'tokens', [])
                        })
                
                logger.info(f"✓ Chuyển đổi thành công! Ngôn ngữ: {result['language']}, Độ dài: {len(result['text'])} ký tự")
                return result
            else:
                # response_format = "json" hoặc "text"
                if isinstance(transcription, dict):
                    return {
                        "text": transcription.get("text", str(transcription)),
                        "segments": []
                    }
                else:
                    return {
                        "text": str(transcription),
                        "segments": []
                    }
                
        except Exception as e:
            logger.error(f"Lỗi khi chuyển đổi: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_transcription(self, result, output_path, format_type="txt"):
        """
        Lưu kết quả transcription ra file
        
        Args:
            result: Kết quả từ transcribe_audio
            output_path: Đường dẫn file output
            format_type: Định dạng output (txt, json, srt)
        """
        if not result:
            logger.error("Không có dữ liệu để lưu")
            return False
        
        try:
            if format_type == "txt":
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(result["text"])
                    
            elif format_type == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                    
            elif format_type == "srt":
                with open(output_path, 'w', encoding='utf-8') as f:
                    segments = result.get("segments", [])
                    if not segments:
                        # Nếu không có segments, tạo 1 segment từ toàn bộ text
                        f.write("1\n")
                        f.write("00:00:00,000 --> 00:00:00,000\n")
                        f.write(f"{result['text'].strip()}\n\n")
                    else:
                        for i, segment in enumerate(segments, 1):
                            start = self._format_timestamp(segment["start"])
                            end = self._format_timestamp(segment["end"])
                            f.write(f"{i}\n")
                            f.write(f"{start} --> {end}\n")
                            f.write(f"{segment['text'].strip()}\n\n")
            
            logger.info(f"✓ Đã lưu: {os.path.basename(output_path)}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu file: {e}")
            return False
    
    def _format_timestamp(self, seconds):
        """Chuyển đổi giây sang định dạng HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def main():
    # Kiểm tra API key
    if not GROQ_API_KEY or GROQ_API_KEY == "gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
        logger.error("❌ Bạn chưa paste API key vào code!")
        logger.info("📝 Hướng dẫn:")
        logger.info("   1. Mở file audio_to_text.py")
        logger.info("   2. Tìm dòng: GROQ_API_KEY = 'gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'")
        logger.info("   3. Paste API key của bạn vào đó")
        logger.info("   4. Lưu file và chạy lại")
        return
    
    # Đường dẫn thư mục
    base_dir = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1"
    audio_dir = os.path.join(base_dir, "audio")
    text_dir = os.path.join(base_dir, "text")
    
    # Tạo thư mục text nếu chưa có
    Path(text_dir).mkdir(parents=True, exist_ok=True)
    
    # Lấy danh sách file MP3 trong thư mục audio
    audio_files = list(Path(audio_dir).glob("*.mp3"))
    
    # Nếu không có file MP3, thử tìm các định dạng khác
    if not audio_files:
        audio_files = list(Path(audio_dir).glob("*.wav"))
    if not audio_files:
        audio_files = list(Path(audio_dir).glob("*.m4a"))
    if not audio_files:
        audio_files = list(Path(audio_dir).glob("*.flac"))
    
    if not audio_files:
        logger.warning(f"Không tìm thấy file audio nào trong: {audio_dir}")
        logger.info("Hỗ trợ các định dạng: .mp3, .wav, .m4a, .flac")
        return
    
    logger.info("=" * 60)
    logger.info(f"📁 Thư mục audio: {audio_dir}")
    logger.info(f"📁 Thư mục output: {text_dir}")
    logger.info(f"📊 Tìm thấy {len(audio_files)} file audio")
    logger.info(f"🌐 Ngôn ngữ: {LANGUAGE.upper() if LANGUAGE != 'auto' else 'Tự động phát hiện'}")
    logger.info("=" * 60)
    
    # Khởi tạo converter
    converter = AudioToTextConverter(GROQ_API_KEY)
    
    success = 0
    failed = 0
    skipped = 0
    
    for i, audio_file in enumerate(audio_files, 1):
        logger.info(f"\n[{i}/{len(audio_files)}] Xử lý: {audio_file.name}")
        
        # Tạo tên file output
        base_name = audio_file.stem
        txt_path = Path(text_dir) / f"{base_name}.txt"
        
        # Kiểm tra file đã tồn tại
        if txt_path.exists():
            logger.info(f"⏭ File {base_name}.txt đã tồn tại, bỏ qua")
            skipped += 1
            continue
        
        # Chuyển đổi audio với ngôn ngữ đã cấu hình
        result = converter.transcribe_audio(str(audio_file), language=LANGUAGE)
        
        if result:
            # Lưu các định dạng
            converter.save_transcription(result, Path(text_dir) / f"{base_name}.txt", "txt")
            converter.save_transcription(result, Path(text_dir) / f"{base_name}.json", "json")
            converter.save_transcription(result, Path(text_dir) / f"{base_name}.srt", "srt")
            
            logger.info(f"✅ Thành công: {audio_file.name}")
            success += 1
        else:
            logger.error(f"❌ Thất bại: {audio_file.name}")
            failed += 1
        
        # Đợi giữa các lần gọi API để tránh rate limit
        if i < len(audio_files):
            logger.info("⏳ Đợi 3 giây trước khi xử lý file tiếp theo...")
            time.sleep(3)
    
    # Tổng kết
    logger.info("\n" + "=" * 60)
    logger.info("📊 KẾT QUẢ:")
    logger.info(f"  ✅ Thành công: {success}/{len(audio_files)}")
    logger.info(f"  ❌ Thất bại: {failed}/{len(audio_files)}")
    logger.info(f"  ⏭ Bỏ qua (đã tồn tại): {skipped}/{len(audio_files)}")
    logger.info(f"  📁 Thư mục output: {text_dir}")
    
    # Hiển thị danh sách file đã tạo
    if success > 0:
        logger.info("\n📄 Các file đã tạo:")
        txt_files = list(Path(text_dir).glob("*.txt"))
        for txt_file in sorted(txt_files):
            size = txt_file.stat().st_size
            logger.info(f"  - {txt_file.name} ({size/1024:.1f} KB)")
    
    logger.info("=" * 60)
    logger.info("✅ HOÀN THÀNH!")

if __name__ == "__main__":
    main()